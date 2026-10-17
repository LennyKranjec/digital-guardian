"""T-13 (Vertrag v1.9/v1.10/v2.1): Diagnose-Auswahl, Intervall, Empfehlungsregeln ADV-xx, Rady.

Läuft gegen den **echten** Inhalt (`challenge/content/`), feste Ankerzeit, kein Tagesdatum, keine
Seed-Anzahlen. Patiententexte werden gegen die Verbotsliste des Frontends (`forbidden.ts`) und gegen
die Wortlisten der Inhaltsprüfung geprüft.
"""

import copy
import re
import shutil
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.persistence.models import AuditEvent
from conftest import login
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import Content, ContentError, load_content
from waechter.models import Patient, Response, Therapy
from waechter.services import advice as advice_service
from waechter.services.advice import (
    SHOWN,
    SUPPRESSED_ACUTE,
    Recommendation,
    is_acute,
    phone_or_none,
    recommendations_for,
)
from waechter.services.questionnaire import (
    NO_GROUP,
    diagnosis_group_for,
    due_for,
    interval_for,
    select_for_regimen,
)

REAL = Path(__file__).resolve().parents[1] / "content"
BASE = "/api/v1/waechter"
QUESTIONNAIRE = f"{BASE}/me/questionnaire"
RESPONSES = f"{BASE}/me/responses"
ADVICE = f"{BASE}/me/advice"
LANGS = ("cs", "en", "de")


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


@pytest.fixture(scope="module")
def content() -> Content:
    return load_content(REAL)


def app_of(client: TestClient) -> FastAPI:
    application = client.app
    assert isinstance(application, FastAPI)
    return application


def forbidden_phrases() -> list[str]:
    """Phrasen aus `forbidden.ts` (Patiententexte, erstes Feld `FORBIDDEN_PHRASES`)."""
    source = (REAL.parent / "frontend" / "waechter" / "i18n" / "forbidden.ts").read_text(
        encoding="utf-8"
    )
    block = source.split("FORBIDDEN_PHRASES", 1)[1].split("];", 1)[0]
    phrases = [
        m.group(1) or m.group(2)
        for line in block.splitlines()
        if (m := re.match(r"""^\s*(?:'([^']+)'|"([^"]+)"),""", line))
    ]
    assert len(phrases) >= 30
    return phrases


EXTRA_FORBIDDEN = re.compile(
    r"ampel|semafor|traffic|\balert|červen|žlut|\bred\b|yellow|\bgrade\b|stupeň|ctcae|diagnos"
    r"|diagnóz|doporuč|recommend|empfehl|keine sorge|don.?t worry|no need to worry|v pořádku"
    r"|we will (contact|call)|ozveme se|zavoláme|wir (melden|rufen)|notfall|emergency|nouz",
    re.IGNORECASE,
)


def assert_patient_safe(text: str) -> None:
    lower = text.lower()
    assert not [p for p in forbidden_phrases() if p in lower], text
    assert EXTRA_FORBIDDEN.search(text) is None, text


def submission(
    answers: Sequence[tuple[str, str, int | None]], questionnaire_id: str
) -> dict[str, Any]:
    return {
        "client_submission_id": str(uuid.uuid4()),
        "questionnaire_id": questionnaire_id,
        "answers": [{"symptom_key": s, "attribute": a, "value": v} for s, a, v in answers],
    }


def questionnaire_id(client: TestClient) -> str:
    return str(client.get(QUESTIONNAIRE).json()["questionnaire_id"])


def send(client: TestClient, answers: Sequence[tuple[str, str, int | None]]) -> dict[str, Any]:
    reply = client.post(RESPONSES, json=submission(answers, questionnaire_id(client)))
    assert reply.status_code == 201, reply.text
    body: dict[str, Any] = reply.json()
    return body


def audit_events(app: FastAPI, action: str) -> list[AuditEvent]:
    with app.state.session_factory() as session:
        return list(session.scalars(select(AuditEvent).where(AuditEvent.action == action)))


def set_diagnosis(app: FastAPI, pseudonym: str, code: str | None) -> None:
    with app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == pseudonym)).one()
        patient.diagnosis_code = code
        session.commit()


