"""Kandidaten ⇒ FHIR-R4-Ressourcen mit Provenance (rein, deterministisch).

Entwurf (`confirmed=False`): Condition `unconfirmed`, Observation `preliminary`. Bestätigt
(ärztlicher Klick): Condition `confirmed`, Observation `final`. MedicationStatement bleibt
`unknown`, weil ein Dokument nur erwähnt, nicht bestätigt, dass das Mittel eingenommen wird. Jede
Ressource trägt
Bestätigung zusätzlich die bestätigende Rolle; Entität = Dokument-Hash und Zitat.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from waechter.documents.allowlists import LOINC_SYSTEM, UCUM_SYSTEM
from waechter.documents.candidates import Candidate
from waechter.fhir import builder as fhir

SOURCE_SYSTEM: Final = "urn:waechter:source"
REVIEW_SYSTEM: Final = "urn:waechter:review"
DOCUMENT_HASH_SYSTEM: Final = "urn:waechter:document-sha256"
PARTICIPANT: Final = "http://terminology.hl7.org/CodeSystem/provenance-participant-type"
CONDITION_VERIFICATION: Final = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
_UNSAFE: Final = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class DocumentInfo:
    document_id: str
    patient_id: str
    sha256: str
    filename: str
    extractor: str
    created_at: str  # ISO 8601 mit Zeitzone


@dataclass(frozen=True)
class Review:
    """Prüfstand eines Kandidaten für die FHIR-Darstellung."""

    confirmed: bool
    decided_at: str | None = None
    decided_role: str | None = None


def safe_filename(name: str) -> str:
    return _UNSAFE.sub("_", name.strip())[:80] or "document"


def _internal_id(info: DocumentInfo, candidate: Candidate) -> str:
    return f"doc:{info.document_id}:{candidate.candidate_id}"


def _meta(review: Review) -> dict[str, Any]:
    return {
        "tag": [
            fhir.SYNTHETIC_TAG,
            {"system": SOURCE_SYSTEM, "code": "document-extraction"},
            {"system": REVIEW_SYSTEM, "code": "confirmed" if review.confirmed else "unconfirmed"},
        ]
    }


def _coding(candidate: Candidate) -> list[dict[str, str]]:
    if candidate.resource_type == "Condition":
        return [{"system": fhir.ICD10_SYSTEM, "code": candidate.code}]
    if candidate.resource_type == "MedicationStatement":
        coding = [{"system": fhir.ATC_SYSTEM, "code": candidate.code}]
        if candidate.sukl_code:
            coding.append({"system": fhir.SUKL_SYSTEM, "code": candidate.sukl_code})
        return coding
    return [{"system": LOINC_SYSTEM, "code": candidate.code}]


def _body(info: DocumentInfo, candidate: Candidate, review: Review) -> dict[str, Any]:
    subject = fhir.ref("Patient", info.patient_id)
    concept: dict[str, Any] = {"coding": _coding(candidate), "text": candidate.display}
    body: dict[str, Any] = {"meta": _meta(review), "subject": subject}
    if candidate.resource_type == "Condition":
        concept["text"] = candidate.quote
        body["verificationStatus"] = {
            "coding": [
                {
                    "system": CONDITION_VERIFICATION,
                    "code": "confirmed" if review.confirmed else "unconfirmed",
                }
            ]
        }
        body["code"] = concept
        body["recordedDate"] = candidate.date
    elif candidate.resource_type == "MedicationStatement":
        body["status"] = "unknown"
        body["medicationCodeableConcept"] = concept
        body["dateAsserted"] = candidate.date
    else:
        body["status"] = "final" if review.confirmed else "preliminary"
        body["category"] = [
            {
                "coding": [
                    {"system": fhir.OBSERVATION_CATEGORY, "code": "laboratory"},
                ]
            }
        ]
        body["code"] = concept
        body["effectiveDateTime"] = candidate.date
        if candidate.value is not None:
            body["valueQuantity"] = {
                "value": float(Decimal(candidate.value)),
                "unit": candidate.unit,
                "system": UCUM_SYSTEM,
                "code": candidate.ucum,
            }
    return body


def _narrative(candidate: Candidate) -> str:
    if candidate.resource_type == "Observation":
        return f"{candidate.display}: {candidate.value} {candidate.unit} (from document)"
    return f"{candidate.display} (from document)"


def _provenance(info: DocumentInfo, candidate: Candidate, review: Review) -> dict[str, Any]:
    internal = _internal_id(info, candidate)
    agents: list[dict[str, Any]] = [
        {
            "type": {"coding": [{"system": PARTICIPANT, "code": "author"}]},
            "who": {"type": "Device", "display": info.extractor},
        }
    ]
    if review.confirmed:
        agents.append(
            {
                "type": {"coding": [{"system": PARTICIPANT, "code": "verifier"}]},
                "who": {"display": review.decided_role or "clinician"},
            }
        )
    return fhir.make_resource(
        "Provenance",
        internal,
        {
            "meta": _meta(review),
            "target": [fhir.ref(candidate.resource_type, internal)],
            "recorded": review.decided_at
            if review.confirmed and review.decided_at
            else info.created_at,
            "agent": agents,
            "entity": [
                {
                    "role": "source",
                    "what": {
                        "identifier": {"system": DOCUMENT_HASH_SYSTEM, "value": info.sha256},
                        "display": safe_filename(info.filename),
                    },
                },
                {"role": "quotation", "what": {"display": candidate.quote}},
            ],
        },
        f"Provenance of {candidate.resource_type} extracted from a document ({info.extractor})",
    )


def resources_for(info: DocumentInfo, candidate: Candidate, review: Review) -> list[dict[str, Any]]:
    """Ressource und Provenance eines Kandidaten (Reihenfolge: Ressource, Provenance)."""
    resource = fhir.make_resource(
        candidate.resource_type,
        _internal_id(info, candidate),
        fhir.prune(_body(info, candidate, review)),
        _narrative(candidate),
    )
    return [resource, _provenance(info, candidate, review)]
