---
phase: 32-monster-harvesting
plan: 02
subsystem: pathfinder-data
tags: [rapidfuzz, yaml, foundry-pf2e, orc-license, scaffold, seed-data]

# Dependency graph
requires:
  - phase: 32-monster-harvesting
    provides: Wave-0 test contract (21 unit + 3 integration stubs — test_rapidfuzz_importable is the only harvest test that flips GREEN here)
provides:
  - rapidfuzz 3.14.5 installed in pathfinder venv and tracked in uv.lock (dep gate for Waves 1-3)
  - modules/pathfinder/scripts/scaffold_harvest_seed.py — one-shot Foundry pf2e scraper (--output flag) for future roster regeneration
  - modules/pathfinder/data/harvest-roster.txt — canonical L1-3 monster roster (160 entries, deterministic input for hand-curation)
  - modules/pathfinder/data/harvest-tables.yaml — seed YAML (160 monsters; 51 humanoid components:[], 109 non-humanoid) bound 1:1 to the roster
  - test_rapidfuzz_importable flipped RED → GREEN (first Wave-0 stub to resolve)
affects: [32-03-harvest-helpers, 32-04-route-handler, 32-05-bot-dispatch]

# Tech tracking
tech-stack:
  added:
    - "rapidfuzz>=3.14.0 (resolved: 3.14.5) — fuzzy-match scorer for D-02 unknown-monster fallback"
  patterns:
    - "Seed YAML header embeds ORC license attribution + Foundry pf2e source citation (D-01 reshape compliance)"
    - "Roster→YAML 1:1 binding rule — every roster line has one YAML monsters entry; no silent substitution"
    - "Scaffold script renders commented-template example block instead of live `components:` key (Blocker 3 mitigation: Pydantic lifespan cannot see a half-shape during DM edits)"
    - "GitHub Contents API + entry['download_url'] rather than hand-constructed raw URLs — insulates scraper from future branch renames (discovered: default branch is v14-dev, not master)"
    - "Component assignment by trait taxonomy (humanoid→empty, animal→hide+fangs/claws, undead→bone/ectoplasm, etc.) — deterministic rules documented in the commit message so a DM can reproduce or override"

key-files:
  created:
    - modules/pathfinder/scripts/scaffold_harvest_seed.py
    - modules/pathfinder/data/harvest-roster.txt
    - modules/pathfinder/data/harvest-tables.yaml
    - modules/pathfinder/uv.lock (newly tracked)
  modified:
    - modules/pathfinder/pyproject.toml

key-decisions:
  - "rapidfuzz pinned to >=3.14.0 per plan (resolved 3.14.5); alphabetically placed between pyyaml and reportlab in dependencies list"
  - "Scaffold script uses GitHub Contents API response field `download_url` rather than hand-constructing raw URLs from a branch constant — auto-tracks default branch rename (caught v14-dev during execution)"
  - "160 monsters committed to the seed instead of the researcher's 25-40 estimate — the Foundry pf2e pathfinder-monster-core pack contains far more L1-3 entries than the research round sampled. Binding rule forbids substitution, so the full roster is authoritative."
  - "Humanoid monsters (51 entries) have components: [] with inline intent documented in the YAML header. Non-humanoids (109) receive components by trait-family rules. DM may override any entry at will; the YAML is the authoring surface."
  - "Medicine DCs are exactly Table 10-5 (L1→15, L2→16, L3→18) with +2 Hard / +5 Rare permitted for unusual components; verifier enforces set membership"
  - "Craftable values use level-0 common item pricing from Foundry pf2e equipment pack under ORC license (waterskin 5 sp, leather armor 2 gp, etc.)"

patterns-established:
  - "YAML scaffold renders a fully-commented-out `# components:` template block — DMs uncomment the whole block together, preventing partial-entry Pydantic crashes at lifespan startup"
  - "Data-layer plans may produce substantial line counts (2423 lines of YAML here); the binding rule (roster ↔ YAML 1:1) is the invariant that makes the scale reviewable"
  - "ORC attribution lives in the YAML header comment block AND will be echoed in the Discord embed footer (Plan 32-05)"

requirements-completed: [HRV-01, HRV-02, HRV-03, HRV-04, HRV-05, HRV-06]

