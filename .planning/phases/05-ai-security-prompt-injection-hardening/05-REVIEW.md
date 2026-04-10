---
phase: 05-ai-security-prompt-injection-hardening
reviewed: 2026-04-10T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - sentinel-core/app/services/injection_filter.py
  - sentinel-core/app/services/output_scanner.py
  - sentinel-core/tests/test_injection_filter.py
  - sentinel-core/tests/test_output_scanner.py
  - security/owasp-llm-checklist.md
  - sentinel-core/app/main.py
  - sentinel-core/app/routes/message.py
  - sentinel-core/tests/test_message.py
  - sentinel-core/tests/test_auth.py
  - security/garak_config.yaml
  - security/pentest-agent/Dockerfile
  - security/pentest-agent/compose.yml
  - security/pentest-agent/pentest.py
  - docker-compose.yml
findings:
  critical: 1
  warning: 2
  info: 2
  total: 5
status: issues_found
---

# Phase 05: Code Review Report

**Reviewed:** 2026-04-10T00:00:00Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 5 introduces `InjectionFilter` (SEC-01) and `OutputScanner` (SEC-02) as shared security
services instantiated in the FastAPI lifespan and threaded through the `POST /message` route.
The design is sound: framing wrapper + pattern blocklist for prompt injection, two-stage regex +
Haiku secondary classifier for output leak detection, and a scheduled pen-test agent for ongoing
adversarial validation.

One critical defect is present: the three new classes (`AsyncAnthropic`, `InjectionFilter`,
`OutputScanner`) are instantiated in `main.py` but never imported. The application will raise a
`NameError` at startup and never serve requests. Two warnings follow: a high-false-positive
`fs_path` output scanner pattern and a silent credential failure mode in the pentest agent.

---

## Critical Issues

### CR-01: Missing imports in `main.py` — app fails to start with NameError

**File:** `sentinel-core/app/main.py:147-156`

**Issue:** `AsyncAnthropic`, `InjectionFilter`, and `OutputScanner` are all used inside the
`lifespan` function to instantiate the security services, but none of these names are imported
anywhere in `main.py`. The import block (lines 11-30) contains no reference to them. At startup,
Python raises `NameError: name 'AsyncAnthropic' is not defined` on the first line that touches
them, which prevents the application from serving any request.

The existing tests do not catch this because they mock `app.state.injection_filter` and
`app.state.output_scanner` directly, bypassing the lifespan initialization entirely.

**Fix:**
```python
# Add to main.py import block (after existing imports, before the logging config)
from anthropic import AsyncAnthropic

from app.services.injection_filter import InjectionFilter
from app.services.output_scanner import OutputScanner
```

---

## Warnings

### WR-01: `fs_path` output scanner pattern has significantly higher false-positive risk than all other patterns

**File:** `sentinel-core/app/services/output_scanner.py:29`

**Issue:** The `fs_path` pattern `r"/(?:etc|home|var/run|proc|sys)/\S+"` fires on any response
containing strings like `/etc/hosts`, `/home/user/notes.md`, `/proc/cpuinfo`, or
`/sys/block/sda`. An AI assistant responding to questions about Linux configuration, file
locations, or system administration will routinely produce these paths. Unlike the other patterns
(API key prefixes, AWS key shapes, sentinel-specific env var names), this pattern has no
structural anchor — a 7-character substring match triggers it.

The Haiku secondary classifier is the backstop, but each false positive incurs a Haiku API call
with a 2-second timeout budget. A heavily adversarial test run or a single detailed Linux
sysadmin response could generate multiple spurious classifier calls per message.

**Fix:** Add a minimum length guard and require the path to include a filename component with
an extension or a non-trivial depth, or scope the match more narrowly to paths that include
content that looks like credentials:

```python
# Option A — require the path segment after the anchor to look like a non-trivial resource
("fs_path", re.compile(r"/(?:etc|home|var/run|proc|sys)/\S{5,}")),

# Option B — pair fs_path with a surrounding context keyword (requires MULTILINE or
# a wrapper that checks context)
# e.g., only fire if "passwd", "shadow", "sudoers", "authorized_keys", etc. appear nearby
("fs_path_sensitive", re.compile(
    r"/(?:etc)/(?:passwd|shadow|sudoers|ssh/authorized_keys|ssl/private)\b"
)),
```

Option B (scope to known sensitive filenames) is strongly preferred. It trades recall on
novel paths for near-zero false positives on the paths that actually matter.

---

### WR-02: Pentest agent sends requests with empty API key when `SENTINEL_API_KEY` is unset

**File:** `security/pentest-agent/pentest.py:23`

**Issue:** `SENTINEL_API_KEY` is read with `os.environ.get("SENTINEL_API_KEY", "")`. If the
variable is not set in the container environment, `SENTINEL_API_KEY` is silently an empty
string. Every probe request is then sent with `X-Sentinel-Key: ""`, which the
`APIKeyMiddleware` rejects with HTTP 401. All ten probe results record `HTTP 401` with a
response snippet of the 401 error body, and the report marks them all `PASS` (401 responses
contain no compliance red flags). The pentest run produces a falsely clean report.

The `compose.yml` does pass `SENTINEL_API_KEY` via environment, but if the variable is absent
from the host `.env` or the shell at run time, the empty default is used with no warning.

**Fix:** Add an explicit check at startup and abort with a clear error message rather than
proceeding silently:

```python
# In run_pentest(), before the async with block:
if not SENTINEL_API_KEY:
    logger.error(
        "SENTINEL_API_KEY is not set — pentest agent cannot authenticate to Sentinel Core. "
        "Set the variable in your .env file and re-run."
    )
    sys.exit(2)
```

---

## Info

### IN-01: `test_timeout_fails_open` exercises the wrong exception branch

**File:** `sentinel-core/tests/test_output_scanner.py:80-84`

**Issue:** The test simulates a timeout by setting `side_effect=asyncio.TimeoutError()` on
`messages.create`. In the production code, `asyncio.wait_for` raises `asyncio.TimeoutError`
when the wrapped coroutine exceeds the deadline — but when the coroutine *itself* raises
`asyncio.TimeoutError` before the deadline, `wait_for` propagates it as an `Exception` rather
than as its own timeout signal. The test therefore exercises the `except Exception` branch
(line 94-95) rather than the `except asyncio.TimeoutError` branch (lines 88-93). Both branches
fail open, so the observable behavior is correct, but the `except asyncio.TimeoutError` branch
is not actually covered by any test.

**Fix:** To test the true timeout path, use `asyncio.sleep` in the mock so `wait_for` fires:

```python
async def test_timeout_fails_open(mock_anthropic):
    async def slow_classify(*args, **kwargs):
        await asyncio.sleep(10)  # longer than SECONDARY_TIMEOUT_S=2.0

    mock_anthropic.messages.create = AsyncMock(side_effect=slow_classify)
    scanner = OutputScanner(mock_anthropic)
    is_safe, reason = await scanner.scan("sk-ant-abc123def456ghi789jkl012mno345")
    assert is_safe is True
```

---

### IN-02: Double truncation of response snippets in pentest report

**File:** `security/pentest-agent/pentest.py:103,127`

**Issue:** `snippet` is set to `response_text[:200]` (line 103), then in the report table rows
it is further sliced to `r['snippet'][:80]` (line 127). The 200-char `snippet` is never used
at its full length. The double truncation is harmless but the intermediate 200-char slice adds
no value.

**Fix:** Either truncate once to 80 at assignment or once to 80 in the table row (not both):

```python
# Line 103 — truncate once, at the size you actually use
snippet = response_text[:80].replace("\n", " ")
```

Then remove the `[:80]` in the `rows` f-string at line 127:
```python
f"| {r['category']} | {r['name']} | {r['status']} | {r['verdict']} | {r['snippet']}... |"
```

---

_Reviewed: 2026-04-10T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
