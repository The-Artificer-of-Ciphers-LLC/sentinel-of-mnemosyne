"""Module gateway forwarding logic.

Provides a single seam for forwarding requests to registered module endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from starlette.responses import JSONResponse


@dataclass(frozen=True)
class ModuleForwardResult:
    content: Any
    status_code: int

def target_url_for(module: Any, path: str) -> str:
    return f"{module.base_url.rstrip('/')}/{path}"


async def forward_get(
    http_client: httpx.AsyncClient,
    target_url: str,
    sentinel_key: str,
) -> ModuleForwardResult:
    resp = await http_client.get(
        target_url,
        headers={"X-Sentinel-Key": sentinel_key},
    )
    try:
        content = resp.json()
    except ValueError:
        content = {"body": resp.text}
    return ModuleForwardResult(content=content, status_code=resp.status_code)


async def forward_post(
    http_client: httpx.AsyncClient,
    target_url: str,
    body: bytes,
    sentinel_key: str,
    timeout: float = 120.0,
) -> ModuleForwardResult:
    resp = await http_client.post(
        target_url,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Sentinel-Key": sentinel_key,
        },
        timeout=timeout,
    )
    try:
        content = resp.json()
    except ValueError:
        content = {"body": resp.text}
    return ModuleForwardResult(content=content, status_code=resp.status_code)


def to_json_response(result: ModuleForwardResult) -> JSONResponse:
    return JSONResponse(content=result.content, status_code=result.status_code)
