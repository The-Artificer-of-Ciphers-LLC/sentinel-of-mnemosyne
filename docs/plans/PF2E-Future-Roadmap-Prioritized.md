# PF2E Future Roadmap (Prioritized)

Prioritized follow-on plan based on completed Foundry import work and current Pathfinder direction.

## Priority 1 — Player Interaction Vault

### Why now
Highest leverage for live play: players capture and recall without interrupting session flow.

### Deliverable
- Implement plan in `docs/plans/PF2E-Player-Interaction-Vault-Plan.md`.

### Dependencies
- Existing PF2E route/Discord command seams.
- Obsidian write/read adapter.

### Success criteria
- Per-player isolated notes.
- Fast capture commands + recall command.
- Full behavioral tests for isolation and idempotency.

---

## Priority 2 — Foundry Timeline Query Module

### Why now
You can import chat; next leverage is retrieval.

### Deliverable
- New `foundry` subcommands:
  - `:pf foundry search <query> [--limit N]`
  - `:pf foundry summarize <query|date-range>`
- Query notes under `mnemosyne/pf2e/sessions/foundry-chat/...`.

### Dependencies
- Imported chat notes from current pipeline.
- Player vault recall conventions (optional alignment).

### Success criteria
- Deterministic search results with source paths.
- Useful summaries for session prep/recall.
- Tests for filtering, date ranges, and empty results.

---

## Priority 3 — NPC Attribution Hardening

### Why now
Prevents memory corruption as player/NPC history projections expand.

### Deliverable
- Deepen speaker-to-NPC match seam.
- Add confidence scoring + unresolved review queue note.

### Dependencies
- Foundry import pipeline.
- NPC note path conventions.

### Success criteria
- Fewer false-positive NPC associations.
- Unmatched/ambiguous attributions captured explicitly.
- Tests for alias collisions and ambiguity handling.

---

## Priority 4 — Session Fusion Module

### Why now
Improves locality: one canonical session artifact instead of scattered notes.

### Deliverable
- Build session fusion that merges:
  - Foundry chat imports
  - PF2E session logs
  - key NPC/player events
- Write fused note per session date.

### Dependencies
- Priority 2 search/summarize foundations.
- Existing session route data.

### Success criteria
- One high-signal session artifact per session.
- Deterministic merge rules.
- Tests for duplicate event suppression and ordering.

---

## Priority 5 — Player Knowledge Boundaries

### Why now
Needed once player memory becomes first-class and richer.

### Deliverable
- Classification for note visibility:
  - `player-known`
  - `table-known`
  - `gm-only`
- Enforce boundary in recall paths.

### Dependencies
- Player Interaction Vault (Priority 1).

### Success criteria
- No cross-boundary leakage in recall.
- Explicit metadata in stored notes.
- Tests for authorization/visibility rules.

---

## Priority 6 — Traffic-Light Canonization Loop (Yellow -> Green/Red)

### Why now
As rules usage grows, unresolved yellow answers create ambiguity. Canonization closes the loop and improves trust.

### Deliverable
- Add a canonization Module for yellow outcomes:
  - Detect `yellow` results from rule/homebrew checks.
  - Run follow-up validation against trusted corpus + homebrew markers.
  - Resolve to:
    - `green` (rules-canon)
    - `red` (homebrew/non-canon/conflict)
- Persist provenance trail and resolution reason.
- Optional Discord follow-up message when resolution completes.

### Dependencies
- Existing rule query/status output shape.
- Session/player note persistence paths.

### Success criteria
- Yellow results are tracked and resolved deterministically.
- Resolution writes include source/provenance and rationale.
- Tests cover yellow->green, yellow->red, and unresolved timeout cases.

---

## Priority 7 — Off-Hours Ruleset Mining + Import

### Why now
Players need fast, trustworthy answers during live sessions. Pre-mining rules off-hours increases retrieval quality and reduces in-session latency.

### Deliverable
- Add scheduled/off-hours mining workflow to ingest PF2E rules content from configured Foundry sources into Pathfinder rules corpus.
- Build/refresh rules index after import so queries are ready before sessions.
- Add provenance metadata (`source`, `imported_at`, `version`, `canon/homebrew tag`).

