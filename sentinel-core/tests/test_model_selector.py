"""Tests for probe_classifier_model_ready — the destructive-sweep gate.

This probe decides whether a live (non-dry-run) vault sweep may mutate the
vault: ``routes/note.py`` re-evaluates it immediately before EACH destructive
move. Everything here is a fail-closed assertion, and a case that starts
reporting "ready" where it previously reported "not ready" is a regression even
if the suite is green.

ADR-0007 rewired the probe onto the Active model seam. The mechanism changed —
it used to discover from ``/v1/models``, fan out one ``/api/v0/models/{id}``
capability fetch per loaded model, and judge the result with ``_score``; it now
asks ``ActiveModel.for_task("structured")`` and reads ``tool_use`` straight off
the resolved profile. Every behavioural case below is the one it guarded
before, re-expressed against the real backend payloads instead of a patched
scoring function. Four cases are new: an absent-capabilities entry, an operator
pin that wins the ladder without being capable, a resolution that RAISES, and
probe/resolver parity.
"""
from __future__ import annotations

import httpx
import pytest

from app.services.model_selector import (
    _reset_cache_for_tests,
    probe_classifier_model_ready,
)

BASE_URL = "http://lmstudio.test/v1"


@pytest.fixture(autouse=True)
def reset_model_cache():
    """Clear the module-level model cache between tests."""
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


# --- Helpers ---------------------------------------------------------------


def v0_entry(model_id: str, *, tool_use: bool = True, loaded: bool = True, **overrides) -> dict:
    """An /api/v0/models entry in LM Studio's real shape."""
    entry = {
        "id": model_id,
        "type": "llm",
        "arch": "qwen3_5",
        "state": "loaded" if loaded else "not-loaded",
        "max_context_length": 32768,
        "loaded_context_length": 8192,
        "capabilities": ["tool_use"] if tool_use else [],
    }
    entry.update(overrides)
    return entry


