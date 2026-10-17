"""Datentypen der Pipeline: ungeprüfter Rohkandidat ⇒ geprüfter Kandidat."""

import hashlib
from dataclasses import dataclass
from typing import Any, Final

RESOURCE_TYPES: Final = ("Condition", "MedicationStatement", "Observation")
MAX_QUOTE: Final = 400
MAX_CANDIDATES: Final = 200


@dataclass(frozen=True)
class RawCandidate:
    """Was ein Extraktor behauptet (Vorschlag, nicht belegt)."""

    resource_type: str
    code: str
    quote: str
    value: str | None = None
    unit: str | None = None
    date: str | None = None


@dataclass(frozen=True)
class Candidate:
    """Vom Prüfer zugelassen: Zitat wörtlich, Code in der Allow-Liste, Angaben belegt."""

    resource_type: str
    code: str
    display: str
    quote: str
    value: str | None = None
    unit: str | None = None
    ucum: str | None = None
    date: str | None = None
    sukl_code: str | None = None

    @property
    def candidate_id(self) -> str:
        key = "|".join(
            (
                self.resource_type,
                self.code,
                self.value or "",
                self.unit or "",
                self.date or "",
                self.quote,
            )
        )
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "resource_type": self.resource_type,
            "code": self.code,
            "display": self.display,
            "quote": self.quote,
            "value": self.value,
            "unit": self.unit,
            "ucum": self.ucum,
            "date": self.date,
            "sukl_code": self.sukl_code,
        }

    @staticmethod
    def from_json(data: dict[str, Any]) -> "Candidate":
        return Candidate(
            resource_type=str(data["resource_type"]),
            code=str(data["code"]),
            display=str(data["display"]),
            quote=str(data["quote"]),
            value=data.get("value"),
            unit=data.get("unit"),
            ucum=data.get("ucum"),
            date=data.get("date"),
            sukl_code=data.get("sukl_code"),
        )


@dataclass(frozen=True)
class Rejected:
    resource_type: str
    code: str
    quote: str
    reasons: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "code": self.code,
            "quote": self.quote[:MAX_QUOTE],
            "reasons": list(self.reasons),
        }
