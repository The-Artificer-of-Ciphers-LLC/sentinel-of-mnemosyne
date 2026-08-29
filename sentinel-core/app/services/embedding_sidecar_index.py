"""Embedding sidecar index format and eligibility semantics.

The sidecar lives in the Vault at ``ops/sweeps/embedding-index.json``. The
vault sweeper writes it, and SemanticRecall reads it through the Vault seam.
This module owns the shared interpretation so writer and reader cannot drift.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from sentinel_shared.embedding_codec import decode_embedding, encode_embedding

logger = logging.getLogger(__name__)

EMBEDDING_INDEX_PATH = "ops/sweeps/embedding-index.json"
"""Canonical vault-relative path for the sweeper-maintained embedding sidecar.

Persisted via ``vault.write_note()``. The vault is REST-only, so there is no
tempfile/os.replace write path.
"""

NOMIC_DOCUMENT_PREFIX = "search_document: "
"""Instruction prefix for nomic-embed-text-v1.5 document embeddings."""

MAX_EMBEDDING_B64_LEN = 256 * 1024
"""Upper bound for a single base64 embedding payload before decode."""


@dataclass(frozen=True)
class EligibleEmbeddingEntry:
    """A decoded sidecar entry that can participate in semantic Recall."""

    path: str
    vector: np.ndarray


def encode_index_body(index: dict[str, dict[str, Any]], path: str) -> str:
    """Encode an embedding index dict to a string body for vault storage."""
    raw_json = json.dumps(index, ensure_ascii=False)
    if path.lower().endswith(".md"):
        return f"```json\n{raw_json}\n```\n"
    return raw_json


def decode_index_body(raw: str, path: str) -> dict[str, dict[str, Any]]:
    """Decode an index body string back to a dict.

    For markdown paths, extract the first fenced code block. Any parse failure
    degrades to ``{}`` so corrupt indexes self-heal on the next sweep.
    """
    if path.lower().endswith(".md"):
        match = re.search(r"```(?:\w*)\n(.*?)\n```", raw, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(1))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def content_hash(text: str) -> str:
    """Return the first 16 hex chars of the SHA-256 of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fresh_entry(
    rest: str,
    embedding: list[float],
    active_model: str,
    *,
    embedding_dim: int | None = None,
) -> dict[str, Any]:
    """Build a fresh index entry for a note body and embedding.

    ``embedding_dim`` (D-08/EMB-04) is the resolved dimension of the
    embedder's output for this sweep batch, threaded in by the caller
    (mirrors ``active_model``). Falls back to ``len(embedding)`` when the
    caller omits it, so this entry's own vector is always self-consistent
    even if a batch-level dimension wasn't resolved.
    """
    return {
        "embedding_b64": encode_embedding(embedding),
        "embedding_model": active_model,
        "content_hash": content_hash(rest),
        "embedding_dim": embedding_dim if embedding_dim is not None else len(embedding),
    }


def stale_entry(
    existing_entry: dict[str, Any],
    *,
    rest: str,
    active_model: str,
    embedding_dim: int | None = None,
) -> dict[str, Any]:
    """Build the degraded entry for a changed body without a fresh vector.

    ``embedding_dim`` carries forward the existing entry's persisted
    dimension when present (mirrors the ``embedding_model`` fallback
    pattern immediately below); otherwise falls back to the caller-supplied
    ``embedding_dim`` (the active sweep's resolved dimension, if any).
    """
    return {
        "embedding_b64": existing_entry.get("embedding_b64", ""),
        "embedding_model": existing_entry.get("embedding_model", active_model),
        "content_hash": content_hash(rest),
        "stale": True,
        "embedding_dim": existing_entry.get("embedding_dim", embedding_dim),
    }


def _is_reusable_entry(
    entry: dict[str, Any],
    *,
    body_hash: str,
    active_model: str,
) -> bool:
    """Return True iff *entry* can be carried forward as-is.

    Incident (2026-08-29, live prod): a stale entry (written by
    ``stale_entry`` after a transient embedding failure) still records the
    note's current ``content_hash`` and the active ``embedding_model`` — it
    just carries no usable vector. A content_hash/model match alone is
    therefore NOT sufficient to prove an entry is safe to carry forward:
    without also checking ``stale`` and the presence of ``embedding_b64``,
    a stale entry would match on every subsequent rebuild forever and could
    never heal, even once a fresh vector for that same note was sitting
    right there in the current sweep's ``embeddings`` list. All three
    carry-forward sites in ``build_embedding_index`` must route through
    this helper so they cannot drift apart on this check again.
    """
    return (
        entry.get("content_hash") == body_hash
        and entry.get("embedding_model") == active_model
        and not entry.get("stale")
        and bool(entry.get("embedding_b64"))
    )


