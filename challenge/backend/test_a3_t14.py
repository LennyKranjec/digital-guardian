"""A3-Gegenproben zu T-14 (Triage-Bibliothek) gegen die unabhängige Referenz `a3_triage_ref.py`.

Die Referenz liest `triage.yaml` selbst (eigene Auflösung der Vererbung, eigener Parser, eigene
Lehrer-/Boden-Auswertung). Verglichen werden Domänen, Lehrerlevel auf dem Aggregatgitter, das
Endlevel auf dem Item-Gitter, Monotonie, Sitzungsprotokolle und Untertriage gegenüber der wahren
Volleingabe; dazu Angriffe auf Parser und Lader.
"""

import copy
import itertools
import os
import random
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

import a3_triage_ref as ref
from waechter.triage import parser
from waechter.triage.engine import TeacherEngine
from waechter.triage.kb import KnowledgeBase, ResolvedProfile, TriageError, build_kb, load_kb
from waechter.triage.policy import FlipPolicy, Question, Stop

CONTENT = Path(__file__).resolve().parents[1] / "content"
LEAVES = ["FOLFOX", "CAPECITABINE", "DOCETAXEL", "PEMBROLIZUMAB"]
LEVEL = {"GREEN": 0, "YELLOW": 1, "RED": 2}


def _yaml(name: str) -> Any:
    return yaml.safe_load((CONTENT / name).read_text(encoding="utf-8"))


RAW = _yaml("triage.yaml")
ITEMS = _yaml("items.yaml")
ATTRIBUTES = {
    item["symptom_key"]: [a["attribute"] for a in item["attributes"]] for item in ITEMS["items"]
}
REGIMENS = {r["id"]: list(r["symptom_keys"]) for r in _yaml("regimens.yaml")["regimens"]}


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_kb()


def reference(leaf: str, raw: dict[str, Any] | None = None) -> ref.Profile:
    return ref.resolve(raw or RAW, leaf)


def level_name(level: Any) -> str:
    return str(level.name)


def cascade_of(
    leaf: str, theirs: ResolvedProfile, raw: dict[str, Any] | None = None
) -> dict[str, list[str]]:
    """Fragereihenfolge je Symptom aus dem YAML (Kaskade), sonst die Reihenfolge der items.yaml."""
    order: dict[str, list[str]] = {s: list(ATTRIBUTES[s]) for s in theirs.symptoms}
    profiles = {p["id"]: p for p in (raw or RAW)["profiles"]}
    chain: list[Any] = []
    current: str | None = leaf
    while current is not None:
        chain.append(profiles[current])
        current = profiles[current].get("extends")
    for profile in reversed(chain):
        for symptom, cascade in (profile.get("cascade") or {}).items():
            order[symptom] = list(cascade["attributes_order"])
    return order


# --- Domänen, Auflösung, Lehrer ----------------------------------------------------------------


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_profile_symptoms_and_aggregate_domains_match_the_reference(
    kb: KnowledgeBase, leaf: str
) -> None:
    theirs, mine = kb.profile(leaf), reference(leaf)
    assert set(theirs.symptoms) == set(mine.items), leaf
    assert {a.id for a in theirs.aggregates} == {a.id for a in mine.aggregates}, leaf
    domains = {a.id: a.domain_max for a in mine.aggregates}
    for aggregate in theirs.aggregates:
        assert aggregate.max_value == domains[aggregate.id], (leaf, aggregate.id)
    assert {r.id for r in theirs.red_rules} == {r.id for r in mine.red}, leaf
    assert {r.id for r in theirs.yellow_rules} == {r.id for r in mine.yellow}, leaf
    assert {r.id for r in theirs.floors} == {r.id for r in mine.floors}, leaf
    assert set(theirs.safety_items) == mine.safety_items, leaf


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_teacher_level_is_identical_on_every_aggregate_grid_point(
    kb: KnowledgeBase, leaf: str
) -> None:
    theirs, mine = kb.profile(leaf), reference(leaf)
    engine = TeacherEngine(theirs)
    full = os.environ.get("A3_FULL_GRID") == "1"  # vollständig: ca. 5 min; sonst jeder 41. Punkt
    stride = 1 if full else 41
    checked = 0
    for point in itertools.islice(ref.grid(mine), 0, None, stride):
        checked += 1
        assert level_name(engine.teacher_level(point)) == ref.teacher_level(mine, point), point
    assert checked >= ref.grid_size(mine) // stride


