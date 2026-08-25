"""DatasetStorage (Normalized) — domain interface (ЧТЗ §6, ADR-002)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from bss.domain.candle import Candle
from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.timeframe import Timeframe

from ..dataset import CandleBatch


class ChunkInfo:
    """Metadata about a stored chunk."""

    def __init__(self, path: Path, symbol: str, timeframe: Timeframe, count: int, checksum: str):
        self.path = path
        self.symbol = symbol
        self.timeframe = timeframe
        self.count = count
        self.checksum = checksum


class ChecksumReport:
    """Result of verify operation."""

    def __init__(self, ok: bool, missing: list[Path], corrupt: list[Path]):
        self.ok = ok
        self.missing = missing
        self.corrupt = corrupt


@runtime_checkable
class DatasetStorage(Protocol):
    """Abstract normalized dataset storage."""

    def write_batch(self, batch: CandleBatch, dataset_id: DatasetId, version: DatasetVersion) -> Path:
        """Atomically write normalized batch chunk, idempotent by chunk identity. Returns final path."""
        ...

    def stream(self, dataset_id: DatasetId, version: DatasetVersion, symbol: str, timeframe: Timeframe, start=None, end=None) -> Iterable[Candle]:
        """Streaming read of candles, deterministic order, no full RAM load."""
        ...

    def list_chunks(self, dataset_id: DatasetId, version: DatasetVersion) -> list[Path]:
        """List all chunk paths for dataset version, deterministic ordering."""
        ...

    def verify(self, dataset_id: DatasetId, version: DatasetVersion) -> ChecksumReport:
        """Verify existence and checksum of all chunks."""
        ...
