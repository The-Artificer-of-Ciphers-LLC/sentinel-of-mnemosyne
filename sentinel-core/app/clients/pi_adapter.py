"""
HTTP client for Pi harness bridge.
Sentinel Core calls the Pi harness over HTTP — it never imports pi-mono directly.
The pi-harness container is the single point of contact with @mariozechner/pi-coding-agent.
"""
import httpx


class PiAdapterClient:
    """HTTP client for the Pi harness Fastify bridge."""

    def __init__(self, http_client: httpx.AsyncClient, harness_url: str) -> None:
        self._client = http_client
        self._harness_url = harness_url.rstrip("/")

    async def send_prompt(self, message: str) -> str:
        """
        Send a message to Pi harness POST /prompt.
        Returns the AI response content string.
        Raises httpx.ConnectError if Pi harness is unreachable (caller handles as 503).
        Raises httpx.HTTPStatusError for 503/504 from Pi harness.
        """
        resp = await self._client.post(
            f"{self._harness_url}/prompt",
            json={"message": message},
            timeout=190.0,  # Pi has 180s timeout; add 10s margin for large local models
        )
        resp.raise_for_status()
        return resp.json()["content"]
