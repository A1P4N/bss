# BSS — AGENTS.md

## 1. Назначение

Ты работаешь над **BSS Structural Monitoring Agent**. Текущий основной workstream: `Historical Data Loader` и `Replay`.

Перед существенными изменениями изучи документацию проекта и соблюдай иерархию источников.

## 2. Иерархия проектной документации

```text
Requirements
    ↓
Event Model
    ↓
Architecture / C4 / Sequence
    ↓
ADR
    ↓
ЧТЗ конкретного компонента
    ↓
Implementation Plan / Acceptance Criteria
    ↓
Code + Tests
```

Основные документы:

```text
docs/requirements/Requirements-v0.4.md
docs/architecture/Event-Model-v0.2.md
docs/specifications/01_CHТЗ_Historical_Data_Loader.md
docs/specifications/02_ARCHITECTURE.md
docs/specifications/03_REPOSITORY_STRUCTURE.md
docs/specifications/04_IMPLEMENTATION_PLAN.md
docs/specifications/05_ACCEPTANCE_CRITERIA.md
docs/specifications/06_OPEN_QUESTIONS.md
docs/specifications/07_CODING_AGENT_TASK.md
docs/specifications/08_CODING_AGENT_RULES.md
```

Актуальные ADR:

```text
docs/decisions/
├── ADR-001-immutable-events-derived-state.md
├── ADR-002-file-first-mvp-storage.md
├── ADR-003-pure-reducer.md
├── ADR-004-push-as-projection.md
├── ADR-005-same-analysis-engine-live-replay.md
└── ADR-006-mother-ob-baseline.md
```

Актуальные диаграммы:

```text
docs/architecture/
├── C4-Context.puml
├── C4-Container.puml
├── C4-Component-Loader.puml
├── C4-Component-Replay.puml
├── C4-Deployment-MVP.puml
├── Sequence-Loader.puml
└── Sequence-Replay.puml
```

Если документа нет, не придумывай его содержание.

## 3. Правила работы с Requirements и ADR

`Requirements v0.4` определяет требования, ограничения и открытые вопросы.
`Event Model v0.2` определяет Event Envelope и семантику событий, State и Push.
`Accepted` ADR фиксируют принятые архитектурные решения и обязательны к соблюдению.

Текущие решения:

```text
ADR-001 → Immutable Events + Derived State
ADR-002 → File-first Storage для MVP
ADR-003 → Pure Reducer
ADR-004 → Push как Derived Projection
ADR-005 → Один Analysis Engine для Live и Replay
ADR-006 → SIMPLE Mother OB как MVP baseline
```

Если обнаружен конфликт:

```text
обнаружен конфликт
      ↓
определить затронутые документы
      ↓
проверить Requirements / Event Model / ADR
      ↓
если конфликт не разрешён
      ↓
TBD / Open Question
      ↓
сообщить пользователю
```

Не менять Accepted ADR автоматически в рамках coding-задачи.

## 4. Главная архитектурная граница

```text
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

Критически важно:

```text
Loader ≠ Replay ≠ Analysis Engine
```

Live и Replay используют один и тот же Analysis Engine. Это закреплено ADR-005.

## 5. ADR-001 — Immutable Events + Derived State

```text
Event = immutable fact
State = current interpretation of events
```

Канонической историей анализа являются неизменяемые события. State вычисляется через:

```text
reduce(state, event) -> state'
```

Snapshots допускаются для ускорения восстановления, но не заменяют event history.

## 6. ADR-002 — File-first Storage для MVP

В MVP используется file-first storage. Storage скрыт за интерфейсами:

```python
class DatasetStorage:
    ...

class EventStorage:
    ...

class StateSnapshotStorage:
    ...
```

Не связывать domain и Analysis Engine с конкретным файловым форматом.

Обязательны append semantics, atomic snapshots, idempotency, versioning, metadata, validation и recovery.

Не добавлять БД, Kafka или distributed storage без отдельного требования.

## 7. ADR-003 — Pure Reducer

State transitions реализуются через:

```text
reduce(state, event) -> state'
```

Reducer не выполняет I/O, не обращается к сети, не отправляет Push, не изменяет Event, не зависит от wall-clock и случайности.

Правильная схема:

```text
Event
 ↓
Reducer
 ↓
State
```

## 8. ADR-004 — Push как Derived Projection

```text
Analysis / Events
        ↓
SETUP_QUALIFIED
        ↓
Push Projection
        ↓
PUSH_CREATED
        ↓
Transport Adapter
        ↓
