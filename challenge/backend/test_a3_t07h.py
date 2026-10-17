"""A3-Gegenproben zu T-07H (Wortstamm-Abgleich, Satzgrenze nach Beleg, Live-Entwürfe).

Der Wortstamm-Abgleich (`_same_stem`) und die neuen Neutralwörter (`ma`, `pacientka`, …) lassen
Beugungsformen durch. Diese Datei hält fest, was dabei **nicht** durchkommen darf:

- Verneinung und Gegenrichtung (`nezvýšil`, `klesá` bei steigendem Wert, `not rising`),
- Handlungs- und Therapiesätze,
- Behauptungen, die dem zitierten Beleg widersprechen (`Pacientka má horečku` bei Wert 0).

Netz und Modell kommen nicht vor; geprüft wird nur der deterministische Prüfer.
"""

import pytest

from waechter.llm.verifier import split_sentences, verify

CS = {
    "obs-1": (
        "Horečka (výskyt), poslední hodnota: 0 dne 2026-10-16; vývoj: beze změny; "
        "dní bez hodnoty: 2."
    ),
    "obs-2": (
        "Průjem (závažnost), poslední hodnota: 3 dne 2026-10-16; vývoj: rostoucí; "
        "dní bez hodnoty: 2."
    ),
    "obs-3": (
        "Únava (závažnost), poslední hodnota: 1 dne 2026-10-16; vývoj: klesající; "
        "dní bez hodnoty: 2."
    ),
    "alert-1": "Červená výstraha: Průjem, závažnost 3, otevřená.",
}
EN = {
    "obs-1": (
        "Fever (presence), latest value: 0 on 2026-10-16; trend: unchanged; days without value: 2."
    ),
    "obs-2": (
        "Diarrhea (severity), latest value: 3 on 2026-10-16; trend: rising; days without value: 2."
    ),
    "obs-3": (
        "Fatigue (severity), latest value: 1 on 2026-10-16; trend: falling; days without value: 2."
    ),
}


def kept(text: str, facts: dict[str, str]) -> list[str]:
    return [s.text for s in verify(text, facts).sentences]


@pytest.mark.parametrize(
    "text",
    [
        "Průjem se nezvýšil [obs-2].",
        "Průjem nerostoucí [obs-2].",
        "Průjem nerostl [obs-2].",
        "Únava klesá [obs-2].",
        "Únava je klesající [obs-2].",
        "Únava je rostoucí [obs-3].",
        "Únava rostla [obs-3].",
        "Únava roste [obs-3].",
        "Průjem klesl [obs-2].",
        "Průjem je stabilní [obs-2].",
        "Průjem se zhoršuje [obs-2].",
        "Průjem se zlepšil [obs-2].",
        "Horečka zmizela [obs-1].",
        "Horečka není přítomna [obs-1].",
        "Pacientka nemá horečku [obs-1].",
        "Pacientka hlásí horečku [obs-1].",
        "Pacientka měla horečku [obs-1].",
        "Průjemová infekce [obs-2].",
        "Pacientka potřebuje léčbu [obs-2].",
        "Je třeba kontaktovat pacientku [obs-2].",
        "Pacientku je nutné kontaktovat [alert-1].",
        "Závažnost průjmu je mírná [obs-2].",
    ],
)
def test_a3_czech_negation_opposite_direction_and_action_stay_dropped(text: str) -> None:
    assert kept(text, CS) == [], text


@pytest.mark.parametrize(
    "text",
    [
        "Diarrhea is not rising [obs-2].",
        "Fever is not unchanged [obs-1].",
        "Diarrhea is falling [obs-2].",
        "Diarrhea is decreasing [obs-2].",
        "Diarrhea increasing [obs-3].",
        "Fatigue is rising [obs-3].",
        "Fatigue rose [obs-3].",
        "Fatigue worsened [obs-3].",
        "Fatigue improved [obs-3].",
        "Fatigue unstable [obs-3].",
        "Fever is not present [obs-1].",
        "Fever presence absent [obs-1].",
        "Patient reported fever [obs-1].",
        "Diarrhea treatment reached 3 [obs-2].",
        "Diarrhea medication reached 3 [obs-2].",
    ],
)
def test_a3_english_negation_opposite_direction_and_action_stay_dropped(text: str) -> None:
    assert kept(text, EN) == [], text


def test_a3_inflected_forms_of_the_same_stem_are_accepted() -> None:
    """Zweck von T-07H: Beugung wird akzeptiert, wenn Wert und Richtung stimmen."""
    assert kept("Průjem 3 podle pravidla [alert-1].", CS)
    assert kept("Fever reported with value 0 [obs-1].", EN)
    assert kept("Závažnost průjmu 3, rostoucí [obs-2].", CS)


# --- Durchbrüche (A3 Befund T-07H F-01/F-02): strikt xfail, bis A2/A0 korrigiert -----------------


def test_a3_f01_claim_of_presence_against_a_zero_value_is_dropped() -> None:
    assert kept("Pacientka má horečku [obs-1].", CS) == [], "Beleg obs-1 sagt: Horečka (výskyt) = 0"


@pytest.mark.parametrize(
    "text",
    [
        "Fever is present [obs-1].",
        "Fever is present, value 0 [obs-1].",
    ],
)
def test_a3_f02_present_against_presence_zero_is_dropped(text: str) -> None:
    assert kept(text, EN) == [], "Beleg obs-1 sagt: Fever (presence) = 0"


@pytest.mark.parametrize("text", ["Fatigue severe [obs-3].", "Fatigue severely [obs-3]."])
def test_a3_f02_severe_against_severity_one_is_dropped(text: str) -> None:
    assert kept(text, EN) == [], "Beleg obs-3 sagt: Fatigue (severity) = 1 (leicht)"


# --- Zeilenumbruch nach dem Beleg: nie mehr Belege, nie ein Satz ohne Beleg --------------------


@pytest.mark.parametrize(
    "text",
    [
        "Průjem 3 [obs-2]\nPacientka potřebuje léčbu",
        "Průjem 3 [obs-2]\n[obs-3]",
        "Průjem 3 [obs-2]\nZávěr bez odkazu\n",
    ],
)
def test_a3_line_break_never_lets_a_sentence_without_reference_through(text: str) -> None:
    result = verify(text, CS)
    assert all(s.refs for s in result.sentences)
    assert [s.text for s in result.sentences if "léčbu" in s.text or "Závěr" in s.text] == []
    assert result.dropped >= 1


def test_a3_line_break_splits_one_reference_per_line() -> None:
    assert split_sentences("Průjem 3 [obs-2]\r\nHorečka 0 [obs-1]\r\n") == [
        ("Průjem 3.", ("obs-2",)),
        ("Horečka 0.", ("obs-1",)),
    ]
    result = verify("Průjem 3 [obs-2]\r\nHorečka 0 [obs-1]\r\n", CS)
    assert [s.refs for s in result.sentences] == [("obs-2",), ("obs-1",)]
