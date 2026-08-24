"""Instrument entity and InstrumentId value type."""

from __future__ import annotations

import dataclasses
from typing import Optional


@dataclasses.dataclass(frozen=True)
class InstrumentId:
    """Value type for a stable instrument identifier."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("InstrumentId must not be empty")

    def __str__(self) -> str:
        return self.value


@dataclasses.dataclass(frozen=True)
class Instrument:
    """A tradeable instrument."""

    instrument_id: InstrumentId
    symbol: str
    base: str
    quote: str
    exchange: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if not self.base or not self.base.strip():
            raise ValueError("base must not be empty")
        if not self.quote or not self.quote.strip():
            raise ValueError("quote must not be empty")