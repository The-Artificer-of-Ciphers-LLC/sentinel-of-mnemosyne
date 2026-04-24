---
phase: 32-monster-harvesting
verified: 2026-04-24T03:00:00Z
status: human_needed
score: 22/22 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run `:pf harvest Boar` in live Discord server with LM Studio running and Obsidian REST API up"
    expected: "Embed renders with 'Boar (Level 2)' title, Medicine DC 16, craftable bullets; a new file appears at `mnemosyne/pf2e/harvest/boar.md` with frontmatter `source: seed`, `verified: true`, ISO-8601 harvested_at"
    why_human: "Requires the live docker stack (sentinel-core + pf2e-module container rebuilt with rapidfuzz), LM Studio model loaded, Obsidian running with Local REST API plugin, and a real Discord connection. No programmatic way to assert the end-to-end visual from this verifier."
  - test: "Run `:pf harvest Barghest` (L4 — outside seed scope) in live Discord"
    expected: "LLM fallback fires; embed shows '⚠ Generated — verify against sourcebook' in description; footer reads 'Source — LLM generated (verify)'; `mnemosyne/pf2e/harvest/barghest.md` exists with `verified: false`, `source: llm-generated`, DC clamped to DC_BY_LEVEL[4]=19 regardless of what the LLM returned"
    why_human: "Requires live LM Studio with a loaded model. LLM response content is model-dependent and cannot be asserted deterministically in automation."
  - test: "Run `:pf harvest Alpha Wolf` in live Discord (fuzzy branch)"
    expected: "Fuzzy-match hits Wolf; embed description shows italic `_Matched to closest entry: Wolf. Confirm if this wasn't intended._`; monster source is `seed-fuzzy`"
    why_human: "Verifies the D-02 fuzzy boundary in a real channel render. Unit tests confirm the helper; human confirms the embed actually renders the italic note."
  - test: "Run `:pf harvest Wolf Lord` in live Discord (fuzzy-below-cutoff branch)"
    expected: "Falls through fuzzy (score 61.5 < 85 cutoff) to LLM fallback; embed shows generated warning, NOT silent Wolf mismatch"
    why_human: "Confirms Pitfall 2 (T-32-SEC-02) boundary is honoured end-to-end against live LM Studio."
  - test: "Run `:pf harvest Boar,Wolf,Orc` in live Discord (batch)"
    expected: "Single aggregated embed titled 'Harvest report — 3 monsters'; components grouped by type (Hide/Fangs/etc.) across monsters; footer matches source mix (all-seed or 'Mixed sources — N seed / M generated'); per-monster cache files written under mnemosyne/pf2e/harvest/"
    why_human: "Batch aggregation (D-04) is unit-tested, but humans must confirm the embed rendering reads well at a glance for a DM mid-encounter."
  - test: "Second `:pf harvest Wolf` after first query (cache-hit path)"
    expected: "Instant response; no LLM token usage observed (verify by watching LM Studio log); cache file timestamp unchanged from first query"
    why_human: "Cache-hit suppression of LLM calls is unit-tested with mocks, but live confirmation that LM Studio receives zero prompts needs human observation of the LM Studio console."
  - test: "After an LLM-fallback query, manually edit `mnemosyne/pf2e/harvest/<slug>.md` in Obsidian to set `verified: true`, then re-query same monster"
    expected: "Embed no longer shows the '⚠ Generated' warning in description; cache is re-read (not LLM-re-generated)"
    why_human: "DM ratification flow (SC-4). Verified flag toggle is a DM-only operation."
  - test: "Start the container stack fresh (`sentinel.sh up`) after Phase 32 changes"
    expected: "pf2e-module container starts cleanly; lifespan log says 'Registered with Sentinel Core (attempt 1)'; no Pydantic validation error on harvest-tables.yaml; `GET /modules/pathfinder/healthz` via sentinel-core returns 200"
    why_human: "Docker compose include + container rebuild to pick up rapidfuzz wheel requires real Docker and cannot be verified from host venv. PATTERNS §6 flags this."
