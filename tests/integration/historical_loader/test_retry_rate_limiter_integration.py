"""Integration: RateLimiter + ConcurrencyLimiter + RetryPolicy with checkpoint invariant."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.checkpoint import Checkpoint
from bss.historical_loader.domain.dataset import CandleBatch
from bss.historical_loader.domain.errors import RateLimitedError, RetryExhaustedError, TemporaryServerError
from bss.historical_loader.infrastructure.networking.clock import FakeClock
from bss.historical_loader.infrastructure.networking.concurrency_limiter import ConcurrencyLimiter
from bss.historical_loader.infrastructure.networking.rate_limiter import RateLimiter
from bss.historical_loader.infrastructure.networking.request_limiter import RequestLimiter
from bss.historical_loader.infrastructure.networking.retry import RetryPolicy
from bss.historical_loader.infrastructure.storage.checkpoint_filesystem import CheckpointFilesystemStorage
from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage
from bss.historical_loader.infrastructure.storage.raw_filesystem import RawFilesystemStorage
from bss.historical_loader.domain.normalization import CandleNormalizer, RawCandle


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _raws(start, end):
    from datetime import timedelta

    raws = []
    cur = start
    interval = timedelta(minutes=15)
    while cur < end:
        raws.append(RawCandle(symbol="SOLUSDT", timeframe="M15", open_time=cur.isoformat(), close_time=(cur + interval).isoformat(), open="100", high="101", low="99", close="100", volume="1000", source="binance"))
        cur += interval
    return raws


def test_rate_concurrency_retry_success(tmp_path: Path):
    clock = FakeClock(0.0)
    rate = RateLimiter(rps=5, clock=clock, capacity=1)
    conc = ConcurrencyLimiter(max_parallel=4)
    limiter = RequestLimiter(rate, conc)
    retry = RetryPolicy(max_attempts=3, initial_delay=1.0, max_delay=60.0, factor=2.0)

    calls = {"n": 0}

    def flaky_download():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RateLimitedError(retry_after=0.5)
        return "batch"

    result = retry.execute(lambda: limiter.execute(flaky_download), clock)
    assert result == "batch"
    assert calls["n"] == 2
    # concurrency never exceeded 4 (only one thread here, but max_observed ==1)
    assert conc.max_observed <= 4
    # rate pacing: first acquire 0.0, second after retry sleeps 0.5, but rate interval 0.2 also applies
    # clock advanced at least 0.5 (Retry-After)
    assert clock.monotonic() >= 0.5


def test_retry_exhausted_no_checkpoint_change(tmp_path: Path):
    base = tmp_path
    ckpt_storage = CheckpointFilesystemStorage(base_path=base)
    norm_storage = NormalizedFilesystemStorage(base_path=base)
    raw_storage = RawFilesystemStorage(base_path=base)

    rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    cp = Checkpoint.initial(job_id="job_retry_exhaust", dataset_id="ds_001", dataset_version="v1", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_storage.save(cp)

    clock = FakeClock(0.0)
    retry = RetryPolicy(max_attempts=3, initial_delay=1.0, max_delay=60.0, factor=2.0)

    def always_fail():
        raise TemporaryServerError()

    with pytest.raises(RetryExhaustedError):
        retry.execute(always_fail, clock)

    # checkpoint unchanged (invariant)
    loaded = ckpt_storage.load("job_retry_exhaust")
    assert loaded.next_start == rr.start
    assert loaded.last_completed is None
    # storage not written (retry before storage)
    assert len(norm_storage.list_chunks(DatasetId("ds_001"), DatasetVersion("v1"))) == 0


def test_storage_checkpoint_invariant_retry_before_storage(tmp_path: Path):
    """Retry failure must not leave partial storage and must not advance checkpoint."""
    base = tmp_path
    ckpt_storage = CheckpointFilesystemStorage(base_path=base)
    norm_storage = NormalizedFilesystemStorage(base_path=base)
    raw_storage = RawFilesystemStorage(base_path=base)

    rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    cp = Checkpoint.initial(job_id="job_inv", dataset_id="ds_001", dataset_version="v1", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_storage.save(cp)

    clock = FakeClock(0.0)
    retry = RetryPolicy(max_attempts=2, initial_delay=1.0, max_delay=60.0, factor=2.0)

    calls = {"n": 0}

    def flaky_then_success():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TemporaryServerError()
        # success: do storage
        raws = _raws(rr.start, rr.end)
        batch = CandleNormalizer().normalize_batch(raws, rr, source="binance")
        raw_storage.write_raw(batch)
        norm_storage.write_batch(batch, DatasetId("ds_001"), DatasetVersion("v1"))
        return batch

    # retry will succeed on second attempt, then we advance checkpoint
    batch = retry.execute(flaky_then_success, clock)
    # only after storage success we advance
    import hashlib

    path = norm_storage.list_chunks(DatasetId("ds_001"), DatasetVersion("v1"))[0]
    cp2 = ckpt_storage.load("job_inv")
    # not yet advanced
    assert cp2.next_start == rr.start
    # now advance
    cp3 = cp2.advance(chunk_from=rr.start, chunk_to=rr.end, checksum=hashlib.sha256(path.read_bytes()).hexdigest(), path=str(path), updated_at=_utc(2025, 1, 10, 12, 1))
    ckpt_storage.save(cp3)
    assert ckpt_storage.load("job_inv").next_start == rr.end


def test_max_parallel_never_exceeds_4_with_retry(tmp_path: Path):
    import threading

    clock = FakeClock(0.0)  # monotonic for rate
    rate = RateLimiter(rps=100, clock=clock, capacity=1)  # high RPS to not interfere
    conc = ConcurrencyLimiter(max_parallel=4)
    limiter = RequestLimiter(rate, conc)
    retry = RetryPolicy(max_attempts=2, initial_delay=0.01, max_delay=1.0, factor=2.0)

    max_observed = {"v": 0}
    lock = threading.Lock()

    def tracked_op():
        with lock:
            if conc.in_flight() > max_observed["v"]:
                max_observed["v"] = conc.in_flight()
        # simulate work
        import time

        time.sleep(0.02)
        return 42

    def run_one():
        # each thread does limiter.execute with retry (no failure)
        return retry.execute(lambda: limiter.execute(tracked_op), clock)

    threads = []
    for _ in range(8):
        t = threading.Thread(target=run_one)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    assert max_observed["v"] <= 4
    assert conc.max_observed <= 4
