"""Belege per Klick: `GET /patients/{id}/facts/{factId}`.

Präfixe: resp-, obs-, alert-, visit-, ther-, assess-, ft- (Freitext, T-22).

Jede in `explanation.evidence`, `series.points.fact_id` und `therapy` genannte Fakt-ID ist hier
auflösbar. Ein Beleg einer anderen Patientin oder eine unbekannte/ungültige ID ergibt 404.
`assess-` (ärztliche CTCAE-Aufnahme) kommt mit T-06 dazu.
"""

import re
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.access import not_found
from waechter.content import Content
from waechter.models import Alert, Answer, Assessment, FreeText, Response, Therapy, Visit
from waechter.services.alert_queries import alert_view
from waechter.services.alerts import headline
from waechter.services.assessment_queries import assessment_view
from waechter.services.patient_views import get_patient, regimen_of, symptom_label
from waechter.services.questionnaire import localize
from waechter.timeutil import iso_prague

FACT_ID: Final = re.compile(r"^(resp|obs|alert|visit|assess|ther|ft)-([A-Za-z0-9-]+)$")

_RESPONSE: Final = {
    "cs": "Odpověď pacienta {at}",
    "en": "Patient response {at}",
    "de": "Antwort der Patientin {at}",
}
_ASSESSMENT: Final = {
    "cs": "Lékařské hodnocení CTCAE ({count} pojmů)",
    "en": "Clinician CTCAE assessment ({count} terms)",
    "de": "Ärztliche CTCAE-Bewertung ({count} Begriffe)",
}
_FREE_TEXT: Final = {
    "cs": "Volný text pacientky {at}",
    "en": "Patient free text {at}",
    "de": "Freitext der Patientin {at}",
}
_SKIPPED: Final = {"cs": "přeskočeno", "en": "skipped", "de": "übersprungen"}
_VISIT: Final = {
    "past": {"cs": "Návštěva (proběhla)", "en": "Visit (done)", "de": "Besuch (erfolgt)"},
    "planned": {
        "cs": "Návštěva (plánovaná)",
        "en": "Visit (planned)",
        "de": "Besuch (geplant)",
    },
}


def _t(table: dict[str, str], lang: str) -> str:
    return table.get(lang) or table["en"]


def get_fact(
    session: Session, patient_id: str, fact_id: str, content: Content, lang: str
) -> dict[str, Any]:
    patient = get_patient(session, patient_id)
    match = FACT_ID.match(fact_id)
    if match is None:
        raise not_found()
    prefix, ident = match.groups()
    if prefix == "resp":
        return _response_fact(session, patient.id, ident, lang)
    if prefix == "obs":
        return _observation_fact(session, patient.id, ident, content, lang)
    if prefix == "alert":
        return _alert_fact(session, patient.id, ident, content, lang)
    if prefix == "visit":
        return _visit_fact(session, patient.id, ident, lang)
    if prefix == "ther":
        return _therapy_fact(session, patient.id, ident, content, lang)
    if prefix == "ft":
        return _free_text_fact(session, patient.id, ident, content, lang)
    return _assessment_fact(session, patient.id, ident, content, lang)


def _free_text_fact(
    session: Session, patient_id: str, ident: str, content: Content, lang: str
) -> dict[str, Any]:
    row = _own(session.get(FreeText, ident), patient_id)
    return {
        "fact_id": f"ft-{row.id}",
        "kind": "free_text",
        "at": iso_prague(row.created_at),
        "label": _t(_FREE_TEXT, lang).format(at=iso_prague(row.created_at)),
        "data": {
            "free_text_id": row.id,
            "response_fact_id": f"resp-{row.response_id}",
            "text": row.text,
            "suggestions": [
                {
                    "symptom_key": s["symptom_key"],
                    "label": symptom_label(content, s["symptom_key"], lang),
                    "quote": s["quote"],
                }
                for s in row.suggestions_json
            ],
            "mode": row.mapper_mode,
        },
    }


