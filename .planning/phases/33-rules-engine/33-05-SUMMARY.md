---
phase: 33
plan: 05
subsystem: interfaces/discord + scripts (rules-engine bot wiring + live UAT)
wave: 4
tags: [discord, bot, dispatch, uat, rules, pf2e, live-test]
requires:
  - Wave 0: 33-01 (10 RED bot-dispatch stubs + conftest Color extension + uat_rules.py skeleton + uat_phase33.sh orchestrator skeleton)
  - Wave 1: 33-02 (app/rules.py pure transforms + corpus)
  - Wave 2: 33-03 (app/llm.py 4 helpers + RETRIEVAL_SIMILARITY_THRESHOLD=0.65)
  - Wave 3: 33-04 (4 HTTP endpoints + lifespan wiring + REGISTRATION_PAYLOAD 14)
provides:
  - interfaces/discord/bot.py — _PF_NOUNS widened to {npc,harvest,rule}; build_ruling_embed helper; 'rule' dispatch branch with 4 sub-verbs + D-11 placeholder-edit UX
  - scripts/uat_rules.py — 16 real live-UAT assertions (L-10 pre-check + UAT-1..16)
  - scripts/uat_phase33.sh — 5-step orchestrator (rebuild / healthy / 14-route / LM-Studio-smoke / run-UAT)
affects:
  - none downstream in Phase 33 — this is the terminal wave
  - Future Phase 33.x (Monster Core ingest) will extend /rule routes but bot surface stable
tech-stack:
  added: []  # no new Python deps; Wave 1 already dual-shipped numpy+bs4+lxml
  patterns:
    - "D-10 reserved-sub-verb router: parts[1] in {show,history,list} wins; else sub_verb='query' with the entire post-noun string as sub_arg"
    - "D-11 slow-query placeholder UX: channel.send placeholder → await upstream → placeholder.edit with embed → return type='suppressed' so outer handler does not re-send"
    - "defensive isinstance(result, dict) guards on .get() in show/history/list branches — upstream 404 / test mocks returning strings degrade to empty-list handler rather than raising into the outer except"
    - "conftest-central Color stub (L-5): discord.Color.{dark_green,dark_gold,red} resolved once in interfaces/discord/tests/conftest.py; zero per-test-file stubs"
    - "UAT runner with record() + _TEARDOWN_CACHE_PATHS: every assertion passes or records a real failure; _TEARDOWN_CACHE_PATHS accumulates Obsidian paths written; end-of-run DELETE loop cleans them"
key-files:
  created:
    - none  # every modified file pre-existed as a Wave-0 skeleton
  modified:
    - interfaces/discord/bot.py  # 1261 total lines (+195 net)
    - interfaces/discord/pyproject.toml  # 1-line build-backend fix
    - scripts/uat_rules.py  # 841 total lines (Wave 0 skeleton → 16 real assertions)
    - scripts/uat_phase33.sh  # 156 total lines (Step 4 LM Studio smoke added; set -e fix)
decisions:
  - D-10 bot wiring: 'rule' sub-verb router with reserved-set {show, history, list}; default = query
  - D-11 slow-query UX: placeholder+edit via channel.send → placeholder.edit (type='suppressed')
  - D-15 scope-lock POSITIVE: UAT-14 asserts Monster Core query marks 'generated' (not declined)
  - L-5 single conftest Color stub retained; zero per-file Color shims in test_subcommands.py
  - L-7 proxy-path correctness: every rule-branch post_to_module uses modules/pathfinder/rule/{query|show|history|list}; never bare 'modules/pathfinder/rule' or 'modules/pathfinder/run'
  - L-9 HTTP timeouts: rely on the existing _pf_dispatch async-client default (5s connect, no read cap) + sentinel-core proxy's own 60s+ ceiling; placeholder UX hides first-call LM Studio latency
  - Rule 1 bug-fix on uat_rules.py: UAT-9 + UAT-13 false-positive guards added after pre-merge smoke revealed assertions that passed on 404/error-string responses
  - Rule 3 unblock: interfaces/discord/pyproject.toml build-backend changed from the invalid 'setuptools.backends.legacy:build' to 'setuptools.build_meta' so uv sync / pytest could run in this worktree
metrics:
  start: 2026-04-24
  completed: 2026-04-24
  tasks: 5 of 6 fully executed in-worktree; Task 33-05-05 (live UAT) and 33-05-06 (human-verify checkpoint) defer to post-merge per worktree isolation boundary
  files: 4 modified
  commits: 5
