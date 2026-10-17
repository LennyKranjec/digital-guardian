"""Europe/Prague ohne tzdata: Versatz und Umstellzeitpunkte 2026 (EU-Regel)."""

from datetime import UTC, datetime, timedelta

import pytest

from waechter.timeutil import from_prague_local, iso_prague, to_prague


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        (datetime(2026, 1, 15, 12, 0, tzinfo=UTC), "2026-01-15T13:00:00+01:00"),
        (datetime(2026, 7, 1, 12, 0, tzinfo=UTC), "2026-07-01T14:00:00+02:00"),
        (datetime(2026, 3, 29, 0, 59, tzinfo=UTC), "2026-03-29T01:59:00+01:00"),
        (datetime(2026, 3, 29, 1, 0, tzinfo=UTC), "2026-03-29T03:00:00+02:00"),
        (datetime(2026, 10, 25, 0, 59, tzinfo=UTC), "2026-10-25T02:59:00+02:00"),
        (datetime(2026, 10, 25, 1, 0, tzinfo=UTC), "2026-10-25T02:00:00+01:00"),
        (datetime(2026, 10, 17, 7, 0, tzinfo=UTC), "2026-10-17T09:00:00+02:00"),
    ],
)
def test_prague_offset_and_dst_switches(utc: datetime, expected: str) -> None:
    assert iso_prague(utc) == expected
    assert to_prague(utc) == utc  # derselbe Zeitpunkt, nur andere Darstellung


@pytest.mark.parametrize(
    ("local", "expected"),
    [
        (datetime(2026, 10, 24, 12, 0), "2026-10-24T12:00:00+02:00"),
        (datetime(2026, 10, 25, 1, 59), "2026-10-25T01:59:00+02:00"),
        (datetime(2026, 10, 25, 2, 30), "2026-10-25T02:30:00+02:00"),  # mehrdeutig ⇒ früher
        (datetime(2026, 10, 25, 3, 0), "2026-10-25T03:00:00+01:00"),  # Zeit nach dem Zurückstellen
        (datetime(2026, 10, 26, 9, 0), "2026-10-26T09:00:00+01:00"),
        (datetime(2026, 3, 28, 12, 0), "2026-03-28T12:00:00+01:00"),
        (datetime(2026, 3, 29, 1, 59), "2026-03-29T01:59:00+01:00"),
        (datetime(2026, 3, 29, 2, 30), "2026-03-29T03:30:00+02:00"),  # Lücke ⇒ nach vorn
        (datetime(2026, 3, 29, 3, 0), "2026-03-29T03:00:00+02:00"),
    ],
)
def test_from_prague_local_around_dst_switches(local: datetime, expected: str) -> None:
    assert from_prague_local(local).isoformat() == expected


def test_from_prague_local_rejects_aware_input() -> None:
    with pytest.raises(ValueError, match="naive"):
        from_prague_local(datetime(2026, 1, 1, tzinfo=UTC))


def test_from_prague_local_roundtrips_with_to_prague() -> None:
    start = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    for hour in range(0, 24 * 5):
        instant = start + timedelta(hours=hour)
        local = to_prague(instant).replace(tzinfo=None)
        if datetime(2026, 10, 25, 2, 0) <= local < datetime(2026, 10, 25, 3, 0):
            continue  # mehrdeutige Stunde: Rückweg liefert die frühere Variante
        assert from_prague_local(local) == instant
