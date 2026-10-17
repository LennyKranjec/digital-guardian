"""T-20b: Triage-Profile für C61/C64 (ENZALUTAMIDE, ABIRATERONE, PAZOPANIB, NIVOLUMAB).

Echte Inhalte (`challenge/content`), alles synthetisch und Platzhalter. Geprüft werden Struktur,
Sicherheitsregeln (kritische Symptome als Gate), Messwerte der Kompilate und die Seed-Entscheidungen
der Demo-Patientinnen SYN-0006 (Prostata, Enzalutamid) und SYN-0007 (Niere, Pazopanib).
"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import CSRF, login
from triage_support import real_inputs, real_kb
from waechter.constants import CONTENT_DIR_ENV
from waechter.models import Alert, Notification, Patient, Response, TriageDecision

REAL = Path(__file__).resolve().parents[1] / "content"
NEW = ("ENZALUTAMIDE", "ABIRATERONE", "PAZOPANIB", "NIVOLUMAB")
BASE = "/api/v1/waechter"


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


def regimen_keys() -> dict[str, list[str]]:
    _, _, regimens = real_inputs()
    return {leaf: list(keys) for leaf, keys in regimens.items()}


@pytest.mark.parametrize("leaf", NEW)
def test_each_new_regimen_has_exactly_one_leaf_profile_with_its_lineage(leaf: str) -> None:
    kb = real_kb()
    assert kb.regimen_profile[leaf] == leaf
    profile = kb.profile(leaf)
    assert profile.regimen_ids == (leaf,)
    assert profile.status == "placeholder"
    expected = {
        "ENZALUTAMIDE": ("base", "hormonal", "ENZALUTAMIDE"),
        "ABIRATERONE": ("base", "hormonal", "ABIRATERONE"),
        "PAZOPANIB": ("base", "tki", "PAZOPANIB"),
        "NIVOLUMAB": ("base", "ici", "NIVOLUMAB"),
    }[leaf]
    assert profile.lineage == expected


@pytest.mark.parametrize("leaf", NEW)
def test_profile_symptoms_stay_inside_the_regimen_and_critical_ones_are_gates(leaf: str) -> None:
    profile = real_kb().profile(leaf)
    keys = regimen_keys()[leaf]
    assert set(profile.symptoms) <= set(keys)
    always_asked = {*profile.fixed_items, *profile.safety_items}
    critical = {i["symptom_key"] for i in real_inputs()[0]["items"] if i["critical"]}
    # jedes kritische Symptom, das das Regime führt, wird immer gefragt (T-14F, A3 F-03)
    assert {s for s in keys if s in critical and s in profile.symptoms} <= always_asked
    assert {s for s in profile.symptoms if s in critical} <= always_asked
    assert "fever" in profile.safety_items


@pytest.mark.parametrize(
    ("leaf", "gates"),
    [
        ("ENZALUTAMIDE", {"vomiting"}),
        ("PAZOPANIB", {"vomiting", "shortness_of_breath"}),
        ("NIVOLUMAB", {"vomiting", "shortness_of_breath"}),
        ("ABIRATERONE", set()),
    ],
)
def test_regimen_specific_critical_symptoms_are_always_asked(leaf: str, gates: set[str]) -> None:
    profile = real_kb().profile(leaf)
    assert gates <= {*profile.fixed_items, *profile.safety_items}


def test_question_counts_and_grids_of_the_new_profiles() -> None:
    kb = real_kb()
    counts = {leaf: kb.profile(leaf).full_question_count for leaf in NEW}
    assert counts == {"ENZALUTAMIDE": 14, "ABIRATERONE": 10, "PAZOPANIB": 22, "NIVOLUMAB": 20}
    assert all(kb.profile(leaf).max_questions == 12 for leaf in NEW)  # Fragenlimit je Sitzung


def test_older_profiles_are_unchanged_by_the_new_classes() -> None:
    kb = real_kb()
    assert {leaf: kb.profile(leaf).full_question_count for leaf in kb.regimen_profile} == {
        "FOLFOX": 17,
        "CAPECITABINE": 17,
        "DOCETAXEL": 15,
        "PEMBROLIZUMAB": 14,
        "ENZALUTAMIDE": 14,
        "ABIRATERONE": 10,
        "PAZOPANIB": 22,
        "NIVOLUMAB": 20,
    }


@pytest.mark.parametrize("leaf", NEW)
def test_new_class_rules_cite_a_declared_assumption(leaf: str) -> None:
    kb = real_kb()
    declared = {a["id"] for a in real_inputs()[0]["assumptions"]}
    profile = kb.profile(leaf)
    for rule in (*profile.red_rules, *profile.yellow_rules, *profile.floors):
        assert rule.assumption in declared, rule.id
    assert {"A-TRI-13", "A-TRI-14", "A-TRI-15"} <= declared


# --- Seed: SYN-0006 (Enzalutamid), SYN-0007 (Pazopanib) ------------------------------------------


def test_seeded_demo_patients_get_a_decision_per_response_with_their_profile(
    seeded_app: FastAPI,
) -> None:
    with seeded_app.state.session_factory() as session:
        for pseudonym, profile_id in (("SYN-0006", "ENZALUTAMIDE"), ("SYN-0007", "PAZOPANIB")):
            patient = session.scalars(select(Patient).where(Patient.pseudonym == pseudonym)).one()
            decisions = session.scalars(
                select(TriageDecision).where(TriageDecision.patient_id == patient.id)
            ).all()
            assert decisions
            assert {d.profile_id for d in decisions} == {profile_id}


# --- Reihenfolge der Sofortbenachrichtigungen bei gleichem Zeitpunkt ---------------------------


def test_notifications_with_the_same_instant_are_ordered_by_text_not_by_random_id(
    seeded_app: FastAPI,
) -> None:
    at = datetime(2026, 10, 17, 12, 0, tzinfo=UTC) + timedelta(days=1)
    with seeded_app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0002")).one()
        alert = session.scalars(select(Alert)).first()
        assert alert is not None
        for name, ident in (
            ("SYN-ZZ", "00000000-0000-4000-8000-000000000001"),
            ("SYN-AA", "ffffffff-ffff-4fff-8fff-ffffffffffff"),
        ):
            session.add(
                Notification(
                    id=ident,
                    patient_id=patient.id,
                    alert_id=alert.id,
                    level="red",
                    channel="in_app",
                    text=f"{name}: Test",
                    at=at,
                    synthetic=True,
                )
            )
        session.commit()
    doctor = TestClient(seeded_app, headers=CSRF)
    login(doctor, "doctor")
    listed = doctor.get(f"{BASE}/notifications").json()
    tied = [n["text"] for n in listed if n["text"].endswith(": Test")]
    assert tied == ["SYN-AA: Test", "SYN-ZZ: Test"]  # id-Reihenfolge wäre umgekehrt


# --- Demo-Konto patient6 = SYN-0006 --------------------------------------------------------------


def patient_client(app: FastAPI, username: str) -> TestClient:
    client = TestClient(app, headers=CSRF)
    login(client, username)
    return client


def test_demo_account_patient6_is_registered_and_linked_to_syn_0006(seeded_app: FastAPI) -> None:
    accounts = {a.username: a.role for a in seeded_app.state.registry.demo_accounts}
    assert accounts["patient6"] == "patient"
    with seeded_app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0006")).one()
        assert patient.user_id is not None
        others = session.scalars(select(Patient).where(Patient.pseudonym != "SYN-0006")).all()
        assert patient.user_id not in {
            p.user_id for p in others
        }  # Konto gehört nur dieser Patientin


def test_patient6_gets_the_enzalutamide_questionnaire_and_only_own_responses(
    seeded_app: FastAPI,
) -> None:
    client = patient_client(seeded_app, "patient6")
    questionnaire = client.get(f"{BASE}/me/questionnaire").json()
    assert ":ENZALUTAMIDE:" in questionnaire["questionnaire_id"]
    assert ":PROSTATE" in questionnaire["questionnaire_id"]
    keys = {item["symptom_key"] for item in questionnaire["items"]}
    assert "fatigue" in keys
    mine = client.get(f"{BASE}/me/responses").json()
    assert mine
    with seeded_app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0006")).one()
        own = {
            r.id for r in session.scalars(select(Response).where(Response.patient_id == patient.id))
        }
    assert {r["response_id"] for r in mine} <= own


def test_patient6_starts_a_session_with_the_enzalutamide_profile_and_may_not_use_staff_routes(
    seeded_app: FastAPI,
) -> None:
    client = patient_client(seeded_app, "patient6")
    started = client.post(f"{BASE}/me/sessions", json={"client_session_id": str(uuid.uuid4())})
    assert started.status_code == 201, started.text
    assert started.json()["next"] is not None
    with seeded_app.state.session_factory() as session:
        other = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0001")).one().id
    assert client.get(f"{BASE}/patients").status_code == 403
    assert client.get(f"{BASE}/patients/{other}/alerts").status_code == 403
