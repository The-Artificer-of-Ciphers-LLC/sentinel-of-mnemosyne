"""PF2e Remaster rules endpoints.

Module-level singletons (obsidian, rules_index, aon_url_map) are assigned by
main.py lifespan. Tests patch them at
app.routes.rule.{obsidian, rules_index, aon_url_map,
                 embed_texts, classify_rule_topic,
                 generate_ruling_from_passages, generate_ruling_fallback}.

The deep Rule Query implementation lives in app.rule_query. This route module
stays as the HTTP adapter: request validation, dependency handoff, HTTP
exception mapping, and enumeration endpoints.

Per CLAUDE.md AI Deferral Ban: every helper completes its job; no TODO/pass/NotImplementedError.
Per project_obsidian_patch_constraint memory: ZERO surgical-PATCH-against-new-fields references
in this file — enforced by grep gate. All writes are full-body PUT on the cached markdown.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.llm import (
    classify_rule_topic,
    embed_texts,
    generate_ruling_fallback,
    generate_ruling_from_passages,
)
from app.resolve_model import resolve
from app.rule_cache_catalog import RuleCacheCatalog
from app.rule_query import (
    RuleQueryCompositionError,
    RuleQueryDependencies,
    RuleQueryEmbeddingError,
    RuleQueryNotInitialized,
    execute_rule_query,
)
from app.rules import (
    MAX_QUERY_CHARS,
    RulesIndex,
    keyword_classify_topic,
)

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

    @field_validator("topic")
    @classmethod
    def _sanitize_topic(cls, v: str) -> str:
        """Reject empty / overlong / control-char topic input (WR-03).

        coerce_topic downstream collapses unknown slugs to 'misc', but that
        happens AFTER Pydantic has copied a potentially huge / malformed
        string through memory. Bound the input here like _validate_rule_query
        does for query text.
        """
        if not isinstance(v, str):
            raise ValueError("topic must be a string")
        v = v.strip()
        if not v:
            raise ValueError("topic cannot be empty")
        if len(v) > 64:
            raise ValueError(f"topic too long (max 64 chars, got {len(v)})")
        if re.search(r"[\x00-\x08\x0b-\x1f\x7f]", v):
            raise ValueError("topic contains invalid control characters")
        return v


class RuleHistoryRequest(BaseModel):
    n: int = 10

    @field_validator("n")
    @classmethod
    def _clamp_n(cls, v: int) -> int:
        # IN-03: align backend cap with RESEARCH §History Count (N=50). Bot
        # layer pre-clamps to 50; this is belt-and-suspenders for direct
        # API callers that bypass the bot.
        if v < 1:
            return 1
        if v > 50:
            return 50
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


@router.post("/query")
async def rule_query(req: RuleQueryRequest) -> JSONResponse:
    """Rule Query HTTP adapter."""
    try:
        result = await execute_rule_query(
            query=req.query,
            user_id=req.user_id,
            deps=RuleQueryDependencies(
                obsidian=obsidian,
                rules_index=rules_index,  # type: ignore[arg-type]
                aon_url_map=aon_url_map,  # type: ignore[arg-type]
                settings=settings,
                resolve_model=resolve,
                keyword_classify_topic=keyword_classify_topic,
                classify_rule_topic=classify_rule_topic,
                embed_texts=embed_texts,
                generate_ruling_from_passages=generate_ruling_from_passages,
                generate_ruling_fallback=generate_ruling_fallback,
            ),
        )
    except RuleQueryNotInitialized:
        raise HTTPException(
            status_code=503,
            detail={"error": "rule subsystem not initialised (lifespan incomplete?)"},
        )
    except RuleQueryEmbeddingError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "embedding failed", "detail": str(exc)},
        )
    except RuleQueryCompositionError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "LLM ruling composition failed", "detail": str(exc)},
        )
    return JSONResponse(result)


# --- Enumeration endpoints — no LLM, no embedding, pure Obsidian directory walks ---


@router.post("/show")
async def rule_show(req: RuleShowRequest) -> JSONResponse:
    """List rulings under a given topic folder. Sorted by last_reused_at desc."""
    if obsidian is None:
        raise HTTPException(
            status_code=503, detail={"error": "rule subsystem not initialised"}
        )
    return JSONResponse(await RuleCacheCatalog(obsidian).show_topic(req.topic))


@router.post("/history")
async def rule_history(req: RuleHistoryRequest) -> JSONResponse:
    """Top-N most-recent rulings across ALL topics by last_reused_at (D-14)."""
    if obsidian is None:
        raise HTTPException(
            status_code=503, detail={"error": "rule subsystem not initialised"}
        )
    return JSONResponse(await RuleCacheCatalog(obsidian).history(req.n))


@router.post("/list")
async def rule_list() -> JSONResponse:
    """Enumerate topic folders and their activity. Sorted by last_activity desc."""
    if obsidian is None:
        raise HTTPException(
            status_code=503, detail={"error": "rule subsystem not initialised"}
        )
    return JSONResponse(await RuleCacheCatalog(obsidian).topics())
