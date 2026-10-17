# ruff: noqa: S311  # deterministische Zufallsschleifen mit festem Seed, keine Kryptografie
"""Selection Policy: Schranken, Gate/Kaskade, FlipPolicy, Safety, Rotation, Limit, Properties."""

import dataclasses
import random
import statistics
from typing import Any

import pytest

from triage_support import (
    build_from,
    profile_ids,
    random_previous,
    random_state,
    random_value,
    real_inputs,
    real_kb,
)
from waechter.triage.engine import Level, TeacherEngine
from waechter.triage.kb import Key, ResolvedProfile, TriageError
from waechter.triage.parser import evaluate
from waechter.triage.policy import FlipPolicy, Question, QuestionKind, Stop

FEVER_NO = {("fever", "presence"): 0}


def _policy(profile_id: str = "FOLFOX", **changes: Any) -> FlipPolicy:
    profile = real_kb().profile(profile_id)
    if changes:
        profile = dataclasses.replace(profile, **changes)
    return FlipPolicy(TeacherEngine(profile))


def _question(result: Question | Stop) -> Question:
    assert isinstance(result, Question), result
    return result


def _stop(result: Question | Stop) -> Stop:
    assert isinstance(result, Stop), result
    return result


def run_session(
    policy: FlipPolicy,
    truth: dict[Key, int],
    rng: random.Random,
    *,
    skip: float = 0.0,
    week: int = 0,
    previous: dict[str, int] | None = None,
) -> tuple[dict[Key, int], list[Key], Stop, list[Question]]:
    """Beantwortet jede gestellte Frage aus `truth` (oder überspringt sie zufällig)."""
    state: dict[Key, int] = {}
    asked: list[Key] = []
    questions: list[Question] = []
    for _ in range(200):
        result = policy.next_question(state, asked, previous, week)
        if isinstance(result, Stop):
            return state, asked, result, questions
        key = (result.symptom_key, result.attribute)
        assert key not in asked
        asked.append(key)
        questions.append(result)
        if rng.random() >= skip:
            state[key] = truth[key]
    raise AssertionError("session did not terminate")


def consistent_truth(rng: random.Random, policy: FlipPolicy, week: int) -> dict[Key, int]:
    """Volle „wahre“ Antworten, konsistent zum Gate-Modell (Gate 0 ⇒ Folgefelder 0).

    Eskalations-Symptome sind nur ungleich 0, wenn ihre Eskalationsbedingung gilt; rotierende
    Symptome haben nur das Gate.
    """
    profile = policy.profile
    truth: dict[Key, int] = {
        (s, a): 0 for s in profile.symptoms for a in profile.items[s].attributes
    }
    universe = policy.session_symptoms(week)
    rotating = (
        set(policy.rotating_symptoms(week)) - set(profile.fixed_items) - set(profile.safety_items)
    )
    base = [
        s
        for s in universe
        if s in profile.fixed_items or s in profile.safety_items or s in rotating
    ]

    def sample(symptom: str) -> None:
        if rng.random() >= 0.3:
            return
        attributes = profile.order(symptom)
        truth[(symptom, attributes[0])] = rng.randint(1, profile.max_value(attributes[0]))
        if symptom not in rotating:
            for attribute in attributes[1:]:
                truth[(symptom, attribute)] = random_value(rng, attribute)

    for symptom in base:
        sample(symptom)
    pending = [s for s in universe if s not in base]
    progressed = True
    while pending and progressed:
        progressed = False
        env = profile.item_env(profile.grades(truth))
        for symptom in list(pending):
            parents = [
                c
                for c in profile.cascade.values()
                if symptom in c.escalation_items and c.escalate_expr is not None
            ]
            if any(evaluate(c.escalate_expr, env) for c in parents if c.escalate_expr is not None):
                sample(symptom)
                pending.remove(symptom)
                progressed = True
    return truth


# ---- Reihenfolge, Gate, Kaskade ---------------------------------------------------------------
def test_first_questions_are_the_safety_items_in_profile_order() -> None:
    first = _question(_policy("FOLFOX").next_question({}))
    assert (first.symptom_key, first.attribute, first.kind) == (
        "fever",
        "presence",
        QuestionKind.SAFETY,
    )
    assert first.red_flag
    ici = _policy("PEMBROLIZUMAB")
    second = _question(ici.next_question(FEVER_NO, [("fever", "presence")]))
    assert (second.symptom_key, second.kind) == ("shortness_of_breath", QuestionKind.SAFETY)
    assert second.attribute == "severity"


