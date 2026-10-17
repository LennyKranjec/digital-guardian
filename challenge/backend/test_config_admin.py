"""Versionierte Konfiguration (T-09): PUT /config/rules|report, Historie, aktive Version."""

import copy
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.persistence.models import AuditEvent
from conftest import CSRF, login, run_parallel
from waechter.models import Alert, ConfigVersion, Patient

BASE = "/api/v1/waechter"
RESPONSES = f"{BASE}/me/responses"
MARKER = "PURPLE-4711"


def client_for(app: FastAPI, username: str) -> TestClient:
    client = TestClient(app, headers=CSRF)
    login(client, username)
    return client


def current_rules(app: FastAPI) -> tuple[str, dict[str, Any]]:
    admin = client_for(app, "admin")
    rules = admin.get(f"{BASE}/config").json()["rules"]
    version = rules.pop("version")
    return version, rules


def current_report(app: FastAPI) -> tuple[str, dict[str, Any]]:
    report = client_for(app, "admin").get(f"{BASE}/config").json()["report"]
    version = report.pop("version")
    return version, report


def put_rules(
    client: TestClient, version: str, rules: dict[str, Any], note: str | None = None
) -> Any:
    body: dict[str, Any] = {"expected_version": version, "rules": rules}
    if note is not None:
        body["change_note"] = note
    return client.put(f"{BASE}/config/rules", json=body)


def with_threshold(rules: dict[str, Any], rule_id: str, value: float) -> dict[str, Any]:
    changed = copy.deepcopy(rules)
    next(r for r in changed["rules"] if r["id"] == rule_id)["params"]["min_value"] = value
    return changed


def alerts_of(app: FastAPI, pseudonym: str, rule: str) -> list[Alert]:
    with app.state.session_factory() as session:
        pid = session.scalars(select(Patient.id).where(Patient.pseudonym == pseudonym)).one()
        return list(
            session.scalars(
                select(Alert)
                .where(Alert.patient_id == pid, Alert.rule_id == rule)
                .order_by(Alert.created_at, Alert.id)
            )
        )


def submit(client: TestClient, answers: list[tuple[str, str, int]]) -> None:
    payload = {
        "client_submission_id": str(uuid.uuid4()),
        "questionnaire_id": "items-v1:FIX-REG",
        "answers": [{"symptom_key": s, "attribute": a, "value": v} for s, a, v in answers],
    }
    assert client.post(RESPONSES, json=payload).status_code == 201


def audits(app: FastAPI) -> list[AuditEvent]:
    with app.state.session_factory() as session:
        return list(session.scalars(select(AuditEvent).where(AuditEvent.action == "config_change")))


def versions(app: FastAPI, kind: str) -> list[str]:
    with app.state.session_factory() as session:
        rows = session.scalars(select(ConfigVersion).where(ConfigVersion.kind == kind)).all()
        return sorted(r.version for r in rows)


# --- Zugriff --------------------------------------------------------------------------------


def test_anonymous_gets_401(seeded_app: FastAPI) -> None:
    anon = TestClient(seeded_app, headers=CSRF)
    assert anon.put(f"{BASE}/config/rules", json={}).status_code == 401
    assert anon.put(f"{BASE}/config/report", json={}).status_code == 401
    assert anon.get(f"{BASE}/config/history", params={"kind": "rules"}).status_code == 401


@pytest.mark.parametrize("username", ["doctor", "patient", "user"])
def test_only_admin_may_change_the_configuration(seeded_app: FastAPI, username: str) -> None:
    version, rules = current_rules(seeded_app)
    other = client_for(seeded_app, username)
    assert put_rules(other, version, with_threshold(rules, "R-SEV-01", 4)).status_code == 403
    report = other.put(
        f"{BASE}/config/report",
        json={"expected_version": "report-v1", "report": {"sections": ["summary"]}},
    )
    assert report.status_code == 403
    assert versions(seeded_app, "rules") == ["rules-v1"]
    assert versions(seeded_app, "report") == ["report-v1"]
    assert audits(seeded_app) == []


def test_history_is_visible_to_staff_only(seeded_app: FastAPI) -> None:
    for username, expected in (("doctor", 200), ("admin", 200), ("patient", 403), ("user", 403)):
        client = client_for(seeded_app, username)
        assert (
            client.get(f"{BASE}/config/history", params={"kind": "rules"}).status_code == expected
        )


