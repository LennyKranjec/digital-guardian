# ruff: noqa: S311, F401, F811
"""A3-Gegenproben zu T-04b (Besitz A3): Rechte, Quittierung (echte Route), Nebenläufigkeit,
Auswertung getrennt von der Antwort (H-5), Benachrichtigungskanal.

Gemeinsame Hilfen kommen aus `test_a3_t04a.py` (Uhr, Benachrichtigungskanal, Modell).
"""

import logging
import random
import time
import uuid
from datetime import timedelta
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.adapters.memory_notifier import MemoryNotifier
from app.persistence.models import AuditEvent
from conftest import CSRF, login
from test_a3_t04a import (
    RESPONSES,
    MutableClock,
    _parallel,
    alerts_of,
    live,
    mailbox,
    nausea_history,
    post,
    seeded_template,
)
from waechter import notifier
from waechter.models import Alert, AlertAction, Notification, Patient, Response
from waechter.services import alerts as alert_service

BASE = "/api/v1/waechter"
RULE = ("R-SEV-01", "nausea", "severity")


def staff(app: FastAPI, username: str = "doctor") -> TestClient:
    client = TestClient(app, headers=CSRF)
    client.__enter__()
    login(client, username)
    return client


def ack(client: TestClient, alert_id: str, decision: str = "no_action_needed", **extra: Any) -> Any:
    body = {"decision": decision, **extra}
    response = client.post(f"{BASE}/alerts/{alert_id}/acknowledge", json=body)
    if response.status_code == 401:  # Sitzung läuft mit verschobener Uhr ab
        login(client, "doctor")
        response = client.post(f"{BASE}/alerts/{alert_id}/acknowledge", json=body)
    return response


def make_alert(app: FastAPI, client: TestClient, value: int = 3) -> Alert:
    known = {a.id for a in alerts_of(app, *RULE)}
    assert post(client, [("nausea", "severity", value)]).status_code == 201
    (created,) = [
        a for a in alerts_of(app, *RULE) if a.id not in known
    ]  # Reihenfolge nicht annehmen
    return created


# --- Rechte und Fehler ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("username", "expected"),
    [
        (None, 401),
        ("patient", 403),
        ("patient2", 403),
        ("user", 403),
        ("doctor", 200),
        ("admin", 200),
    ],
)
@pytest.mark.parametrize("kind", ["list", "detail", "notifications"])
def test_a3_read_endpoints_role_matrix(
    live: Any, kind: str, username: str | None, expected: int
) -> None:
    app, patient_client, _ = live
    alert = make_alert(app, patient_client)
    paths = {
        "list": f"{BASE}/patients/{alert.patient_id}/alerts",
        "detail": f"{BASE}/alerts/{alert.id}",
        "notifications": f"{BASE}/notifications",
    }
    with TestClient(app, headers=CSRF) as client:
        if username:
            login(client, username)
        response = client.get(paths[kind])
    assert response.status_code == expected, response.text
    if expected != 200:
        assert set(response.json()) >= {"code", "message"}
        assert "alert_id" not in response.text  # kein Datenleck im Fehlerfall


@pytest.mark.parametrize(
    ("username", "expected"),
    [
        (None, 401),
        ("patient", 403),
        ("patient2", 403),
        ("user", 403),
        ("doctor", 200),
        ("admin", 200),
    ],
)
def test_a3_acknowledge_role_matrix_and_no_side_effect_when_denied(
    live: Any, username: str | None, expected: int
) -> None:
    app, patient_client, _ = live
    alert = make_alert(app, patient_client)
    with TestClient(app, headers=CSRF) as client:
        if username:
            login(client, username)
        response = (
            ack(client, alert.id)
            if username
            else client.post(f"{BASE}/alerts/{alert.id}/acknowledge", json={"decision": "other"})
        )
    assert response.status_code == expected, response.text
    with app.state.session_factory() as session:
        stored = session.get(Alert, alert.id)
        assert stored is not None
        assert stored.status == ("acknowledged" if expected == 200 else "open")
        actions = session.scalar(
            select(func.count()).select_from(AlertAction).where(AlertAction.alert_id == alert.id)
        )
        assert actions == (1 if expected == 200 else 0)


