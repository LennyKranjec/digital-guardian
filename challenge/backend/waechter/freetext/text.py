"""Textwerkzeuge: längentreues Falten (Diakritika/Großschreibung) und Wortanfangs-Suche.

`fold` liefert einen Text **gleicher Länge** (Zeichen für Zeichen), damit Fundstellen im gefalteten
Text direkt Positionen im Originaltext sind (Zitat = `text[start:end]`).
"""

import re
import unicodedata
from collections.abc import Iterable
from typing import Final

_APOSTROPHES: Final = "\u2019\u2018\u00b4`"  # typografische Apostrophe, Akut, Gravis
_SPACE_RUN: Final = re.compile(r"\s+")
CONTROL: Final = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _fold_char(char: str) -> str:
    if char in _APOSTROPHES:
        return "'"
    decomposed = unicodedata.normalize("NFKD", char)
    base = decomposed[0] if decomposed else char
    lowered = base.lower()
    return lowered if len(lowered) == 1 else base


def fold(text: str) -> str:
    """Kleinschreibung ohne Diakritika, Zeichen für Zeichen (gleiche Länge wie `text`)."""
    return "".join(_fold_char(c) for c in text)


def lower_same_length(text: str) -> str:
    """Nur Kleinschreibung (Diakritika bleiben), gleiche Länge; für wörtliche Zitate."""
    return "".join(c.lower() if len(c.lower()) == 1 else c for c in text)


def clean_text(raw: str) -> str:
    """Zeilenenden vereinheitlichen, Steuerzeichen entfernen, Ränder kürzen."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    return CONTROL.sub("", text).strip()


def _pattern(term: str) -> re.Pattern[str] | None:
    tokens = [re.escape(t) for t in fold(term).split()]
    if not tokens or sum(len(t) for t in tokens) < 3:
        return None
    return re.compile(r"(?<![^\W\d_])" + r"\s+".join(tokens))


def word_end(text: str, end: int) -> int:
    """Verlängert `end` bis zum Ende des angebrochenen Wortes."""
    while end < len(text) and (text[end].isalnum() or text[end] == "_"):
        end += 1
    return end


def find_terms(text: str, terms: Iterable[str]) -> list[tuple[int, int]]:
    """Fundstellen `(start, end)` der Begriffe als Wortanfang; `end` reicht bis Wortende.

    Verglichen wird ohne Diakritika und Großschreibung; Mehrwortbegriffe dürfen beliebigen
    Leerraum (auch Zeilenumbruch) zwischen den Wörtern haben. Überlappende Treffer werden
    zusammengefasst, damit ein Zitat nicht doppelt erscheint.
    """
    folded = fold(text)
    spans: list[tuple[int, int]] = []
    for term in terms:
        pattern = _pattern(term)
        if pattern is None:
            continue
        spans.extend((m.start(), word_end(text, m.end())) for m in pattern.finditer(folded))
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def find_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Erste wörtliche Fundstelle des Zitats (Groß-/Kleinschreibung egal, Leerraum flexibel).

    Diakritika zählen: ein Zitat mit anderen Buchstaben ist nicht wörtlich.
    """
    parts = quote.split()
    if not parts:
        return None
    pattern = re.compile(r"\s+".join(re.escape(lower_same_length(p)) for p in parts))
    match = pattern.search(lower_same_length(text))
    return (match.start(), match.end()) if match else None


def collapse_spaces(text: str) -> str:
    return _SPACE_RUN.sub(" ", text).strip()
