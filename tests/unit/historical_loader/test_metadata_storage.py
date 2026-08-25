"""Tests for MetadataFilesystemStorage (atomic, immutability, checksum)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import DatasetMetadata, DatasetStatus
from bss.historical_loader.domain.errors import ImmutableViolation
from bss.historical_loader.infrastructure.storage.metadata_filesystem import MetadataFilesystemStorage


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _meta(status=DatasetStatus.CREATED, version="v1", dataset_id="ds_001"):
    return DatasetMetadata(
        dataset_id=DatasetId(dataset_id),
        dataset_version=DatasetVersion(version),
        source="binance",
        symbols=("SOLUSDT",),
        timeframes=(Timeframe.M15,),
        range=TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 10)),
        created_at=_utc(2025, 1, 10, 12, 0),
        loader_version="0.1.0",
        schema_version="0.2",
        status=status,
    )


def test_save_and_get(tmp_path: Path):
    storage = MetadataFilesystemStorage(base_path=tmp_path)
    meta = _meta()
    path = storage.save(meta)
    assert path.exists()
    assert "metadata/datasets/ds_001/v1.json" in str(path).replace("\\", "/")
    loaded = storage.get(DatasetId("ds_001"), DatasetVersion("v1"))
    assert loaded == meta


def test_atomic_no_tmp_leaked(tmp_path: Path):
    storage = MetadataFilesystemStorage(base_path=tmp_path)
    storage.save(_meta())
    assert not list((tmp_path / "metadata").rglob("*.tmp.*"))


def test_immutability_ready(tmp_path: Path):
    storage = MetadataFilesystemStorage(base_path=tmp_path)
    meta = _meta(status=DatasetStatus.READY)
    storage.save(meta)
    # attempt to overwrite READY with different content
    meta2 = _meta(status=DatasetStatus.READY, version="v1")
    # change checksum
    import dataclasses

    meta2 = dataclasses.replace(meta2, checksum="different")
    with pytest.raises(ImmutableViolation):
        storage.save(meta2)
    # same content should be allowed? Currently save checks existing != meta, so same content would pass
    # saving same meta again should be idempotent? Let's test
    # same meta should not raise (since ==)
    storage.save(meta)  # should not raise


def test_update_status(tmp_path: Path):
    storage = MetadataFilesystemStorage(base_path=tmp_path)
    meta = _meta(status=DatasetStatus.CREATED)
    storage.save(meta)
    updated = storage.update_status(DatasetId("ds_001"), DatasetVersion("v1"), DatasetStatus.VALIDATING)
    assert updated.status == DatasetStatus.VALIDATING
    # update to READY
    updated2 = storage.update_status(DatasetId("ds_001"), DatasetVersion("v1"), DatasetStatus.READY)
    assert updated2.status == DatasetStatus.READY
    # cannot update READY
    with pytest.raises(ImmutableViolation):
        storage.update_status(DatasetId("ds_001"), DatasetVersion("v1"), DatasetStatus.INVALID)


def test_list_versions(tmp_path: Path):
    storage = MetadataFilesystemStorage(base_path=tmp_path)
    storage.save(_meta(version="v1"))
    storage.save(_meta(version="v2"))
    storage.save(_meta(version="v10"))
    versions = storage.list_versions(DatasetId("ds_001"))
    assert [str(v) for v in versions] == ["v1", "v10", "v2"]  # lexical sorted


def test_get_missing_returns_none(tmp_path: Path):
    storage = MetadataFilesystemStorage(base_path=tmp_path)
    assert storage.get(DatasetId("ds_001"), DatasetVersion("v99")) is None


def test_corrupt_metadata_raises(tmp_path: Path):
    storage = MetadataFilesystemStorage(base_path=tmp_path)
    meta = _meta()
    path = storage.save(meta)
    path.write_text("not json", encoding="utf-8")
    from bss.historical_loader.domain.errors import StorageError

    with pytest.raises(StorageError):
        storage.get(DatasetId("ds_001"), DatasetVersion("v1"))


def test_verify(tmp_path: Path):
    storage = MetadataFilesystemStorage(base_path=tmp_path)
    assert not storage.verify(DatasetId("ds_001"), DatasetVersion("v1"))
    storage.save(_meta())
    assert storage.verify(DatasetId("ds_001"), DatasetVersion("v1"))
