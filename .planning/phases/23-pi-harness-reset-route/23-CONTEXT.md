---
phase: 23
slug: pi-harness-reset-route
status: ready
created: 2026-04-11
updated: 2026-04-11
gap_closure: true
gaps_closed: [GAP-04]
audit_source: v0.1-v0.4-MILESTONE-AUDIT.md
---

# Phase 23 Context: Pi Harness /reset Route

## Phase Goal

Add a `POST /reset` route to `bridge.ts` so that `pi_adapter.py`'s reset-after-exchange call succeeds (200) instead of silently returning 404. Without this, the Pi harness accumulates full session history across every exchange, risking LM Studio RAM exhaustion after approximately 5 calls.

---

<domain>
## Phase Boundary

This phase delivers three concrete changes:
1. A new `POST /reset` route in `bridge.ts` that sends a Pi RPC `new_session` message
2. A new `sendReset()` export in `pi-adapter.ts` that encapsulates the RPC write
3. Configurable `PI_TIMEOUT_S` env var in `pi_adapter.py` for the prompt timeout
4. One vitest integration test for the `/reset` route

No changes to how `pi_adapter.py` calls `/reset` — it already calls the right URL. No Pi RPC protocol changes. No LM Studio configuration changes.
</domain>

---

<decisions>
## Implementation Decisions

### D-01: Add sendReset() to pi-adapter.ts (NEW — replaces previous D-01 sketch)

`bridge.ts` cannot access `piProcess` directly — it is private to `pi-adapter.ts`, and the adapter boundary is intentional (all pi-mono contact isolated there per the file's own comment header).

Add a new exported function to `pi-adapter.ts`:

```typescript
export function sendReset(): void {
  if (!piProcess || !piProcess.stdin) return;
  piProcess.stdin.write(JSON.stringify({ type: 'new_session' }) + '\n');
}
```

Fire-and-forget: write `{"type":"new_session"}` to Pi stdin and return immediately. No acknowledgement is expected — this matches the Pi RPC protocol's `new_session` message type.

### D-02: Add POST /reset route to bridge.ts

Import `sendReset` alongside the existing imports, then add the route:

```typescript
import { spawnPi, sendPrompt, getPiHealth, sendReset } from './pi-adapter';

fastify.post('/reset', async (_request, reply) => {
  sendReset();
  return reply.send({ status: 'ok' });
});
```

Returns HTTP 200 with `{ status: 'ok' }` on every call (even if Pi process is not alive — reset is best-effort, same as `pi_adapter.py`'s graceful error swallow).

### D-03: Verify pi_adapter.py reset_session() — no changes needed

`pi_adapter.py`'s `reset_session()` already calls `POST /reset` at the correct URL with `timeout=5.0`. No changes to `pi_adapter.py` reset logic. Verification is confirming the URL construction matches `bridge.ts` port and path.

### D-04: Restore configurable prompt timeout via PI_TIMEOUT_S

`send_prompt()` in `pi_adapter.py` has a hardcoded `timeout=190.0`. Make this configurable:

```python
import os

PI_TIMEOUT_S = float(os.getenv("PI_TIMEOUT_S", "190"))

async def send_prompt(self, message: str) -> str:
    resp = await self._client.post(
        f"{self._harness_url}/prompt",
        json={"message": message},
        timeout=PI_TIMEOUT_S,
    )
    ...
```

Scope: **prompt timeout only**. The `send_messages()` 30s timeout and `reset_session()` 5s timeout stay hardcoded — they are already appropriate fixed values.

The `PI_TIMEOUT_S` default of 190 matches the current hardcoded value (Pi has 180s timeout; 10s margin for large local models).

### D-05: Add vitest test for /reset route

Add vitest as a dev dependency and write one integration test.

**Test approach:** Mock `sendReset` at the module level using `vi.mock()`. This prevents `spawnPi()` from running (no Pi subprocess needed in test). Test only that:
1. `POST /reset` returns HTTP 200
2. Response body is `{ status: 'ok' }`
3. `sendReset()` was called once

**File:** `pi-harness/src/bridge.test.ts`

**package.json additions:**
```json
"scripts": {
  "test": "vitest run"
},
"devDependencies": {
  "vitest": "^2.0.0"
}
```

### Claude's Discretion

- Exact vitest version pin (within ^2.x)
- Whether to add a `vitest.config.ts` or use zero-config defaults
- Any TypeScript path aliases needed for the test file
</decisions>

---

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Pi Harness Implementation
- `pi-harness/src/bridge.ts` — Current Fastify server; add /reset route here
- `pi-harness/src/pi-adapter.ts` — Pi subprocess adapter; add sendReset() export here
- `pi-harness/package.json` — Add vitest dev dependency and test script

### Sentinel Core
- `sentinel-core/app/clients/pi_adapter.py` — Python client; restore PI_TIMEOUT_S for send_prompt()

### Requirements
- `.planning/REQUIREMENTS.md` §CORE-07 — Requirement this phase partially completes (PARTIAL → full)
- `.planning/v0.1-v0.4-MILESTONE-AUDIT.md` §GAP-04 — Source of this gap; describes the /reset 404 and timeout_s removal

### Protocol Reference
- CLAUDE.md §Pi Harness Container — RPC protocol docs, JSONL message types including new_session
</canonical_refs>

---

<code_context>
## Existing Code Insights

### Reusable Assets
- `piProcess.stdin.write(JSON.stringify({...}) + '\n')` — Exact pattern used by `sendPrompt()` in pi-adapter.ts for writing to Pi stdin. sendReset() follows the same pattern.
- `spawnPi()`, `sendPrompt()`, `getPiHealth()` — Existing exports from pi-adapter.ts. sendReset() is the fourth export.
- Fastify route pattern in bridge.ts — async handler, `reply.send({...})` return. The /reset route follows /health's simpler shape (no body parsing, no subprocess health check needed).

### Established Patterns
- All pi-mono contact is isolated in `pi-adapter.ts` — do not break this. bridge.ts only calls exported functions.
- CRITICAL: Manual `\n` splitting in pi-adapter.ts — do NOT use readline. (This is already handled; sendReset() just writes, doesn't read.)
- Python client uses `httpx.AsyncClient` as the HTTP transport — no changes to transport layer.
- `os.getenv()` pattern for env var config in Python code — PI_TIMEOUT_S follows this.

### Integration Points
- `bridge.ts` imports from `./pi-adapter` — add `sendReset` to the import list
- `sentinel-core/app/clients/pi_adapter.py` `send_prompt()` method — add `PI_TIMEOUT_S` read at module level
- Docker Compose env var injection — PI_TIMEOUT_S should be documented as an optional env var (default 190)
</code_context>

---

<specifics>
## Specific Requirements

- `POST /reset` must return exactly `{ status: 'ok' }` with HTTP 200 (this is what pi_adapter.py's reset_session() checks via raise_for_status())
- sendReset() must be a no-op if piProcess is null or stdin is unavailable — same graceful handling as pi_adapter.py's error swallow
- PI_TIMEOUT_S default must be 190 (not 180) — the 10s margin above Pi's internal 180s timeout is deliberate
- vitest mock must prevent spawnPi() from executing — module-level vi.mock() hoisting handles this
</specifics>

---

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.
</deferred>

---

*Phase: 23-pi-harness-reset-route*
*Context gathered: 2026-04-11 (updated)*
