"""Vault sweeper: walk → classify → embed → de-dup → trash-move.

Idempotent via `sweep_pass` frontmatter. Never deletes — moves to
``_trash/{YYYY-MM-DD}/``. Skips ``_trash/``, ``pf2e/``, ``ops/sessions/``,
``ops/sweeps/``, and ``inbox/`` subtrees (RESEARCH Pitfall 5).

Embedding similarity de-dup: cosine ≥ 0.92 → connected components → keep
the older + longer note in each cluster.

Lockfile sentinel ``ops/sweeps/_in-progress.md`` prevents overlapping sweeps
(stale > 1h is taken over with a WARNING — RESEARCH Pitfall 1).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import AsyncIterator, Awaitable, Callable

import numpy as np
from pydantic import BaseModel, Field

from app.errors import SweepInProgressError
from app.markdown_frontmatter import join_frontmatter, split_frontmatter
from app.time_utils import _iso_utc, _today_str
from sentinel_shared.embedding_codec import decode_embedding, encode_embedding
from sentinel_shared.similarity import cosine_similarity, find_dup_clusters

from app.services.sweep_status_store import (
    get_sweep_status,
    reset_sweep_status,
    set_sweep_status_from_report,
)

# Re-exports preserved for backwards compatibility with existing import sites
# (tests + any downstream callers that import these names from vault_sweeper).
__all__ = [
    "decode_embedding",
    "encode_embedding",
    "cosine_similarity",
    "find_dup_clusters",
    "split_frontmatter",
    "join_frontmatter",
]

logger = logging.getLogger(__name__)


SWEEP_SKIP_PREFIXES: tuple[str, ...] = (
    "_trash/",
    "pf2e/",
    "ops/sessions/",
    "ops/sweeps/",
    "inbox/",
)
"""Module-level fallback default. The runtime denylist is read from
``settings.sweep_skip_prefixes`` via ``_active_skip_prefixes()`` so operators
can extend it via env without code change. This constant is preserved as a
backstop in case settings import fails (and to keep the existing public
import surface stable for callers that referenced it directly)."""


def _active_skip_prefixes() -> tuple[str, ...]:
    """Return the live skip-prefix tuple from settings, falling back to the
    module-level default if settings is unimportable (e.g. during isolated
    unit tests of the helpers).
    """
    try:
        from app.config import settings
        return tuple(settings.sweep_skip_prefixes)
    except Exception:
        return SWEEP_SKIP_PREFIXES

LOCKFILE_PATH = "ops/sweeps/_in-progress.md"
STALE_LOCK_SECONDS = 3600  # 1 hour

EMBEDDING_INDEX_PATH = "ops/sweeps/embedding-index.json"
"""Canonical vault-relative path for the sweeper-maintained embedding sidecar.

Must equal ``RecallConfig.index_path`` in Plan 02 so both sides reference
the same REST path. Persisted via ``vault.write_note()`` — the vault is
REST-only (D-08 REVISED / A6), so there is NO tempfile/os.replace write.
"""

def _encode_index_body(index: dict, path: str) -> str:
    """Encode an embedding index dict to a string body for vault storage.

    Case-insensitively extension-aware (plan 40-07, round-2 item D):
    - If ``path.lower().endswith(".md")``: wrap the JSON in a markdown fenced
      code block tagged with a ``json`` info-string so the Obsidian REST API
      accepts it as a note body.  Example::

          ```json
          {"notes/a.md": {...}}
          ```

    - Otherwise (e.g. ``.json``): return the raw JSON string (existing behaviour).

    Both branches are lossless: ``_decode_index_body`` is the symmetric reader.
    """
    raw_json = json.dumps(index, ensure_ascii=False)
    if path.lower().endswith(".md"):
        return f"```json\n{raw_json}\n```\n"
    return raw_json


def _decode_index_body(raw: str, path: str) -> dict:
    """Decode an index body string back to a dict; case-insensitively extension-aware.

    Symmetric to ``_encode_index_body`` (plan 40-07):
    - If ``path.lower().endswith(".md")``: extract the contents of the first
      fenced code block and ``json.loads`` them.  Falls back to ``{}`` if there
      is no parseable fenced JSON (self-healing — preserves T-40-01 / T-40-30).
    - Otherwise: ``json.loads(raw)`` directly (existing behaviour).

    Any parse failure degrades to ``{}`` for both branches (same graceful
    behaviour that ``_emit_embedding_index`` already applies to the existing-
    index read).
    """
    import re as _re

    if path.lower().endswith(".md"):
        # Extract the first fenced code block (``` … ```)
        match = _re.search(r"```(?:\w*)\n(.*?)\n```", raw, _re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(1))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    else:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}


NOMIC_DOCUMENT_PREFIX = "search_document: "
"""Instruction prefix for nomic-embed-text-v1.5 document embeddings.

