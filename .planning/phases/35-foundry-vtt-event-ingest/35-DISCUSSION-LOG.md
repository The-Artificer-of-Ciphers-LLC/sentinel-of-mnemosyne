# Phase 35: Foundry VTT Event Ingest — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-25
**Phase:** 35-foundry-vtt-event-ingest
**Areas discussed:** Event scope, Discord delivery path, Roll data payload, Foundry module repo home

---

## Event scope

| Option | Description | Selected |
|--------|-------------|----------|
| PF2e-typed rolls only | preCreateChatMessage hook + flags.pf2e inspection — forwards attacks, saves, skills. ~40 lines JS. | ✓ |
| All dice rolls | Single preCreateChatMessage hook, no filtering. Backend classifies roll types. | |
| Trigger-prefixed chat only | DM types trigger prefix manually. Does not satisfy live event stream goal. | |

**User's choice:** PF2e-typed rolls only (recommended)
**Notes:** Easy upgrade path to all-rolls later by relaxing the flag-inspection guard.

**Follow-up — Chat trigger prefix:**

| Option | Description | Selected |
|--------|-------------|----------|
| !s | Short, fast to type. | |
| !sentinel | Explicit, less likely to clash with other macros. | |
| Configurable in world settings | DM sets the prefix in Foundry world config alongside X-Sentinel-Key. | ✓ |

**User's choice:** Configurable in world settings

---

## Discord delivery path

| Option | Description | Selected |
|--------|-------------|----------|
| Internal HTTP endpoint on bot.py | bot.py gains a lightweight internal HTTP route. Pattern-consistent with all other pf2e embeds. | ✓ |
| Discord webhook URL | pathfinder POSTs directly to a webhook. Bypasses bot; second credential. | |
| Route through sentinel-core | Adds a hop and significant new scope at Phase 35. | |

**User's choice:** Internal HTTP endpoint on bot.py (recommended)

**Follow-up — Target channel:**

| Option | Description | Selected |
|--------|-------------|----------|
| Configured env var FOUNDRY_DISCORD_CHANNEL_ID | Dedicated channel for Foundry events. | |
| Same channel as all other pf2e commands | No new config. All pf2e output in one place. | ✓ |

**User's choice:** Same channel as all other pf2e commands

---

## Roll data payload

| Option | Description | Selected |
|--------|-------------|----------|
| PF2e pre-computed result | flags.pf2e.context.outcome + actor/target/type/DC. Backend narrates, doesn't calculate. | ✓ |
| Raw roll total + DC + type | Backend re-implements pf2e's DoS ladder. System-agnostic but duplicates pf2e logic. | |
| Full PF2e message JSON | 100-300+ fields; fragile schema coupling. | |

**User's choice:** PF2e pre-computed result (recommended)

**Follow-up — LLM narration:**

| Option | Description | Selected |
|--------|-------------|----------|
| Plain embed without LLM | Format degree-of-success into text. Fast, free, reliable. | |
| LLM narrative for roll events | One dramatic sentence per roll. e.g. "Seraphina's blade found the gap in the warchief's armor." | ✓ |
| Plain embed by default, LLM on demand | Narrate button per embed. More complex. | |

**User's choice:** LLM narrative for roll events

---

## Foundry module repo home

| Option | Description | Selected |
|--------|-------------|----------|
| modules/pathfinder/foundry-client/ | Subdirectory of pf2e module. FastAPI serves module.json + zip. Phase 36 co-located. | ✓ |
| foundry-module/ at root | Isolated top-level directory. Third taxonomy category. | |
| interfaces/foundry/ | Parallel to interfaces/discord/. Breaks Docker-container-only pattern. | |

**User's choice:** modules/pathfinder/foundry-client/ (recommended)

---

## Claude's Discretion

- aiohttp vs FastAPI sub-app for bot.py internal HTTP listener
- Internal port for bot.py HTTP listener and compose.yml network exposure
- Exact Foundry v14 `game.settings.register` API shape for world settings
- `module.json` v14 manifest fields and `esmodules` array format
- Whether ESModule format requires a bundler in Foundry v14
- Zip structure Foundry expects for installable module packages
- Outcome emoji mapping (proposed: 🎯 criticalSuccess, ✅ success, ❌ failure, 💀 criticalFailure)
- LLM prompt refinement for 20-word narrative sentence
- How pathfinder discovers the bot.py internal URL (env var `DISCORD_BOT_INTERNAL_URL`)
- Whether `preCreateChatMessage` should return false or just read passively

## Deferred Ideas

- Phase 36: NPC pull-import button in Foundry actor directory
- Roll history / session context analytics
- Foundry → Sentinel combat tracker (HP, turn order, conditions)
- All-rolls event scope relaxation
- Player-visible Discord notifications
- Foundry → Obsidian real-time combat log
