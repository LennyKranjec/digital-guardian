"""Deterministischer Prüfer für KI-Sätze (Vertrag README §4, G-09); ohne Uhr, DB und LLM.

Ein Satz gilt als `verified`, wenn
- er mindestens einen Beleg `[fakt-id]` trägt und alle Belege in der Faktenliste dieser Patientin
  existieren,
- jede Zahl im Satz (Regex `(?<![\\d.,])\\d+([.,]\\d+)?(?!\\d)`, `,` gilt als Dezimaltrenner) in den
  Texten der zitierten Belege vorkommt,
- jedes ISO-Datum `YYYY-MM-DD` im Satz wörtlich in den zitierten Belegtexten steht und
- er keine Formulierung der Verbotsliste enthält (Diagnose, Therapieempfehlung, Beruhigung,
  Ursachenbehauptung) und
- (außer beim Textbaustein) jedes Inhaltswort in den zitierten
  Belegtexten oder in der kleinen Erlaubtliste neutraler Verlaufswörter steht (`extractive.py`);
  das fängt umformulierte Therapie-, Ursachen-, Diagnose- und Beruhigungssätze, die der
  Stichwortfilter nicht kennt, und
- (T-07G, nur Entwürfe eines Sprachmodells) er **genau einen** Beleg trägt: Zahlen, Daten und
  Wörter werden gegen diesen einen Beleg geprüft, nicht gegen die Vereinigung mehrerer Belege.
  Sonst ließe sich ein Wert oder Trend eines Belegs in die Aussage eines anderen übernehmen.

Alle anderen Sätze werden verworfen und gezählt (`dropped`). Themen ohne Daten stehen in
`unknown_topics`.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

from waechter.llm.extractive import unsupported_words

NUMBER: Final = re.compile(r"(?<![\d.,])\d+([.,]\d+)?(?!\d)")
ISO_DATE: Final = re.compile(r"\d{4}-\d{2}-\d{2}")
REF_GROUP: Final = re.compile(r"\[([^\[\]]*)\]")
REF_ID: Final = re.compile(r"^[a-z]+-[A-Za-z0-9-]+$")
SENTENCE_END: Final = re.compile(r"(?<=[.!?])\s+")
LEADING_REFS: Final = re.compile(r"^\s*(?:\[[^\[\]]*\]\s*)+")

#: Verbotsliste (COMMON §2): keine Diagnose, keine Therapieentscheidung, keine falsche Beruhigung,
#: keine Ursachenbehauptung. Treffer ⇒ Satz verwerfen. Muster für de, cs und en.
FORBIDDEN: Final = re.compile(
    r"|".join(
        [
            # Diagnose
            r"diagnos",
            r"diagnóz",
            r"\bleidet an\b",
            r"\bsuffers? from\b",
            r"\btrpí\b",
            # Therapieempfehlung / -entscheidung
            r"empfehl",
            r"\bich rate\b",
            r"\brecommend",
            r"doporuč",
            r"\bsuggest(ion)?s?\b",
            r"dosis(anpass|reduzier|erhöh)",
            r"dose (reduction|adjust|increase|change)",
            r"(therapie|behandlung|dosis|medikation|chemo)\w*\s+(zu \w+ )?"
            r"(abbrech|absetz|pausier|stopp|beend|reduzier|erhöh|ändern|anpass)",
            r"(reduzier|erhöh|absetz|pausier|abbrech|stopp|beend)\w*\s+(sie\s+)?(die\s+)?"
            r"(therapie|behandlung|dosis|medikation|chemo)",
            r"(stop|discontinue|interrupt|hold|reduce|increase|adjust)\s+(the\s+)?"
            r"(therapy|treatment|dose|medication|chemotherapy)",
            r"(snížit|zvýšit|vysadit|přerušit|ukončit)\s+(dávk|léčb|terapi)",
            r"therapie(änderung|anpassung|abbruch|wechsel)",
            r"\bprescrib",
            r"\bverordn",
            r"\bpředeps",
            r"\bshould (be )?(treated|given|started)\b",
            r"\bmuss behandelt\b",
            # falsche Beruhigung
            r"keine sorge",
            r"unbedenklich",
            r"harmlos",
            r"kein grund zur",
            r"alles (in ordnung|gut)\b",
            r"\beverything is (fine|well|normal|ok)\b",
            r"\ball good\b",
            r"\bno need to worry\b",
            r"\bnothing to worry\b",
            r"\bno cause for concern\b",
            r"\bharmless\b",
            r"\ball (is )?(well|fine|normal)\b",
            r"není důvod",
            r"nemusí se",
            r"v pořádku",
            r"neškodn",
            r"\breassur",
            # Ursachenbehauptung
            r"verursacht",
            r"\bcaused by\b",
            r"\bdue to the (drug|therapy|treatment)\b",
            r"způsoben",
            r"\bführt(e)? auf\b",
        ]
    ),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Sentence:
    text: str
    refs: tuple[str, ...]
    verified: bool = True


@dataclass(frozen=True)
class Verified:
    sentences: list[Sentence]
    dropped: int
    unknown_topics: list[str] = field(default_factory=list)


def numbers(text: str) -> set[Decimal]:
    """Zahlen-Tokens eines Textes (ISO-Daten ausgenommen; `,` ⇒ `.`)."""
    without_dates = ISO_DATE.sub(" ", text)
    return {Decimal(m.group(0).replace(",", ".")) for m in NUMBER.finditer(without_dates)}


def _refs_of(chunk: str) -> list[str]:
    refs: list[str] = []
    for group in REF_GROUP.findall(chunk):
        refs.extend(part for part in re.split(r"[\s,;]+", group.strip()) if part)
    return refs


def split_sentences(text: str) -> list[tuple[str, tuple[str, ...]]]:
    """Zerlegt in `(Satztext ohne Belege, Belege)`.

    Belege hinter dem Satzzeichen (`Satz. [id]`) gehören zum Vorsatz, auch wenn sie am Anfang des
    nächsten Fragments stehen.
    """
    sentences: list[tuple[str, list[str]]] = []
    # T-07H: ein Zeilenumbruch direkt nach einem Beleg beendet den Satz (Modelle schreiben je Satz
    # eine Zeile „… [id]“ ohne Punkt); ohne das verschmolzen die Zeilen zu einem Satz mit n Belegen.
    text = re.sub(r"\][ \t]*\r?\n", "].\n", text)
    for chunk in SENTENCE_END.split(text.replace("\n", " ").strip()):
        leading = LEADING_REFS.match(chunk)
        if leading is not None and sentences:
            sentences[-1][1].extend(_refs_of(leading.group(0)))
            chunk = chunk[leading.end() :]
        refs = _refs_of(chunk)
        body = re.sub(r"\s+", " ", REF_GROUP.sub(" ", chunk)).strip(" ,;")
        body = re.sub(r"\s+([.,;!?])", r"\1", body)
        if not body.strip(".!? "):  # Fragment besteht nur aus Belegen
            if sentences:
                sentences[-1][1].extend(refs)
            continue
        sentences.append((body, refs))
    return [(body, tuple(dict.fromkeys(refs))) for body, refs in sentences]


def _supported(body: str, evidence: Sequence[str]) -> bool:
    """Alle Zahlen und ISO-Daten des Satzes stehen in den Belegtexten."""
    joined = " ".join(evidence)
    if any(date not in joined for date in ISO_DATE.findall(body)):
        return False
    return numbers(body) <= numbers(joined)


#: Sätze, die einen Freitext-Fakt (`ft-`) belegen, müssen die Zuschreibung tragen: der Wortlaut
#: stammt von der Patientin, nicht vom System (A3 F-02). Der Textbaustein ist ausgenommen.
_ATTRIBUTION: Final = re.compile(
    r"^(die\s+)?(patientin\s+schrieb|patient\s+wrote|the\s+patient\s+wrote|pacientka\s+napsala)\b",
    re.IGNORECASE,
)


def _without_attribution(body: str) -> str:
    """Satz ohne die feste Zuschreibung am Anfang (deren Wörter stehen nicht im Beleg)."""
    return _ATTRIBUTION.sub("", body.strip(), count=1).lstrip(" :,")


def _attributed(body: str, refs: Sequence[str]) -> bool:
    if not any(r.startswith("ft-") for r in refs):
        return True
    return _ATTRIBUTION.match(body.strip()) is not None


def verify(
    text: str,
    facts: Mapping[str, str],
    topics_without_data: Sequence[str] = (),
    *,
    extractive: bool = True,
) -> Verified:
    """Prüft jeden Satz des Entwurfs gegen die Fakten (`fakt-id ⇒ Text`).

    Die Wortprüfung und die Regel "genau ein Beleg je Satz" sind Standard (Entwürfe eines
    Sprachmodells); nur der Textbaustein (besteht aus den Belegtexten, ein Satz je Beleg) schaltet
    sie mit `extractive=False` ab.
    """
    kept: list[Sentence] = []
    dropped = 0
    for body, refs in split_sentences(text):
        valid_refs = bool(refs) and all(REF_ID.match(r) and r in facts for r in refs)
        ok = (
            valid_refs
            and (not extractive or _attributed(body, refs))  # Freitext nur mit Zuschreibung (T-22F)
            and (not extractive or len(refs) == 1)  # LLM-Modus: ein Satz, ein Beleg (T-07G)
            and _supported(body, [facts[r] for r in refs])
            and FORBIDDEN.search(body) is None
            and (
                not extractive
                or not unsupported_words(_without_attribution(body), [facts[r] for r in refs])
            )
        )
        if ok:
            kept.append(Sentence(text=body, refs=refs))
        else:
            dropped += 1
    return Verified(sentences=kept, dropped=dropped, unknown_topics=list(topics_without_data))
