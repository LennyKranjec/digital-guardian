"""Extraktoren der Dokumentenpipeline: `template` (deterministisch, Regex) und `llm` (Adapter).

Beide liefern nur **Rohkandidaten**; zugelassen werden sie erst vom Prüfer (`verify.check_all`).
Der `llm`-Extraktor erreicht das Modell ausschließlich über
`waechter.knowledge.extract.AdapterModel` (= `waechter.llm.adapters`, `WAECHTER_LLM=openai`);
ohne Modell oder bei jedem Fehler fällt der Lauf auf `template` zurück (Modus `fallback`, Grund
im Ergebnis). Der Prompt enthält nur den Dokumenttext.
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from waechter.documents.allowlists import AllowLists, LabTest, lab_pattern, norm_unit
from waechter.documents.candidates import MAX_CANDIDATES, MAX_QUOTE, RESOURCE_TYPES, RawCandidate
from waechter.documents.verify import dates_in
from waechter.knowledge.extract import ExtractionUnavailable, TextModel

logger = logging.getLogger("waechter.documents")

TEMPLATE_ID: Final = "template-regex-v1"
PROMPT_VERSION: Final = "doc-extract-v1"
_ICD: Final = re.compile(r"(?<![\w.])[A-TV-Z]\d{2}(?:\.\d{1,2})?(?![\w])")
_DATE_LINE: Final = re.compile(
    r"^\W*(datum|date|dne|dat\.|odběr|vyšetření|vystaveno|entnahme|erstellt|befund)\b",
    re.IGNORECASE,
)
_FENCE: Final = re.compile(r"^```[a-zA-Z]*\s*\n?|\n?```\s*$")
#: Fabrik des Sprachmodells; Tests ersetzen sie (kein Netz in Tests)
ModelFactory = Callable[[], TextModel]


def _default_model_factory() -> TextModel:
    from waechter.knowledge.extract import AdapterModel

    return AdapterModel()


model_factory: ModelFactory = _default_model_factory


@dataclass(frozen=True)
class Extraction:
    raws: list[RawCandidate]
    extractor: str  # TEMPLATE_ID oder `openai:<Modell>`
    mode: str  # template | llm | fallback
    fallback_reason: str | None = None


def _line_quote(line: str) -> str:
    return " ".join(line.split())[:MAX_QUOTE]


def _first_date(text: str) -> str | None:
    found = dates_in(text)
    return found[0] if found else None


def document_date(lines: list[str]) -> str | None:
    """Datum der Kopfzeile (`Datum:`, `Date:` …); sonst keines (nie geraten)."""
    for line in lines:
        if _DATE_LINE.match(line):
            found = _first_date(line)
            if found:
                return found
    return None


def _lab_patterns(allow: AllowLists) -> list[tuple[LabTest, re.Pattern[str]]]:
    return [(lab, lab_pattern(lab)) for lab in allow.labs]


def extract_template(text: str, allow: AllowLists) -> list[RawCandidate]:
    """Deterministisch: ICD-10-Codes, Arzneimittel (Code/Name), Laborzeilen „Name Wert Einheit“."""
    lines = [line for line in text.splitlines() if line.strip()]
    header_date = document_date(lines)
    labs = _lab_patterns(allow)
    raws: list[RawCandidate] = []
    for line in lines:
        quote = _line_quote(line)
        line_date = _first_date(line) or header_date
        for icd in _ICD.finditer(line):
            # auch Codes außerhalb der Allow-Liste werden vorgeschlagen; der Prüfer lehnt sie ab
            raws.append(RawCandidate("Condition", icd.group(0), quote, date=line_date))
        for med in allow.medications:
            codes = [med.atc, *([med.sukl_code] if med.sukl_code else []), *med.aliases]
            if any(re.search(rf"(?<!\w){re.escape(c)}(?!\w)", line, re.IGNORECASE) for c in codes):
                raws.append(RawCandidate("MedicationStatement", med.atc, quote, date=line_date))
        for lab, pattern in labs:
            for match in pattern.finditer(line):
                unit = match["unit"].rstrip(".)")
                if norm_unit(unit) in lab.units:
                    raws.append(
                        RawCandidate(
                            "Observation",
                            lab.loinc,
                            quote,
                            value=match["value"],
                            unit=unit,
                            date=line_date,
                        )
                    )
        if len(raws) >= 4 * MAX_CANDIDATES:
            break
    return raws


# --- Sprachmodell ---------------------------------------------------------------------------


def build_prompt(text: str, allow: AllowLists) -> str:
    labs = "; ".join(f"{lab.loinc} = {lab.display}" for lab in allow.labs)
    return (
        "Du extrahierst strukturierte Angaben aus einem synthetischen medizinischen Dokument. "
        "Gib NUR JSON zurück, kein weiterer Text: "
        '{"candidates": [{"resourceType": "Condition|MedicationStatement|Observation", '
        '"code": "...", "value": null, "unit": null, "date": null, "quote": "..."}]}.\n'
        "Regeln: quote = WÖRTLICHES Zitat (höchstens "
        f"{MAX_QUOTE} Zeichen) aus dem Text, das die Angabe belegt. Condition: code = ICD-10-Code, "
        "der im Zitat steht. MedicationStatement: code = ATC-Code oder kód SÚKL des Arzneimittels, "
        "das im Zitat genannt ist. Observation (Laborwert): code = einer dieser LOINC-Codes: "
        f"{labs}; value = Zahl wie im Zitat, unit = Einheit wie im Zitat. date = Datum als "
        "YYYY-MM-DD, nur wenn es im Text steht, sonst null. Erfinde nichts, ergänze nichts aus "
        "anderem Wissen, überspringe Unsicheres.\n\n"
        f"TEXT:\n{text}\n"
    )


def parse_answer(answer: str) -> tuple[list[RawCandidate], list[str]]:
    """Antwort ⇒ Rohkandidaten (ungeprüft) und Fehlertexte; nie eine Exception."""
    try:
        data = json.loads(_FENCE.sub("", answer.strip()).strip())
    except ValueError:
        return [], ["answer_not_json"]
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        return [], ["answer_schema_invalid"]
    raws: list[RawCandidate] = []
    errors: list[str] = []
    for index, item in enumerate(data["candidates"][: 2 * MAX_CANDIDATES]):
        if not isinstance(item, dict):
            errors.append(f"candidate_{index}_invalid")
            continue
        kind, code, quote = item.get("resourceType"), item.get("code"), item.get("quote")
        if not (isinstance(kind, str) and isinstance(code, str) and isinstance(quote, str)):
            errors.append(f"candidate_{index}_invalid")
            continue

        def text_or_none(key: str, source: dict[str, Any] = item) -> str | None:
            value = source.get(key)
            if isinstance(value, bool) or value is None:
                return None
            return str(value) if isinstance(value, str | int | float) else None

        raws.append(
            RawCandidate(
                kind if kind in RESOURCE_TYPES else kind[:40],
                code.strip(),
                quote,
                value=text_or_none("value"),
                unit=text_or_none("unit"),
                date=text_or_none("date"),
            )
        )
    return raws, errors


def extract(text: str, allow: AllowLists, requested: str) -> Extraction:
    """Extraktor wählen: `requested == "openai"` ⇒ Sprachmodell, sonst/Fehler ⇒ `template`."""
    if requested == "openai":
        try:
            model = model_factory()
            answer = model.complete(build_prompt(text, allow))
            raws, errors = parse_answer(answer)
            if errors and not raws:
                raise ExtractionUnavailable(errors[0])
            return Extraction(raws, f"openai:{model.model}", "llm")
        except ExtractionUnavailable as error:
            logger.warning("document llm extraction unavailable (%s); using template", error)
            return Extraction(
                extract_template(text, allow), TEMPLATE_ID, "fallback", "llm_unavailable"
            )
        except Exception:  # jeder Modellfehler ⇒ deterministischer Rückfall
            logger.warning("document llm extraction failed; using template")
            return Extraction(extract_template(text, allow), TEMPLATE_ID, "fallback", "llm_failed")
    return Extraction(extract_template(text, allow), TEMPLATE_ID, "template")
