# ruff: noqa: S311  # feste Seeds, keine Kryptografie
"""Compiler, Verifikation, Regelkarte und Hooks H1/H3/H4 (Vertrag §4/§7/§9), Echtinhalt."""

import dataclasses
import itertools
from typing import Any

import pytest

import a3_triage_ref as ref
from triage_support import build_from, profile_ids, real_inputs, real_kb
from waechter.triage import compiler, parser, verify
from waechter.triage.compiler import (
    CompilationError,
    CompiledComponent,
    Tree,
    compile_component,
    domain_caps,
    evaluate_rendered,
    make_grid,
    render_rules,
    teacher_level_array,
    truth_array,
)
from waechter.triage.kb import Level, TriageError, build_kb, canonical_hash
from waechter.triage.runtime import runtime_for
from waechter.triage.verify import (
    VerificationError,
    monotone_violations,
    paint,
    raw_grid,
    require_clean,
    verify_component,
    verify_composition,
)

GOLDEN_PROFILE_HASHES = {
    "FOLFOX": "159ad2769b1079c6fa87d742898bde38321e3d113077000d83b4922173087e97",
    "CAPECITABINE": "9e30bb0d05e315db668e2733cc03903931681f14bd7178be15074abce0ec3259",
    "DOCETAXEL": "8eeba941d00b43e6e2f68afb9f20a582b0f4a7cdfbb55c25708c414bec3b7271",
    "PEMBROLIZUMAB": "1a015f7688c0b56dff7b9501b08b29676aa062c14b0d9ba3733cb1b0443f81b0",
    # T-20b: neue Blattprofile; die Hashes der vier älteren Profile blieben unverändert
    "ENZALUTAMIDE": "55037e0ac1c93703d94b5a4d01aac5c50105e58ffac2f916a4aaf24cc93baf3f",
    "ABIRATERONE": "c27355d2827967b5138ae08a627e1153f4870a17609430e1ed64138d925472c2",
    "PAZOPANIB": "fa40b0fed42feb4646016151d14422a1e79fc0dd338987a3d8cb2f4580818b30",
    "NIVOLUMAB": "f4f38af8b7ec11681f5008f4dee42c2db5ff84564d1e8fdfea92f53e879b4f5c",
}


@pytest.fixture(scope="module")
def built() -> dict[str, CompiledComponent]:
    kb = real_kb()
    return {pid: compile_component(kb.profile(pid)) for pid in profile_ids()}


# ---- H3 Domänenkompression ----------------------------------------------------------------
def test_caps_follow_the_largest_comparison_constant_plus_one() -> None:
    caps = domain_caps(real_kb().profile("FOLFOX"))
    assert caps["n_ge1"] == 5  # n_ge1 >= 4
    assert caps["n_ge2"] == 5  # n_ge2 >= 4
    assert caps["n_ge3"] == 2  # n_ge3 >= 1
    assert caps["max_grade"] == 3
    assert caps["max_critical"] == 3
    assert caps["worsening"] == 1
    for aggregate in real_kb().profile("FOLFOX").aggregates:
        assert 0 <= caps[aggregate.id] <= aggregate.max_value


@pytest.mark.parametrize("leaf", profile_ids())
def test_caps_and_grid_sizes_match_the_independent_reference(
    built: dict[str, CompiledComponent], leaf: str
) -> None:
    reference = ref.resolve(real_inputs()[0], leaf)
    expected = ref.compressed_domains(reference)
    assert dict(zip(built[leaf].features, built[leaf].caps, strict=True)) == expected
    assert built[leaf].grid_points == ref.compressed_size(reference)
    assert built[leaf].natural_points == ref.grid_size(reference)


def test_grid_measurement_before_and_after_compression(built: dict[str, CompiledComponent]) -> None:
    sizes = {p: (c.natural_points, c.grid_points) for p, c in built.items()}
    assert sizes == {
        "FOLFOX": (2_048_000, 221_184),
        "CAPECITABINE": (2_048_000, 221_184),
        "DOCETAXEL": (1_492_992, 221_184),
        "PEMBROLIZUMAB": (93_312, 13_824),
        "ENZALUTAMIDE": (93_312, 13_824),
        "ABIRATERONE": (43_904, 13_824),
        "PAZOPANIB": (281_216, 13_824),
        "NIVOLUMAB": (221_184, 13_824),
    }
    assert all(after <= compiler.MAX_PRODUCT for _, after in sizes.values())


