"""
POST /embeddings — narrow raw-embeddings passthrough (D-06, EMB-01).

Mirrors ``routes/provider.py``'s "everything through Sentinel" gateway
design for the embeddings backend. A domain module (e.g. pf2e-module) calls
this endpoint via ``SentinelCoreClient.embed()`` instead of hardcoding its
own embeddings endpoint/model. The route is a THIN passthrough to
``ctx.embedder`` — it does NOT reuse any part of the /message pipeline (no
memory recall, no prompt-injection filtering, no output scanning, no note
filing).

Authentication: APIKeyMiddleware (global, app/main.py) already covers every
non-/health route, including this one — no new auth code is added here.
"""
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.errors import EmbeddingModelUnavailable
from app.state import get_route_context

logger = logging.getLogger(__name__)

router = APIRouter()

# V5 (DoS guard): bounds worst-case embedding-backend cost/latency from a
# single request — rejected via 422 before any backend call. 200 gives
# generous headroom over pf2e's rules corpus (Open Question 2 — must exceed
# len(load_rules_corpus(...))).
_MAX_TEXTS = 200
# Mirrors provider.py's _MAX_CONTENT_LENGTH-style per-item cap pattern.
_MAX_TEXT_LENGTH = 8000


class EmbeddingsRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=_MAX_TEXTS)

    @field_validator("texts")
    @classmethod
    def _check_text_length(cls, value: list[str]) -> list[str]:
        for text in value:
            if len(text) > _MAX_TEXT_LENGTH:
                raise ValueError(
                    f"text exceeds max length of {_MAX_TEXT_LENGTH}"
                )
        return value


class EmbeddingsResponse(BaseModel):
    embeddings: list[list[float]]
    model: str


@router.post("/embeddings", response_model=EmbeddingsResponse)
async def post_embeddings(
    body: EmbeddingsRequest, request: Request
) -> EmbeddingsResponse:
    """Thin passthrough to ctx.embedder (D-06).

    Reuses no /message pipeline component — the caller supplies raw texts
    and gets raw vectors back. Backend selection (base_url/model) stays
    core-owned (D-04) — the request schema accepts ONLY ``texts``.
    """
    ctx = get_route_context(request)
    try:
        vectors = await ctx.embedder(body.texts)
    except EmbeddingModelUnavailable:
        # Generic detail only — never echo the underlying litellm/httpx
        # exception text, which may embed api_base/api_key (same T-42-08
        # precedent as /provider/complete).
        raise HTTPException(
            status_code=503, detail="Embedding backend unavailable"
        )

    return EmbeddingsResponse(
        embeddings=vectors,
        model=ctx.settings.embedding_model if ctx.settings else "",
    )
