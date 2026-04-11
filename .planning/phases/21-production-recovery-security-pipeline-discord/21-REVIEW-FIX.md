---
phase: 21
status: all_fixed
findings_in_scope: 2
fixed: 2
skipped: 0
iteration: 1
fixed_at: 2026-04-11T00:00:00Z
review_path: .planning/phases/21-production-recovery-security-pipeline-discord/21-REVIEW.md
---

# Phase 21: Code Review Fix Report

**Fixed at:** 2026-04-11
**Source review:** `.planning/phases/21-production-recovery-security-pipeline-discord/21-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 2
- Fixed: 2
- Skipped: 0

## Fixed Issues

### HR-01: `filter_input` return value not confirmed to reach AI provider

**Files modified:** `tests/test_injection_filter.py`, `tests/test_output_scanner.py`
**Commit:** b28b859
**Applied fix:**

The route (`app/routes/message.py` lines 146–147) already correctly unpacks `filter_input`'s return tuple and forwards `safe_input` to the AI provider — the code path was sound. What was missing was test coverage confirming this contract.

Added two tests to `test_injection_filter.py`:

- `test_filter_input_sanitized_text_is_forwarded_not_raw` — mirrors the route's exact unpack pattern (`safe_input, was_modified = filt.filter_input(raw_input)`), asserts `safe_input != raw_input` when injection content is present, asserts `[REDACTED]` is present in the forwarded value, and asserts the raw injection phrase is absent from the messages array entry.
- `test_filter_input_clean_text_forwarded_unchanged` — verifies clean input passes through unmodified and the messages array receives the original string.

Also added `test_secret_at_position_beyond_2000_is_caught` to `test_output_scanner.py` as a companion test for HR-02 (see below).

### HR-02: `_classify_with_haiku` excerpt window always sliced from response start

**Files modified:** `app/services/output_scanner.py`
**Commit:** aca5f31
**Applied fix:**

Replaced the hard-coded `excerpt = response[:2000]` with a new `_extract_excerpt` method that:

1. Iterates `_SECRET_PATTERNS` in order and finds the first pattern whose name is in `fired_patterns`.
2. Runs `pat.search(response)` to locate the match position.
3. Returns `response[max(0, m.start()-500) : min(len(response), m.start()+1500)]` — a 2000-char window centered 500 chars before the match start.
4. Falls back to `response[:2000]` if no match is found (defensive, should not occur in practice).

`_classify_with_haiku` now calls `self._extract_excerpt(response, fired_patterns)` instead of the inline slice.

Added regression tests to `test_output_scanner.py`:

- `test_secret_at_position_beyond_2000_is_caught` — builds a 3000-char padding + secret string, asserts the secret appears in the content sent to the Haiku mock, and asserts `is_safe is False` (LEAK verdict).
- `test_extract_excerpt_centers_on_match` — unit test for `_extract_excerpt` directly: 4000-char padding + AWS key, asserts the key is present in the returned excerpt.

## Skipped Issues

None.

---

## Test Suite Results

Run after all fixes were applied:

```
111 passed, 1 warning in 69.08s
```

The 1 warning (`RuntimeWarning: coroutine 'OutputScanner._classify_with_haiku' was never awaited`) is pre-existing from `test_timeout_fails_open` which monkeypatches `asyncio.wait_for` to raise `TimeoutError` before the coroutine is awaited. Not introduced by these changes.

---

_Fixed: 2026-04-11_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
