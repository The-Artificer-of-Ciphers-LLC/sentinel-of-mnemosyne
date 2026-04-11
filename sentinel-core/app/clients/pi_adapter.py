"""
HTTP client for Pi harness bridge.
Sentinel Core calls the Pi harness over HTTP — it never imports pi-mono directly.
The pi-harness container is the single point of contact with @mariozechner/pi-coding-agent.
"""
import os

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

PI_TIMEOUT_S = float(os.getenv("PI_TIMEOUT_S", "190"))


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
            timeout=PI_TIMEOUT_S,  # configurable via PI_TIMEOUT_S env var (default 190; Pi has 180s timeout)
        )
        resp.raise_for_status()
        return resp.json()["content"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        reraise=True,
    )
    async def send_messages(self, messages: list[dict]) -> str:
        """
        Send a messages array to Pi harness POST /prompt.
        Bridge serializes the array to a string before calling Pi RPC.
        Returns the AI response content string.
        Retries 3 times with exponential backoff on ConnectError/TimeoutException (PROV-03).
        Raises httpx.ConnectError if Pi harness is unreachable after all retries.
        Raises httpx.HTTPStatusError for error responses from Pi harness.
        """
        resp = await self._client.post(
            f"{self._harness_url}/prompt",
            json={"messages": messages},
            timeout=30.0,  # hard 30s ceiling per call (PROV-03)
        )
        resp.raise_for_status()
        return resp.json()["content"]