@pytest.mark.parametrize(
    "leaf",
    [
        "FOLFOX",
        "CAPECITABINE",
        "DOCETAXEL",
        "PEMBROLIZUMAB",
    ],
)
def test_a3_aggregate_grid_stays_within_the_contract_guard(leaf: str) -> None:
    """triage.md §4/§9: Schutz `max_product` 2 000 000 gilt für das KOMPRIMIERTE Gitter (H3)."""
    assert ref.compressed_size(reference(leaf)) <= 2_000_000


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_reference_finds_the_teacher_monotone_and_red_within_yellow(leaf: str) -> None:
    mine = reference(leaf)
    stride = 1 if os.environ.get("A3_FULL_GRID") == "1" else 97  # vollständig: ca. 3 min je Profil
    assert ref.check_teacher_monotone(mine, stride) == []


def grades_to_state(theirs: ResolvedProfile, grades: dict[str, int]) -> dict[tuple[str, str], int]:
    """Antwortzustand, dessen Symptomgrad genau `grades` ergibt (Antwort auf das erste Attribut)."""
    state: dict[tuple[str, str], int] = {}
    for symptom, grade in grades.items():
        gate = theirs.order(symptom)[0]
        value = next(
            v
            for v in range(5)
            if min(theirs.grade_map[v], theirs.items[symptom].grade_max) >= grade
        )
        state[(symptom, gate)] = value if grade > 0 else 0
    return state


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_final_level_equals_the_reference_on_random_item_states(
    kb: KnowledgeBase, leaf: str
) -> None:
    theirs, mine = kb.profile(leaf), reference(leaf)
    engine = TeacherEngine(theirs)
    rng = random.Random(14)  # noqa: S311 - fester Seed
    symptoms = list(theirs.symptoms)
    for _ in range(4000):
        grades = {s: rng.randint(0, theirs.items[s].grade_max) for s in symptoms}
        previous = {s: rng.randint(0, theirs.items[s].grade_max) for s in symptoms}
        state = grades_to_state(theirs, grades)
        for s in theirs.safety_items:  # Safety-Items beantwortet, damit `incomplete` nicht anhebt
            state.setdefault((s, theirs.order(s)[0]), 0)
        for trend in (None, previous):
            got = level_name(engine.level(state, trend).level)
            assert got == ref.final_level(mine, grades, trend), (grades, trend)


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_single_step_neighbours_never_lower_the_level_in_the_implementation(
    kb: KnowledgeBase, leaf: str
) -> None:
    theirs, mine = kb.profile(leaf), reference(leaf)
    engine = TeacherEngine(theirs)

    def predict(grades: Any) -> str:
        state = grades_to_state(theirs, dict(grades))
        for s in theirs.safety_items:
            state.setdefault((s, theirs.order(s)[0]), 0)
        return level_name(engine.level(state, None).level)

    assert ref.single_step_violations(mine, predict, samples=3000, seed=7) == []
    assert ref.single_step_violations(mine, None, samples=3000, seed=7) == []


# --- Sitzungen: Protokolle, Untertriage, Fragenzahl ---


def session_setup(
    kb: KnowledgeBase, leaf: str, raw: dict[str, Any] | None = None
) -> tuple[
    ResolvedProfile, ref.Profile, FlipPolicy, dict[str, list[str]], set[str], ref.Escalation
]:
    """Profil, Referenz, Policy, Fragereihenfolgen (Rotationssymptome nur Gate: Ja/Nein), Menge."""
    theirs, mine = kb.profile(leaf), reference(leaf, raw)
    policy = FlipPolicy(TeacherEngine(theirs))
    order = cascade_of(leaf, theirs, raw)
    for symptom in policy.rotating_symptoms(0):
        order[symptom] = order[symptom][:1]  # Spezifikation: rotierende Slots als Ja/Nein
    return (
        theirs,
        mine,
        policy,
        order,
        set(policy.session_symptoms(0)),
        ref.escalation_of(RAW, leaf),
    )


