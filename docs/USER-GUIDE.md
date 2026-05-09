# Sentinel of Mnemosyne — User Guide

This guide covers every shipped Discord command. The Sentinel is a
self-hosted, containerized AI assistant that wires together a local AI
engine, an Obsidian vault, and pluggable interface modules.

Examples in this guide are copy-pasted from real adapter output — when
the wording diverges, the adapter source is canonical (audit lesson from
CONTEXT.md `PHASE37-F`).

## Discord Command Conventions

The Discord interface uses one slash command and a colon-prefix dispatch
inside its threads:

- `/sen <message>` — primary entry point. Creates a public thread per
  invocation; replies inside the thread continue the conversation.
- `:<subcommand>` (inside a `/sen` thread) — second-brain capture/recall
  verbs documented in [/sen Subcommands](#sen-subcommands).
- `:pf <noun> <verb> ...` (inside a `/sen` thread) — Pathfinder 2e module
  commands. Eight nouns are registered: `npc`, `harvest`, `rule`,
  `session`, `ingest`, `cartosia`, `foundry`, `player`. Documented in
  [Pathfinder 2e Commands](#pathfinder-2e-commands).
- Plain text (no `:` prefix) — routed straight to the AI for free-form
  conversation.

## Table of Contents

- [/sen Subcommands](#sen-subcommands)
  - [Standard verbs](#standard-verbs)
  - [Plugin verbs (`:plugin:*`)](#plugin-verbs-plugin)
- [Pathfinder 2e Commands](#pathfinder-2e-commands)
  - [`:pf npc`](#pf-npc) — NPC CRUD, exports, dialogue
  - [`:pf harvest`](#pf-harvest) — monster harvesting reports
  - [`:pf rule`](#pf-rule) — rules lookups and history
  - [`:pf session`](#pf-session) — session start/show/end
  - [`:pf foundry`](#pf-foundry) — Foundry chat import (admin)
  - [`:pf ingest` / `:pf cartosia`](#pf-ingest--pf-cartosia) — archive ingest (admin)
  - [`:pf player`](#pf-player) — per-player memory (Phase 37)

---

## /sen Subcommands

Type these inside a `/sen` thread, prefixed with `:`. Most expect no
arguments and dispatch to the Sentinel's second-brain agent in
`sentinel-core`. Argless verbs return whatever the Sentinel's response
agent produces — exact wording varies. Verbs that require arguments
return a usage hint when called bare.

Special verb: `:pf <noun> <verb> ...` is documented separately under
[Pathfinder 2e Commands](#pathfinder-2e-commands).

### Standard verbs

| Verb | Args | Purpose |
|------|------|---------|
| `:help` | — | List all subcommands grouped by category |
| `:capture <text>` | required | Extract insights from source material; route to `inbox/` |
| `:seed <text>` | required | Drop raw content into `inbox/` with zero processing |
| `:next` | — | Surface what to work on next based on vault state |
| `:health` | — | Vault health: orphan notes, stale goals, neglected gear |
| `:goals` | — | Show current active goals |
| `:reminders` | — | Show current time-bound reminders |
| `:ralph` | — | Batch-process the inbox queue (Reduce + Reflect) |
| `:pipeline` | — | Run the full 6 Rs pipeline (Record → Reduce → Reflect → Reweave → Verify → Rethink) |
| `:reweave` | — | Backward pass: update older notes with recent vault additions |
| `:check` | — | Validate `_schema` compliance across all `notes/` files |
| `:rethink` | — | Review accumulated observations and tensions; triage each |
| `:refactor` | — | Suggest vault restructuring improvements |
| `:tasks` | — | Show the `ops/queue/` task queue |
| `:stats` | — | Vault metrics: note count, orphan count, link density, hub sizes |
| `:graph [query]` | optional | Graph analysis — orphans, triangles, density, backlinks |
| `:learn <topic>` | required | Research a topic and grow the knowledge graph |
| `:remember <observation>` | required | Capture an operational observation to `ops/observations/` |
| `:connect <note title>` | required | Find connections for a note; add wikilink to hub MOC |
| `:review <note title>` | required | Verify note quality (claim title, schema, wikilinks) |
| `:revisit <note title>` | required | Revisit and update an old note |
| `:note <content>` *or* `:note <topic> <content>` | required | Capture a classified note. Closed-vocab topics: `learning`, `accomplishment`, `journal`, `reference`, `observation`, `noise`, `unsure` |
| `:inbox` | — | List unclassified inbox entries |
| `:inbox classify <n> <topic>` | required | Classify inbox entry `n` with the given topic |
| `:inbox discard <n>` | required | Discard inbox entry `n` |
| `:vault-sweep` | admin | Trigger a sweep over `inbox/` and reclassify (admin only — set `SENTINEL_ADMIN_USER_IDS` in env) |
| `:vault-sweep status` | admin | Show in-flight or last sweep status |
| `:vault-sweep dry-run` | admin | Sweep without persisting changes |
| `:vault-sweep force` | admin | Sweep and force reclassification of everything |

**Usage patterns**

```
/sen :help
→ Shows the full subcommand list grouped by Standard / Plugin.

/sen :capture I read that PF2e Strike action targets AC by default.
→ Capture this insight to my inbox/ for processing: I read that PF2e Strike action targets AC by default.
  (the agent processes and replies)

/sen :next
→ Returns the agent's recommendation for what to work on next.

/sen :note learning Discord adapter→route contract drift is invisible to mocked unit tests.
→ Routes the content with topic=learning into the classified-note pipeline.
```

When a required-argument verb is called bare, the bot replies with a
usage hint, e.g.:

```
/sen :capture
→ Usage: `:capture <text>` — provide something to capture.
```

### Plugin verbs (`:plugin:*`)

The `:plugin:*` family addresses the Sentinel's methodology layer (the
"second-brain" framework itself), separate from your day-to-day notes.

| Verb | Args | Purpose |
|------|------|---------|
| `:plugin:help` | — | Contextual guidance on commands and when to use each |
| `:plugin:health` | — | Full vault diagnostics (orphan notes, dangling wikilinks, hub coherence, stale content) |
| `:plugin:ask <question>` | required | Query the methodology knowledge base |
| `:plugin:architect` | — | Research-backed advice for vault evolution |
| `:plugin:setup` | — | Create the initial vault structure (`self/`, `notes/`, `ops/`, `inbox/`, `templates/`) |
| `:plugin:tutorial` | — | Interactive walkthrough of the second-brain system |
| `:plugin:upgrade` | — | Check for methodology improvements |
| `:plugin:reseed` | — | Principled vault restructuring |
| `:plugin:add-domain <domain>` | required | Extend vault with a new domain area |
| `:plugin:recommend` | — | Architecture advice for the current vault state |

Bare invocation of arg-required plugin verbs returns the matching usage
hint (e.g. ``Usage: `:plugin:ask <question>` — query the methodology knowledge base.``).

---

## Pathfinder 2e Commands

`:pf <noun> <verb> ...` — type these inside a `/sen` thread. The `pf2e`
module must be running (`./sentinel.sh --discord --pf2e up -d`). The
parser requires both a noun and a verb; bare `:pf` and `:pf <noun>`
return usage hints.

Eight nouns are registered: `npc`, `harvest`, `rule`, `session`,
`ingest`, `cartosia`, `foundry`, `player`. Unknown nouns reply with
`Unknown pf category \`<noun>\`. Currently supported: ...`.

### `:pf npc`

NPC CRUD plus exports, token tooling, stat blocks, and dialogue. NPCs
persist as YAML-frontmatter notes under `mnemosyne/pf2e/npcs/{npc_slug}.md`.

#### `:pf npc create <name> | <description>`

Generates an NPC profile (ancestry, class, level, stats, personality,
backstory) from a free-text description and writes it to the vault.

```
:pf npc create Varek | Wiry tiefling locksmith with a grudge against the city watch.
→ NPC **Varek** created.
  Path: `mnemosyne/pf2e/npcs/varek.md`
  Ancestry: tiefling | Class: rogue | Level: 4
```

Empty name returns ``Usage: `:pf npc create <name> | <description>` ``.

#### `:pf npc update <name> | <correction>`

Surgical PATCH against the NPC's frontmatter — does not overwrite prose
sections. The correction is free-text; the LLM resolves which fields to
change.

```
:pf npc update Varek | Bump him to level 6 and switch ancestry to half-elf.
→ NPC **Varek** updated. Fields changed: level, ancestry
```

Empty name *or* empty correction returns ``Usage: `:pf npc update <name> | <correction>` ``.

#### `:pf npc show <name>`

Render a multi-line summary embed for an existing NPC.

```
:pf npc show Varek
→ **Varek** (Level 4 tiefling rogue)
  *Wiry, watchful, slow to trust.*
  Grew up in the alley sweeps of Westgate; lost his sister to a
  press-gang and now runs a small fence shop as cover...
  AC 19 | HP 52 | Fort 8 Ref 12 Will 9
  Relationships: Mira (ally), Captain Halrick (enemy)
  *Mood: neutral | mnemosyne/pf2e/npcs/varek.md*
```

Empty name returns ``Usage: `:pf npc show <name>` ``.

#### `:pf npc relate <npc-name> | <relation> | <target-npc-name>`

Add a relationship row to the NPC's frontmatter. The `<relation>` must
be one of the project's valid relation types (e.g. `ally`, `enemy`,
`rival`, `mentor`, `family` — the bridge injects the canonical set).

```
:pf npc relate Varek | ally | Mira
→ Relationship added: **Varek** ally **Mira**.
```

Invalid relation returns ``\`<relation>\` is not a valid relation type. Valid options: <list>``.

Missing parts returns the usage hint.

#### `:pf npc import` (attach a Foundry actor list JSON)

Bulk-import NPCs from a Foundry world export. Attach the JSON file as a
reply in the thread.

```
:pf npc import   (with foundry-actors.json attached)
→ Imported **12** NPC(s).
  Skipped (already exist): Varek, Halrick
```

No attachment returns ``Usage: `:pf npc import` — attach a Foundry actor list JSON file as a reply in this thread.``.

#### `:pf npc export <name>`

Returns a Foundry-importable PF2e actor JSON file as a Discord
attachment.

```
:pf npc export Varek
→ (file attachment: varek.json)
  Foundry actor JSON for **Varek**:
```

Empty name returns ``Usage: `:pf npc export <name>` ``.

#### `:pf npc token <name>`

Returns a Midjourney `/imagine` prompt as plain text — copy/paste it
into your Midjourney workflow.

```
:pf npc token Varek
→ /imagine prompt: portrait of a wiry tiefling rogue, alley shadows,
  ar 2:3 — locksmith's tools at belt, watchful expression, ...
```

Empty name returns ``Usage: `:pf npc token <name>` ``.

#### `:pf npc token-image <name>` (attach the Midjourney PNG)

Once Midjourney has produced the image, attach the PNG as a reply with
the command. The image is stored alongside the NPC profile and embedded
in the PDF stat card.

```
:pf npc token-image Varek   (with varek.png attached)
→ Token image saved for **Varek** (124387 bytes) → `mnemosyne/pf2e/tokens/varek.png`.
  Run `:pf npc pdf Varek` to see it embedded in the stat card.
```

No attachment returns a usage hint scoped to the named NPC. Non-image
attachment returns ``Expected an image attachment (got `<content_type>`). Midjourney exports PNG — re-attach the PNG and try again.``.

#### `:pf npc stat <name>`

Render the NPC stat block as a Discord embed (AC, HP, saves, attacks).

```
:pf npc stat Varek
→ (Discord embed rendered by build_stat_embed — AC, HP, Fort/Ref/Will, attacks, skills)
```

#### `:pf npc pdf <name>`

Returns a printable PDF stat card as a Discord attachment.

```
:pf npc pdf Varek
→ (file attachment: varek-statcard.pdf)
  PDF stat card for **Varek**:
```

#### `:pf npc say <Name>[,<Name>...] | <party line>`

In-character dialogue. One name → one NPC reply. Multiple
comma-separated names → a multi-NPC scene where each NPC replies in
their own voice. The bot reads back recent thread history (up to 50
messages) so dialogue stays in scene.

```
:pf npc say Varek | The guards are at your door — talk fast.
→ (rendered dialogue from Varek with mood/voice from his profile)

:pf npc say Varek, Mira | We need to vanish before sunrise.
→ (multi-NPC scene — distinct replies from each)
```

Missing pipe separator returns ``Usage: `:pf npc say <Name>[,<Name>...] | <party line>` ``.

### `:pf harvest`

Returns a harvest report for one or more monster names: components,
Medicine DCs, craftable potions/poisons/armor with Crafting DCs and
PF2e gp/sp/cp values. The render is a Discord embed.

```
:pf harvest Boar
→ (Discord embed: components, Medicine DCs, craftables)

:pf harvest Boar,Wolf,Orc
→ (aggregated multi-monster report)

:pf harvest Giant Rat
→ (single monster, multi-word name)
```

Bare `:pf harvest` returns ``Usage: `:pf harvest <Name>[,<Name>...]` ``.

For monsters not in the harvest tables, components are AI-generated and
flagged `[GENERATED — verify]`.

### `:pf rule`

Rules lookups against the PF2e Remaster corpus. Four sub-verbs.

> **Required syntax:** the sub-verb must be one of `query`, `list`,
> `show`, `history` — typing `:pf rule what is sneak attack?` parses
> "what" as the verb and replies ``Unknown rule sub-command `what`.``.

#### `:pf rule query <question>`

Look up a rule. Returns a Discord embed with the ruling, marker
(`[SOURCED]` / `[GENERATED — verify]`), and citation.

```
:pf rule query Does Sneak Attack work on grabbed targets?
→ (embed with ruling text, marker, source citation)
```

Bare `:pf rule query` (or bare `:pf rule`) returns
``Usage: `:pf rule <question>` | `:pf rule show <topic>` | `:pf rule history [N]` | `:pf rule list` ``.

#### `:pf rule list`

List all rule topics that have cached rulings.

```
:pf rule list
→ **Rule topics with cached rulings:**
  • `sneak-attack` (3 rulings, last active 2026-05-07T13:22:01)
  • `grappled` (1 rulings, last active 2026-05-04T08:11:44)
  • ...
```

Empty cache returns `_No rulings cached yet._`.

#### `:pf rule show <topic>`

Show every cached ruling under a topic slug.

```
:pf rule show sneak-attack
→ **Rulings under `sneak-attack`** (3):
  • `a1b2c3d4` — Does Sneak Attack work on grabbed targets? [SOURCED]
  • `e5f6a7b8` — Can a familiar trigger Sneak Attack? [GENERATED — verify]
  • ...
```

Empty topic returns ``Usage: `:pf rule show <topic>` ``. Unknown topic
returns ``_No rulings under \`<topic>\`._``.

#### `:pf rule history [N]`

Recent rulings ordered by reuse time. Default N=10, max N=50.

```
:pf rule history 5
→ **Recent rulings (N=5):**
  • 2026-05-07T13:22:01 — `sneak-attack/Does Sneak Attack work on grabbed targets?` → [SOURCED]
  • 2026-05-04T08:11:44 — `grappled/Can a grappled creature take Reactions?` → [SOURCED]
  • ...
```

Empty cache returns `_No rulings yet._`. Non-integer N is silently
clamped to the default.

### `:pf session`

Per-day session notes under `mnemosyne/pf2e/sessions/YYYY-MM-DD.md`.
Three sub-verbs. All return embeds rendered by `build_session_embed`.

#### `:pf session start [<event>] [--force] [--recap] [--retry-recap]`

Open a new session note for today. Free-text after the verb is logged
as the first event.

| Flag | Effect |
|------|--------|
| `--force` | Overwrite an existing session note for today |
| `--recap` | Suppress automatic recap-from-yesterday rendering |
| `--retry-recap` | Re-run the LLM recap after a previous failure |

```
:pf session start The party arrives at the dragon's gate at dusk.
→ (session embed: today's note path, recap-from-yesterday button if a prior ended session exists)

:pf session start --force
→ (session embed for a fresh note, overwriting today's existing one)
```

#### `:pf session show`

Render the current session's note as an embed (events so far, NPC
links, location anchors).

```
:pf session show
→ (session embed)
```

#### `:pf session end [--force]`

Close the current session and trigger recap generation.

```
:pf session end The party retreats; the dragon escapes south.
→ (session embed with recap text and the closed-note path)

:pf session end --force
→ (closes even if validations would normally block)
```

### `:pf foundry`

Foundry VTT bridge commands. One verb shipped.

#### `:pf foundry import-messages <inbox_dir> [--dry-run|--live] [--limit N]` (admin only)

Import a Foundry chat log dump from disk. Dry-run reports counts; live
writes report notes plus per-player and per-NPC projections (see
[Foundry Chat Memory Projection](#foundry-chat-memory-projection)
below).

| Flag | Effect (default: `--dry-run`) |
|------|--------------------------------|
| `--dry-run` | Parse + report counts; vault unchanged |
| `--live` | Actually persist the report note + projections |
| `--limit N` | Cap the number of messages processed |

```
:pf foundry import-messages /vault/inbox --dry-run
→ Foundry chat import dry-run complete.
  Source: `/vault/inbox`
  Report: `mnemosyne/pf2e/sessions/foundry-chat/2026-05-08/report.md`
  Imported: 412 | Invalid: 3
  IC: 287 | Rolls: 64 | OOC: 41 | System: 20
```

Non-admin users get ``Admin only. Set SENTINEL_ADMIN_USER_IDS in your env to use this command.``. Missing `<inbox_dir>` returns the usage hint.

### `:pf ingest` / `:pf cartosia`

Bulk-import a PF2e archive folder (NPCs, locations, sessions, arcs,
factions, etc.) — admin only. `:pf cartosia` is a deprecated alias that
forwards to `:pf ingest archive/cartosia`.

#### `:pf ingest <subfolder> [--live] [--dry-run] [--limit N] [--force] [--confirm-large]`

| Flag | Effect (default: `--dry-run`) |
|------|--------------------------------|
| `--live` | Actually persist; default is `--dry-run` |
| `--limit N` | Cap items processed per kind |
| `--force` | Force reprocessing of items already in vault |
| `--confirm-large` | Required when item count exceeds the safety threshold |

```
:pf ingest archive/saltmarsh --live
→ PF2e archive ingest live import complete.
  Report: `mnemosyne/pf2e/ingest-reports/2026-05-08-saltmarsh.md`
  NPCs: 23 (skipped existing: 5) | Locations: 8 | Homebrew: 2 |
  Harvest: 4 | Lore: 11 | Sessions: 0 | Arcs: 1 | Factions: 3 |
  Dialogue: 6 | Skipped: 0 | Errors: 0
```

Non-admin: same admin-only message as foundry import. Bare invocation
returns the long usage hint.

#### `:pf cartosia <archive_path>` (deprecated)

```
:pf cartosia /archives/cartosia-pack
→ Deprecated: use `:pf ingest archive/cartosia` instead — forwarding...

  PF2e archive ingest dry-run complete.
  Report: `...`
  NPCs: ... | Locations: ... | ...
```

Forwards transparently. Migrate to `:pf ingest archive/cartosia` when
convenient.

### `:pf player`

The `:pf player <verb>` family (Phase 37) gives every Discord user their own
isolated vault namespace at `mnemosyne/pf2e/players/{player_slug}/`. The slug
is derived deterministically from the Discord user id; an optional alias map
at `mnemosyne/pf2e/players/_aliases.json` lets the operator give specific
players readable slugs.

All eight verbs are gated by onboarding — `:pf player start` must run before
`note`/`ask`/`npc`/`recall`/`todo`/`canonize` will accept input. The `style`
verb's `list` action is exempt from the gate so a new player can preview
options before onboarding.

#### `:pf player start`

Onboard yourself. The default flow is a multi-step conversational dialog
hosted in a Discord thread; a one-shot pipe-syntax form is preserved for
power users and scripting. Both paths write `players/{slug}/profile.md`
with `onboarded: true` so the other verbs unlock.

**Valid style presets** (case-sensitive):

- `Tactician` — concise, mechanics-first
- `Lorekeeper` — setting-rich, context-heavy
- `Cheerleader` — encouraging, positive framing
- `Rules-Lawyer Lite` — RAW citations with brief reasoning

##### Multi-Step Onboarding Dialog

Running `:pf player start` with **no arguments** opens a private-feeling
onboarding thread and walks you through three questions. Reply in plain
text inside the thread — the bot does not invoke the AI on your replies,
each one is consumed as the answer to the current step.

**Flow:**

```
:pf player start
→ (bot creates a thread named "Onboarding — <your display name>")
→ What is your character's name?

  Kael Stormblade
→ How would you like me to address you?

  Kael
→ Pick a style: Tactician, Lorekeeper, Cheerleader, Rules-Lawyer Lite

  Tactician
→ Player onboarded as `Kael` (Tactician). Profile: `mnemosyne/pf2e/players/<slug>/profile.md`
   (the thread is then archived)
```

**Restart safety.** The draft persists in the vault at
`mnemosyne/pf2e/players/_drafts/{thread_id}-{user_id}.md` until you
complete or cancel. If the bot restarts mid-dialog, your prior answers
are preserved and the next reply continues where you left off. Re-issuing
`:pf player start` inside the same thread re-asks the current step rather
than restarting from the top.

**Mid-dialog command rejection.** While you have an open dialog, other
`:pf player <verb>` commands (`note`, `ask`, `npc`, `recall`, `todo`,
`style`, `canonize`) are blocked and the bot replies with a link back to
your open thread. Finish the dialog or run `:pf player cancel` to abort.

##### One-Shot Pipe Syntax (alternative)

For scripted onboarding or operator setup, the pipe-separated form skips
the dialog entirely and onboards in a single message:

```
:pf player start <character_name> | <preferred_name> | <style_preset>
```

Example:

```
:pf player start Kael Stormblade | Kael | Tactician
→ Player onboarded as `Kael` (Tactician). Profile: `mnemosyne/pf2e/players/p-<hash>/profile.md`
```

This path does **not** create a thread and does **not** write a draft —
it calls `/player/onboard` directly with the four-field payload. It
remains supported indefinitely.

#### `:pf player cancel`

Abort an open onboarding dialog. Deletes the draft file from the vault,
posts a cancel acknowledgement, and archives the dialog thread.

```
:pf player cancel
→ Cancelled the onboarding dialog.
```

- With **no draft** in progress: the bot replies `No onboarding dialog in progress.`
- With **one draft**: cancels and archives that thread (you may run cancel
  from inside the dialog thread or from any other channel).
- With **multiple drafts** (parallel onboarding in different threads): all
  drafts are cancelled and all corresponding threads archived; the reply
  reads `Cancelled N onboarding dialogs.`

#### `:pf player note <text>`

Append a free-form note to the player's `inbox.md`. v1: store-only — the
Sentinel does not summarize or react.

```
:pf player note Found a hidden door behind the tapestry.
→ Note recorded for player. Inbox: `mnemosyne/pf2e/players/<slug>/inbox.md`
```

#### `:pf player ask <question>`

Queue a rules or lore question for later canonization. v1 contract:
**store-only — no LLM call**. The question persists in `questions.md` until
the operator runs `:pf player canonize` against it.

The route does **not** generate a question_id. The operator picks an id
when canonizing — typically a short slug they invent (e.g. `q-sneak-grab`).

```
:pf player ask Does Sneak Attack work on grabbed targets?
→ Question logged at `mnemosyne/pf2e/players/<slug>/questions.md`. The GM can canonize it via `:pf player canonize`.
```

#### `:pf player npc <npc_name> <note>`

Record per-player NPC knowledge. The note lands at
`players/{slug}/npcs/{npc_slug}.md` and is **never** mixed with the global
`mnemosyne/pf2e/npcs/{npc_slug}.md` note (PVL-07 isolation). The first
whitespace-bounded token is the NPC name; everything after is the note.

```
:pf player npc Varek Allied — owes me a favor from the dragon hunt.
→ Personal note on **Varek** recorded. Path: `mnemosyne/pf2e/players/<slug>/npcs/varek.md`
```

Two players writing different notes about the same NPC produce two distinct
files; neither sees the other's view.

#### `:pf player recall [query]`

Deterministic keyword + recency recall over the player's own namespace. v1:
no LLM, no embeddings — keyword count + recency-weighted scoring. Empty
query returns most-recent notes; a query filters to keyword matches.

```
:pf player recall dragon
→ Recall (3 hits):
  - Found a hidden door behind the tapestry.
  - Allied — owes me a favor from the dragon hunt.
  - ...
```

#### `:pf player todo <text>`

Append a todo line to `players/{slug}/todo.md`.

```
:pf player todo Buy alchemist's fire before next session.
→ Todo recorded. Path: `mnemosyne/pf2e/players/<slug>/todo.md`
```

#### `:pf player style [list | set <preset>]`

Manage the per-player style preset that influences how the assistant
phrases responses. `list` is read-only and exempt from the onboarding
gate; `set` requires onboarding.

```
:pf player style list
→ Available style presets:
  - Cheerleader
  - Lorekeeper
  - Rules-Lawyer Lite
  - Tactician

:pf player style set Lorekeeper
→ Style preset set to **Lorekeeper**.
```

The `set` form persists `style_preset` into `players/{slug}/profile.md`
frontmatter via GET-then-PUT (preserves the rest of the profile).

#### `:pf player canonize <outcome> <question_id> <rule_text>`

Operator-authorized verb that records a rule outcome in
`players/{slug}/canonization.md` with provenance back to a
question. v1: every canonization is operator-driven (no
timeout-based auto-resolution).

**Argument order:** `<outcome>` first, then `<question_id>`, then the
free-form `<rule_text>` (which may contain spaces).

**Valid outcomes:** `yellow`, `green`, `red` (lowercase, exact). Use
`yellow` to mark a question as still ambiguous, `green` for a confirmed
ruling, `red` for an explicit disallow.

```
:pf player canonize green q-sneak-grab Sneak Attack triggers on grabbed targets per RAW.
→ Ruling canonized (green). Path: `mnemosyne/pf2e/players/<slug>/canonization.md`
```

The `question_id` is operator-chosen — there is no auto-generated id from
`:pf player ask`. Pick a short, unique slug that you'll recognize when
reviewing `canonization.md` later.

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

### `:pf rule what is sneak attack?` says "Unknown sub-command"
`:pf rule` requires an explicit verb. Use `:pf rule query <question>`
(or `list`/`show`/`history`). Bare-noun lookup is not supported.

### `:pf <noun> <verb>` returns "Cannot reach the Sentinel"
sentinel-core isn't running. Check `docker ps` for
`sentinel-of-mnemosyne-sentinel-core-1`. If absent, bring the stack up:
`./sentinel.sh --discord --pf2e up -d`.

### Admin-only command says "Admin only..."
Verbs like `:pf foundry import-messages`, `:pf ingest`, `:pf cartosia`,
and `:vault-sweep` require your Discord user id to be in the
`SENTINEL_ADMIN_USER_IDS` env var (comma-separated). Add it to `.env`
and restart the discord container.

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
