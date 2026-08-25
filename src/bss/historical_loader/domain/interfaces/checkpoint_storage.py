"""CheckpointStorage — domain interface (file-first, atomic)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..checkpoint import Checkpoint


@runtime_checkable
class CheckpointStorage(Protocol):
    def save(self, checkpoint: Checkpoint) -> None:
        """Atomically save checkpoint (tmp→replace)."""
        ...

    def load(self, job_id: str) -> Checkpoint | None:
        """Load checkpoint or None if not exists. Raises on corrupt."""
        ...

    def exists(self, job_id: str) -> bool: ...
