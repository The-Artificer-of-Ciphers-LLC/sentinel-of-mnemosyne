"""Trailing ```_schema fenced-block parser + structural note-quality checks.

Distinct from ``markdown_frontmatter.py``, which owns the LEADING YAML
provenance frontmatter block anchored at the start of the body
(``^---\\s*\\n(.*?)\\n---\\s*\\n?``). This module owns ONLY the trailing
fenced ```_schema block at the END of the note body (D-01) -- it never
parses leading frontmatter and the two blocks are kept strictly disjoint.

The trailing block must be the terminal content of the (rstripped) body: a
stray earlier fenced block sharing the same ```_schema info-string never
wins over the real terminal block (RESEARCH Pattern 1 / multiple same-tag
fenced blocks in one note body).

This module is a pure content parser with no I/O of its own, and makes
zero network/LLM/embedding calls (D-05, T-45-DET) -- see
``test_note_schema_module_has_no_llm_or_network_imports`` for the
enforced determinism gate.
"""
from __future__ import annotations

import re

import yaml

# Self-contained (non-greedy) fenced ```_schema block -- stops at the
# NEAREST closing fence, so multiple such blocks in one body are found as
# separate, non-overlapping matches rather than one match spanning both
# (which a single \\Z-anchored, non-greedy pattern would otherwise do via
# backtracking -- see RESEARCH Pattern 1's trade-offs discussion).
_SCHEMA_BLOCK_RE = re.compile(r"```_schema\s*\n(.*?)\n```", re.DOTALL)


def _find_trailing_block_match(stripped: str) -> re.Match | None:
    """Return the terminal ```_schema block match, or None if absent.

    Scans all non-overlapping ```_schema...``` blocks in ``stripped`` and
    returns the LAST one only if it ends exactly at the end of
    ``stripped`` -- i.e. it is genuinely the terminal content of the body,
    not merely the last block textually followed by trailing prose. This
    is what keeps an earlier same-tag block from ever winning.
    """
    matches = list(_SCHEMA_BLOCK_RE.finditer(stripped))
    if not matches:
        return None
    last = matches[-1]
    if last.end() != len(stripped):
        return None
    return last


def parse_schema_block(body: str) -> dict | None:  # pragma: no cover - RED stub
    """Parse the trailing ```_schema fenced block. Implemented in GREEN step."""
    raise NotImplementedError


def split_schema_block(body: str) -> tuple[str, str | None]:  # pragma: no cover - RED stub
    """Split body into (pre_block_body, raw_block_text_or_None). GREEN step."""
    raise NotImplementedError
