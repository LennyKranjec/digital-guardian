"""Vertragsprobe Frontend ↔ Backend (F-INT): echte Antworten als Fixtures für die Frontend-Schemas.

Der Test fährt den echten Inhalt (`challenge/content/`) mit eingefrorener Uhr durch alle Endpunkte,
die das Frontend nutzt, und vergleicht die Antworten mit den eingecheckten Fixtures unter
`challenge/frontend/waechter/api/__fixtures__/`. Ein Vitest (`api/contract.test.ts`) parst jede
Fixture durch das zod-Schema des Frontends.

- Normalfall: Vergleich ⇒ rot, sobald sich das Backend-Format ändert (Frontend dann nachziehen).
- Neu schreiben: `WAECHTER_WRITE_FIXTURES=1` setzen (z. B. nach einer bewussten Backend-Änderung),
  danach `npx prettier --write challenge/frontend` (der Vergleich ignoriert die Formatierung).

Ids (UUIDs) werden in Reihenfolge des Auftretens durch feste Platzhalter ersetzt, damit die Dateien
reproduzierbar bleiben. Besitz A2b; ändert keine Backend-Datei.
"""

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.services import seed
from conftest import CSRF, login, make_settings, migrate
from waechter.constants import CONTENT_DIR_ENV
from waechter.models import Patient

CHALLENGE = Path(__file__).resolve().parents[1]
REAL_CONTENT = CHALLENGE / "content"
FIXTURE_DIR = CHALLENGE / "frontend" / "waechter" / "api" / "__fixtures__"
WRITE = os.environ.get("WAECHTER_WRITE_FIXTURES") == "1"

API = "/api/v1"
BASE = f"{API}/waechter"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
#: SHA-256-Prüfsummen (z. B. `facts_hash`) hängen von internen Zeilenkennungen ab und schwanken
SHA256_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")

#: feste Einsende-Kennungen der Probe (reproduzierbar)
CSID_ASSESSMENT = "11111111-1111-4111-8111-111111111111"
CSID_ASSESSMENT_BAD = "22222222-2222-4222-8222-222222222222"
CSID_RESPONSE = "33333333-3333-4333-8333-333333333333"
CSID_FOLLOWUP = "44444444-4444-4444-8444-444444444444"


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Überschreibt die Fixture-Welt der Backend-Tests mit dem echten Inhalt."""
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL_CONTENT))
    return REAL_CONTENT


@pytest.fixture
def real_app(tmp_path: Path) -> Any:
    settings = make_settings(tmp_path)
    migrate(settings)
    app = create_app(settings)
    with app.state.session_factory() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
        session.commit()
    yield app
    app.state.engine.dispose()


class Recorder:
    """Sammelt (Anfrage, Status, Körper) je Fixture-Name in fester Reihenfolge."""

    def __init__(self) -> None:
        self.entries: dict[str, dict[str, Any]] = {}

    def record(self, name: str, method: str, path: str, response: Any) -> Any:
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text
        self.entries[name] = {
            "request": f"{method} {path}",
            "status": response.status_code,
            "body": body,
        }
        return body

    def get(self, client: TestClient, name: str, path: str) -> Any:
        return self.record(name, "GET", path, client.get(path))

    def post(
        self,
        client: TestClient,
        name: str,
        path: str,
        payload: dict[str, Any],
        method: str = "POST",
    ) -> Any:
        return self.record(name, method, path, client.request(method, path, json=payload))


def staff(app: FastAPI) -> TestClient:
    client = TestClient(app, headers=CSRF)
    login(client, "doctor")
    return client


def patient_client(app: FastAPI, username: str) -> TestClient:
    client = TestClient(app, headers=CSRF)
    login(client, username)
    return client


def _mask_attachments(value: Any) -> Any:
    """Ersetzt `attachment.data` (base64) durch einen festen Platzhalter, rekursiv."""
    if isinstance(value, dict):
        return {
            k: (
                {**v, "data": "<base64>"}
                if k == "attachment" and isinstance(v, dict) and "data" in v
                else _mask_attachments(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask_attachments(v) for v in value]
    return value


def normalize(entries: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Serialisiert jede Fixture (stabil) und ersetzt UUIDs durch feste Platzhalter."""
    mapping: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        found = match.group(0)
        if found not in mapping:
            mapping[found] = f"00000000-0000-4000-8000-{len(mapping) + 1:012d}"
        return mapping[found]

    # feste Einsende-Kennungen der Probe bleiben lesbar und gleich
    keep = {CSID_ASSESSMENT, CSID_ASSESSMENT_BAD, CSID_RESPONSE, CSID_FOLLOWUP}
    for csid in keep:
        mapping[csid] = csid

    result: dict[str, str] = {}
    for name, entry in entries.items():
        # base64-Anhänge (FHIR) enthalten UUIDs, die der Ersatz nicht sieht (int/3)
        text = json.dumps(_mask_attachments(entry), ensure_ascii=False, indent=2, sort_keys=False)
        result[name] = SHA256_RE.sub("0" * 64, UUID_RE.sub(replace, text)) + "\n"
    return result


