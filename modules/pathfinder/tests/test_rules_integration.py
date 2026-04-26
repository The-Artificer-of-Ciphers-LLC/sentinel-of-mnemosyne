"""Integration tests for /rule — full vault round-trip with mocked LLM (RUL-01..04).

Wave 0 RED scaffolding — implementation lands in Waves 1-3.
Stubs reference app.routes.rule (Wave 3 / Plan 33-04) which does not yet exist.
Collection succeeds; runtime `patch()` of the missing attribute fails with
AttributeError — the honest RED signal.

Decision coverage: D-02 retrieval flow, D-04 cache path, D-05 reuse ≥ 0.80,
D-06 PF1 decline (no cache write), D-13 query_embedding frontmatter,
D-14 last_reused_at update on cache hit.
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Fixture helpers — 5-chunk mini-corpus and AoN URL map from JSON fixtures
# ---------------------------------------------------------------------------


_FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_corpus_fixture():
    return json.loads((_FIXTURE_DIR / "rules_corpus_fixture.json").read_text())


def _load_aon_map_fixture():
    return json.loads((_FIXTURE_DIR / "aon_url_map_fixture.json").read_text())


def _make_stub_index():
    """Build a RulesIndex stub from the 5-chunk fixture with unit-vector rows.

    Import is inside the function so test collection succeeds before Plan 33-02
    creates app.rules. Wave 1 lands RuleChunk + RulesIndex.
    """
    import numpy as np

    from app.rules import RuleChunk, RulesIndex

    raw = _load_corpus_fixture()
    chunks = [RuleChunk.model_validate(c) for c in raw["chunks"]]
    # Identity-basis rows — 5 unit vectors in 5 dims, one per chunk.
    dim = len(chunks)
    matrix = np.eye(dim, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    topic_index: dict[str, list[int]] = {}
    for i, chunk in enumerate(chunks):
        for topic in chunk.topics:
            topic_index.setdefault(topic, []).append(i)
    return RulesIndex(chunks=chunks, matrix=matrix, norms=norms, topic_index=topic_index)


# ---------------------------------------------------------------------------
# StatefulMockVault — extends Phase 32 pattern with list_directory for D-05 scan
# ---------------------------------------------------------------------------


class StatefulMockVault:
    """In-memory vault mock — extends Phase 32 harvest pattern.

    Adds list_directory(prefix) for reuse-match scan (D-05): the route lists
    sibling files under mnemosyne/pf2e/rulings/{topic}/, reads each via
    get_note, parses query_embedding from frontmatter, computes cosine.

    Reuses get_note / put_note AsyncMocks so tests can assert on await counts.
    """

    def __init__(self, initial: dict[str, str]):
        self._store: dict[str, str] = dict(initial)
        self.get_note = AsyncMock(side_effect=self._get)
        self.put_note = AsyncMock(side_effect=self._put)
        self.list_directory = AsyncMock(side_effect=self._list)

    async def _get(self, path: str) -> str | None:
        return self._store.get(path)

    async def _put(self, path: str, content: str) -> None:
        self._store[path] = content

    async def _list(self, prefix: str) -> list[str]:
        return sorted(k for k in self._store.keys() if k.startswith(prefix))


# ---------------------------------------------------------------------------
# Integration tests — Waves 1-3 GREEN target
# ---------------------------------------------------------------------------


async def test_first_query_writes_cache_second_reads_cache():
    """Identical-query exact-hash path (D-04). Second call updates last_reused_at (D-14).

    Call 1: POST /rule/query — corpus-hit → LLM composes source ruling → cache
    PUT at mnemosyne/pf2e/rulings/flanking/{hash}.md. Expect 1 put_note call.
    Call 2: identical payload — cache HIT (exact hash match). LLM NOT called.
    put_note called ONCE more (D-14 last_reused_at update via GET-then-PUT).
    Response on call 2 carries reused=True.
    """

    vault = StatefulMockVault({})
    stub_index = _make_stub_index()
    stub_map = _load_aon_map_fixture()

    # Embed returns the first corpus row so retrieval hits chunk 0 (flanking).
    embed_vec = [1.0, 0.0, 0.0, 0.0, 0.0]
    mock_embed = AsyncMock(return_value=[embed_vec])

    mock_llm_pass = AsyncMock(return_value={
        "question": "How does flanking work?",
        "answer": "Flanking makes the target off-guard (-2 AC).",
        "why": "Two allies on opposite sides impose off-guard.",
        "source": "Pathfinder Player Core p. 416 — Flanking",
        "citations": [{
            "book": "Pathfinder Player Core", "page": "416",
            "section": "Flanking",
            "url": "https://2e.aonprd.com/Rules.aspx?ID=1349",
        }],
        "marker": "source",
        "topic": "flanking",
    })
    mock_llm_fall = AsyncMock(side_effect=AssertionError("fallback must not be called on corpus hit"))

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.rule.obsidian", vault), \
         patch("app.routes.rule.rules_index", stub_index), \
         patch("app.routes.rule.aon_url_map", stub_map), \
         patch("app.routes.rule.generate_ruling_from_passages", new=mock_llm_pass), \
         patch("app.routes.rule.generate_ruling_fallback", new=mock_llm_fall), \
         patch("app.routes.rule.keyword_classify_topic", return_value=None), \
         patch("app.routes.rule.classify_rule_topic", new=AsyncMock(return_value="flanking")), \
         patch("app.routes.rule.embed_texts", new=mock_embed):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = {"query": "How does flanking work?", "user_id": "u1"}

            # Call 1: corpus hit → LLM compose → cache PUT
            resp1 = await client.post("/rule/query", json=payload)
            assert resp1.status_code == 200
            assert vault.put_note.await_count == 1, "first call should write one cache file"
            assert mock_llm_pass.await_count == 1

            body1 = resp1.json()
            assert body1["marker"] == "source"
            assert body1.get("reused") in (None, False)

            # Call 2: identical query — exact-hash cache hit, LLM NOT re-called.
            # D-14: last_reused_at must be updated via GET-then-PUT → put_note += 1
            put_count_before = vault.put_note.await_count
            llm_calls_before = mock_llm_pass.await_count
            resp2 = await client.post("/rule/query", json=payload)
            assert resp2.status_code == 200
            assert mock_llm_pass.await_count == llm_calls_before, "LLM must not be called on cache hit"
            assert vault.put_note.await_count == put_count_before + 1, (
                "last_reused_at update (D-14) requires one GET-then-PUT"
            )

            body2 = resp2.json()
            assert body2.get("reused") is True


async def test_corpus_hit_writes_cache_with_marker_source():
    """RUL-01 full path: retrieval ≥ RETRIEVAL_SIMILARITY_THRESHOLD → LLM composes source ruling."""

    vault = StatefulMockVault({})
    stub_index = _make_stub_index()
    stub_map = _load_aon_map_fixture()

    mock_embed = AsyncMock(return_value=[[1.0, 0.0, 0.0, 0.0, 0.0]])  # hits row 0

    mock_llm_pass = AsyncMock(return_value={
        "question": "flanking rule?",
        "answer": "Flanking imposes off-guard.",
        "why": "Two flanking allies impose -2 AC.",
        "source": "Pathfinder Player Core p. 416 — Flanking",
        "citations": [{
            "book": "Pathfinder Player Core", "page": "416",
            "section": "Flanking",
            "url": "https://2e.aonprd.com/Rules.aspx?ID=1349",
        }],
        "marker": "source",
        "topic": "flanking",
    })
    mock_llm_fall = AsyncMock(side_effect=AssertionError("fallback must not be called on corpus hit"))

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.rule.obsidian", vault), \
         patch("app.routes.rule.rules_index", stub_index), \
         patch("app.routes.rule.aon_url_map", stub_map), \
         patch("app.routes.rule.generate_ruling_from_passages", new=mock_llm_pass), \
         patch("app.routes.rule.generate_ruling_fallback", new=mock_llm_fall), \
         patch("app.routes.rule.keyword_classify_topic", return_value=None), \
         patch("app.routes.rule.classify_rule_topic", new=AsyncMock(return_value="flanking")), \
         patch("app.routes.rule.embed_texts", new=mock_embed):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/rule/query", json={"query": "flanking rule?", "user_id": "u1"}
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["marker"] == "source"
    assert body["source"]
    assert isinstance(body["citations"], list) and len(body["citations"]) >= 1
    assert vault.put_note.await_count == 1


async def test_corpus_miss_writes_cache_with_marker_generated():
    """RUL-02: retrieval returns [] (below threshold) → LLM fallback → marker=generated."""
    vault = StatefulMockVault({})
    stub_index = _make_stub_index()
    stub_map = _load_aon_map_fixture()

    # Query embedding orthogonal to every corpus row → all similarities = 0.
    # In 5-dim identity basis, an additional orthogonal component hits none:
    mock_embed = AsyncMock(return_value=[[0.0, 0.0, 0.0, 0.0, 0.0]])

    mock_llm_pass = AsyncMock(side_effect=AssertionError("passages must not be called on miss"))
    mock_llm_fall = AsyncMock(return_value={
        "question": "Kineticist impulse crit?",
        "answer": "A generated ruling — check the Rage of Elements book.",
        "why": "Outside Player Core corpus; LLM recall only.",
        "source": None,
        "citations": [],
        "marker": "generated",
        "topic": "misc",
    })

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.rule.obsidian", vault), \
         patch("app.routes.rule.rules_index", stub_index), \
         patch("app.routes.rule.aon_url_map", stub_map), \
         patch("app.routes.rule.generate_ruling_from_passages", new=mock_llm_pass), \
         patch("app.routes.rule.generate_ruling_fallback", new=mock_llm_fall), \
         patch("app.routes.rule.classify_rule_topic", new=AsyncMock(return_value="misc")), \
         patch("app.routes.rule.embed_texts", new=mock_embed):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/rule/query",
                json={"query": "Can a Kineticist's impulse crit on a save DC?", "user_id": "u1"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["marker"] == "generated"
    assert body["source"] is None
    assert body["citations"] == []
    assert mock_llm_fall.await_count == 1
    assert vault.put_note.await_count == 1


async def test_pf1_decline_no_cache_write():
    """RUL-04 / D-06: PF1 denylist hit → short-circuits BEFORE any LLM / embed / cache cost."""
    vault = StatefulMockVault({})
    stub_index = _make_stub_index()
    stub_map = _load_aon_map_fixture()

    mock_embed = AsyncMock(side_effect=AssertionError("embed must not be called on PF1 decline"))
    mock_classify = AsyncMock(side_effect=AssertionError("classify must not be called on PF1 decline"))
    mock_llm_pass = AsyncMock(side_effect=AssertionError("LLM must not be called on PF1 decline"))
    mock_llm_fall = AsyncMock(side_effect=AssertionError("LLM fallback must not be called on PF1 decline"))

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.rule.obsidian", vault), \
         patch("app.routes.rule.rules_index", stub_index), \
         patch("app.routes.rule.aon_url_map", stub_map), \
         patch("app.routes.rule.generate_ruling_from_passages", new=mock_llm_pass), \
         patch("app.routes.rule.generate_ruling_fallback", new=mock_llm_fall), \
         patch("app.routes.rule.classify_rule_topic", new=mock_classify), \
         patch("app.routes.rule.embed_texts", new=mock_embed):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/rule/query", json={"query": "What is THAC0?", "user_id": "u1"}
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["marker"] == "declined"
    assert body["answer"].startswith("This Sentinel only supports PF2e Remaster")
    assert body["source"] is None
    assert body["citations"] == []
    assert vault.put_note.await_count == 0
    assert mock_classify.await_count == 0
    assert mock_embed.await_count == 0


async def test_reuse_match_above_0_80_returns_cached_note():
    """D-05: similar-but-not-identical query, cosine ≥ 0.80 against a sibling
    ruling's stored embedding → returns the cached ruling with reuse_note.

    Pre-seed the vault with a flanking ruling whose frontmatter carries a
    known query_embedding ([1,0,0,0]). A NEW query (different hash path)
    mocks embed_texts to return the same [1,0,0,0] vector. The list_directory
    scan finds the sibling, cosine==1.0 ≥ 0.80 → reuse hit.

    Post-conditions: LLM NOT called, no file written at new hash path,
    pre-seeded file's last_reused_at updated (D-14), response reused=True.
    """
    # Build the pre-seeded file manually to match the build_ruling_markdown
    # shape the route's parser will be reading (keys per D-08 + frontmatter
    # embedding fields per D-13).
    preseed_vec = [1.0, 0.0, 0.0, 0.0, 0.0]
    # base64(float32 LE array) — matches D-13 "query_embedding" storage format
    import numpy as np
    b64 = base64.b64encode(np.asarray(preseed_vec, dtype=np.float32).tobytes()).decode("ascii")

    preseed_path = "mnemosyne/pf2e/rulings/flanking/abcd1234.md"
    preseed_md = (
        "---\n"
        "question: How does flanking work?\n"
        "answer: Target is off-guard.\n"
        "why: Two allies on opposite sides.\n"
        "source: Pathfinder Player Core p. 416 — Flanking\n"
        "citations:\n"
        "  - book: Pathfinder Player Core\n"
        "    page: '416'\n"
        "    section: Flanking\n"
        "    url: https://2e.aonprd.com/Rules.aspx?ID=1349\n"
        "marker: source\n"
        "topic: flanking\n"
        "composed_at: '2026-04-20T12:00:00Z'\n"
        "last_reused_at: '2026-04-20T12:00:00Z'\n"
        "embedding_model: text-embedding-nomic-embed-text-v1.5\n"
        f"embedding_hash: {'0' * 40}\n"
        f"query_embedding: {b64}\n"
        "---\n"
        "# How does flanking work?\n"
        "\nTarget is off-guard.\n"
    )

    vault = StatefulMockVault({preseed_path: preseed_md})
    stub_index = _make_stub_index()
    stub_map = _load_aon_map_fixture()

    mock_embed = AsyncMock(return_value=[preseed_vec])
    mock_llm_pass = AsyncMock(side_effect=AssertionError("LLM passages must not be called on reuse hit"))
    mock_llm_fall = AsyncMock(side_effect=AssertionError("LLM fallback must not be called on reuse hit"))

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.rule.obsidian", vault), \
         patch("app.routes.rule.rules_index", stub_index), \
         patch("app.routes.rule.aon_url_map", stub_map), \
         patch("app.routes.rule.generate_ruling_from_passages", new=mock_llm_pass), \
         patch("app.routes.rule.generate_ruling_fallback", new=mock_llm_fall), \
         patch("app.routes.rule.keyword_classify_topic", return_value=None), \
         patch("app.routes.rule.classify_rule_topic", new=AsyncMock(return_value="flanking")), \
         patch("app.routes.rule.embed_texts", new=mock_embed):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # New query — different sha1 hash, same topic folder
            resp = await client.post(
                "/rule/query",
                json={"query": "If I flank an enemy, what happens to their AC?", "user_id": "u1"},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("reused") is True
    assert "reuse_note" in body
    assert "reusing prior ruling on flanking" in body["reuse_note"].lower()
    # list_directory must have been called to scan sibling topic folder
    assert vault.list_directory.await_count >= 1


async def test_reuse_match_below_0_80_composes_fresh():
    """D-05 negative: sibling cosine < 0.80 → LLM composes fresh ruling, new cache file."""
    # Pre-seed with orthogonal embedding → cosine 0.0 → below 0.80 → miss.
    preseed_vec = [0.0, 1.0, 0.0, 0.0, 0.0]
    import numpy as np
    b64 = base64.b64encode(np.asarray(preseed_vec, dtype=np.float32).tobytes()).decode("ascii")

    preseed_path = "mnemosyne/pf2e/rulings/flanking/aaaa1111.md"
    preseed_md = (
        "---\n"
        "question: unrelated flanking question\n"
        "answer: unrelated\n"
        "why: unrelated\n"
        "source: Book p. 1 — X\n"
        "citations: []\n"
        "marker: source\n"
        "topic: flanking\n"
        "composed_at: '2026-04-20T12:00:00Z'\n"
        "last_reused_at: '2026-04-20T12:00:00Z'\n"
        "embedding_model: text-embedding-nomic-embed-text-v1.5\n"
        f"embedding_hash: {'0' * 40}\n"
        f"query_embedding: {b64}\n"
        "---\n"
        "# unrelated flanking question\n"
    )

    vault = StatefulMockVault({preseed_path: preseed_md})
    stub_index = _make_stub_index()
    stub_map = _load_aon_map_fixture()

    # Query embedding orthogonal to pre-seed AND aligned with corpus row 0 (flanking).
    mock_embed = AsyncMock(return_value=[[1.0, 0.0, 0.0, 0.0, 0.0]])

    mock_llm_pass = AsyncMock(return_value={
        "question": "Q",
        "answer": "A fresh compose.",
        "why": "W",
        "source": "Pathfinder Player Core p. 416 — Flanking",
        "citations": [{
            "book": "Pathfinder Player Core", "page": "416",
            "section": "Flanking", "url": "https://2e.aonprd.com/Rules.aspx?ID=1349",
        }],
        "marker": "source",
        "topic": "flanking",
    })

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.rule.obsidian", vault), \
         patch("app.routes.rule.rules_index", stub_index), \
         patch("app.routes.rule.aon_url_map", stub_map), \
         patch("app.routes.rule.generate_ruling_from_passages", new=mock_llm_pass), \
         patch("app.routes.rule.generate_ruling_fallback", new=AsyncMock()), \
         patch("app.routes.rule.keyword_classify_topic", return_value=None), \
         patch("app.routes.rule.classify_rule_topic", new=AsyncMock(return_value="flanking")), \
         patch("app.routes.rule.embed_texts", new=mock_embed):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/rule/query",
                json={"query": "How does flanking apply to AC?", "user_id": "u1"},
            )
    assert resp.status_code == 200
    body = resp.json()
    # Below 0.80 against pre-seed → reuse miss → LLM called, fresh cache file written.
    assert body.get("reused") in (None, False)
    assert mock_llm_pass.await_count == 1
    # Pre-seed + new file = 2 files in store
    flanking_files = [k for k in vault._store.keys() if k.startswith("mnemosyne/pf2e/rulings/flanking/")]
    assert len(flanking_files) >= 2


async def test_rule_reuse_note_survives_cache_roundtrip():
    """CR-03 analog: on exact-hash cache hit the reuse_note text persists.

    Call 1: first query produces a cached ruling. Call 2: identical query →
    cache hit, response has reuse_note "_reusing prior ruling on flanking_".
    Call 3: third identical query → cache hit again, reuse_note TEXT matches
    the call 2 text (was produced from parsed frontmatter, not re-synthesized).
    """
    vault = StatefulMockVault({})
    stub_index = _make_stub_index()
    stub_map = _load_aon_map_fixture()

    mock_embed = AsyncMock(return_value=[[1.0, 0.0, 0.0, 0.0, 0.0]])

    mock_llm_pass = AsyncMock(return_value={
        "question": "Q",
        "answer": "A",
        "why": "W",
        "source": "Pathfinder Player Core p. 416 — Flanking",
        "citations": [{
            "book": "Pathfinder Player Core", "page": "416",
            "section": "Flanking", "url": "https://2e.aonprd.com/Rules.aspx?ID=1349",
        }],
        "marker": "source",
        "topic": "flanking",
    })

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.rule.obsidian", vault), \
         patch("app.routes.rule.rules_index", stub_index), \
         patch("app.routes.rule.aon_url_map", stub_map), \
         patch("app.routes.rule.generate_ruling_from_passages", new=mock_llm_pass), \
         patch("app.routes.rule.generate_ruling_fallback", new=AsyncMock()), \
         patch("app.routes.rule.keyword_classify_topic", return_value=None), \
         patch("app.routes.rule.classify_rule_topic", new=AsyncMock(return_value="flanking")), \
         patch("app.routes.rule.embed_texts", new=mock_embed):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = {"query": "How does flanking work?", "user_id": "u1"}

            # Call 1: fresh compose → cache write
            await client.post("/rule/query", json=payload)
            # Call 2: exact-hash cache hit
            resp2 = await client.post("/rule/query", json=payload)
            body2 = resp2.json()
            assert body2.get("reused") is True
            note2 = body2.get("reuse_note") or ""
            assert "reusing prior ruling" in note2.lower()
            # Call 3: another cache hit — reuse_note must be identical text
            resp3 = await client.post("/rule/query", json=payload)
            body3 = resp3.json()
            note3 = body3.get("reuse_note") or ""
            assert note3 == note2, (
                f"reuse_note dropped/changed by cache roundtrip (CR-03 regression): "
                f"call2={note2!r} vs call3={note3!r}"
            )


async def test_last_reused_at_updated_on_cache_hit():
    """D-14: last_reused_at ISO8601 timestamp is later after cache hit than on creation.

    ISO8601 timestamps sort lexicographically, so string comparison suffices.
    The route must GET-then-PUT the cached file with a fresh last_reused_at
    whenever the cache is served (both exact-hash and reuse-match paths).
    """
    import re

    vault = StatefulMockVault({})
    stub_index = _make_stub_index()
    stub_map = _load_aon_map_fixture()

    mock_embed = AsyncMock(return_value=[[1.0, 0.0, 0.0, 0.0, 0.0]])

    mock_llm_pass = AsyncMock(return_value={
        "question": "Q",
        "answer": "A",
        "why": "W",
        "source": "Pathfinder Player Core p. 416 — Flanking",
        "citations": [{
            "book": "Pathfinder Player Core", "page": "416",
            "section": "Flanking", "url": "https://2e.aonprd.com/Rules.aspx?ID=1349",
        }],
        "marker": "source",
        "topic": "flanking",
    })

    def _extract_last_reused_at(md: str) -> str:
        m = re.search(r"last_reused_at:\s*'?([0-9T:.\-Z+]+)'?", md)
        assert m, f"no last_reused_at found in md: {md[:200]!r}"
        return m.group(1)

    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.rule.obsidian", vault), \
         patch("app.routes.rule.rules_index", stub_index), \
         patch("app.routes.rule.aon_url_map", stub_map), \
         patch("app.routes.rule.generate_ruling_from_passages", new=mock_llm_pass), \
         patch("app.routes.rule.generate_ruling_fallback", new=AsyncMock()), \
         patch("app.routes.rule.keyword_classify_topic", return_value=None), \
         patch("app.routes.rule.classify_rule_topic", new=AsyncMock(return_value="flanking")), \
         patch("app.routes.rule.embed_texts", new=mock_embed):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = {"query": "How does flanking work?", "user_id": "u1"}

            # Call 1: initial compose — captures initial last_reused_at
            await client.post("/rule/query", json=payload)
            # Find the newly-written file (single flanking entry in store)
            flanking_paths = [
                k for k in vault._store.keys()
                if k.startswith("mnemosyne/pf2e/rulings/flanking/")
            ]
            assert len(flanking_paths) == 1
            initial_md = vault._store[flanking_paths[0]]
            initial_ts = _extract_last_reused_at(initial_md)

            # Ensure clock advance: datetime.now() resolution is microseconds, but
            # the route serializes to ISO8601 which we compare lexicographically.
            import asyncio
            await asyncio.sleep(0.01)

            # Call 2: cache hit — last_reused_at MUST update (D-14)
            await client.post("/rule/query", json=payload)
            updated_md = vault._store[flanking_paths[0]]
            updated_ts = _extract_last_reused_at(updated_md)

            assert updated_ts > initial_ts, (
                f"D-14 regression: last_reused_at not updated on cache hit "
                f"(initial={initial_ts!r} vs updated={updated_ts!r})"
            )
