"""MetadataStorage — domain interface for DatasetMetadata (ЧТЗ §7, ADR-002)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from bss.domain.identifiers import DatasetId, DatasetVersion

from ..dataset import DatasetMetadata, DatasetStatus


@runtime_checkable
class MetadataStorage(Protocol):
    """Abstract metadata storage (atomic JSON)."""

    def save(self, meta: DatasetMetadata) -> Path:
        """Atomically save metadata. Enforces immutability if status READY."""
        ...

    def get(self, dataset_id: DatasetId, version: DatasetVersion) -> DatasetMetadata | None:
        """Load metadata or None if not exists."""
        ...

    def list_versions(self, dataset_id: DatasetId) -> list[DatasetVersion]:
        """List all versions for dataset_id, deterministic ordering."""
        ...

    def update_status(self, dataset_id: DatasetId, version: DatasetVersion, status: DatasetStatus) -> DatasetMetadata:
        """Atomically update status, enforcing immutability."""
        ...
