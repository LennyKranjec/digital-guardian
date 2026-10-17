"""A3-Gegenproben zu T-16 (Sitzungs-API, Triage-Entscheidung, Meldungen, Befund-/Regelkarte).

Unabhängig geprüft gegen die Referenz `a3_triage_ref.py` (eigener Parser, Lehrer, Böden)
und gegen den Vertrag (triage.md §10, openapi v2.5/v2.8) - über HTTP mit dem echten Inhalt.
"""
# ruff: noqa: S311, F811  # feste Seeds; Fixture-Import überdeckt das Argument

import random
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import a3_triage_ref as ref
from app.persistence.models import AuditEvent
from conftest import CSRF, run_parallel
from test_a3_t04a import MutableClock
from test_a3_t13 import (  # noqa: F401
    ANCHOR,
    BASE,
    api,
    clear_responses,
    client_for,
    real_template,
)
from test_a3_t14 import session_setup, truth_grades
from test_t16_triage import clear_history, triage_get
from waechter.models import CheckinSession, Response, TriageDecision
from waechter.triage.kb import load_kb

CONTENT = Path(__file__).resolve().parents[1] / "content"
RAW = yaml.safe_load((CONTENT / "triage.yaml").read_text(encoding="utf-8"))
SESSIONS = f"{BASE}/me/sessions"


def start(client: TestClient, csid: str | None = None, **extra: Any) -> tuple[int, dict[str, Any]]:
    reply = client.post(SESSIONS, json={"client_session_id": csid or str(uuid.uuid4()), **extra})
    return reply.status_code, reply.json()


def answer(client: TestClient, sid: str, key: str, attribute: str, value: int | None) -> Any:
    return client.post(
        f"{SESSIONS}/{sid}/answers",
        json={"symptom_key": key, "attribute": attribute, "value": value},
    )


def count(app: FastAPI, model: Any, *where: Any) -> int:
    with app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


def test_a3_identical_repeat_on_an_open_session_returns_the_same_state(
    api: tuple[FastAPI, MutableClock],
) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    clear_responses(app)
    status, step = start(client)
    assert status == 201
    sid = step["session_id"]
    first = step["next"]
    key = (first["symptom_key"], first["attribute"])
    one = answer(client, sid, *key, 0)
    again = answer(client, sid, *key, 0)
    assert (one.status_code, again.status_code) == (200, 200)
    assert again.json() == one.json(), "identische Wiederholung liefert einen anderen Stand"
    nxt = one.json()["next"]
    assert nxt is None or (nxt["symptom_key"], nxt["attribute"]) != key
    assert client.get(f"{SESSIONS}/{sid}").json() == one.json()


def report_fever(client: TestClient) -> str:
    """Patientin meldet Fieber = ja über die Sitzungs-API; liefert die Sitzungskennung."""
    status, step = start(client, lang="cs")
    assert status == 201
    sid = step["session_id"]
    for _ in range(12):
        question = step["next"]
        if question is None:
            return str(sid)
        value = 1 if question["symptom_key"] == "fever" else 0
        reply = answer(client, sid, question["symptom_key"], question["attribute"], value)
        assert reply.status_code == 200, reply.text
        step = reply.json()
    raise AssertionError("session did not stop")


def test_a3_alert_explanation_triage_reason_codes_match_the_frontend_contract(
    api: tuple[FastAPI, MutableClock],
) -> None:
    app, _ = api
    patient = client_for(app, "patient2")
    clear_responses(app)
    report_fever(patient)
    doctor = client_for(app, "doctor")
    rows = doctor.get(f"{BASE}/patients").json()
    pid = next(r["patient_id"] for r in rows if r["pseudonym"] == "SYN-0002")
    overview = doctor.get(f"{BASE}/patients/{pid}/overview", params={"lang": "cs"}).json()
    triages = [
        a["explanation"]["triage"]
        for a in overview["open_alerts"]
        if a["explanation"].get("triage")
    ]
    assert triages, "keine Meldung mit explanation.triage nach roter Meldung"
    for triage in triages:
        for reason in triage["reason_codes"]:
            assert isinstance(reason, dict), (
                f"reason_codes[] ist {type(reason).__name__}: {reason!r}"
            )
            assert {"code", "text"} <= set(reason)


