"""T-25 (b): `tracked_symptoms` der Übersicht = CTCAE-Subraum der Aufnahmevorlage (eine Quelle)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_fhir import BASE, pid, staff
from waechter.models import Patient


def overview(client: TestClient, patient_id: str, lang: str) -> dict[str, object]:
    response = client.get(f"{BASE}/patients/{patient_id}/overview?lang={lang}")
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def template_terms(client: TestClient, patient_id: str, lang: str) -> list[dict[str, str]]:
    response = client.get(f"{BASE}/patients/{patient_id}/assessment-template?lang={lang}")
    assert response.status_code == 200, response.text
    return [
        {"ctcae_term_id": t["ctcae_term_id"], "term_en": t["term_en"], "label": t["label"]}
        for t in response.json()["terms"]
    ]


def test_tracked_symptoms_equal_the_assessment_template_terms(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    patient = pid(seeded_app, "SYN-0001")
    for lang in ("cs", "en", "de"):
        tracked = overview(doctor, patient, lang)["tracked_symptoms"]
        assert tracked == template_terms(doctor, patient, lang), lang
        assert tracked, lang  # Fixture-Regime hat Symptome


def test_patient_without_therapy_has_no_tracked_symptoms(seeded_app: FastAPI) -> None:
    with seeded_app.state.session_factory() as session:
        session.add(
            Patient(
                pseudonym="T25-NOTH",
                display_name="Ohne Therapie",
                birth_year=1970,
                sex="female",
                language="cs",
                synthetic=True,
            )
        )
        session.commit()
    doctor = staff(seeded_app)
    assert overview(doctor, pid(seeded_app, "T25-NOTH"), "cs")["tracked_symptoms"] == []


def test_overview_is_still_staff_only(seeded_app: FastAPI) -> None:
    patient = pid(seeded_app, "SYN-0001")
    other = staff(seeded_app, "patient")
    assert other.get(f"{BASE}/patients/{patient}/overview").status_code == 403
