---
phase: 27-architecture-pivot
plan: "08"
subsystem: sentinel-core/modules
tags: [proxy, auth, x-sentinel-key, tdd, gap-closure]
dependency_graph:
  requires: [27-03]
  provides: [module-proxy-auth-forwarding]
  affects: [sentinel-core/app/routes/modules.py, sentinel-core/tests/test_modules.py]
tech_stack:
  added: []
  patterns: [TDD red-green, header forwarding, mock call_args inspection]
key_files:
  modified:
    - sentinel-core/app/routes/modules.py
    - sentinel-core/tests/test_modules.py
decisions:
  - Forward X-Sentinel-Key verbatim from caller to module (same shared secret, per ARCHITECTURE-Core.md §3.4)
metrics:
  duration: "114 seconds"
  completed: "2026-04-20"
  tasks_completed: 1
  files_changed: 2
---

# Phase 27 Plan 08: Proxy Auth Header Forwarding Summary

**One-liner:** X-Sentinel-Key forwarded verbatim from caller to module containers in proxy_module, eliminating silent 503s from modules that enforce auth.

## What Was Built

The `proxy_module` handler in `sentinel-core/app/routes/modules.py` was not forwarding the `X-Sentinel-Key` header to downstream module containers. A stale comment stated this was intentional ("modules are trusted by virtue of being on the internal network"). This contradicted ARCHITECTURE-Core.md §3.4, which specifies all modules receive `SENTINEL_API_KEY`. The practical consequence was silent 503s: any module that correctly enforced auth received a 401 from sentinel-core's headerless proxy call.

The fix: extract the caller's `X-Sentinel-Key` from `request.headers` and include it in the outbound `httpx.post()` headers dict. The stale comment was removed.

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (test) | a9cfb4f | PASS — test failed with `AssertionError: X-Sentinel-Key not forwarded to module. Got headers: {'Content-Type': 'application/json'}` |
| GREEN (fix) | 2a6ffb2 | PASS — all 5 tests pass |
| REFACTOR | n/a | No refactor needed |

## Task Commits

| Task | Commit | Files | Description |
|------|--------|-------|-------------|
| RED: add failing assertion | a9cfb4f | tests/test_modules.py | Inspect call_args on mock http_client.post, assert X-Sentinel-Key present |
| GREEN: fix proxy_module | 2a6ffb2 | app/routes/modules.py | Forward X-Sentinel-Key, remove stale comment |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Infra Note (not a deviation)

The project venv had a stripped uv-vendored setuptools (82.0.1) that omitted `setuptools.backends`, making `uv run pytest` and `uv pip install -e .` fail. Workaround: run pytest directly via `.venv/bin/pytest` with `PYTHONPATH=.`, and install missing runtime deps (`litellm`, `tenacity`, `anthropic`, `tiktoken`) with `uv pip install` directly. This is a pre-existing environment issue, not caused by this plan.

## Verification Results

```
5 passed in 2.24s
tests/test_modules.py::test_register_module PASSED
tests/test_modules.py::test_proxy_module PASSED
tests/test_modules.py::test_proxy_module_unavailable PASSED
tests/test_modules.py::test_proxy_unknown_module PASSED
tests/test_modules.py::test_register_requires_auth PASSED
```

Acceptance criteria:
- `grep '"X-Sentinel-Key": sentinel_key' modules.py` — 1 match
- `grep 'intentionally not forwarded' modules.py` — 0 matches
- `grep 'X-Sentinel-Key.*forwarded_headers' test_modules.py` — 1 match
- `grep 'sentinel_key = request.headers.get' modules.py` — 1 match
- All 5 tests pass

## Known Stubs

None.

## Threat Flags

No new threat surface introduced. The threat model in the plan (T-27-08-01, T-27-08-02) covers the accepted risk of forwarding the shared secret to modules on the internal Docker network.

## Self-Check: PASSED

- sentinel-core/app/routes/modules.py — exists, contains fix
- sentinel-core/tests/test_modules.py — exists, contains assertion
- RED commit a9cfb4f — present in git log
- GREEN commit 2a6ffb2 — present in git log
