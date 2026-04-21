"""pytest configuration for Discord interface tests."""
import os
import uuid

import httpx
import pytest

OBSIDIAN_BASE_URL = os.environ.get("OBSIDIAN_BASE_URL", "http://host.docker.internal:27124")
OBSIDIAN_API_KEY = os.environ.get("OBSIDIAN_API_KEY", "")


def pytest_configure(config):
    """Register asyncio_mode=auto and custom markers for this test directory."""
    config.option.asyncio_mode = "auto"
    config.addinivalue_line(
        "markers", "integration: mark test as requiring live Obsidian REST API"
    )


@pytest.fixture
def test_run_path():
    """Unique vault path prefix for this test run. Cleaned up by obsidian_teardown."""
    return f"ops/test-run-{uuid.uuid4()}"


@pytest.fixture(autouse=True)
async def obsidian_teardown(request, test_run_path):
    """DELETE the test-run path from Obsidian vault after each integration test.

    Only performs cleanup for tests marked @pytest.mark.integration.
    Best-effort: swallows all errors so test results are never obscured by cleanup failures.
    """
    yield
    if "integration" in request.keywords:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.delete(
                    f"{OBSIDIAN_BASE_URL}/vault/{test_run_path}/",
                    headers={"Authorization": f"Bearer {OBSIDIAN_API_KEY}"},
                )
        except Exception:
            pass  # best-effort cleanup — never fail the test over teardown
