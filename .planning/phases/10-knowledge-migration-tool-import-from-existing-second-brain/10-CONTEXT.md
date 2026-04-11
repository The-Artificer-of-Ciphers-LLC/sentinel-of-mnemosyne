---
phase: 10
slug: knowledge-migration-tool-import-from-existing-second-brain
status: ready
created: 2026-04-11
updated: 2026-04-11
---

# Phase 10: 2nd Brain — Full Command System + Vault Migration

**Gathered:** 2026-04-11
**Updated:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement the complete 2nd brain command system in the Sentinel: all 27 commands as Discord `:prefix` subcommands (26 original + `:reweave`), the full vault structure (`self/`, `notes/`, `ops/`, `inbox/`, `templates/`), session-start memory reading pattern, and migration of existing `core/` vault data to the new structure.

The Sentinel becomes a full 2nd brain agent — not just a Q&A chatbot, but an agent that maintains and traverses a personal knowledge graph grounded in Tiago Forte's BASB methodology and the arscontexta design patterns.

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

These are read via `ObsidianClient` using existing GET `/vault/{path}` calls. **Implementation: `asyncio.gather()` for all 5 reads in parallel.** On 404, return empty string silently — no log entry. On other errors (500, timeout), log a warning and skip. Content is injected as part of the hot-tier context pair, subject to `SESSIONS_BUDGET_RATIO`.

### D-03: All 27 Commands as `:prefix` Subcommands

**Decision:** All commands are invoked as `:commandname` inside a `/sentask` thread. The `:` prefix routes to the subcommand handler. Unrecognized subcommands fall through to AI with the full message.

**Standard commands (17):**

| Command | Behavior | 6 Rs stage |
|---------|----------|------------|
| `:capture [text]` | Extract insights from source material; route to `inbox/` | Record |
| `:seed [text]` | Drop raw content into `inbox/` — zero friction capture | Record |
| `:ralph` | Orchestrated batch processing of `inbox/` queue | Reduce + Reflect |
| `:pipeline` | Run full 6 Rs pipeline (Record → Reduce → Reflect → Reweave → Verify → Rethink) | All |
| `:connect [note title]` | Find connections between a note and the existing graph; add wikilink to hub MOC | Reflect |
| `:reweave` | Backward pass: find older notes that should be updated given recent vault additions | Reweave |
| `:review [note title]` | Verify note quality: claim title, `_schema` block, hub membership | Verify |
| `:check` | Validate `_schema` compliance across `notes/` | Verify |
| `:rethink` | Review accumulated observations and tensions; triage each | Rethink |
| `:refactor` | Restructure and improve vault organization | Rethink |
| `:tasks` | Show and manage the ops/queue/ task queue | — |
| `:stats` | Vault metrics: note count, orphans, link density, hub sizes | — |
| `:graph [query]` | Graph analysis: orphans, triangles, density, backlinks | — |
| `:next` | Workboard reconciliation — surfaces what needs attention based on vault state | — |
| `:learn [topic]` | Research a topic and grow the knowledge graph | — |
| `:remember [observation]` | Capture friction or methodology learning to ops/observations/ | — |
| `:revisit [note title]` | Revisit and update an old note with current understanding | — |

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

### D-05: Note Quality Standard

**Decision:** A note in `notes/` is "done" when it has all three:

1. **Claim title** — passes the claim test: "This note argues that [title]" reads naturally. Prose-as-title, one insight per file.
2. **`_schema` block** — arscontexta pattern. A fenced block at the end of the note defining the note's type and hub membership:
   ```
   _schema:
     type: permanent | hub | literature | fleeting
     hub: [[Hub Note Title]]
     status: draft | ready
   ```
3. **Wikilinks** — at least one `[[wikilink]]` connecting the note to the graph. Hub notes may have many inbound links; permanent notes should link to their hub and related notes.

`:review` validates all three and returns specific actionable feedback. `:check` does batch validation across `notes/`.

### D-06: Maps of Content (MOCs / Hub Notes)

**Decision:** Hub notes aggregate related claims. They live in `notes/` with a concept title (not a claim title). Hub notes link to permanent notes; permanent notes link back to their hub.

- `:connect [note]` — finds which hub the note belongs to and adds a `[[wikilink]]` to the appropriate hub MOC. If no hub exists yet for the concept, it creates one lazily.
- `:graph` — reports hub membership, orphan notes (no hub membership), and link density.
- `:stats` — includes hub count, avg notes per hub, orphan count.

Hub notes are created lazily — they don't exist until `:connect` decides one is needed.

### D-07: Voice and Personality

**Decision:** The Sentinel's response style when operating in 2nd brain commands is warm, direct, and opinionated. Contractions, shorter sentences, casual tone. Nudges are specific.

Examples:
- "12 notes connected, no orphans. Inbox has 4 items older than 3 days — want to process?"
- "You said you wanted to finish that project. No progress logged this week. What's blocking you?"

### D-08: `:help` Response

