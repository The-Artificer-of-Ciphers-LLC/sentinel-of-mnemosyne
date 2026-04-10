---
status: complete
phase: 01-core-loop
source:
  - 01-01-SUMMARY.md
  - 01-02-SUMMARY.md
  - 01-03-SUMMARY.md
started: "2026-04-10T00:00:00Z"
updated: "2026-04-10T00:00:00Z"
---

## Current Test

<!-- OVERWRITE each test - shows where we are -->

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running containers. Run `docker compose up --build` from scratch. Both sentinel-core and pi-harness containers start without errors, stay up, and a `curl http://localhost:8000/health` returns `{"status":"ok"}`.
result: pass

### 2. Pi Harness Health
expected: |
  `curl http://localhost:3000/health` returns JSON with three fields:
  - `status`: "ok"
  - `piAlive`: true (pi subprocess is running)
  - `restarts`: a number (0 on clean start, may be higher if pi respawned)
result: pass

### 3. Sentinel Core Health
expected: |
  `curl http://localhost:8000/health` returns `{"status":"ok"}` with HTTP 200.
  No auth header required — health endpoint is public.
result: pass

### 4. End-to-End Message (AI Response)
expected: |
  ```
  curl -s -X POST http://localhost:8000/message \
    -H "Content-Type: application/json" \
    -H "X-Sentinel-Key: <your-key-from-.env>" \
    -d '{"content": "say hello in exactly three words", "user_id": "test"}' \
    --max-time 210
  ```
  Returns HTTP 200 with JSON body containing `content` (AI text) and `model`
  (the model name from .env). Response may take 30-180s for large local models.
result: pass

### 5. Token Guard — Oversized Message Rejected
expected: |
  ```
  curl -s -X POST http://localhost:8000/message \
    -H "Content-Type: application/json" \
    -H "X-Sentinel-Key: <your-key-from-.env>" \
    -d '{"content": "'"$(python3 -c "print('word ' * 15000)")"'", "user_id": "test"}'
  ```
  Returns HTTP 422 with a detail message indicating the message exceeds the token limit.
  (The 75,000-word message will always exceed any context window.)
result: pass
note: Pydantic max_length=32000 fired before token guard (75k chars > 32k limit). 422 returned correctly — layered defense working as designed.

### 6. Startup Fails Without SENTINEL_API_KEY
expected: |
  Temporarily remove or comment out SENTINEL_API_KEY from .env, then run
  `docker compose up sentinel-core`. The sentinel-core container should exit
  immediately (exit code 1) with a pydantic ValidationError in the logs about
  a missing required field. Pi-harness is unaffected.
  Restore SENTINEL_API_KEY before continuing.
result: pass

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
