"""T-34: Einschreibung einer neuen synthetischen Patientin mit Therapie (POST /patients)."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.persistence.models import AuditEvent
from conftest import CSRF
from test_a3_t04a import MutableClock
from test_a3_t13 import ANCHOR, BASE, api, client_for, real_template  # noqa: F401  (Fixtures)
from waechter.models import Patient, Therapy

TODAY = ANCHOR.date()


def body(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "diagnosis_code": "C50.9",
        "regimen_id": "FOLFOX",
        "cycle_start": TODAY.isoformat(),
        "language": "cs",
    }
    data.update(overrides)
    return data


@pytest.fixture
def doctor(api: tuple[FastAPI, MutableClock]) -> Iterator[TestClient]:  # noqa: F811
    client = client_for(api[0], "doctor")
    yield client
    client.__exit__(None, None, None)


def _max_seed_number(app: FastAPI) -> int:
    with app.state.session_factory() as session:
        names = session.scalars(select(Patient.pseudonym)).all()
    return max(int(n.removeprefix("SYN-")) for n in names)


def test_enroll_creates_synthetic_patient_with_sequential_pseudonym(
    api: tuple[FastAPI, MutableClock],  # noqa: F811
    doctor: TestClient,
) -> None:
    app = api[0]
    start = _max_seed_number(app)
    first = doctor.post(f"{BASE}/patients", json=body())
    second = doctor.post(f"{BASE}/patients", json=body(diagnosis_code=None, language="en"))
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["pseudonym"] == f"SYN-{start + 1:04d}"
    assert second.json()["pseudonym"] == f"SYN-{start + 2:04d}"
    with app.state.session_factory() as session:
        patient = session.get(Patient, first.json()["patient_id"])
        assert patient is not None
        assert patient.synthetic is True
        assert patient.user_id is None  # kein Konto
        assert patient.diagnosis_code == "C50.9"
        therapy = session.scalar(select(Therapy).where(Therapy.patient_id == patient.id))
        assert therapy is not None
        assert therapy.regimen_id == "FOLFOX"
        assert therapy.synthetic
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "enroll_patient", AuditEvent.target_id == patient.id
            )
        )
        assert audit is not None
        # keine personenbezogenen Inhalte: nur Regime und Diagnosegruppe
        assert audit.details_json == {"regimen_id": "FOLFOX", "diagnosis_group": "BREAST"}


def test_enrolled_patient_appears_grey_in_worklist(doctor: TestClient) -> None:
    # bestehende Ampellogik: ohne Antworten grau, sobald die Frist seit Zyklusstart abgelaufen ist
    started = (TODAY - timedelta(days=14)).isoformat()
    created = doctor.post(f"{BASE}/patients", json=body(cycle_start=started)).json()
    rows = doctor.get(f"{BASE}/patients").json()
    row = next(r for r in rows if r["patient_id"] == created["patient_id"])
    assert row["pseudonym"] == created["pseudonym"]
    assert row["regimen_id"] == "FOLFOX"
    assert row["last_response_at"] is None
    assert row["traffic_light"] == "grey"
    overview = doctor.get(f"{BASE}/patients/{created['patient_id']}/overview")
    assert overview.status_code == 200, overview.text


def test_roles(api: tuple[FastAPI, MutableClock]) -> None:  # noqa: F811
    app = api[0]
    with TestClient(app, headers=CSRF) as anonymous:
        assert anonymous.post(f"{BASE}/patients", json=body()).status_code == 401
    patient = client_for(app, "patient")
    try:
        assert patient.post(f"{BASE}/patients", json=body()).status_code == 403
    finally:
        patient.__exit__(None, None, None)
    admin = client_for(app, "admin")
    try:
        assert admin.post(f"{BASE}/patients", json=body()).status_code == 201
    finally:
        admin.__exit__(None, None, None)


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"regimen_id": "NOPE"}, "regimen_id"),
        ({"cycle_start": "2026-13-45"}, "cycle_start"),
        ({"cycle_start": (TODAY + timedelta(days=31)).isoformat()}, "cycle_start"),
        ({"diagnosis_code": "xx1"}, "diagnosis_code"),
        ({"diagnosis_code": "Z99"}, "diagnosis_code"),
        ({"language": "fr"}, "language"),
    ],
)
def test_validation_errors(doctor: TestClient, overrides: dict[str, Any], field: str) -> None:
    response = doctor.post(f"{BASE}/patients", json=body(**overrides))
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["code"] == "validation_failed"
    assert field in [e["field"] for e in payload["field_errors"]]


def test_cycle_start_30_days_ahead_is_allowed(doctor: TestClient) -> None:
    ahead = (TODAY + timedelta(days=30)).isoformat()
    assert doctor.post(f"{BASE}/patients", json=body(cycle_start=ahead)).status_code == 201


def test_idempotent_client_request_id(
    api: tuple[FastAPI, MutableClock],  # noqa: F811
    doctor: TestClient,
) -> None:
    first = doctor.post(f"{BASE}/patients", json=body(client_request_id="req-1"))
    again = doctor.post(f"{BASE}/patients", json=body(client_request_id="req-1"))
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json() == first.json()
    with api[0].state.session_factory() as session:
        count = len(
            session.scalars(select(Patient).where(Patient.enrollment_request_id == "req-1")).all()
        )
    assert count == 1
