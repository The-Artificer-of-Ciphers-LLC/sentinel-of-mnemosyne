"""Wave 0 RED tests for foundry_memory_projection (FCM-01..03, FCM-05).

These tests lock the contracts for the projection module that will be
implemented in Wave 5. They MUST fail at the import boundary in Wave 0 — the
module `app.foundry_memory_projection` does not yet exist.

All imports are function-scope so pytest collection succeeds before the module
lands.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Helpers shared by all tests
# ---------------------------------------------------------------------------


def _record(
    *,
    _id: str = "m1",
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


def _make_identity_resolver(alias_map: dict[str, str], npc_roster: dict[str, str]):
    """Returns an identity_resolver callable.

    Returns one of: ("player", player_slug), ("npc", npc_slug), ("unknown", raw).
    Precedence: alias_map → npc_roster → unknown.
    """

    def _resolve(speaker_token: str):
        if speaker_token in alias_map:
            user_id = alias_map[speaker_token]
            slug = f"p-{user_id}"
            return ("player", slug)
        npc_slug = npc_roster.get(speaker_token.lower())
        if npc_slug:
            return ("npc", npc_slug)
        return ("unknown", speaker_token)

    return _resolve


def _make_npc_matcher(npc_roster: dict[str, str]):
    def _match(speaker_token: str) -> str | None:
        return npc_roster.get(speaker_token.lower())

    return _match


# ---------------------------------------------------------------------------
# FCM-01: classification precedence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_speaker_precedence_alias_first(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    records = [_record(_id="m1", speaker="Valeros", content="hi")]
    resolver = _make_identity_resolver(
        alias_map={"Valeros": "u1"},
        npc_roster={"valeros": "valeros-npc"},
    )
    matcher = _make_npc_matcher({"valeros": "valeros-npc"})

    result = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    # Player path used; NPC path NOT touched.
    put_paths = [c.args[0] for c in obsidian.put_note.await_args_list]
    assert any(p == "mnemosyne/pf2e/players/p-u1.md" for p in put_paths)
    assert not any(p.startswith("mnemosyne/pf2e/npcs/") for p in put_paths)
    # No NPC patch attempted.
    assert obsidian.patch_heading.await_count == 0
    assert result["player_updates"] >= 1
    assert result["npc_updates"] == 0


@pytest.mark.asyncio
async def test_classify_speaker_precedence_npc_roster_second(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    # Existing NPC note WITH the section so we exercise patch_heading append.
    obsidian.get_note = AsyncMock(
        return_value="# Goblin Boss\n\n## Foundry Chat History\n",
    )
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    records = [_record(_id="m9", speaker="Goblin Boss", content="grrr")]
    resolver = _make_identity_resolver(
        alias_map={},
        npc_roster={"goblin boss": "goblin-boss"},
    )
    matcher = _make_npc_matcher({"goblin boss": "goblin-boss"})

    result = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    assert obsidian.patch_heading.await_count == 1
    call = obsidian.patch_heading.await_args
    # Path is the NPC note path.
    assert "mnemosyne/pf2e/npcs/goblin-boss.md" in (
        list(call.args) + list(call.kwargs.values())
    )
    assert result["npc_updates"] >= 1
    assert result["player_updates"] == 0


@pytest.mark.asyncio
async def test_classify_speaker_unknown_increments_stat(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    records = [_record(_id="mX", speaker="Random Bandit", content="hi")]
    resolver = _make_identity_resolver(alias_map={}, npc_roster={})
    matcher = _make_npc_matcher({})

    result = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    assert obsidian.put_note.await_count == 0
    assert obsidian.patch_heading.await_count == 0
    assert "Random Bandit" in result["unmatched_speakers"]
    assert result["player_updates"] == 0
    assert result["npc_updates"] == 0


# ---------------------------------------------------------------------------
# FCM-02: player map four-section build
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_player_map_creates_four_sections(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=None)  # no existing player map
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    records = [_record(_id="m1", speaker="Valeros", content="We move at dawn.")]
    resolver = _make_identity_resolver(alias_map={"Valeros": "abc"}, npc_roster={})
    matcher = _make_npc_matcher({})

    await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    # Find the put_note call for the player map.
    player_calls = [
        c for c in obsidian.put_note.await_args_list
        if c.args[0] == "mnemosyne/pf2e/players/p-abc.md"
    ]
    assert len(player_calls) == 1
    body = player_calls[0].args[1]
    assert "## Voice Patterns" in body
    assert "## Notable Moments" in body
    assert "## Party Dynamics" in body
    assert "## Chat Timeline" in body
    # Speaker line lands under Chat Timeline.
    timeline_idx = body.index("## Chat Timeline")
    timeline_section = body[timeline_idx:]
    assert "We move at dawn." in timeline_section


# ---------------------------------------------------------------------------
# FCM-03: NPC history append (two modes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_npc_history_append_existing_section(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(
        return_value="# Goblin Boss\n\nbody\n\n## Foundry Chat History\n",
    )
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    records = [_record(_id="m1", speaker="Goblin Boss", content="grrr")]
    resolver = _make_identity_resolver(
        alias_map={}, npc_roster={"goblin boss": "goblin-boss"}
    )
    matcher = _make_npc_matcher({"goblin boss": "goblin-boss"})

    await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    assert obsidian.patch_heading.await_count == 1
    # The NPC note was NOT overwritten via put_note.
    npc_put_calls = [
        c for c in obsidian.put_note.await_args_list
        if c.args[0].endswith("/npcs/goblin-boss.md")
    ]
    assert npc_put_calls == []
    # patch_heading invoked with append-style operation.
    call = obsidian.patch_heading.await_args
    all_kwargs_and_args = " ".join(
        [str(a) for a in call.args] + [f"{k}={v}" for k, v in call.kwargs.items()]
    )
    assert "append" in all_kwargs_and_args.lower()


@pytest.mark.asyncio
async def test_npc_history_create_section_when_missing(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(
        return_value="# Goblin Boss\n\nsome body content without the section\n",
    )
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    records = [_record(_id="m1", speaker="Goblin Boss", content="grrr")]
    resolver = _make_identity_resolver(
        alias_map={}, npc_roster={"goblin boss": "goblin-boss"}
    )
    matcher = _make_npc_matcher({"goblin boss": "goblin-boss"})

    await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    # put_note used to add the new section.
    npc_put_calls = [
        c for c in obsidian.put_note.await_args_list
        if c.args[0].endswith("/npcs/goblin-boss.md")
    ]
    assert len(npc_put_calls) == 1
    body = npc_put_calls[0].args[1]
    assert "## Foundry Chat History" in body
    # New section terminates with a row line — verify section trailer.
    after_heading = body.split("## Foundry Chat History", 1)[1]
    assert "grrr" in after_heading
    # patch_heading was NOT called for this NPC.
    assert obsidian.patch_heading.await_count == 0


@pytest.mark.asyncio
async def test_npc_history_row_format_includes_timestamp_source_hash(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    # Existing section so patch_heading is invoked with the row content.
    obsidian.get_note = AsyncMock(
        return_value="# Goblin Boss\n\n## Foundry Chat History\n",
    )
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    records = [_record(_id="m1", speaker="Goblin Boss", content="grrr the grrring")]
    resolver = _make_identity_resolver(
        alias_map={}, npc_roster={"goblin boss": "goblin-boss"}
    )
    matcher = _make_npc_matcher({"goblin boss": "goblin-boss"})

    await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    assert obsidian.patch_heading.await_count == 1
    call = obsidian.patch_heading.await_args
    # The row content is one of the args/kwargs.
    blob = " ".join(
        [str(a) for a in call.args] + [str(v) for v in call.kwargs.values()]
    )
    pattern = (
        r"-\s+\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s+"
        r"\(foundry,\s*key=[A-Za-z0-9|:_\-]+\)\s+grrr the grrring"
    )
    assert re.search(pattern, blob), f"row format mismatch; got: {blob!r}"


# ---------------------------------------------------------------------------
# FCM-05: dry-run parity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_no_writes_same_metric_shape(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    records = [
        _record(_id="m1", speaker="Valeros", content="hi"),
        _record(_id="m2", speaker="Goblin Boss", content="grr"),
    ]
    resolver = _make_identity_resolver(
        alias_map={"Valeros": "u1"},
        npc_roster={"goblin boss": "goblin-boss"},
    )
    matcher = _make_npc_matcher({"goblin boss": "goblin-boss"})

    result = await project_foundry_chat_memory(
        records=records,
        dry_run=True,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    assert obsidian.put_note.await_count == 0
    assert obsidian.patch_heading.await_count == 0
    assert set(result.keys()) >= {
        "player_updates",
        "npc_updates",
        "player_deduped",
        "npc_deduped",
        "unmatched_speakers",
        "dry_run",
    }
    assert result["dry_run"] is True


# ---------------------------------------------------------------------------
# Pitfall 1: schema-drift prevention — projector never writes profile.md
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_md_is_never_written_by_projector(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

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
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    bad = [
        c for c in obsidian.put_note.await_args_list
        if c.args[0].endswith("/profile.md")
    ]
    assert bad == [], f"projector must not write profile.md; got: {bad}"


# ---------------------------------------------------------------------------
# Unknown speakers must not touch any NPC note
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_speaker_does_not_create_unknown_npc_note(tmp_path):
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    records = [_record(_id="mU", speaker="Mystery Voice", content="who am i")]
    resolver = _make_identity_resolver(alias_map={}, npc_roster={})
    matcher = _make_npc_matcher({})

    result = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    npc_get_calls = [
        c for c in obsidian.get_note.await_args_list
        if c.args and "/npcs/" in str(c.args[0])
    ]
    npc_put_calls = [
        c for c in obsidian.put_note.await_args_list
        if c.args and "/npcs/" in str(c.args[0])
    ]
    assert npc_get_calls == []
    assert npc_put_calls == []
    assert "Mystery Voice" in result["unmatched_speakers"]
