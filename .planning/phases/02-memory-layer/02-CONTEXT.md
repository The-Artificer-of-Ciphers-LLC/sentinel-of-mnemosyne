---
phase: 02
name: Memory Layer
created: "2026-04-10T17:34:38Z"
status: final
---

# Phase 02: Memory Layer — Discussion Context

## Phase Goal

The Sentinel remembers. Before answering, it reads user context from Obsidian. After answering, it writes a session summary. A second conversation with the same user can reference a specific detail from a prior session.

## Canonical Refs

- `.planning/REQUIREMENTS.md` — MEM-01 through MEM-08 (full requirement text)
- `.planning/phases/01-core-loop/01-CONTEXT.md` — Phase 01 locked decisions (Docker patterns, tech stack)
- `.planning/phases/01-core-loop/01-03-SUMMARY.md` — Sentinel Core implementation details (app.state pattern, lifespan, clients)
- `sentinel-core/app/routes/message.py` — integration point for memory injection and summary write
- `sentinel-core/app/clients/pi_adapter.py` — pattern to follow for ObsidianClient
- `sentinel-core/app/main.py` — lifespan pattern for wiring ObsidianClient into app.state
- `sentinel-core/app/config.py` — Settings pattern (pydantic-settings, env vars)
- `.env` — OBSIDIAN_API_URL and OBSIDIAN_API_KEY already present

## Prior Decisions (from Phase 01)

- **Obsidian vault = the database.** No SQL, no Redis, no additional stores.
- **`app.state` lifespan pattern.** All shared clients live on `app.state`, initialized in the asynccontextmanager lifespan.
- **Pydantic v2 models + pydantic-settings for env config.** All new models follow this pattern.
- **`httpx.AsyncClient` for all outbound HTTP.** One shared client per service in the lifespan. Never use `requests`.
- **Docker Compose include directive pattern.** No `-f` flag stacking. Graceful degradation via `service_started` (not `service_healthy`).
- **Pi v0.66 has `supportsDeveloperRole: false`.** No system/developer message role. Context must be injected as user/assistant turns.
- **`user_id` already on `MessageEnvelope`.** Ready for per-user memory — no model changes needed.

## Decisions

### 1. Prompt Construction — Context Injection

**Decision:** Prepend user context as a user/assistant turn pair before the actual message.

**Implementation:**
```python
messages = [
    {"role": "user", "content": f"Here is context about me:\n{user_context}"},
    {"role": "assistant", "content": "Understood."},
    {"role": "user", "content": envelope.content},
]
```

**Rationale:** Pi v0.66 does not support the system/developer role (`supportsDeveloperRole: false`). Prepending as a prior user/assistant exchange is the canonical workaround — it grounds the context as background knowledge before the conversation starts. The fake `"Understood."` assistant turn anchors the context without confusing the model.

**Token budget note:** User context + session history are injected before `check_token_limit()` is called. Token guard must account for all messages in the array, not just the user's content.

### 2. Session Summary Write Policy

**Decision:** Always write — every completed exchange produces a session note.

**Path:** `/core/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md`

**Content (minimum):**
- User message
- AI response
- Timestamp
- model used

**Rationale:** Storage is cheap in Obsidian. A complete audit trail enables cross-session memory without complex filtering logic. Pruning/archiving is a manual or future-phase concern.

**Failure handling:** If the Obsidian write fails, log a warning and do NOT fail the HTTP response. The user already received their answer — the write is best-effort.

### 3. Obsidian Failure Behavior

**Decision:** Graceful degradation — proceed without memory when Obsidian is unavailable.

**Behavior:**
- Context retrieval fails → skip context injection, log warning, continue with bare prompt
- Summary write fails → log warning, return response to caller normally
- `/health` endpoint can report Obsidian status as a separate field (non-blocking)

**Rationale:** Obsidian requires manual startup; it will be unavailable on fresh boot until the user opens it. Blocking on Obsidian availability would make every container restart dependent on the user's desktop app. The system must be resilient to this.

**MEM-01 compliance:** Health check detects when Obsidian is not running and degrades gracefully ✓

### 4. User Context File

**Decision:** Manual, free-form Markdown file in Obsidian. Created and owned by the user.

