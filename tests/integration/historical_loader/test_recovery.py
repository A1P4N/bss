"""Integration Recovery: gap -> recovery -> READY, etc."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from decimal import Decimal
import hashlib

import pytest

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId, DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.application.download_service import DownloadService
from bss.historical_loader.application.recovery_service import RecoveryService
from bss.historical_loader.domain.dataset import DatasetStatus
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


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _make_services(tmp_path: Path, source, chunk_interval=timedelta(days=1)):
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
    )


class GapSource:
    """Source that omits one candle to create gap."""

    def __init__(self, missing=None):
        self.missing = missing  # set of open_time

    def available_range(self, symbol, timeframe):
        return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3))

    def download(self, symbol, timeframe, start, end):
        from bss.historical_loader.domain.dataset import CandleBatch

        rr = TimeRange(start=start, end=end)
        candles = []
        cur = start
        interval = timedelta(minutes=timeframe.duration_minutes())
        while cur < end:
            if self.missing and cur in self.missing:
                cur += interval
                continue
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
        return CandleBatch(symbol=symbol, timeframe=timeframe, candles=tuple(candles), source="binance", requested_range=rr)


class FullSource:
    def available_range(self, symbol, timeframe):
        return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3))

    def download(self, symbol, timeframe, start, end):
        from bss.historical_loader.domain.dataset import CandleBatch

        rr = TimeRange(start=start, end=end)
        candles = []
        cur = start
        interval = timedelta(minutes=timeframe.duration_minutes())
        while cur < end:
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
        return CandleBatch(symbol=symbol, timeframe=timeframe, candles=tuple(candles), source="binance", requested_range=rr)


def test_gap_to_recovery_to_ready(tmp_path: Path):
    # gap source creates INVALID, recovery with full source makes READY
    gap_source = GapSource(missing={_utc(2025, 1, 1, 12, 0)})
    svc_gap = _make_services(tmp_path, source=gap_source, chunk_interval=timedelta(days=1))
    job = svc_gap.create_job(DatasetId("ds_001"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3)), now=_utc(2025, 1, 10, 12, 0))
    svc_gap.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    meta = svc_gap.metadata_storage.get(DatasetId("ds_001"), DatasetVersion("v1"))
    assert meta.status == DatasetStatus.INVALID
    # now recovery with full source
    full_source = FullSource()
    svc_full = _make_services(tmp_path, source=full_source, chunk_interval=timedelta(days=1))
    # reuse same storages (tmp_path same) but need to share metadata etc — create new service with same base
    rec = RecoveryService(download_service=svc_full)
    plan = rec.build_plan(DatasetId("ds_001"), DatasetVersion("v1"))
    assert not plan.is_empty
    rec.recover(DatasetId("ds_001"), DatasetVersion("v1"), now=_utc(2025, 1, 10, 14, 0))
    meta2 = svc_full.metadata_storage.get(DatasetId("ds_001"), DatasetVersion("v1"))
    assert meta2.status == DatasetStatus.READY


def test_gap_event_is_persisted(tmp_path: Path):
    gap_source = GapSource(missing={_utc(2025, 1, 1, 12, 0)})
    svc = _make_services(tmp_path, source=gap_source)
    job = svc.create_job(DatasetId("ds_002"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    gap_storage = GapEventFilesystemStorage(base_path=tmp_path)
    events = gap_storage.list("ds_002", "v1")
    assert len(events) >= 1
    assert events[0].payload["symbol"] == "SOLUSDT"
    assert events[0].event_type == "DATA_INTEGRITY_GAP"


def test_missing_chunk_recovery(tmp_path: Path):
    svc = _make_services(tmp_path, source=FullSource())
    job = svc.create_job(DatasetId("ds_003"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # delete a chunk file to simulate missing
    norm = svc.normalized_storage
    path = norm.list_chunks(DatasetId("ds_003"), DatasetVersion("v1"))[0]
    path.unlink()
    rec = RecoveryService(download_service=svc)
    plan = rec.build_plan(DatasetId("ds_003"), DatasetVersion("v1"))
    assert not plan.is_empty
    assert plan.ranges[0].reason.value == "DATA_INTEGRITY_GAP" or "MISSING" in plan.ranges[0].reason.value
    rec.recover(DatasetId("ds_003"), DatasetVersion("v1"), now=_utc(2025, 1, 10, 14, 0))
    assert svc.metadata_storage.get(DatasetId("ds_003"), DatasetVersion("v1")).status == DatasetStatus.READY


def test_corrupt_chunk_recovery(tmp_path: Path):
    svc = _make_services(tmp_path, source=FullSource())
    job = svc.create_job(DatasetId("ds_004"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    path = svc.normalized_storage.list_chunks(DatasetId("ds_004"), DatasetVersion("v1"))[0]
    path.write_text("corrupt", encoding="utf-8")
    rec = RecoveryService(download_service=svc)
    plan = rec.build_plan(DatasetId("ds_004"), DatasetVersion("v1"))
    assert not plan.is_empty
    rec.recover(DatasetId("ds_004"), DatasetVersion("v1"), now=_utc(2025, 1, 10, 14, 0))
    assert svc.metadata_storage.get(DatasetId("ds_004"), DatasetVersion("v1")).status == DatasetStatus.READY


def test_recovery_is_idempotent(tmp_path: Path):
    svc = _make_services(tmp_path, source=GapSource(missing={_utc(2025, 1, 1, 12, 0)}))
    job = svc.create_job(DatasetId("ds_005"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # recover once with full source
    full_svc = _make_services(tmp_path, source=FullSource())
    rec = RecoveryService(download_service=full_svc)
    rec.recover(DatasetId("ds_005"), DatasetVersion("v1"), now=_utc(2025, 1, 10, 14, 0))
    # second recover should be idempotent (no duplicate)
    count1 = len(full_svc.normalized_storage.list_chunks(DatasetId("ds_005"), DatasetVersion("v1")))
    rec.recover(DatasetId("ds_005"), DatasetVersion("v1"), now=_utc(2025, 1, 10, 15, 0))
    count2 = len(full_svc.normalized_storage.list_chunks(DatasetId("ds_005"), DatasetVersion("v1")))
    assert count1 == count2


def test_recovery_after_process_restart(tmp_path: Path):
    # Simulate restart: create new service instances with same base_path
    svc1 = _make_services(tmp_path, source=GapSource(missing={_utc(2025, 1, 1, 12, 0)}))
    job = svc1.create_job(DatasetId("ds_006"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc1.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # restart: new service with same base
    svc2 = _make_services(tmp_path, source=FullSource())
    rec = RecoveryService(download_service=svc2)
    rec.recover(DatasetId("ds_006"), DatasetVersion("v1"), now=_utc(2025, 1, 10, 14, 0))
    assert svc2.metadata_storage.get(DatasetId("ds_006"), DatasetVersion("v1")).status == DatasetStatus.READY


def test_recovery_failure_does_not_mark_ready(tmp_path: Path):
    # Gap source always fails to fill gap (still missing)
    svc = _make_services(tmp_path, source=GapSource(missing={_utc(2025, 1, 1, 12, 0)}))
    job = svc.create_job(DatasetId("ds_007"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # recovery with same gap source (still missing) should not become READY
    rec = RecoveryService(download_service=svc)
    rec.recover(DatasetId("ds_007"), DatasetVersion("v1"), now=_utc(2025, 1, 10, 14, 0))
    assert svc.metadata_storage.get(DatasetId("ds_007"), DatasetVersion("v1")).status == DatasetStatus.INVALID


def test_recovery_dataset_version_isolation(tmp_path: Path):
    svc_v1 = _make_services(tmp_path, source=GapSource(missing={_utc(2025, 1, 1, 12, 0)}))
    job_v1 = svc_v1.create_job(DatasetId("ds_008"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc_v1.run(job_v1.job_id, now=_utc(2025, 1, 10, 13, 0))
    # v2 is full
    svc_v2 = _make_services(tmp_path, source=FullSource())
    job_v2 = svc_v2.create_job(DatasetId("ds_008"), DatasetVersion("v2"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc_v2.run(job_v2.job_id, now=_utc(2025, 1, 10, 13, 0))
    # recovery v1 should not affect v2
    rec = RecoveryService(download_service=svc_v2)  # full source can fix v1
    rec.recover(DatasetId("ds_008"), DatasetVersion("v1"), now=_utc(2025, 1, 10, 14, 0))
    assert svc_v2.metadata_storage.get(DatasetId("ds_008"), DatasetVersion("v1")).status == DatasetStatus.READY
    assert svc_v2.metadata_storage.get(DatasetId("ds_008"), DatasetVersion("v2")).status == DatasetStatus.READY


# Regression for failed/paused resume already covered in download_service tests, but add explicit
def test_failed_job_can_resume_from_checkpoint(tmp_path: Path):
    from bss.historical_loader.domain.errors import RateLimitedError

    class FailOnceSource:
        def __init__(self):
            self.calls = 0

        def available_range(self, symbol, timeframe):
            return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3))

        def download(self, symbol, timeframe, start, end):
            self.calls += 1
            if self.calls == 1:
                raise RateLimitedError(retry_after=0.01)
            # succeed on retry
            from bss.historical_loader.domain.dataset import CandleBatch

            rr = TimeRange(start=start, end=end)
            candles = []
            cur = start
            from datetime import timedelta

            interval = timedelta(minutes=timeframe.duration_minutes())
            while cur < end:
                from bss.domain.candle import Candle
                from bss.domain.identifiers import CandleId

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

    # Use source that fails first chunk then succeeds on retry (but RetryPolicy will handle)
    # Instead test FAILED resume: create job, run with always failing source to get FAILED, then resume with good source
    class AlwaysFail:
        def available_range(self, s, tf):
            return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))

        def download(self, s, tf, start, end):
            raise RateLimitedError(retry_after=0.01)

    svc_fail = _make_services(tmp_path, source=AlwaysFail())
    job = svc_fail.create_job(DatasetId("ds_009"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    try:
        svc_fail.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    except Exception:
        pass
    # now job is FAILED, checkpoint not advanced
    # resume with good source
    svc_good = _make_services(tmp_path, source=FullSource())
    # need to ensure job_storage still has FAILED job
    job_failed = svc_fail.job_storage.load(job.job_id)
    assert job_failed.status.value == "FAILED"
    # run again should transition FAILED->RUNNING and complete
    result = svc_good.run(job.job_id, now=_utc(2025, 1, 10, 14, 0))
    assert result.status.value == "COMPLETED"


def test_paused_job_can_resume_from_checkpoint(tmp_path: Path):
    svc = _make_services(tmp_path, source=FullSource())
    job = svc.create_job(DatasetId("ds_010"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3)), now=_utc(2025, 1, 10, 12, 0))
    # manually pause
    from bss.historical_loader.domain.download_job import JobStatus

    paused = job.transition(JobStatus.RUNNING, _utc(2025, 1, 10, 12, 1)).transition(JobStatus.PAUSED, _utc(2025, 1, 10, 12, 2))
    svc.job_storage.save(paused)
    # resume
    result = svc.run(paused.job_id, now=_utc(2025, 1, 10, 13, 0))
    assert result.status.value == "COMPLETED"
