"""Extraktion von Nebenwirkungen aus dem SmPC-Abschnitt 4.8 durch ein Sprachmodell (nur Entwurf).

Das Modell bekommt ausschließlich den öffentlichen Abschnittstext (keine Patientendaten) und liefert
JSON im geschlossenen Schema `{"rows": [{original_term, frequency_class, evidence,
ctcae_v6_term}]}`. Jede Zeile wird danach vom deterministischen Prüfer (`verify`) gegen den
Quelltext geprüft; nicht belegte Zeilen werden verworfen und mit Grund gemeldet. Das Modell wird nur
über den Adapter `waechter.llm.adapters`
erreicht (`WAECHTER_LLM=openai`); ohne ihn gilt der
Lauf als nicht ausgeführt (`ExtractionUnavailable`); es gibt keinen stillen Ersatz.
"""

import hashlib
import json
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from waechter.knowledge.sources import SourceDocument
from waechter.knowledge.verify import (
    FREQUENCY_CLASSES,
    AeRow,
    Verdict,
    verify_extracted,
    with_status,
)

PROMPT_VERSION: Final = "ae-extract-v1"
MAX_ROWS: Final = 500
MAX_EVIDENCE: Final = 400
_FIELDS: Final = {"original_term", "frequency_class", "evidence", "ctcae_v6_term"}
_FENCE: Final = re.compile(r"^```[a-zA-Z]*\s*\n?|\n?```\s*$")


class ExtractionUnavailable(RuntimeError):
    """Kein Sprachmodell konfiguriert oder erreichbar ⇒ LLM-Lauf NOT RUN."""


class TextModel(Protocol):
    """Schmale Sicht auf ein Sprachmodell: Prompt rein, Text raus."""

    model: str

    def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class Rejection:
    original_term: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Extraction:
    """Ergebnis eines Laufs: geprüfte Zeilen (verified/unverified) und verworfene Kandidaten."""

    rows: tuple[AeRow, ...]
    rejected: tuple[Rejection, ...]
    model: str
    prompt_version: str
    prompt_sha256: str
    parse_errors: tuple[str, ...] = ()


def build_prompt(section_text: str, section_number: str) -> str:
    classes = ", ".join(f'"{c}"' for c in FREQUENCY_CLASSES)
    return (
        "Du extrahierst Nebenwirkungen aus dem Abschnitt "
        f"{section_number} einer Arzneimittel-Fachinformation (SmPC). "
        "Gib NUR JSON zurück, kein weiterer Text: "
        '{"rows": [{"original_term": "...", "frequency_class": "...", "evidence": "...", '
        '"ctcae_v6_term": null}]}.\n'
        "Regeln: original_term = der Begriff WÖRTLICH wie im Text (Sprache des Dokuments). "
        f"frequency_class = genau einer von {classes} (MedDRA-Konvention, englisch), passend zur "
        "Überschrift der Häufigkeit, unter der der Begriff steht. evidence = ein WÖRTLICHES Zitat "
        f"(höchstens {MAX_EVIDENCE} Zeichen) aus dem Text, das den Begriff enthält. "
        "ctcae_v6_term = null (die Zuordnung erfolgt nicht durch dich). Erfinde nichts, ergänze "
        "nichts aus anderem Wissen, überspringe nichts Unsicheres.\n\n"
        f"TEXT:\n{section_text}\n"
    )


def _strip_fence(text: str) -> str:
    return _FENCE.sub("", text.strip()).strip()


