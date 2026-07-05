"""Tests for discover_active_model integration in sentinel-core."""
from unittest.mock import patch

import pytest
import httpx

from app.errors import ModelSelectorError
from app.services.model_selector import (  # noqa: F401 — probe used in tests below
    _reset_cache_for_tests,
    discover_active_model,
    discover_via_exo_state,
    probe_embedding_model_loaded,
    select_model,
)


@pytest.fixture(autouse=True)
def clear_model_cache():
    """Reset the module-level cache between tests."""
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


@pytest.fixture
def discovery_off_settings(monkeypatch):
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "false")
    monkeypatch.setenv("MODEL_NAME", "local-model")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    return Settings()


@pytest.fixture
def discovery_on_settings(monkeypatch):
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "local-model")
    monkeypatch.setenv("MODEL_PREFERRED", "")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    return Settings()


async def test_discovery_off_returns_model_name_prefixed(discovery_off_settings):
    """MODEL_AUTO_DISCOVER=false returns 'openai/{model_name}' without HTTP."""
    async with httpx.AsyncClient() as client:
        result = await discover_active_model(discovery_off_settings, client)
    assert result == "openai/local-model"


async def test_discovery_off_no_double_prefix(monkeypatch):
    """model_name already containing '/' must not get double prefix."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "false")
    monkeypatch.setenv("MODEL_NAME", "openai/some-model")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    from app.config import Settings
    s = Settings()
    async with httpx.AsyncClient() as client:
        result = await discover_active_model(s, client)
    assert result == "openai/some-model"
    assert "openai/openai/" not in result


async def test_discovery_on_single_model(discovery_on_settings):
    """discover_active_model with /v1/models returning ['Qwen2.5-14B'] → 'openai/Qwen2.5-14B'."""
    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "Qwen2.5-14B"}]})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(discovery_on_settings, client)
    assert result == "openai/Qwen2.5-14B"


async def test_discovery_honors_model_preferred(monkeypatch):
    """model_preferred in loaded list is honored."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "other-model")
    monkeypatch.setenv("MODEL_PREFERRED", "Qwen2.5-14B")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "Qwen2.5-14B"}, {"id": "other-model"}]})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)
    assert result == "openai/Qwen2.5-14B"


async def test_discovery_unreachable_falls_back(monkeypatch):
    """ConnectError during discovery → non-fatal fallback to 'openai/{model_name}'."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "fallback-model")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def raise_connect(request):
        raise httpx.ConnectError("refused")
    transport = httpx.MockTransport(raise_connect)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)
    assert result == "openai/fallback-model"


async def test_discovery_empty_models_falls_back(monkeypatch):
    """Empty /v1/models data → non-fatal fallback."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "fallback-model")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def handler(request):
        return httpx.Response(200, json={"data": []})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)
    assert result == "openai/fallback-model"


async def test_discovery_ollama_provider(monkeypatch):
    """ai_provider='ollama' → returns 'ollama/{name}'."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "qwen2.5:14b")
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://test-ollama")
    from app.config import Settings
    s = Settings()

    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "qwen2.5:14b"}]})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)
    assert result == "ollama/qwen2.5:14b"


async def test_discovery_no_double_prefix_with_slash_in_discovered(monkeypatch):
    """Discovered model name already containing '/' must not get double prefix."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "local-model")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    s = Settings()

    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "openai/already-prefixed"}]})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)
    assert result == "openai/already-prefixed"
    assert result.count("openai/") == 1


# --- 260502-1zv D-02: probe_embedding_model_loaded ---


