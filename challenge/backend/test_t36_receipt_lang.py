"""T-36 (A0): Tipps/Eskalation im Beleg in der Sprache des Sendens (nicht Patientensprache)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI

from test_a3_t13 import (  # noqa: F401
    api,
    clear_responses,
    client_for,
    real_template,
)
from test_a3_t16 import answer, start


def _finish(client: Any, step: dict[str, Any]) -> dict[str, Any]:
    sid = step["session_id"]
    for _ in range(60):
        question = step.get("next")
        if not question:
            return step
        value = 1 if question["symptom_key"] == "fever" else 0
        reply = answer(client, sid, question["symptom_key"], question["attribute"], value)
        assert reply.status_code == 200, reply.text
        step = reply.json()
    raise AssertionError("session did not stop")


def test_receipt_advice_follows_the_session_language(
    api: tuple[FastAPI, Any],  # noqa: F811
) -> None:
    app, _ = api
    client = client_for(app, "patient2")  # gespeicherte Sprache der Patientin: cs
    clear_responses(app)
    status, step = start(client, lang="en")
    assert status == 201
    done = _finish(client, step)
    text = json.dumps(done, ensure_ascii=False)
    i = text.find("155")
    assert "call 155" in text, text[max(0, i - 400) : i + 50]  # englischer Akut-Hinweis
    assert "volejte 155" not in text
