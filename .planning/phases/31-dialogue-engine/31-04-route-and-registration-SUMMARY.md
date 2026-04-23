---
phase: 31
plan: 04
subsystem: pathfinder-module
tags: [dialogue, npc, fastapi, pydantic, obsidian, mood-tracking, DLG-01, DLG-02, DLG-03]
requirements: [DLG-01, DLG-02, DLG-03]

dependency_graph:
  requires:
    - 31-01-red-test-stubs   # 16 npc_say tests + 2 integration tests authored
    - 31-02-dialogue-helpers # build_system_prompt, build_user_prompt, apply_mood_delta, cap_history_turns, normalize_mood, MOOD_ORDER
    - 31-03-llm-generate-reply # generate_npc_reply with JSON salvage
  provides:
    - "POST /modules/pathfinder/npc/say endpoint (12th registered route)"
    - "NPCSayRequest / TurnHistory / NPCReply / NPCSayResponse Pydantic v2 models"
    - "GET-then-PUT mood write path (never patch_frontmatter_field)"
    - "Serial round-robin multi-NPC scene dispatch with in-turn awareness"
    - "Soft warning on >=5 NPCs (exact string per D-18)"
  affects:
    - "Unblocks 31-05 (Discord bot wiring) — :pf npc say verb dispatch can now POST to this route"
    - "16/16 npc_say unit tests + 2/2 integration tests transition RED -> GREEN"

tech_stack:
  added: []  # no new runtime deps; all stack members inherited from 31-01..31-03
  patterns:
    - "Pydantic v2 field_validator for request sanitisation (CR-02 pattern, Analog A)"
    - "GET-then-PUT frontmatter mutation via build_npc_markdown (D-09; mirrors update_npc and token_image write)"
    - "Fail-fast 404 before any side effect (D-29; mirrors show_npc / update_npc / token-image)"
    - "Serial round-robin with accumulating this_turn_replies list (D-19)"
    - "Stats block preservation on round-trip write (stats=current_stats if current_stats else None)"

key_files:
  created: []
  modified:
    - modules/pathfinder/app/routes/npc.py   # +183 lines: 4 models + say_npc handler + 6 imports
    - modules/pathfinder/app/main.py         # +2 lines: docstring entry + REGISTRATION_PAYLOAD route

decisions:
  - "Combined tasks 31-04-01 (models) and 31-04-02 (handler) into sequential Edit operations staged as two commits via git add --patch (ruff --fix auto-strips unused imports on each PostToolUse; models alone leave dialogue/llm imports unused; handler must be present for imports to survive). Git history still shows one commit per logical task: 1dc2041 (models + imports) and 71db5aa (handler)."
  - "Mood write uses obsidian.put_note(path, build_npc_markdown(updated_fields, stats=...)) per D-09 — never patch_frontmatter_field. Reason: Obsidian REST API PATCH Operation=replace returns 400 when the target field doesn't exist at time-of-patch, and invalid moods set by hand-editing may produce absent fields on re-read (T-31-SEC-02)."
  - "put_note failure path does NOT raise — logs error and sets new_mood = current_mood so the reply still reaches the user (graceful degradation per RESEARCH.md lines 1007-1012). The LLM-generated reply is more valuable than strict mood-state persistence on a single rare write failure."
  - "Scene relationship filtering (only relationships whose target is in scene_roster reach build_system_prompt) preserves LLM context budget and prevents prompt noise when many NPCs each carry independent relationship lists. Implemented in-handler rather than in build_system_prompt to keep dialogue.py pure."
  - "Debug-only scene_id (slug-sorted hyphen-joined NPC slugs) is logged but NOT surfaced in response — used for post-hoc log correlation without widening public response shape."

metrics:
  duration_minutes: 11
  completed: "2026-04-23"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 2
  tests_green_delta: 18   # 42 -> 60 (16 say unit + 2 integration)
---

# Phase 31 Plan 04: Route and Registration Summary

## One-liner

Wired the dialogue engine into pathfinder's HTTP surface: new POST /modules/pathfinder/npc/say endpoint, 4 Pydantic v2 request/response models, and 12th route registration — all 18 RED tests from Plan 31-01 now GREEN.

## Scope Delivered

- `NPCSayRequest`, `TurnHistory`, `NPCReply`, `NPCSayResponse` Pydantic models in `app/routes/npc.py`
  - Names list must be non-empty; each name passes `_validate_npc_name` (T-31-SEC-01)
  - `party_line` capped at 2000 chars (T-31-SEC-04); empty string is the SCENE ADVANCE signal (D-02)
  - `history` is a list of `TurnHistory` objects bot-assembled from Discord thread (D-11..D-14)
- `say_npc` route handler implementing DLG-01, DLG-02, DLG-03
  - Fail-fast 404 on first missing NPC BEFORE any LLM call (D-29, T-31-SEC-01)
  - Serial round-robin across NPCs with in-turn awareness (D-19)
  - Chat-tier model resolution via `resolve_model("chat")` (D-27)
  - Scene-filtered relationship edges (RESEARCH Finding 7)
  - Mood write via GET-then-PUT using `build_npc_markdown` + `obsidian.put_note` (D-09)
  - Write-elision when `new_mood == current_mood` — handles both zero-delta turns AND clamped no-ops (D-07)
  - Graceful degradation on `put_note` failure: reply returned, `new_mood` reverts to `current_mood`
  - Soft warning when `len(names) >= 5` — exact string `⚠ {N} NPCs in scene — consider splitting for clarity.` (D-18)
  - Debug-only `scene_id` log entry for post-hoc correlation
- `REGISTRATION_PAYLOAD` in `app/main.py` extended from 11 to 12 routes; module docstring updated

