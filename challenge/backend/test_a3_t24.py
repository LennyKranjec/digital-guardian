"""A3-Gegenproben zu T-24 (Module je Wirkstoffklasse, Diagnosemodule, Hooks H1/H2).

Der unabhaengige Referenzrechner `a3_triage_ref` kennt `includes`/`modules` nicht. Er bekommt
eine eigene, synthetische Zusammensetzung (Kette des Blattes, danach die Ketten der eingebundenen
Klassenprofile ohne Doppel, danach das Diagnosemodul) und rechnet den Lehrer, die Boeden und die
Sitzungen selbst. Verglichen werden der kompilierte Baum, die Verschaerfung gegenueber den
Bestandteilen und die Sitzungen. Dazu Angriffe auf die Zusammensetzung (Lockerung per Modul).
"""

import copy
import random
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import a3_triage_ref as ref
import test_a3_t14 as t14
from test_a3_t14 import random_truth, run_session, session_setup, truth_grades
from test_a3_t15 import STRIDE_RAW, compare, exported, runtime
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import content_dir, load_content
from waechter.services.questionnaire import diagnosis_group_for
from waechter.triage.engine import CompiledEngine
from waechter.triage.kb import KnowledgeBase, TriageError, build_kb, load_kb, read_triage_yaml
from waechter.triage.policy import FlipPolicy

REAL = Path(__file__).resolve().parents[1] / "content"
NAMES = {0: "GREEN", 1: "YELLOW", 2: "RED"}
RANK = {"GREEN": 0, "YELLOW": 1, "RED": 2}
COMPOSITIONS = [
    "COMBO_ICI_TKI",
    "PEMBROLIZUMAB+mod-dx-lung",
    "ENZALUTAMIDE+mod-dx-lung",
    "ABIRATERONE+mod-dx-lung",
]


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_kb()


