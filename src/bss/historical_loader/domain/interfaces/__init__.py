"""Loader domain interfaces (source abstractions + storage)."""

from .dataset_storage import DatasetStorage
from .historical_source import HistoricalSource
from .historical_spread_source import HistoricalSpreadSource
from .metadata_storage import MetadataStorage
from .raw_storage import RawStorage

__all__ = ["DatasetStorage", "HistoricalSource", "HistoricalSpreadSource", "MetadataStorage", "RawStorage"]