deviations_requiring_signoff:
  - deviation: "32-03 lookup_seed uses fuzz.ratio + head-noun anchor instead of RESEARCH.md's fuzz.token_set_ratio"
    why_acceptable: "RESEARCH.md's prescription was factually wrong — `token_set_ratio('wolf lord', 'wolf') = 100` because `wolf` is a token subset. The Wave-0 RED test `test_fuzzy_wolf_lord_falls_through` pins the correct (below-cutoff) behavior. The two-tier policy (exact → head-noun → fuzz.ratio at cutoff 85) satisfies every boundary test and matches Pitfall 2 intent. Deviation logged in STATE.md decision log."
    codebase_evidence: "modules/pathfinder/app/harvest.py lines 145-202; test_fuzzy_subset_matches + test_fuzzy_wolf_lord_falls_through both GREEN"
    signoff_needed: "Accept as intentional deviation (research bug, not implementation error)"
  - deviation: "32-03 DC_BY_LEVEL imported inside generate_harvest_fallback function body"
    why_acceptable: "Breaks the app.llm → app.harvest → app.routes.npc → app.llm module-load cycle. Module-scope import deadlocks because app.routes.npc imports build_mj_prompt / extract_npc_fields from app.llm at load time. Function-scope is idiomatic Python cycle-break; import cost is negligible post-first-call. Documented inline in the function docstring."
    codebase_evidence: "modules/pathfinder/app/llm.py line 245 — `from app.harvest import DC_BY_LEVEL` inside `generate_harvest_fallback`"
    signoff_needed: "Accept as blocking-issue fix (Rule 3 auto-fix documented in SUMMARY)"
  - deviation: "32-05 consolidated per-file discord stubs into interfaces/discord/tests/conftest.py"
    why_acceptable: "Pre-existing per-file `sys.modules.setdefault('discord', ...)` pattern caused collection-order races: first-collected file's incomplete stub won and later files' added attributes (Embed/Color) were silently discarded. `test_pf_harvest_returns_embed_dict` passed in isolation but failed in the full suite. Consolidating the stub in conftest.py makes it deterministic across collection order. Existing per-file setdefault calls remain (become no-ops) — no cascading changes."
    codebase_evidence: "interfaces/discord/tests/conftest.py (+87 lines); all 38 discord tests PASS; `test_pf_harvest_returns_embed_dict` reliably GREEN"
    signoff_needed: "Accept as test-infrastructure improvement (scope expansion beyond plan but net positive)"
---

# Phase 32: Monster Harvesting Verification Report

**Phase Goal:** Ship Monster Harvesting for the pf2e module (HRV-01..06) — POST /harvest accepts monster names, walks cache→seed→LLM fallback, writes results back to Obsidian cache, aggregates craftable components with Medicine DCs and vendor values, and exposes via Discord `:pf harvest` noun dispatch. End-to-end contract: given a monster name, a DM gets a harvest report (embed + cache write) that includes Medicine DC, craftable items with crafting DCs, vendor values, and ORC-licensed source attribution.

