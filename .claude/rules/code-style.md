---
description: Code style conventions for Glance — formatting, naming, comments, error handling
---

# Code Style

Conventions for all code in this repo. Loaded on every session.

## Naming

- **Identifiers describe intent, not type.** `transcript`, not `transcriptString`. `meetings`, not `meetingArray`.
- **Functions are verbs.** `summarizeMeeting`, `extractActionItems`, `redactPii`.
- **Booleans read as predicates.** `isFinalized`, `hasTranscript`, `canEdit`.
- **Avoid filler.** No `Helper`, `Util`, `Manager`, `Handler` suffixes unless the module's whole purpose is dispatch.

## Formatting

- TypeScript / JavaScript: 2-space indent, single quotes, trailing commas — defer to Prettier.
- Python: 4-space indent, double quotes — defer to Ruff format.
- One blank line between logical groups; no double blank lines.

## Functions

- One job per function. If you can't name it in 4 words, split it.
- Prefer pure functions in `src/core/` — side effects live in `src/pipelines/` and `src/api/`.
- Early-return for guard clauses; avoid deep nesting.

## Comments

- Default to **none**.
- Add a comment only when the *why* is non-obvious: a hidden constraint, a subtle invariant, a workaround for a specific bug.
- Never explain *what* the code does — well-named code already does that.
- Never leave `// TODO` without an owner and a date.
- Never leave `// removed for X` or revision-history comments; that's what `git log` is for.

## Error handling

- **At boundaries (HTTP, queue consumers, external APIs)**: catch, log structured, return the project's error shape.
- **Inside `src/core/`**: let exceptions propagate. Don't wrap-and-rethrow without adding information.
- **Never swallow.** No `try { ... } catch {}`. If you really mean "ignore," explain why in one line.
- **No defensive checks for things the type system already guarantees.** Trust internal callers.

## Imports

- Absolute imports from `src/` root (e.g. `import { Transcript } from 'src/core/transcript'`).
- Group: stdlib → third-party → first-party → relative. One blank line between groups.

## Files

- One primary export per file. Co-locate small helpers; extract once they're reused.
- Test files: `foo.ts` → `foo.test.ts` next to it (see `testing.md`).

## What not to do

- Don't add abstractions for a single caller. Three similar lines is fine; a premature `BaseHandler` is not.
- Don't add feature flags or back-compat shims when you can just change the code.
- Don't rename unused variables to `_var`. Delete them.
- Don't introduce new dependencies without a clear reason — the standard library covers most needs.
