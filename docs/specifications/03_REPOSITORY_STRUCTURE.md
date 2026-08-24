# BSS --- структура репозитория

## 1. Общий принцип

Рекомендуется один monorepo.

``` text
bss/
├── docs/
├── config/
├── src/
├── tests/
├── data/
├── scripts/
└── tools/
```

Historical Loader, Replay и Analysis Engine являются отдельными bounded
modules внутри одного репозитория.

------------------------------------------------------------------------

## 2. Полная структура

``` text
bss/
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
│
├── docs/
│   ├── requirements/
│   │   ├── requirements-v0.4.md
│   │   └── open-questions.md
│   │
│   ├── architecture/
│   │   ├── c4/
│   │   │   ├── context.puml
│   │   │   ├── container.puml
│   │   │   ├── component.puml
│   │   │   └── deployment.puml
│   │   ├── sequence/
│   │   │   ├── loader-sequence.puml
│   │   │   └── replay-sequence.puml
│   │   └── decisions/
│   │       ├── ADR-001-monorepo.md
│   │       ├── ADR-002-dataset-format.md
│   │       ├── ADR-003-event-model.md
│   │       └── ADR-004-replay.md
│   │
│   ├── specifications/
│   │   ├── dataset-format.md
│   │   ├── replay-protocol.md
│   │   ├── event-model.md
│   │   └── configuration.md
│   │
│   └── runbooks/
│       ├── local-development.md
│       ├── historical-data.md
│       └── replay.md
│
├── config/
│   ├── default.yaml
│   ├── development.yaml
│   ├── test.yaml
│   └── production.yaml
│
├── src/
│   └── bss/
│       ├── domain/
│       │   ├── candle.py
│       │   ├── instrument.py
│       │   ├── timeframe.py
│       │   ├── identifiers.py
│       │   └── time_range.py
│       │
│       ├── event_model/
│       │   ├── envelope.py
│       │   ├── event_types.py
│       │   ├── serializer.py
│       │   └── validators.py
│       │
│       ├── historical_loader/
│       │   ├── application/
│       │   │   ├── download_service.py
│       │   │   ├── validation_service.py
│       │   │   ├── recovery_service.py
│       │   │   └── dataset_service.py
│       │   ├── domain/
│       │   │   ├── dataset.py
│       │   │   ├── download_job.py
│       │   │   ├── checkpoint.py
│       │   │   ├── data_gap.py
│       │   │   └── interfaces/
│       │   │       ├── historical_source.py
│       │   │       ├── raw_storage.py
│       │   │       ├── dataset_storage.py
│       │   │       ├── metadata_storage.py
│       │   │       └── checkpoint_storage.py
│       │   ├── infrastructure/
│       │   │   ├── sources/
│       │   │   │   ├── binance/
│       │   │   │   │   ├── adapter.py
│       │   │   │   │   ├── client.py
│       │   │   │   │   └── mapper.py
│       │   │   │   ├── file/
│       │   │   │   └── archive/
│       │   │   ├── storage/
│       │   │   │   ├── raw_filesystem.py
│       │   │   │   ├── parquet_dataset.py
│       │   │   │   ├── metadata_filesystem.py
│       │   │   │   └── checkpoint_filesystem.py
│       │   │   └── networking/
│       │   │       ├── retry.py
│       │   │       ├── rate_limiter.py
│       │   │       └── http_client.py
│       │   └── cli/
│       │       └── main.py
│       │
│       ├── replay/
│       │   ├── replay_runner.py
│       │   ├── replay_data_source.py
│       │   ├── event_adapter.py
│       │   └── clock.py
│       │
│       ├── analysis/
│       │   ├── swing/
│       │   ├── structure/
│       │   ├── zones/
│       │   ├── cascade/
│       │   ├── volatility/
│       │   └── qualification/
│       │
│       ├── state/
│       │   ├── scenario_state.py
│       │   ├── state_reducer.py
│       │   └── state_rebuilder.py
│       │
│       ├── projections/
│       │   ├── push/
│       │   └── audit/
│       │
│       ├── live/
│       │   └── live_data_source.py
│       │
│       └── application/
│           └── bss_engine.py
│
├── tests/
│   ├── unit/
│   │   ├── historical_loader/
│   │   ├── replay/
│   │   ├── event_model/
│   │   └── analysis/
│   ├── integration/
│   │   ├── historical_loader/
│   │   ├── replay/
│   │   └── engine/
│   ├── recovery/
│   │   ├── gap_recovery/
│   │   └── checkpoint_resume/
│   └── golden/
│       ├── datasets/
│       ├── cases/
│       └── expected_events/
│
├── data/
│   ├── raw/
│   ├── normalized/
│   ├── metadata/
│   ├── checkpoints/
│   ├── validation/
│   └── events/
│       └── replay/
│
├── scripts/
│   ├── download-history
│   ├── validate-dataset
│   ├── find-gaps
│   ├── recover-dataset
│   └── replay
│
└── tools/
```

------------------------------------------------------------------------

## 3. Что не следует делать

Не создавать:

``` text
historical_loader/binance_loader.py
```

с бизнес-логикой.

Не создавать:

``` text
historical_loader/replay.py
```

как смешанный Loader/Replay компонент.

Не помещать BSS rules в Loader.

Не делать отдельную копию Analysis Engine для backtest.

------------------------------------------------------------------------

## 4. Что хранить в Git

В Git:

-   код;
-   конфигурационные шаблоны;
-   документацию;
-   PlantUML;
-   маленькие golden fixtures;
-   схемы;
-   тесты.

Не хранить в Git большие исторические datasets и credentials.

------------------------------------------------------------------------

## 5. Data layout

``` text
data/
├── raw/
│   └── <source>/<symbol>/<timeframe>/<YYYY>/<MM>/<DD>/
├── normalized/
│   └── <symbol>/<timeframe>/
├── metadata/
│   └── datasets/
├── checkpoints/
├── validation/
└── events/
    └── replay/<dataset_id>/<run_id>.jsonl
```

------------------------------------------------------------------------

## 6. Зависимости

Зависимость должна идти в сторону абстракций:

``` text
CLI
 ↓
Application
 ↓
Domain interfaces
 ↑
Infrastructure
```

Business domain не должен зависеть от конкретного HTTP-клиента или
файловой реализации.

------------------------------------------------------------------------

## 7. Общие модели

`Candle`, `Instrument`, `Timeframe`, идентификаторы и Event Envelope не
должны дублироваться между Loader и Analysis Engine.
