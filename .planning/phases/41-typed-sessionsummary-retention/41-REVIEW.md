---
phase: 41-typed-sessionsummary-retention
reviewed: 2026-06-12T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - sentinel-core/app/composition.py
  - sentinel-core/app/config.py
  - sentinel-core/app/routes/status.py
  - sentinel-core/app/services/message_processing.py
  - sentinel-core/app/services/recall.py
  - sentinel-core/app/vault.py
  - sentinel-core/tests/fakes/vault.py
  - sentinel-core/tests/test_config.py
  - sentinel-core/tests/test_integration_obsidian_llm.py
  - sentinel-core/tests/test_message.py
  - sentinel-core/tests/test_obsidian_vault.py
  - sentinel-core/tests/test_recall.py
  - sentinel-core/tests/test_status.py
findings:
  critical: 3
  warning: 5
  info: 3
  total: 11
status: issues_found
---

# Phase 41: Code Review Report

**Reviewed:** 2026-06-12
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Phase 41 migrates session memory from raw `dict`/`str` to a typed `SessionSummary`
value object and wires a policy-driven `RetentionPolicy` for hot-tier retention.
The core path — `_parse_session_summary` → `get_recent_sessions` → `_hot_sessions` →
`RecalledContext.sessions` — is well-structured and the defensive parsing contract
is correctly implemented. The `recency_weight` decay curve and the warm-tier carrier
weighting (`_CARRIER_NAMESPACE_PREFIXES` positive allowlist) are solid.

Three blockers were found:

1. The frontmatter body-start calculation in `_parse_session_summary` is off-by-one
   and will silently misparse a large portion of real vault notes by stripping the
   opening `---` from the body text (corrupting `user_msg`/`sentinel_msg` in edge
   cases and shadowing the closing `---` anchor).
2. `FakeVault.get_recent_sessions` ignores `policy.hot_window_days`, silently
   returning sessions that production would exclude — this makes every retention-
   window test that uses FakeVault unable to detect a regression in the window
   filtering branch.
3. The session-body injection in `MessageProcessor.process` accesses `s.body` on
   each `SessionSummary`; if a note was parsed with an empty body (valid per the
   spec) and empty-body guard is never applied, the hot-tier context block emits an
   empty `---`-separator pair that wastes tokens.

Five warnings and three informational items are documented below.

---

## Critical Issues

### CR-01: `_parse_session_summary` body-start calculation is off by one — silently corrupts user_msg/sentinel_msg

**File:** `sentinel-core/app/vault.py:240-241`

**Issue:** The function locates the closing frontmatter delimiter with:
```python
body_start = raw.find("\n---\n", raw.find("---"))
body_text = raw[body_start + 5:].lstrip("\n") if body_start != -1 else raw
```

`raw.find("---")` starts scanning from position 0, so it immediately matches the
**opening** `---` at offset 0 (or 1 if the note has a leading newline). The subsequent
`raw.find("\n---\n", ...)` therefore starts from position 0 (or 1), not from after
the first `---`, so it finds the **second** `\n---\n` which is the closing delimiter
of the frontmatter block — but only by accident, and only when the opening `---`
is at position 0. If the raw body starts with a blank line (common in Obsidian's
REST API responses) or any other whitespace, `raw.find("---")` may return the offset
of the opening block correctly, but `raw.find("\n---\n", that_offset)` will skip to
a `\n---\n` that appears *inside* frontmatter field values if one exists, or will
find the wrong closing delimiter.

More concretely: a note whose frontmatter contains a field whose value contains
`---` (e.g. `timestamp: 2026-06-12T14:00:00+00:00` never does, but a `model: ---`
or a note body that happens to contain `---` as a markdown horizontal rule before
the first section heading) will silently misparse.

The correct approach is to use the existing `split_frontmatter` helper (already
imported in `vault.py` from `app.markdown_frontmatter`) which owns the canonical
frontmatter parsing logic, rather than re-implementing it inline with a fragile
`find()` chain.

