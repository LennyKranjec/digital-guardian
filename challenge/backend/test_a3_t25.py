"""A3-Gegenproben zu T-25 (Baseline nach Therapiewechsel, Zeile 'Beobachtete Symptome').

Eigener Referenzrechner fuer die gekuerzte Baseline-Regel (Fraction, eigener Median, eigene
Fensterlogik) und fuer die Erkennung des Schemawechsels, gegen Zufallsserien. Dazu: rote Regeln
bleiben unberuehrt, Randfaelle (Grenze, Gleichstand, Zukunft), Rollen der Uebersicht.
"""

import itertools
import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import CSRF, login
from test_fhir import pid, staff
from waechter.models import Alert, Answer, Patient, Response, Therapy
from waechter.services import alerts
from waechter.services import rules as engine

NOW = datetime(2026, 10, 17, 7, 0, tzinfo=UTC)
PARAMS = {"baseline_days": 7, "min_delta": 2, "min_value": 2}
COUNTER = itertools.count(1)


def day(offset: float) -> datetime:
    return NOW + timedelta(days=offset)


# --- eigene Referenz der Regel -----------------------------------------------------------------


def ref_median(values: list[int]) -> Fraction:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return Fraction(ordered[mid])
    return Fraction(ordered[mid - 1] + ordered[mid], 2)


def ref_delta(
    now: datetime, value: int, prior: list[tuple[datetime, int]], earliest: datetime | None
) -> tuple[Fraction, Fraction] | None:
    start = now - timedelta(days=7)
    if earliest is not None and earliest > start:
        start = earliest
    inside = [v for t, v in prior if start <= t < now]
    if len(inside) < 2:
        return None
    baseline = ref_median(inside)
    if value - baseline < 2 or value < 2:
        return None
    return baseline, value - baseline


def random_case(rng: random.Random) -> tuple[int, list[tuple[datetime, int]], datetime | None]:
    count = rng.randint(0, 9)
    prior = [
        (day(-rng.choice([rng.random() * 9, rng.randint(0, 9)])), rng.randint(0, 4))
        for _ in range(count)
    ]
    earliest = (
        None if rng.random() < 0.2 else day(-rng.choice([rng.random() * 9, rng.randint(0, 9)]))
    )
    return rng.randint(0, 4), prior, earliest


def test_a3_baseline_delta_equals_an_independent_reference_on_random_series() -> None:
    rng = random.Random(2503)  # noqa: S311
    fired = 0
    for _ in range(6000):
        value, prior, earliest = random_case(rng)
        points = [engine.Point(t, v, f"obs-{i}") for i, (t, v) in enumerate(prior)]
        got = engine.baseline_delta(NOW, value, points, PARAMS, earliest)
        want = ref_delta(NOW, value, prior, earliest)
        if want is None:
            assert got is None, (value, prior, earliest)
            continue
        assert got is not None, (value, prior, earliest)
        fired += 1
        assert abs(got.observed["baseline"] - float(want[0])) < 1e-3  # type: ignore[operator]
        assert abs(got.observed["delta"] - float(want[1])) < 1e-3  # type: ignore[operator]
    assert fired > 300, "Zufallsserien feuern zu selten, Test waere wirkungslos"


def test_a3_earliest_never_reaches_further_back_than_the_plain_window() -> None:
    rng = random.Random(25)  # noqa: S311
    for _ in range(2000):
        value, prior, _ = random_case(rng)
        points = [engine.Point(t, v, f"obs-{i}") for i, (t, v) in enumerate(prior)]
        old = engine.baseline_delta(NOW, value, points, PARAMS, day(-60))
        plain = engine.baseline_delta(NOW, value, points, PARAMS, None)
        assert old == plain


def test_a3_current_and_future_points_never_enter_the_baseline() -> None:
    prior = [
        engine.Point(day(-2), 0, "a"),
        engine.Point(day(-1), 0, "b"),
        engine.Point(day(0), 4, "c"),
        engine.Point(day(1), 4, "d"),
    ]
    hit = engine.baseline_delta(NOW, 3, prior, PARAMS, day(-3))
    assert hit is not None
    assert hit.refs == ("a", "b")