**Path:** `/core/users/{user_id}.md`

**Format:** Plain Markdown prose — no schema enforcement, no required frontmatter. The system reads the entire file as-is and injects it verbatim as the context string.

**Behavior when file missing:** Skip context injection silently. First message from a new user_id works fine without context — there's simply nothing to inject.

**Example content** (user creates this themselves):
```markdown
# User: trekkie

I'm a software engineer working on Sentinel.
I prefer concise, direct answers.
I play Pathfinder 2e as a GM.
I practice electric guitar (intermediate).
I track personal finances carefully.
```

**Rationale:** The user knows what context is useful. Forcing a schema or auto-creating templates adds friction without benefit. The system's job is to read whatever the user decides to write.

## Architecture Notes (for researcher + planner)

### New component: ObsidianClient

Pattern: same as `LMStudioClient` and `PiAdapterClient` — a class wrapping an `httpx.AsyncClient`, instantiated in lifespan, attached to `app.state.obsidian_client`.

Key methods needed:
- `get_user_context(user_id: str) -> str | None` — GET `/vault/core/users/{user_id}.md`, return body or None if 404
- `get_recent_sessions(user_id: str, limit: int) -> list[str]` — search vault for recent session files for this user
- `write_session_summary(user_id: str, content: str) -> None` — PUT `/vault/core/sessions/{date}/{user_id}-{time}.md`
- `search_vault(query: str) -> list[dict]` — POST `/search/simple/?query={query}` for warm-tier retrieval

Reference: Obsidian Local REST API docs — see CLAUDE.md for endpoint table.

### New config fields

```python
obsidian_api_url: str = "http://host.docker.internal:27124"
obsidian_api_key: str = ""  # Optional — blank means no auth header sent
```

Both already in `.env` as `OBSIDIAN_API_URL` and `OBSIDIAN_API_KEY`.

### Modified: POST /message flow

Current flow:
1. Token guard
2. `pi_adapter.send_prompt(envelope.content)`
3. Return ResponseEnvelope

New flow:
1. Retrieve user context from Obsidian (graceful skip on failure)
2. Retrieve recent session summaries (hot tier — last N sessions)
3. Build message array with context prepended (user/assistant pair)
4. Token guard on full message array
5. `pi_adapter.send_prompt(messages)` — NOTE: requires pi-adapter to accept a message array, not just a string
6. Return ResponseEnvelope
7. Write session summary to Obsidian (best-effort, async, non-blocking)

**Important flag for researcher:** Step 5 requires Pi harness to forward a message array, not a plain string. Check whether the pi RPC `prompt` command supports a `messages` field or only `message` (string). This may require a pi-harness bridge change.

### Tiered memory (MEM-05)

For Phase 2 scope:
- **Hot tier:** Last 3 session summaries for this user_id, always loaded if they exist
- **Warm tier:** Vault keyword search — triggered on demand (reserved for Phase 2 if time allows; not required for MVP cross-session memory demo)
- **Cold tier:** Archive — file organization only, not queried. Sessions older than 30 days move to `/core/sessions/archive/`

The MVP for cross-session memory (MEM-04) only requires hot tier working.

### Token budget (MEM-07)

**Decision (Claude's Discretion):** 25% of context window reserved for injected context (user file + hot-tier sessions combined). Enforced by the existing `check_token_limit()` call on the full message array. No separate ceiling config needed in Phase 2 — token guard naturally enforces it.

## Deferred Ideas

- Vector search / semantic retrieval (VMEM-01) — v2 requirement, out of scope
- Entity graph for NPCs, people, projects — v2 requirement
- User-facing command to query their own memory ("what do you know about me?") — future phase
- Auto-updating user context file (AI writes back what it learns) — interesting but scope creep

## Discussion Log

| Area | Decision | Rationale |
|------|----------|-----------|
| Prompt construction | Prepend as user/assistant turn pair | Pi v0.66 no system role; fake exchange grounds context cleanly |
| Write-selectivity policy | Always write | Simple, complete audit trail; storage cheap in Obsidian |
| Obsidian failure behavior | Graceful degradation | Obsidian requires manual startup; must not block on desktop app availability |
| User context file | Manual, free-form Markdown | User knows what context is useful; no schema friction |
