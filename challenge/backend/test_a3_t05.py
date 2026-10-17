# ruff: noqa: S311, F401, F811
"""A3-Gegenproben zu T-05 (Besitz A3): Ampel/R-MIS-01 an Tagesgrenzen, Verlauf und Übersicht gegen
unabhängige Neuberechnung aus den Rohdaten, Sortierung, Audit, Sicherheitsfragen zu `persisting`.

Hilfen/Fixtures aus `test_a3_t04a.py`/`test_a3_t04b.py`; Kalendertage über das unabhängige Orakel.
"""

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.persistence.models import AuditEvent
from conftest import CSRF, login
from test_a3_realcontent import _load_oracle
from test_a3_t04a import MutableClock, alerts_of, live, mailbox, post, seeded_template
from test_a3_t04b import BASE, ack, staff
from waechter.models import Alert, AlertAction, Answer, Patient, Response

ORACLE: Any = _load_oracle()


ANCHOR = datetime(2026, 10, 17, 7, 0, tzinfo=UTC)  # 09:00 Prager Zeit, Anker des Szenarios


def at_anchor(live_tuple: Any) -> Any:
    """Uhr auf den Szenario-Anker setzen (die Seed-Daten liegen relativ zu ihm)."""
    live_tuple[2].instant = ANCHOR
    return live_tuple


def local_date(instant: datetime) -> date:
    """Prager Kalendertag (unabhängige EU-Regel des Orakels)."""
    utc = instant.astimezone(UTC)
    shifted: datetime = utc + ORACLE.prague_offset(utc)
    return shifted.date()


def doctor_get(app: FastAPI, path: str, **params: Any) -> Any:
    with TestClient(app, headers=CSRF) as client:
        login(client, "doctor")
        return client.get(f"{BASE}{path}", params=params)


def patient_id(app: FastAPI, pseudonym: str = "SYN-0002") -> str:
    with app.state.session_factory() as session:
        found: str = session.scalars(select(Patient.id).where(Patient.pseudonym == pseudonym)).one()
        return found


def missing_alert_open(app: FastAPI, pseudonym: str = "SYN-0002") -> bool:
    open_alerts = doctor_get(
        app, f"/patients/{patient_id(app, pseudonym)}/alerts", status="open"
    ).json()
    return any(a["rule_id"] == "R-MIS-01" for a in open_alerts)


def row_of(app: FastAPI, pseudonym: str = "SYN-0002") -> dict[str, Any]:
    rows = doctor_get(app, "/patients").json()
    return next(r for r in rows if r["pseudonym"] == pseudonym)


# --- Rechte ---


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
@pytest.mark.parametrize("kind", ["worklist", "overview", "timeline", "fact"])
def test_a3_t05_role_matrix(live: Any, kind: str, username: str | None, expected: int) -> None:
    app, client, _ = at_anchor(live)
    pid = patient_id(app)
    post(client, [("nausea", "severity", 2)])
    with app.state.session_factory() as session:
        answer = session.scalars(select(Answer).limit(1)).one()
    paths = {
        "worklist": f"{BASE}/patients",
        "overview": f"{BASE}/patients/{pid}/overview",
        "timeline": f"{BASE}/patients/{pid}/timeline",
        "fact": f"{BASE}/patients/{pid}/facts/obs-{answer.id}",
    }
    with TestClient(app, headers=CSRF) as other:
        if username:
            login(other, username)
        response = other.get(paths[kind])
    if kind == "fact" and expected == 200:
        assert response.status_code in (
            200,
            404,
        )  # beliebige Antwort kann zu anderer Patientin gehören
    else:
        assert response.status_code == expected, response.text
    if expected != 200:
        assert set(response.json()) >= {"code", "message"}
        assert "display_name" not in response.text  # kein Datenleck im Fehlerfall


