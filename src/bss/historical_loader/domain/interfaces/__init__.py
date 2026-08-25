"""Loader domain interfaces (source abstractions)."""

from .historical_source import HistoricalSource
from .historical_spread_source import HistoricalSpreadSource

__all__ = ["HistoricalSource", "HistoricalSpreadSource"]
