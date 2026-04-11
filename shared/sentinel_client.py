"""Canonical HTTP client for Sentinel Core — used by all interfaces."""

import httpx
import logging

logger = logging.getLogger(__name__)


class SentinelCoreClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 200.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def send_message(self, user_id: str, content: str, client: httpx.AsyncClient) -> str:
        try:
            resp = await client.post(
                f"{self._base_url}/message",
                json={"content": content, "user_id": user_id},
                headers={"X-Sentinel-Key": self._api_key},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json()["content"]
        except httpx.TimeoutException:
            logger.error("Core request timed out after %ss", self._timeout)
            return "The Sentinel took too long to respond. Try again."
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                logger.error("Auth mismatch — check SENTINEL_API_KEY")
                return "Authentication error. Check configuration."
            if status == 422:
                logger.warning("Context too long for model window")
                return "Your message plus context is too long. Try a shorter message."
            logger.error("Core returned HTTP %d: %s", status, exc.response.text)
            return f"Something went wrong (HTTP {status})."
        except httpx.ConnectError:
            logger.error("Cannot reach Sentinel Core at %s", self._base_url)
            return "Cannot reach the Sentinel. Is sentinel-core running?"
        except Exception as exc:
            logger.exception("Unexpected error calling Core: %s", exc)
            return "An unexpected error occurred."
