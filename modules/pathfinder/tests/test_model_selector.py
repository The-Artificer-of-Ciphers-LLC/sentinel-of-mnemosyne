"""Tests for app.model_selector — discovery + registry-aware task-kind selection."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.model_selector import (
    ModelSelectorError,
    _reset_cache_for_tests,
    get_loaded_models,
    select_model,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Clear the discovery cache before each test so tests are order-independent."""
    _reset_cache_for_tests()


# ---------------------------------------------------------------------------
# get_loaded_models — discovery + cache
# ---------------------------------------------------------------------------


async def test_get_loaded_models_queries_and_caches():
    """First call hits the network; second call returns from cache."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={
        "data": [{"id": "big-chat-model"}, {"id": "small-fast-model"}]
    })

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
    mock_client.__aexit__.return_value = None

    with patch("app.model_selector.httpx.AsyncClient", return_value=mock_client):
        first = await get_loaded_models("http://host:1234/v1")
        second = await get_loaded_models("http://host:1234/v1")

    assert first == ["big-chat-model", "small-fast-model"]
    assert second == first
    mock_client.__aenter__.return_value.get.assert_awaited_once()


async def test_get_loaded_models_force_refresh_bypasses_cache():
    """force_refresh=True re-queries the endpoint even if cache is warm."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"data": [{"id": "model-a"}]})

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
    mock_client.__aexit__.return_value = None

    with patch("app.model_selector.httpx.AsyncClient", return_value=mock_client):
        await get_loaded_models("http://host:1234/v1")
        await get_loaded_models("http://host:1234/v1", force_refresh=True)

    assert mock_client.__aenter__.return_value.get.await_count == 2


async def test_get_loaded_models_returns_empty_on_network_error():
    """Network errors return [] so callers can fall through; error is logged, not raised."""
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    mock_client.__aexit__.return_value = None

    with patch("app.model_selector.httpx.AsyncClient", return_value=mock_client):
        result = await get_loaded_models("http://host:1234/v1")

    assert result == []


