# Phase 23: Pi Harness /reset Route - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-11
**Phase:** 23-pi-harness-reset-route
**Areas discussed:** pi-adapter.ts export pattern, test framework + mocking approach, timeout scope

---

## pi-adapter.ts Export Pattern

| Option | Description | Selected |
|--------|-------------|----------|
| Add sendReset() to pi-adapter.ts | Exports a new sendReset() from pi-adapter.ts; bridge.ts calls it. Keeps all pi-mono contact isolated in the adapter. | ✓ |
| Export piProcess directly | Export piProcess so bridge.ts can call piProcess.stdin.write() itself. Simpler but breaks the adapter boundary. | |
| Move reset logic into bridge.ts entirely | Manage a separate stdin reference in bridge.ts. Duplicates subprocess management. | |

**User's choice:** Add sendReset() to pi-adapter.ts
**Notes:** Adapter boundary is explicitly documented in pi-adapter.ts's own comment header — must not break it.

| Option | Description | Selected |
|--------|-------------|----------|
| Fire-and-forget | Write new_session to stdin and return immediately. Matches Pi RPC protocol design. | ✓ |
| Wait for agent_start event | Block until Pi emits agent_start to confirm reset. More certainty but adds latency. | |

**User's choice:** Fire-and-forget

---

## Test Approach

| Option | Description | Selected |
|--------|-------------|----------|
| Add vitest | Fast, TypeScript-native, zero-config. Add test script to package.json. | ✓ |
| Add jest + ts-jest | More familiar but heavier config for a single test. | |
| Skip tests | Violates roadmap success criterion 5. | |

**User's choice:** Add vitest

| Option | Description | Selected |
|--------|-------------|----------|
| Mock sendReset() at module level | vi.mock() stubs the pi-adapter module; no Pi process needed in CI. | ✓ |
| Spin up real Fastify with stubbed adapter | More realistic but more setup for a single route. | |
| Test only the route handler | Extract as pure function. Least realistic. | |

**User's choice:** Mock sendReset() at module level via vi.mock()

---

## Timeout Scope (D-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Prompt timeout only via PI_TIMEOUT_S | Make send_prompt()'s 190s configurable; 30s and 5s stay fixed. | ✓ |
| All timeouts via single constructor param | Single timeout_s doesn't make sense across prompt/messages/reset. | |
| Separate env vars per timeout | Maximum flexibility, excessive config for a personal tool. | |

**User's choice:** PI_TIMEOUT_S for send_prompt() only, default 190

---

## Claude's Discretion

- Exact vitest version pin within ^2.x
- Whether to add vitest.config.ts or use zero-config defaults
- TypeScript path aliases for the test file if needed

## Deferred Ideas

None.
