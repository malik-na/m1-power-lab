# Domain docs

This repository uses a single domain context.

## Before exploring

Read these sources when they exist and are relevant:

- `CONTEXT.md` at the repository root.
- Architecture decision records under `docs/adr/`.

If they do not exist, proceed without treating their absence as a problem. The domain-modeling workflow creates them when the project resolves terms or architectural decisions that need a durable record.

## Layout

```text
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Vocabulary

Use the terms defined in `CONTEXT.md` in issues, implementation plans, hypotheses, and code. Avoid introducing synonyms for concepts that the glossary names explicitly. If a needed concept is absent, reconsider whether it is project terminology or record the gap for domain modeling.

## ADR conflicts

Surface any proposal that contradicts an existing ADR and name the ADR. Do not silently override a recorded decision.