def test_gates_follow_the_flip_policy_order() -> None:
    policy = _policy("FOLFOX")
    state = dict(FEVER_NO)
    asked: list[Key] = list(state)
    order: list[str] = []
    for _ in range(5):
        question = _question(policy.next_question(state, asked))
        order.append(question.symptom_key)
        asked.append((question.symptom_key, question.attribute))
        state[(question.symptom_key, question.attribute)] = 0
    assert order == [
        "diarrhea",
        "pain",
        "vomiting",
        "mouth_sores",
        "nausea",
    ]  # Priorität, dann Aufwand, dann Schlüssel


def test_ici_floor_symptom_is_asked_before_other_gates() -> None:
    question = _question(
        _policy("PEMBROLIZUMAB").next_question({**FEVER_NO, ("shortness_of_breath", "severity"): 0})
    )
    assert (question.symptom_key, question.red_flag) == ("diarrhea", True)  # Boden-Item = red_flag


def test_gate_zero_means_follow_up_attributes_are_not_asked() -> None:
    policy = _policy("FOLFOX")
    truth = {(s, a): 0 for s in policy.profile.symptoms for a in policy.profile.items[s].attributes}
    state, asked, stop, _ = run_session(policy, truth, random.Random(1))
    assert stop.reason == "decided"
    assert not stop.incomplete
    assert ("diarrhea", "severity") not in asked
    assert ("pain", "interference") not in asked
    assert ("vomiting", "severity") not in asked  # Gate 0 ⇒ Folgeattribut nicht gefragt
    assert ("vomiting", "frequency") in asked  # kritisch ⇒ immer Gate-Frage (T-14F)
    assert len(asked) == len(policy.session_symptoms(0))  # genau ein Gate je Symptom
    assert len(asked) < policy.profile.full_question_count
    assert policy.engine.level(state).level is Level.GREEN


def test_positive_gate_runs_the_cascade_in_fixed_order() -> None:
    policy = _policy("FOLFOX")
    state = {**FEVER_NO, ("diarrhea", "frequency"): 1}
    follow_up = _question(policy.next_question(state, list(state)))
    assert (follow_up.symptom_key, follow_up.attribute, follow_up.kind) == (
        "diarrhea",
        "severity",
        QuestionKind.CASCADE,
    )


def test_follow_up_is_skipped_when_the_grade_is_already_at_its_maximum() -> None:
    policy = _policy("FOLFOX")
    state = {**FEVER_NO, ("fatigue", "severity"): 4}
    asked = list(state)
    seen = []
    for _ in range(12):
        result = policy.next_question(state, asked)
        if isinstance(result, Stop):
            break
        seen.append((result.symptom_key, result.attribute))
        asked.append(seen[-1])
        state[seen[-1]] = 0
    assert ("fatigue", "interference") not in seen


def escalating_policy() -> FlipPolicy:
    """PEMBROLIZUMAB mit einer Eskalation (nicht kritisch): Appetit nur bei Übelkeit >= 2."""
    raw, _, _ = real_inputs()
    ici = next(p for p in raw["profiles"] if p["id"] == "ici")
    ici["fixed_items"] = ["rash"]
    ici["cascade"]["nausea"] = {
        "attributes_order": ["frequency", "severity"],
        "escalate_when": "nausea.grade >= 2",
        "escalation_items": ["decreased_appetite"],
    }
    return FlipPolicy(TeacherEngine(build_from(raw).profile("PEMBROLIZUMAB")))


def test_escalation_items_are_asked_only_when_the_condition_holds() -> None:
    policy = escalating_policy()
    zero = {(s, a): 0 for s in policy.profile.symptoms for a in policy.profile.items[s].attributes}
    _, calm_asked, calm_stop, _ = run_session(policy, dict(zero), random.Random(2))
    assert calm_stop.reason == "decided"
    assert ("decreased_appetite", "severity") not in calm_asked  # Bedingung nie erfüllt
    sick = dict(zero)
    sick[("nausea", "frequency")] = 2
    sick[("nausea", "severity")] = 2
    _, asked, stop, questions = run_session(policy, sick, random.Random(2))
    assert ("decreased_appetite", "severity") in asked
    kinds = {q.symptom_key: q.kind for q in questions}
    assert kinds["decreased_appetite"] is QuestionKind.ESCALATION
    assert stop.reason == "decided"


