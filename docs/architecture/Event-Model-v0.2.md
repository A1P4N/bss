# Event Model v0.2

**Проект:** BSS Structural Monitoring Agent  
**Status:** Draft for implementation  
**Date:** 2026-08-23

## 1. Purpose

Event Model defines machine-readable facts, scenario states, transitions, validation rules and push payload for the BSS monitoring agent.

Core rule:

> **Event = immutable fact. State = current interpretation of events. Push = derived projection.**

---

# 2. Entities

```text
Instrument
Candle
Swing
Zone
StructureBreak
MotherOB
OBLS
Scenario
Setup
Push
TraderFeedback
```

## 2.1 IDs

Every entity that participates in state transitions must have a stable ID.

Recommended:

```text
instrument_id
candle_id
zone_id
break_id
ob_id
obls_id
scenario_id
setup_id
push_id
event_id
```

`event_id` must be globally unique.

`scenario_id` identifies one directional BSS scenario and must not change during its lifetime.

---

# 3. Event envelope

```json
{
  "event_id": "evt_01J...",
  "event_type": "STRUCTURE_BREAK_CONFIRMED",
  "schema_version": "0.2",
  "event_time": "2026-08-23T00:15:00Z",
  "processed_at": "2026-08-23T00:15:00.125Z",
  "symbol": "SOLUSDT",
  "timeframe": "M15",
  "direction": "LONG",
  "scenario_id": "scn_01J...",
  "source": {
    "type": "historical|live",
    "dataset_id": "...",
    "engine_version": "..."
  },
  "payload": {}
}
```

`event_time` = market event time.  
`processed_at` = system processing time.

Both are required for reproducibility and latency analysis.

---

# 4. Event taxonomy

## 4.1 Market/system events

```text
CANDLE_CLOSED
DATA_INTEGRITY_GAP
DATA_RECOVERY_STARTED
DATA_RECOVERY_COMPLETED
STATE_REBUILD_STARTED
STATE_REBUILD_COMPLETED
```

`DATA_INTEGRITY_GAP` is infrastructure state, not a strategy signal.

## 4.2 Structural events

```text
SWING_CONFIRMED
STRUCTURE_BREAK_CONFIRMED
```

## 4.3 Zone events

```text
MOTHER_OB_IDENTIFIED
OBLS_IDENTIFIED
ZONE_TESTED
ZONE_DEATH
```

## 4.4 Cascade events

```text
SCENARIO_CREATED
CASCADE_LINK_VALIDATED
CASCADE_LINK_INCOMPLETE
CASCADE_INVALIDATED
CASCADE_COMPLETED
```

## 4.5 Filter events

```text
VOLATILITY_PASSED
VOLATILITY_FAILED
```

## 4.6 Qualification/push events

```text
SETUP_QUALIFIED
PUSH_CREATED
PUSH_SENT
PUSH_SEND_FAILED
```

## 4.7 Trader events

```text
TRADER_FEEDBACK_RECEIVED
```

---

# 5. Scenario state

Scenario has a lifecycle:

```text
CREATED
  |
  v
ACTIVE
  |
  +----> INVALIDATED
  |
  v
QUALIFIED
  |
  v
COMPLETED
  |
  v
ARCHIVED
```

`QUALIFIED` is a business state meaning the required structural conditions for a setup are satisfied.

`PUSH_SENT` is not a scenario state. It is an event in the delivery projection.

---

# 6. Composite cascade state

Do not create a giant enum such as `M15_QUALIFIED_AFTER_H1_TESTED_AFTER_H4...`.

Instead:

```json
{
  "scenario_status": "ACTIVE",
  "levels": {
    "D1": {...},
    "H4": {...},
    "H1": {...},
    "M15": {...}
  }
}
```

Recommended level state:

```text
NONE
BREAK_CONFIRMED
LINK_VALIDATED
LINK_INCOMPLETE
FILTERED
QUALIFIED
INVALIDATED
```

Not every value is applicable to every timeframe.

---

# 7. Level state payload

```json
{
  "timeframe": "H1",
  "break_id": "brk_123",
  "mother_ob_id": "ob_123",
  "obls_id": "obls_123",
  "source_zone_id": "h4_ob_99",
  "source_zone_tested": true,
  "state": "LINK_VALIDATED",
  "invalidated_at": null
}
```

---

# 8. Structure break event

```json
{
  "event_type": "STRUCTURE_BREAK_CONFIRMED",
  "payload": {
    "break_id": "brk_123",
    "points": {
      "p1": {"time": "...", "price": 180.1},
      "p2": {"time": "...", "price": 183.9},
      "p3": {"time": "...", "price": 182.4},
      "p4": {"time": "...", "price": 184.2}
    },
    "confirmation": {
      "candle_close": 184.1,
      "p2_price": 183.9,
      "body_closed_beyond_p2": true
    }
  }
}
```

