"""
Integration test: LLM↔Obsidian pipeline validation (GAP-D).

Verifies that POST /message:
  1. Calls obsidian.read_self_context() for each self/ path
  2. Calls obsidian.get_recent_sessions() for the user
  3. Injects returned context into the messages array sent to ai_provider.complete()
  4. Returns a 200 response with the AI content

Uses httpx ASGITransport against the live app with mocked Obsidian + AI clients —
no live infrastructure required.
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app

AUTH_HEADERS = {"X-Sentinel-Key": "test-key-for-pytest"}

KNOWN_IDENTITY = "# Identity\nI am a software engineer focused on distributed systems."
KNOWN_SESSION = "## User\nWhat is my current goal?\n## Sentinel\nBuild the Sentinel platform."


@pytest.fixture(autouse=True)
def setup_app_state():
    """Inject mock state for all integration tests — no live infrastructure required."""
    # Mock ObsidianVault with known return values
    mock_obsidian = AsyncMock()
    mock_obsidian.read_self_context = AsyncMock(return_value="")
    mock_obsidian.read_self_context.side_effect = lambda path: (
        KNOWN_IDENTITY if path == "self/identity.md" else ""
    )
    mock_obsidian.get_recent_sessions = AsyncMock(return_value=[KNOWN_SESSION])
    mock_obsidian.find = AsyncMock(return_value=[])
    mock_obsidian.write_session_summary = AsyncMock(return_value=None)

    # Mock AI provider — returns a known response
    mock_ai_provider = AsyncMock()
    mock_ai_provider.complete = AsyncMock(return_value="Acknowledged. Your goal is the Sentinel platform.")

    # Mock injection filter — pass-through (no filtering for these tests)
    mock_filter = MagicMock()
    mock_filter.wrap_context = lambda text: text
    mock_filter.filter_input = lambda text: (text, False)

    # Mock output scanner — always safe
    mock_scanner = AsyncMock()
    mock_scanner.scan = AsyncMock(return_value=(True, None))

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.ai_provider = "lmstudio"
    mock_settings.model_name = "test-model"
    mock_settings.pi_harness_url = "http://pi-harness:3000"

    app.state.vault = mock_obsidian
    app.state.ai_provider = mock_ai_provider
    app.state.injection_filter = mock_filter
    app.state.output_scanner = mock_scanner
    app.state.settings = mock_settings
    app.state.context_window = 8192
    app.state.module_registry = {}
    app.state.http_client = AsyncMock()

    # Build the singleton MessageProcessor against the just-installed mocks —
    # the route reads app.state.message_processor directly (no factory).
    from app.services.message_processing import MessageProcessor

    app.state.message_processor = MessageProcessor(
        vault=mock_obsidian,
        ai_provider=mock_ai_provider,
        injection_filter=mock_filter,
        output_scanner=mock_scanner,
    )


async def test_obsidian_context_injected_into_llm_prompt():
    """D-GD-01/D-GD-02: Obsidian self-context appears in the messages sent to ai_provider.complete()."""
    captured_messages = []

    async def capturing_complete(messages):
        captured_messages.extend(messages)
        return "Test response referencing vault context."

    app.state.ai_provider.complete = capturing_complete

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message",
            json={"user_id": "test-user-123", "content": "What are my goals?"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    # Verify Obsidian context was called
    app.state.vault.read_self_context.assert_any_call("self/identity.md")

    # Verify known identity content reached the messages array
    all_content = " ".join(
        msg["content"] for msg in captured_messages if isinstance(msg.get("content"), str)
    )
    assert KNOWN_IDENTITY in all_content, (
        f"Obsidian identity context not found in LLM messages.\n"
        f"Expected to find:\n{KNOWN_IDENTITY!r}\n\n"
        f"Messages array had {len(captured_messages)} entries. Full content:\n{all_content[:500]}"
    )


async def test_recent_sessions_injected_into_llm_prompt():
    """D-GD-02: Recent session history from Obsidian appears in the messages sent to ai_provider."""
    captured_messages = []

    async def capturing_complete(messages):
        captured_messages.extend(messages)
        return "Test response."

    app.state.ai_provider.complete = capturing_complete

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message",
            json={"user_id": "test-user-123", "content": "What did we discuss before?"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200

    app.state.vault.get_recent_sessions.assert_called_once_with("test-user-123", limit=3)

    all_content = " ".join(
        msg["content"] for msg in captured_messages if isinstance(msg.get("content"), str)
    )
    assert KNOWN_SESSION in all_content, (
        f"Recent session not found in LLM messages.\n"
        f"Expected:\n{KNOWN_SESSION!r}\n\nGot content:\n{all_content[:500]}"
    )


async def test_pipeline_returns_200_with_response():
    """D-GD-01: Full pipeline — POST /message returns 200 with non-empty content."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message",
            json={"user_id": "test-user-123", "content": "Hello Sentinel"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "content" in body, f"Response missing 'content' field: {body}"
    assert len(body["content"]) > 0, "Response 'content' is empty"
    assert "model" in body, f"Response missing 'model' field: {body}"


async def test_pipeline_degrades_gracefully_when_obsidian_unavailable():
    """D-GD-03: If Obsidian returns empty for all reads, POST /message still returns 200."""
    app.state.vault.read_self_context = AsyncMock(return_value="")
    app.state.vault.get_recent_sessions = AsyncMock(return_value=[])
    app.state.vault.find = AsyncMock(return_value=[])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/message",
            json={"user_id": "test-user-123", "content": "What is 2 + 2?"},
            headers=AUTH_HEADERS,
        )

    assert resp.status_code == 200, (
        f"Pipeline should degrade gracefully without Obsidian context. Got {resp.status_code}: {resp.text}"
    )
