"""Audit-Service: schreibt append-only AuditEvents. Nie Freitext, Passwörter oder Eingabewerte."""

from dataclasses import dataclass
from typing import Final

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.persistence.models import AuditEvent

AuditDetails = dict[str, str | int | bool | None]

ACTOR_ANONYMOUS: Final = "anonymous"
ACTOR_SYSTEM: Final = "system"


@dataclass(frozen=True)
class Actor:
    user_id: str | None
    role: str


def record_audit(
    session: Session,
    clock: Clock,
    actor: Actor,
    action: str,
    target_type: str,
    *,
    target_id: str | None = None,
    subject_id: str | None = None,
    details: AuditDetails | None = None,
) -> AuditEvent:
    """Fügt das Ereignis der laufenden Transaktion hinzu (Commit macht der aufrufende Service)."""
    event = AuditEvent(
        at=clock.now(),
        actor_user_id=actor.user_id,
        actor_role=actor.role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        subject_id=subject_id,
        details_json=dict(details or {}),
    )
    session.add(event)
    return event
