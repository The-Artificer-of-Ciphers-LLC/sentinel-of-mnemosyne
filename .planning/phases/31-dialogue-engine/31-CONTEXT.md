# Phase 31: Dialogue Engine — Context

**Gathered:** 2026-04-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver in-character NPC dialogue grounded in Obsidian profiles, with persistent mood state and multi-NPC scene support. Source of truth for each NPC is the split-schema note at `mnemosyne/pf2e/npcs/{slug}.md` (identity fields in YAML frontmatter; mechanical stats in a fenced `## Stats` block — irrelevant to dialogue).

**What this phase delivers (DLG-01..03):**
1. `:pf npc say <Name> | <what party says>` — in-character reply grounded in that NPC's personality, backstory, traits, mood, and relationships
2. `:pf npc say <Name1>,<Name2>[,...] | <what party says>` — multi-NPC scene; each NPC replies in voice, processed in the order given; NPCs can address each other within a scene
3. `:pf npc say <Name1>,<Name2> |` (empty after pipe) — "scene advance": NPCs continue the exchange without a new party line
4. Persistent mood tracking — dialogue can shift the NPC's `mood:` frontmatter field along a 5-state spectrum

**What this phase explicitly does NOT do:**
- Cross-session persistent memory — thread-scoped only; when Discord archives the thread, conversation memory is gone (mood persists)
- Session note recording (writing dialogue beats to `mnemosyne/pf2e/sessions/…`) — Phase 34
- Tool-augmented dialogue (NPC triggering dice rolls, rules lookups) — Phase 33
- Foundry VTT dialogue event ingest — Phase 35
- Voice I/O (TTS / speech input) — out of scope
- Any new Discord slash commands — all dialogue uses the existing `:pf npc` prefix pattern inside `/sen`

</domain>

<decisions>
## Implementation Decisions

### Discord Command Surface

- **D-01:** Syntax: `:pf npc say <Name>[,<Name>...] | <party line>`
  - One verb (`say`) regardless of NPC count
  - NPC names are comma-separated (no spaces required around commas; bot trims each)
  - Pipe separates the NPC list from the party's spoken line (same separator convention as `:pf npc create`)
  - When ≥2 NPCs are named, the call is treated as SCENE mode (D-14)
- **D-02:** Empty payload after the pipe (`:pf npc say Varek,Baron |`) triggers SCENE ADVANCE — NPCs continue the conversation from the prior turn without a new party line. Bot detects empty/whitespace-only payload and sends a different framing to the LLM ("the party is silent; continue the scene naturally based on the prior exchange"). Works for both 1- and N-NPC calls, though it's most useful in scenes.
- **D-03:** Reply rendering: **plain quoted markdown**, no Discord embed. Format per NPC:
  ```
  > *Varek shifts, eyes darting.* "I told you — I don't have it."
  ```
  For scenes, a single bot message contains multiple quote blocks stacked in the processing order. No trailing mood-change line in the reply — mood is silently updated in frontmatter (DM can `:pf npc show` to see current mood). Copy-pasteable into session notes.
- **D-04:** Unknown verb text in `_pf_dispatch` must include `say` in the "Available:" list.

### Mood State Machine (DLG-02)

- **D-05:** Mood is a single `mood:` string in the NPC's YAML frontmatter (field already exists per Phase 29 D-20; default at create time is `neutral`).
- **D-06:** **5-state ordered spectrum** (enum):
  ```
  hostile  wary  neutral  friendly  allied
     ←─────── persuade / gift / aid ─────→
     threats / betrayal / extortion
  ```
  The `mood:` field's value MUST be exactly one of these five lowercase strings. Invalid values (from hand-edited notes) are treated as `neutral` and a warning is logged.
- **D-07:** Shift trigger: **salient events only.** The LLM call returns a structured object per NPC:
  ```json
  {"reply": "...", "mood_delta": -1 | 0 | +1}
  ```
  `mood_delta = 0` is the default and means "no change" — the vault is NOT written on those turns (most flavor chatter). Non-zero delta moves the mood exactly one state along the spectrum (clamped at `hostile` / `allied`). Jumps >1 per turn are NOT allowed — repeated interactions compound.