Invariants:

```text
LONG: P1.low < P3.low < P2.high < P4.high
SHORT: mirror
close crosses P2 in correct direction
```

Exact swing ordering/uniqueness rules remain TBD.

---

# 9. Mother OB event

```json
{
  "event_type": "MOTHER_OB_IDENTIFIED",
  "payload": {
    "ob_id": "ob_123",
    "method": "SIMPLE",
    "formation_start": "...",
    "formation_end": "...",
    "high": 184.8,
    "low": 184.12,
    "width_pct": 0.368
  }
}
```

`method`:

```text
SIMPLE
SEMANTIC
```

The baseline is `SIMPLE` until semantic predicates are formalized.

---

# 10. OBLS event

```json
{
  "event_type": "OBLS_IDENTIFIED",
  "payload": {
    "obls_id": "obls_123",
    "break_id": "brk_123",
    "candle_time": "...",
    "high": 183.0,
    "low": 182.4,
    "p3_price": 182.4
  }
}
```

Exact rule for multiple opposing candles is TBD.

---

# 11. Zone tested

```json
{
  "event_type": "ZONE_TESTED",
  "payload": {
    "zone_id": "ob_123",
    "test_time": "...",
    "price": 182.46,
    "boundary": 182.55,
    "buffer": {
      "mode": "spread_multiple",
      "multiple": 2.0,
      "value": 0.08
    },
    "test_type": "TOUCH|UNDERSHOOT"
  }
}
```

The exact semantic difference between touch and undershoot may remain an analytics field rather than a state distinction.

---

# 12. Zone death

```json
{
  "event_type": "ZONE_DEATH",
  "payload": {
    "zone_id": "ob_123",
    "timeframe": "H1",
    "price": 181.92,
    "death_boundary": 182.00,
    "buffer_applied": false,
    "evidence": {
      "mode": "tick|intrabar|ohlc"
    }
  }
}
```

A death invalidates the affected scenario branch.

It must not generate Telegram push.

For historical OHLC data, `evidence.mode=ohlc` may be insufficient to determine event order; ambiguity must be explicit.

---

# 13. Cascade link validation

### Valid

```json
{
  "event_type": "CASCADE_LINK_VALIDATED",
  "payload": {
    "parent_timeframe": "H1",
    "child_timeframe": "M15",
    "source_zone_id": "h1_ob_7",
    "break_id": "m15_break_1",
    "source_zone_tested": true
  }
}
```

### Incomplete

```json
{
  "event_type": "CASCADE_LINK_INCOMPLETE",
  "payload": {
    "parent_timeframe": "H1",
    "child_timeframe": "M15",
    "source_zone_id": "h1_ob_7",
    "break_id": "m15_break_1",
    "source_zone_tested": false,
    "flag_code": "CHAIN_INCOMPLETE"
  }
}
```

This does not imply that the structural break itself is invalid.

---

# 14. Volatility filter events

```json
{
  "event_type": "VOLATILITY_PASSED",
  "payload": {
    "mother_ob_id": "m15_ob_1",
    "width_pct": 0.47,
    "threshold_pct": 0.30
  }
}
```

or:

```json
{
  "event_type": "VOLATILITY_FAILED",
  "payload": {
    "mother_ob_id": "m15_ob_1",
    "width_pct": 0.21,
    "threshold_pct": 0.30
  }
}
```

Filter failure is not structure invalidation.

---

# 15. Setup qualification

`SETUP_QUALIFIED` is derived, not a raw market fact.

Baseline predicate:

```text
scenario.status == ACTIVE
AND
M15 structure break is confirmed
AND
required cascade links are valid
AND
M15 mother OB width >= threshold
AND
scenario has no active invalidation
```

The exact interpretation of “required cascade links” depends on Q-01 in Requirements v0.4.

---

# 16. Push event

Push is a projection of `SETUP_QUALIFIED`.

Recommended contract:

```json
{
  "event_type": "PUSH_CREATED",
  "payload": {
    "push_id": "push_123",
    "setup_id": "setup_123",
    "scenario_id": "scn_123",
    "symbol": "SOLUSDT",
    "direction": "LONG",
    "decision_timeframe": "M15",
    "cascade": {
      "D1": {
        "status": "TESTED",
        "ob_id": "d1_ob_1"
      },
      "H4": {
        "status": "VALIDATED",
        "break_id": "h4_brk_1",
        "mother_ob_id": "h4_ob_1",
        "obls_id": "h4_obls_1"
      },
      "H1": {
        "status": "VALIDATED",
        "break_id": "h1_brk_1",
        "mother_ob_id": "h1_ob_1",
        "obls_id": "h1_obls_1"
      },
      "M15": {
        "status": "QUALIFIED",
        "break_id": "m15_brk_1",
        "mother_ob_id": "m15_ob_1",
        "obls_id": "m15_obls_1"
      }
    },
    "volatility": {
      "width_pct": 0.47,
      "threshold_pct": 0.30,
      "passed": true
    },
    "flags": [
      "CHAIN_COMPLETE"
    ],
    "chart_reference": "..."
  }
}
```

