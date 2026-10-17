"""Quelltexte der Fachinformation (SmPC): lokale Datei ⇒ Text ⇒ Abschnitt 4.8.

Unterstützt werden Klartext (`.txt`, z. B. aus einem PDF extrahiert) und HTML (`.html`, `.htm`).
Gelesen wird nur die Datei, die der Aufrufer nennt; es gibt keinen Netzzugriff und keine Suche nach
Dateien. Der Vergleich für „wörtlich“ ist leerraum- und bindestrichnormalisiert (Silbentrennung am
Zeilenende, geschützte Leerzeichen), sonst unverändert (Groß-/Kleinschreibung zählt).
"""

import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Final

SUPPORTED_SUFFIXES: Final = {".txt", ".html", ".htm"}
_BLOCK_TAGS: Final = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table"}
_CELL_TAGS: Final = {"td", "th"}
_SKIPPED_TAGS: Final = {"script", "style"}
_HYPHEN_BREAK: Final = re.compile(r"(\w)[-\u00ad]\s*\n\s*(\w)")
_SPACES: Final = re.compile(r"[ \t\r\f\v\u00a0\u2009\u202f]+")


class SourceError(ValueError):
    """Quelle nicht lesbar, unbekanntes Format oder Abschnitt nicht gefunden."""


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    title: str
    url: str
    retrieved: str
    text: str

    def section(self, number: str) -> "Section":
        return find_section(self.text, number)


@dataclass(frozen=True)
class Section:
    number: str
    text: str


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in _CELL_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in _CELL_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    return "".join(parser.parts)


def clean(text: str) -> str:
    """Zeilenenden vereinheitlichen, Silbentrennung am Zeilenende auflösen, Leerzeilen straffen."""
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def normalize(text: str) -> str:
    """Vergleichsform für „wörtlich“: bereinigt, Zeilenumbrüche und Leerraum als ein Leerzeichen."""
    return " ".join(clean(text).split())


def load_source(
    path: Path, document_id: str, title: str = "", url: str = "", retrieved: str = ""
) -> SourceDocument:
    """Liest genau diese Datei (UTF-8); `.html` wird in Text umgewandelt."""
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise SourceError(f"unsupported source format: {path.suffix or '(none)'}")
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise SourceError(f"source not readable: {path.name}") from error
    text = html_to_text(raw) if path.suffix.lower() in {".html", ".htm"} else raw
    return SourceDocument(document_id, title or document_id, url, retrieved, clean(text))


def _heading(number: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*{re.escape(number)}\.?(?=\s|$)", re.MULTILINE)


def _next_number(number: str) -> str:
    """4.8 ⇒ 4.9 (Ende des Abschnitts); allgemein: letzte Zahl + 1."""
    head, _, tail = number.rpartition(".")
    if not tail.isdigit():
        raise SourceError(f"invalid section number: {number}")
    return f"{head}.{int(tail) + 1}" if head else str(int(tail) + 1)


def find_section(text: str, number: str) -> Section:
    """Text zwischen Überschrift `number` und der nächsten Überschrift (z. B. 4.8 bis 4.9).

    Gibt es die Überschrift mehrfach (Inhaltsverzeichnis), zählt die mit dem längsten Abschnitt.
    """
    end = _heading(_next_number(number))
    best = ""
    for start in _heading(number).finditer(text):
        stop = end.search(text, start.end())
        body = text[start.start() : stop.start() if stop else len(text)].strip()
        if len(body) > len(best):
            best = body
    if not best:
        raise SourceError(f"section {number} not found")
    return Section(number, best)
