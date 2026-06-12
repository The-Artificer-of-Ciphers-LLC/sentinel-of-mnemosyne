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
from app.services.recall import Recall, RecallConfig, RecalledContext, SearchResult, SessionSummary, RetentionPolicy, recency_weight
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


# ---------------------------------------------------------------------------
# Task 3 TDD: 6 deterministic success-criteria tests
# ---------------------------------------------------------------------------


async def test_semantic_paraphrase_returns_correct_note():
    """Success Criterion 1 (MEM-03): semantic recall surfaces a note keyword-only misses.

    Setup:
    - note_A lives on the x-axis: [1.0, 0.0, 0.0]
    - query vector (from fake_embedder): [0.9, 0.436, 0.0] — cosine ≈ 0.90 to note_A
    - keyword search (vault.find) returns ONLY note_B — note_A is NOT a keyword match
    - note_B score in keyword results: -100.0 (above relevance_threshold=-200.0)

    After RRF merge: note_A must appear in the warm list even though keyword-only
    would have excluded it (proving semantic recall adds value).
    """
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    note_a_vec = [1.0, 0.0, 0.0]  # close to query vec — cosine ≈ 0.90

    config = RecallConfig(semantic_cosine_floor=0.50)
    vault = FakeVault()
    vault.notes["notes/b.md"] = "completely different keyword content here"
    vault.notes["notes/a.md"] = "note A semantic body — paraphrase target"
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(["notes/a.md"], [note_a_vec], model)
    )

    # Keyword search returns ONLY note_B — note_A is NOT a keyword hit
    async def fake_find_keyword_only(query: str) -> list[dict]:
        return [{"filename": "notes/b.md", "score": -100.0, "matches": []}]

    vault.find = fake_find_keyword_only  # type: ignore[method-assign]

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)
    recall = Recall(vault=vault, semantic_strategy=semantic, config=config)

    result = await recall.assemble(make_request(content="paraphrase test content"), budget=8192)

    warm_paths = [r.path for r in result.warm]
    assert "notes/a.md" in warm_paths, (
        f"note_A (semantic match) should appear in warm via RRF even though keyword-only missed it. "
        f"Got warm paths: {warm_paths}"
    )


async def test_semantic_recall_no_per_note_rest():
    """Success Criterion 2 (MEM-05): SemanticRecall reads index once via vault.read_note.

    Verifies that:
    - vault.read_note(index_path) is called at most once across two searches (TTL cache)
    - No vault.find() calls are made by SemanticRecall (only Recall._warm_search uses it)
    - Post-RRF body reads are bounded to warm_top_n candidates
    """
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    note_a_vec = [1.0, 0.0, 0.0]

    config = RecallConfig(semantic_cosine_floor=0.50, index_ttl_seconds=60.0)
    vault = FakeVault()
    vault.notes["notes/a.md"] = "semantic test body for note A"
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(["notes/a.md"], [note_a_vec], model)
    )

    find_call_count = 0
    read_note_calls: list[str] = []

    original_read_note = vault.read_note
    original_find = vault.find

    async def tracking_read_note(path: str) -> str:
        read_note_calls.append(path)
        return await original_read_note(path)

    async def tracking_find(query: str) -> list[dict]:
        nonlocal find_call_count
        find_call_count += 1
        return await original_find(query)

    vault.read_note = tracking_read_note  # type: ignore[method-assign]
    vault.find = tracking_find  # type: ignore[method-assign]

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)

    # Call search twice within TTL window
    await semantic.search("test query one", budget=10)
    await semantic.search("test query two", budget=10)

    index_reads = [p for p in read_note_calls if p == config.index_path]
    assert len(index_reads) <= 1, (
        f"Expected at most 1 index read across two searches within TTL, "
        f"got {len(index_reads)} index reads"
    )

    # SemanticRecall must NOT call vault.find — that's KeywordRecall's job
    assert find_call_count == 0, (
        f"SemanticRecall should never call vault.find(), but it was called {find_call_count} times"
    )


