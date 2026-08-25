"""Tests for Checkpoint compact (correction 4,5)."""

from datetime import datetime, timezone

import pytest

from bss.domain.time_range import TimeRange
from bss.historical_loader.domain.checkpoint import Checkpoint


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _range():
    return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 10))


def _ckpt():
    return Checkpoint.initial(job_id="job_123", dataset_id="ds_001", dataset_version="v1", requested_range=_range(), created_at=_utc(2025, 1, 10, 12, 0))


def test_initial():
    cp = _ckpt()
    assert cp.next_start == _range().start
    assert cp.last_completed is None
    assert not cp.is_complete
    assert cp.status == "RUNNING"


def test_advance():
    cp = _ckpt()
    cp2 = cp.advance(chunk_from=_utc(2025, 1, 1), chunk_to=_utc(2025, 1, 2), checksum="sha256:abc", path="data/normalized/.../chunk.jsonl", updated_at=_utc(2025, 1, 10, 12, 1))
    assert cp2.last_completed.start == _utc(2025, 1, 1)
    assert cp2.next_start == _utc(2025, 1, 2)
    assert cp2.last_completed.checksum == "sha256:abc"


def test_advance_wrong_next_start_raises():
    cp = _ckpt()
    with pytest.raises(ValueError, match="chunk_from.*next_start"):
        cp.advance(chunk_from=_utc(2025, 1, 2), chunk_to=_utc(2025, 1, 3), checksum="x", path="p", updated_at=_utc(2025, 1, 10, 12, 1))


def test_advance_beyond_range_raises():
    cp = _ckpt()
    # chunk_from must equal next_start (2025-01-01), chunk_to beyond 2025-01-10
    with pytest.raises(ValueError, match="beyond requested_range"):
        cp.advance(chunk_from=_utc(2025, 1, 1), chunk_to=_utc(2025, 1, 11), checksum="x", path="p", updated_at=_utc(2025, 1, 10, 12, 1))


def test_compact_not_list():
    cp = _ckpt()
    # ensure no completed_chunks list
    assert not hasattr(cp, "completed_chunks")
    assert hasattr(cp, "last_completed")
    assert hasattr(cp, "next_start")


def test_to_dict_roundtrip():
    cp = _ckpt().advance(chunk_from=_utc(2025, 1, 1), chunk_to=_utc(2025, 1, 2), checksum="abc", path="p", updated_at=_utc(2025, 1, 10, 12, 1))
    d = cp.to_dict()
    cp2 = Checkpoint.from_dict(d)
    assert cp == cp2
    # Z handling
    d["next_start"] = "2025-01-02T00:00:00Z"
    cp3 = Checkpoint.from_dict(d)
    assert cp3.next_start.tzinfo == timezone.utc


def test_is_complete():
    cp = _ckpt()
    cp2 = cp.advance(chunk_from=_utc(2025, 1, 1), chunk_to=_utc(2025, 1, 10), checksum="x", path="p", updated_at=_utc(2025, 1, 10, 12, 1))
    assert cp2.is_complete


def test_utc_required():
    with pytest.raises(ValueError, match="timezone-aware"):
        Checkpoint(job_id="j", dataset_id="ds", dataset_version="v1", requested_range=_range(), next_start=datetime(2025, 1, 1), updated_at=_utc(2025, 1, 10, 12, 0))