def test_a3_t05_facts_never_cross_patients_and_bad_ids_are_404(live: Any) -> None:
    app, client, _ = at_anchor(live)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    mine, other = patient_id(app, "SYN-0002"), patient_id(app, "SYN-0001")
    with app.state.session_factory() as session:
        my_answer = session.scalars(
            select(Answer)
            .join(Response, Response.id == Answer.response_id)
            .where(Response.patient_id == mine)
        ).first()
        my_resp = session.scalars(select(Response).where(Response.patient_id == mine)).first()
        their_alert = session.scalars(select(Alert).where(Alert.patient_id == other)).first()
    assert my_answer is not None
    assert my_resp is not None
    assert their_alert is not None
    with TestClient(app, headers=CSRF) as doctor:
        login(doctor, "doctor")

        def get(pid: str, fid: str) -> Any:
            return doctor.get(f"{BASE}/patients/{pid}/facts/{fid}")

        assert get(mine, f"obs-{my_answer.id}").status_code == 200
        assert get(other, f"obs-{my_answer.id}").status_code == 404  # Beleg einer anderen Patientin
        assert get(other, f"resp-{my_resp.id}").status_code == 404
        assert get(mine, f"alert-{their_alert.id}").status_code == 404
        for bad in (
            "",
            "obs-",
            "xyz-1",
            "obs-%2e%2e",
            "OBS-1",
            "obs-a b",
            "obs-" + "a" * 400,
            "obs--",
        ):
            assert get(mine, bad).status_code in (404, 405), bad
        assert get("nope", f"obs-{my_answer.id}").status_code == 404


# --- Ampel/R-MIS-01 an Tagesgrenzen (Kalendertage in Prag, G-04/G-19) ---

DAY_CASES = [
    # (letzte Antwort UTC, jetzt UTC): Sommerzeit, Mitternachtsgrenze, Zeitumstellung 25.10.2026
    (datetime(2026, 10, 20, 21, 50, tzinfo=UTC), datetime(2026, 10, 23, 21, 59, tzinfo=UTC)),
    (datetime(2026, 10, 20, 21, 50, tzinfo=UTC), datetime(2026, 10, 23, 22, 10, tzinfo=UTC)),
    (datetime(2026, 10, 20, 21, 50, tzinfo=UTC), datetime(2026, 10, 24, 21, 59, tzinfo=UTC)),
    (datetime(2026, 10, 24, 23, 30, tzinfo=UTC), datetime(2026, 10, 28, 22, 30, tzinfo=UTC)),
    (datetime(2026, 10, 24, 23, 30, tzinfo=UTC), datetime(2026, 10, 28, 23, 30, tzinfo=UTC)),
    (datetime(2026, 10, 24, 12, 0, tzinfo=UTC), datetime(2026, 10, 27, 23, 30, tzinfo=UTC)),
    (datetime(2026, 10, 25, 0, 30, tzinfo=UTC), datetime(2026, 10, 28, 22, 59, tzinfo=UTC)),
]


@pytest.mark.parametrize(("last", "now"), DAY_CASES)
def test_a3_missing_data_uses_prague_calendar_days(
    live: Any, last: datetime, now: datetime
) -> None:
    app, client, clock = at_anchor(live)
    clock.instant = last
    assert post(client, [("nausea", "severity", 0), ("fever", "presence", 0)]).status_code == 201
    expected_days = (local_date(now) - local_date(last)).days
    clock.instant = now
    row = row_of(app)
    overview = doctor_get(app, f"/patients/{patient_id(app)}/overview").json()
    assert row["traffic_light"] == overview["traffic_light"]
    assert overview["days_without_response"] == expected_days, (last, now)
    # R-MIS-01: höchstens 3 Tage; SYN-0002 hat zusätzlich eine offene gelbe Seed-Meldung
    assert missing_alert_open(app) == (expected_days > 3), (last, now, expected_days)
    assert row["traffic_light"] == "yellow"  # Fixture-Seed: offene gelbe Meldung bleibt maßgeblich
    missing = [a for a in overview["open_alerts"] if a["rule_id"] == "R-MIS-01"]
    assert len(missing) == (1 if expected_days > 3 else 0)


def test_a3_day_cases_cross_the_dst_boundary_and_midnight() -> None:
    """Gegenprobe zur Parametrisierung: die Fälle treffen beide Seiten der 3-Tage-Grenze."""
    results = {(local_date(n) - local_date(last)).days > 3 for last, n in DAY_CASES}
    assert results == {True, False}


# --- Ampel: Sicherheitsfragen ---


def _acknowledge_latest(app: FastAPI, rule: str, symptom: str, attribute: str) -> None:
    alert = alerts_of(app, rule, symptom, attribute)[-1]
    with TestClient(app, headers=CSRF) as doctor:
        login(doctor, "doctor")
        assert ack(doctor, alert.id).status_code == 200


