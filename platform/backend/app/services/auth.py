"""Anmeldung, Sitzungen und Hauptakteur. Sitzungs-Token werden nur als SHA-256-Hash gespeichert.

Die Plattform kennt kein Fachobjekt: `subject_id` füllt der Hook `Registry.resolve_subject`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError
from app.core.security import (
    dummy_password_hash,
    hash_token,
    new_session_token,
    verify_password,
)
from app.persistence.models import AuthSession, User
from app.services.audit import ACTOR_ANONYMOUS, Actor, record_audit

SubjectLookup = Callable[[Session, str], str | None]


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    display_name: str
    role: str
    subject_id: str | None

    @property
    def actor(self) -> Actor:
        return Actor(user_id=self.user_id, role=self.role)


@dataclass(frozen=True)
class LoginResult:
    principal: Principal
    token: str
    max_age_seconds: int


def _principal(session: Session, user: User, lookup: SubjectLookup | None) -> Principal:
    return Principal(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role_name,
        subject_id=lookup(session, user.id) if lookup else None,
    )


def _find_session(session: Session, token: str) -> AuthSession | None:
    return session.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))


def login(
    session: Session,
    clock: Clock,
    *,
    username: str,
    password: str,
    ttl_hours: int,
    lookup: SubjectLookup | None = None,
) -> LoginResult:
    """Einheitlicher Fehler `invalid_credentials`; für unbekannte Konten läuft ein Dummy-Verify."""
    user = session.scalar(select(User).where(User.username == username))
    password_hash = user.password_hash if user is not None else dummy_password_hash()
    password_ok = verify_password(password_hash, password)
    if user is None or not user.is_active or not password_ok:
        record_audit(
            session,
            clock,
            Actor(user_id=None, role=ACTOR_ANONYMOUS),
            "auth.login_failed",
            "user",
            target_id=user.id if user is not None else None,
            details={"reason": "invalid_credentials"},
        )
        session.commit()  # das Audit des Fehlschlags muss trotz Fehlerantwort bestehen bleiben
        raise ApiError(401, "invalid_credentials", "Invalid username or password")

    now = clock.now()
    token = new_session_token()
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
    )
    principal = _principal(session, user, lookup)
    record_audit(
        session,
        clock,
        principal.actor,
        "auth.login",
        "user",
        target_id=user.id,
        subject_id=principal.subject_id,
    )
    session.commit()
    return LoginResult(principal, token, ttl_hours * 3600)


def authenticate(
    session: Session, clock: Clock, token: str | None, lookup: SubjectLookup | None = None
) -> Principal | None:
    """Gültige, nicht widerrufene, nicht abgelaufene Sitzung eines aktiven Kontos, sonst None."""
    if not token:
        return None
    auth_session = _find_session(session, token)
    if auth_session is None or auth_session.revoked_at is not None:
        return None
    if auth_session.expires_at <= clock.now():
        return None
    user = session.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        return None
    return _principal(session, user, lookup)


def logout(session: Session, clock: Clock, principal: Principal, token: str) -> None:
    auth_session = _find_session(session, token)
    if auth_session is not None and auth_session.revoked_at is None:
        auth_session.revoked_at = clock.now()
    record_audit(
        session,
        clock,
        principal.actor,
        "auth.logout",
        "user",
        target_id=principal.user_id,
        subject_id=principal.subject_id,
    )
    session.commit()
