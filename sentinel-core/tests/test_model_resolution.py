"""Tests for model_resolution.resolve_structured_model (fix-score-local-model-
capabilities round 2).

``resolve_structured_model`` is the SINGLE structured-model-resolution
implementation used by ``note_classifier.classify_note`` and every
``six_rs/*`` structured-completion stage. ``probe_classifier_model_ready``
(app/services/model_selector.py) gates destructive vault sweeps on whether
this SAME resolution path would land on a genuinely function-calling-capable
model. If the two paths ever score candidates with different inputs, the
probe could report "ready" while the real resolver lands on a different
(possibly degraded, rule-4 sole-candidate-fallback) model — this file proves
that divergence cannot happen for the scoring inputs (loaded models +
live capability data), and that a live-capability-fetch failure inside
``resolve_structured_model`` degrades gracefully rather than raising.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.model_resolution import resolve_structured_model
from app.services.model_selector import (
    _fetch_live_capabilities as _default_fetch_live_capabilities,
    probe_classifier_model_ready,
    select_model as real_select_model,
    strip_litellm_prefix,
)


@pytest.mark.asyncio
async def test_probe_and_resolve_structured_model_select_same_model_id_for_local_tool_use(
    monkeypatch,
):
    """probe_classifier_model_ready and resolve_structured_model must select the
    SAME model id given identical loaded + live-capability inputs.

    Regression for the divergence introduced by the first round of this fix:
    the probe was updated to fetch live LM Studio capability data, but
    resolve_structured_model (the ACTUAL classify_note / six_rs resolver)
    was not, so a local tool_use-capable model could be reported "ready" by
    the probe while classify_note itself still resolved via the rule-4
    sole-candidate fallback (scoring 0 through the litellm-only path).

    Neither the configured MODEL_NAME nor MODEL_PREFERRED matches the loaded
    model here, so rule 1 (preference) cannot trivially resolve both paths to
    the same answer — this only passes if BOTH paths reach rule 2 (highest
    live-capability-aware score) and agree.
    """
    model_id = "google/gemma-4-31b"

    def handler(request):
        path = request.url.path
        if path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": model_id}]})
        if f"/api/v0/models/{model_id}" in path:
            return httpx.Response(
                200,
                json={
                    "id": model_id,
                    "type": "vlm",
                    "arch": "gemma4",
                    "state": "loaded",
                    "max_context_length": 262144,
                    "loaded_context_length": 71936,
                    "capabilities": ["tool_use"],
                },
            )
        return httpx.Response(404, json={"error": "unmocked"})

    transport = httpx.MockTransport(handler)

    from app.config import settings as real_settings

    monkeypatch.setattr(real_settings, "lmstudio_base_url", "http://lmstudio.test/v1")
    # Deliberately NOT the loaded model — forces both paths past rule 1 into
    # rule 2 (scoring), so this test actually exercises live-capability
    # scoring rather than trivially agreeing via preference match.
    monkeypatch.setattr(real_settings, "model_name", "unrelated-default-model")
    monkeypatch.setattr(real_settings, "model_preferred", None)

    recorded: list[object] = []

    def spy_select_model(*args, **kwargs):
        result = real_select_model(*args, **kwargs)
        recorded.append(result)
        return result

    async def _fetch_live_caps_via_transport(http_client, base_url, model_ids):
        # Route through the SAME fake LM Studio (MockTransport) that the probe
        # is given directly via its injected http_client — proves both paths
        # fetch identical live capability data, not just "probably would."
        async with httpx.AsyncClient(transport=transport) as mock_client:
            return await _default_fetch_live_capabilities(mock_client, base_url, model_ids)

    with patch("app.services.model_selector.select_model", side_effect=spy_select_model):
        async with httpx.AsyncClient(transport=transport) as probe_client:
            probe_ready = await probe_classifier_model_ready(
                probe_client,
                "http://lmstudio.test/v1",
                model_name="unrelated-default-model",
            )
        assert probe_ready is True, "probe must report ready for a local tool_use model"

        resolved_id, _profile, _api_base = await resolve_structured_model(
            get_loaded_models=AsyncMock(return_value=[model_id]),
            select_model=spy_select_model,
            get_profile=AsyncMock(return_value=None),
            fetch_live_capabilities=_fetch_live_caps_via_transport,
        )

    assert len(recorded) == 2, f"expected exactly one select_model call per path; got {recorded}"
    probe_selected_id, resolve_selected_id = recorded
    assert probe_selected_id == resolve_selected_id == model_id, (
        f"probe and resolve_structured_model must select the SAME model id; "
        f"probe selected {probe_selected_id!r}, resolve_structured_model selected "
        f"{resolve_selected_id!r}"
    )
    assert strip_litellm_prefix(resolved_id) == model_id


@pytest.mark.asyncio
async def test_resolve_structured_model_capability_fetch_failure_is_non_fatal(monkeypatch):
    """A live-capability-fetch failure inside resolve_structured_model must NOT
    raise — it must degrade to live_capabilities={} (today's pre-fix,
    litellm-only scoring behavior), mirroring every other except-warn
    fallback already in this function, and must not disturb the existing
    select_model fallback ordering (default/rule-4 still apply normally)."""
    from app.config import settings as real_settings

    monkeypatch.setattr(real_settings, "lmstudio_base_url", "http://lmstudio.test/v1")
    monkeypatch.setattr(real_settings, "model_name", "fallback-model")
    monkeypatch.setattr(real_settings, "model_preferred", None)

    recorded_kwargs: dict = {}

    def _capturing_select_model(task_kind, loaded, **kwargs):
        recorded_kwargs.update(kwargs)
        return real_select_model(task_kind, loaded, **kwargs)

    async def _raising_fetch_live_capabilities(http_client, base_url, model_ids):
        raise httpx.ConnectError("connection refused")

    model_id, profile, api_base = await resolve_structured_model(
        get_loaded_models=AsyncMock(return_value=["fallback-model"]),
        select_model=_capturing_select_model,
        get_profile=AsyncMock(return_value=None),
        fetch_live_capabilities=_raising_fetch_live_capabilities,
    )

    assert recorded_kwargs.get("live_capabilities") == {}, (
        "a capability-fetch failure must degrade to live_capabilities={} "
        "(today's pre-fix behavior) — never propagate the exception, never "
        "leave stale/partial data"
    )
    # Resolution still completed (fell back to rule-4 sole-candidate, exactly
    # as it would have before this fix existed) — never raised.
    assert model_id == "openai/fallback-model"
