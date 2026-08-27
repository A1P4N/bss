"""Event Model tests (6)."""

from datetime import datetime, timezone
from decimal import Decimal
import dataclasses

import pytest

from bss.domain.candle import Candle
from bss.domain.identifiers import CandleId, DatasetId, DatasetVersion
from bss.domain.timeframe import Timeframe
from bss.event_model.envelope import CandleClosedEvent


def _utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def _candle(open_dt):
    close_dt = datetime.fromtimestamp(open_dt.timestamp() + 15 * 60, tz=timezone.utc)
    return Candle(candle_id=CandleId(f"cnd_SOLUSDT_M15_{open_dt.isoformat()}"), instrument_id="inst", symbol="SOLUSDT", timeframe=Timeframe.M15, open_time=open_dt, close_time=close_dt, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1000"))


def test_candle_closed_event_frozen():
    c = _candle(_utc(2025, 1, 1, 10, 0))
    evt = CandleClosedEvent.create(candle=c, run_id="run_123", dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        evt.event_id = "x"  # type: ignore


def test_candle_closed_event_utc():
    c = _candle(_utc(2025, 1, 1, 10, 0))
    # naive processed_at should raise
    with pytest.raises(ValueError, match="timezone-aware"):
        CandleClosedEvent.create(candle=c, run_id="run_123", dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"), processed_at=datetime(2025, 1, 1, 10, 0))
    # naive event_time via candle is already UTC enforced, so test via direct constructor
    with pytest.raises(ValueError, match="UTC"):
        CandleClosedEvent(
            event_id="evt_1",
            event_type="CANDLE_CLOSED",
            schema_version="0.2",
            event_time=datetime(2025, 1, 1, 10, 0),  # naive
            processed_at=_utc(2025, 1, 1, 10, 0),
            run_id="run_1",
            dataset_id=DatasetId("ds_001"),
            dataset_version=DatasetVersion("v1"),
            symbol="SOLUSDT",
            timeframe=Timeframe.M15,
            payload={},
        )


def test_candle_closed_event_accepts_z():
    c = _candle(_utc(2025, 1, 1, 10, 0))
    evt = CandleClosedEvent.create(candle=c, run_id="run_123", dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"), processed_at=datetime.fromisoformat("2025-01-01T10:00:00+00:00"))
    # from_dict with Z
    d = evt.to_dict()
    d["event_time"] = "2025-01-01T10:15:00Z"
    d["processed_at"] = "2025-01-01T10:15:00.123Z"
    evt2 = CandleClosedEvent.from_dict(d)
    assert evt2.event_time.tzinfo == timezone.utc
    assert evt2.processed_at.microsecond == 123000


def test_candle_closed_event_schema_02():
    c = _candle(_utc(2025, 1, 1, 10, 0))
    evt = CandleClosedEvent.create(candle=c, run_id="run_123", dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"))
    assert evt.schema_version == "0.2"
    assert evt.event_type == "CANDLE_CLOSED"
    with pytest.raises(ValueError, match="schema_version"):
        CandleClosedEvent(
            event_id="evt_1",
            event_type="CANDLE_CLOSED",
            schema_version="0.3",
            event_time=_utc(2025, 1, 1, 10, 15),
            processed_at=_utc(2025, 1, 1, 10, 15),
            run_id="run_1",
            dataset_id=DatasetId("ds_001"),
            dataset_version=DatasetVersion("v1"),
            symbol="SOLUSDT",
            timeframe=Timeframe.M15,
            payload={},
        )


def test_candle_closed_event_serialization():
    c = _candle(_utc(2025, 1, 1, 10, 0))
    evt = CandleClosedEvent.create(candle=c, run_id="run_123", dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"))
    d = evt.to_dict()
    evt2 = CandleClosedEvent.from_dict(d)
    assert evt == evt2
    # deterministic serialization (sort_keys)
    import json

    s1 = json.dumps(evt.to_dict(), sort_keys=True)
    s2 = json.dumps(evt2.to_dict(), sort_keys=True)
    assert s1 == s2


def test_event_id_does_not_affect_ordering():
    c1 = _candle(_utc(2025, 1, 1, 10, 0))
    c2 = _candle(_utc(2025, 1, 1, 10, 15))
    evt1 = CandleClosedEvent.create(candle=c1, run_id="run_1", dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"))
    evt2 = CandleClosedEvent.create(candle=c2, run_id="run_1", dataset_id=DatasetId("ds_001"), dataset_version=DatasetVersion("v1"))
    # event_id different, but ordering by event_time
    assert evt1.event_id != evt2.event_id
    assert evt1.event_time < evt2.event_time
    # payload same deterministic
    assert evt1.payload["candle"]["open_time"] != evt2.payload["candle"]["open_time"]
