"""
Anthropic model registry helper.

Fetches live model metadata from the Anthropic API using the SDK.
Lives in app/clients/ — vendor SDK usage is permitted here.
Called by app/services/model_registry.py at startup.
"""
import logging

logger = logging.getLogger(__name__)


async def fetch_anthropic_models(api_key: str) -> dict:
    """
    Fetch model list from Anthropic SDK.
    Returns dict of {model_id: ModelInfo-compatible dict}.
    Falls back to empty dict if key absent or API fails.

    Vendor SDK import is intentionally local to this file (app/clients/).
    """
    try:
        import anthropic  # noqa: PLC0415

        aclient = anthropic.AsyncAnthropic(api_key=api_key)
        models_page = await aclient.models.list()
        result: dict[str, dict] = {}
        for m in models_page.data:
            result[m.id] = {
                "id": m.id,
                "provider": "claude",
                "context_window": getattr(m, "context_window", 200000),
                "capabilities": {"chat": True, "function_calling": True},
                "notes": "Fetched from Anthropic API at startup",
            }
        logger.info(f"Claude models fetched: {list(result.keys())}")
        return result
    except Exception as exc:
        logger.warning(f"Claude model registry fetch failed: {exc} — using seed fallback")
        return {}
