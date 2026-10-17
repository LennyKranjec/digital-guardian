"""A3-Gegenproben zu T-15 (Compiler, Verifier, CompiledEngine, Regelkarte, Kontrafaktische).

Alles gegen die unabhängige Referenz `a3_triage_ref.py` (eigener Parser, eigener Lehrer, eigene
Domänenkompression) und gegen einen EIGENEN Baum-Läufer über den exportierten JSON-Baum, nicht
über `Tree.predict` oder A2s Verifier. Standard: komprimiertes Gitter vollständig, ungekürztes
Gitter mit Schrittweite; `A3_FULL_GRID=1` prüft das ungekürzte Gitter vollständig.
"""

import copy
import itertools
import json
import os
import random
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

import a3_triage_ref as ref
from test_a3_t14 import (
    LEAVES,
    RAW,
    build,
    random_truth,
    reference,
    run_session,
    session_setup,
    truth_grades,
)
from waechter.triage import compiler
from waechter.triage.counterfactual import counterfactuals
from waechter.triage.engine import CompiledEngine
from waechter.triage.kb import KnowledgeBase, TriageError, load_kb
from waechter.triage.policy import FlipPolicy
from waechter.triage.runtime import ProfileRuntime, runtime_for
from waechter.triage.verify import verify_component, verify_composition

CONTENT = Path(__file__).resolve().parents[1] / "content"
FULL = os.environ.get("A3_FULL_GRID") == "1"
STRIDE_RAW = 1 if FULL else 53
NAMES = {0: "GREEN", 1: "YELLOW", 2: "RED"}


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_kb()


_RUNTIMES: dict[str, ProfileRuntime] = {}


def runtime(kb: KnowledgeBase, leaf: str) -> ProfileRuntime:
    if leaf not in _RUNTIMES:
        _RUNTIMES[leaf] = runtime_for(kb, leaf)
    return _RUNTIMES[leaf]


# --- eigener Baum-Läufer über den exportierten JSON-Baum --------------------------------------


def walk(nodes: list[dict[str, Any]], x: tuple[int, ...]) -> int:
    node = nodes[0]
    while "leaf" not in node:
        node = nodes[node["l"] if x[node["f"]] <= node["t"] else node["r"]]
    return int(node["leaf"])


def exported(compiled: compiler.CompiledComponent) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(json.dumps(compiled.to_dict()))
    return data


def tree_level(data: dict[str, Any], x: tuple[int, ...]) -> str:
    yellow, red = walk(data["yellow"]["nodes"], x), walk(data["red"]["nodes"], x)
    if red and not yellow:
        return "INCONSISTENT"
    return "RED" if red else "YELLOW" if yellow else "GREEN"


def point_dict(names: list[str], x: tuple[int, ...]) -> dict[str, int]:
    return dict(zip(names, x, strict=True))


def compare(
    data: dict[str, Any],
    mine: ref.Profile,
    caps: list[int],
    domains: list[int],
    stride: int = 1,
) -> list[str]:
    """Baumlevel (Eingabe auf `caps` gekappt) gegen den Referenzlehrer über das Gitter `domains`."""
    names = [a.id for a in mine.aggregates]
    bad: list[str] = []
    points = itertools.product(*[range(d + 1) for d in domains])
    for x in itertools.islice(points, 0, None, stride):
        got = tree_level(data, tuple(min(v, c) for v, c in zip(x, caps, strict=True)))
        want = ref.teacher_level(mine, point_dict(names, x))
        if got != want:
            bad.append(f"{point_dict(names, x)}: Lehrer {want}, Baum {got}")
            if len(bad) >= 5:
                break
    return bad


