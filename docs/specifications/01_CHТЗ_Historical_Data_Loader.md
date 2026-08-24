# Частное техническое задание

## Historical Data Loader для BSS Structural Monitoring Agent

**Версия:** 1.0\
**Статус:** Draft for implementation\
**Основание:** Requirements v0.4, Event Model v0.2 и результаты
архитектурного обсуждения.

------------------------------------------------------------------------

## 1. Назначение

Разработать `Historical Data Loader`, который получает исторические
рыночные данные, сохраняет исходный слой, нормализует данные, проверяет
их целостность, поддерживает восстановление и предоставляет
воспроизводимый Dataset для Replay.

Loader является инфраструктурным компонентом и **не является BSS
Analysis Engine**.

### Loader не должен:

-   определять Swing;
-   определять Structure Break;
-   определять Mother OB;
-   определять OBLS;
-   определять Cascade;
-   рассчитывать qualification;
-   формировать `SETUP_QUALIFIED`;
-   принимать торговые решения;
-   формировать торговые заявки;
-   отправлять Telegram Push.

------------------------------------------------------------------------

## 2. Архитектурная роль

``` text
Historical Source
      ↓
Historical Data Loader
      ↓
Normalized Historical Dataset
      ↓
ReplayDataSource
      ↓
BSS Analysis Engine
      ↓
Event Stream
      ↓
State / Audit / Push
```

Live и Replay должны использовать один и тот же аналитический движок;
отличается источник данных.

------------------------------------------------------------------------

## 3. MVP scope

### Входит в MVP

1.  Historical Source interface.
2.  Source Adapter.
3.  Raw storage.
4.  Normalized candle storage.
5.  Dataset metadata.
6.  Dataset versioning.
7.  Candle validation.
8.  Duplicate detection.
9.  Gap detection.
10. Checkpoint.
11. Resume.
12. Retry.
13. Rate limiting.
14. Recovery.
15. ReplayDataSource.
16. `CANDLE_CLOSED`.
17. Event envelope integration.
18. Deterministic replay.
19. No look-ahead.
20. Event persistence.
21. Unit, integration и recovery tests.
22. CLI. 

### Не входит в MVP

-   distributed workers;
-   web UI;
-   сложный scheduler;
-   ML;
-   LLM;
-   automatic trading;
-   TigerTrade execution.

------------------------------------------------------------------------

## 4. Исторические данные

### 4.1 Инструменты

MVP должен поддерживать конфигурируемый список минимум из 5
инструментов.

Инструменты не должны быть зашиты в код.

### 4.2 Основные таймфреймы

``` text
D1
H4
H1
M15
```

Также должна существовать возможность загрузки более низкого временного
масштаба для разрешения intrabar ambiguity.

### 4.3 Candle

Минимальная каноническая модель:

``` json
{
  "candle_id": "...",
  "instrument_id": "...",
  "symbol": "SOLUSDT",
  "timeframe": "M15",
  "open_time": "...",
  "close_time": "...",
  "open": 0.0,
  "high": 0.0,
  "low": 0.0,
  "close": 0.0,
  "volume": 0.0
}
```

Все нормализованные timestamps --- UTC.

------------------------------------------------------------------------

## 5. Raw Layer

Исходные данные должны сохраняться до нормализации либо существовать
эквивалентный механизм восстановления исходного набора.

Рекомендуемая структура:

``` text
data/raw/<source>/<symbol>/<timeframe>/<YYYY>/<MM>/<DD>/
```

Raw layer нужен для:

-   повторной обработки;
-   аудита;
-   диагностики;
-   восстановления Dataset;
-   изменения parser без повторной загрузки из внешнего источника.

------------------------------------------------------------------------

## 6. Normalized Layer

Канонический Dataset не должен зависеть от формата конкретного
источника.

Рекомендуемая структура:

``` text
data/normalized/<symbol>/<timeframe>/
```

Для больших datasets предпочтителен Parquet. Для событий --- JSONL.

------------------------------------------------------------------------

## 7. Dataset

Каждый Dataset должен иметь стабильный `dataset_id`.

Metadata должна содержать как минимум:

``` json
{
  "dataset_id": "...",
  "dataset_version": "...",
  "source": "...",
  "symbol": "SOLUSDT",
  "timeframes": ["D1", "H4", "H1", "M15"],
  "from": "...",
  "to": "...",
  "created_at": "...",
  "loader_version": "...",
  "schema_version": "...",
  "checksum": "..."
}
```

Dataset должен получить статус `READY` только после успешной validation.

Для воспроизводимости необходимо фиксировать:

``` text
dataset_id
dataset_version
schema_version
loader_version
engine_version
configuration_version
```

------------------------------------------------------------------------

## 8. Source abstraction

Ядро Loader должно зависеть от интерфейса, а не от конкретного API.

Пример:

