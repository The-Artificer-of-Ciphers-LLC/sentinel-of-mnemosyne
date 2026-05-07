"""Wave 4 RED tests for player_recall_engine (PVL-03 / PVL-07).

Symbols referenced below land in plan 37-09 Task 1B (`app.player_recall_engine.recall`).

Function-scope imports inside each test body keep collection green pre-implementation
(pattern: Phase 33/34/36/37-01..08 Wave 0).

Behavioural-Test-Only Rule: every assertion is on observable I/O — exact
list_directory prefix arg, exact get_note path arg, returned data shape, score
ordering, length cap, snippet substring. No source-grep, no `assert True`,
no `mock.assert_called` as the sole assertion.

Engine contract under test (CONTEXT lock — keyword-match + recency only,
NO LLM, NO embeddings):

    async def recall(slug, query, *, obsidian, limit=10) -> list[dict]

  - Reads via obsidian.list_directory(prefix=f"mnemosyne/pf2e/players/{slug}/")
    and obsidian.get_note(path) for each path.
  - Scores: keyword count (case-insensitive token overlap) plus recency weight.
  - Recency weight: sessions/{yyyy-mm-dd}.md filename → max(0, 1.0 - days_since/365);
    non-session files → fixed weight 0.1.
  - Returns at most `limit` results, sorted desc by (score, recency).
  - Each result: {"path": str, "snippet": str, "score": float}.
  - Deterministic: identical inputs (with frozen "today") → identical outputs.
"""
from __future__ import annotations

import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers (test-local — no production import beyond the engine itself)
# ---------------------------------------------------------------------------


def _make_obsidian(files: dict[str, str]):
    """Build a MagicMock obsidian whose list_directory/get_note serve `files`.

    `files` maps full vault paths -> note bodies. list_directory returns the
    paths whose vault-path starts with the requested prefix (mirrors the real
    client's recursive shape).
    """
    obs = MagicMock()
    paths = list(files.keys())

    async def _list(prefix: str) -> list[str]:
        if not prefix.endswith("/"):
            prefix = prefix + "/"
        return [p for p in paths if p.startswith(prefix)]

    async def _get(path: str) -> str | None:
        return files.get(path)

    obs.list_directory = AsyncMock(side_effect=_list)
    obs.get_note = AsyncMock(side_effect=_get)
    return obs


# Frozen "today" used by recency-weight tests so date math is reproducible.
# Session files dated 2026-05-01 / 2026-04-01 have predictable days_since here.
_FROZEN_TODAY_ISO = "2026-05-07"


# ---------------------------------------------------------------------------
# 1. Slug-prefix isolation: list_directory called only with the slug prefix
# ---------------------------------------------------------------------------


async def test_recall_uses_only_slug_prefix_paths():
    """list_directory is called with exactly mnemosyne/pf2e/players/{slug}/ — never any other prefix."""
    from app.player_recall_engine import recall

    slug = "p-abc123abc123"
    files = {
        f"mnemosyne/pf2e/players/{slug}/inbox.md": "Varek says hi",
        f"mnemosyne/pf2e/players/{slug}/sessions/2026-05-01.md": "Varek the warrior",
    }
    obs = _make_obsidian(files)

    await recall(slug, "Varek", obsidian=obs)

    assert obs.list_directory.await_args_list, "recall must invoke list_directory"
    expected_prefix = f"mnemosyne/pf2e/players/{slug}/"
    for c in obs.list_directory.await_args_list:
        prefix_arg = c.args[0] if c.args else c.kwargs.get("prefix")
        assert prefix_arg == expected_prefix, (
            f"list_directory called with non-slug prefix: {prefix_arg!r} "
            f"(expected exactly {expected_prefix!r})"
        )
    # Every get_note path must also be under the slug prefix.
    for c in obs.get_note.await_args_list:
        path_arg = c.args[0] if c.args else c.kwargs.get("path")
        assert str(path_arg).startswith(expected_prefix), (
            f"get_note called with path outside slug prefix: {path_arg!r}"
        )


# ---------------------------------------------------------------------------
# 2. Empty vault -> empty result
# ---------------------------------------------------------------------------


async def test_recall_returns_empty_when_no_files():
    """list_directory returns [] -> recall returns []."""
    from app.player_recall_engine import recall

    obs = MagicMock()
    obs.list_directory = AsyncMock(return_value=[])
    obs.get_note = AsyncMock(return_value=None)

    result = await recall("p-emptyemptyem", "anything", obsidian=obs)
    assert result == []


