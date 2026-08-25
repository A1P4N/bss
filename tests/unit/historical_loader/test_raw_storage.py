"""Tests for RawFilesystemStorage (AC-08, atomic, idempotent)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import CandleBatch
from bss.historical_loader.infrastructure.storage.raw_filesystem import RawFilesystemStorage


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _candle(open_dt):
    close_dt = datetime.fromtimestamp(open_dt.timestamp() + 15 * 60, tz=timezone.utc)
    return Candle(candle_id=CandleId(f"cnd_SOLUSDT_M15_{open_dt.isoformat()}"), instrument_id="inst_sol", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=open_dt, close_time=close_dt, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))


def _batch(start, end, symbol="SOLUSDT", tf=Timeframe.M15, source="binance"):
    # helper to create batch with 2 candles
    c1 = _candle(start)
    # second candle at +15m
    from datetime import timedelta

    c2_open = start + timedelta(minutes=15)
    if c2_open >= end:
        candles = (c1,)
    else:
        c2 = _candle(c2_open)
        candles = (c1, c2)
    rr = TimeRange(start=start, end=end)
    return CandleBatch(symbol=symbol, timeframe=tf, candles=candles, source=source, requested_range=rr)


def test_write_and_read_roundtrip(tmp_path: Path):
    storage = RawFilesystemStorage(base_path=tmp_path)
    batch = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    path = storage.write_raw(batch)
    assert path.exists()
    # path convention check
    assert "raw/binance/SOLUSDT/M15/2025/01/01" in str(path).replace("\\", "/")
    # list
    listed = storage.list_raw("binance", "SOLUSDT", Timeframe.M15)
    assert len(listed) == 1
    # read streaming
    batches = list(storage.read_raw("binance", "SOLUSDT", Timeframe.M15, "2025-01-01"))
    assert len(batches) == 1
    assert batches[0].symbol == "SOLUSDT"
    assert len(batches[0].candles) == 2


def test_idempotent_write(tmp_path: Path):
    storage = RawFilesystemStorage(base_path=tmp_path)
    batch = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    p1 = storage.write_raw(batch)
    mtime1 = p1.stat().st_mtime
    p2 = storage.write_raw(batch)
    mtime2 = p2.stat().st_mtime
    assert p1 == p2
    assert mtime1 == mtime2  # not rewritten
    # no duplicate files
    assert len(storage.list_raw("binance", "SOLUSDT", Timeframe.M15)) == 1


def test_atomic_write_no_tmp_leaked(tmp_path: Path):
    storage = RawFilesystemStorage(base_path=tmp_path)
    batch = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    storage.write_raw(batch)
    # no .tmp files left
    assert not list((tmp_path / "raw").rglob("*.tmp.*"))


def test_exists_and_list(tmp_path: Path):
    storage = RawFilesystemStorage(base_path=tmp_path)
    assert not storage.exists("binance", "SOLUSDT", Timeframe.M15, "2025-01-01")
    batch = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    storage.write_raw(batch)
    assert storage.exists("binance", "SOLUSDT", Timeframe.M15, "2025-01-01")


def test_corrupt_detection(tmp_path: Path):
    storage = RawFilesystemStorage(base_path=tmp_path)
    batch = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    path = storage.write_raw(batch)
    # corrupt file
    path.write_text("not json\n{{{{", encoding="utf-8")
    # read_raw should raise CorruptChunkError on iteration
    from bss.historical_loader.domain.errors import CorruptChunkError

    gen = storage.read_raw("binance", "SOLUSDT", Timeframe.M15, "2025-01-01")
    with pytest.raises(CorruptChunkError):
        list(gen)


def test_separate_sources_isolation(tmp_path: Path):
    storage = RawFilesystemStorage(base_path=tmp_path)
    b1 = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0), source="binance")
    b2 = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0), source="file")
    storage.write_raw(b1)
    storage.write_raw(b2)
    assert len(storage.list_raw("binance", "SOLUSDT", Timeframe.M15)) == 1
    assert len(storage.list_raw("file", "SOLUSDT", Timeframe.M15)) == 1
