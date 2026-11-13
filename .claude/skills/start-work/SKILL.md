---
name: start-work
description: Start any CompetenceMatch implementation task. Reads architecture.md and docs/tasks specs first, then builds with lean-build reuse rules.
---

# Start work (CompetenceMatch)

Use at the start of every implementation task in this repo.

## 1. Read specs in order

1. `architecture.md` — components, data ownership, state transitions, user flow.
2. `docs/tasks/MATH_SPEC.md` — canonical algorithms, edge cases, ranking rules.
3. `docs/tasks/IMPLEMENTATION_SPEC.md` — work packages, APIs, persistence, quality gates.
4. `docs/tasks/CLAUDE_PROMPT.md` — execution instructions.
5. `README.md`, then the relevant code in `app/backend/` and `app/frontend/`.

Do not start coding before the spec for the touched area is read.

## 2. Scope

- State observable acceptance and non-goals from the request and specs.
- Name the work package in `IMPLEMENTATION_SPEC.md` the task belongs to.

## 3. Build with lean-build

Invoke `caveman:lean-build` before editing. Apply its rules:
- trace the entry point through the layers that own the invariants;
- reuse the existing seam; refactor only when patching would duplicate behavior or hide the root cause;
- no extra modes, config, or extensibility beyond acceptance.

## 4. Verify

- Run focused tests (Python: `app/tests`; TypeScript: typecheck and build in `app/frontend`).
- Record exact commands and real outcomes. Disclose anything not run (Docker, browser, provider).
- Never edit the thesis DOCX files.