def test_a3_acknowledge_input_matrix(live: Any) -> None:
    app, patient_client, _ = live
    alert = make_alert(app, patient_client)
    doctor = staff(app)
    try:
        bad_bodies: list[Any] = [
            {},
            {"decision": None},
            {"decision": ""},
            {"decision": "ACK"},
            {"decision": "other", "note": "x" * 501},
            {"decision": "other", "note": 5},
            {"decision": "other", "unknown": 1},
            {"decision": "other", "by": "Dr. Fake", "at": "2020-01-01T00:00:00Z", "status": "open"},
            [],
            "other",
        ]
        for body in bad_bodies:
            response = doctor.post(f"{BASE}/alerts/{alert.id}/acknowledge", json=body)
            assert response.status_code == 422, (body, response.status_code)
        assert doctor.post(f"{BASE}/alerts/{alert.id}/acknowledge").status_code == 422  # ohne Body
        assert doctor.get(f"{BASE}/alerts/{alert.id}").json()["status"] == "open"  # unverändert
        for bad_id in ("nope", "0" * 36, "../../etc/passwd", "%00"):
            assert doctor.get(f"{BASE}/alerts/{bad_id}").status_code == 404
            assert ack(doctor, bad_id).status_code == 404
        assert doctor.get(f"{BASE}/patients/nope/alerts").status_code == 404
        for query in ({"status": "bogus"}, {"lang": "fr"}, {"status": ""}):
            assert (
                doctor.get(f"{BASE}/patients/{alert.patient_id}/alerts", params=query).status_code
                == 422
            )
    finally:
        doctor.__exit__(None, None, None)


@pytest.mark.parametrize(
    "decision", ["contact_patient", "visit_scheduled", "no_action_needed", "other"]
)
def test_a3_acknowledge_result_is_complete_and_server_controlled(live: Any, decision: str) -> None:
    app, patient_client, _ = live
    alert = make_alert(app, patient_client)
    doctor = staff(
        app, "admin"
    )  # Plattformrolle darf ebenfalls quittieren; `by` kommt aus der Sitzung
    try:
        note = "Rückruf vereinbart; Übelkeit nimmt zu ✓"
        response = ack(doctor, alert.id, decision, note=note)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "acknowledged"
        assert body["acknowledgement"]["decision"] == decision
        assert body["acknowledgement"]["note"] == note
        assert body["acknowledgement"]["by"]  # Anzeigename des angemeldeten Kontos
        assert body["acknowledgement"]["at"].endswith("+02:00")  # Prager Zeit (Anker im Sommer)
        assert (
            doctor.get(f"{BASE}/alerts/{alert.id}").json()["acknowledgement"]
            == body["acknowledgement"]
        )
        patient_id = alert.patient_id
        assert [
            a["status"]
            for a in doctor.get(
                f"{BASE}/patients/{patient_id}/alerts", params={"status": "open"}
            ).json()
            if a["alert_id"] == alert.id
        ] == []
        listed = doctor.get(
            f"{BASE}/patients/{patient_id}/alerts", params={"status": "acknowledged"}
        ).json()
        assert alert.id in {a["alert_id"] for a in listed}
        # Audit: Aktion ja, Notiz und Entscheidungstext nie im Audit/Log
        with app.state.session_factory() as session:
            events = session.scalars(
                select(AuditEvent).where(AuditEvent.action == "acknowledge_alert")
            ).all()
            assert len(events) == 1
            assert note not in str(events[0].details_json)
            assert events[0].details_json == {"decision": decision, "level": "red"}
    finally:
        doctor.__exit__(None, None, None)


# --- Quittierung: Nebenläufigkeit (4 ⇒ 1) und Wirkung auf die Rauschbremse -----------------------


