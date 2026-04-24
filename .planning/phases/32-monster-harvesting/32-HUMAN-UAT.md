---
status: partial
phase: 32-monster-harvesting
source: [32-VERIFICATION.md]
started: 2026-04-24T03:45:00Z
updated: 2026-04-24T03:45:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. `:pf harvest Boar` in live Discord (seed round-trip)
expected: Embed renders with "Boar (Level 2)" title, Medicine DC 16, craftable bullets; a new file appears at `mnemosyne/pf2e/harvest/boar.md` with frontmatter `source: seed`, `verified: true`, ISO-8601 `harvested_at`.
result: [pending]

### 2. `:pf harvest Barghest` in live Discord (LLM fallback — out of seed)
expected: LLM fallback fires; embed description shows "⚠ Generated — verify against sourcebook"; footer reads "Source — LLM generated (verify). Seed reference: FoundryVTT pf2e (Paizo, ORC license)"; `mnemosyne/pf2e/harvest/barghest.md` exists with `verified: false`, `source: llm-generated`, `medicine_dc` clamped to DC_BY_LEVEL[4]=19 regardless of LLM-returned value.
result: [pending]

### 3. `:pf harvest Alpha Wolf` in live Discord (fuzzy seed match)
expected: Fuzzy-match hits Wolf; embed description shows italic `_Matched to closest entry: Wolf. Confirm if this wasn't intended._`; monster source is `seed-fuzzy`; cache file written under **canonical slug** `mnemosyne/pf2e/harvest/wolf.md` (WR-05 fix — not under `alpha-wolf.md`).
result: [pending]

### 4. `:pf harvest Wolf Lord` in live Discord (fuzzy-below-cutoff)
expected: Falls through fuzzy (score <85) to LLM fallback; embed shows generated warning, NOT silent Wolf mismatch. Pitfall 2 boundary honoured end-to-end against live LM Studio.
result: [pending]

### 5. `:pf harvest Boar,Wolf,Orc` in live Discord (batch)
expected: Single aggregated embed titled "Harvest report — 3 monsters"; components grouped by type across monsters; footer matches source mix with FoundryVTT/ORC attribution on all branches (IN-02 fix); per-monster cache files under `mnemosyne/pf2e/harvest/`.
result: [pending]

### 6. Second `:pf harvest Wolf` after first query (cache-hit)
expected: Instant response; no LLM token usage observed in LM Studio log; cache file timestamp unchanged from first query.
result: [pending]

### 7. DM ratification flow — manually edit cached note to `verified: true`, re-query
expected: Embed no longer shows "⚠ Generated" warning; fuzzy-match note (if any) is preserved across the cache re-read (CR-03 fix); cache is re-read (not LLM re-generated).
result: [pending]

### 8. Container rebuild smoke — `sentinel.sh up` after Phase 32 changes
expected: pf2e-module container starts cleanly with rapidfuzz 3.14.5 wheel; lifespan log shows "Registered with Sentinel Core (attempt 1)"; no Pydantic validation error on harvest-tables.yaml (160 monsters loaded); `GET /modules/pathfinder/healthz` via sentinel-core returns 200.
result: [pending]

## Summary

total: 8
passed: 0
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps

None identified automatically. Gaps discovered during human testing should be recorded here with a `debug_session:` field if they require investigation.
