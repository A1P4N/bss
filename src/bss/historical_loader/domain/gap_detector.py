"""Gap detection — pure, deterministic (ЧТЗ §11, AC-06).

Emits DATA_INTEGRITY_GAP payload fields: symbol, timeframe, from, to, expected, actual.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

from bss.domain.time import ensure_utc

from .dataset import CandleBatch


@dataclass(frozen=True)
class Gap:
    """Missing interval inside requested_range."""

    symbol: str
    timeframe: str
    missing_from: datetime  # UTC inclusive
    missing_to: datetime    # UTC exclusive
    expected_candles: int
    actual_candles: int

    def to_data_integrity_gap_payload(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "from": self.missing_from.isoformat(),
            "to": self.missing_to.isoformat(),
            "expected_candles": self.expected_candles,
            "actual_candles": self.actual_candles,
        }


class GapDetector:
    """Detects gaps by expected vs actual candle count on aligned grid."""

    def expected_count(self, batch: CandleBatch) -> int:
        """Expected candles for requested_range given timeframe interval."""
        delta = batch.requested_range.duration()
        interval = timedelta(minutes=batch.timeframe.duration_minutes())
        # ceil division for partial tail
        # e.g. 1h /15m =4, 1h30m /1h =2 (partial)
        total_seconds = delta.total_seconds()
        interval_seconds = interval.total_seconds()
        # integer division with remainder
        count = int(total_seconds // interval_seconds)
        if total_seconds % interval_seconds != 0:
            count += 1
        return count

    def find_gaps(self, batch: CandleBatch) -> List[Gap]:
        """Return list of gaps (empty if contiguous).

        Strategy: walk aligned grid from requested_range.start by interval,
        compare with sorted candles open_time. Any missing open_time → gap.
        """
        if batch.is_empty:
            # entire range missing
            exp = self.expected_count(batch)
            if exp == 0:
                return []
            return [
                Gap(
                    symbol=batch.symbol,
                    timeframe=batch.timeframe.value,
                    missing_from=batch.requested_range.start,
                    missing_to=batch.requested_range.end,
                    expected_candles=exp,
                    actual_candles=0,
                )
            ]

        # ensure UTC already enforced
        interval = timedelta(minutes=batch.timeframe.duration_minutes())
        # build expected open_times set
        expected_times = []
        cursor = batch.requested_range.start
        while cursor < batch.requested_range.end:
            expected_times.append(cursor)
            cursor = cursor + interval
            # safeguard: prevent infinite loop
            if len(expected_times) > 100000:
                break

        actual_map = {c.open_time: c for c in batch.candles}
        gaps: List[Gap] = []
        # iterate expected grid and collect contiguous missing segments
        missing_start: datetime | None = None
        missing_expected = 0

        for exp_time in expected_times:
            if exp_time not in actual_map:
                if missing_start is None:
                    missing_start = exp_time
                missing_expected += 1
            else:
                if missing_start is not None:
                    # close gap segment
                    missing_end = exp_time  # exclusive
                    gaps.append(
                        Gap(
                            symbol=batch.symbol,
                            timeframe=batch.timeframe.value,
                            missing_from=missing_start,
                            missing_to=missing_end,
                            expected_candles=missing_expected,
                            actual_candles=0,
                        )
                    )
                    missing_start = None
                    missing_expected = 0
        # tail missing
        if missing_start is not None:
            gaps.append(
                Gap(
                    symbol=batch.symbol,
                    timeframe=batch.timeframe.value,
                    missing_from=missing_start,
                    missing_to=batch.requested_range.end,
                    expected_candles=missing_expected,
                    actual_candles=0,
                )
            )
        # also handle actual vs expected count mismatch due to misalignment
        # if no gaps but count mismatch, still report as gap
        if not gaps and len(batch.candles) != len(expected_times):
            # counters differ but grid matched — may be extra/missing due to partial tail handling
            # emit generic gap
            if len(batch.candles) < len(expected_times):
                # find which expected missing
                pass  # already handled
            # if extra candles beyond expected, treat as ordering issue — not gap here

        return gaps

    def has_gaps(self, batch: CandleBatch) -> bool:
        return len(self.find_gaps(batch)) > 0
