"""Integration: FakeSource → normalize → validate."""

from __future__ import annotations

from datetime import datetime, timezone

from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.normalization import CandleNormalizer, RawCandle
from bss.historical_loader.domain.validation import CandleValidator


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _fake_raws(start, end, timeframe=Timeframe.M15, symbol="SOLUSDT", missing=None):
    """Generate RawCandle dicts mimicking HistoricalSource download."""
    from datetime import timedelta

    missing = set(missing or [])
    raws = []
    cursor = start
    interval = timedelta(minutes=timeframe.duration_minutes())
    while cursor < end:
        if cursor not in missing:
            raws.append(
                RawCandle(
                    symbol=symbol,
                    timeframe=timeframe.value,
                    open_time=cursor.isoformat(),
                    close_time=(cursor + interval).isoformat(),
                    open="100",
                    high="101",
                    low="99",
                    close="100",
                    volume="1000",
                    source="fake",
                )
            )
        cursor += interval
    return raws


class TestNormalizeValidateIntegration:
    def setup_method(self):
        self.norm = CandleNormalizer()
        self.val = CandleValidator()

    def test_happy_path(self):
        rr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        raws = _fake_raws(rr.start, rr.end)
        batch = self.norm.normalize_batch(raws, rr, source="fake")
        res = self.val.validate(batch)
        assert res.is_valid
        assert len(batch.candles) == 4

    def test_gap_detected(self):
        rr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        missing = {_utc(2025, 1, 1, 10, 15)}
        raws = _fake_raws(rr.start, rr.end, missing=missing)
        batch = self.norm.normalize_batch(raws, rr, source="fake")
        res = self.val.validate(batch)
        assert not res.is_valid
        assert res.has_gaps

    def test_utc_offset_normalized_no_false_gap(self):
        # raw with +03:00 should not create false gaps
        rr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        raws = [
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T13:00:00+03:00", close_time="2025-01-01T13:15:00+03:00", open=100, high=101, low=99, close=100, volume=1000),
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T13:15:00+03:00", close_time="2025-01-01T13:30:00+03:00", open=100, high=101, low=99, close=100, volume=1000),
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T13:30:00+03:00", close_time="2025-01-01T13:45:00+03:00", open=100, high=101, low=99, close=100, volume=1000),
            RawCandle(symbol="SOLUSDT", timeframe="M15", open_time="2025-01-01T13:45:00+03:00", close_time="2025-01-01T14:00:00+03:00", open=100, high=101, low=99, close=100, volume=1000),
        ]
        batch = self.norm.normalize_batch(raws, rr, source="fake")
        res = self.val.validate(batch)
        assert res.is_valid

    def test_duplicate_via_normalizer(self):
        rr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        raws = _fake_raws(rr.start, rr.end)
        raws.append(raws[0])  # duplicate first
        try:
            batch = self.norm.normalize_batch(raws, rr, source="fake")
            # if not raised, validator should catch
            res = self.val.validate(batch)
            assert not res.is_valid
        except Exception as e:
            assert "DUPLICATE" in str(e) or "duplicate" in str(e).lower()

    def test_empty_batch(self):
        rr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
        from bss.historical_loader.domain.dataset import CandleBatch

        batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(), source="fake", requested_range=rr)
        res = self.val.validate(batch)
        assert not res.is_valid
        assert any(i.code == "EMPTY_BATCH" for i in res.issues)
