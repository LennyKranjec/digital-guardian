"""A3-Gegenproben zu T-18 (FHIR Transaction-Bundle im Klinikformat, POST /fhir/push).

Eigene Prüfung des Transaction-Bundles (PUT {Typ}/{id}, stabile IDs, Referenzen Typ/id, Condition
mit ICD-10, Medication mit SÚKL + ATC) und des Push gegen einen EIGENEN lokalen Testserver. Mit
`A3_FHIR_OUT=<Ordner>` werden die Transaction-Bundles für den HAPI-Validator geschrieben.
"""
# ruff: noqa: F811

import base64
import json
import logging
import os
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from app.persistence.models import AuditEvent
from conftest import CSRF, login
from test_a3_t04a import MutableClock
from test_a3_t08 import PSEUDONYMS
from test_a3_t13 import api, real_template  # noqa: F401
from test_fhir import BASE, pid, staff, walk
from waechter.models import Patient

SEVEN = [*PSEUDONYMS, "SYN-0006", "SYN-0007"]


@pytest.fixture
def seeded_app(api: tuple[FastAPI, MutableClock]) -> FastAPI:
    """App mit dem echten Inhalt und dem echten Seed (inkl. Diagnosecode, SYN-0006/7)."""
    return api[0]


def transaction(client: TestClient, patient_id: str) -> dict[str, Any]:
    reply = client.get(f"{BASE}/patients/{patient_id}/fhir", params={"type": "transaction"})
    assert reply.status_code == 200, reply.text
    body: dict[str, Any] = reply.json()
    return body


def references(node: Any) -> list[str]:
    found: list[str] = []
    for value in walk(node):
        if isinstance(value, dict) and isinstance(value.get("reference"), str):
            found.append(value["reference"])
    return found


@pytest.mark.parametrize("pseudonym", SEVEN)
def test_a3_transaction_bundle_has_the_clinic_format(seeded_app: FastAPI, pseudonym: str) -> None:
    doctor = staff(seeded_app)
    try:
        patient = pid(seeded_app, pseudonym)
    except NoResultFound:  # Seed ohne SYN-0006/7 (älterer Stand)
        pytest.skip(f"{pseudonym} nicht im Seed")
    bundle = transaction(doctor, patient)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "transaction"
    entries = bundle["entry"]
    assert entries
    ids: set[str] = set()
    keys: set[str] = set()
    for entry in entries:
        resource = entry["resource"]
        kind, rid = resource["resourceType"], resource["id"]
        assert entry["request"] == {"method": "PUT", "url": f"{kind}/{rid}"}, entry["request"]
        assert entry["fullUrl"] == f"urn:uuid:{rid}"
        assert rid not in ids, f"Ressourcen-ID doppelt: {rid}"
        ids.add(rid)
        keys.add(f"{kind}/{rid}")
    # Referenzen im Klinikformat Typ/id, alle im Bundle aufgelöst, nie urn:uuid
    dangling = [r for r in references(entries) if r.startswith("urn:") or r not in keys]
    assert dangling == [], dangling[:5]
    kinds = {e["resource"]["resourceType"] for e in entries}
    assert {"Patient", "Condition"} <= kinds
    patients = [e["resource"] for e in entries if e["resource"]["resourceType"] == "Patient"]
    assert len(patients) == 1
    assert "name" not in patients[0]  # Pseudonym, kein Klarname
    assert any(i.get("value") == pseudonym for i in patients[0].get("identifier", []))
    for entry in entries:
        resource = entry["resource"]
        if resource["resourceType"] == "Condition":
            codings = [c for cc in [resource["code"]] for c in cc.get("coding", [])]
            assert any("icd-10" in c.get("system", "").lower() for c in codings), codings
        if resource["resourceType"] == "Medication":
            systems = " ".join(c["system"] for c in resource["code"]["coding"]).lower()
            assert "sukl" in systems or "atc" in systems, systems
    out = os.environ.get("A3_FHIR_OUT")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / f"txn-{pseudonym.lower()}.json").write_text(json.dumps(bundle), "utf-8")
        collection = doctor.get(f"{BASE}/patients/{patient}/fhir").json()
        assert collection["type"] == "collection"
        (Path(out) / f"col-{pseudonym.lower()}.json").write_text(json.dumps(collection), "utf-8")


