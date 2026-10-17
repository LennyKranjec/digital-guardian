"""T-18: Transaction-Bundle im Klinikformat (PUT {Typ}/{id}) und Push an einen FHIR-Server.

Der Push läuft gegen einen lokalen `http.server` im Test (kein Netz). Live gegen IRIS for Health:
NOT RUN (kein Server verfügbar). Die HAPI-Prüfung läuft außerhalb von pytest (siehe Handoff).
"""

import json
import logging
import re
import threading
import time
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.persistence.models import AuditEvent
from conftest import CSRF
from test_fhir import BASE, export, pid, references, resources, staff, walk
from waechter.constants import CONTENT_DIR_ENV
from waechter.fhir import builder as fhir
from waechter.models import Patient
from waechter.services import fhir_push

REAL = Path(__file__).resolve().parents[1] / "content"
SECRET = "geheimes-passwort-4711"  # noqa: S105 (Testwert)
USER = "fhir-user"
OFFSET = re.compile(r"(Z|[+-]\d{2}:\d{2})$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Echter Inhalt: Diagnosecodes und SÚKL-Kennungen stehen nur dort."""
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


def tx(client: TestClient, patient_id: str) -> dict[str, Any]:
    response = client.get(f"{BASE}/patients/{patient_id}/fhir?type=transaction")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/fhir+json")
    body: dict[str, Any] = json.loads(response.content)
    return body


# --- Testserver -----------------------------------------------------------------------------


class FakeFhirServer:
    """Minimaler Transaction-Endpunkt: speichert je `Typ/id` (PUT ersetzt, kein Duplikat)."""

    def __init__(self) -> None:
        self.mode = "ok"
        self.store: dict[str, dict[str, Any]] = {}
        self.requests: list[dict[str, Any]] = []
        self.delay = 0.0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # kein Konsolenlärm
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                outer.requests.append(
                    {
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": raw,
                    }
                )
                outer.answer(self, raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/fhir/r4/"

    def answer(self, handler: BaseHTTPRequestHandler, raw: bytes) -> None:
        if self.mode == "timeout":
            time.sleep(self.delay)
            return
        if self.mode in {"401", "500"}:
            outcome = {
                "resourceType": "OperationOutcome",
                "issue": [
                    {
                        "severity": "error",
                        "code": "login" if self.mode == "401" else "exception",
                        "diagnostics": "GEHEIM-PATIENTENDATEN im Freitext",
                    }
                ],
            }
            self.send(handler, int(self.mode), outcome)
            return
        if self.mode == "garbage":
            self.send(handler, 200, None, b"<html>not json</html>")
            return
        bundle = json.loads(raw)
        entries: list[dict[str, Any]] = []
        for entry in bundle["entry"]:
            key = entry["request"]["url"]
            existed = key in self.store
            self.store[key] = entry["resource"]
            entries.append({"response": {"status": "200 OK" if existed else "201 Created"}})
        if self.mode == "partial":
            entries[-1] = {"response": {"status": "422 Unprocessable Entity"}}
        self.send(
            handler,
            200,
            {"resourceType": "Bundle", "type": "transaction-response", "entry": entries},
        )

    @staticmethod
    def send(
        handler: BaseHTTPRequestHandler,
        status: int,
        body: dict[str, Any] | None,
        raw: bytes | None = None,
    ) -> None:
        payload = raw if raw is not None else json.dumps(body).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/fhir+json")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)


@pytest.fixture
def fake() -> Iterator[FakeFhirServer]:
    server = FakeFhirServer()
    server.thread.start()
    yield server
    server.server.shutdown()
    server.server.server_close()


@pytest.fixture
def configured(fake: FakeFhirServer, monkeypatch: pytest.MonkeyPatch) -> FakeFhirServer:
    monkeypatch.setenv(fhir_push.BASE_URL_ENV, fake.url)
    monkeypatch.setenv(fhir_push.USER_ENV, USER)
    monkeypatch.setenv(fhir_push.PASSWORD_ENV, SECRET)
    return fake


def push(app: FastAPI, patient: str, username: str = "admin") -> Any:
    return staff(app, username).post(f"{BASE}/patients/{patient}/fhir/push")


# --- Bundle-Format ----------------------------------------------------------------------------


def test_default_export_is_still_a_collection(seeded_app: FastAPI) -> None:
    bundle = export(staff(seeded_app), pid(seeded_app, "SYN-0001"))
    assert bundle["type"] == "collection"
    assert all("request" not in e for e in bundle["entry"])
    assert all(e["fullUrl"].startswith("urn:uuid:") for e in bundle["entry"])


def test_unknown_bundle_type_is_rejected(seeded_app: FastAPI) -> None:
    patient = pid(seeded_app, "SYN-0001")
    assert staff(seeded_app).get(f"{BASE}/patients/{patient}/fhir?type=batch").status_code == 422


def test_transaction_entries_are_put_type_slash_id_with_the_deterministic_id(
    seeded_app: FastAPI,
) -> None:
    bundle = tx(staff(seeded_app), pid(seeded_app, "SYN-0001"))
    assert bundle["type"] == "transaction"
    assert "timestamp" not in bundle
    assert bundle["entry"]
    for entry in bundle["entry"]:
        resource = entry["resource"]
        assert re.fullmatch(r"[0-9a-f-]{36}", resource["id"])
        assert entry["request"] == {
            "method": "PUT",
            "url": f"{resource['resourceType']}/{resource['id']}",
        }
        assert entry["fullUrl"] == f"urn:uuid:{resource['id']}"
    urls = [e["request"]["url"] for e in bundle["entry"]]
    assert len(urls) == len(set(urls))


def test_transaction_ids_equal_the_collection_ids(seeded_app: FastAPI) -> None:
    doctor, patient = staff(seeded_app), pid(seeded_app, "SYN-0001")
    collection = export(doctor, patient)
    transaction = tx(doctor, patient)
    assert [e["resource"]["id"] for e in collection["entry"]] == [
        e["resource"]["id"] for e in transaction["entry"]
    ]


def test_references_are_relative_and_resolve_inside_the_bundle(seeded_app: FastAPI) -> None:
    bundle = tx(staff(seeded_app), pid(seeded_app, "SYN-0001"))
    known = {e["request"]["url"] for e in bundle["entry"]}
    found = references(bundle["entry"])
    assert found
    assert not [r for r in found if r.startswith("urn:uuid:")]
    assert not [r for r in found if r not in known], "Referenz ins Leere"
    assert any(r.startswith("Patient/") for r in found)


def test_transaction_has_no_empty_elements(seeded_app: FastAPI) -> None:
    def empties(node: Any, path: str = "") -> list[str]:
        out: list[str] = []
        if isinstance(node, dict):
            for key, value in node.items():
                if value is None or value == "" or value == [] or value == {}:
                    out.append(f"{path}.{key}")
                out.extend(empties(value, f"{path}.{key}"))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                out.extend(empties(value, f"{path}[{index}]"))
        return out

    for pseudonym in ("SYN-0001", "SYN-0003"):
        assert empties(tx(staff(seeded_app), pid(seeded_app, pseudonym))) == []


def test_prune_keeps_zero_and_false_but_drops_empty_values() -> None:
    cleaned = fhir.prune(
        {"a": 0, "b": False, "c": "", "d": [], "e": {}, "f": None, "g": [{}, {"h": ""}, 1]}
    )
    assert cleaned == {"a": 0, "b": False, "g": [1]}


def test_all_date_times_carry_the_prague_offset(seeded_app: FastAPI) -> None:
    bundle = tx(staff(seeded_app), pid(seeded_app, "SYN-0001"))
    values = [v for v in walk(bundle) if isinstance(v, str) and DATETIME.match(v)]
    assert values
    assert all(re.search(r"\+0[12]:00$", v) for v in values), [
        v for v in values if not re.search(r"\+0[12]:00$", v)
    ][:3]


def test_transaction_is_deterministic_byte_for_byte(seeded_app: FastAPI) -> None:
    doctor, patient = staff(seeded_app), pid(seeded_app, "SYN-0001")
    url = f"{BASE}/patients/{patient}/fhir?type=transaction"
    assert doctor.get(url).content == doctor.get(url).content


def test_transaction_export_is_audited_like_the_collection(seeded_app: FastAPI) -> None:
    patient = pid(seeded_app, "SYN-0001")
    tx(staff(seeded_app, "admin"), patient)
    with seeded_app.state.session_factory() as session:
        events = session.scalars(select(AuditEvent).where(AuditEvent.action == "export_fhir")).all()
    assert len(events) == 1
    assert set(events[0].details_json) == {"resources"}


def test_other_roles_and_anonymous_may_not_export_transactions(seeded_app: FastAPI) -> None:
    patient = pid(seeded_app, "SYN-0001")
    url = f"{BASE}/patients/{patient}/fhir?type=transaction"
    assert TestClient(seeded_app, headers=CSRF).get(url).status_code == 401
    assert staff(seeded_app, "patient").get(url).status_code == 403


# --- Condition und Medikation -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("pseudonym", "code"), [("SYN-0001", "C18.7"), ("SYN-0002", "C43.9"), ("SYN-0003", "C20")]
)
def test_condition_comes_from_diagnosis_code_in_both_bundle_types(
    seeded_app: FastAPI, pseudonym: str, code: str
) -> None:
    doctor, patient = staff(seeded_app), pid(seeded_app, pseudonym)
    for bundle in (export(doctor, patient), tx(doctor, patient)):
        (condition,) = resources(bundle, "Condition")
        assert condition["code"]["coding"] == [
            {"system": "http://hl7.org/fhir/sid/icd-10", "code": code}
        ]
        assert condition["clinicalStatus"]["coding"][0]["code"] == "active"
        assert condition["meta"]["tag"][0]["code"] == "synthetic"
        assert "diagnosis_text" not in json.dumps(condition)
        subject = condition["subject"]["reference"]
        assert subject.endswith(resources(bundle, "Patient")[0]["id"])


def test_patient_without_diagnosis_code_gets_no_condition(seeded_app: FastAPI) -> None:
    patient = pid(seeded_app, "SYN-0001")
    with seeded_app.state.session_factory() as session:
        row = session.get(Patient, patient)
        assert row is not None
        row.diagnosis_code = None
        session.commit()
    doctor = staff(seeded_app)
    assert resources(export(doctor, patient), "Condition") == []
    assert resources(tx(doctor, patient), "Condition") == []


def test_medication_carries_sukl_code_and_atc_when_known(seeded_app: FastAPI) -> None:
    bundle = tx(staff(seeded_app), pid(seeded_app, "SYN-0001"))
    by_atc = {}
    for med in resources(bundle, "MedicationStatement"):
        codings = med["medicationCodeableConcept"]["coding"]
        atc = next(c["code"] for c in codings if c["system"] == fhir.ATC_SYSTEM)
        by_atc[atc] = {c["system"]: c["code"] for c in codings}
    assert by_atc["L01XA03"][fhir.SUKL_SYSTEM] == "0239968"  # Oxaliplatin Accord
    assert by_atc["L01BC02"][fhir.SUKL_SYSTEM] == "0242250"  # Fluorouracil Accord
    assert fhir.SUKL_SYSTEM not in by_atc["V03AF03"]  # Entwurf ohne SÚKL-Kennung ⇒ nur ATC


# --- Push: Rechte, Guard, deaktiviert ---------------------------------------------------------


def test_push_requires_admin_and_a_known_patient(
    seeded_app: FastAPI, configured: FakeFhirServer
) -> None:
    patient = pid(seeded_app, "SYN-0001")
    assert (
        TestClient(seeded_app, headers=CSRF)
        .post(f"{BASE}/patients/{patient}/fhir/push")
        .status_code
        == 401
    )
    for username in ("doctor", "patient", "patient2", "user"):
        assert push(seeded_app, patient, username).status_code == 403
    assert push(seeded_app, str(uuid.uuid4())).status_code == 404
    assert configured.requests == []  # nichts gesendet


def test_push_without_base_url_is_disabled_not_an_error(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(fhir_push.BASE_URL_ENV, raising=False)
    patient = pid(seeded_app, "SYN-0001")
    response = push(seeded_app, patient)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disabled"
    assert body["http_status"] is None
    assert body["entries"] > 0
    assert body["created"] == body["updated"] == 0
    assert body["errors"] == []
    with seeded_app.state.session_factory() as session:
        (event,) = session.scalars(select(AuditEvent).where(AuditEvent.action == "fhir_push")).all()
    assert event.details_json == {"status": "disabled", "entries": body["entries"]}
    assert event.subject_id == patient


def test_push_refuses_a_patient_that_is_not_synthetic(
    seeded_app: FastAPI, configured: FakeFhirServer
) -> None:
    patient = pid(seeded_app, "SYN-0001")
    with seeded_app.state.session_factory() as session:
        row = session.get(Patient, patient)
        assert row is not None
        row.synthetic = False
        session.commit()
    response = push(seeded_app, patient)
    assert response.status_code == 409
    assert response.json()["code"] == "not_synthetic"
    assert configured.requests == []


# --- Push gegen den lokalen Testserver --------------------------------------------------------


def test_push_sends_the_transaction_bundle_with_headers_and_auth(
    seeded_app: FastAPI, configured: FakeFhirServer
) -> None:
    patient = pid(seeded_app, "SYN-0001")
    response = push(seeded_app, patient)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "sent"
    assert body["http_status"] == 200
    assert body["created"] == body["entries"] > 0
    assert body["updated"] == 0
    assert body["errors"] == []
    (request,) = configured.requests
    assert request["path"] == "/fhir/r4/"
    assert request["headers"]["content-type"] == "application/fhir+json"
    expected = fhir_push.PushConfig(configured.url, USER, SECRET).authorization()
    assert request["headers"]["authorization"] == expected
    sent = json.loads(request["body"])
    assert sent == tx(staff(seeded_app), patient)  # genau das exportierte Transaction-Bundle
    assert len(sent["entry"]) == body["entries"]


def test_second_push_replaces_instead_of_duplicating(
    seeded_app: FastAPI, configured: FakeFhirServer
) -> None:
    patient = pid(seeded_app, "SYN-0001")
    first = push(seeded_app, patient).json()
    stored = dict(configured.store)
    second = push(seeded_app, patient).json()
    assert (first["created"], first["updated"]) == (first["entries"], 0)
    assert (second["created"], second["updated"]) == (0, first["entries"])
    assert second["status"] == "sent"
    assert configured.store == stored  # keine Dubletten, gleicher Inhalt
    assert len(configured.store) == first["entries"]
    assert len(configured.requests) == 2


def test_push_without_credentials_sends_no_authorization_header(
    seeded_app: FastAPI, configured: FakeFhirServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(fhir_push.USER_ENV)
    monkeypatch.delenv(fhir_push.PASSWORD_ENV)
    assert push(seeded_app, pid(seeded_app, "SYN-0001")).json()["status"] == "sent"
    assert "authorization" not in configured.requests[0]["headers"]


def test_push_401_is_reported_as_failed_without_free_text_or_secrets(
    seeded_app: FastAPI, configured: FakeFhirServer
) -> None:
    configured.mode = "401"
    response = push(seeded_app, pid(seeded_app, "SYN-0001"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["http_status"] == 401
    assert body["errors"] == ["HTTP 401", "error: login"]
    assert body["created"] == body["updated"] == 0
    text = response.text
    assert "GEHEIM-PATIENTENDATEN" not in text  # kein Freitext des Servers
    assert SECRET not in text
    assert USER not in text
    assert configured.url not in text


def test_push_500_is_reported_as_failed(seeded_app: FastAPI, configured: FakeFhirServer) -> None:
    configured.mode = "500"
    body = push(seeded_app, pid(seeded_app, "SYN-0001")).json()
    assert body["status"] == "failed"
    assert body["http_status"] == 500
    assert body["errors"] == ["HTTP 500", "error: exception"]


def test_push_timeout_is_reported_as_failed(
    seeded_app: FastAPI, configured: FakeFhirServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fhir_push, "TIMEOUT_SECONDS", 0.3)
    configured.mode, configured.delay = "timeout", 1.5
    body = push(seeded_app, pid(seeded_app, "SYN-0001")).json()
    assert body["status"] == "failed"
    assert body["http_status"] is None
    assert body["errors"] == ["timeout"]


def test_push_to_a_closed_port_is_reported_as_failed(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(fhir_push.BASE_URL_ENV, "http://127.0.0.1:9/fhir/")  # Discard-Port, zu
    body = push(seeded_app, pid(seeded_app, "SYN-0001")).json()
    assert body["status"] == "failed"
    assert body["http_status"] is None
    assert body["errors"] in (["connection_failed"], ["timeout"])


def test_push_with_a_garbage_answer_is_failed(
    seeded_app: FastAPI, configured: FakeFhirServer
) -> None:
    configured.mode = "garbage"
    body = push(seeded_app, pid(seeded_app, "SYN-0001")).json()
    assert (body["status"], body["http_status"]) == ("failed", 200)
    assert body["errors"] == ["invalid_response"]


def test_push_with_a_failing_entry_is_failed_and_names_the_status(
    seeded_app: FastAPI, configured: FakeFhirServer
) -> None:
    configured.mode = "partial"
    body = push(seeded_app, pid(seeded_app, "SYN-0001")).json()
    assert body["status"] == "failed"
    assert body["errors"] == ["entry: HTTP 422"]
    assert body["created"] == body["entries"] - 1


def test_push_audit_records_status_and_count_only(
    seeded_app: FastAPI, configured: FakeFhirServer
) -> None:
    patient = pid(seeded_app, "SYN-0001")
    configured.mode = "500"
    push(seeded_app, patient)
    configured.mode = "ok"
    push(seeded_app, patient)
    with seeded_app.state.session_factory() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "fhir_push").order_by(AuditEvent.at)
        ).all()
    assert [e.details_json["status"] for e in events] == ["failed", "sent"]
    assert all(set(e.details_json) == {"status", "entries"} for e in events)
    dump = json.dumps([e.details_json for e in events])
    assert SECRET not in dump
    assert configured.url not in dump


def test_secrets_never_reach_log_or_repr(
    seeded_app: FastAPI, configured: FakeFhirServer, caplog: pytest.LogCaptureFixture
) -> None:
    config = fhir_push.config_from_env()
    assert SECRET not in repr(config)
    assert SECRET not in str(config)
    assert USER not in repr(config)
    configured.mode = "401"
    with caplog.at_level(logging.DEBUG):
        push(seeded_app, pid(seeded_app, "SYN-0001"))
    assert caplog.records
    assert SECRET not in caplog.text
    assert USER not in caplog.text
    assert configured.url not in caplog.text


# --- Konfiguration ----------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.org/", "localhost:52773"])
def test_only_http_urls_are_accepted(url: str) -> None:
    assert not fhir_push.config_from_env({fhir_push.BASE_URL_ENV: url}).enabled


def test_config_from_env_reads_the_three_variables() -> None:
    config = fhir_push.config_from_env(
        {
            fhir_push.BASE_URL_ENV: " http://localhost:52773/fhir/r4/ ",
            fhir_push.USER_ENV: "u",
            fhir_push.PASSWORD_ENV: "p",
        }
    )
    assert config.enabled
    assert config.base_url == "http://localhost:52773/fhir/r4/"
    assert config.authorization() == "Basic dTpw"
    assert not fhir_push.config_from_env({}).enabled
