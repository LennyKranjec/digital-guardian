"""Plugin, Migration, Seed und GET /config. Keine Tagesdatum- und keine absoluten Seed-Zahlen."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.db import create_db_engine
from app.persistence.migrate import downgrade_to_base, upgrade_to_head
from app.registry import Registry
from app.services import seed
from conftest import FROZEN_NOW, login, make_settings, migrate
from waechter.content import load_content
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
from waechter.timeutil import iso_prague, to_prague

CONFIG = "/api/v1/waechter/config"


def _count(session: Session, model: type[WaechterBase]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _counts(session: Session) -> dict[str, int]:
    models = (Patient, Therapy, Visit, Response, Answer, ConfigVersion, Alert, Notification)
    return {m.__name__: _count(session, m) for m in models}


def test_migration_up_and_down_on_empty_db(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    registry = migrate(settings)
    engine = create_db_engine(settings.resolved_database_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {t.name for t in WaechterBase.metadata.sorted_tables} <= tables
        assert all(t.name.startswith("wa_") for t in WaechterBase.metadata.sorted_tables)
        upgrade_to_head(engine, registry)  # zweimal ist unschädlich
        downgrade_to_base(engine, registry)
        assert not {n for n in inspect(engine).get_table_names() if n.startswith("wa_")}
    finally:
        engine.dispose()


def test_plugin_registers_roles_accounts_and_resolver(tmp_path: Path) -> None:
    registry = migrate(make_settings(tmp_path))
    assert {"patient", "clinician"} <= set(registry.roles)
    accounts = {a.username: a.role for a in registry.demo_accounts}
    assert accounts == {
        "patient": "patient",
        "patient2": "patient",
        "patient6": "patient",
        "doctor": "clinician",
    }
    assert registry.subject_resolver is not None
    assert isinstance(registry, Registry)


def test_seed_is_idempotent(seeded_app: FastAPI) -> None:
    with seeded_app.state.session_factory() as session:
        first = _counts(session)
        seed.provision(
            session, seeded_app.state.settings, seeded_app.state.registry, seeded_app.state.clock
        )
        seed.provision(
            session, seeded_app.state.settings, seeded_app.state.registry, seeded_app.state.clock
        )
        assert _counts(session) == first
        assert first["Patient"] >= 1
        assert first["Patient"] == len(load_content_patients())
        assert first["Alert"] >= 1  # Meldungen entstehen beim Seed über die Regel-Engine


def load_content_patients() -> list[str]:
    from waechter.content import get_content

    content = get_content()
    assert content is not None
    return [p["pseudonym"] for p in content.scenario["patients"]]


def test_seed_times_are_anchor_plus_offset_in_prague_local_time(seeded_app: FastAPI) -> None:
    from waechter.content import get_content

    content = get_content()
    assert content is not None
    anchor = datetime.fromisoformat(content.scenario["anchor"])
    assert anchor.utcoffset() == timedelta(hours=2)
    spec = next(p for p in content.scenario["patients"] if p["pseudonym"] == "SYN-0001")
    with seeded_app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0001")).one()
        responses = session.scalars(
            select(Response).where(Response.patient_id == patient.id).order_by(Response.recorded_at)
        ).all()
        assert len(responses) == len(spec["responses"])
        for stored, planned in zip(
            responses, sorted(spec["responses"], key=lambda r: r["day_offset"]), strict=True
        ):
            local = to_prague(stored.recorded_at)
            assert (local.date() - to_prague(anchor).date()).days == planned["day_offset"]
            assert local.hour == planned.get("hour", to_prague(anchor).hour)
            assert stored.recorded_at.utcoffset() == timedelta(0)  # gespeichert als UTC-Instant
        therapy = session.scalars(select(Therapy).where(Therapy.patient_id == patient.id)).one()
        cycle_local = to_prague(therapy.cycle_start)
        assert (cycle_local.date() - to_prague(anchor).date()).days == spec["cycle_start_offset"]
        assert cycle_local.hour == to_prague(anchor).hour
        assert all(r.synthetic for r in responses)
        assert patient.synthetic is True


def test_skipped_answers_are_stored_as_missing(seeded_app: FastAPI) -> None:
    with seeded_app.state.session_factory() as session:
        missing = session.scalars(select(Answer).where(Answer.value.is_(None))).all()
        assert missing  # Fixture enthält eine übersprungene Antwort
        assert all(a.attribute == "presence" for a in missing)


def test_demo_patient_account_resolves_to_syn_0001(seeded_app: FastAPI) -> None:
    with TestClient(seeded_app, headers={"X-Requested-With": "fetch"}) as client:
        mine = client.post(
            "/api/v1/auth/login", json={"username": "patient", "password": seed.DEMO_PASSWORD}
        ).json()
        assert mine["role"] == "patient"
        assert mine["subject_id"] is not None
        client.post("/api/v1/auth/logout")
        doc = client.post(
            "/api/v1/auth/login", json={"username": "doctor", "password": seed.DEMO_PASSWORD}
        ).json()
        assert doc["role"] == "clinician"
        assert doc["subject_id"] is None
    with seeded_app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0001")).one()
        assert patient.id == mine["subject_id"]


def test_seed_without_content_dir_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAECHTER_CONTENT_DIR", str(tmp_path / "missing"))
    settings = make_settings(tmp_path)
    registry = migrate(settings)
    engine = create_db_engine(settings.resolved_database_url)
    try:
        with Session(engine) as session:
            seed.provision(session, settings, registry, FrozenClock(FROZEN_NOW))
            assert _count(session, Patient) == 0
    finally:
        engine.dispose()


def test_plugin_loads_without_content_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAECHTER_CONTENT_DIR", str(tmp_path / "missing"))
    registry = migrate(make_settings(tmp_path))
    assert "clinician" in registry.roles


def test_seed_writes_active_config_versions(seeded_app: FastAPI) -> None:
    with seeded_app.state.session_factory() as session:
        rows = session.scalars(select(ConfigVersion)).all()
        assert {(r.kind, r.active) for r in rows} == {("rules", True), ("report", True)}
        rules = next(r for r in rows if r.kind == "rules")
        assert rules.version == load_content_version("rules")


def load_content_version(kind: str) -> str:
    from waechter.content import get_content

    content = get_content()
    assert content is not None
    return str(getattr(content, kind)["version"])


def test_config_for_clinician_is_200_and_complete(client: TestClient) -> None:
    login(client, "doctor")
    response = client.get(CONFIG)
    assert response.status_code == 200, response.text
    body = response.json()
    core = {"items", "regimens", "ctcae", "rules", "report"}
    assert core <= set(body) <= {*core, "advice", "medications", "triage_version"}  # v2.5 Zusätze
    assert body["rules"]["version"] == load_content_version("rules")
    assert body["items"]["items"][0]["symptom_key"] == "nausea"


def test_config_for_admin_is_200(client: TestClient) -> None:
    login(client, "admin")
    assert client.get(CONFIG).status_code == 200


def test_config_for_patient_is_403(client: TestClient) -> None:
    login(client, "patient")
    response = client.get(CONFIG)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_config_for_plain_user_is_403(client: TestClient) -> None:
    login(client, "user")
    assert client.get(CONFIG).status_code == 403


def test_config_anonymous_is_401(client: TestClient) -> None:
    response = client.get(CONFIG)
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_config_prefers_the_active_stored_version(seeded_app: FastAPI, client: TestClient) -> None:
    with seeded_app.state.session_factory() as session:
        row = session.scalars(select(ConfigVersion).where(ConfigVersion.kind == "rules")).one()
        row.body_json = {**row.body_json, "version": "rules-v7"}
        session.commit()
    login(client, "doctor")
    assert client.get(CONFIG).json()["rules"]["version"] == "rules-v7"


def test_config_without_content_is_503(
    seeded_app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WAECHTER_CONTENT_DIR", str(tmp_path / "missing"))
    with TestClient(seeded_app, headers={"X-Requested-With": "fetch"}) as client:
        login(client, "doctor")
        response = client.get(CONFIG)
    assert response.status_code == 503
    assert response.json()["code"] == "content_unavailable"


def test_loader_matches_fixture_directory(fixture_content: Path) -> None:
    assert load_content(fixture_content).rules["version"] == "rules-v1"


def test_seed_keeps_local_time_across_the_october_switch(seeded_app: FastAPI) -> None:
    """Termin am 01.11.2026 (Tag +15) liegt nach der Zeitumstellung vom 25.10.: Ortszeit bleibt."""
    with seeded_app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0001")).one()
        planned = session.scalars(
            select(Visit).where(Visit.patient_id == patient.id, Visit.kind == "planned")
        ).one()
        assert iso_prague(planned.at) == "2026-11-01T09:00:00+01:00"
        assert planned.at == datetime(2026, 11, 1, 8, 0, tzinfo=planned.at.tzinfo)  # 08:00 UTC
