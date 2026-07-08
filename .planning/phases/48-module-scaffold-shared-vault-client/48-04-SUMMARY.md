---
phase: 48-module-scaffold-shared-vault-client
plan: 04
subsystem: infra
tags: [obsidian-rest, sentinel-shared, graph-check, vault-sweeper, pydantic-settings, music-module]

# Dependency graph
requires:
  - phase: 48-module-scaffold-shared-vault-client (Plan 01)
    provides: "sentinel_shared.obsidian: ObsidianClientCore; sentinel_shared.graph_check: pure vendored orphan checker"
  - phase: 48-module-scaffold-shared-vault-client (Plan 03)
    provides: "modules/music/ scaffold — app/main.py lifespan, app/obsidian.py core-only ObsidianClient, music venv"
provides:
  - "modules/music/app/seed.py: HUB_NOTES (4-note unique-stem hub-mesh) + seed_music_hub(client), wired into main.py lifespan (graceful)"
  - "modules/music/tests/test_music_vault_seed.py: pure module-side zero-orphan + schema compliance proof (D-10)"
  - "modules/music/scripts/gen_sweep_protection_env.py: derives SWEEP_SKIP_PREFIXES/PROTECTED_NAMESPACES from Core Settings defaults + music/ (D-13)"
  - "sentinel-core/tests/test_env_override_matches_core_defaults.py: Core-side drift/un-protect guard (test only)"
  - ".env.example: documented (generated, do-not-hand-edit) sweeper-protection env block"
