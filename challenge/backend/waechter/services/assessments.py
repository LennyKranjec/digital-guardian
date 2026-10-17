"""Ärztliche CTCAE-Aufnahme: Vorlage (Subraum der getrackten Symptome) und idempotentes Speichern.

Die Ärztin nimmt nur Begriffe auf, die zu den Symptomen des aktuellen Fragebogens der Patientin
gehören (Subraum). Der PRO-Verlauf ist ein reiner Hinweis, nie eine Gradvorgabe; der Grad kommt
ausschließlich von der Ärztin (kein LLM, keine Berechnung). Gradtexte stammen unverändert aus
`ctcae.yaml` (Quelle `source`, CTCAE v6.0 des NCI).
"""

from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError, FieldError
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content
from waechter.models import Alert, Assessment, AssessmentItem, Patient
from waechter.services.assessment_queries import assessment_view, latest_grades, term_order
from waechter.services.patient_views import since_last_visit_rows
from waechter.services.questionnaire import localize, select_items

DEFAULT_ATTRIBUTION: Final = "unknown"


def build_template(
    session: Session, clock: Clock, patient: Patient, content: Content, lang: str
) -> dict[str, Any]:
    selection = select_items(session, patient.id, content)
    terms = {t["id"]: t for t in content.ctcae["terms"]}
    order, symptoms, attributes = term_order(selection)
    progress = {
        (r["symptom_key"], r["attribute"]): r
        for r in since_last_visit_rows(session, clock, content, patient, lang)
    }
    grades = latest_grades(session, patient.id)
    result_terms: list[dict[str, Any]] = []
    for term_id in order:
        term = terms[term_id]
        hint: dict[str, int | None] = {}
        for symptom_key, attribute in attributes[term_id]:
            row = progress.get((symptom_key, attribute))
            hint[f"{symptom_key}.{attribute}.max"] = row["max"] if row else None
            hint[f"{symptom_key}.{attribute}.last"] = row["last"] if row else None
        result_terms.append(
            {
                "ctcae_term_id": term_id,
                "term_en": term["term_en"],
                "label": localize(term["label"], lang) if term.get("label") else term["term_en"],
                "meddra_code": term["meddra_code"],
                "grades": dict(term["grades"]),
                "symptom_keys": symptoms[term_id],
                "pro_hint": hint,
                "last_grade": grades.get(term_id),
            }
        )
    return {
        "patient_id": patient.id,
        "ctcae_version": content.ctcae["version"],
        "source": dict(content.ctcae["source"]),
        "terms": result_terms,
    }


def _error(field: str, code: str, message: str) -> FieldError:
    return FieldError(field=field, code=code, message=message)


def validate(
    session: Session,
    patient: Patient,
    content: Content,
    items: list[dict[str, Any]],
    related_alert_ids: list[str],
) -> None:
    """G-13: Begriff im Subraum, Grad definiert (oder 0), kein Duplikat, nur eigene Meldungen."""
    allowed = {
        term_id
        for item, _ in select_items(session, patient.id, content).items
        for term_id in item["ctcae_terms"]
    }
    terms = {t["id"]: t for t in content.ctcae["terms"]}
    errors: list[FieldError] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        term_id = item["ctcae_term_id"]
        field = f"items.{index}"
        if term_id not in allowed:
            errors.append(_error(f"{field}.ctcae_term_id", "unknown_term", "Term not in subspace"))
            continue
        if term_id in seen:
            errors.append(_error(f"{field}.ctcae_term_id", "duplicate_term", "Duplicate term"))
        seen.add(term_id)
        defined = {int(g) for g in terms[term_id]["grades"]}
        if item["grade"] != 0 and item["grade"] not in defined:
            errors.append(_error(f"{field}.grade", "grade_not_defined", "Grade not defined"))
    if related_alert_ids:
        own = set(
            session.scalars(
                select(Alert.id).where(
                    Alert.patient_id == patient.id, Alert.id.in_(related_alert_ids)
                )
            )
        )
        for index, alert_id in enumerate(related_alert_ids):
            if alert_id not in own:
                errors.append(
                    _error(
                        f"related_alert_ids.{index}",
                        "foreign_alert",
                        "Alert does not belong to this patient",
                    )
                )
    if len(set(related_alert_ids)) != len(related_alert_ids):
        errors.append(_error("related_alert_ids", "duplicate_alert", "Duplicate alert"))
    if errors:
        raise ApiError(422, "validation_failed", "Invalid assessment", errors)


def _signature(items: list[dict[str, Any]], related: list[str]) -> tuple[Any, ...]:
    return (
        sorted(
            (
                i["ctcae_term_id"],
                i["grade"],
                i.get("attribution") or DEFAULT_ATTRIBUTION,
                i.get("note") or "",
            )
            for i in items
        ),
        sorted(related),
    )


def _stored_signature(session: Session, assessment: Assessment) -> tuple[Any, ...]:
    rows = session.scalars(
        select(AssessmentItem).where(AssessmentItem.assessment_id == assessment.id)
    ).all()
    return _signature(
        [
            {
                "ctcae_term_id": r.ctcae_term_id,
                "grade": r.grade,
                "attribution": r.attribution,
                "note": r.note,
            }
            for r in rows
        ],
        list(assessment.related_alert_ids),
    )


def _replay(
    session: Session,
    patient: Patient,
    csid: str,
    content: Content,
    items: list[dict[str, Any]],
    related: list[str],
) -> dict[str, Any] | None:
    existing = session.scalar(
        select(Assessment).where(
            Assessment.patient_id == patient.id, Assessment.client_submission_id == csid
        )
    )
    if existing is None:
        return None
    if _stored_signature(session, existing) != _signature(items, related):
        raise ApiError(409, "idempotency_conflict", "Submission id already used with other content")
    return assessment_view(session, existing, content)


def create(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient: Patient,
    content: Content,
    csid: str,
    items: list[dict[str, Any]],
    related_alert_ids: list[str],
) -> tuple[dict[str, Any], bool]:
    """Speichert die Aufnahme; `(Ansicht, neu angelegt)`. Gleiche ID + gleicher Inhalt ⇒ Replay."""
    replay = _replay(session, patient, csid, content, items, related_alert_ids)
    if replay is not None:
        return replay, False
    validate(session, patient, content, items, related_alert_ids)
    assessment = Assessment(
        patient_id=patient.id,
        assessed_at=clock.now(),
        assessed_by=principal.user_id,
        client_submission_id=csid,
        related_alert_ids=list(related_alert_ids),
        synthetic=True,
    )
    try:
        session.add(assessment)
        session.flush()
    except IntegrityError:
        session.rollback()
        replay = _replay(session, patient, csid, content, items, related_alert_ids)
        if replay is None:
            raise
        return replay, False
    session.add_all(
        AssessmentItem(
            assessment_id=assessment.id,
            ctcae_term_id=i["ctcae_term_id"],
            grade=i["grade"],
            attribution=i.get("attribution") or DEFAULT_ATTRIBUTION,
            note=i.get("note"),
        )
        for i in items
    )
    session.flush()
    record_audit(
        session,
        clock,
        principal.actor,
        "create_assessment",
        "assessment",
        target_id=assessment.id,
        subject_id=patient.id,
        details={"items": len(items), "related_alerts": len(related_alert_ids)},
    )
    session.commit()
    return assessment_view(session, assessment, content), True
