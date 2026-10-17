"""Einschreibung einer neuen (synthetischen) Patientin mit Therapie durch das Personal (T-34).

Legt nur den Klinik-Datensatz an (`Patient` + `Therapy`, Felder wie `services/seed.py`), kein
Patientenkonto. Jede Zeile ist `synthetic=true`; das Pseudonym `SYN-NNNN` wird fortlaufend vergeben.
Das System schlägt weder Diagnose noch Therapie vor: Code und Regime wählt die Ärztin, geprüft wird
nur, ob sie zum Inhalt passen. Fragebogen und Triage-Profil ergeben sich danach aus Regime und
Diagnosegruppe über die bestehende Logik (`questionnaire.diagnosis_group_for`).

Idempotenz: gleiche `client_request_id` ⇒ dieselbe Patientin, `created=False` (Route antwortet 200).
Der Audit-Eintrag enthält keine personenbezogenen Inhalte (nur Regime-ID und Diagnosegruppe).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError, FieldError
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content
from waechter.models import Patient, Therapy
from waechter.services.patient_views import regimen_of
from waechter.services.questionnaire import diagnosis_group_for
from waechter.timeutil import from_prague_local, to_prague

PSEUDONYM_PREFIX = "SYN-"
_PSEUDONYM = re.compile(r"^SYN-(\d{4,})$")
#: ICD-10 (WHO): Buchstabe, zwei Ziffern, optional Punkt und 1 bis 4 Stellen (z. B. C50, C50.9)
ICD10_PATTERN = r"^[A-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$"
MAX_FUTURE_DAYS = 30
#: Platzhalter, wenn das Geburtsjahr nicht angegeben wird (rein synthetisch, kein echter Wert)
DEFAULT_BIRTH_YEAR = 1970
DEFAULT_SEX = "unknown"
_ATTEMPTS = 5


@dataclass(frozen=True)
class Enrollment:
    diagnosis_code: str | None
    regimen_id: str
    cycle_start: date
    language: str
    birth_year: int | None = None
    sex: str | None = None
    client_request_id: str | None = None


@dataclass(frozen=True)
class EnrollmentResult:
    patient_id: str
    pseudonym: str
    created: bool

    def body(self) -> dict[str, str]:
        return {"patient_id": self.patient_id, "pseudonym": self.pseudonym}


def _invalid(field: str, code: str, message: str) -> FieldError:
    return FieldError(field=field, code=code, message=message)


def _validate(clock: Clock, content: Content, data: Enrollment) -> list[FieldError]:
    errors: list[FieldError] = []
    if regimen_of(content, data.regimen_id) is None:
        errors.append(_invalid("regimen_id", "unknown_regimen", "Unknown regimen"))
    if data.diagnosis_code:
        code = data.diagnosis_code.strip().upper()
        if re.fullmatch(ICD10_PATTERN, code) is None:
            errors.append(_invalid("diagnosis_code", "invalid_format", "Not an ICD-10 code"))
        elif content.diagnoses is not None and diagnosis_group_for(content, code) is None:
            errors.append(
                _invalid("diagnosis_code", "unknown_diagnosis_group", "No matching group")
            )
    today = to_prague(clock.now()).date()
    if data.cycle_start > today + timedelta(days=MAX_FUTURE_DAYS):
        errors.append(_invalid("cycle_start", "too_far_in_future", "At most 30 days in the future"))
    if data.birth_year is not None and data.birth_year > today.year:
        errors.append(_invalid("birth_year", "in_future", "Birth year in the future"))
    return errors


def _existing(session: Session, request_id: str | None) -> EnrollmentResult | None:
    if request_id is None:
        return None
    row = session.execute(
        select(Patient.id, Patient.pseudonym).where(Patient.enrollment_request_id == request_id)
    ).first()
    return EnrollmentResult(row[0], row[1], created=False) if row is not None else None


def next_pseudonym(session: Session) -> str:
    """Nächstes freies `SYN-NNNN` (höchste vorhandene Nummer + 1, vierstellig aufgefüllt)."""
    numbers = [
        int(m.group(1))
        for p in session.scalars(
            select(Patient.pseudonym).where(Patient.pseudonym.like(f"{PSEUDONYM_PREFIX}%"))
        )
        if (m := _PSEUDONYM.match(p)) is not None
    ]
    return f"{PSEUDONYM_PREFIX}{max(numbers, default=0) + 1:04d}"


def enroll(
    session: Session, clock: Clock, principal: Principal, content: Content, data: Enrollment
) -> EnrollmentResult:
    known = _existing(session, data.client_request_id)
    if known is not None:
        return known
    errors = _validate(clock, content, data)
    if errors:
        raise ApiError(422, "validation_failed", "Request validation failed", errors)
    code = data.diagnosis_code.strip().upper() if data.diagnosis_code else None
    group = diagnosis_group_for(content, code)
    cycle_start = from_prague_local(datetime.combine(data.cycle_start, datetime.min.time()))
    for _ in range(_ATTEMPTS):
        pseudonym = next_pseudonym(session)
        patient = Patient(
            pseudonym=pseudonym,
            display_name=pseudonym,  # kein Name: nur das Pseudonym (ohne Personenbezug)
            birth_year=data.birth_year if data.birth_year is not None else DEFAULT_BIRTH_YEAR,
            sex=data.sex or DEFAULT_SEX,
            language=data.language,
            diagnosis_text=None,
            diagnosis_code=code,
            user_id=None,  # kein Patientenkonto (nur Klinik-Datensatz)
            enrollment_request_id=data.client_request_id,
            synthetic=True,
        )
        try:
            session.add(patient)
            session.flush()
        except IntegrityError:
            # gleichzeitige Einschreibung: Pseudonym oder Idempotenzschlüssel schon vergeben
            session.rollback()
            known = _existing(session, data.client_request_id)
            if known is not None:
                return known
            continue
        session.add(
            Therapy(
                patient_id=patient.id,
                regimen_id=data.regimen_id,
                cycle_start=cycle_start,
                synthetic=True,
            )
        )
        record_audit(
            session,
            clock,
            principal.actor,
            "enroll_patient",
            "patient",
            target_id=patient.id,
            subject_id=patient.id,
            details={
                "regimen_id": data.regimen_id,
                "diagnosis_group": group["id"] if group is not None else None,
            },
        )
        session.commit()
        return EnrollmentResult(patient.id, pseudonym, created=True)
    raise ApiError(409, "conflict", "Could not allocate a pseudonym")
