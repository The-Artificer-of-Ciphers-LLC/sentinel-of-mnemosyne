"""Shared test fixtures for Sentinel Core tests."""
import os
from types import SimpleNamespace
from typing import Any, Callable

import httpx
import pytest
from unittest.mock import AsyncMock

# Set env vars before any app import so pydantic-settings picks them up
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

from app.model import (  # noqa: E402
    ActiveModel,
    LMStudioModelSource,
    ModelProfile,
    StaticModelSource,
    static_model_source,
)
from app.state import RouteContext  # noqa: E402

# ---------------------------------------------------------------------------
# The shared route-context builder (ADR-0007 step 3).
#
# Three test modules — test_message.py, test_auth.py and
# test_integration_obsidian_llm.py — each carried their own hand-rolled
# `_LazyRouteCtx` class: a duck-typed stand-in with a handful of properties and
# no ActiveModel. They are replaced by this one builder, which returns a REAL
# `RouteContext` around a REAL `ActiveModel` over a REAL `StaticModelSource`.
#
# That is the ADR's stated reason for `StaticModelSource` being a first-class
# adapter rather than a test double: the substitute for a live backend is a
# supported adapter, so tests exercise the same resolution code production runs
# instead of a fake that can drift away from it — which is precisely how the
# three copies came to disagree with each other.
# ---------------------------------------------------------------------------


class LazyStateProxy:
    """Forwards every attribute access to whatever ``getter()`` returns NOW.

    `RouteContext` is a frozen dataclass, so a field pinned at fixture time
    cannot follow a test that reassigns ``app.state.vault`` mid-test and then
    asserts against the new object. This proxy keeps that (long-standing, widely
    relied on) test idiom working without reintroducing a hand-rolled context:
    the laziness moves into the VALUE, and the context itself stays real.
    """

    def __init__(self, getter: Callable[[], Any]) -> None:
        self._getter = getter

    def __getattr__(self, name: str) -> Any:
        # Only reached when normal lookup fails, so `_getter` (in __dict__)
        # never recurses through here.
        return getattr(self._getter(), name)


class AppStateModelSource:
    """A real ``ModelSource`` whose profile reflects the CURRENT test state.

    Delegates to a real ``StaticModelSource`` rebuilt on every refresh, so a test
    that changes the context window mid-test reaches the seam the way a live
    model swap would — through resolution, not around it. ``ActiveModel``'s TTL
    means one refresh per test in practice.
    """

    def __init__(
        self,
        *,
        model_id: str = "test-model",
        api_base: str | None = "http://lmstudio.test/v1",
        context_window_provider: Callable[[], int] | None = None,
        context_window: int = 8192,
        stop_sequences: tuple[str, ...] = (),
        capabilities: frozenset[str] = frozenset({"tool_use"}),
    ) -> None:
        self._model_id = model_id
        self._api_base = api_base
        self._window = context_window_provider or (lambda: context_window)
        self._stop_sequences = stop_sequences
        self._capabilities = capabilities

    async def candidates(self):
        profile = ModelProfile(
            model_id=self._model_id,
            litellm_model=f"openai/{self._model_id}",
            api_base=self._api_base,
            context_window=int(self._window()),
            stop_sequences=self._stop_sequences,
            capabilities=self._capabilities,
        )
        return await StaticModelSource([profile]).candidates()


def build_test_active_model(
    *,
    model_id: str = "test-model",
    api_base: str | None = "http://lmstudio.test/v1",
    context_window_provider: Callable[[], int] | None = None,
    context_window: int = 8192,
    stop_sequences: tuple[str, ...] = (),
    settings: Any = None,
) -> ActiveModel:
    """A real ``ActiveModel`` serving one config-derived profile."""
    source = AppStateModelSource(
        model_id=model_id,
        api_base=api_base,
        context_window_provider=context_window_provider,
        context_window=context_window,
        stop_sequences=stop_sequences,
    )
    return ActiveModel([source], settings if settings is not None else SimpleNamespace())


