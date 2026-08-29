"""Tests for the Embedding sidecar index module."""
from __future__ import annotations

import json

import numpy as np

from app.services.embedding_sidecar_index import (
    EMBEDDING_INDEX_PATH,
    build_embedding_index,
    content_hash,
    decode_index_body,
    eligible_entries,
    encode_index_body,
)
from sentinel_shared.embedding_codec import encode_embedding


def test_encode_index_body_json_extension_returns_raw_json():
    idx = {"notes/a.md": {"embedding_b64": "abc", "embedding_model": "m", "content_hash": "h"}}
    body = encode_index_body(idx, "ops/sweeps/embedding-index.json")
    assert json.loads(body) == idx
    assert "```" not in body


def test_encode_index_body_md_extension_returns_fenced_json():
    idx = {"notes/b.md": {"embedding_b64": "xyz", "embedding_model": "m", "content_hash": "h2"}}
    body = encode_index_body(idx, "ops/sweeps/embedding-index.md")
    assert "```" in body
    try:
        json.loads(body)
        assert False, ".md body must be fenced, not raw JSON"
    except json.JSONDecodeError:
        pass


def test_encode_index_body_md_uppercase_extension_still_fences():
    idx = {"notes/c.md": {"embedding_b64": "q", "embedding_model": "m", "content_hash": "h3"}}
    body = encode_index_body(idx, "ops/sweeps/embedding-index.MD")
    assert "```" in body


def test_encode_index_body_json_uppercase_extension_returns_raw():
    idx = {"notes/d.md": {"embedding_b64": "r", "embedding_model": "m", "content_hash": "h4"}}
    body = encode_index_body(idx, "ops/sweeps/embedding-index.JSON")
    assert json.loads(body) == idx
    assert "```" not in body


def test_decode_index_body_json_extension_parses_raw_json():
    idx = {"notes/a.md": {"embedding_b64": "abc", "embedding_model": "m", "content_hash": "h"}}
    raw = json.dumps(idx, ensure_ascii=False)
    assert decode_index_body(raw, "ops/sweeps/embedding-index.json") == idx


def test_decode_index_body_md_extension_strips_fence_and_parses():
    idx = {"notes/b.md": {"embedding_b64": "xyz", "embedding_model": "m", "content_hash": "h2"}}
    inner = json.dumps(idx, ensure_ascii=False)
    fenced = f"```json\n{inner}\n```\n"
    assert decode_index_body(fenced, "ops/sweeps/embedding-index.md") == idx


def test_decode_index_body_md_uppercase_extension_strips_fence():
    idx = {"notes/c.md": {"embedding_b64": "q", "embedding_model": "m", "content_hash": "h3"}}
    inner = json.dumps(idx, ensure_ascii=False)
    fenced = f"```json\n{inner}\n```\n"
    assert decode_index_body(fenced, "ops/sweeps/embedding-index.MD") == idx


def test_decode_index_body_md_no_fence_returns_empty():
    result = decode_index_body("# This is a note\n\nSome content here.\n", "notes/no-json.md")
    assert result == {}


def test_decode_index_body_md_no_fence_no_crash():
    result = decode_index_body("```\nnot json at all\n```\n", "ops/sweeps/embedding-index.md")
    assert result == {}


def test_json_extension_round_trip_write_read():
    idx = {
        "notes/alpha.md": {
            "embedding_b64": "AACAPw==",
            "embedding_model": "m",
            "content_hash": "c1",
        },
        "notes/beta.md": {
            "embedding_b64": "AAAAQD8=",
            "embedding_model": "m",
            "content_hash": "c2",
        },
    }
    path = "ops/sweeps/embedding-index.json"
    assert decode_index_body(encode_index_body(idx, path), path) == idx


def test_md_extension_round_trip_write_read():
    idx = {
        "notes/alpha.md": {
            "embedding_b64": "AACAPw==",
            "embedding_model": "m",
            "content_hash": "c1",
        },
        "notes/beta.md": {
            "embedding_b64": "AAAAQD8=",
            "embedding_model": "m",
            "content_hash": "c2",
        },
    }
    path = "ops/sweeps/embedding-index.md"
    body = encode_index_body(idx, path)
    assert "```" in body
    assert decode_index_body(body, path) == idx