# --- Köpfe: Gitter, Domänen, Kompression ------------------------------------------------------


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_compiled_header_matches_the_reference_domains(kb: KnowledgeBase, leaf: str) -> None:
    mine = reference(leaf)
    built = runtime(kb, leaf).compiled[0]
    names = [a.id for a in mine.aggregates]
    assert list(built.features) == names
    assert list(built.natural) == [a.domain_max for a in mine.aggregates]
    expected = ref.compressed_domains(mine)
    assert list(built.caps) == [expected[n] for n in names]
    assert built.grid_points == ref.compressed_size(mine)
    assert built.natural_points == ref.grid_size(mine)
    assert built.grid_points <= 2_000_000


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_reference_confirms_that_compression_does_not_change_the_teacher(leaf: str) -> None:
    """Die Kürzung selbst ist gerechtfertigt: ungekürztes Gitter == gekürzt (unabhängig geprüft)."""
    assert ref.check_compression(reference(leaf), 1 if FULL else 61) == []


# --- Exakter Baum == Lehrer -------------------------------------------------------------------


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_exported_tree_equals_the_reference_teacher_on_the_compressed_grid(
    kb: KnowledgeBase, leaf: str
) -> None:
    mine = reference(leaf)
    built = runtime(kb, leaf).compiled[0]
    data = exported(built)
    caps = list(built.caps)
    assert compare(data, mine, caps, caps) == []


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_exported_tree_equals_the_reference_teacher_on_the_uncompressed_grid(
    kb: KnowledgeBase, leaf: str
) -> None:
    mine = reference(leaf)
    built = runtime(kb, leaf).compiled[0]
    data = exported(built)
    assert compare(data, mine, list(built.caps), list(built.natural), STRIDE_RAW) == []


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_tree_is_monotone_and_red_implies_yellow(kb: KnowledgeBase, leaf: str) -> None:
    built = runtime(kb, leaf).compiled[0]
    data = exported(built)
    caps = list(built.caps)
    levels: dict[tuple[int, ...], str] = {}
    rank = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    for x in itertools.product(*[range(c + 1) for c in caps]):
        level = tree_level(data, x)
        assert level != "INCONSISTENT", f"rot ohne gelb bei {x}"
        levels[x] = level
    for x, level in levels.items():
        for axis, cap in enumerate(caps):
            if x[axis] < cap:
                up = (*x[:axis], x[axis] + 1, *x[axis + 1 :])
                assert rank[levels[up]] >= rank[level], f"sinkt bei {x} -> {up}"


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_tree_structure_is_sane(kb: KnowledgeBase, leaf: str) -> None:
    built = runtime(kb, leaf).compiled[0]
    data = exported(built)
    for tree in ("yellow", "red"):
        nodes = data[tree]["nodes"]
        seen: set[int] = set()

        def visit(index: int, nodes: list[dict[str, Any]] = nodes, seen: set[int] = seen) -> None:
            assert index not in seen, "Knoten doppelt erreichbar (kein Baum)"
            seen.add(index)
            node = nodes[index]
            if "leaf" in node:
                assert node["leaf"] in (0, 1)
                assert node["id"]
                return
            assert 0 <= node["f"] < len(built.caps)
            assert 0 <= node["t"] < built.caps[node["f"]], "Schwelle außerhalb der Domäne"
            visit(node["l"])
            visit(node["r"])

        visit(0)
        assert len(seen) == len(nodes), "unerreichbare Knoten"
    # Blatt-IDs eindeutig je Baum
    for tree in ("yellow", "red"):
        ids = [n["id"] for n in data[tree]["nodes"] if "id" in n]
        assert len(ids) == len(set(ids))


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_compiling_twice_gives_the_same_tree_hash(kb: KnowledgeBase, leaf: str) -> None:
    component = kb.resolve(leaf).components[0]
    first, second = compiler.compile_component(component), compiler.compile_component(component)
    assert first.hash == second.hash
    assert exported(first) == exported(second)
    assert first.hash == runtime(kb, leaf).compiled[0].hash


# --- Der Verifier erkennt verfälschte Bäume (sonst wäre „verifiziert“ wertlos) ----------------


