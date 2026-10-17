"""Lesesichten für die Ärztin: Arbeitsliste, Übersicht und Verlauf.

Vertragsschemas `WorklistRow`, `Overview`, `Timeline`.

Nur Darstellung gespeicherter Fakten und der deterministischen Ampel (`status.py`). Kein LLM, keine
neue Bewertung. Zeiten als ISO 8601 in Europe/Prague, Tage als Kalendertage in Prag (G-04).

Festlegungen (im Handoff dokumentiert):
- `since_last_visit`: Fenster beginnt beim letzten vergangenen Termin (sonst beim Zyklusstart, sonst
  bei der ersten Antwort). `first` = erster Wert ab Fensterbeginn, `last` = jüngster Wert, `max` =
  Maximum; `direction`: `up`/`down`/`flat` aus dem Vergleich **letzter gegen ersten** Wert,
  `unknown` bei weniger als zwei Werten. `alerts` = Meldungen des Tripels seit Fensterbeginn.
- Fehlende Tage: Kalendertage von Fensterbeginn (einschließlich) bis gestern ohne Antwort mit
  mindestens einem Wert (je Symptom/Attribut bzw. insgesamt im Verlauf); heute zählt noch nicht.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError, FieldError
from app.services.access import not_found
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content
from waechter.models import Alert, Answer, Patient, Response, Therapy, Visit
from waechter.services import triage as triage_service
from waechter.services.alert_queries import alert_view
from waechter.services.alerts import NO_SYMPTOM, headline
from waechter.services.assessment_queries import list_assessments, tracked_terms
from waechter.services.config import active_body
from waechter.services.questionnaire import localize, select_items
from waechter.services.status import (
    LIGHT_ORDER,
    Status,
    compute_status,
    current_therapy,
)
from waechter.services.summary_queries import latest_summary, summary_view
from waechter.timeutil import days_between, iso_prague, prague_date, to_prague

_THERAPY_EVENT: Final = {
    "cs": "Začátek cyklu: {label}",
    "en": "Cycle start: {label}",
    "de": "Zyklusbeginn: {label}",
}


@dataclass(frozen=True)
class Reading:
    t: datetime
    value: int | None
    answer_id: str


def get_patient(session: Session, patient_id: str) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise not_found()
    return patient


def regimen_of(content: Content, regimen_id: str) -> dict[str, Any] | None:
    return next((r for r in content.regimens["regimens"] if r["id"] == regimen_id), None)


def _age(patient: Patient, now: datetime) -> int:
    return to_prague(now).year - patient.birth_year


def cycle_day_of(therapy: Therapy | None, now: datetime) -> int | None:
    if therapy is None:
        return None
    days = days_between(therapy.cycle_start, now)
    return days + 1 if days >= 0 else None


def visits_of(session: Session, patient_id: str) -> list[Visit]:
    return list(
        session.scalars(
            select(Visit).where(Visit.patient_id == patient_id).order_by(Visit.at, Visit.id)
        )
    )


def upcoming_visit(visits: list[Visit], now: datetime) -> Visit | None:
    return next((v for v in visits if v.kind == "planned" and v.at > now), None)


def latest_past_visit(visits: list[Visit], now: datetime) -> Visit | None:
    past = [v for v in visits if v.kind == "past" and v.at <= now]
    return past[-1] if past else None


def _brief(alert: Alert, content: Content, lang: str) -> dict[str, Any]:
    return {
        "alert_id": alert.id,
        "rule_id": alert.rule_id,
        "level": alert.level,
        "symptom_key": alert.symptom_key or None,
        "headline": headline(alert, content, lang),
        "created_at": iso_prague(alert.created_at),
    }


def _top_alert(alerts: list[Alert]) -> Alert | None:
    """Höchste Stufe, bei Gleichstand die älteste offene Meldung."""
    if not alerts:
        return None
    return sorted(alerts, key=lambda a: (-LIGHT_ORDER[a.level], a.created_at, a.id))[0]


def worklist(session: Session, clock: Clock, content: Content, lang: str) -> list[dict[str, Any]]:
    """Alle Patient:innen, sortiert rot > gelb > grau > grün, dann älteste offene Meldung zuerst."""
    now = clock.now()
    entries: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for patient in session.scalars(select(Patient).order_by(Patient.pseudonym)).all():
        status = compute_status(session, clock, patient, content)
        therapy = current_therapy(session, patient.id)
        regimen = regimen_of(content, therapy.regimen_id) if therapy is not None else None
        visits = visits_of(session, patient.id)
        next_visit = upcoming_visit(visits, now)
        top = _top_alert(status.open_alerts)
        row = {
            "patient_id": patient.id,
            "pseudonym": patient.pseudonym,
            "display_name": patient.display_name,
            "age": _age(patient, now),
            "regimen_id": therapy.regimen_id if therapy is not None else "",
            "regimen_label": localize(regimen["label"], lang) if regimen is not None else "",
            "cycle_day": cycle_day_of(therapy, now),
            "traffic_light": status.traffic_light,
            "open_alerts": len(status.open_alerts),
            "top_alert": _brief(top, content, lang) if top is not None else None,
            "last_response_at": (
                iso_prague(status.last_response_at) if status.last_response_at else None
            ),
            "next_visit_at": iso_prague(next_visit.at) if next_visit is not None else None,
            "persisting": bool(status.persisting),
            "evaluation_pending": status.evaluation_pending,
            "synthetic": True,
        }
        oldest = min(
            (a.created_at for a in status.open_alerts),
            default=datetime.max.replace(tzinfo=now.tzinfo),
        )
        entries.append(((-LIGHT_ORDER[status.traffic_light], oldest, patient.pseudonym), row))
    return [row for _, row in sorted(entries, key=lambda e: e[0])]


# --- Messwerte ------------------------------------------------------------------------------


def readings(session: Session, patient_id: str) -> dict[tuple[str, str], list[Reading]]:
    """Alle gespeicherten Werte (auch `null`) je Symptom/Attribut, chronologisch."""
    rows = session.execute(
        select(Answer.symptom_key, Answer.attribute, Answer.value, Answer.id, Response.recorded_at)
        .join(Response, Response.id == Answer.response_id)
        .where(Response.patient_id == patient_id)
        .order_by(Response.recorded_at, Response.id, Answer.symptom_key, Answer.attribute)
    )
    result: dict[tuple[str, str], list[Reading]] = defaultdict(list)
    for symptom_key, attribute, value, answer_id, recorded_at in rows:
        result[(symptom_key, attribute)].append(Reading(recorded_at, value, answer_id))
    return result


def triples_for(
    session: Session, patient_id: str, content: Content, data: dict[tuple[str, str], list[Reading]]
) -> list[tuple[str, str]]:
    """Fragebogen-Tripel in Anzeigereihenfolge, danach weitere Tripel, zu denen Daten vorliegen."""
    ordered: list[tuple[str, str]] = []
    try:
        selection = select_items(session, patient_id, content)
    except ApiError:
        selection = None
    if selection is not None:
        for item, _ in selection.items:
            ordered.extend((item["symptom_key"], a["attribute"]) for a in item["attributes"])
    ordered.extend(sorted(t for t in data if t not in ordered))
    return ordered


def symptom_label(content: Content, symptom_key: str, lang: str) -> str:
    for item in content.items["items"]:
        if item["symptom_key"] == symptom_key:
            return localize(item["label"], lang)
    return symptom_key


def _days(first_day: date, last_day: date) -> list[date]:
    count = (last_day - first_day).days
    return [first_day + timedelta(days=i) for i in range(count + 1)]


def yesterday_of(now: datetime) -> date:
    return prague_date(now) - timedelta(days=1)


def missing_dates(answered: set[date], first_day: date, last_day: date) -> list[date]:
    """Tage von `first_day` bis `last_day` ohne Wert (spätestens gestern)."""
    return [d for d in _days(first_day, last_day) if d not in answered]


def answered_days(points: list[Reading]) -> set[date]:
    return {prague_date(p.t) for p in points if p.value is not None}


def _direction(values: list[int]) -> str:
    if len(values) < 2:
        return "unknown"
    return "up" if values[-1] > values[0] else "down" if values[-1] < values[0] else "flat"


def window_start(
    visits: list[Visit],
    therapy: Therapy | None,
    data: dict[tuple[str, str], list[Reading]],
    now: datetime,
) -> datetime | None:
    """Fensterbeginn "seit dem letzten Termin": Termin, sonst Zyklusbeginn, sonst erste Antwort."""
    last = latest_past_visit(visits, now)
    if last is not None:
        return last.at
    if therapy is not None:
        return therapy.cycle_start
    return min((p.t for series in data.values() for p in series), default=None)


def _since_last_visit(
    session: Session,
    content: Content,
    patient: Patient,
    visits: list[Visit],
    therapy: Therapy | None,
    data: dict[tuple[str, str], list[Reading]],
    now: datetime,
    lang: str,
) -> list[dict[str, Any]]:
    start = window_start(visits, therapy, data, now)
    alert_rows = session.scalars(
        select(Alert).where(Alert.patient_id == patient.id, Alert.symptom_key != NO_SYMPTOM)
    ).all()
    result: list[dict[str, Any]] = []
    for symptom_key, attribute in triples_for(session, patient.id, content, data):
        points = [
            p for p in data.get((symptom_key, attribute), []) if start is None or p.t >= start
        ]
        values = [p.value for p in points if p.value is not None]
        result.append(
            {
                "symptom_key": symptom_key,
                "label": symptom_label(content, symptom_key, lang),
                "attribute": attribute,
                "first": values[0] if values else None,
                "last": values[-1] if values else None,
                "max": max(values) if values else None,
                "direction": _direction(values),
                "alerts": sum(
                    1
                    for a in alert_rows
                    if (a.symptom_key, a.attribute) == (symptom_key, attribute)
                    and (start is None or a.created_at >= start)
                ),
                "missing_days": (
                    len(missing_dates(answered_days(points), prague_date(start), yesterday_of(now)))
                    if start is not None
                    else 0
                ),
            }
        )
    return result


def since_last_visit_rows(
    session: Session, clock: Clock, content: Content, patient: Patient, lang: str
) -> list[dict[str, Any]]:
    """Verlauf seit dem letzten Termin je Symptom/Attribut (Übersicht und CTCAE-Hinweis)."""
    return _since_last_visit(
        session,
        content,
        patient,
        visits_of(session, patient.id),
        current_therapy(session, patient.id),
        readings(session, patient.id),
        clock.now(),
        lang,
    )


def overview(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient_id: str,
    content: Content,
    lang: str,
) -> dict[str, Any]:
    patient = get_patient(session, patient_id)
    now = clock.now()
    status: Status = compute_status(session, clock, patient, content)
    therapy = current_therapy(session, patient.id)
    regimen = regimen_of(content, therapy.regimen_id) if therapy is not None else None
    visits = visits_of(session, patient.id)
    last_visit, next_visit = latest_past_visit(visits, now), upcoming_visit(visits, now)
    data = readings(session, patient.id)
    report = active_body(session, "report") or content.report
    therapy_block: dict[str, Any] | None = None
    if therapy is not None:
        therapy_block = {
            "fact_id": f"ther-{therapy.id}",
            "regimen_id": therapy.regimen_id,
            "regimen_label": localize(regimen["label"], lang) if regimen else "",
            "drugs": [dict(d) for d in regimen["drugs"]] if regimen else [],
            "cycle_start": iso_prague(therapy.cycle_start),
            "cycle_day": cycle_day_of(therapy, now),
            "watch_notes": (
                [localize(n["text"], lang) for n in regimen.get("watch_notes", [])]
                if regimen
                else []
            ),
        }
    result = {
        "patient": {
            "patient_id": patient.id,
            "pseudonym": patient.pseudonym,
            "display_name": patient.display_name,
            "age": _age(patient, now),
            "sex": patient.sex,
            "language": patient.language,
            "diagnosis_text": patient.diagnosis_text,
            "synthetic": True,
        },
        "therapy": therapy_block,
        "traffic_light": status.traffic_light,
        "open_alerts": [alert_view(session, a, content, lang) for a in status.open_alerts],
        "persisting": bool(status.persisting),
        "persisting_alerts": [alert_view(session, a, content, lang) for a in status.persisting],
        "evaluation_pending": status.evaluation_pending,
        "days_without_response": status.days_without_response,
        "last_visit_at": iso_prague(last_visit.at) if last_visit is not None else None,
        "next_visit_at": iso_prague(next_visit.at) if next_visit is not None else None,
        "last_response_at": iso_prague(status.last_response_at)
        if status.last_response_at
        else None,
        "since_last_visit": _since_last_visit(
            session, content, patient, visits, therapy, data, now, lang
        ),
        "summary": summary_view(latest)
        if (latest := latest_summary(session, patient.id))
        else None,
        "report_sections": list(report["sections"]),
        "triage_latest": triage_service.latest_summary(session, patient.id),
        "tracked_symptoms": tracked_terms(session, patient.id, content, lang),
    }
    record_audit(
        session,
        clock,
        principal.actor,
        "view_overview",
        "patient",
        target_id=patient.id,
        subject_id=patient.id,
    )
    session.commit()
    return result


# --- Verlauf --------------------------------------------------------------------------------


def timeline(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient_id: str,
    content: Content,
    lang: str,
    start: datetime | None,
    end: datetime | None,
) -> dict[str, Any]:
    patient = get_patient(session, patient_id)
    now = clock.now()
    if (start is not None and start.tzinfo is None) or (end is not None and end.tzinfo is None):
        raise ApiError(
            422,
            "validation_failed",
            "Invalid range",
            [FieldError(field="from", code="timezone", message="Time zone required")],
        )
    therapy = current_therapy(session, patient.id)
    data = readings(session, patient.id)
    first_point = min((s[0].t for s in data.values() if s), default=None)
    upper = end or now
    if start is not None:
        lower = start
    else:
        # Standardbereich: Zyklusbeginn bzw. letzter vergangener Termin (der frühere), nie nach `to`
        past = latest_past_visit(visits_of(session, patient.id), now)
        candidates = [
            c
            for c in (
                therapy.cycle_start if therapy is not None else None,
                past.at if past else None,
            )
            if c is not None
        ]
        lower = min([*candidates, upper] if candidates else [first_point or now, upper])
    if lower > upper:
        raise ApiError(
            422,
            "validation_failed",
            "Invalid range",
            [FieldError(field="from", code="range", message="from is after to")],
        )
    series = []
    answered: set[date] = set()
    for symptom_key, attribute in triples_for(session, patient.id, content, data):
        points = [p for p in data.get((symptom_key, attribute), []) if lower <= p.t <= upper]
        answered |= answered_days(points)
        series.append(
            {
                "symptom_key": symptom_key,
                "attribute": attribute,
                "label": symptom_label(content, symptom_key, lang),
                "points": [
                    {"t": iso_prague(p.t), "value": p.value, "fact_id": f"obs-{p.answer_id}"}
                    for p in points
                ],
            }
        )
    alert_rows = session.scalars(
        select(Alert)
        .where(Alert.patient_id == patient.id, Alert.created_at >= lower, Alert.created_at <= upper)
        .order_by(Alert.created_at, Alert.id)
    ).all()
    regimen = regimen_of(content, therapy.regimen_id) if therapy is not None else None
    events = []
    if therapy is not None and lower <= therapy.cycle_start <= upper:
        template = _THERAPY_EVENT.get(lang, _THERAPY_EVENT["en"])
        label = localize(regimen["label"], lang) if regimen else therapy.regimen_id
        events.append(
            {
                "fact_id": f"ther-{therapy.id}",
                "at": iso_prague(therapy.cycle_start),
                "label": template.format(label=label),
            }
        )
    result = {
        "patient_id": patient.id,
        "from": iso_prague(lower),
        "to": iso_prague(upper),
        "series": series,
        "alerts": [alert_view(session, a, content, lang) for a in alert_rows],
        "missing_days": [
            d.isoformat()
            for d in missing_dates(
                answered, prague_date(lower), min(prague_date(upper), yesterday_of(now))
            )
        ],
        "visits": [
            {"fact_id": f"visit-{v.id}", "at": iso_prague(v.at), "kind": v.kind}
            for v in visits_of(session, patient.id)
            if lower <= v.at <= upper
        ],
        "assessments": list_assessments(session, patient.id, content, lower, upper),
        "therapy_events": events,
    }
    record_audit(
        session,
        clock,
        principal.actor,
        "view_timeline",
        "patient",
        target_id=patient.id,
        subject_id=patient.id,
    )
    session.commit()
    return result
