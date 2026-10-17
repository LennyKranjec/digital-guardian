# ruff: noqa: S311  # deterministische Zufallsschleifen mit festem Seed, keine Kryptografie
"""TeacherEngine: Grade, Aggregate, Lehrer, Böden, Safety-Lücken; Property-Tests (fester Seed)."""

import random

import pytest

from triage_support import profile_ids, random_previous, random_state, real_kb
from waechter.triage.engine import INCOMPLETE_SAFETY_ITEMS, Decision, Level, TeacherEngine
from waechter.triage.kb import ResolvedProfile

FEVER_NO = {("fever", "presence"): 0}


def _engine(profile_id: str = "FOLFOX") -> TeacherEngine:
    return TeacherEngine(real_kb().profile(profile_id))


# ---- Symptomgrad (Composite, Platzhalter A-CG-01) ---------------------------------------------
def test_grade_is_the_max_over_answered_attributes_with_the_composite_map() -> None:
    profile = real_kb().profile("FOLFOX")
    assert profile.grade_map == (0, 1, 2, 3, 3)
    grades = profile.grades(
        {("diarrhea", "frequency"): 1, ("diarrhea", "severity"): 4, ("fatigue", "severity"): 2}
    )
    assert grades["diarrhea"] == 3
    assert grades["fatigue"] == 2
    assert grades["pain"] == 0  # nicht beantwortet = 0
    assert profile.grades({("fever", "presence"): 1})["fever"] == 1  # presence: ja = 1


def test_grade_ignores_foreign_symptoms_and_rejects_invalid_values() -> None:
    profile = real_kb().profile("FOLFOX")
    assert profile.grades({("rash", "severity"): 4})["fatigue"] == 0
    for bad in (
        {("fever", "presence"): 2},
        {("diarrhea", "frequency"): 5},
        {("diarrhea", "frequency"): -1},
        {("diarrhea", "presence"): 1},
        {("fever", "severity"): 1},
    ):
        with pytest.raises(ValueError, match=r"unknown attribute|out of range"):
            profile.grades(bad)


# ---- Aggregate -------------------------------------------------------------------------------
def test_aggregates_max_min_count_and_trend() -> None:
    engine = _engine()
    state = {
        **FEVER_NO,
        ("diarrhea", "frequency"): 2,
        ("vomiting", "frequency"): 3,
        ("fatigue", "severity"): 1,
        ("pain", "severity"): 1,
    }
    grades = engine.profile.grades(state)
    values = engine.aggregates(grades, None)
    assert values["max_grade"] == 3
    assert values["max_critical"] == 3  # vomiting ist kritisch
    assert values["n_ge1"] == 4
    assert values["n_ge2"] == 2
    assert values["n_ge3"] == 1
    assert values["combo_dehydration"] == 2  # min(diarrhea 2, vomiting 3)
    assert values["worsening"] == 0  # erster Bericht
    previous = {"diarrhea": 2, "vomiting": 3, "fatigue": 1, "pain": 1}
    assert engine.aggregates(grades, previous)["worsening"] == 0
    assert engine.aggregates(grades, {**previous, "pain": 0})["worsening"] == 1
    assert engine.aggregates(grades, {})["worsening"] == 1  # fehlendes Symptom im Vorbericht = 0


def test_aggregate_values_stay_inside_their_domain() -> None:
    rng = random.Random(7)
    for profile_id in profile_ids():
        engine = _engine(profile_id)
        for _ in range(300):
            grades = engine.profile.grades(random_state(rng, engine.profile))
            values = engine.aggregates(grades, random_previous(rng, engine.profile))
            for aggregate in engine.profile.aggregates:
                assert 0 <= values[aggregate.id] <= aggregate.max_value


# ---- Entscheidung -----------------------------------------------------------------------------
def test_teacher_red_rule_and_reason_codes() -> None:
    decision = _engine().level({**FEVER_NO, ("diarrhea", "frequency"): 4})
    assert decision == Decision(Level.RED, ("R_CRIT_G3", "Y_ANY_G2"), False, ())


