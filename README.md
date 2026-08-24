# BSS OpenCode Ready Package

Copy to the BSS repository root:

```text
BSS/
├── AGENTS.md
├── opencode.json
└── .opencode/
    └── commands/
        ├── bss-start.md
        └── bss-verify.md
```

Available commands:

```text
/bss-plan <task>
/bss-implement <task>
/bss-review
/bss-test <task>
/bss-start <task>
/bss-verify <task>
```

The model is intentionally not hard-coded: OpenCode uses the model/provider configured in the user's environment.
