"""Tests for pf2e-module rules engine (RUL-01..04, D-02 retrieval, D-05 reuse, D-06 PF1 denylist).

Wave 0 RED stubs — symbols referenced below land in:
  - app.rules (Wave 1 / Plan 33-02)
  - app.llm embed_texts / classify_rule_topic / generate_ruling_* (Wave 2 / Plan 33-03)
  - app.routes.rule + main.py lifespan (Wave 3 / Plan 33-04)

Imports of those symbols are function-scope inside each test so pytest collection
succeeds before the implementation lands (pattern from Phase 32 Wave 0).

Decision coverage: D-02, D-05, D-06, D-07, D-08, D-13, D-14, D-15.
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# L-1 smoke tests — Dockerfile dep dual-ship regression guards (Phase 32 G-1)
# ---------------------------------------------------------------------------


def test_numpy_importable():
    """numpy must be installed in BOTH host venv AND pf2e-module container.

    Wave 1 adds numpy to pyproject.toml AND the Dockerfile inline pip install
    block. Skipping the Dockerfile side causes `ModuleNotFoundError` at
    container startup while the host venv silently passes tests (Phase 32 G-1).
    """
    import numpy

    assert numpy.__version__ >= "1.26.0"


def test_bs4_importable():
    """beautifulsoup4 must be installed in BOTH host venv AND pf2e-module container.

    Wave 1 adds bs4 + lxml to pyproject.toml AND the Dockerfile inline pip install
    block. Used by strip_rule_html to clean Foundry journal HTML at corpus load.
    """
    import bs4

    assert bs4.__version__ >= "4.12.0"


# ---------------------------------------------------------------------------
# D-06 PF1 denylist — hard decline cases
# ---------------------------------------------------------------------------


def test_pf1_denylist_thac0_declines():
    """D-06 hard: THAC0 (PF1 combat stat) must trigger decline."""
    from app.rules import check_pf1_scope

    assert check_pf1_scope("What is THAC0?") == "THAC0"


def test_pf1_denylist_bab_declines():
    """D-06 hard: BAB (base attack bonus) is PF1-only terminology."""
    from app.rules import check_pf1_scope

    result = check_pf1_scope("How does a BAB of +8 translate to Remaster?")
    assert result == "BAB"


def test_pf1_denylist_spell_schools_declines():
    """D-06 hard: 'spell schools' phrase was removed in PF2e Remaster."""
    from app.rules import check_pf1_scope

    result = check_pf1_scope("Rules for spell schools in PF2")
    assert result is not None
    assert "spell schools" in result.lower()


def test_pf1_denylist_conjuration_school_declines():
    """D-06 hard: compound 'conjuration school' declines (school of magic removed)."""
    from app.rules import check_pf1_scope

    result = check_pf1_scope("How does the conjuration school work?")
    assert result is not None
    assert "conjuration school" in result.lower()


def test_pf1_denylist_prestige_class_declines():
    """D-06 hard: 'prestige class' was removed in PF2e (archetypes replaced)."""
    from app.rules import check_pf1_scope

    result = check_pf1_scope("What prestige class options do fighters have?")
    assert result is not None
    assert "prestige class" in result.lower()


def test_pf1_denylist_cmb_declines():
    """D-06 hard: CMB (combat maneuver bonus) is PF1-only."""
    from app.rules import check_pf1_scope

    result = check_pf1_scope("CMB check for grappling?")
    assert result == "CMB"


def test_pf1_denylist_vancian_declines():
    """D-06 hard: 'Vancian casting' is pre-Remaster terminology."""
    from app.rules import check_pf1_scope

    result = check_pf1_scope("Does PF2 use Vancian casting?")
    assert result is not None
    assert "vancian" in result.lower()


# ---------------------------------------------------------------------------
# D-06 PF1 denylist — soft-trigger cases (MUST NOT decline)
# ---------------------------------------------------------------------------


def test_pf1_soft_flat_footed_passes():
    """D-06 soft: bare 'flat-footed' must NOT decline (Remaster off-guard rename).

    Only the compound 'flat-footed AC' as a distinct stat is PF1-indicator.
    A DM who says 'my character is flat-footed' is using the old word for
    off-guard; the corpus retrieval re-anchors them to Remaster terminology.
    """
    from app.rules import check_pf1_scope

    result = check_pf1_scope(
        "My character is flat-footed after being tripped — what's the penalty?"
    )
    assert result is None


def test_pf1_soft_attack_of_opportunity_passes():
    """D-06 soft: 'attack of opportunity' warns but does NOT decline.

    Remaster renamed it to 'Reactive Strike'; the query should still flow
    through and let the LLM translate terminology.
    """
    from app.rules import check_pf1_scope

    result = check_pf1_scope("Does a fighter have attack of opportunity?")
    assert result is None


def test_pf1_soft_conjuration_alone_passes():
    """D-06 soft: 'conjuration' alone is a Remaster trait; only 'conjuration school' declines."""
    from app.rules import check_pf1_scope

    result = check_pf1_scope("How does a conjuration spell work?")
    assert result is None


def test_pf1_soft_flanked_passes():
    """D-06 soft: 'flanked' is a Remaster rule; does not trigger denylist."""
    from app.rules import check_pf1_scope

    result = check_pf1_scope("When a fighter is flanked, what happens?")
    assert result is None


# ---------------------------------------------------------------------------
# Cosine similarity math — RESEARCH §Vector Store
# ---------------------------------------------------------------------------


def test_cosine_similarity_deterministic():
    """cosine_similarity(matrix, vec) matches np.dot(matrix, vec) / (norms * vec_norm)."""
    import numpy as np

    from app.rules import cosine_similarity

    matrix = np.array([[1.0, 0.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0, 0.0],
                       [1.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    sims = cosine_similarity(matrix, vec)
    assert sims.shape == (3,)
    assert abs(sims[0] - 1.0) < 1e-4
    assert abs(sims[1] - 0.0) < 1e-4
    assert abs(sims[2] - (1.0 / (2 ** 0.5))) < 1e-4  # ~0.7071


def test_cosine_similarity_zero_vector_safe():
    """Zero-norm rows must NOT produce NaN (division-by-zero guard)."""
    import numpy as np

    from app.rules import cosine_similarity

    matrix = np.array([[0.0, 0.0, 0.0],
                       [1.0, 0.0, 0.0]], dtype=np.float32)
    vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    sims = cosine_similarity(matrix, vec)
    assert not np.any(np.isnan(sims)), "cosine must not NaN on zero-norm rows"
    # Zero-norm row → similarity treated as 0 (never matches)
    assert abs(sims[0] - 0.0) < 1e-6
    assert abs(sims[1] - 1.0) < 1e-4


# ---------------------------------------------------------------------------
# HTML chunker — RESEARCH §Chunking Strategy (Foundry UUID-ref resolution)
# ---------------------------------------------------------------------------


def test_chunker_one_chunk_per_page():
    """strip_rule_html produces plaintext from Foundry page HTML; preserves page citation."""
    from app.rules import strip_rule_html

    plain = strip_rule_html(
        "<p>Hello <em>Pathfinder Player Core pg. 400</em></p>"
    )
    assert "Hello" in plain
    assert "Pathfinder Player Core pg. 400" in plain
    # Should strip HTML tags
    assert "<p>" not in plain
    assert "<em>" not in plain


def test_chunker_html_uuid_refs_resolved():
    """Foundry @UUID[...] wrappers reduce to the trailing identifier.

    Input:  "Condition: @UUID[Compendium.pf2e.conditionitems.Item.Grabbed]"
    Output: "Condition: Grabbed"

    The trailing dot-separated suffix (.Grabbed) is the human-readable name;
    the @UUID wrapper and its Compendium-path prefix are Foundry-internal
    routing and must not leak into embedded text (they'd skew the embedding).
    """
    from app.rules import strip_rule_html

    plain = strip_rule_html(
        "Condition: @UUID[Compendium.pf2e.conditionitems.Item.Grabbed]"
    )
    assert "Grabbed" in plain
    assert "@UUID" not in plain
    assert "Compendium" not in plain


# ---------------------------------------------------------------------------
# RAG retrieval — thresholds (Wave-2 calibrated retrieval=0.65 / D-05 reuse=0.80)
# ---------------------------------------------------------------------------


def test_retrieve_above_threshold_returns_chunk():
    """Query vector aligned with a chunk row returns that chunk (threshold arg=0.55 for math)."""
    import numpy as np

    from app.rules import RuleChunk, RulesIndex, retrieve

    chunks = [
        RuleChunk(
            id="a", book="Pathfinder Player Core", page="1", section="A",
            chapter="X", aon_url=None, text="alpha", topics=["flanking"],
            source_license="ORC",
        ),
        RuleChunk(
            id="b", book="Pathfinder Player Core", page="2", section="B",
            chapter="X", aon_url=None, text="beta", topics=["grapple"],
            source_license="ORC",
        ),
    ]
    matrix = np.array([[1.0, 0.0, 0.0, 0.0],
                       [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    topic_index = {"flanking": [0], "grapple": [1]}
    index = RulesIndex(
        chunks=chunks, matrix=matrix, norms=norms, topic_index=topic_index
    )

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    hits = retrieve(index, query, topic=None, k=3, threshold=0.55)
    assert len(hits) >= 1
    assert hits[0][0].id == "a"
    assert hits[0][1] > 0.55


def test_retrieve_below_threshold_returns_empty():
    """Query orthogonal to all corpus vectors returns empty list (below threshold arg=0.55)."""
    import numpy as np

    from app.rules import RuleChunk, RulesIndex, retrieve

    chunks = [
        RuleChunk(
            id="a", book="Pathfinder Player Core", page="1", section="A",
            chapter="X", aon_url=None, text="alpha", topics=["flanking"],
            source_license="ORC",
        ),
    ]
    matrix = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    index = RulesIndex(
        chunks=chunks, matrix=matrix, norms=norms, topic_index={"flanking": [0]}
    )

    query = np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32)  # orthogonal
    hits = retrieve(index, query, topic=None, k=3, threshold=0.55)
    assert hits == []


def test_retrieve_with_topic_filter_restricts():
    """When topic is provided, retrieval scans only that topic's chunks."""
    import numpy as np

    from app.rules import RuleChunk, RulesIndex, retrieve

    chunks = [
        RuleChunk(
            id="a", book="Pathfinder Player Core", page="1", section="A",
            chapter="X", aon_url=None, text="flank", topics=["flanking"],
            source_license="ORC",
        ),
        RuleChunk(
            id="b", book="Pathfinder Player Core", page="2", section="B",
            chapter="X", aon_url=None, text="grab", topics=["grapple"],
            source_license="ORC",
        ),
    ]
    # Both rows are identical unit vectors — absent topic filter both would match.
    matrix = np.array([[1.0, 0.0, 0.0, 0.0],
                       [1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    topic_index = {"flanking": [0], "grapple": [1]}
    index = RulesIndex(
        chunks=chunks, matrix=matrix, norms=norms, topic_index=topic_index
    )

    query = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    hits = retrieve(index, query, topic="flanking", k=3, threshold=0.55)
    hit_ids = [c.id for c, _ in hits]
    assert "a" in hit_ids
    assert "b" not in hit_ids  # filtered out by topic


# ---------------------------------------------------------------------------
# Topic classifier — L-6 closed-vocabulary coercion
# ---------------------------------------------------------------------------


async def test_classify_rule_topic_returns_known_slug():
    """classify_rule_topic returns a slug from the closed vocabulary."""
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps({"topic": "flanking"}))
            )
        ]
    )
    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        from app.llm import classify_rule_topic

        result = await classify_rule_topic(
            "How does flanking work?", model="x", api_base="y"
        )
    assert result == "flanking"


