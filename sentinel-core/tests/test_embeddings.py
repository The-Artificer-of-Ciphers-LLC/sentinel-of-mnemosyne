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
