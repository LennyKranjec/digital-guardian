"""T-16 (Vertrag v2.0/v2.5): Triage-Entscheidung je Antwort, Meldungen, Befundkarte, Regelkarte."""
# feste Seeds, keine Kryptografie

import uuid
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, inspect, select

from app.persistence.models import AuditEvent
from conftest import login
from test_a3_t04a import MutableClock
from test_t13_clinic import assert_patient_safe
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import get_content
from waechter.models import (
    Alert,
    AlertAction,
    Answer,
    CheckinSession,
    Notification,
    Patient,
    PatientRegimen,
    Response,
    TriageDecision,
)
from waechter.services import triage
from waechter.services.triage import RULE_RED, RULE_YELLOW
from waechter.triage.kb import KnowledgeBase
from waechter.triage.runtime import runtime_for

REAL = Path(__file__).resolve().parents[1] / "content"
BASE = "/api/v1/waechter"
CLASS_MODULE_PROFILES = ("COMBO_ICI_TKI",)  # T-24: Module je Wirkstoffklasse (PoC, kein Regime)
ALL_LEAVES = (
    "FOLFOX",
    "CAPECITABINE",
    "DOCETAXEL",
    "PEMBROLIZUMAB",
    "ENZALUTAMIDE",
    "ABIRATERONE",
    "PAZOPANIB",
    "NIVOLUMAB",
)
LARGE_RAW_GRID = ("PAZOPANIB", "NIVOLUMAB")  # Rohgitter 8,4 bzw. 2,1 Mio. Punkte > 1 Mio.
RESPONSES = f"{BASE}/me/responses"
QUESTIONNAIRE = f"{BASE}/me/questionnaire"


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


def app_of(client: TestClient) -> FastAPI:
    application = client.app
    assert isinstance(application, FastAPI)
    return application


def tick(app: FastAPI, minutes: int = 10) -> None:
    """Lässt die Uhr der Anwendung vorrücken (die Standarduhr der Tests steht still)."""
    clock = app.state.clock
    if not isinstance(clock, MutableClock):
        clock = MutableClock(clock.now())
        app.state.clock = clock
    clock.instant += timedelta(minutes=minutes)


def clear_history(app: FastAPI, pseudonym: str) -> str:
    """Löscht Verlauf, Meldungen und Entscheidungen der Patientin (isolierter Ausgangszustand)."""
    with app.state.session_factory() as session:
        patient_id = session.scalars(select(Patient.id).where(Patient.pseudonym == pseudonym)).one()
        alert_ids = select(Alert.id).where(Alert.patient_id == patient_id)
        response_ids = select(Response.id).where(Response.patient_id == patient_id)
        session.execute(delete(AlertAction).where(AlertAction.alert_id.in_(alert_ids)))
        session.execute(delete(Notification).where(Notification.patient_id == patient_id))
        session.execute(delete(Alert).where(Alert.patient_id == patient_id))
        session.execute(delete(TriageDecision).where(TriageDecision.patient_id == patient_id))
        session.execute(delete(CheckinSession).where(CheckinSession.patient_id == patient_id))
        session.execute(delete(Answer).where(Answer.response_id.in_(response_ids)))
        session.execute(delete(Response).where(Response.patient_id == patient_id))
        session.commit()
    return str(patient_id)


def send(client: TestClient, answers: Sequence[tuple[str, str, int | None]]) -> dict[str, Any]:
    questionnaire = client.get(QUESTIONNAIRE).json()
    payload = {
        "client_submission_id": str(uuid.uuid4()),
        "questionnaire_id": questionnaire["questionnaire_id"],
        "answers": [{"symptom_key": s, "attribute": a, "value": v} for s, a, v in answers],
    }
    reply = client.post(RESPONSES, json=payload)
    assert reply.status_code == 201, reply.text
    body: dict[str, Any] = reply.json()
    return body


def decision_row(app: FastAPI, response_id: str) -> TriageDecision:
    with app.state.session_factory() as session:
        row: TriageDecision = session.scalars(
            select(TriageDecision).where(TriageDecision.response_id == response_id)
        ).one()
        session.expunge(row)
    return row


def alerts_of(app: FastAPI, patient_id: str, rule_prefix: str | None = None) -> list[Alert]:
    with app.state.session_factory() as session:
        found = list(session.scalars(select(Alert).where(Alert.patient_id == patient_id)))
        for alert in found:
            session.expunge(alert)
    return [a for a in found if rule_prefix is None or a.rule_id.startswith(rule_prefix)]


