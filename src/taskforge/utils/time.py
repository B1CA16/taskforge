"""UTC time helpers. TaskForge stores and compares every timestamp in UTC."""

import datetime


def utcnow() -> datetime.datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.datetime.now(datetime.timezone.utc)


def ensure_utc(value: datetime.datetime | None) -> datetime.datetime | None:
    """Return `value` as an aware UTC datetime.

    Naive datetimes are assumed to already be in UTC (that's how TaskForge
    stores them on backends without timezone support, such as SQLite).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)
