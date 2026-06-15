"""Direct tests for the deep Rule Query module."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.rule_query import (
    RuleQueryDependencies,
    RuleQueryNotInitialized,
    execute_rule_query,
)


def _deps(**overrides):
    deps = {
        "obsidian": object(),
        "rules_index": object(),
        "aon_url_map": {},
        "settings": SimpleNamespace(
            litellm_api_base=None,
            rules_embedding_model="test-embed",
        ),
        "resolve_model": AsyncMock(side_effect=AssertionError("must not resolve model")),
        "keyword_classify_topic": lambda _query: None,
        "classify_rule_topic": AsyncMock(),
        "embed_texts": AsyncMock(),
        "generate_ruling_from_passages": AsyncMock(),
        "generate_ruling_fallback": AsyncMock(),
    }
    deps.update(overrides)
    return RuleQueryDependencies(**deps)


async def test_pf1_decline_is_before_cache_embedding_and_llm_cost():
    deps = _deps()

    result = await execute_rule_query(
        query="What is THAC0?",
        user_id="u1",
        deps=deps,
    )

    assert result["marker"] == "declined"
    assert result["reused"] is False
    assert "THAC0" in result["answer"]
    deps.resolve_model.assert_not_awaited()
    deps.classify_rule_topic.assert_not_awaited()
    deps.embed_texts.assert_not_awaited()
    deps.generate_ruling_from_passages.assert_not_awaited()
    deps.generate_ruling_fallback.assert_not_awaited()


async def test_missing_runtime_dependency_raises_not_initialized():
    deps = _deps(obsidian=None)

    with pytest.raises(RuleQueryNotInitialized):
        await execute_rule_query(
            query="How does flanking work?",
            user_id="u1",
            deps=deps,
        )
