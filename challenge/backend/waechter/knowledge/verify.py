"""Deterministischer Prüfer für AE-Zeilen (manuell oder Sprachmodell) und CSV-Ein-/Ausgabe.

Das Modell entscheidet nie, was gilt. Eine Zeile gilt nur, wenn die Belegstelle im Quelltext
vorkommt, den Originalbegriff enthält, die Häufigkeitsklasse aus dem festen Aufzählungstyp stammt
und dem Text nicht widerspricht. Ergebnis je Zeile: `verified` (alle Prüfungen bestanden),
`unverified` (Beleg ok, aber CTCAE-Zuordnung nicht in der Liste oder Zeile als unverified geführt)
oder `rejected` (nicht belegt ⇒ kommt nicht nach FHIR). Klinisch bleibt alles Entwurf.
"""

import csv
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Final, Literal

from waechter.knowledge.sources import clean, normalize

FREQUENCY_CLASSES: Final = (
    "very common",
    "common",
    "uncommon",
    "rare",
    "very rare",
    "not known",
)
#: Überschriften der SmPC-Häufigkeitsklassen (MedDRA-Konvention) in cs/en/de, klein geschrieben.
FREQUENCY_LABELS: Final[dict[str, str]] = {
    "very common": "very common",
    "common": "common",
    "uncommon": "uncommon",
    "rare": "rare",
    "very rare": "very rare",
    "not known": "not known",
    "frequency not known": "not known",
    "velmi časté": "very common",
    "časté": "common",
    "méně časté": "uncommon",
    "vzácné": "rare",
    "velmi vzácné": "very rare",
    "není známo": "not known",
    "četnost není známa": "not known",
    "sehr häufig": "very common",
    "häufig": "common",
    "gelegentlich": "uncommon",
    "selten": "rare",
    "sehr selten": "very rare",
    "nicht bekannt": "not known",
    "häufigkeit nicht bekannt": "not known",
}
_LABEL_PATTERN: Final = re.compile(
    r"(?<!\w)("
    + "|".join(re.escape(k) for k in sorted(FREQUENCY_LABELS, key=len, reverse=True))
    + r")(?!\w)",
    re.IGNORECASE,
)
COLUMNS: Final = (
    "substance_id",
    "document",
    "document_url",
    "section",
    "retrieved",
    "original_term",
    "frequency_class",
    "ctcae_v6_term",
    "patient_reportable",
    "pro_item",
    "status",
    "extraction",
    "evidence",
)
REQUIRED: Final = (
    "substance_id",
    "document",
    "section",
    "retrieved",
    "original_term",
    "frequency_class",
    "status",
    "extraction",
)
_SECTION: Final = re.compile(r"^(\d+(?:\.\d+)*)(?=$|[\s;])")
_EXTRACTION: Final = re.compile(r"^(manual|llm:[A-Za-z0-9_.:/-]+)$")
Status = Literal["verified", "unverified", "rejected"]


def section_number(section: str) -> str | None:
    """Abschnittsnummer am Anfang der Angabe ("4.8 Nežádoucí účinky; Tabulka 1" ⇒ "4.8")."""
    match = _SECTION.match(section.strip())
    return match.group(1) if match else None


@dataclass(frozen=True)
class AeRow:
    """Eine Zeile der AE-Matrix (Vertrag §12, Schritt 2) plus optionale Belegstelle."""

    substance_id: str
    document: str
    document_url: str
    section: str
    retrieved: str
    original_term: str
    frequency_class: str
    ctcae_v6_term: str = ""
    patient_reportable: str = ""
    pro_item: str = ""
    status: str = "unverified"
    extraction: str = "manual"
    evidence: str = ""


@dataclass(frozen=True)
class Verdict:
    status: Status
    reasons: tuple[str, ...] = ()
    checks: dict[str, str] = field(default_factory=dict)


def frequency_in_context(text: str, end: int) -> str | None:
    """Häufigkeitsklasse der letzten Überschrift vor Position `end` (Normaltext), sonst None."""
    last: str | None = None
    for match in _LABEL_PATTERN.finditer(text, 0, end):
        last = FREQUENCY_LABELS[match.group(1).lower()]
    return last


_BEFORE_ITEM: Final = re.compile(r"(?:^|[,;:(\[/|]\s*|(?:^|\s)(?:a|and|und|or|oder|nebo)\s+)$")
_AFTER_ITEM: Final = re.compile(r"^(?:\s*$|\s*[,;:)\]/.|]|\s+(?:a|and|und|or|oder|nebo)\s)")