def chain_of(by_id: dict[str, Any], profile_id: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = by_id[profile_id]
    while current is not None:
        nodes.append(current)
        current = by_id.get(current.get("extends", ""))
    nodes.reverse()
    return nodes


def synthetic(raw: dict[str, Any], composition_id: str) -> None:
    """Haengt die Zusammensetzung als Kette `a3c#i` an `raw["profiles"]` (Referenzlesart)."""
    by_id = {p["id"]: p for p in raw["profiles"]}
    modules = {m["id"]: m for m in raw.get("modules", [])}
    leaf_id, _, module_id = composition_id.partition("+")
    nodes = chain_of(by_id, leaf_id)
    seen = {n["id"] for n in nodes}
    for include in by_id[leaf_id].get("includes", []):
        for node in chain_of(by_id, include):
            if node["id"] not in seen:
                nodes.append(node)
                seen.add(node["id"])
    if module_id:
        nodes.append(modules[module_id])
    previous: str | None = None
    for index, node in enumerate(nodes):
        copy_ = copy.deepcopy(node)
        copy_.pop("includes", None)
        copy_.pop("regimen_ids", None)
        copy_["id"] = composition_id if index == len(nodes) - 1 else f"{composition_id}#{index}"
        if previous is None:
            copy_.pop("extends", None)
        else:
            copy_["extends"] = previous
        previous = copy_["id"]
        raw["profiles"].append(copy_)


@pytest.fixture(scope="module", autouse=True)
def reference_with_compositions(kb: KnowledgeBase) -> Iterator[dict[str, Any]]:
    raw = copy.deepcopy(t14.RAW)
    for composition_id in kb.compositions:
        synthetic(raw, composition_id)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(t14, "RAW", raw)
        yield raw


def test_a3_expected_compositions_are_loaded(kb: KnowledgeBase) -> None:
    assert set(COMPOSITIONS) <= set(kb.compositions)
    assert kb.diagnosis_modules == {"LUNG": "mod-dx-lung"}
    assert {*kb.profiles} == {
        "FOLFOX",
        "CAPECITABINE",
        "DOCETAXEL",
        "PEMBROLIZUMAB",
        "ENZALUTAMIDE",
        "ABIRATERONE",
        "PAZOPANIB",
        "NIVOLUMAB",
    }


@pytest.mark.parametrize("composition", COMPOSITIONS)
def test_a3_composition_header_equals_the_reference(kb: KnowledgeBase, composition: str) -> None:
    theirs, mine = kb.profile(composition), t14.reference(composition)
    assert set(theirs.symptoms) == set(mine.items)
    assert {a.id for a in theirs.aggregates} == {a.id for a in mine.aggregates}
    assert {r.id for r in theirs.red_rules} == {r.id for r in mine.red}
    assert {r.id for r in theirs.yellow_rules} == {r.id for r in mine.yellow}
    assert {r.id for r in theirs.floors} == {r.id for r in mine.floors}
    assert set(theirs.safety_items) == mine.safety_items


@pytest.mark.parametrize("composition", COMPOSITIONS)
def test_a3_composed_tree_equals_the_reference_teacher(kb: KnowledgeBase, composition: str) -> None:
    mine = t14.reference(composition)
    built = runtime(kb, composition).compiled[0]
    data = exported(built)
    caps = list(built.caps)
    assert compare(data, mine, caps, caps) == []
    assert compare(data, mine, caps, list(built.natural), STRIDE_RAW) == []


def random_point(profile: ref.Profile, rng: random.Random) -> dict[str, int]:
    return {
        key: rng.choice([0, 0, rng.randint(0, item.grade_max)])
        for key, item in profile.items.items()
    }


@pytest.mark.parametrize("composition", COMPOSITIONS)
def test_a3_composition_is_never_looser_than_its_components(
    kb: KnowledgeBase, composition: str, reference_with_compositions: dict[str, Any]
) -> None:
    """Nur verschaerfend: Niveau der Zusammensetzung >= Niveau jedes Bestandteils."""
    raw = reference_with_compositions
    by_id = {p["id"]: p for p in raw["profiles"]}
    leaf_id = composition.partition("+")[0]
    parts = [leaf_id] if leaf_id in kb.profiles else [by_id[leaf_id]["extends"]]
    parts += list(by_id[leaf_id].get("includes", []))
    whole = t14.reference(composition)
    rng = random.Random(2424)  # noqa: S311 - fester Seed
    checked = 0
    for part in parts:
        mine = t14.reference(part)
        for _ in range(4000):
            grades = random_point(whole, rng)
            sub = {k: v for k, v in grades.items() if k in mine.items}
            got = ref.final_level(whole, grades, None)
            lower = ref.final_level(mine, sub, None)
            checked += 1
            assert RANK[got] >= RANK[lower], (composition, part, grades, got, lower)
    assert checked > 0


@pytest.mark.parametrize("composition", COMPOSITIONS)
def test_a3_composed_sessions_never_under_triage(kb: KnowledgeBase, composition: str) -> None:
    theirs, mine, _, order, askable, esc = session_setup(kb, composition)
    rt = runtime(kb, composition)
    policy = FlipPolicy(CompiledEngine(theirs, rt.compiled))
    rng = random.Random(2400 + len(composition))  # noqa: S311 - fester Seed
    problems: list[str] = []
    under = over = 0
    for _ in range(300):
        truth = random_truth(theirs, order, rng, esc)
        previous = None if rng.random() < 0.5 else {s: rng.randint(0, 1) for s in theirs.symptoms}
        transcript, stop = run_session(policy, truth, rng, previous, 0.0)
        grades = {s: g if s in askable else 0 for s, g in truth_grades(theirs, truth).items()}
        problems += ref.check_transcript(mine, order, transcript, grades, askable, esc, previous)
        want = ref.final_level(mine, grades, previous)
        if stop.reason == "decided":
            got = NAMES[int(stop.level_lo)]
            under += RANK[got] < RANK[want]
            over += RANK[got] > RANK[want]
    assert problems == [], problems[:5]
    assert (under, over) == (0, 0)


# --- Diagnosegruppe waehlt die Variante ----------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "is_lung"),
    [
        ("C34.1", True),
        ("C34", True),
        ("C61", False),
        ("C50.9", False),
        ("C18.2", False),
        ("", False),
        (None, False),
        ("C340", False),
        ("XC34.1", False),
        ("c34.1", True),  # Gross-/Kleinschreibung egal
    ],
)
def test_a3_only_lung_codes_select_the_lung_group(code: str | None, is_lung: bool) -> None:
    content = load_content(content_dir())
    found = diagnosis_group_for(content, code)
    got = found["id"] if found else None
    assert (got == "LUNG") is is_lung, (code, got)


def test_a3_variant_for_never_returns_an_unknown_profile(kb: KnowledgeBase) -> None:
    for leaf in kb.profiles:
        for group in (None, "LUNG", "NOPE", ""):
            variant = kb.variant_for(leaf, group)
            assert variant in kb.profiles or variant in kb.compositions
            assert variant.startswith(leaf)


