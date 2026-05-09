"""Discord response rendering adapter."""

from __future__ import annotations

import io

import discord


async def send_rendered_response(send_fn, response: "str | dict") -> None:
    """Render router response via provided async send function.

    Empty-string responses are a sentinel from upstream handlers that have
    already posted their final message directly (e.g. dialog cancel/completion
    needs to send before archiving — see UAT G-04). Skip the send entirely.
    """
    if isinstance(response, str):
        if not response:
            return
        await send_fn(response)
        return

    if isinstance(response, dict):
        rtype = response.get("type")
        if rtype == "file":
            df = discord.File(
                io.BytesIO(response["file_bytes"]),
                filename=response["filename"],
            )
            await send_fn(content=response.get("content", ""), file=df)
            return
        if rtype == "embed":
            await send_fn(content=response.get("content", ""), embed=response["embed"])
            return
        await send_fn(response.get("content", str(response)))
        return

    await send_fn(str(response))
