"""
OllamaProvider — stub implementation of AIProvider Protocol.

Ollama runs on the Linux workstation with Nvidia A2000 (12GB VRAM).
Recommended model: Qwen 2.5 14B Q4_K_M (~10-11GB VRAM).
Docker setup: ollama/ollama image, deploy.resources.reservations.devices (nvidia-container-toolkit).
Binding: set OLLAMA_HOST=0.0.0.0 in Ollama container for cross-machine access.

This stub raises NotImplementedError — configure OLLAMA_BASE_URL and OLLAMA_MODEL
in your environment, then implement this class when the workstation is ready.

Phase 4 scope: stub only. Full implementation deferred (GPU workstation infrastructure work).
"""
import logging

logger = logging.getLogger(__name__)


class OllamaProvider:
    """
    Stub AI provider for Ollama on Linux workstation.
    Raises NotImplementedError on complete() — set AI_PROVIDER=ollama only when implemented.
    """

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url
        self._model = model
        logger.info(
            f"OllamaProvider configured: base_url={base_url}, model={model}. "
            "Note: OllamaProvider is a stub — complete() raises NotImplementedError."
        )

    async def complete(self, messages: list[dict]) -> str:
        raise NotImplementedError(
            "OllamaProvider is not yet implemented. "
            f"To use Ollama (model: {self._model}): "
            "1. Ensure nvidia-container-toolkit is installed on the Linux workstation. "
            "2. Run ollama/ollama Docker image with GPU device reservations. "
            "3. Set OLLAMA_HOST=0.0.0.0 in the Ollama container for cross-machine access. "
            "4. Implement OllamaProvider.complete() using litellm with model prefix 'ollama/<model>'. "
            "See CONTEXT.md Phase 4 Ollama section for full setup details."
        )
