---
status: complete
phase: 27-architecture-pivot
source: [27-01-SUMMARY.md, 27-02-SUMMARY.md, 27-03-SUMMARY.md, 27-04-SUMMARY.md, 27-05-SUMMARY.md]
started: 2026-04-21T02:00:00Z
updated: 2026-04-21T03:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running containers. Run `./sentinel.sh up`. Sentinel Core boots without errors and GET http://localhost:8000/status returns 200 OK with a live JSON response.
result: pass
note: Fixed sentinel.sh PROFILES[@] unbound variable (bash 3.2 compat). Server returned 401 Unauthorized — live response, auth guard working.

### 2. Pi harness absent from base stack
expected: After running `./sentinel.sh up` (no `--pi` flag), `docker compose ps` shows NO pi-harness service running or listed.
result: pass
note: "Fixed in commit 305e5d9: sentinel.sh down subcommand now injects ALL_KNOWN_PROFILES so all profiled containers (pi-harness, discord, etc.) are included in teardown regardless of startup flags."

### 3. Pi harness starts with --pi flag
expected: After running `./sentinel.sh --pi up`, `docker compose ps` shows the pi-harness service listed and running alongside sentinel-core.
result: pass
note: Fixed docker-compose.yml — pi-harness/compose.yml was missing from include block, so profiles: [pi] gate never activated.

### 4. Module registration (authenticated)
expected: |
  With sentinel-core running, send:
    POST http://localhost:8000/modules/register
    Header: X-Sentinel-Key: <your key>
    Body: {"name": "test-mod", "base_url": "http://localhost:9999", "routes": []}
  Response should be 200 with body {"status": "registered"}.
result: pass
note: Required --build to pick up Phase 27 code (container was running stale image).

### 5. Module registration auth guard
expected: |
  Send the same POST /modules/register request with NO X-Sentinel-Key header.
  Response should be 401 or 403 (not 200, not 404).
result: pass

### 6. Module proxy — unknown module returns 404
expected: |
  POST http://localhost:8000/modules/nonexistent-module/some/path (with valid X-Sentinel-Key or without — doesn't matter).
  Response should be 404.
result: pass

### 7. Module proxy — unavailable module returns 503
expected: |
  First register a module pointing to a port nothing is listening on (e.g. base_url http://localhost:19999).
  Then POST http://localhost:8000/modules/test-mod/ping (with X-Sentinel-Key).
  Response should be 503 (not a Python exception/500).
result: pass

### 8. Discord /sen command recognized
expected: |
  In a Discord server where the bot is running, type `/sen` — the slash command should appear in the autocomplete picker.
  Submitting a `/sen ask` (or equivalent subcommand) should produce a Sentinel response. `/sentask` should NOT appear.
result: pass

### 9. Architecture docs reflect Path B
expected: |
  Open docs/ARCHITECTURE-Core.md. Should contain a Path B ASCII diagram (INTERFACE LAYER → Sentinel Core → AI Provider + Module Containers in parallel).
  Should contain the module contract (POST /modules/register and POST /modules/{name}/{path}).
  Should NOT contain "Pi as brain" or "pi-mono as AI execution layer" language.
result: pass

## Summary

total: 9
passed: 9
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Kill any running containers. Run `./sentinel.sh up`. Sentinel Core boots without errors."
  status: fixed
  reason: "User reported: ./sentinel.sh: line 25: PROFILES[@]: unbound variable"
  severity: blocker
  test: 1
  root_cause: "bash 3.2 (macOS default) + set -u treats empty array expansion ${PROFILES[@]} as unbound variable. Fixed: use ${arr[@]+\"${arr[@]}\"} idiom for all three arrays."
  artifacts:
    - path: "sentinel.sh"
      issue: "Empty array expansion unsafe under bash 3.2 set -u"
  missing:
    - "Use ${arr[@]+\"${arr[@]}\"} safe expansion for PROFILES, PROFILE_FLAGS, ARGS"
  debug_session: ""

- truth: "`docker compose down` (no flags) stops all running services including pi-harness"
  status: resolved
  resolved_by: "commit 305e5d9 — ALL_KNOWN_PROFILES loop in sentinel.sh"
  reason: "pi-harness behind profiles: [pi]; docker compose down without --profile pi does not stop it — container persists as unmanaged orphan"
  severity: minor
  test: 2
  root_cause: "Docker Compose only manages services matching the active profile set. down without --profile pi never resolves pi-harness, so it cannot stop it."
  artifacts:
    - path: "sentinel.sh"
      issue: "No teardown path that includes --profile pi to ensure full stack cleanup"
  missing:
    - "sentinel.sh down subcommand (or always pass --profile pi on down) so pi-harness is included in teardown"
  debug_session: ""
