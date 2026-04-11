---
phase: 21-production-recovery-security-pipeline-discord
plan: 01
subsystem: security
tags: [injection-filter, output-scanner, anthropic, fastapi, docker-compose, discord]

# Dependency graph
requires:
  - phase: 06-security-pipeline
    provides: Original injection_filter.py and output_scanner.py (commit c6f4753)
provides:
  - InjectionFilter class restoring SEC-01 prompt injection defense
  - OutputScanner class restoring SEC-02 credential/PII leak detection
  - main.py lifespan wiring both security services into app.state
  - Discord interface active in docker-compose.yml include block
  - 24 tests covering security pipeline behaviors
affects: [22-discord-commands, 23-audit-logging, all phases using POST /message]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Security services instantiated once in lifespan, shared via app.state across all requests"
    - "fail-open pattern for OutputScanner when ANTHROPIC_API_KEY not set"
    - "DO NOT COMMENT guard comment on critical docker-compose entries"

key-files:
  created:
    - sentinel-core/app/services/injection_filter.py
    - sentinel-core/app/services/output_scanner.py
    - sentinel-core/tests/test_injection_filter.py
    - sentinel-core/tests/test_output_scanner.py
  modified:
    - sentinel-core/app/main.py
    - docker-compose.yml

key-decisions:
  - "Restored exactly from commit c6f4753 via git show — no manual edits to preserve verified-good content"
  - "DO NOT COMMENT guard added to Discord include line to prevent fourth accidental removal"
  - "uv venv created for sentinel-core worktree to install anthropic package (not in system Python)"

patterns-established:
  - "Pattern: Use git show <hash>:<path> > <path> for exact restoration of deleted files — no manual rewrite"
  - "Pattern: DO NOT COMMENT guard comment on entries that have been removed multiple times"

requirements-completed: [CORE-03, SEC-01, SEC-02, IFACE-02, IFACE-03, IFACE-04]

# Metrics
duration: 18min
completed: 2026-04-11
---

# Phase 21 Plan 01: Production Recovery Summary

**Security pipeline (InjectionFilter + OutputScanner) restored from c6f4753, re-wired into main.py lifespan, Discord uncommented in docker-compose — POST /message AttributeError eliminated, 86 tests pass**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-04-11T~13:30Z
- **Completed:** 2026-04-11T~13:48Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Restored injection_filter.py (83 lines, InjectionFilter class, 13 tests) from commit c6f4753
- Restored output_scanner.py (116 lines, OutputScanner class, 11 tests) from commit c6f4753
- Re-wired InjectionFilter and OutputScanner into main.py lifespan — eliminates the `AttributeError: 'State' object has no attribute 'injection_filter'` crash on every POST /message request
- Uncommented interfaces/discord/compose.yml in docker-compose.yml with DO NOT COMMENT guard to prevent a fourth removal
- Full test suite passes: 86 tests, 0 failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Restore four deleted files from git history** - `4436ee2` (feat)
2. **Task 2: Re-wire InjectionFilter + OutputScanner in main.py lifespan** - `3539aef` (feat)
3. **Task 3: Uncomment Discord include in docker-compose.yml** - `c22fe34` (feat)

## Files Created/Modified

- `sentinel-core/app/services/injection_filter.py` - InjectionFilter class: sanitize(), wrap_context(), filter_input() — strips prompt injection patterns before requests reach AI (SEC-01)
- `sentinel-core/app/services/output_scanner.py` - OutputScanner class: async scan() with fail-open design — uses Claude Haiku as secondary classifier to block confirmed credential/PII leaks (SEC-02)
- `sentinel-core/tests/test_injection_filter.py` - 13 unit tests covering InjectionFilter behaviors
- `sentinel-core/tests/test_output_scanner.py` - 11 async unit tests covering OutputScanner behaviors with AsyncMock
- `sentinel-core/app/main.py` - Added 3 security imports + 11-line lifespan block instantiating InjectionFilter and OutputScanner into app.state
- `docker-compose.yml` - Added active include for interfaces/discord/compose.yml with DO NOT COMMENT guard

## Decisions Made

- Restored from commit c6f4753 exactly via `git show` — no manual rewrites to ensure verified-good content
- Added DO NOT COMMENT guard comment on the Discord include line (this entry has been commented out three separate times)
- Used atomic Write for main.py to avoid ruff formatter stripping imports as "unused" before the lifespan block was in place

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created uv venv for worktree to install anthropic package**
- **Found during:** Task 1 (running restored tests)
- **Issue:** System Python 3.14 did not have `anthropic` installed; `uv pip install` outside venv rejected; no existing venv in worktree
- **Fix:** Created `.venv` via `uv venv --python 3.12` in worktree sentinel-core directory; installed `anthropic>=0.93.0,<1.0` and test dependencies via `uv pip install`
- **Files modified:** sentinel-core/.venv/ (not tracked in git)
- **Verification:** `python -m pytest tests/test_injection_filter.py tests/test_output_scanner.py -v` passed 24 tests
- **Committed in:** Not committed (venv is gitignored)

**2. [Rule 3 - Blocking] Used atomic Write for main.py imports + lifespan block**
- **Found during:** Task 2 (adding imports via Edit)
- **Issue:** A PostToolUse formatter hook (ruff F401) removed newly added imports immediately after each Edit because the imports weren't yet referenced in the file body
- **Fix:** Wrote the complete main.py in a single Write call containing all imports and the full lifespan block — imports are used at the point the formatter runs
- **Files modified:** sentinel-core/app/main.py
- **Verification:** All 6 expected grep matches confirmed present; 86 tests passed
- **Committed in:** 3539aef

---

**Total deviations:** 2 auto-fixed (both Rule 3 blocking)
**Impact on plan:** Both fixes necessary to complete execution. No scope creep.

## Issues Encountered

- Test count in restored files is 24 (13 + 11), not 26 as stated in the plan's expected output. The plan notes "26 tests collected" but commit c6f4753 contains files with 24 tests. Restored exactly as instructed — all 24 pass.

## User Setup Required

None — no external service configuration required. OutputScanner degrades gracefully (fail-open) if ANTHROPIC_API_KEY is not set.

## Next Phase Readiness

- POST /message is no longer crashing — E2E flows 1-3 and 5-6 are unblocked
- Security pipeline (InjectionFilter + OutputScanner) is live on every request
- Discord container will start on next `docker compose up`
- GAP-01 (AttributeError crash) and GAP-02 (Discord commented out) are closed
- Phase 22 (Discord commands) and Phase 23 (audit logging) are unblocked

---
*Phase: 21-production-recovery-security-pipeline-discord*
*Completed: 2026-04-11*
