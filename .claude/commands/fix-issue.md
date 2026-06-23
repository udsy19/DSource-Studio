---
description: Investigate and fix an issue end-to-end (reproduce → root-cause → patch → test)
argument-hint: "<issue number, URL, or short description>"
allowed-tools: Bash(git status), Bash(git diff:*), Bash(gh issue view:*), Bash(npm test:*), Bash(pnpm test:*), Bash(uv run pytest:*), Read, Edit, Write, Grep, Glob
---

# /fix-issue

Fix the issue described in `$ARGUMENTS` end-to-end. Don't patch symptoms — find the root cause.

## Input

Issue: **$ARGUMENTS**

If the argument is a number, treat it as a GitHub issue and fetch it:

```!
case "$ARGUMENTS" in
  ''|*[!0-9]*) echo "Not a numeric issue id — skipping gh fetch." ;;
  *) gh issue view "$ARGUMENTS" 2>/dev/null || echo "gh not available or issue not found." ;;
esac
```

## Workflow

1. **Understand the report**
   - Read the issue. Restate the failure in one sentence.
   - Identify the affected subsystem: ingestion / transcription / summarization / action-items / API / UI / storage.

2. **Reproduce**
   - Write a failing test that captures the bug before changing any code (`.claude/rules/testing.md` describes where it goes).
   - If reproduction needs an audio or transcript fixture, use the smallest one that triggers the bug.

3. **Root-cause**
   - Trace the failure to the line that's actually wrong. State the root cause explicitly before patching.
   - If the cause is a prompt regression, check `src/llm/` and look at prompt + schema version.

4. **Fix**
   - Smallest patch that resolves the root cause. No drive-by refactors (see `.claude/rules/code-style.md`).
   - Match existing patterns in the file.

5. **Verify**
   - The failing test from step 2 now passes.
   - Full test suite passes (`npm test` / `pnpm test` / `uv run pytest`).
   - Lint + typecheck clean.

6. **Report**
   - One paragraph: root cause, what changed, why this fix and not another.
   - List the test that now covers the regression.