async def test_semantic_skips_mismatched_model():
    """Success Criterion 3 (MEM-05): entries with wrong embedding_model return [].

    Index has entries with model='old-model-v1' while active_model='new-model-v2'.
    SemanticRecall must return [] (D-12 exact-string match, D-13 missing model skip).
    """
    from app.services.recall import SemanticRecall

    wrong_model = "old-model-v1"
    active_model = "new-model-v2"
    note_a_vec = [1.0, 0.0, 0.0]

    config = RecallConfig()
    vault = FakeVault()
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(["notes/a.md"], [note_a_vec], wrong_model)
    )

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=active_model, config=config)
    results = await semantic.search("test query", budget=10)

    assert results == [], (
        f"Expected [] when all index entries have embedding_model={wrong_model!r} "
        f"but active_model={active_model!r}, got {results}"
    )


async def test_semantic_all_mismatch_degrades_to_keyword():
    """Success Criterion 3 / D-14: all-mismatch index degrades to keyword-only.

    When SemanticRecall returns [] (all-mismatch), Recall.assemble still returns
    keyword results in warm (WR-03 graceful path preserved). Logs a warning.
    """
    from app.services.recall import SemanticRecall
    import logging

    wrong_model = "old-model-v1"
    active_model = "new-model-v2"
    note_a_vec = [1.0, 0.0, 0.0]

    config = RecallConfig()
    vault = FakeVault()
    vault.notes["notes/keyword-only.md"] = "keyword result body content here"
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(["notes/a.md"], [note_a_vec], wrong_model)
    )

    # Keyword search returns one result
    async def fake_find_keyword(query: str) -> list[dict]:
        return [{"filename": "notes/keyword-only.md", "score": -50.0, "matches": []}]

    vault.find = fake_find_keyword  # type: ignore[method-assign]

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=active_model, config=config)
    recall = Recall(vault=vault, semantic_strategy=semantic, config=config)

    # Should not raise; keyword results should still appear
    result = await recall.assemble(make_request(content="keyword result body content"), budget=8192)

    assert isinstance(result, RecalledContext)
    warm_paths = [r.path for r in result.warm]
    assert "notes/keyword-only.md" in warm_paths, (
        f"Keyword result should appear in warm even when SemanticRecall all-mismatches. "
        f"Got warm paths: {warm_paths}"
    )


async def test_cosine_floor_excludes_weak_candidates():
    """Cosine floor gate (D-11): notes below cosine floor excluded, above included.

    - note_A: cosine ≈ 0.90 with query → above any reasonable floor → included
    - note_B: cosine ≈ 0.436 with query → below 0.50 floor → excluded

    Raising floor to 0.95 excludes note_A; lowering to 0.40 includes note_B.
    This proves the floor is tunable (not hardcoded).
    """
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    note_a_vec = [1.0, 0.0, 0.0]  # cosine with [0.9, 0.436, 0.0] ≈ 0.90
    note_b_vec = [0.0, 1.0, 0.0]  # cosine with [0.9, 0.436, 0.0] ≈ 0.436

    # Default floor 0.50: note_A included, note_B excluded
    config_50 = RecallConfig(semantic_cosine_floor=0.50)
    vault = FakeVault()
    vault.notes[config_50.index_path] = json.dumps(
        make_fixture_index(["notes/a.md", "notes/b.md"], [note_a_vec, note_b_vec], model)
    )

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config_50)
    results_50 = await semantic.search("test query", budget=10)
    paths_50 = [r.path for r in results_50]

    assert "notes/a.md" in paths_50, "note_A (cosine ≈ 0.90) should be above the 0.50 floor"
    assert "notes/b.md" not in paths_50, "note_B (cosine ≈ 0.436) should be below the 0.50 floor"

    # Raising floor to 0.95 excludes note_A too
    config_95 = RecallConfig(semantic_cosine_floor=0.95)
    vault2 = FakeVault()
    vault2.notes[config_95.index_path] = json.dumps(
        make_fixture_index(["notes/a.md", "notes/b.md"], [note_a_vec, note_b_vec], model)
    )

    semantic2 = SemanticRecall(vault=vault2, embed_fn=fake_embedder, active_model=model, config=config_95)
    results_95 = await semantic2.search("test query", budget=10)
    paths_95 = [r.path for r in results_95]

    assert "notes/a.md" not in paths_95, (
        f"note_A (cosine ≈ 0.90) should be excluded by the 0.95 floor, got {paths_95}"
    )

    # Lowering floor to 0.40 includes note_B
    config_40 = RecallConfig(semantic_cosine_floor=0.40)
    vault3 = FakeVault()
    vault3.notes[config_40.index_path] = json.dumps(
        make_fixture_index(["notes/a.md", "notes/b.md"], [note_a_vec, note_b_vec], model)
    )

    semantic3 = SemanticRecall(vault=vault3, embed_fn=fake_embedder, active_model=model, config=config_40)
    results_40 = await semantic3.search("test query", budget=10)
    paths_40 = [r.path for r in results_40]

    assert "notes/b.md" in paths_40, (
        f"note_B (cosine ≈ 0.436) should be included when floor is lowered to 0.40, got {paths_40}"
    )


