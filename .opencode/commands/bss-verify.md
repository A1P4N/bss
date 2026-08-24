---
description: Verify BSS implementation
agent: bss-tester
subtask: true
---

Verify: $ARGUMENTS

Check:
- focused tests;
- full test suite when practical;
- configured lint/type checks;
- deterministic replay;
- no look-ahead;
- UTC;
- idempotency;
- recovery;
- event envelope.

Do not modify files.