Adding this prefix requires a one-time full re-embed because
``hash("search_document: " + body) != hash(body)``. The content-hash
incremental rebuild handles this naturally: every existing entry's hash
diverges from the new prefixed hash on the first post-upgrade sweep,
triggering re-embedding of the whole vault. This is the intended behaviour.

See also: ``SemanticRecall.NOMIC_QUERY_PREFIX = "search_query: "`` (Plan 02).
"""


def _embedding_model_id() -> str:
    """Return the configured embedding model id for frontmatter recording.

    Lazy settings lookup mirrors ``_active_skip_prefixes`` so isolated unit
    tests of helpers don't fail on settings import. Falls back to the
    historical default if settings is unimportable. (260502-1zv D-03 — single
    source of truth: ``Settings.embedding_model``.)
    """
    try:
        from app.config import settings
        return settings.embedding_model
    except Exception:
        return "text-embedding-nomic-embed-text-v1.5"


def _content_hash(text: str) -> str:
    """Return the first 16 hex chars of the SHA-256 of *text*.

    Used to detect body changes for incremental index rebuild (D-05).
    The hash is of the frontmatter-stripped note body — the same ``rest``
    variable passed to the embedder — so a frontmatter-only edit does NOT
    trigger an unnecessary re-embed.

    16 hex chars (64 bits) is sufficient to detect accidental collisions at
    personal-vault scale (~10K notes).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class SweepReport(BaseModel):
    sweep_id: str
    status: str = "complete"  # idle | running | complete | error
    files_processed: int = 0
    files_total: int = 0
    duplicates_moved: int = 0
    noise_moved: int = 0
    topic_moves: int = 0  # misplaced→topic-folder relocations
    errors: list[str] = Field(default_factory=list)
    # In dry_run mode, populated with {kind, src, dst, reason} dicts
    # describing every move the sweeper WOULD make. Empty for live runs.
    proposed_moves: list[dict] = Field(default_factory=list)





# --- Time / utility ---





# --- Frontmatter helpers migrated to app.markdown_frontmatter (260502-g8c Task 3) ---
# split_frontmatter / join_frontmatter now live in app.markdown_frontmatter,
# imported at the top of this module and re-exported via __all__ so existing
# `from app.services.vault_sweeper import split_frontmatter` callers (tests +
# downstream services) keep working.


# --- Embedding codec + similarity migrated to sentinel_shared (260502-g8c Task 2) ---
# encode_embedding / decode_embedding now live in sentinel_shared.embedding_codec;
# cosine_similarity / find_dup_clusters now live in sentinel_shared.similarity.
# Imported at the top of this module and re-exported via __all__ so existing
# `from app.services.vault_sweeper import cosine_similarity` callers keep working.


# --- Skip logic ---


def _should_skip(path: str, frontmatter: dict, current_pass: str) -> bool:
    """True when this path should be left alone in the current pass."""
    if any(path.startswith(p) for p in _active_skip_prefixes()):
        return True
    if not isinstance(frontmatter, dict):
        return False
    if frontmatter.get("sweep_pass") == current_pass and frontmatter.get(
        "topic"
    ) and frontmatter.get("embedding_b64"):
        return True
    return False


# --- Walk ---


async def walk_vault(client, root: str = "") -> AsyncIterator[str]:
    """BFS over Obsidian directory listings; yield .md paths only.

    Skips SWEEP_SKIP_PREFIXES at queue-pop time. Frozen-at-start: callers
    should collect into a list before mutating the vault.
    """
    queue: list[str] = [root]
    skip_prefixes = _active_skip_prefixes()
    while queue:
        dir_path = queue.pop(0)
        if any(dir_path.startswith(p.rstrip("/")) and dir_path != "" for p in skip_prefixes):
            continue
        listing = await client.list_under(dir_path)
        for entry in listing:
            if not entry:
                continue
            full = f"{dir_path}/{entry}".strip("/") if dir_path else entry.strip("/")
            # Re-check skip prefixes against the candidate
            if any(full.startswith(p.rstrip("/")) for p in skip_prefixes):
                continue
            if entry.endswith("/"):
                queue.append(full.rstrip("/"))
            elif entry.endswith(".md"):
                yield full