async def test_classify_rule_topic_unknown_slug_coerced_to_misc():
    """L-6: classifier invents a slug not in RULE_TOPIC_SLUGS → coerced to 'misc'."""
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps({"topic": "flank-attack"})
                )
            )
        ]
    )
    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        from app.llm import classify_rule_topic

        result = await classify_rule_topic(
            "some query", model="x", api_base="y"
        )
    assert result == "misc"


async def test_classify_rule_topic_malformed_json_returns_misc():
    """LLM returns malformed JSON → graceful degradation to 'misc' (no raise)."""
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="oops not json"))
        ]
    )
    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        from app.llm import classify_rule_topic

        result = await classify_rule_topic(
            "some query", model="x", api_base="y"
        )
    assert result == "misc"


# ---------------------------------------------------------------------------
# Query normalization + hash — D-04 cache path shape
# ---------------------------------------------------------------------------


def test_normalize_query_lowercases_and_collapses_whitespace():
    """normalize_query lowercases and collapses consecutive whitespace."""
    from app.rules import normalize_query

    assert normalize_query("  How   Does  Flanking Work? ") == "how does flanking work?"


def test_query_hash_deterministic_8_chars():
    """query_hash returns sha1(normalize_query(q))[:8] — deterministic, 8 hex chars."""
    import re

    from app.rules import query_hash

    h1 = query_hash("How does flanking work?")
    h2 = query_hash("How does flanking work?")
    assert h1 == h2
    assert len(h1) == 8
    assert re.match(r"^[0-9a-f]{8}$", h1)