# ---- Diagnose-Auswahl ------------------------------------------------------------------------
def test_seed_stores_the_synthetic_icd_code(seeded_app: FastAPI) -> None:
    with seeded_app.state.session_factory() as session:
        codes = {p.pseudonym: p.diagnosis_code for p in session.scalars(select(Patient))}
    assert codes["SYN-0001"] == "C18.7"
    assert codes["SYN-0002"] == "C43.9"


@pytest.mark.parametrize(
    ("code", "group"),
    [
        ("C18.7", "COLORECTAL"),
        ("C18", "COLORECTAL"),
        ("c19", "COLORECTAL"),
        ("C20", "COLORECTAL"),
        ("C43.9", "MELANOMA"),
        ("C50.9", "BREAST"),
        ("C34.1", "LUNG"),
        ("C180", None),
        ("C21", None),
        ("C77.0", None),
        ("", None),
        (None, None),
    ],
)
def test_diagnosis_group_is_matched_by_icd_prefix(
    content: Content, code: str | None, group: str | None
) -> None:
    found = diagnosis_group_for(content, code)
    assert (found["id"] if found else None) == group


def test_questionnaire_of_the_colorectal_patient_names_therapy_and_group(
    client: TestClient,
) -> None:
    login(client, "patient")
    data = client.get(QUESTIONNAIRE, params={"lang": "en"}).json()
    assert data["questionnaire_id"] == "items-v1:FOLFOX:COLORECTAL"
    assert data["diagnosis_group"] == "COLORECTAL"
    assert data["selection_reason"].startswith("Questions matching your therapy (")
    assert "Colorectal cancer" in data["selection_reason"]
    sources = {i["source"] for i in data["items"]}
    assert sources == {"core", "regimen"}  # COLORECTAL hat bewusst keine Zusatzfragen
    assert [i["source"] for i in data["items"]] == sorted(
        (i["source"] for i in data["items"]), key=["core", "regimen", "diagnosis"].index
    )


def test_lung_patient_gets_the_additional_questions_from_the_diagnosis_group(
    client: TestClient,
) -> None:
    set_diagnosis(app_of(client), "SYN-0001", "C34.1")
    login(client, "patient")
    data = client.get(QUESTIONNAIRE, params={"lang": "cs"}).json()
    assert data["questionnaire_id"] == "items-v1:FOLFOX:LUNG"
    assert data["diagnosis_group"] == "LUNG"
    extra = [i["symptom_key"] for i in data["items"] if i["source"] == "diagnosis"]
    assert extra == ["shortness_of_breath", "decreased_appetite"]
    assert data["items"][-1]["source"] == "diagnosis"  # Reihenfolge: Kern, Regime, Diagnose
    assert_patient_safe(data["selection_reason"])
    reply = client.post(
        RESPONSES,
        json=submission(
            [("shortness_of_breath", "severity", 0), ("fever", "presence", 0)],
            data["questionnaire_id"],
        ),
    )
    assert reply.status_code == 201


def test_questionnaire_without_diagnosis_code_uses_none_and_the_old_texts(
    client: TestClient,
) -> None:
    set_diagnosis(app_of(client), "SYN-0001", None)
    login(client, "patient")
    data = client.get(QUESTIONNAIRE, params={"lang": "en"}).json()
    assert data["questionnaire_id"] == f"items-v1:FOLFOX:{NO_GROUP}"
    assert data["diagnosis_group"] is None
    assert data["selection_reason"].startswith("Questions matching your therapy: ")


def test_old_questionnaire_id_is_still_accepted_and_unknown_ids_are_not(client: TestClient) -> None:
    login(client, "patient")
    answers = [("fever", "presence", 0), ("nausea", "severity", 1)]
    assert client.post(RESPONSES, json=submission(answers, "items-v1:FOLFOX")).status_code == 201
    new = questionnaire_id(client)
    assert client.post(RESPONSES, json=submission(answers, new)).status_code == 201
    wrong = client.post(RESPONSES, json=submission(answers, "items-v1:FOLFOX:LUNG"))
    assert wrong.status_code == 422
    assert wrong.json()["field_errors"][0]["field"] == "questionnaire_id"