# ---------------------------------------------------------------------------
# 3. Keyword-match ranking: higher count wins
# ---------------------------------------------------------------------------


async def test_recall_keyword_match_ranks_higher_than_no_match():
    """File mentioning 'Varek' twice ranks above a file mentioning it once."""
    from app.player_recall_engine import recall

    slug = "p-keywordrnktst"
    high = f"mnemosyne/pf2e/players/{slug}/inbox.md"
    low = f"mnemosyne/pf2e/players/{slug}/notes.md"
    files = {
        high: "Varek met us at the inn. Varek wore red.",
        low: "Varek showed up briefly.",
    }
    obs = _make_obsidian(files)

    result = await recall(slug, "Varek", obsidian=obs)
    assert len(result) >= 2
    # The first (highest-scored) result must be the higher-keyword-count file.
    assert result[0]["path"] == high, (
        f"expected {high} to rank first; got order: "
        f"{[r['path'] for r in result]}"
    )
    # And the lower-count file must rank below it (or be absent if filtered).
    paths_in_order = [r["path"] for r in result]
    assert paths_in_order.index(high) < paths_in_order.index(low)


# ---------------------------------------------------------------------------
# 4. Recency tie-breaker on equal keyword count
# ---------------------------------------------------------------------------


async def test_recall_recency_weight_breaks_keyword_tie():
    """Two session files, identical keyword count, more-recent date ranks higher."""
    from app.player_recall_engine import recall

    slug = "p-recencytietst"
    recent = f"mnemosyne/pf2e/players/{slug}/sessions/2026-05-01.md"
    older = f"mnemosyne/pf2e/players/{slug}/sessions/2026-04-01.md"
    files = {
        recent: "We had an encounter at the bridge.",
        older: "We had an encounter at the river.",
    }
    obs = _make_obsidian(files)

    with patch("app.player_recall_engine._today_iso", return_value=_FROZEN_TODAY_ISO):
        result = await recall(slug, "encounter", obsidian=obs)

    assert len(result) >= 2
    paths_in_order = [r["path"] for r in result]
    assert paths_in_order.index(recent) < paths_in_order.index(older), (
        f"expected {recent} to rank above {older} via recency tie-break; "
        f"got: {paths_in_order}"
    )


# ---------------------------------------------------------------------------
# 5. No-query case: results sorted by recency
# ---------------------------------------------------------------------------


async def test_recall_no_query_returns_recency_ordered():
    """query=None -> session files sorted desc by date; non-session files weighted lower."""
    from app.player_recall_engine import recall

    slug = "p-noquerysortts"
    newer_session = f"mnemosyne/pf2e/players/{slug}/sessions/2026-05-01.md"
    older_session = f"mnemosyne/pf2e/players/{slug}/sessions/2026-04-01.md"
    inbox = f"mnemosyne/pf2e/players/{slug}/inbox.md"
    files = {
        newer_session: "alpha",
        older_session: "beta",
        inbox: "gamma",
    }
    obs = _make_obsidian(files)

    with patch("app.player_recall_engine._today_iso", return_value=_FROZEN_TODAY_ISO):
        result = await recall(slug, None, obsidian=obs)

    assert len(result) == 3, f"expected 3 results; got {len(result)}: {result}"
    paths_in_order = [r["path"] for r in result]
    # Newer session before older session.
    assert paths_in_order.index(newer_session) < paths_in_order.index(older_session)
    # Newer session ranks above the inbox (recency 1.0 - small_delta vs fixed 0.1).
    assert paths_in_order.index(newer_session) < paths_in_order.index(inbox)


# ---------------------------------------------------------------------------
# 6. Cross-slug isolation: A's recall never reads anything under B/
# ---------------------------------------------------------------------------


