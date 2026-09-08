"""
Model registry — seed data, plus a live fetch for the providers that have one.

Loads models-seed.json (always) and merges whatever a provider's own API can
add. Stored in app.state.model_registry as dict[str, ModelInfo].

Per-provider live fetch:
  LM Studio: none of its own — see below.
  Claude:    Anthropic SDK models.list() → max_input_tokens (or seed fallback)
  Ollama:    POST /api/show → model_info.llama.context_length (stub — seed only)
  llama.cpp: GET /props → n_ctx (stub — seed only)

**ADR-0007 step 4 removed this module's LM Studio live path.** It used to call
``discover_active_model`` (a ``/v1/models`` fetch plus a scoring pass) and then
``get_context_window_from_lmstudio`` (a second, per-model
``/api/v0/models/{id}`` fetch) — two of the three independent startup fetches
the Active model seam collapsed into one model-list call. LM Studio's model
identity and window are now resolved by ``ActiveModel`` and handed in through
``lmstudio_model`` / ``lmstudio_context_window``; the registry keeps only its
seed role, which is what ``StaticModelSource`` reads.
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.clients.anthropic_registry import fetch_anthropic_models
from app.config import Settings

logger = logging.getLogger(__name__)

# Path to seed file — relative to sentinel-core/ project root
_SEED_PATH = Path(__file__).parent.parent.parent / "models-seed.json"


@dataclass
class ModelInfo:
    """Context window size and capability flags for a model."""

    id: str
    provider: str
    context_window: int
    capabilities: dict = field(default_factory=dict)
    notes: str = ""


def _load_seed() -> dict[str, "ModelInfo"]:
    """Load models-seed.json. Returns empty dict on any error (non-fatal)."""
    try:
        with open(_SEED_PATH) as f:
            data = json.load(f)
        result: dict[str, ModelInfo] = {}
        for m in data.get("models", []):
            info = ModelInfo(
                id=m["id"],
                provider=m.get("provider", "unknown"),
                context_window=m.get("context_window", 4096),
                capabilities=m.get("capabilities", {}),
                notes=m.get("notes", ""),
            )
            result[info.id] = info
        logger.info(f"Model registry seed loaded: {list(result.keys())}")
        return result
    except Exception as exc:
        logger.warning(f"Failed to load models-seed.json: {exc} — registry will be empty")
        return {}


async def _fetch_claude(settings: Settings) -> dict[str, "ModelInfo"]:
    """
    Fetch model list from Anthropic API via app/clients/anthropic_registry.py.
    Returns dict of ModelInfo. Falls back to empty dict if key absent or API fails.
    Vendor SDK import lives in app/clients/ — not here.
    """
    if not settings.anthropic_api_key:
        logger.info("ANTHROPIC_API_KEY not set — skipping Claude live model fetch, using seed")
        return {}
    raw = await fetch_anthropic_models(settings.anthropic_api_key)
    return {
        model_id: ModelInfo(
            id=info["id"],
            provider=info["provider"],
            context_window=info["context_window"],
            capabilities=info["capabilities"],
            notes=info["notes"],
        )
        for model_id, info in raw.items()
    }


async def build_model_registry(
    settings: Settings,
    http_client: httpx.AsyncClient,
    *,
    lmstudio_model: str | None = None,
    lmstudio_context_window: int | None = None,
) -> dict[str, ModelInfo]:
    """
    Build the model registry at startup.
    1. Load seed data (always)
    2. Fetch live data from the active provider where that provider has a live
       source of its own (best-effort, non-fatal)
    3. Merge: live data takes precedence over seed for overlapping model ids
    Returns dict[model_id, ModelInfo] stored in app.state.model_registry.

    ``lmstudio_model`` / ``lmstudio_context_window``: LM Studio's model identity
    and window are resolved by the Active model seam (ADR-0007), never by this
    function. When the caller passes both, the resolved answer is recorded here
    so downstream registry readers see the model that is actually loaded. When
    it does not, LM Studio contributes NOTHING and the registry is seed-only for
    that provider — deliberately, because the alternative is this module making
    its own discovery + per-model context fetch, which is the duplicate
    implementation step 4 removes. This function issues no LM Studio HTTP under
    any argument combination.
    """
    registry = _load_seed()

    if settings.ai_provider == "lmstudio":
        if lmstudio_model and lmstudio_context_window:
            registry[lmstudio_model] = ModelInfo(
                id=lmstudio_model,
                provider="lmstudio",
                context_window=lmstudio_context_window,
                capabilities={"chat": True},
                notes="Resolved by the Active model seam (ADR-0007)",
            )
        else:
            logger.info(
                "LM Studio registry entry not supplied by the Active model seam — "
                "using seed data only; no discovery or context fetch is performed here"
            )
    elif settings.ai_provider == "claude":
        live = await _fetch_claude(settings)
        registry.update(live)
    elif settings.ai_provider == "ollama":
        logger.info("Ollama registry fetch: stub only — using seed data")
    elif settings.ai_provider == "llamacpp":
        logger.info("llama.cpp registry fetch: stub only — using seed data")
    else:
        logger.warning(
            f"Unknown AI_PROVIDER '{settings.ai_provider}' — using seed-only registry"
        )

    # Also fetch fallback provider registry if configured
    if settings.ai_fallback_provider == "claude" and settings.ai_provider != "claude":
        live = await _fetch_claude(settings)
        registry.update(live)

    logger.info(f"Model registry ready: {len(registry)} models — {list(registry.keys())}")
    return registry