def test_floor_decision_ends_the_session_without_unlocking_anything_else() -> None:
    ici = _policy("PEMBROLIZUMAB")
    truth = {(s, a): 0 for s in ici.profile.symptoms for a in ici.profile.items[s].attributes}
    truth[("diarrhea", "frequency")] = 2
    _, _, stop, _ = run_session(ici, truth, random.Random(2))
    assert (stop.reason, stop.level_lo) == ("decided", Level.RED)  # Boden F_ICI_DIARRHEA


def test_critical_item_cannot_be_only_an_escalation_or_rotation_target() -> None:
    raw, _, _ = real_inputs()
    chemo = next(p for p in raw["profiles"] if p["id"] == "chemo")
    chemo["fixed_items"] = ["mouth_sores"]  # vomiting ist kritisch und fiele aus den Gate-Fragen
    chemo["cascade"]["nausea"] = {
        "attributes_order": ["frequency", "severity"],
        "escalate_when": "nausea.grade >= 2",
        "escalation_items": ["vomiting"],
    }
    with pytest.raises(TriageError, match="critical item vomiting must be a fixed or safety item"):
        build_from(raw)


def test_safety_items_are_asked_even_when_the_level_is_already_decided() -> None:
    policy = _policy("FOLFOX")
    state = {("diarrhea", "frequency"): 4}  # Grad 3 kritisch ⇒ Rot, aber Fieber unbeantwortet
    bounds = policy.bounds(state)
    assert bounds.lo == Level.RED == bounds.hi
    question = _question(policy.next_question(state, list(state)))
    assert (question.symptom_key, question.kind) == ("fever", QuestionKind.SAFETY)
    state[("fever", "presence")] = 0
    stop = _stop(policy.next_question(state, list(state)))
    assert (stop.reason, stop.level_lo, stop.level_hi) == ("decided", Level.RED, Level.RED)


def test_missing_safety_lifts_the_upper_bound_even_without_any_rule() -> None:
    """Ohne Regeln und Böden bliebe `hi` GREEN, das Endlevel ist aber ≥ YELLOW (Safety-Lücke)."""
    policy = _policy("FOLFOX", red_rules=(), yellow_rules=(), floors=())
    bounds = policy.bounds({})
    level = policy.engine.level({}).level
    assert (bounds.lo, level, bounds.hi) == (Level.GREEN, Level.YELLOW, Level.YELLOW)
    answered = policy.bounds(FEVER_NO)
    assert (answered.lo, answered.hi) == (Level.GREEN, Level.GREEN)


# ---- Stopp-Gründe -----------------------------------------------------------------------------
def test_burden_cap_stops_with_incomplete_when_bounds_differ() -> None:
    policy = _policy("FOLFOX", max_questions=3)
    truth = {(s, a): 1 for s in policy.profile.symptoms for a in policy.profile.items[s].attributes}
    truth[("fever", "presence")] = 0
    _, asked, stop, _ = run_session(policy, truth, random.Random(3))
    assert len(asked) == 3
    assert stop.reason == "burden_cap"
    assert stop.incomplete
    assert stop.level_lo < stop.level_hi


def test_skipping_everything_ends_complete_and_incomplete_never_green_final() -> None:
    policy = _policy("FOLFOX", max_questions=40)
    truth = {(s, a): 0 for s in policy.profile.symptoms for a in policy.profile.items[s].attributes}
    state, asked, stop, _ = run_session(policy, truth, random.Random(4), skip=1.0)
    assert state == {}
    assert stop.reason == "complete"
    assert stop.incomplete
    assert (stop.level_lo, stop.level_hi) == (Level.GREEN, Level.RED)
    decision = policy.engine.level(state)
    assert decision.level >= Level.YELLOW  # fehlende Safety-Info
    assert decision.incomplete
    assert ("fever", "presence") in asked


def test_decided_green_uses_far_fewer_questions_than_the_full_set() -> None:
    policy = _policy("FOLFOX")
    truth = {(s, a): 0 for s in policy.profile.symptoms for a in policy.profile.items[s].attributes}
    _, asked, stop, _ = run_session(policy, truth, random.Random(5))
    assert (stop.reason, stop.level_lo, stop.level_hi) == ("decided", Level.GREEN, Level.GREEN)
    assert len(asked) == len(policy.session_symptoms(0))
    assert len(asked) < policy.profile.full_question_count == 17


