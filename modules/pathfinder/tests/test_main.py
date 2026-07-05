"""Tests for app.main's startup resilience helper (T-lmstudio-provider-switch).

_build_rules_index_safely is the fix for the fail-fast bug where an unreachable
or embeddings-incompatible LITELLM_API_BASE crashed the entire pf2e-module at
FastAPI startup (build_rules_index -> embed_texts raised with no try/except,
propagating out of lifespan -> ASGI startup failure -> Docker restart-loop).

These tests exercise the helper directly rather than the full lifespan() ASGI
context manager (no existing test infra in this suite stands up app.main's
lifespan — see conftest.py — so this keeps the regression coverage focused and
fast without introducing a new heavyweight integration harness).
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import asyncio

import pytest

from app.main import _build_rules_index_safely


async def test_degrades_to_none_when_embedding_build_raises(caplog):
    """Any exception from build_fn (unreachable host, 405 unsupported endpoint,
    malformed embeddings shape, etc.) is caught and logged — NOT re-raised — so
    lifespan can continue starting the rest of the module."""
    async def _failing_build(chunks, embed_fn):
        raise RuntimeError("405 Method Not Allowed — backend has no /v1/embeddings")

    with caplog.at_level("ERROR"):
        result = await _build_rules_index_safely(_failing_build, ["chunk-a"], object())

    assert result is None
    assert any("embedding index build failed" in rec.message for rec in caplog.records)


async def test_returns_built_index_on_success():
    """When build_fn succeeds, its return value passes through unchanged."""
    sentinel_index = object()

    async def _succeeding_build(chunks, embed_fn):
        assert chunks == ["chunk-a", "chunk-b"]
        return sentinel_index

    result = await _build_rules_index_safely(_succeeding_build, ["chunk-a", "chunk-b"], object())

    assert result is sentinel_index


async def test_does_not_swallow_cancellation():
    """asyncio.CancelledError must propagate — this helper only degrades on
    genuine build failures, not on task cancellation during shutdown."""
    async def _cancelled_build(chunks, embed_fn):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await _build_rules_index_safely(_cancelled_build, [], object())