def triage_get(client: TestClient, patient_id: str, **params: str) -> Any:
    return client.get(f"{BASE}/patients/{patient_id}/triage", params=params)


# ---- Schema H5 und Seed -------------------------------------------------------------------
def test_h5_columns_and_the_empty_regimen_table_exist(seeded_app: FastAPI) -> None:
    inspector = inspect(seeded_app.state.engine)
    columns = {c["name"] for c in inspector.get_columns("wa_triage_decisions")}
    assert {
        "composition_hash",
        "composition_status",
        "component_ids_json",
        "coverage_gap",
        "response_id",
        "rule_version",
        "tree_version",
        "leaf_ids_json",
        "shield_hits_json",
        "counterfactuals_json",
        "level_lo",
        "level_hi",
    } <= columns
    regimen = {c["name"] for c in inspector.get_columns("wa_patient_regimens")}
    assert {
        "patient_id",
        "regimen_id",
        "substances_json",
        "module_ids_json",
        "composition_hash",
        "composition_status",
        "coverage_gap",
        "valid_from",
        "valid_to",
    } <= regimen
    assert "receipt_json" in {c["name"] for c in inspector.get_columns("wa_responses")}
    with seeded_app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PatientRegimen)) == 0


def test_seed_stores_decisions_but_creates_no_triage_alerts(seeded_app: FastAPI) -> None:
    with seeded_app.state.session_factory() as session:
        responses = session.scalar(select(func.count()).select_from(Response)) or 0
        decisions = session.scalar(select(func.count()).select_from(TriageDecision)) or 0
        triage_alerts = list(session.scalars(select(Alert).where(Alert.rule_id.like("R-TRI%"))))
    assert decisions == responses > 0  # jede gespeicherte Antwort hat eine Entscheidung
    assert triage_alerts == []  # Bestandsorakel bleiben gültig


# ---- Entscheidung und Befundkarte ---------------------------------------------------------
def test_fever_decision_is_red_with_shield_reason_and_the_stored_header(
    client: TestClient,
) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    receipt = send(client, [("fever", "presence", 1), ("shortness_of_breath", "severity", 0)])
    row = decision_row(app, receipt["response_id"])
    assert (row.level, row.level_lo, row.level_hi) == ("RED", "RED", "RED")
    assert row.incomplete is False
    assert row.profile_id == "PEMBROLIZUMAB"
    kb = triage.get_kb()
    assert isinstance(kb, KnowledgeBase)
    assert row.rule_version == kb.hash
    assert len(row.tree_version) == 64
    assert row.composition_hash == kb.profile("PEMBROLIZUMAB").hash
    assert (row.composition_status, row.coverage_gap) == ("placeholder", False)
    assert row.component_ids_json == ["PEMBROLIZUMAB"]
    assert set(row.leaf_ids_json) == {"yellow", "red"}
    assert row.created_at is not None  # = Zeitpunkt der Antwort (keine Uhr in der Entscheidung)
    login(client, "doctor")
    card = triage_get(client, patient_id, lang="en").json()
    assert (card["level"], card["incomplete"], card["status"]) == ("RED", False, "placeholder")
    assert card["response_id"] == receipt["response_id"]
    kinds = {r["kind"] for r in card["reason_codes"]}
    assert {"shield", "leaf"} <= kinds
    shield = next(r for r in card["reason_codes"] if r["kind"] == "shield")
    assert shield["code"] == "F_FEVER"
    assert "Fever reported" in shield["text"]
    assert shield["items"] == ["fever"]
    assert card["asked_questions"] == 2
    assert card["full_questions"] == 14
    assert {"counterfactuals", "recommendations"} <= set(card)


def test_counterfactuals_are_sentence_parts_without_introduction(client: TestClient) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    send(client, [("fever", "presence", 0), ("diarrhea", "frequency", 2)])
    login(client, "doctor")
    card = triage_get(client, patient_id, lang="en").json()
    assert card["level"] == "RED"  # Boden F_ICI_DIARRHEA
    changes = [c for c in card["counterfactuals"] if c["kind"] == "change"]
    lower = next(c for c in changes if c["direction"] == "lower")
    assert lower["text"].endswith("(grade) dropped to ≤ 1")
    assert not lower["text"].lower().startswith(("would", "if "))  # Einleitung stellt die UI voran
    assert lower["changes"][0]["symptom_key"] == "diarrhea"
    cs = triage_get(client, patient_id, lang="cs").json()
    assert any("klesl na ≤ 1" in c["text"] for c in cs["counterfactuals"])
    raised = [c for c in card["counterfactuals"] if c["direction"] == "raise"]
    assert raised == []  # Rot ist die höchste Stufe