def first_term_with_undefined_grade(template: dict[str, Any]) -> tuple[str, int] | None:
    """Ein Begriff der Vorlage und ein nicht definierter Grad 1 bis 5 (für den 422-Fall)."""
    for term in template["terms"]:
        for grade in range(1, 6):
            if str(grade) not in term["grades"]:
                return term["ctcae_term_id"], grade
    return None


def collect(app: FastAPI) -> dict[str, dict[str, Any]]:
    rec = Recorder()
    doctor = staff(app)

    rec.get(doctor, "meta", f"{API}/meta")
    worklist = rec.get(doctor, "worklist", f"{BASE}/patients?lang=de")
    # Fixture-Patientinnen per Pseudonym, nicht per Reihenfolge der Arbeitsliste (T-20b F-01):
    # SYN-0001 = rote Demo-Patientin mit Kurzfassung und Verlauf, SYN-0003 = ruhige Patientin
    by_pseudonym = {row["pseudonym"]: row for row in worklist}
    red = by_pseudonym["SYN-0001"]
    quiet = by_pseudonym["SYN-0003"]
    assert red["traffic_light"] == "red"
    assert quiet["traffic_light"] != "red"
    pid = red["patient_id"]
    qid = quiet["patient_id"]

    overview = rec.get(doctor, "overview_red", f"{BASE}/patients/{pid}/overview?lang=de")
    rec.get(doctor, "overview_quiet", f"{BASE}/patients/{qid}/overview?lang=de")
    timeline = rec.get(doctor, "timeline_all", f"{BASE}/patients/{pid}/timeline?lang=de")
    last_visit = overview.get("last_visit_at")
    if last_visit:
        rec.get(
            doctor,
            "timeline_from_last_visit",
            f"{BASE}/patients/{pid}/timeline?lang=de&from={last_visit.replace('+', '%2B')}",
        )
    rec.get(doctor, "alerts_list", f"{BASE}/patients/{pid}/alerts?lang=de&status=all")
    open_alerts = overview["open_alerts"]
    rec.get(doctor, "alert_detail", f"{BASE}/alerts/{open_alerts[0]['alert_id']}?lang=de")
    rec.get(doctor, "notifications", f"{BASE}/notifications")
    rec.get(doctor, "config", f"{BASE}/config?lang=de")
    rec.get(doctor, "summary_none", f"{BASE}/patients/{pid}/summary")
    rec.post(doctor, "summary_created", f"{BASE}/patients/{pid}/summary", {})
    rec.get(doctor, "summary_latest", f"{BASE}/patients/{pid}/summary")
    rec.get(doctor, "overview_with_summary", f"{BASE}/patients/{pid}/overview?lang=de")
    rec.get(doctor, "audit", f"{BASE}/patients/{pid}/audit")
    rec.get(doctor, "fhir_bundle", f"{BASE}/patients/{pid}/fhir")

    # Belege: je Präfix ein Beispiel aus den Antworten selbst
    evidence = [e for alert in open_alerts for e in alert["explanation"]["evidence"]]
    fact_ids: dict[str, str] = {}
    for fact_id in [
        *evidence,
        *(p["fact_id"] for s in timeline["series"] for p in s["points"]),
        *(v["fact_id"] for v in timeline["visits"] if v.get("fact_id")),
        overview["therapy"]["fact_id"],
        f"alert-{open_alerts[0]['alert_id']}",
    ]:
        fact_ids.setdefault(fact_id.split("-", 1)[0], fact_id)
    for prefix, fact_id in fact_ids.items():
        rec.get(doctor, f"fact_{prefix}", f"{BASE}/patients/{pid}/facts/{fact_id}?lang=de")
    rec.get(doctor, "fact_not_found", f"{BASE}/patients/{pid}/facts/obs-does-not-exist?lang=de")

    # Aufnahme: Vorlage, gültig speichern, Wiederholung, Fehlerfälle, Beleg, Verlauf danach
    template = rec.get(
        doctor, "assessment_template", f"{BASE}/patients/{pid}/assessment-template?lang=de"
    )
    terms = template["terms"]
    related = [alert["alert_id"] for alert in open_alerts]
    created = rec.post(
        doctor,
        "assessment_created",
        f"{BASE}/patients/{pid}/assessments",
        {
            "client_submission_id": CSID_ASSESSMENT,
            "related_alert_ids": related,
            "items": [
                {
                    "ctcae_term_id": terms[0]["ctcae_term_id"],
                    "grade": 1,
                    "attribution": "possible",
                    "note": "Kontrolle",
                },
                {"ctcae_term_id": terms[1]["ctcae_term_id"], "grade": 0},
            ],
        },
    )
    rec.post(
        doctor,
        "assessment_replay",
        f"{BASE}/patients/{pid}/assessments",
        {
            "client_submission_id": CSID_ASSESSMENT,
            "related_alert_ids": related,
            "items": [
                {
                    "ctcae_term_id": terms[0]["ctcae_term_id"],
                    "grade": 1,
                    "attribution": "possible",
                    "note": "Kontrolle",
                },
                {"ctcae_term_id": terms[1]["ctcae_term_id"], "grade": 0},
            ],
        },
    )
    undefined = first_term_with_undefined_grade(template)
    assert undefined is not None, "Vorlage ohne undefinierten Grad: Fehlerfall nicht erzeugbar"
    rec.post(
        doctor,
        "assessment_invalid",
        f"{BASE}/patients/{pid}/assessments",
        {
            "client_submission_id": CSID_ASSESSMENT_BAD,
            "related_alert_ids": [],
            "items": [
                {"ctcae_term_id": "CTCAE-NOT-IN-SUBSPACE", "grade": 1},
                {"ctcae_term_id": undefined[0], "grade": undefined[1]},
                {"ctcae_term_id": undefined[0], "grade": 0},
            ],
        },
    )
    other_alert = foreign_alert_id(doctor, pid, worklist)
    if other_alert:
        rec.post(
            doctor,
            "assessment_foreign_alert",
            f"{BASE}/patients/{pid}/assessments",
            {
                "client_submission_id": CSID_ASSESSMENT_BAD,
                "related_alert_ids": [other_alert],
                "items": [{"ctcae_term_id": terms[0]["ctcae_term_id"], "grade": 0}],
            },
        )
    rec.get(doctor, "assessments_list", f"{BASE}/patients/{pid}/assessments")
    rec.get(doctor, "fact_assess", f"{BASE}/patients/{pid}/facts/{created['fact_id']}?lang=de")
    rec.get(doctor, "timeline_after_assessment", f"{BASE}/patients/{pid}/timeline?lang=de")

    # Quittieren: 200, erneut ⇒ 409, unbekannt ⇒ 404, ungültige Entscheidung ⇒ 422
    target = open_alerts[0]["alert_id"]
    rec.post(
        doctor,
        "acknowledge_ok",
        f"{BASE}/alerts/{target}/acknowledge?lang=de",
        {"decision": "contact_patient", "note": "Patientin angerufen"},
    )
    rec.post(
        doctor,
        "acknowledge_conflict",
        f"{BASE}/alerts/{target}/acknowledge?lang=de",
        {"decision": "other"},
    )
    rec.post(
        doctor,
        "acknowledge_not_found",
        f"{BASE}/alerts/does-not-exist/acknowledge?lang=de",
        {"decision": "other"},
    )
    rec.post(
        doctor,
        "acknowledge_invalid",
        f"{BASE}/alerts/{target}/acknowledge?lang=de",
        {"decision": "heilen"},
    )
    rec.get(doctor, "overview_after_acknowledge", f"{BASE}/patients/{pid}/overview?lang=de")
    rec.get(doctor, "alert_after_acknowledge", f"{BASE}/alerts/{target}?lang=de")

    # Patientin: Fragebogen, Senden, Wiederholung, Fehlerfälle
    patient = patient_client(app, "patient2")
    questionnaire = rec.get(patient, "questionnaire", f"{BASE}/me/questionnaire?lang=de")
    answers = [
        {
            "symptom_key": item["symptom_key"],
            "attribute": item["questions"][0]["attribute"],
            "value": None,
        }
        for item in questionnaire["items"][:2]
    ]
    submit = {
        "client_submission_id": CSID_RESPONSE,
        "questionnaire_id": questionnaire["questionnaire_id"],
        "answers": answers,
    }
    created = rec.post(patient, "response_created", f"{BASE}/me/responses", submit)
    rec.post(patient, "response_replay", f"{BASE}/me/responses", submit)
    collect_free_text(app, rec, patient, doctor, worklist, created["response_id"])
    rec.post(
        patient,
        "response_conflict",
        f"{BASE}/me/responses",
        {**submit, "answers": [{**answers[0], "value": 0}]},
    )
    rec.post(
        patient,
        "response_invalid",
        f"{BASE}/me/responses",
        {
            **submit,
            "client_submission_id": CSID_ASSESSMENT_BAD,
            "answers": [{**answers[0], "value": 9}],
        },
    )
    rec.get(patient, "my_responses", f"{BASE}/me/responses")
    collect_config_changes(app, rec)
    return rec.entries


