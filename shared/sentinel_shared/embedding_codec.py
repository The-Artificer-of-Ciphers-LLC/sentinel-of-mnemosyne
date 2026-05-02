"""Embedding (de)serialization — single source of truth across packages.

base64-encoded float32 little-endian byte arrays. Used by
sentinel-core's vault sweeper and pathfinder's rule-cache for
durable embedding storage in Obsidian frontmatter.

Verbatim semantics from the prior copies in
``sentinel-core/app/services/vault_sweeper.py`` and
``modules/pathfinder/app/rules.py``. Q4-b: ``decode_embedding`` returns
``list[float]``; ndarray-shaped consumers wrap at the call site.
"""
from __future__ import annotations

import base64
import logging

import numpy as np

logger = logging.getLogger(__name__)


def encode_embedding(vec: list[float] | np.ndarray | str) -> str:
    """base64-encode a list[float] or np.ndarray as float32 little-endian bytes.

    Pass-through for already-encoded base64 strings (caller provided cached
    representation).
    """
    if isinstance(vec, str):
        return vec
    arr = np.asarray(vec, dtype=np.float32)
    return base64.b64encode(arr.tobytes()).decode("ascii")


def decode_embedding(s: str | list | np.ndarray) -> list[float]:
    """Decode base64 embedding back to ``list[float]``.

    Accepts already-decoded list/ndarray inputs (returned as list[float]).
    Empty string and decode failure return ``[]`` (logged at WARNING).
    """
    if isinstance(s, list):
        return [float(x) for x in s]
    if isinstance(s, np.ndarray):
        return s.astype(np.float32).tolist()
    if isinstance(s, str):
        if not s:
            return []
        try:
            raw = base64.b64decode(s.encode("ascii"))
            return np.frombuffer(raw, dtype=np.float32).tolist()
        except Exception as exc:
            logger.warning("Failed to decode embedding base64: %s", exc)
            return []
    return []