def test_select_for_regimen_ignores_an_unknown_group(content: Content) -> None:
    plain = select_for_regimen(content, "FOLFOX")
    unknown = select_for_regimen(content, "FOLFOX", "NO-SUCH-GROUP")
    assert plain is not None
    assert unknown is not None
    assert [i["symptom_key"] for i, _ in plain.items] == [
        i["symptom_key"] for i, _ in unknown.items
    ]
    assert select_for_regimen(content, "NOPE") is None


# ---- Intervall -------------------------------------------------------------------------------
def test_interval_follows_the_cycle_phase(content: Content) -> None:
    assert content.schedule is not None
    first = content.schedule["phases"][0]
    default = content.schedule["default_interval_days"]
    assert interval_for(content.schedule, first["from_cycle_day"]) == first["interval_days"]
    assert interval_for(content.schedule, first["to_cycle_day"]) == first["interval_days"]
    assert interval_for(content.schedule, first["to_cycle_day"] + 1) == default
    assert interval_for(content.schedule, 0) == default


def test_due_uses_last_answer_plus_interval_in_prague_calendar_days(client: TestClient) -> None:
    login(client, "patient")
    due = client.get(QUESTIONNAIRE).json()["due"]
    # SYN-0001: letzte Antwort einen Kalendertag vor dem Anker (Standardintervall 1, DR-041)
    assert due["interval_days"] == 1
    assert due["next_due_at"] == "2026-10-17T00:00:00+02:00"
    assert due["overdue"] is True
    send(client, [("fever", "presence", 0)])  # Antwort am Anker (Zyklustag 15) ⇒ morgen wieder
    after = client.get(QUESTIONNAIRE).json()["due"]
    assert after["next_due_at"] == "2026-10-18T00:00:00+02:00"
    assert after["overdue"] is False


def test_due_without_any_answer_starts_at_the_cycle_start_and_is_overdue(
    client: TestClient, content: Content
) -> None:
    application = app_of(client)
    start = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
    with application.state.session_factory() as session:
        patient = Patient(
            pseudonym="SYN-9999", display_name="Test", birth_year=1970, sex="f", language="cs"
        )
        session.add(patient)
        session.flush()
        session.add(Therapy(patient_id=patient.id, regimen_id="FOLFOX", cycle_start=start))
        session.flush()
        now = datetime(2026, 10, 17, 7, 0, tzinfo=UTC)
        due = due_for(session, patient.id, content, now)
        assert due is not None
        assert due.next_due_at == start
        assert due.overdue is True
        assert due.interval_days == 1  # Zyklustag 1 liegt in der ersten Phase
        early = due_for(session, patient.id, content, start - timedelta(hours=1))
        assert early is not None and early.overdue is False  # noqa: PT018
        session.rollback()


def test_skipped_only_responses_do_not_move_the_due_date(client: TestClient) -> None:
    login(client, "patient")
    before = client.get(QUESTIONNAIRE).json()["due"]
    send(client, [("fever", "presence", None)])
    assert client.get(QUESTIONNAIRE).json()["due"] == before


def test_questionnaire_carries_the_general_escalation_hint_in_each_language(
    client: TestClient, content: Content
) -> None:
    assert content.advice is not None
    login(client, "patient")
    for lang in ("cs", "en"):
        text = client.get(QUESTIONNAIRE, params={"lang": lang}).json()["escalation_general"]
        assert text == content.advice["escalation"]["general"][lang]
        assert "155" in text
    assert client.get(QUESTIONNAIRE, params={"lang": "de"}).json()["escalation_general"]


# ---- Empfehlungsregeln (reine Funktion) ------------------------------------------------------
ADVICE_FILE: dict[str, Any] = {
    "escalation": {"always_acute_for": ["fever"]},
    "advice": [
        {"id": "ADV-A-01", "symptom_key": "a", "min_value": 2, "max_value": 3},
        {"id": "ADV-A-02", "symptom_key": "a", "min_value": 4},
        {"id": "ADV-B-01", "symptom_key": "b", "min_value": 1, "max_value": 4},
        {"id": "ADV-FEVER-01", "symptom_key": "fever", "min_value": 1},
    ],
}