# --- Trash move (migrated to ObsidianVault.move_to_trash in 260502-cky) ---
# The sweeper no longer owns trash/relocate/lock primitives. Decision logic
# below (is_in_topic_dir, propose_topic_move, run_sweep orchestration)
# stays here; I/O goes through the injected ``vault``.


# --- Topic-folder move (misplaced note → correct topic dir) ---


def is_in_topic_dir(path: str, topic_dir: str) -> bool:
    """True when ``path`` is already within ``topic_dir``.

    Handles the journal nested-date case: ``journal/2026-04-27/foo.md`` is
    considered in-dir for any ``journal/...`` topic_dir, not just exact
    same-day match. The sweeper does not relocate journal entries between
    days — only flags a wrong-topic placement.
    """
    if not topic_dir:
        return False
    # Same dir or any subdirectory of topic_dir's root family.
    # For journal/2026-04-27, the family root is "journal/"; so journal/.../
    # is considered "in topic_dir family".
    family_root = topic_dir.split("/", 1)[0] + "/"
    return path.startswith(family_root)


def propose_topic_move(
    src_path: str, topic: str, *, today: str | None = None
) -> str | None:
    """Return the destination path a topic-move WOULD use, or None if no
    move is needed (already in topic family) or topic has no canonical dir.

    Used by ``run_sweep(dry_run=True)`` to populate ``proposed_moves``
    without touching the vault.
    """
    from app.services.note_classifier import topic_dir_for

    topic_dir = topic_dir_for(topic, today=today)
    if not topic_dir:
        return None
    if is_in_topic_dir(src_path, topic_dir):
        return None
    filename = src_path.rsplit("/", 1)[-1]
    return f"{topic_dir}/{filename}"


# --- Lockfile (migrated to ObsidianVault.acquire_sweep_lock / release_sweep_lock) ---


# --- Embedding index emission ---


