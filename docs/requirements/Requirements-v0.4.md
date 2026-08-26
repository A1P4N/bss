# Требования v0.4

**Проект:** Автоматизированный мониторинг структурных сценариев БСС с оповещением и разметкой в TigerTrade  
**Базовая версия:** Requirements v0.3 от 2026-08-18  
**Статус:** Черновик для архитектурного согласования  
**Дата:** 2026-08-23

## 0. Цель документа

v0.4 переводит ТЗ из преимущественно описательного состояния в форму, пригодную для реализации и бэктест. Документ фиксирует:

- функциональные требования;
- ограничения и что не входит в систему;
- архитектурные границы;
- событийную модель / модель состояний;
- требования к воспроизводимости;
- требования к бэктест/replay;
- требования к журналированию;
- допущения и нерешённые вопросы.

Документ **не утверждает автоматически** все решения v0.3. Спорные места явно помечены `TBD`, `ASSUMPTION` или `REJECTED FOR NOW`.

---

# 1. Источник истины и приоритеты

## 1.1. Источники

1. `Trading System.md` — основной источник истины по стратегии.
2. `Corrections_01_20260814.md` — замечания автора стратегии.
3. `ideas/i_01_first.md` — постановка задачи.
4. `ideas/i_02_setup_search.md` — архитектура и интеграция TigerTrade.
5. `ideas/i_03_strategy.md` — стратегия БСС, примеры и статистика.
6. Примеры изображений `ideas/Pasted image 2026*.png` — визуальная валидация.
7. `Requirements_0_4.md` — архитектурная формализация требований.
8. `Событие model_0_2.md` — машинная событийная модель.

## 1.2. Правило разрешения конфликтов

Если архитектурная реализация противоречит исходной стратегии, код не должен «угадывать». Конфликт должен быть зарегистрирован как unresolved question и закрыт через решение владельца стратегии.

---

# 2. Цель системы

Система должна автоматически находить и квалифицировать структурные сценарии БСС, завершившиеся подтверждённым сломом M15, и передавать трейдеру структурное уведомление.

Система **не** принимает торговое решение и **не** исполняет сделки.

Источник и область ответственности закреплены в v0.3: агент определяет сломы, ОБ, ОБЛС, каскад, фильтры, флаги, push и audit log; торговые решения остаются у трейдера.

---

# 3. Термины и сущности

## 3.1. Основные сущности

- `Instrument` — торговый инструмент.
- `Candle` — нормализованная свеча OHLCV.
- `Swing` — подтверждённый экстремум.
- `StructureBreak` — формализованный слом по 4 точкам.
- `MotherOB` — материнская формация/зона.
- `OBLS` — ордер-блок, ломающий структуру.
- `ZoneTest` — факт тестирования зоны с учётом buffer predicate.
- `ZoneDeath` — выход за дальнюю грань материнского ОБ без буфера.
- `Сценарий` — конкретная попытка построения БСС в одном направлении для одного инструмента.
- `CascadeLink` — отношение между сломом на младшем ТФ и зоной старшего ТФ.
- `Сетап` — квалифицированный структурный сценарий, достигший условий M15.
- `Пуш` — транспортное представление `Сетап` для Telegram.
- `Событие` — неизменяемый факт, зарегистрированный системой.

## 3.2. Структурный факт и квалификация

Факт слома и его квалификация не должны смешиваться.

Пример:

- `STRUCTURE_BREAK_CONFIRMED` означает, что слом действительно подтверждён.
- `CASCADE_LINK_VALIDATED` означает, что этот слом связан с ожидаемой старшей зоной.
- `VOLATILITY_PASSED` означает прохождение фильтра 0.3%.
- `SETUP_QUALIFIED` означает право на push.

Это позволяет не превращать детектор в торговый/сигнальный монолит.

---

# 4. Функциональные требования

## FR-01 Рыночные данные

Система должна получать OHLCV и volume по конфигурируемому списку инструментов.

MVP: 5 инструментов.

Целевые ТФ стратегии:

- D1
- H4
- H1
- M15

