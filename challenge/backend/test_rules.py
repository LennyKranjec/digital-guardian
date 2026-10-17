"""Reine Regelfunktionen: Median, Schwelle, Baseline-Delta, Theil-Sen-Trend (G-01)."""

from datetime import UTC, datetime, timedelta
from fractions import Fraction

import pytest

from waechter.services import rules as r

NOW = datetime(2026, 10, 17, 7, 0, tzinfo=UTC)


def day(offset: float) -> datetime:
    return NOW + timedelta(days=offset)


def pts(*pairs: tuple[float, int]) -> list[r.Point]:
    return [r.Point(day(d), v, f"obs-{i}") for i, (d, v) in enumerate(pairs)]


def test_median_odd_and_even() -> None:
    assert r.median([3, 1, 2]) == 2
    assert r.median([4, 1, 3, 2]) == Fraction(5, 2)  # Mittel der zwei mittleren (G-01)
    assert r.median([1]) == 1
    with pytest.raises(ValueError, match="empty"):
        r.median([])


def test_num_is_exact_decimal() -> None:
    assert r.num(0.15) == Fraction(15, 100)
    assert r.num(3) == 3


def test_threshold_boundary_fires_and_below_does_not() -> None:
    params = {"min_value": 3}
    assert r.threshold(3, params) is not None  # Grenzwert = Schwelle feuert
    assert r.threshold(2, params) is None
    hit = r.threshold(4, params)
    assert hit is not None
    assert hit.observed == {"value": 4.0}


BASE = {"baseline_days": 7, "min_delta": 2, "min_value": 2}


def test_baseline_needs_two_values() -> None:
    assert r.baseline_delta(NOW, 3, pts((-3, 0)), BASE) is None
    assert r.baseline_delta(NOW, 3, [], BASE) is None


def test_baseline_median_and_delta_boundary() -> None:
    hit = r.baseline_delta(NOW, 2, pts((-3, 0), (-2, 0)), BASE)  # Delta genau 2
    assert hit is not None
    assert hit.observed["baseline"] == 0.0
    assert hit.observed["delta"] == 2.0
    assert r.baseline_delta(NOW, 2, pts((-3, 1), (-2, 1)), BASE) is None  # Delta 1


def test_baseline_even_count_uses_mean_of_middle_values() -> None:
    hit = r.baseline_delta(NOW, 4, pts((-4, 0), (-3, 1), (-2, 1), (-1, 2)), BASE)
    assert hit is not None
    assert hit.observed["baseline"] == 1.0
    assert hit.observed["delta"] == 3.0


def test_baseline_respects_min_value() -> None:
    assert r.baseline_delta(NOW, 1, pts((-3, 0), (-2, 0)), {**BASE, "min_delta": 1}) is None


def test_baseline_window_edges() -> None:
    inside = pts((-7, 0), (-6, 0))  # Fensterbeginn exakt N·24 h vor jetzt: eingeschlossen
    assert r.baseline_delta(NOW, 3, inside, BASE) is not None
    outside = pts((-7.0001, 0), (-6, 0))  # ein Wert außerhalb ⇒ nur ein Baseline-Wert
    assert r.baseline_delta(NOW, 3, outside, BASE) is None
    current_excluded = pts((-3, 0), (0, 0))  # Punkt zur Zeit now zählt nicht zur Baseline
    assert r.baseline_delta(NOW, 3, list(current_excluded), BASE) is None


TREND = {
    "window_days": 7,
    "min_points": 3,
    "horizon_days": 2,
    "target_value": 3,
    "min_slope_per_day": 0.5,
}


def test_theil_sen_median_of_pairwise_slopes_per_day() -> None:
    assert r.theil_sen_slope(pts((-4, 0), (-2, 1), (0, 2))) == Fraction(1, 2)
    assert r.theil_sen_slope(pts((-2, 0), (0, 4))) == 2
    assert r.theil_sen_slope(pts((0, 1))) is None


def test_theil_sen_drops_pairs_with_zero_time_difference() -> None:
    same_time = [r.Point(NOW, 1, "a"), r.Point(NOW, 3, "b")]
    assert r.theil_sen_slope(same_time) is None
    mixed = [r.Point(day(-1), 0, "a"), r.Point(NOW, 2, "b"), r.Point(NOW, 4, "c")]
    # Paare (a,b)=2/Tag und (a,c)=4/Tag zählen, (b,c) mit Δt = 0 nicht ⇒ Median 3
    assert r.theil_sen_slope(mixed) == 3


def test_trend_fires_exactly_at_slope_boundary_and_projection() -> None:
    history = pts((-4, 0), (-2, 1), (0, 2))
    hit = r.trend(NOW, 2, history, TREND)
    assert hit is not None
    assert hit.observed["slope_per_day"] == 0.5
    assert hit.observed["projected_value"] == 3.0  # 2 + 0.5·2 = Ziel, Grenzwert feuert


def test_trend_needs_min_points() -> None:
    assert r.trend(NOW, 2, pts((-2, 1), (0, 2)), TREND) is None


def test_trend_not_when_slope_too_small_or_projection_short() -> None:
    assert r.trend(NOW, 1, pts((-4, 0), (-2, 0), (0, 1)), TREND) is None
    short = {**TREND, "horizon_days": 1}  # Steigung 0,5 reicht, Prognose 2,5 < Ziel 3
    assert r.trend(NOW, 2, pts((-4, 0), (-2, 1), (0, 2)), short) is None


def test_trend_not_when_current_value_already_at_target() -> None:
    assert r.trend(NOW, 3, pts((-4, 1), (-2, 2), (0, 3)), TREND) is None  # dann greift die Schwelle


def test_trend_ignores_points_outside_window() -> None:
    old = pts((-30, 0), (-20, 0), (-10, 0), (0, 2))
    assert r.trend(NOW, 2, old, TREND) is None  # nur ein Punkt im Fenster


def test_functions_are_deterministic() -> None:
    history = pts((-4, 0), (-3, 1), (-2, 1), (-1, 2))
    first = r.baseline_delta(NOW, 4, history, BASE)
    assert first == r.baseline_delta(NOW, 4, history, BASE)
    assert r.trend(NOW, 2, history, TREND) == r.trend(NOW, 2, history, TREND)
