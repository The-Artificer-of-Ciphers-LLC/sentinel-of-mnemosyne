"""Cosine similarity + duplicate clustering — cross-package SPOT.

Closes the cross-package SPOT violation between sentinel-core's
``vault_sweeper.cosine_similarity(a, b) -> float`` (vec×vec) and
pathfinder's ``rules.cosine_similarity(matrix, vec) -> ndarray``
(matrix×vec). Q1-a: overload via ``np.atleast_2d``; collapse to float
when both inputs were 1D.
"""
from __future__ import annotations

import numpy as np


def cosine_similarity(
    a: np.ndarray | list, b: np.ndarray | list
) -> float | np.ndarray:
    """Cosine similarity, overloaded.

    - 1D × 1D → ``float`` (vec×vec, sentinel-core semantics).
    - 2D × 1D → ``ndarray`` of shape ``(N,)`` (pathfinder semantics:
      every row of ``a`` against ``b``).
    - 2D × 2D → ``ndarray`` of shape ``(N, M)``.

    Zero-norm rows / vectors yield 0.0 (not NaN).
    """
    av_in = np.asarray(a, dtype=np.float32)
    bv_in = np.asarray(b, dtype=np.float32)
    a_was_1d = av_in.ndim == 1
    b_was_1d = bv_in.ndim == 1

    av = np.atleast_2d(av_in)  # (N, D)
    bv = np.atleast_2d(bv_in)  # (M, D) — for vec b, shape is (1, D)

    a_norms = np.linalg.norm(av, axis=1, keepdims=True)  # (N, 1)
    b_norms = np.linalg.norm(bv, axis=1, keepdims=True)  # (M, 1)

    # Replace zero norms with 1.0 to avoid divide-by-zero; numerator is 0
    # for zero-norm rows so the resulting similarity is correctly 0.
    safe_a = np.where(a_norms == 0.0, 1.0, a_norms)
    safe_b = np.where(b_norms == 0.0, 1.0, b_norms)

    dots = av @ bv.T  # (N, M)
    sims = dots / (safe_a * safe_b.T)

    # Force exact-zero on zero-norm rows/cols (the np.where above only
    # protected the divisor; the dot is already 0 in float math but be
    # explicit).
    sims = np.where(a_norms == 0.0, 0.0, sims)
    sims = np.where(b_norms.T == 0.0, 0.0, sims)

    if a_was_1d and b_was_1d:
        return float(sims[0, 0])
    if b_was_1d:
        # (N, 1) → (N,) — matches pathfinder's matrix×vec contract.
        return sims[:, 0].astype(np.float32)
    if a_was_1d:
        return sims[0, :].astype(np.float32)
    return sims.astype(np.float32)


def find_dup_clusters(
    matrix: np.ndarray, threshold: float = 0.92
) -> list[list[int]]:
    """Connected-components on cosine ≥ threshold pairs. Returns groups of 2+ indices."""
    if matrix is None or matrix.size == 0:
        return []
    n = matrix.shape[0]
    if n < 2:
        return []

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe = np.where(norms == 0.0, 1.0, norms)
    sim = (matrix @ matrix.T) / (safe * safe.T)
    np.fill_diagonal(sim, 0.0)

    visited: set[int] = set()
    clusters: list[list[int]] = []
    for i in range(n):
        if i in visited:
            continue
        cluster = [i]
        stack = [i]
        visited.add(i)
        while stack:
            j = stack.pop()
            for k in np.where(sim[j] >= threshold)[0]:
                k_int = int(k)
                if k_int not in visited:
                    visited.add(k_int)
                    cluster.append(k_int)
                    stack.append(k_int)
        if len(cluster) > 1:
            clusters.append(sorted(cluster))
    return clusters
