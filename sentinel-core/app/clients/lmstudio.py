"""
Async HTTP client for LM Studio OpenAI-compatible API.
LM Studio runs on the Mac Mini; accessed via host.docker.internal from containers.
"""
import httpx


async def get_context_window(
    client: httpx.AsyncClient,
    base_url: str,
    model_name: str,
) -> int:
    """
    Fetch max_context_length from LM Studio /api/v0/models/{model_name}.
    Returns 4096 (conservative default) if LM Studio is unavailable at startup.
    Note: base_url is /v1 URL; this function strips /v1 to reach /api/v0/.
    """
    api_base = base_url.rstrip("/").removesuffix("/v1")
    try:
        resp = await client.get(f"{api_base}/api/v0/models/{model_name}", timeout=5.0)
        resp.raise_for_status()
        return int(resp.json().get("max_context_length", 4096))
    except Exception:
        return 4096  # conservative default; lifespan logs this


class LMStudioClient:
    """Thin wrapper around LM Studio's OpenAI-compatible completions endpoint."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        base_url: str,
        model_name: str,
        num_ctx: int = 8192,
    ) -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._num_ctx = num_ctx

    async def complete(self, messages: list[dict]) -> str:
        """
        Submit messages to /v1/chat/completions and return assistant content.
        Raises httpx.ConnectError if LM Studio is unreachable (caller handles as 503).
        """
        payload = {
            "model": self._model_name,
            "messages": messages,
            "num_ctx": self._num_ctx,
        }
        resp = await self._client.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            timeout=180.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