# ---------------------------------------------------------------------------
# build_ruling_markdown — D-13 (embedding frontmatter) + D-14 (last_reused_at)
# ---------------------------------------------------------------------------


def test_build_ruling_markdown_embeds_query_embedding():
    """build_ruling_markdown writes query_embedding + composed_at + last_reused_at frontmatter."""
    from app.rules import build_ruling_markdown

    result = {
        "question": "How does flanking work?",
        "answer": "Flanking means the target is off-guard.",
        "why": "Two allies on opposite sides impose off-guard.",
        "source": "Pathfinder Player Core p. 416 — Flanking",
        "citations": [
            {
                "book": "Pathfinder Player Core",
                "page": "416",
                "section": "Flanking",
                "url": "https://2e.aonprd.com/Rules.aspx?ID=1349",
            }
        ],
        "marker": "source",
        "topic": "flanking",
        "query_embedding": [0.1, 0.2, 0.3],
        "embedding_model": "text-embedding-nomic-embed-text-v1.5",
    }
    md = build_ruling_markdown(result)
    assert "query_embedding:" in md
    assert "composed_at:" in md
    assert "last_reused_at:" in md
    assert "embedding_model:" in md
    assert "Flanking means the target is off-guard." in md


def test_build_ruling_markdown_generated_banner():
    """marker=='generated' → body carries [GENERATED — verify] banner (RUL-02)."""
    from app.rules import build_ruling_markdown

    generated = {
        "question": "Q?",
        "answer": "A",
        "why": "W",
        "source": None,
        "citations": [],
        "marker": "generated",
        "topic": "misc",
        "query_embedding": [0.0],
        "embedding_model": "m",
    }
    md_gen = build_ruling_markdown(generated)
    assert "[GENERATED — verify]" in md_gen

    sourced = {**generated, "marker": "source", "source": "Book p. 1 — Section",
               "citations": [{"book": "X", "page": "1", "section": "S", "url": "u"}]}
    md_src = build_ruling_markdown(sourced)
    assert "[GENERATED — verify]" not in md_src