---

# Phase 33 Plan 05: Rules Engine Bot Wiring + Live UAT — Wave 4 Summary

**One-liner:** Discord bot now dispatches `:pf rule <verb>` to the four Wave-3 rules endpoints with D-08 embed rendering (marker-branched color + [GENERATED — verify] banner + reuse italic), D-11 placeholder-edit UX for the slow query path, L-7-correct proxy paths, and a 16-assertion live-stack UAT harness + 5-step orchestrator. All 10 Wave-0 RED bot-dispatch stubs flip GREEN.

## Requirements Covered

| Req | Title | Status | Evidence |
|-----|-------|--------|----------|
| RUL-01 | Corpus-hit ruling with Paizo citations | Wired | `:pf rule <question>` → POST /modules/pathfinder/rule/query; marker='source' renders dark_green embed with Source + Citations fields |
| RUL-02 | `[GENERATED — verify]` fallback when corpus misses | Wired | marker='generated' renders dark_gold embed with "⚠ **[GENERATED — verify]**" banner prepended to description |
| RUL-03 | Reuse match ≥ 0.80 returns cached ruling | Wired | reuse_note italic prepended to embed description when reused=True (D-08 passthrough from Wave 3) |
| RUL-04 | PF1 scope decline | Wired | marker='declined' renders red embed with "🚫 PF1/pre-Remaster query declined" banner |

## What Shipped

### `interfaces/discord/bot.py`

**Three changes:**

1. **`_PF_NOUNS` widened** (line 188): `frozenset({"npc", "harvest"})` → `frozenset({"npc", "harvest", "rule"})`
2. **Top-level `:pf` usage string extended** (in `_pf_dispatch` early-return): now lists the rule noun alongside npc and harvest
3. **`build_ruling_embed(data: dict) -> discord.Embed`** added after `build_harvest_embed` — renders the Wave-3 D-08 response shape:
   - title = `question[:250]` (defensive against long inputs)
   - description = `_{reuse_note}_` (if reused) + marker banner (`[GENERATED — verify]` / decline prefix) + answer; joined with `\n\n`; truncated to 4000 chars
   - color branched on marker: `dark_green` (source) / `dark_gold` (generated) / `red` (declined), default `dark_gold`
   - Why field (always, when present), Source field (only if source non-null), Citations field (only if citations non-empty; capped at 3 for embed space; renders book + page + section + url)
   - footer = `"topic: <topic> | ORC license (Paizo) — Foundry pf2e"`
4. **`_pf_dispatch` 'rule' branch** added after the `if noun == "harvest":` block — 4 sub-verbs:

| Sub-verb | Trigger | Path | Payload | Returns |
|---|---|---|---|---|
| `query` | default `<free text>` | `modules/pathfinder/rule/query` | `{query, user_id}` | `{type:"suppressed"\|"embed", embed:<Embed>}` |
| `show` | `show <topic>` | `modules/pathfinder/rule/show` | `{topic}` | `str` listing cached rulings or `_No rulings under \`topic\`._` |
| `history` | `history [N]` (N clamped [1,100], default 10) | `modules/pathfinder/rule/history` | `{n}` | `str` enumerating recent rulings or `_No rulings yet._` |
| `list` | `list` | `modules/pathfinder/rule/list` | `{}` | `str` listing topic folders or `_No rulings cached yet._` |

**Reserved-set router:** `parts[1]` in `{show, history, list}` wins; otherwise `sub_verb="query"` and the entire post-noun string becomes `sub_arg`. Bare `:pf rule` falls through to the top-level usage early-return (Task 01); whitespace-only tail returns the per-noun usage string.

**D-11 placeholder-edit UX (query path only):**

1. If `channel` has `.send`, send a `"🤔 _Thinking on PF2e rules: {sub_arg[:80]}..._"` placeholder FIRST.
2. `await _sentinel_client.post_to_module("modules/pathfinder/rule/query", ...)`.
3. On success: `placeholder.edit(content="", embed=build_ruling_embed(result))` and return `{"type": "suppressed", "content": "", "embed": embed}` so the outer handler does NOT re-send.
4. On exception: `placeholder.edit(content=f"⚠ Rules query failed — {exc}", embed=None)` and return suppressed (error surfaces in the same message slot).
5. When `channel is None` or `.send` raises: no placeholder; return `{"type": "embed", "content": "", "embed": embed}` directly (test harness graceful degradation).

