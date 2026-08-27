"""BinanceSource — HistoricalSource Protocol implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from bss.domain.time import ensure_utc
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import CandleBatch

from .client import BinanceClient
from .mapper import map_binance_klines


_INTERVAL_MAP = {
    Timeframe.M15: "15m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
}


class BinanceSource:
    """Implements HistoricalSource via Binance HTTP."""

    def __init__(self, client: BinanceClient | None = None, base_url: str | None = None, timeout: float | None = None):
        if client is not None:
            self.client = client
        else:
            self.client = BinanceClient(base_url=base_url or "https://api.binance.com", timeout=timeout or 10.0)

    def available_range(self, symbol: str, timeframe: Timeframe) -> TimeRange:
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty")
        # Technical fallback: Binance exists since ~2017, use 2017-01-01 to now
        # Config/history contract preferred — but adapter provides fallback, not silent real availability
        start = datetime(2017, 1, 1, tzinfo=timezone.utc)
        end = datetime.now(timezone.utc)
        return TimeRange(start=start, end=end)

    def download(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime) -> CandleBatch:
        ensure_utc(start, "start")
        ensure_utc(end, "end")
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty")
        if start >= end:
            raise ValueError("start must be < end")

        interval = _INTERVAL_MAP.get(timeframe)
        if interval is None:
            raise ValueError(f"unsupported timeframe {timeframe}")

        # Check limit=1000 invariant: expected candles for chunk must be <=1000
        # For M15, 1000*15m = 250h ~10 days. Our default chunk 1d =96 <1000, safe.
        # If chunk would exceed, we raise to avoid silent truncation (clarification 2).
        # Caller (DownloadService) must ensure chunk_interval respects this.
        expected = int((end - start).total_seconds() // (timeframe.duration_minutes() * 60))
        # ceil for partial
        if (end - start).total_seconds() % (timeframe.duration_minutes() * 60) != 0:
            expected += 1
        if expected > 1000:
            raise ValueError(f"chunk range {start.isoformat()}->{end.isoformat()} expects {expected} candles >1000 limit for {timeframe.value}; reduce chunk_interval")

        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        klines = self.client.fetch_klines(symbol=symbol, interval=interval, start_time=start_ms, end_time=end_ms, limit=1000)

        # Binance may return less than expected if no data, but should not silently truncate beyond limit
        # If klines len ==1000 and expected >1000, we already raised; if len==1000 and expected==1000 but more data exists beyond, Binance would truncate
        # For MVP we assume chunk_interval ensures len <1000, so we don't need pagination

        candles = map_binance_klines(klines, symbol, timeframe)

        # Ensure half-open semantics: only candles with open_time in [start,end)
        filtered = [c for c in candles if start <= c.open_time < end]
        # Also ensure not to silently truncate: if Binance returned 1000 but we expected <1000, it's okay; if expected >1000 we already raised
        rr = TimeRange(start=start, end=end)
        return CandleBatch(symbol=symbol, timeframe=timeframe, candles=tuple(sorted(filtered, key=lambda c: c.open_time)), source="binance", requested_range=rr)
