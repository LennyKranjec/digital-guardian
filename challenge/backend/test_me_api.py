"""Patientinnen-API: Fragebogen, Antworten (idempotent), eigene Eingaben, Rechte, Audit."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.persistence.models import AuditEvent
from conftest import CSRF, login
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import get_content
from waechter.models import Answer, Patient, Response
from waechter.services import hooks

QUESTIONNAIRE = "/api/v1/waechter/me/questionnaire"
RESPONSES = "/api/v1/waechter/me/responses"
QID = "items-v1:FIX-REG"


def body(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "client_submission_id": str(uuid.uuid4()),
        "questionnaire_id": QID,
        "answers": [
            {"symptom_key": "nausea", "attribute": "severity", "value": 2},
            {"symptom_key": "fever", "attribute": "presence", "value": 0},
        ],
    }
    result.update(overrides)
    return result


def count_responses(app: FastAPI, submission_id: str) -> int:
    with app.state.session_factory() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(Response)
                .where(Response.client_submission_id == submission_id)
            )
            or 0
        )


def audit_actions(app: FastAPI, action: str) -> list[AuditEvent]:
    with app.state.session_factory() as session:
        return list(session.scalars(select(AuditEvent).where(AuditEvent.action == action)))


# --- Zugriff -------------------------------------------------------------------------------


def test_anonymous_gets_401_everywhere(client: TestClient) -> None:
    assert client.get(QUESTIONNAIRE).status_code == 401
    assert client.get(RESPONSES).status_code == 401
    assert client.post(RESPONSES, json=body()).status_code == 401


@pytest.mark.parametrize("username", ["doctor", "admin", "user"])
def test_staff_and_other_roles_get_403_on_me(client: TestClient, username: str) -> None:
    login(client, username)
    assert client.get(QUESTIONNAIRE).status_code == 403
    assert client.get(RESPONSES).status_code == 403
    sent = client.post(RESPONSES, json=body())
    assert sent.status_code == 403
    assert sent.json()["code"] == "forbidden"


def test_patient_account_without_patient_record_gets_404(
    seeded_app: FastAPI, client: TestClient
) -> None:
    with seeded_app.state.session_factory() as session:
        for patient in session.scalars(select(Patient)):
            patient.user_id = None
        session.commit()
    login(client, "patient")
    assert client.get(QUESTIONNAIRE).status_code == 404


# --- Fragebogen ----------------------------------------------------------------------------


def test_questionnaire_core_then_regimen_profile(client: TestClient) -> None:
    login(client, "patient")
    data = client.get(QUESTIONNAIRE).json()
    assert data["questionnaire_id"] == f"{QID}:none"  # v1.9; QID (alt) bleibt als Antwort-ID gültig
    assert data["items_version"] == "items-v1"
    assert data["regimen_id"] == "FIX-REG"
    assert data["lang"] == "cs"  # Sprache der Patientin SYN-0001
    assert data["recall_period"] == "Za poslední 7 dní"
    assert "Testovací režim" in data["selection_reason"]
    assert [(i["symptom_key"], i["source"]) for i in data["items"]] == [
        ("nausea", "core"),
        ("fever", "regimen"),
    ]
    nausea = data["items"][0]
    assert nausea["label"] == "Nevolnost"
    question = nausea["questions"][0]
    assert question["attribute"] == "severity"
    assert [o["value"] for o in question["options"]] == [0, 1, 2, 3, 4]
    fever = data["items"][1]["questions"][0]
    assert [o["value"] for o in fever["options"]] == [0, 1]


def test_questionnaire_language_default_and_override(client: TestClient) -> None:
    login(client, "patient2")  # SYN-0002 spricht Englisch
    assert client.get(QUESTIONNAIRE).json()["lang"] == "en"
    cs = client.get(QUESTIONNAIRE, params={"lang": "cs"}).json()
    assert cs["lang"] == "cs"
    assert cs["items"][0]["label"] == "Nevolnost"
    de = client.get(QUESTIONNAIRE, params={"lang": "de"}).json()  # de fehlt in den Inhalten ⇒ en
    assert de["lang"] == "de"
    assert de["items"][0]["label"] == "Nausea"
    assert de["selection_reason"].startswith("Fragen passend")
    assert client.get(QUESTIONNAIRE, params={"lang": "fr"}).status_code == 422


def test_questionnaire_without_content_is_503(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    login(client, "patient")
    monkeypatch.setenv(CONTENT_DIR_ENV, str(tmp_path / "missing"))
    assert client.get(QUESTIONNAIRE).status_code == 503


# --- Antworten speichern -------------------------------------------------------------------


def test_submit_returns_neutral_receipt_in_prague_time(
    seeded_app: FastAPI, client: TestClient
) -> None:
    login(client, "patient")
    payload = body()
    response = client.post(RESPONSES, json=payload)
    assert response.status_code == 201, response.text
    receipt = response.json()
    assert set(receipt) == {"response_id", "recorded_at", "answered", "skipped", "message_key"}
    assert receipt["recorded_at"] == "2026-10-17T09:00:00+02:00"  # FROZEN_NOW 07:00Z
    assert (receipt["answered"], receipt["skipped"]) == (2, 0)
    assert receipt["message_key"] == "patient.response.saved"
    assert count_responses(seeded_app, payload["client_submission_id"]) == 1


def test_all_null_answers_are_allowed(client: TestClient) -> None:
    login(client, "patient")
    payload = body(
        answers=[
            {"symptom_key": "nausea", "attribute": "severity", "value": None},
            {"symptom_key": "fever", "attribute": "presence", "value": None},
        ]
    )
    response = client.post(RESPONSES, json=payload)
    assert response.status_code == 201
    assert (response.json()["answered"], response.json()["skipped"]) == (0, 2)


def test_skipped_values_are_stored_as_missing(seeded_app: FastAPI, client: TestClient) -> None:
    login(client, "patient")
    payload = body(
        answers=[
            {"symptom_key": "nausea", "attribute": "severity", "value": None},
            {"symptom_key": "fever", "attribute": "presence", "value": 1},
        ]
    )
    receipt = client.post(RESPONSES, json=payload).json()
    with seeded_app.state.session_factory() as session:
        rows = session.scalars(select(Answer).where(Answer.response_id == receipt["response_id"]))
        stored = {(a.symptom_key, a.value) for a in rows}
    assert stored == {("nausea", None), ("fever", 1)}


def test_same_submission_is_idempotent(seeded_app: FastAPI, client: TestClient) -> None:
    login(client, "patient")
    payload = body()
    first = client.post(RESPONSES, json=payload)
    again = client.post(RESPONSES, json=payload)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert count_responses(seeded_app, payload["client_submission_id"]) == 1
    assert len(audit_actions(seeded_app, "submit_response")) == 1  # Replay erzeugt kein Audit


def test_same_id_with_other_body_is_409(client: TestClient) -> None:
    login(client, "patient")
    payload = body()
    assert client.post(RESPONSES, json=payload).status_code == 201
    conflict = client.post(RESPONSES, json={**payload, "channel": "phone"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"
    other_answers = {**payload, "answers": payload["answers"][:1]}
    assert client.post(RESPONSES, json=other_answers).status_code == 409


def test_submission_id_is_scoped_per_patient_and_never_leaks_a_receipt(
    seeded_app: FastAPI, client: TestClient
) -> None:
    """A3 F-02: dieselbe ID bei zwei Patientinnen ⇒ zwei getrennte Datensätze, kein Fremdbeleg."""
    login(client, "patient2")
    payload = body()
    theirs = client.post(RESPONSES, json=payload)
    assert theirs.status_code == 201
    client.post("/api/v1/auth/logout")
    login(client, "patient")
    mine = client.post(RESPONSES, json=payload)
    assert mine.status_code == 201  # eigener Datensatz, keine Kollision
    assert mine.json()["response_id"] != theirs.json()["response_id"]
    assert client.post(RESPONSES, json=payload).json() == mine.json()  # Replay: eigener Beleg
    assert count_responses(seeded_app, payload["client_submission_id"]) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("questionnaire_id", "items-v1:OTHER"),
        ("answers", [{"symptom_key": "nausea", "attribute": "interference", "value": 1}]),
        ("answers", [{"symptom_key": "headache", "attribute": "severity", "value": 1}]),
        (
            "answers",
            [
                {"symptom_key": "nausea", "attribute": "severity", "value": 1},
                {"symptom_key": "nausea", "attribute": "severity", "value": 2},
            ],
        ),
        ("answers", [{"symptom_key": "fever", "attribute": "presence", "value": 2}]),
        ("answers", [{"symptom_key": "nausea", "attribute": "severity", "value": 5}]),
        ("answers", [{"symptom_key": "nausea", "attribute": "severity", "value": -1}]),
        ("answers", [{"symptom_key": "nausea", "attribute": "severity", "value": "2"}]),
        ("answers", []),
        ("client_submission_id", "not-a-uuid"),
        ("channel", "fax"),
        ("entered_by", "robot"),
    ],
)
def test_invalid_submissions_are_422_and_not_stored(
    seeded_app: FastAPI, client: TestClient, field: str, value: Any
) -> None:
    login(client, "patient")
    payload = body(**{field: value})
    response = client.post(RESPONSES, json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["field_errors"]
    if field != "client_submission_id":
        assert count_responses(seeded_app, payload["client_submission_id"]) == 0
    assert not audit_actions(seeded_app, "submit_response")


def test_validation_errors_name_fields_not_values(client: TestClient) -> None:
    login(client, "patient")
    answers = [{"symptom_key": "fever", "attribute": "presence", "value": 2}]
    response = client.post(RESPONSES, json=body(answers=answers))
    assert response.json()["code"] == "validation_failed"
    (error,) = response.json()["field_errors"]
    assert error["field"] == "answers.0.value"
    assert error["code"] == "out_of_range"


def test_unknown_field_is_rejected(client: TestClient) -> None:
    login(client, "patient")
    assert client.post(RESPONSES, json=body(level="red")).status_code == 422


def test_submit_requires_csrf_header(seeded_app: FastAPI) -> None:
    with TestClient(seeded_app) as bare:  # ohne X-Requested-With
        logged_in = bare.post(
            "/api/v1/auth/login",
            json={"username": "patient", "password": "demo-passwort-2026"},
            headers=CSRF,
        )
        assert logged_in.status_code == 200
        assert bare.post(RESPONSES, json=body()).status_code in {400, 403}


def test_audit_event_has_counts_but_no_values(seeded_app: FastAPI, client: TestClient) -> None:
    login(client, "patient")
    receipt = client.post(RESPONSES, json=body()).json()
    (event,) = audit_actions(seeded_app, "submit_response")
    assert event.target_id == receipt["response_id"]
    assert event.actor_role == "patient"
    assert event.details_json == {"answered": 2, "skipped": 0}
    assert event.subject_id is not None


def test_hook_runs_once_for_new_responses_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(hooks, "on_response_saved", lambda _session, r: calls.append(r.id))
    login(client, "patient")
    payload = body()
    client.post(RESPONSES, json=payload)
    client.post(RESPONSES, json=payload)
    assert len(calls) == 1


# --- Eigene Eingaben -----------------------------------------------------------------------


def test_list_own_responses_only_own_and_newest_first(client: TestClient) -> None:
    content = get_content()
    assert content is not None
    login(client, "patient2")
    mine = client.post(RESPONSES, json=body()).json()
    client.post("/api/v1/auth/logout")
    login(client, "patient")
    seeded = client.get(RESPONSES).json()
    planned = next(p for p in content.scenario["patients"] if p["pseudonym"] == "SYN-0001")
    assert len(seeded) == len(planned["responses"])
    assert mine["response_id"] not in {r["response_id"] for r in seeded}
    assert set(seeded[0]) == {"response_id", "recorded_at", "channel", "entered_by", "answers"}
    stamps = [r["recorded_at"] for r in seeded]
    assert stamps == sorted(stamps, reverse=True)
    assert all(s.endswith("+02:00") for s in stamps)
    assert any(a["value"] is None for r in seeded for a in r["answers"])  # Lücke bleibt Lücke
    client.post("/api/v1/auth/logout")
    login(client, "patient2")
    own = client.get(RESPONSES).json()
    assert mine["response_id"] in {r["response_id"] for r in own}
    assert not {r["response_id"] for r in own} & {r["response_id"] for r in seeded}
