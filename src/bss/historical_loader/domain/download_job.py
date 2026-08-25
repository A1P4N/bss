"""DownloadJob — lifecycle of a download (separate from DatasetStatus).

References: ЧТЗ §9, 04_PLAN §9, AGENTS §21.
JobStatus is distinct from DatasetStatus (correction 2).
job_id is unique & immutable, not deterministic (correction 3).
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Tuple

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time import ensure_utc
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe


class JobStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


@dataclasses.dataclass(frozen=True)
class DownloadJob:
    """Immutable snapshot of a download job. Transitions via replace."""

    job_id: str
    dataset_id: DatasetId
    dataset_version: DatasetVersion
    source: str
    symbol: str
    timeframe: Timeframe
    range: TimeRange
    created_at: datetime
    updated_at: datetime
    status: JobStatus = JobStatus.CREATED
    attempt: int = 1

    def __post_init__(self) -> None:
        if not self.job_id or not self.job_id.strip():
            raise ValueError("job_id must not be empty")
        if not self.source or not self.source.strip():
            raise ValueError("source must not be empty")
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        ensure_utc(self.created_at, "created_at")
        ensure_utc(self.updated_at, "updated_at")
        if self.attempt < 1:
            raise ValueError("attempt must be >=1")

    @staticmethod
    def create(
        dataset_id: DatasetId,
        dataset_version: DatasetVersion,
        source: str,
        symbol: str,
        timeframe: Timeframe,
        range: TimeRange,
        created_at: datetime,
    ) -> "DownloadJob":
        ensure_utc(created_at, "created_at")
        job_id = f"job_{uuid.uuid4().hex}"
        return DownloadJob(
            job_id=job_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            range=range,
            status=JobStatus.CREATED,
            created_at=created_at,
            updated_at=created_at,
            attempt=1,
        )

    def transition(self, new_status: JobStatus, updated_at: datetime) -> "DownloadJob":
        ensure_utc(updated_at, "updated_at")
        # simple allowed transitions: CREATED→RUNNING, RUNNING→PAUSED/FAILED/COMPLETED, PAUSED→RUNNING, FAILED→RUNNING (retry via new attempt)
        allowed = {
            JobStatus.CREATED: {JobStatus.RUNNING, JobStatus.FAILED},
            JobStatus.RUNNING: {JobStatus.PAUSED, JobStatus.FAILED, JobStatus.COMPLETED},
            JobStatus.PAUSED: {JobStatus.RUNNING, JobStatus.FAILED},
            JobStatus.FAILED: {JobStatus.RUNNING},
            JobStatus.COMPLETED: set(),
        }
        if new_status not in allowed.get(self.status, set()):
            raise ValueError(f"illegal transition {self.status} → {new_status}")
        return dataclasses.replace(self, status=new_status, updated_at=updated_at)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "dataset_id": str(self.dataset_id),
            "dataset_version": str(self.dataset_version),
            "source": self.source,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "range": {"from": self.range.start.isoformat(), "to": self.range.end.isoformat()},
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "attempt": self.attempt,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DownloadJob":
        from bss.domain.time import parse_utc

        return cls(
            job_id=data["job_id"],
            dataset_id=DatasetId(data["dataset_id"]),
            dataset_version=DatasetVersion(data["dataset_version"]),
            source=data["source"],
            symbol=data["symbol"],
            timeframe=Timeframe.from_string(data["timeframe"]),
            range=TimeRange(start=parse_utc(data["range"]["from"]), end=parse_utc(data["range"]["to"])),
            created_at=parse_utc(data["created_at"]),
            updated_at=parse_utc(data["updated_at"]),
            status=JobStatus(data["status"]),
            attempt=int(data.get("attempt", 1)),
        )
