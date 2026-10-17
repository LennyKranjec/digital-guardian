"""Lesen von Meldungen und Benachrichtigungen im Vertragsformat (Schema `Alert`, `Notification`).

Nur Darstellung: Stufe, Erklärung und Status stammen unverändert aus den gespeicherten Zeilen
(kein LLM, keine Neuberechnung).
"""

from typing import Any, Final, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import User
from app.services.access import not_found
from waechter.content import Content
from waechter.models import Alert, AlertAction, Notification, Patient
from waechter.services.alerts import ACTION_ACKNOWLEDGE, DEFAULT_LANG, explanation_view, headline
from waechter.timeutil import iso_prague

StatusFilter = Literal["open", "acknowledged", "all"]
NOTIFICATION_LIMIT: Final = 200


def _acknowledgement(session: Session, alert: Alert) -> dict[str, Any] | None:
    action = session.scalars(
        select(AlertAction)
        .where(AlertAction.alert_id == alert.id, AlertAction.action == ACTION_ACKNOWLEDGE)
        .order_by(AlertAction.at.desc(), AlertAction.id)
        .limit(1)
    ).first()
    if action is None:
        return None
    user = session.get(User, action.actor_user_id) if action.actor_user_id else None
    return {
        "by": user.display_name if user is not None else "",
        "at": iso_prague(action.at),
        "decision": action.decision,
        "note": action.note,
    }


def alert_view(
    session: Session, alert: Alert, content: Content, lang: str = DEFAULT_LANG
) -> dict[str, Any]:
    return {
        "alert_id": alert.id,
        "patient_id": alert.patient_id,
        "rule_id": alert.rule_id,
        "rule_version": alert.rule_version,
        "level": alert.level,
        "symptom_key": alert.symptom_key or None,
        "attribute": alert.attribute,
        "headline": headline(alert, content, lang),
        "status": alert.status,
        "created_at": iso_prague(alert.created_at),
        "notified": alert.notified,
        "explanation": explanation_view(alert, lang),
        "acknowledgement": _acknowledgement(session, alert),
    }


def get_alert(session: Session, alert_id: str) -> Alert:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise not_found()
    return alert


def list_alerts(
    session: Session, patient_id: str, status: StatusFilter, content: Content, lang: str
) -> list[dict[str, Any]]:
    """Meldungen einer Patientin, neueste zuerst; unbekannte Patientin ⇒ 404."""
    if session.get(Patient, patient_id) is None:
        raise not_found()
    query = select(Alert).where(Alert.patient_id == patient_id)
    if status != "all":
        query = query.where(Alert.status == status)
    alerts = session.scalars(query.order_by(Alert.created_at.desc(), Alert.id)).all()
    return [alert_view(session, a, content, lang) for a in alerts]


def list_notifications(
    session: Session, content: Content | None = None, lang: str | None = None
) -> list[dict[str, Any]]:
    """Sofortbenachrichtigungen (In-App), neueste zuerst, höchstens `NOTIFICATION_LIMIT`.

    Mit `lang` wird der Text aus der Meldung in der Sprache der Oberfläche neu gebildet (gespeichert
    ist die Standardsprache); ohne `lang` oder ohne Meldung gilt der gespeicherte Text.
    """
    rows = session.scalars(
        select(Notification)
        # gleicher Zeitpunkt: nach Text (beginnt mit dem Pseudonym), nicht nach der zufälligen id
        .order_by(Notification.at.desc(), Notification.text, Notification.id)
        .limit(NOTIFICATION_LIMIT)
    ).all()
    return [
        {
            "notification_id": n.id,
            "at": iso_prague(n.at),
            "patient_id": n.patient_id,
            "alert_id": n.alert_id,
            "level": n.level,
            "channel": n.channel,
            "text": _notification_text(session, n, content, lang),
        }
        for n in rows
    ]


def _notification_text(
    session: Session, notification: Notification, content: Content | None, lang: str | None
) -> str:
    if lang is None or content is None or notification.alert_id is None:
        return notification.text
    alert = session.get(Alert, notification.alert_id)
    patient = session.get(Patient, notification.patient_id)
    if alert is None or patient is None:
        return notification.text
    return f"{patient.pseudonym}: {headline(alert, content, lang)}"
