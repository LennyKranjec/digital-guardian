"""A3-Gegenproben zu T-02 (Besitz A3): Rollenmatrix, Migration, Seed unter Last, Fehlerverhalten.

Mutationsgeprüft (docs/verification/T-02.md). Keine Tagesdaten, keine Seed-Zahlen.
"""

import shutil
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import yaml
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import create_db_engine
from app.persistence.migrate import downgrade_to_base, upgrade_to_head
from app.services import seed
from conftest import CSRF, login, make_settings, migrate
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import ContentError, load_content
from waechter.models import (
    Alert,
    Answer,
    ConfigVersion,
    Notification,
    Patient,
    Response,
    Therapy,
    Visit,
    WaechterBase,
)

CONFIG = "/api/v1/waechter/config"


def _parallel[T](action: Callable[[], T], workers: int) -> list[T]:
    """Wie `run_parallel` (tests/backend/helpers.py), von hier aus nicht importierbar."""
    barrier = threading.Barrier(workers)

    def task() -> T:
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(task) for _ in range(workers)]
        return [f.result(timeout=30) for f in futures]


# --- B1: Rollenmatrix für GET /config (Vertrag: clinician und admin; sonst 401/403) -------------


@pytest.mark.parametrize(
    ("username", "expected"),
    [(None, 401), ("patient", 403), ("user", 403), ("doctor", 200), ("admin", 200)],
)
def test_a3_config_role_matrix(client: TestClient, username: str | None, expected: int) -> None:
    if username is not None:
        login(client, username)
    response = client.get(CONFIG)
    assert response.status_code == expected, response.text
    if expected != 200:
        body = response.json()
        assert set(body) >= {"code", "message"}  # Fehlerformat der Plattform
        assert "items" not in body  # kein Inhaltsleck im Fehlerfall


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_a3_config_mutations_need_csrf_and_are_not_allowed(
    seeded_app: FastAPI, method: str
) -> None:
    with TestClient(seeded_app) as bare:  # ohne Standard-CSRF-Header
        assert getattr(bare, method)(CONFIG).status_code == 403
    with TestClient(seeded_app, headers=CSRF) as client:
        login(client, "admin")
        assert getattr(client, method)(CONFIG).status_code == 405  # PUT /config existiert nicht


def test_a3_config_body_contains_no_patient_data(client: TestClient) -> None:
    login(client, "doctor")
    body = client.get(CONFIG)
    text = body.text
    from waechter.content import get_content

    content = get_content()
    assert content is not None
    for spec in content.scenario["patients"]:
        for needle in (spec["pseudonym"], spec["display_name"], spec.get("username") or "\0"):
            assert needle not in text, needle
    assert "demo-passwort" not in text


# --- B2/Persistenz: Migration = Modell, Auf-/Abwärts mit Daten, Seed idempotent -----------------


def test_a3_migration_matches_models(tmp_path: Path) -> None:
    """Modell und Migration w001 dürfen nicht auseinanderlaufen (alembic compare_metadata)."""
    settings = make_settings(tmp_path)
    migrate(settings)
    engine = create_db_engine(settings.resolved_database_url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={"compare_type": True, "include_object": lambda o, n, t, r, c: _is_wa(n, t)},
            )
            diffs = compare_metadata(ctx, WaechterBase.metadata)
    finally:
        engine.dispose()
    assert diffs == [], diffs


def _is_wa(name: str | None, kind: str) -> bool:
    return kind != "table" or (name or "").startswith("wa_")


def _counts(session: Session) -> dict[str, int]:
    models = (Patient, Therapy, Visit, Response, Answer, ConfigVersion, Alert, Notification)
    return {m.__name__: session.scalar(select(func.count()).select_from(m)) or 0 for m in models}


def test_a3_down_up_seed_roundtrip_gives_same_content(seeded_app: FastAPI) -> None:
    state = seeded_app.state
    with state.session_factory() as session:
        before = _counts(session)
    downgrade_to_base(state.engine, state.registry)
    upgrade_to_head(state.engine, state.registry)
    with state.session_factory() as session:
        seed.provision(session, state.settings, state.registry, state.clock)
        session.commit()
        assert _counts(session) == before


def test_a3_seed_three_times_no_error_same_rows(seeded_app: FastAPI) -> None:
    state = seeded_app.state
    with state.session_factory() as session:
        before = _counts(session)
        for _ in range(3):
            seed.provision(session, state.settings, state.registry, state.clock)
            session.commit()
        assert _counts(session) == before
        ids = session.scalars(select(Response.client_submission_id)).all()
        assert len(ids) == len(set(ids))


def test_a3_everything_seeded_is_synthetic(seeded_app: FastAPI) -> None:
    with seeded_app.state.session_factory() as session:
        for model in (Patient, Therapy, Visit, Response):
            flags = session.scalars(select(model.synthetic)).all()
            assert flags
            assert all(flags), model.__name__
        wrong = session.scalar(
            select(func.count()).select_from(Patient).where(Patient.synthetic.is_not(True))
        )
        assert wrong == 0


