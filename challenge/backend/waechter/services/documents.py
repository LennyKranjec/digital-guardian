"""Dokumente ⇒ FHIR (T-21): hochladen, Kandidaten prüfen, ärztlich bestätigen, in den Export geben.

Geschäftslogik der Dokumentenpipeline; die Route (`waechter.documents_api`) bleibt dünn. Nur
synthetische Patientinnen (sonst 409 `not_synthetic`). Der Dokumenttext wird nicht gespeichert, nur
Hash, Dateiname, geprüfte Kandidaten (mit wörtlichem Zitat) und verworfene Kandidaten. Was nicht
ausdrücklich bestätigt ist, steht nie im Patientenexport.
"""

import hashlib
from typing import Any, Final

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError
from app.services.access import not_found
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content
from waechter.documents import extractors
from waechter.documents.allowlists import LOINC_SYSTEM, from_content
from waechter.documents.candidates import Candidate, Rejected
from waechter.documents.fhir import DocumentInfo, Review, resources_for
from waechter.documents.verify import check_all
from waechter.fhir import builder as fhir
from waechter.llm import adapters
from waechter.models import Document, Patient
from waechter.services.patient_views import get_patient
from waechter.timeutil import iso_prague

MAX_BYTES: Final = 200_000
MAX_REJECTED_SHOWN: Final = 50
ALLOWED_SUFFIXES: Final = (".txt", ".md", ".markdown", ".csv")
STATE_DRAFT: Final = "draft"
STATE_CONFIRMED: Final = "confirmed"
STATE_DISCARDED: Final = "discarded"
DECISIONS: Final = {"confirm": STATE_CONFIRMED, "discard": STATE_DISCARDED}
_SYSTEMS: Final = {
    "Condition": fhir.ICD10_SYSTEM,
    "MedicationStatement": fhir.ATC_SYSTEM,
    "Observation": LOINC_SYSTEM,
}
MAX_ATTEMPTS: Final = 3


def _clean_filename(name: str) -> str:
    return "".join(c for c in name.strip() if c.isprintable() and c not in "\\/")[:120]


def _entry_view(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": entry["candidate_id"],
        "resource_type": entry["resource_type"],
        "code": entry["code"],
        "system": _SYSTEMS[entry["resource_type"]],
        "display": entry["display"],
        "value": entry.get("value"),
        "unit": entry.get("unit"),
        "date": entry.get("date"),
        "sukl_code": entry.get("sukl_code"),
        "quote": entry["quote"],
        "state": entry["state"],
        "decided_at": entry.get("decided_at"),
    }


def view(row: Document) -> dict[str, Any]:
    states = [e["state"] for e in row.candidates_json]
    return {
        "document_id": row.id,
        "patient_id": row.patient_id,
        "filename": row.filename,
        "sha256": row.sha256,
        "size_bytes": row.size_bytes,
        "created_at": iso_prague(row.created_at),
        "version": row.version,
        "extractor": {
            "id": row.extractor,
            "mode": row.extractor_mode,
            "fallback_reason": row.fallback_reason,
        },
        "candidates": [_entry_view(e) for e in row.candidates_json],
        "rejected": row.rejected_json[:MAX_REJECTED_SHOWN],
        "counts": {
            "draft": states.count(STATE_DRAFT),
            "confirmed": states.count(STATE_CONFIRMED),
            "discarded": states.count(STATE_DISCARDED),
            "rejected": len(row.rejected_json),
        },
    }


def _synthetic_patient(session: Session, patient_id: str) -> Patient:
    patient = get_patient(session, patient_id)
    if not patient.synthetic:
        raise ApiError(409, "not_synthetic", "Only synthetic patients may receive documents")
    return patient


def _find(session: Session, patient_id: str, sha256: str) -> Document | None:
    return session.scalars(
        select(Document).where(Document.patient_id == patient_id, Document.sha256 == sha256)
    ).first()


def _check_input(filename: str, text: str) -> bytes:
    if not filename.lower().endswith(ALLOWED_SUFFIXES):
        if filename.lower().endswith(".pdf"):
            raise ApiError(
                415, "pdf_not_supported", "PDF is not supported; upload text, Markdown or CSV"
            )
        raise ApiError(415, "unsupported_format", "Only .txt, .md and .csv documents are accepted")
    raw = text.encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ApiError(413, "document_too_large", "Document exceeds 200 kB")
    if not text.strip():
        raise ApiError(422, "empty_document", "Document is empty")
    if "\x00" in text:
        raise ApiError(422, "binary_content", "Document contains binary data")
    return raw


def upload(
    session: Session,
    clock: Clock,
    principal: Principal,
    content: Content,
    patient_id: str,
    filename: str,
    text: str,
) -> tuple[dict[str, Any], bool]:
    """Dokument prüfen, extrahieren, Kandidaten prüfen, speichern (gleicher Hash: bekannt)."""
    patient = _synthetic_patient(session, patient_id)
    raw = _check_input(filename, text)
    digest = hashlib.sha256(raw).hexdigest()
    existing = _find(session, patient.id, digest)
    if existing is not None:
        return view(existing), False
    allow = from_content(content)
    extraction = extractors.extract(text, allow, adapters.requested_mode())
    accepted, rejected = check_all(extraction.raws, text, allow)
    row = Document(
        patient_id=patient.id,
        sha256=digest,
        filename=_clean_filename(filename) or "document",
        size_bytes=len(raw),
        extractor=extraction.extractor,
        extractor_mode=extraction.mode,
        fallback_reason=extraction.fallback_reason,
        candidates_json=[{**c.to_json(), "state": STATE_DRAFT} for c in accepted],
        rejected_json=[r.to_json() for r in _shown(rejected)],
        version=1,
        uploaded_by=principal.user_id,
        created_at=clock.now(),
    )
    session.add(row)
    record_audit(
        session,
        clock,
        principal.actor,
        "upload_document",
        "document",
        target_id=row.id,
        subject_id=patient.id,
        details={"candidates": len(accepted), "rejected": len(rejected), "mode": extraction.mode},
    )
    try:
        session.commit()
    except IntegrityError:  # paralleler Upload desselben Dokuments war schneller
        session.rollback()
        winner = _find(session, patient.id, digest)
        if winner is None:
            raise
        return view(winner), False
    return view(row), True