- **D-08:** Mood is communicated to the LLM as TONE GUIDANCE in the system prompt, not merely quoted as a field. Example mapping:
  - `hostile` — aggressive, curt, threatens if pushed, gives no useful info
  - `wary` — guarded, deflects, gives partial answers, watches for betrayal
  - `neutral` — businesslike, answers direct questions, no warmth
  - `friendly` — warm, volunteers context, offers help
  - `allied` — freely offers info, warns of danger, acts on NPC's own initiative
- **D-09:** Mood write mechanism: **GET-then-PUT** via the `update_npc` pattern (not `patch_frontmatter_field`). Rationale: consistent with the 2026-04-23 learning that PATCH replace-on-missing fails 400 for some field states; single-field writes are cheap enough; and reuses `build_npc_markdown` which preserves the stats block intact. See `project_obsidian_patch_constraint.md` memory.

### Conversation Memory (shared across DLG-01/DLG-03)

- **D-10:** **Thread-scoped memory** — no vault writes for dialogue history. The Discord thread IS the session log. When the thread archives, memory is gone. Mood persists in frontmatter regardless.
- **D-11:** Memory fetch: the bot walks back recent messages in the current Discord thread (via `discord.Thread.history()`) and extracts prior dialogue turns. A "turn" is a pairing of:
  - A user message matching `:pf npc say <names> | <text>` (or empty payload)
  - The bot's immediately-following reply containing one or more `> *NPC action.* "reply"` quote blocks
- **D-12:** Memory filter for solo calls (`:pf npc say Varek | …`): include prior turns where Varek was in the name list (either solo or as part of a scene). Varek "remembers" what was said in scenes he was present for.
- **D-13:** Memory filter for scene calls (`:pf npc say Varek,Baron | …`): include prior turns where ANY currently-named NPC was in the name list. Each NPC in the current scene sees the full prior scene context (even lines spoken by NPCs who are absent from this turn), so the conversation stays coherent.
- **D-14:** History cap: bounded by token budget. Claude's discretion for exact count (sensible default: last 10 prior turns OR whatever fits under 2000 tokens of history, whichever is smaller). If truncation is needed, drop oldest turns first.

### Scene Orchestration (DLG-03)

- **D-15:** Scene mode = ≥2 comma-separated names. Single-name is SOLO mode.
- **D-16:** **Round-robin with conversation**: within a turn, NPCs are processed IN THE ORDER GIVEN on the command line. Each NPC's LLM prompt sees:
  1. Their own profile (personality, backstory, traits, mood, relationships)
  2. Thread-scoped memory (D-13)
  3. **This-turn context**: the party line AND any replies from OTHER NPCs already generated EARLIER in this same turn
  4. The list of other NPCs present in the scene
  5. Relevant relationship edges between this NPC and every other NPC in the scene (e.g., "Varek fears Baron"; "Baron owes-debt to Varek") — extracted from frontmatter
- **D-17:** No automatic rotation between turns. Order is always "as specified by the DM on this command line." If the DM wants Baron to speak first next turn, the DM reorders: `:pf npc say Baron,Varek | …`. Predictable and DM-controlled.
- **D-18:** **Soft cap at 4 NPCs.** No hard rejection for >4. If ≥5 NPCs are named, the bot prepends a warning line before the quote blocks:
  ```
  ⚠ 5 NPCs in scene — consider splitting for clarity.
  ```
  Token usage and latency grow linearly with count — this is the user's responsibility when they exceed the cap.
- **D-19:** Processing is SERIAL within a turn (each NPC's LLM call waits for the previous NPC's reply so it can see it). Parallelisation is NOT an option here because conversation awareness requires sequential context building.
- **D-20:** SCENE ADVANCE (D-02 empty payload): each NPC's LLM prompt receives "the party is silent; continue the scene naturally based on the prior exchange" in place of a party line. Everything else (D-16 context) applies. Still serial, still per-NPC.

