"""Arztaufnahme im CTCAE-Subraum: Vorlage, idempotentes Speichern, Verknüpfung, Verlauf, Belege."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.persistence.models import AuditEvent
from conftest import CHALLENGE_DIR, CSRF, login, make_settings, migrate, run_parallel
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import get_content
from waechter.models import Alert, Assessment, AssessmentItem, Patient

BASE = "/api/v1/waechter"
NAUSEA = "CTCAE-FIX_NAUSEA"
FEVER = "CTCAE-FIX_FEVER"
OTHER = "CTCAE-FIX_OTHER"
REAL_CONTENT = CHALLENGE_DIR / "content"


def staff(app: FastAPI, username: str = "doctor") -> TestClient:
    client = TestClient(app, headers=CSRF)
    login(client, username)
    return client


def pid(app: FastAPI, pseudonym: str) -> str:
    with app.state.session_factory() as session:
        return str(session.scalars(select(Patient.id).where(Patient.pseudonym == pseudonym)).one())


def body(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "client_submission_id": str(uuid.uuid4()),
        "items": [
            {"ctcae_term_id": NAUSEA, "grade": 2, "attribution": "probable", "note": "Kontrolle"},
            {"ctcae_term_id": FEVER, "grade": 0},
        ],
    }
    result.update(overrides)
    return result


def count_assessments(app: FastAPI, csid: str) -> int:
    with app.state.session_factory() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(Assessment)
                .where(Assessment.client_submission_id == csid)
            )
            or 0
        )


def audits(app: FastAPI, action: str) -> list[AuditEvent]:
    with app.state.session_factory() as session:
        return list(session.scalars(select(AuditEvent).where(AuditEvent.action == action)))


# --- Zugriff --------------------------------------------------------------------------------


def test_anonymous_gets_401(seeded_app: FastAPI) -> None:
    anon = TestClient(seeded_app, headers=CSRF)
    p = pid(seeded_app, "SYN-0001")
    assert anon.get(f"{BASE}/patients/{p}/assessment-template").status_code == 401
    assert anon.get(f"{BASE}/patients/{p}/assessments").status_code == 401
    assert anon.post(f"{BASE}/patients/{p}/assessments", json=body()).status_code == 401


@pytest.mark.parametrize("username", ["patient", "patient2", "user"])
def test_patients_and_other_roles_get_403(seeded_app: FastAPI, username: str) -> None:
    other = staff(seeded_app, username)
    p = pid(seeded_app, "SYN-0001")
    payload = body()
    assert other.get(f"{BASE}/patients/{p}/assessment-template").status_code == 403
    assert other.get(f"{BASE}/patients/{p}/assessments").status_code == 403
    assert other.post(f"{BASE}/patients/{p}/assessments", json=payload).status_code == 403
    assert count_assessments(seeded_app, payload["client_submission_id"]) == 0


def test_unknown_patient_is_404(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    ghost = uuid.uuid4()
    assert doctor.get(f"{BASE}/patients/{ghost}/assessment-template").status_code == 404
    assert doctor.get(f"{BASE}/patients/{ghost}/assessments").status_code == 404
    assert doctor.post(f"{BASE}/patients/{ghost}/assessments", json=body()).status_code == 404


def test_post_needs_csrf_header(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    bare = TestClient(seeded_app)
    bare.cookies.update(doctor.cookies)
    p = pid(seeded_app, "SYN-0001")
    assert bare.post(f"{BASE}/patients/{p}/assessments", json=body()).status_code == 403


# --- Vorlage --------------------------------------------------------------------------------


def test_template_contains_only_terms_of_tracked_symptoms(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    template = doctor.get(f"{BASE}/patients/{p}/assessment-template", params={"lang": "en"}).json()
    assert template["patient_id"] == p
    assert template["ctcae_version"] == "ctcae-subset-v1"
    assert template["source"]["id"] == "SRC-FIXTURE"
    ids = [t["ctcae_term_id"] for t in template["terms"]]
    assert ids == [NAUSEA, FEVER]  # Subraum, Reihenfolge des Fragebogens
    assert OTHER not in ids  # im CTCAE-Subset, aber nicht getrackt
    nausea, fever = template["terms"]
    assert nausea["term_en"] == "Fixture nausea"
    assert nausea["label"] == "Fixture nausea"  # kein lokalisiertes Label im Inhalt ⇒ Englisch
    assert nausea["meddra_code"] == "99999001"
    assert nausea["grades"] == {
        "1": "Fixture grade 1",
        "2": "Fixture grade 2",
        "3": "Fixture grade 3",
    }
    assert nausea["symptom_keys"] == ["nausea"]
    assert fever["grades"] == {"1": "Fixture grade 1", "3": "Fixture grade 3"}  # Grad 2 undefiniert
    assert nausea["last_grade"] is None


def test_template_pro_hint_is_a_hint_not_a_grade(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    terms = {
        t["ctcae_term_id"]: t
        for t in doctor.get(f"{BASE}/patients/{p}/assessment-template").json()["terms"]
    }
    # seit dem letzten Termin (11.10.): Übelkeit 1, 2, 3
    assert terms[NAUSEA]["pro_hint"] == {"nausea.severity.max": 3, "nausea.severity.last": 3}
    assert terms[FEVER]["pro_hint"] == {"fever.presence.max": 0, "fever.presence.last": 0}
    for term in terms.values():
        assert not {"grade", "suggested_grade", "proposal"} & set(term)


def test_template_shows_the_last_recorded_grade(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    assert doctor.post(f"{BASE}/patients/{p}/assessments", json=body()).status_code == 201
    terms = {
        t["ctcae_term_id"]: t["last_grade"]
        for t in doctor.get(f"{BASE}/patients/{p}/assessment-template").json()["terms"]
    }
    assert terms == {NAUSEA: 2, FEVER: 0}


@pytest.mark.skipif(not REAL_CONTENT.is_dir(), reason="challenge/content/ (A1) nicht vorhanden")
def test_template_for_real_content_is_the_tracked_subspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.main import create_app
    from app.services import seed

    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL_CONTENT))
    content = get_content()
    assert content is not None
    settings = make_settings(tmp_path)
    migrate(settings)
    app = create_app(settings)
    with app.state.session_factory() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
    doctor = staff(app)
    spec = next(p for p in content.scenario["patients"] if p["pseudonym"] == "SYN-0001")
    regimen = next(r for r in content.regimens["regimens"] if r["id"] == spec["regimen_id"])
    tracked = {i["symptom_key"] for i in content.items["items"] if i.get("core")} | set(
        regimen["symptom_keys"]
    )
    expected = {
        t for i in content.items["items"] if i["symptom_key"] in tracked for t in i["ctcae_terms"]
    }
    template = doctor.get(f"{BASE}/patients/{pid(app, 'SYN-0001')}/assessment-template").json()
    got = [t["ctcae_term_id"] for t in template["terms"]]
    assert set(got) == expected
    assert len(got) == len(set(got))  # dedupliziert
    for term in template["terms"]:
        defined = next(t for t in content.ctcae["terms"] if t["id"] == term["ctcae_term_id"])
        assert term["grades"] == defined["grades"]  # Gradtexte unverändert aus ctcae.yaml


# --- Speichern ------------------------------------------------------------------------------


def test_create_assessment_returns_contract_shape_and_is_audited(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    payload = body()
    response = doctor.post(f"{BASE}/patients/{p}/assessments", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert set(data) == {
        "assessment_id",
        "fact_id",
        "patient_id",
        "assessed_at",
        "assessed_by",
        "ctcae_version",
        "related_alert_ids",
        "items",
    }
    assert data["fact_id"] == f"assess-{data['assessment_id']}"
    assert data["patient_id"] == p
    assert data["assessed_at"] == "2026-10-17T09:00:00+02:00"
    assert data["assessed_by"] == "doctor"
    assert data["ctcae_version"] == "ctcae-subset-v1"
    assert data["items"] == [
        {
            "ctcae_term_id": FEVER,
            "term_en": "Fixture fever",
            "meddra_code": "99999002",
            "grade": 0,
            "attribution": "unknown",
            "note": None,
        },
        {
            "ctcae_term_id": NAUSEA,
            "term_en": "Fixture nausea",
            "meddra_code": "99999001",
            "grade": 2,
            "attribution": "probable",
            "note": "Kontrolle",
        },
    ]
    (event,) = audits(seeded_app, "create_assessment")
    assert event.target_id == data["assessment_id"]
    assert event.subject_id == p
    assert event.actor_role == "clinician"
    assert event.details_json == {"items": 2, "related_alerts": 0}  # keine Notiz im Audit
    assert "Kontrolle" not in str(event.details_json)


def test_assessment_is_listed_in_timeline_and_resolvable_as_fact(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    created = doctor.post(f"{BASE}/patients/{p}/assessments", json=body()).json()
    listed = doctor.get(f"{BASE}/patients/{p}/assessments").json()
    assert [a["assessment_id"] for a in listed] == [created["assessment_id"]]
    timeline = doctor.get(f"{BASE}/patients/{p}/timeline").json()
    assert [a["assessment_id"] for a in timeline["assessments"]] == [created["assessment_id"]]
    fact = doctor.get(f"{BASE}/patients/{p}/facts/{created['fact_id']}").json()
    assert (fact["kind"], fact["fact_id"], fact["at"]) == (
        "assessment",
        created["fact_id"],
        created["assessed_at"],
    )
    assert fact["data"] == created
    assert "2 pojmů" in fact["label"]
    other = pid(seeded_app, "SYN-0002")
    assert doctor.get(f"{BASE}/patients/{other}/facts/{created['fact_id']}").status_code == 404
    assert doctor.get(f"{BASE}/patients/{other}/assessments").json() == []


def test_assessment_links_to_own_alerts(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    alert = doctor.get(f"{BASE}/patients/{p}/alerts").json()[0]["alert_id"]
    data = doctor.post(
        f"{BASE}/patients/{p}/assessments", json=body(related_alert_ids=[alert])
    ).json()
    assert data["related_alert_ids"] == [alert]
    (event,) = audits(seeded_app, "create_assessment")
    assert event.details_json["related_alerts"] == 1


# --- Idempotenz -----------------------------------------------------------------------------


def test_same_submission_is_idempotent_and_other_body_conflicts(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    payload = body()
    first = doctor.post(f"{BASE}/patients/{p}/assessments", json=payload)
    again = doctor.post(f"{BASE}/patients/{p}/assessments", json=payload)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert count_assessments(seeded_app, payload["client_submission_id"]) == 1
    assert len(audits(seeded_app, "create_assessment")) == 1  # Replay erzeugt kein Audit
    changed = {**payload, "items": [{"ctcae_term_id": NAUSEA, "grade": 3}]}
    conflict = doctor.post(f"{BASE}/patients/{p}/assessments", json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"


def test_item_order_does_not_matter_for_replay(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    payload = body()
    assert doctor.post(f"{BASE}/patients/{p}/assessments", json=payload).status_code == 201
    reordered = {**payload, "items": list(reversed(payload["items"]))}
    assert doctor.post(f"{BASE}/patients/{p}/assessments", json=reordered).status_code == 200


def test_submission_id_is_scoped_per_patient(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    payload = body()
    one = doctor.post(f"{BASE}/patients/{pid(seeded_app, 'SYN-0001')}/assessments", json=payload)
    two = doctor.post(f"{BASE}/patients/{pid(seeded_app, 'SYN-0002')}/assessments", json=payload)
    assert (one.status_code, two.status_code) == (201, 201)
    assert one.json()["assessment_id"] != two.json()["assessment_id"]
    assert count_assessments(seeded_app, payload["client_submission_id"]) == 2


def test_four_identical_parallel_submissions_store_one_record(seeded_app: FastAPI) -> None:
    p = pid(seeded_app, "SYN-0001")
    payload = body()
    doctors = [staff(seeded_app) for _ in range(4)]
    results = run_parallel(
        lambda i: doctors[i].post(f"{BASE}/patients/{p}/assessments", json=payload), 4
    )
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201], [
        (r.status_code, r.text) for r in results
    ]
    assert len({r.json()["assessment_id"] for r in results}) == 1
    assert count_assessments(seeded_app, payload["client_submission_id"]) == 1
    with seeded_app.state.session_factory() as session:
        items = session.scalar(select(func.count()).select_from(AssessmentItem))
    assert items == 2
    assert len(audits(seeded_app, "create_assessment")) == 1


# --- Validierung (G-13) ---------------------------------------------------------------------


def foreign_alert(app: FastAPI) -> str:
    with app.state.session_factory() as session:
        return str(
            session.scalars(
                select(Alert.id).where(Alert.patient_id == pid(app, "SYN-0002"))
            ).first()
        )


@pytest.mark.parametrize(
    ("label", "change", "field", "code"),
    [
        (
            "term outside subspace",
            {"items": [{"ctcae_term_id": OTHER, "grade": 1}]},
            "items.0.ctcae_term_id",
            "unknown_term",
        ),
        (
            "unknown term",
            {"items": [{"ctcae_term_id": "CTCAE-NOPE", "grade": 1}]},
            "items.0.ctcae_term_id",
            "unknown_term",
        ),
        (
            "grade not defined for term",
            {"items": [{"ctcae_term_id": FEVER, "grade": 2}]},
            "items.0.grade",
            "grade_not_defined",
        ),
        (
            "duplicate term",
            {
                "items": [
                    {"ctcae_term_id": NAUSEA, "grade": 1},
                    {"ctcae_term_id": NAUSEA, "grade": 2},
                ]
            },
            "items.1.ctcae_term_id",
            "duplicate_term",
        ),
        (
            "unknown alert",
            {"related_alert_ids": [str(uuid.uuid4())]},
            "related_alert_ids.0",
            "foreign_alert",
        ),
    ],
)
def test_domain_errors_are_422_with_field_path_and_store_nothing(
    seeded_app: FastAPI, label: str, change: dict[str, Any], field: str, code: str
) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    payload = body(**change)
    response = doctor.post(f"{BASE}/patients/{p}/assessments", json=payload)
    assert response.status_code == 422, label
    assert response.json()["code"] == "validation_failed"
    errors = response.json()["field_errors"]
    assert {"field": field, "code": code} == {k: errors[0][k] for k in ("field", "code")}, errors
    assert count_assessments(seeded_app, payload["client_submission_id"]) == 0
    assert not audits(seeded_app, "create_assessment")


def test_alert_of_another_patient_is_422(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    payload = body(related_alert_ids=[foreign_alert(seeded_app)])
    response = doctor.post(f"{BASE}/patients/{p}/assessments", json=payload)
    assert response.status_code == 422
    assert response.json()["field_errors"][0]["code"] == "foreign_alert"
    assert count_assessments(seeded_app, payload["client_submission_id"]) == 0


def test_grade_zero_is_allowed_even_if_not_defined_in_ctcae(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    payload = body(items=[{"ctcae_term_id": FEVER, "grade": 0}])
    assert doctor.post(f"{BASE}/patients/{p}/assessments", json=payload).status_code == 201


@pytest.mark.parametrize(
    "change",
    [
        {"items": []},
        {"items": [{"ctcae_term_id": NAUSEA, "grade": 6}]},
        {"items": [{"ctcae_term_id": NAUSEA, "grade": -1}]},
        {"items": [{"ctcae_term_id": NAUSEA, "grade": "2"}]},
        {"items": [{"ctcae_term_id": NAUSEA, "grade": 2.5}]},
        {"items": [{"ctcae_term_id": NAUSEA, "grade": 1, "attribution": "certain"}]},
        {"items": [{"ctcae_term_id": NAUSEA, "grade": 1, "note": "x" * 501}]},
        {"items": [{"ctcae_term_id": NAUSEA, "grade": 1, "extra": True}]},
        {"client_submission_id": "not-a-uuid"},
        {"related_alert_ids": "abc"},
        {"surprise": 1},
    ],
)
def test_shape_errors_are_422(seeded_app: FastAPI, change: dict[str, Any]) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    response = doctor.post(f"{BASE}/patients/{p}/assessments", json=body(**change))
    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert not audits(seeded_app, "create_assessment")


def test_note_of_500_characters_is_accepted(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    payload = body(items=[{"ctcae_term_id": NAUSEA, "grade": 1, "note": "x" * 500}])
    assert doctor.post(f"{BASE}/patients/{p}/assessments", json=payload).status_code == 201
