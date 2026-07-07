"""Vault-wide backlink scan for the Phase 47 migration cutover.

A deliberately standalone, ``ops/``-inclusive title-reference counter that
closes the gap ``graph_analysis``/``links_sidecar_index`` structurally
cannot cover: both are ``notes/``-scoped by design (they only ever walk
``NOTES_ROOT``) and must NOT be widened to also cover ``ops/``. This module
is a small, independent helper instead -- one function, no state, no side
effects.
"""
from __future__ import annotations

from typing import Any


async def scan_for_title_refs(vault: Any, title: str) -> int:
    """Return the vault-wide count of notes containing a ``[[title]]`` reference.

    Calls the vault's keyword search (``vault.find()``, ``POST
    /search/simple/``) for the exact wikilink text, covering the whole
    vault -- including ``ops/`` -- unlike ``graph_analysis``/
    ``links_sidecar_index``, which only ever walk ``notes/``.

    The caller diffs a pre-move count against a post-move count: an
    unchanged count means title-based resolution held; a drop signals a
    broken/dangling reference to rewrite, or a rollback trigger.
    """
    hits = await vault.find(f"[[{title}]]")
    return len(hits)
