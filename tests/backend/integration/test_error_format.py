"""Fehlerformat laut docs/ARCHITECTURE.md: {code, message, field_errors[]}."""

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ApiError, FieldError


class Payload(BaseModel):
    age: int


@pytest.fixture
def probe_app(app: FastAPI) -> FastAPI:
    @app.get("/probe/query")
    def probe_query(limit: int = Query(le=200)) -> dict[str, int]:
        return {"limit": limit}

    @app.post("/probe/body")
    def probe_body(payload: Payload) -> Payload:
        return payload

    @app.get("/probe/api-error")
    def probe_api_error() -> None:
        raise ApiError(
            409,
            "invalid_transition",
            "Transition not allowed",
            [FieldError(field="to_status", code="not_allowed", message="no")],
        )

    @app.get("/probe/crash")
    def probe_crash() -> None:
        raise RuntimeError("secret-value-must-not-leak")

    return app


@pytest.fixture
def probe(probe_app: FastAPI) -> TestClient:
    return TestClient(probe_app, raise_server_exceptions=False)


def assert_error_shape(body: dict[str, object]) -> None:
    assert set(body) == {"code", "message", "field_errors"}
    assert isinstance(body["code"], str)
    assert isinstance(body["message"], str)
    assert isinstance(body["field_errors"], list)


def test_unknown_route_is_404_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert_error_shape(body)
    assert body["code"] == "not_found"


def test_wrong_method_is_405(client: TestClient) -> None:
    # Seit T-202 verlangt jede mutierende Anfrage den CSRF-Header; ohne ihn wäre die Antwort 403.
    response = client.post("/api/v1/health", headers={"X-Requested-With": "fetch"})
    assert response.status_code == 405
    body = response.json()
    assert_error_shape(body)
    assert body["code"] == "method_not_allowed"


def test_query_validation_is_422_with_field_errors(probe: TestClient) -> None:
    response = probe.get("/probe/query", params={"limit": 999})
    assert response.status_code == 422
    body = response.json()
    assert_error_shape(body)
    assert body["code"] == "validation_failed"
    assert body["field_errors"][0]["field"] == "limit"
    assert body["field_errors"][0]["code"] == "less_than_equal"


def test_body_validation_names_field_and_hides_input_value(probe: TestClient) -> None:
    response = probe.post("/probe/body", json={"age": "very-private-text"})
    assert response.status_code == 422
    body = response.json()
    assert body["field_errors"][0]["field"] == "age"
    assert "very-private-text" not in response.text


def test_api_error_carries_code_and_field_errors(probe: TestClient) -> None:
    response = probe.get("/probe/api-error")
    assert response.status_code == 409
    assert response.json() == {
        "code": "invalid_transition",
        "message": "Transition not allowed",
        "field_errors": [{"field": "to_status", "code": "not_allowed", "message": "no"}],
    }


def test_unhandled_exception_is_500_without_details(probe: TestClient) -> None:
    response = probe.get("/probe/crash")
    assert response.status_code == 500
    body = response.json()
    assert_error_shape(body)
    assert body["code"] == "internal_error"
    assert "secret-value-must-not-leak" not in response.text
