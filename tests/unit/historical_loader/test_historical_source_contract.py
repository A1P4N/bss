"""Tests for HistoricalSource and HistoricalSpreadSource contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import CandleBatch
from bss.historical_loader.domain.interfaces.historical_source import HistoricalSource
from bss.historical_loader.domain.interfaces.historical_spread_source import HistoricalSpreadSource


def _utc(y, m, d, h=0, mi=0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _candle(symbol: str, tf: Timeframe, open_dt: datetime) -> Candle:
    close_dt = datetime.fromtimestamp(open_dt.timestamp() + tf.duration_minutes() * 60, tz=timezone.utc)
    return Candle(
        candle_id=CandleId(f"cnd_{symbol}_{tf.value}_{open_dt.isoformat()}"),
        instrument_id=f"inst_{symbol.lower()}",
        symbol=symbol,
        timeframe=tf,
        open_time=open_dt,
        close_time=close_dt,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("1000"),
    )


class FakeSource:
    """Minimal deterministic fake for contract tests."""

    def available_range(self, symbol: str, timeframe: Timeframe) -> TimeRange:
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty")
        return TimeRange(start=_utc(2024, 1, 1), end=_utc(2024, 12, 31))

    def download(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime) -> CandleBatch:
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start/end must be timezone-aware")
        if start >= end:
            raise ValueError("start must be before end")
        # generate deterministic candles aligned to timeframe
        rr = TimeRange(start=start, end=end)
        # simple: one candle per timeframe interval
        candles = []
        cursor = start
        while cursor < end:
            from datetime import timedelta

            close = cursor + timedelta(minutes=timeframe.duration_minutes())
            if close > end:
                break
            candles.append(_candle(symbol, timeframe, cursor))
            cursor = close
        return CandleBatch(symbol=symbol, timeframe=timeframe, candles=tuple(candles), source="fake", requested_range=rr)


class TestHistoricalSourceProtocol:
    def test_fake_implements_protocol(self):
        fake = FakeSource()
        assert isinstance(fake, HistoricalSource)

    def test_available_range_returns_time_range(self):
        fake = FakeSource()
        tr = fake.available_range("SOLUSDT", Timeframe.M15)
        assert isinstance(tr, TimeRange)
        assert tr.start.tzinfo is not None

    def test_available_range_empty_symbol_raises(self):
        fake = FakeSource()
        with pytest.raises(ValueError, match="symbol"):
            fake.available_range("", Timeframe.M15)

    def test_download_returns_batch(self):
        fake = FakeSource()
        batch = fake.download("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
        assert isinstance(batch, CandleBatch)
        assert batch.symbol == "SOLUSDT"
        assert batch.timeframe == Timeframe.M15
        assert len(batch) == 4  # 1h /15m =4

    def test_download_idempotent(self):
        fake = FakeSource()
        s, e = _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0)
        b1 = fake.download("SOLUSDT", Timeframe.M15, s, e)
        b2 = fake.download("SOLUSDT", Timeframe.M15, s, e)
        assert b1 == b2

    def test_download_naive_raises(self):
        fake = FakeSource()
        with pytest.raises(ValueError, match="timezone-aware"):
            fake.download("SOLUSDT", Timeframe.M15, datetime(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))

    def test_download_start_after_end_raises(self):
        fake = FakeSource()
        with pytest.raises(ValueError, match="start.*before.*end"):
            fake.download("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1, 11, 0), _utc(2025, 1, 1, 10, 0))

    def test_download_no_overlap_with_future(self):
        # batch requested_range must equal requested range, not future data
        fake = FakeSource()
        batch = fake.download("SOLUSDT", Timeframe.H1, _utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 12, 0))
        assert batch.requested_range.start == _utc(2025, 1, 1, 10, 0)
        assert batch.requested_range.end == _utc(2025, 1, 1, 12, 0)
        for c in batch.candles:
            assert c.open_time >= _utc(2025, 1, 1, 10, 0)
            assert c.close_time <= _utc(2025, 1, 1, 12, 0)

    def test_protocol_does_not_import_http(self):
        # domain interface must not import http clients
        import pathlib

        p = pathlib.Path("src/bss/historical_loader/domain/interfaces/historical_source.py").read_text()
        assert "httpx" not in p.lower()
        assert "requests" not in p.lower()
        assert "aiohttp" not in p.lower()


class FakeSpreadSource:
    def spread_at(self, symbol: str, timestamp: datetime) -> Decimal | None:
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        # TBD: no data yet
        return None


class TestHistoricalSpreadSource:
    def test_spread_returns_none_when_no_data(self):
        src = FakeSpreadSource()
        assert isinstance(src, HistoricalSpreadSource)
        assert src.spread_at("SOLUSDT", _utc(2025, 1, 1, 10, 0)) is None

    def test_spread_naive_raises(self):
        src = FakeSpreadSource()
        with pytest.raises(ValueError, match="timezone-aware"):
            src.spread_at("SOLUSDT", datetime(2025, 1, 1, 10, 0))

    def test_tbd_not_closed(self):
        # Ensure the abstraction exists but no business logic invents spread
        import pathlib

        p = pathlib.Path("src/bss/historical_loader/domain/interfaces/historical_spread_source.py").read_text()
        # must mention Q-06 or TBD
        assert "Q-06" in p or "TBD" in p
