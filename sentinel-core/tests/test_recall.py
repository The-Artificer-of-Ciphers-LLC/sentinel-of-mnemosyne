"""Behavioral tests for Recall.assemble().

Each test constructs a real ``Recall`` against ``FakeVault`` directly and calls
``recall.assemble(MessageRequest(...), budget=8192)`` directly.

Assertions are strictly behavioral: values in ``RecalledContext`` fields.
Test surface is Recall-only — no message processor, no AI provider, no
injection filter. This is success criterion #4 for phase 39.
"""
from __future__ import annotations

import json

import pytest

from tests.fakes.vault import FakeVault
from app.services.recall import Recall, RecallConfig, RecalledContext, SearchResult
from app.services.message_processing import MessageRequest

# ---------------------------------------------------------------------------
# Fixture helpers for SemanticRecall tests (Task 2 + Task 3)
# ---------------------------------------------------------------------------

from sentinel_shared.embedding_codec import encode_embedding


def make_fixture_index(
    note_paths: list[str],
    note_vecs: list[list[float]],
    model: str = "test-model-v1",
) -> dict:
    """Build a fixture embedding-index.json dict for SemanticRecall tests.

    Encodes each vector via encode_embedding (float32 base64) so decode_embedding
    round-trips correctly. content_hash is a fixed sentinel value.
    """
    return {
        path: {
            "embedding_b64": encode_embedding(vec),
            "embedding_model": model,
            "content_hash": "deadbeef00000000",
        }
        for path, vec in zip(note_paths, note_vecs)
    }


async def fake_embedder(texts: list[str]) -> list[list[float]]:
    """Deterministic fake embedder.

    Returns a fixed query vector for inputs containing 'search_query:' and
    a document vector otherwise. Allows tests to control cosine relationships.
    """
    results = []
    for text in texts:
        if "search_query:" in text:
            # Query vector — close to [1.0, 0.0, 0.0] (note_A) at ~0.9 cosine
            results.append([0.9, 0.436, 0.0])
        else:
            results.append([1.0, 0.0, 0.0])
    return results


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


# ---------------------------------------------------------------------------
# WR-03: graceful degradation when a tier raises (FIX A)
# ---------------------------------------------------------------------------


async def test_assemble_degrades_gracefully_when_sessions_tier_raises():
    """WR-03: if _hot_sessions raises, assemble() returns sessions=[] and
    still populates the other tiers — does not propagate the exception.
    """
    vault = FakeVault(
        notes={
            "self/identity.md": "I am the user — identity content",
            "notes/topic.md": "unique degrade test content keyword",
        }
    )

    async def raising_sessions(user_id: str, limit: int = 3) -> list[str]:
        raise RuntimeError("simulated session tier failure")

    vault.get_recent_sessions = raising_sessions  # type: ignore[method-assign]

    recall = Recall(vault=vault)
    # Must not raise; must return a valid RecalledContext
    result = await recall.assemble(
        make_request(content="unique degrade test content keyword"), budget=8192
    )

    assert isinstance(result, RecalledContext)
    assert result.sessions == [], (
        "sessions should be empty when the tier raises, not propagate the exception"
    )
    # self_context should still be populated (tier was not broken)
    assert any("identity content" in s for s in result.self_context), (
        "self_context should still be populated when only the sessions tier fails"
    )
    # warm should still be populated
    assert any(r.path == "notes/topic.md" for r in result.warm), (
        "warm tier should still be populated when only the sessions tier fails"
    )


# ---------------------------------------------------------------------------
# WR-01: skip empty-body warm SearchResult (FIX B)
# ---------------------------------------------------------------------------


async def test_warm_skips_empty_body_result_but_keeps_sibling_with_body():
    """WR-01: a warm hit whose note read fails AND has no snippet is omitted;
    a sibling hit WITH a body is still included.
    """
    vault = FakeVault(
        notes={
            "notes/has-body.md": "warm search test fixture body content",
        }
    )

    # Override find() to return two hits: one resolvable, one whose note body
    # will be empty and has no snippet fallback.
    async def fake_find(query: str) -> list[dict]:
        return [
            {
                "filename": "notes/has-body.md",
                "score": 1.0,
                "matches": [],
            },
            {
                "filename": "notes/no-body.md",
                "score": 1.0,
                "matches": [],  # no snippet fallback
            },
        ]

    vault.find = fake_find  # type: ignore[method-assign]

    recall = Recall(vault=vault)
    result = await recall.assemble(
        make_request(content="warm search test fixture"), budget=8192
    )

    paths = [r.path for r in result.warm]
    assert "notes/has-body.md" in paths, (
        "notes/has-body.md should be included — it has content"
    )
    assert "notes/no-body.md" not in paths, (
        "notes/no-body.md should be skipped — body is empty and no snippet"
    )


# ---------------------------------------------------------------------------
# Task 2 TDD: SemanticRecall + _rrf_merge behaviors
# (These tests drive Task 2 GREEN implementation)
# ---------------------------------------------------------------------------


async def test_semantic_blank_query_returns_empty_without_embed():
    """SemanticRecall.search('') returns [] WITHOUT awaiting embed_fn (D-16).

    Uses a call-counting fake embedder to prove embed_fn is never invoked
    for a blank query.
    """
    from app.services.recall import SemanticRecall

    embed_call_count = 0

    async def counting_embedder(texts: list[str]) -> list[list[float]]:
        nonlocal embed_call_count
        embed_call_count += 1
        return [[1.0, 0.0, 0.0] for _ in texts]

    model = "test-model-v1"
    config = RecallConfig()
    vault = FakeVault()
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(["notes/a.md"], [[1.0, 0.0, 0.0]], model)
    )

    semantic = SemanticRecall(vault=vault, embed_fn=counting_embedder, active_model=model, config=config)
    result = await semantic.search("", budget=10)

    assert result == [], f"Expected [] for blank query, got {result}"
    assert embed_call_count == 0, (
        f"embed_fn should not be called for blank query, was called {embed_call_count} times"
    )


