"""Rules helpers for pathfinder module — PF2e Remaster RAG (RUL-01..04, D-01..D-15).

Pure-transform module: no LLM calls (those live in app.llm.embed_texts /
classify_rule_topic / generate_ruling_*), no Obsidian I/O (those live in
app.routes.rule), no FastAPI dependencies. Only stdlib + numpy + bs4 +
pydantic + logging + re + the single slugify import from app.routes.npc
for topic-slug validation (Don't Hand-Roll).

Ships: RuleChunk schema, RulesIndex dataclass, PF1 keyword denylist (D-06),
cosine similarity + retrieve (D-02 step 3), topic-slug vocabulary + coerce
(L-6 prevention), query normalization + sha1 hash (D-04 cache path key),
HTML stripper + UUID-ref resolver (Foundry pf2e journal -> plaintext),
build_ruling_markdown + _parse_ruling_cache (D-13 + D-14 frontmatter),
_validate_ruling_shape + _normalize_ruling_output (L-2 prevention).

Per CLAUDE.md AI Deferral Ban: every helper completes its job; no TODO/pass/NotImplementedError.
Per memory project_obsidian_patch_constraint: no surgical-PATCH-against-new-fields here —
GET-then-PUT is the only safe write pattern, enforced at the route layer (Wave 3).
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.routes.npc import slugify  # reuse — Don't Hand-Roll (Phase 29 precedent)

logger = logging.getLogger(__name__)


__all__ = [
    "D_07_DECLINE_TEMPLATE",
    "EMBEDDING_DIM_DEFAULT",
    "MAX_QUERY_CHARS",
    "RETRIEVAL_SIMILARITY_THRESHOLD",
    "REUSE_SIMILARITY_THRESHOLD",
    "RULE_TOPIC_SLUGS",
    "RULING_CACHE_PATH_PREFIX",
    "RuleChunk",
    "RulesIndex",
    "_PF1_PATTERN",
    "_decode_query_embedding",
    "_normalize_ruling_output",
    "_parse_ruling_cache",
    "_validate_ruling_shape",
    "build_rules_index",
    "build_ruling_markdown",
    "check_pf1_scope",
    "coerce_topic",
    "cosine_similarity",
    "load_aon_url_map",
    "load_rules_corpus",
    "normalize_query",
    "query_hash",
    "render_citation_label",
    "retrieve",
    "slugify",
    "strip_rule_html",
]


# --- Module constants ---

RETRIEVAL_SIMILARITY_THRESHOLD: float = 0.65   # Calibrated Wave 2 (see 33-03-SUMMARY §Threshold Calibration)
REUSE_SIMILARITY_THRESHOLD: float = 0.80       # D-05 — user-locked
RULING_CACHE_PATH_PREFIX: str = "mnemosyne/pf2e/rulings"  # D-04
MAX_QUERY_CHARS: int = 500
EMBEDDING_DIM_DEFAULT: int = 768               # nomic-embed-text-v1.5 dim

# D-06: PF1 denylist regex (RESEARCH §PF1 Denylist — verbatim).
_PF1_DECLINE_TERMS = [
    r"\bTHAC0\b",
    r"\bBAB\b",
    r"\btouch AC\b",
    r"\bflat-footed AC\b",
    r"\bcombat maneuver bonus\b", r"\bCMB\b",
    r"\bcombat maneuver defense\b", r"\bCMD\b",
    r"\bspell schools?\b",
    r"\bschools? of magic\b",
    r"\b(abjuration|conjuration|divination|enchantment|evocation|necromancy|transmutation) school\b",
    r"\b(verbal|somatic|material) components?\b",
    r"\bVancian (casting|magic)\b",
    r"\bprestige class\b", r"\bprestige classes\b",
    r"\bfavored class bonus\b", r"\bFCB\b",
    r"\bracial (HD|hit dice)\b",
    r"\bCore Rulebook 1st\b", r"\bCRB 1e\b",
    r"\b(1st|first) edition( Pathfinder)?\b",
    # Require an explicit E/e suffix so bare "Pathfinder 1" (as in "Pathfinder 1
    # mythic rules compare to Remaster") doesn't false-match. Covers 1E, 1e, 1Ee,
    # 1ee — all legitimate abbreviations for Pathfinder 1st Edition.
    r"\bPathfinder 1[Ee]e?\b", r"\bPF1e?\b",
    r"\b3\.5e?\b", r"\b3\.5 edition\b", r"\bD&D 3\.5\b",
    r"\bd20 [Ss]ystem\b",
    r"\bOGL\b",
]
_PF1_PATTERN = re.compile("|".join(_PF1_DECLINE_TERMS), re.IGNORECASE)

# D-07 (verbatim) — the decline message template.
D_07_DECLINE_TEMPLATE = (
    "This Sentinel only supports PF2e Remaster (2023+). Your query references "
    "{term}, which is a PF1/pre-Remaster concept. For PF1 questions, try "
    "Archives of Nethys 1e (https://legacy.aonprd.com)."
)

# RESEARCH §Topic Slug Vocabulary — 25 slugs, closed set.
RULE_TOPIC_SLUGS: list[str] = [
    "flanking", "off-guard", "grapple", "trip", "shove", "falling",
    "combat", "dcs", "conditions", "healing", "dying", "exploration",
    "skills", "actions", "senses", "detection", "terrain", "spellcasting",
    "downtime", "encumbrance", "treasure", "identification", "hero-points",
    "subsystems", "misc",
]


# --- Pydantic schema + RulesIndex dataclass ---

class RuleChunk(BaseModel):
    id: str
    book: str
    page: str | None = None
    section: str
    chapter: str | None = None
    aon_url: str | None = None
    text: str
    topics: list[str] = Field(default_factory=list)
    source_license: str = "ORC"


@dataclass
class RulesIndex:
    chunks: list[RuleChunk]
    matrix: np.ndarray                      # shape (N, D)
    norms: np.ndarray                       # shape (N,)
    topic_index: dict[str, list[int]] = field(default_factory=dict)


# --- PF1 denylist (D-06) ---

def check_pf1_scope(query: str) -> str | None:
    """Return the matched PF1 token (as it appeared in the query), or None.

    D-06: hard-decline on PF1-only combat stats (THAC0, BAB, CMB, CMD),
    spell-school terminology (removed in Remaster), pre-Remaster editions,
    and explicit 1e/3.5/d20 references. Soft tokens (bare 'flat-footed',
    bare 'conjuration', 'attack of opportunity') fall through — the corpus
    naturally re-anchors the LLM to Remaster terminology.
    """
    if not isinstance(query, str) or not query:
        return None
    m = _PF1_PATTERN.search(query)
    if m is None:
        return None
    return m.group(0)


# --- Vector math (D-02 step 3 retrieval) ---

def cosine_similarity(matrix: np.ndarray, vec: np.ndarray) -> np.ndarray:
    """Return cosine similarity of every row in `matrix` against `vec`.

    Zero-norm rows yield 0.0 (not NaN). Zero-norm `vec` yields an all-zero result.
    """
    matrix = np.asarray(matrix, dtype=np.float32)
    vec = np.asarray(vec, dtype=np.float32)
    if matrix.ndim != 2:
        raise ValueError(f"cosine_similarity expected matrix.ndim=2, got {matrix.ndim}")
    if vec.ndim != 1:
        raise ValueError(f"cosine_similarity expected vec.ndim=1, got {vec.ndim}")

    row_norms = np.linalg.norm(matrix, axis=1)
    vec_norm = float(np.linalg.norm(vec))

    # Guard against divide-by-zero: zero-norm rows or zero-norm query produce sim=0.
    if vec_norm == 0.0:
        return np.zeros(matrix.shape[0], dtype=np.float32)

    # Replace zero row norms with 1.0 to avoid NaN; the numerator is 0 for those rows
    # so the resulting similarity is correctly 0.
    safe_row_norms = np.where(row_norms == 0.0, 1.0, row_norms)
    dots = matrix @ vec
    sims = dots / (safe_row_norms * vec_norm)
    # Explicitly zero-out the rows that had zero norm (in case numerator wasn't exactly 0).
    sims = np.where(row_norms == 0.0, 0.0, sims)
    return sims.astype(np.float32)


def retrieve(
    index: RulesIndex,
    query_vec: np.ndarray,
    topic: str | None,
    k: int = 3,
    threshold: float = RETRIEVAL_SIMILARITY_THRESHOLD,
) -> list[tuple[RuleChunk, float]]:
    """Return top-k (chunk, similarity) pairs above threshold.

    If `topic` is provided AND in index.topic_index with at least one entry,
    only those chunk indices are considered. Otherwise the full matrix is scanned.
    Hits are sorted by similarity desc and capped at k.
    """
    if index.matrix.shape[0] == 0 or not index.chunks:
        return []

    sims = cosine_similarity(index.matrix, query_vec)

    # Restrict indices if topic filter applies.
    if topic and topic in index.topic_index and index.topic_index[topic]:
        candidate_indices = index.topic_index[topic]
    else:
        candidate_indices = list(range(len(index.chunks)))

    scored: list[tuple[RuleChunk, float]] = []
    for i in candidate_indices:
        sim = float(sims[i])
        if sim >= threshold:
            scored.append((index.chunks[i], sim))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]


# --- Query normalization + hash (D-04 cache path key) ---

def normalize_query(q: str) -> str:
    """Lowercase and collapse all whitespace to single spaces; trim edges."""
    if not isinstance(q, str):
        return ""
    return " ".join(q.lower().split())


def query_hash(q: str) -> str:
    """Return 8-hex-char sha1 prefix of the normalized query. Deterministic."""
    normalized = normalize_query(q)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]


# --- Topic-slug coercion (L-6 prevention) ---

def coerce_topic(slug: str) -> str:
    """Return the input slug if it is in the closed vocabulary, else 'misc'.

    L-6: empty strings, whitespace-only strings, non-str inputs, and any unknown
    slug all coerce to 'misc' to prevent empty-slug cache-path collision and
    topic-folder sprawl.
    """
    if not isinstance(slug, str):
        return "misc"
    cleaned = slug.strip()
    if cleaned and cleaned in RULE_TOPIC_SLUGS:
        return cleaned
    return "misc"


# --- Corpus + URL map loaders ---

def load_rules_corpus(path: Path) -> list[RuleChunk]:
    """Read rules-corpus.json and return validated RuleChunk list.

    Called once at FastAPI lifespan startup. Raises on missing file or malformed
    JSON/schema so Docker restart-loop surfaces the problem (fail-fast).
    """
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, dict) or "chunks" not in raw:
        raise ValueError(
            f"load_rules_corpus: expected top-level 'chunks' key in {path}"
        )
    chunks_raw = raw["chunks"]
    if not isinstance(chunks_raw, list):
        raise ValueError(
            f"load_rules_corpus: 'chunks' must be a list (got {type(chunks_raw).__name__})"
        )
    return [RuleChunk.model_validate(c) for c in chunks_raw]


def load_aon_url_map(path: Path) -> dict[str, dict[str, str]]:
    """Read aon-url-map.json and return the nested {book: {section: url}} dict.

    Missing file is non-fatal: log WARNING and return empty dict. Citation
    rendering degrades to no-URL rather than crashing (D-12 incremental coverage).
    """
    p = Path(path)
    if not p.exists():
        logger.warning("aon-url-map.json missing at %s — citations will render without URLs", p)
        return {}
    data = json.loads(p.read_text())
    if not isinstance(data, dict):
        logger.warning("aon-url-map.json at %s not a dict — ignoring", p)
        return {}
    # Light validation — filter out non-dict book values rather than raising.
    out: dict[str, dict[str, str]] = {}
    for book, sections in data.items():
        if isinstance(sections, dict):
            out[book] = {s: u for s, u in sections.items() if isinstance(u, str)}
    return out


# --- Rules index builder (async — takes an embed_fn) ---

async def build_rules_index(
    chunks: list[RuleChunk],
    embed_fn: Callable[[list[str]], Awaitable[list[list[float]]]],
) -> RulesIndex:
    """Build a RulesIndex by embedding every chunk text via `embed_fn`.

    Raises on empty corpus (a rules-engine with zero chunks is a config bug).
    """
    if not chunks:
        raise ValueError("build_rules_index: corpus is empty")
    texts = [c.text for c in chunks]
    vectors = await embed_fn(texts)
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] != len(chunks):
        raise ValueError(
            f"build_rules_index: embed_fn returned shape {matrix.shape} for {len(chunks)} chunks"
        )
    norms = np.linalg.norm(matrix, axis=1)
    # Avoid zero-division for degenerate chunks; store safe norms for downstream math.
    safe_norms = np.where(norms == 0.0, 1.0, norms)
    topic_index: dict[str, list[int]] = {}
    for i, c in enumerate(chunks):
        for t in c.topics:
            topic_index.setdefault(t, []).append(i)
    logger.info(
        "Built rules index: %d chunks, %d topics, shape=%s",
        len(chunks), len(topic_index), matrix.shape,
    )
    return RulesIndex(chunks=chunks, matrix=matrix, norms=safe_norms, topic_index=topic_index)


# --- HTML stripper + UUID-ref resolver (Foundry pf2e -> plaintext) ---

def strip_rule_html(html: str) -> str:
    """Strip HTML tags and resolve Foundry @UUID[...] refs to trailing identifier.

    Input:  "<p>Condition: @UUID[Compendium.pf2e.conditionitems.Item.Grabbed]</p>"
    Output: "Condition: Grabbed"

    The @UUID wrapper and Compendium-path prefix are Foundry-internal routing and
    must not leak into embedded text (they'd skew the embedding).
    """
    soup = BeautifulSoup(html or "", "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    # Resolve @UUID[...] -> last dot-separated identifier.
    text = re.sub(
        r"@UUID\[[^\]]*?([A-Za-z0-9-]+)\]",
        lambda m: m.group(1),
        text,
    )
    # Collapse repeated whitespace introduced by HTML stripping.
    return re.sub(r"\s+", " ", text).strip()


# --- Output-shape validator (CR-02 analog for D-08 response shape) ---

_VALID_MARKERS = {"source", "generated", "declined"}


def _validate_ruling_shape(parsed: dict) -> None:
    """Raise ValueError on missing or wrong-typed D-08 fields.

    Accepts a minimal valid dict; the normalizer is the upstream safety net that
    fills missing fields before this validator runs.
    """
    if not isinstance(parsed, dict):
        raise ValueError(f"ruling shape: expected dict, got {type(parsed).__name__}")

    q = parsed.get("question")
    if not isinstance(q, str) or not q:
        raise ValueError("ruling shape: 'question' must be a non-empty str")

    a = parsed.get("answer")
    if not isinstance(a, str):
        raise ValueError("ruling shape: 'answer' must be a str (key may be missing)")
    if not a and parsed.get("marker") != "declined":
        raise ValueError("ruling shape: 'answer' must be a non-empty str (unless marker='declined')")
    if len(a) > 4000:
        raise ValueError(f"ruling shape: 'answer' exceeds 4000 chars (got {len(a)})")

    w = parsed.get("why")
    if not isinstance(w, str):
        raise ValueError("ruling shape: 'why' must be a str")

    if "source" in parsed:
        src = parsed["source"]
        if src is not None and not isinstance(src, str):
            raise ValueError("ruling shape: 'source' must be a str or None")

    cites = parsed.get("citations")
    if not isinstance(cites, list):
        raise ValueError("ruling shape: 'citations' must be a list")

    marker = parsed.get("marker")
    if marker not in _VALID_MARKERS:
        raise ValueError(f"ruling shape: 'marker' must be one of {_VALID_MARKERS}, got {marker!r}")

    topic = parsed.get("topic")
    if topic is not None and not isinstance(topic, str):
        raise ValueError("ruling shape: 'topic' must be a str or None")


def _normalize_ruling_output(
    parsed: dict,
    *,
    topic: str,
    query: str,
    marker: str | None = None,
) -> dict:
    """Fill safe defaults BEFORE _validate_ruling_shape (L-2 prevention).

    LLM helpers may omit fields; harvest's CR-02 learned that missing !=
    wrong. Before raising on malformed shape, normalize what we can.
    """
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM returned non-dict ruling: {type(parsed).__name__}")
    out = dict(parsed)  # shallow copy
    out.setdefault("question", query)
    out.setdefault("answer", "")
    out.setdefault("why", "")
    out.setdefault("citations", [])
    if not isinstance(out.get("citations"), list):
        out["citations"] = []
    out.setdefault("source", None)
    out["topic"] = coerce_topic(topic)  # never trust LLM for topic — came from classifier
    if marker is not None:
        out["marker"] = marker
    else:
        existing = out.get("marker")
        if existing not in _VALID_MARKERS:
            # Infer: source set AND citations non-empty -> "source"; else "generated".
            out["marker"] = "source" if (out.get("source") and out.get("citations")) else "generated"
    return out


# --- Query-embedding (de)serialization helpers ---

def _encode_query_embedding(vec) -> str:
    """base64-encode a list[float] or np.ndarray as float32 little-endian bytes."""
    if isinstance(vec, str):
        # Already-encoded base64 — caller provided cached representation.
        return vec
    arr = np.asarray(vec, dtype=np.float32)
    return base64.b64encode(arr.tobytes()).decode("ascii")


def _decode_query_embedding(s) -> list[float]:
    """Decode the frontmatter query_embedding back to a list[float].

    Accepts either a base64 string (new-style) or a list/ndarray (already decoded).
    """
    if isinstance(s, list):
        return [float(x) for x in s]
    if isinstance(s, np.ndarray):
        return s.astype(np.float32).tolist()
    if isinstance(s, str):
        if not s:
            return []
        try:
            raw = base64.b64decode(s.encode("ascii"))
            arr = np.frombuffer(raw, dtype=np.float32)
            return arr.tolist()
        except Exception as exc:
            logger.warning("Failed to decode query_embedding base64: %s", exc)
            return []
    return []


def _iso_utc_now() -> str:
    """Return ISO8601 UTC timestamp with 'Z' suffix (Python 3.12+ datetime.UTC convention)."""
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


# --- Canonical D-09 citation-label renderer (WR-05 — single source of truth) ---

def render_citation_label(
    *,
    book: str | None,
    page: str | None,
    section: str | None,
    url: str | None,
) -> str:
    """Render a single D-09 citation label: 'Book p. N — Section | URL'.

    D-09: omit missing fields — NEVER fabricate. Missing is represented as
    None OR the empty string (WR-04 fix — empty string is not a value).

    Called from BOTH build_ruling_markdown (cache body) and
    app.llm._render_citation_label (response source field) so the two
    renderings cannot drift.
    """
    label = book if book else "?"
    if page is not None and page != "":
        label = f"{label} p. {page}"
    if section:
        label = f"{label} — {section}"
    if url:
        label = f"{label} | {url}"
    return label


# --- Obsidian cache markdown builder (D-13 + D-14 frontmatter) ---

def build_ruling_markdown(result: dict) -> str:
    """Build the write-through cache markdown for mnemosyne/pf2e/rulings/<topic>/<hash>.md.

    D-08 body shape, D-13 embedding frontmatter (embedding_model +
    embedding_hash + query_embedding-as-base64), D-14 timestamp pair
    (composed_at on first write, last_reused_at updated on every cache hit).

    Marker handling:
      - marker='source' → Answer / Why / Citations body
      - marker='generated' → body with [GENERATED — verify] banner (RUL-02)
      - marker='declined' → D-07 decline message is the body verbatim
    """
    question = str(result.get("question", "")).strip()
    answer = str(result.get("answer", "")).strip()
    why = str(result.get("why", "")).strip()
    source = result.get("source")
    citations = result.get("citations") or []
    marker = result.get("marker") or "generated"
    topic = result.get("topic")
    reused = bool(result.get("reused", False))
    reuse_note = result.get("reuse_note") or ""
    verified_flag = bool(result.get("verified", False))

    embedding_model = result.get("embedding_model") or ""
    embedding_hash = result.get("embedding_hash") or (
        hashlib.sha1(embedding_model.encode("utf-8")).hexdigest() if embedding_model else ""
    )
    query_embedding_raw = result.get("query_embedding", [])
    query_embedding_b64 = _encode_query_embedding(query_embedding_raw)

    composed_at = result.get("composed_at") or _iso_utc_now()
    last_reused_at = result.get("last_reused_at") or composed_at

    frontmatter = {
        "question": question,
        "topic": topic,
        "marker": marker,
        "source": source,
        "citations": citations,
        "answer": answer,
        "why": why,
        "verified": verified_flag,
        "reused": reused,
        "reuse_note": reuse_note,
        "composed_at": composed_at,
        "last_reused_at": last_reused_at,
        "embedding_model": embedding_model,
        "embedding_hash": embedding_hash,
        "query_embedding": query_embedding_b64,
    }
    fm_yaml = yaml.dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )

    # Body — branches by marker.
    title = (question[:117] + "...") if len(question) > 120 else question
    body_lines: list[str] = [f"# {title}"] if title else ["# Ruling"]

    if marker == "declined":
        # D-07 decline — body is the answer verbatim, nothing else.
        body_lines.append("")
        body_lines.append(answer)
    else:
        if marker == "generated":
            body_lines.append("")
            body_lines.append("> **⚠ [GENERATED — verify] against sourcebook before finalising.**")

        body_lines.append("")
        body_lines.append("## Answer")
        body_lines.append("")
        body_lines.append(answer or "_(no answer produced)_")

        body_lines.append("")
        body_lines.append("## Why")
        body_lines.append("")
        body_lines.append(why or "_(no reasoning produced)_")

        if citations:
            body_lines.append("")
            body_lines.append("## Citations")
            body_lines.append("")
            for c in citations:
                if not isinstance(c, dict):
                    continue
                # D-09 render via canonical helper — WR-05 single source of truth.
                label = render_citation_label(
                    book=c.get("book"),
                    page=c.get("page"),
                    section=c.get("section"),
                    url=c.get("url"),
                )
                body_lines.append(f"- {label}")

        if reused and topic:
            body_lines.append("")
            body_lines.append(f"_reusing prior ruling on {topic} — confirm applicability_")
        elif reuse_note:
            body_lines.append("")
            body_lines.append(f"_{reuse_note}_")

    body_lines.append("")
    body_lines.append(
        f"*Source: PF2e Remaster (Paizo, ORC license) via FoundryVTT pf2e system — verified: {str(verified_flag).lower()}*"
    )

    return f"---\n{fm_yaml}---\n\n" + "\n".join(body_lines) + "\n"


# --- Obsidian cache parser (mirrors _parse_harvest_cache) ---

def _parse_ruling_cache(note_text: str) -> dict | None:
    """Parse a cached ruling note back into a dict. Returns None on malformed.

    Mirrors _parse_harvest_cache's log-and-degrade shape. On any exception:
    log WARNING, return None; route handler treats None like 'no cache file'.
    """
    try:
        if not isinstance(note_text, str) or not note_text.startswith("---"):
            return None
        end = note_text.find("---", 3)
        if end == -1:
            return None
        frontmatter_text = note_text[3:end].strip()
        fm = yaml.safe_load(frontmatter_text) or {}
        if not isinstance(fm, dict) or "question" not in fm:
            return None

        citations = fm.get("citations") or []
        if not isinstance(citations, list):
            citations = []

        return {
            "question": fm.get("question", ""),
            "answer": fm.get("answer", ""),
            "why": fm.get("why", ""),
            "source": fm.get("source"),
            "citations": citations,
            "marker": fm.get("marker", "generated"),
            "topic": fm.get("topic"),
            "verified": bool(fm.get("verified", False)),
            "reused": bool(fm.get("reused", False)),
            "reuse_note": fm.get("reuse_note", ""),
            "composed_at": fm.get("composed_at"),
            "last_reused_at": fm.get("last_reused_at"),
            "embedding_model": fm.get("embedding_model", ""),
            "embedding_hash": fm.get("embedding_hash", ""),
            "query_embedding": fm.get("query_embedding", ""),
        }
    except Exception as exc:
        logger.warning("Rule cache parse failed: %s", exc)
        return None
