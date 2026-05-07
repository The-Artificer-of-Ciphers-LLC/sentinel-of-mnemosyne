"""Wave 0 RED tests for player_interaction_orchestrator (gate, isolation, style enum).

Symbols referenced below land in Wave 1 (plan 37-06):
  - app.player_interaction_orchestrator.handle_player_interaction
  - app.player_interaction_orchestrator.PlayerInteractionRequest

Function-scope imports keep collection green; the module does not exist yet,
so every test fails at the import boundary inside its body — canonical RED.

Behavioral-Test-Only Rule: every assertion is on observable orchestrator
output (return value, downstream mock calls, raised exceptions). The
isolation regression specifically asserts u1's slug != u2's slug AND each
slug appears only in its own call — not the weaker "response is not None".
"""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import pytest
from unittest.mock import AsyncMock, MagicMock


def _build_adapters(*, profile_returns=None, recall_returns=None):
    """Construct the four orchestrator-injected adapters with sensible defaults.

    profile_returns: what store_adapter.read_profile() returns (None = not onboarded).
    recall_returns: what recall_adapter.recall() returns.
    """
    obsidian_client = AsyncMock()
    obsidian_client.get_note = AsyncMock(return_value=profile_returns)
    obsidian_client.put_note = AsyncMock()

    identity_adapter = MagicMock()
    # Default: identity adapter returns a deterministic per-user slug.
    identity_adapter.slug_from_discord_user_id = MagicMock(
        side_effect=lambda uid: f"p-slug-{uid}"
    )

    store_adapter = AsyncMock()
    store_adapter.read_profile = AsyncMock(return_value=profile_returns)
    store_adapter.write_profile = AsyncMock()
    store_adapter.append_to_inbox = AsyncMock()
    store_adapter.append_question = AsyncMock()
    store_adapter.append_todo = AsyncMock()
    store_adapter.write_npc_knowledge = AsyncMock()
    store_adapter.write_canonization = AsyncMock()
    store_adapter.update_style_preset = AsyncMock()

    recall_adapter = AsyncMock()
    recall_adapter.recall = AsyncMock(return_value=recall_returns or [])

    return obsidian_client, identity_adapter, store_adapter, recall_adapter


# ---------------------------------------------------------------------------
# PVL-01 — onboarding gate: first interaction triggers onboarding
# ---------------------------------------------------------------------------


async def test_first_interaction_triggers_onboarding():
    """handle(verb='note') with profile.md absent → requires_onboarding=True; no inbox write."""
    from app.player_interaction_orchestrator import (
        handle_player_interaction,
        PlayerInteractionRequest,
    )
    obs, ident, store, recall = _build_adapters(profile_returns=None)
    req = PlayerInteractionRequest(verb="note", user_id="u1", text="I trust Varek")
    result = await handle_player_interaction(
        req,
        obsidian_client=obs,
        identity_adapter=ident,
        store_adapter=store,
        recall_adapter=recall,
    )
    assert result.requires_onboarding is True
    store.append_to_inbox.assert_not_awaited()


# ---------------------------------------------------------------------------
# PVL-01 — `start` verb is allowed even when not onboarded
# ---------------------------------------------------------------------------


async def test_start_verb_allowed_when_not_onboarded():
    """handle(verb='start') with profile.md absent → write_profile invoked once, no rejection."""
    from app.player_interaction_orchestrator import (
        handle_player_interaction,
        PlayerInteractionRequest,
    )
    obs, ident, store, recall = _build_adapters(profile_returns=None)
    req = PlayerInteractionRequest(
        verb="start",
        user_id="u1",
        character_name="Aria",
        preferred_name="Ari",
        style_preset="Tactician",
    )
    result = await handle_player_interaction(
        req,
        obsidian_client=obs,
        identity_adapter=ident,
        store_adapter=store,
        recall_adapter=recall,
    )
    assert getattr(result, "requires_onboarding", False) is False
    store.write_profile.assert_awaited_once()


# ---------------------------------------------------------------------------
# PVL-05 — `style list` is read-only and allowed pre-onboarding
# ---------------------------------------------------------------------------


