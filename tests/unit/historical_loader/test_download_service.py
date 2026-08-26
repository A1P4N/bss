"""Tests for DownloadService — sequential, chunk vs dataset validation, invariant."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.application.download_service import DownloadService
from bss.historical_loader.domain.checkpoint import Checkpoint
from bss.historical_loader.domain.dataset import DatasetStatus
from bss.historical_loader.domain.download_job import JobStatus
from bss.historical_loader.domain.errors import RateLimitedError, RetryExhaustedError
from bss.historical_loader.domain.normalization import CandleNormalizer
from bss.historical_loader.domain.validation import CandleValidator
from bss.historical_loader.infrastructure.networking.clock import FakeClock
from bss.historical_loader.infrastructure.networking.concurrency_limiter import ConcurrencyLimiter
from bss.historical_loader.infrastructure.networking.rate_limiter import RateLimiter
from bss.historical_loader.infrastructure.networking.request_limiter import RequestLimiter
from bss.historical_loader.infrastructure.networking.retry import RetryPolicy
from bss.historical_loader.infrastructure.storage.checkpoint_filesystem import CheckpointFilesystemStorage
from bss.historical_loader.infrastructure.storage.job_filesystem import JobFilesystemStorage
from bss.historical_loader.infrastructure.storage.metadata_filesystem import MetadataFilesystemStorage
from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage
from bss.historical_loader.infrastructure.storage.raw_filesystem import RawFilesystemStorage


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _make_source(candles_map=None):
    """Fake HistoricalSource that returns CandleBatch for given range."""
    from bss.historical_loader.domain.dataset import CandleBatch
    from bss.domain.candle import Candle
    from bss.domain.identifiers import CandleId
    from decimal import Decimal

    candles_map = candles_map or {}

    class FakeSource:
        def available_range(self, symbol, timeframe):
            return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 10))

        def download(self, symbol, timeframe, start, end):
            # return batch for requested range, with deterministic candles
            rr = TimeRange(start=start, end=end)
            # check if we have custom map
            key = (start.isoformat(), end.isoformat())
            if key in candles_map:
                return candles_map[key]
            # default: generate M15 candles for range
            from datetime import timedelta

            candles = []
            cur = start
            interval = timedelta(minutes=timeframe.duration_minutes())
            while cur < end:
                close = cur + interval
                if close > end:
                    # partial tail - still create candle if open < end (non-aligned)
                    # For non-aligned, we still create one candle for remaining partial?
                    # Instead, create candle with close = cur + interval even if beyond end? But per spec, open < end is enough
                    # For test, we create candle even if close > end, as long as open < end
                    pass
                candles.append(
                    Candle(
                        candle_id=CandleId(f"cnd_{symbol}_{timeframe.value}_{cur.isoformat()}"),
                        instrument_id=f"inst_{symbol.lower()}",
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
                if len(candles) > 1000:
                    break
            return CandleBatch(symbol=symbol, timeframe=timeframe, candles=tuple(candles), source="binance", requested_range=rr)

    return FakeSource()


def _make_service(tmp_path: Path, source=None, chunk_interval=timedelta(days=1)):
    source = source or _make_source()
    clock = FakeClock(0.0)
    rate = RateLimiter(rps=100, clock=clock, capacity=1)  # high RPS for tests
    conc = ConcurrencyLimiter(max_parallel=4)
    limiter = RequestLimiter(rate, conc)
    retry = RetryPolicy(max_attempts=3, initial_delay=0.01, max_delay=1.0, factor=2.0)
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
        retry_policy=retry,
        clock=clock,
        chunk_interval=chunk_interval,
    )


def test_create_job(tmp_path: Path):
    svc = _make_service(tmp_path)
    job = svc.create_job(DatasetId("ds_001"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    assert job.job_id.startswith("job_")
    assert job.status == JobStatus.CREATED
    # checkpoint initial
    cp = svc.checkpoint_storage.load(job.job_id)
    assert cp.next_start == _utc(2025, 1, 1)
    assert not cp.is_complete


def test_run_happy_path(tmp_path: Path):
    svc = _make_service(tmp_path, chunk_interval=timedelta(hours=12))
    job = svc.create_job(DatasetId("ds_001"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    result = svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    assert result.status == JobStatus.COMPLETED
    # dataset READY
    meta = svc.metadata_storage.get(DatasetId("ds_001"), DatasetVersion("v1"))
    assert meta.status == DatasetStatus.READY
    # checkpoint complete
    cp = svc.checkpoint_storage.load(job.job_id)
    assert cp.is_complete
    # streaming returns deterministic order
    candles = list(svc.normalized_storage.stream(DatasetId("ds_001"), DatasetVersion("v1"), "SOLUSDT", Timeframe.M15))
    assert candles == sorted(candles, key=lambda c: c.open_time)


def test_resume(tmp_path: Path):
    svc = _make_service(tmp_path, chunk_interval=timedelta(days=1))
    job = svc.create_job(DatasetId("ds_001"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3)), now=_utc(2025, 1, 10, 12, 0))
    # simulate partial run: manually advance checkpoint for first chunk 1-2
    import hashlib

    batch1 = svc.source.download("SOLUSDT", Timeframe.M15, _utc(2025, 1, 1), _utc(2025, 1, 2))
    norm_path = svc.normalized_storage.write_batch(batch1, DatasetId("ds_001"), DatasetVersion("v1"))
    svc.raw_storage.write_raw(batch1)
    cp = svc.checkpoint_storage.load(job.job_id)
    cp2 = cp.advance(chunk_from=_utc(2025, 1, 1), chunk_to=_utc(2025, 1, 2), checksum=hashlib.sha256(Path(norm_path).read_bytes()).hexdigest(), path=str(norm_path), updated_at=_utc(2025, 1, 10, 12, 1))
    svc.checkpoint_storage.save(cp2)
    # now resume should start from 2025-01-02 and complete
    result = svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    assert result.status == JobStatus.COMPLETED
    assert len(svc.normalized_storage.list_chunks(DatasetId("ds_001"), DatasetVersion("v1"))) == 2


def test_non_aligned_range_no_false_gap(tmp_path: Path):
    # 10:00-10:20 M15 → chunks [10:00-10:15, 10:15-10:20) second is partial 5m tail
    svc = _make_service(tmp_path, chunk_interval=timedelta(minutes=15))
    job = svc.create_job(DatasetId("ds_001"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 20)), now=_utc(2025, 1, 10, 12, 0))
    result = svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # should be COMPLETED, not gap, because open 10:15 inside [10:00,10:20)
    assert result.status == JobStatus.COMPLETED
    meta = svc.metadata_storage.get(DatasetId("ds_001"), DatasetVersion("v1"))
    assert meta.status == DatasetStatus.READY


def test_gap_on_chunk_boundary(tmp_path: Path):
    # 10:00-11:00 split 30m chunks: [10:00-10:30, 10:30-11:00], missing 10:30 candle
    svc = _make_service(tmp_path, chunk_interval=timedelta(minutes=30))
    # custom source that omits 10:30

    class GapSource:
        def available_range(self, symbol, timeframe):
            return TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))

        def download(self, symbol, timeframe, start, end):
            from decimal import Decimal

            from bss.domain.candle import Candle
            from bss.domain.identifiers import CandleId
            from bss.historical_loader.domain.dataset import CandleBatch

            rr = TimeRange(start=start, end=end)
            candles = []
            cur = start
            from datetime import timedelta

            interval = timedelta(minutes=timeframe.duration_minutes())
            while cur < end:
                if cur == _utc(2025, 1, 1, 10, 30):
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

    svc_gap = _make_service(tmp_path, source=GapSource(), chunk_interval=timedelta(minutes=30))
    job = svc_gap.create_job(DatasetId("ds_002"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0)), now=_utc(2025, 1, 10, 12, 0))
    result = svc_gap.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # chunk validation should pass (each chunk internally no gap), but dataset validation should fail with GAP
    assert result.status == JobStatus.FAILED
    meta = svc_gap.metadata_storage.get(DatasetId("ds_002"), DatasetVersion("v1"))
    assert meta.status == DatasetStatus.INVALID


def test_retry_exhausted_no_checkpoint_advance(tmp_path: Path):
    class AlwaysFailSource:
        def available_range(self, symbol, timeframe):
            return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))

        def download(self, symbol, timeframe, start, end):
            raise RateLimitedError(retry_after=0.01)

    svc = _make_service(tmp_path, source=AlwaysFailSource())
    job = svc.create_job(DatasetId("ds_003"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    with pytest.raises(RetryExhaustedError):
        svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    cp = svc.checkpoint_storage.load(job.job_id)
    assert cp.next_start == _utc(2025, 1, 1)  # not advanced
    assert len(svc.normalized_storage.list_chunks(DatasetId("ds_003"), DatasetVersion("v1"))) == 0


def test_rerun_completed_idempotent(tmp_path: Path):
    svc = _make_service(tmp_path)
    job = svc.create_job(DatasetId("ds_004"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # second run should be idempotent
    job2 = svc.run(job.job_id, now=_utc(2025, 1, 10, 14, 0))
    assert job2.status == JobStatus.COMPLETED
    assert len(svc.normalized_storage.list_chunks(DatasetId("ds_004"), DatasetVersion("v1"))) == 1


def test_version_isolation(tmp_path: Path):
    svc = _make_service(tmp_path)
    job1 = svc.create_job(DatasetId("ds_005"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job1.job_id, now=_utc(2025, 1, 10, 13, 0))
    job2 = svc.create_job(DatasetId("ds_005"), DatasetVersion("v2"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 13, 0))
    # v2 not yet run, should not see v1 chunks
    assert len(svc.normalized_storage.list_chunks(DatasetId("ds_005"), DatasetVersion("v2"))) == 0
    svc.run(job2.job_id, now=_utc(2025, 1, 10, 14, 0))
    assert len(svc.normalized_storage.list_chunks(DatasetId("ds_005"), DatasetVersion("v1"))) == 1
    assert len(svc.normalized_storage.list_chunks(DatasetId("ds_005"), DatasetVersion("v2"))) == 1
