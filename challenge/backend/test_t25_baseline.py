"""T-25 (a): Das Baseline-Fenster beginnt frühestens beim Start des aktuellen Therapieschemas.

Regimewechsel = neuer Therapie-Eintrag mit anderer `regimen_id`; ein neuer Zyklus desselben Schemas
setzt nicht zurück; ohne Wechsel bleibt alles wie vor T-25 (die Orakel-Tests in `test_alerts.py`
prüfen das für den Seed). Feste Ankerzeit, keine Tagesuhr.
"""

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from waechter.models import Alert, Answer, Patient, Response, Therapy
from waechter.services import alerts
from waechter.services import rules as engine

NOW = datetime(2026, 10, 17, 7, 0, tzinfo=UTC)
COUNTER = itertools.count(1)
PARAMS = {"baseline_days": 7, "min_delta": 2, "min_value": 2}


def day(offset: float) -> datetime:
    return NOW + timedelta(days=offset)


def pts(*pairs: tuple[float, int]) -> list[engine.Point]:
    return [engine.Point(day(d), v, f"obs-{i}") for i, (d, v) in enumerate(pairs)]


# --- reine Regel -----------------------------------------------------------------------------


def test_earliest_cuts_the_baseline_window() -> None:
    prior = pts((-6, 3), (-5, 3), (-2, 0), (-1, 0))
    unlimited = engine.baseline_delta(NOW, 2, prior, PARAMS)
    assert unlimited is None  # Median(3,3,0,0) = 1,5 ⇒ Delta 0,5
    limited = engine.baseline_delta(NOW, 2, prior, PARAMS, earliest=day(-3))
    assert limited is not None
    assert limited.observed["baseline"] == 0.0
    assert limited.observed["delta"] == 2.0
    assert limited.window == (day(-3), NOW)  # das Fenster nennt den tatsächlichen Beginn
    assert limited.refs == ("obs-2", "obs-3")


def test_earliest_needs_two_values_after_it() -> None:
    prior = pts((-6, 0), (-5, 0), (-1, 0))
    assert engine.baseline_delta(NOW, 3, prior, PARAMS) is not None
    assert engine.baseline_delta(NOW, 3, prior, PARAMS, earliest=day(-3)) is None


def test_earliest_before_the_window_changes_nothing() -> None:
    prior = pts((-6, 0), (-5, 0))
    same = engine.baseline_delta(NOW, 3, prior, PARAMS)
    assert same == engine.baseline_delta(NOW, 3, prior, PARAMS, earliest=day(-30))
    assert same == engine.baseline_delta(NOW, 3, prior, PARAMS, earliest=None)


def test_earliest_is_inclusive() -> None:
    prior = pts((-3, 0), (-2, 0))
    assert engine.baseline_delta(NOW, 3, prior, PARAMS, earliest=day(-3)) is not None


# --- Therapie-Historie -----------------------------------------------------------------------


@pytest.fixture
def session(seeded_app: Any) -> Iterator[Session]:
    with seeded_app.state.session_factory() as db:
        yield db


def new_patient(db: Session, *therapies: tuple[str, float]) -> Patient:
    patient = Patient(
        pseudonym=f"T25-{next(COUNTER):04d}",
        display_name="Test",
        birth_year=1970,
        sex="female",
        language="cs",
        synthetic=True,
    )
    db.add(patient)
    db.flush()
    for regimen, offset in therapies:
        db.add(Therapy(patient_id=patient.id, regimen_id=regimen, cycle_start=day(offset)))
    db.flush()
    return patient


def test_regimen_change_finds_the_start_of_the_current_regimen(session: Session) -> None:
    patient = new_patient(session, ("A", -40), ("A", -19), ("B", -10), ("B", +0))
    # bis Tag -11 gab es nur A ⇒ kein Wechsel; ab Tag -10 gilt B
    assert alerts.regimen_change(session, patient.id, day(-11)) is None
    assert alerts.regimen_change(session, patient.id, day(-10)) == (day(-10), "B")
    # ein neuer Zyklus desselben Schemas (B, Tag 0) setzt den Start nicht zurück
    assert alerts.regimen_change(session, patient.id, day(1)) == (day(-10), "B")