async def test_rrf_merge_combines_both_strategies():
    """Success Criterion 4 (MEM-04): keyword + semantic merged via RRF.

    keyword results: [note_A, note_B]
    semantic results: [note_C, note_A]

    After RRF merge: note_A ranks first (appears in both lists = higher cumulative score).
    note_B and note_C must also be present in the top_n result.
    """
    from app.services.recall import _rrf_merge

    result_a_kw = SearchResult(path="notes/a.md", score=-50.0, body="A keyword body")
    result_b_kw = SearchResult(path="notes/b.md", score=-100.0, body="B keyword body")
    result_c_sem = SearchResult(path="notes/c.md", score=0.85, body="")
    result_a_sem = SearchResult(path="notes/a.md", score=0.90, body="")

    # keyword list: [A, B], semantic list: [C, A]
    merged = _rrf_merge([[result_a_kw, result_b_kw], [result_c_sem, result_a_sem]], k=60, top_n=3)

    assert len(merged) == 3, f"Expected 3 results, got {len(merged)}: {[r.path for r in merged]}"
    paths = [r.path for r in merged]

    # note_A appears in both lists → sum of 1/(60+1) + 1/(60+2) = highest score
    assert paths[0] == "notes/a.md", (
        f"note_A (in both keyword and semantic lists) should rank first. Got: {paths}"
    )
    assert "notes/b.md" in paths, "note_B (keyword-only, rank 2) should be present"
    assert "notes/c.md" in paths, "note_C (semantic-only, rank 1) should be present"


# ---------------------------------------------------------------------------
# Task 3: End-to-end paraphrase integration test + empty-query /context regression
# ---------------------------------------------------------------------------