def test_comparison_between_two_aggregates_blocks_compression() -> None:
    """Arithmetik-/Namensvergleich ⇒ keine Kürzung für die beteiligten Aggregate (Negativtest)."""
    profile = real_kb().profile("PEMBROLIZUMAB")
    odd = dataclasses.replace(
        profile,
        red_rules=(
            *profile.red_rules,
            dataclasses.replace(
                profile.red_rules[0], id="R_X", expr=parser.parse("n_ge1 >= n_ge2")
            ),
        ),
    )
    plain, blocked = domain_caps(profile), domain_caps(odd)
    natural = {a.id: a.max_value for a in profile.aggregates}
    assert blocked["n_ge1"] == natural["n_ge1"] > plain["n_ge1"]
    assert blocked["n_ge2"] == natural["n_ge2"] > plain["n_ge2"]
    assert blocked["max_grade"] == plain["max_grade"]


@pytest.mark.parametrize("leaf", profile_ids())
def test_compression_does_not_change_any_teacher_result_on_the_natural_grid(
    built: dict[str, CompiledComponent], leaf: str
) -> None:
    """Lehrer(x) == Baum(min(x, Kappe)) an jedem Punkt des UNGEKÜRZTEN Gitters (V1 ungekürzt)."""
    report = verify_component(real_kb().profile(leaf), built[leaf], uncompressed=True)
    assert report.uncompressed is not None
    assert report.uncompressed.points == built[leaf].natural_points
    assert (report.uncompressed.under, report.uncompressed.over) == (0, 0)


def test_grid_above_max_product_is_a_compilation_error_not_a_sampled_check() -> None:
    with pytest.raises(CompilationError, match="above max_product 1000"):
        compile_component(real_kb().profile("FOLFOX"), max_product=1000)


# ---- Baum: Exaktheit, Partition, Determinismus --------------------------------------------
@pytest.mark.parametrize("leaf", profile_ids())
def test_trees_are_exact_monotone_and_partition_the_grid(
    built: dict[str, CompiledComponent], leaf: str
) -> None:
    profile = real_kb().profile(leaf)
    report = verify_component(profile, built[leaf])
    assert report.ok, report
    assert (report.under, report.over, report.monotone_violations) == (0, 0, 0)
    assert (report.red_not_yellow, report.partition_gaps) == (0, 0)
    assert (report.corner_mismatches, report.sample_mismatches) == (0, 0)
    assert report.points == built[leaf].grid_points
    # Rohgitter bis max_exhaustive vollständig; größere (PAZOPANIB 8,4 Mio., NIVOLUMAB 2,1 Mio.)
    # nur per Stichprobe mit festem Seed; der Bericht muss das ehrlich so ausweisen
    assert report.raw.exhaustive == (raw_grid(profile).total <= verify.MAX_EXHAUSTIVE_RAW)
    assert report.raw.points > 0
    assert (report.raw.v3_violations, report.raw.v4_violations) == (0, 0)
    assert report.raw.engine_mismatches == 0


@pytest.mark.parametrize("leaf", profile_ids())
def test_leaf_boxes_do_not_overlap_and_cover_the_grid(
    built: dict[str, CompiledComponent], leaf: str
) -> None:
    compiled = built[leaf]
    for tree in (compiled.yellow, compiled.red):
        boxes = tree.boxes(compiled.caps)
        volume = 0
        for box in boxes:
            volume += _volume(box.lo, box.hi)
        assert volume == compiled.grid_points
        for first, second in itertools.combinations(boxes, 2):
            disjoint = any(
                a_hi < b_lo or b_hi < a_lo
                for a_hi, b_lo, b_hi, a_lo in zip(
                    first.hi, second.lo, second.hi, first.lo, strict=True
                )
            )
            assert disjoint


def _volume(lo: tuple[int, ...], hi: tuple[int, ...]) -> int:
    total = 1
    for a, b in zip(lo, hi, strict=True):
        total *= b - a + 1
    return total


@pytest.mark.parametrize("leaf", profile_ids())
def test_leaf_ids_are_unique_stable_and_listed_in_the_header_hash(
    built: dict[str, CompiledComponent], leaf: str
) -> None:
    compiled = built[leaf]
    for tree in (compiled.yellow, compiled.red):
        ids = [i for i, f in zip(tree.leaf_id, tree.feature, strict=True) if f == -1]
        assert len(ids) == len(set(ids)) == tree.leaves
        assert all(len(i) == 12 for i in ids)
    again = compile_component(real_kb().profile(leaf))
    assert again.hash == compiled.hash
    assert again.yellow.leaf_id == compiled.yellow.leaf_id


