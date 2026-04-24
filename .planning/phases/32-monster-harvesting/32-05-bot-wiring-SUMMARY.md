---
phase: 32-monster-harvesting
plan: 05
subsystem: discord-interface
tags: [discord, bot, dispatch, embed, harvest, noun-widen, conftest-stub]

# Dependency graph
requires:
  - phase: 32-monster-harvesting
    provides: POST /harvest route (Plan 32-04 — {monsters, aggregated, footer}), 7 test_pf_harvest_* RED stubs (Plan 32-01)
  - phase: 31-dialogue-engine
    provides: `:pf` dispatch frame (npc noun + verb chain), SentinelCoreClient.post_to_module, per-file discord stub idiom
provides:
  - interfaces/discord/bot.py — build_harvest_embed helper (pure dict → discord.Embed), _pf_dispatch widened noun check, harvest dispatch branch, updated top-level usage + unknown-noun error
  - interfaces/discord/tests/conftest.py — consolidated session-level discord stub (adds Embed/Color + centralises all prior per-file stubs to eliminate collection-order race)
affects: [phase-33-rules-engine, phase-34-session-notes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Harvest branch re-parses `args` rather than reusing parts[2]/rest so multi-word monster names survive the space-splitter (D-04, Pitfall 5: `:pf harvest Giant Rat` → names=['Giant Rat'])"
    - "Defensive leading-whitespace strip before slice (`stripped_args[len('harvest'):]`) so `:pf  harvest Boar` (extra spaces) routes correctly; explicit-length slice chosen over str.lstrip('harvest') because the latter strips any character in {h,a,r,v,e,s,t} not just the word"
    - "Conftest-level discord stub: pre-existing per-file stubs used `sys.modules.setdefault('discord', ...)` → first collector won, downstream tests saw an incomplete stub if their file was collected later. Consolidated into conftest.py so the stub is deterministic across collection order"
    - "Embed construction catches nothing — `build_harvest_embed` is pure; the dispatcher's outer try/except catches network + module errors only, not rendering bugs"

key-files:
  created:
    - .planning/phases/32-monster-harvesting/32-05-bot-wiring-SUMMARY.md (this file)
  modified:
    - interfaces/discord/bot.py (+86 / -3 net — build_harvest_embed helper + harvest dispatch branch + noun widen + usage/error updates)
    - interfaces/discord/tests/conftest.py (+87 / -0 net — session-level discord stub with Embed/Color/Client/Intents/Thread/etc, env bootstrap, sys.path inserts)

key-decisions:
  - "Re-parse `args` in the harvest branch instead of using the space-split parts from the top of _pf_dispatch. Reason: parts[2] would swallow whitespace but splits on spaces, so a multi-word name like `Giant Rat` becomes parts=['harvest','Giant','Rat'] and parts[2]='Rat' drops 'Giant'. Re-parsing from args and splitting only on commas preserves the full name. This is D-04's locked parse rule + Pitfall 5's defence."
  - "Consolidate discord stub into conftest.py (Rule 3 fix). Before: each test file built its own stub and used `sys.modules.setdefault('discord', ...)` — whichever file pytest collected first won, later files' added attributes (e.g. my initially-local Embed/Color) were discarded. `test_pf_harvest_returns_embed_dict` passed in isolation but failed in the full suite because test_live_integration.py collects first and ships a stub without Embed. Centralising the stub in conftest.py makes it deterministic — all test files share one complete stub."
  - "Leave the pre-existing per-file stubs in test_subcommands.py / test_live_integration.py / test_thread_persistence.py untouched. The conftest stub runs first, their `setdefault` calls become no-ops. Touching those per-file stubs would be scope creep (not required by acceptance)."
  - "Did NOT add a separate try/except for the harvest branch. The existing `except httpx.HTTPStatusError | ConnectError | TimeoutException | Exception` chain at the end of _pf_dispatch already covers all upstream failures with appropriate user-facing messages; the harvest branch raises the same exception types the npc branches raise."
  - "Harvest branch returns BEFORE the verb cascade (`if verb == 'create' / 'update' / ...`), so `verb` for `:pf harvest Boar` is bound to 'boar' but never inspected. If a later verb falls through unexpectedly, the existing unknown-verb catch-all at the end of the npc chain returns the npc help text — which would be confusing for a harvest user. Accepted risk: the harvest branch always returns first, so this code path is unreachable for noun='harvest'."

requirements-completed: [HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06]

# Metrics
duration: ~6 min
completed: 2026-04-24
---

# Phase 32 Plan 05: Bot Wiring Summary

**`:pf harvest` wired in Discord: `build_harvest_embed` (pure dict → discord.Embed per D-03a + D-04), `_pf_dispatch` noun-check widened to {npc, harvest}, harvest branch re-parses `args` for comma-separated batch with multi-word name preservation (Pitfall 5), top-level usage + unknown-noun error now list both nouns. All 7 `test_pf_harvest_*` stubs flip from RED → GREEN. 38/38 interfaces/discord tests pass, 84/84 pathfinder module tests still GREEN, zero Phase 29/30/31 regressions. Phase 32 ready for `/gsd-verify-work`.**

## Performance

- **Duration:** ~6 min
- **Tasks:** 1
- **Files modified:** 2 (1 helper + noun-widen + branch in bot.py; 1 consolidated stub in conftest.py)
- **Net lines added:** 173 insertions / 3 deletions

## Accomplishments

### bot.py changes (the four landings the plan called for)

1. **`build_harvest_embed` helper (+55 lines)** placed immediately after `build_stat_embed` at the established module-helpers region. Pure function: `dict → discord.Embed`. Single-monster shape: title = `"{name} (Level {level})"`, description shows optional fuzzy-match note (italic) + `⚠ Generated — verify against sourcebook` warning when `verified: false`. Batch shape: title = `"Harvest report — N monsters"`, description shows generated-count warning if any. Fields: one per D-04 aggregated component, value = Medicine DC line + monsters-tally + craftable bullets, truncated to Discord's 1024-char field cap. Footer = `data["footer"]` (the server-composed source attribution).

2. **Noun-check widened (line 400).** `if noun not in {"npc", "harvest"}:` (was `if noun != "npc":`). Unknown-noun error message now lists both: `"Currently supported: \`npc\`, \`harvest\`."`

3. **Top-level usage string extended (lines 393-396).** When the user sends `:pf` with fewer than 2 space-split parts, the return message now reads:
   ```
   Usage: `:pf npc <create|update|show|relate|import|say> ...` or `:pf harvest <Name>[,<Name>...]`
   ```
   This preserves the pre-Phase-31 verb list verbatim and appends the harvest variant.

4. **Harvest dispatch branch (lines 405-430)** inserted inside the shared `try: async with httpx.AsyncClient() as http_client:` block, before the npc verb cascade. Re-parses `args[len("harvest"):]` (after a leading-whitespace strip) rather than using the space-split parts — multi-word monster names like `Giant Rat` survive because we only split on commas. Defensive empty-names fallback returns a plain usage string without calling `post_to_module`. On a populated name list, posts `{names: [...], user_id: ...}` to `modules/pathfinder/harvest` and returns the standard embed-dict shape `{type: "embed", content: "", embed: build_harvest_embed(result)}` that `on_message` and `/sen` already know how to render.

### conftest.py consolidation (Rule 3 blocking fix)

The per-file discord stubs in `test_subcommands.py`, `test_live_integration.py`, and `test_thread_persistence.py` all used `sys.modules.setdefault("discord", ...)` — i.e. "install this stub only if no `discord` module is already in sys.modules". Whichever test file pytest collected first won; downstream files' stub-attribute additions were silently ignored.

When I first added `Embed`/`Color` locally to `test_subcommands.py`, the 7 harvest tests passed in isolation (collected first) but `test_pf_harvest_returns_embed_dict` failed in the full suite (collected after `test_live_integration.py` which installed a stub *without* Embed/Color).

Fix: move the complete discord stub (Client, Intents, Message, Thread, ChannelType, Forbidden, HTTPException, Interaction, **Embed**, **Color**, app_commands) into `conftest.py` at module-import time, so it's registered before any test file is collected. All existing per-file `setdefault` calls become no-ops. No existing test semantics changed.

## Critical Gates Verified

### Gate 1: 7 harvest bot tests GREEN
```
cd interfaces/discord && uv run --no-sync python -m pytest tests/test_subcommands.py -k harvest -v
→ 7 passed, 27 deselected
```

- `test_pf_harvest_solo_dispatch` — posts to `modules/pathfinder/harvest` with `names=['Boar']`, `user_id='user123'`
- `test_pf_harvest_batch_dispatch` — `:pf harvest Boar,Wolf,Orc` → `names=['Boar','Wolf','Orc']`
- `test_pf_harvest_multi_word_monster` — `:pf harvest Giant Rat` → `names=['Giant Rat']` (Pitfall 5 lock)
- `test_pf_harvest_batch_trimmed_commas` — `:pf harvest Boar , Wolf , Orc` → `names=['Boar','Wolf','Orc']` (whitespace trim)
- `test_pf_harvest_empty_returns_usage` — `:pf harvest` (no names) → `isinstance(result, str)`, contains "Usage" and "harvest", `post_to_module` **not called**
- `test_pf_harvest_returns_embed_dict` — returns `{type: "embed", content: "", embed: ...}` shape (D-03a)
- `test_pf_harvest_noun_recognised` — result does NOT start with `"Unknown pf category"` (noun-widen regression guard)

### Gate 2: Full interfaces/discord suite — zero regressions
```
cd interfaces/discord && uv run --no-sync python -m pytest tests/ -q
→ 38 passed, 50 skipped (live-integration skips when OBSIDIAN_BASE_URL unset)
```

### Gate 3: Pathfinder module suite — zero regressions
```
cd modules/pathfinder && uv run python -m pytest tests/ -q
→ 84 passed
```

### Gate 4: Plan acceptance greps
```
grep -cE '^def build_harvest_embed\('                                → 1
grep -cF 'modules/pathfinder/harvest'                                → 1
grep -cF 'build_harvest_embed(result)'                               → 1
grep -cF 'if noun not in {"npc", "harvest"}:'                        → 1
grep -cF 'Currently supported: `npc`, `harvest`.'                    → 1
grep -cF 'Usage: `:pf npc <create|update|show|relate|import|say>'    → 1 (preserved)
grep -cF ':pf harvest <Name>[,<Name>...]'                            → 3 (top-level usage + defensive fallback + comment)
grep -cF 'discord.Color.dark_green()'                                → 1
grep -cF 'Generated — verify against sourcebook'                     → 1
grep -cF '[:1024]'                                                   → 1
grep -cF 'zero args is caught by the generic'                        → 1 (Warning 4 comment preserved)
grep -nE '(TODO|FIXME|NotImplementedError)' bot.py                   → none (AI Deferral Ban)
```

### Gate 5: End-of-phase contract verification
```
grep -F 'harvest <Name>[,<Name>...]'         interfaces/discord/bot.py  → PASS
grep -F 'Currently supported: `npc`, `harvest`' bot.py                  → PASS
grep -F 'patch_frontmatter_field' modules/pathfinder/app/routes/harvest.py → PASS (0 matches — cache write uses GET-then-PUT)
REGISTRATION_PAYLOAD route count                                         → 13
```

### Gate 6: ruff clean on modified files
```
uvx ruff check interfaces/discord/bot.py interfaces/discord/tests/conftest.py
→ All checks passed!
```

(Pre-existing F841 warnings in `test_subcommands.py` lines 242, 310, 331, 349, 375, 395 are from Phase 29-31 tests — all outside the scope of this plan and not introduced by my changes.)

### Gate 7: Smoke test (plan's in-file Python block)
All 4 async asserts pass in order:
- `build_harvest_embed(data)` runs without exception and returns a non-None embed
- `:pf harvest Boar` — `post_to_module` receives `modules/pathfinder/harvest` path + `names=['Boar']` + returns embed dict
- `:pf harvest Giant Rat` — names preserved as `['Giant Rat']`
- `:pf harvest Boar , Wolf , Orc` — trimmed to `['Boar', 'Wolf', 'Orc']`
- `:pf harvest` (empty) — returns usage string, `post_to_module` NOT invoked

## Task Commits

Single atomic commit per the plan's single-task structure:

1. **Task 32-05-01** (feat): `d8f419b` — `feat(32-05): wire :pf harvest dispatch + build_harvest_embed`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Discord stub in test files missing `Embed` and `Color`**
- **Found during:** Task 32-05-01, when running `pytest tests/` against the full interfaces/discord suite.
- **Issue:** The discord stubs in `test_subcommands.py`, `test_live_integration.py`, and `test_thread_persistence.py` pre-date any test that exercises `discord.Embed(...)` / `discord.Color.dark_green()`. They all use `sys.modules.setdefault("discord", ...)` — the first file collected registers its (incomplete) stub, later files' stub setup becomes a no-op. `test_pf_harvest_returns_embed_dict` passed in isolation (test_subcommands.py collected first) but failed in the full suite (test_live_integration.py collected first, its stub lacks Embed/Color, `build_harvest_embed` raises `AttributeError` → caught by dispatcher's outer except → returns error string, test assertion `isinstance(result, dict)` fails).
- **Fix:** Consolidated the full discord stub into `interfaces/discord/tests/conftest.py`. Conftest imports run before any test file is collected, so the stub is deterministic regardless of collection order. Added Embed + Color class stubs alongside the existing Client/Intents/Thread/etc. Pre-existing per-file stubs' `setdefault` calls become no-ops — no cascading changes needed.
- **Files modified:** `interfaces/discord/tests/conftest.py` (+87 lines)
- **Commit:** `d8f419b`

**2. [Rule 1 — Bug] Extra-whitespace-before-harvest parse bug (defensive fix)**
- **Found during:** Task 32-05-01 during internal review before running tests.
- **Issue:** The plan's suggested parse was `harvest_args = args[len("harvest"):].strip()`. If the upstream `:pf` split produces leading whitespace in `args` (e.g. `:pf  harvest Boar` with two spaces → `args = " harvest Boar"`), the unstripped slice yields `"rvest Boar"` — wrong. While the Phase 31 `_route_message` splitter uses `message[1:].split(" ", 1)` which trims cleanly for single-space inputs, I cannot guarantee no caller produces padded args.
- **Fix:** Strip leading whitespace before the slice: `stripped_args = args.strip(); harvest_args = stripped_args[len("harvest"):].strip()`. Added an explanatory comment noting why `.lstrip("harvest")` is unsafe (it'd strip any character in `{h,a,r,v,e,s,t}`).
- **Files modified:** `interfaces/discord/bot.py` (2 additional lines inside the harvest branch)
- **Commit:** `d8f419b` (same atomic commit)

### Structural Scope Check

- **`if verb == "create":` vs `elif verb == "create":`:** The plan's Edit 4 instructions placed the harvest branch inside the existing `try:` block, before the `if noun == "npc":` / verb cascade. After inserting, the first post-harvest branch in the original file read `elif verb == "create":`, which only makes syntactic sense if attached to a prior `if`. I changed it to `if verb == "create":` (standalone) so the file continues to parse cleanly; subsequent `elif verb == "update":` etc. now attach to this new `if`. Behaviourally identical to the prior single `if/elif/elif` cascade for the npc path, because: (a) when `noun == "harvest"`, the harvest branch always returns before reaching the verb cascade; (b) when `noun == "npc"`, the verb cascade runs exactly as before — `if` opens the chain, `elif`s chain off it.

### AI Deferral Ban Compliance

- Zero `TODO`, `FIXME`, `NotImplementedError`, `pass` stubs, or `# noqa` / `# type: ignore` suppressions introduced in `bot.py` or `conftest.py`.
- Pre-existing `pass` in `conftest.py` is inside a best-effort teardown `except` — untouched (scope boundary: out-of-plan).

## Authentication Gates

None — all execution was offline (pytest against host venv using the stubbed discord module). No Discord API calls, no Sentinel Core calls, no Obsidian traffic.

## Issues Encountered

1. `sys.modules.setdefault` collection-order race (captured above as Rule 3 deviation). Resolved inline; no human intervention needed.

## Verification

### Plan verification block (7/7 PASS)

- **Gate 1 (7 harvest bot tests GREEN):** `pytest tests/test_subcommands.py -k harvest -q` → `7 passed, 27 deselected`
- **Gate 2 (no Phase 29-31 regressions in discord):** `pytest tests/ -q` → `38 passed, 50 skipped`
- **Gate 3 (no module regressions):** `pytest modules/pathfinder/tests/ -q` → `84 passed`
- **Gate 4 (acceptance greps):** all 12 pattern checks match (counts above)
- **Gate 5 (end-of-phase contract greps):** all 4 PASS (harvest usage, noun-list, no PATCH in route, 13 routes registered)
- **Gate 6 (ruff clean on modified files):** `All checks passed!`
- **Gate 7 (smoke test block):** `OK`

## Known Stubs

None. `build_harvest_embed` is fully implemented, handles both single-monster and batch shapes, gracefully defaults missing fields with `.get(..., '?')` fallbacks, and truncates field values to Discord's 1024-char cap. The `if noun == "harvest"` branch is fully wired; no placeholders, no mock returns, no `pass` stubs, no deferred work.

## Carried-Forward Deferred Items (from 32-CONTEXT.md)

These were explicitly out-of-scope for Phase 32 per the context document and remain deferred, not introduced by this plan:

- **Medicine-check roll simulation** — DM rolls physically or in Foundry; the tool only states the DC. Candidate: Phase 33 (`:pf rules`) or separate.
- **Inventory tracking across sessions** — "how many hides does the party have?" No cross-session ledger. Future milestone.
- **Crafting timelines / time-to-craft** — Crafting DC is stated; time-to-craft is a rules-engine concern. Candidate: Phase 33.
- **Rules-engine integration for harvesting-specific rulings** — belongs to Phase 33 (`:pf rules`).
- **Session-log append of each harvest event** — belongs to Phase 34 (`:pf session log`).

## Carried-Forward Limitation (from 32-RESEARCH.md Pitfall 7)

**Seed-level locking on fuzzy matches.** When `:pf harvest Alpha Wolf` fuzzy-matches to the seed's `Wolf` (L1), the response uses the seed Wolf's level-1 Medicine DC even if the DM intended `Alpha Wolf` to be a level-3 variant. The response includes a note surfacing the match, but the DC is not adjusted. DMs must mentally adjust the DC for scaled variants until v2 introduces an explicit level-override syntax (candidate: `:pf harvest Wolf/5` → override DC to level-5 table). Not a bug — documented behaviour.

## Manual Smoke Test Checklist

(For human to run after deployment — 5 items per 32-VALIDATION.md Manual-Only section. Automated gates above cover the full HTTP + bot test contract.)

```
sentinel.sh up
# Then in Discord:
:pf harvest Boar                     # expect: single-monster embed, seed hit, green color
:pf harvest Boar,Wolf,Orc            # expect: aggregated-by-component embed, mixed-sources footer
:pf harvest Barghest                 # expect: out-of-seed → LLM fallback, ⚠ generated warning in description
:pf harvest 'Wolf Lord'              # expect: fuzzy below cutoff → LLM fallback
:pf harvest 'Alpha Wolf'             # expect: fuzzy above cutoff → seed Wolf + italic note
# Then open mnemosyne/pf2e/harvest/barghest.md in Obsidian — verify frontmatter has verified: false.
```

## User Setup Required

None. No new dependencies, no container rebuild, no config changes. Phase 32's runtime state (160-monster YAML seed at `modules/pathfinder/data/harvest-tables.yaml`, POST /harvest route registered with Sentinel Core) is already live from Plan 32-04.

## Next Phase Readiness

- **Phase 32 ready for `/gsd-verify-work 32`.** All five plans shipped; HRV-01..06 satisfied end-to-end (HTTP route + Obsidian cache + bot dispatch + embed rendering). Run `/gsd-verify-work 32` next.
- **v0.5 phase progress:** 5/9 phases complete after Phase 32 verification (28, 29, 30, 31, 32). Next candidate phases: 33 (Rules Engine), 34 (Session Notes), 35 (Foundry VTT Event Ingest), 36 (Foundry NPC Pull Import).

## Self-Check

**Created files exist:**

- `.planning/phases/32-monster-harvesting/32-05-bot-wiring-SUMMARY.md` — FOUND (this file)

**Modified files verified:**

- `interfaces/discord/bot.py` — MODIFIED (build_harvest_embed helper at line 317, noun-widen at line 400, harvest branch at lines 405-430, top-level usage at lines 393-396)
- `interfaces/discord/tests/conftest.py` — MODIFIED (session-level discord stub with Embed/Color)

**Commits exist:**

- `d8f419b` — FOUND (feat(32-05): wire :pf harvest dispatch + build_harvest_embed)

## Self-Check: PASSED

## TDD Gate Compliance

This plan's single task has `type="execute" autonomous="true"` (not `tdd="true"`) — TDD gate enforcement does not apply here directly. However, the plan follows the phase-level Wave-0 RED → Wave-4 GREEN discipline established by Plan 32-01: the 7 `test_pf_harvest_*` stubs were authored as failing tests in Plan 32-01 (commit `8b38a25`) and flipped to GREEN by this plan (commit `d8f419b`). Gate sequence in `git log`:

- **RED commit (Plan 32-01):** `8b38a25` — `test(32-01): append 7 harvest dispatch test stubs`
- **GREEN commit (this plan):** `d8f419b` — `feat(32-05): wire :pf harvest dispatch + build_harvest_embed`

RED→GREEN sequence preserved at the Wave level.

---
*Phase: 32-monster-harvesting*
*Completed: 2026-04-24*