def test_count_rules() -> None:
    four_grade_two = {
        **FEVER_NO,
        ("diarrhea", "frequency"): 2,
        ("nausea", "frequency"): 2,
        ("fatigue", "severity"): 2,
        ("pain", "severity"): 2,
    }
    assert "R_COUNT_G2" in _engine().level(four_grade_two).reason_codes
    assert _engine().level(four_grade_two).level is Level.RED
    four_grade_one = {key: 1 for key in four_grade_two if key != ("fever", "presence")}
    four_grade_one.update(FEVER_NO)
    decision = _engine().level(four_grade_one)
    assert decision.level is Level.YELLOW
    assert decision.reason_codes == ("Y_MANY_G1",)


def test_dehydration_combination_needs_both_symptoms() -> None:
    both = {**FEVER_NO, ("diarrhea", "frequency"): 2, ("vomiting", "frequency"): 2}
    assert "R_DEHYDRATION" in _engine().level(both).reason_codes
    only_one = {**FEVER_NO, ("diarrhea", "frequency"): 2}
    assert "R_DEHYDRATION" not in _engine().level(only_one).reason_codes


def test_floor_fever_forces_red_even_when_the_teacher_says_green() -> None:
    engine = _engine()
    state = {("fever", "presence"): 1}
    grades = engine.profile.grades(state)
    assert engine.teacher_level(engine.aggregates(grades, None)) is Level.GREEN
    decision = engine.level(state)
    assert decision.level is Level.RED  # final = max(Lehrer, Böden)
    assert decision.reason_codes == ("F_FEVER",)
    assert [(h.floor_id, h.min_level, h.items) for h in decision.shield_hits] == [
        ("F_FEVER", Level.RED, ("fever",))
    ]


def test_ici_floors_name_the_triggering_items() -> None:
    engine = _engine("PEMBROLIZUMAB")
    decision = engine.level(
        {
            ("fever", "presence"): 0,
            ("shortness_of_breath", "severity"): 2,
            ("diarrhea", "frequency"): 2,
        }
    )
    assert decision.level is Level.RED
    hits = {h.floor_id: h.items for h in decision.shield_hits}
    assert hits == {"F_ICI_DIARRHEA": ("diarrhea",), "F_ICI_DYSPNEA": ("shortness_of_breath",)}
    assert decision.reason_codes[:2] == ("F_ICI_DIARRHEA", "F_ICI_DYSPNEA")


def test_floor_does_not_apply_to_other_regimens() -> None:
    state = {**FEVER_NO, ("diarrhea", "frequency"): 2}
    assert not _engine("FOLFOX").level(state).shield_hits
    assert (
        _engine("PEMBROLIZUMAB")
        .level({**state, ("shortness_of_breath", "severity"): 0})
        .shield_hits
    )


def test_missing_safety_information_is_never_green() -> None:
    engine = _engine()
    empty = engine.level({})
    assert (empty.level, empty.incomplete, empty.reason_codes) == (
        Level.YELLOW,
        True,
        (INCOMPLETE_SAFETY_ITEMS,),
    )
    answered = engine.level(FEVER_NO)
    assert (answered.level, answered.incomplete) == (Level.GREEN, False)
    # Eine Folgeantwort desselben Symptoms zählt als beantwortet; ein anderes Symptom nicht.
    assert not engine.level({("fever", "presence"): 0, ("pain", "severity"): 0}).incomplete
    assert engine.level({("pain", "severity"): 0}).incomplete
    ici = _engine("PEMBROLIZUMAB")
    assert ici.level(FEVER_NO).incomplete  # Atemnot ist dort Safety-Item
    assert not ici.level({**FEVER_NO, ("shortness_of_breath", "severity"): 0}).incomplete


def test_trend_yellow_needs_a_previous_report() -> None:
    engine = _engine()
    state = {**FEVER_NO, ("fatigue", "severity"): 1}
    assert engine.level(state, None).level is Level.GREEN
    assert engine.level(state, {"fatigue": 0}).reason_codes == ("Y_WORSENING",)
    assert engine.level(state, {"fatigue": 1}).level is Level.GREEN