def test_md_uppercase_extension_round_trip():
    idx = {"notes/g.md": {"embedding_b64": "q", "embedding_model": "m", "content_hash": "h"}}
    path = "ops/sweeps/embedding-index.MD"
    body = encode_index_body(idx, path)
    assert "```" in body
    assert decode_index_body(body, path) == idx


def test_build_embedding_index_marks_changed_unembedded_entry_stale():
    old_entry = {
        "embedding_b64": encode_embedding([1.0, 0.0, 0.0]),
        "embedding_model": "model-a",
        "content_hash": content_hash("old body"),
    }

    index, errors = build_embedding_index(
        existing_index={"notes/a.md": old_entry},
        survivors=[("notes/a.md", {}, "new body", object())],
        embeddings=None,
        active_paths={"notes/a.md"},
        active_model="model-a",
    )

    assert errors == []
    assert index["notes/a.md"]["content_hash"] == content_hash("new body")
    assert index["notes/a.md"]["embedding_b64"] == old_entry["embedding_b64"]
    assert index["notes/a.md"]["stale"] is True


def test_stale_entry_heals_when_fresh_vector_available():
    """Regression for the 2026-08-29 never-heal incident: a stale entry
    (no embedding_b64) whose content_hash and embedding_model both still
    match the note must be replaced with a fresh entry once a fresh vector
    is available in this sweep, not carried forward unhealed forever."""
    body = "unchanged body"
    stale = {
        "embedding_b64": "",
        "embedding_model": "model-a",
        "content_hash": content_hash(body),
        "stale": True,
    }

    index, errors = build_embedding_index(
        existing_index={"notes/a.md": stale},
        survivors=[("notes/a.md", {}, body, object())],
        embeddings=[[1.0, 0.0, 0.0]],
        active_paths={"notes/a.md"},
        active_model="model-a",
    )

    assert errors == []
    entry = index["notes/a.md"]
    assert entry.get("embedding_b64")
    assert not entry.get("stale")


def test_healthy_matching_entry_is_carried_forward_unchanged():
    """A non-stale entry with matching content_hash and model is reused
    as-is — no needless re-embed churn for notes that haven't changed."""
    body = "unchanged body"
    healthy = {
        "embedding_b64": encode_embedding([1.0, 0.0, 0.0]),
        "embedding_model": "model-a",
        "content_hash": content_hash(body),
    }

    index, errors = build_embedding_index(
        existing_index={"notes/a.md": healthy},
        survivors=[("notes/a.md", {}, body, object())],
        embeddings=[[9.0, 9.0, 9.0]],
        active_paths={"notes/a.md"},
        active_model="model-a",
    )

    assert errors == []
    assert index["notes/a.md"] is healthy


def test_changed_body_still_gets_fresh_entry():
    """A note whose content changed always gets a fresh entry, regardless
    of the prior entry's staleness."""
    old_entry = {
        "embedding_b64": encode_embedding([1.0, 0.0, 0.0]),
        "embedding_model": "model-a",
        "content_hash": content_hash("old body"),
    }

    index, errors = build_embedding_index(
        existing_index={"notes/a.md": old_entry},
        survivors=[("notes/a.md", {}, "new body", object())],
        embeddings=[[2.0, 0.0, 0.0]],
        active_paths={"notes/a.md"},
        active_model="model-a",
    )

    assert errors == []
    entry = index["notes/a.md"]
    assert entry["content_hash"] == content_hash("new body")
    assert not entry.get("stale")
    assert entry["embedding_b64"] != old_entry["embedding_b64"]


def test_no_embeddings_no_usable_entry_yields_stale_without_persisting_hash_as_embedded():
    """Invariant: with no embeddings available at all, a note with no
    usable stored entry still yields a stale entry — content_hash is
    persisted, but never as though the note were actually embedded."""
    body = "some body"

    index, errors = build_embedding_index(
        existing_index={},
        survivors=[("notes/a.md", {}, body, object())],
        embeddings=None,
        active_paths={"notes/a.md"},
        active_model="model-a",
    )

    assert errors == []
    entry = index["notes/a.md"]
    assert entry["content_hash"] == content_hash(body)
    assert entry["stale"] is True
    assert not entry.get("embedding_b64")


def test_build_embedding_index_prunes_inactive_paths():
    index, errors = build_embedding_index(
        existing_index={
            "notes/active.md": {"embedding_b64": "a", "embedding_model": "m", "content_hash": "h"},
            "notes/gone.md": {"embedding_b64": "b", "embedding_model": "m", "content_hash": "h"},
        },
        survivors=[],
        embeddings=[],
        active_paths={"notes/active.md"},
        active_model="m",
    )

    assert errors == []
    assert "notes/active.md" in index
    assert "notes/gone.md" not in index