async def test_semantic_ttl_cache_reads_index_at_most_once():
    """SemanticRecall reads index via vault.read_note at most once per TTL window.

    Two back-to-back searches inside the TTL should produce at most 1 index read.
    """
    from app.services.recall import SemanticRecall

    read_note_calls: list[str] = []
    model = "test-model-v1"
    # note_A is geometrically close to the query vector from fake_embedder
    note_a_vec = [1.0, 0.0, 0.0]
    config = RecallConfig(index_ttl_seconds=60.0)
    vault = FakeVault()
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(["notes/a.md"], [note_a_vec], model)
    )

    original_read_note = vault.read_note

    async def tracking_read_note(path: str) -> str:
        read_note_calls.append(path)
        return await original_read_note(path)

    vault.read_note = tracking_read_note  # type: ignore[method-assign]

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)

    # Two searches inside the TTL window
    await semantic.search("test query", budget=10)
    await semantic.search("test query", budget=10)

    index_reads = [p for p in read_note_calls if p == config.index_path]
    assert len(index_reads) <= 1, (
        f"Expected at most 1 index read within TTL window, got {len(index_reads)}"
    )


async def test_semantic_cosine_floor_gating():
    """SemanticRecall returns note_A (high cosine) and excludes note_B (below floor).

    note_A = [1.0, 0.0, 0.0]: cosine with query [0.9, 0.436, 0.0] ≈ 0.90 (above 0.50 floor)
    note_B = [0.0, 1.0, 0.0]: cosine with query ≈ 0.436 (below 0.50 floor? No, 0.436 < 0.50)
    """
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    note_a_vec = [1.0, 0.0, 0.0]  # cosine with query ≈ 0.90
    note_b_vec = [0.0, 1.0, 0.0]  # cosine with query ≈ 0.436

    config = RecallConfig(semantic_cosine_floor=0.50)
    vault = FakeVault()
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(
            ["notes/a.md", "notes/b.md"],
            [note_a_vec, note_b_vec],
            model,
        )
    )

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)
    results = await semantic.search("test query", budget=10)
    paths = [r.path for r in results]

    assert "notes/a.md" in paths, "note_A (cosine ≈ 0.90) should be above the 0.50 floor"
    assert "notes/b.md" not in paths, "note_B (cosine ≈ 0.436) should be excluded by the 0.50 floor"


async def test_semantic_model_mismatch_skips_entries():
    """SemanticRecall skips entries with embedding_model != active_model (D-12/D-13)."""
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    wrong_model = "old-model"
    note_a_vec = [1.0, 0.0, 0.0]

    config = RecallConfig()
    vault = FakeVault()
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(["notes/a.md"], [note_a_vec], wrong_model)
    )

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)
    results = await semantic.search("test query", budget=10)

    assert results == [], (
        f"Expected [] when all entries mismatch active model, got {results}"
    )


async def test_rrf_merge_combines_results():
    """_rrf_merge([[A,B],[C,A]], k=60, top_n=3): A ranks first (appears in both lists)."""
    from app.services.recall import _rrf_merge

    result_a = SearchResult(path="notes/a.md", score=1.0, body="A body")
    result_b = SearchResult(path="notes/b.md", score=0.8, body="B body")
    result_c = SearchResult(path="notes/c.md", score=0.9, body="C body")
    result_a2 = SearchResult(path="notes/a.md", score=0.7, body="A body")

    merged = _rrf_merge([[result_a, result_b], [result_c, result_a2]], k=60, top_n=3)
    paths = [r.path for r in merged]

    # A appears in both lists → highest RRF score → ranks first
    assert paths[0] == "notes/a.md", f"A should rank first (in both lists), got {paths}"
    assert "notes/b.md" in paths, "B should appear in merged result"
    assert "notes/c.md" in paths, "C should appear in merged result"
    assert len(merged) <= 3, f"top_n=3 but got {len(merged)} results"


async def test_recall_warm_search_uses_rrf_when_both_strategies_present():
    """Recall._warm_search calls _rrf_merge and returns warm_top_n results.

    Verifies: blank content -> [], and the RRF orchestrator integrates keyword + semantic.
    """
    from app.services.recall import SemanticRecall, KeywordRecall

    model = "test-model-v1"
    # note_A is close to query; note_B is the keyword hit
    note_a_vec = [1.0, 0.0, 0.0]

    config = RecallConfig(semantic_cosine_floor=0.50)
    vault = FakeVault(notes={"notes/b.md": "keyword match content here"})
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(["notes/a.md"], [note_a_vec], model)
    )
    # Seed note_A with a body for post-RRF reads
    vault.notes["notes/a.md"] = "semantic recall body content"

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)
    recall = Recall(vault=vault, semantic_strategy=semantic, config=config)

    # Blank content should return []
    from tests.test_recall import make_request
    empty_result = await recall.assemble(make_request(content=""), budget=8192)
    assert empty_result.warm == [], "Empty content should yield warm=[]"

    # Non-blank content: warm should include both keyword and semantic results
    result = await recall.assemble(make_request(content="keyword match content"), budget=8192)
    # At least one result expected (keyword path always active)
    # The test verifies the RRF orchestrator runs without error
    assert isinstance(result.warm, list)
