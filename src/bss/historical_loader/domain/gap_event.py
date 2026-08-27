"""Minimal DATA_INTEGRITY_GAP event (file-first, immutable)."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time import ensure_utc, parse_utc
from bss.domain.timeframe import Timeframe


@dataclasses.dataclass(frozen=True)
class DataIntegrityGapEvent:
    """Minimal envelope for DATA_INTEGRITY_GAP (compatible with Event Model)."""

    event_id: str
    event_type: str  # DATA_INTEGRITY_GAP
    schema_version: str
    event_time: datetime  # market event time (gap start)
    processed_at: datetime  # system time
    source: str
    payload: Dict[str, Any]

    def __post_init__(self) -> None:
        ensure_utc(self.event_time, "event_time")
        ensure_utc(self.processed_at, "processed_at")
        if not self.event_id:
            raise ValueError("event_id required")
        if self.event_type != "DATA_INTEGRITY_GAP":
            raise ValueError("event_type must be DATA_INTEGRITY_GAP")

    @staticmethod
    def create(
        dataset_id: DatasetId,
        dataset_version: DatasetVersion,
        symbol: str,
        timeframe: Timeframe,
        gap_from: datetime,
        gap_to: datetime,
        expected: int,
        actual: int,
        source: str = "loader",
        schema_version: str = "0.2",
        event_time: datetime | None = None,
        processed_at: datetime | None = None,
    ) -> "DataIntegrityGapEvent":
        ensure_utc(gap_from, "gap_from")
        ensure_utc(gap_to, "gap_to")
        now = datetime.now(timezone.utc)
        et = event_time or gap_from
        pa = processed_at or now
        ensure_utc(et, "event_time")
        ensure_utc(pa, "processed_at")
        return DataIntegrityGapEvent(
            event_id=f"evt_{uuid.uuid4().hex}",
            event_type="DATA_INTEGRITY_GAP",
            schema_version=schema_version,
            event_time=et,
            processed_at=pa,
            source=source,
            payload={
                "dataset_id": str(dataset_id),
                "dataset_version": str(dataset_version),
                "symbol": symbol,
                "timeframe": timeframe.value,
                "from": gap_from.isoformat(),
                "to": gap_to.isoformat(),
                "expected_candles": expected,
                "actual_candles": actual,
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "event_time": self.event_time.isoformat(),
            "processed_at": self.processed_at.isoformat(),
            "source": self.source,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataIntegrityGapEvent":
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            event_time=parse_utc(data["event_time"]),
            processed_at=parse_utc(data["processed_at"]),
            source=data["source"],
            payload=data["payload"],
        )
