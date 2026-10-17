"""A3-Gegenproben zu T-13 (Besitz A3): Empfehlungsregeln ADV-xx, Akut-Hinweis, Fälligkeit, Diagnose.

Läuft gegen den echten Inhalt; die Erwartungen kommen aus der unabhängigen Referenz
(`a3_triage_ref.py`: ADV-Prüfer) und eigener Neuberechnung (rote Regeln, Fälligkeit, Prager Zeit).
"""

import copy
import random
import re
import shutil
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import a3_triage_ref as ref
from app.adapters.memory_notifier import MemoryNotifier
from app.main import create_app
from app.persistence.models import AuditEvent
from app.services import seed
from conftest import CSRF, login, make_settings, migrate, run_parallel
from test_a3_t04a import MutableClock
from test_config_admin import current_rules, put_rules
from waechter import notifier
from waechter.constants import CONTENT_DIR_ENV
from waechter.models import Answer, Patient, Response, Therapy

BASE = "/api/v1/waechter"
CEST = timezone(timedelta(hours=2))
CET = timezone(timedelta(hours=1))


def _last_sunday(year: int, month: int) -> date:
    day = date(year, month, 31)
    return day - timedelta(days=(day.weekday() + 1) % 7)


def prague_offset(utc: datetime) -> timedelta:
    """EU-Sommerzeit (eigene Regel): letzter Sonntag März 01:00 UTC bis letzter Sonntag Oktober."""
    start = datetime.combine(_last_sunday(utc.year, 3), datetime.min.time(), UTC) + timedelta(
        hours=1
    )
    end = datetime.combine(_last_sunday(utc.year, 10), datetime.min.time(), UTC) + timedelta(
        hours=1
    )
    return timedelta(hours=2) if start <= utc.astimezone(UTC) < end else timedelta(hours=1)


def local_date(utc: datetime) -> date:
    return (utc.astimezone(UTC) + prague_offset(utc)).date()


def local_midnight(day: date) -> datetime:
    """Beginn des Prager Kalendertags als UTC-Instant."""
    naive = datetime.combine(day, datetime.min.time(), UTC)
    for offset in (timedelta(hours=2), timedelta(hours=1)):
        candidate = naive - offset
        if prague_offset(candidate) == offset:
            return candidate
    raise AssertionError(day)


CONTENT = Path(__file__).resolve().parents[1] / "content"
ANCHOR = datetime(2026, 10, 17, 7, 0, tzinfo=UTC)
ADVICE_YAML = yaml.safe_load((CONTENT / "advice.yaml").read_text(encoding="utf-8"))
SCHEDULE = yaml.safe_load((CONTENT / "schedule.yaml").read_text(encoding="utf-8"))
RULES = ref.advice_rules_from(ADVICE_YAML)
ALWAYS_ACUTE = set(ADVICE_YAML["escalation"].get("always_acute_for", []))
FORBIDDEN_KEYS = {"level", "triage", "traffic_light", "alert", "alerts", "grade", "rule_text"}