def rec(
    answers: dict[tuple[str, str], int | None], red: tuple[str, ...] = ()
) -> list[tuple[str, str]]:
    return [(r.rule_id, r.status) for r in recommendations_for(ADVICE_FILE, answers, red)]


@pytest.mark.parametrize(
    ("value", "fired"),
    [(0, []), (1, []), (2, ["ADV-A-01"]), (3, ["ADV-A-01"]), (4, ["ADV-A-02"])],
)
def test_rule_fires_exactly_inside_its_range(value: int, fired: list[str]) -> None:
    assert [rule for rule, _ in rec({("a", "severity"): value})] == fired


def test_any_answered_attribute_in_range_fires_and_skipped_never_does() -> None:
    assert rec({("a", "severity"): 0, ("a", "interference"): 2}) == [("ADV-A-01", SHOWN)]
    assert rec({("a", "severity"): None, ("a", "frequency"): None}) == []
    both = rec({("a", "severity"): 3, ("a", "interference"): 4})
    assert both == [("ADV-A-01", SHOWN), ("ADV-A-02", SHOWN)]  # mehrere Regeln je Symptom


def test_value_reported_is_the_highest_matching_attribute_value() -> None:
    found = recommendations_for(ADVICE_FILE, {("a", "severity"): 2, ("a", "interference"): 3}, ())
    assert found == [Recommendation("ADV-A-01", "a", 3, SHOWN)]


def test_red_symptom_and_always_acute_symptoms_are_suppressed() -> None:
    assert rec({("a", "severity"): 2, ("b", "severity"): 1}, red=("a",)) == [
        ("ADV-A-01", SUPPRESSED_ACUTE),
        ("ADV-B-01", SHOWN),
    ]
    assert rec({("fever", "presence"): 1}) == [("ADV-FEVER-01", SUPPRESSED_ACUTE)]


def test_acute_escalation_conditions() -> None:
    assert not is_acute(ADVICE_FILE, {("fever", "presence"): 0, ("a", "severity"): 4}, ())
    assert is_acute(ADVICE_FILE, {("fever", "presence"): 1}, ())
    assert is_acute(
        ADVICE_FILE, {("a", "severity"): 1}, ("a",)
    )  # rote Regel eines anderen Symptoms
    assert not is_acute(ADVICE_FILE, {}, ())


def test_recommendations_are_a_pure_function() -> None:
    answers: dict[tuple[str, str], int | None] = {("a", "severity"): 3, ("b", "severity"): 2}
    snapshot = copy.deepcopy(ADVICE_FILE)
    first = recommendations_for(ADVICE_FILE, answers, ("b",))
    assert first == recommendations_for(ADVICE_FILE, dict(reversed(list(answers.items()))), ("b",))
    assert snapshot == ADVICE_FILE


def test_placeholder_phone_is_never_shown() -> None:
    assert phone_or_none("[telefon ambulance]") is None
    assert phone_or_none(" [ ] ") is None
    assert phone_or_none("") is None
    assert phone_or_none(None) is None
    assert phone_or_none("+420 123 456 789") == "+420 123 456 789"


def test_every_real_advice_rule_has_a_stable_id_and_a_known_symptom(content: Content) -> None:
    assert content.advice is not None
    ids = [r["id"] for r in content.advice["advice"]]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"ADV-[A-Z0-9_]+-\d\d", i) for i in ids)
    symptoms = {i["symptom_key"] for i in content.items["items"]}
    assert {r["symptom_key"] for r in content.advice["advice"]} <= symptoms


# ---- Beleg: Tipps und Eskalation (Echtinhalt, gegen die API) ---------------------------------
def test_fever_gives_acute_escalation_and_no_fever_tips(
    client: TestClient, content: Content
) -> None:
    assert content.advice is not None
    login(client, "patient2")  # SYN-0002, Pembrolizumab, cs
    receipt = send(client, [("fever", "presence", 1), ("fatigue", "severity", 2)])
    assert receipt["escalation"]["level"] == "acute"
    assert receipt["escalation"]["text"] == content.advice["escalation"]["acute"]["cs"]
    assert receipt["escalation"]["ambulance_phone"] is None  # Platzhalter
    rule_ids = [a["rule_id"] for a in receipt["advice"]]
    assert "ADV-FEVER-01" not in rule_ids
    assert rule_ids == ["ADV-FATIGUE-01"]  # Tipps zu anderen Symptomen bleiben
    assert set(receipt) >= {"response_id", "advice", "escalation", "message_key"}