def collect_free_text(
    app: FastAPI,
    rec: Recorder,
    patient: TestClient,
    doctor: TestClient,
    worklist: list[dict[str, Any]],
    response_id: str,
) -> None:
    """Freitext (T-22): Speichern, Folgefragen, Fehlerfälle, Antwort, Liste, Beleg."""
    text = "Mám PRŮJEM, bolí mě to a nemůžu dýchat"
    payload = {"response_id": response_id, "text": text}
    created = rec.post(patient, "free_text_created", f"{BASE}/me/free-text", payload)
    rec.post(patient, "free_text_replay", f"{BASE}/me/free-text", payload)
    rec.post(patient, "free_text_conflict", f"{BASE}/me/free-text", {**payload, "text": "jiný"})
    rec.post(patient, "free_text_invalid", f"{BASE}/me/free-text", {**payload, "text": "x" * 2001})
    pid = next(r["patient_id"] for r in worklist if r["pseudonym"] == "SYN-0002")
    rec.get(doctor, "free_texts_list_unconfirmed", f"{BASE}/patients/{pid}/free-texts?lang=de")
    rec.get(doctor, "worklist_free_text", f"{BASE}/patients?lang=de")
    cards = rec.get(patient, "free_text_followups", f"{BASE}/me/free-text/followups?lang=de")
    card = cards[0]
    rec.post(
        patient,
        "free_text_answered",
        f"{BASE}/me/free-text/{card['free_text_id']}/answers",
        {
            "client_submission_id": CSID_FOLLOWUP,
            "answers": [
                {"symptom_key": card["symptom_key"], "attribute": q["attribute"], "value": 0}
                for q in card["questions"]
            ],
        },
    )
    rec.get(doctor, "free_texts_list", f"{BASE}/patients/{pid}/free-texts?lang=de")
    rec.get(
        doctor,
        "fact_free_text",
        f"{BASE}/patients/{pid}/facts/ft-{created['free_text_id']}?lang=de",
    )


