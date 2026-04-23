---
phase: 31-dialogue-engine
reviewed: 2026-04-23T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - modules/pathfinder/app/dialogue.py
  - modules/pathfinder/app/llm.py
  - modules/pathfinder/app/routes/npc.py
  - modules/pathfinder/app/main.py
  - interfaces/discord/bot.py
findings:
  blocker: 0
  warning: 5
  info: 3
  total: 8
status: has_issues
---

# Phase 31: Code Review Report

**Reviewed:** 2026-04-23
**Depth:** standard (advisory — do not block)
**Files Reviewed:** 5 source files (tests out of scope)
**Status:** has_issues (no blockers; five warnings worth tracking)

## Summary

Implementation lands the DLG-01..03 contract cleanly at the module layer: T-31-SEC-01 fail-fast 404 is enforced before any LLM call, T-31-SEC-02 `normalize_mood` wraps every frontmatter read, and T-31-SEC-03 JSON-salvage in `generate_npc_reply` degrades without raising. D-09 is honoured — the mood write path uses `build_npc_markdown` + `put_note` and never `patch_frontmatter_field`. `REGISTRATION_PAYLOAD` correctly grows to 12 routes with the verbatim D-26 description. Graceful degradation on `put_note` failure works as specified.

The significant gap is at the bot layer: `_extract_thread_history` is defined but has zero call sites, so DLG-03 memory filtering (D-12/D-13) is structurally present but not wired. The dispatch branch always sends `history=[]`. Plan 31-05 specified a 3-layer `channel=` plumb-through that wasn't implemented; the SUMMARY acknowledges this as a deferral, but per CLAUDE.md "AI Deferral Ban", deferrals require human sign-off and should be surfaced, not absorbed.

No security issues. No data-loss risks. No crashes found under edge-case tracing. Mood math, clamp, and write-elision are correct. Five warnings below — the first (WR-01) is the one that materially reduces DLG-03 quality in production.

## Warnings

### WR-01: `_extract_thread_history` is dead code; `history=[]` always sent

**File:** `interfaces/discord/bot.py:207-252, 518-537`
**Issue:** `_extract_thread_history` has no call site in the module. The `say` dispatch branch (line 528-533) hardcodes `"history": []` in the payload. Plan 31-05 Steps 1-2 specified plumbing a `channel=None` kwarg through `_route_message` → `handle_sentask_subcommand` → `_pf_dispatch` so the helper could run in production; this plumbing is missing. Net effect: DLG-03 memory filtering (D-11..D-14) is untestable end-to-end, and every NPC turn starts with no conversation context, which is the exact symptom D-10..D-14 were designed to prevent. The SUMMARY (31-05) documents this as an intentional "future wiring" deferral, but DLG-03's memory contract is in the phase's must_haves, not a future phase.
**Fix:** Either (a) complete the plan's Step 2 plumb-through and call `_extract_thread_history` from the `say` branch when `channel is not None and isinstance(channel, discord.Thread)`, or (b) explicitly mark DLG-03 memory as deferred in ROADMAP with human sign-off. Leaving a defined-but-unused helper is the worst of both — it looks shipped but isn't.

### WR-02: `_SAY_PATTERN` uses `re.DOTALL`, letting `\n` leak into captured names

**File:** `interfaces/discord/bot.py:186`
**Issue:** `_SAY_PATTERN = re.compile(r"^:pf\s+npc\s+say\s+(.+?)\s*\|(.*)$", re.IGNORECASE | re.DOTALL)`. With `DOTALL`, `(.+?)` and `(.*)` match across newlines. A multi-line user message like `:pf npc say Varek\n\nextra | text` captures `"Varek\n\nextra"` as the name list. The server-side `_validate_npc_name` does reject control chars (`[\x00-\x1f]`), so this is defended in depth — but the bot-layer walker will then silently drop legitimate turns from history because the names string with embedded newlines won't match a stored NPC name. `re.DOTALL` was likely pulled in to permit payloads containing newlines; that's a narrower need than enabling it on group 1.
**Fix:** Drop `re.DOTALL` and split the pattern so only group 2 (`(.*)`) is newline-tolerant — e.g. anchor group 1 with `[^\n|]+?` and keep group 2 as `(.*)` under `re.DOTALL`. Or apply `re.DOTALL` only to a deliberately-multi-line-capable sub-group.

### WR-03: Inconsistent user-prompt quoting in `build_user_prompt`