### `interfaces/discord/pyproject.toml`

**Rule 3 unblock:** `build-backend = "setuptools.backends.legacy:build"` → `build-backend = "setuptools.build_meta"`. The prior path is not a valid setuptools backend — `uv sync` failed with `ModuleNotFoundError: No module named 'setuptools.backends'`. The discord venv could not be (re)created without this fix; the test suite could not run. The same defect still exists in `sentinel-core/pyproject.toml` on main (out of scope for this wave; documented here as a Deferred Issue below).

### `scripts/uat_rules.py`

**Wave-0 skeleton → 16 real live-stack assertions.** Preserves the Wave-0 env bootstrap (sys.path, discord stub with Color dark_gold + red), the L-10 LM Studio pre-check, the record() reporter, and the `_TEARDOWN_CACHE_PATHS` / teardown loop. Every record() call either passes or records a real failure (no silent skips beyond the LIVE_TEST=1 gate).

**Assertion coverage (mapped to RESEARCH.md §Live-UAT Plan):**

| UAT | Scope | Assertion shape |
|---|---|---|
| L-10 pre-check | LM Studio `/v1/embeddings` reachable + `text-embedding-nomic-embed-text-v1.5` loaded | status=200 + data[0].embedding non-empty |
| UAT-1 | flanking source hit | status=200 + marker∈{source,generated} + D-08 shape (question/answer/why/citations) |
| UAT-2 | off-guard source hit | marker='source' + citation.book startswith 'Pathfinder Player Core' |
| UAT-3 | Kineticist edge case (advanced book) generated | marker='generated' + source=None + citations=[] |
| UAT-4 | PF1 decline THAC0 — no cache write | marker='declined' + answer starts 'This Sentinel only supports PF2e Remaster' + Obsidian GET 404 at would-be path |
| UAT-5 | PF1 decline spell schools | marker='declined' + 'spell school' in answer |
| UAT-6 | Remaster soft-trigger (flat-footed after trip) passes | marker ≠ 'declined' |
| UAT-7 | Identical-query cache hit | dt<3s OR reused=True on second identical query |
| UAT-8 | Reuse match ≥ 0.80 | reused=True + reuse_note contains 'reuse'/'prior ruling' |
| UAT-9 | Dissimilar query composes fresh | status=200 + marker∈{source,generated} + reused=False (false-positive guarded) |
| UAT-10 | Topic-folder browsability | POST /rule/show flanking returns count ≥ 1 |
| UAT-11 | `:pf rule <text>` via bot returns embed dict | type∈{suppressed, embed} + embed is not None |
| UAT-12 | `:pf rule show <topic>` returns str | 'flanking' or 'no rulings' or 'rulings under' in response |
| UAT-13 | `:pf rule history` returns str | 'recent rulings' OR 'no rulings yet' OR 'rulings (' in response (false-positive guarded) |
| UAT-14 | **D-15 scope-lock POSITIVE** — Monster Core query marks 'generated' | marker='generated' (NOT 'declined') — proves PF1 denylist does not over-fire |
| UAT-15 | D-11 slow-query placeholder UX | channel.send called once with 'thinking' + placeholder.edit called with embed |
| UAT-16 | Stack smoke | sc/health 200 + pf/healthz 200 + len(routes)==14 + 'rule' in routes |

**False-positive guards (Rule 1 bug-fix):** pre-merge smoke run revealed UAT-9 and UAT-13 both passed despite upstream 404 / generic error string. Fixed:
- UAT-9 now requires status==200 + marker presence in addition to reused=False
- UAT-13 now requires the response to mention rulings (or the empty-list literal) — the three shapes the rule history branch produces on success

**Teardown:** `_TEARDOWN_CACHE_PATHS` accumulates `mnemosyne/pf2e/rulings/{topic}/{sha1(normalize_query(q))[:8]}.md` for every successful query that wrote a cache (via `_track_cache_path`); end-of-script loop DELETEs each path via Obsidian REST API. Failures logged but non-fatal.

### `scripts/uat_phase33.sh`

**Wave-0 4-step orchestrator → 5-step with LM Studio in-container smoke + set -e fix.**

