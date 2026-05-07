# PF2E Foundry Chat Memory Deepening Plan

## Purpose
Add a deep Module in the Pathfinder Sentinel module that turns imported Foundry chat into durable player memory maps and NPC history updates with strong de-duplication and testable seams.

## Outcomes
1. Build per-player chat maps from imported Foundry chat records.
2. Detect NPC-authored chat lines and append them to that NPC’s dialogue/history timeline.
3. Preserve idempotency (safe reruns, no duplicate writes).
4. Keep behavior observable and testable through explicit Interfaces.

## Domain terms (for CONTEXT alignment)
- **Player map**: a per-player memory note summarizing voice, topics, relationships, and notable moments sourced from imported chat.
- **NPC chat memory**: dialogue/history lines attributed to a specific NPC and persisted under that NPC note/history section.

## Scope
### In scope
- Post-import processing of Foundry chat records already parsed by `modules/pathfinder/app/foundry_chat_import.py`.
- New memory write paths in Pathfinder vault namespace.
- NPC matching and attribution rules.
- De-duplication state for both player-map updates and NPC-history updates.

### Out of scope
- LLM-based interpretation/summarization (v1 is deterministic parsing only).
- Changes to Sentinel Core message pipeline.
- Retrospective rewrite of old PF2E notes outside new memory targets.

## Proposed architecture (deepening)

### Candidate deep Module
`modules/pathfinder/app/foundry_memory_projection.py`

### Interface
`project_foundry_chat_memory(records, *, dry_run, obsidian_client, dedupe_store, options) -> ProjectionResult`

### Implementation responsibilities
- Normalize actor/speaker identity.
- Split records into Player vs NPC buckets.
- Build deterministic update payloads for player maps + NPC history sections.
- Apply de-duplication keys before writes.
- Write notes/patch sections through Obsidian adapter.

### Seams and adapters
1. **Identity seam**: `foundry_identity_resolver.py`
   - Adapter resolves speaker => `player | npc | unknown`.
2. **NPC match seam**: `npc_matcher.py`
   - Adapter maps speaker alias/token hints to existing NPC slug.
3. **Projection write seam**: `memory_projection_store.py`
   - Adapter writes/patches player map + NPC history notes.
4. **Dedupe seam**: extend current Foundry import state to track projection keys separately.

This gives leverage (single Interface for all projection behavior) and locality (identity/matching/writes concentrated behind seams).

## Data model + vault targets

### Player maps
- Path: `mnemosyne/pf2e/players/{player_slug}.md`
- Sections:
  - `## Voice Patterns`
  - `## Notable Moments`
  - `## Party Dynamics`
  - `## Chat Timeline`

### NPC chat history updates
- Existing NPC note path discovery via current NPC conventions.
- Append section (create if missing):
  - `## Foundry Chat History`
- Each appended line includes timestamp, source marker, and content hash key.

### Dedupe state
- Extend `.foundry_chat_import_state.json` (or sibling state file) with:
  - `player_projection_keys: []`
  - `npc_projection_keys: []`
- Stable key recipe:
  - prefer Foundry `_id`
  - fallback hash of `timestamp|speaker|content_normalized|target_note`

## Execution plan (GSD-ready)

### Phase 1 — Projection foundations
- Add projection Module + types (`ProjectionInput`, `ProjectionResult`, `ProjectionStats`).
- Implement deterministic identity normalization.
- Add unit tests for classifier and key generation.

### Phase 2 — Player map projection
- Implement player bucket aggregation and markdown section updates.
- Add tests:
  - creates new player map
  - updates existing map without duplicate timeline entries
  - dry-run produces preview without writes

### Phase 3 — NPC memory projection
- Implement NPC matcher + write adapter.
- Append NPC-attributed chat lines to `## Foundry Chat History`.
- Add tests:
  - alias-to-npc match success
  - unknown speaker skipped with stats
  - dedupe prevents repeated appends

### Phase 4 — Route integration
- Wire projection call into Foundry import flow after record extraction.
- Add flags to import request:
  - `--project-player-maps` (default true)
  - `--project-npc-history` (default true)
- Return projection metrics in API/Discord response.

### Phase 5 — Verification and docs
- Add integration tests for full import + projection + rerun idempotency.
- Update `CONTEXT.md` architecture memory section for new deep Module map.
- Update user docs with commands, outputs, and dry-run/live behavior.

## Testing strategy
1. Behavioral unit tests per seam (identity resolver, matcher, dedupe, projection writer).
2. Integration tests against fake Obsidian adapter for end-to-end projection.
3. Regression test: same source imported twice => second run writes zero new player/NPC entries.
4. Dry-run contract test: no vault writes, no source renames, metrics still returned.

## Acceptance criteria
- Live import writes/updates player maps and NPC chat history deterministically.
- Re-running on same source produces zero duplicate entries.
- Dry-run emits identical metrics shape without mutating vault files.
- Discord response includes projection stats (player updates, npc updates, deduped counts, unmatched speakers).
- All new behavior covered by automated tests in `modules/pathfinder/tests/`.

## Open decisions to resolve at implementation start
1. Exact NPC note path contract if multiple NPC naming variants exist.
2. Whether player map generation should create one file per Discord handle vs Foundry actor alias.
3. Preferred section format for NPC history (table vs bullet timeline).
4. Whether unmatched speakers should be persisted to a review queue note.

## Suggested initial slice order
1. Types + projection skeleton + tests.
2. Player projection writer + tests.
3. NPC matcher/writer + tests.
4. Import route integration + Discord summary update.
5. End-to-end idempotency and docs.
