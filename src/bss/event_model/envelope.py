"""CANDLE_CLOSED Event envelope (minimal, immutable, UTC strict)."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from bss.domain.candle import Candle
from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time import ensure_utc, parse_utc
from bss.domain.timeframe import Timeframe


@dataclasses.dataclass(frozen=True)
class CandleClosedEvent:
    """Immutable CANDLE_CLOSED event. Deterministic ordering by event_time, not event_id."""

    event_id: str
    event_type: str  # "CANDLE_CLOSED"
    schema_version: str  # "0.2"
    event_time: datetime  # UTC, candle close_time or open_time? Use close_time as event_time
    processed_at: datetime  # UTC
    run_id: str
    dataset_id: DatasetId
    dataset_version: DatasetVersion
    symbol: str
    timeframe: Timeframe
    payload: Dict[str, Any]  # candle OHLCV + identifiers

    def __post_init__(self) -> None:
        ensure_utc(self.event_time, "event_time")
        ensure_utc(self.processed_at, "processed_at")
        if not self.event_id:
            raise ValueError("event_id required")
        if self.event_type != "CANDLE_CLOSED":
            raise ValueError("event_type must be CANDLE_CLOSED")
        if self.schema_version != "0.2":
            raise ValueError("schema_version must be 0.2")
        if not self.run_id:
            raise ValueError("run_id required")
        if not self.symbol:
            raise ValueError("symbol required")

    @staticmethod
    def create(
        candle: Candle,
        run_id: str,
        dataset_id: DatasetId,
        dataset_version: DatasetVersion,
        processed_at: datetime | None = None,
        schema_version: str = "0.2",
    ) -> "CandleClosedEvent":
        ensure_utc(candle.open_time, "candle.open_time")
        ensure_utc(candle.close_time, "candle.close_time")
        if not run_id:
            raise ValueError("run_id required")
        pa = processed_at or datetime.now(timezone.utc)
        ensure_utc(pa, "processed_at")
        # event_time is candle close_time (market event)
        return CandleClosedEvent(
            event_id=f"evt_{uuid.uuid4().hex}",
            event_type="CANDLE_CLOSED",
            schema_version=schema_version,
            event_time=candle.close_time,
            processed_at=pa,
            run_id=run_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            payload={
                "candle": candle.to_dict(),
                "open_time": candle.open_time.isoformat(),
                "close_time": candle.close_time.isoformat(),
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "event_time": self.event_time.isoformat(),
            "processed_at": self.processed_at.isoformat(),
            "run_id": self.run_id,
            "dataset_id": str(self.dataset_id),
            "dataset_version": str(self.dataset_version),
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandleClosedEvent":
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            event_time=parse_utc(data["event_time"]),
            processed_at=parse_utc(data["processed_at"]),
            run_id=data["run_id"],
            dataset_id=DatasetId(data["dataset_id"]),
            dataset_version=DatasetVersion(data["dataset_version"]),
            symbol=data["symbol"],
            timeframe=Timeframe.from_string(data["timeframe"]),
            payload=data["payload"],
        )
