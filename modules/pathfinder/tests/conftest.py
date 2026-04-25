"""Pytest configuration and shared fixtures for pathfinder module tests.

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
from unittest.mock import AsyncMock, patch

import pytest

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
