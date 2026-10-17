"""Fixtures der Wächter-Tests: Fixture-Inhalte, migrierte Wegwerf-DB, eingefrorene Uhr.

Tests nutzen nie `challenge/content/` (Besitz A1) und nie das Tagesdatum (`FROZEN_NOW`).
"""

import shutil
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.db import create_db_engine
from app.core.settings import Settings
from app.main import create_app
from app.persistence.migrate import upgrade_to_head
from app.registry import Registry
from app.services import seed
from app.services.seed import DEMO_PASSWORD
from waechter.constants import CONTENT_DIR_ENV

CHALLENGE_DIR = Path(__file__).resolve().parents[1]
FIXTURE_CONTENT = Path(__file__).resolve().parent / "fixtures" / "content"
FROZEN_NOW = datetime(2026, 10, 17, 7, 0, tzinfo=UTC)
CSRF = {"X-Requested-With": "fetch"}


@pytest.fixture(autouse=True)
def fixture_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Alle Tests lesen die kleine Fixture-Welt; einzelne Tests überschreiben die Variable."""
    monkeypatch.setenv(CONTENT_DIR_ENV, str(FIXTURE_CONTENT))
    return FIXTURE_CONTENT


@pytest.fixture(autouse=True)
def no_triage_warmup_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests kompilieren die Bäume selbst (Cache); kein Hintergrundthread neben dem Test."""
    monkeypatch.setenv("WAECHTER_TRIAGE_WARMUP", "0")


@pytest.fixture(autouse=True)
def no_network_and_clean_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests nutzen nie das Netz und nie die LLM-Umgebung des Entwicklers (Standard: template)."""
    from waechter.llm import adapters

    for name in (
        adapters.ENV_MODE,
        adapters.ENV_BASE_URL,
        adapters.ENV_API_KEY,
        adapters.ENV_MODEL,
        adapters.ENV_RECORD,
    ):
        monkeypatch.delenv(name, raising=False)

    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access in tests is not allowed")

    monkeypatch.setattr(adapters, "_urlopen", blocked)


@pytest.fixture
def content_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Veränderbare Kopie der Fixture-Inhalte; `WAECHTER_CONTENT_DIR` zeigt darauf."""
    target = tmp_path / "content"
    shutil.copytree(FIXTURE_CONTENT, target)
    monkeypatch.setenv(CONTENT_DIR_ENV, str(target))
    return target


def make_settings(tmp_path: Path) -> Settings:
    """Settings mit Wegwerf-DB; das Challenge-Verzeichnis ist das echte (Plugin wird geladen)."""
    url = f"sqlite:///{(tmp_path / 'wa.db').as_posix()}"
    return Settings(
        _env_file=None, database_url=url, challenge_dir=CHALLENGE_DIR, app_frozen_now=FROZEN_NOW
    )


def migrate(settings: Settings) -> Registry:
    """Plattform + Wächter-Migrationen auf leerer DB; liefert die Registry mit geladenem Plugin."""
    from app.plugins import load_challenge_plugin

    registry = Registry()
    if not load_challenge_plugin(settings, registry):
        pytest.fail("challenge plugin not found")
    engine = create_db_engine(settings.resolved_database_url)
    try:
        upgrade_to_head(engine, registry)
    finally:
        engine.dispose()
    return registry


@pytest.fixture
def waechter_app(tmp_path: Path) -> Iterator[FastAPI]:
    settings = make_settings(tmp_path)
    migrate(settings)
    application = create_app(settings)
    yield application
    application.state.engine.dispose()


@pytest.fixture
def seeded_app(waechter_app: FastAPI) -> FastAPI:
    with waechter_app.state.session_factory() as session:
        seed.provision(
            session,
            waechter_app.state.settings,
            waechter_app.state.registry,
            waechter_app.state.clock,
        )
    return waechter_app


@pytest.fixture
def client(seeded_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(seeded_app, headers=CSRF) as test_client:
        yield test_client


def login(test_client: TestClient, username: str) -> None:
    response = test_client.post(
        "/api/v1/auth/login", json={"username": username, "password": DEMO_PASSWORD}
    )
    if response.status_code != 200:
        pytest.fail(f"login failed: {response.status_code}")


def run_parallel[T](action: Callable[[int], T], workers: int) -> list[T]:
    """Wie `tests/backend/helpers.py::run_parallel` (Barriere ⇒ möglichst gleichzeitiger Start)."""
    barrier = threading.Barrier(workers)

    def task(index: int) -> T:
        barrier.wait(timeout=10)
        return action(index)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(task, i) for i in range(workers)]
        return [f.result(timeout=30) for f in futures]