def test_shield_counterfactual_is_its_own_entry(client: TestClient) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    send(
        client,
        [
            ("fever", "presence", 1),
            ("diarrhea", "frequency", 2),
            ("shortness_of_breath", "severity", 2),
        ],
    )
    login(client, "doctor")
    card = triage_get(client, patient_id, lang="en").json()
    shields = [c for c in card["counterfactuals"] if c["kind"] == "shield"]
    assert {s["text"] for s in shields} == {
        "Floor F_FEVER prevents lowering",
        "Floor F_ICI_DIARRHEA prevents lowering",
        "Floor F_ICI_DYSPNEA prevents lowering",
    }
    assert all(s["changes"] == [] for s in shields)


def test_missing_safety_answer_gives_at_least_yellow_incomplete(client: TestClient) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    receipt = send(client, [("fever", "presence", 0), ("fatigue", "severity", 0)])  # Atemnot fehlt
    row = decision_row(app, receipt["response_id"])
    assert row.incomplete is True
    assert row.level in ("YELLOW", "RED")
    login(client, "doctor")
    card = triage_get(client, patient_id, lang="en").json()
    assert any(r["kind"] == "incomplete" for r in card["reason_codes"])
    assert card["level_lo"] in ("GREEN", "YELLOW")
    assert card["level_hi"] in ("YELLOW", "RED")


def test_decision_is_idempotent_and_selectable_by_response(client: TestClient) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    first = send(client, [("fever", "presence", 0), ("shortness_of_breath", "severity", 0)])
    tick(app)
    second = send(client, [("fever", "presence", 1), ("shortness_of_breath", "severity", 0)])
    login(client, "doctor")
    assert triage_get(client, patient_id).json()["response_id"] == second["response_id"]
    older = triage_get(client, patient_id, response_id=first["response_id"]).json()
    assert older["response_id"] == first["response_id"]
    assert older["level"] in ("GREEN", "YELLOW")
    with app.state.session_factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(TriageDecision)
            .where(TriageDecision.patient_id == patient_id)
        )
        response = session.get(Response, first["response_id"])
        kb = triage.get_kb()
        assert response is not None
        assert kb is not None
        content = get_content()
        assert content is not None
        again = triage.decide(session, response, content, kb)
        assert again is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(TriageDecision)
                .where(TriageDecision.patient_id == patient_id)
            )
            == count
        )


def test_triage_endpoint_access_and_not_found(client: TestClient) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    assert triage_get(client, patient_id).status_code == 401
    login(client, "patient2")
    assert triage_get(client, patient_id).status_code == 403
    login(client, "doctor")
    assert triage_get(client, patient_id).status_code == 404  # noch keine Entscheidung
    assert triage_get(client, "no-such-patient").status_code == 404
    login(client, "patient2")
    send(client, [("fever", "presence", 0)])
    login(client, "doctor")
    assert triage_get(client, patient_id, response_id="no-such-response").status_code == 404
    assert triage_get(client, patient_id, lang="xx").status_code == 422
    assert triage_get(client, patient_id).status_code == 200
    with app.state.session_factory() as session:
        views = session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "view_triage")
        )
    assert views == 1


def test_overview_carries_the_latest_triage_summary(client: TestClient) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "doctor")
    empty = client.get(f"{BASE}/patients/{patient_id}/overview").json()
    assert empty["triage_latest"] is None
    login(client, "patient2")
    receipt = send(client, [("fever", "presence", 1)])
    login(client, "doctor")
    latest = client.get(f"{BASE}/patients/{patient_id}/overview").json()["triage_latest"]
    assert latest["response_id"] == receipt["response_id"]
    assert (latest["level"], latest["profile_id"], latest["status"]) == (
        "RED",
        "PEMBROLIZUMAB",
        "placeholder",
    )
    assert {"level_lo", "level_hi", "incomplete", "decided_at"} <= set(latest)


# ---- Meldungen R-TRI-RED/YEL und Rauschbremse ---------------------------------------------
def test_existing_rule_alert_carries_the_decision_and_no_second_alert_is_created(
    client: TestClient,
) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    receipt = send(client, [("fever", "presence", 1)])
    found = alerts_of(app, patient_id)
    assert [a.rule_id for a in found] == ["R-URG-01"]
    assert found[0].explanation_json["triage"]["level"] == "RED"
    assert found[0].explanation_json["triage"]["response_id"] == receipt["response_id"]
    assert alerts_of(app, patient_id, "R-TRI") == []