async def test_probe_embedding_loaded_true_when_state_loaded():
    """LM Studio /api/v0/models returns the configured embedding model with
    state="loaded" and type="embeddings" → probe returns True."""
    captured: dict[str, str] = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "some-llm",
                        "type": "llm",
                        "state": "loaded",
                    },
                    {
                        "id": "text-embedding-nomic-embed-text-v1.5",
                        "type": "embeddings",
                        "state": "loaded",
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_embedding_model_loaded(
            client,
            "http://test-lmstudio/v1",
            "text-embedding-nomic-embed-text-v1.5",
        )

    assert result is True
    # Probe hits /api/v0/models, not /v1/models
    assert captured["url"].endswith("/api/v0/models")


async def test_probe_embedding_loaded_false_when_state_not_loaded():
    """Same fixture but state="not-loaded" → probe returns False."""
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "text-embedding-nomic-embed-text-v1.5",
                        "type": "embeddings",
                        "state": "not-loaded",
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_embedding_model_loaded(
            client,
            "http://test-lmstudio/v1",
            "text-embedding-nomic-embed-text-v1.5",
        )

    assert result is False


async def test_probe_embedding_loaded_false_on_http_error():
    """httpx.RequestError during probe → False (graceful degrade — never raises)."""
    def raise_connect(request):
        raise httpx.ConnectError("refused")

    transport = httpx.MockTransport(raise_connect)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_embedding_model_loaded(
            client,
            "http://test-lmstudio/v1",
            "text-embedding-nomic-embed-text-v1.5",
        )

    assert result is False


async def test_probe_embedding_strips_openai_prefix():
    """Caller may pass an openai/-prefixed id; probe strips before comparing
    against LM Studio's bare id field."""
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "text-embed-x",
                        "type": "embeddings",
                        "state": "loaded",
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_embedding_model_loaded(
            client,
            "http://test-lmstudio/v1",
            "openai/text-embed-x",
        )

    assert result is True


async def test_probe_embedding_loaded_false_when_only_llm_loaded():
    """A loaded LLM with the same id but type='llm' must not satisfy the
    embedding probe — both type AND state must match."""
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "text-embedding-nomic-embed-text-v1.5",
                        "type": "llm",
                        "state": "loaded",
                    },
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_embedding_model_loaded(
            client,
            "http://test-lmstudio/v1",
            "text-embedding-nomic-embed-text-v1.5",
        )

    assert result is False


# --- exo-model-notfound-502: select_model must not guess a catalog[0] entry ---
#
# exo's /v1/models advertises every model it *could* load (100+ entries in
# production) but SERVES only the one actually running. Unlike real LM Studio
# (where /v1/models genuinely reflects what's loaded), an unmatched preference/
# default here must NOT fall through to an arbitrary "first entry" guess.


def _unscored(task_kind: str, model_id: str) -> int:
    """Patch target: nothing scores for any task_kind (simulates unknown mlx-community
    ids that litellm.get_model_info() has no static metadata for)."""
    return 0


def test_select_model_ambiguous_catalog_prefers_configured_default_over_catalog_zero():
    """Regression for exo-model-notfound-502: with a multi-entry, unscored catalog
    and no matching preference, select_model must return the explicitly configured
    `default`, never `loaded[0]`."""
    # Mirrors the real incident: exo catalog[0] is an unrelated model; the
    # operator's configured model is a DIFFERENT entry deeper in the list.
    loaded = [
        "mlx-community/MiniMax-M2.7-4bit",  # catalog[0] — must NOT be picked
        "mlx-community/Some-Other-Model-4bit",
        "mlx-community/Qwen3.5-27B-8bit",  # the actually-running/configured model
    ]
    with patch("app.services.model_selector._score", side_effect=_unscored):
        result = select_model(
            "chat",
            loaded,
            preferences={"chat": "qwen3.6-35b-a3b"},  # stale pref — matches nothing
            default="mlx-community/Qwen3.5-27B-8bit",
        )

    assert result == "mlx-community/Qwen3.5-27B-8bit"
    assert result != loaded[0], "must never silently fall back to catalog[0]"


def test_select_model_ambiguous_catalog_no_default_raises_loudly():
    """With no configured default and an ambiguous, unscored, multi-entry catalog,
    select_model must fail loudly (raise) rather than silently return catalog[0]."""
    loaded = [
        "mlx-community/MiniMax-M2.7-4bit",
        "mlx-community/Some-Other-Model-4bit",
    ]
    with patch("app.services.model_selector._score", side_effect=_unscored):
        with pytest.raises(ModelSelectorError):
            select_model(
                "chat",
                loaded,
                preferences={"chat": "qwen3.6-35b-a3b"},
                default=None,
            )


def test_select_model_sole_candidate_is_unambiguous():
    """A single-entry loaded list has no ambiguity to guess between — it is safe
    to return even when it doesn't match preferences/default (distinct from the
    multi-entry exo-catalog case, which must NOT do this)."""
    loaded = ["only-model-available"]
    with patch("app.services.model_selector._score", side_effect=_unscored):
        result = select_model(
            "chat",
            loaded,
            preferences={"chat": "something-else"},
            default="yet-another-model",
        )

    assert result == "only-model-available"