PUSH_SENT / PUSH_SEND_FAILED
```

Критическое правило:

```text
Qualification ≠ Delivery
```

Detector не вызывает напрямую Telegram, TigerTrade или другой внешний transport. Replay не должен приводить к реальной внешней отправке Push без явно предусмотренного режима.

## 9. ADR-005 — Один Analysis Engine для Live и Replay

```text
Historical Dataset → ReplayDataSource → Analysis Engine → Event Stream
Live Market Data   → LiveDataSource   → Analysis Engine → Event Stream
```

Запрещено создавать отдельную business-logic версию BSS для backtest/replay.

Replay должен фиксировать:

```text
dataset_id
dataset_version
configuration_version
engine_version
schema_version
```

Одинаковый Dataset + версии + configuration должны давать одинаковый event stream в пределах acceptance criteria.

## 10. ADR-006 — SIMPLE Mother OB

Для MVP используется `SIMPLE Mother OB` как детерминированный базовый режим:

```text
MotherOBDetector
    ├── SIMPLE
    └── SEMANTIC
```

`SIMPLE` — default для MVP, пока semantic predicates не формализованы и не утверждены.

Не добавлять undocumented heuristics. При неоднозначности — TBD/Open Question.

## 11. Historical Data Loader

Loader отвечает только за:

- получение исторических данных;
- Source Adapter;
- Raw Storage;
- parsing;
- normalization;
- Dataset;
- metadata;
- validation;
- duplicate detection;
- gap detection;
- checkpoint/resume;
- retry;
- rate limiting;
- recovery.

Запрещено помещать в Loader:

```text
Swing
HH / HL / LH / LL
Structure Break
Mother OB
OBLS
Cascade
Scenario
Setup
Qualification
SETUP_QUALIFIED
торговые решения
Push business logic
TigerTrade execution
```

## 12. Replay

Replay — отдельный модуль. Он обязан:

- читать Dataset потоково;
- выдавать candles детерминированно;
- генерировать `CANDLE_CLOSED`;
- использовать общий Event Model;
- использовать тот же Analysis Engine, что и Live;
- иметь `run_id`;
- фиксировать версии Dataset/Engine/Configuration;
- не допускать look-ahead.

## 13. Event Model

Event Envelope должен поддерживать:

```text
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
payload
```

Для replay `source.type = historical`.
`event_time` — время рыночного события; `processed_at` — время обработки.

## 14. Dataset

Фиксировать:

```text
dataset_id
dataset_version
schema_version
loader_version
engine_version
configuration_version
```

Dataset получает `READY` только после успешной validation. Published Dataset version immutable. Raw и normalized storage разделены.

## 15. Data Integrity

Проверять UTC, timezone-aware timestamps, ordering, OHLC consistency, duplicates, gaps, диапазоны, целостность chunk и checksum, если предусмотрен контрактом.

При gap не продолжать молча. Использовать:

```text
DATA_INTEGRITY_GAP
DATA_RECOVERY_STARTED
DATA_RECOVERY_COMPLETED
```

Recovery данных и восстановление BSS state — разные операции:

```text
Loader → восстанавливает Dataset
State layer → выполняет STATE_REBUILD через Replay
```

## 16. No look-ahead

На момент replay event времени `T` анализатор не получает данные после `T`.

Запрещено использовать future candles, future Dataset для текущего decision, final state вместо state-as-of-time-T и future metadata, влияющую на решение.

## 17. Intrabar ambiguity

Если OHLC не позволяет доказать порядок событий внутри свечи:

```text
НЕ УГАДЫВАТЬ.
```

Явно фиксировать ambiguity, например `INTRABAR_AMBIGUOUS`. Запрещены неоговорённые эвристики вроде `assume favorable order`.

## 18. Open Questions / TBD

Не закрывать самостоятельно открытые вопросы из `Requirements v0.4` и `06_OPEN_QUESTIONS.md`, в частности:

```text
Q-06 — Historical Spread
Q-07 — порядок конфликтующих событий внутри свечи
Q-12 — downstream transport / TigerTrade
Q-13 — historical period и допустимый bid/ask history source
```

Для Q-06/Q-13 использовать abstraction уровня:

```python
class HistoricalSpreadSource:
    def spread_at(self, symbol, timestamp):
        ...
```

Не подставлять текущий spread как исторический.

## 19. Repository

```text
src/bss/
├── domain/
├── event_model/
├── historical_loader/
├── replay/
├── analysis/
├── state/
├── projections/
├── live/
└── application/
```

Не смешивать Loader, Replay и Analysis. Domain не зависит от конкретного HTTP client/API SDK/storage.

## 20. Source abstraction

```python
class HistoricalSource:
    def available_range(self, symbol, timeframe):
        ...

    def download(self, symbol, timeframe, start, end):
        ...
