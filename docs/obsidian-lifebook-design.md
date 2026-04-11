# Obsidian Lifebook Design

The Sentinel treats the user's Obsidian vault as a living knowledge system — a lifebook — not a
simple session note store. This document describes what the Sentinel reads, what it writes, where
it writes it, and how the Discord interface exposes vault operations as slash-command subcommands.

---

## Vault Structure

The vault lives at the path configured in `OBSIDIAN_BASE_URL` (default: `http://host.docker.internal:27123`).
All paths below are relative to the vault root.

```
self/
├── identity.md        — who the Sentinel is and how it works; injected as persona context
├── methodology.md     — how to work with notes (referenced but not auto-injected)
├── goals.md           — current active threads (music, kids, Coincert, gear, etc.)
└── relationships.md   — kids schedules, family context, key people

notes/                 — prose-as-title atomic knowledge notes with YAML frontmatter
inbox/                 — capture pipeline; Sentinel writes new notes here
ops/
├── reminders.md       — time-bound commitments; injected alongside self/ context
├── sessions/          — session logs written after every completed exchange
│   └── YYYY-MM-DD/
│       └── {user_id}-{HH-MM-SS}.md
└── observations/      — friction signals (written manually or by future modules)

templates/             — note templates (not read by Sentinel)
```

---

## What the Sentinel Reads

### Self context (`get_self_context`)

Concatenates five files on every message:

| File | Purpose |
|------|---------|
| `self/identity.md` | Sentinel persona — values, working style, what it pays attention to |
| `self/methodology.md` | How to work with notes and structure knowledge |
| `self/goals.md` | Current active threads and priorities |
| `self/relationships.md` | Kids schedules, family context, key people |
| `ops/reminders.md` | Time-bound commitments injected alongside self/ context |

All five are fetched in parallel. Any file that returns 404 or errors is silently skipped —
the others still inject. If all five fail, context injection is skipped for that exchange.

### Reminders (`get_reminders`)

Reads `ops/reminders.md` — time-bound commitments (follow-ups, deadlines, scheduled events).
Injected as a separate context section after self/ context. Returns `None` on 404 or error.

### Recent sessions (`get_recent_sessions`)

Lists today's and yesterday's `ops/sessions/{date}/` directories, filters files matching the
current `user_id`, fetches the most recent 3. Injected as "Recent session history" after
reminders. Graceful degrade: returns `[]` on any error.

---

## What the Sentinel Writes

### Session summaries

After every completed exchange, a session note is written as a background task (best-effort —
failure is logged, never surfaces to the user).

**Path:** `ops/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md`

**Format:**
```markdown
---
timestamp: 2026-04-10T14:23:01+00:00
user_id: 123456789012345678
model: llama-3.2-3b-instruct
---

## User

<user message>

## Sentinel

<AI response>
```

### Inbox captures

When `:capture <text>` is invoked, Core receives a message prefixed "Capture this to my inbox: …".
The LM response triggers an `ObsidianClient.write_inbox_note()` call (currently via Core's
message handler interpreting the prompt — a dedicated `/capture` endpoint may be added in a
future phase).

**Path:** `inbox/{YYYYMMDDHHMMSS}-{slug}.md`

**Format:**
```markdown
---
description: <title>
type: insight
status: active
created: YYYY-MM-DD
---

# <title>

<content>
```

---

## Context Injection Model

On each `/message` request, Core builds a single context block from three sources and prepends
it as a `user`/`assistant` pair before the actual user message:

```
Vault context (identity, methodology, goals, relationships, reminders):
<self/identity.md + self/methodology.md + self/goals.md + self/relationships.md + ops/reminders.md>

Recent session history:
<last 3 session files>
---
<next session>
---
<next session>
```

The combined block is truncated to 25% of the model's context window before the token guard
runs. If truncation occurs, a warning is logged with the token counts.

---

## System Prompt (Lifebook Persona)

```
You are the Sentinel of Mnemosyne — a personal second brain and AI assistant.
You know the user's goals, gear, kids' schedules, and active projects from their Obsidian vault.
You are warm, direct, and unafraid to call out neglected gear or stale goals.
You remember context from prior sessions and reference it naturally.
Answer conversationally. Use markdown only when asked.
```

---

## Discord `/sentask` Subcommand Map

Subcommands are triggered by prefixing the message with `:`. Anything without a `:` prefix is
sent directly to the AI as a plain message.

| Subcommand | Action | Prompt sent to Core |
|------------|--------|---------------------|
| `:help` | Returns help text locally | — (no Core call) |
| `:capture <text>` | Capture thought to inbox | `"Capture this to my inbox: <text>"` |
| `:next` | What to work on next | `"What should I work on next based on my current goals?"` |
| `:health` | Vault health check | `"Run a health check on my vault and report orphan notes, stale goals, neglected gear."` |
| `:goals` | Show active goals | `"Show me my current active goals."` |
| `:reminders` | Show reminders | `"What are my current time-bound reminders?"` |
| `:<unknown>` | Error message | — (no Core call) |

All subcommands still create a thread and route the response through the normal thread/followup
flow — the only difference is the message that reaches Core (or the local help text for `:help`).

---

## Vault Path Conventions

| Purpose | Path pattern |
|---------|-------------|
| Self context | `self/identity.md`, `self/methodology.md`, `self/goals.md`, `self/relationships.md`, `ops/reminders.md` |
| Reminders | `ops/reminders.md` |
| Session logs | `ops/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md` |
| Inbox captures | `inbox/{YYYYMMDDHHMMSS}-{slug}.md` |
| Keyword search | `POST /search/simple/?query=…` (via `search_vault`) |

**Single-user vault:** No `user_id` keying is applied to reads from `self/` or `ops/reminders.md`.
These paths are always the same person. `user_id` (Discord snowflake) is only used to namespace
session files within `ops/sessions/`.

---

## Backward Compatibility

`ObsidianClient.get_user_context(user_id)` and `get_recent_sessions(user_id)` remain intact.
`get_user_context` reads `core/users/{user_id}.md` — the old per-user profile path. It is no
longer called by `message.py` but is kept for any future multi-user interface that needs it.
