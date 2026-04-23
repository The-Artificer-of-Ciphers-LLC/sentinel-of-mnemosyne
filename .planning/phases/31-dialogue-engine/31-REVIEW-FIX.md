---
phase: 31-dialogue-engine
fixed_at: 2026-04-23T00:00:00Z
review_path: .planning/phases/31-dialogue-engine/31-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 31: Code Review Fix Report

**Fixed at:** 2026-04-23
**Source review:** `.planning/phases/31-dialogue-engine/31-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (5 warnings + 3 info — full scope per project AI Deferral Ban)
- Fixed: 8
- Skipped: 0

**Test state after all fixes:**
- `modules/pathfinder`: 60 passed
- `interfaces/discord`: 31 passed, 50 skipped (unchanged from baseline; skipped are live-integration)

## Fixed Issues

| ID | Severity | Status | Commit | Files |
|----|----------|--------|--------|-------|
| WR-01 | Warning | fixed: requires human verification | `01aabd9` | `interfaces/discord/bot.py` |
| WR-02 | Warning | fixed | `215bd62` | `interfaces/discord/bot.py` |
| WR-03 | Warning | fixed | `d36128a` | `modules/pathfinder/app/dialogue.py` |
| WR-04 | Warning | fixed: requires human verification | `e3a1b26` | `modules/pathfinder/app/routes/npc.py` |
| WR-05 | Warning | fixed | `ded3e1d` | `interfaces/discord/bot.py` |
| IN-01 | Info | fixed | `c625da6` | `modules/pathfinder/app/dialogue.py` |
| IN-02 | Info | fixed | `650f0f1` | `modules/pathfinder/app/routes/npc.py` |
| IN-03 | Info | fixed | `3beeaf6` | `modules/pathfinder/app/llm.py` |

### WR-01: `_extract_thread_history` is dead code; `history=[]` always sent

**Files modified:** `interfaces/discord/bot.py`
**Commit:** `01aabd9`
**Status:** fixed: requires human verification
**Applied fix:** Plumbed `channel=None` kwarg through the 3-layer call chain — `_route_message` → `handle_sentask_subcommand` → `_pf_dispatch` — all backward-compatible. In the `say` branch of `_pf_dispatch`, when `channel is not None and isinstance(channel, discord.Thread)`, call `_extract_thread_history(thread=channel, current_npc_names=set(names), bot_user_id=bot.user.id if bot.user else 0, limit=50)` and put the result in `payload["history"]`. Exceptions degrade to `history=[]`. Forwarded channel from both call sites: `on_message` passes `message.channel`; `/sen` slash handler passes `thread` (or `interaction.channel` as fallback). Tests stub `channel=None` and remain green. The isinstance check is False against the test's `discord.Thread = object` stub, so tests still exercise the `history=[]` path.

**Requires human verification** because the production path is only exercised when a real `discord.Thread` is passed — no automated end-to-end test covers this. Manual smoke test per 31-VALIDATION.md (send a `:pf npc say` in a real Sentinel thread; confirm log line shows `history_turns > 0` after the second turn).

### WR-02: `_SAY_PATTERN` uses `re.DOTALL`, letting `\n` leak into captured names

**Files modified:** `interfaces/discord/bot.py`
**Commit:** `215bd62`
**Applied fix:** Anchored group 1 to `[^\n|]+?` so newlines and pipes act as hard delimiters between the NPC list and the party line. Group 2 keeps `re.DOTALL` so multi-line party_line text is still captured. Verified via direct regex tests: single-line / multi-name cases still match, crafted `:pf npc say Varek\nextra | text` now returns `None` (match refused), multi-line party lines in group 2 still work.

### WR-03: Inconsistent user-prompt quoting in `build_user_prompt`

**Files modified:** `modules/pathfinder/app/dialogue.py`
**Commit:** `d36128a`
**Applied fix:** Replaced `{party_line!r}` with `f'Party: "{party_line}"'` form at both lines (149 and 157 — the in-memory history section and the this-turn section). Mirrored the change in `_render_history_for_token_count` so tiktoken counts the same string the LLM reads. Line 166 already used the double-quoted form; all three renderings now match.

### WR-04: Invalid stored mood never self-heals on write-elision paths

**Files modified:** `modules/pathfinder/app/routes/npc.py`
**Commit:** `e3a1b26`
**Status:** fixed: requires human verification
**Applied fix:** Track `raw_mood = npc["fields"].get("mood") or "neutral"` alongside the normalized `current_mood`. Compute `needs_normalization_repair = raw_mood != current_mood and new_mood == current_mood`. Widen the write gate to `if new_mood != current_mood or needs_normalization_repair:`. Log line distinguishes `NPC mood self-healed` from `NPC mood updated`. Preserves D-07 zero-delta no-op semantics when the stored value was already valid (existing test coverage remains green).

**Requires human verification** because this is a state-machine write-gate change that depends on invariants held across vault reads. Verify manually by hand-editing an NPC note to `mood: grumpy`, running `:pf npc say <name> | hi`, then confirming the vault file is rewritten with `mood: neutral` on first read.

### WR-05: `name_list` vs `quote_lines` positional zip assumes NPC count equals quote count

**Files modified:** `interfaces/discord/bot.py`
**Commit:** `ded3e1d`
**Applied fix:** If `len(quote_lines) != len(name_list)`, log at DEBUG level and skip the turn (`i += 2; continue`) instead of producing `"?"` placeholder entries. Memory is best-effort; a malformed pairing is safer dropped than half-attributed. The existing scene test (`test_thread_history_filter_scene`) uses matching counts (1:1, 1:1, 2:2) so all 3 turns still pair cleanly — no regression.

### IN-01: `tiktoken.get_encoding("cl100k_base")` is called every `cap_history_turns` invocation

**Files modified:** `modules/pathfinder/app/dialogue.py`
**Commit:** `c625da6`
**Applied fix:** Hoisted `_ENC = tiktoken.get_encoding("cl100k_base")` to module scope after the HISTORY_MAX_* constants. Replaced the per-call construction in `cap_history_turns` with `_ENC.encode(...)`. Comment notes the idiomatic match to `sentinel-core/app/services/token_guard.py`.

### IN-02: `TurnHistory.replies: list[dict] = []` — mutable default is safe here but non-idiomatic

**Files modified:** `modules/pathfinder/app/routes/npc.py`
**Commit:** `650f0f1`
**Applied fix:** Added `Field` to the pydantic import line. Changed `replies: list[dict] = []` to `replies: list[dict] = Field(default_factory=list)` on `TurnHistory`, and `history: list[TurnHistory] = []` to `history: list[TurnHistory] = Field(default_factory=list)` on `NPCSayRequest`. Surprise: on the first edit, the project's pre-configured ruff auto-format hook saw `Field` as unused (since the usages were added in separate edits) and stripped it from the import line. Re-added after the usages were written — final state has all three (BaseModel, Field, field_validator) imported and used.

### IN-03: Magic cap `1500` on reply length in `generate_npc_reply` is not a named constant

**Files modified:** `modules/pathfinder/app/llm.py`
**Commit:** `3beeaf6`
**Applied fix:** Added `_MAX_REPLY_CHARS = 1500` at module scope with the one-line comment `# leaves headroom under Discord's 2000-char limit once wrapped in "> " quote markdown across multi-NPC scenes`. Replaced both `.strip()[:1500]` literals (success path and JSON-salvage path) with `.strip()[:_MAX_REPLY_CHARS]`.

## Skipped Issues

None — all 8 in-scope findings fixed.

## Notes and Edge Cases

- **Hook-formatter interaction (IN-02):** The project's auto-formatter ran between my first edit (adding `Field` to the import) and my second edit (using `Field` in the body), and stripped the newly-added import as unused. Caught by running the pathfinder test suite, which failed with `NameError: name 'Field' is not defined`. Fixed by re-adding the import after the usages were written. Tests then went back to 60 passed.
- **Test-stub isinstance semantics (WR-01):** `interfaces/discord/tests/test_subcommands.py` sets `discord.Thread = object`. The production `isinstance(channel, discord.Thread)` check evaluates False against the test's SimpleNamespace channels, so the history walker is not invoked during unit tests — tests continue to assert `payload["history"] == []`. This is documented in the inline comment on the `say` branch.
- **Two findings flagged `requires human verification`:** WR-01 (no automated end-to-end test covers the production `discord.Thread` path) and WR-04 (state-machine write-gate change depending on vault invariants). Both are documented in the Manual Smoke Test section of 31-VALIDATION.md.

---

_Fixed: 2026-04-23_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