def test_compilation_is_deterministic_and_the_hash_depends_only_on_the_knowledge_base() -> None:
    kb = real_kb()
    first = compile_component(kb.profile("FOLFOX"))
    second = compile_component(kb.profile("FOLFOX"))
    assert first.to_dict() == second.to_dict()
    assert first.hash == second.hash
    assert first.compiler_version == compiler.COMPILER_VERSION
    raw, _, _ = real_inputs()
    base = next(p for p in raw["profiles"] if p["id"] == "base")
    base["teacher"]["red"][0]["when"] = "max_critical >= 2"
    other = build_from(raw)
    assert compile_component(other.profile("FOLFOX")).hash != first.hash


def test_trees_are_small_enough_to_read(built: dict[str, CompiledComponent]) -> None:
    for compiled in built.values():
        assert compiled.yellow.leaves <= 20
        assert compiled.red.leaves <= 10
        assert compiled.yellow.depth <= 12
        assert compiled.red.depth <= 8


def test_json_round_trip_keeps_behaviour_and_hash(built: dict[str, CompiledComponent]) -> None:
    compiled = built["FOLFOX"]
    restored = CompiledComponent.from_dict(compiled.to_dict())
    assert restored.to_dict() == compiled.to_dict()
    values = dict.fromkeys(compiled.features, 1)
    assert restored.classify(values) == compiled.classify(values)
    assert Tree.from_dict(compiled.red.to_dict()) == compiled.red


def test_compiled_component_caps_values_above_the_cap() -> None:
    compiled = compile_component(real_kb().profile("FOLFOX"))
    high = dict(zip(compiled.features, compiled.natural, strict=True))
    capped = dict(zip(compiled.features, compiled.caps, strict=True))
    assert compiled.classify(high) == compiled.classify(capped)
    assert compiled.vector(high) == tuple(compiled.caps)


# ---- Negativtests der Verifikation --------------------------------------------------------
def _with_values(tree: Tree, flips: dict[int, int]) -> Tree:
    values = list(tree.value)
    for node, new in flips.items():
        values[node] = new
    return dataclasses.replace(tree, value=tuple(values))


def _leaf_nodes(tree: Tree, cls: int) -> list[int]:
    return [n for n, f in enumerate(tree.feature) if f == -1 and tree.value[n] == cls]


def test_swapped_leaves_are_detected_as_non_monotone_and_inexact(
    built: dict[str, CompiledComponent],
) -> None:
    profile, compiled = real_kb().profile("FOLFOX"), built["FOLFOX"]
    ones, zeros = _leaf_nodes(compiled.red, 1), _leaf_nodes(compiled.red, 0)
    broken_tree = _with_values(compiled.red, {ones[0]: 0, zeros[0]: 1})
    broken = dataclasses.replace(compiled, red=broken_tree)
    report = verify_component(profile, broken)
    assert not report.ok
    assert report.under > 0
    assert report.over > 0
    assert report.monotone_violations > 0 or report.raw.v3_violations > 0


def test_tree_with_under_triage_fails_v1_and_the_start_check(
    built: dict[str, CompiledComponent],
) -> None:
    _profile, compiled = real_kb().profile("PEMBROLIZUMAB"), built["PEMBROLIZUMAB"]
    victim = _leaf_nodes(compiled.yellow, 1)[0]
    broken = dataclasses.replace(compiled, yellow=_with_values(compiled.yellow, {victim: 0}))
    composition = real_kb().resolve("PEMBROLIZUMAB")
    report = verify_composition(composition, [broken])
    assert report.under > 0
    assert report.verification_scope == "exhaustive_raw"  # Standard: jeder Punkt, auch ungekürzt
    with pytest.raises(VerificationError, match="under="):
        require_clean(report)


def test_tree_with_over_triage_is_reported_as_over(built: dict[str, CompiledComponent]) -> None:
    profile, compiled = real_kb().profile("PEMBROLIZUMAB"), built["PEMBROLIZUMAB"]
    victim = _leaf_nodes(compiled.red, 0)[0]
    broken = dataclasses.replace(compiled, red=_with_values(compiled.red, {victim: 1}))
    report = verify_component(profile, broken)
    assert report.over > 0
    assert not report.ok


def test_red_without_yellow_is_detected(built: dict[str, CompiledComponent]) -> None:
    profile, compiled = real_kb().profile("PEMBROLIZUMAB"), built["PEMBROLIZUMAB"]
    all_zero = _with_values(compiled.yellow, dict.fromkeys(_leaf_nodes(compiled.yellow, 1), 0))
    report = verify_component(profile, dataclasses.replace(compiled, yellow=all_zero))
    assert report.red_not_yellow > 0
    assert not report.ok


