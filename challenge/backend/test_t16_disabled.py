"""T-16: Ohne `triage.yaml` (Fixture-Inhalt) ist die Triage aus, alles andere bleibt gleich."""

import uuid

from fastapi.testclient import TestClient

from conftest import login

BASE = "/api/v1/waechter"


def test_without_a_knowledge_base_sessions_and_cards_are_unavailable_but_responses_work(
    client: TestClient,
) -> None:
    login(client, "patient")
    started = client.post(f"{BASE}/me/sessions", json={"client_session_id": str(uuid.uuid4())})
    assert started.status_code == 409
    assert started.json()["code"] == "triage_unavailable"
    questionnaire = client.get(f"{BASE}/me/questionnaire").json()
    sent = client.post(
        f"{BASE}/me/responses",
        json={
            "client_submission_id": str(uuid.uuid4()),
            "questionnaire_id": questionnaire["questionnaire_id"],
            "answers": [{"symptom_key": "nausea", "attribute": "severity", "value": 1}],
        },
    )
    assert sent.status_code == 201  # Antwort und Regeln unabhängig von der Triage
    login(client, "doctor")
    patients = client.get(f"{BASE}/patients").json()
    patient_id = patients[0]["patient_id"]
    assert client.get(f"{BASE}/patients/{patient_id}/triage").status_code == 404
    assert client.get(f"{BASE}/config/triage").status_code == 404
    overview = client.get(f"{BASE}/patients/{patient_id}/overview").json()
    assert overview["triage_latest"] is None
    config = client.get(f"{BASE}/config").json()
    assert config["triage_version"] is None
