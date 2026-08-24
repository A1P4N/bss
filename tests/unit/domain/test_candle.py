"""Tests for Candle value object."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bss.domain import Candle, Timeframe
from bss.domain.candle import Candle


def _make_candle(**overrides: object) -> Candle:
    """Helper: create a valid default candle and override fields."""
    params = dict(
        candle_id="cnd_SOLUSDT_M15_20250101T000000",
        instrument_id="inst_sol_usdt",
        symbol="SOLUSDT",
        timeframe=Timeframe.M15,
        open_time=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        close_time=datetime(2025, 1, 1, 0, 15, 0, tzinfo=timezone.utc),
        open=Decimal("100.0"),
        high=Decimal("105.0"),
        low=Decimal("99.5"),
        close=Decimal("104.2"),
        volume=Decimal("1234.567"),
    )
    params.update(overrides)
    return Candle(**params)


class TestCandleCreation:
    """Candle construction and immutability."""

    def test_valid_candle(self) -> None:
        c = _make_candle()
        assert c.symbol == "SOLUSDT"
        assert c.timeframe is Timeframe.M15

    def test_immutable(self) -> None:
        c = _make_candle()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.open = Decimal("999")

    def test_candle_id_set(self) -> None:
        c = _make_candle()
        assert c.candle_id.startswith("cnd_")

    def test_instrument_id_set(self) -> None:
        c = _make_candle(instrument_id="inst_test")
        assert c.instrument_id == "inst_test"


class TestCandleValidation:
    """OHLC invariants and timezone checks."""

    def test_naive_open_time_raises(self) -> None:
        with pytest.raises(ValueError, match="open_time.*timezone-aware"):
            _make_candle(open_time=datetime(2025, 1, 1, 0, 0, 0))

    def test_naive_close_time_raises(self) -> None:
        with pytest.raises(ValueError, match="close_time.*timezone-aware"):
            _make_candle(close_time=datetime(2025, 1, 1, 0, 15, 0))

    def test_low_greater_than_high_raises(self) -> None:
        with pytest.raises(ValueError, match="low.*<=.*high"):
            _make_candle(low=Decimal("110"), high=Decimal("100"))

    def test_open_below_low_raises(self) -> None:
        with pytest.raises(ValueError, match="open.*not in"):
            _make_candle(open=Decimal("90"), low=Decimal("95"))

    def test_open_above_high_raises(self) -> None:
        with pytest.raises(ValueError, match="open.*not in"):
            _make_candle(open=Decimal("110"), high=Decimal("105"))

    def test_close_below_low_raises(self) -> None:
        with pytest.raises(ValueError, match="close.*not in"):
            _make_candle(close=Decimal("90"), low=Decimal("95"))

    def test_close_above_high_raises(self) -> None:
        with pytest.raises(ValueError, match="close.*not in"):
            _make_candle(close=Decimal("110"), high=Decimal("105"))

    def test_negative_volume_raises(self) -> None:
        with pytest.raises(ValueError, match="volume.*>= 0"):
            _make_candle(volume=Decimal("-1"))

    def test_zero_volume_allowed(self) -> None:
        c = _make_candle(volume=Decimal("0"))
        assert c.volume == Decimal("0")

    def test_open_time_after_close_time_raises(self) -> None:
        with pytest.raises(ValueError, match="open_time.*<.*close_time"):
            _make_candle(
                open_time=datetime(2025, 1, 1, 0, 15, 0, tzinfo=timezone.utc),
                close_time=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            )

    def test_equal_open_close_time_raises(self) -> None:
        with pytest.raises(ValueError, match="open_time.*<.*close_time"):
            _make_candle(
                open_time=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                close_time=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            )


class TestCandleBodyHelpers:
    """body_direction, body_lower, body_upper."""

    def test_body_direction_up(self) -> None:
        c = _make_candle(open=Decimal("100"), close=Decimal("105"))
        assert c.body_direction() == "UP"

    def test_body_direction_down(self) -> None:
        c = _make_candle(open=Decimal("105"), close=Decimal("100"))
        assert c.body_direction() == "DOWN"

    def test_body_direction_flat(self) -> None:
        c = _make_candle(open=Decimal("100"), close=Decimal("100"))
        assert c.body_direction() == "FLAT"

    def test_body_lower(self) -> None:
        c = _make_candle(open=Decimal("105"), close=Decimal("100"))
        assert c.body_lower() == Decimal("100")

    def test_body_upper(self) -> None:
        c = _make_candle(open=Decimal("100"), close=Decimal("105"))
        assert c.body_upper() == Decimal("105")


class TestCandleContainsPrice:
    """contains_price boundary checks."""

    def test_price_within_range(self) -> None:
        c = _make_candle(low=Decimal("100"), high=Decimal("110"))
        assert c.contains_price(Decimal("105"))

    def test_price_on_low(self) -> None:
        c = _make_candle(low=Decimal("100"), high=Decimal("110"))
        assert c.contains_price(Decimal("100"))

    def test_price_on_high(self) -> None:
        c = _make_candle(low=Decimal("100"), high=Decimal("110"))
        assert c.contains_price(Decimal("110"))

    def test_price_below_low(self) -> None:
        c = _make_candle(low=Decimal("100"), high=Decimal("110"))
        assert not c.contains_price(Decimal("99"))

    def test_price_above_high(self) -> None:
        c = _make_candle(low=Decimal("100"), high=Decimal("110"))
        assert not c.contains_price(Decimal("111"))


class TestCandleSerialization:
    """to_dict / from_dict roundtrip."""

    def test_roundtrip(self) -> None:
        c1 = _make_candle()
        d = c1.to_dict()
        c2 = Candle.from_dict(d)
        assert c1 == c2

    def test_to_dict_types(self) -> None:
        c = _make_candle()
        d = c.to_dict()
        assert d["symbol"] == "SOLUSDT"
        assert isinstance(d["open"], str)
        assert d["timeframe"] == "M15"

    def test_from_dict_restores_decimal(self) -> None:
        c = _make_candle()
        d = c.to_dict()
        c2 = Candle.from_dict(d)
        assert isinstance(c2.open, Decimal)
        assert isinstance(c2.volume, Decimal)


class TestBuildCandleId:
    """Deterministic candle ID generation."""

    def test_format(self) -> None:
        ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        cid = Candle.build_candle_id("SOLUSDT", Timeframe.M15, ts)
        assert cid == "cnd_SOLUSDT_M15_20250101T000000"

    def test_deterministic(self) -> None:
        ts = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        cid1 = Candle.build_candle_id("BTCUSDT", Timeframe.H1, ts)
        cid2 = Candle.build_candle_id("BTCUSDT", Timeframe.H1, ts)
        assert cid1 == cid2