@pytest.fixture(scope="module")
def real_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Einmal geseedete Datenbank mit dem echten Inhalt (Kopiervorlage; spart Laufzeit)."""
    base = tmp_path_factory.mktemp("t13")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(CONTENT_DIR_ENV, str(CONTENT))
        settings = make_settings(base)
        migrate(settings)
        app = create_app(settings)
        previous = notifier.get_notifier()
        notifier.set_notifier(MemoryNotifier())
        try:
            with app.state.session_factory() as session:
                seed.provision(session, settings, app.state.registry, app.state.clock)
                session.commit()
        finally:
            notifier.set_notifier(previous)
            app.state.engine.dispose()
    return base / "wa.db"


@pytest.fixture
def api(
    real_template: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[FastAPI, MutableClock]]:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(CONTENT))
    shutil.copy(real_template, tmp_path / "wa.db")
    app = create_app(make_settings(tmp_path))
    clock = MutableClock(ANCHOR)
    app.state.clock = clock
    yield app, clock
    app.state.engine.dispose()


def client_for(app: FastAPI, username: str) -> TestClient:
    client = TestClient(app, headers=CSRF)
    client.__enter__()
    login(client, username)
    return client


def questionnaire(client: TestClient, **params: str) -> dict[str, Any]:
    response = client.get(f"{BASE}/me/questionnaire", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def fields_of(body: dict[str, Any]) -> list[tuple[str, str, list[int]]]:
    return [
        (item["symptom_key"], q["attribute"], [o["value"] for o in q["options"]])
        for item in body["items"]
        for q in item["questions"]
    ]


def submit(
    client: TestClient,
    body: dict[str, Any],
    answers: dict[tuple[str, str], int | None],
    csid: str | None = None,
    qid: str | None = None,
) -> Any:
    payload = {
        "client_submission_id": csid or str(uuid.uuid4()),
        "questionnaire_id": qid or body["questionnaire_id"],
        "answers": [
            {"symptom_key": s, "attribute": a, "value": v} for (s, a), v in answers.items()
        ],
    }
    return client.post(f"{BASE}/me/responses", json=payload)


def red_symptoms(answers: dict[tuple[str, str], int | None]) -> set[str]:
    """Unabhängig aus rules.yaml: R-SEV-01 (severity/interference >= 3), R-URG-01 (Fieber ja)."""
    found = {
        s
        for (s, a), v in answers.items()
        if a in {"severity", "interference"} and v is not None and v >= 3
    }
    if (answers.get(("fever", "presence")) or 0) >= 1:
        found.add("fever")
    return found


def grouped(answers: dict[tuple[str, str], int | None]) -> dict[str, dict[str, int | None]]:
    out: dict[str, dict[str, int | None]] = {}
    for (symptom, attribute), value in answers.items():
        out.setdefault(symptom, {})[attribute] = value
    return out


# --- Beleg gegen die Referenz ---


def test_a3_receipt_matches_the_reference_on_random_answer_sets(api: Any) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    body = questionnaire(client)
    fields = fields_of(body)
    rng = random.Random(13)  # noqa: S311 - fester Seed
    rules_by_id = {r["id"]: r for r in ADVICE_YAML["advice"]}
    problems: list[str] = []
    for _ in range(80):
        answers: dict[tuple[str, str], int | None] = {}
        for symptom, attribute, values in fields:
            roll = rng.random()
            answers[(symptom, attribute)] = (
                None if roll < 0.1 else rng.choice(values) if roll < 0.6 else values[0]
            )
        response = submit(client, body, answers)
        assert response.status_code == 201, response.text
        receipt = response.json()
        grades = grouped(answers)
        red = red_symptoms(answers)
        want = ref.evaluate_recommendations(RULES, grades, red, ALWAYS_ACUTE)
        shown_want = {i for i, status in want.items() if status == "shown"}
        shown_ids = {r["rule_id"] for r in receipt["advice"]}
        got = {i: ("shown" if i in shown_ids else "suppressed_acute") for i in want}
        problems += ref.check_recommendations(
            RULES, grades, red, ALWAYS_ACUTE, got, sorted(shown_ids)
        )
        acute_want = bool(red) or any(
            (answers.get((s, a)) or 0) >= 1 for s in ALWAYS_ACUTE for a in ("presence", "severity")
        )
        level = receipt["escalation"]["level"]
        if (level == "acute") != acute_want:
            problems.append(f"Eskalation {level}, erwartet acute={acute_want} bei {answers}")
        for block in receipt["advice"]:
            if block["rule_id"] not in shown_want:
                continue
            cs = [t["cs"] for t in rules_by_id[block["rule_id"]]["tips"]]
            if block["tips"] != cs:
                problems.append(f"{block['rule_id']}: Tipps weichen von advice.yaml ab")
        assert not FORBIDDEN_KEYS & set(receipt), set(receipt)
        assert receipt["escalation"]["ambulance_phone"] in (None, "")  # Platzhalter nie ausliefern
        assert "[" not in receipt["escalation"]["text"]
    assert problems == [], problems[:5]


@pytest.mark.parametrize("rule", [r for r in RULES if r.symptom_key not in ALWAYS_ACUTE])
def test_a3_each_rule_fires_exactly_at_its_range_boundaries(api: Any, rule: ref.AdviceRule) -> None:
    app, _ = api
    for user in ("patient2", "patient"):  # ICI bzw. FOLFOX: zusammen alle Symptome
        client = client_for(app, user)
        body = questionnaire(client)
        fields = [f for f in fields_of(body) if f[0] == rule.symptom_key]
        if not fields:
            continue
        symptom, attribute, values = fields[0]
        for value in sorted(set(values)):
            answers: dict[tuple[str, str], int | None] = {(symptom, attribute): value}
            response = submit(client, body, answers)
            assert response.status_code == 201, response.text
            ids = {r["rule_id"] for r in response.json()["advice"]}
            suppressed = symptom in red_symptoms(answers)
            should = rule.min_value <= value <= rule.max_value and not suppressed
            assert (rule.id in ids) == should, (user, rule.id, value, ids)
        return
    pytest.skip(f"{rule.symptom_key} steht in keinem Fragebogen der Demo-Patientinnen")


@pytest.mark.parametrize("symptom", sorted(ALWAYS_ACUTE))
def test_a3_fever_and_breathlessness_never_get_tips_only_the_acute_notice(
    api: Any, symptom: str
) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    body = questionnaire(client)
    fields = [f for f in fields_of(body) if f[0] == symptom]
    if not fields:
        pytest.skip(f"{symptom} nicht im Fragebogen")
    s, attribute, values = fields[0]
    for value in sorted(set(values) - {0}):
        receipt = submit(client, body, {(s, attribute): value}).json()
        assert receipt["escalation"]["level"] == "acute", (symptom, value)
        assert [b for b in receipt["advice"] if b["symptom_key"] == symptom] == []


def test_a3_replay_returns_the_same_receipt_and_parallel_replays_agree(api: Any) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    body = questionnaire(client)
    answers: dict[tuple[str, str], int | None] = {("nausea", "severity"): 2}
    csid = str(uuid.uuid4())
    first = submit(client, body, answers, csid)
    assert first.status_code == 201
    again = submit(client, body, answers, csid)
    assert again.status_code == 200
    assert again.json() == {**first.json()}
    clients = [client_for(app, "patient2") for _ in range(4)]
    results = run_parallel(lambda i: submit(clients[i], body, answers, csid).json(), 4)
    assert all(r == first.json() for r in results)


def test_a3_replay_receipt_stays_stable_when_the_rules_change_in_between(api: Any) -> None:
    """Der Akut-Hinweis eines Belegs darf sich nach einer späteren Regeländerung nicht ändern."""
    app, _ = api
    client = client_for(app, "patient2")
    body = questionnaire(client)
    csid = str(uuid.uuid4())
    answers: dict[tuple[str, str], int | None] = {("diarrhea", "severity"): 3}
    first = submit(client, body, answers, csid).json()
    assert first["escalation"]["level"] == "acute"
    admin = client_for(app, "admin")
    version, rules = current_rules(app)
    changed = copy.deepcopy(rules)
    next(r for r in changed["rules"] if r["id"] == "R-SEV-01")["params"]["min_value"] = 4
    assert put_rules(admin, version, changed).status_code == 200
    again = submit(client, body, answers, csid).json()
    assert again["escalation"] == first["escalation"]
    assert again["advice"] == first["advice"]


# --- /me/advice ---


def test_a3_help_page_hides_tips_for_acute_symptoms_and_is_patient_only(api: Any) -> None:
    app, _ = api
    patient = client_for(app, "patient2")
    page = patient.get(f"{BASE}/me/advice", params={"lang": "cs"})
    assert page.status_code == 200
    data = page.json()
    own = {i["symptom_key"] for i in questionnaire(patient)["items"]}
    assert {r["symptom_key"] for r in data["advice"]} <= own  # nur der eigene Fragebogen
    for rule in data["advice"]:
        if rule["symptom_key"] in ALWAYS_ACUTE:
            assert rule["acute_only"] is True
            assert rule["tips"] == []
            assert rule["sources"] == []
        else:
            assert rule["tips"], rule["rule_id"]
    assert "[" not in str(data["escalation"]["acute"])
    assert data["escalation"]["ambulance_phone"] in (None, "")
    assert client_for(app, "doctor").get(f"{BASE}/me/advice").status_code == 403
    assert client_for(app, "admin").get(f"{BASE}/me/advice").status_code == 403
    anonymous = TestClient(app, headers=CSRF)
    assert anonymous.get(f"{BASE}/me/advice").status_code == 401
    assert patient.get(f"{BASE}/me/advice", params={"lang": "xx"}).status_code in (200, 422)


@pytest.mark.parametrize("lang", ["cs", "en", "de"])
def test_a3_patient_texts_of_the_help_page_pass_the_forbidden_list(api: Any, lang: str) -> None:
    app, _ = api
    data = client_for(app, "patient2").get(f"{BASE}/me/advice", params={"lang": lang}).json()
    texts = [data["escalation"]["general"], data["escalation"]["acute"]]
    texts += [t for r in data["advice"] for t in r["tips"]]
    for text in texts:
        assert not re.search(
            r"ampel|semafor|traffic|alarm|\balert|diagnos|diagnóz|doporuč|recommend|empfehl"
            r"|keine sorge|don.?t worry|nemusíte se bát|v pořádku|we will (contact|call)|ozveme se"
            r"|zavoláme|wir (melden|rufen)",
            text,
            re.IGNORECASE,
        ), text


# --- Audit ---


def test_a3_advice_shown_audit_contains_only_rule_ids(api: Any) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    body = questionnaire(client)
    receipt = submit(client, body, {("nausea", "severity"): 2}).json()
    with app.state.session_factory() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "advice_shown")
        ).all()
    assert events
    for event in events:
        assert set(event.details_json) <= {"rules", "count", "acute"}
        assert "Popíj" not in str(event.details_json)
    assert any(r["rule_id"] in str(e.details_json) for e in events for r in receipt["advice"])


# -- Diagnose-Auswahl --------------------------------------------------------


@pytest.mark.parametrize(
    ("user", "group"),
    [("patient", "COLORECTAL"), ("patient2", "MELANOMA")],
)
def test_a3_questionnaire_id_names_regimen_and_group_and_old_ids_still_work(
    api: Any, user: str, group: str
) -> None:
    app, _ = api
    client = client_for(app, user)
    body = questionnaire(client)
    assert body["questionnaire_id"].endswith(f":{group}")
    assert body["diagnosis_group"] == group or body["diagnosis_group"].get("id") == group
    first = fields_of(body)[0]
    answers: dict[tuple[str, str], int | None] = {(first[0], first[1]): first[2][0]}
    old = body["questionnaire_id"].rsplit(":", 1)[0]
    assert submit(client, body, answers, qid=old).status_code == 201  # alte ID bleibt gültig
    wrong = body["questionnaire_id"].rsplit(":", 1)[0] + ":BREAST"
    assert submit(client, body, answers, qid=wrong).status_code == 422
    assert submit(client, body, answers, qid="items-v1:NOPE:none").status_code == 422


@pytest.mark.parametrize(
    ("code", "group"),
    [
        ("C50.9", "BREAST"),
        ("C34.1", "LUNG"),
        ("C99", "none"),
        (None, "none"),
        ("", "none"),
        ("X", "none"),
    ],
)
def test_a3_diagnosis_code_selects_the_group_and_unknown_codes_mean_none(
    api: Any, code: str | None, group: str
) -> None:
    app, _ = api
    with app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0002")).one()
        patient.diagnosis_code = code
        session.commit()
    body = questionnaire(client_for(app, "patient2"))
    assert body["questionnaire_id"].endswith(f":{group}"), body["questionnaire_id"]
    if group == "LUNG":
        sources = {i["symptom_key"]: i.get("source") for i in body["items"]}
        assert sources.get("shortness_of_breath") in {"diagnosis", "regimen", "core"}
    text = (body.get("selection_reason") or "").lower()
    assert "diagnos" not in text
    assert "diagnóz" not in text


# --- Fälligkeit (Prager Zeit, Sommerzeitwechsel) ---


def expected_due(cycle_start: datetime, last: datetime | None) -> tuple[datetime, int]:
    default = int(SCHEDULE["default_interval_days"])

    def day_of(moment: datetime) -> int:
        return (local_date(moment) - local_date(cycle_start)).days + 1

    if last is None:
        return cycle_start, interval_for(day_of(cycle_start), default)
    day = day_of(last)
    interval = interval_for(day, default)
    midnight = local_midnight(local_date(last) + timedelta(days=interval))
    return midnight, interval


def interval_for(cycle_day: int, default: int) -> int:
    if cycle_day < 1:
        return default
    for phase in SCHEDULE.get("phases", []):
        if phase["from_cycle_day"] <= cycle_day <= phase["to_cycle_day"]:
            return int(phase["interval_days"])
    return default


def clear_responses(app: FastAPI) -> None:
    """Seed-Antworten von SYN-0002 entfernen: nur die eingefügte Antwort bestimmt die Fälligkeit."""
    with app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0002")).one()
        ids = list(session.scalars(select(Response.id).where(Response.patient_id == patient.id)))
        session.execute(delete(Answer).where(Answer.response_id.in_(ids)))
        session.execute(delete(Response).where(Response.id.in_(ids)))
        session.commit()


def add_response(app: FastAPI, at: datetime, value: int | None = 1) -> None:
    with app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0002")).one()
        row = Response(
            patient_id=patient.id,
            client_submission_id=str(uuid.uuid4()),
            channel="web",
            entered_by="self",
            recorded_at=at,
            questionnaire_id="x",
            synthetic=True,
        )
        session.add(row)
        session.flush()
        session.add(
            Answer(response_id=row.id, symptom_key="nausea", attribute="severity", value=value)
        )
        session.commit()


@pytest.mark.parametrize(
    "last_local",
    [
        datetime(2026, 10, 24, 21, 30, tzinfo=CEST),  # Sommerzeit endet in der Nacht auf den 25.
        datetime(2026, 10, 25, 1, 15, tzinfo=CEST),
        datetime(2026, 10, 12, 23, 59, tzinfo=CEST),  # Zyklustag > 10 ⇒ Standardintervall
        datetime(2026, 10, 10, 0, 1, tzinfo=CEST),
        datetime(2026, 10, 9, 8, 0, tzinfo=CEST),  # vor Zyklusbeginn ⇒ Standardintervall
        datetime(2026, 10, 25, 12, 0, tzinfo=CET),  # nach dem Wechsel (Winterzeit)
        datetime(2026, 10, 26, 0, 30, tzinfo=CET),
    ],
)
def test_a3_due_matches_an_independent_calculation_across_dst_and_phases(
    api: Any, last_local: datetime
) -> None:
    app, clock = api
    with app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0002")).one()
        therapy = session.scalars(select(Therapy).where(Therapy.patient_id == patient.id)).first()
        assert therapy is not None
        cycle_start = therapy.cycle_start.astimezone(UTC)
    clear_responses(app)
    add_response(app, last_local.astimezone(UTC))
    clock.instant = last_local.astimezone(UTC) + timedelta(hours=1)
    client = client_for(app, "patient2")
    due = questionnaire(client)["due"]
    want, interval = expected_due(cycle_start, last_local.astimezone(UTC))
    got = datetime.fromisoformat(due["next_due_at"])
    assert got == want, (due, want)
    assert due["interval_days"] == interval
    assert due["overdue"] is (clock.instant >= want)
    clock.instant = want + timedelta(minutes=1)
    assert questionnaire(client_for(app, "patient2"))["due"]["overdue"] is True
    clock.instant = want - timedelta(minutes=1)
    assert questionnaire(client_for(app, "patient2"))["due"]["overdue"] is False


def test_a3_only_skipped_answers_do_not_move_the_due_date(api: Any) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    before = questionnaire(client)["due"]
    add_response(app, ANCHOR - timedelta(hours=1), value=None)
    after = questionnaire(client_for(app, "patient2"))["due"]
    assert after["next_due_at"] == before["next_due_at"]
    assert date.fromisoformat(after["next_due_at"][:10])


# --- Datenschutz: ICD-Code ---


def test_a3_icd_code_never_reaches_patient_endpoints_or_the_fhir_export(api: Any) -> None:
    app, _ = api
    with app.state.session_factory() as session:
        codes = [c for c in session.scalars(select(Patient.diagnosis_code)) if c]
    assert codes
    patient = client_for(app, "patient")
    body = questionnaire(patient)
    first = fields_of(body)[0]
    receipt = submit(patient, body, {(first[0], first[1]): first[2][0]})
    texts = [str(body), receipt.text, patient.get(f"{BASE}/me/advice").text]
    texts.append(patient.get(f"{BASE}/me/responses").text)
    for text in texts:
        for code in codes:
            assert code not in text, code
    doctor = client_for(app, "doctor")
    with app.state.session_factory() as session:
        pid = session.scalars(select(Patient.id).where(Patient.pseudonym == "SYN-0001")).one()
    # Vertrag v2.6 / T-18 (A0, Integration 4b): der Export trägt die Diagnose bewusst als Condition
    # mit ICD-10. Der Code darf nur in dieser Condition stehen: Condition.code.coding[].code (System
    # ICD-10) und ihre Narrative Condition.text.div; nirgends sonst (Patient, Observations).
    icd = "http://hl7.org/fhir/sid/icd-10"
    for kind in ("collection", "transaction"):
        export = doctor.get(f"{BASE}/patients/{pid}/fhir", params={"type": kind}).json()
        hits: list[str] = []

        def walk(node: Any, path: str, hits: list[str] = hits) -> None:
            if isinstance(node, dict):
                base = node.get("resourceType", path)
                if base == "Condition.text":
                    return
                for key, value in node.items():
                    if key == "data":  # Base64-Anhänge (Zufallsbytes) nicht als Text lesen
                        continue
                    allowed = (
                        key == "code"
                        and node.get("system") == icd
                        and base == "Condition.code.coding"
                    )
                    if not allowed:
                        walk(value, f"{base}.{key}")
            elif isinstance(node, list):
                for item in node:
                    walk(item, path)
            elif isinstance(node, str):
                hits.extend(f"{path}: {code}" for code in codes if code in node)

        walk(export, "")
        assert hits == [], (kind, hits)
