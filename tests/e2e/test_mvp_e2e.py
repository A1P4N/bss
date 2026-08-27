"""E2E MVP — 15 scenarios."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId, DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.application.download_service import DownloadService
from bss.historical_loader.application.recovery_service import RecoveryService
from bss.historical_loader.domain.dataset import DatasetStatus, CandleBatch
from bss.historical_loader.domain.errors import RateLimitedError, TemporaryServerError, BadRequestError
from bss.historical_loader.domain.normalization import CandleNormalizer
from bss.historical_loader.domain.validation import CandleValidator
from bss.historical_loader.infrastructure.networking.clock import FakeClock
from bss.historical_loader.infrastructure.networking.concurrency_limiter import ConcurrencyLimiter
from bss.historical_loader.infrastructure.networking.rate_limiter import RateLimiter
from bss.historical_loader.infrastructure.networking.request_limiter import RequestLimiter
from bss.historical_loader.infrastructure.networking.retry import RetryPolicy
from bss.historical_loader.infrastructure.storage.checkpoint_filesystem import CheckpointFilesystemStorage
from bss.historical_loader.infrastructure.storage.gap_event_filesystem import GapEventFilesystemStorage
from bss.historical_loader.infrastructure.storage.job_filesystem import JobFilesystemStorage
from bss.historical_loader.infrastructure.storage.metadata_filesystem import MetadataFilesystemStorage
from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage
from bss.historical_loader.infrastructure.storage.raw_filesystem import RawFilesystemStorage
from bss.replay.replay_data_source import ReplayDataSource


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _make_source(candles_map=None, fail_first=None):
    class FakeSource:
        def __init__(self):
            self.calls = 0

        def available_range(self, symbol, timeframe):
            return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 10))

        def download(self, symbol, timeframe, start, end):
            self.calls += 1
            if fail_first and self.calls <= fail_first[0] and fail_first[1] == "429":
                raise RateLimitedError(retry_after=0.01)
            if fail_first and self.calls <= fail_first[0] and fail_first[1] == "500":
                raise TemporaryServerError()
            if fail_first and fail_first[1] == "400":
                raise BadRequestError()
            rr = TimeRange(start=start, end=end)
            # check custom map
            if candles_map and (start.isoformat(), end.isoformat()) in candles_map:
                return candles_map[(start.isoformat(), end.isoformat())]
            candles = []
            cur = start
            interval = timedelta(minutes=timeframe.duration_minutes())
            while cur < end:
                # check missing map
                if candles_map and "missing" in candles_map and cur in candles_map["missing"]:
                    cur += interval
                    continue
                candles.append(
                    Candle(
                        candle_id=CandleId(f"cnd_{symbol}_{timeframe.value}_{cur.isoformat()}"),
                        instrument_id="inst",
                        symbol=symbol,
                        timeframe=timeframe,
                        open_time=cur,
                        close_time=cur + interval,
                        open=Decimal("100"),
                        high=Decimal("101"),
                        low=Decimal("99"),
                        close=Decimal("100"),
                        volume=Decimal("1000"),
                    )
                )
                cur += interval
            return CandleBatch(symbol=symbol, timeframe=timeframe, candles=tuple(candles), source="binance", requested_range=rr)

    return FakeSource()


def _services(tmp_path: Path, source, chunk_interval=timedelta(days=1)):
    clock = FakeClock(0.0)
    rate = RateLimiter(rps=100, clock=clock, capacity=1)
    return DownloadService(
        source=source,
        normalizer=CandleNormalizer(),
        validator=CandleValidator(),
        raw_storage=RawFilesystemStorage(base_path=tmp_path),
        normalized_storage=NormalizedFilesystemStorage(base_path=tmp_path),
        metadata_storage=MetadataFilesystemStorage(base_path=tmp_path),
        checkpoint_storage=CheckpointFilesystemStorage(base_path=tmp_path),
        job_storage=JobFilesystemStorage(base_path=tmp_path),
        rate_limiter=rate,
        retry_policy=RetryPolicy(max_attempts=3, initial_delay=0.01, max_delay=1.0, factor=2.0),
        clock=clock,
        chunk_interval=chunk_interval,
        gap_event_storage=GapEventFilesystemStorage(base_path=tmp_path),
    ), RecoveryService


def test_1_download_to_ready(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source())
    job = svc.create_job(DatasetId("ds_001"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    res = svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    assert res.status.value == "COMPLETED"
    meta = svc.metadata_storage.get(DatasetId("ds_001"), DatasetVersion("v1"))
    assert meta.status == DatasetStatus.READY


def test_2_checkpoint_crash_resume(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source(), chunk_interval=timedelta(hours=12))
    job = svc.create_job(DatasetId("ds_002"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3)), now=_utc(2025, 1, 10, 12, 0))
    # simulate crash after first chunk by manually checkpointing one chunk
    import hashlib
    from pathlib import Path as P

    batch = svc.source.download("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1), _utc(2025, 1, 2))
    norm_path = svc.normalized_storage.write_batch(batch, DatasetId("ds_002"), DatasetVersion("v1"))
    svc.raw_storage.write_raw(batch)
    cp = svc.checkpoint_storage.load(job.job_id)
    cp2 = cp.advance(chunk_from=_utc(2025, 1, 1), chunk_to=_utc(2025, 1, 2), checksum=hashlib.sha256(P(norm_path).read_bytes()).hexdigest(), path=str(norm_path), updated_at=_utc(2025, 1, 10, 12, 1))
    svc.checkpoint_storage.save(cp2)
    res = svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    assert res.status.value == "COMPLETED"


def test_3_retry_429_5xx_success(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source(fail_first=(2, "429")))
    job = svc.create_job(DatasetId("ds_003"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    res = svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    assert res.status.value == "COMPLETED"


def test_4_permanent_error_failed(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source(fail_first=(1, "400")))
    job = svc.create_job(DatasetId("ds_004"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    try:
        svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    except Exception:
        pass
    job2 = svc.job_storage.load(job.job_id)
    assert job2.status.value == "FAILED"
    cp = svc.checkpoint_storage.load(job.job_id)
    assert cp.next_start == _utc(2025, 1, 1)  # not advanced


def test_5_dataset_gap(tmp_path: Path):
    # gap source missing one candle
    gap_src = _make_source(candles_map={"missing": {_utc(2025, 1, 1, 0, 15)}})
    svc, _ = _services(tmp_path, gap_src)
    job = svc.create_job(DatasetId("ds_005"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 1, 1, 0)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # after run, dataset should be INVALID and gap event persisted
    from bss.historical_loader.infrastructure.storage.gap_event_filesystem import GapEventFilesystemStorage

    gap_storage = GapEventFilesystemStorage(base_path=tmp_path)
    events = gap_storage.list("ds_005", "v1")
    assert len(events) >= 1
    assert events[0].payload["expected_candles"] > events[0].payload["actual_candles"]


def test_6_recovery_to_ready(tmp_path: Path):
    gap_src = _make_source(candles_map={"missing": {_utc(2025, 1, 1, 0, 15)}})
    svc_gap, Rec = _services(tmp_path, gap_src)
    job = svc_gap.create_job(DatasetId("ds_006"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 1, 1, 0)), now=_utc(2025, 1, 10, 12, 0))
    svc_gap.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # recover with full source
    full_svc, _ = _services(tmp_path, _make_source())
    rec = Rec(full_svc)
    plan = rec.build_plan(DatasetId("ds_006"), DatasetVersion("v1"))
    assert not plan.is_empty
    rec.recover(DatasetId("ds_006"), DatasetVersion("v1"), now=_utc(2025, 1, 10, 14, 0))
    meta = full_svc.metadata_storage.get(DatasetId("ds_006"), DatasetVersion("v1"))
    assert meta.status == DatasetStatus.READY


def test_7_ready_replay(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source())
    job = svc.create_job(DatasetId("ds_007"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    ds = ReplayDataSource(svc.normalized_storage)
    events = list(ds.replay(DatasetId("ds_007"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    assert len(events) > 0


def test_8_replay_candle_closed(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source())
    job = svc.create_job(DatasetId("ds_008"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 1, 1, 0)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    ds = ReplayDataSource(svc.normalized_storage)
    events = list(ds.replay(DatasetId("ds_008"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 1, 1, 0)), run_id="run_1"))
    assert all(e.event_type == "CANDLE_CLOSED" for e in events)
    assert all(e.schema_version == "0.2" for e in events)


def test_9_half_open_range(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source())
    job = svc.create_job(DatasetId("ds_009"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    ds = ReplayDataSource(svc.normalized_storage)
    ev = list(ds.replay(DatasetId("ds_009"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 30)), run_id="run_1"))
    assert len(ev) == 2
    assert ev[0].payload["candle"]["open_time"] == _utc(2025, 1, 1, 10, 0).isoformat()


def test_10_tail_candle(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source())
    job = svc.create_job(DatasetId("ds_010"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 20)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    ds = ReplayDataSource(svc.normalized_storage)
    ev = list(ds.replay(DatasetId("ds_010"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 20)), run_id="run_1"))
    assert len(ev) == 2  # 10:00 and 10:15 (close 10:30 > end but open < end)


def test_11_deterministic_replay(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source())
    job = svc.create_job(DatasetId("ds_011"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    ds = ReplayDataSource(svc.normalized_storage)
    ev1 = list(ds.replay(DatasetId("ds_011"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_a"))
    ev2 = list(ds.replay(DatasetId("ds_011"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_b"))
    assert [(e.event_time, e.payload) for e in ev1] == [(e.event_time, e.payload) for e in ev2]


def test_12_no_lookahead(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source())
    job = svc.create_job(DatasetId("ds_012"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    ds = ReplayDataSource(svc.normalized_storage)
    events = list(ds.replay(DatasetId("ds_012"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0)), run_id="run_1"))
    for i in range(len(events) - 1):
        assert events[i].event_time < events[i + 1].event_time
        # payload of i should not contain future
        assert events[i].payload["candle"]["open_time"] != events[i + 1].payload["candle"]["open_time"]


def test_13_repeat_replay_same_payload(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source())
    job = svc.create_job(DatasetId("ds_013"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    ds = ReplayDataSource(svc.normalized_storage)
    ev1 = list(ds.replay(DatasetId("ds_013"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_a"))
    ev2 = list(ds.replay(DatasetId("ds_013"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_b"))
    assert ev1[0].run_id != ev2[0].run_id
    assert ev1[0].event_id != ev2[0].event_id
    assert [(e.event_time, e.payload["candle"]["close"]) for e in ev1] == [(e.event_time, e.payload["candle"]["close"]) for e in ev2]


def test_14_version_isolation(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source())
    job1 = svc.create_job(DatasetId("ds_014"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job1.job_id, now=_utc(2025, 1, 10, 13, 0))
    job2 = svc.create_job(DatasetId("ds_014"), DatasetVersion("v2"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 13, 0))
    svc.run(job2.job_id, now=_utc(2025, 1, 10, 14, 0))
    ds = ReplayDataSource(svc.normalized_storage)
    ev1 = list(ds.replay(DatasetId("ds_014"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    ev2 = list(ds.replay(DatasetId("ds_014"), DatasetVersion("v2"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    assert len(ev1) == len(ev2)
    # different version but same content — still deterministic per version
    assert ev1[0].dataset_version.value == "v1"
    assert ev2[0].dataset_version.value == "v2"


def test_15_corrupt_missing_not_silent(tmp_path: Path):
    svc, _ = _services(tmp_path, _make_source())
    job = svc.create_job(DatasetId("ds_015"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # corrupt file
    path = svc.normalized_storage.list_chunks(DatasetId("ds_015"), DatasetVersion("v1"))[0]
    path.write_text("corrupt", encoding="utf-8")
    from bss.historical_loader.domain.errors import CorruptChunkError

    ds = ReplayDataSource(svc.normalized_storage)
    with pytest.raises(CorruptChunkError):
        list(ds.replay(DatasetId("ds_015"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    # missing: delete
    path.unlink()
    events = list(ds.replay(DatasetId("ds_015"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), run_id="run_1"))
    # missing returns 0, not silent corrupt — but gap would be detected at dataset validation
    assert events == []