**Verified:** 2026-04-24T03:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP SC + PLAN must_haves, merged)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `/pf harvest [monster]` returns ≥1 harvestable component with a Medicine DC (SC-1, HRV-01, HRV-04) | VERIFIED | Smoke test: POST /harvest {"names":["Wolf"]} → 200, components=2, medicine_dc=15. test_harvest_single_seed_hit + test_harvest_medicine_dc_present GREEN |
| 2 | Each component lists craftable outputs with item level and gp/sp/cp value (SC-2, HRV-02, HRV-03) | VERIFIED | test_harvest_components_have_craftable GREEN; CraftableOut Pydantic model in app/routes/harvest.py lines 81-84 enforces name+crafting_dc+value; format_price validates gp/sp/cp shape |
| 3 | Each craftable item includes a Crafting skill DC (SC-3, HRV-05) | VERIFIED | CraftableOut.crafting_dc is int (app/routes/harvest.py:83); test asserts int type |
| 4 | For monsters not in harvest tables, AI-generated components are marked `[GENERATED — verify]` (SC-4) | VERIFIED | generate_harvest_fallback stamps `source='llm-generated'` + `verified=False` (llm.py:290-291); build_harvest_markdown writes `⚠ Generated — verify against sourcebook` (harvest.py:239); bot embed shows `⚠ Generated — verify against sourcebook` (bot.py:336). Exact phrasing differs from ROADMAP `[GENERATED — verify]` but semantic intent and user-visible marker present |
| 5 | `/pf harvest [m1] [m2] [m3]` returns aggregated report covering all monsters (SC-5, HRV-06) | VERIFIED | _aggregate_by_component groups by type; test_harvest_batch_aggregated + test_batch_mixed_sources_footer GREEN; smoke shows batch returns `{monsters:[...], aggregated:[...], footer:...}` |
| 6 | modules/pathfinder/app/harvest.py exposes Pydantic models + 4 constants + 7 helpers | VERIFIED | All symbols importable via `SENTINEL_API_KEY=test uv run python -c "from app.harvest import ..."`; FUZZY_SCORE_CUTOFF=85.0, HARVEST_CACHE_PATH_PREFIX='mnemosyne/pf2e/harvest', MAX_BATCH_NAMES=20, DC_BY_LEVEL keys 0-25 len=26 |
| 7 | Medicine DCs in harvest-tables.yaml EXACTLY 15/16/18 for L1/L2/L3 per Table 10-5 | VERIFIED | `yaml.safe_load` → 160 monsters; per-entry check allows {base, +2 Hard, +5 Rare}; zero off-by-one (no medicine_dc:17 at L1/L2, no medicine_dc:19 at L3 except Hard-marker); all 160 entries within allowed set |
| 8 | ORC license attribution present in YAML header | VERIFIED | harvest-tables.yaml lines 4-6 cite "Derived from Foundry VTT pf2e system" + "Paizo Monster Core / Equipment content used under ORC license with attribution"; `grep -F 'ORC license' harvest-tables.yaml` → 2 matches |
| 9 | POST /harvest is the 13th registered route | VERIFIED | REGISTRATION_PAYLOAD['routes'] length=13, harvest entry at index 12 (last), description "Monster harvest report with Medicine/Crafting DCs and vendor values (HRV-01..06)" |
| 10 | Cache path uses `mnemosyne/pf2e/harvest` prefix (D-03b) | VERIFIED | Smoke test confirmed `put_note` called with `mnemosyne/pf2e/harvest/wolf.md`; HARVEST_CACHE_PATH_PREFIX constant in harvest.py:63 |
| 11 | GET-then-PUT pattern (no PATCH, memory constraint) | VERIFIED | `grep -cF 'patch_frontmatter_field' app/routes/harvest.py` → 0; route uses obsidian.get_note + obsidian.put_note only |
| 12 | Fuzzy cutoff 85 AND tiered fix (exact → head-noun → fuzz.ratio, NOT token_set_ratio) | VERIFIED | `grep -cF 'fuzz.token_set_ratio' app/harvest.py` → 0; `fuzz.ratio` present with score_cutoff=threshold; lookup_seed has 3-tier strategy in lines 166-202; test_fuzzy_wolf_lord_falls_through + test_fuzzy_subset_matches both GREEN |
| 13 | LLM fallback stamps source='llm-generated' + verified=False; clamps medicine_dc to DC_BY_LEVEL[level] | VERIFIED | app/llm.py:290-291 stamps both fields; lines 294-305 clamp medicine_dc with WARNING log when mismatched |
| 14 | No Obsidian I/O in app/harvest.py (pure transforms); I/O lives in routes/harvest.py | VERIFIED | `grep -c 'obsidian' app/harvest.py` → 0; `grep -cE '^(from\|import) (litellm\|httpx\|fastapi)' app/harvest.py` → 0 |
| 15 | Discord harvest is a NOUN peer to npc, NOT an npc verb (D-04) | VERIFIED | bot.py:400 `if noun not in {"npc", "harvest"}:`; harvest branch at bot.py:405 runs BEFORE the npc verb cascade; unknown-noun error lists both `npc` and `harvest`; top-level usage string contains both |
| 16 | rapidfuzz ≥3.14.0 installed | VERIFIED | `uv run python -c 'import rapidfuzz; print(rapidfuzz.__version__)'` → 3.14.5; pyproject.toml declares rapidfuzz>=3.14.0 |
| 17 | 160-monster seed (1:1 roster binding) | VERIFIED | `wc -l` shows harvest-roster.txt=160, harvest-tables.yaml=2423; yaml parse shows len(monsters)=160 |
| 18 | generate_harvest_fallback embeds full DC-by-level table (0-25) verbatim in system prompt | VERIFIED | app/llm.py lines 250-257 enumerate "Level 0: DC 14" through "Level 25: DC 50" inclusive (26 levels) |
| 19 | LLM fallback raises on missing JSON without cache write (anti-pattern guard) | VERIFIED | app/routes/harvest.py:195-200 catches LLM exception → HTTPException(500); cache write (put_note) is in step 4 AFTER the try/except — unreachable on LLM failure; test_harvest_llm_fallback asserts behaviour |
| 20 | Cache PUT failure degrades gracefully | VERIFIED | app/routes/harvest.py:209-211 catches put_note exception, logs WARNING, still returns result; test_harvest_cache_write_failure_degrades GREEN |
| 21 | build_harvest_markdown emits ORC attribution footer always | VERIFIED | app/harvest.py:241-243 unconditionally appends `*Source: PF2e (Paizo, ORC license) via FoundryVTT pf2e system — verified: {...}*` |
| 22 | All 31 Wave-0 RED stubs flipped GREEN | VERIFIED | 21 unit (test_harvest.py) + 3 integration (test_harvest_integration.py) + 7 dispatch (test_subcommands.py harvest-filter) = 31 all PASS |

