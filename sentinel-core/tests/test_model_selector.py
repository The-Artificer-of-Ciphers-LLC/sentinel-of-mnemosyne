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

            def _patched_score(task_kind, model_id):
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

    def _patched_score(task_kind, model_id):
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

    def _zero_score(task_kind, model_id):
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

    def _patched_score(task_kind, model_id):
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
