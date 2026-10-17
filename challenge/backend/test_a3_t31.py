"""A3-Gegenproben zu T-31 (Zurück-Pfeil: POST /me/sessions/{id}/undo).

Orakel: Antworten, Zurücknehmen und erneutes Antworten ergeben genau die Triage-Entscheidung, die
die unabhängige Referenz fuer die am Ende gueltigen Antworten berechnet (Pfadunabhaengigkeit, keine
Untertriage). Dazu Rechte, Eingaben, Parallelitaet, Idempotenz, Datenschutz in Logs und Audit.
"""

# ruff: noqa: S311, F811, F401

import random
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

import a3_triage_ref as ref
from app.persistence.models import AuditEvent
from conftest import run_parallel
from test_a3_t13 import (
    ANCHOR,
    BASE,
    api,
    clear_responses,
    client_for,
    real_template,
)
from test_a3_t14 import session_setup, truth_grades
from test_a3_t16 import SESSIONS, answer, start
from test_t16_triage import clear_history, triage_get
from waechter.models import CheckinSession, Response, TriageDecision
from waechter.triage.kb import load_kb


def undo(client: TestClient, sid: str, steps: Any) -> Any:
    return client.post(f"{SESSIONS}/{sid}/undo", json={"steps": steps})


def run_with_undos(
    client: TestClient, rng: random.Random, p_zero: float, p_undo: float
) -> tuple[dict[tuple[str, str], int], dict[str, Any], int]:
    """Antwortet zufaellig, nimmt zwischendurch zurueck und antwortet anders; liefert die am Ende
    gueltigen Antworten (Stapel), den Stopp und die Zahl der Zuruecknahmen."""
    status, step = start(client)
    assert status == 201, step
    sid = step["session_id"]
    stack: list[tuple[tuple[str, str], int]] = []
    undone = 0
    for _ in range(80):
        question = step["next"]
        if question is None:
            return dict(stack), step, undone
        if stack and rng.random() < p_undo:
            reply = undo(client, sid, len(stack))
            assert reply.status_code == 200, reply.text
            stack.pop()
            undone += 1
            step = reply.json()
            assert step["progress"]["asked"] == len(stack)
            continue
        values = [o["value"] for o in question["options"]]
        key = (question["symptom_key"], question["attribute"])
        value = 0 if rng.random() < p_zero else rng.choice(values)
        reply = answer(client, sid, key[0], key[1], value)
        assert reply.status_code == 200, reply.text
        stack.append((key, value))
        step = reply.json()
    raise AssertionError("session did not stop")


def test_a3_undo_and_reanswer_gives_the_decision_of_the_reference(
    api: tuple[FastAPI, Any],
) -> None:
    app, _ = api
    kb = load_kb()
    theirs, mine, *_ = session_setup(kb, "PEMBROLIZUMAB")
    patient = client_for(app, "patient2")
    doctor = client_for(app, "doctor")
    rng = random.Random(3131)
    mismatches: list[str] = []
    seen = {"GREEN": 0, "YELLOW": 0, "RED": 0}
    total_undos = 0
    for run in range(90):
        pid = clear_history(app, "SYN-0002")
        effective, stop, undone = run_with_undos(patient, rng, (0.2, 0.5, 0.8)[run % 3], 0.35)
        total_undos += undone
        want = ref.final_level(mine, truth_grades(theirs, effective), None)
        seen[want] += 1
        body = triage_get(doctor, pid, response_id=stop["receipt"]["response_id"]).json()
        if body["level_lo"] == body["level_hi"] and body["level"] != want:
            mismatches.append(f"{effective}: Referenz {want}, API {body['level']}")
    assert mismatches == [], mismatches[:3]
    assert total_undos >= 60, "zu wenige Zuruecknahmen, Test waere wirkungslos"
    assert min(seen.values()) >= 4, seen


def test_a3_undo_never_leaves_an_extra_response_or_decision(api: tuple[FastAPI, Any]) -> None:
    app, _ = api
    patient = client_for(app, "patient2")
    pid = clear_history(app, "SYN-0002")
    rng = random.Random(77)
    _, stop, undone = run_with_undos(patient, rng, 0.4, 0.4)
    assert undone >= 1
    with app.state.session_factory() as session:
        responses = session.scalars(select(Response).where(Response.patient_id == pid)).all()
        decisions = session.scalars(
            select(TriageDecision).where(TriageDecision.patient_id == pid)
        ).all()
    assert len(responses) == 1  # eine Antwort pro abgeschlossener Sitzung, nicht je Zwischenstand
    assert len(decisions) == 1
    assert stop["receipt"]["response_id"] == responses[0].id


