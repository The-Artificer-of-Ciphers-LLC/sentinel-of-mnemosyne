---
phase: 09
slug: tech-debt-cleanup
status: ready
created: 2026-04-11
---

# Phase 09: Tech Debt Cleanup — Context

**Gathered:** 2026-04-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix five known defects identified during Phases 6–7 and the milestone audit. All fixes are in existing files — no new features, no new architecture. One documentation artifact (Phase 4 VALIDATION.md) created via full nyquist audit.

</domain>

<decisions>
## Implementation Decisions

### D-01: Bare except in message.py

**Decision:** Narrow `except Exception:` at `message.py:149` to httpx-specific exceptions only.

Catch: `httpx.TimeoutException`, `httpx.ConnectError`, `httpx.RequestError` (or the common base `httpx.HTTPError`).

Any non-httpx exception (including `KeyError` from a malformed Pi response missing the `content` key) must NOT fall through to the AI provider silently. Let it surface as a 502 with the actual exception type logged.

**Rationale:** Current behavior masks Pi protocol errors as "Pi unavailable." A `KeyError` on a bad Pi response is a protocol bug, not a connectivity failure. The two failure modes need distinct handling.

### D-02: Fix stale test assertion

**Decision:** Update `test_send_messages_hard_timeout_set` in `sentinel-core/tests/test_pi_adapter.py:82` to assert `timeout == 90.0` (not `30.0`).

The timeout was changed to 90s in commit `5e224ac` (`fix(pi-harness): increase generation timeout`). The test was never updated. This is the only change needed — the implementation is correct.

### D-03: Remove dead `send_prompt()` method

**Decision:** Delete `send_prompt()` from `sentinel-core/app/clients/pi_adapter.py:27–46`. It has zero production callers. `send_messages()` superseded it in Phase 2.

Verify no callers exist before deleting: `grep -rn "send_prompt" sentinel-core/`.

### D-04: Extend DISCLOSURE detection in pentest agent

**Decision:** Add the `{"name": ..., "arguments": ...}` JSON tool schema format to `DISCLOSURE_RED_FLAGS` in `security/pentest-agent/pentest.py`.

Current flags catch the `read {"path"...}` format. The new format appearing in production is:
```
{"name": "read", "arguments": {"path": "..."}}
{"name": "bash", "arguments": {"command": "..."}}
{"name": "edit", "arguments": {"path": "..."}}
{"name": "write", "arguments": {"path": "..."}}
```

Add these four patterns to `DISCLOSURE_RED_FLAGS`. Also add a new LLM07b probe specifically targeting this format.

### D-05: Phase 4 VALIDATION.md — full nyquist audit

**Decision:** Create `sentinel-core/.planning/phases/04-ai-provider-multi-provider-support-retry-logic-fallback/04-VALIDATION.md` via a full nyquist audit.

**Scope:** Map all PROV-01..05 requirements to their test implementations. Verify each test assertion is present and passing in the codebase. Document manual verification for anything without automated coverage.

**Not documentation-only** — unlike Phase 08 retroactive work, this is a full audit: read the actual test files, verify assertions exist, map each requirement to its test function(s).

Flip `nyquist_compliant: true` only after all PROV-01..05 are mapped with evidence.

### Claude's Discretion

- Whether to use `httpx.HTTPError` (base class) or enumerate specific httpx exceptions for D-01 — choose whichever is idiomatic per the existing httpx usage in the codebase
- Exact YAML structure of the Phase 4 VALIDATION.md (follow the pattern from `01-VALIDATION.md` and `03-VALIDATION.md`)

</decisions>

<specifics>
## Specific Ideas

- D-01 fix must log the actual exception type so Pi protocol errors are visible: `logger.error(f"Pi error: {type(exc).__name__}: {exc}")`
- D-04: the new disclosure format appeared in a real production exchange — this is confirmed not hypothetical

</specifics>

<canonical_refs>
## Canonical References

### Files being modified
- `sentinel-core/app/routes/message.py` — D-01 (bare except at line 149)
- `sentinel-core/tests/test_pi_adapter.py` — D-02 (timeout assertion at line 82)
- `sentinel-core/app/clients/pi_adapter.py` — D-03 (dead send_prompt at lines 27–46)
- `security/pentest-agent/pentest.py` — D-04 (DISCLOSURE_RED_FLAGS)

### Phase 4 nyquist audit source files
- `.planning/phases/04-ai-provider-multi-provider-support-retry-logic-fallback/04-VERIFICATION.md` — ground truth for what was verified
- `.planning/REQUIREMENTS.md` — PROV-01..05 requirement text
- `sentinel-core/tests/test_provider_router.py` — PROV-05 test coverage
- `sentinel-core/tests/test_pi_adapter.py` — PROV-03 test coverage

### Patterns to follow
- `.planning/phases/01-core-loop/01-VALIDATION.md` — Nyquist matrix format (updated in Phase 08)
- `.planning/phases/03-interfaces/03-VALIDATION.md` — Nyquist matrix format with manual verification entries

</canonical_refs>

<code_context>
## Existing Code Insights

### Integration Points
- `message.py:149` — `except Exception:` block immediately after `await pi_adapter.send_messages(messages)` call; `content = None` triggers AI provider fallback
- `pi_adapter.py:48` — `send_messages()` is the production method; uses `self._timeout_s` (90.0) set at line 21
- `pentest.py:89–103` — `DISCLOSURE_RED_FLAGS` list; `score_response()` checks this before `COMPLIANCE_RED_FLAGS`

### Established Patterns
- httpx exception hierarchy: `httpx.TimeoutException`, `httpx.ConnectError` are both subclasses of `httpx.RequestError`; catching `httpx.RequestError` covers both
- Test timeout assertion pattern: `call_args = http_client.post.call_args; call_kwargs = call_args.kwargs`

</code_context>

<deferred>
## Deferred Ideas

- PROV-05 `.env.example` documentation gap — add `AI_FALLBACK_PROVIDER` entry to `.env.example` (low-risk, include in this phase if planner has capacity)
- `SENTINEL_THREAD_IDS` in-memory ephemeral set (thread continuity lost on bot restart) — belongs in Phase 10 Discord improvements

</deferred>

---

*Phase: 09-tech-debt-cleanup*
*Context gathered: 2026-04-11*
