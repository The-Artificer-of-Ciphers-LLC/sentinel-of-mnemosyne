---
status: resolved
phase: 32-monster-harvesting
source: [32-VERIFICATION.md]
started: 2026-04-24T03:45:00Z
updated: 2026-04-24T04:45:00Z
verification_method: automated live-stack UAT via scripts/uat_phase32.sh (rebuild + 17-test run)
---

## Current Test

[resolved — 17/17 automated live-stack tests passed 2026-04-24T04:45:00Z]

## Tests

### 1. `:pf harvest Boar` in live Discord (seed round-trip)
expected: Embed renders with "Boar (Level 2)" title, Medicine DC 16, craftable bullets; cache file at `mnemosyne/pf2e/harvest/boar.md` with frontmatter `source: seed`, `verified: true`, ISO-8601 `harvested_at`.
result: PASS (automated) — POST /modules/pathfinder/harvest returned 200 + source=seed + 2 components; cache file written at mnemosyne/pf2e/harvest/boar.md with "Medicine DC" present (len=437).

### 2. `:pf harvest Barghest` in live Discord (LLM fallback — out of seed)
expected: LLM fallback fires; source=llm-generated + verified=False; medicine_dc clamped to DC_BY_LEVEL[4]=19 regardless of LLM response; ORC attribution in footer.
result: PASS (automated, with 2× retry for LLM non-determinism) — cache file with "Medicine DC" + "ORC" (len=409); verified=False; medicine_dc=19.

### 3. `:pf harvest Alpha Wolf` in live Discord (fuzzy seed match)
expected: Fuzzy match hits Wolf; note "_Matched to closest entry: Wolf._"; cache at CANONICAL slug `wolf.md` (WR-05 fix) — not `alpha-wolf.md`.
result: PASS (automated) — source=seed-fuzzy; note text confirmed; cache at mnemosyne/pf2e/harvest/wolf.md (200), mnemosyne/pf2e/harvest/alpha-wolf.md (404).

### 4. `:pf harvest Wolf Lord` in live Discord (fuzzy-below-cutoff)
expected: Falls through fuzzy (score <85) to LLM fallback; shows generated warning.
result: PASS (automated) — source=llm-generated + verified=False.

### 5. `:pf harvest Boar,Wolf,Orc` in live Discord (batch)
expected: Aggregated embed; components grouped by type across monsters; footer includes FoundryVTT/Paizo/ORC attribution on mixed branch (IN-02 fix).
result: PASS (automated) — 3 monsters, 3 aggregated components, footer="Mixed sources — 2 seed / 1 generated. Seed reference: FoundryVTT pf2e (Paizo, ORC license)".

### 6. Second `:pf harvest Wolf` after first query (cache-hit)
expected: Fast response (no LLM call); source preserved from original seed/llm entry.
result: PASS (automated) — dt=0.01s; source=seed preserved across reads.

### 7. DM ratification — edit cached note `verified: true`, re-query
expected: Re-query returns verified=true (cache re-read, not LLM re-generated); fuzzy note preserved across cache round-trip (CR-03 fix).
result: PASS (automated) — Obsidian PUT returned 204, re-query returned verified=true.

### 8. Container rebuild smoke — `sentinel.sh --pf2e up --build`
expected: pf2e-module starts cleanly with rapidfuzz 3.14.5; registers with sentinel-core; 13 routes including harvest; healthz=200.
result: PASS (automated) — required an iteration: first rebuild 500-loop'd with ModuleNotFoundError because Dockerfile hardcoded deps and missed rapidfuzz. Fixed in commit c3a18d2 (added rapidfuzz>=3.14.0 to Dockerfile); second rebuild healthy. pathfinder registered with 13 routes, harvest_present=True.

## Summary

total: 8
passed: 8
issues: 0
pending: 0
skipped: 0
blocked: 0

## Live UAT Automation

`scripts/uat_phase32.sh` — rebuilds pf2e-module + discord containers → waits for healthy + registration → invokes `scripts/uat_harvest.py` (17 assertions covering HTTP harvest flows, bot dispatch routing, container smoke). Safe to re-run. LIVE_TEST=1 guard.

Final run: 2026-04-24T04:45:00Z — **17/17 PASS** against live stack (sentinel-core + pf2e-module + Obsidian Local REST API + LM Studio qwen2.5-coder-14b-instruct-mlx).

## Gaps

### G-1 — pf2e-module Dockerfile missed rapidfuzz after pyproject.toml update (resolved)
- Discovered: 2026-04-24T04:15:00Z via UAT-8 (first container rebuild 500-loop'd)
- Root cause: modules/pathfinder/Dockerfile hardcodes pip install args inline instead of reading from pyproject.toml. Phase 32 added rapidfuzz>=3.14.0 to pyproject but not the Dockerfile. Unit tests missed it because they ran in host venv where `uv sync` had already installed rapidfuzz.
- Fix commit: c3a18d2 (added rapidfuzz>=3.14.0 to Dockerfile)
- Status: resolved

### G-2 — LLM clamp didn't fill missing medicine_dc from DC_BY_LEVEL (resolved)
- Discovered: 2026-04-24T04:25:00Z via UAT-2/UAT-4 (Barghest + Wolf Lord 500'd intermittently)
- Root cause: DC sanity clamp only overwrote `medicine_dc` when observed value was an int-but-wrong; missing field (`None`) was skipped, then CR-02 validator rejected the whole response. Small LLMs omit the field despite system prompt.
- Fix commit: d4c9e8a (extend clamp to fill from DC_BY_LEVEL[level] when medicine_dc is missing). CR-02 still catches truly unrepairable shapes (non-list components, non-dict component, missing both type+name).
- Added unit tests: `test_harvest_llm_missing_medicine_dc_filled_from_level` (200 + cache write), `test_harvest_llm_truly_malformed_500` (500, no cache write).
- Status: resolved

### G-3 — UAT orchestration nits (resolved)
- sentinel-core proxy route is `/modules/{name}/{path}`, not `/modules/{name}/run` with wrapped payload (my UAT initial mistake)
- `/status` doesn't include module registry; use `/modules` instead
- `OBSIDIAN_API_URL` in .env uses container-perspective `host.docker.internal`; host-side UAT must rewrite to `localhost`
- `discord.Color.dark_green`/`dark_gold` needed in the Color stub
- LLM non-determinism requires retry-on-500 (up to 2 retries) to absorb one-off malformed responses
- Fix commits: d4c9e8a (UAT fixes), last commit (retry generalization)
- Status: resolved
