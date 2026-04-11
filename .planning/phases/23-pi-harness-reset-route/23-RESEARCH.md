# Phase 23: Pi Harness /reset Route — Research

**Researched:** 2026-04-11
**Domain:** Node.js / TypeScript — Fastify routing, vitest module mocking, Python env var config
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: Add sendReset() to pi-adapter.ts**
`bridge.ts` cannot access `piProcess` directly — it is private to `pi-adapter.ts`, and the adapter boundary is intentional. Add a new exported function:

```typescript
export function sendReset(): void {
  if (!piProcess || !piProcess.stdin) return;
  piProcess.stdin.write(JSON.stringify({ type: 'new_session' }) + '\n');
}
```

Fire-and-forget: write `{"type":"new_session"}` to Pi stdin and return immediately. No acknowledgement expected.

**D-02: Add POST /reset route to bridge.ts**
Import `sendReset` alongside existing imports, add the route:

```typescript
import { spawnPi, sendPrompt, getPiHealth, sendReset } from './pi-adapter';

fastify.post('/reset', async (_request, reply) => {
  sendReset();
  return reply.send({ status: 'ok' });
});
```

Returns HTTP 200 with `{ status: 'ok' }` on every call — best-effort even if Pi process is not alive.

**D-03: Verify pi_adapter.py reset_session() — no changes needed**
`pi_adapter.py`'s `reset_session()` already calls `POST /reset` at the correct URL with `timeout=5.0`. Verification only.

**D-04: Restore configurable prompt timeout via PI_TIMEOUT_S**
`send_prompt()` in `pi_adapter.py` has hardcoded `timeout=190.0`. Make configurable:

```python
import os
PI_TIMEOUT_S = float(os.getenv("PI_TIMEOUT_S", "190"))
```

Scope: prompt timeout only. The `send_messages()` 30s and `reset_session()` 5s timeouts stay hardcoded.

**D-05: Add vitest test for /reset route**
- vitest as devDependency with `^2.0.0` constraint
- Test file: `pi-harness/src/bridge.test.ts`
- Mock `sendReset` at module level using `vi.mock()`
- Test assertions: POST /reset returns 200, body is `{ status: 'ok' }`, `sendReset()` called once

### Claude's Discretion

- Exact vitest version pin (within ^2.x)
- Whether to add a `vitest.config.ts` or use zero-config defaults
- Any TypeScript path aliases needed for the test file

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-07 | Docker Compose `include` directive pattern established in base compose — no module or interface uses `-f` flag stacking | This phase completes CORE-07 (PARTIAL → full) by fixing the Pi session reset mechanism that was the remaining gap. The /reset route is the missing runtime piece; compose include pattern itself was established in Phase 1. |
</phase_requirements>

---

## Summary

Phase 23 delivers four targeted changes across two files (pi-adapter.ts, bridge.ts) and one Python file (pi_adapter.py), plus one vitest test. The scope is narrow and well-bounded. All the patterns needed already exist in the codebase — `sendReset()` follows the exact same stdin.write pattern as `sendPrompt()`.

The most significant implementation decision the planner must resolve is the **testability architecture for bridge.ts**. The current `bridge.ts` is a self-contained executable — the `start()` function runs at module load, calling `spawnPi()` and `app.listen()`. Fastify's standard testing pattern uses `app.inject()`, which requires the `app` instance to be importable. The CONTEXT.md does not explicitly specify whether bridge.ts needs refactoring to export `app`, or whether the test should use actual HTTP calls against a listening server. This is a design gap the planner must resolve.

The vitest version constraint (^2.x from CONTEXT.md D-05) requires pinning to vitest 2.1.9, the latest in the v2 series. The current npm `latest` tag is 4.1.4, but the user explicitly chose `^2.0.0`. Vitest 2.x supports `vi.mock()` hoisting, TypeScript via its bundler transform, and `@types/node` ≥20.

**Primary recommendation:** Add a `buildApp()` exported function to bridge.ts (or a separate `app.ts`) that creates and registers all routes but does not call `app.listen()`. The test imports `buildApp()` and uses `app.inject()`. This is the canonical Fastify testing pattern and avoids port conflicts.

---

