"""Tests for app.resolve_model — pathfinder-specific LiteLLM prefix normalization."""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

from unittest.mock import AsyncMock, patch

import pytest

from app.resolve_model import resolve_model


@pytest.fixture(autouse=True)
def _reset_cache():
    from app.model_selector import _reset_cache_for_tests

    _reset_cache_for_tests()


async def test_resolve_model_adds_openai_prefix_to_bare_name():
    """When the selector returns a bare name from /v1/models, resolve_model prefixes it.

    Reproduces the live bug: litellm.acompletion(model="meta-llama-3.1-8b-instruct-abliterated-mlx")
    raises BadRequestError("LLM Provider NOT provided") because the provider is missing.
    """
    with patch(
        "app.resolve_model.get_loaded_models",
        new=AsyncMock(return_value=["meta-llama-3.1-8b-instruct-abliterated-mlx"]),
    ):
        chosen = await resolve_model("structured")

    assert chosen == "openai/meta-llama-3.1-8b-instruct-abliterated-mlx"


async def test_resolve_model_preserves_existing_prefix():
    """When a loaded model already has a provider prefix, resolve_model passes it through."""
    with patch(
        "app.resolve_model.get_loaded_models",
        new=AsyncMock(return_value=["openai/qwen2.5-14b-instruct"]),
    ):
        chosen = await resolve_model("structured")

    assert chosen == "openai/qwen2.5-14b-instruct"


async def test_resolve_model_falls_back_to_placeholder_when_discovery_empty():
    """When discovery returns empty, resolve_model falls back to the inert
    placeholder — never forwarded to a real completion call (SC-6, D-09).

    Phase 42-05 removed the last hardcoded chat-model default
    (`settings.litellm_model`) from app/config.py; resolve_model() no longer
    has a "real" default to fall back to, by design.
    """
    with patch(
        "app.resolve_model.get_loaded_models",
        new=AsyncMock(return_value=[]),
    ):
        chosen = await resolve_model("fast")

    assert chosen == "openai/unused-core-resolves-model"