def test_a3_transaction_ids_are_stable_across_calls(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    patient = pid(seeded_app, "SYN-0001")
    first, second = transaction(doctor, patient), transaction(doctor, patient)

    def ids(bundle: dict[str, Any]) -> list[str]:
        return sorted(e["request"]["url"] for e in bundle["entry"])

    assert ids(first) == ids(second), "IDs ändern sich zwischen zwei Abrufen"


# --- Push gegen einen eigenen Testserver ---------------------------------------------------


class Recorder:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.mode = "ok"


@pytest.fixture
def fhir_server() -> Iterator[tuple[str, Recorder]]:
    recorder = Recorder()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            recorder.requests.append(
                {"auth": self.headers.get("Authorization"),
                 "ctype": self.headers.get("Content-Type"),
                 "bundle": body}
            )  # fmt: skip
            if recorder.mode == "401":
                self.send_response(401)
                self.end_headers()
                return
            if recorder.mode == "500":
                payload = json.dumps(
                    {
                        "resourceType": "OperationOutcome",
                        "issue": [{"severity": "error", "code": "exception"}],
                    }
                ).encode()
                self.send_response(500)
            elif recorder.mode == "garbage":
                payload = b"<html>not json</html>"
                self.send_response(200)
            else:
                entries = [
                    {"response": {"status": "201 Created" if i % 2 == 0 else "200 OK"}}
                    for i, _ in enumerate(body["entry"])
                ]
                payload = json.dumps(
                    {"resourceType": "Bundle", "type": "transaction-response", "entry": entries}
                ).encode()
                self.send_response(200)
            self.send_header("Content-Type", "application/fhir+json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/fhir", recorder
    finally:
        server.shutdown()
        server.server_close()


def push(client: TestClient, patient: str) -> Any:
    return client.post(f"{BASE}/patients/{patient}/fhir/push")


def test_a3_push_is_admin_only_and_disabled_without_a_server(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WAECHTER_FHIR_BASE_URL", raising=False)
    patient = pid(seeded_app, "SYN-0001")
    admin = staff(seeded_app, "admin")
    assert push(admin, patient).json()["status"] == "disabled"
    assert push(staff(seeded_app, "doctor"), patient).status_code == 403
    patient_client = TestClient(seeded_app, headers=CSRF)
    login(patient_client, "patient2")
    assert push(patient_client, patient).status_code in (401, 403)
    assert push(TestClient(seeded_app, headers=CSRF), patient).status_code == 401


def test_a3_push_sends_each_resource_once_with_credentials_and_repeats_without_duplicates(
    seeded_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    fhir_server: tuple[str, Recorder],
    caplog: pytest.LogCaptureFixture,
) -> None:
    url, recorder = fhir_server
    monkeypatch.setenv("WAECHTER_FHIR_BASE_URL", url)
    monkeypatch.setenv("WAECHTER_FHIR_USER", "a3user")
    monkeypatch.setenv("WAECHTER_FHIR_PASSWORD", "geheim-a3-passwort")
    caplog.set_level(logging.DEBUG)
    patient = pid(seeded_app, "SYN-0001")
    admin = staff(seeded_app, "admin")
    first = push(admin, patient)
    second = push(admin, patient)
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "sent"
    assert body["entries"] == len(recorder.requests[0]["bundle"]["entry"])
    assert body["created"] + body["updated"] == body["entries"]
    assert second.json()["status"] == "sent"
    assert len(recorder.requests) == 2
    assert recorder.requests[0]["ctype"].startswith("application/fhir+json")
    token = base64.b64encode(b"a3user:geheim-a3-passwort").decode()
    assert recorder.requests[0]["auth"] == f"Basic {token}"
    urls = [sorted(e["request"]["url"] for e in r["bundle"]["entry"]) for r in recorder.requests]
    assert urls[0] == urls[1], "zweiter Push mit anderen Ressourcen-IDs ⇒ Dubletten auf dem Server"
    # Zugangsdaten und Bundle-Inhalt weder in Antwort noch in Log noch im Audit
    assert "geheim-a3-passwort" not in first.text
    assert "geheim-a3-passwort" not in caplog.text
    assert "a3user" not in caplog.text
    with seeded_app.state.session_factory() as session:
        events = list(session.scalars(select(AuditEvent).where(AuditEvent.action == "fhir_push")))
    assert len(events) >= 2
    blob = " ".join(str(e.details_json) for e in events)
    assert "geheim" not in blob
    assert "SYN-0001" not in blob


@pytest.mark.parametrize(
    ("mode", "status"), [("401", "failed"), ("500", "failed"), ("garbage", "failed")]
)
def test_a3_push_turns_every_server_failure_into_failed_without_a_stacktrace(
    seeded_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    fhir_server: tuple[str, Recorder],
    mode: str,
    status: str,
) -> None:
    url, recorder = fhir_server
    recorder.mode = mode
    monkeypatch.setenv("WAECHTER_FHIR_BASE_URL", url)
    reply = push(staff(seeded_app, "admin"), pid(seeded_app, "SYN-0001"))
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["status"] == status
    assert "Traceback" not in reply.text
    for error in body.get("errors", []):
        assert len(error) < 200
        assert "SYN-" not in error


def test_a3_push_refuses_non_synthetic_patients_without_contacting_the_server(
    seeded_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    fhir_server: tuple[str, Recorder],
) -> None:
    url, recorder = fhir_server
    monkeypatch.setenv("WAECHTER_FHIR_BASE_URL", url)
    patient = pid(seeded_app, "SYN-0001")
    with seeded_app.state.session_factory() as session:
        row = session.get(Patient, patient)
        assert row is not None
        row.synthetic = False
        session.commit()
    try:
        reply = push(staff(seeded_app, "admin"), patient)
        assert reply.status_code == 409
        assert reply.json()["code"] == "not_synthetic"
        assert recorder.requests == []
    finally:
        with seeded_app.state.session_factory() as session:
            row = session.get(Patient, patient)
            assert row is not None
            row.synthetic = True
            session.commit()


def test_a3_push_to_an_unreachable_server_is_failed_not_an_error(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WAECHTER_FHIR_BASE_URL", "http://127.0.0.1:9/fhir")
    reply = push(staff(seeded_app, "admin"), pid(seeded_app, "SYN-0001"))
    assert reply.status_code == 200
    assert reply.json()["status"] == "failed"
    assert reply.json()["errors"]
