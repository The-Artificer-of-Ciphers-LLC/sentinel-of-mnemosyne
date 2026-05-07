# PF2E Player Interaction Vault Plan

## Purpose
Add a Pathfinder Module that lets players interact with the Sentinel during sessions without interrupting game flow, while persisting each player’s notes/questions in a small per-player Vault area.

## Goals
1. Players can quickly save notes, questions, and NPC knowledge during play.
2. Each player gets isolated memory (no cross-player bleed).
3. Session flow remains fast (capture-first, retrieval second).
4. Data remains human-readable markdown in the Vault.
5. First interaction runs player onboarding (character name, preferred form of address, PF2E Sentinel style).
6. Yellow rule/homebrew outcomes can be canonized later to green/red and recorded per player.

## Domain additions
- **Player Vault**: per-player PF2E note space.
- **Player Capture**: fast note/question write.
- **Player Recall**: retrieve player-specific saved knowledge.
- **Player Onboarding**: first-contact setup capturing character name, preferred name, and PF2E Sentinel style preset.
- **PF2E Sentinel Style**: player-selected personality/tone preset for responses in game context.

## Scope
### In scope
- New player-focused commands + route handlers in Pathfinder module.
- Deterministic persistence/retrieval to player-specific markdown notes.
- NPC-specific player knowledge notes.
- Tests for isolation, correctness, and command dispatch.

### Out of scope
- Full LLM summarization pipeline (optional future enhancement).
- Changes to Sentinel Core message route behavior.
- GM moderation workflows beyond basic auth/identity mapping.

## Proposed deepening architecture

### Deep Module
`modules/pathfinder/app/player_interaction_orchestrator.py`

### Interface
`handle_player_interaction(request, *, obsidian_client, identity_adapter, store_adapter, recall_adapter) -> PlayerInteractionResult`

### Seams and adapters
1. **Identity seam** (`player_identity_resolver.py`)
   - Maps Discord user ID -> `player_slug`.
2. **Store seam** (`player_vault_store.py`)
   - Writes/reads player markdown notes.
3. **Recall seam** (`player_recall_engine.py`)
   - Deterministic retrieval/scoring over player notes.
4. **Command seam** (Discord adapter)
   - Maps `:pf player ...` commands to module routes.

## Vault layout
`mnemosyne/pf2e/players/{player_slug}/`
- `profile.md` — character name, preferred name, style preset, onboarding status
- `inbox.md` — quick captures
- `questions.md` — asked questions (+ optional answers)
- `canonization.md` — yellow->green/red follow-up outcomes with provenance
- `npcs/{npc_slug}.md` — player-specific NPC knowledge
- `sessions/{yyyy-mm-dd}.md` — session-local memory
- `todo.md` — deferred actions/follow-ups

## Command plan (Discord)
- `:pf player start` (or implicit first-use onboarding)
- `:pf player note <text>`
- `:pf player ask <question>`
- `:pf player npc <npc_name> <note>`
- `:pf player recall [query]`
- `:pf player todo <text>`
- `:pf player style [list|set <preset>]`

## Route plan (Pathfinder)
- `POST /player/onboard`
- `POST /player/note`
- `POST /player/ask`
- `POST /player/npc`
- `POST /player/recall`
- `POST /player/todo`
- `POST /player/style`
- `GET /player/state`

## Execution slices (GSD-ready)

### Slice 1 — foundations + onboarding
- Add types/models for player interaction requests/responses.
- Add identity + store seams with in-memory/unit-test adapters.
- Add onboarding state model (`character_name`, `preferred_name`, `style_preset`, `onboarded`).
- Add base route skeletons.

### Slice 2 — onboarding flow + style presets
- On first interaction, prompt for:
  1) character name
  2) preferred form of address
  3) PF2E Sentinel style preset
- Store profile in `profile.md`.
- Provide preset options (initial set):
  - `Tactician` (concise, mechanics-first)
  - `Lorekeeper` (setting-rich, context-heavy)
  - `Cheerleader` (supportive, motivational)
  - `Rules-Lawyer Lite` (strict canon emphasis, low flavor)
- Add tests for first-use prompt gating and profile persistence.

### Slice 3 — capture flows
- Implement note/question/todo persistence.
- Implement NPC knowledge write path (`npcs/{npc_slug}.md`).
- Add tests for per-player isolation + append behavior.

### Slice 4 — recall flow
- Implement deterministic recall over player vault files.
- Return concise recall response + source note references.
- Apply style preset to response formatting policy.
- Add retrieval relevance tests.

### Slice 5 — traffic-light canonization capture
- Add capture of yellow rule/homebrew outcomes tied to player question keys.
- Add follow-up resolution write path to `canonization.md`:
  - `green` => rules-canon
  - `red` => homebrew/non-canon/conflict
- Add tests for yellow->green, yellow->red, and unresolved timeout/pending.

### Slice 6 — Discord integration
- Add `player` noun commands in Discord pathfinder dispatcher.
- Add onboarding conversational state handling in adapter.
- Add adapter tests for argument parsing + route calls.

### Slice 7 — hardening + docs
- Add integration tests (end-to-end command -> pathfinder -> vault write/read).
- Update docs for command usage and player vault paths.
- Update CONTEXT.md architecture memory section for new deep Module map.

## Testing strategy
1. Unit tests per seam (identity/store/recall/onboarding).
2. Behavioral route tests with fake Obsidian adapter.
3. Onboarding tests (first-use prompt, resume, completion).
4. Canonization tests for yellow resolution lifecycle.
5. Discord command adapter tests.
6. Regression tests for idempotency and player isolation.

## Acceptance criteria
- First interaction requires onboarding completion before normal commands.
- Player profile captures character name, preferred name, and style preset.
- Player commands persist to correct per-player paths.
- Players can recall their own saved information quickly.
- NPC knowledge updates are player-specific and deterministic.
- No cross-player data leakage.
- Test suite covers all new command/route paths.

## Open decisions
1. Canonical `player_slug` source: Discord username vs explicit registration mapping.
2. Whether `player ask` should always call LLM or only store question in v1.
3. NPC name resolution rules for `player npc` command.
4. Whether GM/admin can query another player’s vault and under what auth.
5. Canonization timeout policy for yellow results (when to keep pending vs mark red).
6. Final style preset list and whether players can define custom presets.

## Suggested first implementation order
1. Store seam + note/todo/question writes.
2. NPC knowledge writes.
3. Recall engine.
4. Canonization capture/resolution path.
5. Discord command wiring.
6. Integration + docs.