**File:** `modules/pathfinder/app/dialogue.py:149, 157, 166`
**Issue:** Three separate renderings of the party line within the same user prompt use different quoting: lines 149 and 157 interpolate via `{party_line!r}` (Python `repr()`, which emits outer single quotes and escapes inner chars), while line 166 uses the human-readable `"{party_line}"` form. The LLM will see `Party: 'hi there'` in the history section but `The party has just said: "hi there"` in the current-turn section. This is prompt-quality noise and also leaks Python-specific escape semantics into the prompt when `party_line` contains apostrophes or non-ASCII (`repr` yields `'it\\'s'`).
**Fix:** Standardise on double-quote interpolation: replace `f"Party: {turn.get('party_line', '')!r}"` (line 149) and `f"Party: {party_line!r}"` (line 157) with `f'Party: "{turn.get("party_line", "")}"'` / `f'Party: "{party_line}"'`. Update `_render_history_for_token_count` (line 184) to match so token-count accounting stays aligned with what the LLM actually reads.

### WR-04: Invalid stored mood never self-heals on write-elision paths

**File:** `modules/pathfinder/app/routes/npc.py:935-952`
**Issue:** If an NPC's frontmatter has `mood: grumpy` (hand-edited or corrupted), `normalize_mood` returns `"neutral"` as the in-memory current mood. On a `mood_delta = 0` turn, `new_mood == current_mood == "neutral"`, so the `if new_mood != current_mood` check fails and no write occurs. The invalid `"grumpy"` persists in the vault indefinitely — every future `/npc/say` read logs a warning and re-runs the same silent normalisation. Subsequent `/npc/show` also returns `mood: grumpy` to the bot, and `_build_foundry_actor` / the stat embed footer will display it.
**Fix:** In `say_npc`, after parsing fields, compare the raw stored value to `normalize_mood(raw)`. If they differ AND no delta write is already queued, either (a) queue a correcting write to set `mood: <normalised>`, or (b) return a diagnostic field in the response so the bot can surface the inconsistency to the DM. A one-shot repair on read is the simpler fix.

### WR-05: `name_list` vs `quote_lines` positional zip assumes NPC count equals quote count

**File:** `interfaces/discord/bot.py:246-249`
**Issue:** `_extract_thread_history` pairs quote lines to NPC names by index: `{"npc": name_list[idx] if idx < len(name_list) else "?", "reply": line}`. This silently produces `"npc": "?"` entries when a bot reply contained more quote lines than NPCs named (e.g. a warning preamble "⚠ 5 NPCs..." that survives into `_QUOTE_PATTERN.findall` — though the warning isn't a quote-block, so that specific case is safe). The failure mode appears if an NPC reply contains an embedded newline-then-`>` pattern within its own quoted text, which `_QUOTE_PATTERN` will pick up as an extra quote line. Silent fallback to `"?"` means the module receives a turn with a phantom NPC name and the scene-membership filter on the server side can then misroute context.
**Fix:** If `len(quote_lines) != len(name_list)`, skip the turn with a `logger.debug` rather than producing `?` entries. Memory is best-effort; a malformed pairing is safer dropped than half-attributed. Combined with WR-01, this becomes moot when/if the history walker is actually invoked.

## Info

### IN-01: `tiktoken.get_encoding("cl100k_base")` is called every `cap_history_turns` invocation

**File:** `modules/pathfinder/app/dialogue.py:201`
**Issue:** The encoder is constructed inside the function body on every call. `get_encoding` is cached internally by tiktoken, so this is not a correctness or performance bug (performance is out of v1 scope regardless). Still, module-level `_ENC = tiktoken.get_encoding("cl100k_base")` is the idiomatic pattern and matches the sibling `sentinel-core/app/services/token_guard.py` reference called out in the module docstring.
**Fix:** Hoist to module scope.

### IN-02: `TurnHistory.replies: list[dict] = []` — mutable default is safe here but non-idiomatic

**File:** `modules/pathfinder/app/routes/npc.py:159, 170`
**Issue:** `list[dict] = []` as a Pydantic v2 field default is safe (Pydantic deep-copies defaults), unlike Python's traditional mutable-default trap. It's still more idiomatic to use `Field(default_factory=list)` for clarity and to signal "the default is a new list per instance" to readers.
**Fix:** Change to `replies: list[dict] = Field(default_factory=list)` and `history: list[TurnHistory] = Field(default_factory=list)` on `NPCSayRequest`. Requires importing `Field` from `pydantic` (already available project-wide).

### IN-03: Magic cap `1500` on reply length in `generate_npc_reply` is not a named constant

**File:** `modules/pathfinder/app/llm.py:104, 114`
**Issue:** `.strip()[:1500]` appears twice (success path + salvage path). The value is undocumented — it's not in CONTEXT.md, not in PATTERNS.md, and nothing in the plan mentions it. Readers will wonder whether 1500 is a Discord limit (it's not — Discord is 2000), a token budget, or an arbitrary choice.
**Fix:** Define `_MAX_REPLY_CHARS = 1500` at module level with a one-line comment explaining the rationale (likely "leaves headroom under Discord's 2000-char limit once wrapped in `> ` quote markdown across multi-NPC scenes"). Replace both literals.

---

_Reviewed: 2026-04-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