async def test_discovery_exo_style_catalog_honors_configured_default_not_catalog_zero(
    monkeypatch,
):
    """End-to-end regression for exo-model-notfound-502 at the discover_active_model
    level: a large, unscored, unmatched catalog (simulating exo's ~120-model
    /v1/models advertisement) must resolve to the configured MODEL_NAME/MODEL_PREFERRED,
    never to the catalog's first entry."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "mlx-community/Qwen3.5-27B-8bit")
    monkeypatch.setenv("MODEL_PREFERRED", "qwen3.6-35b-a3b")  # stale — matches nothing
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-exo/v1")
    from app.config import Settings
    s = Settings()

    catalog = [
        {"id": "mlx-community/MiniMax-M2.7-4bit"},  # catalog[0] — must NOT be chosen
        {"id": "mlx-community/Some-Other-Model-4bit"},
        {"id": "mlx-community/Qwen3.5-27B-8bit"},
    ]

    def handler(request):
        return httpx.Response(200, json={"data": catalog})

    transport = httpx.MockTransport(handler)
    with patch("app.services.model_selector._score", side_effect=_unscored):
        async with httpx.AsyncClient(transport=transport) as client:
            result = await discover_active_model(s, client)

    assert result == "openai/mlx-community/Qwen3.5-27B-8bit"
    assert "MiniMax" not in result, "must never silently resolve to exo's catalog[0]"


async def test_discovery_except_handler_falls_back_to_settings_model_name_not_loaded_zero(
    monkeypatch,
):
    """Regression for exo-model-notfound-502: discover_active_model's OWN
    `except ModelSelectorError` handler (distinct from select_model's internal logic)
    must fall back to settings.model_name, never loaded[0].

    The test above (test_discovery_exo_style_catalog_honors_configured_default_not_catalog_zero)
    passes a non-empty settings.model_name as `default` into select_model, which
    select_model itself then returns via its own rule 3 ("default in loaded") — it never
    actually raises, so that test never exercises discover_active_model's except-handler
    at all. This test forces select_model to raise directly so the except-handler
    (lines ~278-293) is genuinely hit."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "configured-fallback-model")
    monkeypatch.setenv("MODEL_PREFERRED", "")
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-exo/v1")
    from app.config import Settings
    s = Settings()

    catalog = [
        {"id": "mlx-community/MiniMax-M2.7-4bit"},  # loaded[0] — must NOT be chosen
        {"id": "mlx-community/Some-Other-Model-4bit"},
    ]

    def handler(request):
        return httpx.Response(200, json={"data": catalog})

    transport = httpx.MockTransport(handler)
    with patch(
        "app.services.model_selector.select_model",
        side_effect=ModelSelectorError("forced for test"),
    ):
        async with httpx.AsyncClient(transport=transport) as client:
            result = await discover_active_model(s, client)

    assert result == "openai/configured-fallback-model"
    assert "MiniMax" not in result, "except-handler must never fall back to loaded[0]"


# --- Task 1 (42-02): discover_via_exo_state — GET /state tagged-union discovery ---


async def test_discover_via_exo_state_zero_instances_returns_empty_list():
    """Zero running instances ({"instances": {}}) -> [] (D-08's zero-case)."""
    def handler(request):
        assert request.url.path == "/state"
        return httpx.Response(200, json={"instances": {}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_via_exo_state("http://test-exo:52415/v1", client)

    assert result == []


async def test_discover_via_exo_state_mlx_ring_instance_unwraps_tagged_union():
    """Single MlxRingInstance -> one model id via tagged-union unwrap."""
    def handler(request):
        return httpx.Response(
            200,
            json={
                "instances": {
                    "instance-1": {
                        "MlxRingInstance": {
                            "shardAssignments": {
                                "modelId": "mlx-community/Qwen3.5-27B-8bit",
                            }
                        }
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_via_exo_state("http://test-exo:52415/v1", client)

    assert result == ["mlx-community/Qwen3.5-27B-8bit"]


async def test_discover_via_exo_state_mlx_jaccl_instance_unwraps_tagged_union():
    """Single MlxJacclInstance -> same tagged-union unwrap as MlxRingInstance."""
    def handler(request):
        return httpx.Response(
            200,
            json={
                "instances": {
                    "instance-1": {
                        "MlxJacclInstance": {
                            "shardAssignments": {
                                "modelId": "mlx-community/Other-Model-4bit",
                            }
                        }
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_via_exo_state("http://test-exo:52415/v1", client)

    assert result == ["mlx-community/Other-Model-4bit"]


async def test_discover_via_exo_state_malformed_shard_assignments_skipped_not_raised():
    """A malformed/missing shardAssignments entry is skipped, not raised
    (defensive structural walk) — a well-formed sibling instance is still
    returned."""
    def handler(request):
        return httpx.Response(
            200,
            json={
                "instances": {
                    "instance-bad-1": {
                        "MlxRingInstance": {
                            # shardAssignments missing entirely
                        }
                    },
                    "instance-bad-2": {
                        "MlxRingInstance": {
                            "shardAssignments": "not-a-dict",
                        }
                    },
                    "instance-bad-3": "not-a-dict-either",
                    "instance-good": {
                        "MlxJacclInstance": {
                            "shardAssignments": {
                                "modelId": "mlx-community/Good-Model-4bit",
                            }
                        }
                    },
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_via_exo_state("http://test-exo:52415/v1", client)

    assert result == ["mlx-community/Good-Model-4bit"]


async def test_discover_via_exo_state_accepts_snake_case_fallback():
    """A1 defensive fallback: snake_case shard_assignments/model_id is also
    accepted since the camelCase wire format was not live-curl-confirmed."""
    def handler(request):
        return httpx.Response(
            200,
            json={
                "instances": {
                    "instance-1": {
                        "MlxRingInstance": {
                            "shard_assignments": {
                                "model_id": "mlx-community/Snake-Case-Model",
                            }
                        }
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_via_exo_state("http://test-exo:52415/v1", client)

    assert result == ["mlx-community/Snake-Case-Model"]


async def test_discover_via_exo_state_strips_v1_suffix_before_state():
    """base_url with a trailing /v1 (exo_base_url's default shape) must hit
    {root}/state, not {root}/v1/state."""
    captured: dict[str, str] = {}

    def handler(request):
        captured["path"] = request.url.path
        return httpx.Response(200, json={"instances": {}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await discover_via_exo_state("http://test-exo:52415/v1", client)

    assert captured["path"] == "/state"


async def test_discovery_exo_provider_uses_state_not_v1_models(monkeypatch):
    """discover_active_model with ai_provider='exo' routes through GET /state,
    not the generic /v1/models GET (SC-4, D-07)."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "fallback-model")
    monkeypatch.setenv("AI_PROVIDER", "exo")
    monkeypatch.setenv("EXO_BASE_URL", "http://test-exo:52415/v1")
    from app.config import Settings
    s = Settings()

    def handler(request):
        assert request.url.path == "/state", "must query /state, not /v1/models"
        return httpx.Response(
            200,
            json={
                "instances": {
                    "instance-1": {
                        "MlxRingInstance": {
                            "shardAssignments": {
                                "modelId": "mlx-community/Qwen3.5-27B-8bit",
                            }
                        }
                    }
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)

    assert result == "openai/mlx-community/Qwen3.5-27B-8bit"


async def test_discovery_exo_zero_instances_never_guesses_falls_back_to_default(
    monkeypatch,
):
    """D-08: zero exo instances must never yield a guessed model — falls back
    to the configured MODEL_NAME default via select_model's documented
    contract, exactly like get_loaded_models's [] result does for lmstudio."""
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "configured-default-model")
    monkeypatch.setenv("AI_PROVIDER", "exo")
    monkeypatch.setenv("EXO_BASE_URL", "http://test-exo:52415/v1")
    from app.config import Settings
    s = Settings()

    def handler(request):
        return httpx.Response(200, json={"instances": {}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await discover_active_model(s, client)

    assert result == "openai/configured-default-model"


async def test_discovery_unknown_provider_logs_warning_not_silent_lmstudio_default(
    monkeypatch, caplog
):
    """An unrecognized ai_provider logs a WARNING rather than silently
    querying lmstudio_base_url (Pitfall 2)."""
    import logging

    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_AUTO_DISCOVER", "true")
    monkeypatch.setenv("MODEL_NAME", "fallback-model")
    monkeypatch.setenv("AI_PROVIDER", "totally-unknown-provider")
    from app.config import Settings
    s = Settings()

    def raise_connect(request):
        raise httpx.ConnectError("refused")

    transport = httpx.MockTransport(raise_connect)
    with caplog.at_level(logging.WARNING, logger="app.services.model_selector"):
        async with httpx.AsyncClient(transport=transport) as client:
            result = await discover_active_model(s, client)

    assert result == "openai/fallback-model"
    assert any(
        "Unknown AI_PROVIDER" in record.message for record in caplog.records
    ), "unrecognized ai_provider must log a WARNING, not silently default"
