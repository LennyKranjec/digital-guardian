"""A3: erzeugt echte API-Antworten (Backend + echter Inhalt) als JSON für die Vertragsprüfung.

    platform/backend/.venv/Scripts/python.exe docs/verification/tools/openapi_samples.py <ausgabe.json>
Danach (Referenz-venv mit jsonschema/pyyaml): python docs/verification/tools/openapi_check.py <ausgabe.json>
"""

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "challenge" / "backend"))
os.environ["WAECHTER_CONTENT_DIR"] = str(ROOT / "challenge" / "content")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.services import seed  # noqa: E402
from conftest import CSRF, login, make_settings, migrate  # noqa: E402

BASE = "/api/v1/waechter"
samples: dict[str, list[object]] = {}


def add(schema: str, instance: object) -> None:
    samples.setdefault(schema, []).append(instance)


def main() -> None:
    settings = make_settings(Path(tempfile.mkdtemp()))
    migrate(settings)
    app = create_app(settings)
    with app.state.session_factory() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
        session.commit()
    with TestClient(app, headers=CSRF) as patient, TestClient(app, headers=CSRF) as doctor:
        login(patient, "patient2")
        login(doctor, "doctor")
        for lang in ("cs", "en", "de"):
            add("Questionnaire", patient.get(f"{BASE}/me/questionnaire", params={"lang": lang}).json())
        q = patient.get(f"{BASE}/me/questionnaire").json()
        body = {
            "client_submission_id": str(uuid.uuid4()),
            "questionnaire_id": q["questionnaire_id"],
            "answers": [
                {"symptom_key": "fever", "attribute": "presence", "value": 1},
                {"symptom_key": "fatigue", "attribute": "severity", "value": None},
            ],
        }
        add("SubmitReceipt", patient.post(f"{BASE}/me/responses", json=body).json())  # 201
        add("SubmitReceipt", patient.post(f"{BASE}/me/responses", json=body).json())  # 200 Replay
        for record in patient.get(f"{BASE}/me/responses").json():
            add("ResponseRecord", record)
        for patient_row in (doctor.get(f"{BASE}/config").json(),):
            add("ConfigBundle", patient_row)
        me = patient.get("/api/v1/auth/me").json()["subject_id"]
        for status in ("all", "open"):
            for alert in doctor.get(f"{BASE}/patients/{me}/alerts", params={"status": status}).json():
                add("Alert", alert)
        ids = [a["alert_id"] for a in doctor.get(f"{BASE}/patients/{me}/alerts").json()]
        for alert_id in ids:
            add("Alert", doctor.get(f"{BASE}/alerts/{alert_id}", params={"lang": "en"}).json())
        acked = doctor.post(f"{BASE}/alerts/{ids[0]}/acknowledge", json={"decision": "other", "note": "n"})
        add("Alert", acked.json())
        add("Error", doctor.post(f"{BASE}/alerts/{ids[0]}/acknowledge", json={"decision": "other"}).json())  # 409
        add("Error", doctor.post(f"{BASE}/alerts/{ids[0]}/acknowledge", json={"decision": "x"}).json())  # 422
        add("Error", doctor.get(f"{BASE}/alerts/unknown").json())  # 404
        add("Error", patient.get(f"{BASE}/notifications").json())  # 403
        add("Error", patient.post(f"{BASE}/me/responses", json={**body, "answers": []}).json())  # 422
        for note in doctor.get(f"{BASE}/notifications").json():
            add("Notification", note)
        # T-05: Arbeitsliste, Übersicht, Verlauf, Belege
        for row in doctor.get(f"{BASE}/patients").json():
            add("WorklistRow", row)
        rows = {r["pseudonym"]: r["patient_id"] for r in doctor.get(f"{BASE}/patients").json()}
        for pseudonym, patient_id in rows.items():
            overview = doctor.get(f"{BASE}/patients/{patient_id}/overview")
            add("Overview", overview.json())
            timeline = doctor.get(f"{BASE}/patients/{patient_id}/timeline").json()
            add("Timeline", timeline)
            fact_ids = {p["fact_id"] for s in timeline["series"] for p in s["points"]}
            fact_ids |= {a["alert_id"] and f"alert-{a['alert_id']}" for a in timeline["alerts"]}
            fact_ids |= {v["fact_id"] for v in timeline["visits"]}
            fact_ids |= {e["fact_id"] for e in timeline["therapy_events"]}
            for fact_id in sorted(fact_ids)[:40]:
                add("Fact", doctor.get(f"{BASE}/patients/{patient_id}/facts/{fact_id}").json())
        # T-06: Vorlage und Aufnahme
        template = doctor.get(f"{BASE}/patients/{me}/assessment-template").json()
        add("AssessmentTemplate", template)
        term = template["terms"][0]
        grade = int(sorted(term["grades"])[0])
        created = doctor.post(
            f"{BASE}/patients/{me}/assessments",
            json={
                "client_submission_id": str(uuid.uuid4()),
                "related_alert_ids": ids[:1],
                "items": [{"ctcae_term_id": term["ctcae_term_id"], "grade": grade, "note": "n"}],
            },
        )
        add("Assessment", created.json())
        for assessment in doctor.get(f"{BASE}/patients/{me}/assessments").json():
            add("Assessment", assessment)
        add("Error", doctor.post(f"{BASE}/patients/{me}/assessments", json={"items": []}).json())
    Path(sys.argv[1]).write_text(json.dumps(samples, ensure_ascii=False, indent=1), encoding="utf-8")
    print({k: len(v) for k, v in samples.items()})


main()