def build_test_route_context(
    *,
    vault: Any,
    processor: Any = None,
    settings: Any = None,
    classify: Any = None,
    recall: Any = None,
    ai_provider: Any = None,
    ai_provider_name: str | None = None,
    active_model: ActiveModel | None = None,
    context_window: int = 8192,
    lmstudio_stop_sequences: list[str] | None = None,
    http_client: Any = None,
) -> RouteContext:
    """Build a real ``RouteContext`` for route-level tests.

    ``context_window`` and ``lmstudio_stop_sequences`` are the two scalars
    ADR-0007 step 4 removes from ``RouteContext``; they are still accepted here
    because ``build_message_request`` still reads them. When ``active_model`` is
    wired the chat path resolves through it and these two are inert — which is
    the whole point of passing a real seam.
    """
    kwargs: dict[str, Any] = {
        "vault": vault,
        "settings": settings,
        "context_window": context_window,
        "lmstudio_stop_sequences": lmstudio_stop_sequences or [],
        "active_model": active_model,
        "ai_provider": ai_provider,
        "ai_provider_name": ai_provider_name,
        "http_client": http_client,
    }
    if processor is not None:
        kwargs["processor"] = processor
    if classify is not None:
        kwargs["classify"] = classify
    if recall is not None:
        kwargs["recall"] = recall
    return RouteContext(**kwargs)


# ---------------------------------------------------------------------------
# The two backend failure modes ADR-0007 decision 4 (as amended 2026-09-08)
# keeps apart, as seams the five structured call sites can be pointed at.
#
# They are helpers rather than fixtures because each call site asserts on BOTH
# in the same module, and a fixture would make the pairing implicit.
# ---------------------------------------------------------------------------


class _UnreachableSource:
    """A ModelSource standing in for a backend that is simply not there."""

    async def candidates(self):
        raise httpx.ConnectError("connection refused")


async def unreachable_structured_seam(model_id: str = "local-model") -> ActiveModel:
    """UNREACHABLE: the live source raises, the static one answers, nothing raises.

    Built over the REAL ``static_model_source`` — not a hand-made profile —
    because the guarantee under test is that a config-derived candidate is
    usable for structured work when no backend could be asked. A fake profile
    with ``tool_use`` set would assert nothing.
    """
    config = SimpleNamespace(
        ai_provider="lmstudio",
        model_name=model_id,
        lmstudio_base_url="http://lmstudio.test/v1",
        model_preferred=None,
    )
    return ActiveModel(
        [_UnreachableSource(), await static_model_source(config, provider="lmstudio")],
        config,
    )


def ambiguous_structured_seam() -> ActiveModel:
    """AMBIGUOUS LIVE: two equally-capable loaded models and nothing to choose.

    ``for_task("structured")`` RAISES here. Configuration may disambiguate among
    loaded candidates; it may not name one, and there is nothing to name.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/v1/models"):
            return httpx.Response(404, json={"error": "no v1"})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": name,
                        "type": "llm",
                        "arch": "qwen3_5",
                        "state": "loaded",
                        "max_context_length": 32768,
                        "capabilities": ["tool_use"],
                    }
                    for name in ("first/capable", "second/capable")
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ActiveModel(
        [LMStudioModelSource(client, "http://lmstudio.test/v1")],
        SimpleNamespace(model_name="", model_preferred=None),
    )


@pytest.fixture(autouse=True)
def reset_structured_model_seam():
    """Drop the process-wide structured seam around every test.

    ``composition.initialize_startup`` registers one so the five structured
    call sites share the chat path's ``ActiveModel``. A process global that
    survived a test would let one test's backend answer another's resolution —
    the same cross-contamination the deleted module-level ``_model_cache`` used
    to cause, arriving by a different door.
    """
    from app.services.structured_model import reset_structured_active_model

    reset_structured_active_model()
    yield
    reset_structured_active_model()


@pytest.fixture
def mock_lmstudio_response():
    """Mock response from LM Studio /v1/chat/completions."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from mock LM Studio"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
    }


@pytest.fixture
def mock_lmstudio_models_response():
    """Mock response from LM Studio /api/v0/models/{model}."""
    return {"max_context_length": 8192, "id": "test-model"}


@pytest.fixture
def mock_ai_provider():
    """Mock AIProvider (ProviderRouter) for tests — returns canned response."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value="Test AI response")
    return provider
