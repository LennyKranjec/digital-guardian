"""Ärztin-API: Meldungen abrufen, quittieren (bedingt), Benachrichtigungen, Rauschbremse danach."""

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.persistence.models import AuditEvent
from conftest import CSRF, login, run_parallel
from waechter.models import Alert, AlertAction, Patient

BASE = "/api/v1/waechter"
RESPONSES = f"{BASE}/me/responses"
ALERT_KEYS = {
    "alert_id",
    "patient_id",
    "rule_id",
    "rule_version",
    "level",
    "symptom_key",
    "attribute",
    "headline",
    "status",
    "created_at",
    "notified",
    "explanation",
    "acknowledgement",
}


def client_for(app: FastAPI, username: str) -> TestClient:
    test_client = TestClient(app, headers=CSRF)
    login(test_client, username)
    return test_client


def patient_id(app: FastAPI, pseudonym: str) -> str:
    with app.state.session_factory() as session:
        return str(session.scalars(select(Patient.id).where(Patient.pseudonym == pseudonym)).one())


def alerts_of(app: FastAPI, pseudonym: str, rule_id: str | None = None) -> list[Alert]:
    with app.state.session_factory() as session:
        query = select(Alert).where(Alert.patient_id == patient_id(app, pseudonym))
        if rule_id:
            query = query.where(Alert.rule_id == rule_id)
        return list(session.scalars(query.order_by(Alert.created_at, Alert.id)))


def submit(client: TestClient, answers: list[tuple[str, str, int]]) -> None:
    payload = {
        "client_submission_id": str(uuid.uuid4()),
        "questionnaire_id": "items-v1:FIX-REG",
        "answers": [{"symptom_key": s, "attribute": a, "value": v} for s, a, v in answers],
    }
    assert client.post(RESPONSES, json=payload).status_code == 201


def some_open_alert(app: FastAPI) -> str:
    return next(a.id for a in alerts_of(app, "SYN-0003", "R-SEV-01") if a.status == "open")


# --- Zugriff --------------------------------------------------------------------------------


def test_anonymous_gets_401(seeded_app: FastAPI) -> None:
    anon = TestClient(seeded_app, headers=CSRF)
    pid = patient_id(seeded_app, "SYN-0003")
    assert anon.get(f"{BASE}/patients/{pid}/alerts").status_code == 401
    assert anon.get(f"{BASE}/alerts/x").status_code == 401
    assert anon.post(f"{BASE}/alerts/x/acknowledge", json={"decision": "other"}).status_code == 401
    assert anon.get(f"{BASE}/notifications").status_code == 401


@pytest.mark.parametrize("username", ["patient", "patient2", "user"])
def test_other_roles_get_403(seeded_app: FastAPI, username: str) -> None:
    other = client_for(seeded_app, username)
    pid = patient_id(seeded_app, "SYN-0003")
    alert_id = some_open_alert(seeded_app)
    assert other.get(f"{BASE}/patients/{pid}/alerts").status_code == 403
    assert other.get(f"{BASE}/alerts/{alert_id}").status_code == 403
    assert (
        other.post(f"{BASE}/alerts/{alert_id}/acknowledge", json={"decision": "other"}).status_code
        == 403
    )
    assert other.get(f"{BASE}/notifications").status_code == 403
    assert alerts_of(seeded_app, "SYN-0003", "R-SEV-01")[-1].status == "open"  # nichts verändert


# --- Lesen ----------------------------------------------------------------------------------


def test_list_alerts_contract_shape_newest_first_and_filter(seeded_app: FastAPI) -> None:
    doctor = client_for(seeded_app, "doctor")
    pid = patient_id(seeded_app, "SYN-0003")
    everything = doctor.get(f"{BASE}/patients/{pid}/alerts").json()
    assert len(everything) == len(alerts_of(seeded_app, "SYN-0003"))
    assert all(set(a) == ALERT_KEYS for a in everything)
    stamps = [a["created_at"] for a in everything]
    assert stamps == sorted(stamps, reverse=True)
    assert all(a["patient_id"] == pid and a["acknowledgement"] is None for a in everything)
    assert {a["status"] for a in everything} == {"open"}
    assert (
        doctor.get(f"{BASE}/patients/{pid}/alerts", params={"status": "acknowledged"}).json() == []
    )
    open_only = doctor.get(f"{BASE}/patients/{pid}/alerts", params={"status": "open"}).json()
    assert len(open_only) == len(everything)
    assert (
        doctor.get(f"{BASE}/patients/{pid}/alerts", params={"status": "bogus"}).status_code == 422
    )


def test_alerts_only_for_the_requested_patient(seeded_app: FastAPI) -> None:
    doctor = client_for(seeded_app, "doctor")
    other = doctor.get(f"{BASE}/patients/{patient_id(seeded_app, 'SYN-0002')}/alerts").json()
    assert {a["rule_id"] for a in other} == {"R-DLT-01"}