def _shown(rejected: list[Rejected]) -> list[Rejected]:
    return rejected[:MAX_REJECTED_SHOWN]


def list_documents(session: Session, patient_id: str) -> list[dict[str, Any]]:
    patient = get_patient(session, patient_id)
    rows = session.scalars(
        select(Document)
        .where(Document.patient_id == patient.id)
        .order_by(Document.created_at.desc(), Document.id)
    ).all()
    return [view(r) for r in rows]


def get_document(session: Session, patient_id: str, document_id: str) -> Document:
    """Dokument dieser Patientin; fremde oder unbekannte Kennung ⇒ 404."""
    patient = get_patient(session, patient_id)
    row = session.get(Document, document_id)
    if row is None or row.patient_id != patient.id:
        raise not_found()
    return row


def decide(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient_id: str,
    document_id: str,
    candidate_id: str,
    decision: str,
) -> dict[str, Any]:
    """Kandidat bestätigen oder verwerfen; zweite Entscheidung ⇒ 409 (bedingtes Update)."""
    new_state = DECISIONS[decision]
    for _ in range(MAX_ATTEMPTS):
        row = get_document(session, patient_id, document_id)
        entries = [dict(e) for e in row.candidates_json]
        index = next((i for i, e in enumerate(entries) if e["candidate_id"] == candidate_id), None)
        if index is None:
            raise not_found()
        if entries[index]["state"] != STATE_DRAFT:
            raise ApiError(
                409, "already_decided", "This resource was already confirmed or discarded"
            )
        entries[index] = {
            **entries[index],
            "state": new_state,
            "decided_at": iso_prague(clock.now()),
            "decided_role": principal.role,
        }
        result = session.execute(
            update(Document)
            .where(Document.id == row.id, Document.version == row.version)
            .values(candidates_json=entries, version=row.version + 1)
        )
        if result.rowcount == 1:  # type: ignore[attr-defined]
            record_audit(
                session,
                clock,
                principal.actor,
                f"{decision}_document_resource",
                "document",
                target_id=row.id,
                subject_id=row.patient_id,
                details={"resource_type": entries[index]["resource_type"]},
            )
            session.commit()
            session.refresh(row)
            return view(row)
        session.rollback()  # eine parallele Entscheidung war schneller: neu lesen und prüfen
    raise ApiError(409, "conflict", "The document was changed concurrently; reload and retry")


def _info(row: Document) -> DocumentInfo:
    return DocumentInfo(
        document_id=row.id,
        patient_id=row.patient_id,
        sha256=row.sha256,
        filename=row.filename,
        extractor=row.extractor,
        created_at=iso_prague(row.created_at),
    )


def _review(entry: dict[str, Any]) -> Review:
    confirmed = entry["state"] == STATE_CONFIRMED
    return Review(
        confirmed, entry.get("decided_at") if confirmed else None, entry.get("decided_role")
    )


def confirmed_resources(session: Session, patient_id: str) -> list[dict[str, Any]]:
    """Nur ärztlich bestätigte Ressourcen (mit Provenance) für den Patientenexport."""
    rows = session.scalars(
        select(Document)
        .where(Document.patient_id == patient_id)
        .order_by(Document.created_at, Document.id)
    ).all()
    resources: list[dict[str, Any]] = []
    for row in rows:
        info = _info(row)
        for entry in row.candidates_json:
            if entry["state"] == STATE_CONFIRMED:
                resources.extend(resources_for(info, Candidate.from_json(entry), _review(entry)))
    return resources


def draft_bundle(
    session: Session, clock: Clock, patient_id: str, document_id: str
) -> dict[str, Any]:
    """Entwurfs-Bundle (collection): nicht verworfene Kandidaten mit ihrem Prüfstand."""
    row = get_document(session, patient_id, document_id)
    patient = get_patient(session, row.patient_id)
    info = _info(row)
    resources: list[dict[str, Any]] = [
        fhir.patient(
            fhir.ExportData(
                patient_id=patient.id,
                pseudonym=patient.pseudonym,
                sex=patient.sex,
                birth_year=patient.birth_year,
                language=patient.language,
                therapy_id=None,
                regimen_label="",
                cycle_start=None,
                drugs=[],
                generated_at=iso_prague(clock.now()),
            )
        )
    ]
    for entry in row.candidates_json:
        if entry["state"] != STATE_DISCARDED:
            resources.extend(resources_for(info, Candidate.from_json(entry), _review(entry)))
    return _collection(row, patient, resources, iso_prague(row.created_at))


def _collection(
    row: Document, patient: Patient, resources: list[dict[str, Any]], timestamp: str
) -> dict[str, Any]:
    return {
        "resourceType": "Bundle",
        "id": fhir.uid("Bundle", f"doc:{row.id}"),
        "meta": {"tag": [fhir.SYNTHETIC_TAG]},
        "identifier": {"system": "urn:waechter:bundle", "value": f"{patient.pseudonym}:{row.id}"},
        "type": "collection",
        "timestamp": timestamp,
        "entry": [{"fullUrl": f"urn:uuid:{r['id']}", "resource": r} for r in resources],
    }
