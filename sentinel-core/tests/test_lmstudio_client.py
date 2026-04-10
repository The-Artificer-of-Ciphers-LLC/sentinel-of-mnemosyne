"""Tests for LM Studio HTTP client (CORE-04)."""
import pytest
import httpx
from httpx import AsyncClient
from app.clients.lmstudio import LMStudioClient, get_context_window


@pytest.fixture
def lmstudio_mock_transport(mock_lmstudio_response, mock_lmstudio_models_response):
    """httpx MockTransport routing LM Studio endpoints to fixture data."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/v1/chat/completions" in path:
            return httpx.Response(200, json=mock_lmstudio_response)
        if "/api/v0/models/" in path:
            return httpx.Response(200, json=mock_lmstudio_models_response)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_lmstudio_client_returns_completion(lmstudio_mock_transport):
    """LM Studio client returns assistant content from mocked completions response."""
    async with AsyncClient(transport=lmstudio_mock_transport, base_url="http://test") as client:
        lm = LMStudioClient(client, "http://test/v1", "test-model")
        result = await lm.complete([{"role": "user", "content": "hello"}])
    assert result == "Hello from mock LM Studio"


async def test_lmstudio_client_fetches_context_window(lmstudio_mock_transport):
    """get_context_window() returns max_context_length from mocked models response."""
    async with AsyncClient(transport=lmstudio_mock_transport, base_url="http://test") as client:
        result = await get_context_window(client, "http://test/v1", "test-model")
    assert result == 8192


async def test_lmstudio_client_returns_4096_default_on_unavailable():
    """get_context_window() returns 4096 when LM Studio is unreachable."""
    transport = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        result = await get_context_window(client, "http://test/v1", "test-model")
    assert result == 4096