# Metrics
duration: ~9 min
completed: 2026-04-24
---

# Phase 32 Plan 02: Seed YAML + rapidfuzz Dependency Summary

**rapidfuzz 3.14.5 installed; 160-monster L1-3 seed committed bound 1:1 to the canonical Foundry pf2e roster — Wave-0's `test_rapidfuzz_importable` flipped GREEN; data layer complete; helpers land in Plan 32-03.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-04-24T01:49:55Z
- **Completed:** 2026-04-24T01:58:53Z
- **Tasks:** 4
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments

- `modules/pathfinder/pyproject.toml` + `uv.lock` — rapidfuzz 3.14.5 resolved and installed; alphabetical position preserved (pyyaml → rapidfuzz → reportlab)
- `modules/pathfinder/scripts/scaffold_harvest_seed.py` — one-shot httpx.Client sync scraper for Foundry pf2e pathfinder-monster-core; `--output` flag writes a deterministic roster; scaffold YAML mode emits a commented-template block so DM edits cannot produce a Pydantic-invalid half-shape
- `modules/pathfinder/data/harvest-roster.txt` — 160 monsters scraped from foundryvtt/pf2e (54 L1 / 60 L2 / 46 L3); canonical input for the binding rule
- `modules/pathfinder/data/harvest-tables.yaml` — 2423-line seed YAML with ORC license attribution header; every roster entry has a corresponding monsters: entry; Medicine DCs match Table 10-5 exactly (L1→15, L2→16, L3→18; zero medicine_dc: 17 anywhere); craftable values match the gp/sp/cp regex
- `test_rapidfuzz_importable` flipped RED → GREEN — first of the 31 Wave-0 stubs to resolve

## Task Commits

Each task was committed atomically on main:

1. **Task 32-02-01:** Add rapidfuzz>=3.14.0 dep + regenerate uv.lock — `c2cbe16` (chore)
2. **Task 32-02-02:** Add scaffold_harvest_seed.py — Foundry pf2e L1-3 scraper — `e126a89` (feat)
3. **Task 32-02-03:** Generate canonical L1-3 harvest roster from Foundry pf2e — `1050a3c` (feat, includes Rule 1 scaffolder URL fix)
4. **Task 32-02-04:** Hand-curate harvest-tables.yaml — 160 monsters bound to roster — `7def746` (feat)

## Per-Level Breakdown

| Level | Count | Humanoid (components: []) | Non-humanoid |
|-------|-------|---------------------------|--------------|
| 1     | 54    | (subset of 51 total)      | (subset of 109 total) |
| 2     | 60    |                           |              |
| 3     | 46    |                           |              |
| **Total** | **160** | **51** | **109** |

## Files Created/Modified

- `modules/pathfinder/pyproject.toml` (MODIFIED, +1 line) — `"rapidfuzz>=3.14.0",` inserted alphabetically
- `modules/pathfinder/uv.lock` (NEW, 2056 lines) — newly tracked lockfile with rapidfuzz 3.14.5 resolved
- `modules/pathfinder/scripts/scaffold_harvest_seed.py` (NEW, 137 lines) — httpx.Client sync scraper with `--output` roster mode and `render_yaml_scaffold` commented-template mode; no `__init__.py` in scripts dir (intentionally not a package)
- `modules/pathfinder/data/harvest-roster.txt` (NEW, 160 lines) — tab-separated `<name>\t<level>` canonical roster
- `modules/pathfinder/data/harvest-tables.yaml` (NEW, 2423 lines) — ORC-attributed seed YAML, 160 entries bound 1:1 to roster

## Decisions Made

