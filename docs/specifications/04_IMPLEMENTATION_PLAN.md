# План реализации BSS Historical Data Loader

## 1. Стратегия

Реализовывать снизу вверх, сохраняя работающий вертикальный срез.

Не начинать с CLI или сложной инфраструктуры.

Первый end-to-end milestone:

``` text
Fixture Source
 ↓
Raw
 ↓
Normalized
 ↓
Validation
 ↓
READY Dataset
 ↓
ReplayDataSource
 ↓
CANDLE_CLOSED
 ↓
Recorded Event Stream
```

------------------------------------------------------------------------

## 2. Этап 0 --- подготовка

Создать:

-   `pyproject.toml`;
-   package `bss`;
-   базовый test runner;
-   config loader;
-   logging;
-   directories;
-   `.env.example`.

Результат:

``` bash
pytest
```

запускается без ошибок.

------------------------------------------------------------------------

## 3. Этап 1 --- domain

Реализовать:

``` text
Candle
Instrument
Timeframe
TimeRange
DatasetId
DatasetVersion
DatasetMetadata
DownloadJob
Checkpoint
DataGap
```

Добавить unit tests.

------------------------------------------------------------------------

## 4. Этап 2 --- Source interface

Создать:

``` python
class HistoricalSource:
    def available_range(...): ...
    def download(...): ...
```

Сделать сначала `FileHistoricalSource` / fixture source.

Цель --- не зависеть от реального внешнего API на ранних этапах.

------------------------------------------------------------------------

## 5. Этап 3 --- Raw storage

Реализовать:

``` text
RawStorage
```

Требования:

-   deterministic path;
-   atomic write;
-   checksum;
-   existence check;
-   idempotent write;
-   чтение chunk.

------------------------------------------------------------------------

## 6. Этап 4 --- Normalization

Реализовать pipeline:

``` text
Source record
 ↓
Parser
 ↓
Mapper
 ↓
Candle
 ↓
Normalized storage
```

Проверить:

-   UTC;
-   timezone-aware datetime;
-   OHLC;
-   volume;
-   ordering.

------------------------------------------------------------------------

## 7. Этап 5 --- Validation

Реализовать:

``` text
CandleValidator
DuplicateDetector
GapDetector
DatasetIntegrity
```

Dataset не получает `READY`, пока validation не успешна.

------------------------------------------------------------------------

## 8. Этап 6 --- Dataset metadata

Реализовать:

``` text
dataset_id
dataset_version
loader_version
schema_version
checksum
range
symbols
timeframes
status
```

Статусы минимум:

``` text
CREATED
DOWNLOADING
VALIDATING
READY
INVALID
RECOVERING
```

------------------------------------------------------------------------

## 9. Этап 7 --- Checkpoint / Resume

Checkpoint должен позволять продолжить interrupted download.

Минимум:

``` text
job_id
dataset_id
source
symbol
timeframe
completed_ranges
current_range
updated_at
status
```

Повторный запуск не должен создавать duplicate data.

------------------------------------------------------------------------

## 10. Этап 8 --- Retry / Rate Limit

Реализовать отдельно:

``` text
RetryPolicy
BackoffStrategy
RateLimiter
```

Не смешивать их с HTTP client.

Тестировать 429/5xx/timeout.

------------------------------------------------------------------------

## 11. Этап 9 --- Recovery

Pipeline:

``` text
Detect gap
 ↓
Persist DATA_INTEGRITY_GAP
 ↓
Plan recovery range
 ↓
Download
 ↓
Validate
 ↓
Merge
 ↓
Revalidate
 ↓
Mark recovered
```

Recovery должен быть идемпотентным.

------------------------------------------------------------------------

## 12. Этап 10 --- ReplayDataSource

Реализовать потоковую выдачу:

``` python
stream(symbol, timeframe, start, end)
```

Гарантии:

-   deterministic order;
-   UTC;
-   no look-ahead;
-   bounded memory;
-   dataset version fixed for run.

------------------------------------------------------------------------

## 13. Этап 11 --- Event Adapter

Реализовать генерацию `CANDLE_CLOSED`.

Envelope:

``` text
event_id
event_type
schema_version
event_time
processed_at
symbol
timeframe
source
payload
```

`source.type = historical`.

------------------------------------------------------------------------

## 14. Этап 12 --- Replay Runner

Создать:

``` text
run_id
dataset_id
configuration_version
engine_version
```

Сохранять event stream.

Реализовать повторный запуск и сравнение двух stream.

------------------------------------------------------------------------

## 15. Этап 13 --- CLI

Добавить:

``` text
sources
download
validate
datasets
dataset-info
gaps
recover
replay
status
jobs
```

CLI должен вызывать application services, а не содержать бизнес-логику.

------------------------------------------------------------------------

## 16. Этап 14 --- Tests

### Unit

Все domain services.

### Integration

Полный pipeline.

### Recovery

Все аварийные сценарии.

### Determinism

Один Dataset + одна configuration → два replay run → одинаковый event
stream.

------------------------------------------------------------------------

## 17. Этап 15 --- документация

Создать:

``` text
README.md
docs/runbooks/local-development.md
docs/runbooks/historical-data.md
docs/runbooks/replay.md
docs/specifications/dataset-format.md
docs/specifications/replay-protocol.md
```

------------------------------------------------------------------------

## 18. Definition of Done

Реализация считается завершённой, когда выполнены все пункты
`05_ACCEPTANCE_CRITERIA.md` и все пункты DoD из ЧТЗ.

------------------------------------------------------------------------

## 19. Приоритеты

### P0

-   Domain
-   Source interface
-   Raw
-   Normalized
-   Validation
-   Dataset
-   ReplayDataSource
-   CANDLE_CLOSED
-   Determinism
-   Tests

### P1

-   Recovery
-   Checkpoint
-   Resume
-   Retry
-   Rate limiting
-   CLI

### P2

-   Source adapters beyond first source
-   Advanced comparison tooling
-   Performance optimizations
