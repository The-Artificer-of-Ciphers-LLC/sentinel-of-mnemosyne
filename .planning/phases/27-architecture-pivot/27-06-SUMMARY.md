---
plan: 27-06
phase: 27-architecture-pivot
status: complete
completed: 2026-04-21
---

# Summary: Plan 27-06 — Pi Harness Teardown Verification

## What Was Done

Verified at runtime that commit 305e5d9 (`ALL_KNOWN_PROFILES` loop in `sentinel.sh`) correctly resolves UAT Test 2. Closed the Phase 27 UAT gap record.

## Verification Steps Executed

1. `grep "ALL_KNOWN_PROFILES" sentinel.sh` — confirmed fix present (lines 29, 32)
2. `./sentinel.sh --pi up -d` — pi-harness, sentinel-core, discord, ofelia, pentest-agent all started
3. `docker compose ps` — pi-harness listed as Up (healthy) on port 3000
4. `./sentinel.sh down` — ALL_KNOWN_PROFILES injected all profile flags; pi-harness stopped and removed cleanly
5. `docker compose ps` — 0 services (empty)
6. `docker ps -a --filter name=pi-harness` — no containers (empty)

## Result

UAT Test 2: **PASS**. `./sentinel.sh down` stops pi-harness even when it was started with `--pi`. No orphaned containers.

## Artifacts Updated

- `.planning/phases/27-architecture-pivot/27-UAT.md` — Test 2 updated to `result: pass`, summary to 9/9 passed / 0 issues, teardown gap marked `status: resolved` with `resolved_by: commit 305e5d9`

## Self-Check

- [x] sentinel.sh `ALL_KNOWN_PROFILES` loop confirmed present
- [x] pi-harness stops cleanly on bare `./sentinel.sh down`
- [x] `docker ps -a --filter name=pi-harness` returns empty after teardown
- [x] 27-UAT.md shows `passed: 9`, `issues: 0`, `status: resolved` on teardown gap
- [x] SUMMARY.md committed

## Self-Check: PASSED
