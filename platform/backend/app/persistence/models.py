"""Plattform-Modelle: Benutzer, Anmeldesitzungen und Audit-Log. Fachmodelle gehören in `challenge/`.

Konventionen: IDs sind UUID4-Strings, Zeitstempel UTC (`UtcDateTime`). Das Audit ist append-only.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    TypeDecorator,
    event,
    text,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm.mapper import Mapper


class UtcDateTime(TypeDecorator[datetime]):
    """Speichert naive UTC-Werte (SQLite) und liefert immer tz-aware UTC zurück."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime is not allowed; use timezone-aware UTC")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Basis der Plattform-Tabellen; Challenge-Pakete bringen eine eigene Basis mit."""


def _id_column() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = _id_column()
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: frei konfigurierbarer Rollenname (Registry), kein Fremdschlüssel
    role_name: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    synthetic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = _id_column()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class AuditEvent(Base):
    """Append-only. `actor_user_id`/`subject_id` sind bewusst keine Fremdschlüssel: das Audit
    überlebt Resets. `details_json` enthält nie Freitexte oder Werte."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_at", "at"),
        Index("ix_audit_subject", "subject_id"),
        Index("ix_audit_action", "action"),
    )

    id: Mapped[str] = _id_column()
    at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36))
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64))
    subject_id: Mapped[str | None] = mapped_column(String(36))
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    synthetic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )


def _forbid_update(_: Mapper[Any], __: Any, target: Base) -> None:
    raise RuntimeError(f"{type(target).__name__} is append-only; updates are not allowed")


event.listen(AuditEvent, "before_update", _forbid_update)