def _clear_open_alerts(app: FastAPI) -> None:
    """Quittiert alle offenen Meldungen von SYN-0002 (Seed-Zustand: eine gelbe)."""
    pid = patient_id(app)
    with TestClient(app, headers=CSRF) as doctor:
        login(doctor, "doctor")
        for alert in doctor.get(f"{BASE}/patients/{pid}/alerts", params={"status": "open"}).json():
            assert ack(doctor, alert["alert_id"]).status_code == 200


def persisting_rules(app: FastAPI) -> list[str]:
    overview = doctor_get(app, f"/patients/{patient_id(app)}/overview").json()
    return sorted(a["rule_id"] for a in overview["persisting_alerts"])


def _persisting_fever(app: FastAPI, client: TestClient, clock: Any) -> None:
    _clear_open_alerts(app)
    assert post(client, [("fever", "presence", 1)]).status_code == 201
    _acknowledge_latest(app, "R-URG-01", "fever", "presence")
    clock.instant += timedelta(hours=2)
    assert post(client, [("fever", "presence", 1)]).status_code == 201  # Wert besteht weiter


@pytest.mark.parametrize("variant", ["omitted", "skipped"])
def test_a3_persisting_survives_a_later_response_without_the_symptom(
    live: Any, variant: str
) -> None:
    app, client, clock = at_anchor(live)
    _persisting_fever(app, client, clock)
    assert "R-URG-01" in persisting_rules(app)  # Voraussetzung (gilt heute)
    clock.instant += timedelta(hours=2)
    later: list[tuple[str, str, int | None]] = [("nausea", "severity", 0)]
    if variant == "skipped":
        later.append(("fever", "presence", None))
    assert post(client, later).status_code == 201  # Fieber nicht beantwortet
    assert "R-URG-01" in persisting_rules(app)  # letzter bekannter Wert (ja) ist weiter ≥ Schwelle
    assert row_of(app)["traffic_light"] in ("yellow", "red")


def test_a3_acknowledged_alert_with_persisting_value_keeps_the_light_off_green(live: Any) -> None:
    app, client, clock = at_anchor(live)
    _persisting_fever(app, client, clock)
    row = row_of(app)
    assert row["persisting"] is True
    assert row["traffic_light"] == "yellow"  # nie grün, solange ein Wert weiter ≥ Schwelle liegt
    assert "R-URG-01" in persisting_rules(app)
    clock.instant += timedelta(hours=2)
    assert post(client, [("fever", "presence", 0), ("nausea", "severity", 0)]).status_code == 201
    assert "R-URG-01" not in persisting_rules(app)  # Entwarnung beendet „besteht weiter“
    assert row_of(app)["traffic_light"] == "green"


def test_a3_all_null_response_neither_resets_the_missing_clock_nor_clears_alerts(live: Any) -> None:
    app, client, clock = at_anchor(live)
    clock.instant += timedelta(days=5)  # seit der letzten Antwort (Seed) > 3 Tage
    row_of(app)
    assert missing_alert_open(app)
    null_answers: list[tuple[str, str, int | None]] = [
        ("nausea", "severity", None),
        ("fever", "presence", None),
    ]
    assert post(client, null_answers).status_code == 201
    row_of(app)
    assert missing_alert_open(app)  # Überspringen ist keine Antwort mit Wert (G-10/G-19)
    assert post(client, [("nausea", "severity", 0)]).status_code == 201
    row_of(app)
    assert not missing_alert_open(app)


def test_a3_missing_alert_auto_resolve_is_not_a_clinician_acknowledgement(live: Any) -> None:
    app, client, clock = at_anchor(live)
    clock.instant += timedelta(days=6)
    pid = patient_id(app)
    row_of(app)
    assert post(client, [("nausea", "severity", 0)]).status_code == 201
    row_of(app)  # Lesen schließt die graue Meldung
    alerts = doctor_get(app, f"/patients/{pid}/alerts").json()
    missing = [a for a in alerts if a["rule_id"] == "R-MIS-01"]
    assert len(missing) == 1
    assert missing[0]["status"] == "acknowledged"
    assert missing[0]["acknowledgement"] is None  # keine ärztliche Quittierung vorgetäuscht
    with app.state.session_factory() as session:
        actions = session.scalars(
            select(AlertAction.action).where(AlertAction.alert_id == missing[0]["alert_id"])
        ).all()
        assert actions == ["auto_resolve"]
        audits = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "acknowledge_alert")
        )
        assert audits == 0