def test_box_monotonicity_on_hand_made_boxes() -> None:
    from waechter.triage.compiler import Box

    low_one = Box((0, 0), (1, 1), 1, "a")
    high_zero = Box((2, 2), (3, 3), 0, "b")
    assert monotone_violations([low_one, high_zero]) == 1  # 1-Blatt unterhalb eines 0-Blatts
    assert monotone_violations([Box((2, 2), (3, 3), 1, "a"), Box((0, 0), (1, 1), 0, "b")]) == 0
    assert monotone_violations([low_one]) == 0


def test_partition_gap_is_reported_for_a_tree_that_misses_a_region(
    built: dict[str, CompiledComponent],
) -> None:
    profile, compiled = real_kb().profile("PEMBROLIZUMAB"), built["PEMBROLIZUMAB"]
    tree = compiled.red
    root = 0
    cut = dataclasses.replace(
        tree,
        threshold=(tree.threshold[root] + 1, *tree.threshold[1:]),
    )
    report = verify_component(profile, dataclasses.replace(compiled, red=cut))
    assert not report.ok  # verschobene Schwelle ⇒ Abweichung gegenüber dem Lehrer


def test_paint_marks_exactly_the_positive_boxes(built: dict[str, CompiledComponent]) -> None:
    compiled = built["PEMBROLIZUMAB"]
    grid = make_grid(compiled.features, compiled.caps)
    cells = paint(compiled.red.boxes(compiled.caps), grid)
    positives = sum(_volume(b.lo, b.hi) for b in compiled.red.boxes(compiled.caps) if b.cls == 1)
    assert sum(cells) == positives


# ---- render_rules -------------------------------------------------------------------------
@pytest.mark.parametrize("leaf", profile_ids())
def test_rendered_rules_re_evaluated_with_the_safe_parser_equal_the_tree_on_the_whole_grid(
    built: dict[str, CompiledComponent], leaf: str
) -> None:
    profile, compiled = real_kb().profile(leaf), built[leaf]
    rules = render_rules(profile, compiled)
    grid = make_grid(compiled.features, compiled.caps)

    def union(level: str) -> int:
        merged = 0
        for rule in rules:
            if rule.level == level:
                merged |= int.from_bytes(truth_array(grid, parser.parse(rule.expression)), "big")
        return merged

    red, yellow = union("RED"), union("YELLOW") | union("RED")
    rendered = (red + yellow).to_bytes(grid.total, "big")  # 0/1/2 je Gitterpunkt (red ⊂ yellow)
    expected = bytes(
        2 if r else 1 if y else 0
        for y, r in zip(
            paint(compiled.yellow.boxes(compiled.caps), grid),
            paint(compiled.red.boxes(compiled.caps), grid),
            strict=True,
        )
    )
    assert rendered == expected
    assert expected == teacher_level_array(profile, grid)


def test_rendered_rules_are_simplified_ordered_and_explained(
    built: dict[str, CompiledComponent],
) -> None:
    profile, compiled = real_kb().profile("FOLFOX"), built["FOLFOX"]
    rules = render_rules(profile, compiled)
    levels = [r.level for r in rules]
    assert levels == sorted(levels, key=lambda lv: lv != "RED")  # Rot zuerst
    assert levels.count("RED") == sum(1 for b in compiled.red.boxes(compiled.caps) if b.cls == 1)
    leaf_ids = set(compiled.red.leaf_id) | set(compiled.yellow.leaf_id)
    for rule in rules:
        per_feature: dict[str, list[str]] = {}
        for name, op, _ in rule.conditions:
            per_feature.setdefault(name, []).append(op)
        assert all(sorted(ops) in (["<="], [">="], ["<=", ">="]) for ops in per_feature.values())
        assert rule.leaf_id in leaf_ids
        assert (
            rule.teacher_rule_ids
        )  # jede positive Box wird von mindestens einer Lehrerregel getragen
        assert rule.text["cs"]
        assert rule.text["en"]
        assert rule.text["de"]
    assert any("Highest symptom grade" in r.text["en"] for r in rules)
    assert any("Nejvyšší stupeň příznaku" in r.text["cs"] for r in rules)


def test_evaluate_rendered_matches_the_compiled_classification_on_random_points(
    built: dict[str, CompiledComponent],
) -> None:
    import random

    profile, compiled = real_kb().profile("DOCETAXEL"), built["DOCETAXEL"]
    rules = render_rules(profile, compiled)
    rng = random.Random(5)
    for _ in range(1500):
        values = {
            n: rng.randint(0, cap) for n, cap in zip(compiled.features, compiled.caps, strict=True)
        }
        assert evaluate_rendered(rules, values) == compiled.classify(values)[0]


