# Постановка задачи Coding Agent

## Роль

Ты реализуешь MVP `Historical Data Loader` для BSS Structural Monitoring
Agent.

Работай как senior software engineer / system architect.

------------------------------------------------------------------------

## Цель

Создать production-quality основу:

``` text
Historical Source
 ↓
Raw
 ↓
Normalized Dataset
 ↓
Validation
 ↓
Gap / Recovery
 ↓
ReplayDataSource
 ↓
CANDLE_CLOSED
 ↓
Deterministic Event Stream
```

------------------------------------------------------------------------

## Обязательные архитектурные ограничения

### 1. Loader не является Analysis Engine

Не реализовывать в Loader:

``` text
Swing
StructureBreak
MotherOB
OBLS
Cascade
Scenario
Setup
Qualification
Push business logic
```

### 2. Source abstraction

Не связывать domain с конкретным API.

### 3. Replay отдельно от Loader

`ReplayDataSource` должен находиться в модуле `replay`.

### 4. Общий Event Model

Не создавать отдельный event schema только для Loader.

### 5. Streaming

Не читать весь Dataset в память.

### 6. Determinism

Порядок выдачи должен быть стабильным.

### 7. No look-ahead

Будущие данные не должны использоваться текущим replay шагом.

### 8. Explicit ambiguity

Не разрешать неопределённость эвристикой.

------------------------------------------------------------------------

# Первый шаг

Перед написанием большого объёма кода:

1.  изучи текущий репозиторий;
2.  найди существующие модули;
3.  найди существующие модели `Candle` и Event;
4.  найди конфигурацию;
5.  найди существующие tests;
6.  сравни фактическую структуру с `03_REPOSITORY_STRUCTURE.md`.

Не переписывай существующий рабочий код без необходимости.

------------------------------------------------------------------------

# Реализация по вертикальным срезам

## Slice 1

Реализовать:

``` text
Candle
HistoricalSource
FixtureSource
RawStorage
NormalizedStorage
DatasetMetadata
```

Добавить tests.

## Slice 2

Добавить:

``` text
Validator
DuplicateDetector
GapDetector
```

## Slice 3

Добавить:

``` text
Checkpoint
Resume
Retry
RateLimiter
```

## Slice 4

Добавить:

``` text
Recovery
```

## Slice 5

Добавить:

``` text
ReplayDataSource
ReplayRunner
CANDLE_CLOSED
EventEnvelope
Event persistence
```

## Slice 6

Добавить CLI.

------------------------------------------------------------------------

# Обязательные тестовые сценарии

## Happy path

``` text
Fixture Source
 → Raw
 → Normalize
 → Validate
 → READY
 → Replay
 → CANDLE_CLOSED
```

## Duplicate

Повторная загрузка того же chunk не создаёт duplicate.

## Gap

Gap обнаруживается.

## Recovery

Gap восстанавливается.

## Resume

Interrupted download продолжает работу.

## Retry

429/5xx/timeout обрабатываются.

## Determinism

Два одинаковых replay дают одинаковый event stream.

## Ambiguity

Неопределённый intrabar order явно помечается.

------------------------------------------------------------------------

# CLI

Реализовать:

``` text
loader sources
loader download
loader validate
loader datasets
loader dataset-info
loader gaps
loader recover
loader replay
loader status
loader jobs
```

------------------------------------------------------------------------

# Конфигурация

Использовать configuration file и environment variables.

Не хранить credentials в Git.

------------------------------------------------------------------------

# Результат

В конце должны существовать:

``` text
src/bss/historical_loader/
src/bss/replay/
src/bss/event_model/
tests/unit/
tests/integration/
tests/recovery/
docs/
```

и документация:

``` text
README
historical-data runbook
replay runbook
dataset format
```

------------------------------------------------------------------------

# Что запрещено

Не делать:

-   Kubernetes;
-   Kafka;
-   distributed workers;
-   web UI;
-   ML;
-   LLM;
-   automatic trading;
-   TigerTrade execution.

Не добавлять инфраструктуру «на будущее» без необходимости.

------------------------------------------------------------------------

# Работа с TBD

Если встречается Q-06/Q-07/Q-12/Q-13:

-   не придумывай ответ;
-   сделай abstraction;
-   добавь TODO/TBD;
-   продолжай реализацию независимых частей.

------------------------------------------------------------------------

# Финальный отчёт

После реализации сообщить:

1.  какие файлы созданы/изменены;
2.  какие требования реализованы;
3.  какие тесты добавлены;
4.  результаты тестов;
5.  какие TBD остались;
6.  какие архитектурные решения приняты;
7.  какие места требуют решения пользователя.