def tampered(built: compiler.CompiledComponent, how: str) -> compiler.CompiledComponent:
    data = exported(built)
    nodes = data["red"]["nodes"]
    if how == "leaf":
        leaf = next(n for n in nodes if "leaf" in n and n["leaf"] == 1)
        leaf["leaf"] = 0
    elif how == "threshold":
        inner = next(n for n in nodes if "f" in n and n["t"] + 1 < built.caps[n["f"]])
        inner["t"] += 1
    else:
        raise AssertionError(how)
    return compiler.CompiledComponent.from_dict(data)


@pytest.mark.parametrize("how", ["leaf", "threshold"])
@pytest.mark.parametrize("leaf", ["PEMBROLIZUMAB", "FOLFOX"])
def test_a3_tampered_tree_is_detected_by_the_reference_and_by_the_verifier(
    kb: KnowledgeBase, leaf: str, how: str
) -> None:
    mine = reference(leaf)
    good = runtime(kb, leaf).compiled[0]
    bad = tampered(good, how)
    caps = list(good.caps)
    assert compare(exported(bad), mine, caps, caps) != [], "A3-Vergleich übersieht die Fälschung"
    component = kb.resolve(leaf).components[0]
    report = verify_component(component, bad)
    assert not report.ok, "Verifier meldet einen verfälschten Baum als sauber"


# --- CompiledEngine == Referenz (Endlevel mit Böden und Trend) --------------------------------


def random_grades(mine: ref.Profile, rng: random.Random) -> dict[str, int]:
    symptoms = sorted(ref.profile_symptoms(RAW, mine.id))
    grades = dict.fromkeys(symptoms, 0)
    for s in rng.sample(symptoms, rng.randint(0, min(5, len(symptoms)))):
        grades[s] = rng.randint(0, 3)
    return grades


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_compiled_engine_final_level_equals_the_reference(kb: KnowledgeBase, leaf: str) -> None:
    mine = reference(leaf)
    engine = runtime(kb, leaf).engine
    rng = random.Random(1500 + len(leaf))  # noqa: S311 - fester Seed
    grade_max = {i.key: i.grade_max for i in mine.items.values()}
    checked = 0
    for _ in range(4000):
        grades = {s: min(g, grade_max[s]) for s, g in random_grades(mine, rng).items()}
        previous = None if rng.random() < 0.5 else {s: rng.randint(0, 1) for s in grades}
        want = ref.final_level(mine, grades, previous)
        got = engine.level_from_grades(grades, previous).level
        assert NAMES[int(got)] == want, (grades, previous)
        checked += 1
    assert checked == 4000


# --- Regelkarte (render_rules) ----------------------------------------------------------------


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_rendered_rules_evaluate_like_the_reference_teacher(
    kb: KnowledgeBase, leaf: str
) -> None:
    """Die lesbare Regelkarte (Ausdruck als Text) wertet mit MEINEM Parser wie der Lehrer aus."""
    mine = reference(leaf)
    built = runtime(kb, leaf).compiled[0]
    rules = runtime(kb, leaf).rules
    parsed = [(r.level, ref.parse(r.expression)) for r in rules]
    names = list(built.features)
    caps = list(built.caps)
    assert rules, "keine Regeln gerendert"
    for r in rules:
        assert r.expression.isascii()
        assert set(r.text) >= {"cs", "en", "de"}
        assert all(r.text[lang].strip() for lang in ("cs", "en", "de"))
    stride = 1 if leaf == "PEMBROLIZUMAB" else 7
    for x in itertools.islice(itertools.product(*[range(c + 1) for c in caps]), 0, None, stride):
        env = point_dict(names, x)
        got = "GREEN"
        for level in ("RED", "YELLOW"):
            if any(ref.evaluate(node, env) for lvl, node in parsed if lvl == level):
                got = level
                break
        assert got == ref.teacher_level(mine, env), env


# --- Verifikationsbericht ---------------------------------------------------------------------


