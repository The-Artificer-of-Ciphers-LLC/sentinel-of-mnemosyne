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

from app.config import settings
from app.llm import (
    classify_rule_topic,
    embed_texts,
    generate_ruling_fallback,
    generate_ruling_from_passages,
)
from app.resolve_model import resolve_model
from app.rules import (
    D_07_DECLINE_TEMPLATE,
    MAX_QUERY_CHARS,
    RETRIEVAL_SIMILARITY_THRESHOLD,
    REUSE_SIMILARITY_THRESHOLD,
    RULING_CACHE_PATH_PREFIX,
    RulesIndex,
    _parse_ruling_cache,
    build_ruling_markdown,
    check_pf1_scope,
    coerce_topic,
    normalize_query,
    query_hash,
    retrieve,
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
    """RUL-01..04 core — 9-step orchestration (D-02).

    Returns HTTP 200 for all non-exceptional paths (decline is a normal response,
    not an error). HTTP 500 on embed/LLM failure; HTTP 503 when singletons not
    initialised (lifespan hasn't run or module is shutting down).
    """
    if obsidian is None or rules_index is None or aon_url_map is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "rule subsystem not initialised (lifespan incomplete?)"},
        )

    query = req.query
    user_id = req.user_id

    # Step 2: PF1 decline runs FIRST — before any cache / embed / LLM cost (D-06, RUL-04).
    pf1_hit = check_pf1_scope(query)
    if pf1_hit:
        logger.info("rule_query: PF1 decline for user=%s term=%r", user_id, pf1_hit)
        return JSONResponse(
            {
                "question": query,
                "answer": D_07_DECLINE_TEMPLATE.format(term=pf1_hit),
                "why": "",
                "source": None,
                "citations": [],
                "marker": "declined",
                "topic": None,
                "reused": False,
                "reuse_note": "",
            }
        )

    # Step 3: compute query hash + topic classification.
    q_norm = normalize_query(query)
    q_hash = query_hash(query)
    model_chat = await resolve_model("chat")
    model_structured = await resolve_model("structured")
    api_base = settings.litellm_api_base or None

    topic = await classify_rule_topic(query, model=model_structured, api_base=api_base)
    topic = coerce_topic(topic)  # belt + suspenders — classify_rule_topic already coerces

    # Step 4: exact-hash cache check.
    cache_path = f"{RULING_CACHE_PATH_PREFIX}/{topic}/{q_hash}.md"
    cached_text = await obsidian.get_note(cache_path)
    if cached_text is not None:
        parsed = _parse_ruling_cache(cached_text)
        if parsed is not None:
            # D-14: update last_reused_at, GET-then-PUT (NEVER the surgical PATCH — L-3).
            parsed["last_reused_at"] = _now_iso()
            parsed["reused"] = True
            parsed["reuse_note"] = (
                parsed.get("reuse_note")
                or f"_reusing prior ruling on {topic} — confirm applicability_"
            )
            try:
                await obsidian.put_note(cache_path, build_ruling_markdown(parsed))
            except Exception as exc:
                logger.warning("rule_query: last_reused_at PUT failed for %s: %s", cache_path, exc)
            logger.info("rule_query: exact-hash cache hit for user=%s topic=%s", user_id, topic)
            return JSONResponse(_strip_internal_fields(parsed))
        logger.warning("rule_query: cache malformed at %s; re-composing", cache_path)

    # Step 5: embed the query (one vector).
    try:
        query_vecs = await embed_texts(
            [q_norm],
            api_base=api_base,
            model=settings.rules_embedding_model,
        )
    except Exception as exc:
        logger.error("rule_query: embed failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "embedding failed", "detail": str(exc)},
        )
    query_vec = np.asarray(query_vecs[0], dtype=np.float32)

    # Step 6: retrieve top-K passages above threshold, topic-filtered.
    retrieved = retrieve(
        rules_index,
        query_vec,
        topic,
        k=3,
        threshold=RETRIEVAL_SIMILARITY_THRESHOLD,
    )

    # Step 7: reuse-match scan — walk sibling rulings in this topic folder, cosine
    # against the current query_vec; if any >= REUSE_SIMILARITY_THRESHOLD, return it.
    topic_prefix = f"{RULING_CACHE_PATH_PREFIX}/{topic}/"
    try:
        sibling_paths = await obsidian.list_directory(topic_prefix)
    except Exception as exc:
        logger.warning(
            "rule_query: list_directory %s failed: %s; skipping reuse-match scan",
            topic_prefix, exc,
        )
        sibling_paths = []

    best_reuse: tuple[str, dict, float] | None = None  # (path, parsed, cosine)
    for sib_path in sibling_paths:
        if sib_path == cache_path:
            continue  # skip self (defensive — shouldn't happen; cache already missed)
        sib_text = await obsidian.get_note(sib_path)
        if not sib_text:
            continue
        sib_parsed = _parse_ruling_cache(sib_text)
        if not sib_parsed or not sib_parsed.get("query_embedding"):
            continue
        if sib_parsed.get("embedding_model") != settings.rules_embedding_model:
            # D-13: skip rulings from a different embedding model — staleness tolerated.
            continue
        try:
            sib_vec = _decode_query_embedding(sib_parsed["query_embedding"])
        except Exception:
            continue
        # Cosine similarity against the single sibling vector.
        # Dimension mismatch (e.g. test 5-dim vs prod 768-dim) degrades to 0 via shape guard.
        if sib_vec.shape != query_vec.shape:
            continue
        denom = (np.linalg.norm(sib_vec) or 1.0) * (np.linalg.norm(query_vec) or 1.0)
        sim = float((sib_vec @ query_vec) / denom)
        if sim >= REUSE_SIMILARITY_THRESHOLD and (best_reuse is None or sim > best_reuse[2]):
            best_reuse = (sib_path, sib_parsed, sim)

    if best_reuse is not None:
        reuse_path, reuse_parsed, reuse_sim = best_reuse
        reuse_parsed["last_reused_at"] = _now_iso()
        reuse_parsed["reused"] = True
        reuse_parsed["reuse_note"] = (
            f"_reusing prior ruling on {topic} — confirm applicability_"
        )
        try:
            await obsidian.put_note(reuse_path, build_ruling_markdown(reuse_parsed))
        except Exception as exc:
            logger.warning("rule_query: reuse-match last_reused_at PUT failed: %s", exc)
        logger.info(
            "rule_query: reuse-match hit user=%s topic=%s sim=%.3f path=%s",
            user_id, topic, reuse_sim, reuse_path,
        )
        return JSONResponse(_strip_internal_fields(reuse_parsed))

    # Step 8: compose — passages (RUL-01) OR fallback (RUL-02 / D-03).
    try:
        if retrieved:
            # Enrich each RuleChunk's aon_url from aon_url_map when missing (D-12 honesty).
            enriched: list = []
            for chunk, score in retrieved:
                if not chunk.aon_url:
                    book_map = aon_url_map.get(chunk.book, {}) if aon_url_map else {}
                    url = book_map.get(chunk.section)
                    if url:
                        chunk = chunk.model_copy(update={"aon_url": url})
                enriched.append((chunk, score))
            result = await generate_ruling_from_passages(
                query=query,
                passages=enriched,
                topic=topic,
                model=model_chat,
                api_base=api_base,
            )
        else:
            # D-03: corpus-miss falls through to fallback — NEVER decline for non-PF1 queries.
            result = await generate_ruling_fallback(
                query=query,
                topic=topic,
                model=model_chat,
                api_base=api_base,
            )
    except Exception as exc:
        logger.error(
            "rule_query: LLM composition failed for user=%s topic=%s: %s",
            user_id, topic, exc,
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "LLM ruling composition failed", "detail": str(exc)},
        )

    # Step 9: enrich with D-13 frontmatter metadata + write cache.
    now_iso = _now_iso()
    result["composed_at"] = now_iso
    result["last_reused_at"] = now_iso
    result["embedding_model"] = settings.rules_embedding_model
    result["embedding_hash"] = _embedding_hash(settings.rules_embedding_model)
    result["query_embedding"] = _encode_query_embedding(query_vec)
    result["reused"] = False
    result["reuse_note"] = ""

    try:
        await obsidian.put_note(cache_path, build_ruling_markdown(result))
        logger.info(
            "rule_query: cached fresh ruling user=%s topic=%s marker=%s",
            user_id, topic, result.get("marker"),
        )
    except Exception as exc:
        logger.warning(
            "rule_query: cache PUT failed for %s: %s (degrading — still returning)",
            cache_path, exc,
        )

    return JSONResponse(_strip_internal_fields(result))


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
