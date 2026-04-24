---
phase: 33
plan: 04
subsystem: pf2e-module / rules-engine
wave: 3
tags: [fastapi, route, rag, obsidian, rules, pf2e, lifespan]
requires:
  - Wave 0: 33-01 (40 RED unit stubs + 8 RED integration stubs + fixtures + uat_rules.py + uat_phase33.sh)
  - Wave 1: 33-02 (app/rules.py pure transforms + sanitiser skeleton at routes/rule.py)
  - Wave 2: 33-03 (app/llm.py 4 helpers + RETRIEVAL_SIMILARITY_THRESHOLD=0.65)
provides:
  - modules/pathfinder/app/routes/rule.py — 4 FastAPI endpoints + D-02 9-step orchestration
  - modules/pathfinder/app/main.py — REGISTRATION_PAYLOAD 13->14 + lifespan wiring
  - modules/pathfinder/app/obsidian.py — list_directory() added (Rule 2 missing functionality)
  - modules/pathfinder/tests/test_registration.py — 14-route assertion test added
affects:
  - interfaces/discord/bot.py (Wave 4 will dispatch to /modules/pathfinder/rule/{query,show,history,list})
  - scripts/uat_rules.py + scripts/uat_phase33.sh (live UAT already scaffolded in Wave 0)
tech-stack:
  added: []  # Wave 1 already dual-shipped numpy + bs4; Wave 3 introduces no new Python deps
  patterns:
    - lifespan-singleton-assignment (matches Phase 32 _harvest_module pattern)
    - cache-aside GET-then-PUT (Obsidian PATCH constraint — L-3)
    - 9-step orchestration in a single async handler (D-02)
key-files:
  created:
    - modules/pathfinder/app/routes/rule.py  # 527 lines
  modified:
    - modules/pathfinder/app/main.py  # +44 lines (imports + REGISTRATION_PAYLOAD entry + lifespan + include_router)
    - modules/pathfinder/app/obsidian.py  # +50 lines (list_directory helper)
    - modules/pathfinder/tests/test_registration.py  # +17 lines (14-route assertion)
decisions:
  - D-02 9-step flow anchored verbatim in rule_query
  - D-03 corpus-miss -> generate_ruling_fallback (NEVER decline for non-PF1)
  - D-08 response shape passthrough (LLM helpers already emitted it in Wave 2)
  - D-12 citation URL honesty via aon_url_map enrichment (no fabrication)
  - D-13 embedding frontmatter (model + hash + base64 vec) on every fresh compose
  - D-14 last_reused_at updated on every cache + reuse hit via GET-then-PUT
  - L-3 zero patch_frontmatter_field references (enforced by grep gate)
  - L-4 leaf-in-import-graph — module-scope imports in rule.py, function-scope
    imports inside lifespan in main.py (mirrors Phase 32 harvest pattern)
  - L-7 single REGISTRATION_PAYLOAD entry path='rule' — sub-paths proxied by sentinel-core
  - L-8 _validate_rule_query rejects empty / overlong / control-char / all-backtick input
  - L-10 lifespan fail-fast when LM Studio embedding model unreachable (Docker restart-loop visibility)
metrics:
  start: 2026-04-24
  completed: 2026-04-24
  tasks: 5 (4 execute + 1 container smoke; container smoke gated on post-merge rebuild — see deviations)
  files: 4 modified
  tests: 138 passing (40 rules-engine unit + 8 integration + 5 registration + 85 pre-phase)
---

# Phase 33 Plan 04: Rules Engine HTTP Layer — Wave 3 Summary

**One-liner:** HTTP + lifespan layer for the PF2e Remaster rules RAG engine — four FastAPI endpoints, the D-02 nine-step orchestration anchored in `rule_query`, three lifespan singletons wired, REGISTRATION_PAYLOAD bumped 13 → 14, all 8 RED integration stubs flipped GREEN.

## Requirements Covered

