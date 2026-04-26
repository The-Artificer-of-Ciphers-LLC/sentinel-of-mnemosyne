"""Tests for model registry hybrid fetch + seed fallback (PROV-04)."""
import pytest
import httpx

from app.services.model_registry import build_model_registry


@pytest.fixture
def lmstudio_settings(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    return Settings()


@pytest.fixture
def claude_settings_with_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-sk-ant")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-4-5")
    from app.config import Settings
    return Settings()


@pytest.fixture
def claude_settings_no_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from app.config import Settings
    return Settings()


async def test_lmstudio_registry_uses_fetched_context_window(lmstudio_settings):
    def handler(request):
        return httpx.Response(200, json={"max_context_length": 32768, "id": "test-model"})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        registry = await build_model_registry(lmstudio_settings, client)
    assert "test-model" in registry
    assert registry["test-model"].context_window == 32768


async def test_lmstudio_registry_falls_back_to_seed_on_unavailable(lmstudio_settings):
    def raise_connect_error(request):
        raise httpx.ConnectError("refused")
    transport = httpx.MockTransport(raise_connect_error)
    async with httpx.AsyncClient(transport=transport) as client:
        registry = await build_model_registry(lmstudio_settings, client)
    # local-model is in seed
    assert "local-model" in registry
    # live fetch failed — test-model gets 4096 default
    assert registry.get("test-model") is None or registry["test-model"].context_window == 4096


async def test_claude_registry_skips_live_fetch_without_key(claude_settings_no_key):
    async with httpx.AsyncClient() as client:
        registry = await build_model_registry(claude_settings_no_key, client)
    # Seed models should be present
    assert "claude-haiku-4-5" in registry


async def test_seed_always_present_in_registry(lmstudio_settings):
    def raise_connect_error(request):
        raise httpx.ConnectError("refused")
    transport = httpx.MockTransport(raise_connect_error)
    async with httpx.AsyncClient(transport=transport) as client:
        registry = await build_model_registry(lmstudio_settings, client)
    # Seed contains local-model, claude-haiku-4-5, etc.
    assert "local-model" in registry
    assert "claude-haiku-4-5" in registry


async def test_unknown_provider_returns_seed_only(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "unknown-provider")
    from app.config import Settings
    s = Settings()
    async with httpx.AsyncClient() as client:
        registry = await build_model_registry(s, client)
    assert len(registry) >= 1  # at least seed data


async def test_lmstudio_registry_uses_discovered_model_name(monkeypatch):
    """When /v1/models returns a model, the registry key uses the discovered name, not MODEL_NAME."""
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("MODEL_NAME", "static-name")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def handler(request):
        if "/v1/models" in str(request.url):
            return httpx.Response(200, json={"data": [{"id": "discovered-model"}]})
        if "/api/v0/models" in str(request.url):
            return httpx.Response(200, json={"max_context_length": 65536, "id": "discovered-model"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        registry = await build_model_registry(s, client)
    assert "discovered-model" in registry
    assert registry["discovered-model"].context_window == 65536


async def test_lmstudio_registry_fallback_when_discovery_fails(monkeypatch):
    """When /v1/models fails, registry falls back to MODEL_NAME key."""
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("MODEL_NAME", "static-name")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def raise_connect(request):
        raise httpx.ConnectError("refused")

    transport = httpx.MockTransport(raise_connect)
    async with httpx.AsyncClient(transport=transport) as client:
        registry = await build_model_registry(s, client)
    assert "static-name" in registry


async def test_lmstudio_registry_no_discovery_when_disabled(monkeypatch):
    """When MODEL_AUTO_DISCOVER=false, registry uses MODEL_NAME key without attempting discovery."""
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("MODEL_NAME", "static-name")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "false")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def handler(request):
        if "/api/v0/models" in str(request.url):
            return httpx.Response(200, json={"max_context_length": 8192, "id": "static-name"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        registry = await build_model_registry(s, client)
    assert "static-name" in registry
