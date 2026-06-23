---
name: deploy
description: The Glance deploy runbook. Reference content describing how we ship — pre-flight gates, build, deploy targets, smoke tests, rollback. Consult this when reasoning about a deploy, planning a release, or recovering from a failed deploy.
when_to_use: "Use when the user asks about deploy/release process, what runs in CI, how to roll back, what staging vs production differs on, or while executing `/deploy`."
user-invocable: false
allowed-tools: Bash(git status), Bash(git log:*), Bash(gh:*), Read
---

# Deploy runbook

Background knowledge about how Glance deploys. The user-facing trigger is the `/deploy` slash command (`.claude/commands/deploy.md`). This skill is the reference Claude consults to reason about deploys correctly.

## Environments

| Env | URL | Branch | Approval | Rollback target |
|-----|-----|--------|----------|-----------------|
| `dev` | _local_ | any | none | n/a |
| `staging` | `staging.glance.example` | any | none | previous staging release |
| `production` | `glance.example` | `main` only | manual confirmation | last green production release |

## Pre-flight gates

Every deploy, in this order. Abort on first failure.

1. **Clean tree.** `git status --porcelain` empty.
2. **Lint.** `npm run lint` (or `pnpm`/`uv` equivalent).
3. **Typecheck.** `npm run typecheck`.
4. **Tests.** `npm test`. Unit + integration. E2E only required for production.
5. **CI green on head SHA.** `gh run list --branch <branch> --limit 1` reports `success`. Production requires this.
6. **Migrations dry-run.** If the diff touches `migrations/`, run the dry-run plan and confirm it's reversible.

## Build

- `npm run build` produces the deployable artifact.
- Confirm the build artifact exists at the expected path before continuing.
- Build must be reproducible — the same SHA must produce a byte-identical artifact for cache to work.

## Deploy

Replace with the project's actual pipeline:

- Vercel: `vercel deploy --prod` for prod; preview deploy for staging.
- Fly: `flyctl deploy --app glance-<env>`.
- GitHub Actions: `gh workflow run deploy.yml -f env=<env>`.

Always capture and surface:

- Commit SHA being shipped
- Deploy URL
- Pipeline run URL (for later inspection)

## Smoke tests

After the pipeline reports success:

1. `GET <url>/healthz` → expect `200` with `{"status":"ok"}`.
2. `POST <url>/v1/meetings` with a tiny test fixture → expect `202` and a job id.
3. Watch the job for 30s. It should reach `completed` (or at least `transcribing`).

If any smoke test fails, **roll back immediately** — don't try to forward-fix in production.

## Rollback

- Vercel: `vercel rollback <previous-deployment-url>`.
- Fly: `flyctl releases list` → `flyctl deploy --image <previous-image>`.
- DB migrations: if the failed deploy ran a migration, run the matching `down` migration *before* rolling back the app, unless the migration is forward-compatible.

## Post-deploy

- Tail logs for 60s after a production deploy. Look for `level=error` rate spikes.
- Note the deploy in the team channel: commit SHA, deploy URL, who pressed the button.

## What this skill does **not** do

- Does not trigger anything automatically. Side effects belong to the `/deploy` command, which the user invokes explicitly.
- Does not approve deploys. A human approves production.