**Score:** 22/22 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `modules/pathfinder/app/harvest.py` | Pure-transform helpers + 4 models + 4 constants + 7 helpers | VERIFIED | 332 lines; zero litellm/httpx/fastapi imports; all exports resolve |
| `modules/pathfinder/app/llm.py` | generate_harvest_fallback appended | VERIFIED | Function at line 223; stamps source+verified; clamps DC |
| `modules/pathfinder/app/routes/harvest.py` | APIRouter + 4 Pydantic models + handler | VERIFIED | 225 lines; APIRouter(prefix='/harvest'); cache-aside flow implemented |
| `modules/pathfinder/app/main.py` | Lifespan extension + REGISTRATION_PAYLOAD 13th route + include_router | VERIFIED | 151 lines; all wirings present; route count=13 |
| `modules/pathfinder/data/harvest-tables.yaml` | 160 monsters, ORC header, Table 10-5 DCs | VERIFIED | 2423 lines; yaml.safe_load parses; 1:1 roster binding |
| `modules/pathfinder/data/harvest-roster.txt` | 160 L1-3 monsters from Foundry pf2e | VERIFIED | 160 lines (54 L1 + 60 L2 + 46 L3) |
| `modules/pathfinder/scripts/scaffold_harvest_seed.py` | One-shot scraper | VERIFIED | 137 lines; httpx.Client; uses GitHub API download_url |
| `modules/pathfinder/tests/test_harvest.py` | 21 unit stubs | VERIFIED | 21 tests collected; 21 GREEN |
| `modules/pathfinder/tests/test_harvest_integration.py` | 3 integration stubs (StatefulMockVault) | VERIFIED | 3 tests collected; 3 GREEN |
| `interfaces/discord/bot.py` | build_harvest_embed + noun widen + harvest branch | VERIFIED | build_harvest_embed at line 317; noun set {npc,harvest} at line 400; branch at 405-430 |
| `interfaces/discord/tests/test_subcommands.py` | 7 test_pf_harvest_* stubs | VERIFIED | 7 tests collected via -k harvest; 7 GREEN |
| `interfaces/discord/tests/conftest.py` | Consolidated discord stub with Embed/Color | VERIFIED | 128 lines; Client/Intents/Embed/Color/Thread stubs; pytest_configure; collection-order safe |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| bot.py build_harvest_embed | post_to_module /harvest result | dict with monsters/aggregated/footer keys | WIRED | `build_harvest_embed(result)` called in harvest branch (bot.py:429); result shape matches handler output |
| bot.py _pf_dispatch harvest branch | Sentinel Core /modules/pathfinder/harvest | _sentinel_client.post_to_module | WIRED | bot.py:421-425 posts names+user_id to modules/pathfinder/harvest |
| routes/harvest.py | app.harvest helpers | direct import | WIRED | `from app.harvest import HARVEST_CACHE_PATH_PREFIX, MAX_BATCH_NAMES, HarvestTable, _aggregate_by_component, _parse_harvest_cache, build_harvest_markdown, lookup_seed` (lines 26-34) |
| routes/harvest.py | app.llm.generate_harvest_fallback | direct import | WIRED | line 35; called in handler line 190 |
| main.py lifespan | routes/harvest module singletons | `_harvest_module.obsidian = obsidian_client`, `_harvest_module.harvest_tables = load_harvest_tables(...)` | WIRED | main.py:122-125 assigns both; nullified on shutdown (:129-130) |
| main.py | harvest_router registration | `app.include_router(harvest_router)` | WIRED | main.py:141 |
| main.py REGISTRATION_PAYLOAD | sentinel-core | 13th route entry | WIRED | main.py:71 `{"path": "harvest", "description": "Monster harvest report..."}` |
| harvest.py | routes/npc.slugify | re-export + Plan 32-04 call-site | WIRED | harvest.py:32 imports; routes/harvest.py:37 uses directly |
| harvest route handler | Obsidian | get_note + put_note (GET-then-PUT; NO PATCH) | WIRED | Line 174 (get) + line 207 (put); zero patch_frontmatter_field occurrences |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|----|
| routes/harvest.py `per_monster_results` | populated by for-loop over req.names | cache (get_note) / seed (lookup_seed) / LLM (generate_harvest_fallback) | Yes — smoke test POST /harvest {"names":["Wolf"]} returns real populated list with 2 components | FLOWING |
| harvest.py `_aggregate_by_component(per_monster_results)` | aggregated list | per_monster_results | Yes — batch tests confirm grouping preserves component data | FLOWING |
| bot.py `build_harvest_embed(result)` | embed fields | result.monsters, result.aggregated, result.footer | Yes — unit tests confirm dict-shape handling + field rendering | FLOWING |
| YAML tables → lifespan → harvest_tables singleton → lookup_seed | HarvestTable | load_harvest_tables(__file__-relative path) | Yes — smoke test confirms 160 monsters loaded at lifespan startup | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| rapidfuzz importable at 3.14.5 | `cd modules/pathfinder && uv run python -c 'import rapidfuzz; print(rapidfuzz.__version__)'` | 3.14.5 | PASS |
| REGISTRATION_PAYLOAD has 13 routes | `SENTINEL_API_KEY=test uv run python -c "from app.main import REGISTRATION_PAYLOAD; print(len(REGISTRATION_PAYLOAD['routes']))"` | 13, harvest at index 12 | PASS |
| YAML parses + 160 monsters + DCs correct | Custom python -c running yaml.safe_load + DC validation | 160 monsters, bad DC entries=0, medicine_dc==17 at L1/L2 count=0 | PASS |
| Full pathfinder suite | `cd modules/pathfinder && uv run python -m pytest tests/ -q` | 84 passed in 2.28s | PASS |
| Full discord suite | `cd interfaces/discord && uv run --no-sync python -m pytest tests/ -q` | 38 passed, 50 skipped | PASS |
| End-to-end POST /harvest with real seed | Smoke: ASGITransport + mocked obsidian + real YAML + Wolf query | 200, source=seed, level=1, components=2, medicine_dc=15, footer='Source — FoundryVTT pf2e', cache path=mnemosyne/pf2e/harvest/wolf.md | PASS |
| Harvest unit+integration subset | `pytest tests/test_harvest.py tests/test_harvest_integration.py -v` | 24/24 PASS | PASS |
| Discord harvest dispatch subset | `pytest tests/test_subcommands.py -k harvest -v` | 7/7 PASS | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| HRV-01 | 32-01..05 | User can input a killed monster name and receive a list of harvestable components | SATISFIED | POST /harvest returns `monsters[].components`; seed path (Wolf→2 comps), LLM fallback path, fuzzy path all tested |
| HRV-02 | 32-01..05 | Each harvestable component includes what can be crafted from it | SATISFIED | CraftableOut model + craftable list on ComponentOut; YAML seed populates per-component craftable lists; test_harvest_components_have_craftable GREEN |
| HRV-03 | 32-01..05 | Each craftable item includes PF2e vendor value (gp/sp/cp) | SATISFIED | format_price handles single/mixed/empty denominations; YAML value strings match regex `^\d+ (gp\|sp\|cp)( \d+ (sp\|cp))?$`; test_format_price_* ×3 GREEN |
| HRV-04 | 32-01..05 | Each harvestable component includes Medicine check DC | SATISFIED | HarvestComponent.medicine_dc field; Medicine DCs in seed match Table 10-5; DC clamp in LLM fallback; test_harvest_medicine_dc_present GREEN |
| HRV-05 | 32-01..05 | Each craftable item includes Crafting skill DC | SATISFIED | CraftableItem.crafting_dc field; test_harvest_components_have_craftable asserts int on crafting_dc |
| HRV-06 | 32-01..05 | Aggregated harvest for multiple monsters | SATISFIED | HarvestRequest.names accepts list (≤20); _aggregate_by_component groups across monsters; test_harvest_batch_aggregated + test_batch_mixed_sources_footer GREEN; batch footer differentiates mixed/all-seed/all-generated |

