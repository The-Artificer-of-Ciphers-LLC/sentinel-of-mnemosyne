"""Tests for the process-wide structured seam handle (ADR-0007 step 4).

``structured_model`` holds no resolution logic — everything here is about the
one property the module exists to create: the five structured call sites share
ONE ``ActiveModel``, so a multi-stage run costs one metadata refresh per TTL
window instead of one per stage plus one per loaded model.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.model import ActiveModel, LMStudioModelSource, ModelProfile, StaticModelSource
from app.services.structured_model import (
    reset_structured_active_model,
    set_structured_active_model,
    structured_profile,
)

BASE_URL = "http://lmstudio.test/v1"


def counting_backend() -> tuple[httpx.AsyncClient, dict[str, int]]:
    """A fake LM Studio that records every request path it is asked for."""
    counts: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        counts[path] = counts.get(path, 0) + 1
        if path.endswith("/api/v1/models"):
            return httpx.Response(404, json={"error": "no v1 on this backend"})
        if path.endswith("/api/v0/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "qwen/qwen3.8-27b",
                            "type": "llm",
                            "arch": "qwen3_5",
                            "state": "loaded",
                            "max_context_length": 262144,
                            "loaded_context_length": 119552,
                            "capabilities": ["tool_use"],
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": "unmocked"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), counts


@pytest.mark.asyncio
async def test_a_multi_stage_run_issues_one_model_list_fetch_per_ttl_window():
    """The ADR's stated latency consequence, made observable.

    ``resolve_structured_model`` fetched per CALL SITE: each of the five stages
    ran its own ``/v1/models`` discovery and then fanned out one
    ``/api/v0/models/{id}`` capability request per loaded model — roughly
    ``1 + N + 1`` round trips per stage. Through the shared seam a whole 6 Rs
    run (Reduce, Reflect, Rethink, Reweave, classify) issues ONE model-list
    fetch, and no per-model request at all.
    """
    client, counts = counting_backend()
    async with client:
        set_structured_active_model(
            ActiveModel(
                [LMStudioModelSource(client, BASE_URL)],
                SimpleNamespace(model_name="qwen/qwen3.8-27b"),
            )
        )

        profiles = [await structured_profile() for _ in range(5)]

    assert all(p.model_id == "qwen/qwen3.8-27b" for p in profiles)
    assert counts.get("/api/v0/models") == 1, (
        f"five stages must share one model-list fetch, got {counts}"
    )
    per_model = [p for p in counts if p.startswith("/api/v0/models/")]
    assert per_model == [], (
        f"the per-model capability fan-out must be gone entirely, got {per_model}"
    )


@pytest.mark.asyncio
async def test_the_ttl_expiring_costs_exactly_one_more_fetch():
    """The window is a refresh interval, not a permanent cache.

    The deleted ``get_loaded_models`` cache had no TTL at all — a model swapped
    in LM Studio stayed invisible for the life of the process, which is the
    defect ADR-0007 opens with.
    """
    client, counts = counting_backend()
    now = [1000.0]
    async with client:
        set_structured_active_model(
            ActiveModel(
                [LMStudioModelSource(client, BASE_URL)],
                SimpleNamespace(model_name="qwen/qwen3.8-27b"),
                clock=lambda: now[0],
                ttl_seconds=60.0,
            )
        )

        await structured_profile()
        await structured_profile()
        assert counts["/api/v0/models"] == 1

        now[0] += 61.0
        await structured_profile()

    assert counts["/api/v0/models"] == 2, "one refresh, not one per call"


@pytest.mark.asyncio
async def test_the_registered_seam_is_the_one_that_answers():
    """Registration is what ``initialize_startup`` does; it must take effect.

    If it did not, the structured path would lazily compose a SECOND seam with
    its own TTL and its own last-known-good — two objects answering one
    question, inside the module whose whole job is that there is one.
    """
    registered = ActiveModel(
        [
            StaticModelSource(
                [
                    ModelProfile(
                        model_id="registered/model",
                        litellm_model="openai/registered/model",
                        api_base=BASE_URL,
                        capabilities=frozenset({"tool_use"}),
                    )
                ]
            )
        ],
        SimpleNamespace(model_name="registered/model"),
    )
    set_structured_active_model(registered)

    profile = await structured_profile()

    assert profile.model_id == "registered/model"
    assert registered.cached_profile("structured") is not None, (
        "the registered seam's own last-known-good must be the one that filled"
    )


@pytest.mark.asyncio
async def test_reset_drops_the_registration():
    """Without a reset the global would carry one test's backend into the next."""
    set_structured_active_model(
        ActiveModel(
            [StaticModelSource([])], SimpleNamespace(model_name="whatever")
        )
    )
    reset_structured_active_model()

    from app.services import structured_model

    assert structured_model._active_model is None
