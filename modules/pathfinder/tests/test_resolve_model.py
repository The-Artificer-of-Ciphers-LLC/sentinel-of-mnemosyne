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


async def test_resolve_model_falls_back_to_default_with_prefix():
    """When discovery returns empty, resolve_model returns settings.litellm_model verbatim (already prefixed)."""
    with patch(
        "app.resolve_model.get_loaded_models",
        new=AsyncMock(return_value=[]),
    ):
        chosen = await resolve_model("fast")

    # settings.litellm_model defaults to "openai/local-model" — already prefixed
    assert chosen == "openai/local-model"
