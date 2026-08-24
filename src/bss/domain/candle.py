"""Candle — immutable OHLCV value object."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

from .identifiers import CandleId
from .timeframe import Timeframe


def _parse_utc(iso_str: str) -> datetime:
    """Parse an ISO 8601 string and convert to UTC.

    Raises ValueError if the string lacks timezone info.
    """
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


@dataclasses.dataclass(frozen=True)
class Candle:
    """A single normalized OHLCV candle.

    All timestamps are timezone-aware UTC.
    The candle is immutable — once created its fields never change.
    """

    candle_id: CandleId
    instrument_id: str
    symbol: str
    timeframe: Timeframe
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        """Validate invariants after construction."""
        # ── timezone awareness ──────────────────────────────
        for field_name in ("open_time", "close_time"):
            ts = getattr(self, field_name)
            if ts.tzinfo is None:
                raise ValueError(
                    f"{field_name} must be timezone-aware UTC, got naive {ts}"
                )

        # ── OHLC consistency ────────────────────────────────
        if not (self.low <= self.high):
            raise ValueError(
                f"low ({self.low}) must be <= high ({self.high})"
            )
        if not (self.low <= self.open <= self.high):
            raise ValueError(
                f"open ({self.open}) not in [low={self.low}, high={self.high}]"
            )
        if not (self.low <= self.close <= self.high):
            raise ValueError(
                f"close ({self.close}) not in [low={self.low}, high={self.high}]"
            )
        if self.volume < 0:
            raise ValueError(f"volume ({self.volume}) must be >= 0")

        # ── time ordering ───────────────────────────────────
        if self.open_time >= self.close_time:
            raise ValueError(
                f"open_time ({self.open_time}) must be < close_time ({self.close_time})"
            )

    # ── factory helpers ────────────────────────────────────────

    @staticmethod
    def build_candle_id(symbol: str, timeframe: Timeframe, open_time: datetime) -> CandleId:
        """Deterministic candle ID based on symbol, timeframe and open time.

        Uses ISO 8601 with microseconds for global uniqueness
        (see Event Model v0.2 §2.1 — event_id must be globally unique).
        """
        ts = open_time.isoformat()
        return CandleId(f"cnd_{symbol}_{timeframe.value}_{ts}")

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "candle_id": str(self.candle_id),
            "instrument_id": self.instrument_id,
            "instrument_id": self.instrument_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Candle:
        """Deserialize from a dictionary (produced by *to_dict*)."""
        return cls(
            candle_id=CandleId(data["candle_id"]),
            instrument_id=data["instrument_id"],
            symbol=data["symbol"],
            timeframe=Timeframe.from_string(data["timeframe"]),
            open_time=_parse_utc(data["open_time"]),
            close_time=_parse_utc(data["close_time"]),
            open=Decimal(data["open"]),
            high=Decimal(data["high"]),
            low=Decimal(data["low"]),
            close=Decimal(data["close"]),
            volume=Decimal(data["volume"]),
        )

    # ── candle body helpers ────────────────────────────────────

    def body_direction(self) -> str:
        """Return 'UP' if close > open, 'DOWN' if close < open, 'FLAT' otherwise."""
        if self.close > self.open:
            return "UP"
        if self.close < self.open:
            return "DOWN"
        return "FLAT"

    def body_lower(self) -> Decimal:
        """Return the lower bound of the candle body."""
        return min(self.open, self.close)

    def body_upper(self) -> Decimal:
        """Return the upper bound of the candle body."""
        return max(self.open, self.close)

    def contains_price(self, price: Decimal) -> bool:
        """Check whether *price* lies within the high-low range."""
        return self.low <= price <= self.high