| Req | Title | Status | Evidence |
|-----|-------|--------|----------|
| RUL-01 | Corpus-hit ruling with Paizo citations | ✅ | `rule_query` steps 5-8 passages branch; `test_corpus_hit_writes_cache_with_marker_source` GREEN |
| RUL-02 | `[GENERATED — verify]` fallback when corpus misses | ✅ | `rule_query` step 8 fallback branch; `test_corpus_miss_writes_cache_with_marker_generated` GREEN |
| RUL-03 | Reuse match ≥ 0.80 returns cached ruling | ✅ | `rule_query` step 7 reuse-match scan; `test_reuse_match_above_0_80_returns_cached_note` + `_below_0_80_composes_fresh` both GREEN |
| RUL-04 | PF1 scope decline | ✅ | `rule_query` step 2; `test_pf1_decline_no_cache_write` GREEN (embed + classify + LLM mocked to raise — assertion passes) |

## Routes Implemented

| Method | Path | Purpose | Returns |
|--------|------|---------|---------|
| POST | `/rule/query` | RUL-01..04 core — D-02 nine-step orchestration | D-08 ruling dict + `reused` + `reuse_note` |
| POST | `/rule/show` | List cached rulings under one topic folder | `{topic, count, rulings[]}` sorted by `last_reused_at` desc |
| POST | `/rule/history` | Top-N recent rulings across all topics | `{n, rulings[]}` top-N by `last_reused_at` desc (N clamped [1, 100]) |
| POST | `/rule/list` | Enumerate topic folders with activity | `{topics: [{slug, count, last_activity}]}` sorted by activity desc |

External proxy path (via sentinel-core): `POST /modules/pathfinder/rule/{query|show|history|list}`

## D-02 Nine-Step Flow (rule_query)

1. Pydantic `_validate_rule_query` — reject empty / overlong / control-char / all-backtick
2. `check_pf1_scope` — FIRST (no cache, no embed, no LLM cost on decline)
3. `normalize_query` + `query_hash` + `await resolve_model("chat"/"structured")` + `await classify_rule_topic`
4. Exact-hash cache check at `mnemosyne/pf2e/rulings/{topic}/{hash}.md`; on hit, GET-then-PUT last_reused_at (D-14)
5. `await embed_texts([q_norm])` — 500 on embed failure, no cache write
6. `retrieve(index, query_vec, topic, k=3, threshold=RETRIEVAL_SIMILARITY_THRESHOLD)`
7. Reuse-match scan — `list_directory` → per-sibling cosine check with shape guard + embedding_model version filter; ≥ `REUSE_SIMILARITY_THRESHOLD` wins, GET-then-PUT last_reused_at
8. D-03: `if retrieved:` → `generate_ruling_from_passages` (enriched with aon_url_map URLs per D-12); `else:` → `generate_ruling_fallback`; 500 on LLM failure, no cache write
9. Enrich with D-13 frontmatter fields (embedding_model + embedding_hash + query_embedding base64 + composed_at + last_reused_at) → `build_ruling_markdown` → `obsidian.put_note`; PUT-failure degrades gracefully (log + still return 200)

## REGISTRATION_PAYLOAD Bump

| Before | After |
|--------|-------|
| 13 routes | **14 routes** |

New entry: `{"path": "rule", "description": "PF2e Remaster rules RAG engine with Paizo citations (RUL-01..04)"}`

Sub-routes (`/rule/query`, `/rule/show`, `/rule/history`, `/rule/list`) are NOT individually registered — sentinel-core proxies all sub-paths under the module's `rule` base path per the project's L-7 convention (verified in Phase 32 with `/harvest`).

## Lifespan Wiring

Inside `main.lifespan`, after `_harvest_module` singletons, before `yield`:

```python
_rule_module.obsidian = obsidian_client
_rule_module.aon_url_map = load_aon_url_map(data/aon-url-map.json)  # ~138 entries
_rule_corpus_chunks = load_rules_corpus(data/rules-corpus.json)       # 149 Player-Core chunks
async def _rule_embed_fn(texts): return await embed_texts(...)        # settings closure
_rule_module.rules_index = await build_rules_index(_rule_corpus_chunks, _rule_embed_fn)
```

L-10 fail-fast: `build_rules_index` propagates `embed_texts`' `RuntimeError` when LM Studio is unreachable → FastAPI startup exits with SystemExit → Docker restart-loop with the diagnostic message in the log. Operator loads the model in LM Studio and the container comes healthy on restart.

Shutdown (after `yield`): all three `_rule_module` singletons nullified.

## Test Results