def test_regimen_change_without_therapy_or_with_one_regimen_is_none(session: Session) -> None:
    assert alerts.regimen_change(session, new_patient(session).id, NOW) is None
    same = new_patient(session, ("A", -40), ("A", -19), ("A", -2))
    assert alerts.regimen_change(session, same.id, NOW) is None


def test_back_and_forth_uses_the_latest_run(session: Session) -> None:
    patient = new_patient(session, ("A", -30), ("B", -20), ("A", -9), ("A", -2))
    assert alerts.regimen_change(session, patient.id, NOW) == (day(-9), "A")


# --- Auswertung ------------------------------------------------------------------------------


def answer_at(db: Session, patient: Patient, offset: float, value: int) -> Response:
    response = Response(
        patient_id=patient.id,
        client_submission_id=f"{patient.id}-{offset}",
        questionnaire_id="items-v1:FIX-REG",
        channel="web",
        entered_by="self",
        recorded_at=day(offset),
        evaluation_status="done",
        synthetic=True,
    )
    db.add(response)
    db.flush()
    db.add(Answer(response_id=response.id, symptom_key="nausea", attribute="severity", value=value))
    db.flush()
    return response


def delta_alerts(db: Session, patient: Patient) -> list[Alert]:
    return list(
        db.scalars(select(Alert).where(Alert.patient_id == patient.id, Alert.rule_id == "R-DLT-01"))
    )


def run(db: Session, patient: Patient, history: list[tuple[float, int]], current: int) -> None:
    for offset, value in history:
        alerts.evaluate_response(db, answer_at(db, patient, offset, value))
    alerts.evaluate_response(db, answer_at(db, patient, 0, current))


def test_after_a_regimen_change_old_values_do_not_form_the_baseline(session: Session) -> None:
    changed = new_patient(session, ("A", -30), ("B", -3))
    run(session, changed, [(-6, 3), (-5, 3), (-2, 0), (-1, 0)], current=2)
    [alert] = delta_alerts(session, changed)
    explanation = alert.explanation_json
    assert explanation["observed"]["baseline"] == 0.0
    assert explanation["baseline_limit"] == {
        "reason": "regimen_change",
        "regimen_id": "B",
        "since": "2026-10-14T09:00:00+02:00",  # Beginn des Schemas B, Europe/Prague
    }
    assert explanation["baseline_window"]["from"] == "2026-10-14T09:00:00+02:00"
    assert explanation["evidence"][2:] == [
        f"obs-{a}" for a in _answer_ids(session, changed, -2, -1)
    ]


def _answer_ids(db: Session, patient: Patient, *offsets: float) -> list[str]:
    ids = []
    for offset in offsets:
        ids.append(
            db.scalars(
                select(Answer.id)
                .join(Response, Response.id == Answer.response_id)
                .where(Response.patient_id == patient.id, Response.recorded_at == day(offset))
            ).one()
        )
    return ids


def test_without_the_change_the_same_history_fires_no_alert(session: Session) -> None:
    same_regimen = new_patient(session, ("A", -30), ("A", -3))  # neuer Zyklus, kein Wechsel
    run(session, same_regimen, [(-6, 3), (-5, 3), (-2, 0), (-1, 0)], current=2)
    assert delta_alerts(session, same_regimen) == []


def test_too_few_values_after_the_change_means_no_baseline_rule(session: Session) -> None:
    changed = new_patient(session, ("A", -30), ("B", -3))
    run(session, changed, [(-6, 0), (-5, 0), (-1, 0)], current=3)
    assert delta_alerts(session, changed) == []  # vorher (ohne Wechsel) hätte die Regel gefeuert
    plain = new_patient(session, ("A", -30), ("A", -3))
    run(session, plain, [(-6, 0), (-5, 0), (-1, 0)], current=3)
    assert len(delta_alerts(session, plain)) == 1


def test_single_regimen_explanation_has_no_baseline_limit(session: Session) -> None:
    single = new_patient(session, ("A", -30))
    run(session, single, [(-6, 0), (-5, 0)], current=3)
    [alert] = delta_alerts(session, single)
    assert "baseline_limit" not in alert.explanation_json  # Erklärung wie vor T-25