def drive(
    client: TestClient, truth: dict[tuple[str, str], int], **extra: Any
) -> tuple[dict[tuple[str, str], int], dict[str, Any]]:
    """Beantwortet jede gestellte Frage aus `truth` (Rest 0); liefert gestellte Felder und Stopp."""
    status, step = start(client, **extra)
    assert status == 201, step
    sid = step["session_id"]
    asked: dict[tuple[str, str], int] = {}
    for _ in range(40):
        question = step["next"]
        if question is None:
            return asked, step
        key = (question["symptom_key"], question["attribute"])
        asked[key] = truth.get(key, 0)
        reply = answer(client, sid, key[0], key[1], asked[key])
        assert reply.status_code == 200, reply.text
        step = reply.json()
    raise AssertionError("session did not stop")


def drive_random(
    client: TestClient, rng: random.Random, p_zero: float
) -> tuple[dict[tuple[str, str], int], dict[str, Any]]:
    """Beantwortet jede Frage zufällig (mit Wahrscheinlichkeit p_zero mit 0)."""
    status, step = start(client)
    assert status == 201, step
    sid = step["session_id"]
    asked: dict[tuple[str, str], int] = {}
    for _ in range(40):
        question = step["next"]
        if question is None:
            return asked, step
        values = [o["value"] for o in question["options"]]
        key = (question["symptom_key"], question["attribute"])
        asked[key] = 0 if rng.random() < p_zero else rng.choice(values)
        reply = answer(client, sid, key[0], key[1], asked[key])
        assert reply.status_code == 200, reply.text
        step = reply.json()
    raise AssertionError("session did not stop")


def test_a3_stored_decisions_equal_the_independent_reference_on_random_answers(
    api: tuple[FastAPI, MutableClock],
) -> None:
    """Sitzung -> Antworten -> Triage-Entscheidung == Referenz; Antworten bewusst oft ungleich 0."""
    app, _ = api
    kb = load_kb()
    theirs, mine, *_ = session_setup(kb, "PEMBROLIZUMAB")
    patient = client_for(app, "patient2")
    doctor = client_for(app, "doctor")
    rng = random.Random(1617)
    mismatches: list[str] = []
    seen: dict[str, int] = {"GREEN": 0, "YELLOW": 0, "RED": 0}
    for run in range(120):
        pid = clear_history(app, "SYN-0002")
        asked, stop = drive_random(patient, rng, (0.2, 0.5, 0.8)[run % 3])
        want = ref.final_level(mine, truth_grades(theirs, asked), None)
        seen[want] += 1
        body = triage_get(doctor, pid, response_id=stop["receipt"]["response_id"]).json()
        if body["level_lo"] == body["level_hi"] and body["level"] != want:
            mismatches.append(f"{asked}: Referenz {want}, API {body['level']}")
    assert mismatches == [], mismatches[:3]
    assert min(seen.values()) >= 5, f"zu wenig Abdeckung je Stufe: {seen}"


def test_a3_repeated_reports_keep_at_most_one_open_triage_alert_per_level(
    api: tuple[FastAPI, MutableClock],
) -> None:
    """Vertrag: je Antwort höchstens eine R-TRI-Meldung, nie zwei offene derselben R-TRI-Regel."""
    app, clock = api
    patient = client_for(app, "patient2")
    doctor = client_for(app, "doctor")
    pid = clear_history(app, "SYN-0002")
    before = len(doctor.get(f"{BASE}/notifications").json())
    for _ in range(3):
        report_fever(patient)
        clock.instant += timedelta(minutes=5)
    open_alerts = doctor.get(f"{BASE}/patients/{pid}/alerts", params={"status": "open"}).json()
    rules = sorted(a["rule_id"] for a in open_alerts)
    assert rules.count("R-TRI-RED") <= 1, rules
    assert rules.count("R-URG-01") <= 1, rules
    notified = len(doctor.get(f"{BASE}/notifications").json()) - before
    print(f"OFFEN {rules}, neue Benachrichtigungen {notified}")


