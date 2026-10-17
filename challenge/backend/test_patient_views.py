"""Arbeitsliste, Übersicht, Verlauf, Belege, Ampel (G-02, H-5, R-MIS-01) und /meta (DR-009)."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.persistence.models import AuditEvent
from conftest import CHALLENGE_DIR, CSRF, login, make_settings, migrate, run_parallel
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import Content, get_content
from waechter.meta import waechter_meta
from waechter.models import Alert, AlertAction, Answer, Patient, Response
from waechter.timeutil import iso_prague, to_prague

BASE = "/api/v1/waechter"
LIGHT_ORDER = {"red": 3, "yellow": 2, "grey": 1, "green": 0}
REAL_CONTENT = CHALLENGE_DIR / "content"


def staff(app: FastAPI, username: str = "doctor") -> TestClient:
    client = TestClient(app, headers=CSRF)
    login(client, username)
    return client


def pid(app: FastAPI, pseudonym: str) -> str:
    with app.state.session_factory() as session:
        return str(session.scalars(select(Patient.id).where(Patient.pseudonym == pseudonym)).one())


def worklist(client: TestClient) -> dict[str, dict[str, Any]]:
    rows = client.get(f"{BASE}/patients").json()
    return {r["pseudonym"]: r for r in rows}


def audits(app: FastAPI, action: str) -> list[AuditEvent]:
    with app.state.session_factory() as session:
        return list(session.scalars(select(AuditEvent).where(AuditEvent.action == action)))


# --- Zugriff --------------------------------------------------------------------------------


def test_anonymous_gets_401(seeded_app: FastAPI) -> None:
    anon = TestClient(seeded_app, headers=CSRF)
    p = pid(seeded_app, "SYN-0001")
    for url in (
        f"{BASE}/patients",
        f"{BASE}/patients/{p}/overview",
        f"{BASE}/patients/{p}/timeline",
        f"{BASE}/patients/{p}/facts/resp-x",
    ):
        assert anon.get(url).status_code == 401, url


@pytest.mark.parametrize("username", ["patient", "patient2", "user"])
def test_patients_and_other_roles_get_403(seeded_app: FastAPI, username: str) -> None:
    other = staff(seeded_app, username)
    p = pid(seeded_app, "SYN-0001")
    for url in (
        f"{BASE}/patients",
        f"{BASE}/patients/{p}/overview",
        f"{BASE}/patients/{p}/timeline",
        f"{BASE}/patients/{p}/facts/resp-x",
    ):
        assert other.get(url).status_code == 403, url
    assert not audits(seeded_app, "view_overview")


def test_unknown_patient_is_404(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    ghost = uuid.uuid4()
    for url in (
        f"{BASE}/patients/{ghost}/overview",
        f"{BASE}/patients/{ghost}/timeline",
        f"{BASE}/patients/{ghost}/facts/resp-{ghost}",
    ):
        assert doctor.get(url).status_code == 404, url


# --- Arbeitsliste / Ampel -------------------------------------------------------------------


def test_worklist_shape_and_sorting(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    rows = doctor.get(f"{BASE}/patients").json()
    assert len(rows) >= 5
    keys = {
        "patient_id",
        "pseudonym",
        "display_name",
        "age",
        "regimen_id",
        "regimen_label",
        "cycle_day",
        "traffic_light",
        "open_alerts",
        "top_alert",
        "last_response_at",
        "next_visit_at",
        "persisting",
        "evaluation_pending",
        "synthetic",
    }
    assert all(set(r) == keys and r["synthetic"] is True for r in rows)
    order = [LIGHT_ORDER[r["traffic_light"]] for r in rows]
    assert order == sorted(order, reverse=True)  # rot > gelb > grau > grün
    reds = [r for r in rows if r["traffic_light"] == "red"]
    oldest = [r["top_alert"]["created_at"] for r in reds]
    assert oldest == sorted(oldest)  # innerhalb einer Stufe: ältere offene Meldung zuerst
    first = worklist(doctor)["SYN-0001"]
    assert first["age"] == 56
    assert first["regimen_label"] == "Testovací režim"
    assert first["cycle_day"] == 7
    assert first["top_alert"]["rule_id"] == "R-SEV-01"
    assert first["top_alert"]["level"] == "red"
    assert first["next_visit_at"].startswith("2026-11-01T09:00:00+01:00")
    assert first["last_response_at"] == "2026-10-17T08:00:00+02:00"


def traffic_lights_match_expected(app: FastAPI, content: Content) -> int:
    doctor = staff(app)
    rows = worklist(doctor)
    checked = 0
    for spec in content.scenario["patients"]:
        expected = spec.get("expected")
        if expected is None:
            continue
        assert rows[spec["pseudonym"]]["traffic_light"] == expected["traffic_light_at_anchor"], (
            spec["pseudonym"]
        )
        checked += 1
    return checked


def test_traffic_lights_match_the_scenario_oracle(seeded_app: FastAPI) -> None:
    content = get_content()
    assert content is not None
    assert traffic_lights_match_expected(seeded_app, content) == len(content.scenario["patients"])


@pytest.mark.skipif(not REAL_CONTENT.is_dir(), reason="challenge/content/ (A1) nicht vorhanden")
def test_traffic_lights_and_evidence_for_real_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL_CONTENT))
    content = get_content()
    assert content is not None
    app = seeded(tmp_path)
    assert traffic_lights_match_expected(app, content) >= 5
    assert_all_evidence_resolves(app)


def seeded(tmp_path: Path) -> FastAPI:
    from app.main import create_app
    from app.services import seed

    settings = make_settings(tmp_path)
    migrate(settings)
    app = create_app(settings)
    with app.state.session_factory() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
    return app


def test_missing_data_alert_is_created_on_read_and_idempotent(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    for _ in range(3):  # mehrfaches Lesen ⇒ genau eine offene graue Meldung
        row = worklist(doctor)["SYN-0004"]
    assert row["traffic_light"] == "grey"
    assert row["open_alerts"] == 1
    assert row["top_alert"]["rule_id"] == "R-MIS-01"
    assert row["top_alert"]["symptom_key"] is None
    assert row["top_alert"]["headline"] == "Bez odpovědi 6 dní (limit 3)"
    with seeded_app.state.session_factory() as session:
        missing = session.scalars(
            select(Alert).where(
                Alert.rule_id == "R-MIS-01", Alert.patient_id == pid(seeded_app, "SYN-0004")
            )
        ).all()
    assert [(a.level, a.status, a.notified, a.attribute) for a in missing] == [
        ("grey", "open", False, None)
    ]
    detail = doctor.get(f"{BASE}/alerts/{missing[0].id}").json()
    assert detail["explanation"]["kind"] == "missing"
    assert detail["explanation"]["observed"]["days_without_response"] == 6
    assert detail["explanation"]["params"] == {"max_days_without_response": 3}
    assert detail["symptom_key"] is None
    assert any(e.startswith("ther-") for e in detail["explanation"]["evidence"])
    assert any(e.startswith("resp-") for e in detail["explanation"]["evidence"])
    assert detail["headline"] == "Bez odpovědi 6 dní (limit 3)"


def test_parallel_reads_create_exactly_one_missing_alert(seeded_app: FastAPI) -> None:
    clients = [staff(seeded_app) for _ in range(4)]
    results = run_parallel(lambda i: clients[i].get(f"{BASE}/patients"), 4)
    assert [r.status_code for r in results] == [200] * 4
    with seeded_app.state.session_factory() as session:
        open_missing = session.scalars(
            select(Alert).where(Alert.rule_id == "R-MIS-01", Alert.status == "open")
        ).all()
    assert len(open_missing) == 1


def add_response(app: FastAPI, pseudonym: str, answers: dict[tuple[str, str], int | None]) -> None:
    """Fügt am eingefrorenen Jetzt eine Antwort ohne Regelauswertung hinzu (reiner Datenzustand)."""
    with app.state.session_factory() as session:
        row = Response(
            patient_id=pid(app, pseudonym),
            client_submission_id=str(uuid.uuid4()),
            channel="web",
            entered_by="self",
            recorded_at=app.state.clock.now(),
            questionnaire_id="items-v1:FIX-REG",
            synthetic=True,
        )
        session.add(row)
        session.flush()
        for (symptom, attribute), value in answers.items():
            session.add(
                Answer(response_id=row.id, symptom_key=symptom, attribute=attribute, value=value)
            )
        session.commit()


def test_missing_alert_closes_itself_when_data_returns(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    assert worklist(doctor)["SYN-0004"]["traffic_light"] == "grey"
    add_response(seeded_app, "SYN-0004", {("nausea", "severity"): 0, ("fever", "presence"): 0})
    row = worklist(doctor)["SYN-0004"]
    assert row["traffic_light"] == "green"
    assert row["open_alerts"] == 0
    with seeded_app.state.session_factory() as session:
        (alert,) = session.scalars(
            select(Alert).where(
                Alert.rule_id == "R-MIS-01", Alert.patient_id == pid(seeded_app, "SYN-0004")
            )
        )
        actions = session.scalars(select(AlertAction).where(AlertAction.alert_id == alert.id)).all()
    assert alert.status == "acknowledged"
    assert [a.action for a in actions] == ["auto_resolve"]  # keine ärztliche Quittierung
    detail = doctor.get(f"{BASE}/alerts/{alert.id}").json()
    assert detail["acknowledgement"] is None


def test_all_null_response_does_not_count_as_data(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    add_response(
        seeded_app, "SYN-0004", {("nausea", "severity"): None, ("fever", "presence"): None}
    )
    assert worklist(doctor)["SYN-0004"]["traffic_light"] == "grey"  # G-10/G-19


def test_acknowledged_missing_alert_is_held_by_cooldown_but_light_stays_grey(
    seeded_app: FastAPI,
) -> None:
    doctor = staff(seeded_app)
    row = worklist(doctor)["SYN-0004"]
    alert_id = row["top_alert"]["alert_id"]
    ack = doctor.post(f"{BASE}/alerts/{alert_id}/acknowledge", json={"decision": "contact_patient"})
    assert ack.status_code == 200
    row = worklist(doctor)["SYN-0004"]
    assert row["open_alerts"] == 0  # im Cooldown keine neue Meldung
    assert row["traffic_light"] == "grey"  # veraltete Daten sind unbekannt, nie "gut"


def test_acknowledged_alert_that_persists_keeps_the_light_yellow(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    before = worklist(doctor)["SYN-0001"]
    assert before["traffic_light"] == "red"
    alert_id = before["top_alert"]["alert_id"]
    assert (
        doctor.post(
            f"{BASE}/alerts/{alert_id}/acknowledge", json={"decision": "no_action_needed"}
        ).status_code
        == 200
    )
    after = worklist(doctor)["SYN-0001"]
    assert after["open_alerts"] == 0
    assert after["traffic_light"] == "yellow"  # G-02: quittiert, Wert besteht weiter
    assert after["persisting"] is True
    overview = doctor.get(f"{BASE}/patients/{before['patient_id']}/overview").json()
    assert overview["persisting"] is True
    assert [a["alert_id"] for a in overview["persisting_alerts"]] == [alert_id]
    # Wert fällt unter die Schwelle ⇒ Hinweis verschwindet, Ampel wird grün
    add_response(seeded_app, "SYN-0001", {("nausea", "severity"): 1, ("fever", "presence"): 0})
    final = worklist(doctor)["SYN-0001"]
    assert final["persisting"] is False
    assert final["traffic_light"] == "green"


def test_unevaluated_response_makes_the_light_at_least_grey(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    assert worklist(doctor)["SYN-0005"]["traffic_light"] == "green"
    with seeded_app.state.session_factory() as session:
        response = session.scalars(
            select(Response).where(Response.patient_id == pid(seeded_app, "SYN-0005"))
        ).first()
        assert response is not None
        response.evaluation_status = "failed"
        session.commit()
    row = worklist(doctor)["SYN-0005"]
    assert row["traffic_light"] == "grey"
    assert row["evaluation_pending"] is True
    assert row["open_alerts"] == 0
    # eine rote Meldung bleibt rot (nie herabgestuft)
    with seeded_app.state.session_factory() as session:
        response = session.scalars(
            select(Response).where(Response.patient_id == pid(seeded_app, "SYN-0001"))
        ).first()
        assert response is not None
        response.evaluation_status = "failed"
        session.commit()
    assert worklist(doctor)["SYN-0001"]["traffic_light"] == "red"


# --- Übersicht ------------------------------------------------------------------------------


def test_overview_content(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    data = doctor.get(f"{BASE}/patients/{p}/overview", params={"lang": "en"}).json()
    assert data["patient"] == {
        "patient_id": p,
        "pseudonym": "SYN-0001",
        "display_name": "Testpatientin Eins",
        "age": 56,
        "sex": "female",
        "language": "cs",
        "diagnosis_text": "Synthetische Testdiagnose",
        "synthetic": True,
    }
    therapy = data["therapy"]
    assert therapy["fact_id"].startswith("ther-")
    assert therapy["regimen_label"] == "Fixture regimen"
    assert therapy["drugs"] == [{"name": "Fixturdrug", "atc": "L01AA01"}]
    assert therapy["cycle_start"] == "2026-10-11T09:00:00+02:00"
    assert therapy["cycle_day"] == 7
    assert therapy["watch_notes"] == ["Fixture note"]
    assert data["traffic_light"] == "red"
    assert [a["rule_id"] for a in data["open_alerts"]] == ["R-SEV-01"]
    assert data["last_visit_at"] == "2026-10-11T09:00:00+02:00"
    assert data["next_visit_at"] == "2026-11-01T09:00:00+01:00"
    assert data["last_response_at"] == "2026-10-17T08:00:00+02:00"
    summary = data["summary"]  # Demo-Patientin SYN-0001 bekommt beim Seed eine Kurzfassung
    assert summary["mode"] == "fallback"
    assert summary["dropped_sentences"] == 0
    assert summary["sentences"]
    assert data["report_sections"] == ["summary", "alerts", "timeline"]
    assert data["persisting"] is False
    rows = {(r["symptom_key"], r["attribute"]): r for r in data["since_last_visit"]}
    nausea = rows[("nausea", "severity")]
    assert (nausea["first"], nausea["last"], nausea["max"]) == (1, 3, 3)
    assert nausea["direction"] == "up"  # letzter gegen ersten Wert
    assert nausea["alerts"] == 1
    assert nausea["missing_days"] == 4  # Tage -6, -4, -3, -1 ohne Wert
    assert nausea["label"] == "Nausea"
    fever = rows[("fever", "presence")]
    assert (fever["first"], fever["last"], fever["max"], fever["direction"]) == (0, 0, 0, "flat")
    assert fever["missing_days"] == 5  # der übersprungene Wert an Tag -2 ist kein Wert
    (event,) = audits(seeded_app, "view_overview")
    assert (event.target_id, event.subject_id, event.actor_role) == (p, p, "clinician")


def test_overview_direction_follows_last_against_first_value(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    add_response(seeded_app, "SYN-0001", {("nausea", "severity"): 0, ("fever", "presence"): 1})
    data = doctor.get(f"{BASE}/patients/{pid(seeded_app, 'SYN-0001')}/overview").json()
    by_key = {(r["symptom_key"], r["attribute"]): r for r in data["since_last_visit"]}
    assert by_key[("nausea", "severity")]["direction"] == "down"  # erster Wert 1, letzter 0
    assert by_key[("fever", "presence")]["direction"] == "up"  # 0 ... 1


@pytest.mark.parametrize(
    ("values", "expected"),
    [([], "unknown"), ([2], "unknown"), ([1, 3], "up"), ([3, 1], "down"), ([2, 5, 2], "flat")],
)
def test_direction_rule(values: list[int], expected: str) -> None:
    from waechter.services.patient_views import _direction

    assert _direction(values) == expected


# --- Verlauf --------------------------------------------------------------------------------


def test_timeline_default_range_series_gaps_and_missing_days(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    data = doctor.get(f"{BASE}/patients/{p}/timeline").json()
    assert data["from"] == "2026-10-11T09:00:00+02:00"  # Zyklusbeginn
    assert data["to"] == "2026-10-17T09:00:00+02:00"  # server_now
    series = {(s["symptom_key"], s["attribute"]): s for s in data["series"]}
    nausea = series[("nausea", "severity")]
    assert [pt["value"] for pt in nausea["points"]] == [1, 2, 3]
    assert [pt["t"][:10] for pt in nausea["points"]] == ["2026-10-12", "2026-10-15", "2026-10-17"]
    fever = series[("fever", "presence")]
    assert [pt["value"] for pt in fever["points"]] == [0, None, 0]  # Lücke bleibt sichtbar
    assert all(pt["fact_id"].startswith("obs-") for s in data["series"] for pt in s["points"])
    assert [a["rule_id"] for a in data["alerts"]] == ["R-SEV-01"]
    assert data["missing_days"] == ["2026-10-11", "2026-10-13", "2026-10-14", "2026-10-16"]
    assert [v["kind"] for v in data["visits"]] == ["past"]  # geplanter Termin liegt nach `to`
    assert data["assessments"] == []
    (event,) = data["therapy_events"]
    assert event["fact_id"].startswith("ther-")
    assert event["label"] == "Začátek cyklu: Testovací režim"
    assert len(audits(seeded_app, "view_timeline")) == 1


def test_timeline_range_filter_and_validation(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    url = f"{BASE}/patients/{pid(seeded_app, 'SYN-0001')}/timeline"
    narrow = doctor.get(
        url, params={"from": "2026-10-14T00:00:00+02:00", "to": "2026-10-16T00:00:00+02:00"}
    ).json()
    values = {
        (s["symptom_key"], s["attribute"]): [p["value"] for p in s["points"]]
        for s in narrow["series"]
    }
    assert values[("nausea", "severity")] == [2]
    assert narrow["alerts"] == []
    assert narrow["missing_days"] == ["2026-10-14", "2026-10-16"]
    assert narrow["therapy_events"] == []
    naive = doctor.get(url, params={"from": "2026-10-14T00:00:00"})
    assert naive.status_code == 422
    assert naive.json()["code"] == "validation_failed"
    backwards = doctor.get(
        url, params={"from": "2026-10-16T00:00:00+02:00", "to": "2026-10-14T00:00:00+02:00"}
    )
    assert backwards.status_code == 422
    assert doctor.get(url, params={"from": "gestern"}).status_code == 422


def test_timeline_range_missing_days_are_exact(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    url = f"{BASE}/patients/{pid(seeded_app, 'SYN-0001')}/timeline"
    narrow = doctor.get(
        url, params={"from": "2026-10-13T00:00:00+02:00", "to": "2026-10-16T23:00:00+02:00"}
    ).json()
    # Antworten an Tag 15 (Wert 2); fehlend: 13., 14., 16.; heute (17.) zählt nicht
    assert narrow["missing_days"] == ["2026-10-13", "2026-10-14", "2026-10-16"]


# --- Belege ---------------------------------------------------------------------------------


def assert_all_evidence_resolves(app: FastAPI) -> int:
    doctor = staff(app)
    resolved = 0
    for row in doctor.get(f"{BASE}/patients").json():
        patient = row["patient_id"]
        timeline = doctor.get(f"{BASE}/patients/{patient}/timeline").json()
        overview = doctor.get(f"{BASE}/patients/{patient}/overview").json()
        ids: set[str] = set()
        for alert in timeline["alerts"] + overview["open_alerts"]:
            ids.update(alert["explanation"]["evidence"])
            ids.add(f"alert-{alert['alert_id']}")
        ids.update(pt["fact_id"] for s in timeline["series"] for pt in s["points"])
        ids.update(v["fact_id"] for v in timeline["visits"])
        ids.update(e["fact_id"] for e in timeline["therapy_events"])
        ids.add(overview["therapy"]["fact_id"])
        for fact_id in sorted(ids):
            response = doctor.get(f"{BASE}/patients/{patient}/facts/{fact_id}")
            assert response.status_code == 200, (fact_id, response.text)
            fact = response.json()
            assert fact["fact_id"] == fact_id
            assert set(fact) == {"fact_id", "kind", "at", "label", "data"}
            resolved += 1
    return resolved


def test_every_evidence_id_is_resolvable(seeded_app: FastAPI) -> None:
    staff(seeded_app).get(f"{BASE}/patients")  # R-MIS-01 anlegen
    assert assert_all_evidence_resolves(seeded_app) > 30


def test_fact_kinds_and_content(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    timeline = doctor.get(f"{BASE}/patients/{p}/timeline").json()
    alert = timeline["alerts"][0]
    resp_id = next(e for e in alert["explanation"]["evidence"] if e.startswith("resp-"))
    obs_id = next(e for e in alert["explanation"]["evidence"] if e.startswith("obs-"))
    url = f"{BASE}/patients/{p}/facts"
    resp = doctor.get(f"{url}/{resp_id}").json()
    assert resp["kind"] == "response"
    assert resp["at"] == "2026-10-17T08:00:00+02:00"
    assert {a["symptom_key"] for a in resp["data"]["answers"]} == {"nausea", "fever"}
    obs = doctor.get(f"{url}/{obs_id}").json()
    assert obs["kind"] == "observation"
    assert obs["label"] == "Nevolnost (severity): 3"
    assert obs["data"]["response_fact_id"] == resp_id
    skipped = next(pt for s in timeline["series"] for pt in s["points"] if pt["value"] is None)[
        "fact_id"
    ]
    assert "přeskočeno" in doctor.get(f"{url}/{skipped}").json()["label"]
    assert doctor.get(f"{url}/alert-{alert['alert_id']}").json()["kind"] == "alert"
    visit = timeline["visits"][0]["fact_id"]
    assert doctor.get(f"{url}/{visit}").json()["kind"] == "visit"
    ther = timeline["therapy_events"][0]["fact_id"]
    fact = doctor.get(f"{url}/{ther}", params={"lang": "en"}).json()
    assert (fact["kind"], fact["label"]) == ("therapy", "Fixture regimen")


def test_foreign_unknown_and_malformed_facts_are_404(seeded_app: FastAPI) -> None:
    doctor = staff(seeded_app)
    mine = pid(seeded_app, "SYN-0001")
    other = pid(seeded_app, "SYN-0002")
    timeline = doctor.get(f"{BASE}/patients/{mine}/timeline").json()
    foreign = timeline["series"][0]["points"][0]["fact_id"]
    assert doctor.get(f"{BASE}/patients/{mine}/facts/{foreign}").status_code == 200
    assert doctor.get(f"{BASE}/patients/{other}/facts/{foreign}").status_code == 404
    for bad in (
        f"obs-{uuid.uuid4()}",
        f"resp-{uuid.uuid4()}",
        "alert-nope",
        "assess-123",
        "xyz-1",
        "resp-",
        "resp-a_b",
        "RESP-1",
    ):
        assert doctor.get(f"{BASE}/patients/{mine}/facts/{bad}").status_code == 404, bad


# --- /meta (DR-009) -------------------------------------------------------------------------


def test_meta_exposes_server_now_timezone_and_versions(seeded_app: FastAPI) -> None:
    with TestClient(seeded_app) as client:
        meta = client.get("/api/v1/meta").json()
    assert meta["waechter"] == {
        "server_now": "2026-10-17T09:00:00+02:00",  # exakt der Anker (APP_FROZEN_NOW)
        "timezone": "Europe/Prague",
        "content_versions": {"items": "items-v1", "rules": "rules-v1", "report": "report-v1"},
        "free_text": {"enabled": True, "max_length": 500},  # T-22 (Demo: Freitext an)
    }


def test_meta_without_frozen_clock_uses_the_current_time(tmp_path: Path) -> None:
    settings = make_settings(tmp_path).model_copy(update={"app_frozen_now": None})
    before = datetime.now(UTC).replace(microsecond=0)
    value = waechter_meta(settings)["waechter"]["server_now"]
    after = datetime.now(UTC) + timedelta(seconds=1)
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert before <= parsed <= after
    assert value == iso_prague(parsed)
    assert to_prague(parsed).utcoffset() == parsed.utcoffset()


def test_meta_versions_are_null_without_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(tmp_path / "missing"))
    meta = waechter_meta(make_settings(tmp_path))["waechter"]
    assert meta["content_versions"] == {"items": None, "rules": None, "report": None}
