"""Tests for Timeframe enum."""

from __future__ import annotations

from datetime import timedelta

import pytest

from bss.domain import Timeframe


class TestTimeframeValues:
    """All canonical values exist."""

    def test_d1_exists(self) -> None:
        assert Timeframe.D1.value == "D1"

    def test_h4_exists(self) -> None:
        assert Timeframe.H4.value == "H4"

    def test_h1_exists(self) -> None:
        assert Timeframe.H1.value == "H1"

    def test_m15_exists(self) -> None:
        assert Timeframe.M15.value == "M15"

    def test_four_core_timeframes(self) -> None:
        assert len(Timeframe) == 4


class TestTimeframeFromString:
    """Parse string → Timeframe mapping."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("D1", Timeframe.D1),
            ("H4", Timeframe.H4),
            ("H1", Timeframe.H1),
            ("M15", Timeframe.M15),
        ],
    )
    def test_canonical_parsing(self, raw: str, expected: Timeframe) -> None:
        assert Timeframe.from_string(raw) is expected

    def test_case_sensitive(self) -> None:
        with pytest.raises(ValueError):
            Timeframe.from_string("d1")

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="M13"):
            Timeframe.from_string("M13")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            Timeframe.from_string("")


class TestTimeframeDuration:
    """duration_minutes() returns correct values."""

    @pytest.mark.parametrize(
        "tf, minutes",
        [
            (Timeframe.M15, 15),
            (Timeframe.H1, 60),
            (Timeframe.H4, 240),
            (Timeframe.D1, 1440),
        ],
    )
    def test_duration(self, tf: Timeframe, minutes: int) -> None:
        assert tf.duration_minutes() == minutes

    def test_duration_matches_timedelta(self) -> None:
        assert timedelta(minutes=Timeframe.M15.duration_minutes()) == timedelta(minutes=15)


class TestTimeframeHierarchy:
    """next_higher / next_lower navigation."""

    @pytest.mark.parametrize(
        "current, expected_higher, expected_lower",
        [
            (Timeframe.M15, Timeframe.H1, None),
            (Timeframe.H1, Timeframe.H4, Timeframe.M15),
            (Timeframe.H4, Timeframe.D1, Timeframe.H1),
            (Timeframe.D1, None, Timeframe.H4),
        ],
    )
    def test_hierarchy(
        self,
        current: Timeframe,
        expected_higher: Timeframe | None,
        expected_lower: Timeframe | None,
    ) -> None:
        assert current.next_higher() is expected_higher
        assert current.next_lower() is expected_lower