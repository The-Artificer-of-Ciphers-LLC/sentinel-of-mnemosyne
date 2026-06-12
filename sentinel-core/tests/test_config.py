"""Behavioral tests for Settings fields added in plan 41-03 (MEM-06).

All tests construct a real Settings() instance and assert on field values —
they do NOT grep source code or check tautologies.
"""
import pytest

from app.config import Settings


def test_retention_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings() with no env override yields the documented defaults (3 / 2)."""
    # Isolate from any ambient env values so the test is reproducible
    monkeypatch.delenv("RETENTION_HOT_LIMIT", raising=False)
    monkeypatch.delenv("RETENTION_HOT_WINDOW_DAYS", raising=False)
    # sentinel_api_key is required; provide a dummy so Settings() doesn't raise
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")

    s = Settings()

    assert s.retention_hot_limit == 3
    assert s.retention_hot_window_days == 2


def test_retention_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """RETENTION_HOT_LIMIT / RETENTION_HOT_WINDOW_DAYS override the defaults
    and are coerced to int (not left as strings) by pydantic-settings."""
    monkeypatch.setenv("RETENTION_HOT_LIMIT", "5")
    monkeypatch.setenv("RETENTION_HOT_WINDOW_DAYS", "4")
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")

    s = Settings()

    assert s.retention_hot_limit == 5
    assert s.retention_hot_window_days == 4
    assert isinstance(s.retention_hot_limit, int)
    assert isinstance(s.retention_hot_window_days, int)