``` python
class HistoricalSource:
    def available_range(self, symbol, timeframe):
        ...

    def download(self, symbol, timeframe, start, end):
        ...
```

Архитектура:

``` text
HistoricalLoader
       ↓
HistoricalSource
       ├── API
       ├── Files
       └── Archive
```

Конкретный источник может быть заменён без изменения Replay и BSS
Analysis Engine.

------------------------------------------------------------------------

## 9. Загрузка

Загрузка должна выполняться блоками.

Требования:

-   идемпотентность;
-   повторный запуск без дублирования;
-   checkpoint;
-   resume;
-   retry;
-   exponential backoff;
-   timeout;
-   rate limiting.

Пример конфигурации:

``` yaml
retry:
  max_attempts: 5
  initial_delay_seconds: 1
  max_delay_seconds: 60

rate_limit:
  requests_per_second: 5
  max_parallel_requests: 4
```

------------------------------------------------------------------------

## 10. Validation

Минимальные проверки:

-   OHLC consistency;
-   timestamp consistency;
-   UTC;
-   duplicates;
-   ordering;
-   missing candles;
-   допустимость диапазонов;
-   checksum / целостность chunk.

Validation должна быть повторяемой и не изменять исходные Raw данные.

------------------------------------------------------------------------

## 11. Gap Detection

При обнаружении gap необходимо сохранить инфраструктурное событие:

``` text
DATA_INTEGRITY_GAP
```

Пример payload:

``` json
{
  "symbol": "SOLUSDT",
  "timeframe": "M15",
  "from": "...",
  "to": "...",
  "expected_candles": 100,
  "actual_candles": 97
}
```

`DATA_INTEGRITY_GAP` не является стратегическим сигналом.

------------------------------------------------------------------------

## 12. Recovery

Обязательный сценарий:

``` text
DATA_INTEGRITY_GAP
        ↓
DATA_RECOVERY_STARTED
        ↓
download missing range
        ↓
validate
        ↓
DATA_RECOVERY_COMPLETED
```

После recovery Dataset должен быть повторно провалидирован.

`STATE_REBUILD` находится за пределами ответственности Loader: Loader
восстанавливает данные, а state layer пересчитывает состояние через
Replay.

------------------------------------------------------------------------

## 13. ReplayDataSource

Replay не должен загружать весь Dataset в RAM.

Правильная схема:

``` text
Dataset
   ↓
chunk
   ↓
Candle
   ↓
CANDLE_CLOSED
   ↓
BSS Engine
   ↓
next Candle
```

Минимальный интерфейс:

``` python
class ReplayDataSource:
    def candles(self, symbol, timeframe, start, end):
        ...

    def stream(self, symbol, timeframe, start, end):
        ...

    def metadata(self):
        ...
```

------------------------------------------------------------------------

## 14. CANDLE_CLOSED

Каждая закрытая историческая свеча при replay должна приводить к событию
`CANDLE_CLOSED`.

Envelope должен содержать:

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

`event_time` --- время рыночного события.

`processed_at` --- время обработки системой.

------------------------------------------------------------------------

## 15. Deterministic replay

Одинаковая комбинация:

``` text
dataset
+
configuration
+
engine version
+
schema version
```

должна давать одинаковый event stream.

Каждый replay должен иметь:

``` text
run_id
dataset_id
engine_version
configuration_version
started_at
finished_at
status
```

Event stream рекомендуется сохранять:

``` text
data/events/replay/<dataset_id>/<run_id>.jsonl
```

------------------------------------------------------------------------

## 16. No look-ahead

Replay не должен предоставлять аналитическому движку будущие данные.

На момент:

``` text
event_time = 2025-01-10T10:00:00Z
```

данные:

``` text
10:15
10:30
...
```

не должны быть доступны для принятия текущего решения.

------------------------------------------------------------------------

## 17. Intrabar ambiguity

OHLC может быть недостаточно для определения порядка событий внутри
свечи.

Если порядок неразрешим, система **не должна угадывать**.

Необходимо явно фиксировать ambiguity, например:

``` json
{
  "ambiguity": true,
  "reason": "event_order_not_resolvable_from_ohlc"
}
```

Для `ZONE_TESTED`, `ZONE_DEATH` и других зависимых от порядка событий
случаев должен быть доступен более детальный источник, если он
необходим.

------------------------------------------------------------------------

## 18. Historical spread

Loader не должен сам придумывать исторический spread.

Если выбран режим, зависящий от historical spread, Dataset/Replay должен
уметь предоставить соответствующие данные.

При отсутствии достоверного historical bid/ask/spread необходимо явно
фиксировать отсутствие данных.

Текущий spread не должен молча использоваться как исторический.

------------------------------------------------------------------------

## 19. Event Model

Общее правило:

``` text
Event = immutable fact
State = current interpretation
Push = derived projection
```

