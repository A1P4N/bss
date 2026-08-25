"""Tests for CandleBatch."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import CandleBatch


def _utc(y, m, d, h=0, mi=0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _candle(symbol: str, tf: Timeframe, open_dt: datetime, close_dt: datetime, cid_suffix: str = "") -> Candle:
    cid = f"cnd_{symbol}_{tf.value}_{open_dt.isoformat()}{cid_suffix}"
    return Candle(
        candle_id=CandleId(cid),
        instrument_id=f"inst_{symbol.lower()}",
        symbol=symbol,
        timeframe=tf,
        open_time=open_dt,
        close_time=close_dt,
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("99"),
        close=Decimal("104"),
        volume=Decimal("1000"),
    )


def _range() -> TimeRange:
    return TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))


class TestCandleBatchCreation:
    def test_valid_batch(self):
        rr = _range()
        candles = (
            _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 15)),
            _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 15), _utc(2025, 1, 1, 10, 30)),
        )
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=candles, source="binance", requested_range=rr)
        assert len(batch) == 2
        assert not batch.is_empty
        assert batch.first == candles[0]
        assert batch.last == candles[1]

    def test_empty_batch_allowed(self):
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=_range())
        assert batch.is_empty
        assert batch.first is None
        assert batch.last is None
        assert len(batch) == 0

    def test_frozen(self):
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=_range())
        with pytest.raises(dataclasses.FrozenInstanceError):
            batch.symbol = "BTCUSDT"  # type: ignore[misc]

    def test_empty_symbol_raises(self):
        with pytest.raises(ValueError, match="symbol"):
            CandleBatch(symbol="", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=_range())

    def test_empty_source_raises(self):
        with pytest.raises(ValueError, match="source"):
            CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="", requested_range=_range())

    def test_mismatched_symbol_raises(self):
        c = _candle("BTCUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 15))
        with pytest.raises(ValueError, match="symbol"):
            CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c,), source="binance", requested_range=_range())

    def test_mismatched_timeframe_raises(self):
        c = _candle("SOLUSDT", Timeframe.H1, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        with pytest.raises(ValueError, match="timeframe"):
            CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c,), source="binance", requested_range=_range())

    def test_not_sorted_raises(self):
        c1 = _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 15), _utc(2025, 1, 1, 10, 30))
        c2 = _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 15))
        with pytest.raises(ValueError, match="sorted"):
            CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c1, c2), source="binance", requested_range=_range())

    def test_duplicate_candle_id_allowed_but_detectable(self):
        # CandleBatch now allows duplicates for validation layer to detect (DuplicateDetector)
        dt = _utc(2025, 1, 1, 10, 0)
        c1 = _candle("SOLUSDT", Timeframe.M15, dt, _utc(2025, 1, 1, 10, 15))
        c2 = _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 15), _utc(2025, 1, 1, 10, 30))
        c2_dup = Candle(
            candle_id=c1.candle_id,
            instrument_id=c2.instrument_id,
            symbol=c2.symbol,
            timeframe=c2.timeframe,
            open_time=c2.open_time,
            close_time=c2.close_time,
            open=c2.open,
            high=c2.high,
            low=c2.low,
            close=c2.close,
            volume=c2.volume,
        )
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c1, c2_dup), source="binance", requested_range=_range())
        # batch creation succeeds; duplicate is detectable via DuplicateDetector
        from bss.historical_loader.domain.duplicate_detector import DuplicateDetector

        assert DuplicateDetector().has_duplicates(batch)


class TestCandleBatchSerialization:
    def test_roundtrip(self):
        rr = _range()
        candles = (
            _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 15)),
            _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 15), _utc(2025, 1, 1, 10, 30)),
        )
        b1 = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=candles, source="binance", requested_range=rr)
        d = b1.to_dict()
        b2 = CandleBatch.from_dict(d)
        assert b1 == b2

    def test_roundtrip_empty(self):
        b1 = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=_range())
        assert CandleBatch.from_dict(b1.to_dict()) == b1

    def test_to_dict_structure(self):
        b = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=_range())
        d = b.to_dict()
        assert d["symbol"] == "SOLUSDT"
        assert d["timeframe"] == "M15"
        assert "candles" in d
        assert "requested_range" in d

    def test_from_dict_with_offset(self):
        d = {
            "symbol": "SOLUSDT",
            "timeframe": "M15",
            "source": "binance",
            "requested_range": {"from": "2025-01-01T10:00:00+03:00", "to": "2025-01-01T11:00:00+03:00"},
            "candles": [],
        }
        b = CandleBatch.from_dict(d)
        assert b.requested_range.start.hour == 7  # 10+03 -> 07 UTC