def test_a3_second_report_does_not_add_a_second_open_red_alert(
    api: tuple[FastAPI, MutableClock],
) -> None:
    app, clock = api
    patient = client_for(app, "patient2")
    doctor = client_for(app, "doctor")
    pid = clear_history(app, "SYN-0002")
    report_fever(patient)
    clock.instant += timedelta(minutes=5)
    report_fever(patient)
    open_alerts = doctor.get(f"{BASE}/patients/{pid}/alerts", params={"status": "open"}).json()
    assert len([a for a in open_alerts if a["level"] == "red"]) == 1, [
        a["rule_id"] for a in open_alerts
    ]


def test_a3_sessions_are_private_to_their_patient_and_role_checked(
    api: tuple[FastAPI, MutableClock],
) -> None:
    app, _ = api
    owner = client_for(app, "patient2")
    other = client_for(app, "patient")
    doctor = client_for(app, "doctor")
    admin = client_for(app, "admin")
    anonymous = TestClient(app, headers=CSRF)
    _, step = start(owner)
    sid = step["session_id"]
    question = step["next"]
    key = (question["symptom_key"], question["attribute"])
    # fremde Patientin: weder lesen noch beantworten (404 wie „unbekannt“)
    assert other.get(f"{SESSIONS}/{sid}").status_code == 404
    assert answer(other, sid, *key, 0).status_code == 404
    unknown = str(uuid.uuid4())
    assert owner.get(f"{SESSIONS}/{unknown}").status_code == 404
    assert answer(owner, unknown, *key, 0).status_code == 404
    # Klinikrollen und anonym haben keinen Zugriff auf Patientensitzungen
    for who in (doctor, admin):
        assert who.get(f"{SESSIONS}/{sid}").status_code in (403, 404)
        assert who.post(SESSIONS, json={"client_session_id": str(uuid.uuid4())}).status_code == 403
        assert answer(who, sid, *key, 0).status_code in (403, 404)
    assert (
        anonymous.post(SESSIONS, json={"client_session_id": str(uuid.uuid4())}).status_code == 401
    )
    assert anonymous.get(f"{SESSIONS}/{sid}").status_code == 401
    # dieselbe Kennung einer anderen Patientin darf keine fremde Sitzung liefern
    csid = str(uuid.uuid4())
    mine = owner.post(SESSIONS, json={"client_session_id": csid}).json()
    theirs = other.post(SESSIONS, json={"client_session_id": csid}).json()
    assert mine["session_id"] != theirs["session_id"]
    # Patientinnen sehen Triage-Karten und -Regeln nie
    pid = clear_history(app, "SYN-0002")
    for url in (f"{BASE}/patients/{pid}/triage", f"{BASE}/config/triage"):
        assert owner.get(url).status_code == 403
        assert anonymous.get(url).status_code == 401


def test_a3_wrong_input_to_the_session_api_is_a_clean_4xx(
    api: tuple[FastAPI, MutableClock],
) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    for bad in ({}, {"client_session_id": "kein-uuid"}, {"client_session_id": 7}):
        assert client.post(SESSIONS, json=bad).status_code == 422
    _, step = start(client)
    sid = step["session_id"]
    question = step["next"]
    key = (question["symptom_key"], question["attribute"])
    allowed = {o["value"] for o in question["options"]}
    outside = max(allowed) + 7
    for payload in (
        {"symptom_key": key[0], "attribute": key[1], "value": outside},
        {"symptom_key": key[0], "attribute": key[1], "value": "x"},
        {"symptom_key": "nicht_da", "attribute": "severity", "value": 0},
        {"symptom_key": key[0]},
    ):
        reply = client.post(f"{SESSIONS}/{sid}/answers", json=payload)
        assert reply.status_code in (409, 422), (payload, reply.status_code)
        assert "Traceback" not in reply.text
        assert "sqlalchemy" not in reply.text.lower()
    # eine andere als die gestellte Frage ⇒ 409 not_current_question, Sitzung unverändert
    other = [(q, a) for q, a in [("nausea", "severity"), ("pain", "severity")] if (q, a) != key]
    reply = answer(client, sid, other[0][0], other[0][1], 0)
    assert reply.status_code == 409
    assert reply.json()["code"] == "not_current_question"
    assert client.get(f"{SESSIONS}/{sid}").json()["next"] == question


