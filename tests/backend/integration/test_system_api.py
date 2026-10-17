"""`/health`, `/meta`, `/demo/accounts`, Header und Fehlerformat der leeren Plattform."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app


def test_health_ok_on_migrated_db(client: TestClient) -> None:
    assert client.get("/api/v1/health").json() == {"status": "ok", "db": "ok"}


def test_health_reports_not_migrated(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'empty.db').as_posix()}",
        challenge_dir=tmp_path / "none",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["code"] == "db_unavailable"


def test_meta_of_the_empty_platform(client: TestClient) -> None:
    meta = client.get("/api/v1/meta").json()
    assert meta["synthetic_data"] is True
    assert meta["challenge_loaded"] is False
    assert meta["roles"] == ["admin", "user"]


def test_demo_accounts_only_in_demo_mode(tmp_path: Path) -> None:
    from tests.backend.conftest import make_settings

    on = TestClient(create_app(make_settings(tmp_path)))
    assert [a["username"] for a in on.get("/api/v1/demo/accounts").json()] == ["admin", "user"]
    off = TestClient(create_app(make_settings(tmp_path / "off", demo_mode=False)))
    assert off.get("/api/v1/demo/accounts").status_code == 404


def test_api_responses_are_never_cached_and_carry_security_headers(client: TestClient) -> None:
    response = client.get("/api/v1/meta")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
