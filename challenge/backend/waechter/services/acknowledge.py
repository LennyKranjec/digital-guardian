"""Quittieren einer Meldung mit Entscheidung (bedingtes Update, Audit).

Nur aus Status `open`: `UPDATE … WHERE id=? AND status='open' AND version=?` setzt Status und erhöht
`version`; wer nichts ändert, bekommt 409 `alert_not_open`. Vier gleichzeitige Quittierungen ergeben
genau eine Quittierung. Die Rauschbremse (`alerts.suppressed`) nutzt die Zeit der Quittierung.
"""

from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content
from waechter.models import Alert, AlertAction
from waechter.services.alert_queries import alert_view, get_alert
from waechter.services.alerts import (
    ACTION_ACKNOWLEDGE,
    DEFAULT_LANG,
    STATUS_ACKNOWLEDGED,
    STATUS_OPEN,
)


def acknowledge(
    session: Session,
    clock: Clock,
    principal: Principal,
    alert_id: str,
    decision: str,
    note: str | None,
    content: Content,
    lang: str = DEFAULT_LANG,
) -> dict[str, Any]:
    alert = get_alert(session, alert_id)
    not_open = ApiError(409, "alert_not_open", "Alert is not open")
    if alert.status != STATUS_OPEN:
        raise not_open
    changed = session.execute(
        update(Alert)
        .where(Alert.id == alert.id, Alert.status == STATUS_OPEN, Alert.version == alert.version)
        .values(status=STATUS_ACKNOWLEDGED, version=Alert.version + 1)
    )
    if changed.rowcount != 1:  # type: ignore[attr-defined]  # CursorResult.rowcount
        session.rollback()
        raise not_open
    session.add(
        AlertAction(
            alert_id=alert.id,
            action=ACTION_ACKNOWLEDGE,
            decision=decision,
            note=note,
            actor_user_id=principal.user_id,
            at=clock.now(),
            synthetic=True,
        )
    )
    record_audit(
        session,
        clock,
        principal.actor,
        "acknowledge_alert",
        "alert",
        target_id=alert.id,
        subject_id=alert.patient_id,
        details={"decision": decision, "level": alert.level},
    )
    session.commit()
    session.refresh(alert)
    return alert_view(session, alert, content, lang)
