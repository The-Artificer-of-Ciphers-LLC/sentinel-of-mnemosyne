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
    request.app.state.module_registry[registration.name] = registration
    return JSONResponse({"status": "registered"})


@router.post("/modules/{name}/{path:path}")
async def proxy_module(name: str, path: str, request: Request) -> JSONResponse:
    """Proxy a request to a registered module endpoint.

    Forwards the request body to module.base_url/{path} via the shared httpx client.
    Returns 404 if the module is not registered, 503 if the module is unreachable.
    """
    registry = request.app.state.module_registry
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Module '{name}' not registered")
    module = registry[name]
    target_url = f"{module.base_url.rstrip('/')}/{path}"
    body = await request.body()
    # Forward X-Sentinel-Key to the module so it can verify the request comes from sentinel-core.
    # Per ARCHITECTURE-Core.md §3.4: all modules receive SENTINEL_API_KEY for auth.
    # Without forwarding, modules that enforce auth will reject the proxy call with 401 (seen as 503).
    sentinel_key = request.headers.get("X-Sentinel-Key", "")
    try:
        resp = await request.app.state.http_client.post(
            target_url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Sentinel-Key": sentinel_key,
            },
        )
        try:
            content = resp.json()
        except Exception:
            content = {"body": resp.text}
        return JSONResponse(content=content, status_code=resp.status_code)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail={"error": "module unavailable"})
