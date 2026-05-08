# Sentinel of Mnemosyne — User Guide

This guide covers user-facing commands across the Sentinel's modules. The
Sentinel is a self-hosted, containerized AI assistant that wires together a
local AI engine, an Obsidian vault, and pluggable interface modules.

## Discord Command Conventions

The Discord interface dispatches commands by leading prefix:

- `:m ...` — core memory / dialogue
- `:pf ...` — Pathfinder 2e module commands
- `:npc ...` — NPC CRUD and dialogue verbs (Phase 29-31)

Each command returns a single Discord message; multi-step flows (like
onboarding) are stateful in the vault, not in chat.

## PF2E Player Commands

The `:pf player <verb>` family (Phase 37) gives every Discord user their own
isolated vault namespace at `mnemosyne/pf2e/players/{player_slug}/`. The slug
is derived deterministically from the Discord user id; an optional alias map
at `mnemosyne/pf2e/players/_aliases.json` lets the operator give specific
players readable slugs.

All eight verbs are gated by onboarding — `:pf player start` must run before
`note`/`ask`/`npc`/`recall`/`todo`/`canonize` will accept input. The `style`
verb's `list` action is exempt from the gate so a new player can preview
options before onboarding.

### `:pf player start`

Onboard yourself. Provide your character name, preferred name, and style
preset as **pipe-separated arguments**. Writes `players/{slug}/profile.md`
with `onboarded: true` so the other verbs unlock.

**Syntax:**

```
:pf player start <character_name> | <preferred_name> | <style_preset>
```

**Example:**

```
:pf player start Kael Stormblade | Kael | Tactician
→ Player onboarded as `Kael` (Tactician). Profile: `mnemosyne/pf2e/players/p-<hash>/profile.md`
```

**With no arguments**, the bot returns a usage hint listing valid style
presets — it does **not** call the route or partially onboard you.

**Valid style presets** (case-sensitive):

- `Tactician` — concise, mechanics-first
- `Lorekeeper` — setting-rich, context-heavy
- `Cheerleader` — encouraging, positive framing
- `Rules-Lawyer Lite` — RAW citations with brief reasoning

> **Coming in Phase 38:** a stateful conversational dialog will replace the
> one-shot pipe syntax — the bot will ask the three questions across
> separate messages. The pipe-args form will continue to work for power
> users who prefer a single command. See `.planning/ROADMAP.md` Phase 38.

### `:pf player note <text>`

Append a free-form note to the player's `inbox.md`. v1: store-only — the
Sentinel does not summarize or react.

```
:pf player note Found a hidden door behind the tapestry.
→ "noted."
```

### `:pf player ask <question>`

Queue a rules or lore question for later canonization. v1 contract:
**store-only — no LLM call**. The question persists in `questions.md` until
the operator runs `:pf player canonize` against it.

```
:pf player ask Does Sneak Attack work on grabbed targets?
→ "queued (question_id=q-1710000000)"
```

### `:pf player npc <npc_name> <note>`

Record per-player NPC knowledge. The note lands at
`players/{slug}/npcs/{npc_slug}.md` and is **never** mixed with the global
`mnemosyne/pf2e/npcs/{npc_slug}.md` note (PVL-07 isolation).

```
:pf player npc "Varek" Allied — owes me a favor from the dragon hunt.
→ "noted at players/<slug>/npcs/varek.md"
```

Two players writing different notes about the same NPC produce two distinct
files; neither sees the other's view.

### `:pf player recall [query]`

Deterministic keyword + recency recall over the player's own namespace. v1:
no LLM, no embeddings — keyword count + recency-weighted scoring. Empty
query returns most-recent notes.

```
:pf player recall dragon
→ Returns up to 10 ranked snippets from players/<slug>/* with score + path.
```

### `:pf player todo <text>`

Append a todo line to `players/{slug}/todo.md`.

```
:pf player todo Buy alchemist's fire before next session.
→ "todo added."
```

### `:pf player style [list | set <preset>]`

Manage the per-player style preset that influences how the assistant
phrases responses (Tactician / Lorekeeper / Cheerleader / Rules-Lawyer
Lite). `list` is read-only and exempt from the onboarding gate; `set`
requires onboarding.