# --- Erkennung des Schemawechsels --------------------------------------------------------------


@pytest.fixture
def session(seeded_app: FastAPI) -> Iterator[Session]:
    with seeded_app.state.session_factory() as db:
        yield db


def patient_with(db: Session, rows: list[tuple[str, float]]) -> Patient:
    patient = Patient(
        pseudonym=f"A3T25-{next(COUNTER):05d}",
        display_name="Test",
        birth_year=1970,
        sex="female",
        language="cs",
        synthetic=True,
    )
    db.add(patient)
    db.flush()
    for regimen, offset in rows:  # Einfuegereihenfolge = Reihenfolge der Eintraege
        db.add(Therapy(patient_id=patient.id, regimen_id=regimen, cycle_start=day(offset)))
        db.flush()
    return patient


def ref_change(rows: list[tuple[str, float]], now_offset: float) -> tuple[datetime, str] | None:
    known = sorted(
        ((off, i, reg) for i, (reg, off) in enumerate(rows) if off <= now_offset),
    )
    if not known:
        return None
    regimens = [reg for _, _, reg in known]
    last = len(regimens) - 1
    first_of_run = last
    while first_of_run > 0 and regimens[first_of_run - 1] == regimens[last]:
        first_of_run -= 1
    if first_of_run == 0:
        return None
    return day(known[first_of_run][0]), regimens[last]


def test_a3_regimen_change_equals_a_reference_on_random_histories(session: Session) -> None:
    rng = random.Random(2525)  # noqa: S311
    for _ in range(150):
        count = rng.randint(0, 6)
        offsets = rng.sample(range(-40, 5), count)  # verschiedene Tage: Reihenfolge eindeutig
        rows = [(rng.choice("ABC"), float(off)) for off in offsets]
        patient = patient_with(session, rows)
        now_offset = float(rng.randint(-40, 5))
        got = alerts.regimen_change(session, patient.id, day(now_offset))
        assert got == ref_change(rows, now_offset), (rows, now_offset)


def test_a3_a_future_dated_regimen_does_not_cut_the_baseline_yet(session: Session) -> None:
    patient = patient_with(session, [("A", -30), ("B", +5)])
    assert alerts.regimen_change(session, patient.id, NOW) is None
    assert alerts.regimen_change(session, patient.id, day(5)) == (day(5), "B")


@pytest.mark.xfail(strict=True, reason="T-25 F-01 (Low): Gleichstand cycle_start ordnet nach UUID")
def test_a3_same_start_time_with_two_regimens_is_deterministic(session: Session) -> None:
    """Zwei Eintraege mit gleichem cycle_start und verschiedenem Schema: Ergebnis darf nicht von
    der zufaelligen Zeilen-ID abhaengen (Therapy.id ist eine UUID)."""
    outcomes = set()
    for _ in range(12):
        patient = patient_with(session, [("A", -30), ("B", -3), ("C", -3)])
        outcomes.add(alerts.regimen_change(session, patient.id, NOW))
    assert len(outcomes) == 1, outcomes


# --- Auswertung: rote Regeln bleiben unberuehrt --------------------------------------------------


def answer_at(
    db: Session, patient: Patient, offset: float, symptom: str, attr: str, value: int
) -> Response:
    response = Response(
        patient_id=patient.id,
        client_submission_id=f"{patient.id}-{symptom}-{offset}",
        questionnaire_id="items-v1:FIX-REG",
        channel="web",
        entered_by="self",
        recorded_at=day(offset),
        evaluation_status="done",
        synthetic=True,
    )
    db.add(response)
    db.flush()
    db.add(Answer(response_id=response.id, symptom_key=symptom, attribute=attr, value=value))
    db.flush()
    return response


def rule_ids(db: Session, patient: Patient) -> set[str]:
    return {a.rule_id for a in db.scalars(select(Alert).where(Alert.patient_id == patient.id))}


