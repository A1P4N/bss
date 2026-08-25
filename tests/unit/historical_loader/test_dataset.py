"""Tests for DatasetStatus and DatasetMetadata."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Tuple

import pytest

from bss.domain.identifiers import DatasetId, DatasetVersion
from bss.domain.time_range import TimeRange
from bss.domain.timeframe import Timeframe
from bss.historical_loader.domain.dataset import DatasetMetadata, DatasetStatus


def _utc(y, m, d, h=0, mi=0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _range() -> TimeRange:
    return TimeRange(start=_utc(2025, 1, 1), end=_utc(2025, 1, 10))


def _make_meta(**overrides) -> DatasetMetadata:
    base = dict(
        dataset_id=DatasetId("ds_001"),
        dataset_version=DatasetVersion("v1"),
        source="binance",
        symbols=("BTCUSDT", "SOLUSDT"),
        timeframes=(Timeframe.H1, Timeframe.M15),
        range=_range(),
        created_at=_utc(2025, 1, 10, 12, 0),
        loader_version="0.1.0",
        schema_version="0.2",
        status=DatasetStatus.CREATED,
    )
    base.update(overrides)
    # ensure timeframes sorted if overridden as tuple
    return DatasetMetadata(**base)


class TestDatasetStatus:
    def test_all_values(self):
        assert DatasetStatus.CREATED == "CREATED"
        assert DatasetStatus.READY == "READY"
        assert len(DatasetStatus) == 6

    def test_str_comparison(self):
        assert DatasetStatus.READY == "READY"
        assert "READY" == DatasetStatus.READY

    def test_from_string(self):
        assert DatasetStatus("READY") is DatasetStatus.READY


class TestDatasetMetadataCreation:
    def test_valid(self):
        m = _make_meta()
        assert m.symbols == ("BTCUSDT", "SOLUSDT")
        assert m.status is DatasetStatus.CREATED

    def test_frozen(self):
        m = _make_meta()
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.source = "other"  # type: ignore[misc]

    def test_empty_source_raises(self):
        with pytest.raises(ValueError, match="source"):
            _make_meta(source="")

    def test_empty_loader_version_raises(self):
        with pytest.raises(ValueError, match="loader_version"):
            _make_meta(loader_version="")

    def test_empty_schema_version_raises(self):
        with pytest.raises(ValueError, match="schema_version"):
            _make_meta(schema_version="")

    def test_empty_symbols_raises(self):
        with pytest.raises(ValueError, match="symbols.*empty"):
            _make_meta(symbols=())

    def test_empty_symbol_string_raises(self):
        with pytest.raises(ValueError, match="symbol"):
            _make_meta(symbols=("",))

    def test_symbols_not_sorted_raises(self):
        with pytest.raises(ValueError, match="sorted"):
            _make_meta(symbols=("SOLUSDT", "BTCUSDT"))

    def test_symbols_duplicate_raises(self):
        with pytest.raises(ValueError, match="unique"):
            _make_meta(symbols=("BTCUSDT", "BTCUSDT"))

    def test_empty_timeframes_raises(self):
        with pytest.raises(ValueError, match="timeframes.*empty"):
            _make_meta(timeframes=())

    def test_timeframes_duplicate_raises(self):
        with pytest.raises(ValueError, match="unique"):
            _make_meta(timeframes=(Timeframe.M15, Timeframe.M15))

    def test_timeframes_not_sorted_raises(self):
        with pytest.raises(ValueError, match="sorted"):
            _make_meta(timeframes=(Timeframe.M15, Timeframe.H1))

    def test_naive_created_at_raises(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            _make_meta(created_at=datetime(2025, 1, 10, 12, 0))

    def test_optional_fields_default_none(self):
        m = _make_meta()
        assert m.checksum is None
        assert m.engine_version is None
        assert m.configuration_version is None

    def test_with_optional_fields(self):
        m = _make_meta(checksum="abc123", engine_version="1.0.0", configuration_version="cfg1")
        assert m.checksum == "abc123"


class TestDatasetMetadataSerialization:
    def test_roundtrip(self):
        m1 = _make_meta(
            status=DatasetStatus.READY,
            checksum="sha256:xxx",
            engine_version="1.2.3",
            configuration_version="cfg_v2",
        )
        d = m1.to_dict()
        m2 = DatasetMetadata.from_dict(d)
        assert m1 == m2

    def test_to_dict_types(self):
        m = _make_meta()
        d = m.to_dict()
        assert d["dataset_id"] == "ds_001"
        assert d["symbols"] == ["BTCUSDT", "SOLUSDT"]
        assert d["timeframes"] == ["H1", "M15"]
        assert "T" in d["from"]
        assert d["status"] == "CREATED"

    def test_from_dict_with_offset_converts_to_utc(self):
        d = _make_meta().to_dict()
        # simulate +03:00 offset
        d["from"] = "2025-01-01T00:00:00+03:00"
        d["to"] = "2025-01-10T00:00:00+03:00"
        d["created_at"] = "2025-01-10T12:00:00+03:00"
        m = DatasetMetadata.from_dict(d)
        # 00:00+03:00 == 21:00 UTC previous day
        assert m.range.start.hour == 21
        assert m.range.start.day == 31
        assert m.created_at.hour == 9

    def test_from_dict_naive_raises(self):
        d = _make_meta().to_dict()
        d["from"] = "2025-01-01T00:00:00"
        with pytest.raises(ValueError, match="timezone-aware"):
            DatasetMetadata.from_dict(d)

    def test_deterministic_symbols_order(self):
        # to_dict preserves sorted order
        m = _make_meta(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"))
        assert m.to_dict()["symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
