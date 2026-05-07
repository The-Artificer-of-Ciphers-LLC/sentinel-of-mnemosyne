# Phase 37: PF2E Per-Player Memory - Context

**Gathered:** 2026-05-06
**Status:** Ready for planning
**Source:** PRD Express Path (`docs/plans/PF2E-Per-Player-Memory-Combined.md`, derived from `PF2E-Player-Interaction-Vault-Plan.md` + `PF2E-Foundry-Chat-Memory-Plan.md`)

<domain>
## Phase Boundary

Phase 37 delivers per-player vault memory for the PF2E Pathfinder module, with two coordinated writers sharing one schema:

1. **Player Interaction Vault** — Discord-driven capture/recall: onboarding, notes, questions, per-NPC knowledge, todos, style presets, and yellow→green/red rule canonization. Per-player isolated namespace at `mnemosyne/pf2e/players/{player_slug}/`.
2. **Foundry Chat Memory Projection** — Post-import deterministic projection of Foundry chat records into per-player chat maps (`players/{player_slug}.md`) and `## Foundry Chat History` sections on existing NPC notes. Idempotent via dedupe state.

Both writers use a single shared `player_identity_resolver.py` so Discord-driven and Foundry-driven writes for the same physical player land under the same `player_slug`.

Wave 0 RED tests are written before the implementation slice that turns them green (TDD mode is on for this project).

</domain>

<decisions>
## Implementation Decisions

### Architecture & Module Layout
- Two deep modules: `modules/pathfinder/app/player_interaction_orchestrator.py` and `modules/pathfinder/app/foundry_memory_projection.py`.
- Shared seam `modules/pathfinder/app/player_identity_resolver.py` consumed by both modules.
- FCM-only seams: `npc_matcher.py`, `memory_projection_store.py`.
- Existing Foundry import flow (`modules/pathfinder/app/foundry_chat_import.py`) gets a post-extraction call into the projection module.

### Vault Schema (authoritative for Phase 37)
- Per-player namespace root: `mnemosyne/pf2e/players/{player_slug}/`
  - `profile.md` (onboarding output: character_name, preferred_name, style_preset, onboarded flag)
  - `inbox.md`, `questions.md`, `canonization.md`, `todo.md`
  - `npcs/{npc_slug}.md` (per-player NPC knowledge)
  - `sessions/{yyyy-mm-dd}.md`
- Player map root: `mnemosyne/pf2e/players/{player_slug}.md` — sections `## Voice Patterns`, `## Notable Moments`, `## Party Dynamics`, `## Chat Timeline`.
- NPC chat history: append `## Foundry Chat History` section to existing `mnemosyne/pf2e/npcs/{npc_slug}.md` (Phase 29 path); create section if missing.

### Identity & Slug Derivation
- `player_slug` is deterministic and stable across restarts.
- Discord input path: derive `player_slug` from Discord user ID (deterministic hash) with optional alias-override mapping.
- Foundry input path: resolve speaker token → `player | npc | unknown`; player → reuse the same slug derivation (with alias-override able to bridge Foundry actor name to Discord user).
- Identity resolver is a single seam used by both writers — divergence is a bug.

### Discord Commands (Pathfinder dispatcher)
- `:pf player start` (or implicit on first use)
- `:pf player note <text>`
- `:pf player ask <question>` — v1: store-only, no LLM call (LLM-answered ask deferred)
- `:pf player npc <npc_name> <note>`
- `:pf player recall [query]`
- `:pf player todo <text>`
- `:pf player style [list|set <preset>]`
- `:pf player canonize <yellow_ref> <green|red> [reason]` — operator-authorized 8th verb (added 2026-05-06 to satisfy PVL-04 with player-driven trigger; complements `POST /player/canonize` route)