@pytest.mark.parametrize("round_", range(3))
def test_a3_parallel_acknowledgements_exactly_one_wins(live: Any, round_: int) -> None:
    app, patient_client, _ = live
    alert = make_alert(app, patient_client)
    decisions = ["contact_patient", "visit_scheduled", "no_action_needed", "other"] * 2
    doctors = [staff(app, "doctor" if i % 2 else "admin") for i in range(8)]
    try:
        results = _parallel(
            lambda i: doctors[i].post(
                f"{BASE}/alerts/{alert.id}/acknowledge",
                json={"decision": decisions[i], "note": f"von {i}"},
            ),
            8,
        )
    finally:
        for d in doctors:
            d.__exit__(None, None, None)
    codes = [r.status_code for r in results]
    assert sorted(codes) == [200] + [409] * 7, codes
    assert {r.json()["code"] for r in results if r.status_code == 409} == {"alert_not_open"}
    winner = codes.index(200)
    with app.state.session_factory() as session:
        actions = session.scalars(select(AlertAction).where(AlertAction.alert_id == alert.id)).all()
        assert len(actions) == 1
        assert actions[0].decision == decisions[winner]
        assert actions[0].note == f"von {winner}"
        stored = session.get(Alert, alert.id)
        assert stored is not None
        assert (stored.status, stored.version) == ("acknowledged", 2)  # genau ein Versionssprung
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "acknowledge_alert")
        ).all()
        assert len(events) == 1


def test_a3_acknowledging_different_alerts_in_parallel_all_succeed(live: Any) -> None:
    app, patient_client, _ = live
    ids = []
    for value in (3, 4):
        ids.append(make_alert(app, patient_client, value).id)
    assert post(patient_client, [("fever", "presence", 1)]).status_code == 201
    ids.append(alerts_of(app, "R-URG-01", "fever", "presence")[-1].id)
    doctors = [staff(app) for _ in ids]
    try:
        results = _parallel(lambda i: ack(doctors[i], ids[i]), len(ids))
    finally:
        for d in doctors:
            d.__exit__(None, None, None)
    assert [r.status_code for r in results] == [200] * len(ids)


def test_a3_cooldown_counts_from_the_acknowledgement_not_from_creation(live: Any) -> None:
    """Meldung um T, Quittierung um T+20 h: bis T+44 h Ruhe (nicht bis T+24 h)."""
    app, client, clock = live
    alert = make_alert(app, client, 3)
    start = clock.instant
    clock.instant = start + timedelta(hours=20)
    doctor = staff(app)
    try:
        assert ack(doctor, alert.id).status_code == 200
    finally:
        doctor.__exit__(None, None, None)
    clock.instant = start + timedelta(hours=30)  # 30 h nach Entstehung, 10 h nach Quittierung
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert len(alerts_of(app, *RULE)) == 1
    clock.instant = start + timedelta(hours=44) - timedelta(seconds=1)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert len(alerts_of(app, *RULE)) == 1
    clock.instant = start + timedelta(hours=44)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert len(alerts_of(app, *RULE)) == 2


@pytest.mark.parametrize("model_seed", range(3))
def test_a3_noise_brake_model_with_the_real_acknowledge_route(live: Any, model_seed: int) -> None:
    """Wie der Modelltest zu T-04a, aber die Quittierung läuft über die echte Route."""
    app, client, clock = live
    doctor = staff(app)
    rng = random.Random(8800 + model_seed)
    cooldown = timedelta(hours=24)
    model: list[dict[str, Any]] = []
    fired = 0
    history = nausea_history(app)  # bereits gespeicherte Werte (Seed) mit Zeitpunkt
    try:
        for step in range(50):
            action = rng.choice(["send", "send", "send", "ack", "wait"])
            if action == "wait":
                clock.instant += timedelta(hours=rng.choice([1, 12, 23, 24, 25, 48]))
            elif action == "ack":
                open_alerts = [a for a in model if a["open"]]
                if open_alerts:
                    chosen = rng.choice(open_alerts)
                    assert ack(doctor, chosen["id"]).status_code == 200
                    chosen["open"] = False
                    chosen["ack_at"] = clock.instant
            else:
                clock.instant += timedelta(minutes=rng.choice([1, 30, 90]))
                value = rng.randint(0, 4)
                assert post(client, [("nausea", "severity", value)]).status_code == 201
                # DR-012: eine Antwort unter der Schwelle (3) nach der Meldung beendet die Episode
                blocking = [
                    a["value"]
                    for a in model
                    if (a["open"] or clock.instant < a["ack_at"] + cooldown)
                    and not any(a["created"] < at < clock.instant and v < 3 for at, v in history)
                ]
                expected_new = value >= 3 and (not blocking or value > max(blocking))
                stored = alerts_of(app, *RULE)
                new = [a for a in stored if a.id not in {m["id"] for m in model}]
                assert len(new) == (1 if expected_new else 0), (step, value, blocking)
                for alert in new:
                    model.append(
                        {
                            "id": alert.id,
                            "value": value,
                            "open": True,
                            "ack_at": None,
                            "created": clock.instant,
                        }
                    )
                    fired += 1
                history.append((clock.instant, value))
    finally:
        doctor.__exit__(None, None, None)
    assert fired >= 3


