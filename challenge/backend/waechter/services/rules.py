"""Reine Regelfunktionen (Vertrag README §3, G-01): keine Uhr, keine DB, kein Zufall, kein LLM.

Alle Rechnungen laufen exakt mit `fractions.Fraction` (Parameter werden aus ihrer Dezimaldarstellung
gelesen, `0.15` ist genau 15/100). Grenzwerte (`>=`) sind dadurch frei von Gleitkomma-Rauschen, und
gleiche Eingaben liefern immer dieselbe Ausgabe. Zeiten kommen als Parameter herein.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction
from typing import NamedTuple

SECONDS_PER_DAY = 86400
DISPLAY_DIGITS = 4


class Point(NamedTuple):
    """Ein Messwert der Zeitreihe; `ref` ist die Fakt-ID (`obs-…`) für die Evidenz."""

    t: datetime
    value: int
    ref: str


@dataclass(frozen=True)
class RuleHit:
    """Ergebnis einer feuernden Regel: Beobachtung, Fenster und verwendete Belege."""

    observed: dict[str, float | None]
    refs: tuple[str, ...] = ()
    window: tuple[datetime, datetime] | None = None


def num(value: float | int) -> Fraction:
    """Exakte Zahl aus einem Konfigurationswert (über die Dezimaldarstellung)."""
    return Fraction(str(value))


def shown(value: Fraction | int) -> float:
    """Anzeigewert für die Erklärung (gerundet; nie für Entscheidungen verwendet)."""
    return round(float(value), DISPLAY_DIGITS)


def median(values: Sequence[Fraction | int]) -> Fraction:
    """Median; bei gerader Anzahl das Mittel der zwei mittleren Werte (G-01)."""
    if not values:
        raise ValueError("median of empty sequence")
    ordered = sorted(Fraction(v) for v in values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def threshold(value: int, params: Mapping[str, float]) -> RuleHit | None:
    """Feuert, wenn `value >= min_value` (Grenzwert feuert)."""
    if Fraction(value) < num(params["min_value"]):
        return None
    return RuleHit(observed={"value": float(value)})


def baseline_delta(
    now: datetime,
    value: int,
    prior: Sequence[Point],
    params: Mapping[str, float],
    earliest: datetime | None = None,
) -> RuleHit | None:
    """Baseline = Median der Werte in `[now - N·24 h, now)` (aktueller Punkt ausgeschlossen).

    `earliest` (T-25) begrenzt den Beginn des Fensters nach unten (Start des aktuellen
    Therapieschemas): Werte davor zählen nicht zur Baseline. Braucht mindestens zwei
    Baseline-Werte. Feuert, wenn `value - baseline >= min_delta` und `value >= min_value`.
    """
    start = now - timedelta(days=params["baseline_days"])
    if earliest is not None and earliest > start:
        start = earliest
    window = [p for p in prior if start <= p.t < now]
    if len(window) < 2:
        return None
    baseline = median([p.value for p in window])
    delta = Fraction(value) - baseline
    if delta < num(params["min_delta"]) or Fraction(value) < num(params["min_value"]):
        return None
    return RuleHit(
        observed={"value": float(value), "baseline": shown(baseline), "delta": shown(delta)},
        refs=tuple(p.ref for p in window),
        window=(start, now),
    )


def theil_sen_slope(points: Sequence[Point]) -> Fraction | None:
    """Median der paarweisen Steigungen in Wert/Tag; Paare mit Δt = 0 werden verworfen (G-01)."""
    slopes: list[Fraction] = []
    for i, first in enumerate(points):
        for second in points[i + 1 :]:
            micros = (second.t - first.t) // timedelta(microseconds=1)
            if micros == 0:
                continue
            days = Fraction(micros, SECONDS_PER_DAY * 1_000_000)
            slopes.append(Fraction(second.value - first.value) / days)
    return median(slopes) if slopes else None


def trend(
    now: datetime, value: int, history: Sequence[Point], params: Mapping[str, float]
) -> RuleHit | None:
    """Schleichende Veränderung (Theil-Sen) über `[now - window_days·24 h, now]`.

    `history` enthält die Punkte bis einschließlich des aktuellen. Feuert, wenn mindestens
    `min_points` Punkte vorliegen, `slope >= min_slope_per_day`, die Prognose
    `value + slope * horizon_days` den Zielwert erreicht und der aktuelle Wert darunter liegt.
    """
    start = now - timedelta(days=params["window_days"])
    window = [p for p in history if start <= p.t <= now]
    if len(window) < params["min_points"]:
        return None
    slope = theil_sen_slope(window)
    if slope is None:
        return None
    target = num(params["target_value"])
    projected = Fraction(value) + slope * num(params["horizon_days"])
    if slope < num(params["min_slope_per_day"]) or projected < target or Fraction(value) >= target:
        return None
    return RuleHit(
        observed={
            "value": float(value),
            "slope_per_day": shown(slope),
            "projected_value": shown(projected),
        },
        refs=tuple(p.ref for p in window),
        window=(start, now),
    )