def random_truth(
    theirs: ResolvedProfile,
    order: dict[str, list[str]],
    rng: random.Random,
    esc: ref.Escalation | None = None,
) -> dict[tuple[str, str], int]:
    """Wahre Antworten je Feld; Gate 0 ⇒ Folgeattribute 0 (Spezifikation: nicht gefragt = 0).

    Mit `esc`: Symptome, die nur über Eskalation gefragt werden, sind nur ungleich 0, wenn ihre
    Eskalationsbedingung bei den wahren Graden erfüllt ist (klinisch gekoppelte Wahrheit).
    """
    sick = rng.random() < 0.7
    truth: dict[tuple[str, str], int] = {}
    for symptom in theirs.symptoms:
        attributes = order[symptom]
        top = 1 if attributes[0] == "presence" else 4
        gate = rng.randint(0, top) if sick and rng.random() < 0.5 else 0
        truth[(symptom, attributes[0])] = gate
        for attribute in attributes[1:]:
            truth[(symptom, attribute)] = rng.randint(0, 4) if gate > 0 else 0
    if esc is not None:
        for _ in range(4):  # Fixpunkt (Eskalationsziele können weitere auslösen)
            env = ref.item_env_from(truth_grades(theirs, truth))
            allowed = {t for expr, targets in esc.rules if ref.evaluate(expr, env) for t in targets}
            for key in list(truth):
                if key[0] in esc.only and key[0] not in allowed:
                    truth[key] = 0
    return truth


def truth_grades(theirs: ResolvedProfile, truth: dict[tuple[str, str], int]) -> dict[str, int]:
    grades = dict.fromkeys(theirs.symptoms, 0)
    for (symptom, _attribute), value in truth.items():
        grade = min(theirs.grade_map[value], theirs.items[symptom].grade_max)
        grades[symptom] = max(grades[symptom], grade)
    return grades


def run_session(
    policy: FlipPolicy,
    truth: dict[tuple[str, str], int],
    rng: random.Random,
    previous: dict[str, int] | None,
    skip_rate: float,
) -> tuple[ref.Transcript, Stop]:
    state: dict[tuple[str, str], int] = {}
    asked: list[tuple[str, str]] = []
    steps: list[ref.Step] = []
    for _ in range(200):
        question = policy.next_question(state, asked, previous, 0)
        if isinstance(question, Stop):
            return ref.Transcript(steps, question.reason, question.incomplete), question
        key = (question.symptom_key, question.attribute)
        asked.append(key)
        skipped = rng.random() < skip_rate
        if not skipped:
            state[key] = truth[key]
        steps.append(ref.Step(ref.Question(*key), None if skipped else truth[key]))
    raise AssertionError("Sitzung endet nicht")


def drive(
    kb: KnowledgeBase,
    leaf: str,
    coupled: bool,
    runs: int,
    skip_rate: float,
    seed: int,
    raw: dict[str, Any] | None = None,
) -> tuple[list[str], int, list[int], list[ref.Transcript]]:
    theirs, mine, policy, order, askable, esc = session_setup(kb, leaf, raw)
    rng = random.Random(seed)  # noqa: S311 - fester Seed
    problems: list[str] = []
    counts: list[int] = []
    transcripts: list[ref.Transcript] = []
    under = 0
    for _ in range(runs):
        truth = random_truth(theirs, order, rng, esc if coupled else None)
        previous = None if rng.random() < 0.5 else {s: rng.randint(0, 1) for s in theirs.symptoms}
        transcript, stop = run_session(policy, truth, rng, previous, skip_rate)
        counts.append(len(transcript.steps))
        transcripts.append(transcript)
        grades = {s: g if s in askable else 0 for s, g in truth_grades(theirs, truth).items()}
        problems += ref.check_transcript(mine, order, transcript, grades, askable, esc, previous)
        want = ref.final_level(mine, grades, previous)
        if stop.reason == "decided" and LEVEL[level_name(stop.level_lo)] != LEVEL[want]:
            under += 1
    return problems, under, counts, transcripts


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_sessions_pass_the_reference_checker_and_never_under_triage(
    kb: KnowledgeBase, leaf: str
) -> None:
    problems, under, counts, _ = drive(kb, leaf, True, 250, 0.0, 1400 + len(leaf))
    theirs = kb.profile(leaf)
    assert problems == [], problems[:5]
    assert under == 0, f"{under} von 250 'decided'-Sitzungen weichen vom wahren Level ab"
    assert max(counts) <= theirs.max_questions + len(theirs.safety_items)
    mean = sum(counts) / len(counts)
    print(f"{leaf}: Fragen Ø {mean:.1f}, Max {max(counts)}, Vollset {theirs.full_question_count}")
    assert mean < theirs.full_question_count  # adaptiv: weniger als das Vollset


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_escalation_only_symptoms_do_not_hide_red_findings(kb: KnowledgeBase, leaf: str) -> None:
    _, under, _, _ = drive(kb, leaf, False, 250, 0.0, 99)
    assert under == 0, f"{under} von 250 Sitzungen: Untertriage bei unabhängiger Wahrheit"


