"""Behavioral tests for sentinel_shared.similarity."""
from __future__ import annotations

import numpy as np

from sentinel_shared.similarity import cosine_similarity, find_dup_clusters


def test_cosine_similarity_1d_returns_float():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    out = cosine_similarity(a, b)
    assert isinstance(out, float)
    assert out == 1.0

    c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, c) == 0.0


def test_cosine_similarity_2d_returns_ndarray_shape():
    matrix = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    sims = cosine_similarity(matrix, vec)
    assert isinstance(sims, np.ndarray)
    assert sims.shape == (3,)
    np.testing.assert_allclose(sims[0], 1.0, atol=1e-6)
    np.testing.assert_allclose(sims[1], 0.0, atol=1e-6)
    # cos(45deg) = 1/sqrt(2)
    np.testing.assert_allclose(sims[2], 1.0 / np.sqrt(2.0), atol=1e-6)


def test_cosine_similarity_zero_norm_returns_zero_1d():
    a = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    out = cosine_similarity(a, b)
    assert out == 0.0
    assert not np.isnan(out)


def test_cosine_similarity_zero_norm_returns_zero_2d():
    matrix = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float32
    )
    vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    sims = cosine_similarity(matrix, vec)
    assert sims[0] == 0.0
    assert sims[1] == 1.0
    assert not np.any(np.isnan(sims))

    # zero-norm vec
    vec0 = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    sims0 = cosine_similarity(matrix, vec0)
    np.testing.assert_array_equal(sims0, np.zeros(2, dtype=np.float32))


def test_find_dup_clusters_detects_pairs_above_threshold():
    matrix = np.array(
        [
            [1.0, 0.0, 0.0],
            [1.0, 0.01, 0.0],   # near-dup of row 0
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )
    clusters = find_dup_clusters(matrix, threshold=0.92)
    assert clusters == [[0, 1]]


def test_find_dup_clusters_empty_or_singleton_returns_empty():
    assert find_dup_clusters(np.zeros((0, 3), dtype=np.float32)) == []
    assert find_dup_clusters(np.array([[1.0, 0.0]], dtype=np.float32)) == []