@pytest.mark.parametrize("params", [{}, {"kind": "items"}, {"kind": "RULES"}])
def test_history_needs_a_valid_kind(seeded_app: FastAPI, params: dict[str, str]) -> None:
    admin = client_for(seeded_app, "admin")
    assert admin.get(f"{BASE}/config/history", params=params).status_code == 422


def test_put_needs_csrf_header(seeded_app: FastAPI) -> None:
    version, rules = current_rules(seeded_app)
    admin = client_for(seeded_app, "admin")
    bare = TestClient(seeded_app)
    bare.cookies.update(admin.cookies)
    assert put_rules(bare, version, rules).status_code == 403


# --- Änderung -------------------------------------------------------------------------------


def test_update_creates_the_next_version_and_activates_it(seeded_app: FastAPI) -> None:
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    assert version == "rules-v1"
    response = put_rules(admin, version, with_threshold(rules, "R-SEV-01", 4), "Schwelle auf 4")
    assert response.status_code == 200, response.text
    state = response.json()
    assert state == {
        "version": "rules-v2",
        "changed_at": "2026-10-17T09:00:00+02:00",
        "changed_by": "Admin (Demo)",
        "change_note": "Schwelle auf 4",
    }
    config = admin.get(f"{BASE}/config").json()
    assert config["rules"]["version"] == "rules-v2"
    sev = next(r for r in config["rules"]["rules"] if r["id"] == "R-SEV-01")
    assert sev["params"]["min_value"] == 4
    meta = TestClient(seeded_app).get("/api/v1/meta").json()
    assert meta["waechter"]["content_versions"]["rules"] == "rules-v2"  # /meta aus der DB
    assert meta["waechter"]["content_versions"]["report"] == "report-v1"
    history = admin.get(f"{BASE}/config/history", params={"kind": "rules"}).json()
    assert [(h["version"], h["active"]) for h in history] == [
        ("rules-v2", True),
        ("rules-v1", False),
    ]
    assert history[0]["changed_by"] == "Admin (Demo)"
    assert history[0]["change_note"] == "Schwelle auf 4"
    assert history[1]["changed_by"] == "system"  # Startversion aus der Datei
    assert history[1]["change_note"] == "seed"
    assert set(history[0]) == {"version", "changed_at", "changed_by", "change_note", "active"}


def test_clinician_sees_the_active_version_in_config_and_history(seeded_app: FastAPI) -> None:
    version, rules = current_rules(seeded_app)
    put_rules(client_for(seeded_app, "admin"), version, with_threshold(rules, "R-SEV-01", 4))
    doctor = client_for(seeded_app, "doctor")
    assert doctor.get(f"{BASE}/config").json()["rules"]["version"] == "rules-v2"
    assert len(doctor.get(f"{BASE}/config/history", params={"kind": "rules"}).json()) == 2


def test_versions_count_up_and_each_change_is_audited_without_values(seeded_app: FastAPI) -> None:
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    assert (
        put_rules(admin, version, with_threshold(rules, "R-SEV-01", 4), "geheime Notiz").status_code
        == 200
    )
    assert (
        put_rules(admin, "rules-v2", with_threshold(rules, "R-SEV-01", 2)).json()["version"]
        == "rules-v3"
    )
    events = audits(seeded_app)
    assert len(events) == 2
    details = sorted((e.details_json["from"], e.details_json["to"]) for e in events)
    assert details == [("rules-v1", "rules-v2"), ("rules-v2", "rules-v3")]
    first = next(e for e in events if e.details_json["to"] == "rules-v2")
    assert first.details_json == {
        "kind": "rules",
        "from": "rules-v1",
        "to": "rules-v2",
        "note_length": len("geheime Notiz"),
    }
    assert first.actor_role == "admin"
    assert "geheime" not in str([e.details_json for e in events])


def test_wrong_expected_version_is_409_and_changes_nothing(seeded_app: FastAPI) -> None:
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    for stale in ("rules-v0", "rules-v2", "report-v1", "x"):
        response = put_rules(admin, stale, with_threshold(rules, "R-SEV-01", 4))
        assert response.status_code == 409, stale
        assert response.json()["code"] == "version_conflict"
    assert put_rules(admin, version, with_threshold(rules, "R-SEV-01", 4)).status_code == 200
    again = put_rules(admin, version, with_threshold(rules, "R-SEV-01", 2))  # jetzt veraltet
    assert again.status_code == 409
    assert versions(seeded_app, "rules") == ["rules-v1", "rules-v2"]
    assert len(audits(seeded_app)) == 1


