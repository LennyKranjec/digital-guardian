"""Subjekt-Auflösung: Konto → `patient_id` (nur Patient:innen-Konten haben ein Subjekt)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.access import not_found
from app.services.auth import Principal
from waechter.models import Patient


def resolve_patient_id(session: Session, user_id: str) -> str | None:
    return session.scalar(select(Patient.id).where(Patient.user_id == user_id))


def own_patient(session: Session, principal: Principal) -> Patient:
    """Die Patientin des angemeldeten Kontos; ohne Zuordnung 404 (nie fremde Daten)."""
    patient = session.get(Patient, principal.subject_id) if principal.subject_id else None
    if patient is None:
        raise not_found()
    return patient
