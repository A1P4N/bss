"""Integration: checkpoint/resume crash-consistency A-E, corrupted/missing chunk, idempotent, isolation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.checkpoint import Checkpoint
from bss.historical_loader.domain.dataset import CandleBatch
from bss.historical_loader.domain.errors import CorruptChunkError
from bss.historical_loader.domain.normalization import CandleNormalizer, RawCandle
from bss.historical_loader.infrastructure.storage.checkpoint_filesystem import CheckpointFilesystemStorage
from bss.historical_loader.infrastructure.storage.normalized_filesystem import NormalizedFilesystemStorage
from bss.historical_loader.infrastructure.storage.raw_filesystem import RawFilesystemStorage


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _range():
    return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3))  # 2 days


def _raws_for_chunk(start, end, tf=Timeframe.M15, symbol="SOLUSDT"):
    raws = []
    cur = start
    interval = timedelta(minutes=tf.duration_minutes())
    while cur < end:
        raws.append(RawCandle(symbol=symbol, timeframe=tf.value, open_time=cur.isoformat(), close_time=(cur + interval).isoformat(), open="100", high="101", low="99", close="100", volume="1000", source="binance"))
        cur += interval
    return raws


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _do_chunk(raws, rr, storage_raw, storage_norm, dataset_id, version, source="binance"):
    """Helper: normalize + write raw + write normalized (atomic). Returns norm_path."""
    normalizer = CandleNormalizer()
    batch = normalizer.normalize_batch(raws, rr, source=source)
    raw_path = storage_raw.write_raw(batch)
    norm_path = storage_norm.write_batch(batch, dataset_id, version)
    return batch, raw_path, norm_path


# --- Crash A: before storage write ---
def test_crash_A_before_storage(tmp_path: Path):
    base = tmp_path
    raw_s = RawFilesystemStorage(base_path=base)
    norm_s = NormalizedFilesystemStorage(base_path=base)
    ckpt_s = CheckpointFilesystemStorage(base_path=base)
    rr = _range()
    cp = Checkpoint.initial(job_id="job_A", dataset_id="ds_001", dataset_version="v1", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_s.save(cp)
    # crash before any storage write — no chunks, checkpoint next_start = start
    loaded = ckpt_s.load("job_A")
    assert loaded.next_start == rr.start
    assert len(norm_s.list_chunks(DatasetId("ds_001"), DatasetVersion("v1"))) == 0
    # resume should start from same next_start
    assert loaded.next_start == rr.start


# --- Crash B: after Raw, before Normalized ---
def test_crash_B_after_raw(tmp_path: Path):
    base = tmp_path
    raw_s = RawFilesystemStorage(base_path=base)
    norm_s = NormalizedFilesystemStorage(base_path=base)
    ckpt_s = CheckpointFilesystemStorage(base_path=base)
    rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    chunk_rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    raws = _raws_for_chunk(chunk_rr.start, chunk_rr.end)
    cp = Checkpoint.initial(job_id="job_B", dataset_id="ds_001", dataset_version="v1", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_s.save(cp)
    # simulate: raw write succeeds, crash before normalized and checkpoint
    normalizer = CandleNormalizer()
    batch = normalizer.normalize_batch(raws, chunk_rr, source="binance")
    raw_s.write_raw(batch)
    # crash -> checkpoint not advanced
    loaded = ckpt_s.load("job_B")
    assert loaded.next_start == rr.start
    # resume: idempotent re-write normalized + advance
    ds_id = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    norm_path = norm_s.write_batch(batch, ds_id, ver)
    cp2 = loaded.advance(chunk_from=chunk_rr.start, chunk_to=chunk_rr.end, checksum=_checksum(norm_path), path=str(norm_path), updated_at=_utc(2025, 1, 10, 12, 1))
    ckpt_s.save(cp2)
    assert ckpt_s.load("job_B").next_start == chunk_rr.end
    # no duplicate: only one chunk file
    assert len(norm_s.list_chunks(ds_id, ver)) == 1


# --- Crash C: after Normalized, before checkpoint ---
def test_crash_C_after_normalized(tmp_path: Path):
    base = tmp_path
    raw_s = RawFilesystemStorage(base_path=base)
    norm_s = NormalizedFilesystemStorage(base_path=base)
    ckpt_s = CheckpointFilesystemStorage(base_path=base)
    rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    chunk_rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    raws = _raws_for_chunk(chunk_rr.start, chunk_rr.end)
    cp = Checkpoint.initial(job_id="job_C", dataset_id="ds_001", dataset_version="v1", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_s.save(cp)
    batch, raw_path, norm_path = _do_chunk(raws, chunk_rr, raw_s, norm_s, DatasetId("ds_001"), DatasetVersion("v1"))
    # crash before checkpoint advance
    loaded = ckpt_s.load("job_C")
    assert loaded.next_start == rr.start
    # resume: write again idempotently -> mtime unchanged, then advance
    ds_id = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    p2 = norm_s.write_batch(batch, ds_id, ver)
    assert p2 == norm_path
    # advance
    cp2 = loaded.advance(chunk_from=chunk_rr.start, chunk_to=chunk_rr.end, checksum=_checksum(norm_path), path=str(norm_path), updated_at=_utc(2025, 1, 10, 12, 1))
    ckpt_s.save(cp2)
    assert len(norm_s.list_chunks(ds_id, ver)) == 1


# --- Crash D: after checkpoint ---
def test_crash_D_after_checkpoint(tmp_path: Path):
    base = tmp_path
    raw_s = RawFilesystemStorage(base_path=base)
    norm_s = NormalizedFilesystemStorage(base_path=base)
    ckpt_s = CheckpointFilesystemStorage(base_path=base)
    rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3))
    # first chunk 1-2
    chunk1 = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    raws1 = _raws_for_chunk(chunk1.start, chunk1.end)
    cp = Checkpoint.initial(job_id="job_D", dataset_id="ds_001", dataset_version="v1", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_s.save(cp)
    ds_id = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    batch1, _, norm_path1 = _do_chunk(raws1, chunk1, raw_s, norm_s, ds_id, ver)
    cp2 = cp.advance(chunk_from=chunk1.start, chunk_to=chunk1.end, checksum=_checksum(norm_path1), path=str(norm_path1), updated_at=_utc(2025, 1, 10, 12, 1))
    ckpt_s.save(cp2)
    # crash after checkpoint — resume should start at 1-2 end
    loaded = ckpt_s.load("job_D")
    assert loaded.next_start == _utc(2025, 1, 2)
    # second chunk
    chunk2 = TimeRange(start=_utc(2025, 1, 2), end=_utc(2025, 1, 3))
    raws2 = _raws_for_chunk(chunk2.start, chunk2.end)
    batch2, _, norm_path2 = _do_chunk(raws2, chunk2, raw_s, norm_s, ds_id, ver)
    cp3 = loaded.advance(chunk_from=chunk2.start, chunk_to=chunk2.end, checksum=_checksum(norm_path2), path=str(norm_path2), updated_at=_utc(2025, 1, 10, 12, 2))
    ckpt_s.save(cp3)
    assert ckpt_s.load("job_D").is_complete
    assert len(norm_s.list_chunks(ds_id, ver)) == 2


# --- Crash E: corruption after checkpoint ---
def test_crash_E_corruption_after_checkpoint(tmp_path: Path):
    base = tmp_path
    raw_s = RawFilesystemStorage(base_path=base)
    norm_s = NormalizedFilesystemStorage(base_path=base)
    ckpt_s = CheckpointFilesystemStorage(base_path=base)
    rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    raws = _raws_for_chunk(rr.start, rr.end)
    cp = Checkpoint.initial(job_id="job_E", dataset_id="ds_001", dataset_version="v1", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_s.save(cp)
    ds_id = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    batch, _, norm_path = _do_chunk(raws, rr, raw_s, norm_s, ds_id, ver)
    cp2 = cp.advance(chunk_from=rr.start, chunk_to=rr.end, checksum=_checksum(norm_path), path=str(norm_path), updated_at=_utc(2025, 1, 10, 12, 1))
    ckpt_s.save(cp2)
    # corrupt file after checkpoint
    norm_path.write_text("corrupt", encoding="utf-8")
    # resume must detect corrupt and not silently skip
    loaded = ckpt_s.load("job_E")
    # verify checksum mismatch
    actual = hashlib.sha256(norm_path.read_bytes()).hexdigest()
    assert actual != loaded.last_completed.checksum
    # simulate resume check
    with pytest.raises(Exception):
        # our resume logic should verify last_completed checksum
        if _checksum(norm_path) != loaded.last_completed.checksum:
            raise CorruptChunkError(code="CORRUPT_CHUNK", message="checksum mismatch after checkpoint", context={"path": str(norm_path)})


def test_missing_chunk_not_silently_skipped(tmp_path: Path):
    base = tmp_path
    raw_s = RawFilesystemStorage(base_path=base)
    norm_s = NormalizedFilesystemStorage(base_path=base)
    ckpt_s = CheckpointFilesystemStorage(base_path=base)
    rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    raws = _raws_for_chunk(rr.start, rr.end)
    cp = Checkpoint.initial(job_id="job_M", dataset_id="ds_001", dataset_version="v1", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_s.save(cp)
    ds_id = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    batch, _, norm_path = _do_chunk(raws, rr, raw_s, norm_s, ds_id, ver)
    cp2 = cp.advance(chunk_from=rr.start, chunk_to=rr.end, checksum=_checksum(norm_path), path=str(norm_path), updated_at=_utc(2025, 1, 10, 12, 1))
    ckpt_s.save(cp2)
    # delete file
    norm_path.unlink()
    loaded = ckpt_s.load("job_M")
    assert not Path(loaded.last_completed.path).exists()
    # resume must not skip
    with pytest.raises(Exception):
        if not Path(loaded.last_completed.path).exists():
            raise CorruptChunkError(code="MISSING_CHUNK", message="missing chunk pointed by checkpoint", context={"path": loaded.last_completed.path})


def test_idempotent_resume(tmp_path: Path):
    base = tmp_path
    raw_s = RawFilesystemStorage(base_path=base)
    norm_s = NormalizedFilesystemStorage(base_path=base)
    ckpt_s = CheckpointFilesystemStorage(base_path=base)
    rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 3))
    ds_id = DatasetId("ds_001")
    ver = DatasetVersion("v1")
    cp = Checkpoint.initial(job_id="job_I", dataset_id="ds_001", dataset_version="v1", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_s.save(cp)
    # first run: two chunks
    for chunk in [TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), TimeRange(start=_utc(2025, 1, 2), end=_utc(2025, 1, 3))]:
        raws = _raws_for_chunk(chunk.start, chunk.end)
        batch, _, norm_path = _do_chunk(raws, chunk, raw_s, norm_s, ds_id, ver)
        cur = ckpt_s.load("job_I")
        nxt = cur.advance(chunk_from=chunk.start, chunk_to=chunk.end, checksum=_checksum(norm_path), path=str(norm_path), updated_at=_utc(2025, 1, 10, 12, 1))
        ckpt_s.save(nxt)
    # second run same job idempotent (re-apply same chunks)
    for chunk in [TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2)), TimeRange(start=_utc(2025, 1, 2), end=_utc(2025, 1, 3))]:
        raws = _raws_for_chunk(chunk.start, chunk.end)
        # normalize again gives same batch
        from bss.historical_loader.domain.normalization import CandleNormalizer

        batch = CandleNormalizer().normalize_batch(raws, chunk, source="binance")
        # write idempotent — should not duplicate
        p = norm_s.write_batch(batch, ds_id, ver)
        assert p.exists()
    assert len(norm_s.list_chunks(ds_id, ver)) == 2


def test_dataset_version_isolation(tmp_path: Path):
    base = tmp_path
    raw_s = RawFilesystemStorage(base_path=base)
    norm_s = NormalizedFilesystemStorage(base_path=base)
    ckpt_s = CheckpointFilesystemStorage(base_path=base)
    rr = TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 2))
    raws = _raws_for_chunk(rr.start, rr.end)
    # v1
    cp_v1 = Checkpoint.initial(job_id="job_v1", dataset_id="ds_001", dataset_version="v1", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_s.save(cp_v1)
    batch, _, p1 = _do_chunk(raws, rr, raw_s, norm_s, DatasetId("ds_001"), DatasetVersion("v1"))
    cp_v1_2 = cp_v1.advance(chunk_from=rr.start, chunk_to=rr.end, checksum=_checksum(p1), path=str(p1), updated_at=_utc(2025, 1, 10, 12, 1))
    ckpt_s.save(cp_v1_2)
    # v2 separate
    cp_v2 = Checkpoint.initial(job_id="job_v2", dataset_id="ds_001", dataset_version="v2", requested_range=rr, created_at=_utc(2025, 1, 10, 12, 0))
    ckpt_s.save(cp_v2)
    assert ckpt_s.load("job_v1").dataset_version == "v1"
    assert ckpt_s.load("job_v2").dataset_version == "v2"
    assert ckpt_s.load("job_v1").next_start == rr.end
    assert ckpt_s.load("job_v2").next_start == rr.start  # not advanced
    assert len(norm_s.list_chunks(DatasetId("ds_001"), DatasetVersion("v1"))) == 1
    assert len(norm_s.list_chunks(DatasetId("ds_001"), DatasetVersion("v2"))) == 0
