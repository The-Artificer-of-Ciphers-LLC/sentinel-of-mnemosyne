"""
LlamaCppProvider — stub implementation of AIProvider Protocol.

llama.cpp runs as an OpenAI-compatible server (llama-server).
Config: LLAMACPP_BASE_URL=http://<host>:8080, LLAMACPP_MODEL=<model-name>.
LiteLLM prefix: "openai/<model>" with api_base pointing to llama-server endpoint.

This stub raises NotImplementedError. Ollama (OllamaProvider) is preferred over raw
llama.cpp — Ollama IS llama.cpp + Docker + API management. Use Ollama unless you
have a specific reason to run llama-server directly.

Phase 4 scope: stub only.
"""
import logging

logger = logging.getLogger(__name__)


class LlamaCppProvider:
    """
    Stub AI provider for llama.cpp server (OpenAI-compatible).
    Raises NotImplementedError on complete().
    Prefer OllamaProvider — it wraps llama.cpp with better management.
    """

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url
        self._model = model
        logger.info(
            f"LlamaCppProvider configured: base_url={base_url}, model={model}. "
            "Note: LlamaCppProvider is a stub — complete() raises NotImplementedError."
        )

    async def complete(self, messages: list[dict]) -> str:
        raise NotImplementedError(
            "LlamaCppProvider is not yet implemented. "
            f"To use llama.cpp server (model: {self._model}): "
            "1. Run llama-server with --port 8080 --host 0.0.0.0. "
            "2. Implement LlamaCppProvider.complete() using litellm with "
            f"model='openai/{self._model}', api_base='{self._base_url}/v1'. "
            "Consider using OllamaProvider instead — Ollama manages llama.cpp automatically."
        )