No orphaned requirements — all 6 HRV-* IDs map to Phase 32 per REQUIREMENTS.md Traceability section (lines 103-108), and all 5 plan frontmatter blocks list them.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| app/harvest.py | 18 | Docstring mentions "no TODO/pass/NotImplementedError" | Info | Documentation prose explaining AI Deferral Ban; not an active deferral. Matches 32-03 SUMMARY note. |
| app/routes/harvest.py | (docstring) | Docstring mentions "no TODO/pass/NotImplementedError" | Info | Same pattern; documentation not deferral |

Confirmed no substantive anti-patterns:
- `grep -rn 'TODO\|FIXME\|NotImplementedError' app/harvest.py app/routes/harvest.py app/main.py` — docstring-only matches (AI Deferral Ban documentation)
- `grep -c '# noqa\|# type: ignore' app/harvest.py app/routes/harvest.py` — 1 (a type:ignore annotation for the None-typed module singleton, which is the established pattern from routes/npc.py)
- `grep -cE 'return \[\]|return \{\}|return None' app/routes/harvest.py` — only the _build_footer empty-list early-return (correct behavior)
- No placeholder returns, no console.log-only implementations, no empty onClick equivalents.

### Human Verification Required

8 items requiring live-environment testing (see `human_verification:` frontmatter above for full details). Summary:

1. `:pf harvest Boar` in live Discord — full round trip (seed path)
2. `:pf harvest Barghest` — LLM fallback quality + DC clamp against live LM Studio
3. `:pf harvest Alpha Wolf` — fuzzy seed match with italic note in rendered embed
4. `:pf harvest Wolf Lord` — fuzzy-below-cutoff falls through to LLM
5. `:pf harvest Boar,Wolf,Orc` — batch aggregation + mixed-source footer readability
6. Second `:pf harvest Wolf` — cache-hit suppresses LLM call (verify via LM Studio log)
7. DM ratification: edit cached note to `verified: true`, re-query, confirm generated warning gone
8. Container rebuild smoke: `sentinel.sh up` post-Phase-32 — lifespan registration + healthz

### Deviations Requiring Sign-Off

Three documented intentional deviations (see `deviations_requiring_signoff:` frontmatter above):

1. **32-03 fuzzy tiering replaces RESEARCH.md's token_set_ratio.** RESEARCH prescribed a scorer that factually scores `wolf lord` vs `wolf` at 100 (token subset). RED tests pinned the correct behavior; the two-tier policy (exact → head-noun → fuzz.ratio cutoff 85) is the only correct implementation. Accept as research-bug auto-fix.

2. **32-03 DC_BY_LEVEL import-in-function for cycle-break.** Module-scope import deadlocks app.llm ↔ app.harvest ↔ app.routes.npc. Function-scope is idiomatic Python. Accept as Rule 3 blocking-issue fix.

