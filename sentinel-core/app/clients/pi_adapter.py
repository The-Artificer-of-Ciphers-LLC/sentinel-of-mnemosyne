"""
HTTP client for Pi harness bridge.
Sentinel Core calls the Pi harness over HTTP — it never imports pi-mono directly.
The pi-harness container is the single point of contact with @mariozechner/pi-coding-agent.
"""
import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class PiAdapterClient:
    """HTTP client for the Pi harness Fastify bridge."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        harness_url: str,
        timeout_s: float = 90.0,
    ) -> None:
        self._client = http_client
        self._harness_url = harness_url.rstrip("/")
        self._timeout_s = timeout_s

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
            timeout=self._timeout_s,
        )
        resp.raise_for_status()
        return resp.json()["content"]

    async def reset_session(self) -> None:
        """
        Reset the Pi harness session by sending new_session RPC.
        Fire-and-forget: failures are logged and swallowed so a reset error
        never blocks a user request.
        """
        try:
            resp = await self._client.post(
                f"{self._harness_url}/session/reset",
                timeout=5.0,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning(f"Pi harness session reset failed (continuing): {exc}")
