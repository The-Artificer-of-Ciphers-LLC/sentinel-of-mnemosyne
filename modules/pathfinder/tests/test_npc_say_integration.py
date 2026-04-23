"""Integration tests for /npc/say — full vault round-trip with canned LLM (DLG-01..03, SC-1..4).

Wave 0 RED scaffolding — implementation lands in Wave 1.
Stubs reference `app.routes.npc.generate_npc_reply` which does not yet exist.
Collection succeeds; runtime `patch()` of the missing attribute fails with
AttributeError — the honest RED signal.
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
# Fixtures — copied verbatim from test_npc.py for test isolation (per PATTERNS §2)
# ---------------------------------------------------------------------------

NOTE_VAREK_NEUTRAL = (
    "---\n"
    "name: Varek\nlevel: 1\nancestry: Gnome\nclass: Rogue\n"
    "traits:\n- sneaky\npersonality: Nervous and twitchy.\n"
    "backstory: Fled the thieves' guild after stealing a ledger.\n"
    "mood: neutral\nrelationships: []\nimported_from: null\n"
    "---\n"
)

NOTE_BARON_HOSTILE = (
    "---\n"
    "name: Baron Aldric\nlevel: 5\nancestry: Human\nclass: Fighter\n"
    "traits:\n- arrogant\npersonality: Cold and calculating.\n"
    "backstory: A noble who seized the keep through betrayal.\n"
    "mood: hostile\nrelationships: []\nimported_from: null\n"
    "---\n"
)


class StatefulMockVault:
    """In-memory vault mock — get_note returns the last put_note content for each path.

    Allows integration tests to observe the full round-trip: POST → mood write →
    subsequent POST reads the updated state.
    """

    def __init__(self, initial: dict[str, str]):
        self._store: dict[str, str] = dict(initial)
        self.get_note = AsyncMock(side_effect=self._get)
        self.put_note = AsyncMock(side_effect=self._put)

    async def _get(self, path: str) -> str | None:
        return self._store.get(path)

    async def _put(self, path: str, content: str) -> None:
        self._store[path] = content


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


async def test_solo_mood_roundtrip_through_vault():
    """Two-turn solo exchange: mood drops neutral→wary, then wary→neutral.

    Covers SC-1, SC-2, SC-3 (DLG-01, DLG-02).
    Proves that mood state persists across calls via the vault and is surfaced
    as tone-guidance (WARY keyword) in the second turn's system prompt.
    """
    vault = StatefulMockVault({"mnemosyne/pf2e/npcs/varek.md": NOTE_VAREK_NEUTRAL})
    mock_gen = AsyncMock(side_effect=[
        {"reply": "*scowls.* \"You'll regret that.\"", "mood_delta": -1},
        {"reply": "*pauses.* \"...maybe I was wrong.\"", "mood_delta": 1},
    ])
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", vault), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Turn 1: neutral → wary
            resp1 = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "Why did you take the coin?",
                "history": [],
                "user_id": "u1",
            })
            assert resp1.status_code == 200
            assert resp1.json()["replies"][0]["new_mood"] == "wary"
            assert "mood: wary" in vault._store["mnemosyne/pf2e/npcs/varek.md"]

            # Turn 2: wary → neutral. History from turn 1.
            resp2 = await client.post("/npc/say", json={
                "names": ["Varek"],
                "party_line": "I'm sorry, please trust us.",
                "history": [{
                    "party_line": "Why did you take the coin?",
                    "replies": [{"npc": "Varek", "reply": "*scowls.* \"You'll regret that.\""}],
                }],
                "user_id": "u1",
            })
            assert resp2.status_code == 200

    # Second call's system_prompt should reflect Varek's WARY mood (picked up from
    # the freshly-written vault note). Extract from kwargs or positional args[0].
    call_1 = mock_gen.call_args_list[1]
    sys_prompt = call_1.kwargs.get("system_prompt")
    if sys_prompt is None and call_1.args:
        sys_prompt = call_1.args[0]
    assert sys_prompt is not None, "generate_npc_reply second call missing system_prompt"
    assert "WARY" in sys_prompt

    # Final assertions on turn 2 response + vault state after round-trip
    assert resp2.json()["replies"][0]["new_mood"] == "neutral"
    assert "mood: neutral" in vault._store["mnemosyne/pf2e/npcs/varek.md"]


async def test_scene_distinct_voices_and_awareness():
    """Two-NPC scene: each NPC gets distinct mood-tone system prompt AND sees peer replies.

    Covers SC-4 (DLG-03). Order is Varek then Baron; Baron's user_prompt must
    include Varek's just-generated reply (in-turn awareness).
    """
    vault = StatefulMockVault({
        "mnemosyne/pf2e/npcs/varek.md": NOTE_VAREK_NEUTRAL,
        "mnemosyne/pf2e/npcs/baron-aldric.md": NOTE_BARON_HOSTILE,
    })
    mock_gen = AsyncMock(side_effect=[
        {"reply": "*shrinks.* \"P-please...\"", "mood_delta": 0},
        {"reply": "*sneers.* \"He's lying.\"", "mood_delta": 0},
    ])
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", vault), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/npc/say", json={
                "names": ["Varek", "Baron Aldric"],
                "party_line": "We mean no harm.",
                "history": [],
                "user_id": "u1",
            })

    assert resp.status_code == 200
    replies = resp.json()["replies"]
    assert replies[0]["npc"] == "Varek"
    assert replies[1]["npc"] == "Baron Aldric"

    # Distinct system prompts per NPC — tone-guidance keyword (uppercase) must differ.
    call_0 = mock_gen.call_args_list[0]
    call_1 = mock_gen.call_args_list[1]

    sys_0 = call_0.kwargs.get("system_prompt") or (call_0.args[0] if call_0.args else None)
    sys_1 = call_1.kwargs.get("system_prompt") or (call_1.args[0] if call_1.args else None)
    assert sys_0 is not None and sys_1 is not None, "system_prompt missing on scene calls"
    assert "NEUTRAL" in sys_0  # Varek's mood-tone keyword
    assert "HOSTILE" in sys_1  # Baron's mood-tone keyword

    # In-turn awareness: Baron's user_prompt contains Varek's just-generated reply text.
    user_1 = call_1.kwargs.get("user_prompt")
    if user_1 is None and len(call_1.args) >= 2:
        user_1 = call_1.args[1]
    assert user_1 is not None, "user_prompt missing on second scene call"
    assert "P-please" in user_1