3. **32-05 conftest.py consolidation of discord stubs.** Test-infrastructure improvement beyond plan scope. Fixes a latent sys.modules.setdefault collection-order race that masked missing Embed/Color attributes. Accept as net-positive scope expansion.

### Gaps Summary

No gaps. Phase 32 goal is achieved end-to-end in the codebase:

- HRV-01..06 all satisfied, each with at least one unit test + one integration assertion
- Critical invariants verified: Medicine DCs match Table 10-5 exactly; ORC attribution present; route is 13th in payload; cache path namespaced under `mnemosyne/pf2e/harvest`; GET-then-PUT (no PATCH); fuzzy cutoff 85 + tiered lookup; LLM stamps source/verified + clamps DC; no Obsidian I/O in pure-transform module; Discord harvest is a peer NOUN to npc.
- 31/31 Wave-0 RED stubs flipped GREEN; 84/84 pathfinder suite green; 38/38 discord suite green; zero regressions.
- End-to-end smoke against real 160-monster YAML + mocked Obsidian round-trips a real harvest report with correct DC, source, cache path, and footer.

**Status resolution:** Goal is achieved in-code. The 8 human verification items are required because they exercise behaviors that fundamentally depend on live external services (LM Studio, Obsidian REST API, Docker stack, Discord connection) which cannot be observed from the verifier's host venv. Per the decision tree in Step 9, presence of any human-verification items mandates `status: human_needed` even with 22/22 truths verified.

### Code Review Cycle

After initial verification, `/gsd-code-review` was run against all 12 source files changed in this phase (standard depth). Findings summarised in `.planning/phases/32-monster-harvesting/32-REVIEW.md`: 3 critical (CR-01 empty-slug cache collision; CR-02 malformed LLM output → 500; CR-03 fuzzy note dropped by cache round-trip), 7 warnings, 4 info (1 marked "no change required"). All 13 actionable findings were fixed in 13 atomic commits (89fa573..b8507f7). 4 regression tests added:

- `test_harvest_unicode_only_name_rejected` (CR-01)
- `test_harvest_llm_returns_malformed_shape_degrades` (CR-02)
- `test_fuzzy_match_note_survives_cache_roundtrip` (CR-03 — integration)
- `test_harvest_cache_hit_defaults_to_cache_when_source_missing` (WR-06)

Post-fix test counts: **pathfinder 88/88 passed** (up from 84), **discord 38/38 passed** (unchanged). Full report: `.planning/phases/32-monster-harvesting/32-REVIEW-FIX.md`. One deviation from REVIEW suggestions: CR-02's suggested `HarvestComponent.model_validate` was substituted with an inline validator because `HarvestComponent` requires `name` while the LLM contract returns `type` — using model_validate would have broken every valid LLM response.

---
*Verified: 2026-04-24T03:00:00Z*
*Verifier: Claude (gsd-verifier)*
*Code review: 2026-04-24T03:30:00Z — 13/13 findings fixed*
