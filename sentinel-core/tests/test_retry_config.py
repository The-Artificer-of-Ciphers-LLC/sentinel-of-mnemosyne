"""Tests for shared retry configuration — RD-03 / DUP-03."""
from app.clients import retry_config
from tenacity.stop import StopBaseT
from tenacity.wait import WaitBaseT


def test_retry_attempts_value():
    assert retry_config.RETRY_ATTEMPTS == 3


def test_hard_timeout_seconds():
    assert retry_config.HARD_TIMEOUT_SECONDS == 30


def test_retry_stop_is_tenacity_stop():
    assert isinstance(retry_config.RETRY_STOP, StopBaseT)


def test_retry_wait_is_tenacity_wait():
    assert isinstance(retry_config.RETRY_WAIT, WaitBaseT)


def test_no_duplicate_stop_in_pi_adapter():
    import inspect
    import importlib
    src = inspect.getsource(importlib.import_module("app.clients.pi_adapter"))
    assert "stop_after_attempt(3)" not in src


def test_no_duplicate_stop_in_litellm_provider():
    import inspect
    import importlib
    src = inspect.getsource(importlib.import_module("app.clients.litellm_provider"))
    assert "stop_after_attempt(3)" not in src
