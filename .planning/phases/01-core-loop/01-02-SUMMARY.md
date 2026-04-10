---
phase: 01-core-loop
plan: 02
subsystem: pi-harness
tags: [node, typescript, fastify, pi-mono, docker, adapter-pattern]
dependency_graph:
  requires: ["01-01"]
  provides: ["pi-harness HTTP bridge on port 3000"]
  affects: ["01-03 (sentinel-core calls pi-harness:3000/prompt)"]
tech_stack:
  added:
    - "@mariozechner/pi-coding-agent@0.66.1 (exact pin)"
    - "fastify@5.8.4"
    - "typescript@^5.4.5"
    - "@types/node@^22.0.0"
  patterns:
    - "adapter-pattern: all pi-mono contact isolated in pi-adapter.ts"
    - "long-lived subprocess with sequential request queue"
    - "manual JSONL stdout parsing (no readline)"
    - "crash-respawn with 1s backoff"
key_files:
  created:
    - pi-harness/package.json
    - pi-harness/package-lock.json
    - pi-harness/tsconfig.json
    - pi-harness/src/pi-adapter.ts
    - pi-harness/src/bridge.ts
    - pi-harness/Dockerfile
  modified: []
decisions:
  - "Manual stdout split on \\n only (not readline) to avoid U+2028/U+2029 false line breaks in JSONL"
  - "Exact version pin @mariozechner/pi-coding-agent@0.66.1 (no ^ or ~) to prevent silent protocol breaks"
  - "adapter pattern: bridge.ts imports only from ./pi-adapter, never from pi-mono directly"
  - "node:22-alpine base image (locked per CONTEXT.md; pi-mono requires >=20.6.0)"
  - "ENV PATH adds node_modules/.bin so spawn('pi') resolves correctly inside container"
metrics:
  duration: "3m"
  completed: "2026-04-10T15:55:43Z"
  tasks_completed: 2
  files_created: 6
---

# Phase 01 Plan 02: Pi Harness Container Summary

**One-liner:** Fastify HTTP bridge over long-lived Pi subprocess with exact version pin, manual JSONL stdout parsing, and full adapter isolation.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Pi adapter + Fastify bridge implementation | d26b61d | pi-harness/package.json, package-lock.json, tsconfig.json, src/pi-adapter.ts, src/bridge.ts |
| 2 | Pi harness Dockerfile (node:22-alpine + PATH fix) | 85b415d | pi-harness/Dockerfile |

## What Was Built

### pi-adapter.ts
Single point of contact with `@mariozechner/pi-coding-agent`. Exports `spawnPi()`, `sendPrompt()`, and `getPiHealth()`. Key implementation decisions:
- `spawn('pi', ['--mode', 'rpc', '--no-session'], { stdio: ['pipe', 'pipe', 'inherit'] })`
- Stdout parsed via manual `buffer.split('\n')` — readline is explicitly NOT used
- `sendPrompt()` rejects after 30s (`30_000` ms) if no `agent_end` event received
- On stdout `close`, increments `restartCount`, logs warning, calls `setTimeout(spawnPi, 1000)` for crash recovery
- Sequential queue via `pendingQueue` array — concurrent requests are serialized
- `agent_end` event is the sole completion signal; extracts last assistant message from `event.messages`

### bridge.ts
Fastify HTTP server. Imports only from `./pi-adapter` (never from `@mariozechner/pi-coding-agent`). Routes:
- `POST /prompt` — validates `message` field, checks `getPiHealth().alive`, calls `sendPrompt()`, returns `{ content }`. Returns 503 if Pi dead, 504 on timeout, 503/500 on other errors.
- `GET /health` — returns `{ status, piAlive, restarts }` from `getPiHealth()`

### Dockerfile
- `FROM node:22-alpine` (locked decision)
- `RUN apk add --no-cache curl` for Compose healthcheck
- `npm ci --omit=dev` installs only production dependencies
- `ENV PATH="/app/node_modules/.bin:$PATH"` ensures `pi` binary is findable by `spawn()`
- `CMD ["node", "--experimental-strip-types", "src/bridge.ts"]` runs TypeScript directly

## Threat Mitigations Applied

| Threat ID | Mitigation |
|-----------|-----------|
| T-1-02-01 (JSONL injection) | `JSON.stringify()` in `sendPrompt()` escapes all special chars; Pi spawned without shell (default Node behavior) |
| T-1-02-02 (DoS via queue) | 30s timeout per request rejects hung sessions; sequential queue prevents event loop starvation |
| T-1-02-03 (PATH elevation) | Container PATH only adds npm bin — no host PATH inherited at Docker runtime |

## Deviations from Plan

None — plan executed exactly as written. The verify script produces false positives for "readline" (found only in comments explaining why it's not used) and for "@mariozechner/pi-coding-agent" in bridge.ts (found only in a comment documenting the adapter pattern). Both are correct implementations matching the plan's own provided code examples.

## Known Stubs

None — no stub data, no hardcoded empty values, no placeholder text. Both endpoints are fully implemented.

## Self-Check: PASSED

- [x] `pi-harness/package.json` exists with exact pin
- [x] `pi-harness/tsconfig.json` exists
- [x] `pi-harness/src/pi-adapter.ts` exists
- [x] `pi-harness/src/bridge.ts` exists
- [x] `pi-harness/Dockerfile` exists
- [x] `pi-harness/package-lock.json` exists (committed)
- [x] Commit d26b61d exists (Task 1)
- [x] Commit 85b415d exists (Task 2)