@pytest.mark.parametrize("leaf", LEAVES)
def test_a3_skipped_answers_never_hide_incompleteness(kb: KnowledgeBase, leaf: str) -> None:
    theirs, mine, policy, order, askable, esc = session_setup(kb, leaf)
    rng = random.Random(77)  # noqa: S311 - fester Seed
    problems: list[str] = []
    for _ in range(150):
        truth = random_truth(theirs, order, rng, esc)
        previous = None
        transcript, stop = run_session(policy, truth, rng, previous, 0.3)
        grades = {s: g if s in askable else 0 for s, g in truth_grades(theirs, truth).items()}
        problems += ref.check_transcript(mine, order, transcript, grades, askable, esc, previous)
        answered = {
            step.question.symptom_key for step in transcript.steps if step.value is not None
        }
        if any(s not in answered for s in theirs.safety_items):
            assert stop.incomplete, "Safety-Item übersprungen, aber nicht incomplete"
            assert LEVEL[level_name(stop.level_hi)] >= 1  # mindestens gelb
    assert problems == [], problems[:5]


def test_a3_fever_is_asked_first_and_decides_red_immediately(kb: KnowledgeBase) -> None:
    for leaf in LEAVES:
        policy = FlipPolicy(TeacherEngine(kb.profile(leaf)))
        first = policy.next_question({}, (), None, 0)
        assert isinstance(first, Question)
        assert first.symptom_key in kb.profile(leaf).safety_items
        stop = policy.next_question({("fever", "presence"): 1}, [("fever", "presence")], None, 0)
        if isinstance(stop, Question):  # weitere Safety-Fragen (ICI: Atemnot) kommen vor dem Stopp
            assert stop.symptom_key in kb.profile(leaf).safety_items
        else:
            assert (stop.reason, level_name(stop.level_lo)) == ("decided", "RED")


# --- Parser-Angriffe ---


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os').system('x')",
        "a.__class__",
        "max_grade >= 2; max_grade",
        "max_grade >= 0x10",
        "max_grade >= 1e3",
        "max_grade >= 12345",  # zu viele Ziffern
        "max_grade >= 1 >= 0",
        "max_grade ≥ 2",
        "(" * 5000 + "max_grade >= 1" + ")" * 5000,
        "max_grade >= 1 " + "and max_grade >= 1 " * 200,
        "not " * 100 + "max_grade >= 1",
        "",
        "   ",
        "max_grade >=",
        "and",
        "max_grade >= 2 )",
        "lambda: 1",
        "max_grade >= 2 # kommentar",
        "max_grade\x00 >= 2",
    ],
)
def test_a3_parser_rejects_hostile_input_quickly_and_with_the_documented_error(text: str) -> None:
    started = time.monotonic()
    with pytest.raises(parser.ExpressionError):
        parser.parse(text)
    assert time.monotonic() - started < 1.0


def test_a3_parser_accepts_the_real_rules_and_matches_the_reference() -> None:
    rng = random.Random(3)  # noqa: S311 - fester Seed
    expressions = [
        r["when"]
        for p in RAW["profiles"]
        for kind in ("red", "yellow")
        for r in (p.get("teacher") or {}).get(kind, [])
    ] + [f["when"] for p in RAW["profiles"] for f in p.get("floors", [])]
    for text in expressions:
        theirs, mine = parser.parse(text), ref.parse(text)
        names = sorted(ref.names_of(mine))
        for _ in range(60):
            env = {n: rng.randint(0, 4) for n in names}
            assert parser.evaluate(theirs, env) == ref.evaluate(mine, env), (text, env)


# --- Lader: Ladefehler statt stiller Annahmen ---


def build(raw: dict[str, Any]) -> KnowledgeBase:
    return build_kb(raw, attributes=ATTRIBUTES, regimens=REGIMENS)


def mutated(change: Any) -> dict[str, Any]:
    raw: dict[str, Any] = copy.deepcopy(RAW)
    change(raw)
    return raw


