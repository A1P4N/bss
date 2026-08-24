"""Identifier value types and source-type enum."""

from __future__ import annotations

import dataclasses
from enum import Enum


class SourceType(str, Enum):
    """Origin of an event stream."""

    HISTORICAL = "historical"
    LIVE = "live"


# ── ID value types ─────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class CandleId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("CandleId must not be empty")

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"CandleId({self.value!r})"


@dataclasses.dataclass(frozen=True)
class DatasetId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("DatasetId must not be empty")

    def __str__(self) -> str:
        return self.value


@dataclasses.dataclass(frozen=True)
class DatasetVersion:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("DatasetVersion must not be empty")

    def __str__(self) -> str:
        return self.value


@dataclasses.dataclass(frozen=True)
class EventId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("EventId must not be empty")

    def __str__(self) -> str:
        return self.value