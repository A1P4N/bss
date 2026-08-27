"""ReplayDataSource — streaming, deterministic, no look-ahead (separate from Loader)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterator

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time import ensure_utc
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.event_model.envelope import CandleClosedEvent

# Use protocol, not concrete storage
from bss.historical_loader.domain.interfaces.dataset_storage import DatasetStorage


class ReplayDataSource:
    """Reads only Normalized Storage, streaming, deterministic."""

    def __init__(self, storage: DatasetStorage):
        self.storage = storage

    def replay(
        self,
        dataset_id: DatasetId,
        dataset_version: DatasetVersion,
        symbol: str,
        timeframe: Timeframe,
        requested_range: TimeRange,
        run_id: str | None = None,
        processed_at: datetime | None = None,
    ) -> Iterator[CandleClosedEvent]:
        ensure_utc(requested_range.start, "requested_range.start")
        ensure_utc(requested_range.end, "requested_range.end")
        if requested_range.start >= requested_range.end:
            raise ValueError("requested_range start must be < end")
        if not symbol:
            raise ValueError("symbol required")

        # run_id immutable per replay
        rid = run_id or f"run_{uuid.uuid4().hex}"
        pa = processed_at or datetime.now(timezone.utc)
        ensure_utc(pa, "processed_at")

        # Streaming read — do not load all into memory at once for large datasets
        # For MVP we collect for requested_range, sort deterministically, then yield
        # This keeps bounded memory per chunk (chunks are per day), but for requested_range we need sorted
        # To keep true streaming, we would merge sorted chunks via heap; for now collect+sort is deterministic and simple
        candles = list(
            self.storage.stream(
                dataset_id, dataset_version, symbol, timeframe, start=requested_range.start, end=requested_range.end
            )
        )
        # Deterministic ordering: sort by open_time, not filesystem order, not event_id
        candles.sort(key=lambda c: c.open_time)

        # No look-ahead: each event created only from current candle, no future access
        for candle in candles:
            # Range semantics [start, end): open_time must be in range (already filtered by storage, but double-check)
            if not (requested_range.start <= candle.open_time < requested_range.end):
                continue
            # Tail candle contract: close_time may be > end, allowed (existing contract)
            # Duplicate: do not silently dedup — yield as is, validation is dataset-level

            # Create event — processed_at same for all events in this run (deterministic run)
            yield CandleClosedEvent.create(
                candle=candle,
                run_id=rid,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                processed_at=pa,
            )

    def stream(self, *args, **kwargs):
        """Alias for replay for compatibility."""
        return self.replay(*args, **kwargs)