## Standard Stack

### Core (already in package.json)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastify | 5.8.4 | HTTP server | Already installed — CONTEXT.md locked |
| typescript | ^5.4.5 | Type checking | Already installed |
| @types/node | ^22.0.0 | Node type defs | Already installed |

### To Add
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| vitest | 2.1.9 | Test runner + mock framework | CONTEXT.md D-05: ^2.0.0 constraint; 2.1.9 is latest in v2 series [VERIFIED: npm registry] |

**Version verification:**
```
vitest latest: 4.1.4 (dist-tags.latest)
vitest 2.x latest: 2.1.9 (last in v2 series)
```
[VERIFIED: npm view vitest@2 version, 2026-04-11]

The CONTEXT.md specifies `"vitest": "^2.0.0"` — use 2.1.9 as the pin point. The `^` range will resolve to 2.x.

**Installation:**
```bash
cd pi-harness && npm install --save-dev vitest@2.1.9
```

---

## Architecture Patterns

### Current bridge.ts Structure (Problem)

`bridge.ts` is a self-contained executable. At module evaluation time:
1. `const app = Fastify(...)` — creates instance
2. `app.post(...)`, `app.get(...)` — registers routes
3. `start()` is called — spawns Pi subprocess + calls `app.listen()`

This means **importing `bridge.ts` in a test would immediately attempt `spawnPi()` and `app.listen()` on port 3000**. Even with `vi.mock('./pi-adapter')` hoisted (making `spawnPi()` a no-op), `app.listen()` would still bind the port.

### Recommended: Export buildApp() Pattern

The canonical Fastify testing pattern is to separate app construction from app startup. Two valid approaches:

**Option A: Export `app` and guard `start()` (minimal diff)**

Add to bridge.ts:
```typescript
// Export for testing
export { app };

// Guard start() so it doesn't run during test import
if (process.env.NODE_ENV !== 'test') {
  start();
}
```
Test imports `app` directly and uses `app.inject()`.

**Option B: Extract buildApp() function (cleaner, more idiomatic)**

```typescript
// bridge.ts
export function buildApp(): FastifyInstance {
  const fastify = Fastify({ logger: false }); // disable logger in tests
  // register routes here
  return fastify;
}

// Guard: only start() when run as main
if (require.main === module) {
  start();
}
```

`require.main === module` is the CommonJS equivalent of "is this the entry point?" This works because bridge.ts is run via `node --experimental-strip-types src/bridge.ts` (not imported).

**Option A is the minimal diff.** Option B is cleaner. Either is valid — Claude's discretion (CONTEXT.md).

### Fastify app.inject() Pattern (Verified)

