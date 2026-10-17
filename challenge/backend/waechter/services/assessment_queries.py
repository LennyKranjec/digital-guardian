"""Lesen von Arztaufnahmen im Vertragsformat (Schema `Assessment`)."""

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.persistence.models import User
from waechter.content import Content
from waechter.models import Assessment, AssessmentItem
from waechter.services.questionnaire import Selection, localize, select_items
from waechter.timeutil import iso_prague


def _terms(content: Content) -> dict[str, dict[str, Any]]:
    return {t["id"]: t for t in content.ctcae["terms"]}


def term_order(
    selection: Selection,
) -> tuple[list[str], dict[str, list[str]], dict[str, list[tuple[str, str]]]]:
    """CTCAE-Begriffe des Fragebogens (Subraum): Reihenfolge, Symptome und Attribute je Begriff.

    Einzige Quelle für „welche Begriffe kann die Ärztin aufnehmen“: die Aufnahmevorlage
    (`assessments.build_template`) und die Anzeige „Sledované příznaky“ nutzen sie gemeinsam.
    """
    symptoms: dict[str, list[str]] = defaultdict(list)
    attributes: dict[str, list[tuple[str, str]]] = defaultdict(list)
    order: list[str] = []
    for item, _ in selection.items:
        for term_id in item["ctcae_terms"]:
            if term_id not in symptoms:
                order.append(term_id)
            if item["symptom_key"] not in symptoms[term_id]:
                symptoms[term_id].append(item["symptom_key"])
            attributes[term_id].extend(
                (item["symptom_key"], a["attribute"]) for a in item["attributes"]
            )
    return order, symptoms, attributes


def tracked_terms(
    session: Session, patient_id: str, content: Content, lang: str
) -> list[dict[str, str]]:
    """Beobachtete Begriffe (CTCAE-Subraum) des aktuellen Fragebogens; ohne Therapie leer."""
    try:
        selection = select_items(session, patient_id, content)
    except ApiError:
        return []
    terms = _terms(content)
    order, _, _ = term_order(selection)
    return [
        {
            "ctcae_term_id": term_id,
            "term_en": terms[term_id]["term_en"],
            "label": localize(terms[term_id]["label"], lang)
            if terms[term_id].get("label")
            else terms[term_id]["term_en"],
        }
        for term_id in order
    ]


def assessment_view(session: Session, assessment: Assessment, content: Content) -> dict[str, Any]:
    terms = _terms(content)
    items = session.scalars(
        select(AssessmentItem)
        .where(AssessmentItem.assessment_id == assessment.id)
        .order_by(AssessmentItem.ctcae_term_id)
    ).all()
    user = session.get(User, assessment.assessed_by) if assessment.assessed_by else None
    return {
        "assessment_id": assessment.id,
        "fact_id": f"assess-{assessment.id}",
        "patient_id": assessment.patient_id,
        "assessed_at": iso_prague(assessment.assessed_at),
        "assessed_by": user.display_name if user is not None else "",
        "ctcae_version": content.ctcae["version"],
        "related_alert_ids": list(assessment.related_alert_ids),
        "items": [
            {
                "ctcae_term_id": i.ctcae_term_id,
                "term_en": terms.get(i.ctcae_term_id, {}).get("term_en", i.ctcae_term_id),
                "meddra_code": terms.get(i.ctcae_term_id, {}).get("meddra_code", ""),
                "grade": i.grade,
                "attribution": i.attribution or "unknown",
                "note": i.note,
            }
            for i in items
        ],
    }


def list_assessments(
    session: Session,
    patient_id: str,
    content: Content,
    lower: datetime | None = None,
    upper: datetime | None = None,
) -> list[dict[str, Any]]:
    """Aufnahmen einer Patientin, neueste zuerst; optional im Zeitfenster."""
    query = select(Assessment).where(Assessment.patient_id == patient_id)
    if lower is not None:
        query = query.where(Assessment.assessed_at >= lower)
    if upper is not None:
        query = query.where(Assessment.assessed_at <= upper)
    rows = session.scalars(query.order_by(Assessment.assessed_at.desc(), Assessment.id)).all()
    return [assessment_view(session, a, content) for a in rows]


def latest_grades(session: Session, patient_id: str) -> dict[str, int]:
    """Zuletzt aufgenommener Grad je CTCAE-Begriff (neueste Aufnahme gewinnt)."""
    rows = session.execute(
        select(AssessmentItem.ctcae_term_id, AssessmentItem.grade)
        .join(Assessment, Assessment.id == AssessmentItem.assessment_id)
        .where(Assessment.patient_id == patient_id)
        .order_by(Assessment.assessed_at, Assessment.id)
    )
    return {str(term): int(grade) for term, grade in rows}
