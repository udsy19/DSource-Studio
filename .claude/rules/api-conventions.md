---
description: IPC + Claude API conventions for Glance Desktop. Loaded when working in src/main, src/preload, src/shared, or src/main/llm.
paths:
  - "src/main/**/*"
  - "src/preload/**/*"
  - "src/shared/**/*"
---

# IPC + Claude API Conventions

Two halves: (1) the IPC contract between main and renderer, (2) how we call Anthropic's Claude API.

---

## IPC (renderer ↔ main)

### Single shared contract

Every IPC channel is typed in `src/shared/ipc-contract.ts`. Both `ipcMain.handle` and the preload `ipcRenderer.invoke` import the same channel-name constant and the same payload/response type. **No string literals scattered across files.**

### Channel names

Format: `glance:<noun>-<verb>`. Examples: `glance:db-ping`, `glance:meetings-list`, `glance:meeting-toggle-record`, `glance:oauth-start`. Lower-kebab.

### Payloads and responses

- Plain serializable JSON only. No `Date`, no `Buffer`, no functions.
- Timestamps: number of ms since epoch (matches SQLite `mode: 'timestamp_ms'`).
- IDs: opaque strings prefixed by type — `meet_…`, `tx_…`. `randomUUID()` from `node:crypto`.
- Errors: `throw` from the main handler — `ipcRenderer.invoke` will reject. No error envelopes.

### Security

- `nodeIntegration: false`, `contextIsolation: true`, `sandbox: false`.
- Renderer NEVER imports `electron`, `fs`, `child_process`, or `better-sqlite3` directly. Always through preload.
- Preload bridge surface is the smallest possible — one function per channel.

### Long-running operations

Transcription, summarization, and meeting recording MUST be fire-and-forget. The handler kicks off the job and returns immediately; progress comes back via `mainWindow.webContents.send('glance:job-progress', ...)`. The renderer subscribes via preload-exposed listener.

### Idempotency

Pipeline tasks (transcribe, summarize, embed) check for existing output before re-running. Each step's output is its own SQLite row keyed by `meetingId`.

---

## Claude API (Anthropic)

> Every Claude call goes through `src/main/llm/`. Renderer and non-LLM modules NEVER instantiate the SDK directly.

### Model selection

| Task | Model | Why |
|------|-------|-----|
| Meeting summary | `claude-sonnet-4-6` | Best quality/cost for long-context summarization |
| Ask-AI chat | `claude-sonnet-4-6` | Same |
| Selector self-heal | `claude-sonnet-4-6` | Brief one-shot DOM analysis, low volume |
| Short rewrites / titles | `claude-haiku-4-5` | Fast, cheap |

When in doubt, default to Sonnet 4.6.

### Request shape

- Use the official SDK (`@anthropic-ai/sdk`). Never raw `fetch`.
- Set `max_tokens` explicitly for every request.
- System prompt = role + invariants. User message = the task data.
- For structured output, use **tool use** (force the model to call a function). Never parse free-form JSON.

### BYO key

If `apiKeys` table has a row for `provider = 'anthropic'`, decrypt and use that key instead of the shared `ANTHROPIC_API_KEY` env var. Tag the resulting `summaries.byoKeyUsed = true`.

### Retries

Retry on `429` and `5xx` with exponential backoff + jitter. Cap at 3 attempts. Do NOT retry on `400`. Log `request-id` on every failure.

### Prompt caching

Cache system prompts and any large static reference using `cache_control: { type: 'ephemeral' }`. Anything > 1024 tokens that's stable across calls is a caching candidate.

### Cost & token accounting

Log `usage.input_tokens`, `usage.output_tokens`, `usage.cache_read_input_tokens` on every call. Aggregate per meeting.

### PII

Transcripts are PII. Don't log full prompts at INFO level. Log request id + token counts; gate full-prompt logging behind a debug flag.