async def test_style_list_allowed_when_not_onboarded():
    """handle(verb='style', action='list') pre-onboarding → returns 4-preset list, no rejection."""
    from app.player_interaction_orchestrator import (
        handle_player_interaction,
        PlayerInteractionRequest,
    )
    obs, ident, store, recall = _build_adapters(profile_returns=None)
    req = PlayerInteractionRequest(verb="style", action="list", user_id="u1")
    result = await handle_player_interaction(
        req,
        obsidian_client=obs,
        identity_adapter=ident,
        store_adapter=store,
        recall_adapter=recall,
    )
    assert getattr(result, "requires_onboarding", False) is False
    presets = getattr(result, "presets", None) or getattr(result, "data", None)
    assert presets is not None, "style list must surface preset list on result"
    text = repr(presets)
    for preset in ("Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"):
        assert preset in text, f"missing preset '{preset}' in style list result"
    store.update_style_preset.assert_not_awaited()


# ---------------------------------------------------------------------------
# PVL-05 — `style set` is a write — gated by onboarding
# ---------------------------------------------------------------------------


async def test_style_set_blocked_when_not_onboarded():
    """handle(verb='style', action='set') pre-onboarding → requires_onboarding=True (write requires onboarding)."""
    from app.player_interaction_orchestrator import (
        handle_player_interaction,
        PlayerInteractionRequest,
    )
    obs, ident, store, recall = _build_adapters(profile_returns=None)
    req = PlayerInteractionRequest(
        verb="style", action="set", preset="Tactician", user_id="u1"
    )
    result = await handle_player_interaction(
        req,
        obsidian_client=obs,
        identity_adapter=ident,
        store_adapter=store,
        recall_adapter=recall,
    )
    assert result.requires_onboarding is True
    store.update_style_preset.assert_not_awaited()


# ---------------------------------------------------------------------------
# PVL-07 — isolation regression: cross-player slugs MUST NOT bleed
# ---------------------------------------------------------------------------


async def test_isolation_no_cross_player_read():
    """Two recall calls (u1 then u2) must pass distinct slugs and never share a slug arg (PVL-07)."""
    from app.player_interaction_orchestrator import (
        handle_player_interaction,
        PlayerInteractionRequest,
    )
    onboarded_yaml = "---\nonboarded: true\n---\n"
    obs, ident, store, recall = _build_adapters(profile_returns=onboarded_yaml)
    store.read_profile = AsyncMock(return_value=onboarded_yaml)

    slug_log: list[str] = []

    async def _record_slug(slug, *args, **kwargs):
        slug_log.append(slug)
        return []

    recall.recall = AsyncMock(side_effect=_record_slug)

    req_u1 = PlayerInteractionRequest(verb="recall", user_id="u1", query="Varek")
    req_u2 = PlayerInteractionRequest(verb="recall", user_id="u2", query="Varek")
    await handle_player_interaction(
        req_u1,
        obsidian_client=obs,
        identity_adapter=ident,
        store_adapter=store,
        recall_adapter=recall,
    )
    await handle_player_interaction(
        req_u2,
        obsidian_client=obs,
        identity_adapter=ident,
        store_adapter=store,
        recall_adapter=recall,
    )
    assert len(slug_log) == 2, f"expected 2 recall calls; got {len(slug_log)}: {slug_log}"
    u1_slug, u2_slug = slug_log[0], slug_log[1]
    assert u1_slug != u2_slug, (
        f"PVL-07 isolation violation: u1 and u2 resolved to same slug {u1_slug!r}"
    )
    # Per-call: u1's slug must not appear in the u2 call args, and vice versa.
    # Inspect every recorded recall_adapter.recall await — every slug arg/path
    # arg must contain only its own owner's slug.
    all_calls = recall.recall.await_args_list
    assert len(all_calls) == 2
    call0_repr = repr(all_calls[0])
    call1_repr = repr(all_calls[1])
    assert u2_slug not in call0_repr, (
        f"u1 recall leaked u2 slug {u2_slug!r}: {call0_repr}"
    )
    assert u1_slug not in call1_repr, (
        f"u2 recall leaked u1 slug {u1_slug!r}: {call1_repr}"
    )


