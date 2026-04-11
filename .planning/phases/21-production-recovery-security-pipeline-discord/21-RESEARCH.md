# Phase 21: Production Recovery — Security Pipeline + Discord - Research

**Researched:** 2026-04-11
**Domain:** Git history recovery, FastAPI lifespan wiring, Docker Compose include
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Restore `sentinel-core/app/services/injection_filter.py` from commit `c6f4753`
- **D-02:** Restore `sentinel-core/app/services/output_scanner.py` from commit `c6f4753`
- **D-03:** Restore deleted test files (see corrected paths below)
- **D-04:** Re-add imports + `app.state` assignments in `main.py` lifespan — do NOT touch `message.py`
- **D-05:** Uncomment Discord include in `docker-compose.yml` line 10, add danger comment
- **D-06:** Run full pytest to verify no regressions

### Claude's Discretion

None specified.

### Deferred Ideas (OUT OF SCOPE)

- Modifying `message.py` (already correct)
- Modifying `conftest.py` test fixtures (they correctly stub; this is fine)
- Changing any injection filter or output scanner logic (restore exactly, no improvements)
- Phase 24 pentest agent wiring (separate phase)
</user_constraints>

---

## Summary

Phase 10-03 commit `6cfb0d3` performed a large "cleanup" that deleted four service files and stripped all security wiring from `main.py`. The deletions are confirmed in git history. Commit `c6f4753` is the last-known-good state for both service files and both test files — it is the correct restore point.

The `git diff c6f4753 HEAD -- sentinel-core/app/main.py` reveals exactly 14 lines that need to be re-added to main.py: three import lines and eleven lifespan lines. The diff is clean and mechanical — no logic changes, no merge conflicts.

One correction to the CONTEXT.md: it names the test files as `tests/unit/test_injection_filter.py` and `tests/unit/test_output_scanner.py`. The actual paths are `sentinel-core/tests/test_injection_filter.py` and `sentinel-core/tests/test_output_scanner.py`. There is no top-level `tests/` directory in this project.

The docker-compose.yml change is also mechanical: the deletion commit moved the Discord include from the active `include:` block into a commented `# Future modules` comment. The target state from commit `2b11b3f` (the last confirmed-working Discord state) includes `interfaces/discord/compose.yml` in the active include block. The pentest-agent compose.yml was also removed by the same commit but that is Phase 24 scope.

**Primary recommendation:** Use `git show c6f4753:<path>` to restore all four files exactly. Use the verified `git diff` output to re-add the exact 14 lines to `main.py`. Correct the test file paths from CONTEXT.md before executing.

---

## Verified File Paths (CRITICAL CORRECTION)

CONTEXT.md names test files incorrectly. Verified paths from git history:

| CONTEXT.md says | Actual path (verified from git) |
|---|---|
| `tests/unit/test_injection_filter.py` | `sentinel-core/tests/test_injection_filter.py` |
| `tests/unit/test_output_scanner.py` | `sentinel-core/tests/test_output_scanner.py` |

[VERIFIED: `git show 6cfb0d3 --stat` and `git log --follow` confirm paths above]

---

## Architecture Patterns

### Restore Commands (All Verified)

```bash
# Restore service files
git show c6f4753:sentinel-core/app/services/injection_filter.py \
  > sentinel-core/app/services/injection_filter.py

git show c6f4753:sentinel-core/app/services/output_scanner.py \
  > sentinel-core/app/services/output_scanner.py

# Restore test files (corrected paths — NOT tests/unit/)
git show c6f4753:sentinel-core/tests/test_injection_filter.py \
  > sentinel-core/tests/test_injection_filter.py

git show c6f4753:sentinel-core/tests/test_output_scanner.py \
  > sentinel-core/tests/test_output_scanner.py
```

[VERIFIED: All four paths confirmed present in commit c6f4753 via `git show`]

### Exact main.py Changes Required

Three additions to imports (after `from starlette.responses import Response`, before `from app.clients.litellm_provider import LiteLLMProvider`):

```python
from anthropic import AsyncAnthropic
```

After the existing `from app.routes.message import router as message_router` line:

```python
from app.services.injection_filter import InjectionFilter
```

After the existing `from app.services.model_registry import build_model_registry` line:

```python
from app.services.output_scanner import OutputScanner
```

One addition to lifespan (after the `obsidian_ok` warning block, before `logger.info("Sentinel Core ready.")`):

```python
    # Security services — instantiated once, shared across all requests (SEC-01, SEC-02)
    anthropic_client_for_scanner = (
        AsyncAnthropic(api_key=settings.anthropic_api_key)
        if settings.anthropic_api_key
        else None
    )
    if anthropic_client_for_scanner is None:
        logger.warning(
            "ANTHROPIC_API_KEY not set — OutputScanner secondary classifier disabled (fail-open)"
        )
    app.state.injection_filter = InjectionFilter()
    app.state.output_scanner = OutputScanner(anthropic_client_for_scanner)
    logger.info("Security services initialized: InjectionFilter, OutputScanner")
```

[VERIFIED: `git diff c6f4753 HEAD -- sentinel-core/app/main.py` shows exactly these 14 lines deleted]