async def _emit_embedding_index(
    client,
    survivors: list[tuple[str, dict, str, "object"]],
    embeddings: "list[list[float]] | None",
    active_paths: set[str],
    report: "SweepReport",
) -> None:
    """Build and persist the embedding index sidecar via the Vault seam.

    Reads the existing index from ``EMBEDDING_INDEX_PATH`` via
    ``client.read_note()`` (returns ``{}`` on any failure / absence /
    unparseable content — a corrupt index self-heals on the next sweep,
    satisfying T-40-01).

    Incremental rebuild (D-05):
    - Entries in ``active_paths`` whose ``content_hash`` AND ``embedding_model``
      match the current values are carried forward without re-embedding.
    - Entries NOT in ``active_paths`` are pruned (trashed / deleted notes).
    - New or changed entries receive fresh ``embedding_b64``, ``embedding_model``,
      and ``content_hash``.

    Persistence is THROUGH the Vault seam via ``client.write_note()`` — a
    single REST PUT that is atomic at the API level, matching the existing
    sweep-log pattern (lines 426-445). NO tempfile / os.replace / local
    filesystem write (D-08 REVISED / A6 REST_ONLY).

    Failures are logged as warnings and appended to ``report.errors`` (same
    graceful pattern as the sweep-log write).
    """
    # Load existing index — {} on any parse failure (T-40-01: self-healing)
    # _decode_index_body is extension-aware (fenced JSON for .md, raw JSON for .json)
    try:
        raw = await client.read_note(EMBEDDING_INDEX_PATH)
        existing_index: dict = _decode_index_body(raw, EMBEDDING_INDEX_PATH) if raw and raw.strip() else {}
    except Exception:
        existing_index = {}

    new_index: dict = {}

    # Carry forward entries for paths still active (D-05 incremental)
    for path, entry in existing_index.items():
        if path in active_paths:
            new_index[path] = entry
        # else: pruned (path is trashed or no longer in the vault)

    # Update / insert entries for survivors that have embeddings.
    #
    # DEGRADED-INDEX INVARIANT (MEM-05 / T-40-23, deterministic rule):
    # On a degraded run (embeddings=None or partial), a changed note's entry
    # MUST NOT be persisted with the new content_hash and a stale/missing vector.
    # Rule: if the body hash changed but no fresh vector is available, write the
    # entry with the OLD vector and mark it ``stale: true``. This preserves the
    # new content_hash (so SemanticRecall can detect stale entries — 40-07) while
    # making it explicit that the vector does NOT match the new body.
    # The reader-side skip of ``stale: true`` entries is owned by 40-07.
    if embeddings:
        # WR-06: if embedder returned fewer vectors than survivors, log and record
        # the mismatch instead of silently breaking mid-loop.
        if len(embeddings) < len(survivors):
            msg = (
                f"_emit_embedding_index: embedder returned {len(embeddings)} vectors "
                f"for {len(survivors)} survivors — index will be partial"
            )
            logger.warning("sweep: %s", msg)
            report.errors.append(msg)

        for idx, (path, _fm, rest, _cls) in enumerate(survivors):
            if idx >= len(embeddings):
                # No fresh vector for this survivor — apply degraded-index rule
                content_hash = _content_hash(rest)
                active_model = _embedding_model_id()
                existing_entry = existing_index.get(path, {})
                if (
                    existing_entry.get("content_hash") == content_hash
                    and existing_entry.get("embedding_model") == active_model
                ):
                    new_index[path] = existing_entry
                else:
                    # Body changed but no fresh vector available — mark stale
                    new_index[path] = {
                        "embedding_b64": existing_entry.get("embedding_b64", ""),
                        "embedding_model": existing_entry.get("embedding_model", _embedding_model_id()),
                        "content_hash": content_hash,
                        "stale": True,
                    }
                continue
            content_hash = _content_hash(rest)
            active_model = _embedding_model_id()
            existing_entry = existing_index.get(path, {})

            if (
                existing_entry.get("content_hash") == content_hash
                and existing_entry.get("embedding_model") == active_model
            ):
                # Hash + model match — carry forward unchanged (D-05)
                new_index[path] = existing_entry
            else:
                # Body changed, or model changed (triggers re-embed) — write fresh entry
                new_index[path] = {
                    "embedding_b64": encode_embedding(embeddings[idx]),
                    "embedding_model": active_model,
                    "content_hash": content_hash,
                }
    else:
        # No embeddings at all (degraded run) — apply degraded-index rule to all survivors
        for path, _fm, rest, _cls in survivors:
            content_hash = _content_hash(rest)
            active_model = _embedding_model_id()
            existing_entry = existing_index.get(path, {})
            if (
                existing_entry.get("content_hash") == content_hash
                and existing_entry.get("embedding_model") == active_model
            ):
                # Unchanged — carry forward (may still have stale=True from a prior
                # degraded run; preserving it is correct — the body still matches)
                new_index[path] = existing_entry
            else:
                # Body changed but no fresh vector — mark stale (MEM-05 invariant)
                new_index[path] = {
                    "embedding_b64": existing_entry.get("embedding_b64", ""),
                    "embedding_model": existing_entry.get("embedding_model", active_model),
                    "content_hash": content_hash,
                    "stale": True,
                }

    # Persist via vault seam — single REST PUT (D-08 REVISED)
    # _encode_index_body is extension-aware: fenced JSON for .md, raw JSON for .json
    try:
        await client.write_note(EMBEDDING_INDEX_PATH, _encode_index_body(new_index, EMBEDDING_INDEX_PATH))
    except Exception as exc:
        logger.warning("sweep: embedding index write failed: %s", exc)
        report.errors.append(f"index_emit: {exc}")


# --- Index-only rebuild (non-destructive startup path, D-06) ---


