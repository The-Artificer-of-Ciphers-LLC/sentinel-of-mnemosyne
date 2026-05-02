"""LM Studio embedding client.

Wraps litellm.aembedding so the vault sweeper can compute note embeddings
without app/ business logic touching the litellm SDK directly. Lives in
app/clients/ which is exempt from the AI-agnostic guardrail (the guardrail
allows vendor SDK access only inside config.py and clients/).
"""
from __future__ import annotations

import litellm


def _default_model() -> str:
    """Resolve the configured embedding model id at call time.

    Lazy lookup (not import-time) so test monkeypatching of
    ``app.config.settings.embedding_model`` takes effect, and so a missing
    settings import doesn't break the module on first load. Returns the
    historical default if settings is unavailable for any reason.
    """
    try:
        from app.config import settings
        configured = settings.embedding_model
        if configured:
            return f"openai/{configured}"
    except Exception:
        pass
    return "openai/text-embedding-nomic-embed-text-v1.5"


async def embed_texts(
    texts: list[str],
    *,
    api_base: str,
    model: str | None = None,
    timeout: float = 60.0,
) -> list[list[float]]:
    """Return one float-vector per input text. Caller handles failures.

    ``model`` defaults to ``f"openai/{settings.embedding_model}"`` resolved at
    call time. Callers that pass an explicit ``model=`` win.
    """
    resolved_model = model or _default_model()
    resp = await litellm.aembedding(
        model=resolved_model,
        input=list(texts),
        api_base=api_base,
        timeout=timeout,
    )
    data = resp["data"] if isinstance(resp, dict) else resp.data
    out: list[list[float]] = []
    for item in data:
        emb = item["embedding"] if isinstance(item, dict) else item.embedding
        out.append([float(x) for x in emb])
    return out
