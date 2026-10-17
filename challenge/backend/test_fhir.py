"""FHIR-R4-Export (T-08): Struktur, Referenzen, Datenschutz, Determinismus, Rechte, Audit.

Die Prüfung gegen den Referenzvalidator (HAPI, Java) läuft außerhalb von pytest; Befehl und Ergebnis
stehen im Handoff. Diese Tests brauchen kein Java.
"""

import base64
import json
import re
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.persistence.models import AuditEvent
from conftest import CSRF, login
from waechter.fhir import builder as fhir
from waechter.models import Alert, Answer, Patient, Response

BASE = "/api/v1/waechter"
DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(Z|[+-]\d{2}:\d{2})?$")


def staff(app: FastAPI, username: str = "doctor") -> TestClient:
    client = TestClient(app, headers=CSRF)
    login(client, username)
    return client


def pid(app: FastAPI, pseudonym: str) -> str:
    with app.state.session_factory() as session:
        return str(session.scalars(select(Patient.id).where(Patient.pseudonym == pseudonym)).one())


def export(client: TestClient, patient_id: str) -> dict[str, Any]:
    response = client.get(f"{BASE}/patients/{patient_id}/fhir")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = json.loads(response.content)
    return body


def resources(bundle: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == kind]


def walk(node: Any) -> Any:
    """Alle Werte eines JSON-Baums."""
    if isinstance(node, dict):
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)
    else:
        yield node


