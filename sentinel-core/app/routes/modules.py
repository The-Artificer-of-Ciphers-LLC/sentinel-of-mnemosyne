"""
Module gateway router — Phase 27 Path B.

POST /modules/register  — register a module endpoint with sentinel-core
POST /modules/{name}/{path}  — proxy requests to a registered module

Authentication: APIKeyMiddleware (global) covers all routes — no per-route decoration needed.
Registry: in-memory dict stored in app.state.module_registry; populated at runtime.
"""
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse

from app.services.module_gateway import (
    forward_get,
    forward_post,
    target_url_for,
    to_json_response,
)
from app.services.module_registry import (
    list_modules_payload,
    register_module as register_module_entry,
    resolve_module,
)
from app.state import get_route_context

router = APIRouter()


class ModuleRoute(BaseModel):
    path: str
    description: str


class ModuleRegistration(BaseModel):
    name: str
    base_url: str
    routes: list[ModuleRoute]


@router.post("/modules/register")
async def register_module(registration: ModuleRegistration, request: Request) -> JSONResponse:
    """Register a module endpoint with sentinel-core.

    The module container calls this at startup. sentinel-core stores the registration
    in-memory and begins proxying /modules/{name}/{path} requests to the module's base_url.
    """
    ctx = get_route_context(request)
    register_module_entry(ctx.module_registry, registration)
    return JSONResponse({"status": "registered"})


@router.get("/modules")
async def list_modules(request: Request) -> JSONResponse:
    """List all registered modules with their metadata (D-09).

    Returns the module registry as a JSON list. Used by GET /modules to satisfy SC-2.
    """
    ctx = get_route_context(request)
    registry = ctx.module_registry
    result = list_modules_payload(registry)
    return JSONResponse(result)


@router.get("/modules/{name}/{path:path}")
async def get_proxy_module(name: str, path: str, request: Request) -> JSONResponse:
    """Proxy a GET request to a registered module endpoint (D-08)."""
    ctx = get_route_context(request)
    registry = ctx.module_registry
    try:
        module = resolve_module(registry, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Module '{name}' not registered")

    target_url = target_url_for(module, path)
    sentinel_key = request.headers.get("X-Sentinel-Key", "")
    try:
        result = await forward_get(ctx.http_client, target_url, sentinel_key)
        return to_json_response(result)
    except httpx.TransportError:
        raise HTTPException(status_code=503, detail={"error": "module unavailable"})


@router.post("/modules/{name}/{path:path}")
async def proxy_module(name: str, path: str, request: Request) -> JSONResponse:
    """Proxy a request to a registered module endpoint."""
    ctx = get_route_context(request)
    registry = ctx.module_registry
    try:
        module = resolve_module(registry, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Module '{name}' not registered")

    target_url = target_url_for(module, path)
    body = await request.body()
    sentinel_key = request.headers.get("X-Sentinel-Key", "")
    try:
        result = await forward_post(
            ctx.http_client,
            target_url,
            body,
            sentinel_key,
            timeout=120.0,
        )
        return to_json_response(result)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail={"error": "module timed out"})
    except httpx.TransportError:
        raise HTTPException(status_code=503, detail={"error": "module unavailable"})