| Step | Action | Fail mode |
|---|---|---|
| 1 | `./sentinel.sh --pf2e --discord up -d --build` | (compose errors surface directly) |
| 2 | Wait up to 90s for sentinel-core /health 200 + pf2e-module (healthy) | exit 1 with `docker ps` diagnostic + last 50 lines of pf2e-module logs |
| 3 | Retry up to 20×2s for GET /modules → pathfinder.routes length == 14 | exit 1 with `"expected 14 routes, got $ROUTES"` |
| 4 (**NEW**) | `docker exec pf2e-module python -c "..."` asserts embed_texts() from inside the module's own network namespace | exit 1 with `"LM Studio embedding model likely not loaded"` |
| 5 | Run `scripts/uat_rules.py` with LIVE_TEST=1 + host-rewritten Obsidian URL via `uv run --no-sync python` | surfaces the uat_rules.py exit code directly |

**Bug-fix (Rule 1):** wrapped the `uv run` invocation in `set +e` / `set -e`. The script's top-level `set -euo pipefail` would have killed the script on any non-zero uv-run exit BEFORE the `UAT_EXIT=$?` capture, silently masking which UAT failed. With `set +e` around the invocation the exit code reaches the report block correctly.

## Task Commits

| Hash | Task | Message |
|---|---|---|
| `20b8469` | 33-05-01 | `feat(33-05): Task 01 — widen _PF_NOUNS + build_ruling_embed helper (Wave 4)` |
| `fc16cff` | 33-05-02 | `feat(33-05): Task 02 — _pf_dispatch 'rule' branch with 4 sub-verbs (Wave 4)` |
| `bc6301c` | 33-05-03 | `test(33-05): Task 03 — flesh out uat_rules.py to 16 real assertions (Wave 4)` |
| `5d23bba` | 33-05-04 | `test(33-05): Task 04 — add LM Studio in-container smoke + set -e fix (Wave 4)` |
| `64bbed7` | (Rule-1 bug-fix, shipped under Task 03) | `fix(33-05): UAT-9 and UAT-13 false-positive guards (Wave 4)` |

## Test Results

### In-worktree (Python-level)

| Suite | Count | Status |
|---|---|---|
| `interfaces/discord/tests/test_subcommands.py` — 10 Wave-0 RED `test_pf_rule_*` stubs | 10 / 10 | **All GREEN** |
| `interfaces/discord/tests/test_subcommands.py` — full file | 44 / 44 | All passing (34 pre-existing + 10 new) |
| `interfaces/discord/tests/` (full) | 48 passed, 50 skipped | No regression; skipped = integration (require live Obsidian) |

`uat_rules.py` syntax: `ast.parse(...)` OK.  
`uat_phase33.sh` syntax: `bash -n` OK. `test -x` OK.

### Pre-merge live smoke (against Wave-2 running stack)

Ran `uat_rules.py` directly against the running Docker stack (which is on Wave-2 code — 13 routes, no `/rule/*` endpoints) to verify the harness itself works end-to-end. Result: **1/17 passed** — only the L-10 LM Studio pre-check (status=200, dim=768) passed; all 16 UAT-N correctly FAILED with diagnostic detail:

- UAT-1..10: status=404 from missing `/rule/*` routes
- UAT-11..15: 404 propagates to bot outer except → returns `'NPC not found.'` → bot-layer assertions fail
- UAT-16: `routes=13 rule_present=False`

This is the expected pre-merge state; the diagnostic output confirms the harness is correctly wired end-to-end and will flip to 16/16 once Wave 3 + Wave 4 land on main and containers rebuild.

## Deviations from Plan

### Rule 1 — Auto-fixed bugs

**1. UAT-9 false positive (reuse match < 0.80 composes fresh)**
- **Found during:** pre-merge smoke run of uat_rules.py against the Wave-2 stack
- **Issue:** Assertion was `ok = body.get("reused", False) is False`. When the route returned 404, body={}, so `.get("reused", False)` returned False and the assertion passed without ever exercising the route. False GREEN in a diagnostic-only run is a silent failure.
- **Fix:** Now requires `status == 200 AND body.get("marker") in ("source", "generated") AND reused is False`. If any precondition fails, the assertion FAILs with the actual status/marker in the detail.
- **Files modified:** `scripts/uat_rules.py`
- **Commit:** `64bbed7`

