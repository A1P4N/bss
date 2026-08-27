"""Unit: Binance mapper → Candle."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bss.domain.timeframe import Timeframe
from bss.historical_loader.infrastructure.sources.binance.mapper import map_binance_kline


def _kline(open_ms, open_s="100", high_s="101", low_s="99", close_s="100", vol_s="1000"):
    # Binance kline: [openTime, open, high, low, close, volume, closeTime, ...]
    return [open_ms, open_s, high_s, low_s, close_s, vol_s, open_ms + 900000, "0", 0, "0", "0", "0"]


def test_map_valid():
    # 2025-01-01 00:00 UTC = 1735689600000
    open_ms = int(datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    c = map_binance_kline(_kline(open_ms), "SOLUSDT", Timeframe.M15)
    assert c.symbol == "SOLUSDT"
    assert c.timeframe == Timeframe.M15
    assert c.open_time == datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert c.close_time == datetime(2025, 1, 1, 0, 15, tzinfo=timezone.utc)  # open + duration, not Binance closeTime
    assert c.open == Decimal("100")
    assert c.volume == Decimal("1000")


def test_timestamp_utc():
    open_ms = int(datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    c = map_binance_kline(_kline(open_ms), "SOLUSDT", Timeframe.M15)
    assert c.open_time.tzinfo == timezone.utc
    assert c.close_time.tzinfo == timezone.utc


def test_decimal_precision():
    open_ms = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    c = map_binance_kline(_kline(open_ms, open_s="100.12345678"), "SOLUSDT", Timeframe.M15)
    assert str(c.open) == "100.12345678"


def test_tail_candle_close_time():
    # For M15, close_time must be open + 15m, even if Binance closeTime is different
    open_ms = int(datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    k = _kline(open_ms)
    k[6] = open_ms + 1000  # Binance closeTime 1 sec after open, should be ignored
    c = map_binance_kline(k, "SOLUSDT", Timeframe.M15)
    assert c.close_time == datetime(2025, 1, 1, 10, 15, tzinfo=timezone.utc)


def test_invalid_payload_raises():
    with pytest.raises(ValueError):
        map_binance_kline([], "SOLUSDT", Timeframe.M15)
    with pytest.raises(ValueError):
        map_binance_kline([1, 2], "SOLUSDT", Timeframe.M15)
