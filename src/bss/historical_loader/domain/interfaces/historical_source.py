"""HistoricalSource contract — domain interface for historical data.

References:
- ЧТЗ §8 Source abstraction
- AGENTS.md §20 Source abstraction
- AC-01 Source
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from bss.domain.timeframe import Timeframe
from bss.domain.time_range import TimeRange

from ..dataset import CandleBatch


@runtime_checkable
class HistoricalSource(Protocol):
    """Abstract source of historical OHLCV data.

    Implementations (API, Files, Archive) must be interchangeable
    without changing Dataset/Replay/Analysis Engine (ЧТЗ §8).

    All datetimes are timezone-aware UTC. Implementations must
    validate tz-awareness and raise ValueError on naive input.
    Methods must be idempotent and deterministic for same args
    (AGENTS.md §21).
    """

    def available_range(self, symbol: str, timeframe: Timeframe) -> TimeRange:
        """Return the time range for which data is available.

        Args:
            symbol: e.g. "SOLUSDT"
            timeframe: D1/H4/H1/M15 (ЧТЗ §4.2)

        Returns:
            Half-open [start, end) UTC range.

        Raises:
            ValueError: on empty symbol or unsupported timeframe.
        """
        ...

    def download(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> CandleBatch:
        """Download a chunk of candles for [start, end).

        Must be idempotent: repeated call with same args returns
        equal CandleBatch without duplicates (AGENTS.md §21).

        Args:
            symbol: instrument symbol
            timeframe: bar timeframe
            start: inclusive start (UTC-aware)
            end: exclusive end (UTC-aware)

        Returns:
            CandleBatch with 0..N candles sorted by open_time.

        Raises:
            ValueError: on naive datetimes, start>=end, empty symbol.
            SourceUnavailable / RateLimited / TransientError: TBD typed errors
                (not enforced in this domain slice, but implementations
                should use them instead of generic Exception).
        """
        ...