- **rapidfuzz version pin `>=3.14.0`** (resolved 3.14.5) per plan; placed alphabetically between pyyaml and reportlab so future dep scans preserve ordering.
- **Scraper uses GitHub Contents API `download_url` field** rather than constructing raw URLs from a branch constant. Discovered during execution that the Foundry repo's default branch is `v14-dev` (not `master`) and the packs dir was restructured in 2024 to `packs/pf2e/<pack>/`. Using the API's provided download_url auto-tracks any future rename.
- **160 monsters vs researcher's 25-40 estimate:** the pathfinder-monster-core pack contains 492 JSON files; 160 of them are L1-3. The binding rule (one YAML entry per roster line, no substitution) required curating all 160. Humanoids (51) use `components: []` per PLAN; non-humanoids (109) receive trait-derived components.
- **Component assignment by trait taxonomy** (deterministic, documented in the 32-02-04 commit message):
  - `humanoid` → components: [] (51 entries)
  - `animal` / `beast` → Hide + Fangs OR Claws (claw keywords: bear/cat/lion/panther/ape/raptor/eagle/hawk/owl/chupacabra)
  - `undead` / zombie / ghoul / mummy / skeleton / wight → Bone + essence variants
  - `wraith` / specter / shade / `incorporeal` → Ectoplasm only (no Bone)
  - `dragon` in traits or name → Scales + Fangs
  - `construct` → Core + Plating
  - `elemental` + sub-trait (fire/water/air/earth) → essence shard
  - `fey` → Fey essence + Glamour dust
  - `fiend` → Horn + Infernal ichor
  - `celestial` / `holy` / angel-named → Feather + Celestial essence
  - `aberration` → Unusual organ (arcane reagent craftable)
  - `ooze` → Ooze essence (adhesive craftable)
  - `plant` → Fibrous bark + Seeds
  - `swarm` → Swarm bodies (chitin powder)
  - `dinosaur` / `reptilian` / snake / serpent / lizard / crocodile → Scaled hide + Fangs
  - `giant` / `troll` → Hide (scaled up)
  - fallback → generic Hide
