"""Direct tests for pathfinder dispatch seam.

Tests the deepened interface: COMMANDS registry lookup, PathfinderRequest/Response
types, and individual command implementations.

The old adapter-based dispatch (if-chain routing to module-style adapters) has
been replaced by registry lookup: COMMANDS[noun][verb] → command.handle(request).

Each sub-verb is now a separate class implementing PathfinderCommand.
"""

from unittest.mock import AsyncMock

import pytest

from pathfinder_dispatch import COMMANDS
from pathfinder_types import (
    PathfinderCommand,
    PathfinderRequest,
    PathfinderResponse,
)


# --- Registry structure tests ---

class TestRegistryStructure:
    """Verify the COMMANDS registry has all expected nouns and verbs."""

    def test_harvest_has_wildcard(self):
        assert "harvest" in COMMANDS
        assert "*" in COMMANDS["harvest"]

    def test_rule_has_all_verbs(self):
        assert "rule" in COMMANDS
        for verb in ("query", "list", "show", "history"):
            assert verb in COMMANDS["rule"], f"Missing rule sub-verb: {verb}"

    def test_session_has_all_verbs(self):
        assert "session" in COMMANDS
        for verb in ("start", "show", "end"):
            assert verb in COMMANDS["session"], f"Missing session sub-verb: {verb}"

    def test_npc_has_all_basic_verbs(self):
        assert "npc" in COMMANDS
        for verb in ("create", "update", "show", "relate"):
            assert verb in COMMANDS["npc"], f"Missing npc basic sub-verb: {verb}"

    def test_npc_has_all_rich_verbs(self):
        assert "npc" in COMMANDS
        for verb in ("import", "export", "token", "token-image", "stat", "pdf", "say"):
            assert verb in COMMANDS["npc"], f"Missing npc rich sub-verb: {verb}"

    def test_ingest_has_wildcard(self):
        assert "ingest" in COMMANDS
        assert "*" in COMMANDS["ingest"]

    def test_cartosia_has_wildcard(self):
        assert "cartosia" in COMMANDS
        assert "*" in COMMANDS["cartosia"]

    def test_all_commands_implement_pathfinder_command(self):
        """Every registered command must have a handle() method."""
        for noun, verbs in COMMANDS.items():
            for verb, command in verbs.items():
                assert hasattr(command, "handle"), (
                    f"COMMANDS['{noun}']['{verb}'] missing handle() method"
                )
                assert callable(command.handle), (
                    f"COMMANDS['{noun}']['{verb}'].handle is not callable"
                )


# --- Dispatch routing tests ---

class TestDispatchRouting:
    """Test that dispatch looks up the correct command from COMMANDS."""

    @pytest.mark.asyncio
    async def test_dispatch_unknown_noun(self):
        """Unknown noun returns text error."""
        response = await pathfinder_dispatch.dispatch(
            noun="unknown",
            verb="foo",
            rest="",
            user_id="u1",
            channel=None,
            attachments=None,
            bot_user=None,
            sentinel_client=object(),
            http_client=object(),
            is_admin=lambda _u: True,
            valid_relations=frozenset(),
            builders={},
        )
        assert response.kind == "text"
        assert "Unknown pf category" in response.content

    @pytest.mark.asyncio
    async def test_dispatch_unknown_verb(self):
        """Unknown verb for known noun returns text error."""
        response = await pathfinder_dispatch.dispatch(
            noun="rule",
            verb="foobar",
            rest="",
            user_id="u1",
            channel=None,
            attachments=None,
            bot_user=None,
            sentinel_client=object(),
            http_client=object(),
            is_admin=lambda _u: True,
            valid_relations=frozenset(),
            builders={},
        )
        assert response.kind == "text"
        assert "Unknown `rule` sub-command" in response.content

    @pytest.mark.asyncio
    async def test_dispatch_harvest_wildcard(self):
        """Harvest uses wildcard handler (no sub-verbs)."""
        mock_client = AsyncMock()
        response = await pathfinder_dispatch.dispatch(
            noun="harvest",
            verb="anything",  # ignored, wildcard used
            rest="",  # no names → usage error (text response)
            user_id="u1",
            channel=None,
            attachments=None,
            bot_user=None,
            sentinel_client=mock_client,
            http_client=object(),
            is_admin=lambda _u: True,
            valid_relations=frozenset(),
            builders={},
        )
        # HarvestCommand returns text response with usage when no names found
        assert response.kind == "text"
        assert "Usage:" in response.content


# --- Individual command tests ---

class TestHarvestCommand:
    """Test HarvestCommand directly."""

    @pytest.mark.asyncio
    async def test_harvest_no_names(self):
        """Empty rest → usage error."""
        cmd = COMMANDS["harvest"]["*"]
        request = PathfinderRequest(
            noun="harvest", verb="*", rest="", user_id="u1"
        )
        response = await cmd.handle(request)
        assert response.kind == "text"
        assert "Usage:" in response.content

    @pytest.mark.asyncio
    async def test_harvest_single_name(self):
        """Single name → embed response."""
        cmd = COMMANDS["harvest"]["*"]
        mock_client = AsyncMock()
        mock_client.post_to_module = AsyncMock(return_value={
            "name": "Test Character",
            "path": "/vault/harvest/test-character.md",
        })
        request = PathfinderRequest(
            noun="harvest", verb="*", rest="Test Character",
            user_id="u1", sentinel_client=mock_client,
        )

        response = await cmd.handle(request)
        assert response.kind == "embed"
        assert response.embed_data["name"] == "Test Character"