**Decision:** `:help` (and `:plugin:help`) return the full command list grouped by category, with a one-line description of each. Show standard commands first, plugin commands second. Include `:reweave` in the standard commands list.

### D-09: Pipeline and Processing (6 Rs)

**Decision:** Notes never go directly to `notes/`. All content routes through `inbox/` first. When the system writes a note, it captures to `inbox/` and creates a queue entry in `ops/queue/`. `:ralph` and `:pipeline` process the queue.

The full processing sequence (arscontexta 6 Rs):
1. **Record** — `:capture`, `:seed`
2. **Reduce** — AI extracts claim, adds `_schema` block, moves from `inbox/` to `notes/`
3. **Reflect** — `:connect` finds hub, adds wikilinks
4. **Reweave** — `:reweave` backward pass; older notes updated with new context
5. **Verify** — `:review`, `:check`
6. **Rethink** — `:rethink`, `:refactor`

`:pipeline` runs all 6 Rs in sequence. `:ralph` runs Reduce + Reflect (the batch processing core).

Exception: session summaries written by the background task go directly to `ops/sessions/` — they are operational logs, not knowledge graph nodes.

### D-10: Migration Scope

**Decision:** Research phase determines which vault directories already exist and which need to be created. Migration tasks are generated per-directory. Existing `core/sessions/` data is moved to `ops/sessions/`. Existing `core/users/{user_id}.md` content is merged into `self/identity.md`. Research agent reads the actual vault to assess current state.

### D-11: BASB/arscontexta Research Mandate

**Decision:** The researcher and planner MUST study the following before planning:

- `https://github.com/agenticnotetaking/arscontexta` — vault storage design, `_schema` block format, 6 Rs pipeline, MOC pattern, session-orient hook
- Tiago Forte's "Building a Second Brain" — PARA method (Projects/Areas/Resources/Archives), CODE framework (Capture/Organize/Distill/Express), just-in-time organization principle
- The synthesis between BASB and arscontexta three-space model (see D-16)

**Hard constraint:** No Anthropic/Claude API integration. All AI processing uses the local LM Studio model via the Pi harness. No `anthropic` SDK, no `claude-*` API calls anywhere in Phase 10 code.

### D-12: `:plugin:` Routing in handle_sentask_subcommand

**Decision:** Route `:plugin:*` commands using a prefix check + separate dict:

```python
if subcmd.startswith("plugin:"):
    plugin_name = subcmd[7:]  # strip "plugin:" prefix
    fixed_prompt = _PLUGIN_PROMPTS.get(plugin_name)
    if fixed_prompt:
        return await call_core(user_id, fixed_prompt)
    return f"Unknown plugin command `:{subcmd}`. Try `:plugin:help` for available commands."
```

`_PLUGIN_PROMPTS` dict mirrors `_SUBCOMMAND_PROMPTS` — maps plugin command names to AI prompts. Same pattern, no new routing layer.

### D-13: `:ralph` Mechanics

**Decision:** `:ralph` sends a single prompt to `call_core()`:

```python
prompt = "Process my inbox queue — work through items in inbox/ and move completed ones to notes/ following the 2nd brain pipeline."
return await call_core(user_id, prompt)
```

No bot-side vault reads, no iteration loop. The AI handles the orchestration using vault context it already has access to. Consistent with all other commands.

### D-14: Vault Stub File Creation

**Decision:** Lazy creation on first write. When the Sentinel tries to write to a path that doesn't exist (e.g. `ops/reminders.md`), it creates the file at that point. Reads always graceful-skip on 404 (per D-02). Zero startup overhead — vault grows organically as it's used.

### D-15: `:reweave` Command

**Decision:** `:reweave` is added as a 27th standard command. It sends:

```python
prompt = "Run a reweave pass on my vault — identify notes that should be updated given recent additions. Update older notes with new context and connections."
return await call_core(user_id, prompt)
```

This maps directly to the arscontexta Reweave step (6 Rs step 4) and BASB's Distill phase. It's the most intellectually rich operation — old knowledge synthesized with new understanding.

### D-16: PARA + arscontexta Synthesis (Claude's Discretion)

**Claude's Discretion:** The researcher synthesizes PARA (Projects/Areas/Resources/Archives) with the arscontexta three-space model (self/notes/ops) and proposes the optimal vault subdirectory structure. Do not create explicit `notes/projects/`, `notes/areas/` folders unless the synthesis strongly calls for it. The guiding principle: vault structure should feel natural, not imposed.

Guidance for the researcher:
- arscontexta three-space is the outer structure (non-negotiable: self/ notes/ ops/)
- PARA's operational concepts (Projects = active work with deadlines, Areas = ongoing responsibilities) likely map to `ops/` subdirectories, not `notes/` subdirectories
- PARA's Resources ≈ `notes/` knowledge graph
- PARA's Archives ≈ `ops/archive/` or simply old sessions

### Claude's Discretion (implementation details)

