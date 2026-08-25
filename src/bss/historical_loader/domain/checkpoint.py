"""Checkpoint — compact, sequential (corrections 4,5).

Compact representation: last_completed + next_start, not O(N) list.
Invariant: advance only after durable storage (caller enforces).
No stale timeout/lease (correction 1).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any, Dict

from bss.domain.time import ensure_utc, parse_utc
from bss.domain.time_range import TimeRange


@dataclasses.dataclass(frozen=True)
class LastCompleted:
    """Last durably stored chunk."""

    start: datetime
    end: datetime
    checksum: str
    path: str

    def __post_init__(self) -> None:
        ensure_utc(self.start, "last_completed.start")
        ensure_utc(self.end, "last_completed.end")
        if not self.checksum or not self.checksum.strip():
            raise ValueError("checksum must not be empty")
        if not self.path or not self.path.strip():
            raise ValueError("path must not be empty")
        if self.start >= self.end:
            raise ValueError("last_completed start must be < end")

    def to_dict(self) -> Dict[str, Any]:
        return {"from": self.start.isoformat(), "to": self.end.isoformat(), "checksum": self.checksum, "path": self.path}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LastCompleted":
        return cls(start=parse_utc(data["from"]), end=parse_utc(data["to"]), checksum=data["checksum"], path=data["path"])


@dataclasses.dataclass(frozen=True)
class Checkpoint:
    """Immutable checkpoint for a DownloadJob.

    Sequential loading: next_start == last_completed.to if present, else requested_from.
    """

    job_id: str
    dataset_id: str
    dataset_version: str
    requested_range: TimeRange
    next_start: datetime
    updated_at: datetime
    last_completed: LastCompleted | None = None
    status: str = "RUNNING"  # RUNNING, PAUSED, FAILED, COMPLETED

    def __post_init__(self) -> None:
        if not self.job_id or not self.job_id.strip():
            raise ValueError("job_id must not be empty")
        ensure_utc(self.next_start, "next_start")
        ensure_utc(self.updated_at, "updated_at")
        # next_start must be within requested_range
        if self.next_start < self.requested_range.start or self.next_start > self.requested_range.end:
            raise ValueError("next_start outside requested_range")
        if self.last_completed:
            # last_completed must be before next_start
            if self.last_completed.end != self.next_start:
                # allow last_completed.end == next_start for sequential, but also handle initial null
                # we enforce equality for sequential correctness
                if self.last_completed.end != self.next_start:
                    raise ValueError("last_completed.end must equal next_start")
            # last_completed must be within requested_range
            if self.last_completed.start < self.requested_range.start or self.last_completed.end > self.requested_range.end:
                raise ValueError("last_completed outside requested_range")

    @staticmethod
    def initial(job_id: str, dataset_id: str, dataset_version: str, requested_range: TimeRange, created_at: datetime) -> "Checkpoint":
        ensure_utc(created_at, "created_at")
        ensure_utc(requested_range.start, "requested_range.start")
        ensure_utc(requested_range.end, "requested_range.end")
        return Checkpoint(
            job_id=job_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            requested_range=requested_range,
            next_start=requested_range.start,
            updated_at=created_at,
            last_completed=None,
            status="RUNNING",
        )

    def advance(self, chunk_from: datetime, chunk_to: datetime, checksum: str, path: str, updated_at: datetime) -> "Checkpoint":
        ensure_utc(chunk_from, "chunk_from")
        ensure_utc(chunk_to, "chunk_to")
        ensure_utc(updated_at, "updated_at")
        if chunk_from != self.next_start:
            raise ValueError(f"chunk_from {chunk_from.isoformat()} != next_start {self.next_start.isoformat()}")
        if chunk_from >= chunk_to:
            raise ValueError("chunk_from must be < chunk_to")
        if chunk_to > self.requested_range.end:
            raise ValueError("chunk_to beyond requested_range")
        lc = LastCompleted(start=chunk_from, end=chunk_to, checksum=checksum, path=path)
        return dataclasses.replace(self, last_completed=lc, next_start=chunk_to, updated_at=updated_at)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "requested_range": {"from": self.requested_range.start.isoformat(), "to": self.requested_range.end.isoformat()},
            "next_start": self.next_start.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_completed": self.last_completed.to_dict() if self.last_completed else None,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        rr = data["requested_range"]
        return cls(
            job_id=data["job_id"],
            dataset_id=data["dataset_id"],
            dataset_version=data["dataset_version"],
            requested_range=TimeRange(start=parse_utc(rr["from"]), end=parse_utc(rr["to"])),
            next_start=parse_utc(data["next_start"]),
            updated_at=parse_utc(data["updated_at"]),
            last_completed=LastCompleted.from_dict(data["last_completed"]) if data.get("last_completed") else None,
            status=data.get("status", "RUNNING"),
        )

    @property
    def is_complete(self) -> bool:
        return self.next_start == self.requested_range.end