### Routes (modules/pathfinder)
- `POST /player/onboard`, `POST /player/note`, `POST /player/ask`, `POST /player/npc`, `POST /player/recall`, `POST /player/todo`, `POST /player/style`, `GET /player/state`.
- Existing `POST /foundry/import` extended with `--project-player-maps` (default true) and `--project-npc-history` (default true); response gains projection metrics block.

### Style Presets (initial)
- `Tactician` (concise, mechanics-first)
- `Lorekeeper` (setting-rich, context-heavy)
- `Cheerleader` (supportive, motivational)
- `Rules-Lawyer Lite` (strict canon emphasis, low flavor)
- Custom presets deferred.

### Dedupe & Idempotency
- Projection key recipe: prefer Foundry `_id`; fallback to `hash(timestamp|speaker|content_normalized|target_note)`.
- State persisted alongside existing `.foundry_chat_import_state.json` with new arrays `player_projection_keys` and `npc_projection_keys`.
- Re-running projection on the same source MUST produce zero duplicate writes — verified by integration test.

### Per-Player Isolation
- A player cannot read another player's notes/questions/NPC knowledge files. Enforced in the recall engine and store seam, covered by regression tests.
- GM/admin cross-player vault read is **deferred** (not in v1 scope).

### Dry-Run Contract
- Dry-run mode emits identical projection metrics shape without mutating any vault file.
- Live mode response includes: player updates, NPC updates, deduped counts, unmatched speakers.

### TDD
- Project default `workflow.tdd_mode=true`. Every new command/route/projection behavior gets a Wave 0 RED test BEFORE the implementation slice that turns it green.

### Claude's Discretion (planner choices)
- Exact slice/wave packaging (suggested 9 waves in PRD; planner may reorganize).
- Test fixture organization under `modules/pathfinder/tests/`.
- Pydantic model exact shape for `PlayerInteractionRequest/Result`, `ProjectionInput/Result/Stats`.
- Whether to introduce a `players_state.json` registry or rely on directory presence to detect onboarding completion.
- Concrete recall scoring heuristic (deterministic; no LLM in v1).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source PRDs (read all three)
- `docs/plans/PF2E-Per-Player-Memory-Combined.md` — Authoritative merged PRD for Phase 37 (use this first)
- `docs/plans/PF2E-Player-Interaction-Vault-Plan.md` — Original Player Interaction Vault PRD
- `docs/plans/PF2E-Foundry-Chat-Memory-Plan.md` — Original Foundry Chat Memory PRD

### Project-level decisions
- `.planning/PROJECT.md` — Core Value, Validated requirements, Out of Scope (note: multi-user OOS was invalidated 2026-05-06 specifically for Phase 37 per-player support)
- `.planning/REQUIREMENTS.md` — PVL-01..07, FCM-01..05 (defined for this phase)
- `CLAUDE.md` — project guardrails (Spec-Conflict Guardrail, Test-Rewrite Ban, Behavioral-Test-Only Rule, AI Deferral Ban) — all apply

### Existing module the projection extends
- `modules/pathfinder/app/foundry_chat_import.py` — current Foundry import flow; projection hooks in after record extraction
- `modules/pathfinder/app/` — existing routes/services pattern; new player routes follow the established style
- `modules/pathfinder/tests/` — pytest layout; Wave 0 RED tests land here

### Existing NPC note shape (FCM appends to these)
- `mnemosyne/pf2e/npcs/{npc_slug}.md` — Phase 29 contract; FCM adds `## Foundry Chat History` section, must not disturb existing sections

### Discord pathfinder dispatcher
- `interfaces/discord/` — existing `:pf` command dispatcher; `player` noun added per command list above

### Roadmap dependencies
- Phase 29 (NPC CRUD + Obsidian Persistence) — defines NPC note shape FCM extends
- Phase 35 (Foundry VTT Event Ingest) — provides incoming chat record stream
- Phase 36 (Foundry NPC Pull Import — in progress) — sibling, no direct coupling

</canonical_refs>

<specifics>
## Specific Ideas