def test_tree_only_red_creates_one_immediate_alert_with_a_notification(client: TestClient) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    receipt = send(client, [("fever", "presence", 0), ("diarrhea", "frequency", 2)])
    created = alerts_of(app, patient_id)
    assert [(a.rule_id, a.level, a.notified, a.symptom_key) for a in created] == [
        (RULE_RED, "red", True, "")
    ]
    assert created[0].response_id == receipt["response_id"]
    with app.state.session_factory() as session:
        notice = session.scalars(
            select(Notification).where(Notification.patient_id == patient_id)
        ).one()
        assert notice.level == "red"
        assert notice.text.startswith("SYN-0002: ")
    login(client, "doctor")
    listed = client.get(f"{BASE}/patients/{patient_id}/alerts").json()
    view = next(a for a in listed if a["rule_id"] == RULE_RED)
    assert view["headline"] == "Triáž: červená úroveň (zástupná pravidla)"
    assert view["explanation"]["kind"] == "triage"  # A0-Entscheid v2.8, nicht "threshold"
    assert view["explanation"]["triage"]["level"] == "RED"
    assert view["symptom_key"] is None
    english = client.get(f"{BASE}/patients/{patient_id}/alerts", params={"lang": "en"}).json()
    assert any(a["headline"] == "Triage: red level (placeholder rules)" for a in english)


def test_tree_only_yellow_creates_a_yellow_alert_without_immediate_notice(
    client: TestClient,
) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    send(
        client,
        [
            ("fever", "presence", 0),
            ("shortness_of_breath", "severity", 0),
            ("fatigue", "severity", 2),
        ],
    )
    created = alerts_of(app, patient_id)
    assert [(a.rule_id, a.level, a.notified) for a in created] == [(RULE_YELLOW, "yellow", False)]
    with app.state.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.patient_id == patient_id)
            )
            == 0
        )


def test_a_red_rule_alert_on_the_same_response_covers_a_yellow_tree_result(
    client: TestClient,
) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    send(client, [("fever", "presence", 0), ("fatigue", "severity", 4)])  # R-SEV-01 rot (Schwere 3)
    assert [a.rule_id for a in alerts_of(app, patient_id)] == ["R-SEV-01"]


def test_no_second_open_alert_of_the_same_rule_but_a_higher_level_creates_one(
    client: TestClient,
) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    send(
        client,
        [
            ("fever", "presence", 0),
            ("shortness_of_breath", "severity", 0),
            ("fatigue", "severity", 2),
        ],
    )
    tick(app)
    send(
        client,
        [
            ("fever", "presence", 0),
            ("shortness_of_breath", "severity", 0),
            ("fatigue", "severity", 2),
        ],
    )
    assert [a.rule_id for a in alerts_of(app, patient_id)] == [RULE_YELLOW]  # Rauschbremse
    tick(app)
    send(client, [("fever", "presence", 0), ("diarrhea", "frequency", 2)])
    assert sorted(a.rule_id for a in alerts_of(app, patient_id)) == [RULE_RED, RULE_YELLOW]


def test_acknowledged_alert_keeps_quiet_until_a_green_decision_ends_the_episode(
    client: TestClient,
) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    yellow = [
        ("fever", "presence", 0),
        ("shortness_of_breath", "severity", 0),
        ("fatigue", "severity", 2),
    ]
    green = [
        ("fever", "presence", 0),
        ("shortness_of_breath", "severity", 0),
        ("fatigue", "severity", 0),
    ]
    login(client, "patient2")
    send(client, yellow)
    (first,) = alerts_of(app, patient_id)
    tick(app)
    login(client, "doctor")
    ack = client.post(
        f"{BASE}/alerts/{first.id}/acknowledge",
        json={"decision": "no_action_needed", "note": "kontrolliert"},
    )
    assert ack.status_code == 200, ack.text
    tick(app)
    login(client, "patient2")
    send(client, yellow)
    assert len(alerts_of(app, patient_id, "R-TRI")) == 1  # Ruhezeit nach der Quittierung
    tick(app)
    send(client, green)
    tick(app)
    send(client, yellow)
    assert len(alerts_of(app, patient_id, "R-TRI")) == 2  # Entwarnung beendete die Episode


