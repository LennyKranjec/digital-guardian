"""Deterministischer Prüfer der Vorschläge (T-22): wörtliches Zitat, bekanntes Symptom.

Ein Vorschlag des Adapters (`template` oder Sprachmodell) gilt nur, wenn
- er genau die Felder `symptom_key`, `quote` und optional `attribute`, `proposed_value` hat,
- `symptom_key` im Katalog der Symptome existiert und `attribute` (falls genannt) zu diesem
  Symptom gehört,
- `proposed_value` (falls genannt) eine ganze Zahl im Wertebereich des Attributs ist (nur mit
  Attribut; `presence` 0-1, sonst 0-4) und
- `quote` wörtlich im Freitext steht (Groß-/Kleinschreibung und Leerraum egal, Buchstaben exakt).

Alles andere wird verworfen und gezählt. Das Ergebnis ist nur ein Vorschlag; es verändert nie
Antworten, Stufen oder Meldungen: erst die Antwort der Patientin auf die Folgefrage zählt. Der
Vorschlagswert wird nur der Ärztin angezeigt. Zitat und Position stammen aus dem Originaltext.
"""

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from waechter.freetext.text import find_quote

MAX_SUGGESTIONS: Final = 8
MIN_QUOTE: Final = 2
MAX_QUOTE: Final = 200
_FIELDS: Final = {"symptom_key", "attribute", "proposed_value", "quote"}
#: Wertebereich je Attribut (wie `questionnaire.max_value`: presence 0-1, sonst 0-4)
PRESENCE_MAX: Final = 1
SCALE_MAX: Final = 4


@dataclass(frozen=True)
class Suggestion:
    symptom_key: str
    attribute: str | None
    quote: str
    start: int
    end: int
    proposed_value: int | None = None

    def body(self) -> dict[str, Any]:
        return {
            "symptom_key": self.symptom_key,
            "attribute": self.attribute,
            "proposed_value": self.proposed_value,
            "quote": self.quote,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True)
class Verified:
    suggestions: tuple[Suggestion, ...]
    rejected: int


def verify_suggestions(
    text: str, raw: Iterable[Any], catalog: Mapping[str, Collection[str]]
) -> Verified:
    """Prüft rohe Vorschläge gegen Freitext und Symptomkatalog (`symptom_key ⇒ Attribute`)."""
    accepted: list[Suggestion] = []
    rejected = 0
    seen: set[tuple[str, str | None, int]] = set()
    for item in raw:
        suggestion = _check(text, item, catalog)
        if suggestion is None:
            rejected += 1
            continue
        key = (suggestion.symptom_key, suggestion.attribute, suggestion.start)
        if key in seen:
            continue
        seen.add(key)
        accepted.append(suggestion)
    accepted.sort(key=lambda s: (s.start, s.symptom_key, s.attribute or ""))
    return Verified(
        tuple(accepted[:MAX_SUGGESTIONS]), rejected + max(0, len(accepted) - MAX_SUGGESTIONS)
    )


def _check(text: str, item: Any, catalog: Mapping[str, Collection[str]]) -> Suggestion | None:
    if not isinstance(item, dict) or not {"symptom_key", "quote"} <= set(item) <= _FIELDS:
        return None
    key, attribute, quote = item["symptom_key"], item.get("attribute"), item["quote"]
    if not isinstance(key, str) or key not in catalog:
        return None
    if attribute is not None and (not isinstance(attribute, str) or attribute not in catalog[key]):
        return None
    value = item.get("proposed_value")
    if value is not None:
        ceiling = PRESENCE_MAX if attribute == "presence" else SCALE_MAX
        if attribute is None or isinstance(value, bool) or not isinstance(value, int):
            return None
        if not 0 <= value <= ceiling:
            return None
    if not isinstance(quote, str) or not MIN_QUOTE <= len(quote.strip()) <= MAX_QUOTE:
        return None
    found = find_quote(text, quote)
    if found is None:
        return None
    start, end = found
    return Suggestion(key, attribute, text[start:end], start, end, value)
