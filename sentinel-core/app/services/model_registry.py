"""
Model registry — hybrid live-fetch + seed fallback.

Fetches context window sizes from provider APIs at startup.
Falls back to models-seed.json on any fetch failure (non-fatal).
Stored in app.state.model_registry as dict[str, ModelInfo].

Per-provider live fetch:
  LM Studio: GET /api/v0/models/{model_name} → max_context_length
  Claude:    Anthropic SDK models.list() → max_input_tokens (or seed fallback)
  Ollama:    POST /api/show → model_info.llama.context_length (stub — seed only)
  llama.cpp: GET /props → n_ctx (stub — seed only)
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.clients.litellm_provider import get_context_window_from_lmstudio
from app.config import Settings
from app.services.model_selector import discover_active_model

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


async def _fetch_lmstudio(
    settings: Settings, client: httpx.AsyncClient, discovered_name: str
) -> dict[str, "ModelInfo"]:
    """Fetch context window from LM Studio. Returns partial dict (discovered_name → ModelInfo)."""
    ctx = await get_context_window_from_lmstudio(
        client, settings.lmstudio_base_url, discovered_name
    )
    if ctx == 4096:
        logger.warning(
            f"LM Studio context window fetch failed — using 4096 default for model '{discovered_name}'"
        )
    else:
        logger.info(
            f"LM Studio: model '{discovered_name}' has {ctx} token context window"
        )
    return {
        discovered_name: ModelInfo(
            id=discovered_name,
            provider="lmstudio",
            context_window=ctx,
            capabilities={"chat": True},
            notes="Fetched from LM Studio at startup",
        )
    }


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
    settings: Settings, http_client: httpx.AsyncClient
) -> dict[str, ModelInfo]:
    """
    Build the model registry at startup.
    1. Load seed data (always)
    2. Fetch live data from active provider (best-effort, non-fatal)
    3. Merge: live data takes precedence over seed for overlapping model ids
    Returns dict[model_id, ModelInfo] stored in app.state.model_registry.
    """
    registry = _load_seed()

    if settings.ai_provider == "lmstudio":
        # Discover active model name (non-fatal; falls back to settings.model_name)
        model_str = await discover_active_model(settings, http_client)
        # Strip provider prefix for registry key (e.g. "openai/Qwen2.5" → "Qwen2.5")
        discovered_lmstudio_name = model_str.split("/", 1)[-1]
        live = await _fetch_lmstudio(settings, http_client, discovered_lmstudio_name)
        registry.update(live)
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