def _own[T](row: T | None, patient_id: str) -> T:
    if row is None or getattr(row, "patient_id", None) != patient_id:
        raise not_found()
    return row


def _response_fact(session: Session, patient_id: str, ident: str, lang: str) -> dict[str, Any]:
    response = _own(session.get(Response, ident), patient_id)
    answers = session.scalars(
        select(Answer)
        .where(Answer.response_id == response.id)
        .order_by(Answer.symptom_key, Answer.attribute)
    ).all()
    return {
        "fact_id": f"resp-{response.id}",
        "kind": "response",
        "at": iso_prague(response.recorded_at),
        "label": _t(_RESPONSE, lang).format(at=iso_prague(response.recorded_at)),
        "data": {
            "response_id": response.id,
            "channel": response.channel,
            "entered_by": response.entered_by,
            "questionnaire_id": response.questionnaire_id,
            "answers": [
                {
                    "symptom_key": a.symptom_key,
                    "attribute": a.attribute,
                    "value": a.value,
                    "fact_id": f"obs-{a.id}",
                }
                for a in answers
            ],
        },
    }


def _observation_fact(
    session: Session, patient_id: str, ident: str, content: Content, lang: str
) -> dict[str, Any]:
    answer = session.get(Answer, ident)
    if answer is None:
        raise not_found()
    response = _own(session.get(Response, answer.response_id), patient_id)
    shown = _t(_SKIPPED, lang) if answer.value is None else str(answer.value)
    label = symptom_label(content, answer.symptom_key, lang)
    return {
        "fact_id": f"obs-{answer.id}",
        "kind": "observation",
        "at": iso_prague(response.recorded_at),
        "label": f"{label} ({answer.attribute}): {shown}",
        "data": {
            "symptom_key": answer.symptom_key,
            "attribute": answer.attribute,
            "value": answer.value,
            "response_fact_id": f"resp-{response.id}",
        },
    }


def _alert_fact(
    session: Session, patient_id: str, ident: str, content: Content, lang: str
) -> dict[str, Any]:
    alert = _own(session.get(Alert, ident), patient_id)
    return {
        "fact_id": f"alert-{alert.id}",
        "kind": "alert",
        "at": iso_prague(alert.created_at),
        "label": headline(alert, content, lang),
        "data": alert_view(session, alert, content, lang),
    }


def _visit_fact(session: Session, patient_id: str, ident: str, lang: str) -> dict[str, Any]:
    visit = _own(session.get(Visit, ident), patient_id)
    return {
        "fact_id": f"visit-{visit.id}",
        "kind": "visit",
        "at": iso_prague(visit.at),
        "label": _t(_VISIT[visit.kind], lang),
        "data": {"kind": visit.kind},
    }


def _therapy_fact(
    session: Session, patient_id: str, ident: str, content: Content, lang: str
) -> dict[str, Any]:
    therapy = _own(session.get(Therapy, ident), patient_id)
    regimen = regimen_of(content, therapy.regimen_id)
    return {
        "fact_id": f"ther-{therapy.id}",
        "kind": "therapy",
        "at": iso_prague(therapy.cycle_start),
        "label": localize(regimen["label"], lang) if regimen else therapy.regimen_id,
        "data": {
            "regimen_id": therapy.regimen_id,
            "drugs": [dict(d) for d in regimen["drugs"]] if regimen else [],
            "cycle_start": iso_prague(therapy.cycle_start),
        },
    }


def _assessment_fact(
    session: Session, patient_id: str, ident: str, content: Content, lang: str
) -> dict[str, Any]:
    assessment = _own(session.get(Assessment, ident), patient_id)
    view = assessment_view(session, assessment, content)
    return {
        "fact_id": f"assess-{assessment.id}",
        "kind": "assessment",
        "at": view["assessed_at"],
        "label": _t(_ASSESSMENT, lang).format(count=len(view["items"])),
        "data": view,
    }
