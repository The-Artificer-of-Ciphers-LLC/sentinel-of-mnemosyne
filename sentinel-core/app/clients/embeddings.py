"""LM Studio embedding client.

Wraps litellm.aembedding so the vault sweeper can compute note embeddings
without app/ business logic touching the litellm SDK directly. Lives in
app/clients/ which is exempt from the AI-agnostic guardrail (the guardrail
allows vendor SDK access only inside config.py and clients/).
"""
from __future__ import annotations

import litellm

from app.errors import EmbeddingModelUnavailable

DEFAULT_LMSTUDIO_BASE_URL = "http://host.docker.internal:1234"



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
    api_key: str = "lm-studio",
    timeout: float = 60.0,
) -> list[list[float]]:
    """Return one float-vector per input text. Caller handles failures.

    ``model`` defaults to ``f"openai/{settings.embedding_model}"`` resolved at
    call time. Callers that pass an explicit ``model=`` win.
    ``api_key`` must be non-empty for litellm even on local endpoints that
    don't actually validate it — defaults to "lm-studio".
    """
    resolved_model = model or _default_model()
    try:
        resp = await litellm.aembedding(
            model=resolved_model,
            input=list(texts),
            api_base=api_base,
            api_key=api_key,
            timeout=timeout,
        )
    except litellm.BadRequestError as exc:
        # LM Studio returns "No models loaded. Please load a model." as a
        # 400 BadRequest when the embedding model isn't loaded. Translate
        # to a typed exception so callers can distinguish operator-setup
        # problems from genuine bad-request bugs.
        if "no models loaded" in str(exc).lower():
            raise EmbeddingModelUnavailable(
                f"No embedding model loaded on LM Studio. Configured: "
                f"{resolved_model}. Load via `lms load {resolved_model}` "
                f"or LM Studio UI."
            ) from exc
        raise
    data = resp["data"] if isinstance(resp, dict) else resp.data
    out: list[list[float]] = []
    for item in data:
        emb = item["embedding"] if isinstance(item, dict) else item.embedding
        out.append([float(x) for x in emb])
    return out


class Embeddings:
    """Thin adapter over :func:`embed_texts` for compose-root injection.

    Replaces the ``_embedder_fn`` closure that used to live in lifespan(). Pin
    ``Embeddings(...).embed`` (the bound method) onto ``app.state.note_embedder_fn``
    to keep call sites byte-identical (`await embedder(texts)` → list[list[float]]).

    The base URL is normalised to ensure ``/v1`` suffix exactly once — matches
    the closure behavior. The model string is litellm-prefixed with
    ``openai/`` (provider prefix added at the call site, not stored in
    settings — 260502-1zv D-03).

    The ``http_client`` parameter is accepted for forward-compat with future
    clients that route through the shared httpx pool; the current
    ``embed_texts`` helper instantiates its own underlying transport via
    litellm and so the parameter is held but not yet consumed.
    """

    def __init__(
        self,
        http_client: object,
        base_url: str,
        model: str,
        api_key: str = "",
    ) -> None:
        self._http_client = http_client
        # /v1 suffix normalisation — ensure exactly one trailing /v1
        normalised = base_url.rstrip("/") if base_url else DEFAULT_LMSTUDIO_BASE_URL
        if not normalised.endswith("/v1"):
            normalised = f"{normalised}/v1"
        self._api_base = normalised
        # Provider prefix added here, not stored in settings (260502-1zv D-03)
        self._model = f"openai/{model}" if not model.startswith("openai/") else model
        # litellm requires a non-empty api_key even for local endpoints
        self._api_key = api_key or "lm-studio"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one float-vector per input text."""
        return await embed_texts(
            texts,
            api_base=self._api_base,
            model=self._model,
            api_key=self._api_key,
        )
