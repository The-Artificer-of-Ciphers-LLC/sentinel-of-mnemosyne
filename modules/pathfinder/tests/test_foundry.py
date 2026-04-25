"""Tests for foundry route and helpers (FVT-01, FVT-02, FVT-03).

Wave 0 RED stubs — symbols referenced below land in:
  - app.routes.foundry (Wave 1 / Plan 35-02)
  - app.foundry helpers (Wave 1 / Plan 35-02)
  - app.main REGISTRATION_PAYLOAD (Wave 3 / Plan 35-04)

Imports are function-scope inside each test so pytest collection succeeds
before the implementation lands (pattern from Phase 33/34 Wave 0).
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# FVT-01 — Route auth + payload validation
# ---------------------------------------------------------------------------

async def test_roll_event_accepted():
    """POST /foundry/event with valid roll payload + correct X-Sentinel-Key → 200 (FVT-01)."""
    from app.main import app

    payload = {
        "event_type": "roll",
        "roll_type": "attack-roll",
        "actor_name": "Seraphina",
        "target_name": "Goblin Warchief",
        "outcome": "criticalSuccess",
        "roll_total": 28,
        "dc": 14,
        "dc_hidden": False,
        "item_name": "Longsword +1",
        "timestamp": "2026-04-25T19:42:00Z",
    }
    with patch("app.foundry.generate_foundry_narrative", new=AsyncMock(return_value="Seraphina struck true.")):
        with patch("app.foundry.notify_discord_bot", new=AsyncMock()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/foundry/event",
                    json=payload,
                    headers={"X-Sentinel-Key": "test-key-for-pytest"},
                )
    assert resp.status_code == 200


async def test_auth_rejected():
    """POST /foundry/event with wrong X-Sentinel-Key → 401 (FVT-01)."""
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/foundry/event",
            json={
                "event_type": "roll",
                "actor_name": "X",
                "outcome": "success",
                "roll_total": 10,
                "roll_type": "attack-roll",
                "timestamp": "2026-04-25T00:00:00Z",
            },
            headers={"X-Sentinel-Key": "wrong-key"},
        )
    assert resp.status_code == 401


async def test_invalid_payload():
    """POST /foundry/event missing required fields → 422 (FVT-01)."""
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/foundry/event",
            json={"event_type": "roll"},  # missing actor_name, outcome, roll_total, etc.
            headers={"X-Sentinel-Key": "test-key-for-pytest"},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# FVT-02 — Notify dispatch + LLM fallback
# ---------------------------------------------------------------------------

async def test_notify_dispatched():
    """Roll event dispatches notify_discord_bot with embed payload (FVT-02)."""
    from app.main import app

    with patch("app.foundry.generate_foundry_narrative", new=AsyncMock(return_value="A bold strike.")):
        with patch("app.foundry.notify_discord_bot", new=AsyncMock()) as mock_notify:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/foundry/event",
                    json={
                        "event_type": "roll",
                        "roll_type": "attack-roll",
                        "actor_name": "Sera",
                        "outcome": "success",
                        "roll_total": 18,
                        "dc": 14,
                        "dc_hidden": False,
                        "timestamp": "2026-04-25T19:42:00Z",
                    },
                    headers={"X-Sentinel-Key": "test-key-for-pytest"},
                )
    assert resp.status_code == 200
    mock_notify.assert_called_once()
    notify_payload = mock_notify.call_args[0][0]
    assert notify_payload.get("outcome") == "success"
    assert notify_payload.get("narrative") == "A bold strike."


async def test_llm_fallback():
    """LLM timeout → plain-text fallback text in notify payload; embed still dispatched (FVT-02, D-13)."""
    from app.main import app

    with patch("litellm.acompletion", new=AsyncMock(side_effect=Exception("timeout"))):
        with patch("app.foundry.notify_discord_bot", new=AsyncMock()) as mock_notify:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/foundry/event",
                    json={
                        "event_type": "roll",
                        "roll_type": "attack-roll",
                        "actor_name": "Sera",
                        "outcome": "success",
                        "roll_total": 18,
                        "dc": 14,
                        "dc_hidden": False,
                        "timestamp": "2026-04-25T19:42:00Z",
                    },
                    headers={"X-Sentinel-Key": "test-key-for-pytest"},
                )
    assert resp.status_code == 200
    mock_notify.assert_called_once()
    notify_payload = mock_notify.call_args[0][0]
    # D-13: fallback text present — plain string not empty
    assert notify_payload.get("narrative")


# ---------------------------------------------------------------------------
# FVT-01..03 — REGISTRATION_PAYLOAD
# ---------------------------------------------------------------------------

async def test_registration_payload():
    """'foundry/event' appears in REGISTRATION_PAYLOAD routes list (D-09, FVT-01..03)."""
    from app.main import REGISTRATION_PAYLOAD

    paths = [r["path"] for r in REGISTRATION_PAYLOAD["routes"]]
    assert "foundry/event" in paths