# ---- H1: Zusammensetzung mit genau einer Komponente ---------------------------------------
@pytest.mark.parametrize("leaf", profile_ids())
def test_resolve_gives_one_component_with_unchanged_hash_and_items(leaf: str) -> None:
    kb = real_kb()
    composition = kb.resolve(leaf)
    profile = kb.profile(leaf)
    assert [c.id for c in composition.components] == [leaf]
    assert composition.composition_hash == profile.hash == GOLDEN_PROFILE_HASHES[leaf]
    assert composition.coverage_gap is False
    assert composition.composition_status == profile.status == "placeholder"
    assert composition.max_questions == profile.max_questions
    assert composition.q_worst_total == profile.full_question_count
    assert dict(composition.items) == dict(profile.items)


def test_includes_must_be_empty_and_an_empty_list_changes_no_hash() -> None:
    raw, attributes, regimens = real_inputs()
    plain = build_kb(raw, attributes=attributes, regimens=regimens)
    with_empty = real_inputs()[0]
    for profile in with_empty["profiles"]:
        profile["includes"] = []
    empty = build_kb(with_empty, attributes=attributes, regimens=regimens)
    for leaf in profile_ids():
        assert empty.profile(leaf).hash == plain.profile(leaf).hash == GOLDEN_PROFILE_HASHES[leaf]
    with_module = real_inputs()[0]
    next(p for p in with_module["profiles"] if p["id"] == "chemo")["includes"] = ["MOD-X"]
    with pytest.raises(TriageError, match="includes"):
        build_kb(with_module, attributes=attributes, regimens=regimens)


# ---- H4: Bericht --------------------------------------------------------------------------
def test_report_has_components_scope_and_the_card_shape() -> None:
    runtime = runtime_for(real_kb(), "PEMBROLIZUMAB")
    body: dict[str, Any] = runtime.report.to_dict()
    assert body["scope"] == "exhaustive_raw"
    assert (body["under"], body["over"], body["monotone_violations"]) == (0, 0, 0)
    assert body["points"] == 13_824
    (component,) = body["components"]
    assert component["component_id"] == "PEMBROLIZUMAB"
    assert {"points", "under", "over", "monotone_violations", "leaves", "depth"} <= set(component)
    assert component["uncompressed_points"] == 93_312
    assert runtime.tree_version == canonical_hash([c.hash for c in runtime.compiled])
    assert runtime.rules  # Regelkarte vorhanden
    assert runtime_for(real_kb(), "PEMBROLIZUMAB") is runtime  # Cache


def test_scope_is_exhaustive_only_when_every_point_was_checked() -> None:
    composition = real_kb().resolve("PEMBROLIZUMAB")
    compiled = [compile_component(c) for c in composition.components]
    full = verify_composition(composition, compiled)
    skipped = verify_composition(composition, compiled, uncompressed=False)
    assert full.verification_scope == "exhaustive_raw"
    assert skipped.verification_scope == "sampled_raw"  # ungekürztes Gitter nicht geprüft
    assert full.to_dict()["scope"] == "exhaustive_raw"


def test_a_sampled_scope_is_reported_when_the_raw_grid_is_too_large() -> None:
    kb = real_kb()
    composition = kb.resolve("PEMBROLIZUMAB")
    compiled = [compile_component(c) for c in composition.components]
    report = verify_composition(composition, compiled, max_exhaustive=1000)
    assert report.verification_scope == "sampled_raw"
    assert report.ok
    assert all(not c.raw.exhaustive for c in report.components)


def test_runtime_refuses_to_start_on_a_failed_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    from waechter.triage import runtime as runtime_module

    kb = real_kb()
    real_compile = compiler.compile_component

    def broken(component: Any, **kwargs: Any) -> CompiledComponent:
        good = real_compile(component, **kwargs)
        victim = _leaf_nodes(good.yellow, 1)[0]
        return dataclasses.replace(good, yellow=_with_values(good.yellow, {victim: 0}))

    monkeypatch.setattr(compiler, "compile_component", broken)
    runtime_module._CACHE.clear()
    with pytest.raises(VerificationError):
        runtime_for(kb, "PEMBROLIZUMAB")
    runtime_module._CACHE.clear()


def test_level_enum_order_is_the_triage_order() -> None:
    assert Level.GREEN < Level.YELLOW < Level.RED
