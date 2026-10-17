"""CompiledEngine gegen TeacherEngine, Hook H2 (Komponenten), Sitzungen mit kompilierter Engine."""
# ruff: noqa: S311  # feste Seeds, keine Kryptografie

import random
import time

import pytest

from test_triage_policy import consistent_truth, run_session
from triage_support import profile_ids, random_previous, random_state, real_kb
from waechter.triage.compiler import compile_component
from waechter.triage.engine import (
    INCOMPLETE_SAFETY_ITEMS,
    CompiledEngine,
    Decision,
    Level,
    TeacherEngine,
)
from waechter.triage.kb import ResolvedComposition, compose
from waechter.triage.policy import FlipPolicy

STATES = 700  # je Profil; 4 Profile ⇒ 2 800 Zustände je Eigenschaft


def _same(a: Decision, b: Decision) -> bool:
    return (a.level, a.reason_codes, a.incomplete, a.shield_hits) == (
        b.level,
        b.reason_codes,
        b.incomplete,
        b.shield_hits,
    )


@pytest.mark.parametrize("leaf", profile_ids())
def test_compiled_engine_equals_teacher_engine_on_random_states(leaf: str) -> None:
    profile = real_kb().profile(leaf)
    teacher, compiled = TeacherEngine(profile), CompiledEngine(profile)
    rng = random.Random(f"parity-{leaf}")
    for _ in range(STATES):
        state = random_state(rng, profile)
        previous = random_previous(rng, profile)
        expected, actual = teacher.level(state, previous), compiled.level(state, previous)
        assert _same(expected, actual), (state, previous)
        assert actual.leaves
        assert actual.leaves[0].component_id == leaf
        assert len(actual.leaves[0].yellow) == len(actual.leaves[0].red) == 12


@pytest.mark.parametrize("leaf", profile_ids())
def test_compiled_final_level_never_drops_when_an_answer_rises(leaf: str) -> None:
    profile = real_kb().profile(leaf)
    engine = CompiledEngine(profile)
    rng = random.Random(f"mono-{leaf}")
    for _ in range(STATES):
        state = random_state(rng, profile)
        previous = random_previous(rng, profile)
        base = engine.level(state, previous).level
        for key, value in state.items():
            if value < profile.max_value(key[1]):
                assert engine.level({**state, key: value + 1}, previous).level >= base, key


@pytest.mark.parametrize("leaf", profile_ids())
def test_compiled_missing_safety_is_never_green(leaf: str) -> None:
    profile = real_kb().profile(leaf)
    engine = CompiledEngine(profile)
    rng = random.Random(f"safety-{leaf}")
    for _ in range(STATES):
        state = random_state(rng, profile)
        dropped = rng.choice(profile.safety_items)
        trimmed = {k: v for k, v in state.items() if k[0] != dropped}
        decision = engine.level(trimmed, random_previous(rng, profile))
        assert decision.incomplete
        assert decision.level >= Level.YELLOW
        assert INCOMPLETE_SAFETY_ITEMS in decision.reason_codes


def test_reasons_carry_the_component_id_and_match_the_codes() -> None:
    profile = real_kb().profile("PEMBROLIZUMAB")
    engine = CompiledEngine(profile)
    decision = engine.level(
        {
            ("fever", "presence"): 1,
            ("diarrhea", "frequency"): 4,
            ("shortness_of_breath", "severity"): 0,
        }
    )
    assert decision.reason_codes == tuple(r.code for r in decision.reasons)
    assert {r.component_id for r in decision.reasons} == {"PEMBROLIZUMAB"}
    kinds = {r.code: r.kind for r in decision.reasons}
    assert kinds["F_FEVER"] == "shield"
    assert kinds["R_CRIT_G3"] == "rule"
    assert [(c.component_id, c.level) for c in decision.components] == [
        ("PEMBROLIZUMAB", Level.RED)
    ]
    incomplete = engine.level({})
    assert incomplete.reasons[-1].kind == "incomplete"


def test_compiled_engine_needs_a_compiled_component_for_every_component() -> None:
    profile = real_kb().profile("PEMBROLIZUMAB")
    with pytest.raises(ValueError, match="no compiled component"):
        CompiledEngine(profile, [])


# ---- H2: mehrere Komponenten --------------------------------------------------------------
def _two_components() -> ResolvedComposition:
    kb = real_kb()
    return compose([kb.profile("FOLFOX"), kb.profile("PEMBROLIZUMAB")], "COMBO")


