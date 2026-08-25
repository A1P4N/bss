"""Tests for DuplicateDetector."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import CandleBatch
from bss.historical_loader.domain.duplicate_detector import DuplicateDetector


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _candle(symbol, tf, open_dt, close_dt, cid=None):
    cid = cid or f"cnd_{symbol}_{tf.value}_{open_dt.isoformat()}"
    return Candle(candle_id=CandleId(cid), instrument_id=f"inst_{symbol.lower()}", symbol=symbol, timeframe=tf, open_time=open_dt, close_time=close_dt, open=Decimal("100"), high=Decimal("105"), low=Decimal("99"), close=Decimal("104"), volume=Decimal("1000"))


def _range():
    return TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))


class TestDuplicateDetector:
    def setup_method(self):
        self.det = DuplicateDetector()

    def test_no_duplicates(self):
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(_candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 15)), _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 15), _utc(2025, 1, 1, 10, 30))), source="binance", requested_range=_range())
        assert self.det.find_duplicates(batch) == []
        assert not self.det.has_duplicates(batch)

    def test_duplicate_by_id(self):
        c1 = _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 15), cid="dup_id")
        c2 = Candle(candle_id=CandleId("dup_id"), instrument_id="inst_sol", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=_utc(2025, 1, 1, 10, 15), close_time=_utc(2025, 1, 1, 10, 30), open=Decimal("100"), high=Decimal("105"), low=Decimal("99"), close=Decimal("104"), volume=Decimal("1000"))
        # bypass CandleBatch uniqueness check by creating via direct duplicate? CandleBatch would raise, so test detector on pre-validated batch via manual construction
        # Instead test detector logic with batch that has same open_time duplicate via time key
        # Create batch with two candles same open_time but different id (time duplicate)
        c3 = _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 15))
        # Need to circumvent CandleBatch sorted unique check: use different close but same open -> will still raise sorted? No, open same -> not strictly increasing -> CandleBatch raises. So we test DuplicateDetector directly on a batch constructed with validation disabled? Skip this case, test via empty.
        # Instead test simple duplicate via id with different open_time but same id (still duplicate)
        # That will pass CandleBatch sorted check if open times differ
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c1, c2), source="binance", requested_range=_range())
        dups = self.det.find_duplicates(batch)
        assert len(dups) == 1
        assert dups[0].count == 2
        assert dups[0].candle_id == "dup_id"

    def test_empty_batch(self):
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=_range())
        assert self.det.find_duplicates(batch) == []

    def test_three_copies(self):
        c1 = _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 15), cid="dup")
        c2 = Candle(candle_id=CandleId("dup"), instrument_id="inst", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=_utc(2025, 1, 1, 10, 15), close_time=_utc(2025, 1, 1, 10, 30), open=Decimal("100"), high=Decimal("105"), low=Decimal("99"), close=Decimal("104"), volume=Decimal("1000"))
        c3 = Candle(candle_id=CandleId("dup"), instrument_id="inst", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=_utc(2025, 1, 1, 10, 30), close_time=_utc(2025, 1, 1, 10, 45), open=Decimal("100"), high=Decimal("105"), low=Decimal("99"), close=Decimal("104"), volume=Decimal("1000"))
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c1, c2, c3), source="binance", requested_range=_range())
        dups = self.det.find_duplicates(batch)
        assert dups[0].count == 3

    def test_sorted_result(self):
        # two duplicate groups
        c1 = _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 15), cid="a")
        c2 = Candle(candle_id=CandleId("a"), instrument_id="inst", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=_utc(2025, 1, 1, 10, 15), close_time=_utc(2025, 1, 1, 10, 30), open=Decimal("100"), high=Decimal("105"), low=Decimal("99"), close=Decimal("104"), volume=Decimal("1000"))
        c3 = _candle("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 30), _utc(2025, 1, 1, 10, 45), cid="b")
        c4 = Candle(candle_id=CandleId("b"), instrument_id="inst", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=_utc(2025, 1, 1, 10, 45), close_time=_utc(2025, 1, 1, 11, 0), open=Decimal("100"), high=Decimal("105"), low=Decimal("99"), close=Decimal("104"), volume=Decimal("1000"))
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c1, c2, c3, c4), source="binance", requested_range=TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 12, 0)))
        dups = self.det.find_duplicates(batch)
        assert dups[0].open_time < dups[1].open_time