### docker-compose.yml Target State

The file must move the Discord include from the commented `# Future modules` block into the active `include:` block:

```yaml
include:
  - path: sentinel-core/compose.yml
  - path: pi-harness/compose.yml
  - path: interfaces/discord/compose.yml  # DO NOT COMMENT — restored 3x, required for Discord interface

# Future modules (uncomment when phase is ready):
#   - path: modules/pathfinder/compose.yml
```

[VERIFIED: `git show 2b11b3f:docker-compose.yml` confirms this is the correct target structure]

**Note:** The deletion commit also removed `security/pentest-agent/compose.yml` from the active includes. This is Phase 24 scope — do NOT restore it in Phase 21. The pentest-agent source files (Dockerfile, pentest.py, ofelia.ini) were also deleted by `6cfb0d3` and live only as a `__pycache__` artifact. Phase 24 handles their restoration.

---

## What the Restored Files Look Like

### injection_filter.py (83 lines)

- **Class:** `InjectionFilter` — no constructor arguments, no external dependencies
- **Methods:** `sanitize(text: str) -> tuple[str, bool]`, `wrap_context(context: str) -> str`, `filter_input(user_input: str) -> tuple[str, bool]`
- **Instantiation in lifespan:** `InjectionFilter()` — zero-arg constructor
- **Dependencies:** stdlib only (`logging`, `re`) — no pip install required

### output_scanner.py (116 lines)

- **Class:** `OutputScanner` — takes `anthropic_client: AsyncAnthropic | None`
- **Method:** `async scan(response: str) -> tuple[bool, str | None]`
- **Dependencies:** `anthropic` (already in pyproject.toml as `anthropic>=0.93.0,<1.0`), stdlib `asyncio`, `logging`, `re`
- **Model used:** `claude-haiku-4-5` (hardcoded as `HAIKU_MODEL` constant)
- **Fail-open design:** timeout, API error, or `None` client all return `(True, None)` — never blocks on infrastructure failure

### test_injection_filter.py (105 lines)

- **Imports:** `pytest`, `app.services.injection_filter.InjectionFilter`
- **Fixtures:** `injection_filter()` — returns `InjectionFilter()`
- **All tests:** synchronous (no `async def`) — no pytest-asyncio dependency in this file
- **Test count:** 13 tests

### test_output_scanner.py (116 lines)

- **Imports:** `pytest`, `unittest.mock.AsyncMock/MagicMock`, `app.services.output_scanner.OutputScanner`
- **All tests:** `async def` — require `asyncio_mode = "auto"` which is already set in pyproject.toml
- **Test count:** 13 tests (12 async + `test_private_ip_does_not_fire_on_plain_ip` which is also async)

---

## Test Infrastructure State

### Current state (before restore)

The test suite currently collects 29 tests across files that do NOT import the deleted services. `conftest.py`'s `default_app_state` fixture in `test_message.py` stubs both `injection_filter` and `output_scanner` into `app.state` using `MagicMock`/`AsyncMock` — so message tests pass today even without the real service files.

After restore, 26 additional tests will be collected (13 per file).

### `asyncio_mode = "auto"` confirmed active

`sentinel-core/pyproject.toml` has `[tool.pytest.ini_options] asyncio_mode = "auto"` — all `async def test_*` functions auto-get an event loop. [VERIFIED: `cat sentinel-core/pyproject.toml`]

### `anthropic` package is already in pyproject.toml

`anthropic>=0.93.0,<1.0` is in the `dependencies` list — not dev-only. No new pip install required.
[VERIFIED: `cat sentinel-core/pyproject.toml`]

### Running pytest

Pytest must be run from inside `sentinel-core/`:
```bash
cd sentinel-core && python -m pytest tests/ -v
```

Running from the repo root as `python3 -m pytest sentinel-core/tests/` fails with `ModuleNotFoundError: No module named 'litellm'` because the module is not installed in the system Python — it requires the virtualenv or Docker environment. The planner must account for this: the D-06 test run is best executed inside the container or an activated venv.

---

## Common Pitfalls

### Pitfall 1: Wrong test file paths (CRITICAL)
**What goes wrong:** CONTEXT.md references `tests/unit/test_injection_filter.py`. This path does not exist. The project has no top-level `tests/` directory.
**Root cause:** CONTEXT.md was written from memory, not from `git show --stat`.
**Prevention:** Use `sentinel-core/tests/test_injection_filter.py` and `sentinel-core/tests/test_output_scanner.py`.

### Pitfall 2: Missing `from anthropic import AsyncAnthropic` import
**What goes wrong:** Restoring the service files and adding the lifespan block is incomplete without adding the import. `AsyncAnthropic` is used inside the lifespan to construct the scanner client.
**Prevention:** The diff shows three separate import additions, not just two. All three must be applied.

### Pitfall 3: Using the wrong commit for restore
**What goes wrong:** c6f4753 is the correct commit. The deletion commit is `6cfb0d3`. Running `git show 6cfb0d3:<path>` returns an empty file (the file was deleted in that commit).
**Prevention:** Always use `c6f4753` as the source, not any commit after it.

