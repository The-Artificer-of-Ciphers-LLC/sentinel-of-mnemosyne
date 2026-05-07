"""Wave 0 RED tests for FCM-04 idempotency + dedupe key contract.

These tests will fail at the import boundary in Wave 0 (the projection module
doesn't exist yet) and turn green in Wave 5 when
`app.foundry_memory_projection.project_foundry_chat_memory` lands.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest


def _record(
    *,
    _id: str | None = "m1",
    speaker: str = "Valeros",
    content: str = "We move at dawn.",
    timestamp: int = 1710000000000,
    msg_type: int = 1,
) -> dict:
    rec: dict = {
        "type": msg_type,
        "speaker": {"alias": speaker},
        "content": content,
        "timestamp": timestamp,
    }
    if _id is not None:
        rec["_id"] = _id
    return rec


def _make_identity_resolver(alias_map, npc_roster):
    def _resolve(speaker_token: str):
        if speaker_token in alias_map:
            return ("player", f"p-{alias_map[speaker_token]}")
        slug = npc_roster.get(speaker_token.lower())
        if slug:
            return ("npc", slug)
        return ("unknown", speaker_token)

    return _resolve


def _make_npc_matcher(npc_roster):
    return lambda token: npc_roster.get(token.lower())


def _make_obsidian():
    obsidian = AsyncMock()
    # Default: no existing notes (so first run creates them).
    obsidian.get_note = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)
    return obsidian


@pytest.mark.asyncio
async def test_projection_idempotent_on_rerun(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = _make_obsidian()
    state_path = tmp_path / ".foundry_chat_import_state.json"
    records = [
        _record(_id="m1", speaker="Valeros", content="hi"),
        _record(_id="m2", speaker="Goblin Boss", content="grr"),
    ]
    resolver = _make_identity_resolver(
        alias_map={"Valeros": "u1"},
        npc_roster={"goblin boss": "goblin-boss"},
    )
    matcher = _make_npc_matcher({"goblin boss": "goblin-boss"})

    # First run.
    r1 = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=state_path,
        identity_resolver=resolver,
        npc_matcher=matcher,
    )
    assert (r1["player_updates"] >= 1) or (r1["npc_updates"] >= 1)

    put_count_after_first = obsidian.put_note.await_count
    patch_count_after_first = obsidian.patch_heading.await_count

    # Second run — same records, same state path.
    r2 = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=state_path,
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    assert r2["player_updates"] == 0
    assert r2["npc_updates"] == 0
    assert (r2["player_deduped"] + r2["npc_deduped"]) >= 1
    # No new writes on second pass.
    assert obsidian.put_note.await_count == put_count_after_first
    assert obsidian.patch_heading.await_count == patch_count_after_first


@pytest.mark.asyncio
async def test_state_file_persists_player_and_npc_keys(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = _make_obsidian()
    state_path = tmp_path / ".foundry_chat_import_state.json"
    records = [
        _record(_id="m1", speaker="Valeros", content="hi"),
        _record(_id="m2", speaker="Goblin Boss", content="grr"),
    ]
    resolver = _make_identity_resolver(
        alias_map={"Valeros": "u1"},
        npc_roster={"goblin boss": "goblin-boss"},
    )
    matcher = _make_npc_matcher({"goblin boss": "goblin-boss"})

    await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=state_path,
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    assert state_path.exists()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert isinstance(data.get("player_projection_keys"), list)
    assert isinstance(data.get("npc_projection_keys"), list)
    assert len(data["player_projection_keys"]) >= 1
    assert len(data["npc_projection_keys"]) >= 1


@pytest.mark.asyncio
async def test_dedupe_key_uses_foundry_id_when_present(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = _make_obsidian()
    state_path = tmp_path / ".foundry_chat_import_state.json"
    records = [_record(_id="m1", speaker="Valeros", content="hi")]
    resolver = _make_identity_resolver(alias_map={"Valeros": "u1"}, npc_roster={})
    matcher = _make_npc_matcher({})

    await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=state_path,
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    data = json.loads(state_path.read_text(encoding="utf-8"))
    all_keys = data.get("player_projection_keys", []) + data.get("npc_projection_keys", [])
    assert any("m1" in k for k in all_keys), (
        f"expected foundry _id to appear in projection keys; got {all_keys!r}"
    )

    # Now a second run with no _id — fallback recipe must include speaker/content/timestamp.
    state_path2 = tmp_path / ".state2.json"
    obsidian2 = _make_obsidian()
    records2 = [_record(_id=None, speaker="Valeros", content="zzz", timestamp=1710000099000)]
    await project_foundry_chat_memory(
        records=records2,
        dry_run=False,
        obsidian_client=obsidian2,
        dedupe_store_path=state_path2,
        identity_resolver=resolver,
        npc_matcher=matcher,
    )
    data2 = json.loads(state_path2.read_text(encoding="utf-8"))
    keys2 = data2.get("player_projection_keys", []) + data2.get("npc_projection_keys", [])
    # Fallback recipe must reference timestamp AND speaker AND content.
    assert any(
        ("1710000099000" in k) and ("Valeros" in k) and ("zzz" in k)
        for k in keys2
    ), f"fallback key recipe missing components; got {keys2!r}"


@pytest.mark.asyncio
async def test_dedupe_key_target_discriminator(tmp_path):
    """A single record routed to two targets must dedupe per-target.

    The same Foundry record should produce DIFFERENT keys for `player_map`
    vs `npc_history`, so a record landing in one target does not silently
    suppress writes to the other on a future run.
    """
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = _make_obsidian()
    state_path = tmp_path / ".foundry_chat_import_state.json"

    # Speaker resolves as a player (alias map wins). Same speaker is also in
    # npc_roster so a hypothetical second-target write would dedupe separately.
    records = [_record(_id="dual", speaker="Valeros", content="hi")]
    resolver = _make_identity_resolver(
        alias_map={"Valeros": "u1"},
        npc_roster={"valeros": "valeros-npc"},
    )
    matcher = _make_npc_matcher({"valeros": "valeros-npc"})

    await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=state_path,
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    data = json.loads(state_path.read_text(encoding="utf-8"))
    p_keys = set(data.get("player_projection_keys", []))
    n_keys = set(data.get("npc_projection_keys", []))
    # Player-map key set is non-empty and disjoint from npc_history key set.
    assert len(p_keys) >= 1
    assert p_keys.isdisjoint(n_keys), (
        f"player and npc projection keys must be disjoint per-target; "
        f"got intersection {p_keys & n_keys!r}"
    )