def test_triage_failure_never_loses_the_response_or_the_rule_alerts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(triage, "decide", broken)
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    receipt = send(client, [("fever", "presence", 1)])
    assert [a.rule_id for a in alerts_of(app, patient_id)] == ["R-URG-01"]  # Regeln unberührt
    with app.state.session_factory() as session:
        assert session.get(Response, receipt["response_id"]) is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(TriageDecision)
                .where(TriageDecision.patient_id == patient_id)
            )
            == 0
        )
        failed = list(
            session.scalars(select(AuditEvent).where(AuditEvent.action == "triage_failed"))
        )
    assert [e.details_json for e in failed] == [{"error": "RuntimeError"}]


def test_acknowledge_works_for_triage_alerts_too(client: TestClient) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    send(client, [("fever", "presence", 0), ("diarrhea", "frequency", 2)])
    (alert,) = alerts_of(app, patient_id)
    login(client, "doctor")
    ack = client.post(f"{BASE}/alerts/{alert.id}/acknowledge", json={"decision": "contact_patient"})
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"
    detail = client.get(f"{BASE}/alerts/{alert.id}").json()
    assert detail["rule_id"] == RULE_RED


# ---- Regelkarte und Konfiguration ---------------------------------------------------------
def test_rule_card_has_every_profile_with_verification_rules_floors_and_placeholders(
    client: TestClient,
) -> None:
    login(client, "doctor")
    card = client.get(f"{BASE}/config/triage", params={"lang": "en"}).json()
    kb = triage.get_kb()
    assert isinstance(kb, KnowledgeBase)
    assert card["kb_version"] == kb.hash
    assert card["compiler_version"].startswith("compiler-")
    by_id = {p["profile_id"]: p for p in card["profiles"]}
    assert set(by_id) == {*ALL_LEAVES, *CLASS_MODULE_PROFILES}  # T-24: Klassenmodul-PoC
    for profile in by_id.values():
        assert profile["verification"]["under"] == profile["verification"]["over"] == 0
        assert profile["verification"]["monotone_violations"] == 0
        # Rohgitter über 1 Mio. Punkte (PAZOPANIB, NIVOLUMAB) werden nur per Stichprobe geprüft
        expected = "sampled_raw" if profile["profile_id"] in LARGE_RAW_GRID else "exhaustive_raw"
        assert profile["verification"]["scope"] == expected
        assert profile["verification"]["points"] > 0
        assert profile["trees"]["red"]["leaves"] > 0
        assert profile["trees"]["yellow"]["depth"] > 0
        levels = [r["level"] for r in profile["rules"]]
        assert levels == sorted(levels, key=lambda lv: lv != "red")  # Rot zuerst
        assert all(r["text"] and r["leaf_id"] and r["teacher_rule_ids"] for r in profile["rules"])
        assert profile["floors"]
        assert all(f["locked"] is True and f["status"] == "placeholder" for f in profile["floors"])
        assert profile["placeholders"]
        (component,) = profile["components"]
        assert component["component_id"] == profile["profile_id"]
        assert profile["tree_version"]
        assert profile["composition_hash"]
    assert by_id["PEMBROLIZUMAB"]["regimen_ids"] == ["PEMBROLIZUMAB"]
    assert any(f["id"] == "F_ICI_DIARRHEA" for f in by_id["PEMBROLIZUMAB"]["floors"])


def test_rule_card_and_config_access_and_extra_fields(client: TestClient) -> None:
    assert client.get(f"{BASE}/config/triage").status_code == 401
    login(client, "patient")
    assert client.get(f"{BASE}/config/triage").status_code == 403
    login(client, "doctor")
    config = client.get(f"{BASE}/config").json()
    kb = triage.get_kb()
    assert isinstance(kb, KnowledgeBase)
    assert config["triage_version"] == kb.hash
    assert config["advice"]["version"].startswith("advice-v")
    assert config["medications"]["version"].startswith("medications-v")
    cs = client.get(f"{BASE}/config/triage", params={"lang": "cs"}).json()
    en = client.get(f"{BASE}/config/triage", params={"lang": "en"}).json()
    assert cs["profiles"][0]["rules"][0]["text"] != en["profiles"][0]["rules"][0]["text"]


