"""Tests for app.clients.embeddings.

Behavioral coverage:
- D-03: ``embed_texts`` resolves the embedding model id from
  ``settings.embedding_model`` at call time (single source of truth).
- D-01 (added in Task 3): ``embed_texts`` translates litellm's
  "No models loaded" BadRequestError into ``EmbeddingModelUnavailable``;
  unrelated BadRequestErrors propagate untouched.
"""
from __future__ import annotations


import pytest


@pytest.mark.asyncio
async def test_embedding_model_uses_settings(monkeypatch):
    """D-03: when no explicit model= is passed, embed_texts resolves the
    model id via settings.embedding_model and prepends the openai/ prefix
    at the call site."""
    from app.clients import embeddings as embeddings_module
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_model", "test-embed-model")

    captured: dict[str, object] = {}

    async def _fake_aembedding(**kwargs):
        captured.update(kwargs)
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    monkeypatch.setattr(embeddings_module.litellm, "aembedding", _fake_aembedding)

    result = await embeddings_module.embed_texts(
        ["hello"], api_base="http://localhost:1234/v1"
    )

    assert captured["model"] == "openai/test-embed-model"
    assert captured["input"] == ["hello"]
    assert captured["api_base"] == "http://localhost:1234/v1"
    assert result == [[0.1, 0.2, 0.3]]


@pytest.mark.asyncio
async def test_explicit_model_param_wins_over_settings(monkeypatch):
    """D-03 corollary: callers passing model= explicitly bypass the
    settings lookup. Protects vault_sweeper-style call sites that may want
    to override per-invocation in the future."""
    from app.clients import embeddings as embeddings_module
    from app.config import settings

    monkeypatch.setattr(settings, "embedding_model", "test-embed-model")

    captured: dict[str, object] = {}

    async def _fake_aembedding(**kwargs):
        captured.update(kwargs)
        return {"data": [{"embedding": [0.0]}]}

    monkeypatch.setattr(embeddings_module.litellm, "aembedding", _fake_aembedding)

    await embeddings_module.embed_texts(
        ["hi"], api_base="http://x", model="openai/explicit-override"
    )

    assert captured["model"] == "openai/explicit-override"


@pytest.mark.asyncio
async def test_no_models_loaded_raises_typed_error(monkeypatch):
    """D-01: a litellm BadRequestError whose message contains "No models
    loaded" is translated to EmbeddingModelUnavailable, with the
    configured model id embedded in the new exception's message."""
    import litellm

    from app.clients import embeddings as embeddings_module
    from app.clients.embeddings import EmbeddingModelUnavailable

    async def _raise_no_models_loaded(**kwargs):
        raise litellm.BadRequestError(
            message="No models loaded. Please load a model.",
            model=kwargs.get("model", ""),
            llm_provider="openai",
        )

    monkeypatch.setattr(
        embeddings_module.litellm, "aembedding", _raise_no_models_loaded
    )

    with pytest.raises(EmbeddingModelUnavailable) as excinfo:
        await embeddings_module.embed_texts(
            ["hello"],
            api_base="http://localhost:1234/v1",
            model="openai/some-model-id",
        )

    assert "openai/some-model-id" in str(excinfo.value)
    assert "lms load" in str(excinfo.value)
    # __cause__ preserved via `raise ... from exc`
    assert isinstance(excinfo.value.__cause__, litellm.BadRequestError)


@pytest.mark.asyncio
async def test_other_bad_request_passes_through(monkeypatch):
    """D-01: a BadRequestError that is NOT the "No models loaded" sentinel
    propagates untouched — we don't want to swallow genuine bad-request
    bugs (malformed input, wrong endpoint, etc.) under a generic typed
    exception."""
    import litellm

    from app.clients import embeddings as embeddings_module
    from app.clients.embeddings import EmbeddingModelUnavailable

    async def _raise_malformed(**kwargs):
        raise litellm.BadRequestError(
            message="malformed request: invalid input shape",
            model=kwargs.get("model", ""),
            llm_provider="openai",
        )

    monkeypatch.setattr(
        embeddings_module.litellm, "aembedding", _raise_malformed
    )

    with pytest.raises(litellm.BadRequestError) as excinfo:
        await embeddings_module.embed_texts(
            ["hello"], api_base="http://x", model="openai/m"
        )

    # Specifically NOT translated to EmbeddingModelUnavailable
    assert not isinstance(excinfo.value, EmbeddingModelUnavailable)
    assert "malformed request" in str(excinfo.value)
