---
phase: 32
slug: monster-harvesting
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-23
---

# Phase 32 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from §"Validation Architecture" in 32-RESEARCH.md and the 5 PLAN.md files in this phase.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `modules/pathfinder/pyproject.toml`, `interfaces/discord/pyproject.toml` |
| **Quick run command** | `cd modules/pathfinder && uv run python -m pytest tests/ -k harvest -q --tb=short` |
| **Full suite command** | `cd modules/pathfinder && uv run python -m pytest tests/ -q && cd interfaces/discord && uv run --no-sync python -m pytest tests/ -q` |
| **Integration test command** | `cd modules/pathfinder && uv run python -m pytest tests/test_harvest_integration.py -x -q` |
| **Estimated runtime** | ~15 seconds (full) / ~5 seconds (quick) |

---

## Sampling Rate

- **After every task commit:** Run `cd modules/pathfinder && uv run python -m pytest tests/ -k harvest -q`
- **After every plan wave:** Run `cd modules/pathfinder && uv run python -m pytest tests/ -q && cd interfaces/discord && uv run --no-sync python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite green + `tests/test_harvest_integration.py` green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

Wave numbering (post-revision per plan-checker Warning 5 fix): W0 = 32-01; W1 = 32-02; W2 = 32-03; W3 = 32-04; W4 = 32-05.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 32-01-01 | 01 | 0 | HRV-01..06 | — | N/A (test scaffold) | unit (RED) | `cd modules/pathfinder && python -m pytest tests/test_harvest.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 32-01-02 | 01 | 0 | HRV-01..06 (integration) | — | N/A (test scaffold) | integration (RED) | `cd modules/pathfinder && python -m pytest tests/test_harvest_integration.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 32-01-03 | 01 | 0 | HRV-01, HRV-06 (bot) | — | N/A (test scaffold) | unit (RED) | `cd interfaces/discord && python -m pytest tests/test_subcommands.py -k harvest --collect-only -q` | ❌ W0 | ⬜ pending |
| 32-02-01 | 02 | 1 | HRV-01..06 (dep) | T-32-03-T02 (fuzzy) | rapidfuzz wheel installed, importable | smoke | `cd modules/pathfinder && uv run python -c "import rapidfuzz; assert rapidfuzz.__version__ >= '3.14.0'; print('OK')"` | ⬜ | ⬜ pending |
| 32-02-02 | 02 | 1 | HRV-01 (scaffold tool) | T-32-02-D01 (no half-shape) | httpx-only (S7); scaffold renders commented-template (never `components: []` live key); no network at test time | smoke | `python -c "import ast; ast.parse(open('modules/pathfinder/scripts/scaffold_harvest_seed.py').read()); print('OK')"` | ⬜ | ⬜ pending |
| 32-02-03 | 02 | 1 | HRV-01..06 (roster input for hand-curation) | — | Deterministic L1-3 roster committed as input to 32-02-04 binding | smoke | `cd modules/pathfinder && python -c "from pathlib import Path; lines = Path('data/harvest-roster.txt').read_text().strip().splitlines(); assert len(lines) >= 20; [ln.split('\t')[0] for ln in lines]; print(f'OK {len(lines)}')"` | ⬜ | ⬜ pending |
| 32-02-04 | 02 | 1 | HRV-01..06 (seed data) | T-32-02-I01 (ORC attr), T-32-02-T02 (DC correctness) | YAML parses; DCs match Table 10-5; ORC attribution present; one entry per roster line (no silent substitution) | smoke | `cd modules/pathfinder && uv run python -c "import yaml; from pathlib import Path; d=yaml.safe_load(Path('data/harvest-tables.yaml').read_text()); r=[ln for ln in Path('data/harvest-roster.txt').read_text().strip().splitlines() if ln.strip()]; assert len(d['monsters']) == len(r); print(f'OK {len(d[\\\"monsters\\\"])}')"` | ⬜ | ⬜ pending |
| 32-03-01 | 03 | 2 | HRV-01..06, HRV-03 (format_price), HRV-04..05 (DCs), YAML schema, fuzzy + aggregation + cache parser | T-32-03-T01 (yaml safe_load), T-32-03-T02 (fuzzy cutoff 85) | Single-Write module (no `# noqa: F401` anywhere per Blocker 1); yaml.safe_load only; Pydantic validates; format_price normalises; lookup_seed returns (None, None) below cutoff; aggregator deduplicates; _parse_harvest_cache log-and-degrades; build_harvest_markdown emits ORC attribution footer (Info 1) | unit | `cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py -k 'format_price or invalid_yaml or fuzzy_subset or fuzzy_wolf_lord' -q` | ⬜ | ⬜ pending |
| 32-03-02 | 03 | 2 | HRV-01, HRV-04, HRV-05 (LLM fallback) | T-32-03-T03 (prompt injection), T-32-03-T04 (DC hallucination) | System prompt grounds DCs 0-25 verbatim (Warning 2 fix — full table, no level-10 truncation); post-parse clamp to DC_BY_LEVEL; source=llm-generated + verified=False stamped | unit (mocked LLM) | `cd modules/pathfinder && uv run python -c "import asyncio, json; from types import SimpleNamespace; from unittest.mock import AsyncMock, patch; import app.llm as llm; fake=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'monster':'Balor','level':15,'components':[{'type':'Hide','medicine_dc':33,'craftable':[]}]})))]); out=asyncio.run((lambda: (lambda a: a())( (lambda: __import__('asyncio').get_event_loop().run_until_complete.__call__ if False else None) )()) if False else asyncio.run(( __import__('asyncio') ).get_event_loop().run_until_complete(llm.generate_harvest_fallback('Balor', model='x')))) if False else None; print('see plan smoke test')"` | ⬜ | ⬜ pending |
| 32-04-01 | 04 | 3 | HRV-01..06 (route handler) | T-32-04-T01 (name validator), T-32-04-D01 (batch cap), T-32-04-D03 (LLM-fail-no-cache) | _validate_monster_name rejects control chars; MAX_BATCH_NAMES enforced; LLM failure raises 500 without cache write | integration | `cd modules/pathfinder && uv run python -m pytest tests/test_harvest.py tests/test_harvest_integration.py -q` | ⬜ | ⬜ pending |
| 32-04-02 | 04 | 3 | HRV-01..06 (registration) | T-32-04-T04 (path namespace) | REGISTRATION_PAYLOAD length==13; harvest path present; HARVEST_CACHE_PATH_PREFIX under mnemosyne/pf2e/harvest | smoke | `cd modules/pathfinder && uv run python -c "from app.main import REGISTRATION_PAYLOAD; assert len(REGISTRATION_PAYLOAD['routes']) == 13; assert any(r['path']=='harvest' for r in REGISTRATION_PAYLOAD['routes']); print('OK')"` | ⬜ | ⬜ pending |
| 32-05-01 | 05 | 4 | HRV-01, HRV-06 (bot dispatch + embed) | T-32-05-T03 (noun widen strict), T-32-05-D01 (forwarding only) | noun check is strict set {npc, harvest}; comma-split with whitespace trim; multi-word names preserved; field value truncated to 1024 chars; 4 explicit Edit calls documented (Warning 3); early-return interaction comment present (Warning 4) | unit | `cd interfaces/discord && uv run --no-sync python -m pytest tests/test_subcommands.py -k harvest -q` | ⬜ | ⬜ pending |

