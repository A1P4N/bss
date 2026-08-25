"""UTC helpers — single source of truth for time parsing."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_utc(iso_str: str) -> datetime:
    """Parse ISO 8601 and convert to UTC (requires tz-aware input).

    Supports 'Z' suffix as used in Event Model v0.2 examples
    (e.g. 2026-08-23T00:15:00Z) and fractional seconds.
    """
    s = iso_str.strip()
    # Replace Z/z with +00:00 for fromisoformat compatibility
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


def ensure_utc(dt: datetime, field: str = "timestamp") -> None:
    """Validate that dt is timezone-aware UTC (offset == 0)."""
    if dt.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware UTC, got naive {dt!r}")
    # normalize and check offset is zero — allows +00:00 only
    if dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
        # also accept if astimezone would change value — we require caller to pass UTC
        raise ValueError(f"{field} must be UTC, got {dt.isoformat()} (offset {dt.utcoffset()})")
