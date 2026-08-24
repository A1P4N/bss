# BSS --- архитектура проекта

## 1. Архитектурный принцип

``` text
Historical Source
      ↓
Historical Data Loader
      ↓
Normalized Dataset
      ↓
ReplayDataSource
      ↓
BSS Analysis Engine
      ↓
Immutable Events
      ↓
State / Audit / Push Projection
```

Ключевая граница:

``` text
Loader ≠ Replay ≠ Analysis Engine
```

------------------------------------------------------------------------

## 2. Bounded modules

Рекомендуемые основные модули:

``` text
domain
event_model
historical_loader
replay
analysis
state
projections
live
application
```

### `domain`

Общие сущности и value objects:

``` text
Candle
Instrument
Timeframe
TimeRange
DatasetId
DatasetVersion
```

### `event_model`

Общий контракт событий:

``` text
EventEnvelope
EventType
Event validation
Serialization
```

### `historical_loader`

``` text
Download
Raw storage
Normalization
Validation
Gap detection
Recovery
Dataset management
Checkpoint
```

### `replay`

``` text
ReplayRunner
ReplayDataSource
EventAdapter
Replay clock
Deterministic ordering
```

### `analysis`

Только BSS business logic:

``` text
Swing
Structure
Zones
Cascade
Volatility
Qualification
```

### `state`

``` text
Scenario state
State reducer
State rebuild
```

### `projections`

``` text
Push
Audit
Delivery state
```

### `live`

Live source должен подключаться к тому же Analysis Engine.

------------------------------------------------------------------------

## 3. C4 Context

``` text
                         ┌─────────────────────┐
                         │ Оператор /           │
                         │ разработчик          │
                         └──────────┬──────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────┐
                    │ Historical Data Loader      │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │ Historical Data Source       │
                    └─────────────────────────────┘

                    Loader → Replay → BSS Engine
                                      │
                                      ▼
                                 Event Store

Live Data Source ──────────────────► BSS Engine
```

------------------------------------------------------------------------

## 4. C4 Container

Основной pipeline:

``` text
Оператор
   ↓
CLI / API
   ↓
Job Manager
   ↓
Historical Source Adapter
   ↓
Raw Storage
   ↓
Parser / Normalizer
   ↓
Validator
   ↓
Normalized Dataset
   ↓
Gap Detector
   ↓
Recovery Manager
```

Отдельные ветки:

``` text
Job Manager ─────► Metadata / Checkpoint
Validator ───────► Metadata
Recovery ────────► Metadata

Dataset ─────────► ReplayDataSource
ReplayDataSource ─► BSS Analysis Engine
```

------------------------------------------------------------------------

## 5. C4 Component

Внутри Loader:

``` text
CLI/API
   ↓
Job Manager
   ↓
Range Planner
   ↓
Chunk Downloader
   ↓
Parser
   ↓
Normalizer
   ↓
Candle Validator
   ↓
Duplicate Detector
   ↓
Dataset Manager
   ↓
Gap Detector
   ↓
Recovery Manager
```

Инфраструктурные компоненты:

``` text
Retry / Backoff
Rate Limiter
Raw Storage
Dataset Storage
Metadata Store
Checkpoint Store
```

------------------------------------------------------------------------

## 6. Deployment MVP

MVP не требует микросервисов.

Рекомендуемая схема:

``` text
                    Один сервер / рабочая станция
 ┌─────────────────────────────────────────────────────┐
 │                                                     │
 │  CLI/API                                            │
 │      │                                              │
 │      ├── Historical Loader                          │
 │      │       ├── Raw Storage                        │
 │      │       ├── Dataset Storage                    │
 │      │       └── Metadata / Checkpoint              │
 │      │                                              │
 │      ├── Replay Runner                              │
 │      │                                              │
 │      └── BSS Analysis Engine                        │
 │              │                                      │
 │              └── Event Store                        │
 │                                                     │
 └─────────────────────────────────────────────────────┘
          │
          └──── Historical Source
```

Не добавлять Kubernetes/Kafka/очереди без отдельного требования.

------------------------------------------------------------------------

## 7. Архитектурные инварианты

### INV-01

Loader не реализует BSS business rules.

### INV-02

Replay и Live используют один Analysis Engine.

### INV-03

Dataset immutable после публикации версии `READY`.

### INV-04

Raw layer сохраняется отдельно от normalized layer.

### INV-05

Replay потоковый.

### INV-06

Нет look-ahead.

### INV-07

Event имеет immutable фактологическую семантику.

### INV-08

State не является единственным источником истины.

### INV-09

Push --- projection, а не business state Scenario.

### INV-10

Неоднозначность исторических данных должна быть явной.

------------------------------------------------------------------------

## 8. Поток восстановления

``` text
Gap detected
     ↓
DATA_INTEGRITY_GAP
     ↓
DATA_RECOVERY_STARTED
     ↓
Download missing range
     ↓
Validate
     ↓
DATA_RECOVERY_COMPLETED
     ↓
STATE_REBUILD_STARTED
     ↓
Replay affected window
     ↓
STATE_REBUILD_COMPLETED
```

Важно:

``` text
Loader → recovery data
State layer → state rebuild
```

------------------------------------------------------------------------

## 9. Replay flow

``` text
Dataset
  ↓
chunk
  ↓
Candle
  ↓
CANDLE_CLOSED
  ↓
BSS Analysis Engine
  ↓
Business events
  ↓
State
  ↓
Projection
```

Не должно существовать отдельной «backtest версии» BSS business logic.