- Whether to use `httpx.HTTPError` (base class) or enumerate specific httpx exceptions — choose whichever is idiomatic per existing codebase usage
- Exact YAML structure of `_schema` blocks — follow arscontexta format from the repo after research
- Which PARA subdirectories (if any) to create inside `ops/` — defer to D-16 synthesis
- Session-start read parallelism implementation details (`asyncio.gather` + `return_exceptions=True` vs `asyncio.wait`)

</decisions>

<specifics>
## Specific Ideas

- **Kids logistics:** Sensitive data in `self/relationships.md`. Never referenced outside the vault.
- **The claim test for note titles:** "This note argues that [title]" — if it reads naturally, it's a claim.
- **Hub vs permanent distinction:** A hub note's title is a concept ("Mental Models for Decision Making"). A permanent note's title is a claim ("Availability heuristic overpredicts risk in familiar domains").
- **arscontexta session-orient pattern:** On every session start, inject workspace state (active goals, recent notes, reminders). D-02 implements this.
- **Just-in-time organization (BASB principle):** Never schedule cleanup sessions. Organize as a natural consequence of working. Lazy vault creation (D-14) is the structural embodiment of this principle.
- **Local AI constraint:** All processing uses LM Studio via Pi harness. The quality of note reduction, connection finding, and reweave is bounded by the local model's capability — design prompts to work well with smaller models.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read all of these before planning or implementing.**

### Primary research sources (mandatory pre-planning)
- `https://github.com/agenticnotetaking/arscontexta` — vault storage design, `_schema` block format, 6 Rs pipeline, MOC pattern (read README and any architecture docs)
- Tiago Forte BASB: `https://fortelabs.com/blog/basboverview/` — PARA method and CODE framework overview
- Tiago Forte BASB book: `https://archive.org/details/tiago-forte-building.-a.-second.-brain-.-v-2.02.19`

### Sentinel Core integration points
- `sentinel-core/app/clients/obsidian.py` — ObsidianClient: GET/PUT/POST vault endpoints
- `sentinel-core/app/routes/message.py` — POST /message handler: session-start reading and context injection points
- `interfaces/discord/bot.py` — Discord bot: subcommand handler, on_message thread handler, SENTINEL_THREAD_IDS, `_SUBCOMMAND_PROMPTS` dict, `handle_sentask_subcommand()`

### Existing phase context
- `.planning/phases/02-memory-layer/02-CONTEXT.md` — original ObsidianClient decisions, session write pattern
- `.planning/phases/03-interfaces/03-CONTEXT.md` — Discord bot architecture, subcommand routing pattern

### Migration
- Research agent must read the actual Obsidian vault to determine which directories exist and what content needs migration. Vault is at the path configured in `OBSIDIAN_API_URL`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `obsidian.py:get_user_context()` — existing GET `/vault/{path}` call; extend to read `self/*.md` files in parallel
- `obsidian.py:search_vault()` — POST `/search/simple/` with query; used by `:graph`, `:connect`, `:next` for vault queries
- `obsidian.py:write_session_summary()` — PUT `/vault/{path}`; reuse for all vault writes with new paths
- `bot.py:handle_sentask_subcommand()` — existing subcommand router; extend with all 27 new command handlers
- `bot.py:call_core()` — existing POST /message caller; all subcommands use this with constructed prompts
- `bot.py:_SUBCOMMAND_PROMPTS` — dict mapping command names to AI prompts; add `_PLUGIN_PROMPTS` as parallel dict

### Established Patterns
- Discord subcommands use `:prefix` parsed at `message[1:].split(" ", 1)` in `bot.py:217–221`
- Obsidian writes are best-effort (BackgroundTasks, log warning on failure, never fail the HTTP response)
- All context injection is subject to `SESSIONS_BUDGET_RATIO` / token truncation before the token guard
- `asyncio.gather()` for parallel async operations (extend to session-start reads)

### Integration Points
- `message.py:79–82` — retrieve user context + sessions; extend to also read `self/*.md` files in parallel with `asyncio.gather()`
- `bot.py:69–74` — `_SUBCOMMAND_PROMPTS` dict maps command names to AI prompts; extend + add `_PLUGIN_PROMPTS`
- `bot.py:109–127` — `handle_sentask_subcommand()`; add `:plugin:` prefix check before dict lookup
- Thread ID persistence: `SENTINEL_THREAD_IDS` set at `bot.py:52`; needs `ops/discord-threads.md` backing

</code_context>

<deferred>
## Deferred Ideas

- Vector/semantic search (VMEM-01) — v2 requirement
- Auto-updating `self/identity.md` (AI writes back what it learns about the user) — future phase
- Telegram / Slack interface commands — v2
- Multi-user vault separation — single user system in v1
- Git auto-commit hook for vault changes (arscontexta Auto Commit hook) — future phase

</deferred>

---

*Phase: 10-knowledge-migration-tool-import-from-existing-second-brain*
*Context gathered: 2026-04-11*
*Context updated: 2026-04-11 — added D-05 through D-16, :reweave command, BASB/arscontexta research mandate*
