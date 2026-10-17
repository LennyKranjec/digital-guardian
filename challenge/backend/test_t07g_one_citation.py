# ruff: noqa: F401, F811
"""T-07G: im LLM-Modus trägt jeder Satz genau einen Beleg und wird nur gegen diesen geprüft.

Ergänzt `test_a3_t07f.py` (A3). Echte Fakten (SYN-0001, en), Textbaustein-Modus bleibt unberührt.
"""

from typing import Any

import pytest

from test_a3_t07f import DIA, FEV, TIR, facts, find, kept
from test_a3_t08 import real_export_app
from waechter.llm import prompt
from waechter.llm.verifier import verify


def ref(facts: dict[str, str], spec: tuple[str, str]) -> str:
    return f"[{find(facts, spec[0], spec[1])}]"


def test_a_faithful_single_citation_sentence_is_kept(facts: dict[str, str]) -> None:
    text = "Diarrhea (severity), latest value: 3 on 2026-10-16; trend: rising."
    assert kept(f"{text} {ref(facts, DIA)}", facts)


@pytest.mark.parametrize("spec_pair", [(DIA, TIR), (FEV, DIA), (DIA, FEV, TIR)])
def test_two_or_more_citations_are_dropped_even_when_every_word_is_supported(
    facts: dict[str, str], spec_pair: tuple[tuple[str, str], ...]
) -> None:
    refs = "".join(ref(facts, s) for s in spec_pair)
    first = facts[find(facts, *spec_pair[0])]
    assert verify(f"{first} {refs}", facts).dropped == 1


def test_citing_the_same_fact_twice_counts_as_one_citation(facts: dict[str, str]) -> None:
    text = "Diarrhea (severity), latest value: 3 on 2026-10-16."
    both = f"{ref(facts, DIA)}{ref(facts, DIA)}"
    assert kept(f"{text} {both}", facts)


def test_a_sentence_without_citation_is_dropped(facts: dict[str, str]) -> None:
    assert not kept("Diarrhea (severity), latest value: 3 on 2026-10-16.", facts)


FLIPS_WITH_ONE_CITATION: list[tuple[str, tuple[str, str]]] = [
    # Zahl, die der zitierte Beleg nicht nennt (Fieber ist 0, nicht 3)
    ("Fever (presence), latest value: 3 on 2026-10-16.", FEV),
    # Trendwort, das der zitierte Beleg nicht trägt (Durchfall steigt)
    ("Diarrhea (severity), latest value: 3 on 2026-10-16; trend: falling.", DIA),
    ("Fever (presence), latest value: 0 on 2026-10-16; trend: rising.", FEV),
    # Richtungswörter brauchen einen Beleg derselben Richtung: Durchfall steigt
    ("Diarrhea (severity), latest value: 3 on 2026-10-16; trend: unchanged.", DIA),
    ("Diarrhea (severity), latest value: 3 on 2026-10-16; trend: decreased.", DIA),
]


@pytest.mark.parametrize("index", range(len(FLIPS_WITH_ONE_CITATION)))
def test_a_wrong_statement_with_a_single_citation_is_dropped_by_the_cited_fact(
    facts: dict[str, str], index: int
) -> None:
    text, spec = FLIPS_WITH_ONE_CITATION[index]
    assert not kept(f"{text} {ref(facts, spec)}", facts)


def test_the_template_mode_is_not_restricted_to_one_citation(facts: dict[str, str]) -> None:
    dia, tir = find(facts, *DIA), find(facts, *TIR)
    text = f"{facts[dia]} [{dia}][{tir}]"  # ein Satz, zwei Belege
    assert verify(text, facts, extractive=False).dropped == 0
    assert verify(text, facts, extractive=True).dropped == 1


def test_the_prompt_asks_for_exactly_one_citation_and_has_a_new_version() -> None:
    assert int(prompt.PROMPT_VERSION.rsplit("v", 1)[1]) >= 2  # v2 ab T-07G, v3 mit T-22
    assert "exactly one fact reference" in prompt.instructions("en")
    assert "právě jedním odkazem" in prompt.instructions("cs")
    assert "[id1][id2]" not in prompt.instructions("en") + prompt.instructions("cs")


def test_the_template_text_has_one_citation_per_sentence(facts: dict[str, Any]) -> None:
    """Der Rückfall (Textbaustein) erfüllt die Regel selbst: ein Satz je Beleg."""
    from waechter.llm.adapters import template_text
    from waechter.llm.facts import Fact, FactSet

    fact_list = [Fact(id=k, kind="observation", role="latest", text=v) for k, v in facts.items()]
    sample = FactSet(facts=fact_list[:6], hash="x", lang="en", unknown_topics=[])
    result = verify(template_text(sample), sample.mapping(), extractive=True)
    assert result.dropped == 0
    assert all(len(s.refs) == 1 for s in result.sentences)