def test_four_parallel_updates_with_the_same_expected_version_yield_one_success(
    seeded_app: FastAPI,
) -> None:
    version, rules = current_rules(seeded_app)
    admins = [client_for(seeded_app, "admin") for _ in range(4)]
    results = run_parallel(
        lambda i: put_rules(admins[i], version, with_threshold(rules, "R-SEV-01", 4), f"n{i}"), 4
    )
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409], [
        (r.status_code, r.text) for r in results
    ]
    assert {r.json()["code"] for r in results if r.status_code == 409} == {"version_conflict"}
    assert versions(seeded_app, "rules") == ["rules-v1", "rules-v2"]
    with seeded_app.state.session_factory() as session:
        active = session.scalars(
            select(ConfigVersion).where(
                ConfigVersion.kind == "rules", ConfigVersion.active.is_(True)
            )
        ).all()
    assert [a.version for a in active] == ["rules-v2"]  # genau eine aktive Version
    assert len(audits(seeded_app)) == 1


# --- Wirkung auf die Regel-Engine -----------------------------------------------------------


def test_threshold_change_applies_to_new_responses_only(seeded_app: FastAPI) -> None:
    patient = client_for(seeded_app, "patient2")
    admin = client_for(seeded_app, "admin")
    doctor = client_for(seeded_app, "doctor")
    submit(patient, [("nausea", "severity", 3)])
    (old,) = alerts_of(seeded_app, "SYN-0002", "R-SEV-01")
    assert old.rule_version == "rules-v1"
    version, rules = current_rules(seeded_app)
    assert put_rules(admin, version, with_threshold(rules, "R-SEV-01", 4)).status_code == 200
    submit(patient, [("nausea", "severity", 4)])  # 4 ≥ neue Schwelle, höher als 3 ⇒ neue Meldung
    alerts = alerts_of(seeded_app, "SYN-0002", "R-SEV-01")
    assert sorted(a.rule_version for a in alerts) == ["rules-v1", "rules-v2"]
    assert doctor.get(f"{BASE}/alerts/{old.id}").json()["rule_version"] == "rules-v1"  # bleibt
    newest = next(a for a in alerts if a.rule_version == "rules-v2")
    detail = doctor.get(f"{BASE}/alerts/{newest.id}").json()
    assert detail["rule_version"] == "rules-v2"
    assert detail["explanation"]["params"]["min_value"] == 4


def test_the_same_answer_creates_no_alert_after_raising_the_threshold(
    seeded_app: FastAPI,
) -> None:
    version, rules = current_rules(seeded_app)
    put_rules(client_for(seeded_app, "admin"), version, with_threshold(rules, "R-SEV-01", 4))
    submit(client_for(seeded_app, "patient2"), [("nausea", "severity", 3)])
    assert alerts_of(seeded_app, "SYN-0002", "R-SEV-01") == []


def test_disabling_a_rule_stops_its_alerts(seeded_app: FastAPI) -> None:
    version, rules = current_rules(seeded_app)
    changed = copy.deepcopy(rules)
    next(r for r in changed["rules"] if r["id"] == "R-URG-01")["enabled"] = False
    assert put_rules(client_for(seeded_app, "admin"), version, changed).status_code == 200
    submit(client_for(seeded_app, "patient2"), [("fever", "presence", 1)])
    assert alerts_of(seeded_app, "SYN-0002", "R-URG-01") == []


