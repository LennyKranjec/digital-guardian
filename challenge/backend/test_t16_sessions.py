"""T-16 (Vertrag v2.0/v2.5): adaptiver Check-in unter /me/sessions, Echtinhalt, feste Ankerzeit."""
# ruff: noqa: S311  # feste Seeds, keine Kryptografie

import random
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.persistence.models import AuditEvent
from conftest import CSRF, login, run_parallel
from test_a3_t04a import MutableClock
from test_t13_clinic import assert_patient_safe
from test_t16_triage import clear_history
from waechter.constants import CONTENT_DIR_ENV
from waechter.models import CheckinSession, Patient, Response, TriageDecision
from waechter.services import triage
from waechter.triage.engine import TeacherEngine
from waechter.triage.kb import KnowledgeBase

REAL = Path(__file__).resolve().parents[1] / "content"
BASE = "/api/v1/waechter"
SESSIONS = f"{BASE}/me/sessions"


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


def app_of(client: TestClient) -> FastAPI:
    application = client.app
    assert isinstance(application, FastAPI)
    return application


def start(client: TestClient, **extra: Any) -> tuple[int, dict[str, Any]]:
    reply = client.post(SESSIONS, json={"client_session_id": str(uuid.uuid4()), **extra})
    return reply.status_code, reply.json()


def answer(client: TestClient, session_id: str, key: str, attribute: str, value: int | None) -> Any:
    return client.post(
        f"{SESSIONS}/{session_id}/answers",
        json={"symptom_key": key, "attribute": attribute, "value": value},
    )


