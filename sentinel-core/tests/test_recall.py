"""Behavioral tests for Recall.assemble().

Each test constructs a real ``Recall`` against ``FakeVault`` directly and calls
``recall.assemble(MessageRequest(...), budget=8192)`` directly.

Assertions are strictly behavioral: values in ``RecalledContext`` fields.
Test surface is Recall-only — no message processor, no AI provider, no
injection filter. This is success criterion #4 for phase 39.
"""
from __future__ import annotations

import pytest

from tests.fakes.vault import FakeVault
from app.services.recall import Recall, RecallConfig, RecalledContext, SearchResult, MessageRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_recall(
    *,
    notes: dict | None = None,
    config: RecallConfig | None = None,
) -> tuple[Recall, FakeVault]:
    """Build a FakeVault and Recall pair, optionally pre-seeded with notes."""
    vault = FakeVault(notes=notes or {})
    recall = Recall(vault=vault, config=config)
    return recall, vault


def make_request(content: str = "hello", budget: int = 8192) -> MessageRequest:
    """Build a minimal MessageRequest for test use."""
    return MessageRequest(
        content=content,
        user_id="trekkie",
        model_name="test-model",
        context_window=budget,
        stop_sequences=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_assemble_returns_self_context():
    """assemble() populates self_context from seeded self-path notes.

    Seeds 3 of the 6 self_paths including ops/reminders.md to confirm that
    the ops/reminders.md allowlist exception is preserved: ops/ is in
    exclude_prefixes (blocking warm search) but ops/reminders.md IS in
    self_paths and should be returned as self_context (Pitfall 2).
    """
    notes = {
        "self/identity.md": "# I am the user",
        "self/goals.md": "My goals are to ship good code",
        "ops/reminders.md": "Remember to review PRs",
    }
    recall, _ = make_recall(notes=notes)
    result = await recall.assemble(make_request(), budget=8192)

    assert isinstance(result, RecalledContext)
    assert len(result.self_context) == 3
    assert all(isinstance(s, str) and s.strip() for s in result.self_context)
    # ops/reminders.md must appear — it is in self_paths despite ops/ being excluded from warm
    assert any("Remember to review PRs" in s for s in result.self_context)


async def test_assemble_returns_sessions():
    """assemble() populates sessions from ops/sessions notes matching user_id."""
    notes = {
        "ops/sessions/2026-06-11/trekkie-12-00-00.md": "session body here",
    }
    recall, _ = make_recall(notes=notes)
    result = await recall.assemble(make_request(), budget=8192)

    assert len(result.sessions) >= 1
    assert any("session body here" in s for s in result.sessions)


async def test_warm_includes_above_threshold_non_excluded():
    """Warm search returns notes above relevance threshold in non-excluded paths."""
    notes = {
        "notes/omie.md": "omie wise synthwave details about production",
    }
    recall, _ = make_recall(notes=notes)
    result = await recall.assemble(make_request(content="omie wise synthwave"), budget=8192)

    paths = [r.path for r in result.warm]
    assert "notes/omie.md" in paths


async def test_warm_excludes_self_and_ops_prefixes():
    """Warm search excludes notes with ops/, self/, or _trash/ prefixes."""
    notes = {
        "self/identity.md": "shared query term about knowledge",
        "ops/reminders.md": "shared query term about knowledge",
        "_trash/old.md": "shared query term about knowledge",
        "notes/topic.md": "shared query term about knowledge",
    }
    recall, _ = make_recall(notes=notes)
    result = await recall.assemble(
        make_request(content="shared query term about knowledge"), budget=8192
    )

    for r in result.warm:
        assert not r.path.startswith("self/"), f"self/ note leaked into warm: {r.path}"
        assert not r.path.startswith("ops/"), f"ops/ note leaked into warm: {r.path}"
        assert not r.path.startswith("_trash/"), f"_trash/ note leaked into warm: {r.path}"

    # The non-excluded note should be present
    assert any(r.path == "notes/topic.md" for r in result.warm)


async def test_warm_excludes_below_threshold():
    """Warm search excludes notes whose score is below relevance_threshold (-200.0)."""
    vault = FakeVault(notes={"notes/target.md": "below threshold content"})

    # Override find() to return a result with score well below -200.0
    async def fake_find(query: str) -> list[dict]:
        return [{"filename": "notes/target.md", "score": -300.0, "matches": []}]

    vault.find = fake_find  # type: ignore[method-assign]

    recall = Recall(vault=vault)
    result = await recall.assemble(make_request(content="below threshold"), budget=8192)

    assert result.warm == [], f"Expected no warm results but got: {result.warm}"


async def test_empty_vault_graceful_degrade():
    """An empty vault results in all RecalledContext lists being empty."""
    recall, _ = make_recall(notes={})
    result = await recall.assemble(make_request(), budget=8192)

    assert result.self_context == []
    assert result.sessions == []
    assert result.warm == []


async def test_recall_config_respected():
    """A custom RecallConfig.exclude_prefixes drives warm-tier filtering.

    Proves that the filter uses config.exclude_prefixes, not a hardcoded
    constant — satisfying MEM-02.
    """
    notes = {
        "blocked/x.md": "custom blocked content matching query",
        "notes/y.md": "custom blocked content matching query",
    }
    custom_config = RecallConfig(exclude_prefixes=("blocked/",))
    recall, _ = make_recall(notes=notes, config=custom_config)
    result = await recall.assemble(
        make_request(content="custom blocked content matching query"), budget=8192
    )

    paths = [r.path for r in result.warm]
    assert "blocked/x.md" not in paths, "blocked/ prefix should be excluded by custom config"
    assert "notes/y.md" in paths, "notes/y.md should pass the custom exclude_prefixes filter"


async def test_empty_content_skips_find():
    """assemble() with empty content returns warm=[] without calling vault.find().

    This validates Pitfall 8 Option A: when content is empty, _warm_search
    returns early before calling find(), which avoids matching every note in
    FakeVault (where '' in body is always True).
    """
    find_call_count = 0

    vault = FakeVault(
        notes={
            "notes/any.md": "some note content here",
            "self/identity.md": "I am the user",
        }
    )

    original_find = vault.find

    async def tracking_find(query: str) -> list[dict]:
        nonlocal find_call_count
        find_call_count += 1
        return await original_find(query)

    vault.find = tracking_find  # type: ignore[method-assign]

    recall = Recall(vault=vault)
    result = await recall.assemble(make_request(content=""), budget=8192)

    assert result.warm == [], "Empty content should yield warm=[]"
    assert find_call_count == 0, (
        f"find() should not be called for empty content, but was called {find_call_count} times"
    )