# --- Verlauf/Übersicht gegen unabhängige Neuberechnung aus den Rohdaten ---


@pytest.mark.parametrize("seed_value", range(3))
def test_a3_timeline_and_overview_match_a_recomputation_from_raw_rows(
    live: Any, seed_value: int
) -> None:
    app, client, clock = at_anchor(live)
    rng = random.Random(4100 + seed_value)
    for _ in range(14):
        clock.instant += timedelta(hours=rng.choice([5, 19, 26, 30, 50]))
        nausea = rng.choice([None, 0, 1, 2, 3, 4])
        fever = rng.choice([None, 0, 1])
        post(client, [("nausea", "severity", nausea), ("fever", "presence", fever)])
    pid = patient_id(app)
    now = clock.instant
    timeline = doctor_get(app, f"/patients/{pid}/timeline").json()
    overview = doctor_get(app, f"/patients/{pid}/overview").json()
    with app.state.session_factory() as session:
        rows = session.execute(
            select(
                Response.recorded_at,
                Response.id,
                Answer.symptom_key,
                Answer.attribute,
                Answer.value,
                Answer.id,
            )
            .join(Answer, Answer.response_id == Response.id)
            .where(Response.patient_id == pid)
            .order_by(Response.recorded_at, Response.id, Answer.symptom_key, Answer.attribute)
        ).all()
        cycle_start = session.scalar(
            select(
                func.max(__import__("waechter.models", fromlist=["Therapy"]).Therapy.cycle_start)
            ).where(__import__("waechter.models", fromlist=["Therapy"]).Therapy.patient_id == pid)
        )
    assert cycle_start is not None
    lower = cycle_start
    # Punkte je Tripel: genau die gespeicherten Zeilen im Bereich, mit null als Lücke (nie 0)
    for series in timeline["series"]:
        triple = (series["symptom_key"], series["attribute"])
        expected = [(r[5], r[4]) for r in rows if (r[2], r[3]) == triple and lower <= r[0] <= now]
        got = [(p["fact_id"].removeprefix("obs-"), p["value"]) for p in series["points"]]
        assert got == expected, triple
    ids = [p["fact_id"] for s in timeline["series"] for p in s["points"]]
    assert len(ids) == len(set(ids))
    # fehlende Tage: Kalendertage von Zyklusbeginn bis gestern ohne Wert
    answered = {local_date(r[0]) for r in rows if r[4] is not None and lower <= r[0] <= now}
    first, last = local_date(lower), min(local_date(now), local_date(now) - timedelta(days=1))
    expected_missing = [
        (first + timedelta(days=i)).isoformat()
        for i in range((last - first).days + 1)
        if (first + timedelta(days=i)) not in answered
    ]
    assert timeline["missing_days"] == expected_missing
    # Übersicht seit letztem Termin: erster/letzter/maximaler Wert
    visit = max(v["at"] for v in timeline["visits"] if v["kind"] == "past")
    start = datetime.fromisoformat(visit)
    for entry in overview["since_last_visit"]:
        triple = (entry["symptom_key"], entry["attribute"])
        values = [
            r[4] for r in rows if (r[2], r[3]) == triple and r[0] >= start and r[4] is not None
        ]
        assert entry["first"] == (values[0] if values else None), triple
        assert entry["last"] == (values[-1] if values else None), triple
        assert entry["max"] == (max(values) if values else None), triple
        direction = (
            "unknown"
            if len(values) < 2
            else "up"
            if values[-1] > values[0]
            else "down"
            if values[-1] < values[0]
            else "flat"
        )
        assert entry["direction"] == direction, triple