```

Конкретный source adapter можно заменить без изменения Dataset/Replay/Analysis Engine.

## 21. Idempotency / checkpoint / retry

Повторные `download`, `validate`, `recover`, `replay` должны быть безопасными.

Повторная загрузка того же chunk не создаёт duplicates. Checkpoint должен позволять resume. Retry учитывает минимум:

```text
429
5xx
timeout
connection errors
```

Retry и rate limiter — отдельные технические компоненты.

## 22. Time

Все market timestamps — timezone-aware UTC. Не использовать naive datetime.

## 23. Tests

### Unit

- parser;
- normalization;
- validation;
- duplicate detection;
- gap detection;
- checkpoint;
- retry;
- rate limiter;
- metadata;
- replay ordering;
- reducer;
- event schema;
- projection logic.

### Integration

```text
Source
→ Raw
→ Normalized
→ Validation
→ READY
→ Replay
→ CANDLE_CLOSED
→ Analysis Engine
→ Event Stream
```

### Recovery

Проверять interruption, resume, duplicate chunk, corrupted chunk, timeout, 429, 5xx, gap, recovery и повторный replay.

### Determinism

Одинаковые `dataset`, `dataset_version`, `configuration`, `engine_version`, `schema_version` дают одинаковый event stream.

Reducer:

```text
same state + same event
        ==
same resulting state
```

## 24. Код

Предпочитать маленькие классы, явные интерфейсы, dependency injection, типизацию, чистые функции, явные ошибки и детерминированные операции.

Запрещено:

```python
except Exception:
    pass
```

Не логировать secrets/API keys.

## 25. Configuration

Не зашивать в код symbols, даты, endpoints, credentials, retry limits и rate limits. Использовать configuration + environment variables.

## 26. CLI

Минимальный CLI:

```text
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

CLI вызывает application services и не содержит business logic.

## 27. Scope discipline

Без отдельного требования не добавлять:

```text
Kubernetes
Kafka
distributed workers
web UI
ML
LLM
automatic trading
TigerTrade execution
```

Сначала correctness, determinism и tests; потом оптимизация.

## 28. Порядок работы агента

Перед изменением:

1. Прочитать `AGENTS.md`.
2. Прочитать `Requirements v0.4`.
3. Прочитать `Event Model v0.2`.
4. Прочитать релевантные ADR.
5. Прочитать релевантное ЧТЗ.
6. Изучить актуальные C4/Sequence диаграммы.
7. Изучить текущий repository.
8. Найти существующие модели и tests.
9. Сформировать минимальный vertical slice.
10. Реализовать.
11. Добавить tests.
12. Запустить focused tests.
13. Запустить полный suite, если возможно.
14. Проверить diff.
15. Проверить, что реализация не нарушает Accepted ADR.

Не переписывать рабочий код без необходимости. Проверять `pyproject.toml`, README и CI перед выбором команд.

## 29. Изменение архитектуры

Если реализация требует изменения одного из решений:

```text
Immutable Events
File-first MVP Storage
Pure Reducer
Push as Projection
Same Analysis Engine for Live/Replay
SIMPLE Mother OB baseline
```

не обходить ADR изменением кода.

Сначала определить противоречие, затронутый ADR и предлагаемое изменение; получить решение пользователя; обновить ADR; затем менять реализацию.

ADR должен отражать принятое решение, а не предположение агента.

## 30. Диаграммы как архитектурный контракт

`.puml` являются исходниками архитектурных диаграмм.

Перед существенным изменением границ компонентов проверить соответствующие C4/Sequence диаграммы.

Если код меняет архитектурную границу, зависимости или последовательность взаимодействия, соответствующая диаграмма должна быть обновлена в рамках той же задачи, если это входит в scope.

Не создавать PNG вместо исходного `.puml`.

## 31. Финальный отчёт

После задачи сообщить:

1. изменённые файлы;
2. реализованные требования;
3. затронутые ADR;
4. tests;
5. результаты проверок;
6. оставшиеся TBD;
7. архитектурные решения;
8. ограничения/follow-up.

Если изменён архитектурный контракт — явно указать, какой ADR/диаграмма затронуты.

Главный принцип:

```text
Если требование не определено:
не угадывай → abstraction + TBD → сообщи пользователю.

Если решение уже принято в ADR:
не переизобретай → соблюдай ADR.

Если код противоречит ADR:
не маскируй конфликт → остановись и сообщи.
```
