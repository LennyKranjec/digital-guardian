"""Deterministischer Prüfer der KI-Sätze (G-09): Belege, Zahlen, Daten, Verbotsliste."""

from functools import partial

import pytest

from waechter.llm.verifier import FORBIDDEN, numbers, split_sentences
from waechter.llm.verifier import verify as verify_with_words

#: Die Tests dieser Datei prüfen die Schichten Beleg, Zahl, Datum und Verbotsliste einzeln;
#: die extraktive Wortprüfung (T-07F) hat eigene Tests unten und in test_a3_t07.py.
verify = partial(verify_with_words, extractive=False)

FACTS = {
    "obs-1": (
        "Nausea (severity), latest value: 3 on 2026-10-17; trend: rising; days without value: 4."
    ),
    "obs-2": "Gewicht: 3,5 Punkte am 2026-10-12.",
    "ther-9": "Therapy: FOLFOX; substances: Oxaliplatin; cycle start 2026-10-03; cycle day 15.",
}


def kept(text: str) -> list[str]:
    return [s.text for s in verify(text, FACTS).sentences]


def test_valid_sentence_with_reference_is_kept() -> None:
    result = verify("Nausea reached 3 on 2026-10-17 [obs-1].", FACTS)
    assert [(s.text, s.refs, s.verified) for s in result.sentences] == [
        ("Nausea reached 3 on 2026-10-17.", ("obs-1",), True)
    ]
    assert result.dropped == 0


def test_reference_after_the_period_belongs_to_the_previous_sentence() -> None:
    result = verify("Nausea reached 3. [obs-1] Cycle day 15 [ther-9].", FACTS)
    assert [(s.text, s.refs) for s in result.sentences] == [
        ("Nausea reached 3.", ("obs-1",)),
        ("Cycle day 15.", ("ther-9",)),
    ]
    assert result.dropped == 0


@pytest.mark.parametrize(
    "text",
    [
        "Nausea reached 3 on 2026-10-17.",  # kein Beleg
        "Nausea reached 3 [obs-404].",  # erfundener Beleg
        "Nausea reached 3 [obs-1][obs-404].",  # ein Beleg erfunden
        "Nausea reached 3 [obs-1 obs-X!].",  # ungültiges Beleg-Format
        "Nausea reached 3 [].",  # leere Klammer
    ],
)
def test_sentences_without_valid_references_are_dropped(text: str) -> None:
    result = verify(text, FACTS)
    assert result.sentences == []
    assert result.dropped == 1


def test_a_wrong_number_is_dropped() -> None:
    result = verify("Nausea reached 5 on 2026-10-17 [obs-1].", FACTS)
    assert result.sentences == []
    assert result.dropped == 1


def test_numbers_must_come_from_the_cited_evidence_not_from_other_facts() -> None:
    # 15 steht in ther-9, der Satz zitiert aber obs-1
    assert kept("Nausea at 15 [obs-1].") == []
    assert kept("Nausea at 15 [obs-1][ther-9].") == ["Nausea at 15."]


def test_comma_decimal_is_read_as_decimal_point() -> None:
    assert kept("Gewicht 3,5 Punkte [obs-2].") == ["Gewicht 3,5 Punkte."]
    assert kept("Gewicht 3.5 Punkte [obs-2].") == ["Gewicht 3.5 Punkte."]
    assert kept("Gewicht 3,6 Punkte [obs-2].") == []
    assert kept("Gewicht 35 Punkte [obs-2].") == []  # 3,5 ist nicht 35


def test_iso_dates_must_appear_verbatim_in_the_evidence() -> None:
    assert kept("Stand am 2026-10-17 [obs-1].") == ["Stand am 2026-10-17."]
    assert kept("Stand am 2026-10-18 [obs-1].") == []
    assert kept("Stand am 2026-10-12 [obs-1].") == []  # Datum eines anderen Belegs
    # Ziffern eines Datums dürfen keine losen Zahlen decken: 10 steht nur im Datum
    assert kept("Wert 10 [obs-1].") == []


def test_numbers_inside_references_are_ignored() -> None:
    assert kept("Zyklustag 15 [ther-9].") == ["Zyklustag 15."]


def test_several_references_in_one_group_and_in_several_groups() -> None:
    for text in (
        "Nausea 3, Zyklustag 15 [obs-1, ther-9].",
        "Nausea 3, Zyklustag 15 [obs-1][ther-9].",
    ):
        (sentence,) = verify(text, FACTS).sentences
        assert sentence.refs == ("obs-1", "ther-9")


def test_decimal_point_does_not_split_a_sentence() -> None:
    assert split_sentences("Gewicht 3.5 Punkte [obs-2]. Zweiter Satz [ther-9].") == [
        ("Gewicht 3.5 Punkte.", ("obs-2",)),
        ("Zweiter Satz.", ("ther-9",)),
    ]


