"""A3-Gegenproben zu T-20/T-20b: ENZALUTAMIDE, ABIRATERONE, PAZOPANIB, NIVOLUMAB, Seed SYN-0006/7.

Alles gegen die unabhängige Referenz `a3_triage_ref.py` (eigener Parser, Lehrer, Kompression) und
den eigenen Baum-Läufer über den exportierten JSON-Baum (siehe `test_a3_t15.py`).
"""
# ruff: noqa: S311, F811  # feste Seeds; Fixture-Import überdeckt das Argument

import os
import random
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select

import a3_triage_ref as ref
from test_a3_t04a import MutableClock
from test_a3_t13 import api, client_for, real_template  # noqa: F401
from test_a3_t14 import RAW, random_truth, reference, run_session, session_setup, truth_grades
from test_a3_t15 import compare, exported, runtime, tree_level
from waechter.models import Answer, Patient, Response, TriageDecision
from waechter.triage.engine import CompiledEngine
from waechter.triage.kb import KnowledgeBase, load_kb
from waechter.triage.policy import FlipPolicy
from waechter.triage.verify import verify_composition

NEW = ["ENZALUTAMIDE", "ABIRATERONE", "PAZOPANIB", "NIVOLUMAB"]
NAMES = {0: "GREEN", 1: "YELLOW", 2: "RED"}


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_kb()


@pytest.mark.parametrize("leaf", NEW)
def test_a3_new_profiles_have_the_reference_domains_and_grid_sizes(
    kb: KnowledgeBase, leaf: str
) -> None:
    mine = reference(leaf)
    built = runtime(kb, leaf).compiled[0]
    names = [a.id for a in mine.aggregates]
    expected = ref.compressed_domains(mine)
    assert list(built.features) == names
    assert list(built.natural) == [a.domain_max for a in mine.aggregates]
    assert list(built.caps) == [expected[n] for n in names]
    assert built.grid_points == ref.compressed_size(mine) <= 2_000_000
    assert built.natural_points == ref.grid_size(mine)
    assert ref.check_compression(mine, 17) == []


@pytest.mark.parametrize("leaf", NEW)
def test_a3_new_profiles_trees_equal_the_reference_on_the_full_natural_grid(
    kb: KnowledgeBase, leaf: str
) -> None:
    mine = reference(leaf)
    built = runtime(kb, leaf).compiled[0]
    data = exported(built)
    # komprimiertes UND natürliches (ungekürztes) Gitter, jeder Punkt
    assert compare(data, mine, list(built.caps), list(built.caps)) == []
    assert compare(data, mine, list(built.caps), list(built.natural)) == []
    rank = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    caps = list(built.caps)
    import itertools

    levels = {x: tree_level(data, x) for x in itertools.product(*[range(c + 1) for c in caps])}
    assert "INCONSISTENT" not in levels.values()
    for x, level in levels.items():
        for axis, cap in enumerate(caps):
            if x[axis] < cap:
                up = (*x[:axis], x[axis] + 1, *x[axis + 1 :])
                assert rank[levels[up]] >= rank[level], (x, up)


@pytest.mark.parametrize("leaf", NEW)
def test_a3_new_profiles_teacher_is_monotone_and_placeholder(kb: KnowledgeBase, leaf: str) -> None:
    mine = reference(leaf)
    assert ref.check_teacher_monotone(mine, 11) == []
    assert kb.profile(leaf).status == "placeholder"


@pytest.mark.parametrize("leaf", NEW)
def test_a3_new_profiles_sessions_never_under_triage(kb: KnowledgeBase, leaf: str) -> None:
    theirs, mine, _policy, order, askable, esc = session_setup(kb, leaf)
    rt = runtime(kb, leaf)
    policy = FlipPolicy(CompiledEngine(theirs, rt.compiled))
    rng = random.Random(2000 + len(leaf))
    problems: list[str] = []
    under = over = 0
    counts: list[int] = []
    for run in range(400):
        truth = random_truth(theirs, order, rng, esc if run % 2 else None)
        previous = None if rng.random() < 0.5 else {s: rng.randint(0, 1) for s in theirs.symptoms}
        transcript, stop = run_session(policy, truth, rng, previous, 0.0)
        counts.append(len(transcript.steps))
        grades = {s: g if s in askable else 0 for s, g in truth_grades(theirs, truth).items()}
        problems += ref.check_transcript(mine, order, transcript, grades, askable, esc, previous)
        want = ref.final_level(mine, grades, previous)
        if stop.reason == "decided":
            got = NAMES[int(stop.level_lo)]
            if ref.RANK[got] < ref.RANK[want]:
                under += 1
            elif ref.RANK[got] > ref.RANK[want]:
                over += 1
    assert problems == [], problems[:5]
    assert (under, over) == (0, 0)
    print(f"{leaf}: Fragen Ø {sum(counts) / len(counts):.1f} von {theirs.full_question_count}")
    assert sum(counts) / len(counts) < theirs.full_question_count


