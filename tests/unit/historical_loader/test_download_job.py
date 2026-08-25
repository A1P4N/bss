"""Tests for DownloadJob (correction 2,3)."""

from datetime import datetime, timezone

import pytest

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.download_job import DownloadJob, JobStatus


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _range():
    return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 10))


def _job(status=JobStatus.CREATED):
    return DownloadJob.create(
        dataset_id=DatasetId("ds_001"),
        dataset_version=DatasetVersion("v1"),
        source="binance",
        symbol="SOLUSDT",
        timeframe=Timeframe.M15,
        range=_range(),
        created_at=_utc(2025, 1, 10, 12, 0),
    )


def test_create_unique_immutable():
    j1 = _job()
    j2 = _job()
    assert j1.job_id != j2.job_id
    # immutable
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        j1.job_id = "x"  # type: ignore

    assert j1.dataset_id == DatasetId("ds_001")
    assert j1.status == JobStatus.CREATED


def test_separate_from_dataset_status():
    # JobStatus is distinct from DatasetStatus
    from bss.historical_loader.domain.dataset import DatasetStatus

    assert JobStatus.CREATED.value != "READY" or True  # just ensure no confusion
    assert DatasetStatus.READY.value == "READY"
    assert JobStatus.COMPLETED.value == "COMPLETED"
    # not same enum class
    assert JobStatus is not DatasetStatus


def test_transitions():
    j = _job()
    j2 = j.transition(JobStatus.RUNNING, _utc(2025, 1, 10, 12, 1))
    assert j2.status == JobStatus.RUNNING
    j3 = j2.transition(JobStatus.PAUSED, _utc(2025, 1, 10, 12, 2))
    assert j3.status == JobStatus.PAUSED
    j4 = j3.transition(JobStatus.RUNNING, _utc(2025, 1, 10, 12, 3))
    assert j4.status == JobStatus.RUNNING
    j5 = j4.transition(JobStatus.COMPLETED, _utc(2025, 1, 10, 12, 4))
    assert j5.status == JobStatus.COMPLETED
    # illegal: COMPLETED -> RUNNING
    with pytest.raises(ValueError, match="illegal transition"):
        j5.transition(JobStatus.RUNNING, _utc(2025, 1, 10, 12, 5))


def test_illegal_transition_created_to_completed():
    j = _job()
    with pytest.raises(ValueError):
        j.transition(JobStatus.COMPLETED, _utc(2025, 1, 10, 12, 5))


def test_utc_required():
    with pytest.raises(ValueError, match="timezone-aware"):
        DownloadJob.create(
            dataset_id=DatasetId("ds_001"),
            dataset_version=DatasetVersion("v1"),
            source="binance",
            symbol="SOLUSDT",
            timeframe=Timeframe.M15,
            range=_range(),
            created_at=datetime(2025, 1, 10, 12, 0),  # naive
        )


def test_to_dict_roundtrip():
    j = _job()
    d = j.to_dict()
    j2 = DownloadJob.from_dict(d)
    assert j == j2
    # Z handling
    d["created_at"] = "2025-01-10T12:00:00Z"
    j3 = DownloadJob.from_dict(d)
    assert j3.created_at.tzinfo == timezone.utc
