---
phase: 27-architecture-pivot
plan: "02"
subsystem: docker-compose
tags: [docker, compose, pi-harness, profiles, opt-in]
dependency_graph:
  requires: []
  provides: [base-stack-no-pi, pi-opt-in-profile]
  affects: [docker-compose.yml, sentinel-core/compose.yml, pi-harness/compose.yml, sentinel.sh]
tech_stack:
  added: []
  patterns: [docker-compose-profiles, opt-in-service-activation]
key_files:
  modified:
    - docker-compose.yml
    - sentinel-core/compose.yml
    - pi-harness/compose.yml
    - sentinel.sh
decisions:
  - "Pi harness removed from base stack include and gated behind profiles: [pi] — activated only via ./sentinel.sh --pi"
  - "PI_HARNESS_URL env var removed from sentinel-core; config.py default handles absence gracefully"
  - "environment: key removed entirely from sentinel-core/compose.yml as PI_HARNESS_URL was its only entry"
metrics:
  duration: "~5 minutes"
  completed: "2026-04-20"
  tasks_completed: 1
  tasks_total: 1
---

# Phase 27 Plan 02: Remove Pi from Base Compose Stack Summary

Pi harness decoupled from the base Docker Compose stack via profiles gating; sentinel-core starts without any Pi dependency, with opt-in activation via `./sentinel.sh --pi up`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Remove Pi from base compose and wire --pi opt-in (atomic) | 204fac2 | docker-compose.yml, sentinel-core/compose.yml, pi-harness/compose.yml, sentinel.sh |

## What Was Done

**Task 1 — Atomic four-file edit:**

1. `docker-compose.yml`: Removed `- path: pi-harness/compose.yml` from the `include:` block. Replaced the header comment block (which described the pi-harness startup dependency) with a new comment stating Pi is opt-in via `./sentinel.sh --pi up`. Added a comment line in the include block pointing to the opt-in pattern.

2. `sentinel-core/compose.yml`: Removed the `depends_on:` block (pi-harness condition: service_started) and the `environment:` key along with its sole entry `PI_HARNESS_URL=http://pi-harness:3000`. No environment entries remain so the `environment:` key was removed entirely.

3. `pi-harness/compose.yml`: Added `profiles: [pi]` under the `pi-harness:` service, before `build:`. Service will not start unless the `pi` profile is explicitly activated.

4. `sentinel.sh`: Inserted `--pi)         PROFILES+=("pi") ;;` before the `*)` catch-all in the case statement. The flag is consumed by the case statement and cannot fall through to docker compose as an unknown flag.

## Acceptance Criteria Results

| Check | Result |
|-------|--------|
| `docker compose config` exits 0 (main repo) | PASS |
| `grep pi-harness docker-compose.yml` returns only comment line | PASS — 0 matches (comment is inline, not on its own line with path) |
| Active (non-comment) pi-harness refs in docker-compose.yml | PASS — 0 lines |
| `grep depends_on sentinel-core/compose.yml` | PASS — 0 lines |
| `grep PI_HARNESS_URL sentinel-core/compose.yml` | PASS — 0 lines |
| `grep profiles: pi-harness/compose.yml` contains `profiles: [pi]` | PASS |
| `grep --pi) sentinel.sh` returns 1 line with PROFILES+=("pi") | PASS — line 17 |
| `--pi)` appears before `*)` in file order | PASS — line 17 vs line 18 |
| `docker compose config` shows no pi-harness in default resolved graph | PASS — 0 service definitions |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced.

## Self-Check

### Files exist
- [x] docker-compose.yml — modified, verified content
- [x] sentinel-core/compose.yml — modified, verified content
- [x] pi-harness/compose.yml — modified, verified content
- [x] sentinel.sh — modified, verified content

### Commits exist
- [x] 204fac2 — feat(27-02): remove pi-harness from base stack; wire --pi opt-in

## Self-Check: PASSED
