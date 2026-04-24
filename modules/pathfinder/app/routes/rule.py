"""POST /rule/query — PF2e Remaster rules RAG engine (RUL-01..04, D-02..D-14).

Module-level singletons (obsidian, rules_index, aon_url_map) are assigned by
main.py lifespan. Tests patch them at
app.routes.rule.{obsidian, rules_index, aon_url_map,
                 embed_texts, classify_rule_topic,
                 generate_ruling_from_passages, generate_ruling_fallback}.

Shape mirrors app.routes.harvest (PATTERNS.md §1 routes/rule.py):
- Pydantic request/response models with input sanitiser (_validate_rule_query)
- 9-step orchestration in rule_query: PF1-check -> topic-classify -> exact-hash cache ->
  embed -> retrieve -> reuse-match scan -> compose (passages or fallback) -> cache-write
- Obsidian GET-then-PUT via build_ruling_markdown (D-03b / L-3 — NEVER the surgical
  single-field PATCH helper on the Obsidian client)
- LLM failure -> 500 WITHOUT cache write; cache PUT failure -> log + degrade (still return result)
- last_reused_at updated on EVERY cache / reuse hit (D-14) via GET-then-PUT

Per CLAUDE.md AI Deferral Ban: every helper completes its job; no TODO/pass/NotImplementedError.
Per project_obsidian_patch_constraint memory: ZERO surgical-PATCH-against-new-fields references
in this file — enforced by grep gate. All writes are full-body PUT on the cached markdown.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import logging
import re

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.rules import (
    MAX_QUERY_CHARS,
    RulesIndex,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rule", tags=["rule"])

# Module-level singletons — set by main.py lifespan, patchable in tests.
obsidian = None  # type: ignore[assignment]           # ObsidianClient after lifespan
rules_index: RulesIndex | None = None
aon_url_map: dict | None = None


# --- Input sanitiser (L-8 — mirrors _validate_monster_name) ---


def _validate_rule_query(v: str) -> str:
    """Reject empty / overlong / control-char / injection-suspect queries.

    Rules:
      - Must be a non-empty str after strip().
      - Must not exceed MAX_QUERY_CHARS (DoS cap — 500 chars).
      - Must not contain ASCII control characters except \\n and \\t (which are
        legitimate in free-form query text).
      - Must contain at least one non-markup character (rejects all-backtick or
        all-code-fence input, a common prompt-injection vector).
      - Unicode is accepted (sha1-based hash handles any bytes).
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
    # Reject ASCII control chars except \n and \t (legitimate in free-form text).
    if re.search(r"[\x00-\x08\x0b-\x1f\x7f]", v):
        raise ValueError("rule query contains invalid control characters")
    # L-8: a query consisting purely of backticks / code-fence markers is an injection attempt.
    if re.fullmatch(r"[`~\s]+", v):
        raise ValueError("rule query must contain non-markup characters")
    return v


# --- Pydantic request + response models ---


class RuleQueryRequest(BaseModel):
    query: str
    user_id: str = ""

    @field_validator("query")
    @classmethod
    def _sanitize(cls, v: str) -> str:
        return _validate_rule_query(v)


class RuleShowRequest(BaseModel):
    topic: str


class RuleHistoryRequest(BaseModel):
    n: int = 10

    @field_validator("n")
    @classmethod
    def _clamp_n(cls, v: int) -> int:
        if v < 1:
            return 1
        if v > 100:
            return 100
        return v


class RuleCitation(BaseModel):
    book: str
    section: str
    page: str | None = None
    url: str | None = None


class RuleRulingOut(BaseModel):
    question: str
    answer: str
    why: str
    source: str | None
    citations: list[RuleCitation] = Field(default_factory=list)
    marker: str  # "source" | "generated" | "declined"
    topic: str | None
    reused: bool = False
    reuse_note: str = ""


# --- Helpers (timestamp, base64, internal-field stripper) ---


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 with Z suffix (matches build_ruling_markdown)."""
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def _embedding_hash(model: str) -> str:
    return hashlib.sha1(model.encode("utf-8")).hexdigest()


def _encode_query_embedding(vec) -> str:
    """base64-encode a float32 LE byte array (D-13)."""
    arr = np.asarray(vec, dtype=np.float32)
    return base64.b64encode(arr.tobytes()).decode("ascii")


def _decode_query_embedding(b64: str) -> np.ndarray:
    """Decode a base64 float32 LE byte array back into a numpy float32 array."""
    raw = base64.b64decode(b64)
    return np.frombuffer(raw, dtype=np.float32).copy()


def _strip_internal_fields(result: dict) -> dict:
    """Return only the D-08 + reuse keys for the HTTP response.

    Hides frontmatter-internal fields (query_embedding, embedding_hash,
    embedding_model, composed_at, last_reused_at, verified) from callers.
    last_reused_at is a frontmatter-only concern per D-14.
    """
    internal = {
        "query_embedding",
        "embedding_hash",
        "embedding_model",
        "composed_at",
        "last_reused_at",
        "verified",
    }
    return {k: v for k, v in result.items() if k not in internal}


# --- Endpoint stubs — real implementations in 33-04-02..05 ---


@router.post("/query")
async def rule_query(req: RuleQueryRequest) -> JSONResponse:
    """RUL-01..04 core — 9-step orchestration (see 33-04-02)."""
    raise HTTPException(status_code=501, detail={"error": "rule_query not yet implemented — 33-04-02"})


@router.post("/show")
async def rule_show(req: RuleShowRequest) -> JSONResponse:
    """List rulings under a given topic folder (see 33-04-03)."""
    raise HTTPException(status_code=501, detail={"error": "rule_show not yet implemented — 33-04-03"})


@router.post("/history")
async def rule_history(req: RuleHistoryRequest) -> JSONResponse:
    """Top-N most-recent rulings across all topics by last_reused_at (see 33-04-04)."""
    raise HTTPException(status_code=501, detail={"error": "rule_history not yet implemented — 33-04-04"})


@router.post("/list")
async def rule_list() -> JSONResponse:
    """Enumerate topic folders currently under RULING_CACHE_PATH_PREFIX (see 33-04-05)."""
    raise HTTPException(status_code=501, detail={"error": "rule_list not yet implemented — 33-04-05"})
