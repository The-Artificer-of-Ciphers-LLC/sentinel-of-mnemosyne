"""pytest configuration for Discord interface tests."""
import os
import sys
import types
import uuid
from unittest.mock import MagicMock

import httpx
import pytest


# ---------------------------------------------------------------------------
# Stub out discord at session-collection time so all test files share one
# consistent stub. Previously each test file rebuilt its own stub and used
# `sys.modules.setdefault` — the first-to-collect won, and downstream tests
# saw an incomplete stub (e.g. missing Embed/Color) depending on collection
# order. Centralising here makes the stub deterministic across the whole
# interfaces/discord test suite (Phase 32-05 Rule 3 fix).
# ---------------------------------------------------------------------------


class _DiscordClientStub:
    def __init__(self, **kwargs):
        pass


class _IntentsStub:
    message_content = False

    @classmethod
    def default(cls):
        return cls()


class _EmbedStub:
    """Minimal discord.Embed stub — records constructor kwargs + fields so tests
    can introspect the rendered embed without needing the real discord.py library."""

    def __init__(self, **kwargs):
        self.title = kwargs.get("title")
        self.description = kwargs.get("description")
        self.color = kwargs.get("color")
        self.fields: list[dict] = []
        self.footer_text: str | None = None

    def add_field(self, *, name, value, inline=False):
        self.fields.append({"name": name, "value": value, "inline": inline})
        return self

    def set_footer(self, *, text):
        self.footer_text = text
        return self


class _ColorStub:
    """Minimal discord.Color stub returning sentinel values for each named colour.

    Phase 33 adds dark_gold + red for build_ruling_embed marker branching:
      - marker=="source"    -> Color.dark_green()
      - marker=="generated" -> Color.dark_gold()
      - marker=="declined"  -> Color.red()
    Extended centrally here (L-5 prevention) — never add these per-file in
    individual test modules or collection-order races break the stub.
    """

    @classmethod
    def dark_gold(cls):
        return "dark_gold"

    @classmethod
    def dark_green(cls):
        return "dark_green"

    @classmethod
    def red(cls):
        return "red"

    @classmethod
    def blue(cls):
        return "blue"

    @classmethod
    def green(cls):
        return "green"

    @classmethod
    def orange(cls):
        return "orange"

    @classmethod
    def gold(cls):
        return "gold"


_app_commands_stub = types.ModuleType("discord.app_commands")
_app_commands_stub.CommandTree = MagicMock()
_app_commands_stub.describe = lambda **_: (lambda f: f)

_discord_stub = types.ModuleType("discord")
_discord_stub.Client = _DiscordClientStub
_discord_stub.Intents = _IntentsStub
_discord_stub.Message = object
_discord_stub.Thread = object
_discord_stub.ChannelType = MagicMock()
_discord_stub.Forbidden = Exception
_discord_stub.HTTPException = Exception
_discord_stub.Interaction = object
_discord_stub.Embed = _EmbedStub
_discord_stub.Color = _ColorStub
_discord_stub.app_commands = _app_commands_stub
sys.modules.setdefault("discord", _discord_stub)
sys.modules.setdefault("discord.app_commands", _app_commands_stub)

# Phase 34: discord.ui stubs for RecapView testing (Wave 0 gap from RESEARCH.md)
# Never add discord.ui stubs per-file in test modules — extend centrally here (L-5 prevention).


class _ButtonStyleStub:
    primary = "primary"
    secondary = "secondary"


class _ViewStub:
    """Minimal discord.ui.View stub for RecapView tests."""

    def __init__(self, timeout=None):
        self.timeout = timeout
        self.message = None

    def stop(self):
        pass

    async def on_timeout(self):
        pass

    def add_item(self, item):
        pass


def _button_decorator(**kwargs):
    """Passthrough decorator stub for @discord.ui.button."""
    return lambda f: f


_ui_stub = types.ModuleType("discord.ui")
_ui_stub.View = _ViewStub
_ui_stub.Button = object  # used as base class annotation only
_ui_stub.button = _button_decorator

_discord_stub.ui = _ui_stub
_discord_stub.ButtonStyle = _ButtonStyleStub
sys.modules.setdefault("discord.ui", _ui_stub)

# Conftest-level path insertion so `import bot` works in every test file.
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token-for-pytest")
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
_discord_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_discord_dir))
_repo_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, os.path.abspath(_repo_root))


# Pre-import pathfinder_player_dialog so test_dialog_router's stub helper picks
# up the REAL module instead of registering an empty ModuleType (which would
# pollute sys.modules and break test_pathfinder_player_dialog when collected
# alphabetically after test_dialog_router). Phase 38-05 collection-order fix.
try:  # noqa: SIM105 — keep import-error path explicit for diagnostics
    import pathfinder_player_dialog  # noqa: F401
except Exception:
    # If the real module fails to import (e.g. during early phases), let the
    # test that triggers it surface the real error rather than masking here.
    pass


OBSIDIAN_BASE_URL = os.environ.get("OBSIDIAN_BASE_URL", "http://host.docker.internal:27124")
OBSIDIAN_API_KEY = os.environ.get("OBSIDIAN_API_KEY", "")


def pytest_configure(config):
    """Register custom markers for this test directory."""
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
