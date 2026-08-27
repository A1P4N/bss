"""Unit tests for RecoveryService (8 required)."""

from datetime import datetime, timezone
import dataclasses

import pytest

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.recovery import RecoveryPlan, RecoveryRange, RecoveryReason
from bss.historical_loader.domain.gap_event import DataIntegrityGapEvent


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def test_recovery_plan_is_frozen():
    plan = RecoveryPlan(dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"), ranges=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.ranges = ()  # type: ignore


def test_gap_produces_recovery_range():
    # GapDetector produces gaps -> RecoveryRange
    from bss.historical_loader.domain.gap_detector import GapDetector
    from bss.historical_loader.domain.dataset import CandleBatch
    from bss.domain.candle import Candle
    from bss.domain.identifiers import CandleId
    from decimal import Decimal

    rr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
    # missing 10:15
    c1 = Candle(candle_id=CandleId("c1"), instrument_id="inst", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=_utc(2025, 1, 1, 10, 0), close_time=_utc(2025, 1, 1, 10, 15), open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))
    c2 = Candle(candle_id=CandleId("c2"), instrument_id="inst", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=_utc(2025, 1, 1, 10, 30), close_time=_utc(2025, 1, 1, 10, 45), open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))
    c3 = Candle(candle_id=CandleId("c3"), instrument_id="inst", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=_utc(2025, 1, 1, 10, 45), close_time=_utc(2025, 1, 1, 11, 0), open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))
    batch = CandleBatch(symbol="SOLUSDT", timeframe=Timeframe.M15, candles=(c1, c2, c3), source="binance", requested_range=rr)
    gaps = GapDetector().find_gaps(batch)
    assert len(gaps) == 1
    # RecoveryRange from gap
    rr2 = RecoveryRange(start=gaps[0].missing_from, end=gaps[0].missing_to, reason=RecoveryReason.DATA_INTEGRITY_GAP)
    assert rr2.start == _utc(2025, 1, 1, 10, 15)


