"""Recovery domain models (deterministic, UTC, immutable)."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum
from typing import Tuple

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time import ensure_utc


class RecoveryReason(str, Enum):
    DATA_INTEGRITY_GAP = "DATA_INTEGRITY_GAP"
    MISSING_CHUNK = "MISSING_CHUNK"
    CORRUPT_CHUNK = "CORRUPT_CHUNK"


@dataclasses.dataclass(frozen=True)
class RecoveryRange:
    start: datetime
    end: datetime
    reason: RecoveryReason

    def __post_init__(self) -> None:
        ensure_utc(self.start, "RecoveryRange.start")
        ensure_utc(self.end, "RecoveryRange.end")
        if self.start >= self.end:
            raise ValueError("RecoveryRange start must be < end")

    def to_dict(self) -> dict:
        return {"from": self.start.isoformat(), "to": self.end.isoformat(), "reason": self.reason.value}

    @classmethod
    def from_dict(cls, data: dict) -> "RecoveryRange":
        from bss.domain.time import parse_utc

        return cls(start=parse_utc(data["from"]), end=parse_utc(data["to"]), reason=RecoveryReason(data["reason"]))


@dataclasses.dataclass(frozen=True)
class RecoveryPlan:
    """Immutable, deterministic plan. Ranges sorted by start."""

    dataset_id: DatasetId
    dataset_version: DatasetVersion
    ranges: Tuple[RecoveryRange, ...]

    def __post_init__(self) -> None:
        if not self.ranges:
            # empty plan is allowed (no recovery needed)
            return
        # sorted check
        sorted_ranges = tuple(sorted(self.ranges, key=lambda r: r.start))
        if self.ranges != sorted_ranges:
            raise ValueError("RecoveryPlan ranges must be sorted by start")
        # no overlap, start < end already checked
        for i in range(1, len(self.ranges)):
            if self.ranges[i - 1].end > self.ranges[i].start:
                raise ValueError("RecoveryPlan ranges must not overlap")
            ensure_utc(self.ranges[i].start, f"ranges[{i}].start")
            ensure_utc(self.ranges[i].end, f"ranges[{i}].end")

    def to_dict(self) -> dict:
        return {
            "dataset_id": str(self.dataset_id),
            "dataset_version": str(self.dataset_version),
            "ranges": [r.to_dict() for r in self.ranges],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecoveryPlan":
        return cls(
            dataset_id=DatasetId(data["dataset_id"]),
            dataset_version=DatasetVersion(data["dataset_version"]),
            ranges=tuple(RecoveryRange.from_dict(r) for r in data.get("ranges", [])),
        )

    @property
    def is_empty(self) -> bool:
        return len(self.ranges) == 0
