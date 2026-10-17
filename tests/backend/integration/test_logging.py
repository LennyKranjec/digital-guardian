"""Logging ohne Request-Bodies (docs/ARCHITECTURE.md, docs/RULES.md)."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


class Note(BaseModel):
    text: str


@pytest.fixture
def note_app(app: FastAPI) -> FastAPI:
    @app.post("/probe/note")
    def create_note(note: Note) -> dict[str, int]:
        return {"length": len(note.text)}

    @app.get("/probe/crash")
    def crash() -> None:
        raise RuntimeError("body-secret-in-exception")

    return app


@pytest.fixture(autouse=True)
def propagate_app_logs() -> None:
    # `configure_logging` hängt einen eigenen Handler an; caplog braucht Propagation zum Root.
    logging.getLogger("app").propagate = True


def test_access_log_has_method_path_status_but_no_body_or_query(
    note_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    client = TestClient(note_app)
    with caplog.at_level(logging.INFO, logger="app"):
        response = client.post("/probe/note?token=query-secret", json={"text": "free-text-secret"})
    assert response.status_code == 200
    log_text = caplog.text
    assert "method=POST path=/probe/note status=200" in log_text
    assert "free-text-secret" not in log_text
    assert "query-secret" not in log_text


def test_response_carries_request_id_matching_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app"):
        response = client.get("/api/v1/meta")
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert f"request_id={request_id}" in caplog.text


def test_unhandled_error_logs_type_only(
    note_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    client = TestClient(note_app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="app"):
        client.get("/probe/crash")
    assert "error=RuntimeError" in caplog.text
    assert "body-secret-in-exception" not in caplog.text
