"""Normalization of raw historical candles to BSS Candle (ЧТЗ §6, §10).

Pure domain service, no I/O, deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Tuple

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId
from bss.domain.time import parse_utc
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe

from .dataset import CandleBatch
from .errors import NormalizationError


@dataclass(frozen=True)
class RawCandle:
    """Raw input before normalization (flexible types)."""

    symbol: str
    timeframe: str
    open_time: Any  # str ISO or datetime
    close_time: Any
    open: Any
    high: Any
    low: Any
    close: Any
    volume: Any
    source: str = "unknown"
    instrument_id: str | None = None


def _to_datetime(value: Any, field: str, ctx: Dict[str, Any]) -> datetime:
    """Convert str/datetime to UTC datetime."""
    try:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError(f"{field} must be timezone-aware")
            return value.astimezone(timezone.utc)
        if isinstance(value, str):
            return parse_utc(value)
        raise ValueError(f"{field} must be datetime or ISO string, got {type(value).__name__}")
    except Exception as exc:
        raise NormalizationError(
            code="INVALID_TIMESTAMP",
            message=f"{field}: {exc}",
            context={**ctx, "field": field, "value": str(value)},
        ) from exc


def _to_decimal(value: Any, field: str, ctx: Dict[str, Any]) -> Decimal:
    try:
        # Use str(value) to avoid float binary errors
        d = Decimal(str(value))
        return d
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise NormalizationError(
            code="INVALID_NUMERIC",
            message=f"{field}: {exc}",
            context={**ctx, "field": field, "value": str(value)},
        ) from exc


class CandleNormalizer:
    """Maps RawCandle → Candle (single source of normalization)."""

    def normalize(self, raw: RawCandle) -> Candle:
        ctx = {"symbol": raw.symbol, "timeframe": raw.timeframe, "source": raw.source}
        # --- symbol/timeframe ---
        if not raw.symbol or not raw.symbol.strip():
            raise NormalizationError(code="INVALID_SYMBOL", message="symbol must not be empty", context=ctx)
        try:
            tf = Timeframe.from_string(raw.timeframe)
        except Exception as exc:
            raise NormalizationError(code="INVALID_TIMEFRAME", message=str(exc), context=ctx) from exc

        open_dt = _to_datetime(raw.open_time, "open_time", ctx)
        close_dt = _to_datetime(raw.close_time, "close_time", ctx)
        open_d = _to_decimal(raw.open, "open", ctx)
        high_d = _to_decimal(raw.high, "high", ctx)
        low_d = _to_decimal(raw.low, "low", ctx)
        close_d = _to_decimal(raw.close, "close", ctx)
        volume_d = _to_decimal(raw.volume, "volume", ctx)

        instrument_id = raw.instrument_id or f"inst_{raw.symbol.lower()}"
        # deterministic candle_id via Candle helper (UTC normalized)
        candle_id = Candle.build_candle_id(raw.symbol, tf, open_dt)

        try:
            return Candle(
                candle_id=candle_id,
                instrument_id=instrument_id,
                symbol=raw.symbol,
                timeframe=tf,
                open_time=open_dt,
                close_time=close_dt,
                open=open_d,
                high=high_d,
                low=low_d,
                close=close_d,
                volume=volume_d,
            )
        except ValueError as exc:
            # OHLC / ordering / UTC strict errors
            raise NormalizationError(code="INVALID_CANDLE", message=str(exc), context={**ctx, "open_time": open_dt.isoformat()}) from exc

    def normalize_batch(
        self,
        raws: Iterable[RawCandle],
        requested_range: TimeRange,
        source: str,
    ) -> CandleBatch:
        """Normalize iterable of RawCandle to CandleBatch.

        Sorts by open_time for determinism (AC-05).
        """
        raws_list = list(raws)
        if not raws_list:
            # empty batch — requires symbol/timeframe from first raw? use requested_range context
            # need at least one raw to infer symbol/timeframe; if empty, caller must provide batch separately
            # For empty, we create empty batch with symbol from requested context if provided via raws[0]
            # If no raws, return empty with placeholder — caller should handle
            raise NormalizationError(
                code="EMPTY_BATCH_NO_CONTEXT",
                message="empty raws without symbol/timeframe context",
                context={"source": source},
            )
        # infer symbol/timeframe from first (all must match)
        first_tf_str = raws_list[0].timeframe
        first_symbol = raws_list[0].symbol
        try:
            tf = Timeframe.from_string(first_tf_str)
        except Exception as exc:
            raise NormalizationError(code="INVALID_TIMEFRAME", message=str(exc), context={"symbol": first_symbol}) from exc

        candles = []
        for raw in raws_list:
            if raw.symbol != first_symbol:
                raise NormalizationError(
                    code="MISMATCHED_SYMBOL",
                    message=f"raw symbol {raw.symbol!r} != batch {first_symbol!r}",
                    context={"symbol": raw.symbol, "expected": first_symbol},
                )
            if raw.timeframe != first_tf_str:
                raise NormalizationError(
                    code="MISMATCHED_TIMEFRAME",
                    message=f"raw timeframe {raw.timeframe!r} != batch {first_tf_str!r}",
                    context={"timeframe": raw.timeframe},
                )
            c = self.normalize(raw)
            candles.append(c)

        # deterministic ordering
        candles.sort(key=lambda c: c.open_time)
        # check duplicates early (structured error)
        seen = set()
        for c in candles:
            cid = str(c.candle_id)
            if cid in seen:
                raise NormalizationError(code="DUPLICATE_CANDLE", message=f"duplicate {cid}", context={"candle_id": cid})
            seen.add(cid)

        return CandleBatch(
            symbol=first_symbol,
            timeframe=tf,
            candles=tuple(candles),
            source=source,
            requested_range=requested_range,
        )

    def normalize_dict(self, data: Dict[str, Any]) -> Candle:
        """Convenience: dict → RawCandle → Candle."""
        raw = RawCandle(
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            open_time=data["open_time"],
            close_time=data["close_time"],
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data["volume"],
            source=data.get("source", "unknown"),
            instrument_id=data.get("instrument_id"),
        )
        return self.normalize(raw)
