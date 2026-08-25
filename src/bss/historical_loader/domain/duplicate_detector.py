"""Duplicate detection — pure, deterministic (ЧТЗ §10, AC-03, AC-08)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import List

from bss.domain.candle import Candle

from .dataset import CandleBatch


@dataclass(frozen=True)
class DuplicateInfo:
    """One duplicate group."""

    candle_id: str
    open_time: str  # ISO UTC
    count: int
    symbol: str
    timeframe: str


class DuplicateDetector:
    """Finds duplicates by candle_id (and by open_time)."""

    def find_duplicates(self, batch: CandleBatch) -> List[DuplicateInfo]:
        """Return list of duplicates, empty if none. Pure."""
        if batch.is_empty:
            return []
        # count by candle_id string
        ids = [str(c.candle_id) for c in batch.candles]
        cnt = Counter(ids)
        # also check by (symbol,timeframe,open_time) as secondary key
        time_keys = [(c.symbol, c.timeframe.value, c.open_time.isoformat()) for c in batch.candles]
        time_cnt = Counter(time_keys)

        dup_ids = {k for k, v in cnt.items() if v > 1}
        dup_times = {k for k, v in time_cnt.items() if v > 1}

        result: List[DuplicateInfo] = []
        # by candle_id
        for cid, n in cnt.items():
            if n > 1:
                # find representative candle
                rep = next(c for c in batch.candles if str(c.candle_id) == cid)
                result.append(
                    DuplicateInfo(
                        candle_id=cid,
                        open_time=rep.open_time.isoformat(),
                        count=n,
                        symbol=rep.symbol,
                        timeframe=rep.timeframe.value,
                    )
                )
        # by time key not already covered by id
        for (sym, tf, ot), n in time_cnt.items():
            if n > 1 and not any(d.open_time == ot and d.symbol == sym for d in result):
                result.append(
                    DuplicateInfo(
                        candle_id=f"dup:{sym}:{tf}:{ot}",
                        open_time=ot,
                        count=n,
                        symbol=sym,
                        timeframe=tf,
                    )
                )
        # also report any time dup that overlaps with id dup but different count -> already covered
        return sorted(result, key=lambda d: d.open_time)

    def has_duplicates(self, batch: CandleBatch) -> bool:
        return len(self.find_duplicates(batch)) > 0
