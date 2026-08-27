"""Integration Replay (5)."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId, DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import CandleBatch, DatasetMetadata, DatasetStatus
from bss.historical_loader.infrastructure.storage.metadata_filesystem import MetadataFilesystemStorage
from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage
from bss.replay.replay_data_source import ReplayDataSource


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _candle(open_dt):
    close_dt = open_dt + timedelta(minutes=15)
    return Candle(candle_id=CandleId(f"cnd_SOLUSDT_M15_{open_dt.isoformat()}"), instrument_id="inst", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=open_dt, close_time=close_dt, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))


def _populate(tmp_path: Path, start, end, dataset_id="ds_001", version="v1"):
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    candles = []
    cur = start
    while cur < end:
        candles.append(_candle(cur))
        cur += timedelta(minutes=15)
    batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=tuple(candles), source="binance", requested_range=TimeRange(start=start, end=end))
    storage.write_batch(batch, DatasetId(dataset_id), DatasetVersion(version))
    return storage


def test_normalized_storage_to_replay(tmp_path: Path):
    storage = _populate(tmp_path, _utc(2025, 1, 1), _utc(2025, 1, 2))
    ds = ReplayDataSource(storage)
    events = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    assert len(events) == 96  # 24*4
    assert events[0].event_type == "CANDLE_CLOSED"
    assert events[0].payload["candle"]["symbol"] == "SOLUSDT"


def test_replay_range_boundary(tmp_path: Path):
    storage = _populate(tmp_path, _utc(2025, 1, 1), _utc(2025, 1, 2))
    ds = ReplayDataSource(storage)
    # start inclusive
    ev = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 1, 0, 15)), run_id="run_1"))
    assert len(ev) == 1
    assert ev[0].event_time == _utc(2025, 1, 1, 0, 15)
    # end exclusive: candle at 00:00 next day should not be included if end is 00:00
    ev2 = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 23, 45), end=_utc(2025, 1, 2)), run_id="run_1"))
    assert len(ev2) == 1  # only 23:45
    ev3 = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 2), end=_utc(2025, 1, 2, 0, 15)), run_id="run_1"))
    assert len(ev3) == 0  # open_time == end -> excluded


def test_replay_ready_dataset(tmp_path: Path):
    storage = _populate(tmp_path, _utc(2025, 1, 1), _utc(2025, 1, 2))
    meta_storage = MetadataFilesystemStorage(base_path=tmp_path)
    meta = DatasetMetadata(dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"), source="binance", symbols=("SOLUSDT",), timeframes=(Timeframe.M15,), range=TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), created_at=_utc(2025, 1, 2), loader_version="0.1.0", schema_version="0.2", status=DatasetStatus.READY)
    meta_storage.save(meta)
    ds = ReplayDataSource(storage)
    events = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    assert len(events) == 96


def test_replay_missing_corrupt_chunk(tmp_path: Path):
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    # create one chunk then corrupt it
    batch = _populate(tmp_path, _utc(2025, 1, 1), _utc(2025, 1, 2)).list_chunks(DatasetId("ds_001"), DatasetVersion("v1"))
    # corrupt
    path = storage.list_chunks(DatasetId("ds_001"), DatasetVersion("v1"))[0]
    path.write_text("corrupt", encoding="utf-8")
    ds = ReplayDataSource(storage)
    from bss.historical_loader.domain.errors import CorruptChunkError

    with pytest.raises(CorruptChunkError):
        list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    # missing: no chunks but replay should return 0, not silent skip? For missing, stream returns 0, which is valid (no corrupt) but gap would be detected at dataset level
    storage2 = NormalizedFilesystemStorage(base_path=tmp_path / "empty")
    ds2 = ReplayDataSource(storage2)
    events = list(ds2.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    assert events == []


def test_replay_repeatability(tmp_path: Path):
    storage = _populate(tmp_path, _utc(2025, 1, 1), _utc(2025, 1, 2))
    ds = ReplayDataSource(storage)
    ev1 = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_a"))
    ev2 = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_b"))
    assert ev1[0].run_id != ev2[0].run_id
    assert ev1[0].event_id != ev2[0].event_id
    assert [(e.event_time, e.payload) for e in ev1] == [(e.event_time, e.payload) for e in ev2]
