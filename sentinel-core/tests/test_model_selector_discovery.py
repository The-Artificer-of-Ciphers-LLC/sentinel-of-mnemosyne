"""Tests for ``probe_embedding_model_loaded`` and AI_PROVIDER validation.

Formerly the ``discover_active_model`` integration suite. ADR-0007 step 4
deleted that function together with ``select_model`` and ``_score``; the twelve
cases that drove them are enumerated in 03-SUMMARY.md, each with the successor
in ``tests/test_model.py`` that now holds its guarantee. What remains here is
the part that never depended on model SELECTION at all: the embedding probe
(untouched per ADR decision 5 — the embedding model is OBSERVED, never
re-pointed) and the Settings-level rejection of an unknown AI_PROVIDER.
"""
import pytest
import httpx

from app.services.model_selector import probe_embedding_model_loaded


# --- 260502-1zv D-02: probe_embedding_model_loaded ---


async def test_probe_embedding_loaded_true_when_state_loaded():
    """LM Studio /api/v0/models returns the configured embedding model with
    state="loaded" and type="embeddings" → probe returns True."""
    captured: dict[str, str] = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "some-llm",
                        "type": "llm",
                        "state": "loaded",
                    },
                    {
                        "id": "text-embedding-nomic-embed-text-v1.5",
                        "type": "embeddings",
                        "state": "loaded",
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_embedding_model_loaded(
            client,
            "http://test-lmstudio/v1",
            "text-embedding-nomic-embed-text-v1.5",
        )

    assert result is True
    # Probe hits /api/v0/models, not /v1/models
    assert captured["url"].endswith("/api/v0/models")


async def test_probe_embedding_loaded_false_when_state_not_loaded():
    """Same fixture but state="not-loaded" → probe returns False."""
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "text-embedding-nomic-embed-text-v1.5",
                        "type": "embeddings",
                        "state": "not-loaded",
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_embedding_model_loaded(
            client,
            "http://test-lmstudio/v1",
            "text-embedding-nomic-embed-text-v1.5",
        )

    assert result is False


async def test_probe_embedding_loaded_false_on_http_error():
    """httpx.RequestError during probe → False (graceful degrade — never raises)."""
    def raise_connect(request):
        raise httpx.ConnectError("refused")

    transport = httpx.MockTransport(raise_connect)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_embedding_model_loaded(
            client,
            "http://test-lmstudio/v1",
            "text-embedding-nomic-embed-text-v1.5",
        )

    assert result is False


async def test_probe_embedding_strips_openai_prefix():
    """Caller may pass an openai/-prefixed id; probe strips before comparing
    against LM Studio's bare id field."""
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "text-embed-x",
                        "type": "embeddings",
                        "state": "loaded",
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_embedding_model_loaded(
            client,
            "http://test-lmstudio/v1",
            "openai/text-embed-x",
        )

    assert result is True


async def test_probe_embedding_loaded_false_when_only_llm_loaded():
    """A loaded LLM with the same id but type='llm' must not satisfy the
    embedding probe — both type AND state must match."""
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "text-embedding-nomic-embed-text-v1.5",
                        "type": "llm",
                        "state": "loaded",
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_embedding_model_loaded(
            client,
            "http://test-lmstudio/v1",
            "text-embedding-nomic-embed-text-v1.5",
        )

    assert result is False


def test_ai_provider_rejects_unknown_value_at_settings_construction(monkeypatch) -> None:
    """ai_provider is a validated Literal — an unrecognized value fails fast at
    Settings() construction with a pydantic ValidationError.

    ADR-0007 step 4 deleted the three provider-keyed tables in
    ``build_provider_router`` whose Pitfall-1/2/3 fixes existed to stop an
    unknown provider silently adopting another backend's model or base URL.
    This is the guarantee that made deleting them safe: an unknown value never
    reaches composition, because a Settings carrying one cannot be built.
    """
    import pydantic

    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("AI_PROVIDER", "totally-unknown-provider")
    from app.config import Settings

    with pytest.raises(pydantic.ValidationError):
        Settings()
