---
description: Deploy the current branch to staging (default) or a named environment after pre-flight checks
argument-hint: "[staging|production]"
disable-model-invocation: true
allowed-tools: Bash(git status), Bash(git log:*), Bash(git rev-parse:*), Bash(npm test:*), Bash(pnpm test:*), Bash(npm run build:*), Bash(pnpm build:*), Bash(gh:*)
---

# /deploy

Ship the current branch. `$ARGUMENTS` selects the target environment — defaults to `staging`. Production deploys require an explicit `production` argument.

> ⚠️ This command has side effects. It is **not** invokable by Claude automatically (`disable-model-invocation: true`). A human must type `/deploy`.

## Current state

!`git status --short`

!`git log -1 --oneline`

!`git rev-parse --abbrev-ref HEAD`

## Workflow

1. **Resolve the target**
   - If `$ARGUMENTS` is empty, target = `staging`.
   - If `$ARGUMENTS` is `production`, require an additional confirmation step before proceeding.
   - Anything else → abort and ask.

2. **Pre-flight**
   - Working tree must be clean (no uncommitted changes).
   - Current branch must be ahead of `origin/<branch>` only by intended commits — show `git log origin/<branch>..HEAD`.
   - For production: branch must be `main` and CI green on the head SHA (`gh run list --branch main --limit 1`).
   - Run `npm run lint`, `npm run typecheck`, `npm test` (or pnpm/uv equivalents). Abort on any failure.

3. **Build**
   - `npm run build` (or project equivalent). Confirm the build artifact exists.

4. **Deploy**
   - Trigger the deploy pipeline for the target environment. Replace this with the project's actual deploy command (e.g. `vercel deploy --prod`, `gh workflow run deploy.yml -f env=production`, `flyctl deploy`).
   - Capture the deploy URL and the commit SHA being shipped.

5. **Verify**
   - Hit the health endpoint of the deployed service. Expect `2xx`.
   - For production, tail logs for 60s and watch for error-rate spikes.

6. **Report**
   - One line per fact: environment, commit SHA, deploy URL, health-check result.
   - If anything went wrong, surface the rollback command and DO NOT mark the deploy successful.

Target: $ARGUMENTS
