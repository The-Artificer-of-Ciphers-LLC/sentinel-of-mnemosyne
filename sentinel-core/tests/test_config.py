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


def test_lmstudio_base_url_default_is_docker_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-lmstudio-provider-switch: the default must use host.docker.internal (Docker
    host-gateway alias), not bare 'localhost' -- which resolves to the container
    itself, not the host machine running the inference backend. Pinned at
    host.docker.internal:1234 (LM Studio) so a regression to an unreachable
    bare-localhost value fails this test."""
    monkeypatch.delenv("LMSTUDIO_BASE_URL", raising=False)
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")

    s = Settings()

    assert s.lmstudio_base_url == "http://host.docker.internal:1234/v1"
    assert "localhost" not in s.lmstudio_base_url


def test_exo_fields_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """exo_* fields have safe defaults; exo_model defaults to empty string (no
    hardcoded model id — auto-discover via GET /state, D-07/D-08)."""
    monkeypatch.delenv("EXO_BASE_URL", raising=False)
    monkeypatch.delenv("EXO_MODEL", raising=False)
    monkeypatch.delenv("EXO_API_KEY", raising=False)
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")

    s = Settings()

    assert s.exo_base_url == "http://host.docker.internal:52415/v1"
    assert s.exo_model == ""
    assert s.exo_api_key == ""


def test_exo_env_vars_populate_independently_of_lmstudio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting EXO_* env vars populates exo_* fields without touching
    lmstudio_base_url / model_name (SC-1, D-03)."""
    monkeypatch.setenv("EXO_BASE_URL", "http://host.docker.internal:52415/v1")
    monkeypatch.setenv("EXO_MODEL", "mlx-community/Qwen3.5-27B-8bit")
    monkeypatch.setenv("EXO_API_KEY", "exo-secret")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://host.docker.internal:1234/v1")
    monkeypatch.setenv("MODEL_NAME", "some-lmstudio-model")
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")

    s = Settings()

    assert s.exo_base_url == "http://host.docker.internal:52415/v1"
    assert s.exo_model == "mlx-community/Qwen3.5-27B-8bit"
    assert s.exo_api_key == "exo-secret"
    # independence: lmstudio_* fields hold their own values, unaffected
    assert s.lmstudio_base_url == "http://host.docker.internal:1234/v1"
    assert s.model_name == "some-lmstudio-model"


def test_ai_provider_accepts_exo(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI_PROVIDER=exo parses successfully (D-04)."""
    monkeypatch.setenv("AI_PROVIDER", "exo")
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")

    s = Settings()

    assert s.ai_provider == "exo"


def test_ai_fallback_provider_accepts_any_provider_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_FALLBACK_PROVIDER accepts any configured provider name, not just
    claude/none (D-05) — e.g. lmstudio."""
    monkeypatch.setenv("AI_FALLBACK_PROVIDER", "lmstudio")
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")

    s = Settings()

    assert s.ai_fallback_provider == "lmstudio"