- **Vault layout diagram** in the merged PRD (`docs/plans/PF2E-Per-Player-Memory-Combined.md` § "Vault layout") is authoritative for any planner output.
- **Identity resolver returns** one of: `("player", player_slug)`, `("npc", npc_slug)`, `("unknown", raw_token)` — projection skips `unknown` but increments an unmatched-speaker stat.
- **Onboarding gate**: until `profile.md` shows `onboarded: true` (frontmatter), `:pf player <verb>` other than `start`/`style` should redirect into onboarding completion.
- **Deterministic recall (v1)**: simple keyword match + recency weighting over the player's namespace files; no embeddings, no LLM. v2 (deferred) can layer embeddings on top.
- **Existing dedupe state file**: `.foundry_chat_import_state.json` lives in the Foundry import working area; extend in place rather than creating a parallel state file (prevents drift).

</specifics>

<deferred>
## Deferred Ideas

- LLM-answered `:pf player ask` (v1 stores question only).
- LLM summarization in chat memory projection (v1 deterministic only).
- Custom user-defined style presets.
- GM/admin cross-player vault read & moderation UI.
- Embedding-based recall.
- Cross-campaign player profiles.
- Review-queue note for unmatched Foundry speakers (planner may include if cheap; default deferred).
- Retrospective rewrite of pre-Phase-37 PF2E notes outside the new memory targets.

</deferred>

---

## Architecture Map

*Appended 2026-05-07 by plan 37-14 closeout.*

### Two Deep Modules

The Phase 37 implementation lands as two coordinated writers around a shared
identity seam:

- **`modules/pathfinder/app/player_interaction_orchestrator.py`** — Discord-
  driven capture/recall: onboarding, notes, questions, per-NPC knowledge,
  todos, style presets, and yellow→green/red canonization. Reads/writes
  `mnemosyne/pf2e/players/{slug}/*` exclusively.

- **`modules/pathfinder/app/foundry_memory_projection.py`** — Post-import
  deterministic projection of Foundry chat records into per-player chat maps
  (`players/{slug}.md`) and `## Foundry Chat History` sections on existing
  NPC notes. Idempotent via per-target dedupe keys in
  `.foundry_chat_import_state.json`.

### Shared Seams

- `player_identity_resolver.py` — single source of truth for
  `slug_from_discord_user_id` and `resolve_foundry_speaker`. Both writers
  consume it; divergence would be a bug.
- `player_vault_store.py` — slug-prefix-isolation gate. Every read/write
  goes through `_resolve_player_path`, which validates slug shape and
  asserts the resulting path lives under `players/{slug}/`. PVL-07 is
  enforced here.
- `player_recall_engine.py` — deterministic keyword + recency scorer used
  by `POST /player/recall`. Defensive prefix guard rejects any
  `list_directory` result outside the requesting slug's tree.
- `vault_markdown.py` — frontmatter formatter shared by all writers.
- `memory_projection_store.py` — per-player chat-map (4 canonical sections)
  and per-NPC `## Foundry Chat History` writers.
- `npc_matcher.py` — alias → npc_slug with vault-probe fallback.

### Discord Adapter

- `interfaces/discord/pathfinder_player_adapter.py` — translates the eight
  `:pf player <verb>` commands into REST calls against the pathfinder
  module. Stateful state (onboarding step) is keyed off the vault, not
  Discord history.

### Routes (modules/pathfinder)

| Method | Path | Purpose | Plan |
|--------|------|---------|------|
| POST | `/player/onboard` | Create profile.md (PVL-01) | 37-07 |
| POST | `/player/note` | Append to inbox.md (PVL-02) | 37-08 |
| POST | `/player/ask` | Append to questions.md, store-only (PVL-02) | 37-08 |
| POST | `/player/npc` | Per-player NPC knowledge (PVL-07) | 37-08 |
| POST | `/player/todo` | Append to todo.md | 37-08 |
| POST | `/player/recall` | Deterministic recall (PVL-03) | 37-09 |
| POST | `/player/canonize` | yellow→green/red rule (PVL-04) | 37-10 |
| POST | `/player/style` | List/set preset (PVL-05) | 37-07 |
| GET  | `/player/state` | Read profile state | 37-07 |
| POST | `/foundry/messages/import` | Foundry import + projection (FCM-01..05) | 37-12 |

