"""Binance mapper — OHLCV → Candle (UTC, Decimal, close_time = open + duration)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId
from bss.domain.timeframe import Timeframe


def map_binance_kline(
    kline: list[Any],
    symbol: str,
    timeframe: Timeframe,
) -> Candle:
    """Map single Binance kline array to Candle.

    Binance kline: [openTime, open, high, low, close, volume, closeTime, ...]
    openTime is ms since epoch UTC.
    Domain close_time = open_time + timeframe.duration (half-open, not Binance closeTime).
    """
    if not isinstance(kline, (list, tuple)) or len(kline) < 6:
        raise ValueError(f"invalid kline {kline!r}")

    open_ms = int(kline[0])
    open_time = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc)

    # Use Decimal for prices to preserve precision
    o = Decimal(str(kline[1]))
    h = Decimal(str(kline[2]))
    l = Decimal(str(kline[3]))
    c = Decimal(str(kline[4]))
    v = Decimal(str(kline[5]))

    close_time = open_time + timedelta(minutes=timeframe.duration_minutes())

    candle_id = Candle.build_candle_id(symbol, timeframe, open_time)

    return Candle(
        candle_id=candle_id,
        instrument_id=f"inst_{symbol.lower()}",
        symbol=symbol,
        timeframe=timeframe,
        open_time=open_time,
        close_time=close_time,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
    )


def map_binance_klines(klines: list[list[Any]], symbol: str, timeframe: Timeframe) -> list[Candle]:
    return [map_binance_kline(k, symbol, timeframe) for k in klines]
