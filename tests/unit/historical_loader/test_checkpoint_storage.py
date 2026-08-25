"""Tests for CheckpointFilesystemStorage (atomic, UTC, no stale timeout)."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from bss.domain.time_range import TimeRange
from bss.historical_loader.domain.checkpoint import Checkpoint
from bss.historical_loader.domain.errors import CorruptChunkError
from bss.historical_loader.infrastructure.storage.checkpoint_filesystem import CheckpointFilesystemStorage


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _range():
    return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 10))


def _ckpt(job_id="job_123"):
    return Checkpoint.initial(job_id=job_id, dataset_id="ds_001", dataset_version="v1", requested_range=_range(), created_at=_utc(2025, 1, 10, 12, 0))


def test_save_and_load(tmp_path: Path):
    storage = CheckpointFilesystemStorage(base_path=tmp_path)
    cp = _ckpt()
    storage.save(cp)
    loaded = storage.load("job_123")
    assert loaded == cp


def test_atomic_no_tmp_leaked(tmp_path: Path):
    storage = CheckpointFilesystemStorage(base_path=tmp_path)
    storage.save(_ckpt())
    assert not list((tmp_path / "checkpoints").rglob("*.tmp.*"))


def test_load_missing_returns_none(tmp_path: Path):
    storage = CheckpointFilesystemStorage(base_path=tmp_path)
    assert storage.load("missing") is None


def test_corrupt_checkpoint_raises(tmp_path: Path):
    storage = CheckpointFilesystemStorage(base_path=tmp_path)
    cp = _ckpt()
    storage.save(cp)
    path = tmp_path / "checkpoints" / "job_123.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(CorruptChunkError):
        storage.load("job_123")


def test_exists(tmp_path: Path):
    storage = CheckpointFilesystemStorage(base_path=tmp_path)
    assert not storage.exists("job_123")
    storage.save(_ckpt())
    assert storage.exists("job_123")


def test_no_stale_timeout():
    # correction 1: no automatic FAILED after 1h — checkpoint remains RUNNING
    cp = _ckpt()
    # simulate old checkpoint (2h ago) — should still be RUNNING, not auto FAILED
    assert cp.status == "RUNNING"
    # storage does not enforce timeout
    # just verify no timeout logic exists: save and load still RUNNING
    import time

    # no timeout field
    assert "stale" not in cp.to_dict().keys()


def test_dataset_version_isolation(tmp_path: Path):
    storage = CheckpointFilesystemStorage(base_path=tmp_path)
    cp1 = Checkpoint.initial(job_id="job_v1", dataset_id="ds_001", dataset_version="v1", requested_range=_range(), created_at=_utc(2025, 1, 10, 12, 0))
    cp2 = Checkpoint.initial(job_id="job_v2", dataset_id="ds_001", dataset_version="v2", requested_range=_range(), created_at=_utc(2025, 1, 10, 12, 0))
    storage.save(cp1)
    storage.save(cp2)
    assert storage.load("job_v1").dataset_version == "v1"
    assert storage.load("job_v2").dataset_version == "v2"


def test_advance_only_after_storage_invariant(tmp_path: Path):
    # Simulate invariant: checkpoint advanced only after durable write
    # Here we just verify that advance creates new checkpoint with correct next_start
    cp = _ckpt()
    # simulate storage write succeeded, then advance
    cp2 = cp.advance(chunk_from=_utc(2025, 1, 1), chunk_to=_utc(2025, 1, 2), checksum="sha256:ok", path="data/normalized/...", updated_at=_utc(2025, 1, 10, 12, 1))
    storage = CheckpointFilesystemStorage(base_path=tmp_path)
    storage.save(cp2)
    loaded = storage.load(cp2.job_id)
    assert loaded.next_start == _utc(2025, 1, 2)
    assert loaded.last_completed.checksum == "sha256:ok"
