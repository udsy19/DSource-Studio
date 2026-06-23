---
name: pre-edit-scan
description: Run BEFORE writing new code to check whether equivalent code already exists. Surfaces existing helpers, types, prompts, routes, and tests that the new code might duplicate. Use proactively whenever the task involves adding a function, class, type, prompt, file, or endpoint — especially in src/llm/, src/core/, and src/api/. Required by .claude/rules/no-bloat.md.
when_to_use: "Trigger when the user asks to add/create/implement/build X — and before any new Write or Edit that introduces a new symbol. Also trigger on phrases: 'add a helper', 'create a util', 'new endpoint', 'add a prompt', 'extract this into', 'wrap this in a function'."
allowed-tools: Bash(rg:*), Bash(ls:*), Bash(find:*), Bash(ast-grep:*), Read, Grep, Glob
---

# Pre-Edit Scan

Before writing new code, prove the code doesn't already exist. This skill is the operational form of `.claude/rules/no-bloat.md`'s "search before write" rule.

## When to run it

Run this **before** any of these actions:

- Adding a new function, class, method, or React component
- Adding a new type, interface, or schema
- Adding a new file
- Adding a new API endpoint or route
- Adding a new prompt or tool schema in `src/llm/`
- Adding a new test helper or fixture

Do **not** run it for trivial edits inside one function, renames, or pure deletions.

## Inputs you need

Before scanning, write down (in one line each):

1. **The concept** — e.g. "redact emails from transcript text"
2. **3–5 plausible names** an existing implementation could have — e.g. `redactEmails`, `scrubPii`, `cleanTranscript`, `sanitizeText`
3. **A distinctive string** the existing code would contain — e.g. a regex literal `\b[\w.-]+@[\w.-]+\b`, an error message, a field name
4. **The likely directory** — e.g. `src/core/transcript/`, `src/llm/prompts/`

## The scan

Run these in order. Stop as soon as you have a clear answer.

### 1. Name search

```!
echo "=== Name search ==="
for term in redactEmails scrubPii cleanTranscript sanitizeText; do
  echo "--- $term ---"
  rg -i --type-add 'src:*.{ts,tsx,js,jsx,py}' --type src "$term" src/ tests/ 2>/dev/null | head -5
done
```

(Replace the loop terms with *your* candidate names from step 2 above.)

### 2. Behavior search

Grep for distinctive strings the existing code would contain. Examples:

```!
echo "=== Behavior search ==="
# regex literal, error message, key field — pick what's distinctive for THIS task
rg -n '@' src/core/transcript/ src/core/redact/ 2>/dev/null | head -10
```

### 3. Structural search (when applicable)

If your task is a *shape* — "an async function that takes a transcript and returns a redacted transcript" — use `ast-grep` to find functions of that shape. Name doesn't matter; signature does.

```!
echo "=== Structural search (skip if ast-grep not installed) ==="
command -v ast-grep >/dev/null && ast-grep --lang ts -p 'async function $NAME($_: Transcript): Promise<Transcript> { $$ }' src/ 2>/dev/null | head -20 || echo "(ast-grep not installed — skip)"
```

### 4. Type/schema search

If you're adding a type, search for the field names you'd use:

```!
echo "=== Type/schema search ==="
rg -n 'interface |type ' src/ | rg -i '<concept>' | head -10
```

### 5. Neighbor read

List files in the target directory so you match local patterns:

```!
echo "=== Neighbor files ==="
ls src/core/transcript/ 2>/dev/null
ls src/llm/prompts/ 2>/dev/null
```

Pick one and read it before writing anything new.

## Decide

After scanning, classify the situation into exactly one of:

| Outcome | What to do |
|---------|------------|
| **Exact match exists** | Use it. Do not write new code. |
| **Close match exists** | Extend the existing function/file. Add a parameter, broaden the type, or add a small variant *inside* the same file. |
| **Related concept exists nearby** | Put the new code in the same file or directory and match its patterns. |
| **Nothing similar exists** | Write new. State this explicitly: _"No existing implementation. Creating new at `<path>`."_ |

State the decision in one line before any Write/Edit:

```
Scan result: <exact-match|close-match|related|none>. Action: <reuse <symbol>|extend <symbol>|add to <file>|create new at <path>>.
```

## What to do when you find a near-duplicate

If the scan finds something close-but-not-identical:

1. Read the existing implementation.
2. Ask: can I make it satisfy both callers by adding a parameter or relaxing a type?
3. If yes — modify it. Update existing callers in the same change.
4. If no — write down *why* (different responsibility, different invariants) before forking. The note becomes a comment if the divergence is non-obvious.

The default answer is "modify the existing one." Forking requires a written reason.

## What this skill is NOT for

- It is not a substitute for reading the file you're editing.
- It is not a license to be slow — most scans take under 10 seconds.
- It does not block legitimate new code. It blocks *accidental* duplicates.

## Exit criteria

You may write code only after:

- ☐ You ran name + behavior search
- ☐ You read at least one neighbor file in the target directory
- ☐ You stated the scan result and action in one line
