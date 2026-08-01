"""Tests for probe_classifier_model_ready (40-04 Task 2).

Tests the fail-closed classifier readiness probe that mirrors the structured
select_model path used by classify_note. The probe returns True ONLY when a
genuinely-loaded model scores for the 'structured' task kind — a defaulted or
last-resort (rule 4/5) selection is never reported as ready.
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.services.model_selector import _reset_cache_for_tests


@pytest.fixture(autouse=True)
def reset_model_cache():
    """Clear the module-level model cache between tests."""
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


# --- Helper: a handler that returns loaded models from /v1/models ---


def _v1_models_handler(models: list[dict]):
    """Return a MockTransport handler that serves /v1/models with the given model list."""

    def handler(request):
        if "/models" in request.url.path:
            return httpx.Response(200, json={"data": models})
        return httpx.Response(404, json={"error": "unmocked"})

    return handler


# Model stubs
_FC_MODEL = {"id": "function-calling-model"}  # will be patched to score > 0
_NO_FC_MODEL = {"id": "no-function-calling-model"}  # will NOT score for structured


async def _probe(
    client,
    models: list[dict],
    *,
    model_name: str = "default-model",
    model_preferred: str | None = None,
    patch_score_for: str | None = None,
):
    """Run probe_classifier_model_ready with a fake HTTP client serving ``models``."""
    from app.services.model_selector import probe_classifier_model_ready

    transport = httpx.MockTransport(_v1_models_handler(models))
    async with httpx.AsyncClient(transport=transport) as http_client:
        if patch_score_for:
            # Make the named model score > 0 for 'structured'
            original_score = __import__(
                "app.services.model_selector", fromlist=["_score"]
            )._score

            def _patched_score(task_kind, model_id, live_capabilities=None):
                if task_kind == "structured" and model_id == patch_score_for:
                    return 10000
                return 0

            with patch(
                "app.services.model_selector._score", side_effect=_patched_score
            ):
                return await probe_classifier_model_ready(
                    http_client,
                    "http://lmstudio.test/v1",
                    model_name=model_name,
                    model_preferred=model_preferred,
                )
        else:
            return await probe_classifier_model_ready(
                http_client,
                "http://lmstudio.test/v1",
                model_name=model_name,
                model_preferred=model_preferred,
            )


# --- Tests ---


@pytest.mark.asyncio
async def test_probe_classifier_ready_true_when_genuinely_loaded_and_scoring():
    """A loaded model that scores > 0 for 'structured' → probe returns True."""
    from app.services.model_selector import probe_classifier_model_ready

    models = [{"id": "my-fc-model"}]

    def handler(request):
        if "/models" in request.url.path:
            return httpx.Response(200, json={"data": models})
        return httpx.Response(404, json={})

    def _patched_score(task_kind, model_id, live_capabilities=None):
        if task_kind == "structured" and model_id == "my-fc-model":
            return 10000
        return 0

    with patch("app.services.model_selector._score", side_effect=_patched_score):
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            result = await probe_classifier_model_ready(
                client,
                "http://lmstudio.test/v1",
                model_name="my-fc-model",
            )

    assert result is True, "probe must return True for a loaded, structured-capable model"


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_when_no_models_loaded():
    """Empty loaded list → probe returns False.

    This is the fail-closed case: select_model with a default would still return
    the default (rule 5), but the probe must NOT treat a defaulted selection as ready.
    This is the decisive round-2 case: a degraded classifier can never be reported ready.
    """
    from app.services.model_selector import probe_classifier_model_ready

    def handler(request):
        if "/models" in request.url.path:
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_classifier_model_ready(
            client,
            "http://lmstudio.test/v1",
            model_name="some-default-model",
        )

    assert result is False, (
        "probe must return False when no models loaded — a rule-5 defaulted "
        "selection is not 'ready' (fail-closed)"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_when_loaded_model_scores_zero():
    """Loaded model that scores 0 for 'structured' (rule-4 last-resort) → probe returns False.

    This is the DECISIVE round-2 case: select_model returns the model via rule 4
    (loaded[0] fallback) even though no model genuinely scores for the structured
    task kind. The probe must fail closed in this case — a non-scored selection
    is NOT reported ready.
    """
    from app.services.model_selector import probe_classifier_model_ready

    # One model loaded, but it scores 0 for 'structured' (no function calling)
    models = [{"id": "no-fc-model"}]

    def handler(request):
        if "/models" in request.url.path:
            return httpx.Response(200, json={"data": models})
        return httpx.Response(404, json={})

    def _zero_score(task_kind, model_id, live_capabilities=None):
        # No model scores for structured
        return 0

    with patch("app.services.model_selector._score", side_effect=_zero_score):
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            result = await probe_classifier_model_ready(
                client,
                "http://lmstudio.test/v1",
                model_name="no-fc-model",
            )

    assert result is False, (
        "probe must return False when the only loaded model scores 0 for 'structured' "
        "(rule-4 last-resort) — a non-scored selection is not ready"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_on_http_error():
    """httpx / network failure → False (graceful degrade — never raises)."""
    from app.services.model_selector import probe_classifier_model_ready

    def raise_connect(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(raise_connect)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_classifier_model_ready(
            client,
            "http://lmstudio.test/v1",
            model_name="test-model",
        )

    assert result is False, "probe must return False on HTTP error, never raise"


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_on_json_error():
    """JSON-decode failure → False (graceful degrade)."""
    from app.services.model_selector import probe_classifier_model_ready

    def bad_json_handler(request):
        return httpx.Response(200, content=b"not-json-at-all{{{{")

    transport = httpx.MockTransport(bad_json_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_classifier_model_ready(
            client,
            "http://lmstudio.test/v1",
            model_name="test-model",
        )

    assert result is False, "probe must return False on JSON parse error, never raise"


@pytest.mark.asyncio
async def test_probe_classifier_ready_true_when_preference_honored():
    """model_preferred names a loaded, structured-capable model → probe returns True
    via the preference rule (rule 1).

    This mirrors what classify_note would actually select when a preferred model is
    configured and that model is both loaded and function-calling capable.
    """
    from app.services.model_selector import probe_classifier_model_ready

    models = [{"id": "preferred-fc-model"}, {"id": "other-model"}]

    def handler(request):
        if "/models" in request.url.path:
            return httpx.Response(200, json={"data": models})
        return httpx.Response(404, json={})

    def _patched_score(task_kind, model_id, live_capabilities=None):
        if task_kind == "structured" and model_id == "preferred-fc-model":
            return 10000
        return 0

    with patch("app.services.model_selector._score", side_effect=_patched_score):
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            result = await probe_classifier_model_ready(
                client,
                "http://lmstudio.test/v1",
                model_name="default-model",
                model_preferred="preferred-fc-model",
            )

    assert result is True, (
        "probe must return True when model_preferred names a loaded, "
        "structured-capable model (rule-1 preference honored)"
    )


# ---------------------------------------------------------------------------
# fix-score-local-model-capabilities Task 1: live LM Studio capability scoring
#
# litellm.get_model_info()/supports_function_calling() only know about a
# static CLOUD registry — they have no entry for LM Studio-style local model
# ids (e.g. "google/gemma-4-31b"), so `_score` unconditionally returned 0 for
# every local model, which made `probe_classifier_model_ready` permanently
# report "not ready" and silently disabled destructive vault sweeps on any
# local-LLM deployment (measured live: dry_run=false sweep moved 0/26 files).
#
# These tests exercise the REAL `_score`/`select_model` path (no patching of
# `_score`) against a fake LM Studio serving both /v1/models (loaded list)
# and /api/v0/models/{id} (live capability data), matching the confirmed
# production response shape.
# ---------------------------------------------------------------------------


def _lmstudio_v1_and_v0_handler(model_id: str, v0_response: dict | None, *, v0_status: int = 200):
    """Return a MockTransport handler serving both /v1/models and
    /api/v0/models/{model_id} distinctly, mirroring real LM Studio's two
    endpoints (probe_classifier_model_ready discovers via /v1/models;
    get_model_capabilities_from_lmstudio fetches capability data via
    /api/v0/models/{id})."""

    def handler(request):
        path = request.url.path
        if path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": model_id}]})
        if f"/api/v0/models/{model_id}" in path:
            if v0_response is None:
                return httpx.Response(v0_status, json={"error": "not found"})
            return httpx.Response(v0_status, json=v0_response)
        return httpx.Response(404, json={"error": "unmocked"})

    return handler


@pytest.mark.asyncio
async def test_probe_classifier_ready_true_for_local_model_advertising_tool_use():
    """A local (LM Studio) model id that LM Studio reports as loaded with
    capabilities=["tool_use"] must score > 0 for 'structured' and the probe
    must report ready — the exact bug this fix addresses."""
    from app.services.model_selector import probe_classifier_model_ready

    model_id = "google/gemma-4-31b"
    handler = _lmstudio_v1_and_v0_handler(
        model_id,
        {
            "id": model_id,
            "type": "vlm",
            "arch": "gemma4",
            "state": "loaded",
            "max_context_length": 262144,
            "loaded_context_length": 71936,
            "capabilities": ["tool_use"],
        },
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_classifier_model_ready(
            client,
            "http://lmstudio.test/v1",
            model_name=model_id,
        )

    assert result is True, (
        "a loaded local model advertising tool_use must score > 0 for "
        "'structured' via live LM Studio capability data, not litellm's "
        "static cloud registry"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_for_local_model_without_tool_use():
    """A local model LM Studio reports as loaded but WITHOUT tool_use in its
    capabilities must still score 0 for 'structured' — fail-closed preserved.
    The fix must not become permissive for genuinely incapable models."""
    from app.services.model_selector import probe_classifier_model_ready

    model_id = "some-community/non-function-calling-model"
    handler = _lmstudio_v1_and_v0_handler(
        model_id,
        {
            "id": model_id,
            "type": "llm",
            "arch": "llama3",
            "state": "loaded",
            "max_context_length": 8192,
            "loaded_context_length": 8192,
            "capabilities": [],  # no tool_use
        },
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_classifier_model_ready(
            client,
            "http://lmstudio.test/v1",
            model_name=model_id,
        )

    assert result is False, (
        "a loaded local model without tool_use must still score 0 for "
        "'structured' — the live-capability fix must not weaken fail-closed "
        "behavior for genuinely incapable models"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_when_capability_endpoint_unreachable():
    """/v1/models lists a model as loaded, but LM Studio's /api/v0/models/{id}
    capability endpoint is unreachable (or the model is absent from it) →
    no live capability data → falls through to litellm's static registry,
    which has no entry for the local id either → probe still reports False
    (fail-closed preserved end-to-end, not just when /v1/models itself fails)."""
    from app.services.model_selector import probe_classifier_model_ready

    model_id = "mlx-community/some-local-model-8bit"

    def handler(request):
        path = request.url.path
        if path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": model_id}]})
        if f"/api/v0/models/{model_id}" in path:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(404, json={"error": "unmocked"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_classifier_model_ready(
            client,
            "http://lmstudio.test/v1",
            model_name=model_id,
        )

    assert result is False, (
        "an unreachable/absent capability endpoint must never grant a "
        "permissive default — the probe must still fail closed"
    )


def test_score_cloud_model_via_litellm_unchanged():
    """A well-known cloud model id (present in litellm's static registry)
    must keep scoring via litellm exactly as before — with no live_capabilities
    argument (existing sync callers), and even when a live_capabilities dict
    is supplied but doesn't contain this model id (it isn't a local model)."""
    from app.services.model_selector import _score

    score_without_live_caps = _score("structured", "gpt-4o")
    assert score_without_live_caps > 0, (
        "cloud model 'gpt-4o' must keep scoring > 0 for 'structured' via "
        "litellm — this must be unaffected by the local-capability fix"
    )

    # Presence of an (unrelated) live_capabilities mapping must not change
    # the cloud model's score — it isn't in the mapping, so _score falls
    # through to the litellm path exactly as when live_capabilities=None.
    score_with_unrelated_live_caps = _score(
        "structured",
        "gpt-4o",
        {"google/gemma-4-31b": {"max_tokens": 262144, "supports_function_calling": True}},
    )
    assert score_with_unrelated_live_caps == score_without_live_caps, (
        "an unrelated live_capabilities mapping must not change cloud model scoring"
    )
