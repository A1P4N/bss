# ADR-006 — SIMPLE Mother OB как базовый режим

- **Статус:** Accepted for MVP
- **Дата:** 2026-08-23
- **Область:** Strategy Detector / Mother OB
- **Источник:** Architecture Decisions v0.1, Requirements v0.4, Code Agent Prompts v0.1

## Контекст

Mother OB является частью BSS structural analysis. При этом Requirements v0.4 фиксирует открытые вопросы относительно точных машинных предикатов Mother OB, включая понятия `start of struggle`, `loss of initiative` и `reversal`.

Полностью semantic определение недостаточно формализовано для однозначного acceptance.

## Решение

В MVP сначала реализуется **SIMPLE Mother OB** как детерминированный базовый режим.

`SEMANTIC` сохраняется как отдельно тестируемый strategy mode и не должен становиться неявной эвристикой.

Архитектурно:

```text
MotherOBDetector
    ├── SIMPLE
    └── SEMANTIC
```

SIMPLE является default для MVP, пока semantic predicates не будут формально утверждены.

## Ограничение решения

Точное машинное правило выбора Mother OB должно соответствовать актуально утверждённому определению.

Если правило неоднозначно:

```text
не угадывать
    ↓
изолировать ambiguity
    ↓
TBD / Open Question
```

Нельзя добавлять undocumented heuristic только для прохождения теста.

## Альтернативы

### Semantic-only

Плюс: ближе к концептуальному описанию стратегии.

Минус: высокая неоднозначность и слабая воспроизводимость acceptance.

### Simple-only

Плюс: высокая детерминированность.

Минус: может не покрывать более сложные формирования.

### Dual-mode с SIMPLE default

Выбрано.

## Последствия

### Положительные

- deterministic MVP;
- возможность golden tests;
- возможность сравнения SIMPLE и SEMANTIC;
- постепенное уточнение стратегии;
- отсутствие скрытой эвристики.

### Отрицательные

- два strategy mode требуют отдельного тестирования;
- SIMPLE может временно быть менее выразительным.

## Требования к тестам

Для SIMPLE режима нужны:

- positive cases;
- negative cases;
- boundary cases;
- ambiguous cases;
- audit evidence, объясняющее выбор Mother OB.

SEMANTIC mode не должен использоваться как production default до формализации его предикатов.

## Связанные вопросы

Решение не закрывает открытые вопросы стратегии, включая точное определение Mother OB и другие TBD из Requirements v0.4.
