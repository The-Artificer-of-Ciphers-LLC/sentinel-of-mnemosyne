"""Pytest configuration and shared fixtures for pathfinder module tests.

Test-time sys.path setup: the pathfinder Dockerfile copies shared/sentinel_shared
into /app at build time, but local pytest runs from the host where the
repo's `shared/` dir is at ../../shared/ relative to this module. Insert
that path before any other test code imports from sentinel_shared
(otherwise tests that touch app.llm / app.foundry / app.pf_npc_extract
fail at import time).

Two autouse fixtures for test_session_integration.py:

1. freeze_session_date — patches datetime.date.today() in app.routes.session
   to return 2026-04-25, the fixed date used in _OPEN_NOTE_PATH, so tests are
   date-independent regardless of when they run.

2. pre_patch_litellm_acompletion — compensates for a test design issue in
   test_show_calls_llm_and_patches_story where `assert litellm.acompletion.await_count >= 1`
   is checked OUTSIDE the `with patch("litellm.acompletion", ...)` block.
   After the inner patch exits and restores litellm.acompletion to our conftest
   tracker, we set the tracker's await_count to reflect the inner mock's calls.
"""
import datetime
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Make the repo's shared/ package importable for local pytest runs.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SHARED = os.path.join(_REPO_ROOT, "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

# Pre-import app.main so mock.patch("app.main.<symbol>") can resolve the attribute
# at __enter__ time without each test having to do `from app.main import app`
# above the patch context. Test envs that exercise routes via FastAPI all use
# this pattern (test_session_integration, test_player_routes); without this
# pre-import, the patch fails with `module 'app' has no attribute 'main'`.
# Required env vars are set above this block via os.environ.setdefault calls in
# the per-test files; main.py reads them via pydantic-settings at import time.
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")
import app.main  # noqa: E402,F401  — register app.main as attribute of app package

# Fixed date used throughout test_session_integration.py
_TEST_SESSION_DATE = datetime.date(2026, 4, 25)


def _in_session_integration(request) -> bool:
    return "test_session_integration" in (request.fspath.basename if request.fspath else "")


@pytest.fixture(autouse=True)
def freeze_session_date(request):
    """Freeze datetime.date.today() in app.routes.session to 2026-04-25.

    Only applied to test_session_integration tests.
    """
    if not _in_session_integration(request):
        yield
        return

    class _FrozenDate(datetime.date):
        @classmethod
        def today(cls):
            return _TEST_SESSION_DATE

        def isoformat(self):
            return super().isoformat()

    _real_datetime = datetime.datetime
    _real_timezone = datetime.timezone

    with patch("app.routes.session.datetime") as mock_dt:
        mock_dt.date = _FrozenDate
        mock_dt.datetime = _real_datetime
        mock_dt.timezone = _real_timezone
        yield


@pytest.fixture(autouse=True)
def pre_patch_litellm_acompletion(request):
    """Install an AsyncMock on litellm.acompletion for session integration tests.

    test_show_calls_llm_and_patches_story checks `litellm.acompletion.await_count`
    OUTSIDE its own `with patch(...)` block — after the inner patch exits and
    restores litellm.acompletion to our conftest mock, the conftest mock's
    await_count is 0. We fix this by intercepting the module setattr: when
    litellm.acompletion is set BACK to our mock (the inner patch exiting), we
    copy the inner mock's await_count into our mock.

    Implementation: we subclass the litellm module's class to intercept setattr,
    detect the restore event, and propagate the call count.
    """
    if not _in_session_integration(request):
        yield
        return

    import litellm

    original_acompletion = litellm.acompletion
    tracker = AsyncMock(name="conftest.litellm.acompletion")
    _state: dict = {"stack": []}

    # Intercept module-level setattr to detect patch save/restore events.
    # WR-01: use a stack so nested patches each propagate their await_count correctly.
    _orig_module_class = type(litellm)

    class _InterceptingMeta(_orig_module_class):
        def __setattr__(cls, name, value):  # noqa: N805
            if name == "acompletion":
                if value is not tracker and value is not original_acompletion:
                    # Inner patch entering — push onto stack.
                    _state["stack"].append(value)
                elif value is tracker and _state["stack"]:
                    # Inner patch exiting — pop and propagate await_count.
                    inner = _state["stack"].pop()
                    try:
                        tracker.await_count = tracker.await_count + getattr(inner, "await_count", 0)
                    except (AttributeError, TypeError):
                        pass
            super().__setattr__(name, value)

    litellm.__class__ = _InterceptingMeta
    litellm.acompletion = tracker
    try:
        yield
    finally:
        litellm.__class__ = _orig_module_class
        litellm.acompletion = original_acompletion
