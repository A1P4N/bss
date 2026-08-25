"""Tests for NormalizedFilesystemStorage (streaming, idempotent, chunk identity)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId, DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import CandleBatch
from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _candle(open_dt):
    close_dt = datetime.fromtimestamp(open_dt.timestamp() + 15 * 60, tz=timezone.utc)
    return Candle(candle_id=CandleId(f"cnd_SOLUSDT_M15_{open_dt.isoformat()}"), instrument_id="inst_sol", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=open_dt, close_time=close_dt, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))


def _batch(start, end):
    c1 = _candle(start)
    from datetime import timedelta

    c2_open = start + timedelta(minutes=15)
    candles = (c1, _candle(c2_open)) if c2_open < end else (c1,)
    rr = TimeRange(start=start, end=end)
    return CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=candles, source="binance", requested_range=rr)


def test_write_and_stream(tmp_path: Path):
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    ds = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    batch = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    path = storage.write_batch(batch, ds, ver)
    assert path.exists()
    assert f"normalized/ds_001/v1/SOLUSDT/M15/2025/01/01" in str(path).replace("\\", "/")
    # streaming read
    candles = list(storage.stream(ds, ver, "SOLUSDT", Timeframe.M15))
    assert len(candles) == 2
    assert candles[0].open_time < candles[1].open_time


def test_idempotent_write(tmp_path: Path):
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    ds = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    batch = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    p1 = storage.write_batch(batch, ds, ver)
    mtime1 = p1.stat().st_mtime
    p2 = storage.write_batch(batch, ds, ver)
    mtime2 = p2.stat().st_mtime
    assert p1 == p2
    assert mtime1 == mtime2
    assert len(storage.list_chunks(ds, ver)) == 1


def test_streaming_filtered_by_range(tmp_path: Path):
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    ds = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    # two batches on different days
    b1 = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    b2 = _batch(_utc(2025, 1, 2, 10, 0), _utc(2025, 1, 2, 11, 0))
    storage.write_batch(b1, ds, ver)
    storage.write_batch(b2, ds, ver)
    # stream with filter 2025-01-01 only
    candles = list(storage.stream(ds, ver, "SOLUSDT", Timeframe.M15, start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)))
    assert len(candles) == 2
    # all
    all_candles = list(storage.stream(ds, ver, "SOLUSDT", Timeframe.M15))
    assert len(all_candles) == 4


def test_streaming_deterministic_order(tmp_path: Path):
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    ds = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    # write out of order (second day first)
    b2 = _batch(_utc(2025, 1, 2, 10, 0), _utc(2025, 1, 2, 11, 0))
    b1 = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    storage.write_batch(b2, ds, ver)
    storage.write_batch(b1, ds, ver)
    candles = list(storage.stream(ds, ver, "SOLUSDT", Timeframe.M15))
    times = [c.open_time for c in candles]
    assert times == sorted(times)


def test_stream_does_not_load_all(tmp_path: Path):
    # ensure stream is generator (lazy)
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    ds = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    b1 = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    storage.write_batch(b1, ds, ver)
    gen = storage.stream(ds, ver, "SOLUSDT", Timeframe.M15)
    import types

    assert isinstance(gen, types.GeneratorType)
    # consume one by one
    it = iter(gen)
    first = next(it)
    assert first.open_time == _utc(2025, 1, 1, 10, 0)


def test_verify(tmp_path: Path):
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    ds = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    b1 = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    storage.write_batch(b1, ds, ver)
    report = storage.verify(ds, ver)
    assert report.ok
    assert report.corrupt == []
    # corrupt
    path = storage.list_chunks(ds, ver)[0]
    path.write_text("corrupt", encoding="utf-8")
    report2 = storage.verify(ds, ver)
    assert not report2.ok
    assert len(report2.corrupt) == 1


def test_chunk_identity_different_versions_isolation(tmp_path: Path):
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    ds = DatasetId("ds_001")
    v1 = DatasetVersion("v1")
    v2 = DatasetVersion("v2")
    b1 = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    storage.write_batch(b1, ds, v1)
    storage.write_batch(b1, ds, v2)
    assert len(storage.list_chunks(ds, v1)) == 1
    assert len(storage.list_chunks(ds, v2)) == 1
    # different paths
    assert storage.list_chunks(ds, v1)[0] != storage.list_chunks(ds, v2)[0]


def test_corrupt_stream_raises(tmp_path: Path):
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    ds = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    b1 = _batch(_utc(2025, 1, 1, 10, 0), _utc(2025, 1, 1, 11, 0))
    path = storage.write_batch(b1, ds, ver)
    path.write_text("not json", encoding="utf-8")
    from bss.historical_loader.domain.errors import CorruptChunkError

    with pytest.raises(CorruptChunkError):
        list(storage.stream(ds, ver, "SOLUSDT", Timeframe.M15))
