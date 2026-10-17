"""Anmeldung, Sitzung, Rollen, CSRF und Audit des Auth-Gerüsts (neutrale Konten admin/user)."""

from datetime import timedelta

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import require_roles
from app.persistence.models import AuditEvent, AuthSession, User
from app.services.auth import Principal
from tests.backend.conftest import CSRF, FROZEN_NOW, login_as
from tests.backend.helpers import run_parallel


def test_login_me_logout_cycle(seeded_client: TestClient) -> None:
    body = login_as(seeded_client, "admin")
    assert body["role"] == "admin"
    assert body["subject_id"] is None
    assert seeded_client.get("/api/v1/auth/me").json()["username"] == "admin"
    assert seeded_client.post("/api/v1/auth/logout").status_code == 204
    assert seeded_client.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_and_unknown_user_look_the_same(seeded_client: TestClient) -> None:
    wrong = seeded_client.post("/api/v1/auth/login", json={"username": "admin", "password": "x"})
    unknown = seeded_client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["code"] == "invalid_credentials"


def test_mutating_requests_need_the_csrf_header(seeded_app: FastAPI) -> None:
    client = TestClient(seeded_app)  # ohne CSRF-Header
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "x"})
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_header_missing"


def test_roles_are_enforced_on_the_server(seeded_app: FastAPI) -> None:
    router = APIRouter()

    @router.get("/admin-only")
    def admin_only(principal: Principal = Depends(require_roles("admin"))) -> dict[str, str]:  # noqa: B008
        return {"who": principal.username}

    seeded_app.include_router(router, prefix="/api/v1")
    with TestClient(seeded_app, headers=CSRF) as client:
        assert client.get("/api/v1/admin-only").status_code == 401
        login_as(client, "user")
        denied = client.get("/api/v1/admin-only")
        assert denied.status_code == 403
        assert denied.json()["code"] == "forbidden"
    with TestClient(seeded_app, headers=CSRF) as client:
        login_as(client, "admin")
        assert client.get("/api/v1/admin-only").json() == {"who": "admin"}


def test_audit_records_login_without_secrets(seeded_app: FastAPI) -> None:
    with TestClient(seeded_app, headers=CSRF) as client:
        client.post("/api/v1/auth/login", json={"username": "admin", "password": "secret-wrong"})
        login_as(client, "admin")
    with seeded_app.state.session_factory() as session:
        events = list(session.scalars(select(AuditEvent).order_by(AuditEvent.at)))
    actions = [e.action for e in events]
    assert "auth.login_failed" in actions
    assert "auth.login" in actions
    assert all("secret-wrong" not in str(e.details_json) for e in events)
    assert all(e.synthetic for e in events)


def test_parallel_logins_all_succeed(seeded_app: FastAPI) -> None:
    def attempt() -> int:
        with TestClient(seeded_app, headers=CSRF) as client:
            return client.post(
                "/api/v1/auth/login", json={"username": "user", "password": "demo-passwort-2026"}
            ).status_code

    assert run_parallel(attempt, 4) == [200, 200, 200, 200]


def test_audit_events_cannot_be_updated(seeded_app: FastAPI) -> None:
    with seeded_app.state.session_factory() as session:
        with TestClient(seeded_app, headers=CSRF) as client:
            login_as(client, "admin")
        event = session.scalars(select(AuditEvent)).first()
        assert event is not None
        event.action = "tampered"
        with pytest.raises(RuntimeError, match="append-only"):
            session.commit()


def _deactivate(app: FastAPI, username: str) -> None:
    with app.state.session_factory() as session:
        user = session.scalars(select(User).where(User.username == username)).one()
        user.is_active = False
        session.commit()


def test_deactivated_account_cannot_log_in(seeded_app: FastAPI) -> None:
    _deactivate(seeded_app, "user")
    with TestClient(seeded_app, headers=CSRF) as client:
        response = client.post(
            "/api/v1/auth/login", json={"username": "user", "password": "demo-passwort-2026"}
        )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"  # gleiche Antwort wie falsches Passwort


def test_session_of_a_later_deactivated_account_is_rejected(seeded_app: FastAPI) -> None:
    with TestClient(seeded_app, headers=CSRF) as client:
        login_as(client, "user")
        assert client.get("/api/v1/auth/me").status_code == 200
        _deactivate(seeded_app, "user")
        assert client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected_under_a_frozen_clock(seeded_app: FastAPI) -> None:
    with TestClient(seeded_app, headers=CSRF) as client:
        login_as(client, "admin")
        assert client.get("/api/v1/auth/me").status_code == 200
        with seeded_app.state.session_factory() as session:
            auth_session = session.scalars(select(AuthSession)).one()
            auth_session.expires_at = FROZEN_NOW - timedelta(seconds=1)
            session.commit()
        assert client.get("/api/v1/auth/me").status_code == 401
