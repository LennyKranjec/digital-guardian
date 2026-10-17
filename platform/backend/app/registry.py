"""Erweiterungspunkte der Plattform. Ein Challenge-Paket füllt die Registry in `register(registry)`.

Nichts hier kennt eine Fachdomäne: Router, Rollen, Demo-Konten, Seed-Schritte, Meta-Felder,
Subjekt-Auflösung, Metadaten und Migrationsordner werden von außen registriert (docs/EXTENDING.md).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from sqlalchemy import MetaData
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.settings import Settings

SeedStep = Callable[[Session, Clock], None]
SubjectResolver = Callable[[Session, str], str | None]
MetaExtension = Callable[[Settings], dict[str, Any]]


@dataclass(frozen=True)
class DemoAccount:
    username: str
    password: str
    role: str
    label: str


@dataclass
class Registry:
    routers: list[APIRouter] = field(default_factory=list)
    roles: dict[str, str] = field(
        default_factory=lambda: {"admin": "Administration", "user": "Standardrolle"}
    )
    demo_accounts: list[DemoAccount] = field(default_factory=list)
    seed_steps: list[SeedStep] = field(default_factory=list)
    meta_extensions: list[MetaExtension] = field(default_factory=list)
    metadata: list[MetaData] = field(default_factory=list)
    migration_dirs: list[Path] = field(default_factory=list)
    subject_resolver: SubjectResolver | None = None

    def add_router(self, router: APIRouter) -> None:
        self.routers.append(router)

    def add_role(self, name: str, description: str) -> None:
        self.roles[name] = description

    def add_demo_account(self, account: DemoAccount) -> None:
        self.demo_accounts.append(account)

    def add_seed_step(self, step: SeedStep) -> None:
        self.seed_steps.append(step)

    def add_meta_extension(self, extension: MetaExtension) -> None:
        self.meta_extensions.append(extension)

    def add_metadata(self, metadata: MetaData, migrations: Path | None = None) -> None:
        self.metadata.append(metadata)
        if migrations is not None:
            self.migration_dirs.append(migrations)

    def set_subject_resolver(self, resolver: SubjectResolver) -> None:
        """`resolver(session, user_id)` liefert die Subjekt-ID des Kontos (oder `None`)."""
        self.subject_resolver = resolver

    def resolve_subject(self, session: Session, user_id: str) -> str | None:
        return self.subject_resolver(session, user_id) if self.subject_resolver else None