# ---- Rotierende Slots -------------------------------------------------------------------------
def test_rotation_is_round_robin_over_the_cycle_week() -> None:
    one = _policy("FOLFOX", rotation_pool=("a", "b", "c"), rotating_slots=1)
    assert [one.rotating_symptoms(w) for w in range(5)] == [("a",), ("b",), ("c",), ("a",), ("b",)]
    two = _policy("FOLFOX", rotation_pool=("a", "b", "c"), rotating_slots=2)
    assert [two.rotating_symptoms(w) for w in range(4)] == [
        ("a", "b"),
        ("c", "a"),
        ("b", "c"),
        ("a", "b"),
    ]
    none = _policy("PEMBROLIZUMAB")
    assert none.rotating_symptoms(3) == ()
    assert _policy("FOLFOX").rotating_symptoms(7) == ("hand_foot",)


def test_rotating_slot_is_a_yes_no_gate_that_can_only_raise_the_level() -> None:
    policy = _policy("FOLFOX")
    zeros = {(s, a): 0 for s in policy.profile.symptoms for a in policy.profile.items[s].attributes}
    base_state, _, _, _ = run_session(policy, zeros, random.Random(6))
    truth = dict(zeros)
    truth[("hand_foot", "severity")] = 3
    truth[("hand_foot", "interference")] = 3
    state, asked, stop, questions = run_session(policy, truth, random.Random(6))
    assert ("hand_foot", "severity") in asked
    assert ("hand_foot", "interference") not in asked  # Rotation fragt nur das Gate
    assert next(q for q in questions if q.symptom_key == "hand_foot").kind is QuestionKind.ROTATING
    assert stop.reason == "decided"
    assert policy.engine.level(state).level > policy.engine.level(base_state).level


# ---- Typische Fragenzahl ------------------------------------------------------------------------
def test_typical_sessions_ask_well_below_the_full_set() -> None:
    for profile_id in profile_ids():
        policy = _policy(profile_id)
        rng = random.Random(f"typical-{profile_id}")
        counts = []
        for _ in range(150):
            truth = consistent_truth(rng, policy, rng.randint(0, 5))
            counts.append(len(run_session(policy, truth, rng)[1]))
        full = policy.profile.full_question_count
        assert statistics.mean(counts) < 0.65 * full, (profile_id, statistics.mean(counts), full)
        assert max(counts) <= policy.profile.max_questions


# ---- Property-Tests (fester Seed) ----------------------------------------------------------
STATES_PER_PROFILE = 700  # 4 Profile ⇒ 2800 Zustände


def _complete(
    rng: random.Random, state: dict[Key, int], fields: tuple[Key, ...], fraction: float
) -> dict[Key, int]:
    completed = dict(state)
    for key in fields:
        if rng.random() < fraction:
            completed[key] = random_value(rng, key[1])
    return completed


def test_property_bounds_enclose_every_completion_and_collapse_when_decided() -> None:
    checked = 0
    for profile_id in profile_ids():
        policy = _policy(profile_id)
        engine = policy.engine
        rng = random.Random(f"bounds-{profile_id}")
        for _ in range(STATES_PER_PROFILE):
            state = random_state(rng, policy.profile)
            previous = random_previous(rng, policy.profile)
            week = rng.randint(0, 5)
            bounds = policy.bounds(state, previous, week)
            level = engine.level(state, previous).level
            assert bounds.lo <= level <= bounds.hi, (profile_id, state)
            fields = policy.open_fields(state, week)
            for fraction in (0.3, 0.7, 1.0):
                completed = _complete(rng, state, fields, fraction)
                completed_level = engine.level(completed, previous).level
                assert bounds.lo <= completed_level <= bounds.hi
                if bounds.lo == bounds.hi:
                    assert completed_level == level == bounds.lo
            checked += 1
    assert checked >= 2000


