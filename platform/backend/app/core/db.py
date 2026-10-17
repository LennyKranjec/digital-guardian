"""Datenbank-Engine (synchron, SQLAlchemy 2). Modelle: `app.persistence.models`."""

from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.exc import SQLAlchemyError

_SQLITE_PREFIX = "sqlite:///"


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(url: str) -> Engine:
    """Erzeugt die Engine; legt bei SQLite-Dateien das Verzeichnis an. Verbindet nicht.

    SQLite erzwingt Fremdschlüssel nur mit `PRAGMA foreign_keys=ON` je Verbindung.
    """
    if url.startswith(_SQLITE_PREFIX):
        raw = url.removeprefix(_SQLITE_PREFIX)
        if raw not in ("", ":memory:"):
            Path(raw).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


# Fehlen diese Kerntabellen, ist das Schema nicht initialisiert (F-T-303-02, api.md v1.4).
_CORE_TABLES = frozenset({"users", "auth_sessions", "audit_events"})


def db_state(engine: Engine) -> Literal["ok", "unavailable", "not_migrated"]:
    """Betriebszustand der DB: erreichbar und migriert, nicht erreichbar oder nicht migriert."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        names = set(inspect(engine).get_table_names())
    except SQLAlchemyError:
        return "unavailable"
    return "ok" if names >= _CORE_TABLES else "not_migrated"