**2. UAT-13 false positive (:pf rule history returns str)**
- **Found during:** pre-merge smoke run of uat_rules.py against the Wave-2 stack
- **Issue:** Assertion was `ok = isinstance(result, str) and len(result) > 0`. When the bot's outer `except` caught a 404 from the missing `/rule/history` route, it returned the string "NPC not found." — a non-empty string that satisfied the assertion without proving the history branch ran.
- **Fix:** Now requires the response to contain one of the three shapes the rule history branch produces: `'recent rulings'` (when N>0 results), `'no rulings yet'` (empty), or `'rulings ('` (count-prefixed).
- **Files modified:** `scripts/uat_rules.py`
- **Commit:** `64bbed7`

**3. `scripts/uat_phase33.sh` set -e masks UAT exit code**
- **Found during:** Task 04 review
- **Issue:** Script top-level `set -euo pipefail` would have killed execution on any non-zero `uv run python uat_rules.py` exit BEFORE `UAT_EXIT=$?` could capture the code, silently masking which UAT failed and why.
- **Fix:** Wrapped the `uv run` invocation in `set +e` / `set -e` so the exit code reaches the report block.
- **Files modified:** `scripts/uat_phase33.sh`
- **Commit:** `5d23bba` (bundled with Task 04)

### Rule 3 — Auto-fixed blocking issue

**4. `interfaces/discord/pyproject.toml` invalid build-backend**
- **Found during:** Task 01 — `uv sync` at worktree startup failed with `ModuleNotFoundError: No module named 'setuptools.backends'`
- **Issue:** `build-backend = "setuptools.backends.legacy:build"` is not a valid setuptools backend path. The correct canonical backend for the standard `[build-system] requires = ["setuptools", "wheel"]` shape is `setuptools.build_meta`. Without this, the discord venv cannot be (re)created, pytest cannot run, and the 10 Wave-0 RED test_pf_rule_* stubs cannot be verified GREEN.
- **Fix:** Changed to `build-backend = "setuptools.build_meta"`. `uv sync --all-extras` now succeeds; pytest installs and runs.
- **Files modified:** `interfaces/discord/pyproject.toml`
- **Commit:** `20b8469` (bundled with Task 01)
- **Scope note:** The same defect exists in `sentinel-core/pyproject.toml` on main. Out of scope for this wave — flagged here for the human operator.

### Plan-text correction

**5. Exception-path content must contain "failed" (not "error")**
- **Found during:** Task 02
- **Issue:** Plan template specified `content=f"⚠ Rules engine error — {exc}"` for the placeholder-edit exception path. But Wave-0 test `test_pf_rule_placeholder_edit_on_exception` asserts `"failed" in edit_kwargs.get("content", "").lower()`. "error" does not contain "failed".
- **Fix:** Used `f"⚠ Rules query failed — {exc}"` — functionally equivalent, satisfies the Wave-0 test contract.
- **Files modified:** `interfaces/discord/bot.py`
- **Commit:** `fc16cff` (Task 02)

### Deferred to post-merge (structural worktree constraint — NOT an AI deferral)

**6. Task 33-05-05 — live-stack UAT 16/16 GREEN run**
- **Found during:** Task 05
- **Issue:** The running Docker stack is built from main-branch source (Wave-2 code); rebuilding `pf2e-module` + `discord` against the worktree directly would either leave the main stack broken until merge or require a separate compose profile with port collisions. The plan's Task 05 invocation (`cd /Users/trekkie/projects/sentinel-of-mnemosyne && ./scripts/uat_phase33.sh`) explicitly targets the MAIN REPO ROOT — not the worktree — so the 14-route registration gate at Step 3 would fail with `routes=13` until the worktree merges to main.
- **What I did instead:**
    - Ran `uat_rules.py` directly against the pre-merge running stack (Wave 2 code) with credentials from `.env` to verify the harness operates end-to-end. Result: 1/17 passed (L-10 pre-check only) — all 16 UAT-N correctly failed with diagnostic detail. This confirms the script is wired correctly and will flip to 16/16 once Wave 3 + Wave 4 deploy.
    - Fixed two false positives discovered during this smoke run (UAT-9, UAT-13 — see Rule 1 bug-fixes above).
    - Verified `bash -n scripts/uat_phase33.sh` and `python3 -c "import ast; ast.parse(open('scripts/uat_rules.py').read())"` both pass.