def item_ends(text: str, term: str) -> list[int]:
    """Endpositionen aller Vorkommen von `term` als **ganzer Aufzählungspunkt** in `text`.

    Ein Vorkommen zählt nur, wenn davor Textanfang, ein Trenner (`, ; : ( [ /`) oder ein
    Bindewort steht und danach Textende, ein Trenner oder ein Bindewort folgt. So ist `bolest`
    kein Treffer in `bolest břicha` (T-19G, A3 F-02). Beide Texte sind bereits normalisiert und
    werden klein geschrieben verglichen (Positionen bleiben gleich).
    """
    haystack, needle = text.lower(), term.lower()
    ends: list[int] = []
    start = haystack.find(needle) if needle else -1
    while start >= 0:
        end = start + len(needle)
        if _BEFORE_ITEM.search(haystack[:start]) and _AFTER_ITEM.match(haystack[end:]):
            ends.append(end)
        start = haystack.find(needle, start + 1)
    return ends


def _context_labels(source: str, ends: list[int]) -> list[str | None]:
    return [frequency_in_context(source, end) for end in ends]


def _context_verdict(labels: list[str | None], claimed: str) -> str:
    """`confirmed`, wenn die behauptete Klasse an einem Fundort des Begriffs steht.

    `contradicts`, wenn alle Fundorte unter einer anderen Überschrift stehen (mindestens einer mit
    erkennbarer Überschrift); sonst `not_checkable`.
    """
    if claimed in labels:
        return "confirmed"
    return "contradicts" if any(label is not None for label in labels) else "not_checkable"


def normalize_lines(text: str) -> str:
    """Wie `normalize`, aber Zeilenenden bleiben als Trenner ` | ` erhalten (Listenende)."""
    lines = (line.strip() for line in clean(text).splitlines())
    return " | ".join(line for line in lines if line)


def evidence_spans(source: str, evidence: str) -> list[tuple[int, int]]:
    """Alle wörtlichen Fundstellen der Belegstelle in `source` (Zeilenform, Groß-/Kleinschreibung).

    Ein Zeilenende im Quelltext darf in der Belegstelle als Leerzeichen erscheinen.
    """
    tokens = normalize(evidence).split()
    if not tokens:
        return []
    pattern = re.compile(r"\s(?:\|\s)?".join(re.escape(token) for token in tokens))
    return [(m.start(), m.end()) for m in pattern.finditer(source)]


def _evidence_term_ends(source: str, spans: list[tuple[int, int]], term: str) -> list[int]:
    """Fundorte des Begriffs als ganzer Punkt **im Quelltext** innerhalb einer Belegstelle.

    Die Ränder werden im Zusammenhang des Quelltextes beurteilt (nicht im Zitat allein): ein
    Zitat darf den Begriff nicht erst durch das Abschneiden zum ganzen Punkt machen.
    """
    in_source = item_ends(source, term)
    ends = [e for e in in_source for a, b in spans if e - len(term) >= a and e <= b]
    return list(dict.fromkeys(ends))


def _ctcae_known(term: str, allowed: Collection[str]) -> bool:
    folded = {a.casefold() for a in allowed}
    return term.casefold() in folded


def _final(checks: dict[str, str], reasons: list[str], unverified: bool) -> Verdict:
    rejected = [r for r in reasons if r.endswith("!")]
    if rejected:
        return Verdict("rejected", tuple(r.rstrip("!") for r in reasons), checks)
    if unverified or reasons:
        return Verdict("unverified", tuple(reasons), checks)
    return Verdict("verified", (), checks)


