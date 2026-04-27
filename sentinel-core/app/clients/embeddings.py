"""LM Studio embedding client.

Wraps litellm.aembedding so the vault sweeper can compute note embeddings
without app/ business logic touching the litellm SDK directly. Lives in
app/clients/ which is exempt from the AI-agnostic guardrail (the guardrail
allows vendor SDK access only inside config.py and clients/).
"""
from __future__ import annotations

import litellm

EMBEDDING_MODEL_DEFAULT = "openai/text-embedding-nomic-embed-text-v1.5"


async def embed_texts(
    texts: list[str],
    *,
    api_base: str,
    model: str = EMBEDDING_MODEL_DEFAULT,
    timeout: float = 60.0,
) -> list[list[float]]:
    """Return one float-vector per input text. Caller handles failures."""
    resp = await litellm.aembedding(
        model=model,
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