# --- Angriffe auf die Zusammensetzung ------------------------------------------------------------


def build(raw: Any) -> KnowledgeBase:
    content = load_content(content_dir())
    attributes = {
        item["symptom_key"]: [a["attribute"] for a in item["attributes"]]
        for item in content.items["items"]
    }
    regimens = {r["id"]: list(r["symptom_keys"]) for r in content.regimens["regimens"]}
    groups = [g["id"] for g in content.diagnoses["diagnoses"]] if content.diagnoses else None
    return build_kb(raw, attributes=attributes, regimens=regimens, diagnosis_groups=groups)


def fresh() -> Any:
    return copy.deepcopy(read_triage_yaml(content_dir()))


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda r: r["modules"][0]["cascade"].update(
                fatigue={"attributes_order": ["interference", "severity"]}
            ),
            id="cascade-order",
        ),
        pytest.param(
            lambda r: r["modules"][0]["aggregates"].append(
                {
                    "id": "max_critical",
                    "kind": "max_over",
                    "items": ["shortness_of_breath"],
                    "label": {"cs": "x", "en": "x"},
                }
            ),
            id="aggregate-redefined",
        ),
        pytest.param(
            lambda r: r["modules"].append(
                {**copy.deepcopy(r["modules"][0]), "id": "mod-dx-lung-2"}
            ),
            id="second-module-same-group",
        ),
        pytest.param(
            lambda r: r["modules"][0]["cascade"]["shortness_of_breath"].update(
                escalate_when="shortness_of_breath >= 99"
            ),
            id="unreachable-escalation",
        ),
    ],
)
def test_a3_module_attacks_that_are_refused(mutate: Any) -> None:
    raw = fresh()
    mutate(raw)
    with pytest.raises(TriageError):
        build(raw)


def test_a3_f01_a_module_cannot_lower_the_question_limit() -> None:
    raw = fresh()
    raw["modules"][0]["screening"] = {"max_questions": 3}
    try:
        kb_ = build(raw)
    except TriageError:
        return
    plain = kb_.profile("PEMBROLIZUMAB").max_questions
    assert kb_.find("PEMBROLIZUMAB+mod-dx-lung").max_questions >= plain  # type: ignore[union-attr]


def test_a3_f01_a_module_cannot_lower_the_rotation_slots() -> None:
    raw = fresh()
    raw["modules"][0]["screening"] = {"rotating_slots": 0}
    try:
        kb_ = build(raw)
    except TriageError:
        return
    plain = kb_.profile("FOLFOX").rotating_slots
    variant = kb_.find("FOLFOX+mod-dx-lung")
    assert variant is not None
    assert variant.rotating_slots >= min(plain, len(variant.rotation_pool))


def test_a3_f02_unknown_diagnosis_group_in_a_module_is_a_load_error() -> None:
    raw = fresh()
    raw["modules"][0]["diagnosis_groups"] = ["NOPE"]
    with pytest.raises(TriageError):
        build(raw)


def test_a3_existing_profile_hashes_do_not_change_when_modules_are_removed(
    kb: KnowledgeBase,
) -> None:
    raw = fresh()
    raw.pop("modules", None)
    raw["profiles"] = [p for p in raw["profiles"] if not p.get("includes")]
    plain = build(raw)
    assert {k: v.hash for k, v in plain.profiles.items()} == {
        k: v.hash for k, v in kb.profiles.items()
    }
    assert not plain.compositions


def test_a3_rotation_pool_loses_exactly_the_symptoms_the_module_asks_every_time(
    kb: KnowledgeBase,
) -> None:
    for leaf in kb.profiles:
        base, variant = kb.profile(leaf), kb.profile(f"{leaf}+mod-dx-lung")
        asked = {*variant.fixed_items, *variant.safety_items}
        assert not set(variant.rotation_pool) & asked, leaf
        assert set(base.rotation_pool) - set(variant.rotation_pool) <= asked, leaf
        assert set(variant.fixed_items) >= set(base.fixed_items), leaf
        assert set(variant.safety_items) >= set(base.safety_items), leaf
        assert {r.id for r in variant.red_rules} >= {r.id for r in base.red_rules}, leaf
        assert {f.id for f in variant.floors} >= {f.id for f in base.floors}, leaf