async def test_get_loaded_models_filters_malformed_entries():
    """Entries missing 'id' or with non-string ids are skipped, not raised."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={
        "data": [{"id": "valid"}, {}, {"id": None}, "notadict", {"id": ""}]
    })
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
    mock_client.__aexit__.return_value = None

    with patch("app.model_selector.httpx.AsyncClient", return_value=mock_client):
        result = await get_loaded_models("http://host:1234/v1")

    assert result == ["valid"]


# ---------------------------------------------------------------------------
# select_model — scoring and fallback
# ---------------------------------------------------------------------------


def _mock_info(max_tokens: int, supports_fc: bool):
    """Build a side_effect factory that returns different info per model_id."""
    def factory(model_name_to_info: dict):
        def get_info(model: str, **_):
            if model in model_name_to_info:
                return model_name_to_info[model]
            raise Exception(f"unknown model: {model}")
        return get_info
    return factory


def test_select_chat_prefers_large_context():
    """chat task_kind rewards max_tokens + function_calling bonus."""
    info_map = {
        "small": {"max_tokens": 4_000},
        "big": {"max_tokens": 32_000},
        "medium-fc": {"max_tokens": 8_000},
    }
    fc_map = {"small": False, "big": False, "medium-fc": True}

    with patch("app.model_selector.litellm.get_model_info", side_effect=lambda model, **_: info_map.get(model) or _raise()), \
         patch("app.model_selector.litellm.supports_function_calling", side_effect=lambda model, **_: fc_map.get(model, False)):
        chosen = select_model("chat", ["small", "big", "medium-fc"])

    # big (32000) > medium-fc (8000 + 10000 = 18000) > small (4000) — big wins on raw context
    assert chosen == "big"


def test_select_structured_requires_function_calling():
    """structured task must not select a model without function_calling support."""
    info_map = {
        "big-no-fc": {"max_tokens": 32_000},
        "medium-fc": {"max_tokens": 8_000},
    }
    fc_map = {"big-no-fc": False, "medium-fc": True}

    with patch("app.model_selector.litellm.get_model_info", side_effect=lambda model, **_: info_map.get(model) or _raise()), \
         patch("app.model_selector.litellm.supports_function_calling", side_effect=lambda model, **_: fc_map.get(model, False)):
        chosen = select_model("structured", ["big-no-fc", "medium-fc"])

    assert chosen == "medium-fc"


def test_select_fast_prefers_smaller_context_above_minimum():
    """fast task prefers smaller max_tokens but rejects anything below 4K."""
    info_map = {
        "tiny": {"max_tokens": 2_000},     # below 4K — disqualified
        "small": {"max_tokens": 4_000},    # at threshold — best after threshold
        "medium": {"max_tokens": 16_000},
        "big": {"max_tokens": 128_000},
    }
    fc_map = {k: False for k in info_map}

    with patch("app.model_selector.litellm.get_model_info", side_effect=lambda model, **_: info_map.get(model) or _raise()), \
         patch("app.model_selector.litellm.supports_function_calling", side_effect=lambda model, **_: fc_map.get(model, False)):
        chosen = select_model("fast", list(info_map.keys()))

    assert chosen == "small"


def test_preference_overrides_scoring():
    """If preferences[task_kind] is in loaded, use it regardless of scoring."""
    info_map = {
        "preferred": {"max_tokens": 2_000},  # would normally disqualify for fast
        "great-fast": {"max_tokens": 4_000},
    }
    fc_map = {k: False for k in info_map}

    with patch("app.model_selector.litellm.get_model_info", side_effect=lambda model, **_: info_map.get(model) or _raise()), \
         patch("app.model_selector.litellm.supports_function_calling", side_effect=lambda model, **_: fc_map.get(model, False)):
        chosen = select_model(
            "fast",
            ["preferred", "great-fast"],
            preferences={"fast": "preferred"},
        )

    assert chosen == "preferred"


def test_falls_back_to_default_when_in_loaded_and_no_match():
    """When no model scores > 0 but default is loaded, use default."""
    # Every model is unknown to litellm — all score 0
    with patch("app.model_selector.litellm.get_model_info", side_effect=Exception("unknown")), \
         patch("app.model_selector.litellm.supports_function_calling", side_effect=Exception("unknown")):
        chosen = select_model(
            "chat",
            ["opaque-a", "opaque-b"],
            default="opaque-b",
        )

    assert chosen == "opaque-b"


def test_falls_back_to_first_loaded_when_default_not_in_loaded():
    """No scores and default isn't among loaded — pick first loaded."""
    with patch("app.model_selector.litellm.get_model_info", side_effect=Exception("unknown")), \
         patch("app.model_selector.litellm.supports_function_calling", side_effect=Exception("unknown")):
        chosen = select_model(
            "chat",
            ["opaque-a", "opaque-b"],
            default="not-loaded",
        )

    assert chosen == "opaque-a"


def test_uses_default_when_loaded_is_empty():
    """Empty loaded (e.g. LM Studio unreachable) — use default string as-is."""
    chosen = select_model("chat", [], default="openai/local-model")
    assert chosen == "openai/local-model"


def test_raises_when_no_loaded_and_no_default():
    """Empty loaded AND no default → ModelSelectorError."""
    with pytest.raises(ModelSelectorError):
        select_model("chat", [], default=None)


def test_preference_skipped_when_not_in_loaded():
    """Preference is ignored if the preferred model isn't loaded — falls through to scoring."""
    info_map = {"big": {"max_tokens": 32_000}}
    fc_map = {"big": False}

    with patch("app.model_selector.litellm.get_model_info", side_effect=lambda model, **_: info_map.get(model) or _raise()), \
         patch("app.model_selector.litellm.supports_function_calling", side_effect=lambda model, **_: fc_map.get(model, False)):
        chosen = select_model(
            "chat",
            ["big"],
            preferences={"chat": "not-loaded-model"},
        )

    assert chosen == "big"


def _raise():
    raise Exception("unknown model")
