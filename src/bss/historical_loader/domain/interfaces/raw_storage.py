"""RawStorage — domain interface for raw layer (ЧТЗ §5, ADR-002)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from bss.domain.timeframe import Timeframe

from ..dataset import CandleBatch


@runtime_checkable
class RawStorage(Protocol):
    """Abstract raw storage (file-first hidden behind interface)."""

    def write_raw(self, batch: CandleBatch) -> Path:
        """Atomically write raw batch chunk, idempotent. Returns final path."""
        ...

    def exists(self, source: str, symbol: str, timeframe: Timeframe, date: str) -> bool:
        """Check existence of raw chunk for given date (YYYY-MM-DD)."""
        ...

    def read_raw(self, source: str, symbol: str, timeframe: Timeframe, date: str) -> Iterable[CandleBatch]:
        """Streaming read of raw chunks for date (generator)."""
        ...

    def list_raw(self, source: str, symbol: str, timeframe: Timeframe) -> list[Path]:
        """List all raw chunk paths for symbol/timeframe, deterministic ordering."""
        ...