## Test Results

```
cd modules/pathfinder && python -m pytest tests/test_npc.py -k npc_say -q
  → 16 passed, 21 deselected

cd modules/pathfinder && python -m pytest tests/test_npc_say_integration.py -q
  → 2 passed

cd modules/pathfinder && python -m pytest tests/ -q
  → 60 passed (42 pre-existing + 16 say unit + 2 integration — no regressions)
```

Registration smoke test:
```
len(REGISTRATION_PAYLOAD['routes']) == 12  ✓
any(r['path'] == 'npc/say' for r in REGISTRATION_PAYLOAD['routes'])  ✓
say['description'] == 'In-character NPC dialogue with mood tracking (DLG-01..03)'  ✓
```

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 31-04-01 | Models + dialogue/llm imports | `1dc2041` | modules/pathfinder/app/routes/npc.py (+67) |
| 31-04-02 | `say_npc` handler | `71db5aa` | modules/pathfinder/app/routes/npc.py (+116) |
| 31-04-03 | REGISTRATION_PAYLOAD + docstring | `301b4ca` | modules/pathfinder/app/main.py (+2) |

## Deviations from Plan

**1. [Rule 3 - Blocking issue] Split of tasks 01 and 02 required paired editing to survive ruff auto-fix**

- **Found during:** Task 31-04-01 first edit attempt
- **Issue:** The user's global PostToolUse hook runs `ruff check --fix` on every Python edit. Ruff's F401 rule strips unused imports. Adding the dialogue imports (`apply_mood_delta`, `build_system_prompt`, `build_user_prompt`, `cap_history_turns`, `normalize_mood`) and `generate_npc_reply` in task 01 — before their first use in the handler (task 02) — caused ruff to silently delete them between edits. Two consecutive attempts confirmed this.
- **Fix:** Implemented the models (task 01 content) and the handler (task 02 content) in a single file edit session, then used `git add --patch` to split the diff into two logically-separated commits preserving the per-task commit boundary required by the plan. Git history still shows the plan's task split.
- **CLAUDE.md relevance:** The AI Deferral Ban forbids `# noqa: F401` suppressions, which would have been the simpler workaround. The git-patch split is the compliant path.
- **Files affected:** modules/pathfinder/app/routes/npc.py
- **Commits:** `1dc2041` (task 01), `71db5aa` (task 02)

No other deviations. No Rule-4 architectural changes were required. No authentication gates encountered.

## Authentication Gates

None.

## Known Stubs

None. Every new branch in `say_npc` returns a real response or raises a documented HTTPException. Graceful-degrade path (put_note failure) sets a real `new_mood` fallback and continues — not a stub.

## Accepted Limitations (documented, not fixed in v1)

Per the PLAN threat model `T-31-04-D03` (race condition on rapid-fire `/npc/say` against the same NPC): two back-to-back requests issued within the 60-second LLM call window can produce stale mood writes, where the second request's GET reads a pre-first-write state. Result is mild mood under-counting, never data corruption. Mitigation is behavioural (Discord's per-channel on_message serialisation narrows the window); a proper fix would require per-NPC optimistic-lock tokens and is deferred to a future phase. Documented in RESEARCH.md Finding 6.

## Threat Surface Scan

No new threat-relevant surface introduced beyond the plan's documented `<threat_model>`. All mitigations listed (T-31-04-T01..T03, D01..D02, I01, S01) are implemented or structurally satisfied:

- T01 (path traversal): `_validate_npc_name` applied per-element in `NPCSayRequest.sanitize_names`
- T02 (mood poisoning): `normalize_mood` called on every `fields.get("mood")` read
- T03 (prompt injection via party_line): `generate_npc_reply` salvage path + mood_delta clamp (inherited from 31-03)
- D01 (token budget): `cap_history_turns` + `party_line <= 2000 chars`
- D02 (many-NPC cost): soft warning at 5 NPCs; serial within-turn
- I01 (stats leak): stats parsed only for preservation round-trip; never passed to `build_system_prompt`
- S01 (auth): inherited from sentinel-core's `X-Sentinel-Key` middleware

## Follow-on Work (Plan 31-05)

- Discord bot verb dispatch for `:pf npc say <name>` and `:pf npc say <Name1>, <Name2>` (scene mode)
- Thread history walker that reconstructs `TurnHistory[]` from prior bot quote-block messages
- Discord embed / quote-block rendering of `replies[]` with per-NPC mood indicator
- Per-channel serialisation to narrow the T-31-04-D03 race window (best-effort)

## Self-Check: PASSED

Verified on 2026-04-23:

- [x] `modules/pathfinder/app/routes/npc.py` — FOUND, contains NPCSayRequest / TurnHistory / NPCReply / NPCSayResponse / say_npc
- [x] `modules/pathfinder/app/main.py` — FOUND, contains `npc/say` entry with exact D-26 description
- [x] Commit `1dc2041` — FOUND in `git log` (models + imports)
- [x] Commit `71db5aa` — FOUND in `git log` (say_npc handler)
- [x] Commit `301b4ca` — FOUND in `git log` (REGISTRATION_PAYLOAD)
- [x] 16/16 test_npc_say_* tests GREEN
- [x] 2/2 test_npc_say_integration.py tests GREEN
- [x] 60/60 full pathfinder test suite GREEN (no Phase 29/30 regressions)
- [x] `len(REGISTRATION_PAYLOAD['routes']) == 12` verified via smoke test
- [x] `patch_frontmatter_field` count in routes/npc.py unchanged from baseline (1) — say_npc uses PUT not PATCH
- [x] No TODO / FIXME / NotImplementedError markers introduced by this plan