def test_build_ruling_markdown_declined_shape():
    """marker=='declined' renders D-07 template body with AoN 1e pointer."""
    from app.rules import build_ruling_markdown

    declined = {
        "question": "What is THAC0?",
        "answer": (
            "This Sentinel only supports PF2e Remaster (2023+). "
            "Your query references THAC0, which is a PF1/pre-Remaster concept. "
            "For PF1 questions, try Archives of Nethys 1e (https://legacy.aonprd.com)."
        ),
        "why": "",
        "source": None,
        "citations": [],
        "marker": "declined",
        "topic": None,
        "query_embedding": [0.0],
        "embedding_model": "m",
    }
    md = build_ruling_markdown(declined)
    assert "This Sentinel only supports PF2e Remaster" in md
    assert "Archives of Nethys 1e" in md


# ---------------------------------------------------------------------------
# _parse_ruling_cache — CR-03 roundtrip analog
# ---------------------------------------------------------------------------


def test_parse_ruling_cache_roundtrip_preserves_marker():
    """build_ruling_markdown → _parse_ruling_cache preserves marker + citations."""
    from app.rules import _parse_ruling_cache, build_ruling_markdown

    source_result = {
        "question": "Q",
        "answer": "A",
        "why": "W",
        "source": "Book p. 1 — Section",
        "citations": [
            {"book": "Book", "page": "1", "section": "Section", "url": "https://x"}
        ],
        "marker": "source",
        "topic": "flanking",
        "query_embedding": [0.1, 0.2],
        "embedding_model": "m",
    }
    md = build_ruling_markdown(source_result)
    parsed = _parse_ruling_cache(md)
    assert parsed is not None
    assert parsed["marker"] == "source"
    assert parsed["citations"] == source_result["citations"]