def profile_of(raw: dict[str, Any], profile_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(p for p in raw["profiles"] if p["id"] == profile_id)
    return found


def drop_source(raw: dict[str, Any]) -> None:
    rule = profile_of(raw, "base")["teacher"]["red"][0]
    rule.pop("assumption", None)
    rule.pop("source", None)


def non_monotone_rule(raw: dict[str, Any]) -> None:
    profile_of(raw, "base")["teacher"]["yellow"][0]["when"] = "max_grade == 2"


def negated_rule(raw: dict[str, Any]) -> None:
    profile_of(raw, "base")["teacher"]["yellow"][0]["when"] = "not n_ge1 >= 1"


def loosen_child_rule(raw: dict[str, Any]) -> None:
    child = profile_of(raw, "chemo")
    child["teacher"]["red"] = [
        {
            "id": "R_CRIT_G3",  # gleiche ID wie in base, höhere Schwelle ⇒ Lockerung
            "when": "max_critical >= 4",
            "assumption": "A-TRI-01",
            "status": "placeholder",
        }
    ]


def loosen_child_floor(raw: dict[str, Any]) -> None:
    child = profile_of(raw, "ici")
    child["floors"] = [
        {
            "id": "F_FEVER",
            "when": "fever.grade >= 2",
            "min_level": "YELLOW",
            "locked": True,
            "assumption": "A-TRI-07",
            "status": "placeholder",
        }
    ]


def redefine_aggregate(raw: dict[str, Any]) -> None:
    profile_of(raw, "chemo")["aggregates"].append(
        {"id": "max_grade", "kind": "max_over", "items": ["diarrhea"]}
    )


@pytest.mark.parametrize(
    "change",
    [
        drop_source,
        non_monotone_rule,
        negated_rule,
        loosen_child_rule,
        loosen_child_floor,
        redefine_aggregate,
        lambda raw: raw["items"].append({"symptom_key": "fever", "grade_max": 1, "critical": True}),
        lambda raw: profile_of(raw, "base")["aggregates"].append(
            {"id": "x_empty", "kind": "max_over", "items": []}
        ),
        lambda raw: profile_of(raw, "base")["aggregates"].append(
            {"id": "x_bad", "kind": "max_over", "items": "ALLE"}
        ),
        lambda raw: profile_of(raw, "base")["aggregates"].append(
            {"id": "x_unknown", "kind": "max_over", "items": ["no_such_symptom"]}
        ),
        lambda raw: profile_of(raw, "base")["teacher"]["red"].append(
            {
                "id": "R_UNKNOWN",
                "when": "no_such_aggregate >= 1",
                "assumption": "A-TRI-01",
                "status": "placeholder",
            }
        ),
        lambda raw: profile_of(raw, "base")["screening"].update({"max_questions": 1}),
        lambda raw: profile_of(raw, "chemo").update({"extends": "chemo"}),
        lambda raw: profile_of(raw, "FOLFOX").update({"extends": "missing_profile"}),
        lambda raw: raw.update({"mode": "production"}),
    ],
)
def test_a3_loader_rejects_unsafe_or_incomplete_knowledge_bases(change: Any) -> None:
    with pytest.raises(TriageError):
        build(mutated(change))


def test_a3_unmodified_knowledge_base_loads_and_has_all_four_regimens(kb: KnowledgeBase) -> None:
    assert set(LEAVES) <= set(kb.profiles)
    assert {kb.regimen_profile[r] for r in LEAVES} == set(LEAVES)
    assert all(kb.profile(leaf).status == "placeholder" for leaf in kb.profiles)


def test_a3_parser_rejects_non_ascii_digits() -> None:
    digit = chr(0xFF12)  # Vollbreiten-Ziffer Zwei (sieht aus wie 2)
    with pytest.raises(parser.ExpressionError):
        parser.parse(f"max_grade >= {digit}")


def test_a3_burden_cap_stops_report_incompleteness_consistently() -> None:
    """Fragenlimit 5: Sitzungen enden mit burden_cap, `incomplete` entspricht lo < hi."""
    raw: dict[str, Any] = copy.deepcopy(RAW)
    profile_of(raw, "base")["screening"]["max_questions"] = 5
    small = build(raw)
    problems, _, counts, transcripts = drive(small, "FOLFOX", True, 300, 0.0, 21, raw)
    assert problems == [], problems[:5]
    reasons = {t.stop_reason for t in transcripts}
    assert "burden_cap" in reasons, reasons
    capped = [t for t in transcripts if t.stop_reason == "burden_cap"]
    assert all(t.incomplete for t in capped if len(t.steps) > 5)
    assert max(counts) <= 5 + len(small.profile("FOLFOX").safety_items)