[CITED: https://fastify.dev/docs/v5.3.x/Guides/Testing/]

```typescript
import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';
import { buildApp } from './bridge'; // or import { app }

vi.mock('./pi-adapter', () => ({
  spawnPi: vi.fn(),
  sendPrompt: vi.fn(),
  getPiHealth: vi.fn(() => ({ alive: true, restarts: 0 })),
  sendReset: vi.fn(),
}));

describe('POST /reset', () => {
  let fastify: ReturnType<typeof buildApp>;

  beforeAll(async () => {
    fastify = buildApp();
    await fastify.ready();
  });

  afterAll(async () => {
    await fastify.close();
  });

  it('returns 200 with { status: ok }', async () => {
    const response = await fastify.inject({
      method: 'POST',
      url: '/reset',
    });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ status: 'ok' });
  });
});
```

`app.inject()` does not bind a port — it simulates HTTP in-process. [CITED: Fastify v5 testing docs]

### vi.mock() Hoisting

`vi.mock('./pi-adapter', factory)` is hoisted above all imports by vitest's transform layer. This ensures the mock is in place before any module that imports from `./pi-adapter` loads. [CITED: https://vitest.dev/guide/mocking]

The factory function must return an object matching all named exports from `pi-adapter.ts`:
- `spawnPi: vi.fn()`
- `sendPrompt: vi.fn()`
- `getPiHealth: vi.fn(() => ({ alive: true, restarts: 0 }))`
- `sendReset: vi.fn()`

### Anti-Patterns to Avoid

- **Do not call `app.listen()` in tests** — binds port, causes flakiness and CI conflicts
- **Do not use readline in pi-adapter.ts** — existing CLAUDE.md prohibition; `sendReset()` only writes, doesn't read, so this is not an issue for this phase
- **Do not mock at the wrong level** — mock `./pi-adapter` (the module bridge.ts imports), not the internal `piProcess` variable

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP test injection | Manual fetch to localhost | `fastify.inject()` | No port binding, no network, no race conditions |
| Module mock isolation | Monkey-patching exports | `vi.mock('./pi-adapter')` with factory | Hoisted, survives module cache, works with ESM and CJS |
| TypeScript transform in tests | ts-node, tsc compile step | vitest's built-in bundler transform | Zero config for TypeScript; no separate compile step needed |

---

## Common Pitfalls

### Pitfall 1: bridge.ts not exporting app / start() runs at import

**What goes wrong:** Test imports bridge.ts, `start()` runs, `app.listen()` binds port 3000, `spawnPi()` attempts to spawn the Pi subprocess (even if mocked, `app.listen()` still runs).

**Why it happens:** bridge.ts is structured as an executable, not a module. `start()` is called unconditionally at the bottom.

**How to avoid:** Use `require.main === module` guard, or `process.env.NODE_ENV !== 'test'` guard, or move `start()` call to a separate entrypoint file.

**Warning signs:** Test hangs on `app.listen()`, or "address already in use" errors in CI.

### Pitfall 2: vitest ^2 vs ^4 version confusion

**What goes wrong:** `npm install vitest` without version pin installs 4.1.4 (current latest), which is outside the `^2.0.0` range specified in D-05.

**Why it happens:** CONTEXT.md specifies `^2.0.0` but npm default installs `latest`.

**How to avoid:** Explicitly install `vitest@2.1.9` (latest v2). The package.json entry should be `"vitest": "^2.1.9"` or `"vitest": "^2.0.0"` (both resolve to 2.1.9 until a v2.2.0 appears, which is not expected given v3+ is current stable).

### Pitfall 3: vitest config needed for CommonJS output target

**What goes wrong:** tsconfig.json has `"module": "commonjs"`. Vitest uses its own bundler (Vite under the hood) and handles TypeScript natively — the tsconfig `module` setting does not affect vitest's transform. However, if a `vitest.config.ts` is needed, it should NOT inherit the CJS tsconfig without care.

**Why it happens:** Confusion between tsc output (CommonJS for the `dist/` build) and vitest's internal bundler (ESM-native).

**How to avoid:** Vitest 2.x works zero-config for TypeScript with no `vitest.config.ts` needed. If a config file is added, use `defineConfig` from `vitest/config` — not from `vite`.

**Warning signs:** Import errors like "Cannot use import statement in a module" or "Unexpected token 'export'".

### Pitfall 4: vi.mock factory missing exports causes runtime errors

**What goes wrong:** `vi.mock('./pi-adapter', () => ({ sendReset: vi.fn() }))` — omitting `spawnPi`, `sendPrompt`, `getPiHealth` causes bridge.ts import to fail because the destructured imports resolve to `undefined`.

**Why it happens:** vi.mock factory completely replaces the module; any export not in the factory is undefined.

**How to avoid:** The mock factory must include ALL named exports that bridge.ts imports: `spawnPi`, `sendPrompt`, `getPiHealth`, `sendReset`.

### Pitfall 5: PI_TIMEOUT_S parsed at module load, not per-call

**What goes wrong:** If PI_TIMEOUT_S is set as `PI_TIMEOUT_S = float(os.getenv("PI_TIMEOUT_S", "190"))` at module level, changing the env var at runtime has no effect. This is fine for Docker Compose injection but matters for tests.

**Why it happens:** Module-level evaluation runs once at import time.

**How to avoid:** Module-level parsing is the correct approach for env var configuration — it fails fast at startup (not silently mid-call) and is consistent with how `PI_MODEL` is read in `pi-adapter.ts`. Tests that need different timeouts should set the env var before importing the module.

---

## Code Examples

### sendReset() in pi-adapter.ts

```typescript
// Follows exact pattern of existing piProcess.stdin.write() in sendPrompt()
export function sendReset(): void {
  if (!piProcess || !piProcess.stdin) return;
  piProcess.stdin.write(JSON.stringify({ type: 'new_session' }) + '\n');
}
```

[VERIFIED: pattern matches existing sendPrompt() in pi-adapter.ts line 148]

### POST /reset route in bridge.ts

```typescript
// Add sendReset to import
import { spawnPi, sendPrompt, getPiHealth, sendReset } from './pi-adapter';

// New route — place after /health, before start()
app.post('/reset', async (_request, reply) => {
  sendReset();
  return reply.send({ status: 'ok' });
});
```

[VERIFIED: matches Fastify route pattern in bridge.ts lines 38–68 and 70–77]

### PI_TIMEOUT_S in pi_adapter.py

```python
import os

PI_TIMEOUT_S = float(os.getenv("PI_TIMEOUT_S", "190"))

async def send_prompt(self, message: str) -> str:
    resp = await self._client.post(
        f"{self._harness_url}/prompt",
        json={"message": message},
        timeout=PI_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()["content"]
```

[VERIFIED: existing send_prompt() timeout is 190.0 at line 27 of pi_adapter.py]

### Complete bridge.test.ts

```typescript
// pi-harness/src/bridge.test.ts
import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';

vi.mock('./pi-adapter', () => ({
  spawnPi: vi.fn(),
  sendPrompt: vi.fn(),
  getPiHealth: vi.fn(() => ({ alive: true, restarts: 0 })),
  sendReset: vi.fn(),
}));

// Import AFTER vi.mock() so the mock is hoisted and in place
import { buildApp } from './bridge';
import { sendReset } from './pi-adapter';

describe('POST /reset', () => {
  let app: ReturnType<typeof buildApp>;

  beforeAll(async () => {
    app = buildApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  it('returns 200 with { status: ok }', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/reset',
    });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ status: 'ok' });
  });

  it('calls sendReset() once', async () => {
    vi.clearAllMocks();
    await app.inject({ method: 'POST', url: '/reset' });
    expect(sendReset).toHaveBeenCalledOnce();
  });
});
```

Note: This requires bridge.ts to export `buildApp()`. If the planner chooses the `export { app }` + `process.env.NODE_ENV !== 'test'` guard instead, replace `buildApp()` with the imported `app` directly.

### package.json additions

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "devDependencies": {
    "vitest": "^2.1.9"
  }
}
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | vitest, pi-harness | ✓ | v24.14.0 | — |
| npm | package install | ✓ | (bundled with Node 24) | — |
| vitest | test suite | ✗ (not yet installed) | — | Install via npm in Wave 0 |

