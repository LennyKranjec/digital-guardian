"""Triage-Wissensbasis: Laden, Herkunft, Vererbung „nur verschärfen“, Hash, Ladefehler."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from triage_support import CONTENT, build_from, real_inputs, real_kb
from waechter.triage.kb import (
    STATUS_ORDER,
    Level,
    TriageError,
    build_kb,
    canonical_hash,
    load_kb,
    read_triage_yaml,
)


def _profile(raw: dict[str, Any], profile_id: str) -> dict[str, Any]:
    return next(p for p in raw["profiles"] if p["id"] == profile_id)


def _issues(change: Callable[[dict[str, Any]], None]) -> list[str]:
    raw, attributes, regimens = real_inputs()
    change(raw)
    with pytest.raises(TriageError) as caught:
        build_kb(raw, attributes=attributes, regimens=regimens)
    return [str(issue) for issue in caught.value.issues]


def _has(issues: list[str], *needles: str) -> bool:
    return any(all(n in issue for n in needles) for issue in issues)


# ---- Positiv: die echte Wissensbasis ----------------------------------------------------------
def test_real_kb_loads_with_one_leaf_profile_per_regimen() -> None:
    kb = real_kb()
    assert kb.version == "triage-v1"
    assert set(kb.regimen_profile) == {
        "FOLFOX",
        "CAPECITABINE",
        "DOCETAXEL",
        "PEMBROLIZUMAB",
        "ENZALUTAMIDE",
        "ABIRATERONE",
        "PAZOPANIB",
        "NIVOLUMAB",
    }
    assert kb.profile_for_regimen("PEMBROLIZUMAB").lineage == ("base", "ici", "PEMBROLIZUMAB")
    assert kb.profile_for_regimen("FOLFOX").lineage == ("base", "chemo", "FOLFOX")
    assert len(kb.hash) == 64


def test_everything_is_placeholder_with_assumption_ids() -> None:
    kb = real_kb()
    assert kb.raw["composite_grading"]["status"] == "placeholder"
    assert kb.raw["composite_grading"]["assumption"] in kb.assumptions
    for assumption in kb.assumptions.values():
        assert assumption["status"] == "placeholder"
    for profile in kb.profiles.values():
        assert profile.status == "placeholder"
        for rule in (*profile.red_rules, *profile.yellow_rules, *profile.floors):
            assert rule.status == "placeholder"
            assert (rule.source is None) != (rule.assumption is None)
            if rule.assumption is not None:
                assert rule.assumption in kb.assumptions
    for raw_profile in kb.raw["profiles"]:
        assert raw_profile["status"] == "placeholder"


def test_floors_are_locked_and_every_profile_has_the_fever_shield() -> None:
    for profile in real_kb().profiles.values():
        assert profile.floors
        assert all(floor.locked for floor in profile.floors)
        fever = next(f for f in profile.floors if f.id == "F_FEVER")
        assert fever.level is Level.RED
        assert "fever" in profile.safety_items


def test_children_only_add_to_their_parents() -> None:
    kb = real_kb()
    base = kb.raw["profiles"][0]
    for profile in kb.profiles.values():
        rule_ids = {r.id for r in (*profile.red_rules, *profile.yellow_rules, *profile.floors)}
        inherited = {
            r["id"] for r in base["teacher"]["red"] + base["teacher"]["yellow"] + base["floors"]
        }
        assert inherited <= rule_ids
        assert set(base["fixed_items"]) <= set(profile.fixed_items)
        assert {a["id"] for a in base["aggregates"]} <= {a.id for a in profile.aggregates}
    assert any(f.id == "F_ICI_DIARRHEA" for f in kb.profile("PEMBROLIZUMAB").floors)
    assert all(f.id != "F_ICI_DIARRHEA" for f in kb.profile("FOLFOX").floors)


def test_profile_symptoms_come_from_items_and_the_regimen() -> None:
    _, attributes, regimens = real_inputs()
    for regimen_id, profile in ((r, real_kb().profile_for_regimen(r)) for r in regimens):
        assert set(profile.symptoms) <= set(attributes)
        assert set(profile.symptoms) <= set(regimens[regimen_id])


def test_hash_is_canonical_and_changes_with_content() -> None:
    raw, attributes, regimens = real_inputs()
    first = build_kb(raw, attributes=attributes, regimens=regimens)
    reversed_raw = {key: raw[key] for key in reversed(list(raw))}
    reversed_raw["profiles"] = [dict(reversed(list(p.items()))) for p in raw["profiles"]]
    second = build_kb(reversed_raw, attributes=attributes, regimens=regimens)
    assert first.hash == second.hash == real_kb().hash
    assert first.hash == canonical_hash(json.loads(json.dumps(raw)))
    changed = copy.deepcopy(raw)
    changed["profiles"][0]["teacher"]["red"][0]["when"] = "max_critical >= 2"
    assert build_kb(changed, attributes=attributes, regimens=regimens).hash != first.hash
    assert len({p.hash for p in first.profiles.values()}) == len(first.profiles)


def test_load_kb_reads_directory_and_missing_or_invalid_file_is_an_error(tmp_path: Path) -> None:
    assert load_kb(CONTENT).hash == real_kb().hash
    with pytest.raises(TriageError) as missing:
        read_triage_yaml(tmp_path)
    assert "file is missing" in str(missing.value)
    (tmp_path / "triage.yaml").write_text("a: [unclosed", encoding="utf-8")
    with pytest.raises(TriageError) as invalid:
        read_triage_yaml(tmp_path)
    assert "invalid YAML" in str(invalid.value)


# ---- Negativ: Monotonie ---------------------------------------------------------------------
def test_non_monotone_teacher_rule_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["teacher"]["red"][1]["when"] = "n_ge2 == 4"

    assert _has(_issues(change), "R_COUNT_G2", "not monotone")


def test_less_than_comparison_on_aggregate_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["teacher"]["yellow"][0]["when"] = "max_grade <= 1"

    assert _has(_issues(change), "Y_ANY_G2", "not monotone")


def test_not_on_an_aggregate_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["teacher"]["red"][0]["when"] = "not max_critical >= 3"

    assert _has(_issues(change), "R_CRIT_G3", "not on an aggregate")


def test_hidden_not_inside_a_larger_rule_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["teacher"]["yellow"][1]["when"] = "n_ge1 >= 1 and not (n_ge2 >= 5)"

    assert _has(_issues(change), "Y_MANY_G1", "not on an aggregate")


def test_teacher_rule_over_raw_item_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["teacher"]["yellow"][0]["when"] = "fever.present"

    assert _has(_issues(change), "Y_ANY_G2", "only use aggregates")


def test_non_monotone_floor_and_escalation_condition_are_load_errors() -> None:
    def floor(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["floors"][0]["when"] = "not fever.present"

    def escalation(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["cascade"]["diarrhea"]["escalate_when"] = "not diarrhea.grade >= 2"

    assert _has(_issues(floor), "F_FEVER", "not monotone")
    assert _has(_issues(escalation), "escalate_when", "not monotone")


def test_decreasing_composite_map_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        raw["composite_grading"]["map"] = [0, 2, 1, 3, 3]

    assert _has(_issues(change), "composite_grading.map", "never decrease")


def test_attack_string_in_rule_is_a_load_error_and_not_executed(tmp_path: Path) -> None:
    marker = tmp_path / "pwned"

    def change(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["teacher"]["red"][0]["when"] = (
            f"__import__('os').system('echo x > {marker.as_posix()}')"
        )

    assert _has(_issues(change), "R_CRIT_G3", ".when")
    assert not marker.exists()


# ---- Negativ: Lockerung / „nur verschärfen“ ---------------------------------------------------
def _redefine(
    raw: dict[str, Any], when: str, *, loosening: bool, status: str = "placeholder"
) -> None:
    chemo = _profile(raw, "chemo")
    chemo["teacher"]["red"].append(
        {"id": "R_CRIT_G3", "when": when, "assumption": "A-TRI-01", "status": status}
    )
    if loosening:
        chemo["loosening"] = [
            {"rule_id": "R_CRIT_G3", "rationale": "Test", "approved_by": ["Person A", "Person B"]}
        ]


def test_loosening_without_block_is_a_load_error() -> None:
    issues = _issues(lambda raw: _redefine(raw, "max_critical >= 4", loosening=False))
    assert _has(issues, "R_CRIT_G3", "without loosening block")


def test_loosening_with_block_needs_status_approved() -> None:
    issues = _issues(lambda raw: _redefine(raw, "max_critical >= 4", loosening=True))
    assert _has(issues, "R_CRIT_G3", "requires status approved")


def test_loosening_with_block_and_approved_loads_and_is_marked() -> None:
    raw, attributes, regimens = real_inputs()
    _redefine(raw, "max_critical >= 4", loosening=True, status="approved")
    profile = build_kb(raw, attributes=attributes, regimens=regimens).profile("FOLFOX")
    assert profile.loosened == ("R_CRIT_G3",)
    rule = next(r for r in profile.red_rules if r.id == "R_CRIT_G3")
    assert rule.loosened
    assert rule.when == "max_critical >= 4"


def test_loosening_block_without_matching_redefinition_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        _profile(raw, "chemo")["loosening"] = [
            {"rule_id": "R_COUNT_G2", "rationale": "x", "approved_by": ["A", "B"]}
        ]

    assert _has(_issues(change), "loosening[R_COUNT_G2]", "does not match")


def test_lowering_a_floor_without_block_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        _profile(raw, "chemo")["floors"] = [
            {
                "id": "F_FEVER",
                "when": "fever.present",
                "min_level": "YELLOW",
                "locked": True,
                "assumption": "A-TRI-07",
                "status": "placeholder",
            }
        ]

    assert _has(_issues(change), "F_FEVER", "without loosening block")


def test_identical_redefinition_is_a_no_op() -> None:
    raw, attributes, regimens = real_inputs()
    _profile(raw, "chemo")["floors"] = copy.deepcopy(_profile(raw, "base")["floors"])
    build_kb(raw, attributes=attributes, regimens=regimens)


def test_child_cannot_redefine_an_aggregate_or_change_an_inherited_cascade() -> None:
    def aggregate(raw: dict[str, Any]) -> None:
        _profile(raw, "chemo")["aggregates"].append(
            {"id": "max_grade", "kind": "max_over", "items": ["fever"]}
        )

    def order(raw: dict[str, Any]) -> None:
        _profile(raw, "chemo")["cascade"]["diarrhea"] = {
            "attributes_order": ["severity", "frequency"]
        }

    def condition(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["cascade"]["diarrhea"]["escalate_when"] = "diarrhea.grade >= 2"
        _profile(raw, "chemo")["cascade"]["diarrhea"] = {
            "attributes_order": ["frequency", "severity"],
            "escalate_when": "diarrhea.grade >= 3",
        }

    assert _has(_issues(aggregate), "max_grade", "redefined")
    assert _has(_issues(order), "cascade.diarrhea", "attribute order")
    assert _has(_issues(condition), "cascade.diarrhea", "loosening")


def test_duplicate_rule_id_across_kinds_or_within_a_profile_is_a_load_error() -> None:
    def kinds(raw: dict[str, Any]) -> None:
        _profile(raw, "chemo")["teacher"]["yellow"].append(
            {
                "id": "R_CRIT_G3",
                "when": "max_critical >= 3",
                "assumption": "A-TRI-01",
                "status": "placeholder",
            }
        )

    def same(raw: dict[str, Any]) -> None:
        base = _profile(raw, "base")
        base["teacher"]["red"].append(copy.deepcopy(base["teacher"]["red"][0]))

    assert _has(_issues(kinds), "R_CRIT_G3", "duplicate rule id")
    assert _has(_issues(same), "R_CRIT_G3", "duplicate rule id")


# ---- Negativ: Herkunft ------------------------------------------------------------------------
def test_missing_source_and_assumption_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        del _profile(raw, "base")["teacher"]["red"][0]["assumption"]

    assert _has(_issues(change), "R_CRIT_G3", "exactly one of source/assumption")


def test_both_source_and_assumption_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["floors"][0]["source"] = "SRC-1"

    assert _has(_issues(change), "F_FEVER", "exactly one of source/assumption")


def test_unknown_assumption_id_is_a_load_error() -> None:
    def rule(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["teacher"]["red"][0]["assumption"] = "A-NOPE-99"

    def composite(raw: dict[str, Any]) -> None:
        raw["composite_grading"]["assumption"] = "A-NOPE-99"

    assert _has(_issues(rule), "R_CRIT_G3", "unknown assumption id")
    assert _has(_issues(composite), "composite_grading", "unknown assumption id")


def test_composite_without_provenance_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        del raw["composite_grading"]["assumption"]

    assert _has(_issues(change), "composite_grading", "exactly one of source/assumption")


def test_floor_must_be_locked() -> None:
    def missing(raw: dict[str, Any]) -> None:
        del _profile(raw, "base")["floors"][0]["locked"]

    def false(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["floors"][0]["locked"] = False

    assert _has(_issues(missing), "F_FEVER", "locked")
    assert _has(_issues(false), "locked")


# ---- Negativ: Schema und Querverweise -----------------------------------------------------------
def test_schema_violations_name_the_path() -> None:
    def extra(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["unknown_field"] = 1

    def status(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["status"] = "final"

    def mode(raw: dict[str, Any]) -> None:
        raw["mode"] = "pilot"

    assert _has(_issues(extra), "unknown_field", "additional field is not allowed")
    assert _has(_issues(status), "status", "not one of the allowed values")
    assert _has(_issues(mode), "$.mode", "constant")


def test_unknown_symptom_regimen_and_profile_references_are_load_errors() -> None:
    def symptom(raw: dict[str, Any]) -> None:
        raw["items"][0]["symptom_key"] = "fieber_xyz"

    def regimen(raw: dict[str, Any]) -> None:
        _profile(raw, "FOLFOX")["regimen_ids"] = ["NOPE"]

    def parent(raw: dict[str, Any]) -> None:
        _profile(raw, "chemo")["extends"] = "nowhere"

    assert _has(_issues(symptom), "symptom_key", "items.yaml")
    assert _has(_issues(regimen), "regimen_ids", "unknown regimen id")
    assert _has(_issues(parent), "extends", "unknown profile id")


def test_regimen_without_profile_and_regimen_on_inner_profile_are_load_errors() -> None:
    def without(raw: dict[str, Any]) -> None:
        del _profile(raw, "PEMBROLIZUMAB")["regimen_ids"]

    def inner(raw: dict[str, Any]) -> None:
        _profile(raw, "chemo")["regimen_ids"] = ["CAPECITABINE"]
        del _profile(raw, "CAPECITABINE")["regimen_ids"]

    assert _has(_issues(without), "regimen without triage profile")
    assert _has(_issues(inner), "only allowed on leaf profiles")


def test_inheritance_cycle_and_duplicate_ids_are_load_errors() -> None:
    def cycle(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["extends"] = "FOLFOX"

    def duplicate(raw: dict[str, Any]) -> None:
        raw["profiles"].append(copy.deepcopy(_profile(raw, "chemo")))

    def item(raw: dict[str, Any]) -> None:
        raw["items"].append(copy.deepcopy(raw["items"][0]))

    assert _has(_issues(cycle), "inheritance cycle")
    assert _has(_issues(duplicate), "duplicate id")
    assert _has(_issues(item), "duplicate id")


def test_profile_symptom_outside_the_regimen_is_a_load_error() -> None:
    def change(raw: dict[str, Any]) -> None:
        _profile(raw, "FOLFOX")["fixed_items"].append("rash")

    assert _has(_issues(change), "FOLFOX", "outside regimen FOLFOX")


def test_floor_or_aggregate_reading_a_foreign_symptom_is_a_load_error() -> None:
    def floor(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["floors"][0]["when"] = "rash.present"

    def aggregate(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["aggregates"].append(
            {"id": "rash_max", "kind": "max_over", "items": ["rash"]}
        )

    assert _has(_issues(floor), "F_FEVER", "profile item")
    assert _has(_issues(aggregate), "rash_max", "outside the profile")


def test_aggregate_definition_errors_are_load_errors() -> None:
    def bad_items(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["aggregates"][0]["items"] = "SOME"

    def no_threshold(raw: dict[str, Any]) -> None:
        del _profile(raw, "base")["aggregates"][2]["threshold"]

    def stray_threshold(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["aggregates"][0]["threshold"] = 2

    assert _has(_issues(bad_items), "aggregates[max_grade].items", "ALL, CRITICAL")
    assert _has(_issues(no_threshold), "n_ge1", "required for count_ge")
    assert _has(_issues(stray_threshold), "max_grade", "only allowed for count_ge")


def test_cascade_errors_are_load_errors() -> None:
    def attribute(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["cascade"]["fatigue"]["attributes_order"] = ["presence"]

    def no_condition(raw: dict[str, Any]) -> None:
        _profile(raw, "chemo")["cascade"]["vomiting"]["escalation_items"] = ["mouth_sores"]

    def unparsable(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["cascade"]["diarrhea"]["escalate_when"] = "diarrhea.grade >="

    assert _has(_issues(attribute), "cascade.fatigue", "belong to the item")
    assert _has(_issues(no_condition), "cascade.vomiting", "escalate_when")
    assert _has(_issues(unparsable), "cascade.diarrhea.escalate_when")


def test_screening_errors_are_load_errors() -> None:
    def slots(raw: dict[str, Any]) -> None:
        _profile(raw, "FOLFOX")["screening"] = {"rotating_slots": 2, "rotation_pool": ["hand_foot"]}

    def pool(raw: dict[str, Any]) -> None:
        _profile(raw, "FOLFOX")["screening"] = {"rotating_slots": 1, "rotation_pool": ["pain"]}

    def limit(raw: dict[str, Any]) -> None:
        _profile(raw, "base")["screening"]["max_questions"] = 1

    assert _has(_issues(slots), "rotating_slots", "more slots")
    assert _has(_issues(pool), "rotation_pool", "already a fixed item")
    assert _has(_issues(limit), "max_questions")


def test_presence_item_needs_grade_max_one() -> None:
    def change(raw: dict[str, Any]) -> None:
        raw["items"][0]["grade_max"] = 2

    assert _has(_issues(change), "grade_max", "presence")


def test_kb_status_order_is_ascending() -> None:
    assert STATUS_ORDER.index("placeholder") < STATUS_ORDER.index("approved")


def test_build_from_helper_uses_real_attribute_tables() -> None:
    raw, _, _ = real_inputs()
    assert build_from(raw).hash == real_kb().hash
