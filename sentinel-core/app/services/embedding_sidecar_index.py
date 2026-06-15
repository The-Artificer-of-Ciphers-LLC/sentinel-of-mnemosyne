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


def fresh_entry(rest: str, embedding: list[float], active_model: str) -> dict[str, Any]:
    """Build a fresh index entry for a note body and embedding."""
    return {
        "embedding_b64": encode_embedding(embedding),
        "embedding_model": active_model,
        "content_hash": content_hash(rest),
    }


def stale_entry(
    existing_entry: dict[str, Any],
    *,
    rest: str,
    active_model: str,
) -> dict[str, Any]:
    """Build the degraded entry for a changed body without a fresh vector."""
    return {
        "embedding_b64": existing_entry.get("embedding_b64", ""),
        "embedding_model": existing_entry.get("embedding_model", active_model),
        "content_hash": content_hash(rest),
        "stale": True,
    }


def build_embedding_index(
    *,
    existing_index: dict[str, dict[str, Any]],
    survivors: list[tuple[str, dict, str, object]],
    embeddings: list[list[float]] | None,
    active_paths: set[str],
    active_model: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Build the next sidecar index from prior state and current sweep results."""
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
                if (
                    existing_entry.get("content_hash") == body_hash
                    and existing_entry.get("embedding_model") == active_model
                ):
                    new_index[path] = existing_entry
                else:
                    new_index[path] = stale_entry(
                        existing_entry,
                        rest=rest,
                        active_model=active_model,
                    )
                continue

            if (
                existing_entry.get("content_hash") == body_hash
                and existing_entry.get("embedding_model") == active_model
            ):
                new_index[path] = existing_entry
            else:
                new_index[path] = fresh_entry(rest, embeddings[idx], active_model)

        return new_index, errors

    for path, _fm, rest, _cls in survivors:
        body_hash = content_hash(rest)
        existing_entry = existing_index.get(path, {})
        if (
            existing_entry.get("content_hash") == body_hash
            and existing_entry.get("embedding_model") == active_model
        ):
            new_index[path] = existing_entry
        else:
            new_index[path] = stale_entry(
                existing_entry,
                rest=rest,
                active_model=active_model,
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
