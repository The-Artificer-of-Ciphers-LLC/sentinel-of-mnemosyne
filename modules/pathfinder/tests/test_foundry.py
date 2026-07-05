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

import httpx
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
    assert resp.status_code != 401, "Auth rejected before Pydantic validation — test is incorrect"
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
    """LLM timeout → plain-text fallback text in notify payload; embed still dispatched (FVT-02, D-13).

    Phase 42-05 (D-09, SC-6): the roll-narration call site reaches the LLM via
    `app.foundry._core_client.complete()`, not litellm directly — patch the
    core client singleton instead of litellm.acompletion.
    """
    from app.main import app

    with patch("app.foundry._core_client.complete", new=AsyncMock(side_effect=Exception("timeout"))):
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
# Phase 42-05 (D-09, SC-6) — generate_foundry_narrative core-client handoff
# ---------------------------------------------------------------------------
# Direct unit tests of app.foundry.generate_foundry_narrative, mirroring the
# 42-04 test_llm_core_handoff.py pattern: patch the module-level _core_client
# singleton's complete() method and assert (1) no model/api_base forwarded,
# (2) result["content"] is consumed correctly, (3) complete() raising is
# caught by the function's own try/except and degrades to "" (D-13 — never
# raises), matching acompletion_with_profile's pre-migration failure posture.


async def test_generate_foundry_narrative_consumes_core_client_content():
    from app.foundry import generate_foundry_narrative

    with patch(
        "app.foundry._core_client.complete",
        new=AsyncMock(return_value={"content": "Seraphina struck true.", "model": "test-model"}),
    ) as mock_complete:
        result = await generate_foundry_narrative(
            actor_name="Seraphina",
            target_name="Goblin Warchief",
            item_name="Longsword +1",
            outcome="criticalSuccess",
            roll_total=28,
            dc=14,
        )

    assert result == "Seraphina struck true."
    mock_complete.assert_awaited_once()
    kwargs = mock_complete.await_args.kwargs
    assert "messages" in kwargs
    assert "client" in kwargs
    # SC-6/D-09: no model/api_base forwarded to core — core resolves both.
    assert "model" not in kwargs
    assert "api_base" not in kwargs


async def test_generate_foundry_narrative_core_raise_degrades_to_empty_string():
    """complete() raising is caught by generate_foundry_narrative's own
    try/except (D-13 fallback policy) — never propagates, returns ""."""
    from app.foundry import generate_foundry_narrative

    with patch(
        "app.foundry._core_client.complete",
        new=AsyncMock(side_effect=httpx.ConnectError("core unreachable")),
    ):
        result = await generate_foundry_narrative(
            actor_name="Sera",
            target_name=None,
            item_name=None,
            outcome="success",
            roll_total=18,
            dc=14,
        )

    assert result == ""


# ---------------------------------------------------------------------------
# FVT-01..03 — REGISTRATION_PAYLOAD
# ---------------------------------------------------------------------------

async def test_registration_payload():
    """'foundry/event' appears in REGISTRATION_PAYLOAD routes list (D-09, FVT-01..03)."""
    from app.main import REGISTRATION_PAYLOAD

    paths = [r["path"] for r in REGISTRATION_PAYLOAD["routes"]]
    assert "foundry/event" in paths
