---
description: Review the current diff for correctness, style, security, and missing tests
argument-hint: "[focus area, e.g. 'auth' or 'transcription pipeline']"
allowed-tools: Bash(git status), Bash(git diff:*), Bash(git log:*), Bash(rg:*), Read, Grep, Glob
---

# /review

Review the pending changes on this branch. If `$ARGUMENTS` names a focus area, weight the review toward those files; otherwise review the full diff.

## Current diff

!`git status --short`

!`git diff --stat`

!`git diff HEAD`

## Review process

1. **Read the diff above.** Don't open files unless you need surrounding context the diff doesn't show.
2. **Check against project rules:**
   - `.claude/rules/code-style.md` for naming, formatting, comment hygiene
   - `.claude/rules/testing.md` for test coverage and structure
   - `.claude/rules/api-conventions.md` for HTTP + Claude API usage
3. **Look for these categories of issues, in order:**
   - **Bloat (highest priority)**: duplicate implementations, parallel files (`foo_v2.ts`), dead code, premature abstractions, scope creep, file proliferation. Apply `.claude/rules/no-bloat.md`. For each new symbol introduced in the diff, run `rg -i <name>` to confirm an equivalent doesn't already exist.
   - **Correctness**: logic errors, off-by-one, wrong types, missing await/error handling
   - **Security**: secrets in code, missing input validation, PII leaks (we're a transcript product — be paranoid here)
   - **Tests**: regressions, missing coverage for new branches, mocks where we should use fixtures
   - **Style**: only the things that materially affect readability — skip nits
4. **If the diff touches `src/llm/`**, also check: prompt safety, schema validation, retry policy, model-id correctness.
5. **Diff shape check**: count lines added vs deleted, files added vs deleted. A `+N -0` diff for a non-greenfield task is suspicious — call it out.

## Output format

A single punch list, no preamble:

```
SEVERITY | file:line | issue | suggested fix
```

`SEVERITY` is one of `block | major | minor | nit`. End with one line stating whether the diff is mergeable as-is or needs changes.

Focus area: $ARGUMENTS