def test_eligible_entries_skips_stale_model_and_dimension_mismatch():
    index = {
        "notes/good.md": {
            "embedding_b64": encode_embedding([1.0, 0.0, 0.0]),
            "embedding_model": "m",
            "content_hash": "h1",
        },
        "notes/stale.md": {
            "embedding_b64": encode_embedding([1.0, 0.0, 0.0]),
            "embedding_model": "m",
            "content_hash": "h2",
            "stale": True,
        },
        "notes/wrong-model.md": {
            "embedding_b64": encode_embedding([1.0, 0.0, 0.0]),
            "embedding_model": "other",
            "content_hash": "h3",
        },
        "notes/wrong-dim.md": {
            "embedding_b64": encode_embedding([1.0, 0.0]),
            "embedding_model": "m",
            "content_hash": "h4",
        },
    }

    entries, matched_model_count = eligible_entries(
        index,
        active_model="m",
        exclude_prefixes=("ops/", "_trash/", "self/"),
        query_dim=3,
    )

    assert [entry.path for entry in entries] == ["notes/good.md"]
    assert np.array_equal(entries[0].vector, np.asarray([1.0, 0.0, 0.0], dtype=np.float32))
    assert matched_model_count == 2


def test_eligible_entries_skips_same_model_different_persisted_dim_cutover_case():
    """D-08 cutover case (EMB-04): an entry whose embedding_model string
    MATCHES the active model but whose PERSISTED embedding_dim differs from
    the live query dimension (e.g. same nomic model name, truncated
    Matryoshka dim after an LM Studio cutover) must be skipped by the
    dimension guard even though the MEM-05 model-string check alone would
    pass it through. This must be caught BEFORE the vector is decoded.
    """
    index = {
        "notes/same-model-diff-dim.md": {
            # Decoded length (3) intentionally matches query_dim so that,
            # absent the persisted-dim fast path, the decode-time check
            # would wrongly admit this entry. The persisted embedding_dim
            # (768) is what must trigger the skip.
            "embedding_b64": encode_embedding([1.0, 0.0, 0.0]),
            "embedding_model": "m",
            "content_hash": "hcut",
            "embedding_dim": 768,
        },
    }

    entries, matched_model_count = eligible_entries(
        index,
        active_model="m",
        exclude_prefixes=("ops/", "_trash/", "self/"),
        query_dim=3,
    )

    assert entries == []
    # Model string matched, so it still counts toward matched_model_count —
    # the dimension guard is a separate, later check.
    assert matched_model_count == 1


def test_eligible_entries_no_embedding_dim_field_falls_back_to_decode_check():
    """An entry with no persisted `embedding_dim` field must still be
    skipped via the decode-time `len(raw) != query_dim` fallback — proving
    backward compatibility with pre-existing (pre-D-08) index entries.
    """
    index = {
        "notes/no-dim-field.md": {
            "embedding_b64": encode_embedding([1.0, 0.0]),  # decodes to dim 2
            "embedding_model": "m",
            "content_hash": "hnodim",
            # no "embedding_dim" key at all
        },
    }

    entries, matched_model_count = eligible_entries(
        index,
        active_model="m",
        exclude_prefixes=("ops/", "_trash/", "self/"),
        query_dim=3,
    )

    assert entries == []
    assert matched_model_count == 1


def test_eligible_entries_matching_model_and_persisted_dim_is_retained():
    """A matching-model, matching-persisted-dim entry is retained (positive
    control for the fast path added above)."""
    index = {
        "notes/matching.md": {
            "embedding_b64": encode_embedding([1.0, 0.0, 0.0]),
            "embedding_model": "m",
            "content_hash": "hmatch",
            "embedding_dim": 3,
        },
    }

    entries, matched_model_count = eligible_entries(
        index,
        active_model="m",
        exclude_prefixes=("ops/", "_trash/", "self/"),
        query_dim=3,
    )

    assert [entry.path for entry in entries] == ["notes/matching.md"]
    assert matched_model_count == 1


def test_embedding_index_path_constant():
    assert EMBEDDING_INDEX_PATH == "ops/sweeps/embedding-index.json"