- **What the orchestrator must do post-merge:** after merging this worktree to main, run `./scripts/uat_phase33.sh` from the main repo root. Expected terminal output: `── UAT Summary: 17/17 passed ──` (or `16/16` depending on whether the L-10 pre-check is counted). The evidence file `.planning/phases/33-rules-engine/33-UAT-RESULT.md` should be written by that run: `./scripts/uat_phase33.sh 2>&1 | tee .planning/phases/33-rules-engine/33-UAT-RESULT.md`.
- **Note:** Wave 3's Task 33-04-05 applied the same structural deferral (see 33-04-SUMMARY.md §"Deferred to post-merge").

**7. Task 33-05-06 — checkpoint:human-verify in-Discord visual verification**
- **Found during:** Task 06
- **Issue:** This task requires live Discord interaction (running `:pf rule <question>` in the `/sen` thread, observing embed colors and banners, opening Obsidian to inspect frontmatter, re-issuing queries to verify reuse-match timing). Same worktree-isolation constraint as Task 05 applies — the running discord container is on Wave-2 code and would not dispatch `:pf rule` at all (would return "Unknown pf category `rule`").
- **What the orchestrator must do post-merge:** after Task 05's 16/16 UAT passes, present the `<how-to-verify>` steps from `33-05-PLAN.md` Task 33-05-06 to the human operator and await the "approved" resume-signal (or a concrete discrepancy report).

### Authentication / operational gates

None during this wave. All credentials (SENTINEL_API_KEY, OBSIDIAN_API_KEY) were available in the project `.env` for the pre-merge smoke run.

## Known Stubs

None. Every added symbol is fully implemented:
- `build_ruling_embed` has no `TODO`/`FIXME`/`pass`-stub/`NotImplementedError` — it renders a complete D-08 shape with marker-branched color, banner prepend, conditional fields, and footer.
- The 4 sub-verb dispatch branches each call `post_to_module` with a real path + payload and render the response to a real string or embed.
- `uat_rules.py` has 17 real `record()` calls; none is a stub (the Wave-0 `"stub — Wave 3/4 fills in ..."` placeholders have all been replaced).
- `uat_phase33.sh` all 5 steps execute real commands — no placeholder echoes.

## Deferred Issues (out of scope — flagged for human operator)

1. **`sentinel-core/pyproject.toml` also uses the invalid `setuptools.backends.legacy:build` backend.** The discord fix in this wave was scoped to unblock Wave 4's test verification; sentinel-core's pyproject has the same defect but was not touched. Recommendation: apply the same one-line fix (`build-backend = "setuptools.build_meta"`) in a separate infrastructure commit before the next wave of sentinel-core work.

## L-3 Verification (Obsidian PATCH constraint — project memory)

```
grep -c patch_frontmatter_field interfaces/discord/bot.py     → 0
grep -c patch_frontmatter_field scripts/uat_rules.py          → 0
grep -c patch_frontmatter_field scripts/uat_phase33.sh        → 0
```

None of this wave's modified files touch Obsidian frontmatter directly. The rule cache writes happen inside `modules/pathfinder/app/routes/rule.py` (Wave 3) via full `put_note` — unchanged from Wave 3's clean L-3 posture.

## L-5 Verification (central conftest Color stub)

```
grep -c "discord.Color.dark_gold" interfaces/discord/tests/test_subcommands.py  → 0
grep -c "discord.Color.red"       interfaces/discord/tests/test_subcommands.py  → 0
grep -c "discord.Color.dark_gold" interfaces/discord/bot.py                     → 1 (build_ruling_embed)
grep -c "discord.Color.red"       interfaces/discord/bot.py                     → 1 (build_ruling_embed)
```

Single-source-of-truth preserved: `discord.Color.{dark_gold, red}` classmethods live only in `interfaces/discord/tests/conftest.py` (Wave 0); production consumers (`bot.py`) import them from the real `discord` package; test modules do not re-stub them.

## L-7 Verification (proxy path correctness)

```
grep "modules/pathfinder/rule/" interfaces/discord/bot.py:
  - modules/pathfinder/rule/query   (1×, in the query sub-verb)
  - modules/pathfinder/rule/show    (1×, in the show sub-verb)
  - modules/pathfinder/rule/history (1×, in the history sub-verb)
  - modules/pathfinder/rule/list    (1×, in the list sub-verb)

grep -E "modules/pathfinder/run\b" interfaces/discord/bot.py          → 0
grep -E 'modules/pathfinder/rule"' interfaces/discord/bot.py          → 0
```

Every rule-branch `post_to_module` call targets a valid sub-path. Zero Phase-30-class mistakes (missing sub-path or `run` typo).

