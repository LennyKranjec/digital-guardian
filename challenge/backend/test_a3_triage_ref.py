"""Selbsttest der A3-Referenz für den Triage-Kern (a3_triage_ref.py) mit eigener Mini-Wissensbasis.

Jede Prüffunktion hat eine Negativkontrolle (absichtlich falsche Regel, falscher Baum oder falsches
Protokoll ⇒ wird erkannt).
"""

import copy
from typing import Any

import pytest

import a3_triage_ref as ref

KB: dict[str, Any] = {
    "composite_grading": {"map": [0, 1, 2, 3, 3]},
    "items": [
        {"symptom_key": "fever", "grade_max": 1, "critical": True},
        {"symptom_key": "diarrhea", "grade_max": 3, "critical": True},
        {"symptom_key": "nausea", "grade_max": 3, "critical": False},
        {"symptom_key": "fatigue", "grade_max": 3, "critical": False},
    ],
    "profiles": [
        {
            "id": "base",
            "fixed_items": ["fever", "diarrhea", "nausea", "fatigue"],
            "safety_items": ["fever"],
            "screening": {"max_questions": 6},
            "aggregates": [
                {"id": "max_all", "kind": "max_over", "items": "ALL"},
                {"id": "n_ge2", "kind": "count_ge", "items": "ALL", "threshold": 2},
                {"id": "trend", "kind": "trend_flag", "items": "ALL"},
            ],
            "teacher": {
                "red": [{"id": "R_MAX", "when": "max_all >= 3 or n_ge2 >= 3"}],
                "yellow": [{"id": "Y_MAX", "when": "max_all >= 2 or trend >= 1"}],
            },
            "floors": [{"id": "F_FEVER", "when": "fever.present == 1", "min_level": "RED"}],
        },
        {
            "id": "chemo",
            "extends": "base",
            "teacher": {"yellow": [{"id": "Y_TWO", "when": "n_ge2 >= 2"}]},
        },
    ],
}
CASCADE: dict[str, list[str]] = {
    k["symptom_key"]: ["severity", "interference"] for k in KB["items"]
}
CASCADE["fever"] = ["presence"]


def profile(kb: dict[str, Any] = KB, name: str = "base") -> ref.Profile:
    return ref.resolve(kb, name)


# --- Parser ---


@pytest.mark.parametrize(
    ("text", "env", "want"),
    [
        ("a >= 2", {"a": 2}, 1),
        ("a >= 2", {"a": 1}, 0),
        ("a >= 2 or b >= 3 and c == 1", {"a": 0, "b": 3, "c": 1}, 1),
        ("a >= 2 or b >= 3 and c == 1", {"a": 0, "b": 3, "c": 0}, 0),  # and bindet stärker als or
        ("(a >= 2 or b >= 3) and c == 1", {"a": 2, "b": 0, "c": 0}, 0),
        ("not a == 1", {"a": 0}, 1),
        ("x.grade != 2", {"x.grade": 2}, 0),
    ],
)
def test_a3_expression_parser_precedence_and_comparisons(
    text: str, env: dict[str, int], want: int
) -> None:
    assert ref.evaluate(ref.parse(text), env) == want


@pytest.mark.parametrize("text", ["a >=", "a >= 2 )", "(a >= 2", "a >= 2 b", "__import__('os')"])
def test_a3_parser_rejects_malformed_and_code_like_input(text: str) -> None:
    with pytest.raises(ref.TriageError):
        ref.parse(text)


# --- Lehrer, Böden, Vererbung ---


def test_a3_teacher_floors_and_inheritance() -> None:
    base, chemo = profile(), profile(name="chemo")
    grades = {"fever": 0, "diarrhea": 2, "nausea": 0, "fatigue": 0}
    assert ref.final_level(base, grades) == "YELLOW"
    assert ref.final_level(base, {**grades, "diarrhea": 3}) == "RED"
    assert ref.final_level(base, {"fever": 1}) == "RED"  # Boden
    two = {"fever": 0, "diarrhea": 1, "nausea": 1, "fatigue": 0}
    assert ref.final_level(base, two) == "GREEN"
    two_high = {"fever": 0, "diarrhea": 2, "nausea": 2, "fatigue": 0}
    assert ref.final_level(chemo, two_high) == "YELLOW"
    assert {r.id for r in chemo.yellow} == {"Y_MAX", "Y_TWO"}  # Vereinigung, nichts entfernt


def test_a3_trend_flag_counts_any_worsening_against_the_previous_report() -> None:
    p = profile()
    now = {"fever": 0, "diarrhea": 1, "nausea": 0, "fatigue": 0}
    assert ref.aggregate_values(p, now)["trend"] == 0  # erster Bericht
    assert ref.aggregate_values(p, now, {"diarrhea": 0})["trend"] == 1
    assert ref.aggregate_values(p, now, {"diarrhea": 1})["trend"] == 0


# --- Gitter und Monotonie ---