---

# 17. Push schema exclusions

The schema must reject/ignore the following business fields:

```text
entry
limit
stop
take_profit
rr
score
recommendation
order
position
```

Reason: they are outside agent responsibility.

---

# 18. Push delivery state

Delivery is a separate state machine:

```text
NOT_CREATED
  |
  v
CREATED
  |
  +--> SEND_FAILED
  |
  v
SENT
```

Retry of `SEND_FAILED` must be idempotent.

`PUSH_SENT` must never create a second `SETUP_QUALIFIED` event.

---

# 19. Scenario transitions

| Current | Event | Next | Side effect |
|---|---|---|---|
| CREATED | SCENARIO_CREATED | ACTIVE | initialize scenario |
| ACTIVE | STRUCTURE_BREAK_CONFIRMED | ACTIVE | attach break |
| ACTIVE | MOTHER_OB_IDENTIFIED | ACTIVE | attach OB |
| ACTIVE | OBLS_IDENTIFIED | ACTIVE | attach OBLS |
| ACTIVE | CASCADE_LINK_VALIDATED | ACTIVE | mark link valid |
| ACTIVE | CASCADE_LINK_INCOMPLETE | ACTIVE | add flag |
| ACTIVE | ZONE_DEATH | INVALIDATED | close scenario branch |
| ACTIVE | VOLATILITY_FAILED | ACTIVE | no push |
| ACTIVE | SETUP_QUALIFIED | QUALIFIED | create setup |
| QUALIFIED | PUSH_CREATED | QUALIFIED | snapshot push |
| QUALIFIED | TRADER_FEEDBACK_RECEIVED | QUALIFIED | store feedback |
| QUALIFIED | lifecycle close | COMPLETED | archive business outcome |

---

# 20. Reducer rules

Reducer input:

```text
(previous_state, event) -> new_state
```

Reducer must be:

- deterministic;
- side-effect free;
- replayable;
- versioned.

External side effects belong to consumers:

```text
Reducer -> State
        -> Push Projection
        -> Persistence Projection
        -> TigerTrade Projection
```

---

# 21. Event ordering

Events must be ordered using a deterministic ordering key.

Recommended:

```text
event_time
sequence_in_source
processed_at
```

A market event arriving late must not silently corrupt state.

Recovery should replay the affected time window.

---

# 22. Idempotency

The following keys must be stable:

```text
event_id
break_id
zone_id
scenario_id
setup_id
push_id
```

Duplicate ingestion of the same event must not produce duplicate state transitions.

---

# 23. Backtest semantics

Backtest should produce the same event types as live mode.

Example:

```text
Historical candles
    |
    v
CANDLE_CLOSED
    |
    v
STRUCTURE_BREAK_CONFIRMED
    |
    v
CASCADE_LINK_VALIDATED
    |
    v
VOLATILITY_PASSED
    |
    v
SETUP_QUALIFIED
    |
    v
PUSH_CREATED
```

No separate “backtest logic” is allowed for business predicates.

---

# 24. Event log example

```text
10:00 D1 MOTHER_OB_IDENTIFIED
10:15 D1 ZONE_TESTED
10:15 H4 STRUCTURE_BREAK_CONFIRMED
10:15 H4 MOTHER_OB_IDENTIFIED
10:15 H4 OBLS_IDENTIFIED
10:30 H1 STRUCTURE_BREAK_CONFIRMED
10:30 H1 MOTHER_OB_IDENTIFIED
10:30 H1 OBLS_IDENTIFIED
11:00 M15 STRUCTURE_BREAK_CONFIRMED
11:00 M15 MOTHER_OB_IDENTIFIED
11:00 M15 OBLS_IDENTIFIED
11:00 H1->M15 CASCADE_LINK_VALIDATED
11:00 VOLATILITY_PASSED
11:00 SETUP_QUALIFIED
11:00 PUSH_CREATED
11:00 PUSH_SENT
```

The above is illustrative only; actual event ordering follows market timestamps.

---

# 25. Event categories that must not be conflated

```text
STRUCTURE_BREAK_CONFIRMED != SETUP_QUALIFIED
ZONE_DEATH != DATA_INTEGRITY_GAP
TRADER_FEEDBACK != SCENARIO_INVALIDATED
PUSH_SENT != SETUP_QUALIFIED
VOLATILITY_FAILED != STRUCTURE_BREAK_REJECTED
```

This distinction is a core invariant.
