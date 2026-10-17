"""Paralleltest für den schreibenden Endpunkt POST /me/responses (COMMON §4)."""

import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from conftest import CSRF, login, run_parallel
from waechter.models import Answer, Response

RESPONSES = "/api/v1/waechter/me/responses"
WORKERS = 4


def _payload(submission_id: str, value: int) -> dict[str, Any]:
    return {
        "client_submission_id": submission_id,
        "questionnaire_id": "items-v1:FIX-REG",
        "answers": [
            {"symptom_key": "nausea", "attribute": "severity", "value": value},
            {"symptom_key": "fever", "attribute": "presence", "value": 0},
        ],
    }


def _stored(app: FastAPI, submission_id: str) -> tuple[int, int]:
    with app.state.session_factory() as session:
        ids = list(
            session.scalars(
                select(Response.id).where(Response.client_submission_id == submission_id)
            )
        )
        answers = session.scalar(
            select(func.count()).select_from(Answer).where(Answer.response_id.in_(ids))
        )
    return len(ids), answers or 0


def test_four_identical_submissions_store_exactly_one_record(seeded_app: FastAPI) -> None:
    submission_id = str(uuid.uuid4())
    clients = []
    for _ in range(WORKERS):
        c = TestClient(seeded_app, headers=CSRF)
        login(c, "patient")
        clients.append(c)
    results = run_parallel(
        lambda i: clients[i].post(RESPONSES, json=_payload(submission_id, 2)), WORKERS
    )
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201], [
        (r.status_code, r.text) for r in results
    ]
    assert len({r.json()["response_id"] for r in results}) == 1  # überall derselbe Beleg
    assert _stored(seeded_app, submission_id) == (1, 2)


def test_four_different_bodies_with_one_id_yield_exactly_one_success(seeded_app: FastAPI) -> None:
    submission_id = str(uuid.uuid4())
    clients = []
    for _ in range(WORKERS):
        c = TestClient(seeded_app, headers=CSRF)
        login(c, "patient")
        clients.append(c)
    results = run_parallel(
        lambda i: clients[i].post(RESPONSES, json=_payload(submission_id, i)), WORKERS
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [201, 409, 409, 409], [(r.status_code, r.text) for r in results]
    assert _stored(seeded_app, submission_id) == (1, 2)
