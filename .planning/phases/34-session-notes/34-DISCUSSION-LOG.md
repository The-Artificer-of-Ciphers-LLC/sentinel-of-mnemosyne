# Phase 34: Session Notes - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-25
**Phase:** 34-session-notes
**Areas discussed:** Session lifecycle + command surface, Event log model, NPC + Location link resolution, Recap + session note shape, LLM model selection, Discord button + interactive components, Schema evolution, Telemetry

---

## Session lifecycle + command surface

### Verb set

| Option | Description | Selected |
|--------|-------------|----------|
| start / log / end / show | Minimum + show — shows live event log mid-session | ✓ (initially) |
| start / log / end only | Strictly the 3 verbs in the roadmap | |
| start / log / end / show / cancel | Adds `cancel` to abort without writing recap | |
| You decide | Pick verbs matching codebase conventions | |

**User's choice:** start / log / end / show (extended later to include `undo` from event-log discussion → final set: start, log, end, show, undo)

### Active-session state model

| Option | Description | Selected |
|--------|-------------|----------|
| Frontmatter `status: open` + append-on-log | Session note IS the state; PATCH-append events; survives restart | ✓ |
| In-memory dict keyed by guild_id | Fastest; container restart loses logged events | |
| Marker file `.active.yaml` | Hidden file holds running buffer | |

**User's choice:** Frontmatter `status: open` + append-on-log

### Collision policy when today's session note exists

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse with helpful embed | Different message for status:open vs status:ended; --force creates -2.md | ✓ |
| Auto-suffix to YYYY-MM-DD-2.md | Silent increment | |
| Auto-end previous and start new | Aggressive; risk of unintended finalization | |

**User's choice:** Refuse with helpful embed

### `:pf session end` reply shape

| Option | Description | Selected |
|--------|-------------|----------|
| Short embed: path + counts | Terse; matches NPC create confirmation | ✓ |
| Full recap text inline + path | Recap visible in Discord channel | |
| Just a check reaction | Minimum noise | |

**User's choice:** Short embed: path + counts

### `:pf session show` shape

| Option | Description | Selected |
|--------|-------------|----------|
| Embed with last N events + counts | Static log view | ✓ (with significant elaboration — see Notes) |
| Full event log inline | Spammy after 50+ events | |
| Just the Obsidian path | Cheapest, no Discord visibility | |

**User's choice:** Embed (option 1) BUT stylized with AI — "recap conversations with NPCs, recap fights, don't just dump the log, use the log to make a fun recap 'the story so far' type of response"
**Notes:** This redirected the area significantly — `:pf session show` now requires an LLM call producing a third-person past-tense storyteller narrative, not a static log dump. Decision propagated into D-18, D-19, D-20.

### Obsidian unreachable at start

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse with diagnostic embed | No session started, surface base_url | ✓ |
| Buffer in memory until Obsidian recovers | Fragile, contradicts state model | |
| Allow start, fail on first log | Confusing UX | |

**User's choice:** Refuse with diagnostic embed

### Recap inputs (memory for the storyteller LLM)

| Option | Description | Selected |
|--------|-------------|----------|
| Event log only | Simplest, cheapest, fastest | ✓ (with significant elaboration — see Notes) |
| Event log + same-day :pf npc say threads | Verbatim NPC dialogue, requires Discord history crawl | |
| Event log + linked NPC notes | Adds personality/mood/backstory flavor | (folded into the chosen approach) |

**User's choice:** "want to be as robust as possible on recap and show. when starting a new session, ask if I want you to recap the last session. We want to be a story teller, but summary, to help people remember as it could be weeks or more between sessions. so would want the log and notes to reflect what would help that. also would want to log the story so far and the end of session recap so that you could make an entire story of the adventure for them to read"
**Notes:** This vision-level reply expanded scope around recap quality (storyteller voice, durable across weeks-between-sessions), recap-on-start (button-prompted), persisting story-so-far (D-19), and a future campaign-narrative compiler (deferred per scope guard). MVP recap inputs locked at: event log + linked NPC frontmatter (D-30). Discord-thread crawling stays deferred.

### Recap caching for `:pf session show`

| Option | Description | Selected |
|--------|-------------|----------|
| Always regenerate | Simple, always reflects latest events | ✓ |
| Cache, invalidate on next `log` | Saves repeat LLM calls | |
| Cache, regenerate every N events | Stale window | |

**User's choice:** Always regenerate

### Recap on `:pf session start` (auto/manual)

| Option | Description | Selected |
|--------|-------------|----------|
| Always show prior-session recap on start | Zero friction; reads frontmatter recap field | (folded into the chosen approach as a togglable setting) |
| Ask first via Discord button | One-click consent, introduces discord.ui.View pattern | ✓ (default) |
| Opt-in flag `:pf session start --recap` | Explicit | ✓ (also available) |

**User's choice:** "2 and 3 with 1 being something you can turn on/off"
**Notes:** Default is button-prompt (option 2). Always-available flag is `--recap` (option 3). A persistent setting `SESSION_AUTO_RECAP=true|false` (D-10) makes recap automatic without the button (option 1 as a toggle). All three paths captured.

