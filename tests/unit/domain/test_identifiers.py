"""Tests for identifier value types and SourceType enum."""

from __future__ import annotations

import pytest

from bss.domain.identifiers import (
    CandleId,
    DatasetId,
    DatasetVersion,
    EventId,
    SourceType,
)


class TestSourceType:
    def test_historical(self) -> None:
        assert SourceType.HISTORICAL.value == "historical"

    def test_live(self) -> None:
        assert SourceType.LIVE.value == "live"

    def test_two_values(self) -> None:
        assert len(SourceType) == 2


class TestCandleId:
    def test_valid(self) -> None:
        cid = CandleId("cnd_SOLUSDT_M15_20250101T000000")
        assert str(cid) == "cnd_SOLUSDT_M15_20250101T000000"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            CandleId("")

    def test_equality(self) -> None:
        assert CandleId("a") == CandleId("a")
        assert CandleId("a") != CandleId("b")

    def test_repr(self) -> None:
        cid = CandleId("test")
        assert repr(cid) == "CandleId('test')"


class TestDatasetId:
    def test_valid(self) -> None:
        did = DatasetId("ds_001")
        assert str(did) == "ds_001"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            DatasetId("")

    def test_equality(self) -> None:
        assert DatasetId("x") == DatasetId("x")


class TestDatasetVersion:
    def test_valid(self) -> None:
        dv = DatasetVersion("v1.0")
        assert str(dv) == "v1.0"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            DatasetVersion("")


class TestEventId:
    def test_valid(self) -> None:
        eid = EventId("evt_abc")
        assert str(eid) == "evt_abc"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            EventId("")