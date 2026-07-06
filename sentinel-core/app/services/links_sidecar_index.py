"""Links sidecar index: persistence + freshness layer for the wikilink graph.

Structural clone of ``embedding_sidecar_index.py`` (D-04): builds/decodes the
``ops/graph/links-index.json`` sidecar, self-heals on parse failure, excludes
its own path from the notes/ walk it indexes, and carries unchanged notes
forward by content hash.

Freshness is hybrid (D-04a): a service-side writer can patch a single entry
directly (not implemented here — that seam belongs to the writer, e.g.
``moc_maintenance.attach_to_hub``), and this module provides the lazy
full-rebuild-if-stale fallback that ``:graph``/``:stats``/``:check`` (Plan
45-06) call on every invocation. The staleness signal is a ``notes/``
path-set diff against the stored index keys — a single cheap
``list_under`` call, not a full walk (Pitfall 5). A body edit to an
*existing* note with no path-set change is a documented, accepted
approximation gap (RESEARCH Pitfall 5): the next full rebuild (triggered by
any add/remove/rename) will pick it up.

This module performs vault I/O (unlike ``graph_analysis.py``, which is pure
computation) but never classifies, relocates, or trashes a note — only
``list_under``/``read_note``/``write_note`` primitives are used, mirroring
``rebuild_embedding_index``'s non-destructive contract.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.errors import SweepInProgressError
from app.services.embedding_sidecar_index import content_hash
from app.services.graph_analysis import NOTES_ROOT, extract_wikilinks
from app.services.note_schema import parse_schema_block
from app.services.vault_sweeper import walk_vault

logger = logging.getLogger(__name__)

LINKS_INDEX_PATH = "ops/graph/links-index.json"
"""Canonical vault-relative path for the links-graph sidecar (D-04).

Persisted via ``vault.write_note()``. The vault is REST-only, so there is
no tempfile/os.replace write path (mirrors ``EMBEDDING_INDEX_PATH``).
"""


def encode_index_body(index: dict[str, dict[str, Any]]) -> str:
    """Encode a links index dict to a JSON string body for vault storage."""
    return json.dumps(index, ensure_ascii=False)


def decode_index_body(raw: str) -> dict[str, dict[str, Any]]:
    """Decode an index body string back to a dict.

    Any parse failure (malformed JSON, non-dict top level) degrades to
    ``{}`` so a corrupt index self-heals on the next rebuild (T-45-SELFHEAL)
    — this function never raises, mirroring
    ``embedding_sidecar_index.decode_index_body`` exactly.
    """
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


async def build_links_index(
    vault, existing: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Walk ``NOTES_ROOT`` and build the links index, carrying unchanged notes forward.

    Explicitly skips ``LINKS_INDEX_PATH`` (D-04) as a defensive guard even
    though the notes-scoped walk cannot reach ``ops/graph/``. For each note,
    stores its content hash, extracted wikilinks (as a sorted list for JSON
    stability), and parsed ``_schema`` block. A note whose content hash is
    unchanged versus ``existing`` is carried forward by reusing the existing
    entry object, without recomputing wikilinks or the schema block.
    """
    new_index: dict[str, dict[str, Any]] = {}
    async for path in walk_vault(vault, root=NOTES_ROOT):
        if path == LINKS_INDEX_PATH:
            continue

        body = await vault.read_note(path)
        body_hash = content_hash(body)

        existing_entry = existing.get(path)
        if existing_entry is not None and existing_entry.get("content_hash") == body_hash:
            new_index[path] = existing_entry
            continue

        new_index[path] = {
            "content_hash": body_hash,
            "wikilinks": sorted(extract_wikilinks(body)),
            "schema": parse_schema_block(body),
        }
    return new_index


async def rebuild_links_index(vault) -> dict[str, dict[str, Any]]:
    """Unconditionally rebuild and persist the links index sidecar.

    Reads the existing index (self-healing to ``{}`` on any read/parse
    failure), rebuilds via ``build_links_index``, writes the encoded result
    to ``LINKS_INDEX_PATH`` via ``write_note``, and returns the fresh index.
    Never relocates or deletes any note content — only read/write/list
    primitives are used (mirrors ``rebuild_embedding_index``'s
    non-destructive contract, D-04).

    Piggybacks the existing sweep lock (acquire/release) so this rebuild
    coordinates with the sweeper and cannot interleave writes with an
    in-progress sweep (D-04a). Raises ``SweepInProgressError`` when the lock
    is already held — the caller (``rebuild_links_index_if_stale``) is
    responsible for catching that and degrading gracefully (Pitfall 2); a
    direct caller of this function gets the same signal a destructive sweep
    would. A write failure is logged and swallowed (never fatal), matching
    ``_emit_embedding_index``'s graceful-degrade posture.
    """
    if not await vault.acquire_sweep_lock():
        raise SweepInProgressError("a sweep is already running")

    try:
        try:
            raw = await vault.read_note(LINKS_INDEX_PATH)
            existing = decode_index_body(raw) if raw and raw.strip() else {}
        except Exception:
            existing = {}

        new_index = await build_links_index(vault, existing)

        try:
            await vault.write_note(LINKS_INDEX_PATH, encode_index_body(new_index))
        except Exception as exc:
            logger.warning("rebuild_links_index: write failed: %s", exc)

        return new_index
    finally:
        await vault.release_sweep_lock()


async def rebuild_links_index_if_stale(vault) -> dict[str, dict[str, Any]]:
    """D-04a hybrid freshness: full rebuild only when the notes/ path-set changed.

    Reads the existing index, then computes the current ``notes/`` path-set
    from a single ``vault.list_under(NOTES_ROOT)`` call (cheap — no full
    walk) and compares it against ``set(existing.keys())``. Any add/remove/
    rename mismatch triggers a full rebuild via ``rebuild_links_index``;
    otherwise the existing index is returned unchanged.

    A hand-edit of an *existing* note's wikilinks with no path-set change is
    the accepted approximation gap (Pitfall 5) — this cheap check cannot
    detect it; only a full rebuild (triggered by some other add/remove) or a
    direct single-entry patch from a writer (out of scope for this function)
    picks it up.

    When the sweep lock is already held (``SweepInProgressError``), degrades
    to returning the existing (possibly stale) index rather than propagating
    the error (Pitfall 2) — a read-mostly ``:graph``/``:stats``/``:check``
    call must never hard-fail just because an unrelated sweep is running.
    """
    try:
        raw = await vault.read_note(LINKS_INDEX_PATH)
        existing = decode_index_body(raw) if raw and raw.strip() else {}
    except Exception:
        existing = {}

    try:
        listing = await vault.list_under(NOTES_ROOT)
    except Exception:
        listing = []
    current_paths = {
        f"{NOTES_ROOT}/{entry}" for entry in listing if entry.endswith(".md")
    }

    if current_paths == set(existing.keys()):
        return existing

    try:
        return await rebuild_links_index(vault)
    except SweepInProgressError:
        logger.warning(
            "rebuild_links_index_if_stale: sweep already in progress — serving existing (possibly stale) index"
        )
        return existing
