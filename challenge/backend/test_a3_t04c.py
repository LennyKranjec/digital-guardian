# ruff: noqa: F401, F811
"""A3-Gegenproben zu T-04c (Besitz A3): Episodenende nach Entwarnung (DR-012) und Patientensperre.

Hilfen und Fixtures kommen aus `test_a3_t04a.py` (steuerbare Uhr, Benachrichtigungskanal).
"""

from datetime import timedelta
from typing import Any

import pytest

from test_a3_t04a import (
    MutableClock,
    _parallel,
    acknowledge,
    alerts_of,
    live,
    mailbox,
    post,
    seeded_template,
)

RULE = ("R-SEV-01", "nausea", "severity")  # Schwelle 3 (Fixture-Regeln)
FEVER = ("R-URG-01", "fever", "presence")  # Schwelle 1


def count(app: Any, rule: tuple[str, str, str] = RULE) -> int:
    return len(alerts_of(app, *rule))


@pytest.mark.parametrize("recovery", [0, 1, 2])
def test_a3_value_below_threshold_ends_the_episode(live: Any, recovery: int) -> None:
    app, client, clock = live
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert count(app) == 1
    clock.instant += timedelta(hours=1)
    assert post(client, [("nausea", "severity", recovery)]).status_code == 201
    clock.instant += timedelta(hours=1)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert count(app) == 2  # Rückfall meldet sofort (auch bei noch offener erster Meldung)


@pytest.mark.parametrize("not_a_recovery", [3, 4])
def test_a3_value_at_or_above_threshold_does_not_end_the_episode(
    live: Any, not_a_recovery: int
) -> None:
    app, client, clock = live
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    clock.instant += timedelta(hours=1)
    assert post(client, [("nausea", "severity", not_a_recovery)]).status_code == 201
    clock.instant += timedelta(hours=1)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert count(app) == (2 if not_a_recovery == 4 else 1)  # 4 ist höher ⇒ Eskalation (G-02)


def test_a3_skipping_the_question_is_not_a_recovery(live: Any) -> None:
    """Safety: Überspringen (null) darf einen Rückfall nicht „entwarnen“."""
    app, client, clock = live
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    clock.instant += timedelta(hours=1)
    assert post(client, [("nausea", "severity", None)]).status_code == 201
    clock.instant += timedelta(hours=1)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert count(app) == 1


def test_a3_a_recovery_of_another_symptom_does_not_count(live: Any) -> None:
    app, client, clock = live
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    clock.instant += timedelta(hours=1)
    assert post(client, [("fever", "presence", 0)]).status_code == 201
    clock.instant += timedelta(hours=1)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert count(app) == 1


def test_a3_a_recovery_before_the_alert_does_not_count(live: Any) -> None:
    app, client, clock = live
    assert post(client, [("nausea", "severity", 0)]).status_code == 201
    clock.instant += timedelta(hours=1)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    clock.instant += timedelta(hours=1)
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert count(app) == 1


def test_a3_acknowledged_alert_then_recovery_then_relapse_alerts_again(live: Any) -> None:
    app, client, clock = live
    assert post(client, [("fever", "presence", 1)]).status_code == 201
    (first,) = alerts_of(app, *FEVER)
    acknowledge(app, first.id, clock.instant)
    clock.instant += timedelta(hours=1)
    assert post(client, [("fever", "presence", 0)]).status_code == 201
    clock.instant += timedelta(hours=1)
    assert post(client, [("fever", "presence", 1)]).status_code == 201  # innerhalb des Cooldowns
    assert count(app, FEVER) == 2
    # ohne Entwarnung bleibt der Cooldown gültig
    (_, second) = sorted(alerts_of(app, *FEVER), key=lambda a: a.created_at)
    acknowledge(app, second.id, clock.instant)
    clock.instant += timedelta(hours=1)
    assert post(client, [("fever", "presence", 1)]).status_code == 201
    assert count(app, FEVER) == 2


def test_a3_each_new_episode_notifies_exactly_once(live: Any, mailbox: Any) -> None:
    app, client, clock = live
    before = len(mailbox.sent)
    for _ in range(3):
        assert post(client, [("nausea", "severity", 4)]).status_code == 201
        clock.instant += timedelta(hours=1)
        assert post(client, [("nausea", "severity", 4)]).status_code == 201  # keine zweite Meldung
        clock.instant += timedelta(hours=1)
        assert post(client, [("nausea", "severity", 0)]).status_code == 201
        clock.instant += timedelta(hours=1)
    assert count(app) == 3
    assert len(mailbox.sent) - before == 3


def test_a3_frozen_clock_same_instant_recovery_is_not_detected(live: Any) -> None:
    """Dokumentiert die Grenze bei fester Uhr (Demo/E2E): gleicher Zeitstempel, keine Reihenfolge.

    Entwarnung zählt nur mit Zeitstempel nach der Meldung. Bei fester Uhr (alle Sendungen zur
    selben Sekunde) bleibt ein Rückfall unsichtbar; mit echter Uhr tritt das nicht auf.
    """
    app, client, _ = live
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert post(client, [("nausea", "severity", 0)]).status_code == 201  # gleiche Sekunde
    assert post(client, [("nausea", "severity", 3)]).status_code == 201
    assert count(app) == 1
