"""Behavioral tests for the compose root (app.composition).

Each test CALLS ``build_application`` or ``build_provider_router`` directly and
asserts on observable graph state — no source-grep, no tautologies, no
mock-call-shape-only assertions (Behavioral-Test-Only Rule). Fakes are passed
via explicit kwargs (W1) so typos surface as TypeErrors rather than being
silently swallowed.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.composition import (
    AppGraph,
    build_application,
    build_provider_router,
)
from app.config import Settings
from app.services.provider_router import ProviderRouter


def _settings(**overrides) -> Settings:
    """Build a Settings instance for tests with deterministic defaults.

    Uses a fixed sentinel_api_key (required field) and disables auto-discovery
    so model resolution short-circuits to ``settings.model_name`` and does not
    touch the network.
    """
    base: dict = {
        "sentinel_api_key": "test-key",
        "model_auto_discover": False,
        "model_name": "test-model",
        "embedding_model": "test-embedding-model",
        "lmstudio_base_url": "http://lmstudio.test/v1",
        "ai_provider": "lmstudio",
        "ai_fallback_provider": "none",
        "anthropic_api_key": "",
        "ollama_model": "ollama-test",
        "llamacpp_model": "llamacpp-test",
    }
    base.update(overrides)
    return Settings(**base)


def _empty_models_handler(request: httpx.Request) -> httpx.Response:
    """MockTransport handler that returns empty model lists / 404 for everything.

    Lets ``build_provider_router`` walk through model discovery + profile +
    embedding probe deterministically without any real network. Each branch
    falls into its non-fatal path and the function returns successfully.
    """
    # /v1/models or /api/v0/models — empty list
    if request.url.path.endswith("/models") or "/api/v0/models" in request.url.path:
        return httpx.Response(200, json={"data": []})
    # Anthropic registry
    if request.url.host == "api.anthropic.com":
        return httpx.Response(404, json={"error": "not used in test"})
    return httpx.Response(404, json={"error": "unmocked"})


@pytest.fixture
def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_empty_models_handler))


class _FakeVault:
    """Minimal in-memory vault double — implements only the surface we test."""

    async def read_persona(self) -> str | None:
        return "fake persona"

    async def check_health(self) -> bool:
        return True


# ---- Tests ----


async def test_build_application_uses_provided_vault_fake(http_client):
    """When ``vault=`` kwarg is supplied, the graph holds the same instance."""
    fake_vault = _FakeVault()
    settings = _settings()

    graph = await build_application(settings, http_client, vault=fake_vault)

    assert isinstance(graph, AppGraph)
    assert graph.vault is fake_vault


async def test_build_application_constructs_default_provider_when_not_overridden(
    http_client,
):
    """No ``ai_provider=`` kwarg → composition builds the production ProviderRouter."""
    settings = _settings(ai_provider="lmstudio")

    graph = await build_application(settings, http_client, vault=_FakeVault())

    assert isinstance(graph.ai_provider, ProviderRouter)
    assert graph.ai_provider_name == "lmstudio"
    # The graph should expose all 15 fields populated
    for field in (
        "settings",
        "http_client",
        "model_registry",
        "context_window",
        "lmstudio_stop_sequences",
        "ai_provider",
        "ai_provider_name",
        "vault",
        "embedding_model_loaded",
        "injection_filter",
        "output_scanner",
        "message_processor",
        "module_registry",
        "embeddings",
        "note_classifier_fn",
    ):
        assert getattr(graph, field) is not None or field in (
            "lmstudio_stop_sequences",
            "module_registry",
        )


async def test_build_provider_router_picks_primary_from_settings(http_client):
    """Two distinct settings configurations produce routers with matching ai_provider_name."""
    settings_lm = _settings(ai_provider="lmstudio", ai_fallback_provider="none")
    settings_ollama = _settings(ai_provider="ollama", ai_fallback_provider="none")

    bundle_lm = await build_provider_router(settings_lm, http_client)
    bundle_ollama = await build_provider_router(settings_ollama, http_client)

    assert isinstance(bundle_lm.router, ProviderRouter)
    assert isinstance(bundle_ollama.router, ProviderRouter)
    assert bundle_lm.ai_provider_name == "lmstudio"
    assert bundle_ollama.ai_provider_name == "ollama"
    # Distinct configurations produce distinct router instances
    assert bundle_lm.router is not bundle_ollama.router


async def test_build_application_typo_kwarg_raises_typeerror(http_client):
    """Explicit-kwargs (W1) — a typo like ``vualt=`` must raise TypeError, not be swallowed."""
    settings = _settings()

    with pytest.raises(TypeError):
        # Intentional typo: 'vualt' instead of 'vault'. The signature is
        # explicit-kwargs (no **fakes bag), so Python rejects this at the
        # call boundary — exactly what W1 was designed to ensure.
        await build_application(  # type: ignore[call-arg]
            settings, http_client, vualt=_FakeVault()
        )


# Suppress unused-import warning when running with json available
_ = json
