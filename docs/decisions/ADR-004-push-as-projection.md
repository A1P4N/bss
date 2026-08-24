# ADR-004 — Push как Derived Projection

- **Статус:** Accepted
- **Дата:** 2026-08-23
- **Область:** Qualification / Push / External Transport
- **Источник:** Architecture Decisions v0.1, Event Model v0.2, Requirements v0.4

## Контекст

BSS должен формировать уведомления о квалифицированных setup, но Push не является частью структурного детектора.

Event Model v0.2 явно определяет Push как derived projection.

`SETUP_QUALIFIED` также является derived event, а не raw market fact.

## Решение

Push реализуется как отдельная projection layer:

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

Detector не должен напрямую вызывать Telegram, TigerTrade или другой внешний transport.

## Push schema

Push должен ссылаться на исходные идентификаторы и содержать необходимые для аудита сведения о setup/cascade.

При этом Push schema не должна содержать execution semantics:

```text
entry
limit
stop
take_profit
rr
score
recommendation
order
position
```

## Delivery state

```text
NOT_CREATED
    ↓
CREATED
    ├──> SEND_FAILED
    ↓
SENT
```

Повторная отправка должна быть идемпотентной.

`PUSH_SENT` не должен повторно создавать `SETUP_QUALIFIED`.

## Альтернативы

### Detector → Telegram

Просто для прототипа, но создаёт сильную связанность и мешает replay.

### Application service → transport

Лучше, но всё ещё смешивает qualification и delivery.

### Projection + transport adapter

Выбрано.

## Последствия

### Положительные

- detector остаётся чистым;
- Push можно тестировать отдельно;
- transport можно заменить;
- replay не вызывает реальные внешние отправки;
- delivery failures не изменяют structural state.

### Отрицательные

- появляется дополнительный слой;
- требуется idempotency/deduplication.

## Правило

```text
Qualification ≠ Delivery
```

Факт того, что setup квалифицирован, не должен зависеть от успешности внешней доставки.