@pytest.mark.parametrize("steps", [-1, 201, 1.5, "1", None, True, [1], {"a": 1}])
def test_a3_wrong_undo_input_is_a_clean_422(api: tuple[FastAPI, Any], steps: Any) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    clear_responses(app)
    _, step = start(client)
    reply = client.post(f"{SESSIONS}/{step['session_id']}/undo", json={"steps": steps})
    assert reply.status_code == 422, (steps, reply.status_code)
    assert "Traceback" not in reply.text
    assert client.post(f"{SESSIONS}/{step['session_id']}/undo", json={}).status_code == 422
    assert client.post(
        f"{SESSIONS}/{step['session_id']}/undo", json={"steps": 0, "x": 1}
    ).status_code in (
        200,
        422,
    )


def test_a3_undo_on_an_unknown_or_foreign_session_and_anonymous(api: tuple[FastAPI, Any]) -> None:
    app, _ = api
    owner = client_for(app, "patient2")
    other = client_for(app, "patient")
    clear_responses(app)
    _, step = start(owner)
    sid = step["session_id"]
    first = step["next"]
    answer(owner, sid, first["symptom_key"], first["attribute"], 1)
    before = owner.get(f"{SESSIONS}/{sid}").json()
    assert undo(other, sid, 1).status_code == 404
    assert undo(owner, "00000000-0000-4000-8000-000000000000", 1).status_code == 404
    assert undo(TestClient(app), sid, 1).status_code in (401, 403)
    for role in ("doctor", "admin"):
        assert undo(client_for(app, role), sid, 1).status_code in (403, 404)
    assert owner.get(f"{SESSIONS}/{sid}").json() == before  # nichts veraendert


def test_a3_stale_or_wrong_step_count_never_removes_an_answer(api: tuple[FastAPI, Any]) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    clear_responses(app)
    _, step = start(client)
    sid = step["session_id"]
    for _ in range(3):
        q = step["next"]
        step = answer(client, sid, q["symptom_key"], q["attribute"], 0).json()
    asked = step["progress"]["asked"]
    assert asked == 3
    for wrong in (0, 1, 2, 4, 50):
        reply = undo(client, sid, wrong)
        assert reply.status_code == 200
        assert reply.json()["progress"]["asked"] == 3, wrong
    right = undo(client, sid, 3)
    assert right.json()["progress"]["asked"] == 2
    again = undo(client, sid, 3)  # veraltet: nichts weiter
    assert again.json()["progress"]["asked"] == 2


def test_a3_parallel_undos_with_the_same_step_count_remove_exactly_one_answer(
    api: tuple[FastAPI, Any],
) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    clear_responses(app)
    _, step = start(client)
    sid = step["session_id"]
    for _ in range(3):
        q = step["next"]
        step = answer(client, sid, q["symptom_key"], q["attribute"], 0).json()

    def one(_: int) -> int:
        return int(undo(client_for(app, "patient2"), sid, 3).json()["progress"]["asked"])

    results = run_parallel(one, 4)
    assert set(results) <= {2}, results
    final = client.get(f"{SESSIONS}/{sid}").json()
    assert final["progress"]["asked"] == 2


def test_a3_undo_after_an_acute_stop_is_refused_and_keeps_the_decision(
    api: tuple[FastAPI, Any],
) -> None:
    """Wer Fieber angibt und beendet, kann die rote Entscheidung nicht per Zurueck loeschen."""
    app, _ = api
    client = client_for(app, "patient2")
    pid = clear_history(app, "SYN-0002")
    _, step = start(client)
    sid = step["session_id"]
    for _ in range(40):
        q = step["next"]
        if q is None:
            break
        value = 1 if q["symptom_key"] == "fever" and q["attribute"] == "presence" else 0
        step = answer(client, sid, q["symptom_key"], q["attribute"], value).json()
    assert step["next"] is None
    assert step["receipt"]
    asked = step["progress"]["asked"]
    for steps in (asked, asked - 1, 1):
        reply = undo(client, sid, steps)
        assert reply.status_code == 409, (steps, reply.status_code, reply.text)
    with app.state.session_factory() as session:
        row = session.scalars(select(CheckinSession).where(CheckinSession.id == sid)).one()
        assert row.status == "closed"
        decisions = session.scalars(
            select(TriageDecision).where(TriageDecision.patient_id == pid)
        ).all()
    assert len(decisions) == 1


def test_a3_audit_and_logs_of_undo_contain_no_answer_values(
    api: tuple[FastAPI, Any], caplog: pytest.LogCaptureFixture
) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    clear_responses(app)
    _, step = start(client)
    sid = step["session_id"]
    q = step["next"]
    answer(client, sid, q["symptom_key"], q["attribute"], 3)
    undo(client, sid, 1)
    with app.state.session_factory() as session:
        details = " ".join(str(e.details_json) for e in session.scalars(select(AuditEvent)).all())
    assert '"value"' not in details
    assert "undo" not in caplog.text.lower() or "value" not in caplog.text.lower()