def lmstudio_handler(entries: list[dict] | None, *, v0_error: Exception | None = None,
                     v1_error: Exception | None = None, bad_json: bool = False):
    """A fake LM Studio with no v1 model API (404), serving ``entries`` on v0."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/api/v1/models"):
            if v1_error is not None:
                raise v1_error
            return httpx.Response(404, json={"error": "unknown endpoint"})
        if path.endswith("/api/v0/models"):
            if v0_error is not None:
                raise v0_error
            if bad_json:
                return httpx.Response(200, content=b"not-json-at-all{{{{")
            return httpx.Response(200, json={"data": entries or []})
        return httpx.Response(404, json={"error": "unmocked"})

    return handler


async def probe(handler, *, model_name: str = "default-model",
                model_preferred: str | None = None, **kwargs) -> bool:
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        return await probe_classifier_model_ready(
            client,
            BASE_URL,
            model_name=model_name,
            model_preferred=model_preferred,
            **kwargs,
        )


# --- Tests -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_classifier_ready_true_when_genuinely_loaded_and_scoring():
    """A loaded model that can do structured work → probe returns True."""
    result = await probe(
        lmstudio_handler([v0_entry("my-fc-model")]), model_name="my-fc-model"
    )

    assert result is True, (
        "probe must return True for a loaded, structured-capable model"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_when_no_models_loaded():
    """Empty loaded list → probe returns False.

    This is the fail-closed case: configuration names a model, but the backend
    reports nothing, and a model the backend never said it had must never be
    treated as ready.
    """
    result = await probe(lmstudio_handler([]), model_name="some-default-model")

    assert result is False, (
        "probe must return False when no models loaded — a selection resting on "
        "configuration alone is not 'ready' (fail-closed)"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_when_loaded_model_scores_zero():
    """The sole loaded model cannot do structured work → probe returns False.

    The DECISIVE case: resolution still returns this model (it is the only
    candidate, and with exactly one there is nothing to guess between), but
    resolvable is not ready. classify_note would run on it and emit degraded
    classifications, so the probe must fail closed.
    """
    result = await probe(
        lmstudio_handler([v0_entry("no-fc-model", tool_use=False)]),
        model_name="no-fc-model",
    )

    assert result is False, (
        "probe must return False when the only loaded model cannot do structured "
        "work — a non-capable selection is not ready"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_on_http_error():
    """httpx / network failure → False (graceful degrade — never raises).

    The failure lands on the PREFERRED generation, which must not be mistaken
    for the 404 that selects the v0 fallback.
    """
    result = await probe(
        lmstudio_handler(None, v1_error=httpx.ConnectError("connection refused"))
    )

    assert result is False, "probe must return False on HTTP error, never raise"


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_on_json_error():
    """JSON-decode failure → False (graceful degrade)."""
    result = await probe(lmstudio_handler(None, bad_json=True))

    assert result is False, "probe must return False on JSON parse error, never raise"


@pytest.mark.asyncio
async def test_probe_classifier_ready_true_when_preference_honored():
    """MODEL_PREFERRED names a loaded, structured-capable model → True.

    This mirrors what the structured path would actually select when a
    preferred model is configured and that model is both loaded and capable.
    """
    result = await probe(
        lmstudio_handler(
            [
                v0_entry("preferred-fc-model"),
                v0_entry("other-model", tool_use=False),
            ]
        ),
        model_name="default-model",
        model_preferred="preferred-fc-model",
    )

    assert result is True, (
        "probe must return True when MODEL_PREFERRED names a loaded, "
        "structured-capable model"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_true_for_local_model_advertising_tool_use():
    """A local model LM Studio reports as loaded with capabilities ["tool_use"].

    litellm's static cloud registry has no entry for local model ids, so under
    the old ``_score`` path every local model scored 0 for 'structured' —
    permanently reporting "not ready" and silently disabling destructive vault
    sweeps on any local-LLM deployment. Capabilities now come straight off the
    backend, which is what makes this answerable at all.
    """
    model_id = "google/gemma-4-31b"
    result = await probe(
        lmstudio_handler(
            [
                v0_entry(
                    model_id,
                    type="vlm",
                    arch="gemma4",
                    max_context_length=262144,
                    loaded_context_length=71936,
                )
            ]
        ),
        model_name=model_id,
    )

    assert result is True, (
        "a loaded local model advertising tool_use must be reported ready, via "
        "live LM Studio capability data rather than litellm's static registry"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_for_local_model_without_tool_use():
    """A loaded local model WITHOUT tool_use is still not ready.

    Reading capabilities from the backend must not become permissive for
    genuinely incapable models.
    """
    model_id = "some-community/non-function-calling-model"
    result = await probe(
        lmstudio_handler(
            [v0_entry(model_id, tool_use=False, type="llm", arch="llama3")]
        ),
        model_name=model_id,
    )

    assert result is False, (
        "a loaded local model without tool_use must not be reported ready — "
        "reading live capabilities must not weaken fail-closed behaviour"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_when_capability_endpoint_unreachable():
    """The model-list endpoint is unreachable → still fail closed.

    Fail-closed end to end, not merely when the preferred generation fails: the
    v1 probe answers 404 (an older backend) and the v0 fallback is then
    unreachable.
    """
    result = await probe(
        lmstudio_handler(None, v0_error=httpx.ConnectError("connection refused")),
        model_name="mlx-community/some-local-model-8bit",
    )

    assert result is False, (
        "an unreachable model-list endpoint must never grant a permissive "
        "default — the probe must still fail closed"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_when_capabilities_are_absent():
    """An entry carrying NO capability data at all is not ready.

    Absent data is not permission. This is the shape an older backend can
    return for a model it has not loaded, and it must never be read as capable.
    """
    entry = v0_entry("mlx-community/some-local-model-8bit")
    del entry["capabilities"]

    result = await probe(lmstudio_handler([entry]), model_name=entry["id"])

    assert result is False, (
        "absent capability data must never grant a permissive default"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_when_an_operator_pin_lacks_tool_use():
    """An operator pin wins the ladder absolutely — and still is not ready.

    ADR-0007 makes MODEL_PREFERRED absolute over the capability filter, so
    resolution RETURNS the pinned model even though it cannot do structured
    work. The probe must answer on the resolved profile's capability, not on
    the fact that a model came back, or an explicit pin would become a way to
    unlock destructive sweeps with a degraded classifier.
    """
    result = await probe(
        lmstudio_handler(
            [v0_entry("capable/model"), v0_entry("pinned/model", tool_use=False)]
        ),
        model_name="default-model",
        model_preferred="pinned/model",
    )

    assert result is False, (
        "a pinned-but-incapable model must be reported not ready even though "
        "the ladder honours the pin"
    )


@pytest.mark.asyncio
async def test_probe_classifier_ready_false_when_resolution_raises():
    """A live backend whose candidates cannot be disambiguated → not ready.

    NEW mechanism, same verdict. Under ADR decision 4 as amended, that case
    makes ``for_task("structured")`` RAISE rather than return a config-named
    phantom; the probe previously received a model string there and had to
    judge it. Fail-closed is the right answer either way, but an uncaught raise
    would reach the destructive-sweep gate as a 500 instead of a refusal — and
    a 500 is not a refusal.

    Two capable candidates, a cold cache and no configuration that names either.
    """
    result = await probe(
        lmstudio_handler([v0_entry("first/capable"), v0_entry("second/capable")]),
        model_name="",
        model_preferred=None,
    )

    assert result is False, (
        "an undisambiguatable live backend must be answered not-ready, and the "
        "raise must never propagate to the sweep gate"
    )


@pytest.mark.asyncio
async def test_probe_and_structured_resolution_agree_on_the_same_model():
    """Probe/resolver parity, against the seam.

    This replaces the parity guarantee held by test_model_resolution.py, which
    Plan 03 deletes; landing the replacement here means Plan 03 never has an
    unguarded window. Both now ask the same object the same question, so the
    documented deliberate divergence is gone rather than merely narrowed.
    """
    from types import SimpleNamespace

    from app.model import ActiveModel, LMStudioModelSource

    handler = lmstudio_handler(
        [
            v0_entry(
                "qwen/qwen3.8-27b",
                type="vlm",
                max_context_length=262144,
                loaded_context_length=119552,
            ),
            {
                "id": "text-embedding-nomic-embed-text-v1.5",
                "type": "embeddings",
                "state": "loaded",
                "max_context_length": 2048,
            },
        ]
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        seam = ActiveModel(
            [LMStudioModelSource(client, BASE_URL)],
            SimpleNamespace(model_name="google/gemma-4-31b"),
        )
        resolved = await seam.for_task("structured")
        ready = await probe_classifier_model_ready(
            client,
            BASE_URL,
            model_name="google/gemma-4-31b",
            active_model=seam,
        )

    assert ready is True
    assert resolved.model_id == "qwen/qwen3.8-27b"
    assert seam.cached_profile("structured").model_id == resolved.model_id, (
        "the probe and the structured resolution path must name the same model"
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