def test_a3_parallel_identical_answers_store_exactly_one_response_and_decision(
    api: tuple[FastAPI, MutableClock],
) -> None:
    app, _ = api
    pid = clear_history(app, "SYN-0002")
    first = client_for(app, "patient2")
    status, step = start(first)
    assert status == 201
    sid = step["session_id"]
    first_question = step["next"]
    assert first_question["symptom_key"] == "fever"
    step = answer(first, sid, "fever", "presence", 1).json()
    clients = [client_for(app, "patient2") for _ in range(4)]
    last = step["next"]
    assert last is not None
    key = (last["symptom_key"], last["attribute"])

    def send(i: int) -> tuple[int, dict[str, Any]]:
        reply = answer(clients[i], sid, *key, 0)
        return reply.status_code, reply.json()

    # die letzte Frage gleichzeitig mehrfach beantworten (Wettlauf um die Speicherung)
    results = run_parallel(send, 4)
    codes = sorted(code for code, _ in results)
    assert codes[0] == 200, results
    assert all(code in (200, 409) for code in codes), codes
    stops = [body for code, body in results if code == 200 and body.get("next") is None]
    assert stops, results
    assert len({body["receipt"]["response_id"] for body in stops}) == 1
    assert count(app, Response, Response.patient_id == pid) == 1
    assert count(app, TriageDecision, TriageDecision.patient_id == pid) == 1
    assert count(app, CheckinSession, CheckinSession.patient_id == pid) == 1


def test_a3_audit_of_sessions_and_triage_contains_no_answer_values_or_texts(
    api: tuple[FastAPI, MutableClock],
) -> None:
    app, _ = api
    pid = clear_history(app, "SYN-0002")
    patient = client_for(app, "patient2")
    doctor = client_for(app, "doctor")
    sid = report_fever(patient)
    response_id = patient.get(f"{SESSIONS}/{sid}").json()["receipt"]["response_id"]
    assert triage_get(doctor, pid, response_id=response_id).status_code == 200
    with app.state.session_factory() as session:
        events = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action.in_(("start_session", "view_triage", "triage_failed"))
                )
            )
        )
    assert {e.action for e in events} >= {"start_session", "view_triage"}
    blob = " ".join(str(e.details_json) for e in events).lower()
    for needle in ("fever", "horečka", "presence", "value", "shortness", "dusnost", "tělesn"):
        assert needle not in blob, needle
    assert not any(e.action == "triage_failed" for e in events)


def test_a3_rule_card_reports_exact_grid_sizes_and_no_deviation(
    api: tuple[FastAPI, MutableClock],
) -> None:
    app, _ = api
    doctor = client_for(app, "doctor")
    kb = load_kb()
    reply = doctor.get(f"{BASE}/config/triage", params={"lang": "cs"})
    assert reply.status_code == 200, reply.text
    card = reply.json()
    by_id = {p["profile_id"]: p for p in card["profiles"]}
    assert {"FOLFOX", "CAPECITABINE", "DOCETAXEL", "PEMBROLIZUMAB"} <= set(by_id)
    for leaf in ("FOLFOX", "CAPECITABINE", "DOCETAXEL", "PEMBROLIZUMAB"):
        mine = ref.resolve(RAW, leaf)
        verification = by_id[leaf]["verification"]
        assert verification["points"] == ref.compressed_size(mine), leaf
        assert (verification["under"], verification["over"]) == (0, 0)
        assert verification["monotone_violations"] == 0
        assert verification["scope"] in ("exhaustive_raw", "exhaustive_orbit", "sampled_raw")
        assert by_id[leaf]["rules"], "Regelkarte leer"
        assert by_id[leaf]["floors"], "Böden fehlen"
        assert kb.profile(leaf).status == "placeholder"
        assert by_id[leaf].get("placeholders"), "Platzhalter-Annahmen fehlen"
    assert card["kb_version"]
