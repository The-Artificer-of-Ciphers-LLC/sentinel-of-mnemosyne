# Requirements: v0.5 The Dungeon

**Milestone:** v0.5 — The Dungeon (Pathfinder 2e DM Co-pilot Module)
**Status:** Active
**Defined:** 2026-04-21

---

## NPC Management

- [ ] **NPC-01**: User can create an NPC (name, level, ancestry, class, traits, personality, stats, backstory) via Discord command; stored in Obsidian under `mnemosyne/pf2e/npcs/`
- [ ] **NPC-02**: User can update any field of an existing NPC by name via Discord command
- [ ] **NPC-03**: User can query an NPC by name and receive a summary in Discord
- [ ] **NPC-04**: User can define NPC relationships (knows/trusts/hostile-to) stored in the NPC's Obsidian note
- [ ] **NPC-05**: User can bulk-import NPCs from a Foundry VTT actor list JSON export

## NPC Outputs

- [ ] **OUT-01**: User can export any NPC as a PF2e Remaster-compatible Foundry VTT actor JSON file attachment in Discord
- [ ] **OUT-02**: User can request a Midjourney `/imagine` prompt for an NPC's token art, delivered as copyable text in Discord
- [ ] **OUT-03**: User can view a formatted PF2e stat block for an NPC inline in Discord
- [ ] **OUT-04**: User can export an NPC as a PDF stat card

## Dialogue Engine

- [ ] **DLG-01**: User can send "party says [X]" with an NPC name and receive an in-character reply grounded in that NPC's Obsidian profile
- [ ] **DLG-02**: NPC mood state is tracked per NPC and influences dialogue responses over time
- [ ] **DLG-03**: User can run a multi-NPC dialogue scene where multiple NPCs each reply in their distinct voice

## Monster Harvesting

- [ ] **HRV-01**: User can input a killed monster name and receive a list of harvestable components
- [ ] **HRV-02**: Each harvestable component includes what can be crafted from it (potions, poisons, armor)
- [ ] **HRV-03**: Each craftable item includes its PF2e vendor value (gp/sp/cp)
- [ ] **HRV-04**: Each harvestable component includes a Medicine check DC to successfully harvest it
- [ ] **HRV-05**: Each craftable item includes the Crafting skill DC to create it
- [ ] **HRV-06**: User can input multiple killed monsters and receive aggregated harvest results

## Rules Engine

- [ ] **RUL-01**: User can ask a PF2e Remaster rules question and receive a ruling with source citation
- [ ] **RUL-02**: When no direct Remaster source exists, Sentinel reasons from rules and returns a ruling marked `[GENERATED — verify]`
- [ ] **RUL-03**: Every ruling is saved to `mnemosyne/pf2e/rulings/` for future reuse (same situation not re-adjudicated)
- [ ] **RUL-04**: Rules engine is scoped exclusively to PF2e Remaster; PF1 and pre-Remaster PF2e queries are declined with an explanation

## Session Notes

- [ ] **SES-01**: User can trigger session note capture; a structured note (recap, NPCs encountered, decisions made) is written to `mnemosyne/pf2e/sessions/`
- [ ] **SES-02**: Session notes automatically tag and link to existing NPC and location Obsidian pages
- [ ] **SES-03**: Session events are logged with real-world timestamps during the session

## Foundry VTT Connector

- [ ] **FVT-01**: A Foundry VTT JS module hooks into chat messages and dice rolls and POSTs events to Sentinel Core (authenticated with `X-Sentinel-Key`)
- [ ] **FVT-02**: Sentinel processes incoming Foundry events and sends responses to the DM's Discord channel
- [ ] **FVT-03**: Sentinel interprets roll results in Discord (hit/miss, effect description, DC comparison)
- [ ] **FVT-04**: The Foundry JS module can pull NPC actor JSON directly from Sentinel (pull-based import, no file attachment)

## Player Vault (Phase 37)

- [ ] **PVL-01**: First player interaction triggers onboarding capturing character name, preferred form of address, and PF2E Sentinel style preset; persisted to `mnemosyne/pf2e/players/{player_slug}/profile.md`
- [ ] **PVL-02**: Players can capture quick notes, questions, todos, and per-NPC knowledge via `:pf player note|ask|npc|todo` commands; writes go to per-player paths only
- [ ] **PVL-03**: Player recall (`:pf player recall [query]`) returns deterministic results scoped to the requesting player's vault only — no cross-player data leakage
- [ ] **PVL-04**: Yellow rule/homebrew outcomes can be canonized to green or red and recorded in `canonization.md` with provenance back to the originating question
- [ ] **PVL-05**: Style presets (`Tactician`, `Lorekeeper`, `Cheerleader`, `Rules-Lawyer Lite` at minimum) influence response formatting; players can list and switch presets via `:pf player style`
- [x] **PVL-06**: Discord identity-to-`player_slug` mapping is deterministic and stable across restarts
- [x] **PVL-07**: Per-player isolation is enforced: a player cannot read another player's notes, questions, or NPC knowledge files

