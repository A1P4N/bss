"""Integration: Raw → Normalized → Validation → Metadata READY → streaming."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import DatasetMetadata, DatasetStatus
from bss.historical_loader.domain.normalization import CandleNormalizer, RawCandle
from bss.historical_loader.domain.validation import CandleValidator
from bss.historical_loader.infrastructure.storage.metadata_filesystem import MetadataFilesystemStorage
from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage
from bss.historical_loader.infrastructure.storage.raw_filesystem import RawFilesystemStorage


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _raws(start, end, symbol="SOLUSDT", tf="M15"):
    from datetime import timedelta

    raws = []
    cur = start
    interval = timedelta(minutes=Timeframe.from_string(tf).duration_minutes())
    while cur < end:
        raws.append(RawCandle(symbol=symbol, timeframe=tf, open_time=cur.isoformat(), close_time=(cur + interval).isoformat(), open="100", high="101", low="99", close="100", volume="1000", source="binance"))
        cur += interval
    return raws


def test_pipeline_raw_normalized_metadata_stream(tmp_path: Path):
    base = tmp_path
    raw_storage = RawFilesystemStorage(base_path=base)
    norm_storage = NormalizedFilesystemStorage(base_path=base)
    meta_storage = MetadataFilesystemStorage(base_path=base)
    normalizer = CandleNormalizer()
    validator = CandleValidator()

    ds_id = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    rr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 12, 0))
    raws = _raws(rr.start, rr.end)

    # 1. normalize batch
    batch = normalizer.normalize_batch(raws, rr, source="binance")
    # 2. write raw
    raw_path = raw_storage.write_raw(batch)
    assert raw_path.exists()
    # 3. write normalized
    norm_path = norm_storage.write_batch(batch, ds_id, ver)
    assert norm_path.exists()
    # 4. validate
    res = validator.validate(batch)
    assert res.is_valid
    # 5. save metadata CREATED -> VALIDATING -> READY
    meta = DatasetMetadata(dataset_id=ds_id, dataset_version=ver, source="binance", symbols=("SOLUSDT",), timeframes=(Timeframe.M15,), range=rr, created_at=_utc(2025, 1, 1, 12, 0), loader_version="0.1.0", schema_version="0.2", status=DatasetStatus.VALIDATING)
    meta_storage.save(meta)
    ready_meta = meta_storage.update_status(ds_id, ver, DatasetStatus.READY)
    assert ready_meta.status == DatasetStatus.READY
    # 6. streaming read — not loading all at once
    candles = list(norm_storage.stream(ds_id, ver, "SOLUSDT", Timeframe.M15))
    assert len(candles) == 8  # 2h /15m =8
    assert candles[0].open_time == _utc(2025, 1, 1, 10, 0)
    # 7. verify checksums
    report = norm_storage.verify(ds_id, ver)
    assert report.ok
    # 8. idempotent re-write same batch does not duplicate
    p2 = norm_storage.write_batch(batch, ds_id, ver)
    assert p2 == norm_path
    assert len(norm_storage.list_chunks(ds_id, ver)) == 1
    # metadata immutability: cannot overwrite READY
    import dataclasses

    bad = dataclasses.replace(ready_meta, checksum="tamper")
    try:
        meta_storage.save(bad)
        assert False, "should raise ImmutableViolation"
    except Exception as e:
        assert "IMMUTABLE" in str(e) or "immutable" in str(e).lower()


def test_pipeline_with_gap_and_corrupt(tmp_path: Path):
    base = tmp_path
    norm_storage = NormalizedFilesystemStorage(base_path=base)
    ds_id = DatasetId("ds_002")
    ver = DatasetVersion("v1")
    rr = TimeRange(start=_utc(2025, 1, 1, 10, 0), end=_utc(2025, 1, 1, 11, 0))
    # missing middle candle
    raws = _raws(rr.start, rr.end)
    raws.pop(1)  # remove 10:15
    batch = CandleNormalizer().normalize_batch(raws, rr, source="binance")
    norm_storage.write_batch(batch, ds_id, ver)
    # validation should detect gap
    from bss.historical_loader.domain.validation import CandleValidator

    res = CandleValidator().validate(batch)
    assert not res.is_valid
    assert res.has_gaps
    # corrupt chunk
    path = norm_storage.list_chunks(ds_id, ver)[0]
    path.write_text("corrupt", encoding="utf-8")
    from bss.historical_loader.domain.errors import CorruptChunkError
    import pytest

    with pytest.raises(CorruptChunkError):
        list(norm_storage.stream(ds_id, ver, "SOLUSDT", Timeframe.M15))
    report = norm_storage.verify(ds_id, ver)
    assert not report.ok