*Status codes: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Primary Test | Plan |
|--------|----------|-----------|--------------|------|
| HRV-01 | `/harvest` with one name returns ≥1 harvestable component | integration | `test_harvest_single_seed_hit` (+ `test_harvest_llm_fallback_marks_generated` for fallback path) | 32-01 (RED) → 32-04 (GREEN) |
| HRV-02 | Each component lists craftable items (name+DC+value) | integration | `test_harvest_components_have_craftable` | 32-01 → 32-04 |
| HRV-03 | Each craftable includes vendor value string | unit | `test_format_price_*` (3 tests) | 32-01 → 32-03 |
| HRV-04 | Each component has Medicine check DC integer | integration | `test_harvest_medicine_dc_present` (+ DC sanity clamp in generate_harvest_fallback) | 32-01 → 32-04 |
| HRV-05 | Each craftable has Crafting DC integer | integration | `test_harvest_components_have_craftable` (same test; asserts crafting_dc is int) | 32-01 → 32-04 |
| HRV-06 | `/harvest` with N names returns aggregated component view | integration | `test_harvest_batch_aggregated` + `test_batch_mixed_sources_footer` | 32-01 → 32-04 |
| D-02 fuzzy | "Alpha Wolf" → seed Wolf + note; "Wolf Lord" → LLM fallback | unit | `test_fuzzy_subset_matches`, `test_fuzzy_wolf_lord_falls_through`, `test_harvest_fuzzy_match_returns_note`, `test_harvest_fuzzy_below_threshold_falls_to_llm` | 32-01 → 32-03 (unit) + 32-04 (integration) |
| D-02 LLM | Unknown monster → `verified: false`, footer signals "generated" | integration | `test_harvest_llm_fallback_marks_generated` | 32-01 → 32-04 |
| D-03b cache | Second query reads from Obsidian, no LLM call | integration | `test_harvest_cache_hit_skips_llm`, `test_first_query_writes_cache_second_reads_cache` | 32-01 → 32-04 |
| D-03b write path | GET-then-PUT via build_harvest_markdown (never PATCH) | unit + integration | `test_harvest_cache_write_on_miss`, `test_harvest_cache_write_failure_degrades`, `test_seed_hit_writes_cache_with_source_seed` | 32-01 → 32-04 |
| D-04 aggregation | Components grouped by type across batch | integration | `test_harvest_batch_aggregated`, `test_batch_mixed_sources_footer` | 32-01 → 32-04 |
| YAML schema | Invalid harvest-tables.yaml fails Pydantic validation | unit | `test_invalid_yaml_raises` | 32-01 → 32-03 |
| Embed | `build_harvest_embed` handles single + batch shapes | unit | `test_pf_harvest_returns_embed_dict` | 32-01 → 32-05 |
| Dispatch | `:pf harvest A,B` → POST /modules/pathfinder/harvest | unit | `test_pf_harvest_solo_dispatch`, `test_pf_harvest_batch_dispatch`, `test_pf_harvest_multi_word_monster`, `test_pf_harvest_batch_trimmed_commas`, `test_pf_harvest_empty_returns_usage`, `test_pf_harvest_noun_recognised` | 32-01 → 32-05 |
| Security (empty) | POST with `{"names": []}` → 422 (field_validator path) | unit | `test_harvest_empty_names_422` | 32-01 → 32-04 |
| Security (missing-key) | POST with `{}` (no `names` key) → 422 (FastAPI required-field path — different code path from empty-list) | unit | `test_harvest_missing_names_key_422` (Warning 1 coverage gap fix) | 32-01 → 32-04 |
| Security (control chars) | Name validator rejects control chars | unit | `test_harvest_invalid_name_control_char` | 32-01 → 32-04 |
| Security (batch cap) | MAX_BATCH_NAMES=20 enforced | unit | `test_harvest_batch_cap_enforced` | 32-01 → 32-04 |
| Smoke | rapidfuzz wheel installed in venv | unit | `test_rapidfuzz_importable` | 32-01 → 32-02 |

