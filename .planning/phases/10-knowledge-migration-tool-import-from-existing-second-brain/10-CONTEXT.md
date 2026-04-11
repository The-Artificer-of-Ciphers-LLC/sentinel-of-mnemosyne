---
phase: 10
slug: knowledge-migration-tool-import-from-existing-second-brain
status: ready
created: 2026-04-11
---

# Phase 10: 2nd Brain — Full Command System + Vault Migration

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement the complete 2nd brain command system in the Sentinel: all 26 commands as Discord `:prefix` subcommands, the full vault structure (`self/`, `notes/`, `ops/`, `inbox/`, `templates/`), session-start memory reading pattern, and migration of existing `core/` vault data to the new structure.

The Sentinel becomes a full 2nd brain agent — not just a Q&A chatbot, but an agent that maintains and traverses a personal knowledge graph.

</domain>

<decisions>
## Implementation Decisions

### D-01: Vault Structure — Migrate, Don't Bridge

**Decision:** The Sentinel migrates to the 2nd brain vault paths natively. The `core/` prefix is replaced.

| Old path | New path |
|----------|----------|
| `core/users/{user_id}.md` | `self/identity.md` (single user system) |
| `core/sessions/{date}/{user_id}-{time}.md` | `ops/sessions/{date}/{user_id}-{time}.md` |

All new reads and writes use the 2nd brain structure. Any existing `core/` data is migrated by the migration task in this phase.

**Vault directory structure to establish:**
```
self/
├── identity.md
├── methodology.md
├── goals.md
├── relationships.md
└── memory/

notes/

inbox/

ops/
├── reminders.md
├── observations/
├── tensions/
├── methodology/
├── sessions/
├── health/
└── queue/

templates/
```

Create stub files for any that don't exist yet. Migrate content from `core/` for any that have existing data.

### D-02: Session Start Reading Pattern

**Decision:** The POST /message handler reads the following at every exchange (in addition to hot-tier sessions):

1. `self/identity.md` — who the user is, working style
2. `self/methodology.md` — how the system works, principles
3. `self/goals.md` — current active threads
4. `self/relationships.md` — kids schedules, key people
5. `ops/reminders.md` — time-bound commitments; surface overdue items

These are read via `ObsidianClient` using existing GET `/vault/{path}` calls. All reads are graceful-skip on 404 (file not created yet → no injection). Content is injected as part of the hot-tier context pair, subject to `SESSIONS_BUDGET_RATIO`.

### D-03: All 26 Commands as `:prefix` Subcommands

**Decision:** All commands are invoked as `:commandname` inside a `/sentask` thread. The `:` prefix routes to the subcommand handler. Unrecognized subcommands fall through to AI with the full message.

**Standard commands (16):**

| Command | Behavior |
|---------|----------|
| `:capture [text]` | Extract insights from source material; route to `inbox/` |
| `:connect [note title]` | Find connections between a note and the existing graph |
| `:revisit [note title]` | Revisit and update an old note with current understanding |
| `:review [note title]` | Verify note quality: description, schema, hub membership |
| `:check` | Validate schema compliance across `notes/` |
| `:seed [text]` | Drop raw content into `inbox/` — zero friction capture |
| `:ralph` | Orchestrated batch processing of `inbox/` queue |
| `:pipeline` | Run full processing pipeline (capture → process → connect → review) |
| `:tasks` | Show and manage the ops/queue/ task queue |
| `:stats` | Vault metrics: note count, orphans, link density, hub sizes |
| `:graph [query]` | Graph analysis: orphans, triangles, density, backlinks |
| `:next` | Workboard reconciliation — surfaces what needs attention based on vault state |
| `:learn [topic]` | Research a topic and grow the knowledge graph |
| `:remember [observation]` | Capture friction or methodology learning to ops/observations/ |
| `:rethink` | Review accumulated observations and tensions; triage each |
| `:refactor` | Restructure and improve vault organization |

**Plugin commands (10) — invoked as `:plugin:command`:**

| Command | Behavior |
|---------|----------|
| `:plugin:help` | Contextual guidance — what commands exist and when to use each |
| `:plugin:health` | Full vault diagnostics: orphans, dangling links, hub coherence, stale content |
| `:plugin:ask [question]` | Query the methodology knowledge base |
| `:plugin:architect` | Research-backed vault evolution advice |
| `:plugin:setup` | Initial vault structure creation |
| `:plugin:tutorial` | Interactive walkthrough of the 2nd brain system |
| `:plugin:upgrade` | Check for methodology improvements |
| `:plugin:reseed` | Principled vault restructuring |
| `:plugin:add-domain [domain]` | Extend vault with a new domain area |
| `:plugin:recommend` | Architecture advice for current vault state |

### D-04: Thread Continuity Fix