# ---- Property-Tests (eigene Zufallsschleifen, fester Seed, je ≥ 2000 Zustände) ----------------
STATES_PER_PROFILE = 700  # 4 Profile ⇒ 2800 Zustände je Eigenschaft


def _states(profile: ResolvedProfile, seed: int) -> list[dict[tuple[str, str], int]]:
    rng = random.Random(seed)
    return [random_state(rng, profile) for _ in range(STATES_PER_PROFILE)]


def test_property_raising_an_answer_never_lowers_the_final_level() -> None:
    checked = 0
    for profile_id in profile_ids():
        engine = _engine(profile_id)
        rng = random.Random(f"mono-{profile_id}")
        for state in _states(engine.profile, 11):
            previous = random_previous(rng, engine.profile)
            base = engine.level(state, previous).level
            for key, value in state.items():
                if value < engine.profile.max_value(key[1]):
                    higher = {**state, key: value + 1}
                    assert engine.level(higher, previous).level >= base, (profile_id, key)
            # erstmaliges Beantworten mit Wert ≥ 1 senkt nie (nur 0 darf Safety klären)
            free = [
                (s, a) for s in engine.profile.symptoms for a in engine.profile.items[s].attributes
            ]
            key = rng.choice(free)
            if key not in state:
                added = {**state, key: rng.randint(1, engine.profile.max_value(key[1]))}
                answered = {s for s, _ in state}
                if key[0] in answered or key[0] not in engine.profile.safety_items:
                    assert engine.level(added, previous).level >= base
            checked += 1
    assert checked >= 2000


def test_property_missing_safety_information_is_never_green() -> None:
    checked = 0
    for profile_id in profile_ids():
        engine = _engine(profile_id)
        rng = random.Random(f"safety-{profile_id}")
        for state in _states(engine.profile, 13):
            drop = rng.choice(engine.profile.safety_items)
            trimmed = {k: v for k, v in state.items() if k[0] != drop}
            decision = engine.level(trimmed, random_previous(rng, engine.profile))
            assert decision.incomplete
            assert decision.level >= Level.YELLOW
            assert INCOMPLETE_SAFETY_ITEMS in decision.reason_codes
            checked += 1
    assert checked >= 2000


def test_property_decision_is_independent_of_insertion_order() -> None:
    checked = 0
    for profile_id in profile_ids():
        engine = _engine(profile_id)
        rng = random.Random(f"order-{profile_id}")
        for state in _states(engine.profile, 17):
            previous = random_previous(rng, engine.profile)
            items = list(state.items())
            rng.shuffle(items)
            assert engine.level(dict(items), previous) == engine.level(state, previous)
            checked += 1
    assert checked >= 2000


def test_property_final_level_is_at_least_every_floor_and_teacher_level() -> None:
    checked = 0
    for profile_id in profile_ids():
        engine = _engine(profile_id)
        rng = random.Random(f"shield-{profile_id}")
        for state in _states(engine.profile, 19):
            previous = random_previous(rng, engine.profile)
            decision = engine.level(state, previous)
            grades = engine.profile.grades(state)
            teacher = engine.teacher_level(engine.aggregates(grades, previous))
            assert decision.level >= teacher
            for hit in decision.shield_hits:
                assert decision.level >= hit.min_level
                assert hit.floor_id in decision.reason_codes
            checked += 1
    assert checked >= 2000


def test_property_red_implies_yellow_rules_are_not_required() -> None:
    """Rot gilt unabhängig von gelben Regeln; GREEN heißt: keine Regel, kein Boden, keine Lücke."""
    for profile_id in profile_ids():
        engine = _engine(profile_id)
        rng = random.Random(f"green-{profile_id}")
        for state in _states(engine.profile, 23):
            decision = engine.level(state, random_previous(rng, engine.profile))
            if decision.level is Level.GREEN:
                assert not decision.reason_codes
                assert not decision.incomplete
                assert not decision.shield_hits
