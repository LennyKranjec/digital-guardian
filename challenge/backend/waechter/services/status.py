"""Ampel je Patientin und R-MIS-01 (fehlende Daten), deterministisch.

Vertrag: README §3, G-02, G-04, G-19, H-5.

Ampel: höchste offene Stufe rot > gelb > grau; sonst grün. Zusätzlich gilt:
- G-02 `persisting`: eine quittierte Meldung, deren Wert in der jüngsten Antwort weiter über ihrer
  Schwelle liegt, hält die Ampel mindestens auf gelb (nie grün).
- H-5: ist eine Antwort nicht ausgewertet (`evaluation_status = failed`), ist die Ampel
  mindestens grau ("Auswertung ausstehend").
- Keine Daten überhaupt ⇒ grau ("unbekannt", nie "gut").
R-MIS-01 wird beim Lesen idempotent ausgewertet: Referenz ist `max(letzte Antwort mit ≥ 1 Wert,
Zyklusstart)` (G-19), "Tage" sind Kalendertage in Prag (G-04). Es gibt höchstens eine offene graue
Meldung je Patientin; sobald wieder Daten vorliegen, wird sie automatisch geschlossen (Aktion
`auto_resolve`, nie als ärztliche Quittierung).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.services.audit import ACTOR_SYSTEM, Actor, record_audit
from waechter.content import Content
from waechter.models import Alert, AlertAction, Answer, Patient, Response, Therapy
from waechter.services.alerts import (
    ACTION_ACKNOWLEDGE,
    NO_SYMPTOM,
    STATUS_ACKNOWLEDGED,
    STATUS_OPEN,
)
from waechter.services.config import active_body
from waechter.timeutil import days_between, iso_prague

logger = logging.getLogger("waechter.status")

ACTION_AUTO_RESOLVE: Final = "auto_resolve"
KIND_MISSING: Final = "missing"
LIGHT_ORDER: Final = {"green": 0, "grey": 1, "yellow": 2, "red": 3}
EVALUATION_FAILED: Final = "failed"


@dataclass(frozen=True)
class Status:
    traffic_light: str
    open_alerts: list[Alert]
    persisting: list[Alert]
    evaluation_pending: bool
    last_response_at: datetime | None
    days_without_response: int | None


def current_rules(session: Session, content: Content) -> dict[str, Any]:
    return active_body(session, "rules") or content.rules


def missing_rule(rules: dict[str, Any]) -> dict[str, Any] | None:
    return next((r for r in rules["rules"] if r["enabled"] and r["kind"] == KIND_MISSING), None)


def latest_response(session: Session, patient_id: str) -> Response | None:
    return session.scalars(
        select(Response)
        .where(Response.patient_id == patient_id)
        .order_by(Response.recorded_at.desc(), Response.id.desc())
        .limit(1)
    ).first()


def last_value_response(session: Session, patient_id: str) -> Response | None:
    """Jüngste Antwort mit mindestens einem Wert (Alles-`null` zählt nicht, G-10)."""
    return session.scalars(
        select(Response)
        .where(
            Response.patient_id == patient_id,
            select(Answer.id)
            .where(Answer.response_id == Response.id, Answer.value.is_not(None))
            .exists(),
        )
        .order_by(Response.recorded_at.desc(), Response.id.desc())
        .limit(1)
    ).first()


def current_therapy(session: Session, patient_id: str) -> Therapy | None:
    return session.scalars(
        select(Therapy)
        .where(Therapy.patient_id == patient_id)
        .order_by(Therapy.cycle_start.desc(), Therapy.id)
        .limit(1)
    ).first()


def _reference(value_response: Response | None, therapy: Therapy | None) -> datetime | None:
    """G-19: `max(letzte Antwort mit ≥ 1 Wert, Zyklusstart)`."""
    times = [
        t
        for t in (value_response and value_response.recorded_at, therapy and therapy.cycle_start)
        if t
    ]
    return max(times) if times else None


def _open_missing(session: Session, patient_id: str, rule_id: str) -> Alert | None:
    return session.scalars(
        select(Alert).where(
            Alert.patient_id == patient_id,
            Alert.rule_id == rule_id,
            Alert.symptom_key == NO_SYMPTOM,
            Alert.status == STATUS_OPEN,
        )
    ).first()


def _in_cooldown(
    session: Session, patient_id: str, rule_id: str, now: datetime, hours: float
) -> bool:
    """Nach ärztlicher Quittierung der letzten Meldung keine neue innerhalb des Cooldowns."""
    acked_at = session.scalar(
        select(func.max(AlertAction.at))
        .join(Alert, Alert.id == AlertAction.alert_id)
        .where(
            Alert.patient_id == patient_id,
            Alert.rule_id == rule_id,
            Alert.symptom_key == NO_SYMPTOM,
            AlertAction.action == ACTION_ACKNOWLEDGE,
        )
    )
    return acked_at is not None and now < acked_at + timedelta(hours=hours)


def _audit(
    session: Session, clock: Clock, action: str, alert: Alert, patient: Patient, rule_id: str
) -> None:
    """Lese-Seiteneffekt R-MIS-01 (DR-011) nachvollziehbar machen; ohne Werte."""
    record_audit(
        session,
        clock,
        Actor(user_id=None, role=ACTOR_SYSTEM),
        action,
        "alert",
        target_id=alert.id,
        subject_id=patient.id,
        details={"rule_id": rule_id},
    )


def ensure_missing_alert(
    session: Session, clock: Clock, patient: Patient, content: Content, rules: dict[str, Any]
) -> None:
    """R-MIS-01 beim Lesen: anlegen, wenn Daten fehlen; schließen, wenn sie wieder da sind."""
    rule = missing_rule(rules)
    if rule is None:
        return
    now = clock.now()
    value_response = last_value_response(session, patient.id)
    therapy = current_therapy(session, patient.id)
    reference = _reference(value_response, therapy)
    open_alert = _open_missing(session, patient.id, rule["id"])
    days = days_between(reference, now) if reference is not None else None
    limit = rule["params"]["max_days_without_response"]
    is_missing = days is not None and days > limit
    if not is_missing:
        if open_alert is not None:
            open_alert.status = STATUS_ACKNOWLEDGED
            open_alert.version += 1
            session.add(
                AlertAction(
                    alert_id=open_alert.id, action=ACTION_AUTO_RESOLVE, at=now, synthetic=True
                )
            )
            _audit(session, clock, "missing_alert_closed", open_alert, patient, rule["id"])
            session.commit()
        return
    if open_alert is not None or _in_cooldown(
        session, patient.id, rule["id"], now, rules["noise"]["cooldown_hours"]
    ):
        return
    evidence = [f"ther-{therapy.id}"] if therapy is not None else []
    if value_response is not None:
        evidence.append(f"resp-{value_response.id}")
    created_alert = Alert(
        patient_id=patient.id,
        response_id=None,
        rule_id=rule["id"],
        rule_version=rules["version"],
        level=rule["level"],
        symptom_key=NO_SYMPTOM,
        attribute=None,
        status=STATUS_OPEN,
        explanation_json={
            "kind": KIND_MISSING,
            "params": dict(rule["params"]),
            "observed": {
                "value": None,
                "baseline": None,
                "delta": None,
                "slope_per_day": None,
                "projected_value": None,
                "days_without_response": float(days or 0),
            },
            "baseline_window": None,
            "cycle_day": None,
            "evidence": evidence,
            "rationale_i18n": rule["rationale"],
            "source_id": rule.get("source_id"),
            "reference_at": iso_prague(reference) if reference is not None else None,
        },
        notified=False,
        version=1,
        created_at=now,
        synthetic=True,
    )
    try:
        session.add(created_alert)
        session.flush()
        _audit(session, clock, "missing_alert_opened", created_alert, patient, rule["id"])
        session.commit()
    except IntegrityError:  # paralleler Lesezugriff war schneller: genau eine offene Meldung bleibt
        session.rollback()


def latest_value(
    session: Session, patient_id: str, symptom_key: str, attribute: str | None
) -> int | None:
    """Jüngster **nicht-null** Wert des Tripels (übersprungene/fehlende Werte zählen nicht)."""
    return session.scalar(
        select(Answer.value)
        .join(Response, Response.id == Answer.response_id)
        .where(
            Response.patient_id == patient_id,
            Answer.symptom_key == symptom_key,
            Answer.attribute == (attribute or ""),
            Answer.value.is_not(None),
        )
        .order_by(Response.recorded_at.desc(), Response.id.desc())
        .limit(1)
    )


def _persisting(session: Session, patient_id: str, open_alerts: list[Alert]) -> list[Alert]:
    open_triples = {(a.symptom_key, a.attribute) for a in open_alerts}
    acknowledged = session.scalars(
        select(Alert)
        .where(
            Alert.patient_id == patient_id,
            Alert.status == STATUS_ACKNOWLEDGED,
            Alert.symptom_key != NO_SYMPTOM,
            select(AlertAction.id)
            .where(AlertAction.alert_id == Alert.id, AlertAction.action == ACTION_ACKNOWLEDGE)
            .exists(),
        )
        .order_by(Alert.created_at, Alert.id)
    ).all()
    result: list[Alert] = []
    seen: set[tuple[str, str | None]] = set()
    for alert in acknowledged:
        triple = (alert.symptom_key, alert.attribute)
        value = latest_value(session, patient_id, alert.symptom_key, alert.attribute)
        explanation = alert.explanation_json
        threshold = explanation.get("params", {}).get("min_value")
        if threshold is None:
            threshold = explanation.get("observed", {}).get("value")
        if value is None or threshold is None or triple in open_triples or triple in seen:
            continue
        if value >= threshold:
            result.append(alert)
            seen.add(triple)
    return result


def compute_status(session: Session, clock: Clock, patient: Patient, content: Content) -> Status:
    rules = current_rules(session, content)
    ensure_missing_alert(session, clock, patient, content, rules)
    open_alerts = list(
        session.scalars(
            select(Alert)
            .where(Alert.patient_id == patient.id, Alert.status == STATUS_OPEN)
            .order_by(Alert.created_at, Alert.id)
        )
    )
    persisting = _persisting(session, patient.id, open_alerts)
    pending = (
        session.scalar(
            select(func.count())
            .select_from(Response)
            .where(
                Response.patient_id == patient.id, Response.evaluation_status == EVALUATION_FAILED
            )
        )
        or 0
    ) > 0
    value_response = last_value_response(session, patient.id)
    therapy = current_therapy(session, patient.id)
    reference = _reference(value_response, therapy)
    light = "green"
    for level in [a.level for a in open_alerts]:
        light = max(light, level, key=LIGHT_ORDER.__getitem__)
    if persisting:
        light = max(light, "yellow", key=LIGHT_ORDER.__getitem__)
    rule = missing_rule(current_rules(session, content))
    days = days_between(reference, clock.now()) if reference is not None else None
    stale = (
        rule is not None and days is not None and days > rule["params"]["max_days_without_response"]
    )
    if pending or reference is None or stale:  # veraltete Daten sind "unbekannt", nie "gut"
        light = max(light, "grey", key=LIGHT_ORDER.__getitem__)
    latest = latest_response(session, patient.id)
    return Status(
        traffic_light=light,
        open_alerts=open_alerts,
        persisting=persisting,
        evaluation_pending=pending,
        last_response_at=latest.recorded_at if latest is not None else None,
        days_without_response=days,
    )
