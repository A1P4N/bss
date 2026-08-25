"""Tests for parse_utc Z handling (P1-01)."""

from datetime import timezone

import pytest

from bss.domain.time import parse_utc


def test_parse_utc_z():
    dt = parse_utc("2026-08-23T00:15:00Z")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 0
    assert dt.minute == 15


def test_parse_utc_z_millis():
    dt = parse_utc("2026-08-23T00:15:00.123Z")
    assert dt.tzinfo == timezone.utc
    assert dt.microsecond == 123000


def test_parse_utc_z_lowercase():
    dt = parse_utc("2026-08-23T00:15:00z")
    assert dt.tzinfo == timezone.utc


def test_parse_utc_offset_still_works():
    dt = parse_utc("2025-01-01T10:00:00+03:00")
    assert dt.hour == 7


def test_parse_utc_naive_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_utc("2025-01-01T10:00:00")


def test_candle_from_dict_z():
    from bss.domain.candle import Candle

    d = {
        "candle_id": "cnd_test",
        "instrument_id": "inst",
        "symbol": "SOLUSDT",
        "timeframe": "M15",
        "open_time": "2026-08-23T00:15:00Z",
        "close_time": "2026-08-23T00:30:00Z",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100",
        "volume": "1000",
    }
    c = Candle.from_dict(d)
    assert c.open_time.tzinfo == timezone.utc