Для бэктест/replay допускается дополнительный нижний ТФ для разрешения intrabar ambiguity.

### Ограничение

Нельзя использовать как обязательные признаки:

- CVD;
- OI;
- funding;
- order book;
- liquidations;
- FVG;
- imbalance;
- sweep;
- ATR;
- VWAP;
- LLM score.

Они вне текущего scope.

---

# 5. Функциональные требования: структура

## FR-10 Слом структуры по четырём точкам

Для LONG:

- P1 = low;
- P2 = high;
- P3 = higher low относительно P1;
- P4 = extreme выше P2;
- тело свечи, давшей P4, закрывается выше P2.

Для SHORT — зеркально.

Слом является strict event. Buffer к нему не применяется.

## FR-11 Детектор swing

Детектор swing high/low должен быть параметризуемым и детерминированным.

Точные параметры back/front candles являются `TBD`.

## FR-12 HH/HL/LH/LL

Должен существовать отдельный детектор/классификатор экстремумов тренда.

Он не должен самостоятельно квалифицировать setup.

---

# 6. Функциональные требования: материнский ОБ

## FR-20 Материнский ОБ

Система должна поддерживать идентификацию материнской формации.

В v0.4 допускаются два режима детектора:

1. `SIMPLE` — последняя валидная встречная свеча перед импульсом.
2. `SEMANTIC` — формация по маркерам «начало борьбы / утрата инициативы / переворот».

### Архитектурное решение

`SIMPLE` рекомендуется как базовый режим для первой реализации.

`SEMANTIC` остаётся экспериментальным режимом до появления формальной спецификации маркеров.

Причина: v0.3 одновременно описывает semantic-подход и признаёт, что он может быть слишком строгим.

## FR-21 Границы материнского ОБ

Границы формации вычисляются по максимуму high и минимуму low всех свечей формации.

## FR-22 Фильтр волатильности M15

Для M15 width материнской формации должна быть `>= 0.3%` для прохождения фильтра.

Фильтр не применяется к H1/H4/D1.

---

# 7. Функциональные требования: ОБЛС

## FR-30 ОБЛС

OBLS — последняя встречная свеча перед импульсом, сделавшим структурный слом.

Экстремум OBLS является P3.

---

# 8. Функциональные требования: тест зоны и buffer

## FR-40 Тест зоны

Buffer применяется только к предикаты типа «точка–зона».

Buffer не применяется к:

- structural break;
- death of level.

## FR-41 Конфигурация buffer

Baseline параметр:

`2–3 текущий spreads`.

### Архитектурное ограничение

Для бэктест должно существовать явно параметризованное представление buffer:

- `spread_multiple`;
- `fixed_pct`.

Конкретный режим и значение должны быть указаны в конфигурации каждого бэктест run.

Причина: историческая OHLCV-свеча сама по себе не содержит достоверной intrabar bid/ask истории.

---

# 9. Функциональные требования: смерть уровня

## FR-50 Смерть уровня

Zone death:

- происходит при выходе цены за дальнюю грань материнского ОБ;
- buffer не применяется;
- любой тик должен считаться достаточным в боевой режим;
- Telegram notification о death не отправляется.

### Требование к бэктесту

Если исторический источник не содержит intrabar последовательность, результат может быть неоднозначным.

Бэктест обязан уметь маркировать `INTRABAR_AMBIGUOUS` вместо молчаливого угадывания.

---

# 10. Cascade

## FR-60 Cascade

Базовая последовательность:

`D1 -> H4 -> H1 -> M15`

Каждое звено должно иметь собственный результат:

- structural break;
- source zone relation;
- source zone tested/not tested;
- link status.

## FR-61 Incomplete link

Если младший structural break произошёл без теста ожидаемой старшей зоны, structural break не отменяется.

Должен быть создан:

`CASCADE_LINK_INCOMPLETE`

и flag:

`CHAIN_INCOMPLETE`.

## FR-62 Critical clarification required

v0.3 одновременно говорит:

- H4/H1/M15 должны происходить от теста старшей зоны;
- отсутствие теста не отменяет нижний слом;
- старшая зона не обязательна для сигнала.

