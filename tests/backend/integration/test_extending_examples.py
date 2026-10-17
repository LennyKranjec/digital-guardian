"""Ausführbare Beispiele zu docs/EXTENDING.md: Modul (Router), Datenmodell (Modell + Migration),
Rolle, Demo-Konto, Seed-Schritt, Meta-Erweiterung, Subjekt-Auflösung und deterministische Regel.

Das Challenge-Paket entsteht hier in einem Wegwerf-Ordner; echt liegt es unter `challenge/`.
"""

import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.db import create_db_engine
from app.core.settings import Settings
from app.main import create_app
from app.persistence.migrate import upgrade_to_head
from app.plugins import load_challenge_plugin
from app.registry import Registry
from app.services import seed
from tests.backend.conftest import CSRF

MODELS = """
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ChallengeBase(DeclarativeBase):
    pass


class Note(ChallengeBase):
    __tablename__ = "example_notes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
"""

MIGRATION = '''
"""Beispiel-Migration des Challenge-Pakets (hängt an der Plattform-Revision 0001)."""
import sqlalchemy as sa
from alembic import op

revision = "c001"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "example_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(80), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("example_notes")
'''

PLUGIN = """
import importlib.util
from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import text

from app.registry import DemoAccount

HERE = Path(__file__).parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def register(registry):
    models = _load("models")
    router = APIRouter(prefix="/example", tags=["example"])

    @router.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    registry.add_router(router)
    registry.add_role("reviewer", "Beispielrolle")
    registry.add_demo_account(
        DemoAccount("rev", "demo-passwort-2026", "reviewer", "Reviewer (Demo)")
    )
    registry.add_meta_extension(lambda settings: {"example": {"enabled": True}})
    registry.add_metadata(models.ChallengeBase.metadata, migrations=HERE / "migrations")
    registry.set_subject_resolver(lambda session, user_id: f"subject-of-{user_id[:4]}")

    def seed_notes(session, clock):
        session.execute(
            text("INSERT OR IGNORE INTO example_notes (id, title) VALUES ('n1', 'Beispiel')")
        )

    registry.add_seed_step(seed_notes)
"""


@pytest.fixture
def challenge_dir(tmp_path: Path) -> Path:
    backend = tmp_path / "challenge" / "backend"
    (backend / "migrations").mkdir(parents=True)
    (backend / "models.py").write_text(textwrap.dedent(MODELS), encoding="utf-8")
    (backend / "migrations" / "c001_notes.py").write_text(
        textwrap.dedent(MIGRATION), encoding="utf-8"
    )
    (backend / "plugin.py").write_text(textwrap.dedent(PLUGIN), encoding="utf-8")
    return tmp_path / "challenge"


def test_platform_without_challenge_is_empty(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, challenge_dir=tmp_path / "missing")
    registry = Registry()
    assert load_challenge_plugin(settings, registry) is False
    assert registry.routers == []
    assert registry.demo_accounts == []


def test_challenge_package_extends_the_platform(tmp_path: Path, challenge_dir: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'ext.db').as_posix()}"
    settings = Settings(_env_file=None, database_url=url, challenge_dir=challenge_dir)
    registry = Registry()
    assert load_challenge_plugin(settings, registry) is True

    engine = create_db_engine(url)
    try:
        upgrade_to_head(engine, registry)  # Plattform 0001 + Challenge c001
        assert {"users", "audit_events", "example_notes"} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    app = create_app(settings, Registry())  # frische Registry, lädt das Plugin selbst
    with sessionmaker(app.state.engine)() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
        assert session.execute(text("SELECT title FROM example_notes")).scalar_one() == "Beispiel"

    with TestClient(app, headers=CSRF) as client:
        assert client.get("/api/v1/example/ping").json() == {"pong": "ok"}  # neues Modul
        meta = client.get("/api/v1/meta").json()
        assert meta["example"] == {"enabled": True}
        assert "reviewer" in meta["roles"]
        assert meta["challenge_loaded"] is True
        accounts = {a["username"] for a in client.get("/api/v1/demo/accounts").json()}
        assert accounts == {"admin", "user", "rev"}
        me = client.post(
            "/api/v1/auth/login", json={"username": "rev", "password": "demo-passwort-2026"}
        ).json()
        assert me["role"] == "reviewer"
        assert me["subject_id"].startswith("subject-of-")


def test_meta_extension_cannot_override_platform_keys(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, challenge_dir=tmp_path / "none")
    registry = Registry()
    registry.add_meta_extension(lambda s: {"version": "evil"})
    from app.services import system

    with pytest.raises(ValueError, match="must not override"):
        system.get_meta(settings, registry)


def deterministic_rule(value: int, threshold: int) -> str:
    """Beispiel „neue Regel“: reine Funktion mit festem Schwellenwert, ohne Zufall oder LLM."""
    return "above" if value >= threshold else "below"


def test_example_rule_is_deterministic() -> None:
    assert [deterministic_rule(v, 5) for v in (4, 5, 6)] == ["below", "above", "above"]
    assert deterministic_rule(5, 5) == deterministic_rule(5, 5)
