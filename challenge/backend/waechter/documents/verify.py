"""Deterministischer Prüfer der Dokumentenkandidaten (kein Modell, keine Uhr, kein Netz).

Ein Kandidat wird nur zugelassen, wenn
1. der Ressourcentyp bekannt ist,
2. das Zitat wörtlich im Dokument steht (Vergleich leerraum-/silbentrennungsnormalisiert),
3. der Code in der Allow-Liste steht (ICD-10-Präfix aus `diagnoses.yaml`, ATC/kód SÚKL aus
   `medications.yaml`, LOINC aus `allowlists.LABS`),
4. der Code bzw. ein Name der Allow-Liste im Zitat vorkommt,
5. bei Laborwerten Wert und Einheit im Zitat stehen und die Einheit zum Laborwert passt,
6. ein angegebenes Datum im Dokument vorkommt.
Anzeigetexte und UCUM-Codes kommen aus der Allow-Liste, nie vom Extraktor.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from waechter.documents.allowlists import (
    AllowLists,
    LabTest,
    Medication,
    lab_pattern,
    norm_unit,
)
from waechter.documents.candidates import (
    MAX_CANDIDATES,
    MAX_QUOTE,
    RESOURCE_TYPES,
    Candidate,
    RawCandidate,
    Rejected,
)
from waechter.knowledge.sources import normalize

_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_LOCAL_DATE = re.compile(r"(?<!\d)(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})(?!\d)")


def parse_iso(text: str) -> str | None:
    """`YYYY-MM-DD` ⇒ dieselbe Zeichenkette, wenn es ein gültiges Datum ist."""
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text.strip())
    if match is None:
        return None
    try:
        return date(int(match[1]), int(match[2]), int(match[3])).isoformat()
    except ValueError:
        return None


def dates_in(text: str) -> list[str]:
    """Alle gültigen Datumsangaben des Textes (ISO und `d.m.yyyy`) als ISO, in Textreihenfolge."""
    found: list[tuple[int, str]] = []
    for m in _ISO_DATE.finditer(text):
        iso = parse_iso(m.group(0))
        if iso:
            found.append((m.start(), iso))
    for m in _LOCAL_DATE.finditer(text):
        try:
            found.append((m.start(), date(int(m[3]), int(m[2]), int(m[1])).isoformat()))
        except ValueError:
            continue
    return [iso for _, iso in sorted(found)]


MAX_DIGITS = 15
MAX_EXPONENT = 9


def decimal_of(text: str) -> Decimal | None:
    """Zahl aus Text; nicht endlich, riesig, winzig oder überlang ⇒ `None` (nie eine Ausnahme)."""
    try:
        value = Decimal(text.strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    _, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int) or len(digits) > MAX_DIGITS:
        return None
    if not -MAX_EXPONENT <= exponent <= MAX_EXPONENT or value.adjusted() > MAX_EXPONENT:
        return None
    return value


def contains_word(text: str, word: str) -> bool:
    """Ganzes Wort bzw. ganzer Code (Groß-/Kleinschreibung egal), nicht Teil eines Wortes."""
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) is not None


def _quote_problem(quote: str, normalized_document: str) -> str | None:
    if not 3 <= len(quote) <= MAX_QUOTE:
        return "quote_length_invalid"
    if normalize(quote) not in normalized_document:
        return "quote_not_verbatim"
    return None


_Result = tuple[Candidate | None, list[str]]

#: Kontext, in dem ein Code keine Aussage über die Patientin ist (Verneinung, Familie; cs/de/en)
_NEGATION = re.compile(
    r"(?<!\w)(?:vylou[cč]en|bez\s+(?:zn[aá]mek|pr[uů]kazu|nález)|neprok[aá]z|nezji[sš]t|negativn|"
    r"ausgeschlossen|kein(?:e|en)?\s+(?:nachweis|hinweis)|ohne\s+(?:nachweis|hinweis)|"
    r"nicht\s+nachweisbar|no\s+evidence|ruled\s+out|excluded|negative\s+for|without\s+evidence)",
    re.IGNORECASE,
)
_FAMILY = re.compile(
    r"(?<!\w)(?:rodinn|matk|ot[ce]c|sest[rř]|brat[rř]|bab[iy]čk|d[eě]de[kč]|"
    r"familienanamnese|famili[aä]r|mutter|vater|schwester|bruder|gro(?:ß|ss)(?:mutter|vater)|"
    r"family\s+history|mother|father|sister|brother|grand(?:mother|father))",
    re.IGNORECASE,
)


def _context_problem(quote: str, *, family: bool) -> str | None:
    """Zeile spricht von etwas Ausgeschlossenem oder von Angehörigen ⇒ kein Entwurf."""
    if _NEGATION.search(quote):
        return "context_negated"
    if family and _FAMILY.search(quote):
        return "context_family"
    return None


def _check_condition(raw: RawCandidate, quote: str, allow: AllowLists) -> _Result:
    code = raw.code.strip().upper()
    if not allow.icd_allowed(code):
        return None, ["code_not_allowed"]
    if not contains_word(quote, code):
        return None, ["code_not_in_quote"]
    if (problem := _context_problem(quote, family=True)) is not None:
        return None, [problem]
    return Candidate("Condition", code, code, quote), []


def _medication_in_quote(quote: str, med: Medication) -> bool:
    if contains_word(quote, med.atc):
        return True
    if med.sukl_code and contains_word(quote, med.sukl_code):
        return True
    return any(contains_word(quote, alias) for alias in med.aliases)


def _check_medication(raw: RawCandidate, quote: str, allow: AllowLists) -> _Result:
    med = allow.medication_by_code(raw.code)
    if med is None:
        return None, ["code_not_allowed"]
    if not _medication_in_quote(quote, med):
        return None, ["code_not_in_quote"]
    if (problem := _context_problem(quote, family=False)) is not None:
        return None, [problem]
    return Candidate(
        "MedicationStatement", med.atc, med.display, quote, sukl_code=med.sukl_code
    ), []


def _check_lab(raw: RawCandidate, quote: str, allow: AllowLists) -> _Result:
    lab: LabTest | None = allow.lab_by_loinc(raw.code)
    if lab is None:
        return None, ["code_not_allowed"]
    if not any(contains_word(quote, alias) for alias in lab.aliases):
        return None, ["name_not_in_quote"]
    value = decimal_of(raw.value or "")
    if value is None:
        return None, ["value_invalid"]
    unit = (raw.unit or "").strip()
    ucum = lab.units.get(norm_unit(unit))
    if ucum is None:
        return None, ["unit_not_allowed"]
    # Wert und Einheit müssen direkt hinter dem Namen DIESES Laborwerts stehen (nicht beim Nachbarn)
    bound = [m for m in lab_pattern(lab).finditer(quote) if decimal_of(m["value"]) == value]
    if not bound:
        return None, ["value_not_in_quote"]
    if not any(norm_unit(m["unit"].rstrip(".)")) == norm_unit(unit) for m in bound):
        return None, ["unit_not_in_quote"]
    return (
        Candidate("Observation", lab.loinc, lab.display, quote, format(value, "f"), unit, ucum),
        [],
    )


@dataclass(frozen=True)
class DocumentContext:
    """Einmal je Dokument berechnet (nicht je Kandidat): normalisierter Text und Datumsmenge."""

    normalized: str
    dates: frozenset[str]


def document_context(document_text: str) -> DocumentContext:
    return DocumentContext(normalize(document_text), frozenset(dates_in(document_text)))


def check(
    raw: RawCandidate,
    document_text: str,
    allow: AllowLists,
    context: DocumentContext | None = None,
) -> _Result:
    """Ein Kandidat ⇒ (zugelassener Kandidat, []) oder (None, Gründe der Ablehnung)."""
    if raw.resource_type not in RESOURCE_TYPES:
        return None, ["resource_type_unknown"]
    context = context or document_context(document_text)
    quote = raw.quote.strip()
    problem = _quote_problem(quote, context.normalized)
    if problem is not None:
        return None, [problem]
    if raw.resource_type == "Condition":
        candidate, reasons = _check_condition(raw, quote, allow)
    elif raw.resource_type == "MedicationStatement":
        candidate, reasons = _check_medication(raw, quote, allow)
    else:
        candidate, reasons = _check_lab(raw, quote, allow)
    if candidate is None:
        return None, reasons
    if raw.date:
        iso = parse_iso(raw.date)
        if iso is None:
            return None, ["date_invalid"]
        if iso not in context.dates:
            return None, ["date_not_in_document"]
        candidate = Candidate(
            candidate.resource_type,
            candidate.code,
            candidate.display,
            candidate.quote,
            candidate.value,
            candidate.unit,
            candidate.ucum,
            iso,
            candidate.sukl_code,
        )
    return candidate, []


def check_all(
    raws: Iterable[RawCandidate], document_text: str, allow: AllowLists
) -> tuple[list[Candidate], list[Rejected]]:
    """Alle Kandidaten prüfen; Duplikate entfallen, die Zahl ist begrenzt (Rest ⇒ verworfen)."""
    accepted: list[Candidate] = []
    rejected: list[Rejected] = []
    seen: set[str] = set()
    context = document_context(document_text)
    for raw in raws:
        if len(accepted) >= MAX_CANDIDATES:  # Obergrenze erreicht: Rest nicht mehr einzeln prüfen
            rejected.append(
                Rejected(raw.resource_type, raw.code, raw.quote, ("too_many_candidates",))
            )
            break
        candidate, reasons = check(raw, document_text, allow, context)
        if candidate is None:
            rejected.append(Rejected(raw.resource_type, raw.code, raw.quote, tuple(reasons)))
            continue
        key = f"{candidate.resource_type}|{candidate.code}|{candidate.value}|{candidate.date}"
        if key in seen:
            continue
        if len(accepted) >= MAX_CANDIDATES:
            rejected.append(
                Rejected(raw.resource_type, raw.code, raw.quote, ("too_many_candidates",))
            )
            continue
        seen.add(key)
        accepted.append(candidate)
    return accepted, rejected