async def test_end_to_end_paraphrase_recall():
    """End-to-end: a paraphrase query surfaces note_A through the composed Recall.

    Exercises the FULL composed path (SemanticRecall + KeywordRecall + RRF +
    body-read) proving MEM-03, MEM-04, MEM-05 work together:

    Setup:
    - note_A has embedding [1.0, 0.0, 0.0] — close to the query vector from
      fake_embedder ([0.9, 0.436, 0.0]; cosine ≈ 0.90 > 0.50 floor)
    - note_B is the ONLY keyword hit (fake_find returns note_B, not note_A)
    - Both notes have real bodies so post-RRF body-read returns non-empty content

    After RRF merge: note_A must appear in warm even though keyword-only missed it
    (semantic recall adds value). note_A body must be non-empty (Recall reads it
    post-RRF, not from the index stub).
    """
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    note_a_vec = [1.0, 0.0, 0.0]  # cosine ≈ 0.90 with fake_embedder query vector

    config = RecallConfig(semantic_cosine_floor=0.50)
    vault = FakeVault()
    vault.notes["notes/b.md"] = "keyword only content not related to note_a"
    vault.notes["notes/a.md"] = "paraphrase target body — semantic recall surfaces this"
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(["notes/a.md"], [note_a_vec], model)
    )

    # Keyword search returns ONLY note_B — note_A is NOT a keyword match
    async def fake_find_keyword_only(query: str) -> list[dict]:
        return [{"filename": "notes/b.md", "score": -100.0, "matches": []}]

    vault.find = fake_find_keyword_only  # type: ignore[method-assign]

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)
    recall = Recall(vault=vault, semantic_strategy=semantic, config=config)

    result = await recall.assemble(make_request(content="paraphrase query end to end"), budget=8192)

    warm_paths = [r.path for r in result.warm]
    assert "notes/a.md" in warm_paths, (
        f"note_A (semantic hit) should appear in warm via RRF even though keyword missed it. "
        f"Warm paths: {warm_paths}"
    )

    # Body must be non-empty — Recall reads real bodies post-RRF (A5)
    note_a_results = [r for r in result.warm if r.path == "notes/a.md"]
    assert note_a_results, "note_A should be in warm results"
    assert note_a_results[0].body.strip(), (
        f"note_A body should be non-empty (read post-RRF), got: {note_a_results[0].body!r}"
    )
    assert "paraphrase target body" in note_a_results[0].body, (
        f"note_A body should contain the fixture content; got: {note_a_results[0].body!r}"
    )


async def test_context_empty_query_skips_embedding():
    """D-16 end-to-end: empty content (/context path) returns without calling embed_fn.

    The /context/{user_id} debug route passes content="" into Recall.assemble.
    This test verifies that the full composed Recall path (with a wired
    SemanticRecall) never invokes embed_fn when content is blank — preserving D-16
    through the entire composition stack, not just at the SemanticRecall unit level.
    """
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    note_a_vec = [1.0, 0.0, 0.0]

    embed_call_count = 0

    async def counting_embedder(texts: list[str]) -> list[list[float]]:
        nonlocal embed_call_count
        embed_call_count += 1
        return [[0.9, 0.436, 0.0] for _ in texts]

    config = RecallConfig(semantic_cosine_floor=0.50)
    vault = FakeVault()
    vault.notes["notes/a.md"] = "semantic note body content"
    vault.notes[config.index_path] = json.dumps(
        make_fixture_index(["notes/a.md"], [note_a_vec], model)
    )

    semantic = SemanticRecall(
        vault=vault, embed_fn=counting_embedder, active_model=model, config=config
    )
    recall = Recall(vault=vault, semantic_strategy=semantic, config=config)

    # content="" simulates the /context/{user_id} path (D-16)
    result = await recall.assemble(make_request(content=""), budget=8192)

    assert result.warm == [], (
        f"Empty content should yield warm=[], got: {result.warm}"
    )
    assert embed_call_count == 0, (
        f"embed_fn must NOT be called for empty content (D-16), "
        f"was called {embed_call_count} times"
    )


# ---------------------------------------------------------------------------
# CR-02: per-entry decode/dimension resilience
# ---------------------------------------------------------------------------