def test_composition_level_is_the_maximum_of_the_component_levels_then_floors() -> None:
    combo = _two_components()
    engine = CompiledEngine(combo, [compile_component(c) for c in combo.components])
    teacher = TeacherEngine(combo)
    singles = [TeacherEngine(c) for c in combo.components]
    answered = {("fever", "presence"): 0, ("shortness_of_breath", "severity"): 0}
    complete_states = (
        {**answered, ("nausea", "frequency"): 2},  # Gelb in beiden Komponenten
        {**answered, ("diarrhea", "frequency"): 2},  # Boden F_ICI_DIARRHEA (nur PEMBROLIZUMAB)
        {**answered, ("vomiting", "frequency"): 4},  # kritisch ⇒ Rot (nur FOLFOX kennt es)
        {**answered, ("fatigue", "severity"): 2, ("pain", "severity"): 2},
    )
    for state in complete_states:
        decisions = (teacher.level(state), engine.level(state))
        assert _same(*decisions)
        for decision in decisions:
            best = max(e.level(state).level for e in singles)
            assert decision.level == best  # alle Safety-Items beantwortet ⇒ genau das Maximum
            assert decision.level >= max(c.level for c in decision.components)
    # Unbeantwortete Safety-Items beider Komponenten: Vereinigung ⇒ mindestens so streng wie jede
    empty = engine.level({})
    assert empty.level >= max(e.level({}).level for e in singles)
    assert empty.incomplete


def test_composition_reasons_name_their_component_and_floors_are_united() -> None:
    combo = _two_components()
    engine = CompiledEngine(combo, [compile_component(c) for c in combo.components])
    state = {
        ("fever", "presence"): 1,
        ("diarrhea", "frequency"): 2,
        ("shortness_of_breath", "severity"): 2,
    }
    decision = engine.level(state)
    owners = {r.code: r.component_id for r in decision.reasons if r.kind == "shield"}
    assert owners["F_ICI_DIARRHEA"] == "PEMBROLIZUMAB"
    assert owners["F_ICI_DYSPNEA"] == "PEMBROLIZUMAB"
    assert owners["F_FEVER"] in {"FOLFOX", "PEMBROLIZUMAB"}
    assert decision.level is Level.RED
    assert {c.component_id for c in decision.components} == {"FOLFOX", "PEMBROLIZUMAB"}
    assert {leaf.component_id for leaf in decision.leaves} == {"FOLFOX", "PEMBROLIZUMAB"}


def test_composition_hash_changes_with_the_components() -> None:
    kb = real_kb()
    single = kb.resolve("FOLFOX")
    combo = _two_components()
    assert single.composition_hash == kb.profile("FOLFOX").hash
    assert combo.composition_hash != single.composition_hash
    assert combo.q_worst_total == sum(c.full_question_count for c in combo.components)


# ---- Sitzungen mit kompilierter Engine ----------------------------------------------------
@pytest.mark.parametrize("leaf", profile_ids())
def test_sessions_with_the_compiled_engine_equal_sessions_with_the_teacher(leaf: str) -> None:
    profile = real_kb().profile(leaf)
    teacher_policy = FlipPolicy(TeacherEngine(profile))
    compiled_policy = FlipPolicy(CompiledEngine(profile))
    rng = random.Random(f"sessions-{leaf}")
    for index in range(120):
        week = rng.randint(0, 5)
        previous = random_previous(rng, profile)
        truth = consistent_truth(rng, teacher_policy, week)
        skip = 0.0 if index % 2 == 0 else 0.15
        seed = rng.randint(0, 10**6)
        first = run_session(
            teacher_policy, truth, random.Random(seed), skip=skip, week=week, previous=previous
        )
        second = run_session(
            compiled_policy, truth, random.Random(seed), skip=skip, week=week, previous=previous
        )
        assert first[1] == second[1]  # gleiche Fragenfolge
        assert first[2] == second[2]  # gleicher Stopp samt lo/hi
        assert first[3] == second[3]  # gleiche Fragen samt Art und Flip-Kennzeichen


def test_compiled_engine_is_fast_enough_for_a_request() -> None:
    profile = real_kb().profile("FOLFOX")
    engine = CompiledEngine(profile)
    rng = random.Random(3)
    states = [random_state(rng, profile) for _ in range(300)]
    started = time.perf_counter()
    for state in states:
        engine.level(state, None)
    per_call = (time.perf_counter() - started) / len(states)
    assert per_call < 0.02, per_call  # deutlich unter einer Anfrage (Reserve für langsame Rechner)