---

## Wave 0 Requirements

Wave 0 establishes the test scaffolding before implementation lands. RED is expected; GREEN after later waves.

- [ ] `modules/pathfinder/tests/test_harvest.py` — 21 unit stubs (covers HRV-01..06, D-02 fuzzy, D-03b cache, format_price, YAML schema, security caps including both empty-names-422 and missing-names-key-422 per Warning 1)
- [ ] `modules/pathfinder/tests/test_harvest_integration.py` — 3 round-trip stubs (StatefulMockVault per Phase 31 pattern)
- [ ] `interfaces/discord/tests/test_subcommands.py` — append 7 `test_pf_harvest_*` stubs
- [ ] No new framework install — pytest-asyncio + ASGITransport already configured
- [ ] New production dependency — `rapidfuzz>=3.14.0` lands in Plan 32-02 and flips `test_rapidfuzz_importable` GREEN

Wave 0 is complete when:
- `cd modules/pathfinder && python -m pytest tests/test_harvest.py --collect-only -q` shows `21 tests collected`
- `cd modules/pathfinder && python -m pytest tests/test_harvest_integration.py --collect-only -q` shows `3 tests collected`
- `cd interfaces/discord && python -m pytest tests/test_subcommands.py -k harvest --collect-only -q` shows `7 tests collected`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LLM-generated fallback quality (T-32-LLM-01) | HRV-01, SC-4 | LLM output correctness requires DM judgment vs. Paizo Bestiary prose | Run `:pf harvest Barghest` (L4, out of seed), open `mnemosyne/pf2e/harvest/barghest.md`, verify components plausible against Paizo Bestiary 2 p.46 |
| Fuzzy-match false-positive behavior | HRV-01, T-32-SEC-02 | Edge cases require human judgment | Run `:pf harvest 'Wolf Lord'`, confirm LLM fallback triggers (not silent match to Wolf); run `:pf harvest 'Alpha Wolf'`, confirm fuzzy seed match to Wolf with the "Matched to closest" note visible in embed description |
| YAML seed edit → cache invalidation | D-03b | Requires local file edit + re-query | Edit `modules/pathfinder/data/harvest-tables.yaml` Wolf entry (change a DC), delete `mnemosyne/pf2e/harvest/wolf.md`, re-run `:pf harvest Wolf`, confirm new data returned in embed |
| DM ratification flow | SC-4 | Verified-flag toggle is a DM-only operation | After an LLM fallback query, open the cache note in Obsidian, change `verified: false` to `verified: true`, re-query the same monster, confirm the single-monster embed no longer shows the ⚠ Generated warning |
| Batch mixed sources footer (D-04) | HRV-06 | Visual inspection of the embed footer wording | Run `:pf harvest Boar,Wolf,Unicorn` (Boar+Wolf in seed, Unicorn out). Confirm footer reads `"Mixed sources — 2 seed / 1 generated"`. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (21 module unit + 3 integration + 7 bot = 31 automated)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every HRV-* requirement is covered by ≥1 unit test + ≥1 integration assertion)
- [x] Wave 0 covers all MISSING references (test stubs before implementation)
- [x] No watch-mode flags
- [x] Feedback latency < 20s (full harvest suite)
- [x] `nyquist_compliant: true` set in frontmatter
- [x] Wave structure post-revision: W0(01) → W1(02) → W2(03) → W3(04) → W4(05) — each wave's plans have zero `files_modified` overlap with same-wave plans

**Approval:** pending plan-checker review (iteration 2)
