---
status: partial
phase: 28-pf2e-module-skeleton-cors
source: [28-VERIFICATION.md]
started: 2026-04-22T01:23:44Z
updated: 2026-04-22T01:23:44Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. CORS preflight smoke against running server
expected: `curl -X OPTIONS -H "Origin: http://localhost:30000" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: X-Sentinel-Key" -v http://localhost:8000/modules/pathfinder/healthz` returns `access-control-allow-origin: http://localhost:30000` header (not 401)
result: [pending]

### 2. pf2e-module Docker build
expected: `docker build -t pf2e-module modules/pathfinder/` exits 0 — pip installs resolve, image is constructable
result: [pending]

### 3. Full stack startup with --pf2e profile
expected: `./sentinel.sh --pf2e up` starts pf2e-module container; pf2e-module POSTs to `/modules/register`; `GET /modules` returns entry with name "pathfinder"
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
