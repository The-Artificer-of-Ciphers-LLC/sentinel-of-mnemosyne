"""
Live HTTP integration tests for sentinel-core API.
Requires a running sentinel-core instance. Guard: set LIVE_TEST=1 to enable.
"""
import os
import uuid

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("LIVE_TEST"),
    reason="requires LIVE_TEST=1 and running sentinel-core",
)

BASE_URL = os.getenv("SENTINEL_CORE_URL", "http://localhost:8000")
API_KEY = os.getenv("SENTINEL_API_KEY", "test-sentinel-key")
AUTH = {"X-Sentinel-Key": API_KEY}


# ---------------------------------------------------------------------------
# 1. GET /health — no auth required
# ---------------------------------------------------------------------------


async def test_health():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# 2. GET /status — requires auth
# ---------------------------------------------------------------------------


async def test_status():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/status", headers=AUTH)
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


# ---------------------------------------------------------------------------
# 3–8. POST /message
# ---------------------------------------------------------------------------


async def test_message_happy_path():
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{BASE_URL}/message",
            json={"content": "Say hello", "user_id": "live-test"},
            headers=AUTH,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert len(data["content"]) > 0


async def test_message_no_auth():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/message",
            json={"content": "hello", "user_id": "live-test"},
        )
    assert resp.status_code == 401


async def test_message_wrong_auth():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/message",
            json={"content": "hello", "user_id": "live-test"},
            headers={"X-Sentinel-Key": "wrong"},
        )
    assert resp.status_code == 401


async def test_message_empty_content():
    """Empty content must be rejected (400 or 422) — not silently accepted."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/message",
            json={"content": "", "user_id": "live-test"},
            headers=AUTH,
        )
    assert resp.status_code in (400, 422)


async def test_message_missing_user_id():
    """Missing user_id triggers Pydantic validation error — 422."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/message",
            json={"content": "hello"},
            headers=AUTH,
        )
    assert resp.status_code == 422


async def test_message_token_overload():
    """50k character payload — must not 500; 200 or 422 are both acceptable."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{BASE_URL}/message",
            json={"content": "x" * 50000, "user_id": "live-test"},
            headers=AUTH,
        )
    assert resp.status_code in (200, 422), (
        f"Expected 200 or 422 for overload payload, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 9–10. POST /modules/register
# ---------------------------------------------------------------------------


async def test_modules_register_happy_path():
    module_name = f"uat-test-module-{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/modules/register",
            json={
                "name": module_name,
                "base_url": "http://localhost:19999",
                "routes": [{"path": "run", "description": "Run module"}],
            },
            headers=AUTH,
        )
    assert resp.status_code == 200
    assert resp.json() == {"status": "registered"}


async def test_modules_register_no_auth():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/modules/register",
            json={
                "name": "no-auth-module",
                "base_url": "http://localhost:19999",
                "routes": [{"path": "run", "description": "Run module"}],
            },
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 11. POST /modules/{unknown}/run — 404
# ---------------------------------------------------------------------------


async def test_modules_unknown_proxy():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/modules/nonexistent-module/run",
            json={},
            headers=AUTH,
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 12. POST /modules/{registered-down}/run — 503
# ---------------------------------------------------------------------------


async def test_modules_proxy_module_down():
    """Register a module pointing at nothing, then proxy to it — expect 503."""
    module_name = f"uat-down-module-{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient() as client:
        # Register a module with a base_url pointing at nothing
        reg_resp = await client.post(
            f"{BASE_URL}/modules/register",
            json={
                "name": module_name,
                "base_url": "http://localhost:19999",
                "routes": [{"path": "run", "description": "Run module"}],
            },
            headers=AUTH,
        )
    assert reg_resp.status_code == 200, (
        f"Registration failed — cannot proceed with proxy test: {reg_resp.text}"
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        proxy_resp = await client.post(
            f"{BASE_URL}/modules/{module_name}/run",
            json={},
            headers=AUTH,
        )
    assert proxy_resp.status_code == 503, (
        f"Expected 503 for unreachable module, got {proxy_resp.status_code}"
    )