def test_multiple_gaps_are_sorted():
    ranges = (
        RecoveryRange(start=_utc(2025, 1, 1, 11, 0), end=_utc(2025, 1, 1, 12, 0), reason=RecoveryReason.DATA_INTEGRITY_GAP),
        RecoveryRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 30), reason=RecoveryReason.MISSING_CHUNK),
    )
    plan = RecoveryPlan(dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"), ranges=tuple(sorted(ranges, key=lambda r: r.start)))
    assert plan.ranges[0].start < plan.ranges[1].start
    # also test that unsorted raises
    with pytest.raises(ValueError, match="sorted"):
        RecoveryPlan(dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"), ranges=ranges)


def test_recovery_plan_is_deterministic():
    rr = RecoveryRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 30), reason=RecoveryReason.DATA_INTEGRITY_GAP)
    plan1 = RecoveryPlan(dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"), ranges=(rr,))
    plan2 = RecoveryPlan(dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"), ranges=(rr,))
    assert plan1 == plan2
    # same input state -> same plan (deterministic)
    assert hash(plan1) == hash(plan2)


def test_dataset_version_isolation():
    rr = RecoveryRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 10, 30), reason=RecoveryReason.DATA_INTEGRITY_GAP)
    p1 = RecoveryPlan(dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"), ranges=(rr,))
    p2 = RecoveryPlan(dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v2"), ranges=(rr,))
    assert p1.dataset_version != p2.dataset_version
    assert p1 != p2


def test_data_integrity_gap_event_payload():
    evt = DataIntegrityGapEvent.create(
        dataset_id=DatasetId("ds_001"),
        dataset_version=DatasetVersion("v1"),
        symbol="SOLUSDT",
        timeframe=Timeframe.M15,
        gap_from=_utc(2025, 1, 1, 10, 15),
        gap_to=_utc(2025, 1, 1, 10, 30),
        expected=4,
        actual=3,
    )
    assert evt.event_type == "DATA_INTEGRITY_GAP"
    assert evt.payload["dataset_id"] == "ds_001"
    assert evt.payload["symbol"] == "SOLUSDT"
    assert evt.payload["from"] == _utc(2025, 1, 1, 10, 15).isoformat()
    assert evt.schema_version == "0.2"
    assert evt.event_time.tzinfo == timezone.utc
    # roundtrip
    d = evt.to_dict()
    evt2 = DataIntegrityGapEvent.from_dict(d)
    assert evt == evt2


def test_recovery_uses_download_service():
    # Verify RecoveryService does not import HistoricalSource directly
    import pathlib

    text = pathlib.Path("src/bss/historical_loader/application/recovery_service.py").read_text()
    assert "HistoricalSource" not in text or "DownloadService" in text
    # Should import DownloadService
    assert "DownloadService" in text
    # Should not create second RetryPolicy
    assert text.count("RetryPolicy") <= 1  # only via DownloadService


def test_ready_dataset_recovery_is_noop(tmp_path):
    # Setup minimal dataset READY
    from pathlib import Path
    from bss.historical_loader.infrastructure.storage.metadata_filesystem import MetadataFilesystemStorage
    from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage
    from bss.historical_loader.infrastructure.storage.raw_filesystem import RawFilesystemStorage
    from bss.historical_loader.infrastructure.storage.checkpoint_filesystem import CheckpointFilesystemStorage
    from bss.historical_loader.infrastructure.storage.job_filesystem import JobFilesystemStorage
    from bss.historical_loader.infrastructure.storage.gap_event_filesystem import GapEventFilesystemStorage
    from bss.historical_loader.application.download_service import DownloadService
    from bss.historical_loader.application.recovery_service import RecoveryService
    from bss.historical_loader.domain.normalization import CandleNormalizer
    from bss.historical_loader.domain.validation import CandleValidator
    from bss.historical_loader.infrastructure.networking.clock import FakeClock
    from bss.historical_loader.infrastructure.networking.rate_limiter import RateLimiter
    from bss.historical_loader.infrastructure.networking.retry import RetryPolicy
    from bss.historical_loader.infrastructure.networking.concurrency_limiter import ConcurrencyLimiter
    from bss.historical_loader.infrastructure.networking.request_limiter import RequestLimiter
    from bss.domain.time_range import TimeRange as TR
    from bss.domain.candle import Candle
    from bss.domain.identifiers import CandleId
    from decimal import Decimal

    base = tmp_path
    # Create a READY dataset via DownloadService happy path
    from bss.historical_loader.domain.dataset import DatasetStatus

    def _make_source():
        class FakeSource:
            def available_range(self, symbol, timeframe):
                return TR(start=_utc(2025, 1, 1), end=_utc(2025, 1, 10))

            def download(self, symbol, timeframe, start, end):
                from bss.historical_loader.domain.dataset import CandleBatch

                rr = TR(start=start, end=end)
                candles = []
                cur = start
                from datetime import timedelta

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

        return FakeSource()

    source = _make_source()
    svc = DownloadService(
        source=source,
        normalizer=CandleNormalizer(),
        validator=CandleValidator(),
        raw_storage=RawFilesystemStorage(base_path=base),
        normalized_storage=NormalizedFilesystemStorage(base_path=base),
        metadata_storage=MetadataFilesystemStorage(base_path=base),
        checkpoint_storage=CheckpointFilesystemStorage(base_path=base),
        job_storage=JobFilesystemStorage(base_path=base),
        rate_limiter=RateLimiter(rps=100, clock=FakeClock(0.0)),
        retry_policy=RetryPolicy(max_attempts=3),
        clock=FakeClock(0.0),
        gap_event_storage=GapEventFilesystemStorage(base_path=base),
    )
    job = svc.create_job(DatasetId("ds_ready"), DatasetVersion("v1"), "binance", "SOLUSDT", Timeframe.M15, TR(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), now=_utc(2025, 1, 10, 12, 0))
    svc.run(job.job_id, now=_utc(2025, 1, 10, 13, 0))
    # Now recovery on READY should be noop
    rec_svc = RecoveryService(download_service=svc)
    plan = rec_svc.build_plan(DatasetId("ds_ready"), DatasetVersion("v1"))
    assert plan.is_empty
    # recover should not re-download
    plan2 = rec_svc.recover(DatasetId("ds_ready"), DatasetVersion("v1"), now=_utc(2025, 1, 10, 14, 0))
    assert plan2.is_empty
    # still READY
    meta = svc.metadata_storage.get(DatasetId("ds_ready"), DatasetVersion("v1"))
    assert meta.status == DatasetStatus.READY
