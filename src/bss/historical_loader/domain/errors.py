"""Typed errors for Loader domain (08_RULES §7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class LoaderError(Exception):
    """Base class for loader domain errors."""

    code: str
    message: str
    context: Dict[str, Any]

    def __str__(self) -> str:
        return f"[{self.code}] {self.message} context={self.context}"


class NormalizationError(LoaderError):
    """Raised when raw candle cannot be normalized to Candle."""



class ValidationError(LoaderError):
    """Raised for validation-specific failures (optional, ValidationResult preferred)."""



class DuplicateError(ValidationError):
    """Duplicate candle detected."""


class GapError(ValidationError):
    """Gap detected (missing candles)."""


class StorageError(LoaderError):
    """Storage layer error (atomicity, checksum, immutability)."""


class ImmutableViolation(StorageError):
    """Attempt to mutate published READY version."""


class CorruptChunkError(StorageError):
    """Chunk is partially written or checksum mismatch."""
