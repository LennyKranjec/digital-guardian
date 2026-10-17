# ruff: noqa: F401, F811
"""A3-Gegenproben zu T-08 (Besitz A3): FHIR-Bundle unabhängig geprüft - Pflichtfelder je Ressource
(R4-Kardinalität 1..1), Zeitzonen, Referenzen über fullUrl, Zählung gegen die Datenbank,
Privacy, Parallelabruf. Mit `A3_FHIR_OUT=<Ordner>` schreibt der Test die Bundles für den
HAPI-Referenzvalidator (Java, außerhalb von pytest). Hilfen aus `test_fhir.py`.
"""

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from conftest import run_parallel
from test_fhir import BASE, export, pid, references, resources, staff, walk, worked
from waechter.models import Alert, Answer, Patient, Response

PSEUDONYMS = ["SYN-0001", "SYN-0002", "SYN-0003", "SYN-0004", "SYN-0005"]
#: FHIR R4: Elemente mit Mindestkardinalität 1 (nur die der exportierten Ressourcenarten)
REQUIRED: dict[str, list[str]] = {
    "Patient": [],
    "Condition": ["clinicalStatus", "code", "subject"],  # v2.6: aus diagnosis_code
    "MedicationStatement": ["status", "subject"],
    "Questionnaire": ["status"],
    "QuestionnaireResponse": ["status"],
    "Observation": ["status", "code"],
    "Flag": ["status", "code", "subject"],
    "DocumentReference": ["status", "content"],
    "Provenance": ["target", "recorded", "agent"],
    "AuditEvent": ["type", "recorded", "agent", "source"],
}
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
WITH_ZONE = re.compile(r"(Z|[+-]\d{2}:\d{2})$")


def check_structure(bundle: dict[str, Any]) -> None:
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    urls: list[str] = [e["fullUrl"] for e in bundle["entry"]]
    assert len(urls) == len(set(urls)), "fullUrl nicht eindeutig"
    assert all(u.startswith("urn:uuid:") for u in urls)
    ids = [e["resource"]["id"] for e in bundle["entry"]]
    assert len(ids) == len(set(ids)), "Ressourcen-ID nicht eindeutig"
    for entry in bundle["entry"]:
        resource = entry["resource"]
        assert entry["fullUrl"] == f"urn:uuid:{resource['id']}"
        missing = [
            k for k in REQUIRED[resource["resourceType"]] if resource.get(k) in (None, [], {})
        ]
        assert not missing, (resource["resourceType"], missing)
        assert resource["resourceType"] in REQUIRED, "unerwartete Ressourcenart"
    known = set(urls)
    dangling = [r for r in references(bundle["entry"]) if r not in known]
    assert not dangling, dangling[:3]
    for value in walk(bundle):
        if isinstance(value, str) and DATETIME.match(value):
            assert WITH_ZONE.search(value), f"Zeit ohne Zeitzone: {value}"


def dump(bundle: dict[str, Any], name: str) -> None:
    out = os.environ.get("A3_FHIR_OUT")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / f"{name}.json").write_text(json.dumps(bundle, ensure_ascii=False), "utf-8")


@pytest.mark.parametrize("pseudonym", PSEUDONYMS)
def test_a3_every_patient_bundle_is_structurally_valid_and_counts_match(
    seeded_app: FastAPI, pseudonym: str
) -> None:
    doctor = staff(seeded_app)
    patient = pid(seeded_app, pseudonym)
    bundle = export(doctor, patient)
    dump(bundle, pseudonym.lower())
    check_structure(bundle)
    with seeded_app.state.session_factory() as session:
        responses = session.scalar(
            select(func.count()).select_from(Response).where(Response.patient_id == patient)
        )
        answers = session.scalar(
            select(func.count())
            .select_from(Answer)
            .join(Response, Answer.response_id == Response.id)
            .where(Response.patient_id == patient)
        )
        alerts = session.scalar(
            select(func.count()).select_from(Alert).where(Alert.patient_id == patient)
        )
    qrs = resources(bundle, "QuestionnaireResponse")
    flags = resources(bundle, "Flag")
    pro = [
        o
        for o in resources(bundle, "Observation")
        if any(
            c.get("code") == "pro-item"
            for cat in [o.get("code", {})]
            for c in cat.get("coding", [])
        )
    ]
    assert len(flags) == alerts, "Flag je Meldung"
    assert len(qrs) <= responses  # nur auflösbare Fragebögen
    assert len(pro) <= answers
    assert len(resources(bundle, "Patient")) == 1