def test_a3_timeline_range_semantics_and_validation(live: Any) -> None:
    app, client, clock = at_anchor(live)
    start = clock.instant
    for hours, value in ((1, 1), (2, 2), (3, 3)):
        clock.instant = start + timedelta(hours=hours)
        assert post(client, [("nausea", "severity", value)]).status_code == 201
    pid = patient_id(app)
    t1, t2, t3 = (start + timedelta(hours=h) for h in (1, 2, 3))

    def points(**params: Any) -> list[int | None]:
        body = doctor_get(app, f"/patients/{pid}/timeline", **params).json()
        series = next(s for s in body["series"] if s["symptom_key"] == "nausea")
        return [p["value"] for p in series["points"] if p["fact_id"]][-3:]

    assert points(**{"from": t1.isoformat(), "to": t3.isoformat()}) == [1, 2, 3]  # Ränder inklusive
    assert points(**{"from": t2.isoformat(), "to": t2.isoformat()}) == [2]
    assert points(**{"from": (t1 + timedelta(seconds=1)).isoformat(), "to": t3.isoformat()}) == [
        2,
        3,
    ]
    for bad in (
        {"from": "2026-10-17T09:00:00"},
        {"from": "gestern"},
        {"to": "x"},
        {"from": t3.isoformat(), "to": t1.isoformat()},
    ):
        response = doctor_get(app, f"/patients/{pid}/timeline", **bad)
        assert response.status_code == 422, bad
        assert response.json()["code"] == "validation_failed"


# --- Sortierung der Arbeitsliste (unabhängig aus den Zeilen abgeleitet) ---


def test_a3_worklist_order_follows_the_contract_in_changing_states(live: Any) -> None:
    app, client, clock = at_anchor(live)
    rank = {"red": 3, "yellow": 2, "grey": 1, "green": 0}

    def check() -> list[str]:
        rows = doctor_get(app, "/patients").json()
        oldest = {}
        for row in rows:
            alerts = doctor_get(app, f"/patients/{row['patient_id']}/alerts", status="open").json()
            oldest[row["pseudonym"]] = min((a["created_at"] for a in alerts), default="9999")
        keys = [
            (
                -rank[r["traffic_light"]],
                datetime.fromisoformat(oldest[r["pseudonym"]])
                if oldest[r["pseudonym"]] != "9999"
                else datetime.max.replace(tzinfo=UTC),
                r["pseudonym"],
            )
            for r in rows
        ]
        assert keys == sorted(keys), [(r["pseudonym"], r["traffic_light"]) for r in rows]
        assert [r["open_alerts"] for r in rows] == [
            len(doctor_get(app, f"/patients/{r['patient_id']}/alerts", status="open").json())
            for r in rows
        ]
        return [r["pseudonym"] for r in rows]

    check()
    clock.instant += timedelta(hours=3)
    assert post(client, [("fever", "presence", 1)]).status_code == 201  # SYN-0002 wird rot
    order = check()
    assert order.index("SYN-0002") <= order.index("SYN-0005")
    clock.instant += timedelta(days=6)  # alle ohne Daten ⇒ grau; Sortierung weiter gültig
    check()


# --- Audit der Lesezugriffe (G-16) ---


def test_a3_reads_are_audited_without_data(live: Any) -> None:
    app, _, _ = at_anchor(live)
    pid = patient_id(app)
    doctor_get(app, f"/patients/{pid}/overview")
    doctor_get(app, f"/patients/{pid}/timeline")
    with app.state.session_factory() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action.in_(["view_overview", "view_timeline"]))
        ).all()
    assert {e.action for e in events} == {"view_overview", "view_timeline"}
    for event in events:
        assert event.target_id == pid
        assert event.actor_role == "clinician"
        assert event.details_json in (None, {})


def test_a3_missing_alert_creation_on_read_is_audited(live: Any) -> None:
    app, _, clock = at_anchor(live)
    clock.instant += timedelta(days=7)
    row_of(app)
    with app.state.session_factory() as session:
        created = session.scalar(
            select(func.count()).select_from(Alert).where(Alert.rule_id == "R-MIS-01")
        )
        audited = session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like("%missing%"))
        )
    assert created
    assert audited


def test_a3_timeline_default_range_works_before_the_cycle_has_started(live: Any) -> None:
    """Geplante Therapie (Zyklusbeginn nach 'jetzt'): leerer Verlauf statt Fehler."""
    app, _, _ = live  # Uhr 1.10.2026, Zyklusbeginn von SYN-0002 am 9.10.2026
    response = doctor_get(app, f"/patients/{patient_id(app)}/timeline")
    assert response.status_code == 200, response.text