def test_diarrhea_two_shows_its_tips_and_the_general_hint(
    client: TestClient, content: Content
) -> None:
    assert content.advice is not None
    login(client, "patient2")
    receipt = send(client, [("fever", "presence", 0), ("diarrhea", "frequency", 2)])
    assert [a["rule_id"] for a in receipt["advice"]] == ["ADV-DIARRHEA-01"]
    entry = receipt["advice"][0]
    assert entry["symptom_key"] == "diarrhea"
    assert entry["label"]
    assert len(entry["tips"]) >= 1
    assert entry["sources"]
    assert {"id", "title"} <= set(entry["sources"][0])
    assert receipt["escalation"]["level"] == "general"
    assert receipt["escalation"]["text"] == content.advice["escalation"]["general"]["cs"]


def test_diarrhea_severity_three_is_red_so_tips_are_suppressed_and_acute(
    client: TestClient,
) -> None:
    login(client, "patient2")
    receipt = send(
        client,
        [("fever", "presence", 0), ("diarrhea", "severity", 3), ("fatigue", "severity", 2)],
    )
    assert receipt["escalation"]["level"] == "acute"
    assert [a["rule_id"] for a in receipt["advice"]] == ["ADV-FATIGUE-01"]  # nicht ADV-DIARRHEA-01
    logged = audit_events(app_of(client), "advice_shown")
    assert logged[-1].details_json == {"rules": "ADV-FATIGUE-01", "count": 1, "acute": True}


def test_value_below_the_range_shows_no_tip_and_stays_general(client: TestClient) -> None:
    login(client, "patient2")
    receipt = send(client, [("fever", "presence", 0), ("fatigue", "severity", 1)])
    assert receipt["advice"] == []
    assert receipt["escalation"]["level"] == "general"


def test_acute_notice_does_not_depend_on_a_new_alert_being_created(client: TestClient) -> None:
    """Rauschbremse/Cooldown darf den Akut-Hinweis nie verschlucken (Safety)."""
    login(client, "patient2")
    first = send(client, [("fever", "presence", 1)])
    second = send(client, [("fever", "presence", 1)])  # zweite Meldung wäre Dublette
    assert first["escalation"]["level"] == second["escalation"]["level"] == "acute"


def test_replay_returns_the_same_receipt_including_advice(client: TestClient) -> None:
    login(client, "patient2")
    payload = submission(
        [("fever", "presence", 0), ("diarrhea", "frequency", 3)], questionnaire_id(client)
    )
    first = client.post(RESPONSES, json=payload)
    again = client.post(RESPONSES, json=payload)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json() == again.json()
    assert first.json()["advice"]
    assert len(audit_events(app_of(client), "advice_shown")) == 1  # Replay auditiert nicht


def test_audit_advice_shown_holds_only_rule_ids_and_counts(client: TestClient) -> None:
    login(client, "patient2")
    send(
        client, [("fever", "presence", 0), ("diarrhea", "frequency", 2), ("nausea", "severity", 2)]
    )
    event = audit_events(app_of(client), "advice_shown")[-1]
    assert event.details_json == {
        "rules": "ADV-NAUSEA-01,ADV-DIARRHEA-01",
        "count": 2,
        "acute": False,
    }


