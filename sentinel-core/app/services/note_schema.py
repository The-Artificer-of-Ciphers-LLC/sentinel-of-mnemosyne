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

# Structural claim-title check: any Markdown H1 line, anywhere in the body.
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

# Wikilink target extraction -- excludes the alias/heading-anchor portion
# of [[Target|Alias]] / [[Target#Heading]]; mirrors graph_analysis.py's
# extract_wikilinks (Plan 45-03) so both modules agree on wikilink shape.
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


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


def parse_schema_block(body: str) -> dict | None:
    """Parse the trailing ```_schema fenced block.

    Returns the parsed dict for a well-formed terminal block. Returns
    None when the block is absent, not the terminal content of the body,
    non-dict, or when the inner YAML fails to parse for any reason --
    this function never raises (T-45-DOS1).
    """
    stripped = (body or "").rstrip()
    match = _find_trailing_block_match(stripped)
    if match is None:
        return None
    try:
        parsed = yaml.safe_load(match.group(1))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def split_schema_block(body: str) -> tuple[str, str | None]:
    """Split ``body`` into ``(pre_block_body, raw_block_text_or_None)``.

    ``pre_block_body`` preserves all content before the trailing block
    byte-for-byte. When no terminal block is present, returns
    ``(body, None)`` unchanged. Callers mutate ``pre_block_body`` and
    re-append ``raw_block_text`` unchanged to preserve the block -- never
    ``patch_append`` a hub note blindly (RESEARCH Pitfall 1). This is the
    exact seam Plan 45-05's ``attach_to_hub`` depends on.
    """
    body = body or ""
    stripped = body.rstrip()
    match = _find_trailing_block_match(stripped)
    if match is None:
        return body, None
    return body[: match.start()], match.group(0)


def has_claim_title(body: str, filename_slug: str) -> bool:
    """D-05 structural-only claim-title check -- zero LLM calls.

    True when an H1 line exists, its normalized text differs from the
    normalized filename slug, and the title has more than one word.
    Deliberately narrow: this does not judge whether the title is
    genuinely claim-shaped (a topic label like "Notes on X" passes) --
    that nuance is out of scope for this cheap, deterministic check and
    is left to a future, separately-gated, opt-in pass with different
    tooling than this structural check.
    """
    match = _H1_RE.search(body or "")
    if not match:
        return False
    title = match.group(1).strip()
    normalized = title.lower().replace(" ", "-").replace("_", "-")
    bare_slug = (filename_slug or "").lower().replace("_", "-")
    return normalized != bare_slug and len(title.split()) > 1


def has_wikilink(body: str) -> bool:
    """True when at least one wikilink target is present in ``body``."""
    return _WIKILINK_RE.search(body or "") is not None


def check_note_compliance(body: str, filename_slug: str) -> dict:
    """Aggregate per-note NOTE-01 compliance into a deterministic report.

    Never raises -- any internal error is caught and recorded as a FAIL
    entry rather than propagating (T-45-DOS1). Makes zero network/LLM/
    embedding calls (T-45-DET / D-05).
    """
    result: dict = {
        "has_schema": False,
        "has_type": False,
        "has_claim_title": False,
        "has_wikilink": False,
        "failures": [],
    }
    try:
        schema = parse_schema_block(body)
        result["has_schema"] = schema is not None
        if not result["has_schema"]:
            result["failures"].append("missing _schema block")

        result["has_type"] = schema is not None and "type" in schema
        if result["has_schema"] and not result["has_type"]:
            result["failures"].append("missing type key in _schema block")

        result["has_claim_title"] = has_claim_title(body, filename_slug)
        if not result["has_claim_title"]:
            result["failures"].append("missing claim-style title")

        result["has_wikilink"] = has_wikilink(body)
        if not result["has_wikilink"]:
            result["failures"].append("missing wikilink")
    except Exception as exc:  # pragma: no cover - defensive, never expected
        result["failures"].append(f"compliance check error: {exc}")
    return result
