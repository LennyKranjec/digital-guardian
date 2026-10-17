"""H-5 (Safety): die Eingabe der Patientin geht nie durch einen Regelfehler verloren."""

import logging
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.memory_notifier import MemoryNotifier
from app.main import create_app
from app.persistence.models import AuditEvent
from app.services import seed
from conftest import CSRF, login, make_settings, migrate
from waechter import notifier
from waechter.models import Alert, Answer, Notification, Patient, Response
from waechter.services import alerts, hooks

RESPONSES = "/api/v1/waechter/me/responses"
MARKER = "GEHEIM-4711"


@pytest.fixture
def mailbox() -> Iterator[MemoryNotifier]:
    previous = notifier.get_notifier()
    fresh = MemoryNotifier()
    notifier.set_notifier(fresh)
    yield fresh
    notifier.set_notifier(previous)


def body(severity: int = 3, fever: int = 1) -> dict[str, Any]:
    return {
        "client_submission_id": str(uuid.uuid4()),
        "questionnaire_id": "items-v1:FIX-REG",
        "answers": [
            {"symptom_key": "nausea", "attribute": "severity", "value": severity},
            {"symptom_key": "fever", "attribute": "presence", "value": fever},
        ],
    }


def stored(app: FastAPI, csid: str) -> list[Response]:
    with app.state.session_factory() as session:
        return list(session.scalars(select(Response).where(Response.client_submission_id == csid)))


def count(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_successful_evaluation_marks_the_response_done(seeded_app: FastAPI) -> None:
    with TestClient(seeded_app, headers=CSRF) as client:
        login(client, "patient2")
        payload = body()
        assert client.post(RESPONSES, json=payload).status_code == 201
    (row,) = stored(seeded_app, payload["client_submission_id"])
    assert row.evaluation_status == "done"
    with seeded_app.state.session_factory() as session:
        assert not session.scalars(
            select(AuditEvent).where(AuditEvent.action == "rule_evaluation_failed")
        ).all()


def test_rule_error_keeps_the_answer_and_marks_it_failed(
    seeded_app: FastAPI,
    mailbox: MemoryNotifier,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def explode(session: Session, response: Response) -> None:
        # erst etwas schreiben (Meldung + Benachrichtigung), dann scheitern: alles muss zurück
        alerts.evaluate_response(session, response)
        raise RuntimeError(f"kaputt {MARKER}")

    monkeypatch.setattr(hooks, "on_response_saved", explode)
    sent_before = len(mailbox.sent)
    with seeded_app.state.session_factory() as session:
        alerts_before, notes_before = count(session, Alert), count(session, Notification)
    payload = body()
    caplog.set_level(logging.DEBUG)
    with TestClient(seeded_app, headers=CSRF) as client:
        login(client, "patient2")
        created = client.post(RESPONSES, json=payload)
        replay = client.post(RESPONSES, json=payload)
    # Patientin merkt nichts: neutraler Beleg, Replay liefert denselben
    assert created.status_code == 201, created.text
    assert set(created.json()) == {
        "response_id",
        "recorded_at",
        "answered",
        "skipped",
        "message_key",
    }
    assert replay.status_code == 200
    assert replay.json() == created.json()
    # die Eingabe ist gespeichert und als "Auswertung fehlgeschlagen" markiert
    (row,) = stored(seeded_app, payload["client_submission_id"])
    assert row.evaluation_status == "failed"
    with seeded_app.state.session_factory() as session:
        assert count(session, Answer) >= 2
        assert (
            session.scalar(
                select(func.count()).select_from(Answer).where(Answer.response_id == row.id)
            )
            == 2
        )
        # die Regel-Transaktion wurde zurückgerollt: keine Meldung, keine Benachrichtigung
        assert count(session, Alert) == alerts_before
        assert count(session, Notification) == notes_before
        audits = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "rule_evaluation_failed")
        ).all()
        assert len(audits) == 1
        assert audits[0].target_id == row.id
        assert audits[0].details_json == {"error": "RuntimeError"}
        assert MARKER not in str(audits[0].details_json)
        submit_audits = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "submit_response")
        ).all()
        assert any(a.target_id == row.id for a in submit_audits)
    assert len(mailbox.sent) == sent_before  # nichts "ausgesendet", was zurückgerollt wurde
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "rule evaluation failed (RuntimeError)" in logged
    assert MARKER not in logged  # Fehler ohne Werte


def test_evaluation_failure_is_not_a_server_error(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: Session, response: Response) -> None:
        raise ValueError("x")

    monkeypatch.setattr(hooks, "on_response_saved", boom)
    with TestClient(seeded_app, headers=CSRF, raise_server_exceptions=False) as client:
        login(client, "patient")
        assert client.post(RESPONSES, json=body()).status_code == 201
        listed = client.get(RESPONSES).json()
    assert len(listed) >= 4  # drei Seed-Antworten plus die neue


def test_seed_uses_the_same_path_and_marks_failures(
    tmp_path: Path, mailbox: MemoryNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(session: Session, response: Response) -> None:
        raise RuntimeError(MARKER)

    monkeypatch.setattr(hooks, "on_response_saved", boom)
    settings = make_settings(tmp_path)
    migrate(settings)
    app = create_app(settings)
    with app.state.session_factory() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
        seed.provision(session, settings, app.state.registry, app.state.clock)  # idempotent
    with app.state.session_factory() as session:
        responses = session.scalars(select(Response)).all()
        assert responses
        assert {r.evaluation_status for r in responses} == {"failed"}
        assert count(session, Patient) >= 3
        assert count(session, Alert) == 0
        audits = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "rule_evaluation_failed")
        ).all()
        assert len(audits) == len(responses)  # je Antwort genau ein Audit, auch nach 2. Seed
        assert {a.actor_role for a in audits} == {"system"}
    assert not mailbox.sent


def test_seed_without_failure_marks_everything_done(
    tmp_path: Path, mailbox: MemoryNotifier
) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    app = create_app(settings)
    with app.state.session_factory() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
    with app.state.session_factory() as session:
        assert {r.evaluation_status for r in session.scalars(select(Response))} == {"done"}
        assert count(session, Alert) >= 1
    assert mailbox.sent  # rote Meldungen wurden nach dem Commit über den Port gesendet