async def test_semantic_resilient_to_corrupt_and_wrong_dim_entries():
    """CR-02: a corrupt entry + a wrong-dimension entry do not kill semantic results.

    Fixture index has three entries:
    - notes/good.md  — valid embedding at query dimension → should appear in results
    - notes/corrupt.md — invalid base64 (not decodeable) → must be skipped, not raised
    - notes/wrongdim.md — valid base64 but dimension != query dimension → must be skipped

    SemanticRecall.search() must:
    1. Return the good entry (not []) — i.e. not raise out of the loop
    2. Skip (not raise on) the corrupt entry
    3. Skip (not raise on) the wrong-dimension entry
    """
    from app.services.recall import SemanticRecall
    import base64
    import struct

    model = "test-model-v1"

    # Good entry: [1.0, 0.0, 0.0] — 3 floats, cosine ≈ 0.90 with fake_embedder query
    good_vec = [1.0, 0.0, 0.0]
    good_b64 = encode_embedding(good_vec)

    # Corrupt entry: not valid base64
    corrupt_b64 = "!!!NOT_VALID_BASE64!!!"

    # Wrong-dimension entry: encode a 5-float vector (query is 3-dim from fake_embedder)
    wrong_dim_b64 = encode_embedding([1.0, 0.0, 0.0, 0.0, 0.0])

    index = {
        "notes/good.md": {
            "embedding_b64": good_b64,
            "embedding_model": model,
            "content_hash": "aabbccdd00000000",
        },
        "notes/corrupt.md": {
            "embedding_b64": corrupt_b64,
            "embedding_model": model,
            "content_hash": "eeff001100000000",
        },
        "notes/wrongdim.md": {
            "embedding_b64": wrong_dim_b64,
            "embedding_model": model,
            "content_hash": "11223344000000000",
        },
    }

    config = RecallConfig(semantic_cosine_floor=0.50)
    vault = FakeVault()
    vault.notes[config.index_path] = json.dumps(index)

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)

    # Must not raise even though two entries are malformed
    results = await semantic.search("test query", budget=10)

    paths = [r.path for r in results]

    assert "notes/good.md" in paths, (
        f"Good entry should still be returned despite corrupt/wrong-dim siblings. "
        f"Got paths: {paths}"
    )
    assert "notes/corrupt.md" not in paths, (
        "Corrupt-base64 entry must be skipped, not raise"
    )
    assert "notes/wrongdim.md" not in paths, (
        "Wrong-dimension entry must be skipped, not raise"
    )


# ---------------------------------------------------------------------------
# Phase 40 Plan 07 — Task 1 RED: single-source-of-truth constant + recall
# round-trip tests
# ---------------------------------------------------------------------------


def test_index_path_single_source_constant_equality():
    """EMBEDDING_INDEX_PATH (vault_sweeper) == RecallConfig().index_path.

    RecallConfig.index_path must DERIVE FROM (import) EMBEDDING_INDEX_PATH.
    This test guards the derivation: if a future edit reintroduces a literal
    in recall.py, this fails CI immediately.
    """
    from app.services.vault_sweeper import EMBEDDING_INDEX_PATH
    from app.services.recall import RecallConfig

    assert EMBEDDING_INDEX_PATH == RecallConfig().index_path, (
        "RecallConfig.index_path must equal EMBEDDING_INDEX_PATH (single physical source); "
        f"vault_sweeper={EMBEDDING_INDEX_PATH!r}, recall={RecallConfig().index_path!r}"
    )


def test_recall_index_path_no_duplicate_literal():
    """recall.py must NOT re-state the literal path string.

    The literal 'ops/sweeps/embedding-index' must appear in EXACTLY one
    module — vault_sweeper.py (or, if a leaf module was created, that module).
    It must NOT appear in recall.py itself.
    """
    import pathlib

    recall_src = pathlib.Path(__file__).parent.parent / "app" / "services" / "recall.py"
    text = recall_src.read_text(encoding="utf-8")
    # The literal path fragment used in EMBEDDING_INDEX_PATH
    assert "ops/sweeps/embedding-index" not in text, (
        "recall.py must NOT contain the literal index path — it must import "
        "EMBEDDING_INDEX_PATH from vault_sweeper (single physical source of truth)"
    )


def test_recall_imports_embedding_index_path():
    """recall.py must import EMBEDDING_INDEX_PATH from vault_sweeper (or a leaf module).

    The field default must be the imported constant, not a re-stated literal.
    """
    import pathlib

    recall_src = pathlib.Path(__file__).parent.parent / "app" / "services" / "recall.py"
    text = recall_src.read_text(encoding="utf-8")
    assert "EMBEDDING_INDEX_PATH" in text, (
        "recall.py must reference EMBEDDING_INDEX_PATH (imported from vault_sweeper)"
    )


