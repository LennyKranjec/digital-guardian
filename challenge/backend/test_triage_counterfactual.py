"""Kontrafaktische: exakt durch Aufzählung (Brute-Force-Vergleich), Schild-Hinweis, Laufzeit."""
# ruff: noqa: S311  # feste Seeds, keine Kryptografie

import itertools
import random
import time

from triage_support import real_kb
from waechter.triage.counterfactual import Change, Counterfactual, counterfactuals
from waechter.triage.engine import CompiledEngine, Engine, Level, TeacherEngine

Grades = dict[str, int]


def _engine(profile_id: str = "PEMBROLIZUMAB") -> CompiledEngine:
    return CompiledEngine(real_kb().profile(profile_id))


def _level(engine: Engine, grades: Grades, previous: Grades | None = None) -> Level:
    return engine.level_from_grades(grades, previous).level


def _zero(engine: Engine) -> Grades:
    return dict.fromkeys(engine.profile.symptoms, 0)


def _key(change_set: tuple[Change, ...]) -> frozenset[tuple[str, int]]:
    return frozenset((c.symptom_key, c.to_grade) for c in change_set)


# ---- Beispiele ----------------------------------------------------------------------------
def test_single_lowering_names_the_nearest_value_that_lowers_the_level() -> None:
    engine = _engine()
    grades = {**_zero(engine), "diarrhea": 2}  # Boden F_ICI_DIARRHEA ⇒ Rot
    assert _level(engine, grades) is Level.RED
    lower = [c for c in counterfactuals(engine, grades) if c.direction == "lower"]
    assert [(c.kind, c.changes, c.to_level) for c in lower] == [
        ("single", (Change("diarrhea", 2, 1),), Level.GREEN)
    ]
    assert lower[0].api_kind == "change"


def test_two_floors_need_a_pair_and_no_single_is_offered() -> None:
    engine = _engine()
    grades = {**_zero(engine), "fever": 1, "diarrhea": 2}
    lower = [c for c in counterfactuals(engine, grades) if c.direction == "lower"]
    assert [c.kind for c in lower] == ["pair"]
    assert _key(lower[0].changes) == frozenset({("fever", 0), ("diarrhea", 1)})
    assert lower[0].to_level is Level.GREEN


def test_three_floors_cannot_be_lowered_by_two_changes_and_the_shield_is_named() -> None:
    engine = _engine()
    grades = {**_zero(engine), "fever": 1, "diarrhea": 2, "shortness_of_breath": 2}
    entries = counterfactuals(engine, grades)
    lower = [c for c in entries if c.direction == "lower"]
    assert {c.kind for c in lower} == {"shield"}
    assert {c.floor_id for c in lower} == {"F_FEVER", "F_ICI_DIARRHEA", "F_ICI_DYSPNEA"}
    assert all(c.changes == () and c.to_level is None for c in lower)
    assert {c.api_kind for c in lower} == {"shield"}


def test_raise_names_the_single_step_that_lifts_the_level() -> None:
    engine = _engine()
    grades = _zero(engine)
    raised = [c for c in counterfactuals(engine, grades) if c.direction == "raise"]
    assert [(c.kind, c.changes, c.to_level) for c in raised] == [
        ("single", (Change("fever", 0, 1),), Level.RED)
    ]


def test_green_has_nothing_to_lower_and_red_nothing_to_raise() -> None:
    engine = _engine()
    green = counterfactuals(engine, _zero(engine))
    assert all(c.direction == "raise" for c in green)
    red = counterfactuals(engine, {**_zero(engine), "fever": 1})
    assert all(c.direction == "lower" for c in red)


# ---- Brute-Force-Vergleich auf dem kleinen Profil -----------------------------------------
def _brute_lower(
    engine: Engine, grades: Grades, previous: Grades | None
) -> set[frozenset[tuple[str, int]]]:
    base = _level(engine, grades, previous)
    symptoms = [s for s in engine.profile.symptoms if grades[s] > 0]

    def lowers(change_set: dict[str, int]) -> bool:
        return _level(engine, {**grades, **change_set}, previous) < base

    singles = {
        (s, v)
        for s in symptoms
        for v in range(grades[s])
        if lowers({s: v})
        and not any(lowers({s: w}) for w in range(v + 1, grades[s]))  # minimal: kein schwächerer
    }
    if singles:
        return {frozenset({item}) for item in singles}
    pairs: set[frozenset[tuple[str, int]]] = set()
    for first, second in itertools.combinations(symptoms, 2):
        for v1, v2 in itertools.product(range(grades[first]), range(grades[second])):
            if not lowers({first: v1, second: v2}):
                continue
            weaker = [
                (w1, w2)
                for w1 in range(v1, grades[first])
                for w2 in range(v2, grades[second])
                if (w1, w2) != (v1, v2)
            ]
            if not any(lowers({first: w1, second: w2}) for w1, w2 in weaker):
                pairs.add(frozenset({(first, v1), (second, v2)}))
    return pairs


