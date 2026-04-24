---
phase: 33-rules-engine
plan: 02
subsystem: rules-engine
tags: [rag, pure-transform, rules, pf2e, numpy, bs4, pydantic, orc]

requires:
  - phase: 33-01
    provides: Wave-0 RED test stubs (40 in tests/test_rules.py, 8 in tests/test_rules_integration.py, 3 fixture files)
  - phase: 32-monster-harvesting
    provides: app/harvest.py pure-transform template, _PF_NOUNS dispatch constant, L-1/L-2 landmine precedents

provides:
  - "modules/pathfinder/app/rules.py — pure-transform module with 14 public helpers (RuleChunk, RulesIndex, check_pf1_scope, cosine_similarity, retrieve, normalize_query, query_hash, coerce_topic, load_rules_corpus, load_aon_url_map, build_rules_index, strip_rule_html, build_ruling_markdown, _parse_ruling_cache, _validate_ruling_shape, _normalize_ruling_output) + constants (RETRIEVAL_SIMILARITY_THRESHOLD=0.55, REUSE_SIMILARITY_THRESHOLD=0.80, RULING_CACHE_PATH_PREFIX, MAX_QUERY_CHARS=500, RULE_TOPIC_SLUGS, _PF1_PATTERN, D_07_DECLINE_TEMPLATE)"
  - "modules/pathfinder/app/routes/rule.py — Wave 1 skeleton with _validate_rule_query sanitiser (Wave 3 extends)"
  - "modules/pathfinder/data/rules-corpus.json — 149 Player-Core chunks (D-15 enforced; zero Monster Core/GM Core book entries)"
  - "modules/pathfinder/data/aon-url-map.json — 138 hand-curated verified AoN URLs under 'Pathfinder Player Core'"
  - "modules/pathfinder/scripts/scaffold_rules_corpus.py — idempotent Foundry pf2e builder"
  - "rules_embedding_model setting in app/config.py"
  - "numpy>=1.26.0 + beautifulsoup4>=4.12.0 dual-shipped in pyproject.toml AND Dockerfile (L-1)"

affects: [33-03-wave-2-llm-plumbing, 33-04-wave-3-route-plumbing, 33-05-wave-4-discord-dispatch, future-phase-33.x-corpus-expansion]

tech-stack:
  added: [numpy>=1.26.0, beautifulsoup4>=4.12.0]
  patterns:
    - "Pure-transform module alongside route handler (mirrors app/harvest.py shape)"
    - "Dataclass + Pydantic BaseModel hybrid — RuleChunk validates external JSON, RulesIndex holds runtime numpy arrays"
    - "L-2 normalizer precedes L-2 validator (_normalize_ruling_output → _validate_ruling_shape) so LLM field-omission degrades gracefully"
    - "Dual-ship dep invariant — pyproject.toml AND Dockerfile inline pip install (Phase 32 G-1 prevention)"
    - "D-15 scope lock at ingestion boundary — scaffolding skips non-Player-Core entries with WARNING log rather than silently including them"

key-files:
  created:
    - modules/pathfinder/app/rules.py
    - modules/pathfinder/app/routes/rule.py
    - modules/pathfinder/data/rules-corpus.json
    - modules/pathfinder/data/aon-url-map.json
    - modules/pathfinder/scripts/scaffold_rules_corpus.py
  modified:
    - modules/pathfinder/pyproject.toml
    - modules/pathfinder/Dockerfile
    - modules/pathfinder/app/config.py
    - modules/pathfinder/uv.lock

key-decisions:
  - "D-05 thresholds locked in code: RETRIEVAL_SIMILARITY_THRESHOLD=0.55, REUSE_SIMILARITY_THRESHOLD=0.80 (user-confirmed; do not drift in later waves)"
  - "D-15 Player-Core-only scope enforced at scaffolder level; Monster Core / GM Core entries log WARNING and skip (zero chunks with non-Player-Core `book` field)"
  - "Per D-09, aon-url-map.json omits entries where the AoN ID is not confidently known (138 verified vs 148 total sections = 93% coverage); missing URLs render citation without URL rather than fabricating"
  - "Per RESEARCH line 457, conditions/actions have no page field in Foundry JSON; page numbers only come from the journal-footer regex. Pages-per-chunk count is 22/149 (not 50+) — D-15 scope lock makes the 50+ target unreachable from Foundry alone; a hand-curated page map is a follow-up"

