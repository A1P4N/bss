"""Tests for CandleNormalizer."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.errors import NormalizationError
from bss.historical_loader.domain.normalization import CandleNormalizer, RawCandle


def _utc(y, m, d, h=0, mi=0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _range() -> TimeRange:
    return TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))


class TestNormalizeSingle:
    def setup_method(self):
        self.norm = CandleNormalizer()

    def test_valid_dict(self):
        raw = RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open="100", high="105", low="99", close="104", volume="1000", source="binance")
        c = self.norm.normalize(raw)
        assert c.symbol == "SOLUSDT"
        assert c.timeframe == Timeframe.M15
        assert c.open == Decimal("100")
        assert c.open_time.tzinfo is not None

    def test_offset_converts_to_utc(self):
        raw = RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+03:00", close_time="2025-01-01T10:15:00+03:00", open=100, high=105, low=99, close=104, volume=1000)
        c = self.norm.normalize(raw)
        assert c.open_time.hour == 7  # 10+03 -> 07 UTC
        assert c.open_time.tzinfo == timezone.utc

    def test_datetime_input(self):
        raw = RawCandle(symbol="SOLUSDT", timeframe="M15", open_time=_utc(2025, 1, 1, 10, 0), close_time=_utc(2025, 1, 1, 10, 15), open=Decimal("100"), high=Decimal("105"), low=Decimal("99"), close=Decimal("104"), volume=Decimal("1000"))
        c = self.norm.normalize(raw)
        assert c.open_time == _utc(2025, 1, 1, 10, 0)

    def test_naive_raises(self):
        raw = RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00", close_time="2025-01-01T10:15:00+00:00", open=100, high=105, low=99, close=104, volume=1000)
        with pytest.raises(NormalizationError) as exc:
            self.norm.normalize(raw)
        assert exc.value.code == "INVALID_TIMESTAMP"
        assert "open_time" in exc.value.context["field"]

    def test_invalid_timeframe_raises(self):
        raw = RawCandle(symbol="SOLUSDT", timeframe="M13", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=100, high=105, low=99, close=104, volume=1000)
        with pytest.raises(NormalizationError) as exc:
            self.norm.normalize(raw)
        assert exc.value.code == "INVALID_TIMEFRAME"

    def test_ohlc_invalid_raises(self):
        raw = RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=200, high=105, low=99, close=104, volume=1000)
        with pytest.raises(NormalizationError) as exc:
            self.norm.normalize(raw)
        assert exc.value.code == "INVALID_CANDLE"

    def test_float_decimal_precision(self):
        raw = RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=100.1, high=100.1, low=100.1, close=100.1, volume=0.1)
        c = self.norm.normalize(raw)
        assert isinstance(c.open, Decimal)
        assert str(c.open) == "100.1"

    def test_normalize_dict(self):
        d = {"symbol": "SOLUSDT", "timeframe": "M15", "open_time": "2025-01-01T10:00:00+00:00", "close_time": "2025-01-01T10:15:00+00:00", "open": "100", "high": "105", "low": "99", "close": "104", "volume": "1000"}
        c = self.norm.normalize_dict(d)
        assert c.symbol == "SOLUSDT"


class TestNormalizeBatch:
    def setup_method(self):
        self.norm = CandleNormalizer()

    def test_batch_sorted(self):
        rr = _range()
        raws = [
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:30:00+00:00", close_time="2025-01-01T10:45:00+00:00", open=100, high=101, low=99, close=100, volume=1000),
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=100, high=101, low=99, close=100, volume=1000),
        ]
        batch = self.norm.normalize_batch(raws, rr, source="binance")
        assert batch.candles[0].open_time == _utc(2025, 1, 1, 10, 0)
        assert batch.candles[1].open_time == _utc(2025, 1, 1, 10, 30)

    def test_batch_mismatched_symbol_raises(self):
        rr = _range()
        raws = [
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=100, high=101, low=99, close=100, volume=1000),
            RawCandle(symbol="BTCUSDT", timeframe="M15", open_time="2025-01-01T10:15:00+00:00", close_time="2025-01-01T10:30:00+00:00", open=100, high=101, low=99, close=100, volume=1000),
        ]
        with pytest.raises(NormalizationError) as exc:
            self.norm.normalize_batch(raws, rr, source="binance")
        assert exc.value.code == "MISMATCHED_SYMBOL"

    def test_batch_duplicate_is_validation_not_normalization(self):
        """P0-3 unified semantics: duplicate is Validation, not NormalizationError (AC-03/AC-08)."""
        rr = _range()
        raws = [
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=100, high=101, low=99, close=100, volume=1000),
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=100, high=101, low=99, close=100, volume=1000),
        ]
        # Normalizer must NOT raise — passes to CandleBatch with duplicates
        batch = self.norm.normalize_batch(raws, rr, source="binance")
        assert len(batch.candles) == 2
        # Duplicate is caught by DuplicateDetector / Validator, not Normalizer (no silent dedup)
        from bss.historical_loader.domain.duplicate_detector import DuplicateDetector
        from bss.historical_loader.domain.validation import CandleValidator

        assert DuplicateDetector().has_duplicates(batch)
        res = CandleValidator().validate(batch)
        assert not res.is_valid
        assert any(i.code == "DUPLICATE" for i in res.issues)
        # deterministic: second validation equal
        res2 = CandleValidator().validate(batch)
        assert res == res2
        # idempotent re-normalization gives same result
        batch2 = self.norm.normalize_batch(raws, rr, source="binance")
        assert batch == batch2

    def test_empty_batch_raises(self):
        rr = _range()
        with pytest.raises(NormalizationError) as exc:
            self.norm.normalize_batch([], rr, source="binance")
        assert exc.value.code == "EMPTY_BATCH_NO_CONTEXT"