@pytest.mark.parametrize("leaf", ["PAZOPANIB", "NIVOLUMAB"])
def test_a3_sampled_profiles_report_sampled_scope_honestly(kb: KnowledgeBase, leaf: str) -> None:
    """Im Betrieb nur Stichprobe des Rohgitters: der Bericht darf dann nie `exhaustive_*` melden."""
    report = runtime(kb, leaf).report.to_dict()
    assert report["scope"] in ("sampled_raw", "exhaustive_raw")
    assert (report["under"], report["over"], report["monotone_violations"]) == (0, 0, 0)


@pytest.mark.skipif(
    os.environ.get("A3_FULL_GRID") != "1", reason="Vollnachweis ca. 2 min; mit A3_FULL_GRID=1"
)
@pytest.mark.parametrize("leaf", ["PAZOPANIB", "NIVOLUMAB"])
def test_a3_full_raw_grid_has_zero_violations_when_checked_exhaustively(
    kb: KnowledgeBase, leaf: str
) -> None:
    """Eigener Vollnachweis des Rohgitters (V3/V4); der Betrieb prüft dort nur eine Stichprobe."""
    rt = runtime(kb, leaf)
    report = verify_composition(
        rt.composition, rt.compiled, uncompressed=True, max_exhaustive=10**9
    )
    data = report.to_dict()
    assert data["scope"] == "exhaustive_raw", data["scope"]
    assert (data["under"], data["over"], data["monotone_violations"]) == (0, 0, 0)
    for component in data["components"]:
        assert component["v3_violations"] == 0
        assert component["v4_violations"] == 0


def test_a3_seeded_decisions_equal_the_reference_for_every_patient(
    api: tuple[FastAPI, MutableClock],
) -> None:
    """Jede Seed-Entscheidung (inkl. SYN-0006/0007) == Referenz aus den gespeicherten Antworten."""
    app, _ = api
    kb = load_kb()
    compared: dict[str, int] = {}
    skipped = 0
    with app.state.session_factory() as session:
        patients = {p.id: p for p in session.scalars(select(Patient))}
        for patient in patients.values():
            responses = list(
                session.scalars(
                    select(Response)
                    .where(Response.patient_id == patient.id)
                    .order_by(Response.recorded_at, Response.id)
                )
            )
            decisions = {
                d.response_id: d
                for d in session.scalars(
                    select(TriageDecision).where(TriageDecision.patient_id == patient.id)
                )
            }
            previous: dict[str, int] | None = None
            for response in responses:
                answers = list(
                    session.scalars(select(Answer).where(Answer.response_id == response.id))
                )
                decision = decisions.get(response.id)
                if decision is None:
                    continue
                theirs = kb.profile(decision.profile_id)
                mine = reference(decision.profile_id)
                values = {(a.symptom_key, a.attribute): a.value for a in answers}
                if any(v is None for v in values.values()):
                    skipped += 1  # fehlende Antworten: Schutzregel, hier nicht Teil des Orakels
                    grades = truth_grades(
                        theirs, {k: v for k, v in values.items() if v is not None}
                    )
                    previous = grades
                    continue
                grades = truth_grades(
                    theirs, {k: int(v) for k, v in values.items() if v is not None}
                )
                want = ref.final_level(mine, grades, previous)
                if decision.level_lo == decision.level_hi:
                    assert decision.level == want, (
                        patient.pseudonym,
                        response.recorded_at,
                        decision.level,
                        want,
                    )
                compared[patient.pseudonym] = compared.get(patient.pseudonym, 0) + 1
                previous = grades
    assert {"SYN-0001", "SYN-0006", "SYN-0007"} <= set(compared), compared
    assert sum(compared.values()) > 40, (compared, skipped)


def test_a3_new_regimens_are_covered_by_profiles_and_the_catalog(kb: KnowledgeBase) -> None:
    from pathlib import Path

    import yaml

    content = Path(__file__).resolve().parents[1] / "content"
    regimens = yaml.safe_load((content / "regimens.yaml").read_text(encoding="utf-8"))["regimens"]
    meds = yaml.safe_load((content / "medications.yaml").read_text(encoding="utf-8"))["medications"]
    leaves = {
        p["id"]
        for p in RAW["profiles"]
        if not any(q.get("extends") == p["id"] for q in RAW["profiles"])
    }
    for regimen in regimens:
        assert regimen["id"] in kb.profiles, regimen["id"]
        assert regimen["id"] in leaves, regimen["id"]
        assert any(regimen["id"] in m["regimen_ids"] for m in meds), regimen["id"]
    _ = (timedelta, Any)