def test_a3_grid_enumerates_the_full_aggregate_product() -> None:
    p = profile()
    points = list(ref.grid(p))
    assert len(points) == ref.grid_size(p) == 4 * 5 * 2
    assert len({tuple(sorted(x.items())) for x in points}) == len(points)


def test_a3_teacher_is_monotone_and_a_non_monotone_rule_is_detected() -> None:
    assert ref.check_teacher_monotone(profile()) == []
    broken = copy.deepcopy(KB)
    broken["profiles"][0]["teacher"]["yellow"] = [{"id": "Y_BAD", "when": "max_all == 2"}]
    broken["profiles"][0]["teacher"]["red"] = []
    assert ref.check_teacher_monotone(profile(broken))  # Gelb bei 2, bei 3 wieder Grün
    negated = copy.deepcopy(KB)
    negated["profiles"][0]["teacher"]["yellow"] = [{"id": "Y_NOT", "when": "not max_all >= 2"}]
    assert any("not" in p for p in ref.check_teacher_monotone(profile(negated)))


def test_a3_compare_on_grid_finds_under_and_over_triage() -> None:
    p = profile()
    exact = ref.compare_on_grid(p, lambda point: ref.teacher_level(p, point))
    assert (exact.points, exact.under, exact.over) == (40, 0, 0)

    def lowered(point: Any) -> str:  # Schwelle um eins zu hoch: Untertriage
        shifted = {**point, "max_all": max(0, point["max_all"] - 1)}
        return ref.teacher_level(p, shifted)

    assert ref.compare_on_grid(p, lowered).under > 0

    def too_cautious(point: Any) -> str:
        level = ref.teacher_level(p, point)
        return "RED" if level == "YELLOW" else level

    assert ref.compare_on_grid(p, too_cautious).over > 0


def test_a3_single_step_neighbours_never_lower_the_final_level() -> None:
    assert ref.single_step_violations(profile()) == []
    broken = copy.deepcopy(KB)  # Boden, der bei höherem Grad wieder ausgeht
    broken["profiles"][0]["floors"] = [
        {"id": "F_BAD", "when": "diarrhea.grade == 1", "min_level": "RED"}
    ]
    assert ref.single_step_violations(profile(broken))


# --- Schranken und Protokolle ---


def q(symptom: str, attribute: str) -> ref.Question:
    return ref.Question(symptom, attribute)


def test_a3_bounds_shrink_with_each_answer_and_gate_zero_decides_the_item() -> None:
    p = profile()
    assert ref.level_bounds(p, CASCADE, {}) == ("GREEN", "RED")
    done = {
        "fever": {"presence": 0},
        **{k: {"severity": 0} for k in ("diarrhea", "nausea", "fatigue")},
    }
    assert ref.level_bounds(p, CASCADE, done) == ("GREEN", "GREEN")  # Gate 0 ⇒ Rest 0
    assert ref.level_bounds(p, CASCADE, {"fever": {"presence": 1}})[0] == "RED"  # Boden schon unten
    one = {"diarrhea": {"severity": 3}}
    assert ref.level_bounds(p, CASCADE, one)[0] == "RED"


def test_a3_checker_accepts_a_sound_transcript_and_flags_defects() -> None:
    p = profile()
    truth = {"fever": 1, "diarrhea": 0, "nausea": 0, "fatigue": 0}
    # Fieber ja ⇒ Boden RED: lo == hi nach der ersten Antwort, kein weiterer Schritt nötig
    sound = ref.Transcript([ref.Step(q("fever", "presence"), 1)], "decided", False)
    assert ref.check_transcript(p, CASCADE, sound, truth) == []

    premature = ref.Transcript([ref.Step(q("diarrhea", "severity"), 1)], "decided", False)
    assert any("decided" in x for x in ref.check_transcript(p, CASCADE, premature, truth))

    extra = ref.Transcript(
        [ref.Step(q("fever", "presence"), 1), ref.Step(q("diarrhea", "severity"), 1)],
        "decided",
        False,
    )
    assert any("entschiedenem" in x for x in ref.check_transcript(p, CASCADE, extra, truth))

    twice = ref.Transcript(
        [ref.Step(q("fever", "presence"), 0), ref.Step(q("fever", "presence"), 0)],
        "burden_cap",
        True,
    )
    assert any("doppelt" in x for x in ref.check_transcript(p, CASCADE, twice, truth))

    wrong_flag = ref.Transcript([ref.Step(q("fever", "presence"), 0)], "burden_cap", False)
    assert any("incomplete" in x for x in ref.check_transcript(p, CASCADE, wrong_flag, truth))


# --- Empfehlungsregeln ADV-xx ---

ADVICE_RULES = [
    ref.AdviceRule("ADV-DIARRHEA-01", "diarrhea", 1, 2),
    ref.AdviceRule("ADV-DIARRHEA-02", "diarrhea", 3),
    ref.AdviceRule("ADV-FEVER-01", "fever", 1),
    ref.AdviceRule("ADV-NAUSEA-01", "nausea", 2),
]


