# Git Workflow

How we commit in this repo. Loaded on every session. **Follow exactly.**

Remote: `https://github.com/udsy19/DSource-AI.git` · default branch: `main`.

## Commit after every change

- After you finish implementing something — a feature, a fix, a refactor, a doc — **commit it**. Don't batch unrelated work into one giant commit; don't leave finished work uncommitted.
- One logical change per commit. The diff should tell one story.
- When the work spans backend + frontend for the same feature, commit them together.

## Commit messages

- Imperative mood, present tense: `add real-time material swap`, `fix DXF unit scaling`, not `added` / `fixes`.
- First line ≤ 72 chars, lower-case, no trailing period. Add a body only when the *why* isn't obvious from the diff.
- Optional conventional prefixes are fine: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`.

## Attribution — hard rule

- **NEVER credit Claude, Claude Code, AI, or any assistant in commits.** No `Co-Authored-By: Claude`, no `Generated with Claude Code`, no "AI-assisted" trailers, no emoji robot footers — nothing.
- Commits are authored as the repository owner. Messages describe the change only.

## Standard commands

```bash
git add -A
git commit -m "<imperative summary>"
git push
```

If on a fresh branch: `git push -u origin main`.

## Safety

- **Never commit secrets.** `backend/.env` and all `*.env` files are gitignored — keep it that way. Run `git status` before every commit and confirm no `.env`, `.db`, or key material is staged.
- Never `git push --force` to `main`.
- If `git status` shows an ignored secret as tracked, stop and fix `.gitignore` before committing.