def test_advice_failure_never_loses_the_response_and_never_under_warns(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(advice_service, "evaluate_with_escalation", broken)
    login(client, "patient2")
    payload = submission([("fever", "presence", 0)], questionnaire_id(client))
    reply = client.post(RESPONSES, json=payload)
    assert reply.status_code == 201
    assert reply.json()["advice"] == []
    assert reply.json()["escalation"]["level"] == "acute"  # im Zweifel warnen
    with app_of(client).state.session_factory() as session:
        stored = session.scalars(
            select(Response).where(Response.client_submission_id == payload["client_submission_id"])
        ).all()
    assert len(stored) == 1


# ---- GET /me/advice --------------------------------------------------------------------------
def test_advice_page_is_limited_to_the_own_questionnaire_and_localized(client: TestClient) -> None:
    login(client, "patient2")  # Pembrolizumab: kein Erbrechen, kein Hand-Fuß-Syndrom
    cs = client.get(ADVICE, params={"lang": "cs"})
    en = client.get(ADVICE, params={"lang": "en"})
    assert cs.status_code == en.status_code == 200
    keys = {a["symptom_key"] for a in cs.json()["advice"]}
    assert {"fatigue", "diarrhea", "rash"} <= keys
    assert not keys & {"vomiting", "hand_foot", "peripheral_neuropathy"}
    first_cs = next(a for a in cs.json()["advice"] if a["symptom_key"] == "fatigue")
    first_en = next(a for a in en.json()["advice"] if a["symptom_key"] == "fatigue")
    assert first_cs["tips"] != first_en["tips"]
    assert cs.json()["escalation"]["general"] != en.json()["escalation"]["general"]
    assert cs.json()["escalation"]["ambulance_phone"] is None


def test_advice_page_shows_no_tips_for_acute_symptoms_and_no_levels(client: TestClient) -> None:
    login(client, "patient2")
    page = client.get(ADVICE).json()
    for entry in page["advice"]:
        assert set(entry) == {"rule_id", "symptom_key", "label", "acute_only", "tips", "sources"}
        if entry["symptom_key"] in {"fever", "shortness_of_breath"}:
            assert entry["acute_only"] is True
            assert entry["tips"] == []
            assert entry["sources"] == []
        else:
            assert entry["acute_only"] is False
            assert entry["tips"]


def test_advice_page_includes_diagnosis_group_symptoms(client: TestClient) -> None:
    set_diagnosis(app_of(client), "SYN-0001", "C34.1")
    login(client, "patient")
    keys = {a["symptom_key"] for a in client.get(ADVICE).json()["advice"]}
    assert {"shortness_of_breath", "decreased_appetite"} <= keys


def test_advice_page_access_control(client: TestClient) -> None:
    assert client.get(ADVICE).status_code == 401
    login(client, "doctor")
    assert client.get(ADVICE).status_code == 403
    assert client.get(ADVICE, params={"lang": "xx"}).status_code in (403, 422)


# ---- Patiententexte gegen die Verbotsliste ---------------------------------------------------
def texts(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [
            t for key, v in node.items() if key not in {"url", "rule_id", "id"} for t in texts(v)
        ]
    if isinstance(node, list):
        return [t for v in node for t in texts(v)]
    return []


@pytest.mark.parametrize("lang", LANGS)
def test_patient_facing_texts_pass_the_forbidden_lists(client: TestClient, lang: str) -> None:
    set_diagnosis(app_of(client), "SYN-0001", "C34.1")
    login(client, "patient")
    page = client.get(QUESTIONNAIRE, params={"lang": lang}).json()
    for text in (page["selection_reason"], page["escalation_general"]):
        assert_patient_safe(text)
    help_page = client.get(ADVICE, params={"lang": lang}).json()
    for text in texts(help_page):
        assert_patient_safe(text)
    receipt = send(
        client,
        [("fever", "presence", 1), ("fatigue", "severity", 3), ("nausea", "severity", 2)],
    )
    for text in texts({k: receipt[k] for k in ("advice", "escalation")}):
        if text:
            assert_patient_safe(text)


def test_receipt_never_shows_rule_text_grade_or_threshold(client: TestClient) -> None:
    login(client, "patient2")
    receipt = send(client, [("fever", "presence", 0), ("diarrhea", "severity", 3)])
    flat = repr(receipt).lower()
    for word in ("min_value", "max_value", "threshold", "r-sev", "r-urg", "traffic", "grade"):
        assert word not in flat


# ---- FHIR mit neuer Fragebogen-ID ------------------------------------------------------------
def test_fhir_export_handles_the_new_questionnaire_id(client: TestClient) -> None:
    set_diagnosis(app_of(client), "SYN-0001", "C34.1")
    login(client, "patient")
    send(client, [("shortness_of_breath", "severity", 1), ("fever", "presence", 0)])
    login(client, "doctor")
    with app_of(client).state.session_factory() as session:
        patient_id = (
            session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0001")).one().id
        )
    bundle = client.get(f"{BASE}/patients/{patient_id}/fhir")
    assert bundle.status_code == 200
    urls = {
        e["resource"]["url"]
        for e in bundle.json()["entry"]
        if e["resource"]["resourceType"] == "Questionnaire"
    }
    assert "urn:waechter:questionnaire:items-v1:FOLFOX:LUNG" in urls
    lung = next(
        e["resource"]
        for e in bundle.json()["entry"]
        if e["resource"]["resourceType"] == "Questionnaire"
        and e["resource"]["url"].endswith(":LUNG")
    )
    link_ids = {i["linkId"] for item in lung["item"] for i in item.get("item", [item])}
    assert any(link.startswith("shortness_of_breath.") for link in link_ids)


# ---- Inhaltslader: optionale Dateien und Querverweise ----------------------------------------
def edit(directory: Path, filename: str, change: Any) -> None:
    path = directory / filename
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def issues(directory: Path) -> list[str]:
    with pytest.raises(ContentError) as caught:
        load_content(directory)
    return [str(i) for i in caught.value.issues]


@pytest.fixture
def real_copy(tmp_path: Path) -> Path:
    target = tmp_path / "content"
    shutil.copytree(REAL, target, ignore=shutil.ignore_patterns("__pycache__", "tools", "*.py"))
    return target


def test_real_content_loads_the_three_new_files(content: Content) -> None:
    assert content.advice is not None
    assert content.diagnoses is not None
    assert content.schedule is not None


def test_new_files_are_optional(real_copy: Path) -> None:
    for name in ("advice.yaml", "diagnoses.yaml", "schedule.yaml"):
        (real_copy / name).unlink()
    loaded = load_content(real_copy)
    assert (loaded.advice, loaded.diagnoses, loaded.schedule) == (None, None, None)


def test_advice_cross_references_are_checked(real_copy: Path) -> None:
    def unknown_symptom(data: dict[str, Any]) -> None:
        data["advice"][0]["symptom_key"] = "no_such_symptom"

    def duplicate_id(data: dict[str, Any]) -> None:
        data["advice"][1]["id"] = data["advice"][0]["id"]

    def unknown_source(data: dict[str, Any]) -> None:
        data["advice"][0]["source_ids"] = ["SRC-NOPE"]

    def bad_range(data: dict[str, Any]) -> None:
        data["advice"][0]["min_value"] = 4
        data["advice"][0]["max_value"] = 2

    def acute_symptom(data: dict[str, Any]) -> None:
        data["escalation"]["always_acute_for"] = ["no_such_symptom"]

    for change, needle in (
        (unknown_symptom, "unknown symptom_key"),
        (duplicate_id, "duplicate id"),
        (unknown_source, "unknown source id"),
        (bad_range, "below min_value"),
        (acute_symptom, "unknown symptom_key"),
    ):
        fresh = real_copy.parent / f"c-{needle[:6]}-{change.__name__}"
        shutil.copytree(real_copy, fresh)
        edit(fresh, "advice.yaml", change)
        assert any("advice.yaml" in i and needle in i for i in issues(fresh)), change.__name__


def test_diagnoses_and_schedule_cross_references_are_checked(real_copy: Path) -> None:
    def duplicate_prefix(data: dict[str, Any]) -> None:
        data["diagnoses"][1]["icd10_prefixes"].append(data["diagnoses"][0]["icd10_prefixes"][0])

    def unknown_symptom(data: dict[str, Any]) -> None:
        data["diagnoses"][0]["symptom_keys"] = ["no_such_symptom"]

    def inverted_phase(data: dict[str, Any]) -> None:
        data["phases"][0]["from_cycle_day"] = 9
        data["phases"][0]["to_cycle_day"] = 3

    for filename, change, needle in (
        ("diagnoses.yaml", duplicate_prefix, "duplicate prefix"),
        ("diagnoses.yaml", unknown_symptom, "unknown symptom_key"),
        ("schedule.yaml", inverted_phase, "below from_cycle_day"),
    ):
        fresh = real_copy.parent / f"d-{change.__name__}"
        shutil.copytree(real_copy, fresh)
        edit(fresh, filename, change)
        assert any(filename in i and needle in i for i in issues(fresh)), change.__name__