def collect_config_changes(app: FastAPI, rec: Recorder) -> None:
    """Einstellungen: Änderung durch die Administration und alle Fehlerfälle (T-09, DR-014/016)."""
    admin = TestClient(app, headers=CSRF)
    login(admin, "admin")
    bundle = rec.get(admin, "config_admin", f"{BASE}/config?lang=de")
    rules_doc = {k: v for k, v in bundle["rules"].items() if k != "version"}
    rules_version = bundle["rules"]["version"]
    report_doc = {k: v for k, v in bundle["report"].items() if k != "version"}
    report_version = bundle["report"]["version"]
    url_rules = f"{BASE}/config/rules"
    url_report = f"{BASE}/config/report"

    def with_rules(change: Any) -> dict[str, Any]:
        document = json.loads(json.dumps(rules_doc))
        change(document)
        return {"expected_version": rules_version, "rules": document, "change_note": "Probe"}

    # Rolle: Ärztin darf nicht ändern
    rec.post(staff(app), "rules_forbidden", url_rules, with_rules(lambda d: None), method="PUT")

    # Fehlerfälle (ändern nichts)
    def all_red_off(document: dict[str, Any]) -> None:
        for rule in document["rules"]:
            if rule["level"] == "red":
                rule["enabled"] = False

    rec.post(admin, "rules_no_red_rule", url_rules, with_rules(all_red_off), method="PUT")
    rec.post(
        admin,
        "rules_no_red_notification",
        url_rules,
        with_rules(lambda d: d["noise"].__setitem__("notify_levels", ["yellow"])),
        method="PUT",
    )

    def negative_param(document: dict[str, Any]) -> None:
        rule = document["rules"][0]
        name = next(iter(rule["params"]))
        rule["params"][name] = -1

    rec.post(admin, "rules_invalid", url_rules, with_rules(negative_param), method="PUT")
    stale = with_rules(lambda d: None)
    stale["expected_version"] = "rules-v0"
    rec.post(admin, "rules_conflict", url_rules, stale, method="PUT")
    rec.post(
        admin,
        "report_invalid",
        url_report,
        {"expected_version": report_version, "report": {"sections": ["gibt-es-nicht"]}},
        method="PUT",
    )

    # Erfolg: neue Regelversion (Parameter der ersten Regel geringfügig geändert) und neuer Bericht
    def tweak(document: dict[str, Any]) -> None:
        rule = document["rules"][0]
        name = next(iter(rule["params"]))
        rule["params"][name] = rule["params"][name]

    rec.post(admin, "rules_updated", url_rules, with_rules(tweak), method="PUT")
    sections = [x for x in report_doc["sections"] if x != "audit"]
    rec.post(
        admin,
        "report_updated",
        url_report,
        {
            "expected_version": report_version,
            "report": {"since": "days_14", "sections": sections},
            "change_note": "ohne Audit",
        },
        method="PUT",
    )
    rec.get(admin, "config_updated", f"{BASE}/config?lang=de")
    rec.get(admin, "config_history_rules", f"{BASE}/config/history?kind=rules&lang=de")
    rec.get(admin, "config_history_report", f"{BASE}/config/history?kind=report&lang=de")