def _brute_raise(
    engine: Engine, grades: Grades, previous: Grades | None
) -> set[frozenset[tuple[str, int]]]:
    base = _level(engine, grades, previous)
    caps = {s: engine.profile.items[s].grade_max for s in engine.profile.symptoms}
    symptoms = [s for s in engine.profile.symptoms if grades[s] < caps[s]]
    singles = {
        frozenset({(s, grades[s] + 1)})
        for s in symptoms
        if _level(engine, {**grades, s: grades[s] + 1}, previous) > base
    }
    if singles:
        return singles
    return {
        frozenset({(a, grades[a] + 1), (b, grades[b] + 1)})
        for a, b in itertools.combinations(symptoms, 2)
        if _level(engine, {**grades, a: grades[a] + 1, b: grades[b] + 1}, previous) > base
    }


def test_counterfactuals_equal_the_brute_force_enumeration_and_really_change_the_level() -> None:
    engine = _engine("PEMBROLIZUMAB")
    teacher = TeacherEngine(real_kb().profile("PEMBROLIZUMAB"))
    rng = random.Random(20261016)
    symptoms = engine.profile.symptoms
    checked = 0
    for _ in range(220):
        grades = {
            s: rng.choices(
                range(engine.profile.items[s].grade_max + 1),
                [5, 2, 2, 1][: engine.profile.items[s].grade_max + 1],
            )[0]
            for s in symptoms
        }
        previous = None if rng.random() < 0.5 else {s: rng.randint(0, 2) for s in symptoms}
        base = _level(engine, grades, previous)
        found = counterfactuals(engine, grades, previous, limit=10_000)
        lower = [c for c in found if c.direction == "lower" and c.kind != "shield"]
        raised = [c for c in found if c.direction == "raise"]
        assert {_key(c.changes) for c in lower} == _brute_lower(engine, grades, previous)
        assert {_key(c.changes) for c in raised} == _brute_raise(engine, grades, previous)
        for entry in lower + raised:
            changed = {**grades, **{c.symptom_key: c.to_grade for c in entry.changes}}
            now = _level(engine, changed, previous)
            assert now == entry.to_level  # Wiederauswertung bestätigt das Ergebnis
            assert (now < base) if entry.direction == "lower" else (now > base)
            assert _level(teacher, changed, previous) == now  # Baum == Lehrer auch hier
            assert all(
                (c.to_grade < c.from_grade) == (entry.direction == "lower") for c in entry.changes
            )
        checked += 1
    assert checked == 220


def test_shield_entry_appears_exactly_when_a_floor_holds_and_nothing_lowers() -> None:
    engine = _engine()
    rng = random.Random(7)
    for _ in range(150):
        grades = {
            s: rng.randint(0, engine.profile.items[s].grade_max) for s in engine.profile.symptoms
        }
        entries = counterfactuals(engine, grades, limit=10_000)
        lower = [c for c in entries if c.direction == "lower"]
        shields = [c for c in lower if c.kind == "shield"]
        decision = engine.level_from_grades(grades)
        real_lowering = [c for c in lower if c.kind != "shield"]
        if shields:
            assert not real_lowering
            assert decision.level > Level.GREEN
            assert {c.floor_id for c in shields} <= {h.floor_id for h in decision.shield_hits}
        elif decision.level > Level.GREEN:
            assert real_lowering or not any(
                h.min_level >= decision.level for h in decision.shield_hits
            )


def test_counterfactuals_for_the_larger_profiles_are_fast_and_deterministic() -> None:
    engine = _engine("FOLFOX")
    rng = random.Random(11)
    states = [
        {s: rng.randint(0, engine.profile.items[s].grade_max) for s in engine.profile.symptoms}
        for _ in range(40)
    ]
    started = time.perf_counter()
    first = [counterfactuals(engine, g) for g in states]
    elapsed = time.perf_counter() - started
    assert elapsed < 20, elapsed  # 9 Symptome, Einzel- und Paarvarianten, exakt aufgezählt
    assert first == [counterfactuals(engine, g) for g in states]


def test_counterfactual_size_orders_the_output() -> None:
    engine = _engine("FOLFOX")
    grades = {**_zero(engine), "diarrhea": 3, "pain": 2}
    lower = [c for c in counterfactuals(engine, grades) if c.direction == "lower"]
    sizes = [c.size for c in lower]
    assert sizes == sorted(sizes)
    assert isinstance(lower[0], Counterfactual)
