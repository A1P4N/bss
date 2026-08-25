"""Tests for GapDetector."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import CandleBatch
from bss.historical_loader.domain.gap_detector import GapDetector


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _candle(open_dt):
    close_dt = datetime.fromtimestamp(open_dt.timestamp() + 15 * 60, tz=timezone.utc)
    return Candle(candle_id=CandleId(f"cnd_SOLUSDT_M15_{open_dt.isoformat()}"), instrument_id="inst_sol", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=open_dt, close_time=close_dt, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))


def _range(s, e):
    return TimeRange(start=s, end=e)


class TestGapDetector:
    def setup_method(self):
        self.det = GapDetector()

    def test_no_gaps_contiguous(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        candles = tuple(_candle(_utc(2025, 1, 1, 10, m)) for m in [0, 15, 30, 45])
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=candles, source="binance", requested_range=rr)
        assert self.det.find_gaps(batch) == []
        assert self.det.expected_count(batch) == 4

    def test_missing_middle(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        candles = tuple(_candle(_utc(2025, 1, 1, 10, m)) for m in [0, 45])  # missing 15,30
        # This actually has two missing contiguous block 10:15-10:45 -> 2 candles
        # But our batch has 00 and 45, missing 15 and 30 -> one gap segment 10:15-10:45
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=candles, source="binance", requested_range=rr)
        gaps = self.det.find_gaps(batch)
        assert len(gaps) == 1
        assert gaps[0].missing_from == _utc(2025, 1, 1, 10, 15)
        assert gaps[0].missing_to == _utc(2025, 1, 1, 10, 45)
        assert gaps[0].expected_candles == 2
        # payload
        payload = gaps[0].to_data_integrity_gap_payload()
        assert payload["symbol"] == "SOLUSDT"
        assert payload["expected_candles"] == 2

    def test_missing_at_start(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        candles = tuple(_candle(_utc(2025, 1, 1, 10, m)) for m in [30, 45])
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=candles, source="binance", requested_range=rr)
        gaps = self.det.find_gaps(batch)
        assert gaps[0].missing_from == _utc(2025, 1, 1, 10, 0)

    def test_empty_batch_entire_range_gap(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=rr)
        gaps = self.det.find_gaps(batch)
        assert len(gaps) == 1
        assert gaps[0].expected_candles == 4
        assert gaps[0].actual_candles == 0

    def test_expected_count_partial_tail(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 30))  # 30m /15m =2
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=rr)
        assert self.det.expected_count(batch) == 2
        rr2 = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 20))  # 20m /15m =1 +1 tail =2
        batch2 = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=rr2)
        assert self.det.expected_count(batch2) == 2

    def test_multiple_gaps(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 12, 0))  # 2h =8 candles
        # provide 00, 45, 90? Let's provide 10:00 and 11:00 only
        candles = (_candle(_utc(2025, 1, 1, 10, 0)), _candle(_utc(2025, 1, 1, 11, 0)))
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=candles, source="binance", requested_range=rr)
        gaps = self.det.find_gaps(batch)
        # missing 10:15,10:30,10:45 and 11:15,11:30,11:45 -> two segments
        assert len(gaps) == 2