async def test_recall_isolation_no_cross_slug():
    """recall('A') hits A's prefix only; never touches paths under players/B/."""
    from app.player_recall_engine import recall

    slug_a = "p-aaaaaaaaaaaa"
    slug_b = "p-bbbbbbbbbbbb"
    a_path = f"mnemosyne/pf2e/players/{slug_a}/inbox.md"
    b_path = f"mnemosyne/pf2e/players/{slug_b}/inbox.md"
    files = {
        a_path: "Varek",
        b_path: "Varek",
    }
    obs = _make_obsidian(files)

    result = await recall(slug_a, "Varek", obsidian=obs)

    # 1. list_directory was called only with A's prefix.
    a_prefix = f"mnemosyne/pf2e/players/{slug_a}/"
    b_prefix = f"mnemosyne/pf2e/players/{slug_b}/"
    for c in obs.list_directory.await_args_list:
        prefix_arg = c.args[0] if c.args else c.kwargs.get("prefix")
        assert str(prefix_arg).startswith(a_prefix), (
            f"list_directory used wrong prefix: {prefix_arg!r}"
        )
        assert b_prefix not in str(prefix_arg), (
            f"list_directory leaked B's prefix into A's recall: {prefix_arg!r}"
        )
    # 2. get_note was called only on A-rooted paths.
    for c in obs.get_note.await_args_list:
        path_arg = c.args[0] if c.args else c.kwargs.get("path")
        assert str(path_arg).startswith(a_prefix), (
            f"get_note read outside A's namespace: {path_arg!r}"
        )
    # 3. Every result path is under A's prefix; B's slug never appears anywhere.
    for r in result:
        assert r["path"].startswith(a_prefix), (
            f"result path outside A's namespace: {r['path']!r}"
        )
        assert slug_b not in r["path"]
        assert slug_b not in r["snippet"]


# ---------------------------------------------------------------------------
# 7. Limit enforced
# ---------------------------------------------------------------------------


async def test_recall_limit_enforced():
    """30 matching files, limit=5 -> result list of length 5."""
    from app.player_recall_engine import recall

    slug = "p-limitenforced"
    files = {
        f"mnemosyne/pf2e/players/{slug}/note_{i:02d}.md": f"Varek mention #{i}"
        for i in range(30)
    }
    obs = _make_obsidian(files)

    result = await recall(slug, "Varek", obsidian=obs, limit=5)
    assert len(result) == 5, f"expected exactly 5; got {len(result)}"


# ---------------------------------------------------------------------------
# 8. Snippet contains the query token with surrounding context
# ---------------------------------------------------------------------------


async def test_recall_returns_snippet_around_query():
    """Snippet for 'Varek' contains 'Varek' plus context characters around it."""
    from app.player_recall_engine import recall

    slug = "p-snippetcheckk"
    body = (
        "lorem ipsum dolor sit amet "  # leading filler
        "alpha beta Varek gamma delta "  # the targeted region
        "consectetur adipiscing elit"  # trailing filler
    )
    path = f"mnemosyne/pf2e/players/{slug}/sessions/2026-05-01.md"
    files = {path: body}
    obs = _make_obsidian(files)

    with patch("app.player_recall_engine._today_iso", return_value=_FROZEN_TODAY_ISO):
        result = await recall(slug, "Varek", obsidian=obs)

    assert result, "expected at least one result"
    snippet = result[0]["snippet"]
    # Snippet must contain the matched token (case-insensitive).
    assert "Varek" in snippet, f"snippet missing query token: {snippet!r}"
    # Surrounding context must be present (at least one neighbouring word on
    # one side). 'beta' is to the left, 'gamma' is to the right of 'Varek'.
    assert ("beta" in snippet) or ("gamma" in snippet), (
        f"snippet has no surrounding context: {snippet!r}"
    )


# ---------------------------------------------------------------------------
# 9. Determinism: same inputs -> identical outputs across two calls
# ---------------------------------------------------------------------------


async def test_recall_deterministic():
    """Two recall() calls with identical inputs produce byte-identical results."""
    from app.player_recall_engine import recall

    slug = "p-determinismts"
    files = {
        f"mnemosyne/pf2e/players/{slug}/sessions/2026-05-01.md": "Varek strikes first.",
        f"mnemosyne/pf2e/players/{slug}/sessions/2026-04-01.md": "Varek lays low.",
        f"mnemosyne/pf2e/players/{slug}/inbox.md": "Varek owes me 5gp.",
        f"mnemosyne/pf2e/players/{slug}/notes.md": "no match here",
    }
    obs1 = _make_obsidian(files)
    obs2 = _make_obsidian(files)

    with patch("app.player_recall_engine._today_iso", return_value=_FROZEN_TODAY_ISO):
        a = await recall(slug, "Varek", obsidian=obs1)
        b = await recall(slug, "Varek", obsidian=obs2)

    assert a == b, f"non-deterministic recall: a={a} b={b}"
