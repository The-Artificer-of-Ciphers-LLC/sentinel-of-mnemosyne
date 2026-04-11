# Quick Task 260411-kdc: Restore reset_session() to pi_adapter.py — Phase 23 SC-3 gap

**Date:** 2026-04-11
**Status:** Complete
**Commit:** 2e91e92

## What was done

Phase 23's VERIFICATION.md had `status: human_needed` because SC-3 ("pi_adapter.py reset_session() confirmed calling correct URL") showed `✗ FAIL`. The user chose Option B: ensure the Python caller exists.

Inspection revealed `reset_session()` was actually defined **twice** in `pi_adapter.py`:

1. **Lines 36–51** (graceful): catches all exceptions, logs a warning, never raises — correct for fire-and-forget reset before each exchange
2. **Lines 76–83** (strict): calls `raise_for_status()`, no exception handling — silently shadowed by Python's method resolution

The duplicate strict definition was removed. The graceful version is retained and active.

## Why graceful is correct

`message.py:161` calls `await pi_adapter.reset_session()` unconditionally before every exchange with no surrounding try/except. If reset fails (harness restarting, slow start), the message must still proceed. The strict version would have propagated `httpx.HTTPStatusError` to the route handler on any non-2xx reset response.

## Files changed

- `sentinel-core/app/clients/pi_adapter.py` — removed duplicate `reset_session()` (lines 76–83)
- `.planning/phases/23-pi-harness-reset-route/23-VERIFICATION.md` — updated to `status: passed`, `score: 5/5`, SC-3 row to ✓ VERIFIED, key link row fixed, spot-check row fixed, gaps section updated

## Test results

- `pytest tests/test_pi_adapter.py`: 6 passed