def parse_answer(text: str) -> tuple[list[AeRow], list[str]]:
    """Antwort ⇒ Kandidaten (noch ungeprüft) und Fehlertexte; nie eine Exception."""
    errors: list[str] = []
    try:
        data = json.loads(_strip_fence(text))
    except ValueError:
        return [], ["answer_not_json"]
    if not isinstance(data, dict) or set(data) != {"rows"} or not isinstance(data["rows"], list):
        return [], ["answer_schema_invalid"]
    candidates: list[AeRow] = []
    items: Sequence[Any] = data["rows"]
    if len(items) > MAX_ROWS:
        errors.append("too_many_rows")
        items = items[:MAX_ROWS]
    for index, item in enumerate(items):
        if (
            not isinstance(item, dict)
            or not set(item) <= _FIELDS
            or not ({"original_term", "frequency_class", "evidence"} <= set(item))
        ):
            errors.append(f"row_{index}_schema_invalid")
            continue
        values = {k: item.get(k) for k in _FIELDS}
        if not all(isinstance(values[k], str) for k in ("original_term", "frequency_class")):
            errors.append(f"row_{index}_types_invalid")
            continue
        if not isinstance(values["evidence"], str) or len(values["evidence"]) > MAX_EVIDENCE:
            errors.append(f"row_{index}_evidence_invalid")
            continue
        ctcae = values["ctcae_v6_term"]
        if ctcae is not None and not isinstance(ctcae, str):
            errors.append(f"row_{index}_types_invalid")
            continue
        candidates.append(
            AeRow(
                substance_id="",
                document="",
                document_url="",
                section="",
                retrieved="",
                original_term=str(values["original_term"]).strip(),
                frequency_class=str(values["frequency_class"]).strip().lower(),
                ctcae_v6_term=(ctcae or "").strip(),
                evidence=str(values["evidence"]).strip(),
            )
        )
    return candidates, errors


def run_extraction(
    document: SourceDocument,
    section_number: str,
    substance_id: str,
    model: TextModel,
    ctcae_terms: Collection[str],
) -> Extraction:
    """Modell fragen, Antwort parsen, jede Zeile prüfen; Duplikate (Begriff+Klasse) entfallen."""
    section = document.section(section_number)
    prompt = build_prompt(section.text, section_number)
    answer = model.complete(prompt)
    candidates, errors = parse_answer(answer)
    rows: list[AeRow] = []
    rejected: list[Rejection] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        row = AeRow(
            substance_id=substance_id,
            document=document.document_id,
            document_url=document.url,
            section=section_number,
            retrieved=document.retrieved,
            original_term=candidate.original_term,
            frequency_class=candidate.frequency_class,
            ctcae_v6_term=candidate.ctcae_v6_term,
            status="unverified",
            extraction=f"llm:{model.model}",
            evidence=candidate.evidence,
        )
        verdict: Verdict = verify_extracted(row, section.text, ctcae_terms)
        if verdict.status == "rejected":
            rejected.append(Rejection(row.original_term, verdict.reasons))
            continue
        key = (row.original_term.casefold(), row.frequency_class)
        if key in seen:
            continue
        seen.add(key)
        rows.append(with_status(row, verdict))
    return Extraction(
        rows=tuple(rows),
        rejected=tuple(rejected),
        model=model.model,
        prompt_version=PROMPT_VERSION,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        parse_errors=tuple(errors),
    )


class AdapterModel:
    """Brücke zum bestehenden Adapter (`WAECHTER_LLM=openai`); jeder Fehler ⇒ nicht verfügbar."""

    def __init__(self) -> None:
        from waechter.llm import adapters

        if adapters.requested_mode() != "openai":
            raise ExtractionUnavailable("WAECHTER_LLM is not 'openai': LLM extraction NOT RUN")
        try:
            self._adapter = adapters.select_adapter()
        except adapters.AdapterUnavailable as error:
            raise ExtractionUnavailable("openai adapter not configured") from error
        self.model = self._adapter.model or "unknown"

    def complete(self, prompt: str) -> str:
        from waechter.llm import adapters

        complete = getattr(self._adapter, "complete", None)
        if complete is None:
            raise ExtractionUnavailable("adapter cannot complete free text")
        try:
            return str(complete(prompt, {}).text)
        except adapters.AdapterUnavailable as error:
            raise ExtractionUnavailable(f"model call failed: {error}") from error