def test_unknown_patient_and_alert_are_404(seeded_app: FastAPI) -> None:
    doctor = client_for(seeded_app, "doctor")
    assert doctor.get(f"{BASE}/patients/{uuid.uuid4()}/alerts").status_code == 404
    assert doctor.get(f"{BASE}/alerts/{uuid.uuid4()}").status_code == 404
    unknown = doctor.post(f"{BASE}/alerts/{uuid.uuid4()}/acknowledge", json={"decision": "other"})
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "not_found"


def test_alert_detail_has_full_explanation_and_language(seeded_app: FastAPI) -> None:
    doctor = client_for(seeded_app, "doctor")
    trend = next(a for a in alerts_of(seeded_app, "SYN-0003", "R-TRD-01"))
    cs = doctor.get(f"{BASE}/alerts/{trend.id}").json()
    assert set(cs) == ALERT_KEYS
    assert cs["rule_id"] == "R-TRD-01"
    assert cs["rule_version"] == "rules-v1"
    assert cs["level"] == "yellow"
    assert cs["explanation"]["kind"] == "trend"
    assert cs["explanation"]["observed"]["slope_per_day"] == 0.5
    assert cs["explanation"]["rationale"] == "Testovací plíživá změna"
    assert "rationale_i18n" not in cs["explanation"]
    assert cs["headline"].startswith("Nevolnost")
    en = doctor.get(f"{BASE}/alerts/{trend.id}", params={"lang": "en"}).json()
    assert en["explanation"]["rationale"] == "Fixture creeping change"
    assert en["headline"].startswith("Nausea")
    assert doctor.get(f"{BASE}/alerts/{trend.id}", params={"lang": "fr"}).status_code == 422


# --- Quittieren -----------------------------------------------------------------------------


def test_acknowledge_changes_status_and_records_decision(seeded_app: FastAPI) -> None:
    doctor = client_for(seeded_app, "doctor")
    alert_id = some_open_alert(seeded_app)
    response = doctor.post(
        f"{BASE}/alerts/{alert_id}/acknowledge",
        json={"decision": "contact_patient", "note": "Rückruf vereinbart"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == ALERT_KEYS
    assert data["status"] == "acknowledged"
    ack = data["acknowledgement"]
    assert ack["decision"] == "contact_patient"
    assert ack["note"] == "Rückruf vereinbart"
    assert ack["by"] == "doctor"
    assert ack["at"] == "2026-10-17T09:00:00+02:00"
    assert doctor.get(f"{BASE}/alerts/{alert_id}").json()["status"] == "acknowledged"
    listed = doctor.get(
        f"{BASE}/patients/{data['patient_id']}/alerts", params={"status": "acknowledged"}
    ).json()
    assert [a["alert_id"] for a in listed] == [alert_id]
    with seeded_app.state.session_factory() as session:
        stored = session.get(Alert, alert_id)
        assert stored is not None
        assert stored.version == 2  # bedingtes Update hat die Version erhöht


def test_second_acknowledge_is_409_alert_not_open(seeded_app: FastAPI) -> None:
    doctor = client_for(seeded_app, "doctor")
    alert_id = some_open_alert(seeded_app)
    url = f"{BASE}/alerts/{alert_id}/acknowledge"
    assert doctor.post(url, json={"decision": "no_action_needed"}).status_code == 200
    again = doctor.post(url, json={"decision": "other"})
    assert again.status_code == 409
    assert again.json()["code"] == "alert_not_open"
    with seeded_app.state.session_factory() as session:
        decisions = session.scalars(
            select(AlertAction.decision).where(AlertAction.alert_id == alert_id)
        ).all()
    assert decisions == ["no_action_needed"]  # erste Entscheidung bleibt


def test_admin_may_acknowledge(seeded_app: FastAPI) -> None:
    admin = client_for(seeded_app, "admin")
    alert_id = some_open_alert(seeded_app)
    response = admin.post(f"{BASE}/alerts/{alert_id}/acknowledge", json={"decision": "other"})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"decision": "ignore"},
        {"decision": "other", "note": "x" * 501},
        {"decision": "other", "extra": 1},
        {"decision": None},
    ],
)
def test_invalid_acknowledge_body_is_422_and_changes_nothing(
    seeded_app: FastAPI, payload: dict[str, Any]
) -> None:
    doctor = client_for(seeded_app, "doctor")
    alert_id = some_open_alert(seeded_app)
    response = doctor.post(f"{BASE}/alerts/{alert_id}/acknowledge", json=payload)
    assert response.status_code == 422
    assert response.json()["field_errors"]
    with seeded_app.state.session_factory() as session:
        stored = session.get(Alert, alert_id)
        assert stored is not None
        assert (stored.status, stored.version) == ("open", 1)


def test_note_of_exactly_500_characters_is_accepted(seeded_app: FastAPI) -> None:
    doctor = client_for(seeded_app, "doctor")
    alert_id = some_open_alert(seeded_app)
    ok = doctor.post(
        f"{BASE}/alerts/{alert_id}/acknowledge", json={"decision": "other", "note": "x" * 500}
    )
    assert ok.status_code == 200


