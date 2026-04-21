---
phase: 26-nyquist-validation-cleanup
reviewed: 2026-04-20T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - interfaces/discord/tests/conftest.py
  - interfaces/discord/tests/test_subcommands.py
  - interfaces/discord/tests/test_thread_persistence.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 26: Code Review Report

**Reviewed:** 2026-04-20T00:00:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Three test files covering Phase 26 Nyquist validation cleanup were reviewed: the shared `conftest.py`, subcommand routing tests, and thread ID persistence tests. The tests are structurally sound and correctly exercise the production bot code. No critical bugs or security vulnerabilities were found.

Two warnings stand out: the discord stub bootstrap block is copy-pasted verbatim across both test files, making future stub changes error-prone; and a redundant `import os as _os` inside a test function body shadows the module-level import in a misleading way. Three info-level items round out the report.

## Warnings

### WR-01: Discord stub block duplicated across test files

**File:** `interfaces/discord/tests/test_subcommands.py:13-51` and `interfaces/discord/tests/test_thread_persistence.py:15-58`

**Issue:** The entire discord stub setup — `_DiscordClientStub`, `_IntentsStub`, `_app_commands_stub`, `_discord_stub`, `sys.modules.setdefault`, env var defaults, and `sys.path.insert` calls — is copy-pasted verbatim across both files. When both files are collected in the same pytest session, the second file's `sys.modules.setdefault` calls are no-ops (the stubs are already registered), but the path-manipulation and class definitions still execute twice. More critically, any change to the stub (e.g., adding a new `discord.*` attribute required by the bot) must be applied in both files or one silently wins depending on collection order.

**Fix:** Move the entire stub block into `conftest.py` as a session-scoped fixture or module-level setup. Since both test files already import from `conftest.py` (via `autouse` fixtures), the stubs can be registered there unconditionally:

```python
# conftest.py — add before any test collection

import os
import sys
import types
from unittest.mock import MagicMock

class _DiscordClientStub:
    def __init__(self, **kwargs):
        pass

class _IntentsStub:
    message_content = False

    @classmethod
    def default(cls):
        return cls()

_app_commands_stub = types.ModuleType("discord.app_commands")
_app_commands_stub.CommandTree = MagicMock()
_app_commands_stub.describe = lambda **_: (lambda f: f)

_discord_stub = types.ModuleType("discord")
_discord_stub.Client = _DiscordClientStub
_discord_stub.Intents = _IntentsStub
_discord_stub.Message = object
_discord_stub.Thread = object
_discord_stub.ChannelType = MagicMock()
_discord_stub.Forbidden = Exception
_discord_stub.HTTPException = Exception
_discord_stub.Interaction = object
_discord_stub.app_commands = _app_commands_stub
sys.modules.setdefault("discord", _discord_stub)
sys.modules.setdefault("discord.app_commands", _app_commands_stub)

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

_discord_dir = os.path.join(os.path.dirname(__file__), "..")
_repo_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, os.path.abspath(_repo_root))
sys.path.insert(0, os.path.abspath(_discord_dir))
```

Both test files can then drop their stub blocks entirely and simply `import bot`.

---

### WR-02: Redundant local import shadows module-level `os` import

**File:** `interfaces/discord/tests/test_thread_persistence.py:160`

**Issue:** `import os as _os` is written inside the body of `test_persist_thread_id_integration`. The module already imports `os` at line 2. The aliased re-import is a copy-paste artifact. It is not harmful in isolation, but it suggests `os` was not expected to be available at module scope — misleading for anyone reading the test. It also silently hides the dependency on the module-level import, making the test look more self-contained than it is.

**Fix:** Remove the inline import and use the module-level `os` directly:

```python
# Before (line 160-163):
import os as _os
base_url = _os.environ.get("OBSIDIAN_BASE_URL", "http://host.docker.internal:27124")
api_key = _os.environ.get("OBSIDIAN_API_KEY", "")

# After:
base_url = os.environ.get("OBSIDIAN_BASE_URL", "http://host.docker.internal:27124")
api_key = os.environ.get("OBSIDIAN_API_KEY", "")
```

---

## Info

### IN-01: `obsidian_teardown` forces `test_run_path` instantiation on every test

**File:** `interfaces/discord/tests/conftest.py:26-42`

**Issue:** `obsidian_teardown` is `autouse=True` and lists `test_run_path` as a parameter, so pytest generates a UUID path for every test in the suite — including all unit tests in `test_subcommands.py` that never touch Obsidian. The UUID generation is cheap, but the invisible fixture dependency can confuse contributors who don't expect a UUID path to be allocated for pure-mock tests.

**Fix:** Use `request.getfixturevalue` lazily inside the integration guard, and remove `test_run_path` from the fixture signature, so the UUID is only generated when actually needed:

```python
@pytest.fixture(autouse=True)
async def obsidian_teardown(request):
    yield
    if "integration" in request.keywords:
        run_path = request.getfixturevalue("test_run_path")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.delete(
                    f"{OBSIDIAN_BASE_URL}/vault/{run_path}/",
                    headers={"Authorization": f"Bearer {OBSIDIAN_API_KEY}"},
                )
        except Exception:
            pass
```

---

### IN-02: `asyncio_mode=auto` is an implicit dependency on conftest scope

**File:** `interfaces/discord/tests/test_subcommands.py:60` (and all `async def test_*` functions)

**Issue:** All test functions in `test_subcommands.py` and `test_thread_persistence.py` are `async def` but carry no `@pytest.mark.asyncio` decorator. They rely entirely on `conftest.py`'s `pytest_configure` hook setting `asyncio_mode=auto`. If these test files are ever run in isolation from a different working directory (or if `conftest.py` is reorganized), the async tests will silently be treated as sync functions and pass vacuously without awaiting their coroutines.

**Fix:** Either keep this as-is and document the conftest dependency explicitly, or add `pytest.ini` / `pyproject.toml` config so `asyncio_mode = auto` is project-wide rather than injected via a hook:

```toml
# pyproject.toml or pytest.ini
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

This makes the setting visible and robust regardless of conftest discovery order.

---

### IN-03: `content_arg` assertion uses `.kwargs` access — silent failure if arg is positional

**File:** `interfaces/discord/tests/test_thread_persistence.py:96`

**Issue:** The assertion extracts the `content` kwarg from `captured_patch.call_args.kwargs`. If `_persist_thread_id` were ever refactored to pass `content` as a positional argument, `.kwargs.get("content", b"")` would return the default `b""` and the assertion `b"99999" in b""` would fail with a cryptic message that doesn't indicate whether PATCH was called at all or the argument was merely positional.

**Fix:** Assert both argument-access paths explicitly, or use `assert_called_once_with` for the full call signature. At minimum, add a clearer fallback:

```python
call_args = captured_patch.call_args
# Try kwargs first, then positional args
content_arg = call_args.kwargs.get("content") or (call_args.args[1] if len(call_args.args) > 1 else b"")
assert b"99999" in content_arg, (
    f"99999 was not found in PATCH body. call_args={call_args!r}"
)
```

---

_Reviewed: 2026-04-20T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
