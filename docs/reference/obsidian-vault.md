# Obsidian vault reference

**Type:** Reference (Diataxis)
**Version audit:** Sentinel Core `v0.51.1`, Pathfinder module `v1.1.2`

Sentinel uses an Obsidian vault as its system of record. The vault remains plain markdown owned by the operator. Sentinel Core and modules access it through the Obsidian Local REST API, and Pathfinder also mounts the vault at `/vault` for archive and Foundry import flows.

---

## Core Vault Paths

All paths are relative to the vault root.

| Path | Owner | Purpose |
|---|---|---|
| `sentinel/persona.md` | Operator | Runtime persona prompt. Required when Obsidian is reachable at Core startup |
| `self/identity.md` | Operator | Identity and long-lived self context |
| `self/methodology.md` | Operator | Knowledge-working methodology |
| `self/goals.md` | Operator | Current goals and active threads |
| `self/relationships.md` | Operator | People and relationship context |
| `ops/reminders.md` | Operator/Core | Time-bound reminders |
| `ops/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md` | Core | Session summaries written after exchanges |
| `ops/sweeps/` | Core | Vault sweep reports |
| `ops/observations/` | Core/Discord command prompts | Operational observations |
| `inbox/` | Core | Low-confidence or raw captures awaiting classification |
| `notes/` | Core/operator | Classified knowledge notes |
| `core/users/{user_id}.md` | Core compatibility | Legacy per-user context path read by `get_user_context` |

---

## Persona Contract

`sentinel/persona.md` is the operator-controlled Sentinel voice file.

Startup behaviour:

| Condition | Behaviour |
|---|---|
| Obsidian reachable and `sentinel/persona.md` exists | Core starts and uses the vault persona |
| Obsidian reachable and `sentinel/persona.md` is missing | Core fails startup with a setup error |
| Obsidian unreachable at startup | Core starts degraded and uses the fallback persona |
| Persona read fails during a message | The message still proceeds with fallback persona and a warning log |

Edit this file in Obsidian to change Sentinel's voice without rebuilding or restarting containers.

---

## Recall Inputs

On each `/message` request, Core assembles recall context from:

| Source | Notes |
|---|---|
| Persona/self context | Includes persona and configured self-context files |
| Reminders | `ops/reminders.md` |
| Recent sessions | Hot window defaults to the most recent 3 sessions over 2 days |
| Warm recall | Semantic recall over searchable notes within the context budget |

The assembled context is budgeted against the active model's context window before the provider call.

---

## Core Writes

### Session summaries

Path:

```text
ops/sessions/{YYYY-MM-DD}/{user_id}-{HH-MM-SS}.md
```

Typical shape:

```markdown
---
timestamp: 2026-06-16T12:00:00+00:00
user_id: 123456789012345678
model: gemma-4-e4b-it-mlx
---

## User

<user message>

## Sentinel

<assistant response>
```

### Classified notes and inbox

The note intake pipeline classifies substantive content into a closed vocabulary used by the Discord `:note` and inbox commands:

```text
learning
accomplishment
journal
reference
observation
noise
unsure
```

Classifier outcomes:

| Outcome | Effect |
|---|---|
| `filed` | Writes a topic-organised note |
| `inboxed` | Appends an item to `inbox/` for review |
| `dropped` | Drops low-value noise without filing |

The Discord inbox commands call Core's `/inbox`, `/inbox/classify`, and `/inbox/discard` routes.

---

## Sweep Safety

Vault sweep flows skip or protect operator-critical namespaces.

Default sweep skip prefixes include:

```text
_trash/
pf2e/
mnemosyne/
core/
self/
templates/
archive/
security/
ops/sessions/
ops/sweeps/
inbox/
.obsidian/
```

Protected namespaces that Core refuses to move or trash:

```text
sentinel/
self/
security/
```

Live sweeps also require runtime model readiness. Dry-runs do not mutate the vault.

---

## Pathfinder Vault Layout

The Pathfinder module writes under:

```text
mnemosyne/pf2e/
```

Primary paths:

| Path | Purpose |
|---|---|
| `mnemosyne/pf2e/npcs/{npc_slug}.md` | Global GM-owned NPC profiles |
| `mnemosyne/pf2e/tokens/{npc_slug}.png` | NPC token images uploaded from Discord |
| `mnemosyne/pf2e/rulings/` | Cached PF2e rulings |
| `mnemosyne/pf2e/sessions/YYYY-MM-DD.md` | Session notes |
| `mnemosyne/pf2e/sessions/foundry-chat/` | Foundry chat import reports |
| `mnemosyne/pf2e/ingest-reports/` | PF2e archive import reports |
| `mnemosyne/pf2e/players/_aliases.json` | Optional Discord user id to readable slug mapping |
| `mnemosyne/pf2e/players/_drafts/` | Multi-step onboarding drafts |
| `mnemosyne/pf2e/players/{player_slug}.md` | Foundry chat-map projection for a player |
| `mnemosyne/pf2e/players/{player_slug}/profile.md` | Player onboarding profile |
| `mnemosyne/pf2e/players/{player_slug}/inbox.md` | Player notes |
| `mnemosyne/pf2e/players/{player_slug}/questions.md` | Player questions |
| `mnemosyne/pf2e/players/{player_slug}/canonization.md` | Operator canonized rulings |
| `mnemosyne/pf2e/players/{player_slug}/todo.md` | Player todos |
| `mnemosyne/pf2e/players/{player_slug}/npcs/{npc_slug}.md` | Player-specific NPC knowledge |

Per-player routes enforce path-prefix isolation so one player's writes do not land in another player's namespace or in the global NPC namespace.

---

## Foundry Chat Import State

Foundry chat imports read a filesystem inbox mounted at `/vault` inside the Pathfinder container. The import state is stored beside the source inbox:

```text
<inbox_dir>/.foundry_chat_import_state.json
```

The state tracks:

| Key | Purpose |
|---|---|
| `imported_keys` | Records parsed and classified |
| `player_projection_keys` | Records projected into player chat maps |
| `npc_projection_keys` | Records projected into NPC notes |

Re-running a live import on the same inbox should produce zero duplicate writes for records already present in the state.

---

## Backward Compatibility

`core/users/{user_id}.md` remains a compatibility read path for older per-user context. New operator identity context should live in `sentinel/`, `self/`, and `ops/`.