@pytest.mark.parametrize(
    "phrase",
    [
        "Das spricht für die Diagnose einer Neutropenie",
        "Verdacht auf diagnostik",
        "Wir empfehlen die Dosis zu reduzieren",
        "Eine Dosisanpassung ist nötig",
        "Therapie abbrechen",
        "Bitte Therapieänderung prüfen",
        "Reduzieren Sie die Dosis",
        "Stop the treatment",
        "Discontinue treatment now",
        "We recommend a break",
        "Dose reduction is advised",
        "doporučujeme snížit dávku",
        "Je nutné přerušit léčbu",
        "Keine Sorge, das ist harmlos",
        "Das ist unbedenklich",
        "There is no need to worry",
        "This is harmless",
        "Everything is fine",
        "Není důvod k obavám",
        "Je to v pořádku",
        "Das wurde verursacht durch die Chemotherapie",
        "The nausea is caused by the drug",
        "Nevolnost je způsobena lékem",
        "He suffers from anemia",
    ],
)
def test_forbidden_phrases_are_dropped_even_with_valid_references(phrase: str) -> None:
    assert FORBIDDEN.search(phrase), phrase
    assert kept(f"{phrase} bei 3 [obs-1].") == []


@pytest.mark.parametrize(
    "sentence",
    [
        "Therapy: FOLFOX with Oxaliplatin, cycle day 15 [ther-9].",
        "Nausea at 3 and rising, 4 days without a value [obs-1].",
        "Die Therapie läuft seit Zyklustag 15 [ther-9].",
    ],
)
def test_neutral_descriptions_pass_the_forbidden_list(sentence: str) -> None:
    assert len(verify(sentence, FACTS).sentences) == 1


def test_unknown_topics_are_passed_through_and_empty_text_yields_nothing() -> None:
    result = verify("", FACTS, ["assessment"])
    assert (result.sentences, result.dropped, result.unknown_topics) == ([], 0, ["assessment"])


def test_dropped_sentences_are_counted_in_a_mixed_text() -> None:
    text = (
        "Nausea reached 3 on 2026-10-17 [obs-1]. "  # ok
        "Das ist harmlos [obs-1]. "  # Verbotsliste
        "Der Wert ist 9 [obs-1]. "  # falsche Zahl
        "Ohne Beleg 3. "  # kein Beleg
        "Zyklustag 15 [ther-9]."  # ok
    )
    result = verify(text, FACTS)
    assert [s.refs for s in result.sentences] == [("obs-1",), ("ther-9",)]
    assert result.dropped == 3


def test_number_tokens_follow_the_contract_regex() -> None:
    assert {str(n) for n in numbers("Wert 3,5 und 12 am 2026-10-17, ab 7.")} == {"3.5", "12", "7"}


# --- Extraktive Wortprüfung (T-07F) ---------------------------------------------------------

EVIDENCE = {
    "alert-1": "Offene rote Meldung R-URG-01: Fieber ja seit 2026-10-16.",
    "obs-2": "Übelkeit: erster Wert 1, letzter Wert 3 (steigend).",
}


@pytest.mark.parametrize(
    "sentence",
    [
        "Fieber ja seit 2026-10-16 [alert-1].",
        "Die Übelkeit: letzter Wert 3 [obs-2].",
        "UBELKEIT, letzter Wert 3 [obs-2].",  # Diakritika und Großschreibung egal
        "Es gibt eine rote Meldung [alert-1].",  # neutrale Meldungswörter
        "Übelkeit gestiegen von 1 auf 3 [obs-2].",  # neutrales Verlaufswort
    ],
)
def test_words_found_in_the_cited_evidence_are_kept(sentence: str) -> None:
    assert verify_with_words(sentence, EVIDENCE).dropped == 0


@pytest.mark.parametrize(
    "sentence",
    [
        "Fieber ja, die Dosis sollte angepasst werden [alert-1].",
        "Kein Fieber [alert-1].",  # Verneinung ist kein Funktionswort
        "Fieber deutet auf Sepsis hin [alert-1].",
        "Die Übelkeit wird sich bessern [obs-2].",
        "Fever since 2026-10-16 [alert-1].",  # englisches Wort fehlt im deutschen Beleg
    ],
)
def test_words_missing_from_the_cited_evidence_drop_the_sentence(sentence: str) -> None:
    assert verify_with_words(sentence, EVIDENCE).dropped == 1


def test_words_of_a_different_fact_do_not_support_the_sentence() -> None:
    result = verify_with_words("Übelkeit seit 2026-10-16 [alert-1].", EVIDENCE)
    assert result.dropped == 1  # "Übelkeit" steht nur in obs-2, zitiert wird alert-1


def test_the_template_mode_may_switch_the_word_check_off() -> None:
    assert verify_with_words("Frei formuliert [obs-2].", EVIDENCE, extractive=False).dropped == 0
    assert verify_with_words("Frei formuliert [obs-2].", EVIDENCE).dropped == 1


def test_line_break_after_a_reference_ends_the_sentence() -> None:
    """T-07H: Live-Modell schreibt je Satz eine Zeile ohne Punkt (gpt-6-1-sol, Sa 06:55)."""
    text = "Průjem 3 [alert-1]\nNávštěva 2026-10-18 [visit-2]\nZávěr bez odkazu"
    assert split_sentences(text) == [
        ("Průjem 3.", ("alert-1",)),
        ("Návštěva 2026-10-18.", ("visit-2",)),
        ("Závěr bez odkazu", ()),
    ]
