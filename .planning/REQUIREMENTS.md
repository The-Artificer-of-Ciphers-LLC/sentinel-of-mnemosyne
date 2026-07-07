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

- [x] **PVL-01**: First player interaction triggers onboarding capturing character name, preferred form of address, and PF2E Sentinel style preset; persisted to `mnemosyne/pf2e/players/{player_slug}/profile.md`
- [x] **PVL-02**: Players can capture quick notes, questions, todos, and per-NPC knowledge via `:pf player note|ask|npc|todo` commands; writes go to per-player paths only
- [x] **PVL-03**: Player recall (`:pf player recall [query]`) returns deterministic results scoped to the requesting player's vault only — no cross-player data leakage
- [x] **PVL-04**: Yellow rule/homebrew outcomes can be canonized to green or red and recorded in `canonization.md` with provenance back to the originating question
- [x] **PVL-05**: Style presets (`Tactician`, `Lorekeeper`, `Cheerleader`, `Rules-Lawyer Lite` at minimum) influence response formatting; players can list and switch presets via `:pf player style`
- [x] **PVL-06**: Discord identity-to-`player_slug` mapping is deterministic and stable across restarts
- [x] **PVL-07**: Per-player isolation is enforced: a player cannot read another player's notes, questions, or NPC knowledge files

## Foundry Chat Memory Projection (Phase 37)

- [x] **FCM-01**: Imported Foundry chat records are classified into `player | npc | unknown` buckets via deterministic identity normalization
- [x] **FCM-02**: Player-attributed lines project into `mnemosyne/pf2e/players/{player_slug}.md` with sections `## Voice Patterns`, `## Notable Moments`, `## Party Dynamics`, `## Chat Timeline`
- [x] **FCM-03**: NPC-attributed lines append to a `## Foundry Chat History` section on the matching NPC note (created if missing) with timestamp, source marker, and content hash key
- [x] **FCM-04**: Re-running projection on the same source produces zero duplicate entries (dedupe key prefers Foundry `_id`, falls back to hash of `timestamp|speaker|content_normalized|target_note`); state persisted alongside existing `.foundry_chat_import_state.json`
- [x] **FCM-05**: Dry-run mode emits identical projection metrics shape without mutating vault files; live mode returns metrics in API/Discord response (player updates, NPC updates, deduped counts, unmatched speakers)

## Module / Platform

- [ ] **MOD-01**: PF2e module is delivered as a Docker Compose `include` (Path B reference implementation)
- [ ] **MOD-02**: CORS middleware is added to Sentinel Core to allow Foundry browser `fetch()` calls with `X-Sentinel-Key`

## Memory & Recall (v0.5.1 — The Second Brain)

- [x] **MEM-01**: The Sentinel assembles recalled memory for every message through a single Recall module, and the `/context/{user_id}` endpoint uses that same module (no duplicated assembly logic)
- [x] **MEM-02**: Recall policy — relevance threshold, namespace exclusions (including `ops/`), and per-tier context budgets — is consolidated as explicit configuration rather than inline constants
- [x] **MEM-03**: The Sentinel recalls relevant vault content by meaning (semantic/vector search over note embeddings), not only exact keyword matches
- [x] **MEM-04**: Keyword and semantic recall results are merged into one ranked recall set (hybrid retrieval)
- [x] **MEM-05**: Semantic recall reads embeddings from a sweeper-maintained index (no per-note HTTP read at query time) and skips notes whose embedding model no longer matches the active model
- [x] **MEM-06**: The recent-session window is a tunable retention policy rather than a fixed 3-turn / two-day limit
- [x] **MEM-07**: Sessions older than the hot window are recalled via the index instead of being dropped
- [x] **MEM-08**: Session data crosses the Recall interface as typed values, enabling recency-aware merging
- [x] **MEM-09**: Recalled session summaries are weighted by recency in the merge (more recent sessions rank above older ones) using the typed `SessionSummary.date`; recency weighting applies to episodic Session summaries only, never to Self-namespace or authored notes

## Embeddings Gateway (v0.5.2 — Provider Independence)

