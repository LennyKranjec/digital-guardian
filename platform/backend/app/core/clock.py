"""Injizierbare Uhr (architecture.md §8). `domains/**` bekommt `now` als Parameter."""

from datetime import UTC, datetime
from typing import Annotated, Protocol, cast

from fastapi import Depends, Request


class Clock(Protocol):
    def now(self) -> datetime:
        """Aktueller Zeitpunkt, UTC, tz-aware."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Feste Uhr für Tests/E2E (`APP_FROZEN_NOW`)."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware datetime")
        self._instant = instant.astimezone(UTC)

    def now(self) -> datetime:
        return self._instant


def get_clock(request: Request) -> Clock:
    """FastAPI-Dependency; Tests überschreiben sie über `app.dependency_overrides`."""
    return cast(Clock, request.app.state.clock)


ClockDep = Annotated[Clock, Depends(get_clock)]


def iso_z(instant: datetime) -> str:
    """UTC ISO 8601 mit `Z` (Vertragsformat für alle Zeitstempel)."""
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
