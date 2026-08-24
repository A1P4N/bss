# ADR-001 — Immutable Events + Derived State

- **Статус:** Accepted
- **Дата:** 2026-08-23
- **Область:** Event Model / State / Replay
- **Источник:** Architecture Decisions v0.1, Requirements v0.4, Event Model v0.2

## Контекст

BSS требует аудируемость, воспроизводимый replay/backtest, согласованность live и historical режимов и корректное восстановление после перезапуска.

Event Model v0.2 устанавливает базовое правило:

> Event = immutable fact. State = current interpretation of events. Push = derived projection.

Requirements v0.4 также рекомендует immutable events + derived state как основу для replay, audit и deterministic recovery.

## Решение

Канонической историей анализа являются **неизменяемые события**.

Текущее состояние сценария вычисляется как результат reducer:

```text
reduce(state, event) -> state'
```

Допускается сохранять snapshots состояния для ускорения восстановления, но snapshot не заменяет event history.

События после создания не изменяются.

Минимальный Event Envelope включает:

```text
event_id
event_type
schema_version
event_time
processed_at
symbol
timeframe
direction
scenario_id
source
payload
```

`event_time` — время рыночного события, `processed_at` — время обработки.

## Последствия

### Положительные

- детерминированный replay;
- audit trail;
- возможность STATE_REBUILD;
- воспроизводимость состояния;
- возможность сравнения двух replay run;
- отсутствие необходимости в полном event-sourcing framework для MVP.

### Отрицательные

- event storage сложнее mutable state;
- требуется versioning схемы;
- требуется идемпотентная обработка событий.

## Не входит в решение

Не вводится полноценная event-sourcing платформа, distributed event broker или Kafka в MVP.

## Проверка

Acceptance должна подтверждать:

1. события immutable;
2. одинаковая последовательность событий даёт одинаковое состояние;
3. повторная обработка не создаёт дублирующих business effects;
4. состояние может быть восстановлено через replay.