- [x] **EMB-01**: pf2e-module no longer calls an embeddings endpoint directly — embeddings for its rules index are obtained via sentinel-core (a narrow core embeddings endpoint + `SentinelCoreClient.embed()`); pf2e retains ownership of its rules index and retrieval
- [x] **EMB-02**: sentinel-core is configured with a non-exo embeddings backend that actually serves `/v1/embeddings` for the configured embedding model, selectable independently of the chat `ai_provider` (chat=exo and embeddings=LM Studio can coexist)
- [x] **EMB-03**: `:pf rule` semantic retrieval works end-to-end — the rules index builds and returns relevant rules with no 503 degradation when the embeddings backend is up
- [x] **EMB-04**: core's Phase-40 semantic recall produces/reads embeddings successfully against the same backend, with a dimension-mismatch guard that prevents stale/garbage cosine and no silent empty-index degradation

## VAULT — three-space vault + taxonomy (v0.6.0 — Restore the Second-Brain Core)

- [x] **VAULT-01**: The vault has the three-space arscontexta structure (`self/ notes/ ops/ inbox/ templates/`) with stub files auto-created where missing
- [x] **VAULT-02**: PARA taxonomy supersedes the flat-7 classifier — `learning`/`reference` route to `inbox/` for Reduce-phase transformation; `journal`/`accomplishment`/`observation` file under `ops/` subdirectories
- [x] **VAULT-03**: Semantic recall recency-weighting recognizes the new namespaces (no silent recall degradation when `_CARRIER_NAMESPACE_PREFIXES` moves off flat-7 paths)
- [x] **VAULT-04**: The vault sweeper no longer wholesale-skips `inbox/` — staged captures are embedded (`inbox/` removed from `SWEEP_SKIP_PREFIXES`) so it stops being an unconditional recall blind-spot, while remaining excluded from the keyword warm tier (`RecallConfig.exclude_prefixes`) until Reduce promotes them to `notes/`
- [x] **VAULT-05**: Every message reads the three-space `self/` files at session start (identity, methodology, goals, relationships)

## NOTE — note quality + graph (v0.6.0)

- [x] **NOTE-01**: Notes carry an `_schema` footer block (type + hub membership), a claim-style title, and wikilinks
- [x] **NOTE-02**: Maps of Content (MOC/hub notes) are created lazily and updated as notes join a hub
- [x] **NOTE-03**: The user can run graph analysis (`:graph`/`:stats`/`:check`) to see orphans, backlinks, link density, and `_schema` compliance, backed by a `links-index.json` sidecar

## PIPE — the 6 Rs pipeline (v0.6.0)

- [x] **PIPE-01**: The user can capture with zero friction — `:capture`/`:seed` drop raw content into `inbox/`
- [x] **PIPE-02**: `:ralph` batch-processes the `inbox/` queue (Reduce + Reflect) via single-prompt orchestration, writing `notes/` with `_schema`, wikilinks, and MOC updates
- [x] **PIPE-03**: `:pipeline` runs the full 6 Rs sequence (Record → Reduce → Reflect → Reweave → Verify → Rethink)
- [x] **PIPE-04**: `:reweave` runs a backward pass that updates older notes given recent vault additions (reusing SemanticRecall for candidate discovery)
- [x] **PIPE-05**: `:rethink`/`:refactor` triage accumulated observations and tensions
- [x] **PIPE-06**: Pipeline commands are guarded against concurrent runs (lockfile precedent from the sweeper) and expose run status
- [x] **PIPE-07**: `_schema` quality enforcement happens at the Verify stage, not at capture/Reduce (capture stays frictionless)

## MIG — migration + safety (v0.6.0)

- [x] **MIG-01**: Existing flat-7-classified notes are backfilled into the PARA/`_schema` structure with wikilinks
- [x] **MIG-02**: The embedding sidecar index and wikilink integrity are preserved through migration (no recall regression)
- [ ] **MIG-03**: A MEM-0x + command-surface regression ledger is verified at every phase boundary to prevent the core being gutted again
- [ ] **MIG-04**: Pathfinder module and recall/embeddings remain intact post-migration (existing 404+ test suite stays green)

---

## Future Requirements (deferred)

