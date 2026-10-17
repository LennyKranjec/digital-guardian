# ruff: noqa: S311
"""A3-Gegenproben zu T-04a (Besitz A3): Eigenschaftstest gegen unabhängige Referenz, Modelltest der
Rauschbremse (inkl. Quittierung/Cooldown/Safety), Nebenläufigkeit, Reinheit, Privacy.

Die Referenz unten ist eine eigene Umsetzung von Vertrag README §3 + §9 (G-01, G-02); sie importiert
nichts aus `waechter.services.rules`/`alerts`. Feste Zufallssaat, kein Tagesdatum, keine Zahlen.
"""

import ast
import random
import shutil
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.adapters.memory_notifier import MemoryNotifier
from app.main import create_app
from app.services import seed
from conftest import CSRF, FIXTURE_CONTENT, login, make_settings, migrate
from waechter import notifier
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import get_content
from waechter.models import Alert, AlertAction, Answer, Notification, Patient, Response
from waechter.services import rules as engine

RESPONSES = "/api/v1/waechter/me/responses"
QID = "items-v1:FIX-REG"
EPOCH = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


# --- Unabhängige Referenz (Vertrag §3/§9) -----------------------------------------------------


def ref_median(values: list[int]) -> Fraction:
    ordered = sorted(values)
    n = len(ordered)
    if n % 2:
        return Fraction(ordered[n // 2])
    return Fraction(ordered[n // 2 - 1] + ordered[n // 2], 2)


def ref_threshold(value: int, p: dict[str, Any]) -> bool:
    return value >= Fraction(str(p["min_value"]))


def ref_baseline(
    now: datetime, value: int, prior: list[tuple[datetime, int]], p: dict[str, Any]
) -> bool:
    lo = now - timedelta(days=p["baseline_days"])
    base = [v for (t, v) in prior if lo <= t < now]
    if len(base) < 2:
        return False
    return value - ref_median(base) >= Fraction(str(p["min_delta"])) and value >= Fraction(
        str(p["min_value"])
    )


def ref_trend(
    now: datetime, value: int, hist: list[tuple[datetime, int]], p: dict[str, Any]
) -> bool:
    lo = now - timedelta(days=p["window_days"])
    pts = [(t, v) for (t, v) in hist if lo <= t <= now]
    if len(pts) < p["min_points"]:
        return False
    slopes: list[Fraction] = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            dt = pts[j][0] - pts[i][0]
            if dt == timedelta(0):
                continue
            slopes.append(Fraction(pts[j][1] - pts[i][1]) * 86400 / Fraction(dt.total_seconds()))
    if not slopes:
        return False
    slopes.sort()
    k = len(slopes)
    slope = slopes[k // 2] if k % 2 else (slopes[k // 2 - 1] + slopes[k // 2]) / 2
    projected = value + slope * Fraction(str(p["horizon_days"]))
    return (
        slope >= Fraction(str(p["min_slope_per_day"]))
        and projected >= Fraction(str(p["target_value"]))
        and value < Fraction(str(p["target_value"]))
    )


def points(spec: list[tuple[datetime, int]]) -> list[engine.Point]:
    return [engine.Point(t=t, value=v, ref=f"obs-{i}") for i, (t, v) in enumerate(spec)]


# --- Eigenschaftstests: Engine = Referenz über viele zufällige Historien -----------------------


def _random_history(rng: random.Random, size: int) -> list[tuple[datetime, int]]:
    # Raster aus 12-Stunden-Schritten ⇒ viele Gleichstände und genaue Fensterränder
    hist = [
        (EPOCH + timedelta(hours=12 * rng.randint(0, 24)), rng.randint(0, 4)) for _ in range(size)
    ]
    return sorted(hist, key=lambda x: x[0])


@pytest.mark.parametrize("seed_value", range(6))
def test_a3_engine_matches_reference_on_random_histories(seed_value: int) -> None:
    rng = random.Random(20261016 + seed_value)
    checked = {"threshold": 0, "baseline": 0, "trend": 0, "fired": 0}
    for _ in range(400):
        hist = _random_history(rng, rng.randint(1, 9))
        now, value = hist[-1]
        if rng.random() < 0.5:  # aktuellen Zeitpunkt auch mit Gleichständen und Randlagen
            now = EPOCH + timedelta(hours=12 * rng.randint(0, 26))
            value = rng.randint(0, 4)
            hist = [h for h in hist if h[0] <= now] + [(now, value)]
            hist.sort(key=lambda x: x[0])
        prior = [h for h in hist if h[0] < now]
        tp = {"min_value": rng.choice([1, 2, 3, 4])}
        bp = {
            "baseline_days": rng.choice([1, 2, 3, 7]),
            "min_delta": rng.choice([1, 2, 3]),
            "min_value": rng.choice([0, 1, 2, 3]),
        }
        rp = {
            "window_days": rng.choice([2, 3, 5, 10]),
            "min_points": rng.choice([2, 3, 4]),
            "horizon_days": rng.choice([1, 2, 3, 5]),
            "target_value": rng.choice([2, 3, 4]),
            "min_slope_per_day": rng.choice([0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.5, 1.0]),
        }
        assert (engine.threshold(value, tp) is not None) == ref_threshold(value, tp), (value, tp)
        got_b = engine.baseline_delta(now, value, points(prior), bp) is not None
        assert got_b == ref_baseline(now, value, prior, bp), (now, value, prior, bp)
        got_t = engine.trend(now, value, points(hist), rp) is not None
        assert got_t == ref_trend(now, value, hist, rp), (now, value, hist, rp)
        checked["threshold"] += 1
        checked["baseline"] += 1
        checked["trend"] += 1
        checked["fired"] += got_b + got_t
    assert checked["fired"] > 20  # der Lauf trifft beide Zweige (nicht nur „feuert nie“)


def test_a3_engine_handles_all_equal_timestamps_without_error() -> None:
    now = EPOCH
    hist = points([(now, 1), (now, 2), (now, 3), (now, 4)])
    assert (
        engine.trend(
            now,
            4,
            hist,
            {
                "window_days": 5,
                "min_points": 2,
                "horizon_days": 1,
                "target_value": 6,
                "min_slope_per_day": 0.1,
            },
        )
        is None
    )


def test_a3_engine_edge_pairs_are_exact_not_float() -> None:
    """Steigung exakt 0,15/Tag (3 Werte, Δt = 20 Tage ⇒ 3 Punkte) und Parameter 0.15 ⇒ feuert."""
    t0 = EPOCH
    hist = [(t0, 0), (t0 + timedelta(days=10), 1), (t0 + timedelta(days=20), 3)]
    # Paarsteigungen: 0.1, 0.1, 0.15 ⇒ Median 0.1 ⇒ nicht 0.15; Gegenprobe mit exakt passender Reihe
    exact = [(t0, 0), (t0 + timedelta(days=20), 3), (t0 + timedelta(days=40), 6)]
    p = {
        "window_days": 100,
        "min_points": 3,
        "horizon_days": 1,
        "target_value": 7,
        "min_slope_per_day": 0.15,
    }
    now, value = exact[-1][0], exact[-1][1]
    assert engine.trend(now, value, points(exact), p) is None  # value 6 < 7, projected 6.15 < 7
    p2 = {**p, "target_value": 6.15}
    assert engine.trend(now, value, points(exact), p2) is not None  # genau 6.15 ⇒ feuert (>=)
    assert hist  # (nur zur Dokumentation der Gegenreihe)


# --- Reinheit: keine Uhr, kein Zufall, kein LLM im Regelmodul -----------------------------------


def test_a3_rules_module_is_pure() -> None:
    source = Path(engine.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    } | {
        n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
    }
    assert imported <= {"collections", "dataclasses", "datetime", "fractions", "typing"}, imported
    for forbidden in (
        "now(",
        "today(",
        "utcnow(",
        "random",
        "time.time",
        "llm",
        "Llm",
        "os.environ",
    ):
        assert forbidden not in source, forbidden


# --- Modelltest: Rauschbremse + Quittierung + Cooldown + Safety (unabhängiges Modell) -----------


class MutableClock:
    def __init__(self, instant: datetime) -> None:
        self.instant = instant

    def now(self) -> datetime:
        return self.instant


@pytest.fixture
def mailbox() -> Any:
    previous = notifier.get_notifier()
    fresh = MemoryNotifier()
    notifier.set_notifier(fresh)
    yield fresh
    notifier.set_notifier(previous)


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Einmal geseedete Fixture-Datenbank (Kopiervorlage für `live`; spart Laufzeit)."""
    base = tmp_path_factory.mktemp("template")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(CONTENT_DIR_ENV, str(FIXTURE_CONTENT))
        settings = make_settings(base)
        migrate(settings)
        app = create_app(settings)
        clock = MutableClock(EPOCH)
        app.state.clock = clock
        previous = notifier.get_notifier()
        notifier.set_notifier(MemoryNotifier())  # Seed-Benachrichtigungen nicht in Tests tragen
        try:
            with app.state.session_factory() as session:
                seed.provision(session, settings, app.state.registry, clock)
                session.commit()
        finally:
            notifier.set_notifier(previous)
            app.state.engine.dispose()
    return base / "wa.db"


@pytest.fixture
def live(tmp_path: Path, mailbox: MemoryNotifier, seeded_template: Path) -> Any:
    shutil.copy(seeded_template, tmp_path / "wa.db")
    app = create_app(make_settings(tmp_path))
    clock = MutableClock(EPOCH)
    app.state.clock = clock
    client = TestClient(app, headers=CSRF)
    client.__enter__()
    login(client, "patient2")
    yield app, client, clock
    client.__exit__(None, None, None)
    app.state.engine.dispose()


def post(client: TestClient, answers: list[tuple[str, str, int | None]]) -> Any:
    body = {
        "client_submission_id": str(uuid.uuid4()),
        "questionnaire_id": QID,
        "answers": [{"symptom_key": s, "attribute": a, "value": v} for s, a, v in answers],
    }
    response = client.post(RESPONSES, json=body)
    if response.status_code == 401:  # Sitzung läuft mit der verschobenen Uhr ab: neu anmelden
        login(client, "patient2")
        response = client.post(RESPONSES, json=body)
    return response


def alerts_of(app: FastAPI, rule: str, symptom: str, attribute: str) -> list[Alert]:
    with app.state.session_factory() as session:
        pid = session.scalars(select(Patient.id).where(Patient.pseudonym == "SYN-0002")).one()
        return list(
            session.scalars(
                select(Alert)
                .where(
                    Alert.patient_id == pid,
                    Alert.rule_id == rule,
                    Alert.symptom_key == symptom,
                    Alert.attribute == attribute,
                )
                .order_by(Alert.created_at, Alert.id)
            )
        )


def nausea_history(app: FastAPI) -> list[tuple[datetime, int]]:
    """Alle gespeicherten Übelkeitswerte (ohne `null`) von SYN-0002 mit Zeitpunkt."""
    with app.state.session_factory() as session:
        pid = session.scalars(select(Patient.id).where(Patient.pseudonym == "SYN-0002")).one()
        rows = session.execute(
            select(Response.recorded_at, Answer.value)
            .join(Answer, Answer.response_id == Response.id)
            .where(
                Response.patient_id == pid,
                Answer.symptom_key == "nausea",
                Answer.attribute == "severity",
                Answer.value.is_not(None),
            )
        )
        return [(at, int(value)) for at, value in rows]


def acknowledge(app: FastAPI, alert_id: str, at: datetime) -> None:
    with app.state.session_factory() as session:
        alert = session.get(Alert, alert_id)
        assert alert is not None
        alert.status = "acknowledged"
        session.add(
            AlertAction(
                alert_id=alert_id,
                action="acknowledge",
                decision="no_action_needed",
                at=at,
                synthetic=True,
            )
        )
        session.commit()


@pytest.mark.parametrize("model_seed", range(4))
def test_a3_noise_brake_matches_independent_model(live: Any, model_seed: int) -> None:
    """Zufallsfolge aus Senden, Quittieren und Zeitsprüngen; Modell = Vertrag §3 + G-02."""
    app, client, clock = live
    rng = random.Random(7700 + model_seed)
    cooldown = timedelta(hours=24)
    model: list[dict[str, Any]] = []  # {value, open, ack_at, created}
    fired_total = 0
    history = nausea_history(app)  # (Zeit, Wert) bereits gespeicherter Antworten (Seed)
    for step in range(60):
        action = rng.choice(["send", "send", "send", "ack", "wait", "wait"])
        if action == "wait":
            clock.instant += timedelta(hours=rng.choice([1, 6, 12, 23, 24, 25, 48]))
        elif action == "ack":
            open_alerts = [a for a in model if a["open"]]
            if open_alerts:
                chosen = rng.choice(open_alerts)
                chosen["open"] = False
                chosen["ack_at"] = clock.instant
                acknowledge(app, chosen["id"], clock.instant)
        else:
            clock.instant += timedelta(minutes=rng.choice([1, 30, 90]))  # eigene Zeit je Sendung
            value = rng.randint(0, 4)
            assert post(client, [("nausea", "severity", value)]).status_code == 201
            # DR-012: eine Antwort unter der Schwelle (3) nach der Meldung beendet ihre Episode
            blocking = [
                a["value"]
                for a in model
                if (a["open"] or clock.instant < a["ack_at"] + cooldown)
                and not any(a["created"] < at < clock.instant and v < 3 for at, v in history)
            ]
            expected_new = value >= 3 and (not blocking or value > max(blocking))
            stored = alerts_of(app, "R-SEV-01", "nausea", "severity")
            known = {a["id"] for a in model}
            new = [a for a in stored if a.id not in known]
            assert len(new) == (1 if expected_new else 0), (step, value, blocking, len(new))
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
                fired_total += 1
            history.append((clock.instant, value))
    assert fired_total >= 3  # die Folge hat die Bremse tatsächlich geprüft


def test_a3_open_alert_invariants_after_random_sequence(live: Any) -> None:
    """Neue Meldungen je Tripel nur bei Verschlechterung oder nach Entwarnung (DR-012)."""
    app, client, clock = live
    rng = random.Random(99)
    for _ in range(40):
        clock.instant += timedelta(hours=rng.choice([1, 3, 30]))
        post(
            client,
            [("nausea", "severity", rng.randint(0, 4)), ("fever", "presence", rng.randint(0, 1))],
        )
    with app.state.session_factory() as session:
        pid = session.scalars(select(Patient.id).where(Patient.pseudonym == "SYN-0002")).one()
        stamps = {
            (symptom, attribute): [
                (at, int(value))
                for at, value in session.execute(
                    select(Response.recorded_at, Answer.value)
                    .join(Answer, Answer.response_id == Response.id)
                    .where(
                        Response.patient_id == pid,
                        Answer.symptom_key == symptom,
                        Answer.attribute == attribute,
                        Answer.value.is_not(None),
                    )
                )
            ]
            for symptom, attribute in (("nausea", "severity"), ("fever", "presence"))
        }
    for rule, symptom, attribute, threshold in (
        ("R-SEV-01", "nausea", "severity", 3),
        ("R-URG-01", "fever", "presence", 1),
    ):
        alerts = alerts_of(app, rule, symptom, attribute)
        for earlier, later in pairwise(alerts):
            higher = (
                later.explanation_json["observed"]["value"]
                > earlier.explanation_json["observed"]["value"]
            )
            recovered = any(
                earlier.created_at < at < later.created_at and v < threshold
                for at, v in stamps[(symptom, attribute)]
            )
            # neue Meldung nur bei Verschlechterung oder mit Entwarnung dazwischen (DR-012)
            assert higher or recovered, (rule, earlier.created_at, later.created_at)


# --- Nebenläufigkeit über die API -------------------------------------------------------------


def _parallel[T](action: Callable[[int], T], workers: int) -> list[T]:
    barrier = threading.Barrier(workers)

    def task(index: int) -> T:
        barrier.wait(timeout=10)
        return action(index)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(task, i) for i in range(workers)]
        return [f.result(timeout=60) for f in futures]


def test_a3_parallel_identical_red_submissions_create_exactly_one_alert_and_one_notice(
    live: Any, mailbox: MemoryNotifier
) -> None:
    app, _, _ = live
    clients = []
    for _ in range(8):
        c = TestClient(app, headers=CSRF)
        c.__enter__()
        login(c, "patient2")
        clients.append(c)
    try:
        before_notices = len(mailbox.sent)
        results = _parallel(lambda i: post(clients[i], [("nausea", "severity", 3)]), 8)
    finally:
        for c in clients:
            c.__exit__(None, None, None)
    assert [r.status_code for r in results] == [201] * 8, [r.text for r in results]
    assert len(alerts_of(app, "R-SEV-01", "nausea", "severity")) == 1
    assert len(mailbox.sent) - before_notices == 1
    with app.state.session_factory() as session:
        notes = session.scalars(select(Notification).where(Notification.level == "red")).all()
        by_alert = [n.alert_id for n in notes if n.alert_id]
        assert len(by_alert) == len(set(by_alert))  # eine Benachrichtigung je Meldung


def test_a3_parallel_escalation_yields_one_alert_per_value_level(live: Any) -> None:
    """Gleichzeitig 3 und 4 (je 4 Mal): höchstens eine Meldung je Wert, nie mehr als zwei."""
    app, _, _ = live
    clients = []
    for _ in range(8):
        c = TestClient(app, headers=CSRF)
        c.__enter__()
        login(c, "patient2")
        clients.append(c)
    try:
        results = _parallel(lambda i: post(clients[i], [("nausea", "severity", 3 + i % 2)]), 8)
    finally:
        for c in clients:
            c.__exit__(None, None, None)
    assert all(r.status_code == 201 for r in results)
    stored = alerts_of(app, "R-SEV-01", "nausea", "severity")
    values = sorted(a.explanation_json["observed"]["value"] for a in stored)
    assert values in ([3.0], [4.0], [3.0, 4.0]), values  # nie zwei Meldungen gleichen Werts


# --- Privacy, Erklärung, Belege -----------------------------------------------------------------


def test_a3_notification_and_headline_do_not_leak_names_and_evidence_resolves(live: Any) -> None:
    app, client, _ = live
    receipt = post(client, [("nausea", "severity", 4), ("fever", "presence", 1)]).json()
    with app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0002")).one()
        notes = session.scalars(
            select(Notification).where(Notification.patient_id == patient.id)
        ).all()
        assert notes
        for note in notes:
            assert note.text.startswith("SYN-0002")
            assert patient.display_name.split()[0] not in note.text
        alert = session.scalars(
            select(Alert).where(Alert.response_id == receipt["response_id"])
        ).first()
        assert alert is not None
        for ref in alert.explanation_json["evidence"]:
            kind, _, ident = ref.partition("-")
            if kind == "resp":
                assert session.get(Response, ident) is not None, ref
            elif kind == "obs":
                row = session.get(Answer, ident)
                assert row is not None, ref
                assert row.value is not None  # Belege sind echte Werte, nie imputierte Lücken
            else:
                pytest.fail(f"unbekannter Belegtyp {ref}")
        # Antwort an die Patientin bleibt neutral, auch wenn eine rote Meldung entstand
        assert set(receipt) == {"response_id", "recorded_at", "answered", "skipped", "message_key"}
        assert receipt["message_key"] == "patient.response.saved"


def test_a3_alert_level_and_text_come_only_from_rule_configuration(live: Any) -> None:
    app, client, _ = live
    post(client, [("nausea", "severity", 3), ("fever", "presence", 1)])
    content = get_content()
    assert content is not None
    levels = {r["id"]: r["level"] for r in content.rules["rules"]}
    with app.state.session_factory() as session:
        for alert in session.scalars(
            select(Alert).where(Alert.symptom_key.in_(["nausea", "fever"]))
        ):
            assert alert.rule_version == "rules-v1"
            assert alert.level == levels[alert.rule_id]  # Stufe = Stufe der Regel, nie vom Wert
            assert alert.explanation_json["rationale_i18n"]["cs"]
            assert alert.notified == (alert.level == "red")
    with app.state.session_factory() as session:
        total = session.scalar(select(func.count()).select_from(Alert))
        assert total is not None


def test_a3_cooldown_boundary_is_exact(live: Any) -> None:
    """Quittiert um T: bei T+24 h minus 1 s noch Ruhe, bei T+24 h wieder eine Meldung möglich."""
    app, client, clock = live
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    (first,) = alerts_of(app, "R-SEV-01", "nausea", "severity")
    ack_at = clock.instant
    acknowledge(app, first.id, ack_at)
    clock.instant = ack_at + timedelta(hours=24) - timedelta(seconds=1)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert len(alerts_of(app, "R-SEV-01", "nausea", "severity")) == 1  # noch Ruhe
    clock.instant = ack_at + timedelta(hours=24)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert len(alerts_of(app, "R-SEV-01", "nausea", "severity")) == 2  # Cooldown abgelaufen
    # Safety: Verschlechterung durchbricht den Cooldown sofort
    second = alerts_of(app, "R-SEV-01", "nausea", "severity")[-1]
    acknowledge(app, second.id, clock.instant)
    assert post(client, [("nausea", "severity", 4)]).status_code == 201
    assert len(alerts_of(app, "R-SEV-01", "nausea", "severity")) == 3
    assert post(client, [("nausea", "severity", 4)]).status_code == 201  # gleich hoch ⇒ keine neue
    assert len(alerts_of(app, "R-SEV-01", "nausea", "severity")) == 3


def test_a3_recurrence_after_recovery_inside_cooldown_must_alert_again(live: Any) -> None:
    """Fieber ja ⇒ quittiert ⇒ nach 1 h nein ⇒ nach 2 h wieder ja: neue Episode, neue rote Meldung.

    Vertrag §3 (Rauschbremse) und G-02 entschärfen nur „höherer Wert“; bei binären Warnsymptomen
    (presence 0/1) kann der Wert nie höher sein, ein Rückfall bliebe 24 h lang stumm.
    """
    app, client, clock = live
    assert post(client, [("fever", "presence", 1)]).status_code == 201
    (first,) = alerts_of(app, "R-URG-01", "fever", "presence")
    acknowledge(app, first.id, clock.instant)
    clock.instant += timedelta(hours=1)
    assert post(client, [("fever", "presence", 0)]).status_code == 201  # Entwarnung
    clock.instant += timedelta(hours=1)
    assert post(client, [("fever", "presence", 1)]).status_code == 201  # Rückfall
    assert len(alerts_of(app, "R-URG-01", "fever", "presence")) == 2
