---
description: Testing conventions for Glance — structure, fixtures, what to mock vs not
---

# Testing

How we write and run tests in this repo. Loaded on every session.

## Principles

1. **Every bug fix gets a regression test.** Write the failing test before the fix.
2. **Test behavior, not implementation.** If you'd have to rewrite the test when refactoring without changing behavior, the test is too coupled.
3. **Tests must be deterministic.** No real time, no random ordering, no network unless explicitly an integration test.
4. **Don't mock the LLM or transcription provider in integration tests.** Use recorded fixtures (VCR-style cassettes). Mocks lie; cassettes catch real API drift.

## Layout

```
tests/
├── unit/           Mirrors src/. Fast (< 10ms each). No I/O.
│   ├── core/
│   ├── llm/
│   └── pipelines/
├── integration/    Real Postgres, real S3-compatible store, recorded LLM/STT fixtures.
└── e2e/            Browser-level (Playwright) for the UI flows.
```

Unit tests sit next to source for tight feedback loops where it makes sense (`foo.ts` ↔ `foo.test.ts`). Cross-module integration tests live under `tests/integration/`.

## Fixtures

- Audio fixtures: small clips checked into `tests/fixtures/audio/` (< 30s each).
- Transcript fixtures: JSON in `tests/fixtures/transcripts/`.
- LLM cassettes: `tests/fixtures/llm-cassettes/`. Re-record with `RECORD=1` when prompts change — review the diff carefully before committing.

## What to mock and not

| Boundary | Unit tests | Integration tests |
|----------|------------|-------------------|
| Postgres | in-memory or testcontainers | real (testcontainers) |
| S3 / object store | in-memory adapter | real (minio in CI) |
| Claude API | mock with fixed responses | cassette (recorded real responses) |
| Transcription API | mock | cassette |
| HTTP egress (anything else) | mock | mock — we don't want external flakiness |

## Naming

- `describe('summarizeMeeting')` → `it('returns one bullet per decision')`.
- One assertion per test where possible. Multiple is fine when they verify the same behavior.
- Failure messages must point to the bug: assert on the value, not on a boolean derived from it.

## Running

| Task | Command |
|------|---------|
| Full suite | `npm test` |
| Watch | `npm test -- --watch` |
| Single file | `npm test -- tests/unit/core/transcript.test.ts` |
| Integration only | `npm run test:integration` |
| With coverage | `npm run test:coverage` |
| Re-record LLM cassettes | `RECORD=1 npm run test:integration` |

## Before declaring "done"

1. New test exists and **fails before** your change.
2. New test **passes after** your change.
3. Full suite passes locally.
4. Lint + typecheck clean.

If you couldn't write a test for the fix, say so explicitly — don't claim coverage you don't have.
