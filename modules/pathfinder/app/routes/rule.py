"""Rule query route — Wave 1 skeleton (sanitiser only).

Wave 3 (Plan 33-04) fills in the FastAPI router, Pydantic models, lifespan
singleton wiring, and the full D-02 retrieval flow. This Wave 1 skeleton ships
just the input sanitiser so the Wave-0 RED unit stubs for MAX_QUERY_CHARS and
unicode handling flip GREEN at the same time as the pure-transform module.

Per CLAUDE.md AI Deferral Ban: the sanitiser is a real implementation — not a
stub. Wave 3 will ADD to this file; it will not replace the helpers below.
"""
from __future__ import annotations

import re

from app.rules import MAX_QUERY_CHARS


# --- Input sanitiser (mirrors _validate_monster_name from routes/harvest.py) ---


def _validate_rule_query(v: str) -> str:
    """Validate and normalize a rule-query string.

    Rules:
      - Must be a non-empty str after strip().
      - Must not exceed MAX_QUERY_CHARS (DoS cap — 500 chars).
      - Must not contain ASCII control characters (\\x00-\\x1f, \\x7f).
      - Unicode (e.g., "测试 rules") is accepted — sha1-based hash handles any bytes.
    """
    if not isinstance(v, str):
        raise ValueError("rule query must be a string")
    v = v.strip()
    if not v:
        raise ValueError("rule query cannot be empty")
    if len(v) > MAX_QUERY_CHARS:
        raise ValueError(
            f"rule query too long (max {MAX_QUERY_CHARS} chars, got {len(v)})"
        )
    if re.search(r"[\x00-\x1f\x7f]", v):
        raise ValueError("rule query contains invalid control characters")
    return v