Поэтому в v0.4 это разделяется на:

`STRUCTURAL_VALIDITY` и `PUSH_ELIGIBILITY`.

**Но окончательная политика eligibility остаётся открытым вопросом Q-01.**

Baseline assumption для реализации: полный qualified cascade требуется для `SETUP_QUALIFIED`.

---

# 11. Сценарий state

Сценарий должен хранить независимые состояния D1/H4/H1/M15.

Рекомендуемый logical state:

```text
CREATED
ACTIVE
QUALIFIED
INVALIDATED
COMPLETED
ARCHIVED
```

Подуровни каскада хранятся отдельно.

Не следует моделировать всю систему одним enum с десятками состояний.

---

# 12. Событие sourcing boundary

Все значимые факты аналитический движок должны регистрироваться как immutable events.

Минимальный envelope:

```json
{
  "event_id": "...",
  "event_type": "...",
  "event_time": "...",
  "processed_at": "...",
  "symbol": "...",
  "timeframe": "M15",
  "direction": "LONG",
  "scenario_id": "...",
  "payload": {}
}
```

Текущее state является производным от событий и может быть сохранён как snapshot для ускорения восстановления.

---

# 13. Требования к бэктесту / replay

## BR-01 Один и тот же движок

Бэктест и боевой режим обязаны использовать один и тот же аналитический движок.

Меняется только источник времени/событий:

- `ReplayDataSource` — исторический;
- `LiveDataSource` — exchange.

## BR-02 Детерминизм

Одинаковый input dataset + одинаковая configuration + одинаковая engine version должны давать одинаковый набор events.

## BR-03 Отсутствие look-ahead

Бэктест не должен использовать данные после момента принятия решения.

## BR-04 Неоднозначность

Intrabar ambiguity должна быть явной, а не скрытой эвристикой.

## BR-05 Эталонный набор

Перед боевой режим вывод в боевой режим должен существовать ручной эталон минимум на 100 кейсах.

Дополнительно желательно иметь отдельные наборы:

- положительные;
- отрицательные;
- неоднозначные;
- граничные случаи.

---

# 14. Audit and observability

Engine должен логировать не только положительные events, но и причины rejection.

Пример:

```text
M15_BREAK_CONFIRMED
VOLATILITY_FAILED
reason=mother_ob_width_pct 0.21 < 0.30
```

Не должно быть «тихих» ветви отклонения для условий, влияющих на setup qualification.

---

# 15. Пуш requirements

Пуш создаётся только после `SETUP_QUALIFIED`.

Пуш должен содержать:

- push_id;
- setup_id;
- scenario_id;
- symbol;
- direction;
- decision timeframe = M15;
- status каждого звена D1/H4/H1/M15;
- IDs структурных объектов;
- M15 mother OB width;
- применённый threshold;
- flags;
- ссылка на график, если transport layer способен её сформировать.

Пуш не должен содержать:

- entry;
- limit;
- stop;
- take profit;
- RR;
- score;
- buy/sell recommendation;
- automated order.

Это должно быть schema-level ограничением.

---

# 16. Trader feedback

Feedback является отдельным потоком событий и не должен изменять структурную truth state.

Минимум:

- `ACCEPTED`;
- `REJECTED`;
- optional код причины;
- свободный текст причины;
- final результат.

---

# 17. Надёжность requirements

## REL-01 Restart safety

После рестарта система должна уметь восстановить current state без генерации duplicate push.

## REL-02 Idempotency

`push_id` и event IDs должны обеспечивать идемпотентную обработку.

## REL-03 Data gap recovery

При разрыве потока система должна:

1. зафиксировать integrity event;
2. восстановить пропущенный диапазон;
3. повторно прогнать affected window;
4. продолжить боевой режим processing.

## REL-04 Reconciliation

После recovery current state должен быть проверен против replay/rebuilt state за affected window.

---

# 18. Storage requirements

Для MVP storage должен поддерживать:

- исторический candles;
- immutable events;
- current snapshots;
- setup/push history;
- feedback.

