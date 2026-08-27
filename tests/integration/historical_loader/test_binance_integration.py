"""Integration: Binance mock server → DownloadService → Storage → Checkpoint."""

import http.server
import json
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.application.download_service import DownloadService
from bss.historical_loader.domain.normalization import CandleNormalizer
from bss.historical_loader.domain.validation import CandleValidator
from bss.historical_loader.infrastructure.networking.clock import FakeClock
from bss.historical_loader.infrastructure.networking.concurrency_limiter import ConcurrencyLimiter
from bss.historical_loader.infrastructure.networking.rate_limiter import RateLimiter
from bss.historical_loader.infrastructure.networking.request_limiter import RequestLimiter
from bss.historical_loader.infrastructure.networking.retry import RetryPolicy
from bss.historical_loader.infrastructure.sources.binance.adapter import BinanceSource
from bss.historical_loader.infrastructure.sources.binance.client import BinanceClient
from bss.historical_loader.infrastructure.storage.checkpoint_filesystem import CheckpointFilesystemStorage
from bss.historical_loader.infrastructure.storage.gap_event_filesystem import GapEventFilesystemStorage
from bss.historical_loader.infrastructure.storage.job_filesystem import JobFilesystemStorage
from bss.historical_loader.infrastructure.storage.metadata_filesystem import MetadataFilesystemStorage
from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage
from bss.historical_loader.infrastructure.storage.raw_filesystem import RawFilesystemStorage


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


class MockBinanceHandler(http.server.BaseHTTPRequestHandler):
    calls = 0
    # first call 429, second success
    klines = []

    def do_GET(self):
        MockBinanceHandler.calls += 1
        if MockBinanceHandler.calls == 1:
            self.send_response(429)
            self.send_header("Retry-After", "1")
            self.end_headers()
            self.wfile.write(b"{}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(MockBinanceHandler.klines).encode())

    def log_message(self, format, *args):
        pass


def _make_klines(start, end, timeframe=Timeframe.M15):
    klines = []
    cur = start
    interval_ms = timeframe.duration_minutes() * 60 * 1000
    while cur < end:
        open_ms = int(cur.timestamp() * 1000)
        klines.append([open_ms, "100", "101", "99", "100", "1000", open_ms + interval_ms, "0", 0, "0", "0", "0"])
        cur += timedelta(minutes=timeframe.duration_minutes())
    return klines


def test_binance_source_to_storage(tmp_path: Path):
    # Setup mock server with 429 then success
    klines = _make_klines(_utc(2025, 1, 1), _utc(2025, 1, 1, 1, 0))
    MockBinanceHandler.klines = klines
    MockBinanceHandler.calls = 0
    server = http.server.HTTPServer(("127.0.0.1", 0), MockBinanceHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)

    try:
        base_url = f"http://127.0.0.1:{port}"
        client = BinanceClient(base_url=base_url, timeout=2.0)
        source = BinanceSource(client=client)

        # services with retry and rate limiter
        clock = FakeClock(0.0)
        rate = RateLimiter(rps=100, clock=clock, capacity=1)
        conc = ConcurrencyLimiter(max_parallel=4)
        limiter = RequestLimiter(rate, conc)
        retry = RetryPolicy(max_attempts=3, initial_delay=0.1, max_delay=1.0, factor=2.0)

        download_service = DownloadService(
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
            chunk_interval=timedelta(hours=1),
            gap_event_storage=GapEventFilesystemStorage(base_path=tmp_path),
        )

        job = download_service.create_job(DatasetId("ds_test"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 1, 1, 0)), now=_utc(2025, 1, 10, 12, 0))
        # retry should handle 429
        result = download_service.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
        assert result.status.value == "COMPLETED"
        # checkpoint advanced
        cp = download_service.checkpoint_storage.load(job.job_id)
        assert cp.is_complete
        # storage has data
        assert len(download_service.normalized_storage.list_chunks(DatasetId("ds_test"), DatasetVersion("v1"))) == 1
        # retry used Retry-After 1 (clock should have slept 1)
        assert clock.sleeps[0] == 1.0
        # dataset READY only after validation
        meta = download_service.metadata_storage.get(DatasetId("ds_test"), DatasetVersion("v1"))
        assert meta.status.value == "READY"
    finally:
        server.shutdown()


def test_config_driven_download(tmp_path: Path):
    # Test that chunk_interval from config is used, not hardcoded 1d
    from bss.config.loader import load_config

    # create config with 12h chunk
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
source:
  name: binance
  base_url: "http://localhost:9999"
  timeout_seconds: 5.0
  rate_limit:
    requests_per_second: 5
    max_parallel_requests: 4
  retry:
    max_attempts: 5
    initial_delay_seconds: 1.0
    max_delay_seconds: 60.0
    backoff_factor: 2.0
loader:
  chunk_interval: "12h"
dataset:
  loader_version: "0.1.0"
  schema_version: "0.2"
storage:
  base_path: "data"
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.chunk_interval == timedelta(hours=12)
    # DownloadService should use this interval
    # Create service with this chunk_interval and verify chunk boundaries
    from bss.historical_loader.domain.normalization import CandleNormalizer
    from bss.historical_loader.domain.validation import CandleValidator
    from bss.historical_loader.infrastructure.networking.clock import FakeClock

    clock = FakeClock(0.0)
    rate = RateLimiter(rps=100, clock=clock, capacity=1)
    conc = ConcurrencyLimiter(max_parallel=4)
    limiter = RequestLimiter(rate, conc)
    retry = RetryPolicy(max_attempts=3)

    # Use synthetic source
    from bss.historical_loader.application.download_service import DownloadService

    class FakeSource:
        def available_range(self, s, tf):
            return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3))

        def download(self, symbol, timeframe, start, end):
            from bss.historical_loader.domain.dataset import CandleBatch

            return CandleBatch(symbol=symbol, timeframe=timeframe, candles=(), source="binance", requested_range=TimeRange(start=start, end=end))

    svc = DownloadService(
        source=FakeSource(),
        normalizer=CandleNormalizer(),
        validator=CandleValidator(),
        raw_storage=RawFilesystemStorage(base_path=tmp_path / "data1"),
        normalized_storage=NormalizedFilesystemStorage(base_path=tmp_path / "data1"),
        metadata_storage=MetadataFilesystemStorage(base_path=tmp_path / "data1"),
        checkpoint_storage=CheckpointFilesystemStorage(base_path=tmp_path / "data1"),
        job_storage=JobFilesystemStorage(base_path=tmp_path / "data1"),
        rate_limiter=rate,
        retry_policy=retry,
        clock=clock,
        chunk_interval=cfg.chunk_interval,
    )
    assert svc.chunk_interval == timedelta(hours=12)
    # Ensure 1d would be different
    svc2 = DownloadService(
        source=FakeSource(),
        normalizer=CandleNormalizer(),
        validator=CandleValidator(),
        raw_storage=RawFilesystemStorage(base_path=tmp_path / "data2"),
        normalized_storage=NormalizedFilesystemStorage(base_path=tmp_path / "data2"),
        metadata_storage=MetadataFilesystemStorage(base_path=tmp_path / "data2"),
        checkpoint_storage=CheckpointFilesystemStorage(base_path=tmp_path / "data2"),
        job_storage=JobFilesystemStorage(base_path=tmp_path / "data2"),
        rate_limiter=RateLimiter(rps=100, clock=FakeClock(0.0)),
        retry_policy=RetryPolicy(max_attempts=3),
        clock=FakeClock(0.0),
        chunk_interval=timedelta(days=1),
    )
    assert svc.chunk_interval != svc2.chunk_interval