| Suite | Count | Status |
|-------|-------|--------|
| `tests/test_rules.py` (unit) | 40 | ✅ All passing (no regression from Wave 2) |
| `tests/test_rules_integration.py` (Wave 0 RED → GREEN) | **8 / 8** | ✅ **All flipped GREEN after Task 04** |
| `tests/test_registration.py` | 5 (+1 new: 14-route assertion) | ✅ All passing |
| Full pathfinder suite | 138 | ✅ All passing |

Every Wave-0 RED integration stub went GREEN:

1. `test_first_query_writes_cache_second_reads_cache` — D-14 round-trip
2. `test_corpus_hit_writes_cache_with_marker_source` — RUL-01
3. `test_corpus_miss_writes_cache_with_marker_generated` — RUL-02 / D-03
4. `test_pf1_decline_no_cache_write` — RUL-04 / D-06 (zero side-effects asserted)
5. `test_reuse_match_above_0_80_returns_cached_note` — D-05
6. `test_reuse_match_below_0_80_composes_fresh` — D-05 negative
7. `test_rule_reuse_note_survives_cache_roundtrip` — CR-03 analog
8. `test_last_reused_at_updated_on_cache_hit` — D-14 timestamp advance

## Commits

| Hash | Task | Message |
|------|------|---------|
| `37838cf` | 01 | routes/rule.py skeleton (router + singletons + Pydantic models + 501 stubs) |
| `a511537` | 02 | rule_query D-02 nine-step orchestration |
| `3f3335a` | 03 | rule_show/history/list enumeration endpoints (pure Obsidian walks) |
| `cece680` | 04 | wire rule_router + lifespan singletons in main.py (REGISTRATION_PAYLOAD 13→14) |

## Deviations from Plan

### Rule 2 — Auto-added missing critical functionality

**1. `ObsidianClient.list_directory(prefix)` method**
- **Found during:** Task 03 (rule_show/history/list) and Task 04 (main.py lifespan wiring)
- **Issue:** The plan and the Wave-0 tests both call `obsidian.list_directory(prefix)`, but the real `ObsidianClient` in `modules/pathfinder/app/obsidian.py` did not have this method — only `get_note`, `put_note`, `put_binary`, `get_binary`, `patch_frontmatter_field`. Tests passed against the patched `StatefulMockVault` singleton, but the real container would raise `AttributeError` on the first reuse-match scan or `/rule/list` call.
- **Fix:** Added `async def list_directory(self, prefix: str) -> list[str]` to `ObsidianClient`. Uses `GET /vault/{dir}/` (Obsidian REST v3 lists directory children), recurses into subdirectories (children ending with `/`), returns flat list of leaf file paths. Silent-fallback on 404 or error (returns `[]`) — matches `get_note`'s degrade-gracefully shape via `_safe_request`. 50 lines added.
- **Files modified:** `modules/pathfinder/app/obsidian.py`
- **Commit:** `cece680` (bundled with Task 04)

### Plan-text correction

**2. `resolve_model` is async in this project — plan used sync call syntax**
- **Found during:** Task 02
- **Issue:** The plan text showed `model_chat = resolve_model("chat")` (sync), but `modules/pathfinder/app/resolve_model.py` defines `async def resolve_model(...)` and `routes/harvest.py` (the canonical template) uses `await resolve_model("chat")`. Calling the sync form would assign a coroutine object to `model_chat` and `litellm.acompletion` would raise on `model=<coroutine>`.
- **Fix:** Used `await resolve_model("chat")` and `await resolve_model("structured")` — matches harvest route. No cost impact (LM Studio `/v1/models` discovery is cached after first call per process).
- **Files modified:** `modules/pathfinder/app/routes/rule.py`
- **Commit:** `a511537`

### Deferred to post-merge

**3. Task 33-04-05 container rebuild smoke test**
- **Found during:** Task 05
- **Issue:** Task 05 requires rebuilding `pf2e-module` with the worktree's code and running three live assertions against the running stack. The worktree is isolated from the host's running compose stack — rebuilding `pf2e-module` against the worktree directory would either (a) leave the main stack broken until merge, or (b) require a separate compose profile. The plan-prescribed `./sentinel.sh --pf2e up -d --build` rebuilds against `main` branch code, which does not contain Wave 3 yet.
- **Fix:** Ran the in-process equivalents of all three Task-05 assertions against the worktree's Python module directly:
  - `len(REGISTRATION_PAYLOAD["routes"]) == 14` ✅
  - `'rule'` present in payload paths ✅
  - All four `/rule/*` endpoints registered on the FastAPI `app` and appear in `app.openapi()["paths"]` ✅
