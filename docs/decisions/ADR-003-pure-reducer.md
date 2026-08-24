# ADR-003 — Pure Reducer для State Transitions

- **Статус:** Accepted
- **Дата:** 2026-08-23
- **Область:** State / Scenario / Replay
- **Источник:** Architecture Decisions v0.1, Event Model v0.2

## Контекст

Scenario State изменяется в ответ на события. Для replay и восстановления необходимо гарантировать одинаковый результат при одинаковой истории событий.

Event Model определяет State как текущую интерпретацию событий.

## Решение

State transitions реализуются через чистую функцию:

```text
reduce(state, event) -> state'
```

Reducer:

- не выполняет I/O;
- не обращается к сети;
- не отправляет Push;
- не изменяет Event;
- не зависит от wall-clock;
- не содержит случайности;
- должен быть детерминированным.

Все необходимые данные для перехода должны находиться в `state` и `event`.

## Пример

```text
Event:
STRUCTURE_BREAK_CONFIRMED

        ↓

reduce(previous_state, event)

        ↓

new_state
```

## Альтернативы

### Mutable object methods

Проще начать, но сложнее гарантировать replayability и тестируемость.

### State-machine framework

Даёт дополнительную формализацию, но для MVP создаёт неоправданную зависимость и сложность.

## Последствия

### Положительные

- детерминизм;
- простые unit tests;
- replayability;
- возможность STATE_REBUILD;
- отсутствие side effects;
- проще проводить differential testing.

### Отрицательные

- необходимо явно передавать состояние;
- некоторые операции требуют больше кода;
- immutable/копируемые структуры могут увеличить стоимость операций.

## Правило

Business state не должен изменяться напрямую внешними сервисами.

```text
Event
 ↓
Reducer
 ↓
State
```

а не:

```text
Service
 ↓
mutate State
```

## Проверка

Тесты должны подтверждать:

```text
same state + same event
        ==
same resulting state
```

и повторный replay одной истории должен давать идентичный результат.
