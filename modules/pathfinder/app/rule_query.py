"""Deep Rule Query module for PF2e Remaster rules RAG.

Owns the query execution path behind ``POST /rule/query``:
PF1 decline, topic classification, exact cache, embedding, retrieval,
reuse-match scan, LLM composition, cache write, and response scrubbing.

The HTTP route is an adapter. It validates request shape, supplies runtime
dependencies, maps exceptions to HTTP status codes, and serializes the result.
"""
from __future__ import annotations

import datetime
import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.rules import (
    D_07_DECLINE_TEMPLATE,
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
from sentinel_shared.embedding_codec import decode_embedding, encode_embedding

logger = logging.getLogger(__name__)


class RuleQueryNotInitialized(RuntimeError):
    """Raised when required rule-query runtime dependencies are missing."""


class RuleQueryEmbeddingError(RuntimeError):
    """Raised when query embedding fails."""


class RuleQueryCompositionError(RuntimeError):
    """Raised when LLM ruling composition fails."""


@dataclass(frozen=True)
class RuleQueryDependencies:
    """Runtime adapters used by the Rule Query module."""

    obsidian: Any
    rules_index: RulesIndex
    aon_url_map: dict
    settings: Any
    resolve_model: Callable[[str], Awaitable[Any]]
    keyword_classify_topic: Callable[[str], str | None]
    classify_rule_topic: Callable[..., Awaitable[str]]
    embed_texts: Callable[..., Awaitable[list[list[float]]]]
    generate_ruling_from_passages: Callable[..., Awaitable[dict]]
    generate_ruling_fallback: Callable[..., Awaitable[dict]]


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 with Z suffix."""
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def _embedding_hash(model: str) -> str:
    return hashlib.sha1(model.encode("utf-8")).hexdigest()


def strip_internal_fields(result: dict) -> dict:
    """Return only the D-08 + reuse keys for the HTTP response."""
    internal = {
        "query_embedding",
        "embedding_hash",
        "embedding_model",
        "composed_at",
        "last_reused_at",
        "verified",
    }
    return {k: v for k, v in result.items() if k not in internal}


async def execute_rule_query(
    *,
    query: str,
    user_id: str,
    deps: RuleQueryDependencies,
) -> dict:
    """Execute the PF2e rule query flow and return the public response dict."""
    if deps.obsidian is None or deps.rules_index is None or deps.aon_url_map is None:
        raise RuleQueryNotInitialized(
            "rule subsystem not initialised (lifespan incomplete?)"
        )

    # Step 2: PF1 decline runs FIRST, before any cache / embed / LLM cost.
    pf1_hit = check_pf1_scope(query)
    if pf1_hit:
        logger.info("rule_query: PF1 decline for user=%s term=%r", user_id, pf1_hit)
        return {
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

    q_norm = normalize_query(query)
    q_hash = query_hash(query)
    r_chat = await deps.resolve_model("chat")
    r_structured = await deps.resolve_model("structured")
    model_chat = r_chat.model
    model_structured = r_structured.model
    api_base = deps.settings.litellm_api_base or None
    profile_chat = r_chat.profile
    profile_structured = r_structured.profile

    topic = deps.keyword_classify_topic(query)
    if topic is None:
        topic = await deps.classify_rule_topic(
            query,
            model=model_structured,
            api_base=api_base,
            profile=profile_structured,
        )
    topic = coerce_topic(topic)

    cache_path = f"{RULING_CACHE_PATH_PREFIX}/{topic}/{q_hash}.md"
    cached_text = await deps.obsidian.get_note(cache_path)
    if cached_text is not None:
        parsed = _parse_ruling_cache(cached_text)
        if parsed is not None:
            parsed["last_reused_at"] = _now_iso()
            parsed["reused"] = True
            parsed["reuse_note"] = (
                parsed.get("reuse_note")
                or f"_reusing prior ruling on {topic} — confirm applicability_"
            )
            try:
                await deps.obsidian.put_note(cache_path, build_ruling_markdown(parsed))
            except Exception as exc:
                logger.warning(
                    "rule_query: last_reused_at PUT failed for %s: %s",
                    cache_path,
                    exc,
                )
            logger.info(
                "rule_query: exact-hash cache hit for user=%s topic=%s",
                user_id,
                topic,
            )
            return strip_internal_fields(parsed)
        logger.warning("rule_query: cache malformed at %s; re-composing", cache_path)

    try:
        query_vecs = await deps.embed_texts(
            [q_norm],
            api_base=api_base,
            model=deps.settings.rules_embedding_model,
        )
    except Exception as exc:
        logger.error("rule_query: embed failed: %s", exc)
        raise RuleQueryEmbeddingError(str(exc)) from exc
    query_vec = np.asarray(query_vecs[0], dtype=np.float32)

    retrieved = retrieve(
        deps.rules_index,
        query_vec,
        topic,
        k=3,
        threshold=RETRIEVAL_SIMILARITY_THRESHOLD,
    )

    topic_prefix = f"{RULING_CACHE_PATH_PREFIX}/{topic}/"
    try:
        sibling_paths = await deps.obsidian.list_directory(topic_prefix)
    except Exception as exc:
        logger.warning(
            "rule_query: list_directory %s failed: %s; skipping reuse-match scan",
            topic_prefix,
            exc,
        )
        sibling_paths = []

    best_reuse: tuple[str, dict, float] | None = None
    for sib_path in sibling_paths:
        if sib_path == cache_path:
            continue
        sib_text = await deps.obsidian.get_note(sib_path)
        if not sib_text:
            continue
        sib_parsed = _parse_ruling_cache(sib_text)
        if not sib_parsed or not sib_parsed.get("query_embedding"):
            continue
        if sib_parsed.get("embedding_model") != deps.settings.rules_embedding_model:
            continue
        try:
            sib_vec = np.asarray(
                decode_embedding(sib_parsed["query_embedding"]),
                dtype=np.float32,
            )
        except Exception:
            continue
        if sib_vec.shape != query_vec.shape:
            continue
        denom = (np.linalg.norm(sib_vec) or 1.0) * (np.linalg.norm(query_vec) or 1.0)
        sim = float((sib_vec @ query_vec) / denom)
        if sim >= REUSE_SIMILARITY_THRESHOLD and (
            best_reuse is None or sim > best_reuse[2]
        ):
            best_reuse = (sib_path, sib_parsed, sim)

    if best_reuse is not None:
        reuse_path, reuse_parsed, reuse_sim = best_reuse
        reuse_parsed["last_reused_at"] = _now_iso()
        reuse_parsed["reused"] = True
        reuse_parsed["reuse_note"] = (
            f"_reusing prior ruling on {topic} — confirm applicability_"
        )
        try:
            await deps.obsidian.put_note(reuse_path, build_ruling_markdown(reuse_parsed))
        except Exception as exc:
            logger.warning("rule_query: reuse-match last_reused_at PUT failed: %s", exc)
        logger.info(
            "rule_query: reuse-match hit user=%s topic=%s sim=%.3f path=%s",
            user_id,
            topic,
            reuse_sim,
            reuse_path,
        )
        return strip_internal_fields(reuse_parsed)

    try:
        if retrieved:
            enriched: list = []
            for chunk, score in retrieved:
                if not chunk.aon_url:
                    book_map = deps.aon_url_map.get(chunk.book, {})
                    url = book_map.get(chunk.section)
                    if url:
                        chunk = chunk.model_copy(update={"aon_url": url})
                enriched.append((chunk, score))
            result = await deps.generate_ruling_from_passages(
                query=query,
                passages=enriched,
                topic=topic,
                model=model_chat,
                api_base=api_base,
                profile=profile_chat,
            )
        else:
            result = await deps.generate_ruling_fallback(
                query=query,
                topic=topic,
                model=model_chat,
                api_base=api_base,
                profile=profile_chat,
            )
    except Exception as exc:
        logger.error(
            "rule_query: LLM composition failed for user=%s topic=%s: %s",
            user_id,
            topic,
            exc,
        )
        raise RuleQueryCompositionError(str(exc)) from exc

    now_iso = _now_iso()
    result["composed_at"] = now_iso
    result["last_reused_at"] = now_iso
    result["embedding_model"] = deps.settings.rules_embedding_model
    result["embedding_hash"] = _embedding_hash(deps.settings.rules_embedding_model)
    result["query_embedding"] = encode_embedding(query_vec)
    result["reused"] = False
    result["reuse_note"] = ""

    try:
        await deps.obsidian.put_note(cache_path, build_ruling_markdown(result))
        logger.info(
            "rule_query: cached fresh ruling user=%s topic=%s marker=%s",
            user_id,
            topic,
            result.get("marker"),
        )
    except Exception as exc:
        logger.warning(
            "rule_query: cache PUT failed for %s: %s (degrading — still returning)",
            cache_path,
            exc,
        )

    return strip_internal_fields(result)
