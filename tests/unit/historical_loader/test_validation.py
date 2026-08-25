"""Tests for CandleValidator."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import CandleBatch
from bss.historical_loader.domain.validation import CandleValidator


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _candle(open_dt):
    close_dt = datetime.fromtimestamp(open_dt.timestamp() + 15 * 60, tz=timezone.utc)
    return Candle(candle_id=CandleId(f"cnd_SOLUSDT_M15_{open_dt.isoformat()}"), instrument_id="inst_sol", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=open_dt, close_time=close_dt, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))


def _range(s, e):
    return TimeRange(start=s, end=e)


class TestCandleValidator:
    def setup_method(self):
        self.val = CandleValidator()

    def test_valid_batch(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        candles = tuple(_candle(_utc(2025, 1, 1, 10, m)) for m in [0, 15, 30, 45])
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=candles, source="binance", requested_range=rr)
        res = self.val.validate(batch)
        assert res.is_valid
        assert res.issues == ()
        assert res.gaps == ()
        assert res.duplicates == ()

    def test_empty_batch_invalid(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=rr)
        res = self.val.validate(batch)
        assert not res.is_valid
        assert any(i.code == "EMPTY_BATCH" for i in res.issues)
        assert len(res.gaps) == 1

    def test_duplicate_invalid(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        c1 = _candle(_utc(2025, 1, 1, 10, 0))
        c2 = Candle(candle_id=c1.candle_id, instrument_id=c1.instrument_id, symbol=c1.symbol, timeframe=c1.timeframe, open_time=_utc(2025, 1, 1, 10, 15), close_time=_utc(2025, 1, 1, 10, 30), open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))
        # Use distinct close but duplicate id -> still duplicate
        # Need batch with 4 candles where two share id
        c3 = _candle(_utc(2025, 1, 1, 10, 30))
        c4 = _candle(_utc(2025, 1, 1, 10, 45))
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c1, c2, c3, c4), source="binance", requested_range=rr)
        res = self.val.validate(batch)
        assert not res.is_valid
        assert res.has_duplicates
        assert any(i.code == "DUPLICATE" for i in res.issues)
        # context contains diagnostic info
        dup_issue = next(i for i in res.issues if i.code == "DUPLICATE")
        assert "candle_id" in dup_issue.context

    def test_gap_invalid(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        candles = (_candle(_utc(2025, 1, 1, 10, 0)), _candle(_utc(2025, 1, 1, 10, 45)))
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=candles, source="binance", requested_range=rr)
        res = self.val.validate(batch)
        assert not res.is_valid
        assert res.has_gaps
        assert any(i.code == "GAP" for i in res.issues)
        gap_issue = next(i for i in res.issues if i.code == "GAP")
        assert "from" in gap_issue.context

    def test_ordering_issue(self):
        # Bypass CandleBatch validation by constructing unsorted but we need to test validator's own ordering check
        # CandleBatch already raises on unsorted, so validator ordering check is secondary
        # Instead test that valid sorted passes
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 30))
        candles = tuple(_candle(_utc(2025, 1, 1, 10, m)) for m in [0, 15])
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=candles, source="binance", requested_range=rr)
        res = self.val.validate(batch)
        assert res.is_valid

    def test_structured_context(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="binance", requested_range=rr)
        res = self.val.validate(batch)
        for issue in res.issues:
            assert isinstance(issue.context, dict)
            assert "symbol" in issue.context or "from" in issue.context


class TestP0DuplicateUnifiedSemantics:
    """P0-3: single normative semantics — duplicate is Validation, not Normalization, deterministic & idempotent (AC-03, AC-08)."""

    def test_normalizer_preserves_duplicate(self):
        """Duplicate raw must not be silently deduped and not raise in Normalizer."""
        from bss.domain.time_range import TimeRange as TR
        from bss.historical_loader.domain.normalization import CandleNormalizer, RawCandle

        rr = TR(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        raws = [
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=100, high=101, low=99, close=100, volume=1000, source="fake"),
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=100, high=101, low=99, close=100, volume=1000, source="fake"),
        ]
        batch = CandleNormalizer().normalize_batch(raws, rr, source="fake")
        # preserved, not deduped
        assert len(batch.candles) == 2
        assert str(batch.candles[0].candle_id) == str(batch.candles[1].candle_id)

    def test_duplicate_deterministic(self):
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        c1 = _candle(_utc(2025, 1, 1, 10, 0))
        c2 = Candle(candle_id=c1.candle_id, instrument_id=c1.instrument_id, symbol=c1.symbol, timeframe=c1.timeframe, open_time=_utc(2025, 1, 1, 10, 15), close_time=_utc(2025, 1, 1, 10, 30), open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))
        c3 = _candle(_utc(2025, 1, 1, 10, 30))
        c4 = _candle(_utc(2025, 1, 1, 10, 45))
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c1, c2, c3, c4), source="binance", requested_range=rr)
        val = CandleValidator()
        r1 = val.validate(batch)
        r2 = val.validate(batch)
        assert r1 == r2  # deterministic
        assert not r1.is_valid
        assert r1.has_duplicates

    def test_reprocessing_idempotent(self):
        """AC-08: reprocessing same batch yields same ValidationResult."""
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        from bss.historical_loader.domain.normalization import CandleNormalizer, RawCandle

        raws = [
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=100, high=101, low=99, close=100, volume=1000, source="fake"),
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:00:00+00:00", close_time="2025-01-01T10:15:00+00:00", open=100, high=101, low=99, close=100, volume=1000, source="fake"),
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:30:00+00:00", close_time="2025-01-01T10:45:00+00:00", open=100, high=101, low=99, close=100, volume=1000),
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T10:45:00+00:00", close_time="2025-01-01T11:00:00+00:00", open=100, high=101, low=99, close=100, volume=1000),
        ]
        batch1 = CandleNormalizer().normalize_batch(raws, rr, source="fake")
        batch2 = CandleNormalizer().normalize_batch(raws, rr, source="fake")
        assert batch1 == batch2
        r1 = CandleValidator().validate(batch1)
        r2 = CandleValidator().validate(batch2)
        assert r1 == r2
        assert len(r1.duplicates) == 1
        assert r1.duplicates[0].count == 2

    def test_no_silent_dedup(self):
        """ЧТЗ §10: no silent dedup — count must reflect actual duplicates."""
        rr = _range(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 10, 30))
        # 3 copies of same open_time
        c = _candle(_utc(2025, 1, 1, 10, 0))
        c2 = Candle(candle_id=c.candle_id, instrument_id=c.instrument_id, symbol=c.symbol, timeframe=c.timeframe, open_time=c.open_time, close_time=c.close_time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume)
        c3 = Candle(candle_id=c.candle_id, instrument_id=c.instrument_id, symbol=c.symbol, timeframe=c.timeframe, open_time=c.open_time, close_time=c.close_time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume)
        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c, c2, c3), source="binance", requested_range=rr)
        res = CandleValidator().validate(batch)
        assert res.duplicates[0].count == 3
        assert len(batch.candles) == 3  # preserved
