"""TimeRange — a half-open [start, end) UTC time interval."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from typing import Iterator, List, Tuple

from .timeframe import Timeframe


@dataclasses.dataclass(frozen=True)
class TimeRange:
    """A half-open interval [start, end) in UTC.

    *start* is inclusive, *end* is exclusive.
    Both timestamps must be timezone-aware UTC.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None:
            raise ValueError("start must be timezone-aware, got naive")
        if self.end.tzinfo is None:
            raise ValueError("end must be timezone-aware, got naive")
        if self.start >= self.end:
            raise ValueError(
                f"start ({self.start}) must be before end ({self.end})"
            )

    # ── query ──────────────────────────────────────────────────

    def contains(self, timestamp: datetime) -> bool:
        """Check if *timestamp* falls inside [start, end)."""
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return self.start <= timestamp < self.end

    def overlaps(self, other: TimeRange) -> bool:
        """Check if this range overlaps with *other*."""
        return self.start < other.end and other.start < self.end

    def duration(self) -> timedelta:
        """Return the total duration."""
        return self.end - self.start

    # ── splitting ──────────────────────────────────────────────

    def split_by_timeframe(self, tf: Timeframe) -> List[TimeRange]:
        """Split this range into contiguous chunks of *tf* duration.

        Returns a list of non-overlapping TimeRange instances.
        """
        chunk_minutes = tf.duration_minutes()
        chunk_delta = timedelta(minutes=chunk_minutes)
        result: List[TimeRange] = []

        cursor = self.start
        while cursor < self.end:
            chunk_end = min(cursor + chunk_delta, self.end)
            result.append(TimeRange(start=cursor, end=chunk_end))
            cursor = chunk_end

        return result

    # ── serialisation ──────────────────────────────────────────

    def to_tuple(self) -> Tuple[str, str]:
        """Return (start_iso, end_iso) string tuple."""
        return (self.start.isoformat(), self.end.isoformat())

    @classmethod
    def from_tuple(cls, start_iso: str, end_iso: str) -> TimeRange:
        """Create from ISO strings."""
        return cls(
            start=datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc),
            end=datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc),
        )

    def __repr__(self) -> str:
        return f"TimeRange({self.start.isoformat()}, {self.end.isoformat()})"