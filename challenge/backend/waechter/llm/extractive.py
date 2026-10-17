"""Extraktive Prüfung (T-07F): Sätze eines Sprachmodells nutzen nur Wörter der zitierten Belege.

Der Stichwortfilter der Verbotsliste (`verifier.FORBIDDEN`) erkennt nur bekannte Formulierungen;
umformulierte Therapie-, Ursachen-, Diagnose- oder Beruhigungssätze passierten. Deshalb muss in
Entwürfen eines Sprachmodells (Modus `live`/`cached`) zusätzlich jedes **Inhaltswort** des Satzes
in den Texten der zitierten Belege vorkommen. Ausgenommen sind

- Funktionswörter (Artikel, Hilfsverben, Präpositionen; Verneinungen nicht: sie ändern die
  Aussage),
- Zahlen und ISO-Daten (prüft der Zahlen-/Datumsvergleich des Prüfers),
- eine kleine Liste neutraler Verlaufs- und Meldungswörter (`NEUTRAL`); Richtungswörter
  (steigend, fallend, unverändert; `DIRECTIONS`) gehören nicht dazu: eine Richtung im Satz braucht
  ein Wort derselben Richtung im Beleg (T-07G).

Wörter werden klein geschrieben und ohne Diakritika verglichen; sonst keine Stammbildung
(bewusst streng: ein verworfener Satz kostet nur Text, ein durchgelassener die Sicherheit).
Der Textbaustein-Modus besteht aus den Belegtexten selbst und braucht diese Prüfung nicht.
"""

import re
import unicodedata
from collections.abc import Iterable
from typing import Final

WORD: Final = re.compile(r"[^\W\d_]+")

STOPWORDS: Final = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "by",
        "with",
        "and",
        "or",
        "as",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "has",
        "have",
        "had",
        "there",
        "then",
        "than",
        "also",
        "der",
        "die",
        "das",
        "den",
        "dem",
        "des",
        "ein",
        "eine",
        "einer",
        "einen",
        "einem",
        "eines",
        "und",
        "oder",
        "ist",
        "sind",
        "war",
        "waren",
        "wird",
        "wurde",
        "wurden",
        "hat",
        "haben",
        "hatte",
        "es",
        "gibt",
        "im",
        "am",
        "an",
        "auf",
        "zu",
        "zum",
        "zur",
        "von",
        "vom",
        "mit",
        "bei",
        "aus",
        "fur",
        "nach",
        "uber",
        "um",
        "als",
        "auch",
        "noch",
        "nur",
        "sich",
        "dass",
        "bis",
        "wie",
        "wo",
        "a",
        "i",
        "je",
        "jsou",
        "byl",
        "byla",
        "bylo",
        "byly",
        "byt",
        "se",
        "si",
        "na",
        "v",
        "ve",
        "z",
        "ze",
        "do",
        "k",
        "ke",
        "s",
        "o",
        "u",
        "po",
        "pro",
        "ze",
        "ktery",
        "ktera",
        "ktere",
        "to",
        "ten",
        "ta",
        "tam",
        "tez",
        "take",
        "ale",
        "nebo",
        "jako",
        "pri",
        "pred",
        "za",
    ]
)

#: Neutrale Verlaufs- und Meldungswörter (cs/en/de): beschreiben Entwicklung oder Vorhandensein
#: einer Meldung, behaupten aber weder Ursache noch Diagnose noch Handlung.
NEUTRAL: Final = frozenset(
    [
        # T-07H: Funktionswörter aus Live-Entwürfen (gpt-6-1-sol), ohne eigene Aussage
        "podle",
        "pravidla",
        "pocet",
        "under",
        "value",
        "with",
        "seit",
        "zwischen",
        "gemeldet",
        "zuletzt",
        "meldung",
        "meldungen",
        "rote",
        "roten",
        "rot",
        "gelbe",
        "gelben",
        "gelb",
        "graue",
        "grauen",
        "grau",
        "offene",
        "offenen",
        "offen",
        "quittiert",
        "since",
        "between",
        "reported",
        "latest",
        "alert",
        "alerts",
        "red",
        "yellow",
        "grey",
        "gray",
        "open",
        "acknowledged",
        "od",
        "mezi",
        "hlaseno",
        "vystraha",
        "vystrahy",
        "cervena",
        "cervene",
        "zluta",
        "seda",
        "otevrena",
        "potvrzena",
    ]
)


#: Richtungswörter (normalisiert) je Richtung; eine Richtung im Satz braucht ein Wort derselben
#: Richtung im zitierten Beleg (T-07G): "unchanged" darf nicht für einen steigenden Wert stehen.
DIRECTIONS: Final[dict[str, frozenset[str]]] = {
    "up": frozenset(
        ["rising", "increased", "gestiegen", "steigend", "rostouci", "zvysil", "zvysila"]
    ),
    "down": frozenset(
        ["falling", "decreased", "gesunken", "fallend", "sinkend", "klesajici", "snizil", "snizila"]
    ),
    "flat": frozenset(["unchanged", "unverandert", "gleichbleibend", "beze", "zmeny", "stabilni"]),
}


def normalize(word: str) -> str:
    """Kleinschreibung ohne Diakritika (`Übelkeit` ⇒ `ubelkeit`, `Horečka` ⇒ `horecka`)."""
    decomposed = unicodedata.normalize("NFKD", word.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def words(text: str) -> set[str]:
    return {normalize(w) for w in WORD.findall(text) if len(w) > 1}


# A3 T-07H F-02: Attributnamen sind keine Stammbasis (sonst „present“ ⇐ „presence“, „severe“ ⇐
# „severity“; eine Aussage aus dem Attributnamen statt aus dem Wert).
_NO_STEM_BASE: Final = frozenset(
    normalize(w)
    for w in (
        "presence",
        "severity",
        "frequency",
        "interference",
        "výskyt",
        "závažnost",
        "četnost",
        "vliv",
        "Auftreten",
        "Schweregrad",
        "Häufigkeit",
        "Beeinträchtigung",
    )
)


def _same_stem(word: str, known: str) -> bool:
    """T-07H: Beugungsform desselben Stamms (cs `průjmu`/`průjem`, `závažnosti`/`závažnost`, en
    `reaching`/`reached`): gemeinsamer Anfang ≥ 4 Zeichen und ≥ 60 % des kürzeren Wortes. Zahlen,
    Daten, Richtungs- und Verbotswörter prüfen weiterhin eigene, strenge Regeln."""
    if word.isdigit() or known.isdigit() or known in _NO_STEM_BASE:
        return False
    common = 0
    for a, b in zip(word, known, strict=False):
        if a != b:
            break
        common += 1
    return common >= 4 and common >= 0.6 * min(len(word), len(known))


def unsupported_words(body: str, evidence: Iterable[str]) -> set[str]:
    """Inhaltswörter des Satzes, die weder in den Belegen noch in der Erlaubtliste stehen."""
    allowed = {normalize(w) for w in STOPWORDS | NEUTRAL}
    evidence_words = [words(text) for text in evidence]
    known = set().union(*evidence_words)
    spoken = words(body)
    every_direction = frozenset().union(*DIRECTIONS.values())
    unsupported = spoken - allowed - known - every_direction  # Richtungswörter prüft die Schleife
    unsupported = {w for w in unsupported if not any(_same_stem(w, k) for k in known)}
    for direction in DIRECTIONS.values():
        used = spoken & direction
        if used and not known & direction:  # Richtung nicht belegt (auch nicht sinngleich)
            unsupported |= used
    return unsupported