def foreign_alert_id(
    client: TestClient, own_patient_id: str, worklist: list[dict[str, Any]]
) -> str | None:
    """Offene Meldung einer anderen Patientin (Fehlerfall `foreign_alert`), falls vorhanden."""
    for row in worklist:
        if row["patient_id"] == own_patient_id or row["open_alerts"] == 0:
            continue
        other = client.get(f"{BASE}/patients/{row['patient_id']}/overview?lang=de").json()
        if other["open_alerts"]:
            return str(other["open_alerts"][0]["alert_id"])
    return None


def same_json(name: str, generated_text: str) -> bool:
    """Gleicher Inhalt wie die eingecheckte Fixture (Formatierung egal, Prettier ändert sie)."""
    path = FIXTURE_DIR / f"{name}.json"
    if not path.is_file():
        return False
    return bool(json.loads(path.read_text(encoding="utf-8")) == json.loads(generated_text))


def test_frontend_fixtures_match_real_backend(real_app: FastAPI, tmp_path: Path) -> None:
    generated = normalize(collect(real_app))
    assert len(generated) >= 30

    if WRITE:
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        for stale in FIXTURE_DIR.glob("*.json"):
            if stale.stem not in generated:
                stale.unlink()
        for name, text in generated.items():
            (FIXTURE_DIR / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")
        return

    drift = [name for name, text in generated.items() if not same_json(name, text)]
    extra = sorted(p.stem for p in FIXTURE_DIR.glob("*.json") if p.stem not in generated)
    if drift:
        # aktuelle Antworten zum Vergleichen ablegen (z. B. mit `diff -r`)
        current = tmp_path / "current"
        current.mkdir()
        for name in drift:
            (current / f"{name}.json").write_text(generated[name], encoding="utf-8", newline="\n")
    hint = (
        "Fixtures weichen vom Backend ab (neu schreiben mit WAECHTER_WRITE_FIXTURES=1 und das "
        f"Frontend nachziehen; aktuelle Antworten unter {tmp_path / 'current'})"
    )
    assert not drift, f"{hint}: geändert/fehlend={drift}"
    assert not extra, f"{hint}: überzählig={extra}"


def test_patient_pseudonyms_in_probe_exist(real_app: FastAPI) -> None:
    """Die Probe setzt die Demo-Geschichte voraus (SYN-0001 rot am Anker, G-08)."""
    with real_app.state.session_factory() as session:
        pseudonyms = set(session.scalars(select(Patient.pseudonym)))
    assert {"SYN-0001", "SYN-0002"} <= pseudonyms