### Candidate module seams
- `rules_mining_scheduler` (off-hours trigger/orchestration)
- `foundry_rules_extractor` (Foundry data extraction)
- `rules_corpus_importer` (normalization + write)
- `rules_index_refresher` (rebuild embeddings/index)

### Dependencies
- Existing rule route/index flow in `modules/pathfinder/app/main.py` + `app/rules.py`.
- Canonization loop (yellow->green/red) benefits from stronger corpus.

### Success criteria
- Off-hours run completes without manual intervention.
- Imported rules appear in next-session `:pf rule` answers.
- Clear import reports with counts, conflicts, and source provenance.
- Tests cover extraction, normalization, and index refresh.

---

## Priority 8 — Foundry Actor/Party Inbox Import

### Why now
GM-managed actor exports are the cleanest path to keep NPC/party state aligned with Foundry before and between sessions.

### Deliverable
- Add actor import workflow where GM drops Foundry actor data folder into inbox and triggers import.
- Import creates/updates:
  - party roster records
  - actor/NPC notes
  - player-character linkage metadata
- NPC handling policy:
  - attempt match to existing NPCs first
  - if confident match: update existing NPC
  - if no match: create new NPC
  - if ambiguous match: write review queue entry and skip destructive merge
- Define required inbox directory contract and validation.

### Required GM drop structure (v1 proposal)
- Inbox path: `/vault/inbox/foundry-actors/`
- Required files:
  - `actors.db` (or equivalent actor export JSON/NDJSON from Foundry)
  - optional assets folder for portraits/tokens
- Import command:
  - `:pf foundry import-actors /vault/inbox/foundry-actors --dry-run|--live`

### Candidate module seams
- `foundry_actor_import_orchestrator`
- `foundry_actor_source_probe`
- `actor_normalizer`
- `party_roster_projector`
- `npc_matcher` (existing-NPC match and confidence)
- `npc_merge_policy` (update/create/review decision)
- `actor_import_dedupe_store`

### Dependencies
- Existing NPC import/update paths in Pathfinder module.
- Player vault profile linkage from Player Interaction plan.

### Success criteria
- Dry-run validates folder/files and returns import preview.
- Live run creates/updates actor + party notes deterministically.
- NPCs are matched to existing records when possible; otherwise created safely.
- Ambiguous NPC matches are surfaced for GM review (no silent bad merges).
- Re-runs are idempotent (dedupe keys + stable updates).
- Tests cover schema validation, NPC match/merge policy, projection, and rerun behavior.

---

## Priority 9 — Import Ops Dashboard Note

### Why now
Operational observability for long-running campaigns and repeated imports.

### Deliverable
- Auto-write/import run summaries under ops namespace with:
  - imported count
  - deduped count
  - invalid count
  - attribution misses
  - source snapshots

### Dependencies
- Current import result shape.
- Optional: attribution stats from Priority 3.

### Success criteria
- Every import run leaves an auditable ops note.
- Easy troubleshooting without digging container logs.

---

## Recommended slice order
1. Complete Priority 1 (Player Interaction Vault).
2. Ship Priority 2 minimal search.
3. Add Priority 3 attribution hardening.
4. Build Priority 4 session fusion.
5. Introduce Priority 5 boundaries.
6. Add Priority 6 canonization loop.
7. Add Priority 7 off-hours rules mining.
8. Add Priority 8 actor/party inbox import.
9. Add Priority 9 dashboard polish.

## Suggested implementation cadence
- **M1:** Priority 1
- **M2:** Priority 2 + 3
- **M3:** Priority 4
- **M4:** Priority 5 + 6
- **M5:** Priority 7
- **M6:** Priority 8
- **M7:** Priority 9

## Notes for GSD import
- This roadmap is intentionally milestone-shaped and can be decomposed into vertical slices directly.
- Use the existing plan docs as source artifacts:
  - `docs/plans/PF2E-Player-Interaction-Vault-Plan.md`
  - `docs/plans/PF2E-Foundry-Chat-Memory-Plan.md`