Loader отвечает только за инфраструктурные события и передачу
`CANDLE_CLOSED`.

BSS business events генерирует Analysis Engine.

------------------------------------------------------------------------

## 20. Что Loader не должен знать

Loader не должен содержать:

``` text
P1/P2/P3/P4
HH/HL/LH/LL
Swing
StructureBreak
MotherOB
OBLS
Cascade
Scenario
Setup
0.3% qualification
SETUP_QUALIFIED
Push business logic
```

------------------------------------------------------------------------

## 21. CLI

Минимальный CLI:

``` bash
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

Примеры:

``` bash
loader download   --source binance   --symbol SOLUSDT   --timeframes D1,H4,H1,M15   --from 2024-01-01   --to 2026-01-01
```

``` bash
loader validate --dataset ds_001
```

``` bash
loader gaps --dataset ds_001
```

``` bash
loader recover --dataset ds_001
```

``` bash
loader replay   --dataset ds_001   --from 2025-01-01   --to 2025-06-01
```

``` bash
loader dataset-info --dataset ds_001
```

------------------------------------------------------------------------

## 22. Логирование

Структурированные логи должны включать:

``` text
timestamp
level
job_id
dataset_id
symbol
timeframe
operation
period_from
period_to
rows
duration
error
```

------------------------------------------------------------------------

## 23. Метрики

Минимум:

``` text
download_requests_total
download_errors_total
download_retries_total
candles_downloaded_total
candles_validated_total
candles_rejected_total
duplicates_total
gaps_total
bytes_downloaded_total
download_duration
validation_duration
replay_duration
```

------------------------------------------------------------------------

## 24. Безопасность

Credentials не должны храниться:

-   в коде;
-   в Git;
-   в Dataset;
-   в event log.

Использовать environment variables, external configuration или secret
manager.

------------------------------------------------------------------------

## 25. Производительность

MVP:

-   5 инструментов;
-   D1/H4/H1/M15;
-   потоковый replay;
-   память не должна расти линейно с размером Dataset.

------------------------------------------------------------------------

## 26. Тестирование

### Unit

-   parser;
-   normalization;
-   timezone;
-   candle validation;
-   duplicate detection;
-   gap detection;
-   checkpoint;
-   retry;
-   rate limiter;
-   metadata;
-   checksum;
-   replay ordering.

### Integration

``` text
Source
 ↓
Raw
 ↓
Normalized
 ↓
Validation
 ↓
Dataset READY
 ↓
ReplayDataSource
 ↓
CANDLE_CLOSED
 ↓
BSS Engine
 ↓
Event Stream
```

### Recovery

Проверить:

1.  остановку во время download;
2.  restart;
3.  повреждение chunk;
4.  duplicate chunk;
5.  timeout;
6.  HTTP 429;
7.  HTTP 500;
8.  отсутствие candles;
9.  gap;
10. recovery;
11. повторный replay;
12. идентичность результата после восстановления.

------------------------------------------------------------------------

## 27. Acceptance baseline

-   Dataset становится `READY` только после validation.
-   Нет duplicate candles.
-   Все timestamps в UTC.
-   Все gaps обнаруживаются и фиксируются.
-   Download можно продолжить с checkpoint.
-   Повторная загрузка идемпотентна.
-   Replay использует тот же Analysis Engine, что и live.
-   Нет look-ahead.
-   Intrabar ambiguity не скрывается эвристикой.
-   Dataset можно восстановить после gap.
-   Полный replay event stream можно сохранить.
-   Event envelope соответствует Event Model v0.2.
-   Одинаковые dataset/configuration/engine version дают одинаковый
    event stream.

------------------------------------------------------------------------

## 28. Open Questions

До реализации нельзя самостоятельно закрывать:

-   Q-06 --- источник historical spread;
-   Q-07 --- порядок конфликтующих событий внутри свечи;
-   Q-12 --- ограничения downstream transport/TigerTrade;
-   Q-13 --- первый исторический период и допустимый bid/ask history
    source.

Если вопрос влияет на архитектуру или бизнес-логику, зафиксировать его
как `TBD` и остановиться на безопасном интерфейсе.

------------------------------------------------------------------------

## 29. Definition of Done

``` text
[ ] Historical source adapter
[ ] Raw storage
[ ] Normalized storage
[ ] Dataset metadata
[ ] Dataset versioning
[ ] Candle validation
[ ] Gap detection
[ ] Checkpoint
[ ] Resume
[ ] Retry
[ ] Rate limiting
[ ] ReplayDataSource
[ ] CANDLE_CLOSED integration
[ ] Event envelope
[ ] event_time / processed_at
[ ] Intrabar ambiguity
[ ] Deterministic replay
[ ] No look-ahead
[ ] Recovery
[ ] Unit tests
[ ] Integration tests
[ ] Recovery tests
[ ] Documentation
```