def test_acknowledge_needs_csrf_header(seeded_app: FastAPI) -> None:
    bare = TestClient(seeded_app)
    doctor = client_for(seeded_app, "doctor")
    bare.cookies.update(doctor.cookies)
    alert_id = some_open_alert(seeded_app)
    response = bare.post(f"{BASE}/alerts/{alert_id}/acknowledge", json={"decision": "other"})
    assert response.status_code == 403
    assert alerts_of(seeded_app, "SYN-0003", "R-SEV-01")[0].status == "open"


def test_acknowledge_is_audited_without_note(seeded_app: FastAPI) -> None:
    doctor = client_for(seeded_app, "doctor")
    alert_id = some_open_alert(seeded_app)
    doctor.post(
        f"{BASE}/alerts/{alert_id}/acknowledge",
        json={"decision": "visit_scheduled", "note": "geheime Notiz"},
    )
    with seeded_app.state.session_factory() as session:
        (event,) = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "acknowledge_alert")
        )
    assert event.target_type == "alert"
    assert event.target_id == alert_id
    assert event.actor_role == "clinician"
    assert event.details_json == {"decision": "visit_scheduled", "level": "red"}
    assert "geheime" not in str(event.details_json)
    assert event.subject_id == patient_id(seeded_app, "SYN-0003")


def test_four_parallel_acknowledgements_yield_exactly_one_success(seeded_app: FastAPI) -> None:
    alert_id = some_open_alert(seeded_app)
    doctors = [client_for(seeded_app, "doctor") for _ in range(4)]
    results = run_parallel(
        lambda i: doctors[i].post(
            f"{BASE}/alerts/{alert_id}/acknowledge", json={"decision": "other", "note": str(i)}
        ),
        4,
    )
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409], [
        (r.status_code, r.text) for r in results
    ]
    assert {r.json()["code"] for r in results if r.status_code == 409} == {"alert_not_open"}
    with seeded_app.state.session_factory() as session:
        actions = session.scalar(
            select(func.count()).select_from(AlertAction).where(AlertAction.alert_id == alert_id)
        )
        audits = session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == alert_id)
        )
        stored = session.get(Alert, alert_id)
    assert (actions, audits) == (1, 1)
    assert stored is not None
    assert (stored.status, stored.version) == ("acknowledged", 2)


# --- Rauschbremse nach Quittierung ----------------------------------------------------------


def test_cooldown_after_acknowledgement_holds_equal_values_but_not_worsening(
    seeded_app: FastAPI,
) -> None:
    patient = client_for(seeded_app, "patient2")  # SYN-0002
    doctor = client_for(seeded_app, "doctor")
    submit(patient, [("nausea", "severity", 3)])
    (first,) = alerts_of(seeded_app, "SYN-0002", "R-SEV-01")
    ack = doctor.post(f"{BASE}/alerts/{first.id}/acknowledge", json={"decision": "contact_patient"})
    assert ack.status_code == 200

    submit(patient, [("nausea", "severity", 3)])  # gleicher Wert im Cooldown ⇒ keine neue Meldung
    assert len(alerts_of(seeded_app, "SYN-0002", "R-SEV-01")) == 1

    submit(patient, [("nausea", "severity", 4)])  # Verschlechterung ⇒ durch (G-02)
    after = alerts_of(seeded_app, "SYN-0002", "R-SEV-01")
    assert sorted(a.status for a in after) == [
        "acknowledged",
        "open",
    ]  # Zeit eingefroren ⇒ ohne Reihenfolge
    open_ids = [
        a["alert_id"]
        for a in doctor.get(
            f"{BASE}/patients/{first.patient_id}/alerts", params={"status": "open"}
        ).json()
        if a["rule_id"] == "R-SEV-01"
    ]
    assert len(open_ids) == 1
    assert open_ids[0] != first.id


# --- Benachrichtigungen ---------------------------------------------------------------------


def test_notifications_for_staff_newest_first(seeded_app: FastAPI) -> None:
    doctor = client_for(seeded_app, "doctor")
    seeded = doctor.get(f"{BASE}/notifications").json()
    assert seeded
    assert all(
        set(n) == {"notification_id", "at", "patient_id", "alert_id", "level", "channel", "text"}
        for n in seeded
    )
    assert {n["level"] for n in seeded} == {"red"}  # gelb ⇒ nur Arbeitsliste
    assert all(n["channel"] == "in_app" and n["text"].startswith("SYN-") for n in seeded)
    stamps = [n["at"] for n in seeded]
    assert stamps == sorted(stamps, reverse=True)

    patient = client_for(seeded_app, "patient2")
    submit(patient, [("fever", "presence", 1)])
    latest = doctor.get(f"{BASE}/notifications").json()
    assert len(latest) == len(seeded) + 1
    fresh = [n for n in latest if n["text"].startswith("SYN-0002")]
    assert len(fresh) == 1
    assert fresh[0]["at"] == "2026-10-17T09:00:00+02:00"
    assert [n["at"] for n in latest] == sorted((n["at"] for n in latest), reverse=True)
    admin = client_for(seeded_app, "admin")
    assert len(admin.get(f"{BASE}/notifications").json()) == len(latest)