Требование — не конкретная СУБД, а свойства:

- durable;
- replayable;
- append-friendly;
- inspectable;
- atomic snapshot update;
- deduplication/idempotency.

### Technology decision

Для 5 инструментов допускается file-first MVP:

- CSV/JSONL для истории и events;
- JSON snapshot для state.

SQLite и Parquet не являются обязательными для MVP.

Но решение должно быть заменяемым через storage interface.

---

# 19. Non-функциональные требования

| NFR | Requirement |
|---|---|
| Correctness | deterministic analysis, no look-ahead |
| Надёжность | recovery without duplicate push |
| Auditability | decision/rejection event trail |
| Testability | detector unit tests + scenario tests + replay tests |
| Reproducibility | versioned dataset + config + engine version |
| Extensibility | pluggable detectors/data source/storage/transport |
| Safety | no trading API, no order execution |
| Performance | real-time for MVP load; exact latency target TBD |

---

# 20. Explicit что не входит в систему

В текущем релизе не реализуются:

- автоматическая торговля;
- ML/CV recognition;
- scoring;
- adaptive strategy optimization inside боевой режим engine;
- execution levels;
- stop/TP recommendation;
- order book analytics;
- funding/OI/CVD.

---

# 21. Architecture decisions requiring alternatives

## ADR-01 State handling

### Option A — mutable state only
Сложность: Low  
Стоимость: Low  
Масштабируемость: Medium-Low  
Надёжность: Medium-Low  
Операционная нагрузка: Low

Weakness: poor replay/debugging; difficult recovery correctness.

### Option B — immutable events + derived state (**recommended**)
Сложность: Medium  
Стоимость: Low-Medium  
Масштабируемость: High  
Надёжность: High  
Операционная нагрузка: Medium

Benefit: replay, audit, deterministic recovery.

### Option C — full event sourcing framework
Сложность: High  
Стоимость: Medium-High  
Масштабируемость: High  
Надёжность: High  
Операционная нагрузка: High

Not justified for MVP.

---

## ADR-02 Storage

### Option A — files only (**acceptable MVP**)
Сложность: Low  
Стоимость: Very Low  
Масштабируемость: Low-Medium  
Надёжность: Medium if append + atomic snapshots are implemented correctly  
Операционная нагрузка: Low

### Option B — SQLite
Сложность: Low-Medium  
Стоимость: Low  
Масштабируемость: Medium  
Надёжность: High for local single-node transactional state  
Операционная нагрузка: Low

### Option C — Parquet + separate event store
Сложность: Medium  
Стоимость: Low-Medium  
Масштабируемость: High for analytics  
Надёжность: High for immutable исторический datasets  
Операционная нагрузка: Medium

Recommendation: files for MVP, migration path to SQLite + Parquet if analytics/history grows.

---

## ADR-03 Live-to-TigerTrade transport

### Option A — JSON files
Сложность: Low  
Стоимость: Low  
Масштабируемость: Low  
Надёжность: Medium  
Операционная нагрузка: Low

### Option B — local HTTP
Сложность: Low-Medium  
Стоимость: Low  
Масштабируемость: Medium  
Надёжность: High  
Операционная нагрузка: Low

### Option C — local WebSocket
Сложность: Medium  
Стоимость: Low  
Масштабируемость: Medium-High  
Надёжность: High when reconnect/idempotency are implemented  
Операционная нагрузка: Medium

DoD for this decision is postponed until TigerTrade API constraints are verified.

---

# 22. Assumptions

A-01. M15 is the final decision timeframe.

A-02. Structural break confirmation is based on closed candles.

A-03. Live zone death may use tick/intrabar data; исторический ambiguity is explicit.

A-04. Analysis engine is deterministic and contains no LLM.

A-05. Сетап/push is not an order signal in the execution sense.

A-06. One scenario is directional: LONG and SHORT are independent state machines.

A-07. Same аналитический движок is used in бэктест and боевой режим.

A-08. The 0.3% filter is retained as a strategy parameter but its economic rationale is not implemented as trading logic.

