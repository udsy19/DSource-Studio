---
description: Anti-bloat discipline for Glance. Always-on. The single highest-priority rule set in this repo. Prevents the common AI failure modes — duplicate files, parallel implementations, dead code, premature abstractions, half-finished migrations.
---

# No Bloat — How To Change Code Here

Loaded on every session. Read first. **These rules outrank style and preference rules when they conflict.**

The biggest failure mode of an AI coding assistant on a long-lived codebase is not bad code — it's *additive* code. New file next to an old one. New helper that does what an existing helper already does. New abstraction "just in case." Over weeks, the codebase doubles in size and nothing is deletable because everything has one caller. **Don't do that here.**

## The two-question test (run it before every change)

Before you write a single new line of code, answer both out loud:

1. **Does something like this already exist in the codebase?**
   - If you didn't search, you don't know. Search.
2. **If yes — should I modify the existing thing instead of writing a new one?**
   - Default: yes.
   - Only acceptable reasons to write a new one: the existing thing has a different *responsibility*, not a different *shape*.

Skipping this check is the #1 cause of bloat in this repo.

## Search before write — mandatory

When the task involves adding a function, class, file, route, schema, prompt, type, or utility:

1. **Name search.** `rg -i "<likely name>" src/ tests/` for the concept by all plausible names.
2. **Behavior search.** Grep for distinctive strings the existing implementation would use (error messages, log lines, regex literals, API field names).
3. **Structural search** (when language-aware tools are available, e.g. `ast-grep`). Names and strings miss semantic duplicates — `formatDate` vs `toDateString` vs `prettyDate` all do the same thing. Look at the *shapes* of functions in the relevant directory.
4. **Type search.** If you're adding a type/interface, grep for the field names you'd use. Type duplicates are the worst because they silently diverge.
5. **Read the neighbors.** Open 1–2 existing files in the target directory. Match the patterns you see.

State what you found in one line before writing: _"Searched `src/llm/` and `src/core/transcript/`; closest existing helper is `redactPiiFromText` in `src/core/transcript/redact.ts` — I'll extend it rather than create a new one."_

If the search returns nothing, say so explicitly: _"No existing implementation found. Creating new."_

## Refactor in place — never in parallel

If you're changing how something works:

- **Modify the existing file.** Do not create `foo_v2.ts`, `fooNew.ts`, `foo.improved.ts`, or `foo/new/`.
- **No "old" + "new" living side by side.** If the new version replaces the old, delete the old in the same change. No deprecation period in an internal codebase unless we have external consumers.
- **No feature-flag forks of the same logic** unless the user explicitly asked for a gradual rollout. Default: cut over.
- **Rename, don't duplicate.** If a function's old name is wrong, rename it (with all callers updated). Don't leave the old name as a thin wrapper.

When you delete the old code, **delete it.** Don't comment it out. Don't leave a `// removed for X` marker. `git log` is the history; the file is the current state.

## Abstractions: three-strikes rule

You do not need an abstraction for one caller. You usually do not need one for two. By the third occurrence with the same shape, extract.

- Three similar lines is fine. A premature `BaseHandler` / `AbstractProcessor` / `EntityFactory` is not.
- "I might need this later" is not a reason. YAGNI applies hard here.
- Options bags with five optional fields where every caller passes the same three? Bad sign — you've abstracted too early.
- Generic helpers that take a `kind: 'meeting' | 'transcript' | 'action'` discriminator and a giant switch? That's two functions pretending to be one. Split.

Test code is the exception: a few duplicated setup lines is better than a clever shared helper that obscures what each test actually does.

## Dead code: forbidden

When you finish a change, your branch must contain **zero**:

- Unused exports (the function exists, no one imports it)
- Unused imports
- Unused variables (don't rename to `_var` — delete)
- Unreferenced files
- Unreachable branches (`if (false)`, dead `else`)
- Commented-out blocks of code
- TODO comments without an owner and a date
- "Future" code (`// will use this when ...`)

Before declaring done, run a dead-code check. For TypeScript: `npx ts-prune` or your project's equivalent. For Python: `vulture` or `ruff --select F401,F841`. Add the dead-code linter to CI if it isn't there.

If a function isn't called yet but will be in the same change, write the caller in the same commit. No orphans landing alone.

## File proliferation: forbidden

- **One concept, one file.** If you find yourself making `transcript.ts`, `transcript-utils.ts`, `transcript-helpers.ts`, `transcript-shared.ts` — that's one file pretending to be four. Merge.
- **Don't split a file just because it's getting long.** 500 lines of coherent code is fine. 3 files of 200 lines of incoherent code is worse.
- **Don't create a directory for a single file.** `src/core/transcript.ts` is better than `src/core/transcript/transcript.ts`.
- **Don't add an `index.ts` barrel just because.** Only add one if it provides a real API boundary.

## Scope discipline

When the user asks for X:

- Do X. Don't also do Y because Y caught your eye.
- A bug fix doesn't need surrounding cleanup. If you spotted unrelated dead code, mention it; don't sneak it into the fix.
- A one-shot operation doesn't need a helper. Inline is fine.
- Don't add error handling for cases that can't happen.
- Don't add validation at internal boundaries the type system already guards.
- Don't add fallbacks for hypotheticals.

If you find yourself wanting to make changes outside the task's scope, **stop and ask** instead of expanding silently.

## What "done" means here

A change is done when **all** of these are true:

1. The new behavior works (test exists and passes).
2. The thing it replaces, if any, is **deleted in the same change**.
3. No dead code, no unused imports, no orphaned files.
4. Lint, typecheck, tests all pass.
5. The diff is *smaller* than you'd expect — because you reused, not added.
6. If you can't reduce LoC, the new code earned its size by deleting more code elsewhere.

A diff that only adds lines is almost always wrong.

## Self-check before reporting "done"

Run through this in your head:

- ☐ Did I search for existing implementations before writing new ones?
- ☐ Did I modify in place rather than create parallel files?
- ☐ Did I delete the old code path in the same change?
- ☐ Did I avoid premature abstractions (three-strikes rule)?
- ☐ Are there any unused exports, imports, vars, or files in my diff?
- ☐ Did I stay within the scope the user asked for?
- ☐ Is the diff net-smaller or close to net-zero, given what it replaces?

If any answer is "no" or "not sure" — fix it before you say you're done.

## Why this matters more than other rules

A clean codebase is the substrate every other quality depends on:

- **Reviewability**: small diffs get reviewed; sprawling diffs get rubber-stamped.
- **Debuggability**: one place for one concept means one place to look.
- **Agent reliability**: an AI assistant working in this codebase next month will only do the right thing if there's *one obvious* right thing to extend.
- **Velocity**: every duplicate today is a bug tomorrow when they diverge.

Treat additive change as the failure mode. Treat deletion as a feature.
