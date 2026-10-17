"""HTTP-Schicht der Dokumentenpipeline (T-21, dünn): Autorisierung, Parameter, Aufruf des Services.

Nur Personal (Ärztin/Admin); Patient:innen bekommen 403, Anonyme 401, fremde Kennung 404.
"""

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import require_roles
from app.core.clock import ClockDep
from app.core.deps import SessionDep
from app.services.auth import Principal
from waechter.constants import ROLE_ADMIN, ROLE_CLINICIAN
from waechter.services import config as config_service
from waechter.services import documents as documents_service

router = APIRouter(prefix="/waechter", tags=["waechter-documents"])

StaffDep = Annotated[Principal, Depends(require_roles(ROLE_CLINICIAN, ROLE_ADMIN))]


class DocumentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=200)
    #: Dokumenttext (UTF-8); die Größe (≤ 200 kB) prüft der Service (413)
    text: str = Field(max_length=documents_service.MAX_BYTES * 2)


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["confirm", "discard"]


@router.post("/patients/{patient_id}/documents", status_code=201)
def upload_document(
    patient_id: str,
    body: DocumentBody,
    response: Response,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, Any]:
    content = config_service.require_content()
    result, created = documents_service.upload(
        session, clock, principal, content, patient_id, body.filename, body.text
    )
    if not created:
        response.status_code = 200
    return result


@router.get("/patients/{patient_id}/documents")
def list_documents(patient_id: str, _: StaffDep, session: SessionDep) -> list[dict[str, Any]]:
    return documents_service.list_documents(session, patient_id)


@router.get("/patients/{patient_id}/documents/{document_id}")
def get_document(
    patient_id: str, document_id: str, _: StaffDep, session: SessionDep
) -> dict[str, Any]:
    return documents_service.view(documents_service.get_document(session, patient_id, document_id))


@router.get("/patients/{patient_id}/documents/{document_id}/bundle")
def get_document_bundle(
    patient_id: str, document_id: str, _: StaffDep, session: SessionDep, clock: ClockDep
) -> Response:
    """Entwurfs-Bundle (FHIR R4, `collection`); Content-Type `application/fhir+json`."""
    bundle = documents_service.draft_bundle(session, clock, patient_id, document_id)
    return Response(
        content=json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        media_type="application/fhir+json",
    )


@router.post("/patients/{patient_id}/documents/{document_id}/candidates/{candidate_id}")
def decide_candidate(
    patient_id: str,
    document_id: str,
    candidate_id: str,
    body: DecisionBody,
    principal: StaffDep,
    session: SessionDep,
    clock: ClockDep,
) -> dict[str, Any]:
    """Eine Ressource bestätigen (⇒ Patientenexport) oder verwerfen; zweite Entscheidung ⇒ 409."""
    return documents_service.decide(
        session, clock, principal, patient_id, document_id, candidate_id, body.decision
    )