@pytest.mark.parametrize(
    "rows", [[("A", -30)], [("A", -30), ("B", -1)], [("A", -30), ("B", -2), ("A", -1)]]
)
def test_a3_red_rules_fire_identically_with_and_without_a_regimen_change(
    session: Session, rows: list[tuple[str, float]]
) -> None:
    patient = patient_with(session, rows)
    alerts.evaluate_response(session, answer_at(session, patient, -0.5, "nausea", "severity", 3))
    alerts.evaluate_response(session, answer_at(session, patient, 0, "fever", "presence", 1))
    assert {"R-SEV-01", "R-URG-01"} <= rule_ids(session, patient)


def test_a3_yellow_baseline_rule_is_the_only_one_that_stays_quiet_after_a_switch(
    session: Session,
) -> None:
    """Dokumentiert die Folge: nach Wechsel kein R-DLT-01 ohne 2 Werte im neuen Schema (ANN)."""
    patient = patient_with(session, [("A", -30), ("B", -1)])
    for off, val in ((-6, 0), (-5, 0), (-4, 0)):
        alerts.evaluate_response(
            session, answer_at(session, patient, off, "nausea", "severity", val)
        )
    alerts.evaluate_response(session, answer_at(session, patient, 0, "nausea", "severity", 2))
    assert "R-DLT-01" not in rule_ids(session, patient)
    control = patient_with(session, [("A", -30)])
    for off, val in ((-6, 0), (-5, 0), (-4, 0)):
        alerts.evaluate_response(
            session, answer_at(session, control, off, "nausea", "severity", val)
        )
    alerts.evaluate_response(session, answer_at(session, control, 0, "nausea", "severity", 2))
    assert "R-DLT-01" in rule_ids(session, control)


@pytest.mark.xfail(strict=True, reason="T-25 F-02 (Low): baseline_limit auch ohne echte Kuerzung")
def test_a3_baseline_limit_is_only_reported_when_the_window_was_really_shortened(
    session: Session,
) -> None:
    """Wechsel genau 7 Tage vor der Antwort: das Fenster wird nicht gekuerzt (start == since)."""
    patient = patient_with(session, [("A", -30), ("B", -7)])
    for off, val in ((-6, 0), (-5, 0)):
        alerts.evaluate_response(
            session, answer_at(session, patient, off, "nausea", "severity", val)
        )
    alerts.evaluate_response(session, answer_at(session, patient, 0, "nausea", "severity", 3))
    delta = list(
        session.scalars(
            select(Alert).where(Alert.patient_id == patient.id, Alert.rule_id == "R-DLT-01")
        )
    )
    assert len(delta) == 1
    explanation: dict[str, Any] = delta[0].explanation_json
    # Fenster beginnt am Schemastart UND am Rand von 7 Tagen: eine Kuerzung hat nicht stattgefunden
    assert "baseline_limit" not in explanation


# --- Uebersicht: Rollen und Inhalt -------------------------------------------------------------


def test_a3_tracked_symptoms_only_for_staff_and_matching_the_questionnaire(
    seeded_app: FastAPI,
) -> None:
    syn1 = pid(seeded_app, "SYN-0001")
    url = f"/api/v1/waechter/patients/{syn1}/overview"
    anonymous = TestClient(seeded_app, headers=CSRF)
    assert anonymous.get(url).status_code == 401
    for user in ("patient", "patient2"):
        client = TestClient(seeded_app, headers=CSRF)
        login(client, user)
        assert client.get(url).status_code == 403, user
    doctor = staff(seeded_app, "doctor")
    body = doctor.get(url).json()
    tracked = body["tracked_symptoms"]
    assert tracked
    assert all({"ctcae_term_id", "term_en", "label"} <= set(t) for t in tracked)
    assert len({t["ctcae_term_id"] for t in tracked}) == len(tracked)
    template = doctor.get(f"/api/v1/waechter/patients/{syn1}/assessment-template")
    assert template.status_code == 200
    wanted = [t["ctcae_term_id"] for t in template.json()["terms"]]
    assert [t["ctcae_term_id"] for t in tracked] == wanted
