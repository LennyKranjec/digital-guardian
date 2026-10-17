"""Plattform-Einstellungen aus Umgebung/`.env`; Challenge-Pakete erweitern per Vererbung."""

from datetime import datetime
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parents[1]
_SQLITE_PREFIX = "sqlite:///"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_name: str = "rakathon-platform"
    app_env: str = "development"
    demo_mode: bool = True
    database_url: str = "sqlite:///data/app.db"
    log_level: str = "INFO"
    #: Ordner des Challenge-Pakets (`backend/plugin.py` wird, falls vorhanden, geladen)
    challenge_dir: Path = REPO_ROOT / "challenge"

    app_frozen_now: datetime | None = None
    session_cookie_secure: bool = False
    session_ttl_hours: int = Field(default=12, ge=1, le=168)

    @field_validator("log_level")
    @classmethod
    def _log_level_known(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")
        return normalized

    @model_validator(mode="after")
    def _frozen_clock_never_in_production(self) -> Self:
        if self.app_env.lower() == "production" and self.app_frozen_now is not None:
            raise ValueError("APP_FROZEN_NOW is not allowed when APP_ENV=production")
        if self.app_frozen_now is not None and self.app_frozen_now.tzinfo is None:
            raise ValueError("APP_FROZEN_NOW must carry a timezone, e.g. 2026-10-14T08:00:00Z")
        return self

    @property
    def resolved_database_url(self) -> str:
        """Relative SQLite-Pfade werden gegen `platform/backend/` aufgelöst (unabhängig vom cwd)."""
        if not self.database_url.startswith(_SQLITE_PREFIX):
            return self.database_url
        raw = self.database_url.removeprefix(_SQLITE_PREFIX)
        if raw in ("", ":memory:") or Path(raw).is_absolute():
            return self.database_url
        return f"{_SQLITE_PREFIX}{(BACKEND_DIR / raw).as_posix()}"
