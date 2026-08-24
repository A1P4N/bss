# ADR-002 — File-first Storage для MVP

- **Статус:** Accepted
- **Дата:** 2026-08-23
- **Область:** Storage / Historical Data / Events / State
- **Источник:** Architecture Decisions v0.1, Requirements v0.4, ЧТЗ Historical Data Loader

## Контекст

Для MVP целевой масштаб — порядка пяти инструментов. На этом этапе основной риск проекта связан с корректностью, воспроизводимостью и тестируемостью, а не с объёмом данных.

Requirements v0.4 прямо допускает file-first MVP и требует сохранять возможность замены storage через интерфейсы.

## Решение

В MVP используется **file-first storage**.

Допустимые форматы:

```text
CSV / JSONL — исторические данные и events
JSON snapshot — state snapshots
Parquet — при необходимости для крупных аналитических datasets
```

Для append-friendly event stream предпочтителен JSONL.

Рекомендуемая структура:

```text
data/
├── raw/
├── normalized/
├── metadata/
├── checkpoints/
├── validation/
└── events/
    └── replay/
```

Storage должен быть скрыт за интерфейсами.

Например:

```python
class DatasetStorage:
    ...

class EventStorage:
    ...

class StateSnapshotStorage:
    ...
```

## Требования к реализации

File-first не означает «просто писать файлы».

Необходимы:

- append semantics;
- atomic snapshots;
- idempotency;
- dataset versioning;
- metadata;
- validation;
- безопасное завершение записи;
- возможность resume/recovery.

Replay разрешён только для Dataset со статусом `READY`, если иное явно не предусмотрено контрактом.

## Альтернативы

### SQLite

Плюсы: транзакционность, удобный локальный state store.

Минусы: для immutable historical datasets не даёт существенного преимущества на текущем масштабе.

### Parquet + отдельное хранилище событий

Плюсы: хорошо подходит для больших аналитических datasets.

Минусы: дополнительная сложность для MVP.

### Полноценная DB/event store

Плюсы: масштабирование и развитые query capabilities.

Минусы: преждевременная инфраструктурная сложность.

## Последствия

### Положительные

- минимальная инфраструктура;
- простой локальный запуск;
- удобный audit;
- удобный обмен Dataset;
- простая диагностика;
- низкая стоимость MVP.

### Отрицательные

- необходимо самостоятельно обеспечить atomicity/idempotency;
- ограниченные возможности concurrent access;
- при росте Dataset может потребоваться миграция.

## Migration path

Storage API не должен зависеть от файлового формата.

При росте проекта можно заменить реализацию:

```text
FileStorage
   ↓
SQLite / Parquet / Event Store
```

без изменения domain и Analysis Engine.
