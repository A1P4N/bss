"""Timeframe enumeration and utilities."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class Timeframe(str, Enum):
    """Canonical BSS timeframes.

    Values follow the exchange convention: D1, H4, H1, M15.
    Additional intraday values (e.g. M5, M1) are allowed for
    intrabar ambiguity resolution (see ЧТЗ §4.2).
    """

    D1 = "D1"
    H4 = "H4"
    H1 = "H1"
    M15 = "M15"

    # ── constructors ────────────────────────────────────────────

    @classmethod
    def from_string(cls, value: str) -> Timeframe:
        """Parse a timeframe string, raising ValueError on invalid input.

        Supports canonical names (D1, H4, H1, M15) and custom
        numerical formats (e.g. M5, H2, M1).
        """
        canonical = {tf.value: tf for tf in cls}
        if value in canonical:
            return canonical[value]

        if re.fullmatch(r"\d+[mhdMH]", value):
            # custom intraday timeframe, keep as raw string
            pass

        raise ValueError(
            f"Unknown timeframe: {value!r}. "
            f"Expected one of {[tf.value for tf in cls]} "
            f"or a custom format like 'M5', 'H2'."
        )

    # ── properties ─────────────────────────────────────────────

    def duration_minutes(self) -> int:
        """Return the duration of this timeframe in minutes."""
        mapping = {
            Timeframe.M15: 15,
            Timeframe.H1: 60,
            Timeframe.H4: 240,
            Timeframe.D1: 1440,
        }
        return mapping[self]

    # ── hierarchy navigation ───────────────────────────────────

    def next_higher(self) -> Optional[Timeframe]:
        """Return the next higher timeframe, or *None* if already D1."""
        hierarchy = [Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1]
        try:
            idx = hierarchy.index(self)
            if idx + 1 < len(hierarchy):
                return hierarchy[idx + 1]
            return None
        except ValueError:
            return None

    def next_lower(self) -> Optional[Timeframe]:
        """Return the next lower timeframe, or *None* if already M15."""
        hierarchy = [Timeframe.D1, Timeframe.H4, Timeframe.H1, Timeframe.M15]
        try:
            idx = hierarchy.index(self)
            if idx + 1 < len(hierarchy):
                return hierarchy[idx + 1]
            return None
        except ValueError:
            return None

    def __repr__(self) -> str:
        return f"Timeframe.{self.value}"