### Campaign-narrative compiler scope

| Option | Description | Selected |
|--------|-------------|----------|
| Defer to a follow-up phase | Phase 34 stores recaps in frontmatter; future phase compiles | ✓ |
| Include a `:pf session story` verb in this phase | Adds ~1 plan; output format/length decisions needed | |

**User's choice:** Defer to follow-up phase

---

## Event log model

### Log shape

| Option | Description | Selected |
|--------|-------------|----------|
| Freeform with optional `type:` prefix | Recognized types: combat/dialogue/decision/discovery/loot/note | ✓ |
| Strict typed: `<type> | <text>` | Always require type | |
| Pure freeform, no types | LLM infers category | |

**User's choice:** Freeform with optional `type:` prefix

### Timestamps

| Option | Description | Selected |
|--------|-------------|----------|
| Real wall-clock only | UTC stored, local rendered, SESSION_TZ env var | ✓ |
| Wall-clock + optional in-game date marker | "Calistran 14, evening" | |
| Wall-clock only, in-game time deferred | Equivalent to option 1 with explicit deferral | |

**User's choice:** Real wall-clock only (in-game time explicitly deferred per option 3 wording)

### Persistence

| Option | Description | Selected |
|--------|-------------|----------|
| PATCH append under `## Events Log` heading | One Obsidian roundtrip, survives restart | ✓ |
| GET-then-PUT whole file | 2 roundtrips, safer if PATCH-append surprises | |
| In-memory buffer + flush on end | Fastest log; rejected by lifecycle decision | |

**User's choice:** PATCH append under `## Events Log` heading

### Per-event line format

| Option | Description | Selected |
|--------|-------------|----------|
| `- HH:MM [type] text` markdown bullet | Bracketed type, omitted when default | ✓ |
| `HH:MM — type: text` plain line | Em-dash separator, no bullet | |
| Per-event YAML block | Most structured, hardest to read | |

**User's choice:** `- HH:MM [type] text` markdown bullet

### Length cap

| Option | Description | Selected |
|--------|-------------|----------|
| Single-line, max ~500 chars | Hard limit, newlines rejected | ✓ |
| Multi-line allowed, no hard cap | Flexible; harder to format | |
| Multi-line allowed, soft 2000-char cap | Compromise | |

**User's choice:** Single-line, max ~500 chars

### Edit/undo

| Option | Description | Selected |
|--------|-------------|----------|
| No edit/no undo in MVP | Append-only audit log | |
| Add `:pf session undo` (removes last event) | Adds 5th verb; race condition risk | ✓ |
| Add `:pf session edit <idx>` | Most flexible; requires indices in `show` | |

**User's choice:** Add `:pf session undo`

### Undo reply

| Option | Description | Selected |
|--------|-------------|----------|
| Echo removed line + count remaining | Easy to re-log if mistakenly undone | ✓ |
| Just a check reaction | Risky — can't verify | |
| Embed with last 3 events after removal | More context; bigger reply | |

**User's choice:** Echo removed line + count remaining

### Undo edge cases

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse with helpful embed | Distinct messages for no-session vs empty-log | ✓ |
| Silently no-op | Misleading | |

**User's choice:** Refuse with helpful embed

---

## NPC + Location link resolution

### When NPC linking happens

| Option | Description | Selected |
|--------|-------------|----------|
| Both: scan at log + final pass at end | Real-time visibility + LLM safety net | ✓ |
| Only at session-end (one LLM pass) | Simpler; no mid-session linking | |
| Only at log-time (slug match only) | Fast but brittle on aliases | |

**User's choice:** Both: scan at log + final pass at end

### NPC match strategy at log-time

| Option | Description | Selected |
|--------|-------------|----------|
| Exact word-boundary match against slug + name field | Conservative, low false-positive | ✓ |
| Slug + frontmatter aliases list | Requires Phase 29 schema growth | |
| Fuzzy match (Levenshtein ≤2) | Catches typos, false-positive risk | |

**User's choice:** Exact word-boundary match against slug + name field

### Location handling for SES-02

| Option | Description | Selected |
|--------|-------------|----------|
| Ship unresolved wikilinks + auto-stub creation | Wikilinks + minimal frontmatter stubs under mnemosyne/pf2e/locations/ | ✓ |
| Ship unresolved wikilinks only | Red links, DM creates location notes manually | |
| Defer locations entirely — NPC links only | Doesn't satisfy SES-02 literally | |

**User's choice:** Ship unresolved wikilinks + auto-stub creation

### Location detection

| Option | Description | Selected |
|--------|-------------|----------|
| LLM extraction at session-end only | Same end-of-session LLM pass extracts locations | ✓ |
| Slug match + stub creation at log-time | Defeats SES-02 for brand-new locations | |
| Capitalized-noun heuristic | Noisy; double-tags NPCs | |

**User's choice:** LLM extraction at session-end only

---

## Recap + session note shape

### Note shape