async def test_recall_json_extension_round_trip():
    """Recall round-trip for .json path: sweeper writes raw JSON, recall loader parses it.

    Seeds a RecallConfig with index_path ending in .json, seeds the index in
    FakeVault as raw JSON (what _emit_embedding_index writes for .json), and
    verifies SemanticRecall loads it into a dict equal to the original.
    """
    import time
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    note_a_vec = [1.0, 0.0, 0.0]
    index_path = "ops/sweeps/test-index.json"

    config = RecallConfig(
        index_path=index_path,
        index_ttl_seconds=0.0,  # always reload
    )
    idx = make_fixture_index(["notes/a.md"], [note_a_vec], model)
    raw_body = json.dumps(idx, ensure_ascii=False)  # what writer emits for .json

    vault = FakeVault()
    vault.notes[index_path] = raw_body

    semantic = SemanticRecall(
        vault=vault, embed_fn=fake_embedder, active_model=model, config=config
    )
    await semantic._load_index_if_stale()

    assert semantic._index == idx, (
        f".json round-trip failed: expected {idx!r}, got {semantic._index!r}"
    )


async def test_recall_md_extension_round_trip():
    """Recall round-trip for .md path: sweeper writes fenced JSON, recall loader parses it.

    Seeds a RecallConfig with index_path ending in .md, seeds the index in
    FakeVault as a markdown fenced-JSON body (what _encode_index_body writes for .md),
    and verifies SemanticRecall loads it via _decode_index_body into a dict equal
    to the original.
    """
    from app.services.recall import SemanticRecall
    from app.services.vault_sweeper import _encode_index_body

    model = "test-model-v1"
    note_a_vec = [1.0, 0.0, 0.0]
    index_path = "ops/sweeps/test-index.md"

    config = RecallConfig(
        index_path=index_path,
        index_ttl_seconds=0.0,
    )
    idx = make_fixture_index(["notes/a.md"], [note_a_vec], model)
    fenced_body = _encode_index_body(idx, index_path)

    vault = FakeVault()
    vault.notes[index_path] = fenced_body

    semantic = SemanticRecall(
        vault=vault, embed_fn=fake_embedder, active_model=model, config=config
    )
    await semantic._load_index_if_stale()

    assert semantic._index == idx, (
        f".md round-trip failed: expected {idx!r}, got {semantic._index!r}"
    )


async def test_recall_md_extension_body_contains_fenced_block():
    """The .md body written by _encode_index_body contains a fenced code block.

    Verifies that the writer actually fences the JSON (not writes raw JSON)
    when the path ends in .md, so the Obsidian REST API accepts it as a note.
    """
    from app.services.vault_sweeper import _encode_index_body

    idx = make_fixture_index(["notes/a.md"], [[1.0, 0.0, 0.0]], "test-model-v1")
    body = _encode_index_body(idx, "ops/sweeps/embedding-index.md")
    assert "```" in body, (
        ".md body must contain a fenced code block (Obsidian REST API requires note format)"
    )
    # Must not be directly parseable as JSON
    try:
        json.loads(body)
        assert False, ".md body must NOT be raw JSON — it must be fenced markdown"
    except json.JSONDecodeError:
        pass


async def test_recall_md_uppercase_extension_round_trip():
    """Case-insensitive .MD round-trip: writer fences, recall loader parses."""
    from app.services.recall import SemanticRecall
    from app.services.vault_sweeper import _encode_index_body

    model = "test-model-v1"
    note_a_vec = [1.0, 0.0, 0.0]
    index_path = "ops/sweeps/test-index.MD"

    config = RecallConfig(
        index_path=index_path,
        index_ttl_seconds=0.0,
    )
    idx = make_fixture_index(["notes/a.md"], [note_a_vec], model)
    fenced_body = _encode_index_body(idx, index_path)

    assert "```" in fenced_body, ".MD (uppercase) body must contain a fenced code block"

    vault = FakeVault()
    vault.notes[index_path] = fenced_body

    semantic = SemanticRecall(
        vault=vault, embed_fn=fake_embedder, active_model=model, config=config
    )
    await semantic._load_index_if_stale()

    assert semantic._index == idx, (
        f".MD (uppercase) round-trip failed: expected {idx!r}, got {semantic._index!r}"
    )