def test_a3_worked_state_bundle_is_valid_and_keeps_notes_private(
    worked: tuple[FastAPI, str],
) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    dump(bundle, "syn0001-actions")
    check_structure(bundle)
    text = json.dumps(bundle, ensure_ascii=False)
    assert "GEHEIM-QUITTIERUNG" not in text  # Notiz der Quittierung wird nie exportiert
    assert "Testpatientin" not in text  # kein Name
    assert "Synthetische Testdiagnose" not in text  # kein Diagnosetext
    assert resources(bundle, "AuditEvent"), "Quittierung muss als AuditEvent erscheinen"
    assert resources(bundle, "Provenance")


def test_a3_parallel_exports_are_identical_apart_from_the_timestamp(
    seeded_app: FastAPI,
) -> None:
    patient = pid(seeded_app, "SYN-0001")
    clients = [staff(seeded_app) for _ in range(4)]
    bundles = run_parallel(lambda i: export(clients[i], patient), 4)
    for bundle in bundles:
        bundle.pop("timestamp", None)
    assert all(b == bundles[0] for b in bundles)


def test_a3_export_does_not_leak_other_patients(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    first = json.dumps(export(doctor, pid(seeded_app, "SYN-0001")), ensure_ascii=False)
    for other in PSEUDONYMS[1:]:
        assert other not in first
        assert pid(seeded_app, other) not in first


# --- Echter Inhalt (challenge/content): das ist, was der HAPI-Validator sehen muss ---------------


@pytest.fixture
def real_export_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from app.main import create_app
    from app.services import seed
    from conftest import make_settings, migrate
    from waechter.constants import CONTENT_DIR_ENV

    monkeypatch.setenv(CONTENT_DIR_ENV, str(Path(__file__).resolve().parents[1] / "content"))
    settings = make_settings(tmp_path)
    migrate(settings)
    app = create_app(settings)
    with app.state.session_factory() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
        session.commit()
    yield app
    app.state.engine.dispose()


@pytest.mark.parametrize("pseudonym", PSEUDONYMS)
def test_a3_real_content_bundle_is_structurally_valid(
    real_export_app: FastAPI, pseudonym: str
) -> None:
    bundle = export(staff(real_export_app), pid(real_export_app, pseudonym))
    dump(bundle, f"real-{pseudonym.lower()}")
    check_structure(bundle)
    kinds = {e["resource"]["resourceType"] for e in bundle["entry"]}
    assert {"Patient", "Questionnaire", "QuestionnaireResponse", "Observation"} <= kinds


def test_a3_real_content_after_actions(real_export_app: FastAPI) -> None:
    app = real_export_app
    doctor = staff(app)
    patient = pid(app, "SYN-0001")
    alert = doctor.get(f"{BASE}/patients/{patient}/alerts").json()[0]["alert_id"]
    marker = "GEHEIM-QUITTIERUNG-A3"
    assert (
        doctor.post(
            f"{BASE}/alerts/{alert}/acknowledge",
            json={"decision": "contact_patient", "note": marker},
        ).status_code
        == 200
    )
    template = doctor.get(f"{BASE}/patients/{patient}/assessment-template").json()
    term = template["terms"][0]["ctcae_term_id"]
    created = doctor.post(
        f"{BASE}/patients/{patient}/assessments",
        json={
            "client_submission_id": str(uuid.uuid4()),
            "items": [{"ctcae_term_id": term, "grade": 2, "note": "Ärztliche Beobachtung A3"}],
        },
    )
    assert created.status_code == 201, created.text
    assert doctor.post(f"{BASE}/patients/{patient}/summary").status_code in (200, 201)
    bundle = export(doctor, patient)
    dump(bundle, "real-syn0001-actions")
    check_structure(bundle)
    assert marker not in json.dumps(bundle, ensure_ascii=False)
    kinds = {e["resource"]["resourceType"] for e in bundle["entry"]}
    assert {"AuditEvent", "Provenance", "DocumentReference", "Flag"} <= kinds
