"""ReplayDataSource tests (12)."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
import types
import pathlib

import pytest

import pytest

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId, DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.event_model.envelope import CandleClosedEvent
from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage
from bss.replay.replay_data_source import ReplayDataSource
from bss.historical_loader.domain.dataset import CandleBatch


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _candle(open_dt, symbol="SOLUSDT", tf=Timeframe.M15):
    close_dt = open_dt + timedelta(minutes=tf.duration_minutes())
    return Candle(candle_id=CandleId(f"cnd_{symbol}_{tf.value}_{open_dt.isoformat()}"), instrument_id="inst", symbol=symbol, timeframe=tf, open_time=open_dt, close_time=close_dt, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))


def _populate_storage(tmp_path: Path, dataset_id="ds_001", version="v1", symbol="SOLUSDT", timeframe=Timeframe.M15, start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)):
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    # create batch for whole range
    candles = []
    cur = start
    interval = timedelta(minutes=timeframe.duration_minutes())
    while cur < end:
        candles.append(_candle(cur, symbol, timeframe))
        cur += interval
    rr = TimeRange(start=start, end=end)
    batch = CandleBatch(symbol=symbol, timeframe=timeframe, candles=tuple(candles), source="binance", requested_range=rr)
    storage.write_batch(batch, DatasetId(dataset_id), DatasetVersion(version))
    return storage


def test_replay_streaming(tmp_path: Path):
    storage = _populate_storage(tmp_path)
    ds = ReplayDataSource(storage)
    gen = ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1")
    assert isinstance(gen, types.GeneratorType)
    # not loading all: can iterate one by one
    it = iter(gen)
    first = next(it)
    assert isinstance(first, CandleClosedEvent)


def test_replay_ordering(tmp_path: Path):
    storage = _populate_storage(tmp_path)
    ds = ReplayDataSource(storage)
    events = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    times = [e.event_time for e in events]
    assert times == sorted(times)
    # open_time ordering same
    for i in range(1, len(events)):
        assert events[i].event_time > events[i - 1].event_time


def test_replay_half_open_range(tmp_path: Path):
    storage = _populate_storage(tmp_path, start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))  # 10:00-11:00
    ds = ReplayDataSource(storage)
    # [10:00,10:30) should include 10:00,10:15 but not 10:30
    events = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 30)), run_id="run_1"))
    assert len(events) == 2
    assert events[0].payload["candle"]["open_time"] == _utc(2025, 1, 1, 10, 0).isoformat()
    assert events[1].payload["candle"]["open_time"] == _utc(2025, 1, 1, 10, 15).isoformat()


def test_replay_tail_candle(tmp_path: Path):
    # tail where close > end but open < end should be included
    storage = _populate_storage(tmp_path, start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 20))  # 20m range, M15 candles at 10:00 and 10:15 (close 10:30 > end)
    ds = ReplayDataSource(storage)
    events = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 20)), run_id="run_1"))
    # both 10:00 and 10:15 should be included (open < end)
    assert len(events) == 2
    assert events[1].event_time == _utc(2025, 1, 1, 10, 30)  # close_time


def test_replay_no_lookahead(tmp_path: Path):
    storage = _populate_storage(tmp_path, start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
    ds = ReplayDataSource(storage)
    events = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0)), run_id="run_1"))
    # each event payload should only contain its own candle, not future
    for i, evt in enumerate(events):
        # payload open_time should equal event_time - interval
        payload_open = evt.payload["open_time"]
        assert payload_open == events[i].payload["candle"]["open_time"]
        # no future data leaking: ensure payload does not contain next candle's open
        if i < len(events) - 1:
            assert payload_open != events[i + 1].payload["open_time"]


def test_replay_run_id(tmp_path: Path):
    storage = _populate_storage(tmp_path)
    ds = ReplayDataSource(storage)
    events = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_abc"))
    assert all(e.run_id == "run_abc" for e in events)
    assert len(events) > 0


def test_replay_run_id_isolation(tmp_path: Path):
    storage = _populate_storage(tmp_path)
    ds = ReplayDataSource(storage)
    ev1 = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    ev2 = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_2"))
    assert ev1[0].run_id != ev2[0].run_id
    assert ev1[0].run_id == "run_1"
    assert ev2[0].run_id == "run_2"


def test_replay_deterministic(tmp_path: Path):
    storage = _populate_storage(tmp_path)
    ds = ReplayDataSource(storage)
    ev1 = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    ev2 = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_2"))
    # event_time and payload must be identical, run_id/event_id may differ
    assert [(e.event_time, e.payload) for e in ev1] == [(e.event_time, e.payload) for e in ev2]


def test_replay_event_id_not_determinism_key(tmp_path: Path):
    storage = _populate_storage(tmp_path)
    ds = ReplayDataSource(storage)
    ev1 = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    ev2 = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    # event_id should differ across runs even same run_id? Actually same run_id, second run new UUID, so different
    assert ev1[0].event_id != ev2[0].event_id
    # but payload/time same
    assert ev1[0].payload == ev2[0].payload


def test_replay_deterministic_filesystem_order(tmp_path: Path):
    # Create two chunk files out of order and ensure replay still sorted
    storage = NormalizedFilesystemStorage(base_path=tmp_path)
    # write chunk 02 first, then 01
    rr2 = TimeRange(start=_utc(2025, 1, 2), end=_utc(2025, 1, 3))
    rr1 = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    # create batches
    def _batch(start, end):
        candles = []
        cur = start
        while cur < end:
            candles.append(_candle(cur))
            cur += timedelta(minutes=15)
        return CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=tuple(candles), source="binance", requested_range=TimeRange(start=start, end=end))

    storage.write_batch(_batch(rr2.start, rr2.end), DatasetId("ds_001"), DatasetVersion("v1"))
    storage.write_batch(_batch(rr1.start, rr1.end), DatasetId("ds_001"), DatasetVersion("v1"))
    ds = ReplayDataSource(storage)
    events = list(ds.replay(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3)), run_id="run_1"))
    times = [e.event_time for e in events]
    assert times == sorted(times)
    assert events[0].event_time == _utc(2025, 1, 1, 0, 15)  # close of first candle


def test_replay_no_loader_import():
    text = pathlib.Path("src/bss/replay/replay_data_source.py").read_text()
    assert "historical_loader.application.download_service" not in text
    assert "HistoricalSource" not in text


def test_replay_no_analysis_import():
    text = pathlib.Path("src/bss/replay/replay_data_source.py").read_text()
    assert "from bss.analysis" not in text
    assert "import analysis" not in text