### Pitfall 4: Restoring pentest-agent compose.yml
**What goes wrong:** The deletion commit removed both `security/pentest-agent/compose.yml` and `interfaces/discord/compose.yml` from docker-compose.yml. The pentest-agent source files are also missing. Restoring both together is out of scope.
**Prevention:** Phase 21 restores Discord only. Phase 24 handles pentest-agent.

### Pitfall 5: Running pytest from repo root without venv
**What goes wrong:** `python3 -m pytest sentinel-core/tests/` from the repo root fails with `ModuleNotFoundError: No module named 'litellm'` because the host system Python doesn't have the project's dependencies.
**Prevention:** Either activate the sentinel-core venv, run inside Docker, or run `cd sentinel-core && python -m pytest tests/`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Restoring deleted files | Manually recreating the content | `git show c6f4753:<path>` — exact content is in git history |
| Diffing what changed | Reading both versions and comparing | `git diff c6f4753 HEAD -- sentinel-core/app/main.py` already shows exactly what needs re-adding |

---

## Runtime State Inventory

Step 2.5 is not applicable — this is not a rename/refactor/migration phase. It is a production recovery restoring deleted files from git history.

---

## Environment Availability

Step 2.6: SKIPPED — this phase is purely code/file restoration from git history with no new external dependencies.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `sentinel-core/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `cd sentinel-core && python -m pytest tests/test_injection_filter.py tests/test_output_scanner.py -v` |
| Full suite command | `cd sentinel-core && python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-01 | InjectionFilter strips injection patterns | unit | `pytest tests/test_injection_filter.py -v` | Wave 0 (restore) |
| SEC-02 | OutputScanner blocks confirmed leaks, fails open on timeout | unit | `pytest tests/test_output_scanner.py -v` | Wave 0 (restore) |
| CORE-03 | POST /message returns ResponseEnvelope without AttributeError | unit | `pytest tests/test_message.py -v` | ✅ (uses stubs, passes today) |
| IFACE-02 | Discord container starts via docker compose up | integration | `cd sentinel-core && pytest tests/` | manual (requires Docker) |

### Wave 0 Gaps

- [ ] `sentinel-core/tests/test_injection_filter.py` — restore from git (13 tests, SEC-01)
- [ ] `sentinel-core/tests/test_output_scanner.py` — restore from git (13 tests, SEC-02)

*(Service files must be restored first — tests import from `app.services.*`)*

---

## Security Domain

Not applicable as a standalone security section — this phase IS the security restoration. The phase restores SEC-01 and SEC-02 controls that were accidentally deleted.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | `InjectionFilter` — already implemented, being restored |
| V8 Data Protection | yes | `OutputScanner` — already implemented, being restored |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The restored files at c6f4753 are identical to what Phase 05 intended — no code review findings were applied after that commit | Architecture Patterns | If a later fix commit exists between c6f4753 and 6cfb0d3, we'd restore a pre-fix version. Checked: commit `020a5a6` (fix(05)) was applied BEFORE c6f4753 in the history — c6f4753 IS the post-fix state. [VERIFIED] |

**All other claims in this research were verified via git commands or direct file reads — no unverified assumptions remain.**

---

## Open Questions

1. **pytest execution environment for D-06**
   - What we know: running pytest from repo root without a venv fails (litellm not installed on system Python)
   - What's unclear: whether the executor has a venv activated or uses Docker
   - Recommendation: Planner should include `cd sentinel-core` before pytest, and note that if no venv is active, the test run should be deferred to Docker

---

## Sources

### Primary (HIGH confidence)
- `git show 6cfb0d3 --stat` — confirmed which files were deleted and in which commit
- `git log --all --diff-filter=D -- sentinel-core/app/services/injection_filter.py` — confirmed c6f4753 as last-known-good
- `git show c6f4753:sentinel-core/app/services/injection_filter.py` — full file content verified
- `git show c6f4753:sentinel-core/app/services/output_scanner.py` — full file content verified
- `git show c6f4753:sentinel-core/tests/test_injection_filter.py` — test file content and path verified
- `git show c6f4753:sentinel-core/tests/test_output_scanner.py` — test file content and path verified
- `git diff c6f4753 HEAD -- sentinel-core/app/main.py` — exact 14-line diff verified
- `cat sentinel-core/app/main.py` — current state of lifespan confirmed (no security wiring)
- `cat docker-compose.yml` — current state confirmed (Discord commented out)
- `git show 2b11b3f:docker-compose.yml` — last confirmed Discord-active state
- `cat sentinel-core/pyproject.toml` — asyncio_mode=auto and anthropic dependency confirmed

---

## Metadata

**Confidence breakdown:**
- Restore commands: HIGH — verified by direct git show commands
- main.py diff: HIGH — verified by git diff output
- Test file paths: HIGH — verified by git show --stat (corrects CONTEXT.md)
- docker-compose target state: HIGH — verified by git show on last working Discord commit

**Research date:** 2026-04-11
**Valid until:** N/A — all findings are from this repo's own git history, not external sources
