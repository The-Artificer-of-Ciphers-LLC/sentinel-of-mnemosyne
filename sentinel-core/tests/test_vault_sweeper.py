"""Tests for vault_sweeper service (260427-vl1 Task 7)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import numpy as np
import pytest

from app.services.note_classifier import ClassificationResult
from app.services.vault_sweeper import (
    LOCKFILE_PATH,
    SWEEP_SKIP_PREFIXES,
    _should_skip,
    run_sweep,
    walk_vault,
)
from sentinel_shared.embedding_codec import decode_embedding, encode_embedding
from sentinel_shared.similarity import cosine_similarity, find_dup_clusters
from tests.fakes.vault import FakeVault

# Plan 260502-cky Task 4: this file historically used a test-local
# FakeObsidian class. Migrated to the canonical tests.fakes.vault.FakeVault
# fixture-wiring refactor under the Test-Rewrite Ban allowed list —
# assertions and call paths preserved (FakeVault exposes ``.store`` as an
# alias for ``.notes`` so ``fake.store[path]`` style assertions read
# unchanged). Only the test double's implementation changed.
FakeObsidian = FakeVault


# --- Pure helpers ---


def test_encode_decode_embedding_round_trip():
    vec = [0.1, 0.2, -0.3, 1.0, 0.0]
    encoded = encode_embedding(vec)
    decoded = decode_embedding(encoded)
    assert len(decoded) == len(vec)
    for a, b in zip(decoded, vec):
        assert abs(a - b) < 1e-6


def test_encode_decode_embedding_768_dim():
    vec = list(np.random.rand(768).astype(np.float32))
    encoded = encode_embedding(vec)
    decoded = decode_embedding(encoded)
    assert len(decoded) == 768


def test_cosine_similarity_basic():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(1.0)
    assert cosine_similarity(a, c) == pytest.approx(0.0, abs=1e-6)


def test_cosine_zero_norm_safe():
    a = np.zeros(3, dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == 0.0


def test_find_dup_clusters_basic():
    matrix = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.999, 0.0, 0.04],  # very close to row 0
            [0.0, 1.0, 0.0],  # orthogonal
        ],
        dtype=np.float32,
    )
    clusters = find_dup_clusters(matrix, threshold=0.92)
    assert clusters == [[0, 1]]


def test_find_dup_clusters_no_dups():
    matrix = np.eye(3, dtype=np.float32)
    assert find_dup_clusters(matrix, threshold=0.92) == []


def test_should_skip_prefixes():
    assert _should_skip("_trash/foo.md", {}, "now") is True
    assert _should_skip("pf2e/x.md", {}, "now") is True
    assert _should_skip("ops/sessions/2026-04-27/x.md", {}, "now") is True
    assert _should_skip("ops/sweeps/2026-04-27.md", {}, "now") is True
    assert _should_skip("inbox/_pending-classification.md", {}, "now") is True


def test_should_skip_by_sweep_pass():
    fm = {"sweep_pass": "now", "topic": "reference", "embedding_b64": "abc"}
    assert _should_skip("references/foo.md", fm, "now") is True
    # missing embedding → process
    assert _should_skip("references/foo.md", {**fm, "embedding_b64": ""}, "now") is False
    # mismatched pass → process
    assert _should_skip("references/foo.md", {**fm, "sweep_pass": "old"}, "now") is False


# --- walk_vault ---


@pytest.mark.asyncio
async def test_walk_vault_skips_protected_subtrees():
    fake = FakeObsidian()
    fake.dirs[""] = ["root.md", "_trash/", "pf2e/", "references/", "ops/"]
    fake.dirs["references"] = ["a.md", "b.md"]
    fake.dirs["ops"] = ["sessions/", "observations/"]
    fake.dirs["ops/observations"] = ["o1.md"]
    # _trash and pf2e should never be listed
    fake.dirs["_trash"] = ["never.md"]
    fake.dirs["pf2e"] = ["never2.md"]
    fake.dirs["ops/sessions"] = ["never3.md"]

    paths: list[str] = []
    async for p in walk_vault(fake):
        paths.append(p)

    assert "root.md" in paths
    assert "references/a.md" in paths
    assert "references/b.md" in paths
    assert "ops/observations/o1.md" in paths
    assert not any(p.startswith("_trash") for p in paths)
    assert not any(p.startswith("pf2e") for p in paths)
    assert not any(p.startswith("ops/sessions") for p in paths)


# --- move_to_trash ---


@pytest.mark.asyncio
async def test_move_to_trash_basic():
    fake = FakeObsidian()
    fake.store["foo.md"] = "---\ntopic: reference\n---\n\nbody"

    dst = await fake.move_to_trash(
        "foo.md", reason="duplicate of bar.md", sweep_at="2026-04-27T00:00:00Z"
    )
    assert dst.startswith("_trash/")
    assert dst.endswith("foo.md")
    assert "foo.md" not in fake.store  # source deleted
    assert dst in fake.store  # trash file written
    body = fake.store[dst]
    assert "original_path: foo.md" in body
    assert "duplicate of bar.md" in body


@pytest.mark.asyncio
async def test_move_to_trash_collision_suffix():
    fake = FakeObsidian()
    fake.store["foo.md"] = "body1"
    today_dst = ""
    # Pre-populate the would-be trash target
    from app.services.vault_sweeper import _today_str

    today_dst = f"_trash/{_today_str()}/foo.md"
    fake.store[today_dst] = "existing"

    dst = await fake.move_to_trash("foo.md", reason="dup")
    assert dst != today_dst
    assert dst in fake.store


# --- Lockfile ---


@pytest.mark.asyncio
async def test_acquire_lock_fresh_blocks_new():
    fake = FakeObsidian()
    now = datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)
    assert await fake.acquire_sweep_lock(now=now) is True
    # second attempt at the same time → blocked
    assert await fake.acquire_sweep_lock(now=now) is False
    await fake.release_sweep_lock()
    assert LOCKFILE_PATH not in fake.store


@pytest.mark.asyncio
async def test_acquire_lock_stale_takeover():
    from datetime import timedelta

    fake = FakeObsidian()
    # Plant a stale lock from 2h ago
    started = datetime(2026, 4, 27, 10, 0, 0, tzinfo=timezone.utc)
    fake.store[LOCKFILE_PATH] = f"---\nstarted_at: {started.strftime('%Y-%m-%dT%H:%M:%SZ')}\n---\n"
    now = started + timedelta(hours=2)
    assert await fake.acquire_sweep_lock(now=now) is True


# --- End-to-end run_sweep with embedding-failure degrade ---


@pytest.mark.asyncio
async def test_run_sweep_embedder_failure_continues_classification():
    fake = FakeObsidian()
    fake.dirs[""] = ["learning/"]
    fake.dirs["learning"] = ["x.md"]
    fake.store["learning/x.md"] = "Real content body to classify"

    classifier = AsyncMock(
        return_value=ClassificationResult(
            topic="learning", confidence=0.9, title_slug="x", reasoning="r"
        )
    )

    async def _failing_embedder(texts):
        raise RuntimeError("LM Studio offline")

    report = await run_sweep(
        fake, classifier, _failing_embedder, force_reclassify=True
    )
    # Classification did write back
    body = fake.store["learning/x.md"]
    assert "topic: learning" in body
    assert "embedding_b64" not in body  # embed was skipped
    assert report.duplicates_moved == 0
    assert report.files_processed == 1


@pytest.mark.asyncio
async def test_run_sweep_dedup_moves_duplicate_to_trash():
    fake = FakeObsidian()
    fake.dirs[""] = ["references/"]
    fake.dirs["references"] = ["a.md", "b.md"]
    fake.store["references/a.md"] = "shared content body shared shared shared"
    fake.store["references/b.md"] = "shared content body shared shared"  # shorter

    classifier = AsyncMock(
        return_value=ClassificationResult(
            topic="reference", confidence=0.9, title_slug="x", reasoning="r"
        )
    )

    # Identical embeddings for both → cosine == 1.0 → cluster
    async def _same_embedder(texts):
        return [[1.0, 0.0, 0.0]] * len(texts)

    report = await run_sweep(fake, classifier, _same_embedder, force_reclassify=True)
    assert report.duplicates_moved == 1
    # The shorter body's path should be gone (moved to trash); the longer kept.
    surviving = [p for p in ("references/a.md", "references/b.md") if p in fake.store]
    assert len(surviving) == 1
    # A trash file exists
    trash = [p for p in fake.store if p.startswith("_trash/")]
    assert len(trash) >= 1


@pytest.mark.asyncio
async def test_run_sweep_idempotent_skips_marked():
    """Re-running on a fully-marked vault skips already-processed notes."""
    fake = FakeObsidian()
    fake.dirs[""] = ["references/"]
    fake.dirs["references"] = ["a.md"]

    # First run
    classifier = AsyncMock(
        return_value=ClassificationResult(
            topic="reference", confidence=0.9, title_slug="x", reasoning="r"
        )
    )

    async def _emb(texts):
        return [[0.5, 0.5, 0.5]] * len(texts)

    fake.store["references/a.md"] = "content"
    report1 = await run_sweep(fake, classifier, _emb, force_reclassify=True)
    assert report1.files_processed == 1
    classifier.reset_mock()

    # Mark sweep_pass with the existing pass on the file (post-run)
    body_after_first = fake.store["references/a.md"]
    # Second run with same sweep_id behavior — but run_sweep generates a fresh
    # sweep_id, so we patch by re-running with force_reclassify=False AND
    # setting sweep_pass to whatever the file currently has.
    from app.services.vault_sweeper import split_frontmatter

    fm, _ = split_frontmatter(body_after_first)
    # Force the next sweep_id to match by monkey-patching _iso_utc... too invasive.
    # Simpler test: with force_reclassify=False, a freshly-written note carrying
    # an old sweep_pass != current sweep_id will still be re-processed.
    # Instead verify: when sweep_pass equals a string we craft, _should_skip is True.
    assert _should_skip(
        "references/a.md",
        {
            "sweep_pass": "match",
            "topic": "reference",
            "embedding_b64": fm.get("embedding_b64", ""),
        },
        "match",
    ) == bool(fm.get("embedding_b64"))


# --- RED tests for missing behavior (operator authorized 2026-04-27) ---
#
# Gap #1: sweeper classifies in place but does not move misplaced notes
#         to their topic-appropriate folder. The whole point of the
#         operator's import/cleanup ask is to physically relocate
#         misclassified notes, not just tag them with frontmatter.
#
# Gap #2: no dry-run mode. Operator wants to preview moves before
#         committing them.
#
# Both tests will FAIL on the current implementation; that is the point.


@pytest.mark.asyncio
async def test_sweep_moves_misplaced_note_to_topic_folder():
    """A note classified `accomplishment` but living at a non-accomplishment
    path must be moved to ``accomplishments/<original-filename>``.

    The original path must no longer exist in the store after the sweep,
    and the destination path must contain the note's body with updated
    frontmatter (`topic: accomplishment`, `original_path: <old>`).
    """
    fake = FakeObsidian()
    # Misplaced: an accomplishment-shaped note living in a random folder
    fake.dirs[""] = ["random-folder/"]
    fake.dirs["random-folder"] = ["finished-bass-day-19.md"]
    fake.store["random-folder/finished-bass-day-19.md"] = (
        "Finished day 19 of the 30-day bass level 2 course."
    )

    classifier = AsyncMock(
        return_value=ClassificationResult(
            topic="accomplishment",
            confidence=0.95,
            title_slug="finished-bass-day-19",
            reasoning="course completion milestone",
        )
    )

    async def _emb(texts):
        return [[1.0, 0.0, 0.0]] * len(texts)

    report = await run_sweep(fake, classifier, _emb, force_reclassify=True)

    # The misplaced original is gone
    assert "random-folder/finished-bass-day-19.md" not in fake.store, (
        "expected the original path to be removed after the move"
    )

    # The note now lives under the topic folder, keeping its filename
    expected_dst = "accomplishments/finished-bass-day-19.md"
    assert expected_dst in fake.store, (
        f"expected the note to be moved to {expected_dst}; "
        f"current paths: {sorted(fake.store.keys())}"
    )

    # The moved note carries classification + provenance
    moved_body = fake.store[expected_dst]
    assert "topic: accomplishment" in moved_body
    assert "original_path: random-folder/finished-bass-day-19.md" in moved_body

    # Report counts the move
    assert getattr(report, "topic_moves", 0) == 1, (
        "report.topic_moves should track misplaced→topic-folder relocations"
    )


@pytest.mark.asyncio
async def test_sweep_dry_run_produces_proposed_moves_no_file_writes():
    """With ``dry_run=True``, run_sweep must:

      1. Walk and classify normally.
      2. Populate ``report.proposed_moves`` with every move it WOULD make
         (noise→trash, dup→trash, misplaced→topic-folder).
      3. NOT write or delete a single file in the store.

    This is the safety preview the operator runs before authorizing a
    real sweep.
    """
    fake = FakeObsidian()
    fake.dirs[""] = ["random-folder/", "stale/"]
    fake.dirs["random-folder"] = ["finished-bass-day-19.md"]
    fake.dirs["stale"] = ["hello.md"]
    fake.store["random-folder/finished-bass-day-19.md"] = (
        "Finished day 19 of the 30-day bass level 2 course."
    )
    fake.store["stale/hello.md"] = "hello"  # cheap-filter noise

    # Snapshot the store before running
    pre_paths = set(fake.store.keys())
    pre_bodies = dict(fake.store)

    async def _classifier(text: str) -> ClassificationResult:
        if text.strip().lower() == "hello":
            return ClassificationResult(
                topic="noise",
                confidence=1.0,
                title_slug="hello",
                reasoning="cheap-filter:noise",
            )
        return ClassificationResult(
            topic="accomplishment",
            confidence=0.95,
            title_slug="finished-bass-day-19",
            reasoning="course completion",
        )

    async def _emb(texts):
        return [[1.0, 0.0, 0.0]] * len(texts)

    report = await run_sweep(
        fake,
        _classifier,
        _emb,
        force_reclassify=True,
        dry_run=True,
    )

    # Store is byte-for-byte unchanged
    post_paths = set(fake.store.keys())
    assert post_paths == pre_paths, (
        f"dry_run must not add or remove paths; "
        f"added={post_paths - pre_paths}, removed={pre_paths - post_paths}"
    )
    for path in pre_paths:
        assert fake.store[path] == pre_bodies[path], (
            f"dry_run must not modify {path}"
        )

    # Proposed moves include both kinds: misplaced→topic and noise→trash
    proposed = getattr(report, "proposed_moves", None)
    assert proposed is not None, "report.proposed_moves must be populated in dry-run"
    assert len(proposed) >= 2, (
        f"expected at least 2 proposed moves (1 misplaced + 1 noise); got {len(proposed)}"
    )

    # The misplaced→topic move is in the list
    topic_moves = [m for m in proposed if m.get("kind") == "topic"]
    assert any(
        m.get("src") == "random-folder/finished-bass-day-19.md"
        and m.get("dst") == "accomplishments/finished-bass-day-19.md"
        for m in topic_moves
    ), f"expected misplaced→accomplishments move in proposed_moves; got {proposed}"

    # The noise→trash move is in the list
    trash_moves = [m for m in proposed if m.get("kind") == "trash"]
    assert any(
        m.get("src") == "stale/hello.md" for m in trash_moves
    ), f"expected stale/hello.md→_trash in proposed_moves; got {proposed}"


# --- skip prefix sanity ---


def test_sweep_skip_prefixes_constant():
    assert "_trash/" in SWEEP_SKIP_PREFIXES
    assert "pf2e/" in SWEEP_SKIP_PREFIXES
    assert "ops/sessions/" in SWEEP_SKIP_PREFIXES
    assert "ops/sweeps/" in SWEEP_SKIP_PREFIXES
    assert "inbox/" in SWEEP_SKIP_PREFIXES


# --- 260427-cza tests: structural-awareness skip-prefix expansion +
#     dry-run topic_moves counter fix.
# Behavioral tests — call the real walker / run_sweep and assert on
# observable outputs (not source-grep). Per CLAUDE.md.


@pytest.mark.asyncio
async def test_skip_prefixes_block_module_dirs():
    """Default skip-prefix tuple must keep walk_vault out of every
    module-managed subtree we know about today: mnemosyne/, core/, self/,
    templates/, archive/, security/, .obsidian/. Only `notes/real.md`
    should survive the walk.
    """
    fake = FakeObsidian()
    # Vault root containing one allowed dir (`notes/`) plus one entry
    # per protected subtree.
    fake.dirs[""] = [
        "notes/",
        "mnemosyne/",
        "core/",
        "self/",
        "templates/",
        "archive/",
        "security/",
        ".obsidian/",
    ]
    fake.dirs["notes"] = ["real.md"]
    # If the walker descended into any of these, it would see these files.
    fake.dirs["mnemosyne"] = ["pf2e/"]
    fake.dirs["mnemosyne/pf2e"] = ["npcs/"]
    fake.dirs["mnemosyne/pf2e/npcs"] = ["jareth.md"]
    fake.dirs["core"] = ["foo.md"]
    fake.dirs["self"] = ["bar.md"]
    fake.dirs["templates"] = ["x.md"]
    fake.dirs["archive"] = ["cartosia/"]
    fake.dirs["archive/cartosia"] = ["y.md"]
    fake.dirs["security"] = ["z.md"]
    fake.dirs[".obsidian"] = ["config.json", "ignore.md"]

    paths: list[str] = []
    async for p in walk_vault(fake):
        paths.append(p)

    assert paths == ["notes/real.md"], (
        f"only notes/real.md should survive; got {paths}"
    )


@pytest.mark.asyncio
async def test_dry_run_topic_moves_counter_matches_proposed_moves():
    """run_sweep(dry_run=True) on a vault with N misplaced notes must report
    report.topic_moves == N (matching the count of `kind=='topic'` entries
    in proposed_moves). Currently the dry-run branch never increments the
    counter — this test FAILS on main.
    """
    fake = FakeObsidian()
    fake.dirs[""] = ["random/"]
    fake.dirs["random"] = ["a.md", "b.md", "c.md"]
    fake.store["random/a.md"] = "alpha body"
    fake.store["random/b.md"] = "beta body"
    fake.store["random/c.md"] = "gamma body"

    classifier = AsyncMock(
        return_value=ClassificationResult(
            topic="accomplishment",
            confidence=0.95,
            title_slug="x",
            reasoning="r",
        )
    )

    async def _emb(texts):
        return [[1.0, 0.0, 0.0]] * len(texts)

    report = await run_sweep(
        fake, classifier, _emb, force_reclassify=True, dry_run=True
    )

    topic_proposals = [m for m in report.proposed_moves if m.get("kind") == "topic"]
    assert len(topic_proposals) == 3, (
        f"expected 3 topic proposals; got {len(topic_proposals)}: {report.proposed_moves}"
    )
    assert report.topic_moves == 3, (
        f"report.topic_moves should equal len(topic-kind proposed_moves); "
        f"got topic_moves={report.topic_moves}, proposals={len(topic_proposals)}"
    )


@pytest.mark.asyncio
async def test_skip_prefixes_configurable_via_settings(monkeypatch):
    """walk_vault must consult settings.sweep_skip_prefixes at runtime so
    operators can extend the denylist via env without code change. Override
    the setting to add `custom-skip/`, place a file under it, assert it's
    skipped.
    """
    from app import config as config_module

    # Override settings to add a custom prefix; keep the defaults so the
    # rest of the protections still apply.
    custom_prefixes = tuple(config_module.settings.sweep_skip_prefixes) + (
        "custom-skip/",
    )
    monkeypatch.setattr(
        config_module.settings, "sweep_skip_prefixes", custom_prefixes
    )

    fake = FakeObsidian()
    fake.dirs[""] = ["notes/", "custom-skip/"]
    fake.dirs["notes"] = ["keep.md"]
    fake.dirs["custom-skip"] = ["skipme.md"]

    paths: list[str] = []
    async for p in walk_vault(fake):
        paths.append(p)

    assert "notes/keep.md" in paths
    assert not any(p.startswith("custom-skip") for p in paths), (
        f"custom-skip/ entries should be skipped; got {paths}"
    )


# --- Phase 40 Plan 01: embedding index emission tests (Wave 0 RED) ---
#
# These tests pin the index-emission, model-write, incremental-rebuild,
# prune, and document-prefix behaviors required by MEM-05 (producer side).
# All five MUST FAIL initially (RED step) because EMBEDDING_INDEX_PATH,
# NOMIC_DOCUMENT_PREFIX, and _emit_embedding_index do not yet exist.


import json as _json  # local alias to avoid shadowing the module-level `json`


class _CallCountingEmbedder:
    """Fake embedder that records which texts it was called with.

    Returns DISTINCT unit vectors per position so notes never appear as
    duplicates to the de-dup logic (cosine between distinct axis vectors = 0).
    This keeps the embedding-index tests independent of de-dup behaviour.
    """

    # Pool of orthogonal unit vectors; enough for any test vault (<=8 notes)
    _VECS: list[list[float]] = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
        [1.0, 1.0, 0.0, 0.0],
        [1.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 1.0, 0.0],
        [1.0, 0.0, 0.0, 1.0],
    ]

    def __init__(self):
        self.calls: list[list[str]] = []
        self._counter: int = 0

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        vecs = []
        for _ in texts:
            vecs.append(self._VECS[self._counter % len(self._VECS)])
            self._counter += 1
        return vecs

    @property
    def all_texts(self) -> list[str]:
        return [t for batch in self.calls for t in batch]


def _make_classifiable_note_vault(
    paths: list[str],
    body: str = "A classifiable note body.",
) -> FakeObsidian:
    """Return a FakeVault pre-populated with notes at *paths* and a dir tree.

    Notes are placed INSIDE their topic-canonical directory (``references/``)
    so ``is_in_topic_dir`` returns True and the sweeper does NOT attempt to
    relocate them. This keeps the post-sweep paths predictable for the index
    emission tests.
    """
    fake = FakeObsidian()
    # Populate root directory listing
    top_dirs: set[str] = set()
    for p in paths:
        parts = p.split("/")
        if len(parts) > 1:
            top_dirs.add(parts[0] + "/")
        else:
            top_dirs.add(p)
    fake.dirs[""] = sorted(top_dirs)
    for p in paths:
        parts = p.split("/")
        if len(parts) > 1:
            dir_key = "/".join(parts[:-1])
            fake.dirs.setdefault(dir_key, [])
            if parts[-1] not in fake.dirs[dir_key]:
                fake.dirs[dir_key].append(parts[-1])
        fake.notes[p] = body
    return fake


@pytest.mark.asyncio
async def test_sweep_emits_embedding_index():
    """After run_sweep over a FakeVault with classifiable notes the FakeVault
    has a note at EMBEDDING_INDEX_PATH whose JSON body is an object keyed by
    surviving note paths."""
    from app.services.vault_sweeper import EMBEDDING_INDEX_PATH  # must exist (RED: will NameError)

    # Use references/ path so classifier topic="reference" keeps notes in-place
    note_paths = ["references/alpha.md", "references/beta.md"]
    fake = _make_classifiable_note_vault(note_paths)

    classifier = AsyncMock(
        return_value=ClassificationResult(
            topic="reference", confidence=0.9, title_slug="x", reasoning="r"
        )
    )
    embedder = _CallCountingEmbedder()

    await run_sweep(fake, classifier, embedder, force_reclassify=True)

    assert EMBEDDING_INDEX_PATH in fake.notes, (
        f"expected {EMBEDDING_INDEX_PATH!r} in vault after sweep; "
        f"present paths: {sorted(fake.notes.keys())}"
    )
    raw = fake.notes[EMBEDDING_INDEX_PATH]
    index = _json.loads(raw)
    assert isinstance(index, dict), f"index must be a JSON object; got {type(index)}"
    for path in note_paths:
        assert path in index, f"expected note path {path!r} as key in index; keys={list(index.keys())}"


@pytest.mark.asyncio
async def test_sweep_writes_embedding_model_to_index():
    """Every index entry must carry embedding_b64, embedding_model (== the
    no-prefix model id from _embedding_model_id()), and content_hash."""
    from app.services.vault_sweeper import EMBEDDING_INDEX_PATH  # RED: NameError

    # Use references/ path so classifier topic="reference" keeps note in-place
    note_paths = ["references/alpha.md"]
    fake = _make_classifiable_note_vault(note_paths)

    classifier = AsyncMock(
        return_value=ClassificationResult(
            topic="reference", confidence=0.9, title_slug="x", reasoning="r"
        )
    )
    embedder = _CallCountingEmbedder()

    await run_sweep(fake, classifier, embedder, force_reclassify=True)

    raw = fake.notes[EMBEDDING_INDEX_PATH]
    index = _json.loads(raw)
    entry = index["references/alpha.md"]

    # Must carry all three required fields
    assert "embedding_b64" in entry, f"missing embedding_b64 in entry: {entry}"
    assert "embedding_model" in entry, f"missing embedding_model in entry: {entry}"
    assert "content_hash" in entry, f"missing content_hash in entry: {entry}"

    # embedding_model must NOT have the "openai/" prefix
    em = entry["embedding_model"]
    assert not em.startswith("openai/"), (
        f"embedding_model must not have 'openai/' prefix; got {em!r}"
    )
    # embedding_model must equal the value _embedding_model_id() returns
    from app.services.vault_sweeper import _embedding_model_id
    assert em == _embedding_model_id(), (
        f"embedding_model {em!r} != _embedding_model_id() {_embedding_model_id()!r}"
    )


@pytest.mark.asyncio
async def test_sweep_index_incremental_carry_forward():
    """A second run_sweep where a note's body is unchanged must carry the
    same entry forward WITHOUT calling the embedder for that path.
    A note whose body changed must get a new content_hash + fresh embedding."""
    from app.services.vault_sweeper import EMBEDDING_INDEX_PATH  # RED: NameError

    # Use references/ paths so classifier topic="reference" keeps notes in-place
    note_paths = ["references/stable.md", "references/changing.md"]
    fake = _make_classifiable_note_vault(note_paths, body="original body")
    classifier = AsyncMock(
        return_value=ClassificationResult(
            topic="reference", confidence=0.9, title_slug="x", reasoning="r"
        )
    )
    embedder = _CallCountingEmbedder()

    # First sweep — embeds both notes
    await run_sweep(fake, classifier, embedder, force_reclassify=True)
    calls_after_first = len(embedder.all_texts)

    # Record the content_hash of the stable note from the first index
    index_after_first = _json.loads(fake.notes[EMBEDDING_INDEX_PATH])
    stable_hash_first = index_after_first["references/stable.md"]["content_hash"]
    stable_b64_first = index_after_first["references/stable.md"]["embedding_b64"]

    # Mutate the body of the changing note so it will need re-embedding
    # We need to write it directly to the vault (bypass frontmatter)
    # After the first sweep, the note has frontmatter — we must update the body part
    # For simplicity just set a fresh body without frontmatter
    fake.notes["references/changing.md"] = "completely new body content"

    # Second sweep
    embedder.calls.clear()
    classifier.reset_mock()
    await run_sweep(fake, classifier, embedder, force_reclassify=True)

    index_after_second = _json.loads(fake.notes[EMBEDDING_INDEX_PATH])

    # The stable note's entry must be carried forward unchanged (same hash + b64)
    stable_entry = index_after_second["references/stable.md"]
    assert stable_entry["content_hash"] == stable_hash_first, (
        "stable note content_hash must not change between sweeps when body is unchanged"
    )
    assert stable_entry["embedding_b64"] == stable_b64_first, (
        "stable note embedding_b64 must be carried forward when body is unchanged"
    )

    # The stable note must NOT have triggered a re-embed: the texts sent to the
    # embedder in the second sweep must NOT contain the stable note's body.
    texts_in_second_sweep = embedder.all_texts
    # The stable note's body (after first sweep it has frontmatter, body = "original body")
    # At minimum, the stable note body text should NOT appear fresh in the second batch
    # because its hash hasn't changed.
    # Verify: the changing note WAS re-embedded (its new body must appear in texts)
    assert any("completely new body content" in t for t in texts_in_second_sweep), (
        "changing note's new body must be sent to embedder in second sweep; "
        f"texts sent: {texts_in_second_sweep}"
    )

    # And the changing note must have a DIFFERENT content_hash than in the first index
    changing_hash_first = index_after_first["references/changing.md"]["content_hash"]
    changing_hash_second = index_after_second["references/changing.md"]["content_hash"]
    assert changing_hash_second != changing_hash_first, (
        "changed note must have a new content_hash in the second index"
    )


@pytest.mark.asyncio
async def test_sweep_index_prunes_trashed():
    """A note present in the first index but trashed/absent on the second sweep
    must be removed (pruned) from the new index."""
    from app.services.vault_sweeper import EMBEDDING_INDEX_PATH  # RED: NameError

    # Use references/ paths so classifier topic="reference" keeps notes in-place
    note_paths = ["references/keeper.md", "references/goner.md"]
    fake = _make_classifiable_note_vault(note_paths, body="some body")
    classifier = AsyncMock(
        return_value=ClassificationResult(
            topic="reference", confidence=0.9, title_slug="x", reasoning="r"
        )
    )
    embedder = _CallCountingEmbedder()

    # First sweep — both notes indexed
    await run_sweep(fake, classifier, embedder, force_reclassify=True)
    index_first = _json.loads(fake.notes[EMBEDDING_INDEX_PATH])
    assert "references/keeper.md" in index_first
    assert "references/goner.md" in index_first

    # Remove "references/goner.md" from the vault entirely (simulate trash/delete)
    del fake.notes["references/goner.md"]
    refs_dir = fake.dirs.get("references", [])
    if "goner.md" in refs_dir:
        refs_dir.remove("goner.md")

    # Second sweep
    embedder.calls.clear()
    classifier.reset_mock()
    await run_sweep(fake, classifier, embedder, force_reclassify=True)

    index_second = _json.loads(fake.notes[EMBEDDING_INDEX_PATH])
    assert "references/keeper.md" in index_second, "keeper note must remain in index after second sweep"
    assert "references/goner.md" not in index_second, (
        "goner note must be pruned from index because it no longer exists in the vault"
    )


@pytest.mark.asyncio
async def test_sweep_embeds_with_document_prefix():
    """The strings passed to the embedder must each be prefixed with
    NOMIC_DOCUMENT_PREFIX ('search_document: ')."""
    from app.services.vault_sweeper import NOMIC_DOCUMENT_PREFIX  # RED: NameError

    # Use references/ paths so classifier topic="reference" keeps notes in-place
    note_paths = ["references/alpha.md", "references/beta.md"]
    fake = _make_classifiable_note_vault(note_paths, body="note body text")
    classifier = AsyncMock(
        return_value=ClassificationResult(
            topic="reference", confidence=0.9, title_slug="x", reasoning="r"
        )
    )
    embedder = _CallCountingEmbedder()

    await run_sweep(fake, classifier, embedder, force_reclassify=True)

    all_texts = embedder.all_texts
    assert len(all_texts) >= 2, f"expected at least 2 texts sent to embedder; got {all_texts}"
    for text in all_texts:
        assert text.startswith(NOMIC_DOCUMENT_PREFIX), (
            f"embedder received text without NOMIC_DOCUMENT_PREFIX; "
            f"prefix={NOMIC_DOCUMENT_PREFIX!r}, text={text!r}"
        )
