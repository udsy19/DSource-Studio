---
name: security-review
description: Security review of pending changes — finds secrets, injection vectors, auth/authz gaps, unsafe deps, and PII leaks. Use when the user asks to review for security, before merging anything touching auth/input/external APIs/PII, or when the diff includes new dependencies, new endpoints, or new data flows.
when_to_use: "Trigger on phrases: 'security review', 'is this safe?', 'check for secrets', 'audit the diff', 'is the auth right', 'PII review', or before any PR merge into main."
allowed-tools: Bash(git status), Bash(git diff:*), Bash(git log:*), Bash(rg:*), Read, Grep, Glob
---

# Security Review

A focused security pass on the current diff. Aimed at catching the realistic, high-impact problems for a meeting-transcript product — not a generic OWASP checklist.

## Current diff

!`git diff --stat HEAD`

!`git diff HEAD`

## What to check

Walk the diff and look for each category. If a category doesn't apply to this diff, skip it — don't pad the output.

### 1. Secrets in code

- API keys, tokens, OAuth client secrets, private keys, DB connection strings with passwords.
- Watch for: `sk_`, `xoxb-`, `xoxp-`, `AKIA`, `-----BEGIN`, hardcoded `Authorization: Bearer ...`.
- Even in tests/fixtures — those get pushed too.

### 2. Injection

- **SQL**: any string concatenation into a query. Must use parameterized queries.
- **Command**: `exec`, `spawn`, `subprocess.run(..., shell=True)`, backticks with interpolated input.
- **Path traversal**: user-controlled filenames joined with `path.join` without resolution + boundary check.
- **SSRF**: outbound HTTP to a URL that's user-controlled (we accept meeting recording URLs — be paranoid).
- **Prompt injection**: untrusted meeting transcript content concatenated into a system prompt without sandboxing.

### 3. Auth & authz

- New endpoints: is auth required? Is org/tenant scoping enforced?
- IDOR: does the handler check that the authenticated user owns the meeting/transcript being requested?
- Role checks: are they enforced server-side, not just hidden in the UI?

### 4. PII / transcript safety

This is the one specific to our product.

- Logging full transcripts at INFO level — block.
- Sending transcripts to third-party analytics — block.
- Including transcript content in error messages or `details` returned to clients — block.
- Missing redaction step for emails/phones/credit cards before storing in error logs.

### 5. Crypto

- Hardcoded keys, IVs, or salts.
- `Math.random()` / `random.random()` used for tokens, IDs, or anything security-sensitive — use crypto-secure RNG.
- Weak algorithms (MD5, SHA1, DES) where a cryptographic property is needed.
- TLS verification disabled.

### 6. Dependencies

- New entries in `package.json` / `pyproject.toml` / `Cargo.toml`. Check:
  - Maintained (last release < 1 year ago)
  - No known critical CVEs (`npm audit`, `pip-audit`, etc.)
  - Not a typosquat (e.g. `requesst`, `lod-ash`)

### 7. Permissions in `.claude/`

- New entries in `.claude/settings.json` `allow` that grant broad shell access (`Bash(*)`, `Bash(curl *)`).
- New skills with `allowed-tools` that grant unrestricted Bash.

## Output

Punch list only, no preamble:

```
SEVERITY | file:line | issue | concrete attack path | suggested fix
```

`SEVERITY` is one of `critical | high | medium | low | info`.

- `critical` = exploitable now, no auth required
- `high` = exploitable with low effort or by authenticated user
- `medium` = needs unusual conditions
- `low` = defense-in-depth
- `info` = noteworthy, not a finding

End with one line: **"Mergeable: yes/no — <reason>."**

If you can't construct a concrete attack path, downgrade the finding or drop it. Speculation is noise.