def run(
    client: TestClient, truth: dict[tuple[str, str], int | None], **extra: Any
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Beantwortet jede Frage aus `truth` (fehlt ein Feld ⇒ 0) bis zum Stopp."""
    status, step = start(client, **extra)
    assert status == 201, step
    session_id = step["session_id"]
    asked: list[dict[str, Any]] = []
    for _ in range(60):
        question = step["next"]
        if question is None:
            return session_id, asked, step
        asked.append(question)
        key = (question["symptom_key"], question["attribute"])
        reply = answer(client, session_id, key[0], key[1], truth.get(key, 0))
        assert reply.status_code == 200, reply.text
        step = reply.json()
    raise AssertionError("session did not stop")


def responses_of(app: FastAPI, pseudonym: str) -> int:
    with app.state.session_factory() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(Response)
                .join(Patient, Patient.id == Response.patient_id)
                .where(Patient.pseudonym == pseudonym)
            )
            or 0
        )


# ---- Start --------------------------------------------------------------------------------
def test_start_offers_the_safety_question_first_with_progress_reason_and_due(
    client: TestClient,
) -> None:
    login(client, "patient2")
    status, step = start(client, lang="en")
    assert status == 201
    question = step["next"]
    assert (question["symptom_key"], question["attribute"]) == ("fever", "presence")
    assert question["safety"] is True
    assert question["kind"] == "gate"
    assert question["label"]
    assert question["text"]
    assert [o["value"] for o in question["options"]] == [0, 1]
    assert step["progress"] == {"asked": 0, "max": 12}
    assert step["stop"] is None
    assert step["receipt"] is None
    assert step["selection_reason"].startswith("Questions matching your therapy")
    assert {"next_due_at", "overdue", "interval_days"} <= set(step["due"])
    assert_patient_safe(question["text"])
    assert_patient_safe(step["selection_reason"])


def test_start_is_idempotent_per_client_session_id(client: TestClient) -> None:
    login(client, "patient2")
    csid = str(uuid.uuid4())
    first = client.post(SESSIONS, json={"client_session_id": csid})
    again = client.post(SESSIONS, json={"client_session_id": csid})
    other = client.post(SESSIONS, json={"client_session_id": str(uuid.uuid4())})
    assert (first.status_code, again.status_code, other.status_code) == (201, 200, 201)
    assert first.json() == again.json()
    assert other.json()["session_id"] != first.json()["session_id"]


def test_parallel_starts_with_the_same_id_create_exactly_one_session(client: TestClient) -> None:
    app = app_of(client)
    login(client, "patient2")
    csid = str(uuid.uuid4())
    clients = []
    for _ in range(4):
        extra = TestClient(app, headers=CSRF)
        login(extra, "patient2")
        clients.append(extra)
    results = run_parallel(
        lambda i: clients[i].post(SESSIONS, json={"client_session_id": csid}).json(), 4
    )
    assert len({r["session_id"] for r in results}) == 1
    with app.state.session_factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(CheckinSession)
            .where(CheckinSession.client_session_id == csid)
        )
    assert count == 1


def test_start_validates_the_body_and_the_role(client: TestClient) -> None:
    assert client.post(SESSIONS, json={"client_session_id": str(uuid.uuid4())}).status_code == 401
    login(client, "doctor")
    assert client.post(SESSIONS, json={"client_session_id": str(uuid.uuid4())}).status_code == 403
    login(client, "patient2")
    assert client.post(SESSIONS, json={"client_session_id": "not-a-uuid"}).status_code == 422
    assert client.post(SESSIONS, json={}).status_code == 422
    assert (
        client.post(
            SESSIONS, json={"client_session_id": str(uuid.uuid4()), "lang": "xx"}
        ).status_code
        == 422
    )


# ---- Ablauf -------------------------------------------------------------------------------
def test_healthy_patient_stops_decided_after_the_gates_with_one_stored_response(
    client: TestClient,
) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    session_id, asked, step = run(client, {}, lang="cs")
    assert step["stop"] == {"reason": "decided", "incomplete": False}
    assert step["next"] is None
    gates = [q for q in asked if q["kind"] in ("gate", "slot")]
    assert len(gates) == len(asked)  # Gate = 0 ⇒ keine Folgeattribute
    assert len({q["symptom_key"] for q in asked}) == len(asked)
    receipt = step["receipt"]
    assert receipt["response_id"]
    assert receipt["escalation"]["level"] == "general"
    assert receipt["advice"] == []
    assert responses_of(app, "SYN-0002") == 1
    kb = triage.get_kb()
    assert isinstance(kb, KnowledgeBase)
    assert len(asked) < kb.profile("PEMBROLIZUMAB").full_question_count
    with app.state.session_factory() as session:
        row = session.scalars(
            select(TriageDecision).where(TriageDecision.response_id == receipt["response_id"])
        ).one()
        assert row.level == "GREEN"
        assert row.asked_questions == len(asked)
        stored = session.get(CheckinSession, session_id)
        assert stored is not None
        assert stored.status == "closed"
        assert stored.response_id == receipt["response_id"]
    flat = repr(step).lower()
    for word in ("green", "yellow", "level_lo", "triage", "rule_version"):
        assert word not in flat


def test_positive_gate_runs_the_cascade_and_the_answers_are_stored(client: TestClient) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    status, step = start(client)
    session_id = step["session_id"]
    step = answer(client, session_id, "fever", "presence", 0).json()
    while step["next"] is not None and step["next"]["symptom_key"] != "fatigue":
        q = step["next"]
        step = answer(client, session_id, q["symptom_key"], q["attribute"], 0).json()
    assert step["next"]["symptom_key"] == "fatigue"
    step = answer(client, session_id, "fatigue", "severity", 1).json()
    assert step["next"]["kind"] == "cascade"
    assert (step["next"]["symptom_key"], step["next"]["attribute"]) == ("fatigue", "interference")
    assert status == 201


def test_wrong_question_is_409_not_current_question_and_nothing_is_stored(
    client: TestClient,
) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    _, step = start(client)
    session_id = step["session_id"]
    wrong = answer(client, session_id, "pain", "severity", 1)
    assert wrong.status_code == 409
    assert wrong.json()["code"] == "not_current_question"
    assert client.get(f"{SESSIONS}/{session_id}").json()["progress"]["asked"] == 0
    assert responses_of(app, "SYN-0002") == 0


def test_invalid_answers_are_422(client: TestClient) -> None:
    login(client, "patient2")
    _, step = start(client)
    session_id = step["session_id"]
    assert answer(client, session_id, "fever", "presence", 2).status_code == 422
    assert answer(client, session_id, "fever", "presence", -1).status_code == 422
    assert answer(client, session_id, "fever", "severity", 1).status_code == 422
    assert answer(client, session_id, "nope", "severity", 1).status_code == 422
    assert (
        client.post(
            f"{SESSIONS}/{session_id}/answers",
            json={"symptom_key": "fever", "attribute": "presence", "value": "x"},
        ).status_code
        == 422
    )


def test_identical_repeat_of_an_open_answer_is_idempotent(client: TestClient) -> None:
    login(client, "patient2")
    _, step = start(client)
    session_id = step["session_id"]
    first = answer(client, session_id, "fever", "presence", 0)
    again = answer(client, session_id, "fever", "presence", 0)  # Antwort ging verloren
    assert (first.status_code, again.status_code) == (200, 200)
    assert first.json() == again.json()
    assert again.json()["progress"]["asked"] == 1


def test_skipped_answers_are_stored_as_missing_and_end_incomplete(client: TestClient) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    status, step = start(client)
    session_id = step["session_id"]
    for _ in range(40):
        if step["next"] is None:
            break
        q = step["next"]
        step = answer(client, session_id, q["symptom_key"], q["attribute"], None).json()
    assert status == 201
    assert step["stop"]["reason"] == "complete"
    assert step["stop"]["incomplete"] is True
    assert step["receipt"]["skipped"] > 0
    assert step["receipt"]["answered"] == 0
    with app.state.session_factory() as session:
        row = session.scalars(
            select(TriageDecision).where(
                TriageDecision.response_id == step["receipt"]["response_id"]
            )
        ).one()
        assert row.incomplete is True
        assert row.level in ("YELLOW", "RED")  # fehlende Information ergibt nie Grün


# ---- Stopp, Wiederholung, Beleg (v2.5) ----------------------------------------------------
def _finish_red(client: TestClient) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Fieber = ja ⇒ Boden ⇒ Rot entschieden; liefert (Sitzung, letzte Antwort, Stopp-Schritt)."""
    _, step = start(client)
    session_id = step["session_id"]
    reply = answer(client, session_id, "fever", "presence", 1)
    final = reply.json()
    while final["next"] is not None:
        q = final["next"]
        reply = answer(client, session_id, q["symptom_key"], q["attribute"], 0)
        final = reply.json()
    return session_id, {"symptom_key": q["symptom_key"], "attribute": q["attribute"]}, final


def test_fever_stops_the_session_with_the_acute_notice_and_without_fever_tips(
    client: TestClient,
) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    _, step = start(client)
    session_id = step["session_id"]
    reply = answer(client, session_id, "fever", "presence", 1)
    step = reply.json()
    while step["next"] is not None:
        q = step["next"]
        assert q["safety"] or q["kind"] in ("gate", "cascade", "slot", "escalation")
        step = answer(client, session_id, q["symptom_key"], q["attribute"], 0).json()
    assert step["stop"]["reason"] == "decided"
    receipt = step["receipt"]
    assert receipt["escalation"]["level"] == "acute"
    assert "ADV-FEVER-01" not in [a["rule_id"] for a in receipt["advice"]]
    login(client, "doctor")
    with app.state.session_factory() as session:
        pid = session.scalars(select(Patient.id).where(Patient.pseudonym == "SYN-0002")).one()
    card = client.get(f"{BASE}/patients/{pid}/triage").json()
    assert card["level"] == "RED"
    assert card["response_id"] == receipt["response_id"]


def test_identical_last_answer_after_the_stop_returns_the_same_receipt_without_a_new_record(
    client: TestClient,
) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    _, step = start(client)
    session_id = step["session_id"]
    last: tuple[str, str, int] | None = None
    reply = answer(client, session_id, "fever", "presence", 1)
    step = reply.json()
    last = ("fever", "presence", 1)
    while step["next"] is not None:
        q = step["next"]
        last = (q["symptom_key"], q["attribute"], 0)
        reply = answer(client, session_id, *last)
        step = reply.json()
    assert reply.status_code == 200
    assert step["stop"] is not None
    before = responses_of(app, "SYN-0002")
    again = answer(client, session_id, *last)  # Funkloch: dieselbe Stopp-Antwort noch einmal
    assert again.status_code == 200
    assert again.json() == step
    assert again.json()["receipt"] == step["receipt"]
    assert responses_of(app, "SYN-0002") == before == 1
    different = answer(client, session_id, last[0], last[1], 1 - last[2])
    assert different.status_code == 409
    assert different.json()["code"] == "session_closed"
    other = answer(client, session_id, "pain", "severity", 1)
    assert other.status_code == 409
    assert other.json()["code"] == "session_closed"
    assert responses_of(app, "SYN-0002") == 1


def run_to_stop(client: TestClient, session_id: str, step: dict[str, Any]) -> dict[str, Any]:
    while step["next"] is not None:
        q = step["next"]
        step = answer(client, session_id, q["symptom_key"], q["attribute"], 0).json()
    return step


def test_get_session_returns_the_open_question_and_after_the_stop_the_receipt(
    client: TestClient,
) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    _, step = start(client)
    session_id = step["session_id"]
    open_step = client.get(f"{SESSIONS}/{session_id}")
    assert open_step.status_code == 200
    assert open_step.json()["next"] == step["next"]
    final = run_to_stop(client, session_id, step)
    again = client.get(f"{SESSIONS}/{session_id}")
    assert again.status_code == 200
    assert again.json() == final
    assert again.json()["receipt"]["response_id"] == final["receipt"]["response_id"]


def test_receipt_is_persisted_with_the_response_and_served_from_there(client: TestClient) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    session_id, _, final = _finish_red(client)
    with app.state.session_factory() as session:
        row = session.get(Response, final["receipt"]["response_id"])
        assert row is not None
        assert row.receipt_json is not None
        stored = dict(row.receipt_json)
    assert stored["escalation"] == final["receipt"]["escalation"]
    assert stored["advice"] == final["receipt"]["advice"]
    assert client.get(f"{SESSIONS}/{session_id}").json()["receipt"] == final["receipt"]


# ---- Rechte (IDOR) ------------------------------------------------------------------------
def test_other_patients_and_staff_cannot_touch_a_session(client: TestClient) -> None:
    login(client, "patient2")
    _, step = start(client)
    session_id = step["session_id"]
    login(client, "patient")
    assert client.get(f"{SESSIONS}/{session_id}").status_code == 404
    assert answer(client, session_id, "fever", "presence", 0).status_code == 404
    login(client, "doctor")
    assert client.get(f"{SESSIONS}/{session_id}").status_code == 403
    assert answer(client, session_id, "fever", "presence", 0).status_code == 403
    anonymous = TestClient(app_of(client), headers=CSRF)
    assert anonymous.get(f"{SESSIONS}/{session_id}").status_code == 401
    login(client, "patient")
    assert client.get(f"{SESSIONS}/does-not-exist").status_code == 404


# ---- Parallelität -------------------------------------------------------------------------
def test_four_parallel_identical_answers_apply_exactly_once(client: TestClient) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    _, step = start(client)
    session_id = step["session_id"]
    clients = []
    for _ in range(4):
        extra = TestClient(app, headers=CSRF)
        login(extra, "patient2")
        clients.append(extra)
    results = run_parallel(
        lambda i: answer(clients[i], session_id, "fever", "presence", 0).json(), 4
    )
    assert {r["progress"]["asked"] for r in results} == {1}
    with app.state.session_factory() as session:
        row = session.get(CheckinSession, session_id)
        assert row is not None
        assert row.steps_json == [["fever", "presence", 0]]


def test_four_parallel_final_answers_create_exactly_one_response(client: TestClient) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    _, step = start(client)
    session_id = step["session_id"]
    step = answer(client, session_id, "fever", "presence", 1).json()
    while step["next"] is not None and step["next"]["safety"] is False:
        q = step["next"]
        step = answer(client, session_id, q["symptom_key"], q["attribute"], 0).json()
    # offen ist die letzte Safety-Frage (Atemnot): diese Antwort parallel senden
    last: dict[str, Any] | None = step["next"]
    assert last is not None
    clients = []
    for _ in range(4):
        extra = TestClient(app, headers=CSRF)
        login(extra, "patient2")
        clients.append(extra)
    results = run_parallel(
        lambda i: answer(clients[i], session_id, last["symptom_key"], last["attribute"], 0).json(),
        4,
    )
    stopped = [r for r in results if r["stop"] is not None]
    assert stopped
    assert len({r["receipt"]["response_id"] for r in stopped}) == 1
    assert responses_of(app, "SYN-0002") == 1


# ---- Entscheidung und Volleingabe ---------------------------------------------------------
def _consistent_truth(
    rng: random.Random, kb: KnowledgeBase, profile_id: str
) -> dict[tuple[str, str], int | None]:
    profile = kb.profile(profile_id)
    truth: dict[tuple[str, str], int | None] = {}
    for symptom in profile.symptoms:
        attributes = profile.order(symptom)
        if rng.random() < 0.3:
            top = 1 if attributes[0] == "presence" else 4
            truth[(symptom, attributes[0])] = rng.randint(1, top)
            for attribute in attributes[1:]:
                truth[(symptom, attribute)] = rng.randint(0, 4)
    return truth


def tick_clock(app: FastAPI) -> None:
    clock = app.state.clock
    if not isinstance(clock, MutableClock):
        clock = MutableClock(clock.now())
        app.state.clock = clock
    clock.instant += timedelta(hours=1)


def test_stored_session_decision_equals_the_teacher_on_the_full_truth(client: TestClient) -> None:
    """Ende-zu-Ende über die API: `decided` ⇒ Entscheidung == Lehrerlevel der Volleingabe."""
    app = app_of(client)
    kb = triage.get_kb()
    assert isinstance(kb, KnowledgeBase)
    profile = kb.profile("PEMBROLIZUMAB")
    engine = TeacherEngine(profile)
    rng = random.Random(20261016)
    login(client, "patient2")
    clear_history(app, "SYN-0002")
    decided = 0
    for _ in range(12):
        truth = _consistent_truth(rng, kb, "PEMBROLIZUMAB")
        _, _, step = run(client, truth)
        assert step["stop"]["reason"] in ("decided", "burden_cap")
        with app.state.session_factory() as session:
            response = session.get(Response, step["receipt"]["response_id"])
            assert response is not None
            row = session.scalars(
                select(TriageDecision).where(TriageDecision.response_id == response.id)
            ).one()
            previous = triage.previous_grades(session, response, profile)
        everything = {
            (symptom, attribute): truth.get((symptom, attribute)) or 0
            for symptom in profile.symptoms
            for attribute in profile.items[symptom].attributes
        }
        full = engine.level(everything, previous)  # Volleingabe: nicht genannte Felder = 0
        order = ["GREEN", "YELLOW", "RED"]
        assert order.index(row.level_lo) <= order.index(row.level) <= order.index(row.level_hi)
        if step["stop"]["reason"] == "decided":
            decided += 1
            assert row.level == full.level.name, (truth, previous)
        tick_clock(app)
    assert decided >= 8


def test_audit_records_the_session_start_without_answers(client: TestClient) -> None:
    app = app_of(client)
    login(client, "patient2")
    start(client)
    with app.state.session_factory() as session:
        events = list(
            session.scalars(select(AuditEvent).where(AuditEvent.action == "start_session"))
        )
    assert len(events) == 1
    assert events[0].details_json == {}


def test_texts_follow_the_language_of_the_session(client: TestClient) -> None:
    login(client, "patient2")
    _, cs = start(client, lang="cs")
    _, en = start(client, lang="en")
    _, de = start(client, lang="de")
    assert cs["next"]["text"] != en["next"]["text"]
    assert de["next"]["text"] != en["next"]["text"]  # de: eigene Texte seit T-27a
    assert cs["selection_reason"].startswith("Otázky")
    assert de["selection_reason"].startswith("Fragen")
    for step in (cs, en, de):
        assert_patient_safe(step["next"]["text"])
        for option in step["next"]["options"]:
            assert_patient_safe(option["label"])