async def rebuild_embedding_index(
    client,
    embedder: Callable[[list[str]], Awaitable[list[list[float]]]],
    *,
    model_loaded: bool = True,
    source_folder: str = "",
) -> SweepReport:
    """Walk vault, embed bodies, and write the embedding-index sidecar.

    This is the STARTUP path (D-06 / T-40-13): it refreshes
    ``ops/sweeps/embedding-index.json`` without ever calling the classifier,
    relocating notes, moving anything to trash, or de-duplicating.  Only
    ``list_under``, ``read_note``, and ``write_note`` primitives are used —
    ``relocate``, ``move_to_trash``, and ``delete_note`` are NEVER called.

    Because no destructive operation is performed, this routine takes NO
    ``safe_to_mutate`` probe (that probe gates destructive moves in
    ``run_sweep``).  The ``model_loaded`` keyword here governs ONLY whether
    the embedder is invoked:

    - ``model_loaded=True``  → embed bodies and write a fresh index.
    - ``model_loaded=False`` → skip embedding entirely, log a WARNING, set
      ``report.status = "skipped"``, and return WITHOUT writing fresh vectors.
      The degraded-index invariant governs carry-forward semantics in
      ``_emit_embedding_index``: a changed note's hash is never persisted
      without a fresh vector.

    Reuses the existing sweep lock so a cold-start rebuild and an admin
    ``run_sweep`` cannot interleave writes (T-40-16).
    """
    sweep_id = _iso_utc()
    report = SweepReport(sweep_id=sweep_id, status="running")

    if not await client.acquire_sweep_lock():
        raise SweepInProgressError("a sweep is already running")

    try:
        if not model_loaded:
            logger.warning(
                "rebuild_embedding_index: embedding model unavailable — index refresh skipped"
            )
            report.status = "skipped"
            return report

        # 1. Walk → freeze list at start (read/list only — no classifier)
        paths: list[str] = []
        async for p in walk_vault(client, root=source_folder):
            paths.append(p)
        report.files_total = len(paths)

        # 2. Build survivors tuples (path, fm, rest, None) — NO classifier call
        survivors: list[tuple[str, dict, str, "object"]] = []
        for path in paths:
            try:
                body = await client.read_note(path)
                fm, rest = split_frontmatter(body)
                survivors.append((path, fm, rest, None))
                report.files_processed += 1
            except Exception as exc:
                msg = f"{path}: {exc}"
                logger.warning("rebuild_embedding_index error: %s", msg)
                report.errors.append(msg)

        # 3. Embed all surviving bodies (NOMIC_DOCUMENT_PREFIX for nomic instruction space)
        bodies = [NOMIC_DOCUMENT_PREFIX + s[2] for s in survivors]
        embeddings: list[list[float]] | None = None
        if bodies:
            try:
                embeddings = await embedder(bodies)
            except Exception as exc:
                logger.warning(
                    "rebuild_embedding_index: embedding endpoint failed (%s); index will be partial",
                    exc,
                )
                embeddings = None

        # 4. Emit index sidecar — reuses the shared helper; no classify/relocate/trash
        active_paths: set[str] = {s[0] for s in survivors}
        await _emit_embedding_index(client, survivors, embeddings, active_paths, report)

        report.status = "complete"
        return report
    except SweepInProgressError:
        report.status = "blocked"
        raise
    except Exception as exc:
        report.status = "error"
        report.errors.append(str(exc))
        raise
    finally:
        await client.release_sweep_lock()


# --- Sweep orchestrator ---