def verify_extracted(row: AeRow, section_text: str, ctcae_terms: Collection[str]) -> Verdict:
    """Prüft eine vom Sprachmodell gelieferte Zeile gegen den Abschnittstext der Quelle."""
    checks: dict[str, str] = {}
    reasons: list[str] = []
    evidence = normalize(row.evidence)
    source = normalize_lines(section_text)
    spans = evidence_spans(source, evidence)
    if not spans:
        checks["evidence"] = "missing"
        reasons.append("evidence_not_in_source!")
    else:
        checks["evidence"] = "found"
    term = normalize(row.original_term)
    if not term or term.lower() not in evidence.lower():  # ganzer Punkt: unten im Quelltext
        checks["term"] = "not_in_evidence"
        reasons.append("term_not_in_evidence!")
    else:
        checks["term"] = "in_evidence"
    if row.frequency_class not in FREQUENCY_CLASSES:
        checks["frequency_enum"] = "invalid"
        reasons.append("frequency_class_invalid!")
    else:
        checks["frequency_enum"] = "valid"
    if (
        checks["evidence"] == "found"
        and checks["term"] == "in_evidence"
        and checks["frequency_enum"] == "valid"
    ):
        # Häufigkeits-Kontext am Fundort des BEGRIFFS (nicht am ersten Vorkommen der Belegstelle)
        ends = _evidence_term_ends(source, spans, term)
        if not ends:  # an der Fundstelle steht der Begriff nicht als ganzer Punkt (z. B. im Zitat)
            checks["term"] = "not_an_item_in_source"
            reasons.append("term_not_in_evidence!")
        else:
            context = _context_verdict(_context_labels(source, ends), row.frequency_class)
            checks["frequency_context"] = context
            if context == "contradicts":
                reasons.append("frequency_contradicts_source!")
    unverified = False
    if row.ctcae_v6_term:
        if _ctcae_known(row.ctcae_v6_term, ctcae_terms):
            checks["ctcae"] = "in_list"
        else:
            checks["ctcae"] = "not_in_list"
            reasons.append("ctcae_not_in_list")
            unverified = True
    return _final(checks, reasons, unverified)


def verify_manual(
    row: AeRow, ctcae_terms: Collection[str], section_text: str | None = None
) -> Verdict:
    """Prüft eine manuell belegte Matrixzeile (Schema; mit Quelltext auch den Originalbegriff)."""
    checks: dict[str, str] = {}
    reasons: list[str] = []
    for name in REQUIRED:
        if not getattr(row, name).strip():
            reasons.append(f"missing_{name}!")
    if reasons:
        return _final(checks, reasons, False)
    if row.frequency_class not in FREQUENCY_CLASSES:
        reasons.append("frequency_class_invalid!")
    if not _SECTION.match(row.section):
        reasons.append("section_invalid!")
    try:
        date.fromisoformat(row.retrieved)
    except ValueError:
        reasons.append("retrieved_invalid!")
    if row.status not in {"verified", "unverified"}:
        reasons.append("status_invalid!")
    if not _EXTRACTION.fullmatch(row.extraction):
        reasons.append("extraction_invalid!")
    if row.patient_reportable not in {"", "yes", "no"}:
        reasons.append("patient_reportable_invalid!")
    if reasons:
        return _final(checks, reasons, False)
    unverified = row.status == "unverified"
    if row.ctcae_v6_term:
        if _ctcae_known(row.ctcae_v6_term, ctcae_terms):
            checks["ctcae"] = "in_list"
        else:
            checks["ctcae"] = "not_in_list"
            reasons.append("ctcae_not_in_list")
            unverified = True
    if section_text is None:
        checks["source_text"] = "not_checked"
    else:
        source = normalize_lines(section_text)
        term = normalize(row.original_term)
        ends = item_ends(source, term)
        if not ends:
            checks["source_text"] = "term_missing"
            reasons.append("term_not_in_source!")
        else:
            checks["source_text"] = "term_found"
            checks["frequency_context"] = _context_verdict(
                _context_labels(source, ends), row.frequency_class
            )
            if checks["frequency_context"] == "contradicts":
                reasons.append("frequency_contradicts_source!")
    return _final(checks, reasons, unverified)


def read_matrix(path: Path) -> list[AeRow]:
    """Liest `ae_matrix.csv` (UTF-8, Kopfzeile Pflicht; fehlende optionale Spalten sind leer)."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = set(reader.fieldnames or [])
        missing = [c for c in REQUIRED if c not in header]
        if missing:
            raise ValueError(f"ae_matrix.csv: missing columns {missing}")
        unknown = sorted(header - set(COLUMNS))
        if unknown:
            raise ValueError(f"ae_matrix.csv: unknown columns {unknown}")
        return [AeRow(**{c: (record.get(c) or "").strip() for c in COLUMNS}) for record in reader]


def write_matrix(path: Path, rows: Iterable[AeRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([getattr(row, c) for c in COLUMNS])


def with_status(row: AeRow, verdict: Verdict) -> AeRow:
    """Zeile mit dem geprüften Status; eine nicht in der Liste stehende CTCAE-Zuordnung entfällt."""
    cleared = "" if verdict.checks.get("ctcae") == "not_in_list" else row.ctcae_v6_term
    return replace(row, status=verdict.status, ctcae_v6_term=cleared)