**Fix:**
```python
# Replace the entire "--- parse body sections ---" block with:
user_msg = ""
sentinel_msg = ""
try:
    from app.markdown_frontmatter import split_frontmatter
    _fm, body_text = split_frontmatter(raw)
    body_text = body_text.lstrip("\n") if body_text else ""
    user_section = re.search(
        r"## User\s*\n+(.*?)(?=\n## |\Z)", body_text, re.DOTALL
    )
    sentinel_section = re.search(
        r"## Sentinel\s*\n+(.*?)(?=\n## |\Z)", body_text, re.DOTALL
    )
    if user_section:
        user_msg = user_section.group(1).strip()
    if sentinel_section:
        sentinel_msg = sentinel_section.group(1).strip()
except Exception:
    pass
```

This reuses the tested, single-source-of-truth `split_frontmatter` helper and
eliminates the fragile `find()` chain entirely.

---

### CR-02: `FakeVault.get_recent_sessions` ignores `policy.hot_window_days` — retention-window tests cannot detect production regressions

**File:** `sentinel-core/tests/fakes/vault.py:91-111`

**Issue:** The production `ObsidianVault.get_recent_sessions` filters candidates to
only the last `policy.hot_window_days` days by computing a date range:
```python
dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(policy.hot_window_days)]
```

`FakeVault.get_recent_sessions` does none of this — it simply returns all notes
whose path starts with `ops/sessions/` and matches `user_id`, up to
`policy.hot_limit`, with no date window applied at all:
```python
for path, body in self.notes.items():
    if not path.startswith("ops/sessions/"):
        continue
    filename = path.rsplit("/", 1)[-1]
    if f"{user_id}-" in filename and filename.endswith(".md"):
        candidates.append((path, body))
candidates.sort(key=lambda t: t[0], reverse=True)
for path, body in candidates[: policy.hot_limit]:
    ...
```

The test `test_retention_window_tunable` (test_recall.py:1673) seeds three sessions
with `today`'s date and uses `hot_window_days=30` so the discrepancy is invisible.
The test `test_recency_order_hot` (test_recall.py:1373) uses `hot_window_days=30` to
ensure both the old and new session survive — so again the gap is never surfaced.

If production code introduced a bug that broke the window filter (returned sessions
from 90 days ago), FakeVault-based tests would never catch it because FakeVault
always returns every session regardless of date. This is a test-seam fidelity
failure: the fake does not faithfully model the production contract it is supposed
to exercise.

**Fix:**
```python
async def get_recent_sessions(
    self, user_id: str, policy: RetentionPolicy
) -> list[SessionSummary]:
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    window_dates = {
        (now - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(policy.hot_window_days)
    }
    candidates: list[tuple[str, str]] = []
    for path, body in self.notes.items():
        if not path.startswith("ops/sessions/"):
            continue
        # Extract date from path shape ops/sessions/{date}/...
        parts = path.split("/")
        if len(parts) < 4:
            continue
        note_date = parts[2]
        if note_date not in window_dates:
            continue
        filename = path.rsplit("/", 1)[-1]
        if f"{user_id}-" in filename and filename.endswith(".md"):
            candidates.append((path, body))
    candidates.sort(key=lambda t: t[0], reverse=True)
    summaries: list[SessionSummary] = []
    for path, body in candidates[: policy.hot_limit]:
        parsed = _parse_session_summary(path, body)
        if parsed is not None:
            summaries.append(parsed)
    return summaries
```

---

### CR-03: Hot-tier session injection in `MessageProcessor.process` emits empty separator strings — silent context waste when session body is empty

**File:** `sentinel-core/app/services/message_processing.py:110-112`

**Issue:**
```python
context_parts.append(
    "Recent session history:\n" + "\n---\n".join(s.body for s in recalled.sessions)
)
```