class TestRuleQueryCommand:
    """Test RuleQueryCommand directly."""

    @pytest.mark.asyncio
    async def test_rule_query_no_question(self):
        """Empty query → usage error."""
        cmd = COMMANDS["rule"]["query"]
        request = PathfinderRequest(
            noun="rule", verb="query", rest="", user_id="u1"
        )
        response = await cmd.handle(request)
        assert response.kind == "text"
        assert "Usage:" in response.content

    @pytest.mark.asyncio
    async def test_rule_query_with_question(self):
        """Question → embed response."""
        cmd = COMMANDS["rule"]["query"]
        mock_client = AsyncMock()
        mock_client.post_to_module = AsyncMock(return_value={
            "question": "How does sneak attack work?",
            "answer": "Sneak attack deals extra damage when...",
        })
        request = PathfinderRequest(
            noun="rule", verb="query",
            rest="How does sneak attack work?",
            user_id="u1", sentinel_client=mock_client,
        )

        response = await cmd.handle(request)
        assert response.kind == "embed"


class TestNpcCreateCommand:
    """Test NpcCreateCommand directly."""

    @pytest.mark.asyncio
    async def test_npc_create_no_name(self):
        """No name → usage error."""
        cmd = COMMANDS["npc"]["create"]
        request = PathfinderRequest(
            noun="npc", verb="create", rest="", user_id="u1"
        )
        response = await cmd.handle(request)
        assert response.kind == "text"
        assert "Usage:" in response.content

    @pytest.mark.asyncio
    async def test_npc_create_with_name(self):
        """Name + description → text response."""
        cmd = COMMANDS["npc"]["create"]
        mock_client = AsyncMock()
        mock_client.post_to_module = AsyncMock(return_value={
            "name": "Grog",
            "path": "/vault/npc/grog.md",
            "ancestry": "Orc",
            "class": "Barbarian",
            "level": 5,
        })
        request = PathfinderRequest(
            noun="npc", verb="create",
            rest="Grog | A strong orc warrior",
            user_id="u1", sentinel_client=mock_client,
        )

        response = await cmd.handle(request)
        assert response.kind == "text"
        assert "Grog" in response.content


class TestNpcShowCommand:
    """Test NpcShowCommand directly."""

    @pytest.mark.asyncio
    async def test_npc_show_no_name(self):
        """No name → usage error."""
        cmd = COMMANDS["npc"]["show"]
        request = PathfinderRequest(
            noun="npc", verb="show", rest="", user_id="u1"
        )
        response = await cmd.handle(request)
        assert response.kind == "text"

    @pytest.mark.asyncio
    async def test_npc_show_with_name(self):
        """Name → text response with NPC details."""
        cmd = COMMANDS["npc"]["show"]
        mock_client = AsyncMock()
        mock_client.post_to_module = AsyncMock(return_value={
            "name": "Grog",
            "level": 5,
            "ancestry": "Orc",
            "class": "Barbarian",
            "personality": "Brash and loyal",
            "backstory": "Once a slave, now free...",
            "stats": {"ac": 16, "hp": 45},
            "relationships": [{"target": "Aragorn", "relation": "friend"}],
            "mood": "content",
            "path": "/vault/npc/grog.md",
        })
        request = PathfinderRequest(
            noun="npc", verb="show",
            rest="Grog", user_id="u1",
            sentinel_client=mock_client,
        )

        response = await cmd.handle(request)
        assert response.kind == "text"
        assert "Grog" in response.content
        assert "Level 5 Orc Barbarian" in response.content


class TestNpcRelateCommand:
    """Test NpcRelateCommand directly."""

    @pytest.mark.asyncio
    async def test_npc_relate_invalid_relation(self):
        """Invalid relation type → error."""
        cmd = COMMANDS["npc"]["relate"]
        request = PathfinderRequest(
            noun="npc", verb="relate",
            rest="Grog | foobar | Aragorn",
            user_id="u1", valid_relations=frozenset({"knows", "fights"}),
        )
        response = await cmd.handle(request)
        assert response.kind == "text"
        assert "not a valid relation type" in response.content

    @pytest.mark.asyncio
    async def test_npc_relate_valid(self):
        """Valid relation → text response."""
        cmd = COMMANDS["npc"]["relate"]
        mock_client = AsyncMock()
        mock_client.post_to_module = AsyncMock(return_value={})
        request = PathfinderRequest(
            noun="npc", verb="relate",
            rest="Grog | knows | Aragorn",
            user_id="u1", valid_relations=frozenset({"knows", "fights"}),
            sentinel_client=mock_client,
        )

        response = await cmd.handle(request)
        assert response.kind == "text"
        assert "Relationship added:" in response.content


# --- Import pathfinder_dispatch to trigger registry population ---
import pathfinder_dispatch  # noqa: F401 — triggers COMMANDS population
