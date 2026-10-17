"""Zeit in `Europe/Prague` (Vertrag G-04) ohne `tzdata`-Abhängigkeit.

Windows liefert keine IANA-Zeitzonendaten und neue Abhängigkeiten sind nicht erlaubt. Es gilt die
EU-Sommerzeitregel (seit 1996): MESZ (+02:00) von letztem Sonntag im März 01:00 UTC bis letztem
Sonntag im Oktober 01:00 UTC, sonst MEZ (+01:00). Das Ergebnis ist eine Zeit mit festem Versatz.
"""

from datetime import UTC, date, datetime, timedelta, timezone

CET = timezone(timedelta(hours=1), "CET")
CEST = timezone(timedelta(hours=2), "CEST")


def _last_sunday(year: int, month: int) -> datetime:
    """Letzter Sonntag des Monats, 01:00 UTC (EU-Umstellzeitpunkt)."""
    nxt = datetime(year + (month == 12), month % 12 + 1, 1, 1, tzinfo=UTC)
    last_day = nxt - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() + 1) % 7)


def to_prague(instant: datetime) -> datetime:
    """Derselbe Zeitpunkt mit dem Versatz von Europe/Prague (CET/CEST)."""
    utc = instant.astimezone(UTC)
    summer = _last_sunday(utc.year, 3) <= utc < _last_sunday(utc.year, 10)
    return utc.astimezone(CEST if summer else CET)


def iso_prague(instant: datetime) -> str:
    """ISO 8601 mit Zeitzonenversatz, z. B. `2026-10-17T09:00:00+02:00`."""
    return to_prague(instant).isoformat(timespec="seconds")


def from_prague_local(local: datetime) -> datetime:
    """Ortszeit in Prag (naiv) → Zeitpunkt mit Versatz.

    Mehrdeutige Zeit beim Zurückstellen (Oktober, 02:00 bis 02:59): die frühere (MESZ). Nicht
    existierende Zeit beim Vorstellen (März, 02:00 bis 02:59): sie wird um eine Stunde nach vorn
    geschoben (also 03:xx MESZ), wie es Kalenderprogramme tun.
    """
    if local.tzinfo is not None:
        raise ValueError("local time must be naive")
    for offset in (CEST, CET):
        candidate = local.replace(tzinfo=offset)
        if to_prague(candidate).utcoffset() == offset.utcoffset(None):
            return candidate
    return to_prague(local.replace(tzinfo=CET))  # Lücke: nicht existierende Ortszeit


def prague_date(instant: datetime) -> date:
    """Kalendertag in Europe/Prague (G-04: ganze Tage = Differenz der Kalendertage)."""
    return to_prague(instant).date()


def days_between(earlier: datetime, later: datetime) -> int:
    """Ganze Kalendertage zwischen zwei Zeitpunkten in Prag (negativ, wenn `later` früher liegt)."""
    return (prague_date(later) - prague_date(earlier)).days
