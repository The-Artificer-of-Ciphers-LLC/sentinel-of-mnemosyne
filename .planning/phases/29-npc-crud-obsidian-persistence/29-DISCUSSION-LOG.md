# Phase 29: NPC CRUD + Obsidian Persistence — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-22
**Phase:** 29-npc-crud-obsidian-persistence
**Areas discussed:** Discord command routing, NPC create input UX, Obsidian note schema, Foundry bulk import, NPC update syntax, NPC relate syntax, NPC show embed format, Vault PATCH location

---

## Discord Command Routing

| Option | Description | Selected |
|--------|-------------|----------|
| A — /pf app_commands.Group in bot.py | Proper slash commands with autocomplete; Core proxy carries the request; single CommandTree | |
| B — :pf prefix inside /sen | Extend existing colon-prefix router; zero Discord API changes; not a slash command | ✓ |
| C — Separate Cog in pathfinder container | Module self-contained; breaks single-token/single-CommandTree constraint | |

**User's choice:** B — `:pf` prefix inside `/sen`
**Notes:** User prefers minimal Discord API surface and consistency with the existing prefix pattern. The success criteria's `/pf npc create` notation is treated as naming convention, not a strict slash command requirement. Added follow-up: CRUD dispatches directly to module endpoints (not through AI pipeline) — user confirmed.

---

## NPC Create Input UX

| Option | Description | Selected |
|--------|-------------|----------|
| A — Name-only, AI fills stubs | Fastest in-session flow; DM edits Obsidian between sessions | |
| B — Discord modal (5 key fields) | Structured input for critical fields; one popup per create | |
| C — Freeform description string | Natural DM verbal style; AI parses into frontmatter fields | ✓ |
| D — Multi-step wizard | Collects all fields; too much in-session friction | |

**User's choice:** C — freeform description string
**Notes:** User added: "allow for random selection if a feature isn't described from known ancestries." This means unspecified fields are randomly filled from PF2e Remaster valid options (ancestry, class, traits) — not left blank.

---

## Obsidian Note Schema

| Option | Description | Selected |
|--------|-------------|----------|
| A — Minimal frontmatter | Name/level/ancestry/class only; stats in prose | |
| B — Full structured frontmatter | All 30+ fields in frontmatter; every field PATCHable; Phase 30 reads directly | |
| C — Split: identity frontmatter + fenced stats block | Small frontmatter; stats in ```yaml block; stat updates are full-block PUT | ✓ |

**User's choice:** C — split schema (selected via visual preview)
**Notes:** Frontmatter: name, level, ancestry, class, traits, personality, backstory, mood, relationships, imported_from. Stats in `## Stats` fenced yaml block. Slug: `slugify(name)` only. Collision check: GET before create, return 409 if exists.

---

## Foundry Bulk Import

| Option | Description | Selected |
|--------|-------------|----------|
| File attachment + identity fields only | Natural DM workflow; schema-safe for Phase 30; discord.py Attachment.read() | ✓ |
| File attachment + full stat block | Richer notes but builds on unverified Phase 30 schema | |
| Paste-based inline JSON | Discord 2000-char limit kills bulk lists | |
| File path reference | Bypasses Discord; path variance by OS | |

**User's choice:** File attachment + identity fields only (Recommended)
**Notes:** Consistent with STATE.md ADR — Foundry PF2e JSON schema derivation is Phase 30's job. Importer extracts name, level, ancestry, class, traits and defensively ignores unknown keys.

---

## NPC Update Syntax

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit key=value | `:pf npc update Varek level=7` — precise, no AI | |
| Freeform AI-parsed correction | Same pattern as create; AI extracts which fields changed | ✓ |
| Positional (field then value) | Ambiguous for multi-word values | |

**User's choice:** Freeform AI-parsed correction
**Notes:** Consistent with create UX — DM uses same natural-language style for updates as for create.

---

## NPC Relate Syntax + Relationship Types

| Option | Description | Selected |
|--------|-------------|----------|
| Open set — any label | Maximum flexibility; stored as-is | |
| Closed set — fixed PF2e-relevant types | Enum: knows/trusts/hostile-to/allied-with/fears/owes-debt; validated at input | ✓ |

**User's choice:** Closed set — fixed PF2e-relevant types
**Notes:** Enum: `knows | trusts | hostile-to | allied-with | fears | owes-debt`. Invalid type returns error embed listing valid options.

---

## NPC Show Embed Format

| Option | Description | Selected |
|--------|-------------|----------|
| Identity only | Name/level/ancestry/class/personality/relationships; stats omitted | |
| Identity + key stats summary | Adds AC, HP, Perception, saves as embed fields | ✓ |

**User's choice:** Identity + key stats summary
**Notes:** Stats fields omitted from embed if the stats block is absent (e.g., identity-only NPC).

---

## Vault PATCH Location

| Option | Description | Selected |
|--------|-------------|----------|
| Pathfinder module calls Obsidian directly | Own httpx client; OBSIDIAN_BASE_URL + OBSIDIAN_API_KEY env vars; no Core changes | ✓ |
| Add PATCH to sentinel-core, expose via Core route | Centralizes vault access; adds Core API surface per operation type | |
| Add Obsidian client to shared/ package | Clean DRY but grows shared/ into a library | |

**User's choice:** Pathfinder module calls Obsidian directly (Recommended)
**Notes:** "Fat module" pattern — modules own their domain integrations. sentinel-core API surface stays stable.

---

## Claude's Discretion

- LLM prompt templates for NPC create extraction and update diff parsing
- Internal router file structure within pathfinder module
- Pydantic model shapes for NPC request/response
- Stats block section heading (user preview showed `## Stats`)

## Deferred Ideas

- Full Foundry stat block extraction from bulk import — Phase 30
- True Discord slash command group for `/pf` — future polish phase
- NPC combat tracker integration — future milestone
- Mood state auto-transitions from dialogue history — Phase 31