async def run_sweep(
    client,
    classifier: Callable[[str], Awaitable["object"]],
    embedder: Callable[[list[str]], Awaitable[list[list[float]]]],
    *,
    force_reclassify: bool = False,
    status_callback: Callable[[SweepReport], None] | None = None,
    dry_run: bool = False,
    source_folder: str = "",
    safe_to_mutate: "Callable[[], Awaitable[bool]] | None" = None,
) -> SweepReport:
    """Walk vault, classify, embed, de-dup, relocate-misplaced, move-to-trash.

    Args:
        client: Vault adapter (ObsidianVault or FakeVault) with list_under/
            read_note/write_note/delete_note/patch_append plus the sweep
            primitives move_to_trash/relocate/acquire_sweep_lock/release_sweep_lock.
        classifier: async fn(text) → ClassificationResult (or compatible).
            Bound caller passes ``classify_note`` from note_classifier.
        embedder: async fn(list[str]) → list[list[float]]. Caller binds the
            current LLM endpoint. Failure raises and degrades de-dup.
        force_reclassify: re-classify already-marked notes.
        status_callback: optional progress hook called after each file.
        dry_run: when True, populate ``report.proposed_moves`` with every
            move the sweeper WOULD make and write nothing to the vault.
            Operator runs this first to preview before authorizing a real
            sweep. Lockfile is still acquired/released (one preview at a
            time is correct semantics). Dry-run performs no moves regardless
            of ``safe_to_mutate`` — no probe needed for preview.
        safe_to_mutate: MANDATORY for destructive (non-dry-run) runs.
            An async callable () → bool that the sweeper re-evaluates
            IMMEDIATELY BEFORE EACH live ``relocate`` / ``move_to_trash``
            call in ALL THREE destructive branches. This ensures that if the
            readiness signal flips to False partway through a sweep, no
            destructive move occurs after that point.

            FAIL-CLOSED BY CONSTRUCTION (round-3 HIGH): if ``safe_to_mutate``
            is None (omitted), the per-move helper ``_is_safe()`` returns
            False — a destructive run with no probe performs ZERO destructive
            moves. There is NO permissive default that means "safe". The
            bypass is closed by construction, not by callers remembering to
            pass a probe.

            The dry-run path (``dry_run=True``) does NOT require a probe:
            it performs no vault mutations regardless.
    """
    sweep_id = _iso_utc()
    report = SweepReport(sweep_id=sweep_id, status="running")

    # -----------------------------------------------------------------------
    # MANDATORY FAIL-CLOSED PER-MOVE SAFETY HELPER (round-3 HIGH)
    # Re-evaluated IMMEDIATELY BEFORE each live relocate/move_to_trash call.
    # When safe_to_mutate is None (no probe supplied), returns False so that a
    # destructive run without a probe performs ZERO moves by construction.
    # -----------------------------------------------------------------------
    async def _is_safe() -> bool:
        if safe_to_mutate is not None:
            return await safe_to_mutate()
        return False  # fail-closed — no probe means unsafe

    # Import ProtectedPathError lazily so this module doesn't hard-depend on
    # 40-05 being merged. Falls back to catching the broad Exception that
    # already wraps these branches.
    try:
        from app.errors import ProtectedPathError as _ProtectedPathError
    except ImportError:
        _ProtectedPathError = Exception  # type: ignore[misc,assignment]

    if not await client.acquire_sweep_lock():
        raise SweepInProgressError("a sweep is already running")

    try:
        # 1. Walk → freeze list at start
        paths: list[str] = []
        async for p in walk_vault(client, root=source_folder):
            paths.append(p)
        report.files_total = len(paths)

        survivors: list[tuple[str, dict, str, "object"]] = []  # path, fm, body, classification

        for path in paths:
            try:
                body = await client.read_note(path)
                fm, rest = split_frontmatter(body)
                if not force_reclassify and _should_skip(path, fm, sweep_id):
                    report.files_processed += 1
                    if status_callback:
                        status_callback(report)
                    continue

                # Cheap-filter check before LLM (delegated to classifier)
                result = await classifier(rest if rest.strip() else body)

                if getattr(result, "topic", None) == "noise":
                    if dry_run:
                        today = _today_str()
                        report.proposed_moves.append({
                            "kind": "trash",
                            "src": path,
                            "dst": f"_trash/{today}/{path.rsplit('/', 1)[-1]}",
                            "reason": "cheap-filter:noise",
                        })
                        report.noise_moved += 1
                    else:
                        # MANDATORY per-move safety check (re-evaluated here, not once per run)
                        if await _is_safe():
                            try:
                                await client.move_to_trash(
                                    path, reason="cheap-filter:noise", sweep_at=sweep_id
                                )
                                report.noise_moved += 1
                            except _ProtectedPathError as exc:
                                report.errors.append(f"protected: refused to move {path}: {exc}")
                        else:
                            report.errors.append(f"degraded/unsafe: skipped noise-trash for {path}")
                    report.files_processed += 1
                    if status_callback:
                        status_callback(report)
                    continue

                # Misplaced-note relocation: if classified topic has a canonical
                # directory and the current path isn't already in that family,
                # move (or propose to move) the note to {topic_dir}/{filename}.
                topic = getattr(result, "topic", None)
                proposed_dst = (
                    propose_topic_move(path, topic) if topic else None
                )
                if proposed_dst is not None:
                    if dry_run:
                        report.proposed_moves.append({
                            "kind": "topic",
                            "src": path,
                            "dst": proposed_dst,
                            "reason": f"topic={topic} (confidence={result.confidence:.2f})",
                        })
                        # 260427-cza: parity with the live `else` branch below
                        # which increments topic_moves. Without this, dry-run
                        # reports `topic_moves: 0` while listing N proposals.
                        report.topic_moves += 1
                        # Don't add to survivors in dry-run — we're not writing
                        # frontmatter or computing embeddings. Just report.
                        report.files_processed += 1
                        if status_callback:
                            status_callback(report)
                        continue
                    else:
                        # MANDATORY per-move safety check (re-evaluated before each relocate)
                        if not await _is_safe():
                            report.errors.append(f"degraded/unsafe: skipped topic-move for {path}")
                            report.files_processed += 1
                            if status_callback:
                                status_callback(report)
                            continue
                        try:
                            new_path = await client.relocate(
                                path, proposed_dst, sweep_at=sweep_id
                            )
                            report.topic_moves += 1
                            # Continue processing using the new path so
                            # frontmatter + embedding land at the right location.
                            path = new_path
                            # Re-read body from new location for survivors entry
                            body = await client.read_note(path)
                            fm, rest = split_frontmatter(body)
                        except _ProtectedPathError as exc:
                            report.errors.append(f"protected: refused to move {path}: {exc}")
                            report.files_processed += 1
                            if status_callback:
                                status_callback(report)
                            continue
                        except Exception as exc:
                            report.errors.append(f"topic_move {path}: {exc}")
                            report.files_processed += 1
                            if status_callback:
                                status_callback(report)
                            continue

                # (round-2 item C) SUPPRESS CLASSIFICATION FRONTMATTER WRITE-BACK on
                # unsafe runs. On a degraded run, degraded classifier output must NOT be
                # persisted anywhere — not just suppressed as a move. The note is left
                # byte-identical.
                # Guard: re-evaluate safety here (same per-note call as relocate guard;
                # the embedder is separate — its failure doesn't decide safety alone).
                if not dry_run and not await _is_safe():
                    # Unsafe — skip frontmatter write-back, don't add to survivors
                    # (no embedding index update with fresh hash either)
                    report.files_processed += 1
                    if status_callback:
                        status_callback(report)
                    continue

                # Write back classification frontmatter (preserve extras)
                new_fm = dict(fm)
                new_fm["topic"] = result.topic
                new_fm["confidence"] = float(result.confidence)
                new_fm["sweep_pass"] = sweep_id
                new_fm["source"] = new_fm.get("source") or "vault-sweep"
                if result.title_slug:
                    new_fm.setdefault("title_slug", result.title_slug)

                survivors.append((path, new_fm, rest, result))
                report.files_processed += 1
                if status_callback:
                    status_callback(report)
            except Exception as exc:
                msg = f"{path}: {exc}"
                logger.warning("sweep error: %s", msg)
                report.errors.append(msg)

        # 2. Embed all surviving bodies — degrade gracefully on failure.
        # Prepend NOMIC_DOCUMENT_PREFIX before calling the embedder so that
        # document and query embeddings share the same nomic instruction space
        # (RESEARCH Pattern 6). Note: adding this prefix changes the content-hash
        # of every existing note, triggering a one-time full re-embed on the
        # first post-upgrade sweep (intended — see NOMIC_DOCUMENT_PREFIX docstring).
        bodies = [NOMIC_DOCUMENT_PREFIX + s[2] for s in survivors]
        embeddings: list[list[float]] | None = None
        if bodies:
            try:
                embeddings = await embedder(bodies)
            except Exception as exc:
                logger.warning(
                    "sweep: embedding endpoint failed (%s); skipping de-dup. "
                    "safe-to-mutate probe governs whether moves proceed",
                    exc,
                )
                embeddings = None

        # 3. Write classification + (optional) embedding back to each note.
        # Skipped entirely in dry_run — no vault mutations are allowed.
        if not dry_run:
            for idx, (path, fm, rest, _) in enumerate(survivors):
                try:
                    if embeddings and idx < len(embeddings):
                        fm["embedding_model"] = _embedding_model_id()
                        fm["embedding_b64"] = encode_embedding(embeddings[idx])
                    new_body = join_frontmatter(fm, rest)
                    await client.write_note(path, new_body)
                except Exception as exc:
                    report.errors.append(f"write_back {path}: {exc}")

        # 3b. Emit embedding index sidecar (D-04 / D-05 / D-07 / D-08).
        # Called immediately after the step-3 write-back loop so the index
        # reflects the same embeddings just written into note frontmatter.
        # Guarded by ``not dry_run`` — index emission is a vault write.
        # On a degraded run (unsafe/no probe) embeddings=None is passed so that
        # the degraded-index invariant governs carry-forward (see _emit_embedding_index).
        #
        # DEGRADED ACTIVE PATHS (MEM-05): on a degraded run, survivors may be
        # empty because the safe-to-mutate gate skipped all notes. We must NOT
        # prune existing index entries for paths that still exist in the vault —
        # use the full ``paths`` list (all walked paths) as active_paths so that
        # notes walked but not processed through survivors aren't evicted from the
        # index. Actual stale/missing entries are governed by the degraded-index
        # rule in _emit_embedding_index.
        if not dry_run:
            active_paths: set[str] = set(paths)  # all walked paths, not just survivors
            await _emit_embedding_index(client, survivors, embeddings, active_paths, report)

        # 4. De-dup
        moves: list[tuple[str, str, str]] = []  # (src, dst, reason)
        if embeddings and len(embeddings) >= 2:
            matrix = np.asarray(embeddings, dtype=np.float32)
            clusters = find_dup_clusters(matrix, threshold=0.92)
            for cluster in clusters:
                # Keeper rule: max(cluster, key=(-mtime, len(body))) — older wins
                # We don't have mtime from Obsidian REST, so fall back to:
                # keeper = the longest body in the cluster (older proxy unavailable).
                keeper_idx = max(
                    cluster, key=lambda i: len(survivors[i][2])
                )
                for i in cluster:
                    if i == keeper_idx:
                        continue
                    src = survivors[i][0]
                    conf = float(survivors[i][3].confidence)
                    keeper_path = survivors[keeper_idx][0]
                    if dry_run:
                        today = _today_str()
                        proposed = f"_trash/{today}/{src.rsplit('/', 1)[-1]}"
                        report.proposed_moves.append({
                            "kind": "trash",
                            "src": src,
                            "dst": proposed,
                            "reason": f"duplicate of {keeper_path} (cosine≥0.92, conf={conf:.1f})",
                        })
                        report.duplicates_moved += 1
                        continue
                    # MANDATORY per-move safety check (re-evaluated before each dedup-trash)
                    if not await _is_safe():
                        report.errors.append(f"degraded/unsafe: skipped dedup-trash for {src}")
                        continue
                    try:
                        dst = await client.move_to_trash(
                            src,
                            reason=f"duplicate of {keeper_path}",
                            sweep_at=sweep_id,
                        )
                        moves.append((src, dst, f"duplicate (cosine≥0.92, conf={conf:.1f})"))
                        report.duplicates_moved += 1
                    except _ProtectedPathError as exc:
                        report.errors.append(f"protected: refused to move {src}: {exc}")
                    except Exception as exc:
                        report.errors.append(f"trash {src}: {exc}")

        # 5. Per-sweep log — never written in dry-run
        if not dry_run and (moves or report.noise_moved):
            log_path = f"ops/sweeps/{_today_str()}.md"
            log_lines = [f"\n## Sweep {sweep_id}\n"]
            for src, dst, reason in moves:
                log_lines.append(f"- `{src}` → `{dst}` — {reason}\n")
            log_lines.append(
                f"\nProcessed: {report.files_processed}/{report.files_total}; "
                f"noise: {report.noise_moved}; duplicates: {report.duplicates_moved}\n"
            )
            log_block = "".join(log_lines)
            try:
                existing = await client.read_note(log_path)
                if existing:
                    await client.patch_append(log_path, log_block)
                else:
                    await client.write_note(
                        log_path, f"# Sweep log {_today_str()}\n{log_block}"
                    )
            except Exception as exc:
                logger.warning("sweep log write failed: %s", exc)
                report.errors.append(f"log: {exc}")

        report.status = "complete"
        return report
    except SweepInProgressError:
        report.status = "blocked"
        raise
    except Exception as exc:
        report.status = "error"
        report.errors.append(str(exc))
        raise
    finally:
        await client.release_sweep_lock()


# --- Operational status wrappers (for /vault/sweep/status route) ---


def get_status() -> dict:
    return get_sweep_status()


def _set_status(report: SweepReport) -> None:
    set_sweep_status_from_report(report)


def reset_status_for_tests() -> None:
    reset_sweep_status()