def test_a3_advice_rule_ids_ranges_and_defects() -> None:
    assert ref.check_advice_rules(ADVICE_RULES) == []
    bad = [
        ref.AdviceRule("ADV-DIARRHEA-1", "diarrhea", 1),  # Muster
        ref.AdviceRule("ADV-NAUSEA-01", "diarrhea", 1),  # falsches Symptom in der ID
        ref.AdviceRule("ADV-FEVER-01", "fever", 3, 2),  # min > max
        ref.AdviceRule("ADV-FEVER-01", "fever", 1),  # doppelt
        ref.AdviceRule("ADV-PAIN-01", "pain", 1, 5),  # max > 4
    ]
    assert len(ref.check_advice_rules(bad)) == 5


def test_a3_each_rule_fires_exactly_inside_its_range() -> None:
    rule = ADVICE_RULES[0]  # [1, 2]
    fires = [ref.advice_fires(rule, {"severity": v}) for v in range(5)]
    assert fires == [False, True, True, False, False]
    assert ref.advice_fires(rule, {"severity": 0, "interference": 2})  # irgendein Attribut
    assert not ref.advice_fires(rule, {"severity": None})  # nicht beantwortet


def test_a3_recommendations_are_suppressed_for_red_and_always_acute_symptoms() -> None:
    answers = {"diarrhea": {"severity": 3}, "fever": {"presence": 1}, "nausea": {"severity": 2}}
    got = ref.evaluate_recommendations(ADVICE_RULES, answers, {"diarrhea"}, {"fever"})
    assert got == {
        "ADV-DIARRHEA-02": "suppressed_acute",
        "ADV-FEVER-01": "suppressed_acute",
        "ADV-NAUSEA-01": "shown",
    }
    # mehrere Regeln je Symptom: alle passenden gelten
    both = ref.evaluate_recommendations(
        ADVICE_RULES, {"diarrhea": {"severity": 2, "interference": 3}}, set(), set()
    )
    assert both == {"ADV-DIARRHEA-01": "shown", "ADV-DIARRHEA-02": "shown"}


def test_a3_recommendation_checker_flags_missing_extra_and_leaked_rules() -> None:
    answers = {"diarrhea": {"severity": 3}, "nausea": {"severity": 2}}
    want = ref.evaluate_recommendations(ADVICE_RULES, answers, {"diarrhea"}, set())
    assert ref.check_recommendations(ADVICE_RULES, answers, {"diarrhea"}, set(), want) == []
    assert (
        ref.check_recommendations(
            ADVICE_RULES, answers, {"diarrhea"}, set(), want, ["ADV-NAUSEA-01"]
        )
        == []
    )
    shown_wrongly = {**want, "ADV-DIARRHEA-02": "shown"}
    assert ref.check_recommendations(ADVICE_RULES, answers, {"diarrhea"}, set(), shown_wrongly)
    missing = {k: v for k, v in want.items() if k != "ADV-NAUSEA-01"}
    assert ref.check_recommendations(ADVICE_RULES, answers, {"diarrhea"}, set(), missing)
    extra = {**want, "ADV-FEVER-01": "shown"}
    assert ref.check_recommendations(ADVICE_RULES, answers, {"diarrhea"}, set(), extra)
    leaked = ["ADV-NAUSEA-01", "ADV-DIARRHEA-02"]  # unterdrückte Regel bei der Patientin
    assert ref.check_recommendations(ADVICE_RULES, answers, {"diarrhea"}, set(), want, leaked)


# --- Domänenkompression ---


def test_a3_compression_keeps_every_rule_result_and_shrinks_the_grid() -> None:
    p = profile()
    assert ref.check_compression(p) == []
    small = copy.deepcopy(KB)  # Konstanten klein ⇒ kürzbar
    small["profiles"][0]["teacher"]["red"] = [{"id": "R_X", "when": "n_ge2 >= 1"}]
    small["profiles"][0]["teacher"]["yellow"] = [{"id": "Y_X", "when": "max_all >= 1"}]
    q = profile(small)
    caps = ref.compressed_domains(q)
    assert (caps["n_ge2"], caps["max_all"]) == (2, 2)  # min(natürlich, Konstante + 1)
    assert ref.compressed_size(q) < ref.grid_size(q)
    assert ref.check_compression(q) == []


def test_a3_compression_detects_a_wrong_cut_and_refuses_variable_comparisons() -> None:
    p = profile()
    real = ref.compressed_domains
    broken = {**real(p), "max_all": 1}  # zu stark gekürzt: Schwelle 3 nicht mehr unterscheidbar
    squeezed = {k: min(v, broken[k]) for k, v in {"max_all": 3, "n_ge2": 0, "trend": 0}.items()}
    assert ref.teacher_level(p, {"max_all": 3, "n_ge2": 0, "trend": 0}) != ref.teacher_level(
        p, squeezed
    )
    arithmetic = copy.deepcopy(KB)
    arithmetic["profiles"][0]["teacher"]["yellow"] = [{"id": "Y_VAR", "when": "max_all >= n_ge2"}]
    q = profile(arithmetic)
    assert ref.compressed_domains(q)["max_all"] == q.aggregates[0].domain_max  # keine Kürzung