**Decision:** `SENTINEL_THREAD_IDS` in bot.py must persist across restarts. Store active thread IDs in Obsidian at `ops/discord-threads.md` (simple newline-delimited list). On bot startup, read this file and populate the in-memory set. On new thread creation, write the thread ID to the file immediately.

### D-07: Voice and Personality

**Decision:** The Sentinel's response style when operating in 2nd brain commands is warm, direct, and opinionated. Contractions, shorter sentences, casual tone. Nudges are specific.

Examples:
- "12 notes connected, no orphans. Inbox has 4 items older than 3 days — want to process?"
- "You said you wanted to finish that project. No progress logged this week. What's blocking you?"

### D-08: `:help` Response

**Decision:** `:help` (and `:plugin:help`) return the full command list grouped by category, with a one-line description of each. Show standard commands first, plugin commands second.

### D-09: Pipeline and Processing

**Decision:** Notes never go directly to `notes/`. All content routes through `inbox/` first. When the system writes a note, it captures to `inbox/` and creates a queue entry in `ops/queue/`. `:ralph` and `:pipeline` process the queue.

Exception: session summaries written by the background task go directly to `ops/sessions/` — they are operational logs, not knowledge graph nodes.

### D-10: Migration Scope

**Decision:** Research phase determines which vault directories already exist and which need to be created. Migration tasks are generated per-directory. Existing `core/sessions/` data is moved to `ops/sessions/`. Existing `core/users/{user_id}.md` content is merged into `self/identity.md`. Research agent reads the actual vault to assess current state.

</decisions>

<specifics>
## Specific Ideas

**Kids logistics:** Sensitive data in `self/relationships.md`. Never referenced outside the vault.

**The claim test for note titles:** "This note argues that [title]" — if it reads naturally, it's a claim.

</specifics>

<canonical_refs>
## Canonical References

### Sentinel Core integration points
- `sentinel-core/app/clients/obsidian.py` — ObsidianClient: GET/PUT/POST vault endpoints
- `sentinel-core/app/routes/message.py` — POST /message handler: session-start reading and context injection points
- `interfaces/discord/bot.py` — Discord bot: subcommand handler, on_message thread handler, SENTINEL_THREAD_IDS

### Vault structure spec (provided by user)
The full 2nd brain specification is captured verbatim in the discussion that produced this CONTEXT.md. Key structural elements:
- `self/` — agent identity and persistent memory
- `notes/` — knowledge graph (one insight per file, prose-as-title)
- `inbox/` — zero-friction capture, processed before notes/
- `ops/` — operational state (reminders, queue, sessions, observations, tensions)
- `templates/` — note type templates with `_schema` blocks

### Existing phase context
- `.planning/phases/02-memory-layer/02-CONTEXT.md` — original ObsidianClient decisions, session write pattern
- `.planning/phases/03-interfaces/03-CONTEXT.md` — Discord bot architecture, subcommand routing pattern

### Migration
- Research agent must read the actual Obsidian vault to determine which directories exist and what content needs migration. Vault is at the path configured in `OBSIDIAN_API_URL`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `obsidian.py:get_user_context()` — existing GET `/vault/{path}` call; extend to read `self/*.md` files
- `obsidian.py:search_vault()` — POST `/search/simple/` with query; used by `:graph`, `:connect`, `:next` for vault queries
- `obsidian.py:write_session_summary()` — PUT `/vault/{path}`; reuse for all vault writes with new paths
- `bot.py:handle_sentask_subcommand()` — existing subcommand router; extend with all 26 new command handlers
- `bot.py:call_core()` — existing POST /message caller; all subcommands use this with constructed prompts

### Established Patterns
- Discord subcommands use `:prefix` parsed at `message[1:].split(" ", 1)` in `bot.py:217–221`
- Obsidian writes are best-effort (BackgroundTasks, log warning on failure, never fail the HTTP response)
- All context injection is subject to `SESSIONS_BUDGET_RATIO` / token truncation before the token guard

### Integration Points
- `message.py:79–82` — retrieve user context + sessions; extend to also read `self/*.md` files
- `bot.py:69–74` — `_SUBCOMMAND_PROMPTS` dict maps command names to AI prompts; extend significantly
- Thread ID persistence: `SENTINEL_THREAD_IDS` set at `bot.py:52`; needs `ops/discord-threads.md` backing

</code_context>

<deferred>
## Deferred Ideas

- Vector/semantic search (VMEM-01) — v2 requirement
- Auto-updating `self/identity.md` (AI writes back what it learns about the user) — future phase
- Telegram / Slack interface commands — v2
- Multi-user vault separation — single user system in v1

</deferred>

---

*Phase: 10-knowledge-migration-tool-import-from-existing-second-brain*
*Context gathered: 2026-04-11*
