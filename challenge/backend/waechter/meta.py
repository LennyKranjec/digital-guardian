"""Erweiterung von `GET /api/v1/meta` (Vertrag v1.2, DR-009).

Liefert Serverzeit, Zeitzone und Inhaltsversionen.

Das Frontend rechnet relative Zeiten nur gegen `server_now` (Demo mit eingefrorener Uhr), nie gegen
die Browseruhr. `server_now` ist `APP_FROZEN_NOW`, sonst die aktuelle Zeit (Europe/Prague).
Regel- und Report-Version: aktive Versionen aus der Datenbank (T-09), sonst die der Dateien.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.core.settings import Settings
from waechter.content import ContentError, get_content
from waechter.models import ConfigVersion
from waechter.services import freetext
from waechter.timeutil import iso_prague

TIMEZONE = "Europe/Prague"


def _active_versions(settings: Settings) -> dict[str, str]:
    """Aktive Konfigurationsversionen aus der Datenbank (leer, wenn nicht erreichbar/migriert)."""
    engine = create_engine(settings.resolved_database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                select(ConfigVersion.kind, ConfigVersion.version).where(
                    ConfigVersion.active.is_(True)
                )
            )
            return {str(kind): str(version) for kind, version in rows}
    except SQLAlchemyError:
        return {}
    finally:
        engine.dispose()


def _versions(settings: Settings) -> dict[str, str | None]:
    try:
        content = get_content()
    except ContentError:
        content = None
    if content is None:
        return {"items": None, "rules": None, "report": None}
    active = _active_versions(settings)
    return {
        "items": content.items["version"],
        "rules": active.get("rules", content.rules["version"]),
        "report": active.get("report", content.report["version"]),
    }


def _content() -> Any:
    try:
        return get_content()
    except ContentError:
        return None


def waechter_meta(settings: Settings) -> dict[str, Any]:
    now = settings.app_frozen_now or datetime.now(UTC)
    return {
        "waechter": {
            "server_now": iso_prague(now),
            "timezone": TIMEZONE,
            "content_versions": _versions(settings),
            "free_text": freetext.features(_content(), settings.demo_mode),
        }
    }
