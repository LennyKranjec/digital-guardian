"""Gemeinsame Fixtures: migrierte Wegwerf-DB, App, Client, geseedete Demo-Konten."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.db import create_db_engine
from app.core.settings import Settings
from app.main import create_app
from app.persistence.migrate import upgrade_to_head
from app.services.seed import DEMO_PASSWORD

CSRF = {"X-Requested-With": "fetch"}
FROZEN_NOW = datetime(2026, 10, 14, 8, 0, tzinfo=UTC)


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    """Settings mit migrierter Wegwerf-DB; ohne Challenge-Ordner (leere Plattform)."""
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    engine = create_db_engine(url)
    try:
        upgrade_to_head(engine)
    finally:
        engine.dispose()
    return Settings(
        _env_file=None, database_url=url, challenge_dir=tmp_path / "no-challenge", **overrides
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded_app(tmp_path: Path) -> Iterator[FastAPI]:
    """App mit migrierter DB, Demo-Konten und eingefrorener Uhr."""
    from app.services import seed

    application = create_app(make_settings(tmp_path, app_frozen_now=FROZEN_NOW))
    with application.state.session_factory() as session:
        seed.provision(
            session, application.state.settings, application.state.registry, application.state.clock
        )
    yield application
    application.state.engine.dispose()


@pytest.fixture
def seeded_client(seeded_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(seeded_app, headers=CSRF) as test_client:
        yield test_client


def login_as(client: TestClient, username: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())