def test_a3_parallel_seed_creates_no_duplicates(waechter_app: FastAPI) -> None:
    """Vier gleichzeitige Seed-Läufe: keine Doppelzeilen; Ausnahmen werden gezählt."""
    state = waechter_app.state

    def run() -> str:
        with state.session_factory() as session:
            try:
                seed.provision(session, state.settings, state.registry, state.clock)
                session.commit()
            except Exception as exc:  # Ergebnis wird unten bewertet
                session.rollback()
                return type(exc).__name__
        return "ok"

    results = _parallel(run, 4)
    with state.session_factory() as session:
        pseudonyms = session.scalars(select(Patient.pseudonym)).all()
        assert len(pseudonyms) == len(set(pseudonyms))
        active = session.scalars(select(ConfigVersion).where(ConfigVersion.active.is_(True))).all()
        assert len({(c.kind) for c in active}) == len(active)  # höchstens eine aktive je Art
    print("A3-PARALLEL-SEED", sorted(results))
    assert "ok" in results  # mindestens ein Lauf gelingt
    # Informativ (siehe Bericht): Fehlerklassen der übrigen Läufe
    assert set(results) <= {"ok", "IntegrityError", "OperationalError"}, results


# --- Loader: Verstöße leaken nie Werte; Laufzeitfehler sind kontrolliert ----------------------

MARKER = "A3-LEAK-MARKER-8841"


def _edit(directory: Path, filename: str, change: Callable[[Any], None]) -> None:
    path = directory / filename
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.mark.parametrize(
    ("filename", "change"),
    [
        ("rules.yaml", lambda d: d["rules"][0].update(level=MARKER)),
        ("rules.yaml", lambda d: d["rules"][0].update(id=MARKER)),
        ("rules.yaml", lambda d: d["rules"][0].update(params={"min_value": MARKER})),
        ("scenario.yaml", lambda d: d["patients"][0].update(pseudonym=MARKER)),
        ("scenario.yaml", lambda d: d["patients"][0].update(regimen_id=MARKER)),
        (
            "scenario.yaml",
            lambda d: d["patients"][0]["responses"][0]["answers"].update({MARKER: 1}),
        ),
        ("items.yaml", lambda d: d["items"][0].update(ctcae_terms=[MARKER])),
        ("items.yaml", lambda d: d.update(version=MARKER)),
        ("regimens.yaml", lambda d: d["regimens"][0]["drugs"][0].update(atc=MARKER)),
    ],
)
def test_a3_loader_errors_never_leak_values(
    content_copy: Path, filename: str, change: Callable[[Any], None]
) -> None:
    _edit(content_copy, filename, change)
    with pytest.raises(ContentError) as caught:
        load_content(content_copy)
    rendered = str(caught.value) + " ".join(str(i) for i in caught.value.issues)
    assert caught.value.issues, "Verstoß wurde nicht erkannt"
    assert all(i.file and i.path for i in caught.value.issues)  # Datei + Feldpfad
    if f"answers.{MARKER}" not in rendered:  # als Schlüssel steht er im Feldpfad (erlaubt)
        assert MARKER not in rendered, rendered  # als Wert nie


def test_a3_loader_key_names_may_appear_but_values_not(content_copy: Path) -> None:
    """Schlüssel stehen im Pfad (Feldpfad), Werte nie: Gegenprobe zur vorigen Parametrisierung."""
    _edit(content_copy, "rules.yaml", lambda d: d["rules"][0].update(level=MARKER))
    with pytest.raises(ContentError) as caught:
        load_content(content_copy)
    assert MARKER not in str(caught.value)


def test_a3_runtime_invalid_content_is_a_controlled_error(
    seeded_app: FastAPI, content_copy: Path
) -> None:
    """Inhalt wird nach dem Start kaputt: GET /config darf kein 500 mit Traceback liefern."""
    with TestClient(seeded_app, headers=CSRF, raise_server_exceptions=False) as client:
        login(client, "doctor")
        assert client.get(CONFIG).status_code == 200
        (content_copy / "rules.yaml").write_text("rules: [unclosed\n", encoding="utf-8")
        response = client.get(CONFIG)
        assert response.status_code == 503, f"{response.status_code} {response.text[:200]}"
        body = response.json()
        assert body["code"] == "content_unavailable"
        assert "Traceback" not in response.text


def test_a3_env_override_is_respected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv(CONTENT_DIR_ENV, str(empty))
    from waechter.content import get_content

    with pytest.raises(ContentError) as caught:
        get_content()
    assert all(i.message == "file is missing" for i in caught.value.issues)
    assert len(caught.value.issues) == 6  # alle sechs Dateien werden gemeldet
    shutil.rmtree(empty)


def test_a3_idempotency_key_is_scoped_per_patient(seeded_app: FastAPI) -> None:
    """Zwei Patientinnen dürfen dieselbe client_submission_id nutzen (sonst Fremdwirkung)."""
    from datetime import UTC, datetime

    with seeded_app.state.session_factory() as session:
        patients = session.scalars(select(Patient).order_by(Patient.pseudonym)).all()
        assert len(patients) >= 2
        for patient in patients[:2]:
            session.add(
                Response(
                    patient_id=patient.id,
                    client_submission_id="a3-shared-key",
                    channel="web",
                    entered_by="self",
                    recorded_at=datetime(2026, 10, 17, 7, 0, tzinfo=UTC),
                    questionnaire_id="q",
                )
            )
            session.commit()
