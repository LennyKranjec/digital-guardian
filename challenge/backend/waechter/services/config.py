"""Aktive Konfiguration (`ConfigBundle`): Inhalte aus Dateien, Regeln/Report in aktiver Version.

`rules` und `report` liegen versioniert in `wa_config_versions` (Änderung ab T-04). Solange dort
nichts aktiv ist (Seed nicht gelaufen), gelten die geprüften Dateiinhalte.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from waechter.content import Content, ContentError, get_content
from waechter.models import ConfigVersion

logger = logging.getLogger("waechter.config")


def active_body(session: Session, kind: str) -> dict[str, Any] | None:
    row = session.scalar(
        select(ConfigVersion).where(ConfigVersion.kind == kind, ConfigVersion.active.is_(True))
    )
    return dict(row.body_json) if row is not None else None


def require_content() -> Content:
    """Geprüfter Inhalt oder 503 `content_unavailable` (Ordner fehlt)."""
    try:
        content = get_content()
    except ContentError as error:  # Inhalt nach dem Start beschädigt: kontrolliert, ohne Werte
        logger.error("content invalid: %d issue(s)", len(error.issues))
        raise ApiError(503, "content_unavailable", "Configuration content is not valid") from error
    if content is None:
        raise ApiError(503, "content_unavailable", "Configuration content is not available")
    return content


def get_bundle(session: Session) -> dict[str, Any]:
    content = require_content()
    return {
        "items": content.items,
        "regimens": content.regimens,
        "ctcae": content.ctcae,
        "rules": active_body(session, "rules") or content.rules,
        "report": active_body(session, "report") or content.report,
        "advice": content.advice,
        "medications": content.medications,
    }