def test_doctor_texts_avoid_the_forbidden_words(client: TestClient) -> None:
    app = app_of(client)
    patient_id = clear_history(app, "SYN-0002")
    login(client, "patient2")
    send(client, [("fever", "presence", 0), ("diarrhea", "frequency", 2)])
    login(client, "doctor")
    forbidden = ("empfehl", "doporuč", "recommend", "diagnos")
    for lang in ("cs", "en", "de"):
        card = triage_get(client, patient_id, lang=lang).json()
        texts = [r["text"] for r in card["reason_codes"]] + [
            c["text"] for c in card["counterfactuals"]
        ]
        for text in texts:
            assert not [w for w in forbidden if w in text.lower()], text


def test_patient_never_sees_the_level_in_the_receipt(client: TestClient) -> None:
    app = app_of(client)
    clear_history(app, "SYN-0002")
    login(client, "patient2")
    receipt = send(client, [("fever", "presence", 1)])
    assert set(receipt) <= {
        "response_id",
        "recorded_at",
        "answered",
        "skipped",
        "message_key",
        "advice",
        "escalation",
    }
    flat = repr(receipt).lower()
    for word in ("level_lo", "level_hi", "triage", "rule_version", "leaf", "green", "yellow"):
        assert word not in flat
    assert receipt["escalation"]["level"] in ("acute", "general")  # Eskalationsart, kein Befund
    assert_patient_safe(receipt["escalation"]["text"])


# ---- Vorwärmen ----------------------------------------------------------------------------
def test_warmup_starts_once_and_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []

    class FakeThread:
        def __init__(self, target: Any, name: str, daemon: bool) -> None:
            self.name = name
            assert daemon is True

        def start(self) -> None:
            started.append(self.name)

    monkeypatch.setattr("waechter.services.triage.threading.Thread", FakeThread)
    monkeypatch.setattr("waechter.services.triage._WARMUP_STARTED", False)
    monkeypatch.setenv(triage.WARMUP_ENV, "0")
    assert triage.start_warmup() is False  # abgeschaltet
    monkeypatch.delenv(triage.WARMUP_ENV)
    assert triage.start_warmup() is True
    assert triage.start_warmup() is False  # nur einmal je Prozess
    assert started == ["triage-warmup"]


def test_warm_compiles_every_profile_into_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    real = runtime_for

    def spy(kb: KnowledgeBase, profile_id: str, **kwargs: Any) -> Any:
        seen.append(profile_id)
        return real(kb, profile_id, **kwargs)

    monkeypatch.setattr("waechter.services.triage.runtime_for", spy)
    triage._warm()
    assert sorted(seen) == sorted([*ALL_LEAVES, *CLASS_MODULE_PROFILES])  # T-24


# ---- Orakel: unabhängige Referenz ---------------------------------------------------------
def test_every_seeded_decision_equals_the_independent_reference(seeded_app: FastAPI) -> None:
    """Orakel-Ergänzung: Level je Seed-Antwort == unabhängige Referenz `a3_triage_ref`."""
    import a3_triage_ref as ref
    from triage_support import real_inputs

    raw, _, _ = real_inputs()
    composite = raw["composite_grading"]["map"]
    grade_max = {i["symptom_key"]: i["grade_max"] for i in raw["items"]}
    order = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    profiles = {leaf: ref.resolve(raw, leaf) for leaf in ALL_LEAVES}

    def grades_of(rows: list[Answer]) -> dict[str, int]:
        grades: dict[str, int] = {}
        for row in rows:
            if row.value is not None:
                grade = min(composite[row.value], grade_max.get(row.symptom_key, 3))
                grades[row.symptom_key] = max(grade, grades.get(row.symptom_key, 0))
        return grades

    checked = 0
    with seeded_app.state.session_factory() as session:
        for patient in session.scalars(select(Patient)):
            previous: dict[str, int] | None = None
            history = session.scalars(
                select(Response)
                .where(Response.patient_id == patient.id)
                .order_by(Response.recorded_at, Response.id)
            ).all()
            for response in history:
                rows = list(
                    session.scalars(select(Answer).where(Answer.response_id == response.id))
                )
                decision = session.scalars(
                    select(TriageDecision).where(TriageDecision.response_id == response.id)
                ).one()
                profile = profiles[decision.profile_id]
                grades = grades_of([r for r in rows if r.symptom_key in profile.items])
                expected = ref.final_level(profile, grades, previous)
                answered = {r.symptom_key for r in rows if r.value is not None}
                if any(s not in answered for s in profile.safety_items):
                    expected = max(expected, "YELLOW", key=order.__getitem__)
                assert decision.level == expected, (patient.pseudonym, response.id)
                previous = {s: g for s, g in grades.items() if s in profile.items}
                checked += 1
    assert checked > 50