`SessionSummary.body` is the raw note body (including frontmatter). When
`_parse_session_summary` successfully parses the path triplet but the raw note body
is empty (e.g., an empty file, or a note whose HTTP read returned `""`), the
`SessionSummary` is constructed with `body=raw` where `raw=""`. The `"---".join(...)`
call over a list that contains empty strings silently emits:
```
Recent session history:\n\n---\n\n---\n<real body>
```
Each empty-body session contributes a stray `\n---\n` separator, wasting tokens and
degrading injection quality. There is no guard equivalent to the warm-tier's WR-01
empty-body skip.

Note: `_parse_session_summary` does _not_ return `None` when body is empty — the
`None`-return path is triggered only when the path shape is too malformed to derive
the date/user_id/time triplet. A note that exists but has an empty body produces a
`SessionSummary` with `body=""`.

**Fix:**
```python
non_empty_sessions = [s for s in recalled.sessions if s.body.strip()]
if non_empty_sessions:
    context_parts.append(
        "Recent session history:\n" + "\n---\n".join(s.body for s in non_empty_sessions)
    )
```

---

## Warnings

### WR-01: `recency_weight` called with `None` via `_path_date()` return — but the fail-open contract means the test for `None` asserts the wrong value

**File:** `sentinel-core/app/services/recall.py:871`

**Issue:**
```python
date_str = _path_date(r.path)
w = recency_weight(date_str if date_str is not None else "", now=now)
```

When `_path_date` returns `None` (unrecognised path shape), the code passes `""` as
the `date_str` to `recency_weight`. `recency_weight` will call
`datetime.strptime("", "%Y-%m-%d")` which raises `ValueError`, caught by the
`except (ValueError, TypeError)` block, returning `1.0`. This is correct behavior
(fail-open), but it means parsing an empty string is handled as a caught exception
rather than a fast path — a minor inefficiency. More importantly, the test at
test_recall.py:1325 asserts `recency_weight(None, ...)` returns 1.0, which exercises
the `TypeError` path of the `except` clause. The production code never actually
calls `recency_weight(None, ...)` because of the `if date_str is not None else ""`
guard — so the `None` test exercises a code path that is never reached in production.

The issue is not a correctness failure but a subtle contract gap: if someone
removes the `is not None` guard in `_warm_search`, `recency_weight(None)` would
still return 1.0 as documented — but a test that specifically tests this path would
be the right guard for the reachable case.

**Fix:** Replace the `None` guard with a direct pass-through so the production code
actually exercises the same path the test exercises:
```python
w = recency_weight(date_str or "", now=now)
```
This is functionally identical but removes the explicit `None` check, making the
two code paths converge.

---

### WR-02: `test_assemble_degrades_gracefully_when_sessions_tier_raises` uses a wrong signature on the injected function — test may pass vacuously

**File:** `sentinel-core/tests/test_recall.py:276-280`

**Issue:**
```python
async def raising_sessions(user_id: str, limit: int = 3) -> list[str]:
    raise RuntimeError("simulated session tier failure")

vault.get_recent_sessions = raising_sessions
```

The production `Vault.get_recent_sessions` signature is:
```python
async def get_recent_sessions(self, user_id: str, policy: RetentionPolicy) -> list[SessionSummary]
```

The test stub accepts `(user_id: str, limit: int = 3)` — the second parameter is
`limit` with a default, not `policy`. In production, `_hot_sessions` calls
`vault.get_recent_sessions(user_id, self._policy)` passing a `RetentionPolicy`
instance as the second positional argument. When the stub is called, Python assigns
that `RetentionPolicy` instance to the `limit` parameter — which doesn't raise a
`TypeError` because the function signature accepts any second positional argument.
The test does exercise the exception path (the stub still raises `RuntimeError`), so
it is not completely vacuous, but the signature mismatch means the stub accepts
malformed calls without complaint. If the production call site changed to keyword
arguments (`get_recent_sessions(user_id, policy=self._policy)`) the stub would
silently accept it even though `limit=` and `policy=` are different parameters.