affects: [phase-49-plus-music-routes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cross-repo generation script pattern: a module-owned script (gen_sweep_protection_env.py) reaches across the repo via a repo-relative sys.path insert to READ a sibling service's Settings.model_fields[...].default at generation time only — never at module runtime, and never as a module dependency (MUS-01/MUS-02 stay intact)."
    - "Pure derive_override() helper shared by the generator's __main__ and the Core-side drift test — 'generate, never hand-copy' is enforced by one code path being called from both places, not merely documented."
    - "D-13 atomic co-commit exception: this plan's two tasks land in ONE git commit (first music/ write + its sweeper protection together), the single deliberate exception to GSD's one-commit-per-task rule."

key-files:
  created:
    - modules/music/app/seed.py
    - modules/music/tests/test_music_vault_seed.py
    - modules/music/scripts/gen_sweep_protection_env.py
    - sentinel-core/tests/test_env_override_matches_core_defaults.py
  modified:
    - modules/music/app/main.py
    - .env.example

key-decisions:
  - "Hub-mesh uses 4 UNIQUE filename stems (index, lessons-index, practice-log-index, ideas-index) with bare-stem wikilink targets, per the plan's corrected design — Core's resolve_wikilink matches strictly by unique stem, so RESEARCH Pattern 4's identically-named index.md bodies would NOT resolve and would false-flag as orphans."
  - "seed_music_hub lets put_note's httpx.HTTPStatusError propagate; the caller (main.py's lifespan) owns the single try/except that logs and swallows a vault outage, keeping the graceful-degrade decision in one place."
  - "gen_sweep_protection_env.py sets SENTINEL_API_KEY as a placeholder env default before importing sentinel-core's app.config, purely to satisfy that module's required-field validation at import time — the script never reads or uses that key's value, only Settings.model_fields[...].default (class-level metadata)."
  - "The drift test lives in sentinel-core/tests/ (not sentinel-core/app/) — MUS-01's 'zero Core code changes' scopes the app package, not its test suite, matching the plan's explicit framing."

patterns-established:
  - "Any future module needing to protect its own vault namespace from the sweeper can follow the same generate-from-Settings-defaults + drift-test pattern rather than hand-copying Core's tuples."

requirements-completed: [MUS-01, MUS-02, MUS-05]

coverage:
  - id: D1
    description: "The music/ hub-mesh (4 unique-stem notes) is written via the module's own ObsidianClient and is provably zero-orphan + _schema/wikilink-compliant by a pure module-side test (no live Obsidian, no sentinel-core import)"
    requirement: "MUS-05"
    verification:
      - kind: unit
        ref: "modules/music/tests/test_music_vault_seed.py (4 tests: zero-orphan, four-unique-stems, schema-fence+wikilink, schema-fields-and-null-reserved)"
        status: pass
    human_judgment: false
  - id: D2
    description: "main.py's lifespan seeds the hub-mesh after registration inside a guard that logs and swallows a vault outage, never crashing startup"
    requirement: "MUS-05"
    verification:
      - kind: unit
        ref: "modules/music/tests/ full suite (10 passed) — registration/healthz tests unaffected by the added lifespan seed call"
        status: pass
    human_judgment: false
  - id: D3
    description: "Seed writes exclusively through the module's own ObsidianClient (put_note); MUS-02 import-boundary grep stays empty"
    requirement: "MUS-02"
    verification:
      - kind: unit
        ref: "grep -rn 'from app.vault import|import vault|sentinel_core.*vault' modules/music/ (empty, exit 1)"
        status: pass
    human_judgment: false
  - id: D4
    description: "SWEEP_SKIP_PREFIXES/PROTECTED_NAMESPACES are generated from Core's committed Settings defaults + music/ (never hand-copied) and guarded by a Core-side drift test that also asserts critical protected prefixes survive"
    requirement: "MUS-01"
    verification:
      - kind: unit
        ref: "sentinel-core/tests/test_env_override_matches_core_defaults.py (5 tests: skip-prefixes-match, protected-namespaces-match, critical-skip-prefixes-survive, critical-protected-namespaces-survive, music-trailing-slash-in-both-never-bare)"
        status: pass
      - kind: integration
        ref: "cd modules/music && .venv/bin/python scripts/gen_sweep_protection_env.py | grep -c \"music/\" -> 2"
        status: pass
    human_judgment: false
  - id: D5
    description: "The seed writer and its sweeper protection land in ONE atomic commit (D-13/Pitfall 1) with zero sentinel-core/app/* changes"
    requirement: "MUS-01"
    verification:
      - kind: unit
        ref: "git show --stat e2ca9ef (lists both modules/music/app/seed.py and modules/music/scripts/gen_sweep_protection_env.py); git diff --stat sentinel-core/app/ (empty)"
        status: pass
    human_judgment: false

duration: 18min
completed: 2026-07-08
status: complete
---

# Phase 48 Plan 04: Music Vault Seed + Sweeper Protection Summary

**First music/ write is a 4-note unique-stem hub-mesh (zero-orphan + _schema-compliant, proven by a pure module-side test), landed in the SAME atomic commit as a generated SWEEP_SKIP_PREFIXES/PROTECTED_NAMESPACES sweeper-protection override derived from sentinel-core's own Settings defaults.**

## Performance

- **Duration:** 18 min (estimated from session start to commit)
- **Started:** 2026-07-07T22:53:00-04:00 (approx.)
- **Completed:** 2026-07-07T23:11:19-04:00 (commit `e2ca9ef`)
- **Tasks:** 2 (co-committed per D-13 — see Task Commits below)
- **Files modified:** 6 (4 new, 2 modified)

## Accomplishments
- `modules/music/app/seed.py` — `HUB_NOTES` (4 unique-stem notes: `music/index.md`, `music/lessons/lessons-index.md`, `music/practice-log/practice-log-index.md`, `music/ideas/ideas-index.md`), each with leading YAML frontmatter, an H1 claim title, ≥1 bare-stem resolvable wikilink, and a trailing ` ```_schema ` block (title + wikilinks + null `listenbrainz_context`/`discogs_context`); `async def seed_music_hub(client)` idempotently PUTs each note.
- `modules/music/app/main.py` — `lifespan` now calls `seed_music_hub(app.state.obsidian_client)` after registration, wrapped in a try/except that logs and swallows a vault outage so startup never crashes.
- `modules/music/tests/test_music_vault_seed.py` — 4 pure tests proving `build_graph_report(HUB_NOTES).orphans == []`, exactly the 4 mandated unique stems, every note ending in a terminal ` ```_schema ` fence with ≥1 wikilink, and each schema block carrying `title`/`wikilinks` + null reserved fields.
- `modules/music/scripts/gen_sweep_protection_env.py` — pure `derive_override(core_default) -> list` helper + a `__main__` that imports sentinel-core's `Settings` (via a repo-relative `sys.path` insert, generation-time only) and prints generated `SWEEP_SKIP_PREFIXES`/`PROTECTED_NAMESPACES` deploy-`.env` lines, both containing trailing-slash `music/`.
- `sentinel-core/tests/test_env_override_matches_core_defaults.py` — 5 tests: generated values exactly equal Core's live defaults + `music/`, and the critical prefixes (`security/`, `self/`, `pf2e/`, `mnemosyne/`, `templates/`) and namespaces (`security/`, `self/`, `templates/`) survive — the un-protect regression guard (Pitfall B).
- `.env.example` — new documented block explaining both vars are GENERATED, never hand-edited, and must land in the same commit as any change to the first `music/` write.
- **D-13 atomicity verified:** `git show --stat e2ca9ef` lists both `modules/music/app/seed.py` and `modules/music/scripts/gen_sweep_protection_env.py`; `git log --oneline --follow` on each file shows only this one commit — no earlier commit introduced the seed without the protection.

## Task Commits

Per the plan's Commit Discipline section (D-13/Pitfall 1), Task 1 does NOT commit on its own — both tasks land in ONE atomic commit:

1. **Task 1: First music/ hub-mesh write + module-side compliance test** — verified green, left staged (no commit)
2. **Task 2: Generated sweeper protection + Core-side drift guard** — `e2ca9ef` (feat, co-commit covering BOTH tasks)

**Plan metadata:** (this commit, docs: complete plan)

_Note: This is the plan's single deliberate exception to GSD's one-commit-per-task rule, per the plan's explicit Commit Discipline instructions._

## Files Created/Modified
- `modules/music/app/seed.py` - `HUB_NOTES` 4-note hub-mesh + `seed_music_hub(client)`
- `modules/music/app/main.py` - lifespan wiring for the graceful seed call
- `modules/music/tests/test_music_vault_seed.py` - pure zero-orphan + schema compliance test
- `modules/music/scripts/gen_sweep_protection_env.py` - Settings-defaults-derived sweeper-protection generator
- `sentinel-core/tests/test_env_override_matches_core_defaults.py` - Core-side drift/un-protect guard (test only)
- `.env.example` - documented generated sweeper-protection env block

## Decisions Made
- Corrected hub-mesh design used unique stems + bare-stem wikilink targets (not RESEARCH Pattern 4's identically-named `index.md` bodies), per the plan's explicit objective correction — this is what makes the mesh genuinely zero-orphan under Core's real stem-match `resolve_wikilink` rule.
- `seed_music_hub` itself does not catch `put_note` errors — the single graceful-degrade guard lives in `main.py`'s lifespan, keeping the "who decides to swallow this error" decision in one place rather than duplicated across the seed function and its caller.
- The generator script sets a placeholder `SENTINEL_API_KEY` env default (only if unset) purely so sentinel-core's `app.config` module-level `Settings()` instantiation succeeds on import — the script never reads that key's value, only `Settings.model_fields[...].default`, which is class-level metadata independent of any instance.
- Placed the drift test at `sentinel-core/tests/test_env_override_matches_core_defaults.py` (test tree, not `app/`) since MUS-01's zero-Core-code-change scope is the `app` package specifically, matching the plan's explicit framing ("a TEST — not Core app code").

## Deviations from Plan

None — plan executed exactly as written, including the D-13 atomic co-commit discipline.

## Issues Encountered
- Running `gen_sweep_protection_env.py` as a bare script initially raised `pydantic_core.ValidationError: sentinel_api_key Field required`, because importing sentinel-core's `app.config` module triggers a module-level `settings = Settings()` instantiation that requires that field. Resolved by setting a placeholder `SENTINEL_API_KEY` env default (via `os.environ.setdefault`) before the import — the script only ever reads `Settings.model_fields[...].default` (class-level), never the instantiated singleton's values, so the placeholder has no effect on the generated output. Not a plan deviation (no plan text specified this workaround, but it was necessary to make the specified `<verify>` command run at all, and is a Rule 3 auto-fix — the same class of import-path nuance Plan 03 hit with bare `python -c` invocations not consulting `pyproject.toml`'s `pythonpath`).

## User Setup Required
None - the generated `.env` lines are commented placeholders in `.env.example`; the deploy checkout (`/Volumes/Mini Me`) is where an operator would run the generator and append its real output to the live `.env`, per existing project convention. Not part of this dev-tree scaffold.

## Next Phase Readiness
- `music/` has durable, zero-orphan link targets (`index`, `lessons-index`, `practice-log-index`, `ideas-index`) that Phase 49+ practice/idea/lesson notes can resolve against immediately instead of being born orphans.
- `music/` is protected from the vault sweeper via both `SWEEP_SKIP_PREFIXES` and `PROTECTED_NAMESPACES` (belt-and-suspenders, D-14) — but only once an operator runs the generator and appends its output to the LIVE deploy `.env`; this dev-tree change alone does not protect a running deployment until that manual step happens.
- Phase 48 is now fully executed (Plans 01, 02, 03, 04 all complete).
- No blockers.

---
*Phase: 48-module-scaffold-shared-vault-client*
*Completed: 2026-07-08*

## Self-Check: PASSED

All created files verified present on disk (`modules/music/app/seed.py`, `modules/music/tests/test_music_vault_seed.py`, `modules/music/scripts/gen_sweep_protection_env.py`, `sentinel-core/tests/test_env_override_matches_core_defaults.py`, this SUMMARY.md). The D-13 co-commit hash `e2ca9ef` confirmed present in `git log --oneline --all`. Re-ran `git show --stat e2ca9ef` — both `app/seed.py` and `scripts/gen_sweep_protection_env.py` listed together. Re-ran the music venv suite (10 passed) and the sentinel-core suite (598 passed, 12 skipped) — both green.