## L-9 Verification (HTTP client timeouts)

The rule branch uses the existing `async with httpx.AsyncClient() as http_client:` in `_pf_dispatch` — default timeouts (5s connect, no read cap). The real per-call ceiling is the sentinel-core proxy's own 60s+ timeout (module-proxy pattern from Phase 32). The D-11 placeholder UX hides first-call LM Studio embedding-model cold-start latency (typical 5-15s, worst-case 30s) from the DM. Did not pre-optimise client.timeout per plan guidance ("catch it in UAT").

## Deviation From Plan Structure (Task 05 + Task 06)

Tasks 05 and 06 are structurally post-merge operations (see Deviations above). The orchestrator owns execution of those tasks after merging this worktree. The worktree-executable portion of Wave 4 is complete: all 10 Wave-0 RED bot-dispatch stubs GREEN; `uat_rules.py` + `uat_phase33.sh` syntactically valid and harness-wired end-to-end against the live stack.

## Self-Check: PASSED

**Files verified on disk:**
- `interfaces/discord/bot.py` (1261 lines; includes `_PF_NOUNS = frozenset({"npc", "harvest", "rule"})`, `build_ruling_embed`, and the rule-branch dispatch) — FOUND
- `interfaces/discord/pyproject.toml` (build-backend = setuptools.build_meta) — FOUND
- `scripts/uat_rules.py` (841 lines; 16 UAT-N record() calls + L-10 pre-check + _TEARDOWN_CACHE_PATHS + teardown) — FOUND
- `scripts/uat_phase33.sh` (156 lines; 5 steps including `docker exec pf2e-module ... embed_texts` smoke) — FOUND, executable (`test -x` OK)

**Commits verified on current branch:**
- `20b8469` `feat(33-05): Task 01 — widen _PF_NOUNS + build_ruling_embed helper` — FOUND
- `fc16cff` `feat(33-05): Task 02 — _pf_dispatch 'rule' branch with 4 sub-verbs` — FOUND
- `bc6301c` `test(33-05): Task 03 — flesh out uat_rules.py to 16 real assertions` — FOUND
- `5d23bba` `test(33-05): Task 04 — add LM Studio in-container smoke + set -e fix` — FOUND
- `64bbed7` `fix(33-05): UAT-9 and UAT-13 false-positive guards` — FOUND

**Grep gates (Wave-4 acceptance):**
- `_PF_NOUNS = frozenset({"npc", "harvest", "rule"})` in bot.py → 1 ✓
- `def build_ruling_embed(` in bot.py → 1 ✓
- `GENERATED — verify` in bot.py → 1 ✓
- `ORC license (Paizo)` in bot.py → 2 (docstring + code — both required for intent) ✓
- `if noun == "rule":` in bot.py → 1 ✓
- 4 sub-verb proxy paths present, 0 bad-path references ✓
- `discord.Color.dark_gold` / `.red` in test_subcommands.py → 0 / 0 (L-5) ✓
- `TODO|FIXME|XXX|NotImplementedError` in bot.py/uat_rules.py/uat_phase33.sh → 0 / 0 / 0 ✓
- `patch_frontmatter_field` in all three files → 0 (L-3 regression gate) ✓

**Test suite:**
- `uv run python -m pytest tests/test_subcommands.py -k "test_pf_rule"` → 10 passed ✓
- `uv run python -m pytest tests/` → 48 passed, 50 skipped (no regression) ✓
- `ast.parse(open('scripts/uat_rules.py'))` → VALID ✓
- `bash -n scripts/uat_phase33.sh` → OK ✓

**Pre-merge live smoke (against Wave-2 stack):**
- L-10 LM Studio pre-check: PASS (status=200, dim=768) ✓
- UAT-1..16: all FAIL with diagnostic detail (404 from missing routes — expected pre-merge state) ✓
- No false positives after Rule-1 UAT-9 / UAT-13 guards applied ✓

---
*Phase: 33-rules-engine*  
*Completed: 2026-04-24 (worktree-executable portion); live 16/16 UAT pending post-merge per Task 33-05-05 deferral*
*Phase 33 readiness: **Phase 33 Rules Engine bot-wiring complete — RUL-01..04 wired to Wave-3 HTTP surface with D-08 embed rendering and D-11 placeholder UX; live 16/16 UAT runs on next orchestrator merge.***
