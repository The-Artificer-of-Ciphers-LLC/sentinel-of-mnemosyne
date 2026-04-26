"""Tests for discover_active_model integration in sentinel-core."""
import pytest
import httpx

from app.services.model_selector import discover_active_model, _reset_cache_for_tests


@pytest.fixture(autouse=True)
def clear_model_cache():
    """Reset the module-level cache between tests."""
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


@pytest.fixture
def discovery_off_settings(monkeypatch):
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "false")
    monkeypatch.setenv("MODEL_NAME", "local-model")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    return Settings()


@pytest.fixture
def discovery_on_settings(monkeypatch):
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "local-model")
    monkeypatch.setenv("MODEL_PREFERRED", "")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    return Settings()


async def test_discovery_off_returns_model_name_prefixed(discovery_off_settings):
    """MODEL_AUTO_DISCOVER=false returns 'openai/{model_name}' without HTTP."""
    async with httpx.AsyncClient() as client:
        result = await discover_active_model(discovery_off_settings, client)
    assert result == "openai/local-model"


async def test_discovery_off_no_double_prefix(monkeypatch):
    """model_name already containing '/' must not get double prefix."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "false")
    monkeypatch.setenv("MODEL_NAME", "openai/some-model")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    from app.config import Settings
    s = Settings()
    async with httpx.AsyncClient() as client:
        result = await discover_active_model(s, client)
    assert result == "openai/some-model"
    assert "openai/openai/" not in result


async def test_discovery_on_single_model(discovery_on_settings):
    """discover_active_model with /v1/models returning ['Qwen2.5-14B'] → 'openai/Qwen2.5-14B'."""
    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "Qwen2.5-14B"}]})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(discovery_on_settings, client)
    assert result == "openai/Qwen2.5-14B"


async def test_discovery_honors_model_preferred(monkeypatch):
    """model_preferred in loaded list is honored."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "other-model")
    monkeypatch.setenv("MODEL_PREFERRED", "Qwen2.5-14B")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "Qwen2.5-14B"}, {"id": "other-model"}]})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)
    assert result == "openai/Qwen2.5-14B"


async def test_discovery_unreachable_falls_back(monkeypatch):
    """ConnectError during discovery → non-fatal fallback to 'openai/{model_name}'."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "fallback-model")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def raise_connect(request):
        raise httpx.ConnectError("refused")
    transport = httpx.MockTransport(raise_connect)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)
    assert result == "openai/fallback-model"


async def test_discovery_empty_models_falls_back(monkeypatch):
    """Empty /v1/models data → non-fatal fallback."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "fallback-model")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def handler(request):
        return httpx.Response(200, json={"data": []})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)
    assert result == "openai/fallback-model"


async def test_discovery_ollama_provider(monkeypatch):
    """ai_provider='ollama' → returns 'ollama/{name}'."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "qwen2.5:14b")
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://test-ollama")
    from app.config import Settings
    s = Settings()

    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "qwen2.5:14b"}]})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)
    assert result == "ollama/qwen2.5:14b"


async def test_discovery_no_double_prefix_with_slash_in_discovered(monkeypatch):
    """Discovered model name already containing '/' must not get double prefix."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "local-model")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "openai/already-prefixed"}]})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)
    assert result == "openai/already-prefixed"
    assert result.count("openai/") == 1