### Grounding Payload per LLM Call

- **D-21:** The pathfinder module owns prompt construction. Bot sends raw inputs; module does the assembly. Payload shape:
  ```
  System: <tone guidance by mood> + <role: you are <name>, a <ancestry> <class>> + <personality, backstory, traits> + <relationship context> + <scene context: other NPCs present> + <output format: plain prose reply + mood_delta JSON>
  User: <thread memory — prior turns as text> + <this-turn other-NPC replies so far> + <current party line OR scene-advance framing>
  ```
- **D-22:** Backstory is truncated to the first 400 characters before interpolation (same injection-surface-reduction pattern as Phase 30 D-11). Personality is truncated to 200 chars. Traits, relationships are inlined in full (they're small).
- **D-23:** LLM response is expected as structured JSON `{"reply": "...", "mood_delta": -1|0|+1}`. Code-fence stripping reuses the existing `_strip_code_fences()` helper in `modules/pathfinder/app/llm.py`.

### Module Endpoint

- **D-24:** New endpoint: `POST /modules/pathfinder/npc/say`
  - Request: `{names: [str], party_line: str, history: [{party_line: str, replies: [{npc: str, reply: str}]}], user_id: str}` — `history` is the thread-scoped memory sent by the bot; `party_line == ""` signals SCENE ADVANCE.
  - Response: `{replies: [{npc: str, reply: str, mood_delta: int, new_mood: str}], warning: str | null}` — `warning` is populated when ≥5 NPCs.
- **D-25:** Bot layer owns the Discord side:
  - Assembling the `history` array by walking `message.channel.history()` (current thread)
  - Formatting the final quote-block reply message
  - No bot-side mood logic; the module does writes.
- **D-26:** Add `{"path": "npc/say", "description": "In-character NPC dialogue with mood tracking (DLG-01..03)"}` to `REGISTRATION_PAYLOAD` in `modules/pathfinder/app/main.py` — registry goes from 11 → 12 routes.

### Model Selection

- **D-27:** Use `resolve_model("chat")` from the existing model selector — dialogue is open-ended prose, not structured extraction. The `mood_delta` JSON extraction is lightweight enough that the chat-tier model handles it (LLM returns `{reply, mood_delta}` in one shot — no separate structured call). If chat-tier struggles with JSON compliance, fall back to `resolve_model("structured")`. This decision is re-evaluated in execution.

### Input Validation

- **D-28:** NPC name sanitization reuses `_validate_npc_name` (Phase 29 CR-02 mitigation — strips control chars, caps at 100 chars). Party line has a separate 2000-char cap (covers typical tabletop turn length without exploding token budget).
- **D-29:** NPC name lookup is 404 on first missing NPC (processed in given order). No partial success — a scene with one missing NPC is the whole scene failing. Error message names the missing NPC.

### Claude's Discretion

- Exact wording of the tone-guidance system prompt per mood state
- Exact wording of the SCENE ADVANCE framing ("the party is silent…")
- Exact history cap value (token-budget-driven; research task)
- How the bot reads thread history (discord.Thread.history limit value, filtering logic)
- Pydantic model names and field shapes for the `/npc/say` request/response
- Whether to add a lightweight "scene-id" string derived from sorted NPC slugs for debugging (not user-visible)
- Helper function locations (new `app/dialogue.py` vs extending `app/llm.py`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — DLG-01 through DLG-03 requirements text
- `.planning/ROADMAP.md` §Phase 31 — goal, dependency (Phase 29), success criteria SC-1..SC-4

### Architecture — This Project
- `.planning/PROJECT.md` — core value, tech stack constraints (Python 3.12, FastAPI, litellm via resolve_model)
- `.planning/phases/29-npc-crud-obsidian-persistence/29-CONTEXT.md` — NPC schema (D-15..D-22: frontmatter fields INCLUDING `mood: neutral` at D-20, relationships enum at D-13, ObsidianClient at D-27..D-29, `:pf` routing at D-01..D-04)
- `.planning/phases/30-npc-outputs/30-CONTEXT.md` — LLM grounding and sanitization patterns (D-10: constrained-output prompt; D-11: input sanitization; D-23: REGISTRATION_PAYLOAD extension)
- `.planning/phases/28-pf2e-module-skeleton-cors/28-CONTEXT.md` — Module registration Pitfall 7 (all routes at startup); REGISTRATION_PAYLOAD location
- `.planning/phases/27-architecture-pivot/27-CONTEXT.md` — Path B module contract (pathfinder module is its own FastAPI service, registers with sentinel-core)

### Hard-Won Constraints (memory)
- `~/.claude/projects/-Users-trekkie-projects-sentinel-of-mnemosyne/memory/project_obsidian_patch_constraint.md` — Obsidian PATCH replace-on-missing returns 400; use GET-then-PUT for mood writes (D-09)

### Files Being Modified
- `interfaces/discord/bot.py` — new `elif verb == "say":` branch in `_pf_dispatch`; new helper to walk `message.channel.history()` and assemble the `history` array per D-11..D-14; update unknown-verb help text
- `modules/pathfinder/app/main.py` — extend `REGISTRATION_PAYLOAD` with `npc/say` (11 → 12 routes); docstring update
- `modules/pathfinder/app/routes/npc.py` — add `NPCSayRequest` / `NPCSayResponse` Pydantic models; new `POST /npc/say` handler that fetches each NPC note, parses frontmatter, builds per-NPC LLM calls in serial, writes mood back via GET-then-PUT when delta ≠ 0
- `modules/pathfinder/app/llm.py` — new helper (likely `generate_npc_reply`) that wraps `litellm.acompletion()` with the dialogue-specific system prompt, tone-by-mood map, and JSON response parsing
- `modules/pathfinder/tests/test_npc.py` — new test block for `/npc/say` (solo happy path, scene order preservation, mood delta +1/-1/0, unknown NPC 404, scene advance with empty payload, ≥5-NPC warning)

### Existing Patterns to Follow
- `modules/pathfinder/app/llm.py` — `extract_npc_fields` / `update_npc_fields` show the litellm.acompletion wrapper pattern, system/user message construction, and JSON response parsing via `_strip_code_fences`
- `modules/pathfinder/app/routes/npc.py` — `update_npc` GET-then-PUT pattern (D-09 mood write); `_validate_npc_name` input sanitization; slugify; `_parse_frontmatter` / `_parse_stats_block` / `build_npc_markdown` round-trip
- `interfaces/discord/bot.py` `_pf_dispatch` — existing verb dispatch (`create` / `update` / `show` / `relate` / `import` / `export` / `token` / `token-image` / `stat` / `pdf`); pipe-separator parsing via `rest.partition("|")`; error handling for `httpx.HTTPStatusError`, `ConnectError`, `TimeoutException`
- `interfaces/discord/bot.py` `on_message` — existing thread detection via `SENTINEL_THREAD_IDS` and `thread.owner_id` fallback; this is where dialogue calls originate

### LLM / LiteLLM References (research territory — linked for the researcher)
- LiteLLM docs for chat-model JSON response handling: https://docs.litellm.ai/docs/completion/json_mode — for the `mood_delta` structured field
- discord.py `Thread.history()` async iterator: https://discordpy.readthedocs.io/en/stable/api.html?highlight=thread#discord.Thread.history — for thread memory walking (limit, oldest_first)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `modules/pathfinder/app/routes/npc.py` — `obsidian` module-level client, `_NPC_PATH_PREFIX = "mnemosyne/pf2e/npcs"`, `_validate_npc_name`, `slugify`, `_parse_frontmatter`, `_parse_stats_block`, `build_npc_markdown`, and the `update_npc` GET-then-PUT flow are all directly reusable for the mood write-back
- `modules/pathfinder/app/llm.py` — `_strip_code_fences` handles the LLM-wraps-JSON-in-fences edge case; `extract_npc_fields` is a structural template for the dialogue LLM call (system prompt + user input + JSON parsing)
- `modules/pathfinder/app/resolve_model.py` — `resolve_model("chat")` returns the model string to pass to litellm (registry-aware, per quick task 260423-mdl)
- `interfaces/discord/bot.py` `_pf_dispatch` — established verb dispatch pattern; pipe-separator parsing (`rest.partition("|")` — maxsplit=1 implicitly); error-mapping stanza for HTTPStatusError 404/409/other

### Established Patterns
- All pf routes respond through `_sentinel_client.post_to_module("modules/pathfinder/npc/<verb>", payload, http_client)` — same pattern for `/npc/say`
- NPC notes are split-schema: frontmatter (identity, mood, relationships) + optional `## Stats` block. Dialogue only needs frontmatter; stats block is irrelevant.
- LLM calls use `resolve_model(<task_kind>)` + `litellm.acompletion` with `api_base=settings.litellm_api_base or None` — consistent across all existing LLM endpoints
- Mood field is already initialized (`mood: neutral`) at NPC create time per Phase 29 D-20 — no migration needed for Phase 29+ NPCs. NPCs imported via `/npc/import` also set `mood: neutral` (see `import_npcs` handler).

### Integration Points
- Thread memory requires access to the Discord thread object. `on_message` already has `message.channel` as a `discord.Thread` inside Sentinel threads. Slash-command path (`/sen <text>` creating a new thread) has no prior history — first `:pf npc say` in a new thread gets empty history (expected).
- Relationship edges for scene context: `fields["relationships"]` in each NPC's frontmatter is a list of `{target, relation}` dicts (D-14 in Phase 29). For scene mode, filter each NPC's relationships to only those where `target` matches another NPC in the current scene.
- No new Docker / compose / env-var changes. No new Python dependencies (litellm, httpx, pydantic, yaml, fastapi all already installed).

</code_context>

<specifics>
## Specific Ideas

- **Reply rendering example** (solo, mood-neutral NPC):
  ```
  > *Varek's eyes dart to the door.* "Look, I don't know anything about the coin. I swear."
  ```
- **Scene example** (2 NPCs, round-robin awareness, mood-wary + mood-hostile):
  ```
  > *Varek shrinks behind a chair.* "N-no, I don't know anything."
  > *Baron laughs coldly at Varek.* "He's lying. He always does."
  ```
- **Mood spectrum numeric mapping** (for delta math, not user-visible):
  `hostile = 0, wary = 1, neutral = 2, friendly = 3, allied = 4`
  `new_mood = clamp(current + delta, 0, 4)`
- **Scene advance framing (Claude's discretion, starter wording):**
  > "The party is silent. The scene continues — react to what was just said, or advance the situation based on your character and the conversation so far."

</specifics>

<deferred>
## Deferred Ideas

- **Phase 34 (Session Notes):** Writing significant dialogue beats (mood shifts, reveals, confrontations) to `mnemosyne/pf2e/sessions/<date>.md` for campaign history — thread memory is ephemeral; session notes are permanent
- **Phase 33 (Rules Engine):** Tool-augmented dialogue — NPC can trigger a dice roll or rules lookup in response to a party statement (e.g., party attempts Deception, NPC gets Perception check in-line)
- **Cross-session dialogue memory** — summarizing a thread's dialogue into a compact "Recent Events" block in the NPC note, so the NPC "remembers" the prior session in a new thread. Thread-scoped only is the v1 scope.
- **Mood-change visibility** — an optional `:pf npc say --verbose …` flag that appends a subtle mood-change line when delta ≠ 0. Out of scope for v1 (plain quoted text is the commitment).
- **Inter-NPC dialogue injection** — NPCs addressing party members by character name. Requires party-roster data that doesn't exist yet. Future phase.
- **Voice I/O (TTS out / speech in)** — hardware + latency issues outside scope.

</deferred>

---

*Phase: 31-dialogue-engine*
*Context gathered: 2026-04-23*