- **YAML quoting normalized** for plan grep compliance: `version: "1.0"` and `source: "foundryvtt-pf2e"` rendered with double quotes (PyYAML's default single-quote output was post-processed).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Scaffolder URL constants pointed to wrong path/branch**
- **Found during:** Task 32-02-03 (running the scaffolder for the first time)
- **Issue:** The initial `REPO_API` used `packs/pathfinder-monster-core` (404 — the repo restructured to `packs/pf2e/pathfinder-monster-core` in 2024). The `RAW_BASE` used `master` branch (404 — default branch is `v14-dev`). Result: all 492 file fetches failed silently and the scaffolder wrote a zero-monster roster.
- **Fix:** Changed `REPO_API` to the correct nested path. Removed the hardcoded `RAW_BASE` constant and switched to using each API listing entry's own `download_url` field. Added `raise_for_status()` + list-type guard so future API errors surface immediately instead of silently skipping all entries.
- **Files modified:** `modules/pathfinder/scripts/scaffold_harvest_seed.py` (before `data/harvest-roster.txt` was committed)
- **Commit:** `1050a3c` (shipped alongside the roster generation)

**2. [Rule 1 — Bug] Python comment contained literal `components: []` string that tripped the source-level grep**
- **Found during:** Task 32-02-02 acceptance verification
- **Issue:** The scaffolder had a Python comment block explaining *why* the script avoids emitting `components: []`. The comment contained the literal string `components: []`, which made `grep -c 'components: \[\]'` on the source return 1 instead of the plan's required 0.
- **Fix:** Reworded the Python comment to say "the empty-list form" rather than literally repeating the forbidden pattern. The plan's load-bearing smoke test (`assert 'components: []' not in out` against `render_yaml_scaffold` output) still passes — the YAML *render* never emits the half-shape.
- **Files modified:** `modules/pathfinder/scripts/scaffold_harvest_seed.py` (in the same commit as the fix)
- **Commit:** `e126a89`

### Scope Observation (not a deviation — PLAN accepts this)

- **160 monsters** is far above the RESEARCH.md `25-40` estimate. The researcher likely sampled only a subset or looked at Bestiary 1 instead of pathfinder-monster-core. The plan's binding rule mandates 1:1 roster↔YAML, so all 160 are committed. No silent substitution — this is exactly the behaviour the plan requested.

## Authentication Gates

None — all execution was local (host venv, GitHub API with anonymous rate limits, Python tooling).

## Issues Encountered

None that required human intervention. Rule 1 auto-fixes covered both defects inline.

## Verification

### 7/7 plan verification steps pass

```
=== 1. rapidfuzz importable ===       3.14.5
=== 2. test_rapidfuzz_importable ===  1 passed in 0.07s
=== 3. scaffold render smoke ===      OK (render has `# components:` and no `components: []`)
=== 4. roster line count ===          160 data/harvest-roster.txt
=== 5. YAML binding ===               160 monsters bound to 160 roster lines
=== 6. Other harvest stubs still RED === 23 failed, 1 passed in 0.17s
=== 7. No Phase 29/30/31 regressions === 60 passed, 24 deselected in 1.87s
```

### Acceptance greps

- `grep -F '"rapidfuzz>=3.14.0",' modules/pathfinder/pyproject.toml` → 1 match
- `grep -cE '^\s*"(pyyaml|rapidfuzz|reportlab)' modules/pathfinder/pyproject.toml` → 3 (alphabetical)
- `grep -F 'ORC license' modules/pathfinder/data/harvest-tables.yaml` → 2 matches (header block)
- `grep -F 'github.com/foundryvtt/pf2e' modules/pathfinder/data/harvest-tables.yaml` → 1 match
- `grep -F 'version: "1.0"' modules/pathfinder/data/harvest-tables.yaml` → 1 match
- `grep -F 'source: "foundryvtt-pf2e"' modules/pathfinder/data/harvest-tables.yaml` → 1 match
- `grep -cE 'medicine_dc: 17\b' modules/pathfinder/data/harvest-tables.yaml` → 0 (no off-by-one)
- `grep -F '# components:' modules/pathfinder/scripts/scaffold_harvest_seed.py` → 1 match (commented template)
- `grep -F 'components: []' modules/pathfinder/scripts/scaffold_harvest_seed.py` → 0 matches (plan's Blocker-3 check)

### YAML structural check

- `yaml.safe_load` parses without exception
- `doc['version'] == '1.0'`, `doc['source'] == 'foundryvtt-pf2e'`, `set([1,2,3]).issubset(doc['levels'])`
- `len(monsters) == 160 == len(roster)`
- `set(monster names in YAML) == set(monster names in roster)` (no missing, no extra)
- Every component has `name` (str), `medicine_dc` (int in {15,17,20} for L1 / {16,18,21} for L2 / {18,20,23} for L3), `craftable` (list)
- Every craftable has `name` (str), `crafting_dc` (int), `value` matching `^\d+ (gp|sp|cp)( \d+ (sp|cp))?$`
- All 160 YAML levels match their roster levels (no level mismatches)

## User Setup Required

None — rapidfuzz is installed via `uv sync`; YAML loads at Plan 32-03 lifespan startup.

## Next Phase Readiness

- **Wave 1 (Plan 32-03) unblocked.** rapidfuzz dep + YAML seed are the two hard prerequisites for the harvest helpers module:
  - `app.harvest.load_harvest_tables(path)` will `yaml.safe_load` the file created here and `HarvestTable.model_validate(raw)` the result
  - `app.harvest.lookup_seed` will use `rapidfuzz.process.extractOne` against the monster names in this seed
  - `app.harvest.format_price` will consume the vendor-value strings this YAML wrote
- **Waves 2-3 (Plans 32-04 / 32-05) unaffected** — this plan ships ZERO app-code or route-level changes.
- **Docker container rebuild:** PATTERNS §6 notes the pf2e-module container must be rebuilt to pick up the new rapidfuzz wheel. The executor's host venv has it; a containerized integration test run (Wave 2/3) will trigger `docker compose build pf2e-module`.

## Self-Check: PASSED

**Created files exist:**
- `modules/pathfinder/scripts/scaffold_harvest_seed.py` — FOUND
- `modules/pathfinder/data/harvest-roster.txt` — FOUND
- `modules/pathfinder/data/harvest-tables.yaml` — FOUND
- `modules/pathfinder/uv.lock` — FOUND (newly tracked)

**Commits exist:**
- `c2cbe16` — FOUND (rapidfuzz dep + uv.lock)
- `e126a89` — FOUND (scaffold script)
- `1050a3c` — FOUND (roster + scaffolder URL fix)
- `7def746` — FOUND (harvest-tables.yaml)

---
*Phase: 32-monster-harvesting*
*Completed: 2026-04-24*
