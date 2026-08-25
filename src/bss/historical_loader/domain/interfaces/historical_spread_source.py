"""HistoricalSpreadSource — TBD abstraction for Q-06.

Per AGENTS.md §18 and 06_OPEN_QUESTIONS.md Q-06:
Do not invent historical spread. Provide abstraction, leave implementation TBD.
Current spread must NOT be silently used as historical.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class HistoricalSpreadSource(Protocol):
    """Abstraction for historical spread lookup.

    Q-06 TBD: which historical spread source is authoritative.
    Implementations will be provided in a later slice when
    bid/ask history source is decided. Until then, callers must
    handle None (no data) explicitly.
    """

    def spread_at(self, symbol: str, timestamp: datetime) -> Decimal | None:
        """Return spread at given UTC timestamp, or None if unavailable.

        Args:
            symbol: e.g. "SOLUSDT"
            timestamp: timezone-aware UTC

        Returns:
            Spread value or None if no historical data.

        Raises:
            ValueError: if timestamp is naive.
        """
        ...