- Remaster vs pre-Remaster rule comparison — scoped out per user decision; Remaster-only scope reduces hallucination risk
- Voice interface for DM narration — TTS/STT pipeline complexity; out of scope for v1
- NPC combat tracker integration — out of scope for v0.5; belongs in a later combat module
- Encounter builder (balanced encounter by party level) — deferred to future module milestone
- Loot generator (non-harvest) — deferred; harvesting covers monster-specific loot
- Persistent ANN vector index when the vault grows past ~10k notes (RetrievalStrategy adapter swap)
- Per-stage isolated 6 Rs calls ("fresh context per phase" with separate LLM completions per stage) — deferred to a later milestone; v0.6.0 starts with single-prompt orchestration pending a local-model latency benchmark

## Out of Scope

- **Pre-Remaster PF2e / PF1 content** — rules engine explicitly Remaster-only; pre-Remaster rules differ enough to cause dangerous rulings confusion
- **Automated Midjourney DM** — Discord API blocks bot-to-bot DMs; prompt text output is the correct implementation
- **Vector database** — start with Obsidian full-text search; add vectors when quality demands it (from PROJECT.md)
- **Multi-user / multi-campaign** — personal tool; single DM campaign only
- **Re-injecting the Sentinel's own past replies as recalled context** — the `ops/` exclusion stays; feeding the assistant's own output back creates a self-echo/hallucination loop
- **Recency decay on stable vault notes (Self namespace, authored knowledge)** — recency weighting applies only to episodic Session summaries, never to deliberately-authored notes
- **Persistent ANN vector index (hnswlib/faiss/sqlite-vec/chroma)** — an in-memory numpy cosine scan is sufficient at personal-vault scale; the RetrievalStrategy seam allows a later swap without architectural change
- **Operator-tunable RecallConfig via a vault file** — v0.5.1 keeps recall config as code; vault-file tuning is deferred
- **Cross-encoder reranking of recall results** — deferred; RRF hybrid merge is sufficient for v0.5.1
- **Reverting the phase-27 modular architecture or the `pi` removal (v0.6.0)** — we build ON TOP of current architecture

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
| MEM-01 | 39 | Extract the Recall Module |
| MEM-02 | 39 | Extract the Recall Module |
| MEM-03 | 40 | Semantic Recall |
| MEM-04 | 40 | Semantic Recall |
| MEM-05 | 40 | Semantic Recall |
| MEM-06 | 41 | Typed SessionSummary + Retention |
| MEM-07 | 41 | Typed SessionSummary + Retention |
| MEM-08 | 41 | Typed SessionSummary + Retention |
| MEM-09 | 41 | Typed SessionSummary + Retention |
| EMB-01 | 43 | Embeddings Through Sentinel |
| EMB-02 | 43 | Embeddings Through Sentinel |
| EMB-03 | 43 | Embeddings Through Sentinel |
| EMB-04 | 43 | Embeddings Through Sentinel |
| VAULT-01 | 44 | Vault Namespace + Taxonomy Foundation |
| VAULT-02 | 44 | Vault Namespace + Taxonomy Foundation |
| VAULT-03 | 44 | Vault Namespace + Taxonomy Foundation |
| VAULT-04 | 44 | Vault Namespace + Taxonomy Foundation |
| VAULT-05 | 44 | Vault Namespace + Taxonomy Foundation |
| NOTE-01 | 45 | Note-Quality Schema + Graph Analysis |
| NOTE-02 | 45 | Note-Quality Schema + Graph Analysis |
| NOTE-03 | 45 | Note-Quality Schema + Graph Analysis |
| PIPE-01 | 46 | 6 Rs Pipeline Orchestrator |
| PIPE-02 | 46 | 6 Rs Pipeline Orchestrator |
| PIPE-03 | 46 | 6 Rs Pipeline Orchestrator |
| PIPE-04 | 46 | 6 Rs Pipeline Orchestrator |
| PIPE-05 | 46 | 6 Rs Pipeline Orchestrator |
| PIPE-06 | 46 | 6 Rs Pipeline Orchestrator |
| PIPE-07 | 46 | 6 Rs Pipeline Orchestrator |
| MIG-01 | 47 | Migration Cutover + Hardening |
| MIG-02 | 47 | Migration Cutover + Hardening |
| MIG-03 | 47 | Migration Cutover + Hardening |
| MIG-04 | 47 | Migration Cutover + Hardening |