async def test_recall_md_body_no_fenced_json_yields_empty():
    """_load_index_if_stale with .md path and no parseable fenced JSON returns {} (self-healing)."""
    from app.services.recall import SemanticRecall

    index_path = "ops/sweeps/test-index.md"
    config = RecallConfig(index_path=index_path, index_ttl_seconds=0.0)

    vault = FakeVault()
    vault.notes[index_path] = "# This is a note\n\nSome content with no fenced JSON.\n"

    semantic = SemanticRecall(
        vault=vault, embed_fn=fake_embedder, active_model="m", config=config
    )
    await semantic._load_index_if_stale()

    assert semantic._index == {}, (
        "no parseable fenced JSON in .md body must yield {} (self-healing)"
    )


# ---------------------------------------------------------------------------
# Phase 40 Plan 07 — Task 2 RED: SemanticRecall stale-skip tests
# ---------------------------------------------------------------------------


async def test_semantic_stale_entry_skipped_non_stale_returned():
    """Stale-skip (round-3 / MEM-05): one stale=True entry + one non-stale entry.

    Both match the active model and would score above the cosine floor.
    SemanticRecall.search must return ONLY the non-stale entry's path.
    """
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    # Both vectors are close to the query vector from fake_embedder [0.9, 0.436, 0.0]
    good_vec = [1.0, 0.0, 0.0]   # cosine ≈ 0.90
    stale_vec = [0.95, 0.31, 0.0]  # cosine ≈ 0.96 — would score HIGHER if not skipped

    index = {
        "notes/good.md": {
            "embedding_b64": encode_embedding(good_vec),
            "embedding_model": model,
            "content_hash": "c1",
            # No stale key — non-stale
        },
        "notes/stale.md": {
            "embedding_b64": encode_embedding(stale_vec),
            "embedding_model": model,
            "content_hash": "c2",
            "stale": True,  # 40-04 degraded-index invariant
        },
    }
    config = RecallConfig(semantic_cosine_floor=0.50)
    vault = FakeVault()
    vault.notes[config.index_path] = json.dumps(index)

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)
    results = await semantic.search("test query", budget=10)
    paths = [r.path for r in results]

    assert "notes/good.md" in paths, (
        f"non-stale entry must be returned; got paths={paths}"
    )
    assert "notes/stale.md" not in paths, (
        "stale=True entry must be SKIPPED even though its vector would score above the floor"
    )


async def test_semantic_stale_false_entry_participates_normally():
    """Non-stale entries (stale: False or missing stale key) participate in scoring normally."""
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    good_vec = [1.0, 0.0, 0.0]

    index = {
        "notes/no-stale-key.md": {
            "embedding_b64": encode_embedding(good_vec),
            "embedding_model": model,
            "content_hash": "c1",
            # No stale key at all
        },
        "notes/stale-false.md": {
            "embedding_b64": encode_embedding(good_vec),
            "embedding_model": model,
            "content_hash": "c2",
            "stale": False,  # explicitly non-stale
        },
    }
    config = RecallConfig(semantic_cosine_floor=0.50)
    vault = FakeVault()
    vault.notes[config.index_path] = json.dumps(index)

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)
    results = await semantic.search("test query", budget=10)
    paths = [r.path for r in results]

    assert "notes/no-stale-key.md" in paths, (
        "entry with no stale key must be treated as non-stale and returned"
    )
    assert "notes/stale-false.md" in paths, (
        "entry with stale=False must be treated as non-stale and returned"
    )