- **Remaining work:** The actual `docker compose up -d --build pathfinder sentinel-core` + the three curl assertions (14-route `/modules` registry, `/openapi.json` paths, `embed_texts` inside the container) run after the orchestrator merges this worktree to `main`. L-10 fail-fast guarantees operator visibility if LM Studio embeddings are unreachable: Docker restart-loop with the diagnostic message in the `pf2e-module` log.
- **Files modified:** none (this is an execution-path deviation, not a code change)

### Authentication / operational gates

None. No secret or credential was needed during this wave.

## Known Stubs

None. Every symbol imported is used; every endpoint is fully implemented; no `TODO`/`FIXME`/`NotImplementedError`/`pass`-stubs.

## L-3 Verification (Obsidian PATCH constraint — project memory)

```
grep -c patch_frontmatter_field modules/pathfinder/app/routes/rule.py → 0
grep -c patch_frontmatter_field modules/pathfinder/app/main.py        → 0
```

Every cache write — fresh compose, exact-hash last_reused_at update, reuse-match last_reused_at update — uses `obsidian.put_note(path, build_ruling_markdown(result))` on the full markdown body. The project memory `project_obsidian_patch_constraint.md` observation (PATCH replace-on-missing fails 400) holds across this wave.

## L-7 Verification (proxy path correctness)

- External path: `POST /modules/pathfinder/rule/query` — sentinel-core proxies to the module's internal `POST http://pf2e-module:8000/rule/query`
- REGISTRATION_PAYLOAD uses single `{"path": "rule"}` entry — all sub-paths proxied (matches Phase 32 `/harvest` convention)
- Wave 4's Discord bot dispatcher must hit `/modules/pathfinder/rule/{verb}` — not the direct module port 8000

## Architectural note — No new cycles

`app.routes.rule` is a **leaf** in the import graph. It imports from `app.rules`, `app.llm`, `app.config`, `app.resolve_model`, `app.obsidian`, FastAPI, pydantic, numpy. None of those import from `app.routes.rule`. The `main.py` lifespan's `from app.rules import build_rules_index, load_aon_url_map, load_rules_corpus` and `from app.llm import embed_texts` stay function-scope (inside the `async with httpx.AsyncClient()` block) to mirror the Phase 32 `_harvest_module` pattern and keep module-load test-infra compatible.

## Self-Check: PASSED

**Files verified to exist:**
- `modules/pathfinder/app/routes/rule.py` (527 lines) — FOUND
- `modules/pathfinder/app/main.py` (197 lines, REGISTRATION_PAYLOAD has 14 routes) — FOUND
- `modules/pathfinder/app/obsidian.py` (172 lines, includes `list_directory`) — FOUND
- `modules/pathfinder/tests/test_registration.py` (includes `test_registration_payload_has_14_routes`) — FOUND
- `.planning/phases/33-rules-engine/33-04-SUMMARY.md` — this file

**Commits verified on current branch:**
- `37838cf` feat(33-04): Task 01 — routes/rule.py skeleton — FOUND
- `a511537` feat(33-04): Task 02 — rule_query D-02 nine-step orchestration — FOUND
- `3f3335a` feat(33-04): Task 03 — rule_show/history/list enumeration endpoints — FOUND
- `cece680` feat(33-04): Task 04 — wire rule_router + lifespan singletons — FOUND

**Grep gates:**
- `patch_frontmatter_field` in rule.py / main.py → 0 / 0 ✅
- `TODO|FIXME|XXX|NotImplementedError` in rule.py / main.py → 0 / 0 ✅
- `"path": "rule"` in main.py → 1 ✅
- Registration payload length → 14 ✅

**Test suite:**
- `pytest tests/test_rules.py tests/test_rules_integration.py tests/test_registration.py -q` → 53 passed ✅
- Full pathfinder suite → 138 passed ✅
