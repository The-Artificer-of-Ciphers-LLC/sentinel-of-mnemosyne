"""Markdown frontmatter parse/emit — single source of truth for sentinel-core.

Canonical helpers consolidating the prior triplicate copies in
``app/services/vault_sweeper.py`` (public ``split_frontmatter`` /
``join_frontmatter``), ``app/services/inbox.py`` (private
``_split_frontmatter`` / ``_join_frontmatter``), and ``app/vault.py``
(private versions with an empty-fm short-circuit).

The canonical ``join_frontmatter`` ALWAYS emits the frontmatter block —
matches the inbox.py/vault_sweeper.py semantics (the dominant pattern).
The vault.py copy used to short-circuit when fm was empty
(``if not fm: return rest``); audit at migration time confirmed every
vault.py call site passes a non-empty dict (sets ``original_path`` /
``topic_moved_at`` / ``started_at`` before calling), so the short-circuit
was dead code at the call sites and migrating to canonical behavior is
behavior-preserving for all live callers.
"""
from __future__ import annotations

import re

import yaml


# Module-private — the single SPOT for the frontmatter regex repo-wide.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def split_frontmatter(body: str) -> tuple[dict, str]:
    """Return ``(frontmatter_dict, body_without_frontmatter)``.

    Empty / missing / unparsable frontmatter → ``({}, body or "")``.
    """
    m = _FRONTMATTER_RE.match(body or "")
    if not m:
        return ({}, body or "")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception:
        fm = {}
    return (fm, body[m.end():])


def join_frontmatter(fm: dict, rest: str) -> str:
    """Emit ``---\\n<yaml>\\n---\\n\\n<rest>`` — always emits the block.

    Use ``split_frontmatter`` first if you want round-trip semantics on
    bodies that may have no frontmatter.
    """
    block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).strip()
    return f"---\n{block}\n---\n\n{rest.lstrip()}"