def test_property_next_question_is_deterministic_new_and_safety_first() -> None:
    checked = 0
    for profile_id in profile_ids():
        policy = _policy(profile_id)
        rng = random.Random(f"next-{profile_id}")
        for _ in range(STATES_PER_PROFILE):
            state = random_state(rng, policy.profile)
            skipped = [
                (s, a)
                for s in policy.profile.symptoms
                for a in policy.profile.items[s].attributes
                if (s, a) not in state and rng.random() < 0.2
            ]
            asked = list(state) + skipped
            week = rng.randint(0, 5)
            previous = random_previous(rng, policy.profile)
            first = policy.next_question(state, asked, previous, week)
            assert first == policy.next_question(state, asked, previous, week)
            answered = {s for s, _ in state}
            unasked_safety = [
                s
                for s in policy.profile.safety_items
                if s not in answered and (s, policy.profile.order(s)[0]) not in asked
            ]
            if isinstance(first, Question):
                assert (first.symptom_key, first.attribute) not in asked
                if unasked_safety:
                    assert first.kind is QuestionKind.SAFETY
            elif unasked_safety:
                raise AssertionError("stopped while a safety item was still unasked")
            checked += 1
    assert checked >= 2000


def test_property_sessions_never_undertriage_when_decided_and_flag_the_rest() -> None:
    sessions = 0
    decided = 0
    for profile_id in profile_ids():
        policy = _policy(profile_id)
        engine = policy.engine
        profile = policy.profile
        rng = random.Random(f"sessions-{profile_id}")
        for index in range(300):
            week = rng.randint(0, 5)
            previous = random_previous(rng, profile)
            truth = consistent_truth(rng, policy, week)
            skip = 0.0 if index % 2 == 0 else 0.15
            state, asked, stop, _ = run_session(
                policy, truth, rng, skip=skip, week=week, previous=previous
            )
            bounds = policy.bounds(state, previous, week)
            assert (stop.level_lo, stop.level_hi) == (bounds.lo, bounds.hi)
            level = engine.level(state, previous)
            truth_level = engine.level(truth, previous).level
            assert bounds.lo <= level.level <= bounds.hi
            assert bounds.lo <= truth_level <= bounds.hi  # Volleingabe liegt in den Schranken
            if stop.reason == "decided":
                decided += 1
                assert (
                    level.level == truth_level
                )  # kein Unter-/Obertriage gegenüber der Volleingabe
                assert stop.incomplete == level.incomplete
            else:
                assert stop.incomplete == (level.incomplete or bounds.lo < bounds.hi)
            if stop.reason == "burden_cap":
                assert len(asked) >= profile.max_questions
            assert len(asked) <= profile.max_questions
            for symptom in profile.safety_items:
                assert (symptom, profile.order(symptom)[0]) in asked  # Safety immer gefragt
            for symptom, attribute in asked:
                gate = profile.order(symptom)[0]
                if attribute != gate:  # Folgefrage ⇒ Gate beantwortet und > 0
                    assert (symptom, gate) in state
                    assert profile.grades({(symptom, gate): state[(symptom, gate)]})[symptom] > 0
            assert len(set(asked)) == len(asked)
            sessions += 1
    assert sessions == 300 * len(profile_ids())  # 300 Sitzungen je Blattprofil (8 Profile)
    assert decided > 0


def test_property_decided_means_no_remaining_question_changes_the_level() -> None:
    """lo == hi ⇒ jede mögliche Antwort auf jedes noch offene Feld lässt das Level unverändert."""
    checked = 0
    for profile_id in profile_ids():
        policy = _policy(profile_id)
        engine = policy.engine
        rng = random.Random(f"flip-{profile_id}")
        for _ in range(150):
            week = rng.randint(0, 5)
            truth = consistent_truth(rng, policy, week)
            state, _asked, stop, _ = run_session(policy, truth, rng, week=week)
            if stop.reason != "decided":
                continue
            level = engine.level(state).level
            for field in policy.open_fields(state, week):
                for value in range(policy.profile.max_value(field[1]) + 1):
                    assert engine.level({**state, field: value}).level == level
                    checked += 1
    assert checked > 0


def test_policy_is_a_pure_function_of_its_inputs() -> None:
    policy = _policy("FOLFOX")
    rng = random.Random(9)
    for _ in range(50):
        truth = consistent_truth(rng, policy, 2)
        first = run_session(policy, truth, random.Random(1), week=2)
        second = run_session(policy, dict(truth), random.Random(1), week=2)
        assert first[1:3] == second[1:3]


def test_profile_type_exposes_what_the_policy_needs() -> None:
    profile: ResolvedProfile = real_kb().profile("CAPECITABINE")
    assert profile.max_questions >= len(profile.safety_items)
    assert set(profile.rotation_pool) == {"decreased_appetite"}
    assert profile.red_flag_symptoms >= {"fever"}