def build_embedding_index(
    *,
    existing_index: dict[str, dict[str, Any]],
    survivors: list[tuple[str, dict, str, object]],
    embeddings: list[list[float]] | None,
    active_paths: set[str],
    active_model: str,
    active_embedding_dim: int | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Build the next sidecar index from prior state and current sweep results.

    ``active_embedding_dim`` (D-08/EMB-04) is the resolved dimension of the
    current sweep's embedder output (e.g. ``len(embeddings[0])``), threaded
    into every ``fresh_entry``/``stale_entry`` call alongside ``active_model``
    so the sidecar reader (``eligible_entries``) can skip-before-decode on a
    stale-dimension entry. Optional and defaults to ``None`` for backward
    compatibility with callers that don't resolve a batch-level dimension
    (each ``fresh_entry`` still self-resolves from its own vector in that case).
    """
    errors: list[str] = []
    new_index: dict[str, dict[str, Any]] = {}

    for path, entry in existing_index.items():
        if path in active_paths:
            new_index[path] = entry

    if embeddings:
        if len(embeddings) < len(survivors):
            errors.append(
                f"_emit_embedding_index: embedder returned {len(embeddings)} vectors "
                f"for {len(survivors)} survivors — index will be partial"
            )

        for idx, (path, _fm, rest, _cls) in enumerate(survivors):
            body_hash = content_hash(rest)
            existing_entry = existing_index.get(path, {})

            if idx >= len(embeddings):
                if _is_reusable_entry(
                    existing_entry, body_hash=body_hash, active_model=active_model
                ):
                    new_index[path] = existing_entry
                else:
                    new_index[path] = stale_entry(
                        existing_entry,
                        rest=rest,
                        active_model=active_model,
                        embedding_dim=active_embedding_dim,
                    )
                continue

            if _is_reusable_entry(
                existing_entry, body_hash=body_hash, active_model=active_model
            ):
                new_index[path] = existing_entry
            else:
                new_index[path] = fresh_entry(
                    rest, embeddings[idx], active_model, embedding_dim=active_embedding_dim
                )

        return new_index, errors

    for path, _fm, rest, _cls in survivors:
        body_hash = content_hash(rest)
        existing_entry = existing_index.get(path, {})
        if _is_reusable_entry(
            existing_entry, body_hash=body_hash, active_model=active_model
        ):
            new_index[path] = existing_entry
        else:
            new_index[path] = stale_entry(
                existing_entry,
                rest=rest,
                active_model=active_model,
                embedding_dim=active_embedding_dim,
            )

    return new_index, errors


def eligible_entries(
    index: dict[str, dict[str, Any]],
    *,
    active_model: str,
    exclude_prefixes: tuple[str, ...],
    query_dim: int,
    max_b64_len: int = MAX_EMBEDDING_B64_LEN,
) -> tuple[list[EligibleEmbeddingEntry], int]:
    """Return entries eligible for semantic Recall and the matched-model count."""
    entries: list[EligibleEmbeddingEntry] = []
    matched_model_count = 0

    for path, entry in index.items():
        if path.startswith(exclude_prefixes):
            continue
        if entry.get("stale"):
            continue

        entry_model = entry.get("embedding_model", "")
        if not entry_model or entry_model != active_model:
            continue
        matched_model_count += 1

        # D-08 (EMB-04): dimension-mismatch guard — the single source of
        # truth for "never cosine across vectors of mismatched dimension".
        # This is defense-in-depth beyond the MEM-05 model-string skip
        # above: the LM Studio cutover can carry the SAME embedding_model
        # string with a DIFFERENT output dimension (e.g. a Matryoshka
        # truncation change), so the model-string match alone is not
        # sufficient. Do not add a second guard elsewhere (e.g. in
        # SemanticRecall) — this is the only place this invariant is
        # enforced.
        #
        # Cheap fast path: if the sidecar entry carries a persisted
        # ``embedding_dim`` (written by the sweeper — see vault_sweeper.py
        # rebuild_embedding_index), compare it to query_dim BEFORE
        # decoding the base64 vector, skipping the decode entirely on
        # mismatch. Entries without a persisted embedding_dim (older,
        # pre-D-08 indexes) fall through unchanged to the decode-time
        # ``len(raw) != query_dim`` check below — fully backward
        # compatible.
        stored_dim = entry.get("embedding_dim")
        if isinstance(stored_dim, int) and stored_dim > 0 and stored_dim != query_dim:
            logger.warning(
                "Embedding sidecar index: persisted embedding_dim mismatch for %r "
                "(%d vs query %d), skipping before decode",
                path,
                stored_dim,
                query_dim,
            )
            continue

        try:
            b64 = entry.get("embedding_b64", "")
            if len(b64) > max_b64_len:
                logger.warning(
                    "Embedding sidecar index: embedding_b64 for %r exceeds cap (%d > %d), skipping",
                    path,
                    len(b64),
                    max_b64_len,
                )
                continue

            raw = decode_embedding(b64)
            if not raw:
                logger.warning(
                    "Embedding sidecar index: zero-length embedding for %r, skipping",
                    path,
                )
                continue

            # D-08 (EMB-04) decode-time fallback guard: hard-skip (log +
            # continue, never raise) any entry whose decoded vector length
            # differs from the live query vector's dimension. This is the
            # backward-compatible path for entries lacking a persisted
            # embedding_dim, and the final backstop for all entries.
            if len(raw) != query_dim:
                logger.warning(
                    "Embedding sidecar index: dimension mismatch for %r (%d vs query %d), skipping",
                    path,
                    len(raw),
                    query_dim,
                )
                continue

            entries.append(
                EligibleEmbeddingEntry(
                    path=path,
                    vector=np.asarray(raw, dtype=np.float32),
                )
            )
        except Exception as exc:
            logger.warning(
                "Embedding sidecar index: error decoding %r: %r — skipping entry",
                path,
                exc,
            )

    return entries, matched_model_count
