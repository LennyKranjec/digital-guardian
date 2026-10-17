"""Betriebszustand (`/health`) und Meta-Angaben (`/meta`); Erweiterungen aus der Registry."""

from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine

from app import __version__
from app.core.db import db_state
from app.core.errors import ApiError
from app.core.settings import Settings
from app.registry import Registry


class HealthStatus(BaseModel):
    status: str
    db: str


def get_health(engine: Engine) -> HealthStatus:
    state = db_state(engine)
    if state == "unavailable":
        raise ApiError(503, "db_unavailable", "Database is not reachable")
    if state == "not_migrated":
        raise ApiError(
            503,
            "db_unavailable",
            "Database is not initialized - run python -m app.cli migrate",
        )
    return HealthStatus(status="ok", db="ok")


def get_meta(settings: Settings, registry: Registry) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "app_name": settings.app_name,
        "version": __version__,
        "demo_mode": settings.demo_mode,
        "synthetic_data": True,
        "roles": sorted(registry.roles),
        "challenge_loaded": bool(registry.routers or registry.meta_extensions),
    }
    for extension in registry.meta_extensions:
        for key, value in extension(settings).items():
            if key in meta:
                raise ValueError(f"meta extension must not override platform key {key!r}")
            meta[key] = value
    return meta
