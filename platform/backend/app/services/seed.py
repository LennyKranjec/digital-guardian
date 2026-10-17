"""Seed: neutrale, synthetische Demo-Konten der Plattform plus die registrierten Seed-Schritte.

Idempotent: vorhandene Konten bleiben unverändert. Nur mit `DEMO_MODE` (sonst 404-artige Ablehnung).
"""

from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError
from app.core.security import hash_password
from app.core.settings import Settings
from app.persistence.models import User
from app.registry import DemoAccount, Registry

DEMO_PASSWORD: Final = "demo-passwort-2026"  # noqa: S105 - öffentlich dokumentiertes Demo-Passwort

PLATFORM_ACCOUNTS: Final = (
    DemoAccount("admin", DEMO_PASSWORD, "admin", "Admin (Demo)"),
    DemoAccount("user", DEMO_PASSWORD, "user", "Nutzer:in (Demo)"),
)


def all_demo_accounts(registry: Registry) -> list[DemoAccount]:
    return [*PLATFORM_ACCOUNTS, *registry.demo_accounts]


def provision(session: Session, settings: Settings, registry: Registry, clock: Clock) -> None:
    if not settings.demo_mode:
        raise ApiError(404, "not_found", "Not found")
    for account in all_demo_accounts(registry):
        if account.role not in registry.roles:
            raise ValueError(f"demo account {account.username!r} uses unregistered role")
        exists = session.scalar(select(User.id).where(User.username == account.username))
        if exists is None:
            session.add(
                User(
                    username=account.username,
                    display_name=account.label,
                    role_name=account.role,
                    password_hash=hash_password(account.password),
                    created_at=clock.now(),
                )
            )
    session.flush()
    for step in registry.seed_steps:
        step(session, clock)
    session.commit()
