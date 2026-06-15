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

import logging
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
from app.rule_query import (
    RuleQueryCompositionError,
    RuleQueryDependencies,
    RuleQueryEmbeddingError,
    RuleQueryNotInitialized,
    execute_rule_query,
)
from app.rules import (
    MAX_QUERY_CHARS,
    RULING_CACHE_PATH_PREFIX,
    RulesIndex,
    _parse_ruling_cache,
    coerce_topic,
    keyword_classify_topic,
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


def _build_ruling_index_entry(path: str, parsed: dict, topic: str | None = None) -> dict:
    """Extract the summary fields a UI / bot would list from a cached ruling."""
    # hash is the last path component without .md.
    hash_part = path.rsplit("/", 1)[-1].removesuffix(".md")
    return {
        "hash": hash_part,
        "topic": topic or parsed.get("topic"),
        "question": parsed.get("question", ""),
        "composed_at": parsed.get("composed_at", ""),
        "last_reused_at": parsed.get("last_reused_at", parsed.get("composed_at", "")),
        "marker": parsed.get("marker", ""),
        "source": parsed.get("source"),
    }


async def _collect_rulings_under(prefix: str) -> list[tuple[str, dict]]:
    """Walk a topic-prefix (or root rulings prefix), return list of (path, parsed_frontmatter)."""
    if obsidian is None:
        return []
    try:
        paths = await obsidian.list_directory(prefix)
    except Exception as exc:
        logger.warning("_collect_rulings_under: list_directory %s failed: %s", prefix, exc)
        return []
    out: list[tuple[str, dict]] = []
    for p in paths:
        if not p.endswith(".md"):
            continue
        text = await obsidian.get_note(p)
        if not text:
            continue
        parsed = _parse_ruling_cache(text)
        if parsed is None:
            logger.warning("_collect_rulings_under: malformed cache at %s — skipping", p)
            continue
        out.append((p, parsed))
    return out


@router.post("/show")
async def rule_show(req: RuleShowRequest) -> JSONResponse:
    """List rulings under a given topic folder. Sorted by last_reused_at desc."""
    if obsidian is None:
        raise HTTPException(
            status_code=503, detail={"error": "rule subsystem not initialised"}
        )
    topic = coerce_topic(req.topic)
    prefix = f"{RULING_CACHE_PATH_PREFIX}/{topic}/"
    collected = await _collect_rulings_under(prefix)
    entries = [_build_ruling_index_entry(p, parsed, topic=topic) for p, parsed in collected]
    entries.sort(key=lambda e: e.get("last_reused_at", ""), reverse=True)
    return JSONResponse({"topic": topic, "count": len(entries), "rulings": entries})


@router.post("/history")
async def rule_history(req: RuleHistoryRequest) -> JSONResponse:
    """Top-N most-recent rulings across ALL topics by last_reused_at (D-14)."""
    if obsidian is None:
        raise HTTPException(
            status_code=503, detail={"error": "rule subsystem not initialised"}
        )
    n = req.n  # already clamped to [1, 100] by field_validator
    root_prefix = f"{RULING_CACHE_PATH_PREFIX}/"
    try:
        all_paths = await obsidian.list_directory(root_prefix)
    except Exception as exc:
        logger.warning("rule_history: root list_directory failed: %s", exc)
        all_paths = []
    all_entries: list[dict] = []
    for p in all_paths:
        if not p.endswith(".md"):
            continue
        text = await obsidian.get_note(p)
        if not text:
            continue
        parsed = _parse_ruling_cache(text)
        if parsed is None:
            continue
        # topic = path segment between the root prefix and the final filename.
        stripped = p.removeprefix(root_prefix)
        topic = stripped.split("/", 1)[0] if "/" in stripped else "misc"
        all_entries.append(_build_ruling_index_entry(p, parsed, topic=topic))
    all_entries.sort(key=lambda e: e.get("last_reused_at", ""), reverse=True)
    return JSONResponse({"n": n, "rulings": all_entries[:n]})


@router.post("/list")
async def rule_list() -> JSONResponse:
    """Enumerate topic folders and their activity. Sorted by last_activity desc."""
    if obsidian is None:
        raise HTTPException(
            status_code=503, detail={"error": "rule subsystem not initialised"}
        )
    root_prefix = f"{RULING_CACHE_PATH_PREFIX}/"
    try:
        all_paths = await obsidian.list_directory(root_prefix)
    except Exception as exc:
        logger.warning("rule_list: root list_directory failed: %s", exc)
        all_paths = []
    # Group by topic slug (first segment after root_prefix).
    per_topic: dict[str, dict] = {}
    for p in all_paths:
        if not p.endswith(".md"):
            continue
        stripped = p.removeprefix(root_prefix)
        if "/" not in stripped:
            continue
        topic = stripped.split("/", 1)[0]
        text = await obsidian.get_note(p)
        if not text:
            continue
        parsed = _parse_ruling_cache(text)
        if parsed is None:
            continue
        bucket = per_topic.setdefault(topic, {"slug": topic, "count": 0, "last_activity": ""})
        bucket["count"] += 1
        last_act = parsed.get("last_reused_at", parsed.get("composed_at", ""))
        if last_act > bucket["last_activity"]:
            bucket["last_activity"] = last_act
    topics = list(per_topic.values())
    topics.sort(key=lambda t: t.get("last_activity", ""), reverse=True)
    return JSONResponse({"topics": topics})