# --- H-5: Auswertung getrennt von der Antwort ------------------------------------------------


def _response_row(app: FastAPI, response_id: str) -> Response:
    with app.state.session_factory() as session:
        row = session.get(Response, response_id)
        assert row is not None
        session.expunge(row)
        return cast(Response, row)


def test_a3_rule_failure_never_loses_the_answer_and_is_recoverable(
    live: Any,
    mailbox: MemoryNotifier,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, client, _ = live
    marker = "A3-SECRET-VALUE-6612"

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError(marker)

    caplog.set_level(logging.DEBUG)
    sent_before = len(mailbox.sent)  # der Seed hat bereits rote Meldungen gesendet
    with monkeypatch.context() as patch:
        patch.setattr(alert_service, "evaluate_response", boom)
        csid = str(uuid.uuid4())
        body = {
            "client_submission_id": csid,
            "questionnaire_id": "items-v1:FIX-REG",
            "answers": [{"symptom_key": "fever", "attribute": "presence", "value": 1}],
        }
        failed = client.post(RESPONSES, json=body)
        assert failed.status_code == 201  # Patientin sieht keinen Fehler und verliert nichts
        replay = client.post(RESPONSES, json=body)
        assert (replay.status_code, replay.json()) == (200, failed.json())
    row = _response_row(app, failed.json()["response_id"])
    assert row.evaluation_status == "failed"
    with app.state.session_factory() as session:
        values = session.scalars(select(Response).where(Response.id == row.id)).one()
        assert (
            session.scalar(
                select(func.count()).select_from(Alert).where(Alert.response_id == row.id)
            )
            == 0
        )
        events = [
            e.action
            for e in session.scalars(select(AuditEvent).where(AuditEvent.target_id == row.id))
        ]
        assert "submit_response" in events
        assert "rule_evaluation_failed" in events
        assert values.patient_id
    assert len(mailbox.sent) == sent_before  # nichts „ausgesendet“
    assert marker not in caplog.text  # Fehlermeldung (mit Wert) gelangt nicht ins Log
    assert "RuntimeError" in caplog.text  # nur der Typname
    # danach arbeitet das System normal weiter: nächste Antwort wird ausgewertet
    ok = post(client, [("nausea", "severity", 4)])
    assert ok.status_code == 201
    assert _response_row(app, ok.json()["response_id"]).evaluation_status == "done"
    assert len(alerts_of(app, *RULE)) == 1


def test_a3_failure_after_partial_work_rolls_back_alert_and_notice(
    live: Any, mailbox: MemoryNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fehler nach dem Anlegen einer Meldung: weder Meldung noch Benachrichtigung bleibt zurück."""
    app, client, _ = live
    original = alert_service._notify

    def notify_then_fail(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        raise ValueError("nach Anlegen")

    monkeypatch.setattr(alert_service, "_notify", notify_then_fail)
    sent_before = len(mailbox.sent)
    response = post(client, [("nausea", "severity", 4)])
    assert response.status_code == 201
    assert alerts_of(app, *RULE) == []
    with app.state.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.text.like("SYN-0002%"))
            )
            == 0
        )
    assert len(mailbox.sent) == sent_before
    assert _response_row(app, response.json()["response_id"]).evaluation_status == "failed"


def test_a3_broken_rule_configuration_does_not_break_patient_submissions(live: Any) -> None:
    app, client, _ = live
    from waechter.models import ConfigVersion

    with app.state.session_factory() as session:
        active = session.scalars(
            select(ConfigVersion).where(
                ConfigVersion.kind == "rules", ConfigVersion.active.is_(True)
            )
        ).one()
        active.body_json = {"version": "rules-v9", "rules": [{"id": "R-X-01"}], "noise": {}}
        session.commit()
    response = post(client, [("nausea", "severity", 4)])
    assert response.status_code == 201
    assert _response_row(app, response.json()["response_id"]).evaluation_status == "failed"


def test_a3_notifier_outage_must_not_break_the_patients_submission(live: Any) -> None:
    class Down:
        def notify(self, notice: Any, now: Any) -> None:
            raise ConnectionError("Kanal nicht erreichbar")

    app, _, _ = live
    previous = notifier.get_notifier()
    notifier.set_notifier(Down())
    try:
        response = TestClient(app, headers=CSRF, raise_server_exceptions=False)
        with response as raw:
            login(raw, "patient2")
            result = raw.post(
                RESPONSES,
                json={
                    "client_submission_id": str(uuid.uuid4()),
                    "questionnaire_id": "items-v1:FIX-REG",
                    "answers": [{"symptom_key": "nausea", "attribute": "severity", "value": 4}],
                },
            )
        assert result.status_code == 201
    finally:
        notifier.set_notifier(previous)
    assert len(alerts_of(app, *RULE)) == 1  # Meldung bleibt in jedem Fall erhalten


# --- Wettlauf zwischen Prüfung und Anlegen (Regression durch die Trennung in H-5) ---------------


def test_a3_parallel_dedupe_holds_even_when_the_check_is_slow(
    live: Any, mailbox: MemoryNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Künstlich verlangsamte Prüfung simuliert Last: zwischen `suppressed()` und Einfügen liegt ein
    Zeitfenster. In T-04a (alles in einer Transaktion mit Schreibsperre) sah jede Anfrage die
    Meldung der anderen; seit der Trennung (H-5) nicht mehr."""
    original = alert_service.suppressed

    def slow(*args: Any, **kwargs: Any) -> bool:
        result = original(*args, **kwargs)
        time.sleep(0.05)
        return result

    monkeypatch.setattr(alert_service, "suppressed", slow)
    app, _, _ = live
    clients = [staff(app, "patient2") for _ in range(6)]
    try:
        before = len(mailbox.sent)
        results = _parallel(lambda i: post(clients[i], [("nausea", "severity", 3)]), 6)
    finally:
        for c in clients:
            c.__exit__(None, None, None)
    assert [r.status_code for r in results] == [201] * 6
    assert len(alerts_of(app, *RULE)) == 1
    assert len(mailbox.sent) - before == 1


# --- Migration w002 mit vorhandenen Daten ---


def test_a3_migration_w002_keeps_existing_rows_and_backfills_done(live: Any) -> None:
    """Dev-Datenbanken auf w001 werden mit Daten hochgezogen (Zeilen bleiben erhalten)."""
    from alembic import command
    from app.persistence.migrate import _config

    app, client, _ = live
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    state = app.state

    def counts() -> tuple[int, int]:
        with state.session_factory() as session:
            return (
                session.scalar(select(func.count()).select_from(Response)) or 0,
                session.scalar(select(func.count()).select_from(Alert)) or 0,
            )

    before = counts()
    config = _config(state.engine, state.registry)
    command.downgrade(config, "w001")  # Zustand eines Dev-Standes vor T-04b, mit Daten
    command.upgrade(config, "heads")
    assert counts() == before
    with state.session_factory() as session:
        statuses = set(session.scalars(select(Response.evaluation_status)))
        assert statuses == {"done"}  # Rückfüllung über den Server-Default