```
:pf player style list
→ "Tactician, Lorekeeper, Cheerleader, Rules-Lawyer Lite"

:pf player style set Lorekeeper
→ "style set: Lorekeeper"
```

### `:pf player canonize <question_id> <green|red> [reason]`

Operator-authorized 8th verb (added 2026-05-06). Records a yellow→green or
yellow→red rule outcome in `players/{slug}/canonization.md` with provenance
back to the originating `question_id` from `:pf player ask`. v1: NO
timeout-based auto-resolution — every canonization is operator-driven.

```
:pf player canonize q-1710000000 green Sneak Attack triggers on grabbed targets per RAW.
→ "canonized: q-1710000000 → green"
```

## Onboarding Flow

A typical first-session flow for a new player:

1. (Optional) Run `:pf player style list` to preview the four style
   presets. This works without onboarding because `list` is gate-exempt.
2. Run `:pf player start <character_name> | <preferred_name> | <style_preset>`
   in any Discord channel where the Pathfinder bot is present. The bot
   replies with the path to the newly created `profile.md`.
3. Begin capturing memory: `:pf player note ...`, `:pf player npc ...`,
   `:pf player ask ...`.
4. The operator (GM) periodically runs `:pf player canonize <q_id> green|red`
   to lock yellow questions into per-player canon.
5. Across sessions, `:pf player recall <topic>` surfaces past notes ranked
   by keyword + recency.

**Re-running `:pf player start`** is idempotent — it overwrites
`profile.md` with the latest values. Use this to change your character
name or preferred name. Use `:pf player style set <preset>` to change
just the style preset without re-typing the other fields.

## Foundry Chat Memory Projection

When the Foundry VTT module exports a chat log, the operator can run:

```
POST /foundry/messages/import {"inbox_dir": "/vault/inbox", "dry_run": true}
```

Dry-run mode reports projection metrics (player_updates, npc_updates,
unmatched_speakers, deduped counts) without touching the vault. A live run
projects each chat record into:

- `players/{slug}.md` — the per-player chat-map (sections: Voice Patterns,
  Notable Moments, Party Dynamics, Chat Timeline).
- `npcs/{npc_slug}.md` — appends a row to `## Foundry Chat History` on
  existing NPC notes (created if missing).

Idempotency is per-record per-target — re-running a live import on the
same inbox produces zero new writes (FCM-04). The dedupe state is stored
in-place at `<inbox_dir>/.foundry_chat_import_state.json` with three
arrays: `imported_keys`, `player_projection_keys`, `npc_projection_keys`.

## Troubleshooting

### `:pf player start` says "Usage:..."
You called it with no arguments. Provide all three pipe-separated fields:

```
:pf player start <character_name> | <preferred_name> | <style_preset>
```

### `:pf player start` says "Invalid style preset"
The preset is case-sensitive and must be one of: `Tactician`,
`Lorekeeper`, `Cheerleader`, `Rules-Lawyer Lite`. Note the hyphen in
"Rules-Lawyer Lite".

### `:pf player note` (or any verb) says "onboard first"
The onboarding gate is closed. Run `:pf player start ...` to write your
profile. The orchestrator checks `players/{slug}/profile.md` for
`onboarded: true` before any non-`start`/non-`style-list` verb.

### Recall returns nothing
`:pf player recall` only searches **your** namespace at
`players/{slug}/*`, never the global vault. If you've never written a
note, ask, npc record, or todo, recall has nothing to find. Empty query
returns most-recent items; a query filters by keyword.

### Two players seem to share an NPC note
They don't. Each `:pf player npc <name> <note>` writes to
`players/{slug}/npcs/{npc_slug}.md` — a per-player file. The global NPC
note at `mnemosyne/pf2e/npcs/{npc_slug}.md` is owned by the GM
(`:npc create` / `:npc update`) and is never written by `:pf player`
verbs.

## See Also

- `docs/foundry-setup.md` — Foundry VTT module installation.
- `.planning/REQUIREMENTS.md` — full PVL-* / FCM-* requirement IDs.
- `.planning/phases/37-pf2e-per-player-memory/37-CONTEXT.md` — Phase 37
  architecture map and decision history.
