"""Tests for Instrument and InstrumentId."""

from __future__ import annotations

import pytest

from bss.domain import Instrument, InstrumentId


class TestInstrumentId:
    """InstrumentId value type."""

    def test_creation(self) -> None:
        iid = InstrumentId("inst_sol_usdt")
        assert str(iid) == "inst_sol_usdt"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            InstrumentId("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            InstrumentId("  ")

    def test_equality(self) -> None:
        assert InstrumentId("a") == InstrumentId("a")
        assert InstrumentId("a") != InstrumentId("b")


class TestInstrument:
    """Instrument entity."""

    def test_valid_instrument(self) -> None:
        inst = Instrument(
            instrument_id=InstrumentId("inst_sol_usdt"),
            symbol="SOLUSDT",
            base="SOL",
            quote="USDT",
        )
        assert inst.symbol == "SOLUSDT"
        assert inst.base == "SOL"
        assert inst.quote == "USDT"

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError, match="symbol.*not be empty"):
            Instrument(
                instrument_id=InstrumentId("inst_x"),
                symbol="",
                base="X",
                quote="Y",
            )

    def test_empty_base_raises(self) -> None:
        with pytest.raises(ValueError, match="base.*not be empty"):
            Instrument(
                instrument_id=InstrumentId("inst_x"),
                symbol="XY",
                base="",
                quote="Y",
            )

    def test_empty_quote_raises(self) -> None:
        with pytest.raises(ValueError, match="quote.*not be empty"):
            Instrument(
                instrument_id=InstrumentId("inst_x"),
                symbol="XY",
                base="X",
                quote="",
            )

    def test_immutable(self) -> None:
        inst = Instrument(
            instrument_id=InstrumentId("inst_x"),
            symbol="XY",
            base="X",
            quote="Y",
        )
        with pytest.raises(Exception):
            inst.symbol = "ZZ"  # type: ignore[misc]

    def test_exchange_optional(self) -> None:
        inst = Instrument(
            instrument_id=InstrumentId("inst_x"),
            symbol="XY",
            base="X",
            quote="Y",
            exchange="BINANCE",
        )
        assert inst.exchange == "BINANCE"

        inst_no_exchange = Instrument(
            instrument_id=InstrumentId("inst_y"),
            symbol="AB",
            base="A",
            quote="B",
        )
        assert inst_no_exchange.exchange is None