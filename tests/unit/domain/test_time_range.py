"""Tests for TimeRange value object."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from bss.domain import TimeRange, Timeframe


def _utc(y: int, m: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


class TestTimeRangeCreation:
    """Construction and basic invariants."""

    def test_valid_range(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
        assert tr.start == _utc(2025, 1, 1)
        assert tr.end == _utc(2025, 1, 2)

    def test_naive_start_raises(self) -> None:
        with pytest.raises(ValueError, match="start.*timezone-aware"):
            TimeRange(
                start=datetime(2025, 1, 1),
                end=_utc(2025, 1, 2),
            )

    def test_naive_end_raises(self) -> None:
        with pytest.raises(ValueError, match="end.*timezone-aware"):
            TimeRange(
                start=_utc(2025, 1, 1),
                end=datetime(2025, 1, 2),
            )

    def test_start_after_end_raises(self) -> None:
        with pytest.raises(ValueError, match="start.*before.*end"):
            TimeRange(start=_utc(2025, 1, 2), end=_utc(2025, 1, 1))

    def test_start_equals_end_raises(self) -> None:
        with pytest.raises(ValueError, match="start.*before.*end"):
            TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 1))

    def test_immutable(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
        with pytest.raises(Exception):
            tr.start = _utc(2025, 2, 1)  # type: ignore[misc]


class TestTimeRangeContains:
    """contains() boundary semantics."""

    def test_start_inclusive(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        assert tr.contains(_utc(2025, 1, 1, 10, 0))

    def test_end_exclusive(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        assert not tr.contains(_utc(2025, 1, 1, 11, 0))

    def test_midpoint(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        assert tr.contains(_utc(2025, 1, 1, 10, 30))

    def test_before_start(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        assert not tr.contains(_utc(2025, 1, 1, 9, 59))


class TestTimeRangeOverlaps:
    """overlaps() semantics."""

    def test_overlapping(self) -> None:
        a = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 12, 0))
        b = TimeRange(start=_utc(2025, 1, 1, 11, 0), end=_utc(2025, 1, 1, 13, 0))
        assert a.overlaps(b)

    def test_non_overlapping(self) -> None:
        a = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        b = TimeRange(start=_utc(2025, 1, 1, 11, 0), end=_utc(2025, 1, 1, 12, 0))
        assert not a.overlaps(b)  # [10,11) and [11,12) — adjacent, no overlap

    def test_contained(self) -> None:
        outer = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 14, 0))
        inner = TimeRange(start=_utc(2025, 1, 1, 11, 0), end=_utc(2025, 1, 1, 12, 0))
        assert outer.overlaps(inner)
        assert inner.overlaps(outer)


class TestTimeRangeDuration:
    def test_duration(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
        assert tr.duration() == timedelta(days=1)

    def test_duration_hours(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 14, 30))
        assert tr.duration() == timedelta(hours=4, minutes=30)


class TestTimeRangeSplit:
    """split_by_timeframe chunking."""

    def test_split_m15_one_hour(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        chunks = tr.split_by_timeframe(Timeframe.M15)
        assert len(chunks) == 4
        base = _utc(2025, 1, 1, 10, 0)
        for i, chunk in enumerate(chunks):
            assert chunk.start == base + timedelta(minutes=15 * i)
            assert chunk.end == base + timedelta(minutes=15 * (i + 1))

    def test_split_h1_partial(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 30))
        chunks = tr.split_by_timeframe(Timeframe.H1)
        assert len(chunks) == 2
        assert chunks[0].end == _utc(2025, 1, 1, 11, 0)
        assert chunks[1].end == _utc(2025, 1, 1, 11, 30)
        assert chunks[1].start == _utc(2025, 1, 1, 11, 0)

    def test_split_d1_single_chunk(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
        chunks = tr.split_by_timeframe(Timeframe.D1)
        assert len(chunks) == 1

    def test_split_empty_on_negative_duration(self) -> None:
        with pytest.raises(ValueError):
            TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 0))


class TestTimeRangeSerialization:
    """to_tuple / from_tuple roundtrip."""

    def test_roundtrip(self) -> None:
        tr1 = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 18, 30))
        tup = tr1.to_tuple()
        tr2 = TimeRange.from_tuple(*tup)
        assert tr1 == tr2

    def test_tuple_types(self) -> None:
        tr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
        s, e = tr.to_tuple()
        assert isinstance(s, str)
        assert isinstance(e, str)