## Foundry Chat Memory Projection (Phase 37)

- [x] **FCM-01**: Imported Foundry chat records are classified into `player | npc | unknown` buckets via deterministic identity normalization
- [x] **FCM-02**: Player-attributed lines project into `mnemosyne/pf2e/players/{player_slug}.md` with sections `## Voice Patterns`, `## Notable Moments`, `## Party Dynamics`, `## Chat Timeline`
- [x] **FCM-03**: NPC-attributed lines append to a `## Foundry Chat History` section on the matching NPC note (created if missing) with timestamp, source marker, and content hash key
- [ ] **FCM-04**: Re-running projection on the same source produces zero duplicate entries (dedupe key prefers Foundry `_id`, falls back to hash of `timestamp|speaker|content_normalized|target_note`); state persisted alongside existing `.foundry_chat_import_state.json`
- [ ] **FCM-05**: Dry-run mode emits identical projection metrics shape without mutating vault files; live mode returns metrics in API/Discord response (player updates, NPC updates, deduped counts, unmatched speakers)

## Module / Platform

- [ ] **MOD-01**: PF2e module is delivered as a Docker Compose `include` (Path B reference implementation)
- [ ] **MOD-02**: CORS middleware is added to Sentinel Core to allow Foundry browser `fetch()` calls with `X-Sentinel-Key`

---

## Future Requirements (deferred)

- Remaster vs pre-Remaster rule comparison — scoped out per user decision; Remaster-only scope reduces hallucination risk
- Voice interface for DM narration — TTS/STT pipeline complexity; out of scope for v1
- NPC combat tracker integration — out of scope for v0.5; belongs in a later combat module
- Encounter builder (balanced encounter by party level) — deferred to future module milestone
- Loot generator (non-harvest) — deferred; harvesting covers monster-specific loot

## Out of Scope

- **Pre-Remaster PF2e / PF1 content** — rules engine explicitly Remaster-only; pre-Remaster rules differ enough to cause dangerous rulings confusion
- **Automated Midjourney DM** — Discord API blocks bot-to-bot DMs; prompt text output is the correct implementation
- **Vector database** — start with Obsidian full-text search; add vectors when quality demands it (from PROJECT.md)
- **Multi-user / multi-campaign** — personal tool; single DM campaign only

---

## Traceability

_Filled by roadmapper. Maps each REQ-ID to its implementing phase._

| REQ-ID | Phase | Phase Name |
|--------|-------|------------|
| MOD-01 | 28 | pf2e-module Skeleton + CORS |
| MOD-02 | 28 | pf2e-module Skeleton + CORS |
| NPC-01 | 29 | NPC CRUD + Obsidian Persistence |
| NPC-02 | 29 | NPC CRUD + Obsidian Persistence |
| NPC-03 | 29 | NPC CRUD + Obsidian Persistence |
| NPC-04 | 29 | NPC CRUD + Obsidian Persistence |
| NPC-05 | 29 | NPC CRUD + Obsidian Persistence |
| OUT-01 | 30 | NPC Outputs |
| OUT-02 | 30 | NPC Outputs |
| OUT-03 | 30 | NPC Outputs |
| OUT-04 | 30 | NPC Outputs |
| DLG-01 | 31 | Dialogue Engine |
| DLG-02 | 31 | Dialogue Engine |
| DLG-03 | 31 | Dialogue Engine |
| HRV-01 | 32 | Monster Harvesting |
| HRV-02 | 32 | Monster Harvesting |
| HRV-03 | 32 | Monster Harvesting |
| HRV-04 | 32 | Monster Harvesting |
| HRV-05 | 32 | Monster Harvesting |
| HRV-06 | 32 | Monster Harvesting |
| RUL-01 | 33 | Rules Engine |
| RUL-02 | 33 | Rules Engine |
| RUL-03 | 33 | Rules Engine |
| RUL-04 | 33 | Rules Engine |
| SES-01 | 34 | Session Notes |
| SES-02 | 34 | Session Notes |
| SES-03 | 34 | Session Notes |
| FVT-01 | 35 | Foundry VTT Event Ingest |
| FVT-02 | 35 | Foundry VTT Event Ingest |
| FVT-03 | 35 | Foundry VTT Event Ingest |
| FVT-04 | 36 | Foundry NPC Pull Import |
| PVL-01 | 37 | PF2E Per-Player Memory |
| PVL-02 | 37 | PF2E Per-Player Memory |
| PVL-03 | 37 | PF2E Per-Player Memory |
| PVL-04 | 37 | PF2E Per-Player Memory |
| PVL-05 | 37 | PF2E Per-Player Memory |
| PVL-06 | 37 | PF2E Per-Player Memory |
| PVL-07 | 37 | PF2E Per-Player Memory |
| FCM-01 | 37 | PF2E Per-Player Memory |
| FCM-02 | 37 | PF2E Per-Player Memory |
| FCM-03 | 37 | PF2E Per-Player Memory |
| FCM-04 | 37 | PF2E Per-Player Memory |
| FCM-05 | 37 | PF2E Per-Player Memory |