def test_parse_ruling_cache_malformed_returns_none():
    """Missing --- frontmatter fences → returns None (no raise)."""
    from app.rules import _parse_ruling_cache

    assert _parse_ruling_cache("no frontmatter at all, just text") is None
    assert _parse_ruling_cache("") is None


# ---------------------------------------------------------------------------
# _validate_ruling_shape — CR-02 analog for D-08 response shape
# ---------------------------------------------------------------------------


def test_validate_ruling_shape_rejects_missing_answer():
    """Missing 'answer' key in LLM-produced dict → ValueError."""
    from app.rules import _validate_ruling_shape

    with pytest.raises(ValueError):
        _validate_ruling_shape({
            "question": "Q",
            "why": "W",
            "source": None,
            "citations": [],
            "marker": "generated",
            "topic": "misc",
        })


def test_validate_ruling_shape_rejects_citations_not_list():
    """citations must be a list — string 'oops' → ValueError."""
    from app.rules import _validate_ruling_shape

    with pytest.raises(ValueError):
        _validate_ruling_shape({
            "question": "Q",
            "answer": "A",
            "why": "W",
            "source": None,
            "citations": "oops",
            "marker": "generated",
            "topic": "misc",
        })


def test_validate_ruling_shape_accepts_minimal_valid():
    """Valid dict with all D-08 keys and correct types does not raise."""
    from app.rules import _validate_ruling_shape

    _validate_ruling_shape({
        "question": "Q",
        "answer": "A",
        "why": "W",
        "source": None,
        "citations": [],
        "marker": "generated",
        "topic": "misc",
    })


# ---------------------------------------------------------------------------
# Input sanitiser — MAX_QUERY_CHARS cap + unicode acceptance
# ---------------------------------------------------------------------------


def test_empty_query_rejected():
    """Empty query → ValueError (can't adjudicate nothing)."""
    from app.routes.rule import _validate_rule_query

    with pytest.raises(ValueError):
        _validate_rule_query("")


def test_query_too_long_rejected():
    """Query over MAX_QUERY_CHARS (500) → ValueError (DoS cap)."""
    from app.routes.rule import _validate_rule_query

    with pytest.raises(ValueError):
        _validate_rule_query("x" * 501)


def test_unicode_query_accepted():
    """Unicode in query does NOT raise (sha1-based hash handles any bytes)."""
    from app.routes.rule import _validate_rule_query

    # Should not raise
    _validate_rule_query("测试 rules")


# ---------------------------------------------------------------------------
# coerce_topic — L-6 empty-slug cache-collision prevention
# ---------------------------------------------------------------------------


def test_coerce_topic_passes_valid_slug():
    """A slug in RULE_TOPIC_SLUGS passes through unchanged."""
    from app.rules import coerce_topic

    assert coerce_topic("flanking") == "flanking"


def test_coerce_topic_rejects_empty_returns_misc():
    """Empty string → 'misc' (prevents empty-slug cache path collision — L-6)."""
    from app.rules import coerce_topic

    assert coerce_topic("") == "misc"


def test_coerce_topic_rejects_unknown_returns_misc():
    """Slug outside vocabulary → 'misc' (prevents folder sprawl — L-6)."""
    from app.rules import coerce_topic

    assert coerce_topic("flank-attack") == "misc"


# ---------------------------------------------------------------------------
# Threshold constants — RETRIEVAL (0.65 Wave-2 calibrated) + REUSE (D-05 0.80)
# ---------------------------------------------------------------------------


def test_retrieval_threshold_constants_present():
    """Thresholds: RETRIEVAL (Wave-2 calibrated) + REUSE (D-05 user-locked).

    RETRIEVAL_SIMILARITY_THRESHOLD was calibrated in Wave 2 against the 20-query
    fixture (tests/fixtures/rules_threshold_calibration.json) using LM Studio's
    text-embedding-nomic-embed-text-v1.5 — the F1-maximizer is 0.65 (see the
    Plan 33-03 SUMMARY §Threshold Calibration for the full sweep table).

    REUSE_SIMILARITY_THRESHOLD=0.80 is D-05 user-locked (CONTEXT.md) and must
    never drift without a new user decision.
    """
    from app.rules import (
        RETRIEVAL_SIMILARITY_THRESHOLD,
        REUSE_SIMILARITY_THRESHOLD,
    )

    assert RETRIEVAL_SIMILARITY_THRESHOLD == 0.65
    assert REUSE_SIMILARITY_THRESHOLD == 0.80
