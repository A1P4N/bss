# ADR-005 — Один Analysis Engine для Live и Replay

- **Статус:** Accepted
- **Дата:** 2026-08-23
- **Область:** Analysis / Replay / Live
- **Источник:** Architecture Decisions v0.1, Requirements v0.4, ЧТЗ Historical Data Loader

## Контекст

Ключевое требование BSS — исторический replay должен воспроизводить поведение боевого анализа, а не отдельную «backtest версию» алгоритма.

Requirements v0.4 и ЧТЗ Loader фиксируют единый Analysis Engine с различными источниками данных.

## Решение

Использовать один Analysis Engine:

```text
Historical Dataset
       ↓
ReplayDataSource
       ↓
Analysis Engine
       ↓
Event Stream
```

и:

```text
Live Market Data
       ↓
LiveDataSource
       ↓
Analysis Engine
       ↓
Event Stream
```

Различаться должны только input adapters и особенности инфраструктурной доставки данных.

## Архитектурное правило

```text
Loader ≠ Replay ≠ Analysis Engine
```

Loader отвечает за подготовку исторического Dataset.

Replay отвечает за детерминированную подачу Dataset.

Analysis Engine отвечает за BSS analysis.

## Альтернативы

### Отдельный backtest engine

Быстрее для прототипа, но создаёт высокий риск divergence между backtest и live.

### Один engine + два input adapters

Выбрано.

### Общая библиотека + отдельные процессы

Возможна позже, но для MVP не требуется.

## Последствия

### Положительные

- одинаковые business rules;
- меньше дублирования;
- replay становится regression mechanism;
- проще сравнивать live/replay;
- снижается риск расхождения алгоритмов.

### Отрицательные

- Analysis Engine должен быть чистым от специфики источника;
- нужно строго разделять market-time и processing-time;
- intrabar/live особенности требуют явных input contracts.

## Reproducibility

Replay должен быть определён комбинацией:

```text
dataset_id
dataset_version
configuration_version
engine_version
schema_version
```

При изменении любой составляющей создаётся новый replay run.

## No look-ahead

Replay не должен предоставлять Analysis Engine данные после текущего `event_time`.

## Проверка

Для одного Dataset и одинаковых версий:

```text
Run A event stream == Run B event stream
```

по крайней мере на уровне определённых acceptance criteria для event type, event_time, identifiers и payload.
