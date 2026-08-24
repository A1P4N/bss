# Acceptance Criteria --- Historical Data Loader

## AC-01 --- Source

Источник подключается через `HistoricalSource` abstraction.

**Проверка:** замена fixture source не требует изменения
domain/application logic.

------------------------------------------------------------------------

## AC-02 --- Dataset READY

Dataset получает:

``` text
READY
```

только после успешной validation.

------------------------------------------------------------------------

## AC-03 --- No duplicates

В normalized Dataset нет duplicate candles по идентификатору
инструмента, таймфрейму и времени.

------------------------------------------------------------------------

## AC-04 --- UTC

Все normalized timestamps timezone-aware и представлены в UTC.

------------------------------------------------------------------------

## AC-05 --- Ordering

Stream выдаёт candles в детерминированном порядке.

------------------------------------------------------------------------

## AC-06 --- Gap detection

Все ожидаемые gaps обнаруживаются и фиксируются.

------------------------------------------------------------------------

## AC-07 --- Checkpoint

Прерванный download можно продолжить.

------------------------------------------------------------------------

## AC-08 --- Idempotency

Повторная загрузка того же диапазона не создаёт duplicate data.

------------------------------------------------------------------------

## AC-09 --- Retry

Transient failures обрабатываются retry policy.

------------------------------------------------------------------------

## AC-10 --- Rate limit

Источник не получает запросы чаще заданного лимита.

------------------------------------------------------------------------

## AC-11 --- Recovery

Gap можно восстановить без полного пересоздания Dataset.

------------------------------------------------------------------------

## AC-12 --- Replay streaming

Replay не требует загрузки всего Dataset в RAM.

------------------------------------------------------------------------

## AC-13 --- CANDLE_CLOSED

Каждая replay candle порождает корректный `CANDLE_CLOSED`.

------------------------------------------------------------------------

## AC-14 --- Event envelope

Event содержит:

``` text
event_id
event_type
schema_version
event_time
processed_at
symbol
timeframe
source.type
source.dataset_id
source.engine_version
```

------------------------------------------------------------------------

## AC-15 --- Historical source

Для replay:

``` text
source.type = historical
```

------------------------------------------------------------------------

## AC-16 --- No look-ahead

Analysis Engine не получает будущие данные относительно текущего replay
event.

------------------------------------------------------------------------

## AC-17 --- Determinism

Одинаковые:

``` text
dataset
dataset_version
configuration
engine_version
schema_version
```

порождают одинаковый event stream.

------------------------------------------------------------------------

## AC-18 --- Replay run

Каждый run имеет:

``` text
run_id
dataset_id
engine_version
configuration_version
started_at
finished_at
status
```

------------------------------------------------------------------------

## AC-19 --- Event persistence

Полный replay event stream может быть сохранён.

------------------------------------------------------------------------

## AC-20 --- Intrabar ambiguity

Если порядок событий невозможно доказать из OHLC, ambiguity явно
фиксируется.

Запрещена скрытая эвристика.

------------------------------------------------------------------------

## AC-21 --- Historical spread

Если replay требует historical spread, отсутствие данных явно
фиксируется.

Current spread не подставляется молча.

------------------------------------------------------------------------

## AC-22 --- Separation of concerns

В Loader отсутствуют BSS business rules.

------------------------------------------------------------------------

## AC-23 --- Same engine

Replay и Live используют один BSS Analysis Engine.

------------------------------------------------------------------------

## AC-24 --- Recovery and state rebuild separation

Loader восстанавливает Dataset.

State layer выполняет STATE_REBUILD.

------------------------------------------------------------------------

## AC-25 --- Tests

Должны существовать:

-   unit tests;
-   integration tests;
-   recovery tests;
-   determinism tests;
-   replay ordering tests.

------------------------------------------------------------------------

## AC-26 --- Documentation

Должны быть описаны:

-   запуск;
-   конфигурация;
-   структура Dataset;
-   recovery;
-   replay;
-   troubleshooting.

------------------------------------------------------------------------

# Definition of Done

``` text
[ ] Source adapter
[ ] Raw storage
[ ] Normalized storage
[ ] Dataset metadata
[ ] Dataset versioning
[ ] Validation
[ ] Gap detection
[ ] Checkpoint
[ ] Resume
[ ] Retry
[ ] Rate limiting
[ ] Recovery
[ ] ReplayDataSource
[ ] CANDLE_CLOSED
[ ] Event envelope
[ ] event_time / processed_at
[ ] Intrabar ambiguity
[ ] Deterministic replay
[ ] No look-ahead
[ ] Event persistence
[ ] Unit tests
[ ] Integration tests
[ ] Recovery tests
[ ] Documentation
```