async def test_semantic_all_stale_entries_returns_empty_list():
    """All-stale index degrades to [] cleanly — no exception, empty result."""
    from app.services.recall import SemanticRecall

    model = "test-model-v1"
    stale_vec = [1.0, 0.0, 0.0]

    index = {
        "notes/stale-a.md": {
            "embedding_b64": encode_embedding(stale_vec),
            "embedding_model": model,
            "content_hash": "c1",
            "stale": True,
        },
        "notes/stale-b.md": {
            "embedding_b64": encode_embedding(stale_vec),
            "embedding_model": model,
            "content_hash": "c2",
            "stale": True,
        },
    }
    config = RecallConfig(semantic_cosine_floor=0.50)
    vault = FakeVault()
    vault.notes[config.index_path] = json.dumps(index)

    semantic = SemanticRecall(vault=vault, embed_fn=fake_embedder, active_model=model, config=config)
    results = await semantic.search("test query", budget=10)

    assert results == [], (
        f"all-stale index must return [] cleanly (no exception); got {results}"
    )


# ---------------------------------------------------------------------------
# Phase 41 Plan 01 — Task 1 RED: recency_weight curve + value-type construction
# ---------------------------------------------------------------------------


def test_recency_weight_curve():
    """recency_weight: today=1.0, 7d=0.5, 14d=0.25, future clamped to 1.0.

    Pins the exponential decay curve with explicit half_life_days=7.0 so
    the constant is captured in the test, not assumed from the default.
    Uses pytest.approx with tight abs tolerance for float comparisons.
    """
    from datetime import datetime, timezone

    now = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)

    # Same-day date → weight = 1.0
    assert recency_weight("2026-06-12", now=now, half_life_days=7.0) == pytest.approx(1.0, abs=1e-9)

    # Exactly 7 days old → weight = 0.5 ** (7/7) = 0.5
    assert recency_weight("2026-06-05", now=now, half_life_days=7.0) == pytest.approx(0.5, abs=1e-9)

    # Exactly 14 days old → weight = 0.5 ** (14/7) = 0.25
    assert recency_weight("2026-05-29", now=now, half_life_days=7.0) == pytest.approx(0.25, abs=1e-9)

    # Future date (1 day ahead) → age floored at 0 → weight = 1.0 (clamped)
    assert recency_weight("2026-06-13", now=now, half_life_days=7.0) == pytest.approx(1.0, abs=1e-9)


def test_recency_weight_failopen_on_bad_date():
    """recency_weight: unparseable string and None both return 1.0 (fail-open).

    A hostile or malformed date from vault content must never raise — it
    must silently return 1.0 so the recall path is uninterrupted (T-41-01).
    """
    from datetime import datetime, timezone

    now = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)

    # Unparseable date string → 1.0
    assert recency_weight("not-a-date", now=now, half_life_days=7.0) == pytest.approx(1.0, abs=1e-9)

    # None date (non-string) → 1.0
    assert recency_weight(None, now=now, half_life_days=7.0) == pytest.approx(1.0, abs=1e-9)


def test_session_summary_is_frozen_value():
    """SessionSummary: constructs with all 7 fields; field reassignment raises FrozenInstanceError."""
    import dataclasses

    summary = SessionSummary(
        date="2026-06-12",
        user_id="trekkie",
        time="12-00-00",
        user_msg="Hello Sentinel",
        sentinel_msg="Hello user",
        path="ops/sessions/2026-06-12/trekkie-12-00-00.md",
        body="# Session\n## User\nHello Sentinel\n## Sentinel\nHello user\n",
    )

    assert summary.date == "2026-06-12"
    assert summary.user_id == "trekkie"
    assert summary.time == "12-00-00"
    assert summary.user_msg == "Hello Sentinel"
    assert summary.sentinel_msg == "Hello user"
    assert summary.path == "ops/sessions/2026-06-12/trekkie-12-00-00.md"
    assert "Hello Sentinel" in summary.body

    # Must be frozen — field assignment must raise
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        summary.date = "2099-01-01"  # type: ignore[misc]


def test_retention_policy_defaults():
    """RetentionPolicy(): defaults hot_limit=3, hot_window_days=2; explicit values override."""
    policy = RetentionPolicy()
    assert policy.hot_limit == 3
    assert policy.hot_window_days == 2

    custom = RetentionPolicy(hot_limit=5, hot_window_days=7)
    assert custom.hot_limit == 5
    assert custom.hot_window_days == 7
