# BSS --- пакет постановки задачи Coding Agent

## Назначение

Этот каталог содержит нормативные материалы для реализации MVP проекта
BSS Structural Monitoring Agent, с отдельным фокусом на
`Historical Data Loader` и `Replay`.

## Порядок чтения

Coding Agent должен читать документы в следующем порядке:

1.  `01_CHТЗ_Historical_Data_Loader.md` --- основное частное техническое
    задание.
2.  `02_ARCHITECTURE.md` --- архитектурные границы и взаимодействия.
3.  `03_REPOSITORY_STRUCTURE.md` --- целевая структура репозитория.
4.  `04_IMPLEMENTATION_PLAN.md` --- порядок реализации.
5.  `05_ACCEPTANCE_CRITERIA.md` --- критерии приёмки.
6.  `06_OPEN_QUESTIONS.md` --- нерешённые вопросы и запреты на
    самовольную интерпретацию.
7.  `07_CODING_AGENT_TASK.md` --- непосредственная постановка задачи
    агенту.
8.  `08_CODING_AGENT_RULES.md` --- правила работы агента.

## Главный принцип

``` text
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
Immutable Event Stream
      ↓
State / Audit / Push Projection
```

`Historical Data Loader` не реализует BSS-аналитику.

## Источники требований

-   Requirements v0.4
-   Event Model v0.2
-   результаты обсуждения архитектуры и структуры репозитория

Если требование не определено однозначно, Coding Agent не должен
придумывать бизнес-правило. Неоднозначность фиксируется как `TBD` /
`Open Question`.