def test_a3_verification_report_numbers_match_the_reference(kb: KnowledgeBase) -> None:
    leaf = "PEMBROLIZUMAB"
    mine = reference(leaf)
    full = runtime(
        kb, leaf
    )  # runtime_for-Cache ignoriert full_check: eigener Bericht mit ungekürzt
    data = verify_composition(full.composition, full.compiled, uncompressed=True).to_dict()
    component = data["components"][0]
    assert data["scope"] in ("exhaustive_raw", "sampled_raw")
    assert component["points"] == ref.compressed_size(mine)
    assert component["uncompressed_points"] == ref.grid_size(mine)
    assert (component["under"], component["over"], component["monotone_violations"]) == (0, 0, 0)
    assert component["v3_violations"] == 0
    assert component["v4_violations"] == 0
    assert component["leaves"]["yellow"] == full.compiled[0].yellow.leaves
    assert component["leaves"]["red"] == full.compiled[0].red.leaves


# --- Grenzen und Angriffe ---------------------------------------------------------------------


def test_a3_grid_above_max_product_is_refused_not_sampled(kb: KnowledgeBase) -> None:
    component = kb.resolve("PEMBROLIZUMAB").components[0]
    with pytest.raises(compiler.CompilationError):
        compiler.compile_component(component, max_product=1000)


def variant(
    mutate: Callable[[dict[str, Any]], None],
) -> tuple[KnowledgeBase, dict[str, Any]]:
    raw = copy.deepcopy(RAW)
    mutate(raw)
    return build(raw), raw


def add_rule(raw: dict[str, Any], profile: str, color: str, rule_id: str, when: str) -> None:
    target = next(p for p in raw["profiles"] if p["id"] == profile)
    target.setdefault("teacher", {}).setdefault(color, []).append(
        {
            "id": rule_id,
            "when": when,
            "text": {"cs": "Testregel", "en": "Test rule"},
            "assumption": "A-TRI-04",
            "status": "placeholder",
        }
    )


def check_variant(leaf: str, rule_when: str, color: str = "yellow") -> None:
    kb2, raw2 = variant(lambda raw: add_rule(raw, "base", color, "Y_A3_TEST", rule_when))
    mine = ref.resolve(raw2, leaf)
    built = compiler.compile_component(kb2.resolve(leaf).components[0])
    expected = ref.compressed_domains(mine)
    assert list(built.caps) == [expected[a.id] for a in mine.aggregates]
    data = exported(built)
    caps = list(built.caps)
    assert compare(data, mine, caps, caps) == []
    assert compare(data, mine, caps, list(built.natural), 11) == []


def test_a3_aggregate_against_aggregate_rule_is_a_load_error_not_a_wrong_compression() -> None:
    """Angriff: Vergleich Aggregat/Aggregat (nicht monoton) darf nie kompiliert werden."""
    with pytest.raises(TriageError, match="not monotone"):
        variant(lambda raw: add_rule(raw, "base", "yellow", "Y_A3_TEST", "n_ge1 > n_ge2"))


def test_a3_rule_on_a_new_constant_changes_domain_and_tree() -> None:
    """Angriff: neue Schwelle (n_ge3 >= 2) ändert Kappe und Baum; Kürzung bleibt exakt."""
    check_variant("PEMBROLIZUMAB", "n_ge3 >= 2 and max_grade >= 2", "red")


def test_a3_changing_a_threshold_changes_the_tree_hash(kb: KnowledgeBase) -> None:
    kb2, _ = variant(lambda raw: add_rule(raw, "base", "yellow", "Y_A3_TEST", "n_ge1 >= 3"))
    changed = compiler.compile_component(kb2.resolve("PEMBROLIZUMAB").components[0])
    assert changed.hash != runtime(kb, "PEMBROLIZUMAB").compiled[0].hash


# --- Kontrafaktische gegen die Referenz -------------------------------------------------------