| Option | Description | Selected |
|--------|-------------|----------|
| Frontmatter + Recap + Story-So-Far + NPCs + Locations + Events Log | Full 5-section structure | ✓ |
| Frontmatter + Recap + Events Log only | Lean; arrays-only NPCs/locations | |
| Frontmatter + Recap + Events Log + NPCs only (defer locations subsection) | Like option 1 minus Locations | |

**User's choice:** Full 5-section structure

### End LLM call shape

| Option | Description | Selected |
|--------|-------------|----------|
| Single LLM call producing all needed outputs | One prompt, JSON-schema constrained | ✓ |
| Two-stage: extract entities first, then narrate | More robust to large logs | |
| Three-stage: events → entities → recap → per-NPC | Overkill for v1 | |

**User's choice:** Single LLM call producing all needed outputs

### Storyteller voice

| Option | Description | Selected |
|--------|-------------|----------|
| DM third-person past-tense narrative | TV-recap style, evocative but factual | ✓ |
| Bullet-point summary with bolded subjects | Skimmable; less storytelling | |
| Mixed: opening paragraph + bullet beats | Compromise | |
| Configurable env var | Default + SESSION_RECAP_STYLE knob | |

**User's choice:** DM third-person past-tense narrative

### Recap length cap

| Option | Description | Selected |
|--------|-------------|----------|
| 300-500 words | Soft cap; fits 2-4 paragraphs | |
| 100-200 words | Tight; fits Discord embed without truncation | |
| Unbounded — LLM picks based on event count | Scales with session length | ✓ |

**User's choice:** Unbounded — LLM picks based on event count

### LLM failure at end

| Option | Description | Selected |
|--------|-------------|----------|
| Write skeleton note + retry hint | Session closes; retry via flag later | ✓ |
| Refuse to end — keep session open | Blocks closure if LM Studio dead | |
| Write fallback recap from raw events | Deterministic; poor quality | |

**User's choice:** Write skeleton note + retry hint

### `--retry-recap` flag

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — reads existing note's events log, regenerates | Recovers from failures days later | ✓ |
| No — retry only via in-memory cached events | Simpler; brittle | |
| No — final recap is final | Most strict; loses recoverability | |

**User's choice:** Yes — reads existing note's events log, regenerates

---

## LLM model selection

| Option | Description | Selected |
|--------|-------------|----------|
| New `SESSION_RECAP_MODEL` env var, default to LITELLM_MODEL | Optional override; mirrors RULES_EMBEDDING_MODEL | ✓ |
| Reuse `LITELLM_MODEL` directly | One model for everything | |
| Hard-code to a project-default model | Removes flexibility | |

**User's choice:** New `SESSION_RECAP_MODEL` env var, default to LITELLM_MODEL

---

## Discord button + interactive components

### Button timeout

| Option | Description | Selected |
|--------|-------------|----------|
| Edit message to 'Timed out — use --recap to recap later' | 180s default; new session already started | ✓ |
| Cancel the new session | Aggressive | |
| Auto-recap after timeout | Risky — unwanted recap | |

**User's choice:** Edit message to 'Timed out — use --recap to recap later'

---

## Schema evolution

| Option | Description | Selected |
|--------|-------------|----------|
| `schema_version: 1` field + best-effort forward read | Defensive reads, version-tagged | ✓ |
| No version field, defensive readers | Cheapest; fragile on renames | |
| Migration script + version bump | Most thorough; high effort per change | |

**User's choice:** `schema_version: 1` field + best-effort forward read

---

## Telemetry

| Option | Description | Selected |
|--------|-------------|----------|
| Standard structured logs: lifecycle + LLM + Obsidian failures | Match Phase 33 logger.info/warning patterns | ✓ |
| Standard logs + per-recap LLM token count | Adds cost trending visibility | |
| Minimal: errors only | Hardest to debug | |

**User's choice:** Standard structured logs: lifecycle + LLM + Obsidian failures

---

## Claude's Discretion

- Exact `discord.ui.View` subclass shape and button callback registration; persistent vs ephemeral views
- Whether `SESSION_AUTO_RECAP` lives as env var or `mnemosyne/pf2e/sessions/.config.yaml`
- Exact LLM prompts (system + user) for `:pf session show` and `:pf session end`
- JSON-schema enforcement mechanism (LiteLLM `response_format: json_schema` vs prompt-only)
- Whether `_pf_dispatch` parses flags inline or sends `flags: {}` object to the route
- Internal pathfinder router file structure (`app/routes/session.py`) and pydantic models
- Timezone env var name and default (`SESSION_TZ`, default `America/New_York`?)
- How `## NPCs Encountered` notes merge when an NPC appears in multiple events
- Whether `:pf session undo` uses heading-replace PATCH or GET-then-PUT

## Deferred Ideas

- Campaign-narrative compiler verb (cross-session story aggregation)
- Locations CRUD module (Phase 29-equivalent for locations)
- In-game time / calendar markers
- Edit-by-index for events (`:pf session edit <idx>`)
- Phase 31 thread-history integration into recap inputs
- NPC frontmatter `aliases:` field
- Token-count telemetry for recap LLM cost tracking
- Per-location stub enrichment (auto-update body with sessions list)
- Migration script tooling for schema bumps