### Vault Layout

```
mnemosyne/pf2e/
├── players/
│   ├── _aliases.json                          # operator alias overrides
│   ├── {slug}.md                              # per-player chat map (FCM)
│   └── {slug}/
│       ├── profile.md                         # onboarding output
│       ├── inbox.md                           # :pf player note
│       ├── questions.md                       # :pf player ask
│       ├── canonization.md                    # :pf player canonize
│       ├── todo.md                            # :pf player todo
│       ├── npcs/{npc_slug}.md                 # :pf player npc (PVL-07)
│       └── sessions/{yyyy-mm-dd}.md           # session journals
└── npcs/
    └── {npc_slug}.md                          # global NPC note
                                               # ## Foundry Chat History
                                               # appended by FCM-03
```

### Test Files → Requirement Mapping

| Requirement | Test file(s) |
|-------------|--------------|
| PVL-01 onboarding | `test_player_routes.py::test_post_onboard_*` |
| PVL-02 note/ask/todo capture | `test_player_routes.py::test_post_note_*`, `test_post_ask_*`, `test_post_todo_*` |
| PVL-03 deterministic recall | `test_player_recall_engine.py`, `test_player_routes.py::test_post_recall_*` |
| PVL-04 canonization | `test_player_routes.py::test_post_canonize_*` |
| PVL-05 style preset | `test_player_routes.py::test_post_style_*` |
| PVL-06 deterministic slug | `test_player_identity_resolver.py` |
| PVL-07 cross-player isolation | `test_player_vault_store.py`, `test_player_recall_engine.py`, **`test_player_isolation.py`** (E2E regression) |
| FCM-01 identity classifier | `test_player_identity_resolver.py::test_resolve_foundry_speaker_*` |
| FCM-02 player chat map | `test_memory_projection_store.py::test_write_player_map_*` |
| FCM-03 NPC chat history | `test_memory_projection_store.py::test_append_npc_history_*` |
| FCM-04 idempotency | `test_projection_idempotency.py`, **`test_phase37_integration.py`** (E2E) |
| FCM-05 dry-run contract | `test_foundry_memory_projection.py::test_dry_run_*`, **`test_phase37_integration.py::test_foundry_import_dry_run_then_live_writes_once`** |

End-to-end tests added in plan 37-14 (bold above) exercise the full route
stack with a recording obsidian mock; they catch contract drift between the
route wrappers and the seam APIs that unit tests miss.

### Closeout Notes

- Plan 37-14 surfaced and fixed a real bug in the plan-37-12 route wrapper:
  `routes/foundry._identity_resolver` was typed and coded to accept a
  record dict, but `foundry_memory_projection.project_foundry_chat_memory`
  invokes it with the already-extracted speaker token (string). The bug
  was silent — every Foundry import classified all speakers as "unknown"
  and produced zero player/npc projection updates. The end-to-end test in
  `test_phase37_integration.py` exposed the regression that no Wave 7 unit
  test caught.
- Two pre-existing pathfinder test failures remain on main (logged in
  `deferred-items.md`): `test_foundry.py` NameError and
  `test_registration.py` stale 16-route assertion. Both are out of scope
  for Phase 37 and require separate operator-authorized fixes (Test-Rewrite
  Ban applies to the registration test).

---

*Phase: 37-pf2e-per-player-memory*
*Context gathered: 2026-05-06 via PRD Express Path*
*Architecture map appended: 2026-05-07 (plan 37-14 closeout)*