# ---------------------------------------------------------------------------
# PVL-03 / PVL-07 — recall passes resolver-derived slug only, never raw user_id
# ---------------------------------------------------------------------------


async def test_recall_passes_resolver_slug_only():
    """Orchestrator passes the resolver-derived slug to recall_adapter — not raw user_id."""
    from app.player_interaction_orchestrator import (
        handle_player_interaction,
        PlayerInteractionRequest,
    )
    onboarded_yaml = "---\nonboarded: true\n---\n"
    obs, ident, store, recall = _build_adapters(profile_returns=onboarded_yaml)
    store.read_profile = AsyncMock(return_value=onboarded_yaml)
    # Make the resolver return a unique sentinel slug so we can detect it.
    ident.slug_from_discord_user_id = MagicMock(return_value="p-resolver-sentinel-XYZ")

    req = PlayerInteractionRequest(verb="recall", user_id="raw-discord-id-12345", query="Varek")
    await handle_player_interaction(
        req,
        obsidian_client=obs,
        identity_adapter=ident,
        store_adapter=store,
        recall_adapter=recall,
    )
    recall.recall.assert_awaited()
    call_repr = repr(recall.recall.await_args_list[0])
    assert "p-resolver-sentinel-XYZ" in call_repr, (
        f"resolver-derived slug missing from recall call: {call_repr}"
    )
    assert "raw-discord-id-12345" not in call_repr, (
        f"raw user_id leaked into recall call (must use resolver slug only): {call_repr}"
    )


# ---------------------------------------------------------------------------
# PVL-05 — invalid style preset raises with closed-enum message
# ---------------------------------------------------------------------------


async def test_invalid_style_preset_raises():
    """handle(verb='style', action='set', preset='MadeUp') raises ValueError listing the four valid presets."""
    from app.player_interaction_orchestrator import (
        handle_player_interaction,
        PlayerInteractionRequest,
    )
    onboarded_yaml = "---\nonboarded: true\n---\n"
    obs, ident, store, recall = _build_adapters(profile_returns=onboarded_yaml)
    store.read_profile = AsyncMock(return_value=onboarded_yaml)

    req = PlayerInteractionRequest(
        verb="style", action="set", preset="MadeUp", user_id="u1"
    )
    with pytest.raises(ValueError) as exc_info:
        await handle_player_interaction(
            req,
            obsidian_client=obs,
            identity_adapter=ident,
            store_adapter=store,
            recall_adapter=recall,
        )
    msg = str(exc_info.value)
    for preset in ("Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"):
        assert preset in msg, f"ValueError message missing preset '{preset}': {msg}"


# ---------------------------------------------------------------------------
# PVL-06 — identity resolver is the SOLE seam for slug derivation
# ---------------------------------------------------------------------------


async def test_orchestrator_uses_identity_resolver_seam():
    """A fake resolver pinned to 'p-fixed' makes every downstream call use 'p-fixed' regardless of user_id."""
    from app.player_interaction_orchestrator import (
        handle_player_interaction,
        PlayerInteractionRequest,
    )
    onboarded_yaml = "---\nonboarded: true\n---\n"
    obs, ident, store, recall = _build_adapters(profile_returns=onboarded_yaml)
    store.read_profile = AsyncMock(return_value=onboarded_yaml)
    # Pin resolver to a fixed slug regardless of user_id.
    ident.slug_from_discord_user_id = MagicMock(return_value="p-fixed")

    req = PlayerInteractionRequest(
        verb="note", user_id="totally-different-id-999", text="hello"
    )
    await handle_player_interaction(
        req,
        obsidian_client=obs,
        identity_adapter=ident,
        store_adapter=store,
        recall_adapter=recall,
    )
    # The store_adapter.append_to_inbox call must reference 'p-fixed' (via slug
    # arg or path arg) and must NOT contain the raw user_id.
    store.append_to_inbox.assert_awaited()
    call_repr = repr(store.append_to_inbox.await_args_list[0])
    assert "p-fixed" in call_repr, (
        f"downstream call did not use resolver-derived slug: {call_repr}"
    )
    assert "totally-different-id-999" not in call_repr, (
        f"raw user_id leaked past resolver into downstream call: {call_repr}"
    )