[VERIFIED: `node --version` → v24.14.0, 2026-04-11]

**Missing dependencies with no fallback:** None.

**Missing dependencies requiring install:** vitest must be installed as dev dep in Wave 0.

Note: Node 24.14.0 is installed on this machine (newer than the v22 LTS constraint in CLAUDE.md). The pi-harness Docker container still uses `node:22-alpine` per CLAUDE.md — this is correct. Tests run on the host machine with Node 24, which is fully compatible with vitest 2.x and all TypeScript features used.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | vitest 2.1.9 |
| Config file | None (zero-config; or minimal vitest.config.ts if needed) |
| Quick run command | `cd pi-harness && npm test` |
| Full suite command | `cd pi-harness && npm test` (single test file) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CORE-07 (part) | POST /reset returns 200 + `{ status: 'ok' }` | integration (inject) | `cd pi-harness && npm test` | ❌ Wave 0 |
| CORE-07 (part) | sendReset() called on each POST /reset | unit (mock verify) | `cd pi-harness && npm test` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd pi-harness && npm test`
- **Per wave merge:** `cd pi-harness && npm test`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `pi-harness/src/bridge.test.ts` — covers CORE-07 integration test
- [ ] vitest install: `cd pi-harness && npm install --save-dev vitest@2.1.9`
- [ ] bridge.ts refactor to export `buildApp()` or `app` (required for `app.inject()`)

---

## Security Domain

> No new authentication, session management, or cryptography introduced. The `/reset` route is internal to the stack — it is only callable from within the same container network (pi_adapter.py → bridge.ts). No external exposure.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Route is internal, same-network only |
| V3 Session Management | No | Route resets Pi session, not HTTP session |
| V4 Access Control | No | Same-network access only; X-Sentinel-Key is on Core, not Pi harness |
| V5 Input Validation | No | No request body parsed |
| V6 Cryptography | No | No crypto involved |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | bridge.ts needs refactoring to export `app` or `buildApp()` for `app.inject()` to work in tests | Architecture Patterns | If the test instead uses actual HTTP (listen + fetch), the approach works but requires port management; test would be slower and flakier |
| A2 | vitest 2.1.9 is the latest v2.x release and no 2.2.x will appear | Standard Stack | Minor — if 2.2.0 ships, `^2.0.0` would resolve to it; no breaking change expected within ^2 range |
| A3 | `require.main === module` guard works correctly with `node --experimental-strip-types` | Architecture Patterns | If ESM semantics apply (import.meta.main), the guard would fail; but tsconfig module=commonjs means CJS semantics apply |

---

## Open Questions (RESOLVED)

1. **bridge.ts testability: export `app` vs export `buildApp()`**
   - What we know: bridge.ts currently does not export `app`; `app.inject()` requires an importable instance; CONTEXT.md D-05 says test uses `vi.mock()` but doesn't specify how `app` is accessed
   - What's unclear: Whether planner should do the minimal diff (export `app` + NODE_ENV guard) or the idiomatic refactor (extract `buildApp()`)
   - Recommendation: Export `buildApp()` as a named function; it's a 10-line refactor that makes the intent clear. The planner should document this as a required prerequisite task.
   - **RESOLVED:** Plan 23-01 Task 1 Step 4 implements `buildApp()` export pattern. `start()` is guarded with `if (process.env.NODE_ENV !== 'test')`. Test imports `buildApp()` and uses `app.inject()`.

2. **vitest config: zero-config vs vitest.config.ts**
   - What we know: vitest 2.x works zero-config for TypeScript with Node 24; no `tsconfig.json` conflicts expected
   - What's unclear: Whether the CommonJS tsconfig causes any transform issues under vitest
   - Recommendation: Start zero-config. Add `vitest.config.ts` only if the first test run fails with transform errors.
   - **RESOLVED:** Plan 23-01 uses zero-config vitest. No `vitest.config.ts` added — add only if first test run fails with transform errors.

---

## Sources

### Primary (HIGH confidence)
- npm registry — `npm view vitest@2 version` — confirmed 2.1.9 is latest v2 [VERIFIED: 2026-04-11]
- `pi-harness/src/bridge.ts` — confirmed app structure, existing route patterns [VERIFIED: local file]
- `pi-harness/src/pi-adapter.ts` — confirmed existing exports and stdin.write pattern [VERIFIED: local file]
- `sentinel-core/app/clients/pi_adapter.py` — confirmed reset_session() URL and send_prompt() timeout [VERIFIED: local file]
- `pi-harness/package.json` — confirmed existing deps and scripts [VERIFIED: local file]

### Secondary (MEDIUM confidence)
- [Fastify v5 Testing Guide](https://fastify.dev/docs/v5.3.x/Guides/Testing/) — app.inject() pattern
- [Vitest Mocking Guide](https://vitest.dev/guide/mocking) — vi.mock() hoisting behavior
- [Vitest experimental/Node TS config](https://vitest.dev/config/experimental.html) — Node 22+ strip-types support

### Tertiary (LOW confidence)
- DEV.to Fastify+vitest article (June 2024) — general setup patterns; verified against official docs

---

## Metadata

**Confidence breakdown:**
- sendReset() implementation: HIGH — exact pattern exists in codebase
- POST /reset route: HIGH — exact Fastify pattern exists in codebase
- PI_TIMEOUT_S: HIGH — exact os.getenv pattern in existing Python code
- vitest setup: MEDIUM — zero-config may work; CommonJS tsconfig + vitest interaction not fully verified
- bridge.ts testability refactor: MEDIUM — standard Fastify pattern, but bridge.ts guard approach has one [ASSUMED] claim

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (stable APIs; vitest 2.x maintenance-only)
