"""T-31 (A0): Zurück-Pfeil: letzte Antwort einer offenen adaptiven Sitzung zurücknehmen."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from test_a3_t13 import (  # noqa: F401
    api,
    clear_responses,
    client_for,
    real_template,
)
from test_a3_t16 import SESSIONS, answer, start


def _key(step: dict[str, Any]) -> tuple[str, str]:
    return step["next"]["symptom_key"], step["next"]["attribute"]


def test_undo_offers_the_last_question_again_and_is_idempotent(
    api: tuple[FastAPI, Any],  # noqa: F811
) -> None:
    app, _ = api
    client = client_for(app, "patient2")
    clear_responses(app)
    status, step = start(client)
    assert status == 201
    sid = step["session_id"]
    first = _key(step)
    one = answer(client, sid, *first, 1)
    assert one.status_code == 200
    assert one.json()["progress"]["asked"] == 1
    back = client.post(f"{SESSIONS}/{sid}/undo", json={"steps": 1})
    assert back.status_code == 200, back.text
    assert _key(back.json()) == first
    assert back.json()["progress"]["asked"] == 0
    again = client.post(f"{SESSIONS}/{sid}/undo", json={"steps": 1})  # veralteter Stand
    assert again.status_code == 200
    assert again.json() == back.json()  # nichts weiter zurückgenommen
    corrected = answer(client, sid, *first, 0)  # andere Antwort auf dieselbe Frage
    assert corrected.status_code == 200


def test_undo_is_private_and_impossible_after_the_session_closed(
    api: tuple[FastAPI, Any],  # noqa: F811
) -> None:
    app, _ = api
    owner = client_for(app, "patient2")
    other = client_for(app, "patient")
    doctor = client_for(app, "doctor")
    clear_responses(app)
    _, step = start(owner)
    sid = step["session_id"]
    assert other.post(f"{SESSIONS}/{sid}/undo", json={"steps": 0}).status_code == 404
    assert doctor.post(f"{SESSIONS}/{sid}/undo", json={"steps": 0}).status_code in (403, 404)
    for _ in range(60):  # bis zum Stopp beantworten
        if not step.get("next"):
            break
        reply = answer(owner, sid, *_key(step), 0)
        assert reply.status_code == 200
        step = reply.json()
    asked = step["progress"]["asked"]
    closed = owner.post(f"{SESSIONS}/{sid}/undo", json={"steps": asked})
    assert closed.status_code == 409
    assert "session_closed" in closed.text
