"""MetadataFilesystemStorage — atomic JSON for DatasetMetadata (ЧТЗ §7, ADR-002)."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from bss.domain.identifiers import DatasetId, DatasetVersion

from ...domain.dataset import DatasetMetadata, DatasetStatus
from ...domain.errors import ImmutableViolation, StorageError


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp.{uuid.uuid4().hex}"
    try:
        tmp.write_bytes(content)
        with tmp.open("rb") as f:
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        tmp.replace(path)
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


class MetadataFilesystemStorage:
    """Filesystem metadata storage."""

    def __init__(self, base_path: Path | str = "data"):
        self.base = Path(base_path) / "metadata" / "datasets"

    def _path(self, dataset_id: DatasetId, version: DatasetVersion) -> Path:
        return self.base / str(dataset_id) / f"{str(version)}.json"

    def save(self, meta: DatasetMetadata) -> Path:
        path = self._path(meta.dataset_id, meta.dataset_version)
        # enforce immutability if existing is READY
        if path.exists():
            try:
                existing = self.get(meta.dataset_id, meta.dataset_version)
                if existing and existing.status == DatasetStatus.READY and existing != meta:
                    raise ImmutableViolation(
                        code="IMMUTABLE_VIOLATION",
                        message="published READY version is immutable",
                        context={"dataset_id": str(meta.dataset_id), "version": str(meta.dataset_version)},
                    )
            except ImmutableViolation:
                raise
            except Exception:
                pass  # if corrupt, overwrite
        content = json.dumps(meta.to_dict(), indent=2, sort_keys=True).encode("utf-8")
        try:
            _atomic_write(path, content)
        except ImmutableViolation:
            raise
        except Exception as exc:
            raise StorageError(code="WRITE_FAILED", message=str(exc), context={"path": str(path)}) from exc
        return path

    def get(self, dataset_id: DatasetId, version: DatasetVersion) -> DatasetMetadata | None:
        path = self._path(dataset_id, version)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return DatasetMetadata.from_dict(data)
        except Exception as exc:
            raise StorageError(code="CORRUPT_METADATA", message=str(exc), context={"path": str(path)}) from exc

    def list_versions(self, dataset_id: DatasetId) -> list[DatasetVersion]:
        base = self.base / str(dataset_id)
        if not base.exists():
            return []
        versions = []
        for p in sorted(base.glob("*.json")):
            try:
                ver = DatasetVersion(p.stem)
                versions.append(ver)
            except Exception:
                continue
        # deterministic ordering by string
        return sorted(versions, key=lambda v: str(v))

    def update_status(self, dataset_id: DatasetId, version: DatasetVersion, status: DatasetStatus) -> DatasetMetadata:
        meta = self.get(dataset_id, version)
        if meta is None:
            raise StorageError(code="NOT_FOUND", message="metadata not found", context={"dataset_id": str(dataset_id), "version": str(version)})
        if meta.status == DatasetStatus.READY:
            raise ImmutableViolation(code="IMMUTABLE_VIOLATION", message="cannot update READY version", context={"dataset_id": str(dataset_id), "version": str(version)})
        # create new metadata with updated status (frozen, so replace)
        import dataclasses

        new_meta = dataclasses.replace(meta, status=status)
        self.save(new_meta)
        return new_meta

    def verify(self, dataset_id: DatasetId, version: DatasetVersion) -> bool:
        """Check existence and not corrupt."""
        path = self._path(dataset_id, version)
        if not path.exists():
            return False
        try:
            json.loads(path.read_text(encoding="utf-8"))
            return True
        except Exception:
            return False