**Fix:** Update the stub signature to match the production contract:
```python
async def raising_sessions(user_id: str, policy: RetentionPolicy) -> list[SessionSummary]:
    raise RuntimeError("simulated session tier failure")
```

---

### WR-03: `status.py` debug endpoint leaks `SessionSummary` fields via explicit serialization — `body` field omitted, creating a silent asymmetry

**File:** `sentinel-core/app/routes/status.py:56-68`

**Issue:** The `/context/{user_id}` endpoint serializes `SessionSummary` with an
explicit dict comprehension:
```python
"sessions": [
    {
        "date": s.date,
        "user_id": s.user_id,
        "time": s.time,
        "user_msg": s.user_msg,
        "sentinel_msg": s.sentinel_msg,
        "path": s.path,
    }
    for s in recalled.sessions
],
```

The `SessionSummary.body` field (the full raw markdown) is intentionally omitted
from the API response — this is correct for production security. However, the
comment at line 51 says `# Plan 41-05 lockstep: explicit SessionSummary field
serialization (mirrors warm idiom)` but the warm idiom at `recall.py` returns
`s.body` for injection. The asymmetry is fine in intent but the code comment is
misleading: it says it "mirrors warm idiom" when it actually does the opposite
(warm uses body; this endpoint strips body). A future developer adding a field to
`SessionSummary` might add it to the warm injection path but forget to add it here,
or vice versa, because the comment suggests they're the same shape.

More concretely: the `body` field contains full raw markdown including the system
prompt persona and detailed conversation text. If this endpoint is ever proxied or
logged, the comment misdirection increases the risk of accidentally including `body`
in the serialization.

**Fix:** Rename the comment to accurately describe what the serialization does:
```python
# Plan 41-05: serialize typed fields only — body excluded (debug endpoint only,
# not injection path; body contains raw markdown not suitable for external APIs).
```

---

### WR-04: `_parse_session_summary` frontmatter regex `_FM_FIELD_RE` uses `re.MULTILINE` but the pattern is applied to a captured group, not to the full string — `re.MULTILINE` is a no-op here

**File:** `sentinel-core/app/vault.py:177, 227`

**Issue:**
```python
_FM_FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)
...
for fm_m in _FM_FIELD_RE.finditer(fm_match.group(1)):
```

`_FM_FIELD_RE` is compiled with `re.MULTILINE` so that `^` and `$` match at line
boundaries within a multi-line string. This is correct for the intended use: the
captured group `fm_match.group(1)` contains the multi-line frontmatter content.
However, the flag is applied at compile time to the module-level constant and has
no effect on `finditer` across a captured group — `re.MULTILINE` controls `^`/`$`
anchors against `\n` in the target string, which is correct here. This is actually
fine as-is, but the value captured by group(2) uses `(.+)$` which will not capture
trailing whitespace before `\n`. More importantly, the `(.+)` pattern is greedy and
does not account for YAML values that span multiple lines (e.g. `title: "foo: bar"`
or `description: |-`). For the current session note schema (`timestamp`, `user_id`,
`model`) this is not a practical problem, but the regex is silently fragile for
any future frontmatter field that contains a colon.

This is a quality warning, not a blocker, because the current field set never
triggers it and the outer `except Exception: pass` absorbs any parse failures.

**Fix:** Document the limitation explicitly:
```python
# NOTE: _FM_FIELD_RE only handles simple key: value pairs.
# Multi-line YAML values and values containing colons are not parsed.
# The session note schema (timestamp, user_id, model) is always simple — acceptable.
_FM_FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)
```

---

### WR-05: `test_context_sessions_serializes_typed_fields` does not assert that `body` is absent from the response — the security boundary is untested

**File:** `sentinel-core/tests/test_status.py:130-146`

**Issue:** The test verifies that the explicit typed fields (`date`, `user_id`,
`time`, `user_msg`, `sentinel_msg`, `path`) appear in the serialized session dict,
but it does not assert that `body` is absent. `SessionSummary.body` contains the
full raw markdown of the session note (potentially including the AI persona and
detailed conversation history). If a future change accidentally included `body` in
the serialized output, no existing test would catch it.

