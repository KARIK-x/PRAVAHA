"""Timestamp parsing and normalization.

All stored timestamps are UTC ISO-8601 strings. Nepal-local display uses
Asia/Kathmandu (UTC+5:45, no DST). Publication time and retrieval time are
always stored separately; a missing or unparseable timestamp is NULL, never
zero or "now" (Part 17/18 of the specification).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

KATHMANDU = timezone(timedelta(hours=5, minutes=45), name="Asia/Kathmandu")
UTC = timezone.utc

_ISO_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def parse_timestamp(value: object) -> datetime | None:
    """Parse RSS RFC-822 dates, ISO-8601 strings, or datetime objects.

    Returns an aware datetime in UTC, or None when parsing fails. Naive
    inputs are assumed to be Asia/Kathmandu (the dominant case for Nepali
    sources) and this assumption is documented in DATA_DICTIONARY.md.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if not s:
            return None
        dt = None
        # RFC 822 (RSS pubDate)
        try:
            dt = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            dt = None
        if dt is None:
            s2 = s.replace("Z", "+00:00") if s.endswith("Z") else s
            try:
                dt = datetime.fromisoformat(s2)
            except ValueError:
                for fmt in _ISO_FORMATS:
                    try:
                        dt = datetime.strptime(s, fmt)
                        break
                    except ValueError:
                        continue
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KATHMANDU)
    return dt.astimezone(UTC)


def to_utc_iso(value: object) -> str | None:
    """Normalize any supported timestamp input to a UTC ISO-8601 string."""
    dt = parse_timestamp(value)
    return dt.isoformat() if dt else None


def to_kathmandu(dt: datetime) -> datetime:
    """Convert an aware datetime to Asia/Kathmandu for display."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(KATHMANDU)


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_utc_iso() -> str:
    return now_utc().isoformat()


def is_sane_publication_time(dt: datetime, *, reference: datetime | None = None,
                             max_future_skew_hours: float = 6.0) -> bool:
    """Reject implausible publication times (far future, pre-1994 NEPSE era)."""
    ref = reference or now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    if dt > ref + timedelta(hours=max_future_skew_hours):
        return False
    if dt.year < 1994:  # NEPSE opened its modern trading floor in Jan 1994
        return False
    return True