def references(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "reference" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(references(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(references(value))
    return found


@pytest.fixture
def worked(seeded_app: FastAPI) -> tuple[FastAPI, str]:
    """SYN-0001 mit Quittierung (Notiz), CTCAE-Aufnahme (Notiz) und der Seed-Kurzfassung."""
    doctor = staff(seeded_app)
    patient = pid(seeded_app, "SYN-0001")
    alert = doctor.get(f"{BASE}/patients/{patient}/alerts").json()[0]["alert_id"]
    doctor.post(
        f"{BASE}/alerts/{alert}/acknowledge",
        json={"decision": "contact_patient", "note": "GEHEIM-QUITTIERUNG"},
    )
    doctor.post(
        f"{BASE}/patients/{patient}/assessments",
        json={
            "client_submission_id": str(uuid.uuid4()),
            "items": [
                {
                    "ctcae_term_id": "CTCAE-FIX_NAUSEA",
                    "grade": 2,
                    "attribution": "probable",
                    "note": "Ärztliche Beobachtung",
                }
            ],
        },
    )
    return seeded_app, patient


# --- Zugriff --------------------------------------------------------------------------------


def test_anonymous_gets_401(seeded_app: FastAPI) -> None:
    anon = TestClient(seeded_app, headers=CSRF)
    assert anon.get(f"{BASE}/patients/{pid(seeded_app, 'SYN-0001')}/fhir").status_code == 401


@pytest.mark.parametrize("username", ["patient", "patient2", "user"])
def test_patients_and_other_roles_get_403(seeded_app: FastAPI, username: str) -> None:
    other = staff(seeded_app, username)
    patient = pid(seeded_app, "SYN-0001")
    assert other.get(f"{BASE}/patients/{patient}/fhir").status_code == 403
    with seeded_app.state.session_factory() as session:
        assert not session.scalars(
            select(AuditEvent).where(AuditEvent.action == "export_fhir")
        ).all()


def test_unknown_patient_is_404(seeded_app: FastAPI) -> None:
    assert staff(seeded_app).get(f"{BASE}/patients/{uuid.uuid4()}/fhir").status_code == 404


def test_clinician_and_admin_may_export_and_the_export_is_audited(seeded_app: FastAPI) -> None:
    patient = pid(seeded_app, "SYN-0001")
    for username in ("doctor", "admin"):
        client = staff(seeded_app, username)
        response = client.get(f"{BASE}/patients/{patient}/fhir")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/fhir+json")
    with seeded_app.state.session_factory() as session:
        events = session.scalars(select(AuditEvent).where(AuditEvent.action == "export_fhir")).all()
    assert {e.actor_role for e in events} == {"clinician", "admin"}
    assert all(e.subject_id == patient and e.target_id == patient for e in events)
    assert all(set(e.details_json) == {"resources"} for e in events)  # nur die Anzahl


# --- Struktur -------------------------------------------------------------------------------


def test_bundle_is_a_collection_with_deterministic_ids(worked: tuple[FastAPI, str]) -> None:
    app, patient = worked
    doctor = staff(app)
    first = doctor.get(f"{BASE}/patients/{patient}/fhir").content
    second = doctor.get(f"{BASE}/patients/{patient}/fhir").content
    assert first == second  # gleiche Daten und Uhr ⇒ gleiches Bundle (Byte für Byte)
    bundle = json.loads(first)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert bundle["timestamp"] == "2026-10-17T09:00:00+02:00"
    assert bundle["identifier"] == {"system": "urn:waechter:bundle", "value": "SYN-0001"}
    ids = [e["resource"]["id"] for e in bundle["entry"]]
    assert len(ids) == len(set(ids))
    for entry in bundle["entry"]:
        assert entry["fullUrl"] == f"urn:uuid:{entry['resource']['id']}"
        assert re.fullmatch(r"[0-9a-f-]{36}", entry["resource"]["id"])


def test_builder_is_pure_and_orders_entries_by_type() -> None:
    data = fhir.ExportData(
        patient_id="p1",
        pseudonym="SYN-9999",
        sex="female",
        birth_year=1970,
        language="cs",
        therapy_id="t1",
        regimen_label="R",
        cycle_start="2026-10-01T09:00:00+02:00",
        drugs=[fhir.DrugData("Drug", "L01AA01")],
        generated_at="2026-10-17T09:00:00+02:00",
    )
    assert fhir.build_bundle(data) == fhir.build_bundle(data)
    kinds = [e["resource"]["resourceType"] for e in fhir.build_bundle(data)["entry"]]
    assert kinds == ["Patient", "MedicationStatement"]
    assert fhir.uid("Patient", "p1") == fhir.uid("Patient", "p1") != fhir.uid("Patient", "p2")


def test_every_reference_resolves_inside_the_bundle(worked: tuple[FastAPI, str]) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    full_urls = {e["fullUrl"] for e in bundle["entry"]}
    found = references(bundle)
    assert len(found) > 20
    assert all(r.startswith("urn:uuid:") and r in full_urls for r in found)  # nur interne Bezüge


def test_all_date_times_carry_a_time_zone(worked: tuple[FastAPI, str]) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    stamps = [v for v in walk(bundle) if isinstance(v, str) and re.match(r"\d{4}-\d{2}-\d{2}T", v)]
    assert len(stamps) > 10
    for stamp in stamps:
        match = DATETIME.match(stamp)
        assert match is not None, stamp
        assert match.group(1) is not None, stamp


def test_patient_has_pseudonym_birth_year_and_no_personal_data(worked: tuple[FastAPI, str]) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    (resource,) = resources(bundle, "Patient")
    assert resource["identifier"] == [{"system": "urn:waechter:pseudonym", "value": "SYN-0001"}]
    assert resource["birthDate"] == "1970"
    assert resource["gender"] == "female"
    assert {"urn:waechter:tag"} == {t["system"] for t in resource["meta"]["tag"]}
    assert resource["meta"]["tag"][0]["code"] == "synthetic"
    for forbidden in ("name", "telecom", "address", "photo", "contact", "maritalStatus"):
        assert forbidden not in resource
    blob = json.dumps(bundle, ensure_ascii=False)
    for secret in ("Testpatientin", "Synthetische Testdiagnose", "GEHEIM-QUITTIERUNG", "SYN-0002"):
        assert secret not in blob
    assert "Ärztliche Beobachtung" in blob  # ärztliche Dokumentation der Aufnahme bleibt erhalten


def test_every_resource_is_synthetic_tagged_and_has_a_narrative(
    worked: tuple[FastAPI, str],
) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    for entry in bundle["entry"]:
        resource = entry["resource"]
        tags = {(t["system"], t["code"]) for t in resource["meta"]["tag"]}
        assert ("urn:waechter:tag", "synthetic") in tags, resource["resourceType"]
        assert resource["text"]["status"] == "generated"
        assert resource["text"]["div"].startswith('<div xmlns="http://www.w3.org/1999/xhtml"')


def test_medication_statements_use_atc(worked: tuple[FastAPI, str]) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    statements = resources(bundle, "MedicationStatement")
    assert statements
    for statement in statements:
        coding = statement["medicationCodeableConcept"]["coding"][0]
        assert coding["system"] == "http://www.whocc.no/atc"
        assert re.fullmatch(r"[A-Z][0-9]{2}[A-Z]{2}[0-9]{2}", coding["code"])
        assert statement["status"] == "active"
        assert statement["effectivePeriod"]["start"].endswith("+02:00")


def test_questionnaire_matches_the_patient_language_and_scales(worked: tuple[FastAPI, str]) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    (questionnaire,) = resources(bundle, "Questionnaire")
    assert questionnaire["url"] == "urn:waechter:questionnaire:items-v1:FIX-REG"
    assert questionnaire["status"] == "active"
    assert questionnaire["language"] == "cs"  # Sprache der Patientin
    assert questionnaire["subjectType"] == ["Patient"]
    groups = {g["linkId"]: g for g in questionnaire["item"]}
    assert set(groups) == {"nausea", "fever"}
    assert groups["nausea"]["text"] == "Nevolnost"
    severity = groups["nausea"]["item"][0]
    assert severity["linkId"] == "nausea.severity"
    assert severity["type"] == "choice"
    assert [o["valueCoding"]["code"] for o in severity["answerOption"]] == ["0", "1", "2", "3", "4"]
    presence = groups["fever"]["item"][0]
    assert [o["valueCoding"]["code"] for o in presence["answerOption"]] == ["0", "1"]
    assert all(
        o["valueCoding"]["system"] == "urn:waechter:pro-scale" for o in presence["answerOption"]
    )
    link_ids = [i["linkId"] for g in questionnaire["item"] for i in [g, *g["item"]]]
    assert len(link_ids) == len(set(link_ids))


def test_responses_and_observations_mirror_the_stored_answers(worked: tuple[FastAPI, str]) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    with app.state.session_factory() as session:
        stored_responses = session.scalar(
            select(func.count()).select_from(Response).where(Response.patient_id == patient)
        )
        stored_answers = session.scalar(
            select(func.count())
            .select_from(Answer)
            .join(Response, Response.id == Answer.response_id)
            .where(Response.patient_id == patient)
        )
    qrs = resources(bundle, "QuestionnaireResponse")
    pro = [
        o
        for o in resources(bundle, "Observation")
        if o["category"][0]["coding"][0]["code"] == "survey"
    ]
    assert len(qrs) == stored_responses
    assert len(pro) == stored_answers
    (questionnaire,) = resources(bundle, "Questionnaire")
    known_links = {i["linkId"] for g in questionnaire["item"] for i in g["item"]}
    qr_ids = {f"urn:uuid:{q['id']}" for q in qrs}
    for qr in qrs:
        assert qr["status"] == "completed"
        assert qr["questionnaire"] == questionnaire["url"]
        assert DATETIME.match(qr["authored"])
        tags = {t["system"]: t["code"] for t in qr["meta"]["tag"]}
        assert tags["urn:waechter:channel"] in {"web", "phone", "paper"}
        assert tags["urn:waechter:entered-by"] in {"self", "proxy", "nurse"}
        if tags["urn:waechter:entered-by"] == "self":
            assert qr["source"]["reference"].startswith("urn:uuid:")
        else:
            assert "source" not in qr  # Bezug nur, wenn die Patientin selbst antwortete
        for group in qr["item"]:
            for child in group["item"]:
                assert child["linkId"] in known_links
                for answer in child.get("answer", []):
                    assert answer["valueCoding"]["code"] in {"0", "1", "2", "3", "4"}
    for observation in pro:
        assert observation["status"] == "final"
        assert observation["code"]["coding"][0]["system"] == "urn:waechter:pro-item"
        assert observation["derivedFrom"][0]["reference"] in qr_ids
        assert ("valueInteger" in observation) != ("dataAbsentReason" in observation)
        assert observation["performer"]
    skipped = [o for o in pro if "dataAbsentReason" in o]
    assert skipped  # übersprungene Werte (null) bleiben als 'asked-declined' sichtbar
    assert skipped[0]["dataAbsentReason"]["coding"][0]["code"] == "asked-declined"
    assert skipped[0]["dataAbsentReason"]["coding"][0]["system"] == (
        "http://terminology.hl7.org/CodeSystem/data-absent-reason"
    )


def test_flags_mirror_the_alerts(worked: tuple[FastAPI, str]) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    with app.state.session_factory() as session:
        alerts = session.scalars(select(Alert).where(Alert.patient_id == patient)).all()
    flags = resources(bundle, "Flag")
    assert len(flags) == len(alerts)
    by_rule = {f["code"]["coding"][0]["code"]: f for f in flags}
    assert set(by_rule) == {a.rule_id for a in alerts}
    statuses = {f["status"] for f in flags}
    assert statuses == {"inactive"}  # die einzige Meldung von SYN-0001 wurde quittiert
    flag = by_rule["R-SEV-01"]
    assert flag["code"]["coding"][0]["system"] == "urn:waechter:rule"
    assert flag["category"][0]["coding"][0]["code"] == "red"
    assert flag["period"]["start"].endswith("+02:00")
    assert flag["period"]["end"].endswith("+02:00")  # Quittierung beendet den Zeitraum
    assert flag["code"]["text"].startswith("Nevolnost")


def test_open_alerts_are_active_flags(seeded_app: FastAPI) -> None:
    bundle = export(staff(seeded_app), pid(seeded_app, "SYN-0003"))
    flags = resources(bundle, "Flag")
    assert flags
    assert {f["status"] for f in flags} == {"active"}
    assert all("end" not in f["period"] for f in flags)


def test_ctcae_assessment_is_an_exam_observation(worked: tuple[FastAPI, str]) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    exams = [
        o
        for o in resources(bundle, "Observation")
        if o["category"][0]["coding"][0]["code"] == "exam"
    ]
    (exam,) = exams
    codings = {c["system"]: c for c in exam["code"]["coding"]}
    assert codings["http://terminology.hl7.org/CodeSystem/mdr"]["code"] == "99999001"
    assert codings["urn:waechter:ctcae"]["code"] == "CTCAE-FIX_NAUSEA"
    assert exam["valueCodeableConcept"]["coding"][0] == {
        "system": "urn:waechter:ctcae-grade",
        "code": "2",
        "display": "Grade 2",
    }
    component = exam["component"][0]
    assert component["valueCodeableConcept"]["coding"][0]["code"] == "probable"
    assert exam["performer"] == [{"display": "clinician"}]
    assert exam["note"] == [{"text": "Ärztliche Beobachtung"}]
    assert exam["status"] == "final"
    assert exam["effectiveDateTime"] == "2026-10-17T09:00:00+02:00"


def test_summary_is_exported_as_document_reference_with_provenance(
    worked: tuple[FastAPI, str],
) -> None:
    app, patient = worked
    doctor = staff(app)
    bundle = export(doctor, patient)
    (document,) = resources(bundle, "DocumentReference")
    (provenance,) = resources(bundle, "Provenance")
    attachment = document["content"][0]["attachment"]
    assert attachment["contentType"] == "text/plain"
    text = base64.b64decode(attachment["data"]).decode("utf-8")
    summary = doctor.get(f"{BASE}/patients/{patient}/summary").json()
    assert text.splitlines()[0].startswith(summary["sentences"][0]["text"])
    assert summary["sentences"][0]["refs"][0] in text
    assert document["status"] == "current"
    assert document["docStatus"] == "preliminary"
    assert provenance["target"] == [{"reference": f"urn:uuid:{document['id']}"}]
    assert provenance["agent"][0]["who"] == {"type": "Device", "display": "template-v1"}
    assert provenance["recorded"] == "2026-10-17T09:00:00+02:00"
    assert (
        provenance["entity"][0]["what"]["identifier"]["value"]
        == (summary["provenance"]["facts_hash"])
    )


def test_acknowledgement_is_exported_as_audit_event(worked: tuple[FastAPI, str]) -> None:
    app, patient = worked
    bundle = export(staff(app), patient)
    (event,) = resources(bundle, "AuditEvent")
    assert event["action"] == "U"
    assert event["recorded"] == "2026-10-17T09:00:00+02:00"
    assert event["outcome"] == "0"
    assert event["type"]["code"] == "rest"
    assert event["agent"] == [{"requestor": True, "who": {"display": "clinician"}}]
    assert event["source"]["observer"]["display"]
    (flag,) = resources(bundle, "Flag")
    assert event["entity"][0]["what"] == {"reference": f"urn:uuid:{flag['id']}"}
    assert "GEHEIM-QUITTIERUNG" not in json.dumps(event)  # Notiz der Quittierung nie im Export


def test_patient_without_alerts_has_no_flags_and_no_audit_events(seeded_app: FastAPI) -> None:
    bundle = export(staff(seeded_app), pid(seeded_app, "SYN-0005"))
    assert resources(bundle, "Flag") == []
    assert resources(bundle, "AuditEvent") == []
    assert resources(bundle, "Patient")


def test_english_patient_gets_english_texts(seeded_app: FastAPI) -> None:
    bundle = export(staff(seeded_app), pid(seeded_app, "SYN-0002"))
    (questionnaire,) = resources(bundle, "Questionnaire")
    assert questionnaire["language"] == "en"
    assert questionnaire["item"][0]["text"] == "Nausea"


def test_export_only_contains_the_requested_patient(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    one = export(doctor, pid(seeded_app, "SYN-0001"))
    two = export(doctor, pid(seeded_app, "SYN-0002"))
    assert {e["fullUrl"] for e in one["entry"]}.isdisjoint({e["fullUrl"] for e in two["entry"]})
    assert resources(two, "Patient")[0]["identifier"][0]["value"] == "SYN-0002"
