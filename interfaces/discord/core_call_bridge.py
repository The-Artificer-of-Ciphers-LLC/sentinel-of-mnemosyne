"""Bridge wrapper for core chat call."""

from __future__ import annotations

import httpx


async def call_core_message(*, sent_client, user_id: str, message: str) -> str:
    async with httpx.AsyncClient() as http_client:
        return await sent_client.send_message(user_id, message, http_client)