**Fix:** Add a negative assertion:
```python
assert "body" not in session_dict, (
    "SessionSummary.body must NOT be serialized in the /context endpoint "
    "(contains raw markdown including conversation history)"
)
```

---

## Info

### IN-01: `composition.py` imports `Embeddings` twice — once at module level and once inside `TYPE_CHECKING`

**File:** `sentinel-core/app/composition.py:22, 45`

**Issue:**
```python
from app.clients.embeddings import DEFAULT_LMSTUDIO_BASE_URL, Embeddings  # line 22

if TYPE_CHECKING:
    ...
    from app.clients.embeddings import Embeddings  # line 45 — duplicate
```

The `TYPE_CHECKING` block re-imports `Embeddings` which is already imported
unconditionally at line 22. The `TYPE_CHECKING` import is unreachable at runtime
and shadowed by the module-level import. Static type checkers will use the runtime
import correctly. This is dead code in the `TYPE_CHECKING` block.

**Fix:** Remove line 45 (`from app.clients.embeddings import Embeddings`) from the
`TYPE_CHECKING` block.

---

### IN-02: `test_recall_index_path_no_duplicate_literal` and `test_recall_imports_embedding_index_path` are source-grep tests — banned pattern per CLAUDE.md

**File:** `sentinel-core/tests/test_recall.py:991-1021`

**Issue:** Three tests in the "single-source-of-truth" section use
`pathlib.Path(...).read_text()` + `assert "..." in text` / `assert "..." not in text`
to inspect source code rather than calling the function under test:
```python
recall_src = pathlib.Path(__file__).parent.parent / "app" / "services" / "recall.py"
text = recall_src.read_text(encoding="utf-8")
assert "ops/sweeps/embedding-index" not in text
```

These are source-grep tests — they check the implementation's source text rather
than its observable behavior. Per the project's Behavioral-Test-Only Rule in
CLAUDE.md, this pattern is explicitly banned:
> `assert re.search(r"pattern", source)` — regex on source code is not a behavior test

The single-source equality test (`test_index_path_single_source_constant_equality`)
at line 975 is behaviorally correct (it compares runtime values). The two grep
tests at lines 991 and 1009 are the problematic ones.

These tests were presumably added to enforce an architectural constraint, but that
constraint is already covered by the behavioral test: if `recall.py` introduced its
own duplicate literal, `RecallConfig().index_path` would diverge from
`EMBEDDING_INDEX_PATH` and the behavioral test would fail. The source-grep tests
are redundant with the behavioral test and violate the project's testing rules.

**Fix:** Delete `test_recall_index_path_no_duplicate_literal` and
`test_recall_imports_embedding_index_path`. The behavioral test
`test_index_path_single_source_constant_equality` already covers the contract.

---

### IN-03: `FakeVault.get_recent_sessions` returns sessions ignoring the `hot_window_days` window — but `_hot_sessions` in `Recall` independently re-sorts by `recency_weight` after the fact

**File:** `sentinel-core/app/services/recall.py:802`
**Related:** `sentinel-core/tests/fakes/vault.py:91`

**Issue:** This is a documentation gap rather than a bug: the recency-sort in
`_hot_sessions` is applied AFTER `vault.get_recent_sessions` returns. In production,
`vault.get_recent_sessions` applies the window filter first (returning only sessions
within `hot_window_days`), then `_hot_sessions` sorts the survivors by
`recency_weight`. In the FakeVault, ALL sessions are returned (no window), then
sorted. The result is that `_hot_sessions` correctly orders what it receives, but
FakeVault includes sessions that production would exclude. This compounds CR-02 and
should be noted in the test file as a known contract gap until CR-02 is fixed.

**Fix:** Addressed by CR-02. No additional code change needed here; the note is
informational to track the dependency.

---

_Reviewed: 2026-06-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