def test_report_change_is_versioned_and_shown_in_the_overview(seeded_app: FastAPI) -> None:
    admin = client_for(seeded_app, "admin")
    version, _ = current_report(seeded_app)
    assert version == "report-v1"
    changed = {"since": "days_14", "sections": ["summary", "alerts", "audit"]}
    response = admin.put(
        f"{BASE}/config/report",
        json={"expected_version": version, "report": changed, "change_note": "mit Audit"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["version"] == "report-v2"
    config = admin.get(f"{BASE}/config").json()
    assert config["report"] == {"version": "report-v2", **changed}
    with seeded_app.state.session_factory() as session:
        pid = session.scalars(select(Patient.id).where(Patient.pseudonym == "SYN-0001")).one()
    overview = client_for(seeded_app, "doctor").get(f"{BASE}/patients/{pid}/overview").json()
    assert overview["report_sections"] == ["summary", "alerts", "audit"]
    assert (
        TestClient(seeded_app).get("/api/v1/meta").json()["waechter"]["content_versions"]["report"]
        == "report-v2"
    )
    history = admin.get(f"{BASE}/config/history", params={"kind": "report"}).json()
    assert [h["version"] for h in history] == ["report-v2", "report-v1"]
    stale = admin.put(
        f"{BASE}/config/report", json={"expected_version": version, "report": changed}
    )
    assert stale.status_code == 409
    assert versions(seeded_app, "rules") == ["rules-v1"]  # Regeln unberührt


# --- Validierung ----------------------------------------------------------------------------


def error_fields(response: Any) -> set[tuple[str, str]]:
    return {(e["field"], e["code"]) for e in response.json()["field_errors"]}


def assert_rejected(app: FastAPI, response: Any, code: str) -> None:
    assert response.status_code == 422, response.text
    assert response.json()["code"] == code
    assert MARKER not in response.text  # nie Werte in der Fehlermeldung
    assert versions(app, "rules") == ["rules-v1"]  # nichts gespeichert, nichts aktiviert
    assert audits(app) == []


def test_no_red_rule_is_rejected(seeded_app: FastAPI) -> None:
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    disabled = copy.deepcopy(rules)
    for rule in disabled["rules"]:
        if rule["level"] == "red":
            rule["enabled"] = False
    response = put_rules(admin, version, disabled)
    assert_rejected(seeded_app, response, "no_red_rule")
    demoted = copy.deepcopy(rules)
    for rule in demoted["rules"]:
        if rule["level"] == "red":
            rule["level"] = "yellow"
    assert_rejected(seeded_app, put_rules(admin, version, demoted), "no_red_rule")


def test_red_rule_that_cannot_trigger_does_not_count_as_red_rule(seeded_app: FastAPI) -> None:
    """T-09F: eine rote Regel jenseits der Antwortskala (presence <= 1) ist nicht aktiv rot."""
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    only_fever = copy.deepcopy(rules)
    for rule in only_fever["rules"]:
        if rule["id"] == "R-SEV-01":
            rule["enabled"] = False
    only_fever = with_threshold(only_fever, "R-URG-01", 2)  # presence kennt nur 0/1
    assert_rejected(seeded_app, put_rules(admin, version, only_fever), "no_red_rule")
    reachable = with_threshold(only_fever, "R-URG-01", 1)
    assert put_rules(admin, version, reachable).status_code == 200


@pytest.mark.parametrize(
    ("rule_id", "name", "value"),
    [
        ("R-SEV-01", "min_value", 5),  # jenseits der Skala 0-4
        ("R-SEV-01", "min_value", 99),
        ("R-DLT-01", "min_delta", 5),
        ("R-DLT-01", "baseline_days", 0),
        ("R-DLT-01", "baseline_days", 4000),
        ("R-TRD-01", "target_value", 7),
        ("R-TRD-01", "window_days", 2),  # kleiner als min_points
        ("R-MIS-01", "max_days_without_response", 0),
    ],
)
def test_parameters_outside_plausible_ranges_are_rejected(
    seeded_app: FastAPI, rule_id: str, name: str, value: float
) -> None:
    version, rules = current_rules(seeded_app)
    changed = copy.deepcopy(rules)
    next(r for r in changed["rules"] if r["id"] == rule_id)["params"][name] = value
    response = put_rules(client_for(seeded_app, "admin"), version, changed)
    assert_rejected(seeded_app, response, "validation_failed")
    assert any(e["field"].endswith(f"params.{name}") for e in response.json()["field_errors"])


def test_red_alerts_must_stay_notified(seeded_app: FastAPI) -> None:
    version, rules = current_rules(seeded_app)
    silent = copy.deepcopy(rules)
    silent["noise"]["notify_levels"] = ["yellow"]
    response = put_rules(client_for(seeded_app, "admin"), version, silent)
    assert_rejected(seeded_app, response, "no_red_notification")
    loud = copy.deepcopy(rules)
    loud["noise"]["notify_levels"] = ["red", "yellow"]
    assert put_rules(client_for(seeded_app, "admin"), version, loud).status_code == 200


@pytest.mark.parametrize(
    ("label", "change", "field", "code"),
    [
        (
            "missing rationale",
            lambda r: r["rules"][0].pop("rationale"),
            "rules.rules[0].rationale",
            "invalid",
        ),
        (
            "bad level",
            lambda r: r["rules"][0].update(level=MARKER),
            "rules.rules[0].level",
            "invalid",
        ),
        ("bad kind", lambda r: r["rules"][0].update(kind=MARKER), "rules.rules[0].kind", "invalid"),
        (
            "extra field",
            lambda r: r["rules"][0].update(surprise=1),
            "rules.rules[0].surprise",
            "invalid",
        ),
        ("bad id", lambda r: r["rules"][0].update(id="sev-1"), "rules.rules[0].id", "invalid"),
        (
            "string param",
            lambda r: r["rules"][0]["params"].update(min_value="3"),
            "rules.rules[0].params.min_value",
            "invalid",
        ),
        (
            "missing param",
            lambda r: r["rules"][0]["params"].pop("min_value"),
            "rules.rules[0].params.min_value",
            "required",
        ),
        (
            "negative threshold",
            lambda r: r["rules"][0]["params"].update(min_value=-1),
            "rules.rules[0].params.min_value",
            "out_of_range",
        ),
        (
            "zero baseline window",
            lambda r: next(x for x in r["rules"] if x["kind"] == "baseline_delta")["params"].update(
                baseline_days=0
            ),
            "rules.rules[2].params.baseline_days",
            "out_of_range",
        ),
        (
            "single-point trend",
            lambda r: next(x for x in r["rules"] if x["kind"] == "trend")["params"].update(
                min_points=1
            ),
            "rules.rules[3].params.min_points",
            "out_of_range",
        ),
        (
            "unknown symptom",
            lambda r: r["rules"][1].update(symptom_keys=["headache"]),
            "rules.rules[1].symptom_keys[0]",
            "unknown_symptom",
        ),
        (
            "duplicate id",
            lambda r: r["rules"][1].update(id=r["rules"][0]["id"]),
            "rules.rules[1].id",
            "duplicate_id",
        ),
        ("no rules", lambda r: r.update(rules=[]), "rules.rules", "invalid"),
        ("no noise", lambda r: r.pop("noise"), "rules.noise", "invalid"),
        (
            "negative cooldown",
            lambda r: r["noise"].update(cooldown_hours=-1),
            "rules.noise.cooldown_hours",
            "invalid",
        ),
    ],
)
def test_invalid_rules_are_422_with_a_field_path_and_store_nothing(
    seeded_app: FastAPI, label: str, change: Any, field: str, code: str
) -> None:
    version, rules = current_rules(seeded_app)
    broken = copy.deepcopy(rules)
    change(broken)
    response = put_rules(client_for(seeded_app, "admin"), version, broken)
    assert_rejected(seeded_app, response, "validation_failed")
    assert (field, code) in error_fields(response), (label, error_fields(response))


def test_the_server_assigns_the_version(seeded_app: FastAPI) -> None:
    version, rules = current_rules(seeded_app)
    response = put_rules(
        client_for(seeded_app, "admin"), version, {"version": "rules-v99", **rules}
    )
    assert_rejected(seeded_app, response, "validation_failed")
    assert ("rules.version", "not_allowed") in error_fields(response)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"expected_version": "rules-v1"},
        {"rules": {}},
        {"expected_version": "", "rules": {}},
        {"expected_version": "rules-v1", "rules": {}, "surprise": 1},
        {"expected_version": "rules-v1", "rules": [], "change_note": "x"},
        {"expected_version": "rules-v1", "rules": {}, "change_note": "x" * 301},
    ],
)
def test_malformed_bodies_are_422(seeded_app: FastAPI, body: dict[str, Any]) -> None:
    response = client_for(seeded_app, "admin").put(f"{BASE}/config/rules", json=body)
    assert response.status_code == 422
    assert versions(seeded_app, "rules") == ["rules-v1"]


def test_note_of_300_characters_is_accepted(seeded_app: FastAPI) -> None:
    version, rules = current_rules(seeded_app)
    response = put_rules(
        client_for(seeded_app, "admin"), version, with_threshold(rules, "R-SEV-01", 4), "x" * 300
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "report",
    [
        {"sections": ["summary", "bogus"]},
        {"sections": "summary"},
        {"since": "forever", "sections": ["summary"]},
        {"sections": ["summary"], "extra": 1},
        {"since": "days_14"},
        {"version": "report-v9", "sections": ["summary"]},
    ],
)
def test_invalid_report_is_422(seeded_app: FastAPI, report: dict[str, Any]) -> None:
    response = client_for(seeded_app, "admin").put(
        f"{BASE}/config/report", json={"expected_version": "report-v1", "report": report}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert versions(seeded_app, "report") == ["report-v1"]
