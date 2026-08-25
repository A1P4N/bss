"""Dataset domain models: DatasetStatus, DatasetMetadata, CandleBatch.

References:
- ЧТЗ §7 Dataset (metadata fields, READY only after validation, immutability)
- AGENTS.md §14 Dataset + §22 Time (UTC)
- ADR-002 file-first storage (metadata/versioning)
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Tuple

from bss.domain.candle import Candle
from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time import ensure_utc, parse_utc
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe


class DatasetStatus(str, Enum):
    """Lifecycle status of a Dataset version.

    See 04_IMPLEMENTATION_PLAN.md §8 and ЧТЗ §7.
    Transitions are enforced by application service, not by this value object.
    Allowed transitions (documented):
      CREATED -> DOWNLOADING -> VALIDATING -> READY
      VALIDATING -> INVALID
      READY -> RECOVERING -> VALIDATING -> READY
    """

    CREATED = "CREATED"
    DOWNLOADING = "DOWNLOADING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    INVALID = "INVALID"
    RECOVERING = "RECOVERING"


@dataclasses.dataclass(frozen=True)
class DatasetMetadata:
    """Immutable metadata of a versioned Dataset.

    Fields follow ЧТЗ §7 minimum + AGENTS.md §14 reproducibility set.
    `symbols` and `timeframes` are stored as sorted tuples for determinism.
    All datetimes are timezone-aware UTC.
    Published version after READY is immutable (ADR-002).
    """

    dataset_id: DatasetId
    dataset_version: DatasetVersion
    source: str
    symbols: Tuple[str, ...]
    timeframes: Tuple[Timeframe, ...]
    range: TimeRange
    created_at: datetime
    loader_version: str
    schema_version: str
    status: DatasetStatus = DatasetStatus.CREATED
    # reproducibility / replay fields (AGENTS.md §14)
    engine_version: str | None = None
    configuration_version: str | None = None
    # TBD until storage slice decides algorithm (ЧТЗ §7 checksum)
    checksum: str | None = None

    def __post_init__(self) -> None:
        # --- source / versions ---
        if not self.source or not self.source.strip():
            raise ValueError("source must not be empty")
        if not self.loader_version or not self.loader_version.strip():
            raise ValueError("loader_version must not be empty")
        if not self.schema_version or not self.schema_version.strip():
            raise ValueError("schema_version must not be empty")

        # --- symbols ---
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        for s in self.symbols:
            if not s or not s.strip():
                raise ValueError("symbol must not be empty")
        # determinism: must be sorted unique
        if tuple(sorted(self.symbols)) != self.symbols:
            raise ValueError("symbols must be sorted")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("symbols must be unique")

        # --- timeframes ---
        if not self.timeframes:
            raise ValueError("timeframes must not be empty")
        # timeframes unique (sorted by enum value for determinism)
        if len(set(self.timeframes)) != len(self.timeframes):
            raise ValueError("timeframes must be unique")
        # sort check by value string
        sorted_tf = tuple(sorted(self.timeframes, key=lambda t: t.value))
        if self.timeframes != sorted_tf:
            raise ValueError("timeframes must be sorted by value")

        # --- time ---
        ensure_utc(self.created_at, "created_at")

        # --- range already validated by TimeRange ---

    # ── serialisation ────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """JSON-compatible dict (deterministic order of symbols/timeframes preserved)."""
        return {
            "dataset_id": str(self.dataset_id),
            "dataset_version": str(self.dataset_version),
            "source": self.source,
            "symbols": list(self.symbols),
            "timeframes": [t.value for t in self.timeframes],
            "from": self.range.start.isoformat(),
            "to": self.range.end.isoformat(),
            "created_at": self.created_at.isoformat(),
            "loader_version": self.loader_version,
            "schema_version": self.schema_version,
            "status": self.status.value,
            "engine_version": self.engine_version,
            "configuration_version": self.configuration_version,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatasetMetadata":
        """Deserialize from dict produced by to_dict."""
        return cls(
            dataset_id=DatasetId(data["dataset_id"]),
            dataset_version=DatasetVersion(data["dataset_version"]),
            source=data["source"],
            symbols=tuple(data["symbols"]),
            timeframes=tuple(Timeframe.from_string(v) for v in data["timeframes"]),
            range=TimeRange(start=parse_utc(data["from"]), end=parse_utc(data["to"])),
            created_at=parse_utc(data["created_at"]),
            loader_version=data["loader_version"],
            schema_version=data["schema_version"],
            status=DatasetStatus(data["status"]) if "status" in data else DatasetStatus.CREATED,
            engine_version=data.get("engine_version"),
            configuration_version=data.get("configuration_version"),
            checksum=data.get("checksum"),
        )


@dataclasses.dataclass(frozen=True)
class CandleBatch:
    """Immutable batch of candles for a single symbol/timeframe.

    Returned by HistoricalSource.download as a chunk (ЧТЗ §9).
    All candles must share symbol/timeframe, be sorted by open_time,
    have unique candle_id and be timezone-aware UTC (delegated to Candle).
    Stored as tuple for immutability and determinism.
    """

    symbol: str
    timeframe: Timeframe
    candles: Tuple[Candle, ...]
    source: str
    requested_range: TimeRange

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if not self.source or not self.source.strip():
            raise ValueError("source must not be empty")

        # empty batch is allowed (e.g. no data for range) — but still validated range
        if not self.candles:
            return

        # all candles must match batch symbol/timeframe
        for c in self.candles:
            if c.symbol != self.symbol:
                raise ValueError(f"candle symbol {c.symbol!r} != batch symbol {self.symbol!r}")
            if c.timeframe != self.timeframe:
                raise ValueError(f"candle timeframe {c.timeframe} != batch timeframe {self.timeframe}")
            if not c.open_time.tzinfo or not c.close_time.tzinfo:
                raise ValueError("candle timestamps must be timezone-aware")

        # sorted by open_time strictly increasing (gaps/duplicates handled by validators, not here)
        for i in range(1, len(self.candles)):
            if self.candles[i - 1].open_time > self.candles[i].open_time:
                raise ValueError("candles must be sorted by open_time")
            if self.candles[i - 1].open_time == self.candles[i].open_time:
                # allow equal open_time to surface as duplicate via DuplicateDetector
                # but keep deterministic order: still require non-decreasing
                pass

        # uniqueness is checked by DuplicateDetector, not here (allows validation to report)
        # requested_range containment: open_time must be in [start, end) (ЧТЗ §10, P1-03)
        # close_time may exceed end for last candle when range not aligned to timeframe — allowed
        for c in self.candles:
            if c.open_time < self.requested_range.start or c.open_time >= self.requested_range.end:
                raise ValueError(
                    f"candle {c.candle_id} open_time {c.open_time.isoformat()} outside requested_range [{self.requested_range.start.isoformat()}->{self.requested_range.end.isoformat()})"
                )

    # ── helpers ────────────────────────────────────────────────

    @property
    def is_empty(self) -> bool:
        return len(self.candles) == 0

    @property
    def first(self) -> Candle | None:
        return self.candles[0] if self.candles else None

    @property
    def last(self) -> Candle | None:
        return self.candles[-1] if self.candles else None

    def __len__(self) -> int:
        return len(self.candles)

    # ── serialisation ────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "source": self.source,
            "requested_range": {
                "from": self.requested_range.start.isoformat(),
                "to": self.requested_range.end.isoformat(),
            },
            "candles": [c.to_dict() for c in self.candles],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandleBatch":
        rr = data["requested_range"]
        return cls(
            symbol=data["symbol"],
            timeframe=Timeframe.from_string(data["timeframe"]),
            source=data["source"],
            requested_range=TimeRange(start=parse_utc(rr["from"]), end=parse_utc(rr["to"])),
            candles=tuple(Candle.from_dict(d) for d in data["candles"]),
        )
