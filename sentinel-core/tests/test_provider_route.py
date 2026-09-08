"""Tests for POST /provider/complete (Phase 42-03, D-09/SC-6).

Thin passthrough to ctx.ai_provider.complete() — no /message pipeline reuse.
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.errors import ProviderUnavailableError
from app.main import app
from app.state import RouteContext

AUTH_HEADERS = {"X-Sentinel-Key": "test-key-for-pytest"}

_VALID_BODY = {"messages": [{"role": "user", "content": "hello"}]}

# Sentinel value distinguishing "attribute absent" from "attribute set to None".
_MISSING = object()


@pytest.fixture
def mock_ai_provider():
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value="Hi there")
    return provider


@pytest.fixture(autouse=True)
def setup_app_state(mock_ai_provider):
    """Seed RouteContext.ai_provider before each test; restore after."""
    orig = getattr(app.state, "route_ctx", _MISSING)
    app.state.route_ctx = RouteContext(
        vault=AsyncMock(),
        ai_provider=mock_ai_provider,
        ai_provider_name="lmstudio",
    )
    yield
    if orig is _MISSING:
        try:
            delattr(app.state, "route_ctx")
        except AttributeError:
            pass
    else:
        app.state.route_ctx = orig


async def test_provider_complete_success(mock_ai_provider):
    """200 with valid key + body returns {content, model} via ctx.ai_provider.complete()."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"content": "Hi there", "model": "lmstudio"}
    mock_ai_provider.complete.assert_awaited_once()
    call_args = mock_ai_provider.complete.call_args
    assert call_args.args[0] == [{"role": "user", "content": "hello"}]


async def test_provider_complete_requires_auth():
    """No X-Sentinel-Key header -> 401 (existing global middleware, no new auth code)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY)

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Unauthorized"}


async def test_provider_complete_no_provider_configured():
    """ctx.ai_provider is None -> 500 'ai_provider not configured'."""
    app.state.route_ctx = RouteContext(vault=AsyncMock(), ai_provider=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 500
    assert resp.json() == {"detail": "ai_provider not configured"}


async def test_provider_complete_503_on_provider_unavailable(mock_ai_provider):
    """ProviderUnavailableError -> 503 with a generic detail; no secrets leaked (T-42-08)."""
    mock_ai_provider.complete = AsyncMock(
        side_effect=ProviderUnavailableError(
            "Both providers failed. api_base=http://secret-lmstudio-host:1234 api_key=sk-super-secret"
        )
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 503
    body_text = resp.text
    assert "secret-lmstudio-host" not in body_text
    assert "sk-super-secret" not in body_text


async def test_provider_complete_422_on_too_many_messages():
    """messages array exceeding the cap is rejected by Pydantic validation (422)."""
    too_many = {"messages": [{"role": "user", "content": "x"}] * 51}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=too_many, headers=AUTH_HEADERS)

    assert resp.status_code == 422


async def test_provider_complete_422_on_content_too_long():
    """A single message exceeding the content-length cap is rejected (422)."""
    too_long = {"messages": [{"role": "user", "content": "x" * 32_001}]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=too_long, headers=AUTH_HEADERS)

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# ADR-0007 step 3 — a task name crosses the wire, and core resolves
# ---------------------------------------------------------------------------


def _seam(*profiles):
    """A real ActiveModel over a real StaticModelSource."""
    from types import SimpleNamespace

    from app.model import ActiveModel, StaticModelSource

    return ActiveModel([StaticModelSource(list(profiles))], SimpleNamespace())


def _profile(model_id: str, *, capabilities=frozenset({"tool_use"})):
    from app.model import ModelProfile

    return ModelProfile(
        model_id=model_id,
        litellm_model=f"openai/{model_id}",
        api_base="http://lmstudio.test/v1",
        context_window=119552,
        capabilities=capabilities,
    )


async def test_task_defaults_to_chat_and_resolves_core_side(mock_ai_provider):
    """No task field behaves exactly as before for the caller: core resolves the
    chat profile and answers. pf2e sends nothing about models."""
    app.state.route_ctx = RouteContext(
        vault=AsyncMock(),
        ai_provider=mock_ai_provider,
        ai_provider_name="lmstudio",
        active_model=_seam(_profile("qwen/qwen3.8-27b")),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 200, resp.text
    resolved = mock_ai_provider.complete.await_args.args[1]
    assert resolved.model_id == "qwen/qwen3.8-27b"
    assert resolved.task_kind == "chat"


async def test_task_structured_resolves_the_structured_profile(mock_ai_provider):
    """`task: "structured"` narrows to a tool-use-capable model.

    Two models are loaded; only one reports tool_use, so the capability filter —
    not a guess — decides. A chat request would be ambiguous between them.
    """
    app.state.route_ctx = RouteContext(
        vault=AsyncMock(),
        ai_provider=mock_ai_provider,
        ai_provider_name="lmstudio",
        active_model=_seam(
            _profile("qwen/qwen3.8-27b"),
            _profile("some/vision-only", capabilities=frozenset()),
        ),
    )
    body = dict(_VALID_BODY, task="structured")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=body, headers=AUTH_HEADERS)

    assert resp.status_code == 200, resp.text
    resolved = mock_ai_provider.complete.await_args.args[1]
    assert resolved.model_id == "qwen/qwen3.8-27b"
    assert resolved.task_kind == "structured"


async def test_unrecognised_task_is_422_before_any_llm_call(mock_ai_provider):
    """Fail before cost, like the message-count and content-length guards.

    Silently falling back to chat would answer a structured request with a chat
    model and let the caller parse prose as JSON.
    """
    body = dict(_VALID_BODY, task="creative")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=body, headers=AUTH_HEADERS)

    assert resp.status_code == 422
    mock_ai_provider.complete.assert_not_called()


async def test_response_model_field_is_the_resolved_model_not_the_provider_name(
    mock_ai_provider,
):
    """Defect B on the HTTP path.

    The configured provider name and the model id are deliberately different
    here: a caller asking core what answered used to get back `lmstudio`.
    """
    app.state.route_ctx = RouteContext(
        vault=AsyncMock(),
        ai_provider=mock_ai_provider,
        ai_provider_name="lmstudio",
        active_model=_seam(_profile("qwen/qwen3.8-27b")),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 200, resp.text
    assert resp.json()["model"] == "qwen/qwen3.8-27b"
    assert resp.json()["model"] != "lmstudio"


async def test_resolution_failure_is_a_503_that_leaks_nothing(mock_ai_provider):
    """An undisambiguatable backend is a 503 with a generic detail — not an
    unhandled 500, not a phantom model, and not an inventory listing.

    Two equally-plausible chat models are loaded and nothing disambiguates them,
    so resolution refuses (ADR decision 4 as amended). The response must not name
    either of them or the api_base, however tempting it is to "help" by saying
    what WAS loaded.
    """
    app.state.route_ctx = RouteContext(
        vault=AsyncMock(),
        ai_provider=mock_ai_provider,
        ai_provider_name="lmstudio",
        active_model=_seam(
            _profile("qwen/qwen3.8-27b"), _profile("google/gemma-4-31b")
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/provider/complete", json=_VALID_BODY, headers=AUTH_HEADERS)

    assert resp.status_code == 503
    body_text = resp.text
    assert "qwen" not in body_text
    assert "gemma" not in body_text
    assert "lmstudio.test" not in body_text
    mock_ai_provider.complete.assert_not_called()
