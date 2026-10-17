# ruff: noqa: F401, F811
"""A3-Gegenproben zu T-07F (Besitz A3): extraktive Wortprüfung gegen echte Fakten (SYN-0001, en).

Beide Richtungen: treue Sätze bleiben, Therapie-/Ursachenaussagen fallen; Fakten dürfen aber
nicht über mehrere Belege hinweg neu kombiniert werden. Hilfen aus `test_a3_t08.py`.
"""

from collections.abc import Callable
from typing import Any

import pytest

from test_a3_t08 import real_export_app
from test_fhir import pid
from waechter.llm.facts import build_facts
from waechter.llm.verifier import verify
from waechter.models import Patient
from waechter.services.config import require_content


@pytest.fixture
def facts(real_export_app: Any) -> dict[str, str]:
    app = real_export_app
    with app.state.session_factory() as session:
        patient = session.get(Patient, pid(app, "SYN-0001"))
        return build_facts(session, app.state.clock, require_content(), patient, "en").mapping()


def find(facts: dict[str, str], prefix: str, text: str) -> str:
    found = [k for k, v in facts.items() if k.startswith(prefix) and text in v]
    assert len(found) == 1, (prefix, text, found)
    return found[0]


def kept(sentence: str, facts: dict[str, str]) -> bool:
    return verify(sentence, facts).dropped == 0


def test_a3_faithful_sentences_are_kept(facts: dict[str, str]) -> None:
    dia = find(facts, "obs-", "Diarrhea (severity), latest")
    alert = find(facts, "alert-", "R-SEV-01")
    nxt = find(facts, "visit-", "Next planned")
    ther = find(facts, "ther-", "FOLFOX")
    assert kept(
        f"Diarrhea (severity), latest value: 3 on 2026-10-16; trend: rising. [{dia}]",
        facts,
    )
    open_alert = "There is an open red alert for diarrhea (severity)"
    assert kept(f"{open_alert}: value 3 reached threshold 3 [{alert}].", facts)
    assert kept(f"The next planned visit is 2026-10-18. [{nxt}]", facts)
    assert kept(f"Therapy FOLFOX, cycle day 15. [{ther}]", facts)


def test_a3_policy_sentences_with_new_words_are_dropped(facts: dict[str, str]) -> None:
    dia = find(facts, "obs-", "Diarrhea (severity), latest")
    ther = find(facts, "ther-", "FOLFOX")
    assert not kept(f"Reduce oxaliplatin. [{ther}]", facts)
    assert not kept(
        f"Diarrhea (severity) rising: oxaliplatin therapy should be paused. [{dia}][{ther}]",
        facts,
    )
    assert not kept(f"Diarrhea is caused by oxaliplatin. [{dia}][{ther}]", facts)
    assert not kept(f"The patient has no fever on 2026-10-16. [{dia}]", facts)  # Verneinung


def refs(facts: dict[str, str], *specs: tuple[str, str]) -> str:
    return "".join(f"[{find(facts, 'obs-', text)}]" for _, text in specs)


DIA = ("obs-", "Diarrhea (severity), latest")
TIR = ("obs-", "Tiredness (interference), latest")
FEV = ("obs-", "Fever (presence), latest")
FLIPS: list[tuple[str, tuple[tuple[str, str], ...]]] = [
    # Trendwort aus einem zweiten Beleg geliehen: Durchfall "fällt" - tatsächlich steigt er
    ("Diarrhea (severity), latest value: 3 on 2026-10-16; trend: falling.", (DIA, TIR)),
    # Zahl aus einem zweiten Beleg geliehen: Fieber-Wert 3 - tatsächlich 0
    ("Fever (presence), latest value: 3 on 2026-10-16.", (FEV, DIA)),
    # Trend vertauscht: Fieber "steigt" - tatsächlich unverändert
    ("Fever (presence), latest value: 0 on 2026-10-16; trend: rising.", (FEV, DIA)),
]


@pytest.mark.parametrize("index", range(len(FLIPS)))
def test_a3_recombining_values_across_citations_is_dropped(
    facts: dict[str, str], index: int
) -> None:
    text, cited = FLIPS[index]
    assert not kept(f"{text} {refs(facts, *cited)}", facts)