patterns-established:
  - "_validate_rule_query sanitiser pattern (mirrors _validate_monster_name/_validate_npc_name): strip → empty-check → length-cap → control-char reject; accepts unicode"
  - "Frontmatter query_embedding encoded base64 (float32 LE) + embedding_model + embedding_hash triple; reuse-match (D-05) compares against runtime embedding_model and skips mismatched cached rulings"
  - "composed_at / last_reused_at iso8601-Z pair; composed_at sticks on first write, last_reused_at updates on every cache hit (D-14)"

requirements-completed: [RUL-01, RUL-02, RUL-03, RUL-04]

duration: 1h 15m
completed: 2026-04-24
---

# Phase 33 Plan 02: Rules Engine Wave 1 — Pure-Transform + Corpus Summary

**Pure-transform rules module (rules.py, 637 lines) with PF1 denylist regex, cosine retrieval, L-2 normalizer, and D-13 embedding frontmatter — plus a 149-chunk Player-Core corpus and 138-entry AoN URL map, dual-shipped numpy + bs4.**

## Performance

- **Duration:** ~1h 15m
- **Started:** 2026-04-24T20:40:00Z (approx, from first commit)
- **Completed:** 2026-04-24T21:54:41Z
- **Tasks:** 4 executed (Task 5 was "commit + push" — commits landed via Tasks 1-4; push to main is the orchestrator's job after merge)
- **Files created:** 5
- **Files modified:** 4

## Accomplishments

- **app/rules.py (637 lines, 14 public helpers)** — complete pure-transform foundation. Every RAG helper the Wave 2/3/4 code will need: PF1 denylist, cosine + retrieve with topic-filter restrict, query normalization + sha1 hash, topic-slug coercion to closed vocabulary, HTML+UUID-ref stripper, L-2 LLM-clamp normalizer/validator pair, D-13 embedding-frontmatter markdown builder/parser. No LLM calls, no Obsidian I/O, no FastAPI.
- **149-chunk Player-Core rules corpus** — scaffolded from foundryvtt/pf2e repo via the idempotent scripts/scaffold_rules_corpus.py. 28 gm-screen journal pages + 43 conditions + ~78 basic/skill/exploration actions. All 149 chunks have `book = Pathfinder Player Core` (D-15 scope lock enforced with WARNING logs for skipped non-Player-Core entries).
- **138-entry AoN URL map** — hand-curated coverage: all 42 Player-Core conditions, key rules-prose journal pages, and all Player-Core skill + basic + exploration actions. 136/149 corpus chunks now carry an aon_url after re-scaffolding.
- **Dep dual-ship (L-1 prevention)** — numpy>=1.26.0 and beautifulsoup4>=4.12.0 added to pyproject.toml AND Dockerfile inline pip install block in the same commit. Closes the Phase 32 G-1 regression vector.
- **rules_embedding_model config setting** — default `text-embedding-nomic-embed-text-v1.5`; env-configurable via `RULES_EMBEDDING_MODEL`.

## Task Commits

Each task was committed atomically (--no-verify per worktree executor protocol):

1. **Task 1: Dual-ship deps + config setting** — `f2a208a` (feat)
2. **Task 2: app/rules.py + routes/rule.py sanitiser skeleton** — `4a3b061` (feat)
3. **Task 3: scaffold_rules_corpus.py + rules-corpus.json (149 chunks)** — `42a4d22` (feat)
4. **Task 4: aon-url-map.json (138 entries)** — `feae0c0` (feat)

Task 5 ("commit + push + final verification") is satisfied by the atomic per-task commits above; push-to-main is deferred to the orchestrator after worktree merge per the parallel-executor contract.

## Files Created/Modified

**Created:**
- `modules/pathfinder/app/rules.py` (637 lines) — pure-transform RAG module
- `modules/pathfinder/app/routes/rule.py` (42 lines) — Wave 1 sanitiser skeleton (Wave 3 extends with router/models/lifespan)
- `modules/pathfinder/data/rules-corpus.json` (149 chunks, 189 KB) — committed corpus
- `modules/pathfinder/data/aon-url-map.json` (138 entries, 9 KB) — hand-curated URL map
- `modules/pathfinder/scripts/scaffold_rules_corpus.py` (260 lines) — idempotent Foundry pf2e ingester

**Modified:**
- `modules/pathfinder/pyproject.toml` — added numpy>=1.26.0, beautifulsoup4>=4.12.0
- `modules/pathfinder/Dockerfile` — mirrored same two deps in inline pip install (L-1)
- `modules/pathfinder/app/config.py` — added `rules_embedding_model` Settings field
- `modules/pathfinder/uv.lock` — refreshed for new deps (numpy 2.4.4, bs4 4.14.3, soupsieve 2.8.3)

## Test Status

**test_rules.py:** 37 passed / 3 RED-pending-Wave-2.

The 3 RED tests reference `app.llm.classify_rule_topic`, which is intentionally a Wave 2 symbol (Plan 33-03):
- `test_classify_rule_topic_returns_known_slug`
- `test_classify_rule_topic_unknown_slug_coerced_to_misc`
- `test_classify_rule_topic_malformed_json_returns_misc`

This matches the plan's acceptance floor (`≥ 37 passed`) and the Task 2 note "some may still be RED if they reference Wave 2 symbols like classify_rule_topic".

All 10 "MUST be green" tests from Task 2 acceptance pass:
- test_pf1_denylist_thac0_declines, test_pf1_soft_flat_footed_passes
- test_cosine_similarity_deterministic
- test_retrieve_above_threshold_returns_chunk, test_retrieve_with_topic_filter_restricts
- test_coerce_topic_rejects_unknown_returns_misc
- test_retrieval_threshold_constants_present
- test_build_ruling_markdown_embeds_query_embedding
- test_parse_ruling_cache_roundtrip_preserves_marker
- test_validate_ruling_shape_rejects_missing_answer

**Sanitiser + input-cap tests (MAX_QUERY_CHARS)** — all 3 GREEN:
- test_empty_query_rejected, test_query_too_long_rejected, test_unicode_query_accepted

**Regression check:** 89 prior-phase tests (Phase 28-32) pass — zero regressions.

## Decisions Made

- **Added minimal `app/routes/rule.py` in Wave 1** (not listed in the plan's Task 5 commit files, but necessary). The Wave-0 sanitiser tests import `_validate_rule_query` from `app.routes.rule` — without the file the three sanitiser tests stay RED despite being listed in the prompt's success criteria as Wave-1 GREEN gates. The skeleton file contains only the sanitiser function; Wave 3 (Plan 33-04) will add the FastAPI router, Pydantic models, and lifespan singletons to the same file. Documented as Rule 3 deviation (missing referenced file blocking task completion).
- **D-05 threshold constants match RESEARCH.md exactly** (0.55 retrieval / 0.80 reuse) — no calibration drift from plan.
- **Page-field coverage is 22/149 (not 50+)** — Foundry's pack JSON has page numbers only in journal-page footers (`Pathfinder Player Core pg. NNN`), and D-15's Player-Core-only scope lock reduces journal-page count from ~60 to ~28. Conditions (43 chunks) and skill/basic/exploration actions (~78 chunks) have no page field in Foundry JSON per RESEARCH line 457. D-09 forbids fabricating page numbers. Honoring both D-09 and D-15 caps the achievable page count below 50. See Deviations below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Created app/routes/rule.py sanitiser skeleton in Wave 1**
- **Found during:** Task 2 (running test_rules.py after rules.py landed)
- **Issue:** Three Wave-0 unit stubs (test_empty_query_rejected, test_query_too_long_rejected, test_unicode_query_accepted) import `_validate_rule_query` from `app.routes.rule` — a Wave 3 module. Without the file those tests stay RED, violating the prompt's success criterion "Wave-0 unit-stub tests in test_rules.py that target Wave-1 helpers (… MAX_QUERY_CHARS, sanitiser) flip GREEN".
- **Fix:** Created `modules/pathfinder/app/routes/rule.py` with only the `_validate_rule_query` sanitiser (42 lines). Imports `MAX_QUERY_CHARS` from `app.rules`. Wave 3 (Plan 33-04) will extend this file with FastAPI router, Pydantic models, lifespan singletons, and endpoint handlers.
- **Files modified:** modules/pathfinder/app/routes/rule.py (new file)
- **Verification:** All 3 sanitiser tests GREEN; AI Deferral Ban gate passes (no TODO/FIXME/NotImplementedError).
- **Committed in:** 4a3b061 (Task 2 commit)

**2. [Rule 4-adjacent — documentation not architectural] Page-field coverage below must_have target (22/149 vs ≥50)**
- **Found during:** Task 3 (running scaffolder against foundryvtt/pf2e repo)
- **Issue:** The plan's must_haves.truths included "≥ 50 chunks have a `page` number extracted via the 'Pathfinder Player Core pg. NNN' footer regex". Foundry's pack layout puts page numbers only in journal-page HTML footers; conditions and actions have no page field. D-15's Player-Core-only scope lock reduces journal-page count from ~60 to ~28 Player-Core pages, of which 22 have a page footer. Conditions (43) and actions (~78) contribute zero pages. Total: 22/149, below the 50 target.
- **Resolution:** Did NOT fabricate page numbers (D-09 explicit prohibition: "never fabricate citations"). Did NOT expand scope to Monster Core / GM Core journal pages (D-15 explicit prohibition). Both D-09 and D-15 are user-confirmed decisions; violating either would be a worse outcome than the lower page count. The `[GENERATED — verify]` marker (RUL-02) plus the partial page coverage is acceptable per RESEARCH line 335 ("page YES 55/60 journal pages, NO for conditions/actions").
- **Follow-up path (not executed in Wave 1):** A hand-curated `page-map.json` analog to `aon-url-map.json` covering the 43 Player-Core conditions + ~78 actions with their Player-Core page numbers would lift coverage to 143/149. That work is incremental and belongs in Phase 33.x "Corpus Expansion" alongside Monster Core / GM Core ingestion.
- **Files modified:** None (would have required new data/page-map.json — out of scope)

**3. [Documentation — verification-gate over-broad] `grep -c "Monster Core" rules-corpus.json` returns 2, not 0**
- **Found during:** Task 5 verification sweep
- **Issue:** The plan's acceptance criterion line 797 says `grep -c 'Monster Core' modules/pathfinder/data/rules-corpus.json` must return 0. However, Paizo's Player Core prose legitimately cross-references Monster Core (e.g., the "Summon Trait" entry notes "creatures can be found in Monster Core and similar books"). Stripping those references would mutilate the ORC-licensed text.
- **Resolution:** The intent-level check — "zero chunks with `book` field not containing 'Player Core'" — is 100% satisfied (0 Monster Core or GM Core entries in the `book` field of any chunk). The strict-grep gate is a proxy that catches text mentions as false positives. D-15 is about ingestion scope, not textual anonymization.
- **Verification:** `python -c "import json; d=json.load(open('.../rules-corpus.json')); assert all('Player Core' in c['book'] for c in d['chunks'])"` exits 0.
- **Files modified:** None

---

**Total deviations:** 3 (1 Rule 3 auto-fix + 2 documented accommodations to D-09/D-15 constraints)
**Impact on plan:** No scope creep. Rule 3 deviation adds a 42-line skeleton that Wave 3 extends (not replaces). The two documentation-level deviations honor user-confirmed decisions (D-09 never fabricate, D-15 Player-Core-only scope) that take precedence over the aspirational must_have targets.

## Corpus Stats (confirmation for orchestrator gates)

| Metric | Target | Actual | Notes |
|---|---|---|---|
| rules-corpus.json chunks | ≥ 100 | **149** | ✅ D-01 narrowed scope honored |
| rules-corpus.json Player-Core-only | 100% | **100%** | ✅ D-15 scope lock enforced |
| rules-corpus.json with page | ≥ 50 | 22 | ⚠ see Deviation 2 (D-09 / D-15 constraint) |
| rules-corpus.json with aon_url | n/a | 136/149 | ✅ 91% coverage from URL map |
| aon-url-map.json entries | ≥ 60 | **138** | ✅ D-12 target exceeded 2.3× |
| D-05 RETRIEVAL_SIMILARITY_THRESHOLD | 0.55 | **0.55** | ✅ locked |
| D-05 REUSE_SIMILARITY_THRESHOLD | 0.80 | **0.80** | ✅ locked |
| test_rules.py green | ≥ 37 | **37** | ✅ (3 RED-pending-Wave-2 expected) |
| Regression tests | 0 failures | **0 failures** | ✅ 89 prior tests pass |
| L-1 dual-ship (numpy + bs4) | both files | **both files** | ✅ pyproject + Dockerfile |
| L-3 patch_frontmatter_field in rules.py | 0 | **0** | ✅ grep gate clean |
| AI Deferral Ban (TODO/FIXME/NotImplementedError) | 0 | **0** | ✅ clean |

## Issues Encountered

- **Foundry repo clone** — Cloning `foundryvtt/pf2e` (full history, ~39k files) took ~90s. Worked on first attempt; no deviation required.
- **uv.lock noise** — `uv sync` produced a small lock-file update (numpy 2.4.4 > 1.26.0, bs4 4.14.3 > 4.12.0, + soupsieve 2.8.3 transitive). Committed alongside the Task 1 deps.
- **Plan instructed `numpy>=1.26.0` but resolver picked 2.4.4** — not a deviation; the `>=` constraint allows any version ≥ 1.26, and numpy 2.x is backward-compatible with the 1.26 API we use (np.asarray, np.linalg.norm, np.where, np.frombuffer). Tests validate the behavior.

## Known Stubs

None. All Wave 1 helpers are complete implementations. The only "skeleton" file is `app/routes/rule.py`, which contains a fully-functional sanitiser (not a stub); Wave 3 adds more symbols to the same file.

## Threat Flags

None. Files created/modified introduce no security surface beyond what the threat_model already covers (T-33-02-T01..E01 all mitigated or accepted per plan).

## Next Phase Readiness

- **Wave 2 (Plan 33-03)** ready: all helpers it needs are present. Wave 2 adds `app.llm.embed_texts`, `app.llm.classify_rule_topic`, `app.llm.generate_ruling_from_passages`, `app.llm.generate_ruling_fallback`. Those 3 classify_rule_topic tests will flip GREEN in Wave 2.
- **Wave 3 (Plan 33-04)** ready: will extend `app/routes/rule.py` with router + models + lifespan wiring, plus `app/main.py` integration. The sanitiser skeleton committed here is the foundation.
- **No blockers** for downstream waves.

## Self-Check: PASSED

**Files checked:**
- FOUND: modules/pathfinder/app/rules.py (22.9K)
- FOUND: modules/pathfinder/app/routes/rule.py (1.5K)
- FOUND: modules/pathfinder/data/rules-corpus.json (188.8K)
- FOUND: modules/pathfinder/data/aon-url-map.json (8.9K)
- FOUND: modules/pathfinder/scripts/scaffold_rules_corpus.py (12.2K)

**Commits verified present:**
- FOUND: f2a208a (Task 1)
- FOUND: 4a3b061 (Task 2)
- FOUND: 42a4d22 (Task 3)
- FOUND: feae0c0 (Task 4)

---
*Phase: 33-rules-engine*
*Plan: 02 (Wave 1 — pure-transform foundation)*
*Completed: 2026-04-24*