def apply(grades: Mapping[str, int], changes: Any) -> dict[str, int]:
    out = dict(grades)
    for change in changes:
        assert out[change.symptom_key] == change.from_grade
        out[change.symptom_key] = change.to_grade
    return out


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_counterfactuals_are_true_and_minimal_against_the_reference(
    kb: KnowledgeBase, leaf: str
) -> None:
    mine = reference(leaf)
    engine = runtime(kb, leaf).engine
    rank = ref.RANK
    rng = random.Random(1600 + len(leaf))  # noqa: S311 - fester Seed
    grade_max = {i.key: i.grade_max for i in mine.items.values()}
    seen_lower = seen_raise = seen_shield = 0
    for _ in range(300):
        grades = {s: min(g, grade_max[s]) for s, g in random_grades(mine, rng).items()}
        base = ref.final_level(mine, grades, None)
        for cf in counterfactuals(engine, grades, None):
            if cf.kind == "shield":
                seen_shield += 1
                assert cf.api_kind == "shield"
                assert cf.floor_id
                # Schild: keine einzelne Absenkung eines Symptoms senkt das Level
                for symptom, grade in grades.items():
                    for g in range(grade):
                        lowered = {**grades, symptom: g}
                        assert rank[ref.final_level(mine, lowered, None)] >= rank[base]
                continue
            assert cf.api_kind == "change"
            after = ref.final_level(mine, apply(grades, cf.changes), None)
            if cf.direction == "lower":
                seen_lower += 1
                assert rank[after] < rank[base], (grades, cf)
            else:
                seen_raise += 1
                assert rank[after] > rank[base], (grades, cf)
            if cf.kind == "single" and cf.direction == "lower":
                change = cf.changes[0]
                # nächstliegende Absenkung: ein größerer Zielgrad senkt das Level nicht
                for g in range(change.to_grade + 1, change.from_grade):
                    alt = {**grades, change.symptom_key: g}
                    assert rank[ref.final_level(mine, alt, None)] >= rank[base], (grades, cf)
    assert seen_lower + seen_raise + seen_shield > 0


# --- Sitzungen mit CompiledEngine: Protokollprüfer und Untertriage ----------------------------


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_compiled_sessions_pass_the_reference_checker_and_never_under_triage(
    kb: KnowledgeBase, leaf: str
) -> None:
    theirs, mine, _, order, askable, esc = session_setup(kb, leaf)
    rt = runtime(kb, leaf)
    policy = FlipPolicy(CompiledEngine(theirs, rt.compiled))
    rng = random.Random(1700 + len(leaf))  # noqa: S311 - fester Seed
    problems: list[str] = []
    under = 0
    for _ in range(250):
        truth = random_truth(theirs, order, rng, esc)
        previous = None if rng.random() < 0.5 else {s: rng.randint(0, 1) for s in theirs.symptoms}
        transcript, stop = run_session(policy, truth, rng, previous, 0.0)
        grades = {s: g if s in askable else 0 for s, g in truth_grades(theirs, truth).items()}
        problems += ref.check_transcript(mine, order, transcript, grades, askable, esc, previous)
        want = ref.final_level(mine, grades, previous)
        if stop.reason == "decided" and NAMES[int(stop.level_lo)] != want:
            under += 1
    assert problems == [], problems[:5]
    assert under == 0


def test_a3_yaml_content_is_unchanged_by_the_loader() -> None:
    """Sicherung gegen stille Änderungen: die Referenz liest dieselbe Datei wie der Lader."""
    raw = yaml.safe_load((CONTENT / "triage.yaml").read_text(encoding="utf-8"))
    assert raw == RAW


def test_a3_runtime_cache_does_not_hand_out_a_weaker_verification_than_requested() -> None:
    kb2, _ = variant(lambda raw: add_rule(raw, "base", "yellow", "Y_A3_CACHE", "n_ge1 >= 5"))
    runtime_for(kb2, "PEMBROLIZUMAB", full_check=False)
    strong = runtime_for(kb2, "PEMBROLIZUMAB", full_check=True)
    component = strong.report.to_dict()["components"][0]
    assert component["uncompressed_points"] is not None