A-09. Mother OB semantic rules are not yet precise enough for final acceptance; SIMPLE detector is базовый режим.

---

# 23. Open Questions

## Q-01 Cascade qualification

Does a completed M15 push require every higher-level cascade link to have a tested source zone, or can a structurally complete M15 chain still push with `CHAIN_INCOMPLETE`?

### Ответ

При определении сломов на M15 использовать правило буфера. Валидный слом на M15 по четырём точкам может произойти без чистого теста ордер-блоков старшего таймфрейма. 

## Q-02 Swing definition

What exact front/back candle parameters define a confirmed swing on each timeframe?

### Ответ

Использование свингов перенести на будущее.

## Q-03 Mother OB

What exact machine предикаты define `start of struggle`, `loss of initiative`, and `reversal`?

### Ответ

В первой версии Система должна поддерживать идентификацию материнской формации  только `SIMPLE` — последняя валидная встречная свеча перед импульсом. Где под словом `валидная` понимается - свеча, на примере бычьей, закрытие которой произошло выше середины диапазона от low до high. Для шорта зеркально. 

## Q-04 OBLS

What exactly counts as the "last opposing candle" if several consecutive opposing candles precede the impulse?

### Ответ

Последняя валидная свеча перед импульсом.

## Q-05 Test

Does a test occur intrabar, on wick touch, or only after candle close? Is first touch enough?

### Ответ

Оба варианта.

## Q-06 Buffer

Which exact value is used initially: 2x, 3x, or a calibrated value? Which исторический spread source is authoritative?

### Ответ

в файле конфигурации с последующей калибровкой TBD

## Q-07 Same-candle conflicts

If a candle crosses death level and later reaches a test boundary, which event wins for strategy state?

### Ответ

побеждает смерть.

## Q-08 Multiple concurrent scenarios

Can multiple LONG/HIGH-level scenarios for the same symbol coexist, or is only the most recent one retained?

### Ответ

Нет, не может.

## Q-09 Сценарий reset

After death on H1, should all lower-timeframe objects be deleted immediately or retained in audit/history only?

### Ответ

Удаляй сразу.

## Q-10 News flag

What exact source and timestamp semantics qualify as "red news nearby"?

### Ответ

TBD

## Q-11 Пуш deduplication

What constitutes the same setup if the engine restarts or the same M15 bar is reprocessed?

### Ответ

Вопрос не понятен. Переформулируй на русском языке

## Q-12 TigerTrade contract

What exact API/object model and transport mechanisms are available in the target TigerTrade version?

### Ответ

Тебе необходимо изучить документацию из открытых источников.

## Q-13 Исторический data

What period is required for the first бэктест and what is the acceptable source of bid/ask history?

### Ответ

временной промежуток должен настраиваться через конфигурационный файл. источник Binance.

## Q-14 Acceptance

How many examples are required before the system is trusted for shadow/боевой режим monitoring: 100, 300, or another number?

### Ответ

300

---

# 24. Acceptance strategy

The project should not move directly from unit tests to боевой режим push.

Required gates:

1. detector golden tests;
2. cascade scenario tests;
3. исторический replay;
4. ambiguity report;
5. manual comparison;
6. shadow боевой режим mode without Telegram push;
7. Telegram push in controlled mode;
8. TigerTrade integration.

---

# 25. Рекомендуемое implementation order

```text
1. Freeze unresolved business rules
2. Define Событие Model
3. Define normalized Candle model
4. Build replay engine
5. Implement swing detector
6. Implement 4-point break detector
7. Implement Mother OB базовый режим
8. Implement OBLS
9. Implement zone test / death
10. Implement cascade reducer/state machine
11. Implement deterministic бэктест
12. Build visual regression set
13. Add боевой режим market adapter
14. Add persistence/recovery
15. Add Telegram
16. Add TigerTrade
```

---

# 26. Design principle

The central architecture rule is:

> **Событиеs are facts; state is derived; push is a derived projection.**

Бэктест, боевой режим monitoring and replay/debugging must consume the same analysis/event engine.
