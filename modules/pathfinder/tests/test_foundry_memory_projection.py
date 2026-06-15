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
async def test_projection_planner_builds_typed_plan_without_vault():
    from app.foundry_projection_planner import (
        ProjectionState,
        build_foundry_projection_plan,
        projection_key,
    )

    player_record = _record(_id="p1", speaker="Valeros", content="hi")
    npc_record = _record(_id="n1", speaker="Goblin Boss", content="grrr")
    unknown_record = _record(_id="u1", speaker="Mystery Voice", content="who")
    state = ProjectionState(
        imported_keys=set(),
        player_projection_keys={projection_key(player_record, "player_map")},
        npc_projection_keys=set(),
    )

    plan = await build_foundry_projection_plan(
        records=[player_record, npc_record, unknown_record],
        state=state,
        identity_resolver=_make_identity_resolver(
            alias_map={"Valeros": "u1"},
            npc_roster={"goblin boss": "goblin-boss"},
        ),
        npc_matcher=_make_npc_matcher({"goblin boss": "goblin-boss"}),
    )

    assert plan.player_updates == 0
    assert plan.player_deduped == 1
    assert plan.npc_updates == 1
    assert plan.npc_rows[0].npc_slug == "goblin-boss"
    assert plan.unmatched_speakers == ("Mystery Voice",)


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


# ---------------------------------------------------------------------------
# Regression: unknown-speaker rescue via npc_matcher (case-sensitive miss fix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_speaker_resolved_via_npc_matcher_gets_history(tmp_path):
    """identity_resolver returns ("unknown", token) due to case-sensitive roster miss
    (e.g. "Bandit" vs lowercased "bandit" key). The projection must rescue the
    speaker via npc_matcher (case-insensitive), write an NPC history row to the
    bandit note, and count it in npc_updates. The unmatched_speakers list must
    NOT contain "Bandit".
    """
    from app.foundry_memory_projection import project_foundry_chat_memory

    obsidian = AsyncMock()
    # The bandit NPC note exists with the history section — exercises patch_heading.
    obsidian.get_note = AsyncMock(
        return_value="# Bandit\n\n## Foundry Chat History\n",
    )
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    records = [
        _record(_id="bx1", speaker="Bandit", content="Stand and deliver!", timestamp=1710000001000),
        _record(_id="bx2", speaker="Bandit", content="Your money or your life!", timestamp=1710000002000),
        _record(_id="bx3", speaker="Bandit", content="Flee!", timestamp=1710000003000),
    ]

    # identity_resolver does a CASE-SENSITIVE roster lookup → misses "Bandit".
    def identity_resolver(speaker_token: str):
        # Simulates the production case: alias_map empty, roster keyed lowercase only.
        # "Bandit" != "bandit" → returns unknown.
        return ("unknown", speaker_token)

    # npc_matcher is case-insensitive (uses .lower()), so "Bandit" → "bandit".
    async def npc_matcher(speaker_token: str) -> str | None:
        mapping = {"bandit": "bandit"}
        return mapping.get(speaker_token.lower())

    result = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=identity_resolver,
        npc_matcher=npc_matcher,
    )

    # Core assertion: rescued speaker counted as NPC updates, not unmatched.
    assert result["npc_updates"] >= 1, (
        f"expected npc_updates >= 1, got {result['npc_updates']}; "
        f"unmatched={result['unmatched_speakers']}"
    )
    assert "Bandit" not in result["unmatched_speakers"], (
        f"'Bandit' should be resolved, not unmatched; got {result['unmatched_speakers']}"
    )

    # Obsidian received NPC history writes targeting the bandit note.
    npc_write_paths = []
    for c in obsidian.patch_heading.await_args_list:
        all_args = list(c.args) + list(c.kwargs.values())
        for a in all_args:
            if isinstance(a, str) and "bandit" in a.lower():
                npc_write_paths.append(a)
    for c in obsidian.put_note.await_args_list:
        all_args = list(c.args) + list(c.kwargs.values())
        for a in all_args:
            if isinstance(a, str) and "bandit" in a.lower() and "/npcs/" in a:
                npc_write_paths.append(a)

    assert npc_write_paths, (
        "expected at least one obsidian write referencing the bandit note path; "
        f"patch_heading calls={obsidian.patch_heading.await_args_list}, "
        f"put_note calls={obsidian.put_note.await_args_list}"
    )

    # Player notes must not be touched for this speaker.
    assert result["player_updates"] == 0


# ---------------------------------------------------------------------------
# Regression: NPC history rows must be newline-separated, not run together
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_npc_history_rows_are_newline_separated(tmp_path):
    """Project 3+ NPC records (normal, roll/number, embedded-newline content) for one
    matched NPC and assert that the ## Foundry Chat History section has each row on its
    own separate line — no two timestamps appear on the same line.

    This locks the fix for the cosmetic bug where successive patch_heading/append calls
    concatenated rows without a line separator, producing output like:
        - [2024-01-13 01:22:11] ... 26- [2023-12-02 ...] Bandit takes 1 damage.
    """
    from app.foundry_memory_projection import project_foundry_chat_memory
    from app.memory_projection_store import _NPC_HISTORY_HEADING

    # Simulate the full projection flow using a fake obsidian that actually
    # accumulates the note body in memory so we can inspect the final state.
    class FakeObsidian:
        def __init__(self, initial_body: str) -> None:
            self._body = initial_body

        async def get_note(self, path: str) -> str | None:
            if "/npcs/" in path:
                return self._body
            return None

        async def put_note(self, path: str, content: str) -> None:
            if "/npcs/" in path:
                self._body = content

        async def patch_heading(
            self, path: str, heading: str, content: str, operation: str = "append"
        ) -> None:
            # Replicate Obsidian REST append: find the heading, append content after
            # the section body. For this test the section always exists so we just
            # tack content at the end of the note body.
            if operation == "append" and heading == _NPC_HISTORY_HEADING:
                self._body = self._body + content

    npc_body_initial = "# Bandit\n\nSome background.\n\n## Foundry Chat History\n"

    records = [
        # Normal IC message
        {
            "_id": "r1",
            "type": 1,
            "speaker": {"alias": "Bandit"},
            "content": "<p>Bandit takes 1 damage.</p>",
            "timestamp": 1701476697000,  # 2023-12-02 02:24:57 UTC
        },
        # Roll message — HTML collapses to bare number
        {
            "_id": "r2",
            "type": 5,
            "speaker": {"alias": "Bandit"},
            "content": "<div>26</div>",
            "timestamp": 1705106531000,  # 2024-01-13 01:22:11 UTC
        },
        # Message whose content contains an embedded newline (after HTML strip)
        {
            "_id": "r3",
            "type": 1,
            "speaker": {"alias": "Bandit"},
            "content": "Bandit is healed for 8 damage.",
            "timestamp": 1701476700000,  # 2023-12-02 02:25:00 UTC
        },
    ]

    obsidian = FakeObsidian(npc_body_initial)

    resolver = _make_identity_resolver(alias_map={}, npc_roster={"bandit": "bandit"})
    matcher = _make_npc_matcher({"bandit": "bandit"})

    result = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=tmp_path / ".foundry_chat_import_state.json",
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    assert result["npc_updates"] == 3, (
        f"expected 3 npc_updates, got {result['npc_updates']}"
    )

    final_body = obsidian._body

    # Extract the ## Foundry Chat History section content.
    assert "## Foundry Chat History" in final_body, (
        f"section heading missing from final body:\n{final_body!r}"
    )
    section_tail = final_body.split("## Foundry Chat History", 1)[1]

    # Every history row starts with "- [" — split on that marker.
    # There must be exactly 3 rows.
    row_count = section_tail.count("\n- [")
    assert row_count == 3, (
        f"expected 3 rows in ## Foundry Chat History section, got {row_count}; "
        f"section content:\n{section_tail!r}"
    )

    # No two timestamps should appear on the same line — i.e., every line that
    # contains a timestamp pattern contains exactly one.
    import re as _re
    ts_pattern = _re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
    for line in final_body.splitlines():
        hits = ts_pattern.findall(line)
        assert len(hits) <= 1, (
            f"two timestamps on one line — rows are running together:\n{line!r}\n"
            f"full section:\n{section_tail!r}"
        )


# ---------------------------------------------------------------------------
# Fix 1 regression: gate dedupe key / npc_updates on real write result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_npc_missing_note_not_counted_and_row_written_on_rerun(tmp_path):
    """Fix 1: when append_npc_history_row returns 'skipped (npc note missing)',
    npc_updates must be 0, speaker must appear in unmatched_speakers, and the
    dedupe key must NOT be saved — so a subsequent run with the note present
    writes the row and counts it (npc_updates==1).
    """
    from app.foundry_memory_projection import project_foundry_chat_memory

    state_path = tmp_path / ".foundry_chat_import_state.json"
    records = [_record(_id="npc-miss-1", speaker="Wraith", content="Boo!", timestamp=1710001000000)]
    resolver = _make_identity_resolver(alias_map={}, npc_roster={"wraith": "wraith"})
    matcher = _make_npc_matcher({"wraith": "wraith"})

    # --- Run 1: NPC note is MISSING (get_note returns None for NPC paths) ---
    obsidian_missing = AsyncMock()
    obsidian_missing.get_note = AsyncMock(return_value=None)
    obsidian_missing.put_note = AsyncMock(return_value=None)
    obsidian_missing.patch_heading = AsyncMock(return_value=None)

    result_miss = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian_missing,
        dedupe_store_path=state_path,
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    # append_npc_history_row returned "skipped (npc note missing)" → must not count.
    assert result_miss["npc_updates"] == 0, (
        f"expected npc_updates==0 when note missing, got {result_miss['npc_updates']}"
    )
    # Speaker must surface in unmatched so the operator knows writes are failing.
    assert "Wraith" in result_miss["unmatched_speakers"], (
        f"expected 'Wraith' in unmatched_speakers, got {result_miss['unmatched_speakers']}"
    )
    # Dedupe key must NOT be in state file — retry must be allowed.
    import json as _json
    if state_path.exists():
        saved = _json.loads(state_path.read_text(encoding="utf-8"))
        npc_keys_saved = saved.get("npc_projection_keys", [])
        assert npc_keys_saved == [], (
            f"expected empty npc_projection_keys after skipped write, got {npc_keys_saved!r}"
        )

    # --- Run 2: NPC note NOW EXISTS — same record must be written (not deduped) ---
    obsidian_present = AsyncMock()
    # Note body without the history section → triggers "created" branch.
    obsidian_present.get_note = AsyncMock(
        return_value="# Wraith\n\nA spectral foe.\n"
    )
    obsidian_present.put_note = AsyncMock(return_value=None)
    obsidian_present.patch_heading = AsyncMock(return_value=None)

    result_write = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian_present,
        dedupe_store_path=state_path,
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    assert result_write["npc_updates"] == 1, (
        f"expected npc_updates==1 on rerun with note present, got {result_write['npc_updates']}; "
        f"unmatched={result_write['unmatched_speakers']}"
    )
    # The NPC note must have received the row via put_note (created branch).
    npc_put_calls = [
        c for c in obsidian_present.put_note.await_args_list
        if c.args and "/npcs/wraith.md" in str(c.args[0])
    ]
    assert npc_put_calls, (
        "expected put_note targeting mnemosyne/pf2e/npcs/wraith.md on rerun; "
        f"put_note calls: {obsidian_present.put_note.await_args_list}"
    )
    body_written = npc_put_calls[0].args[1]
    assert "Boo!" in body_written, (
        f"expected row content 'Boo!' in written NPC note body; got:\n{body_written!r}"
    )


@pytest.mark.asyncio
async def test_dry_run_npc_missing_note_still_counts(tmp_path):
    """Fix 1 dry-run parity: in dry_run mode, no real append is called so the
    note-missing gate does not apply. npc_updates must be 1 (unchanged from
    pre-fix behavior) and the dedupe key must NOT be saved (dry_run never saves).
    """
    from app.foundry_memory_projection import project_foundry_chat_memory

    state_path = tmp_path / ".foundry_chat_import_state.json"
    records = [_record(_id="dry-npc-1", speaker="Specter", content="Whooooo", timestamp=1710002000000)]
    resolver = _make_identity_resolver(alias_map={}, npc_roster={"specter": "specter"})
    matcher = _make_npc_matcher({"specter": "specter"})

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=None)  # note missing
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    result = await project_foundry_chat_memory(
        records=records,
        dry_run=True,
        obsidian_client=obsidian,
        dedupe_store_path=state_path,
        identity_resolver=resolver,
        npc_matcher=matcher,
    )

    # Dry-run must preserve metric shape: count as if the write happened.
    assert result["npc_updates"] == 1, (
        f"dry_run: expected npc_updates==1 even when note would be missing; "
        f"got {result['npc_updates']}"
    )
    # No obsidian calls in dry-run.
    assert obsidian.get_note.await_count == 0
    assert obsidian.put_note.await_count == 0
    # State file must not be written in dry-run.
    assert not state_path.exists(), "dry_run must not write state file"


# ---------------------------------------------------------------------------
# Fix 2 regression: independently-gated projection targets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_npc_history_true_player_maps_false_skips_player_writes(tmp_path):
    """Fix 2 (a): project_player_maps=False with a player-classified speaker →
    no write_player_map_section call and no player key saved to state.
    The NPC speaker must still be processed normally (project_npc_history=True).
    """
    from app.foundry_memory_projection import project_foundry_chat_memory

    state_path = tmp_path / ".foundry_chat_import_state.json"
    records = [
        _record(_id="p1", speaker="Valeros", content="I attack!", timestamp=1710003000000),
        _record(_id="n1", speaker="Goblin Boss", content="Flee!", timestamp=1710003001000),
    ]
    resolver = _make_identity_resolver(
        alias_map={"Valeros": "u1"},
        npc_roster={"goblin boss": "goblin-boss"},
    )
    matcher = _make_npc_matcher({"goblin boss": "goblin-boss"})

    obsidian = AsyncMock()
    # NPC note exists (with history section) so patch_heading is used.
    obsidian.get_note = AsyncMock(
        return_value="# Goblin Boss\n\n## Foundry Chat History\n"
    )
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    result = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=state_path,
        identity_resolver=resolver,
        npc_matcher=matcher,
        project_player_maps=False,
        project_npc_history=True,
    )

    # Player writes must be completely absent.
    player_put_calls = [
        c for c in obsidian.put_note.await_args_list
        if c.args and "/players/" in str(c.args[0])
    ]
    assert player_put_calls == [], (
        f"expected no player-map put_note calls with project_player_maps=False; "
        f"got: {player_put_calls}"
    )
    assert result["player_updates"] == 0, (
        f"expected player_updates==0, got {result['player_updates']}"
    )

    # Player key must not be saved in state.
    import json as _json
    saved = _json.loads(state_path.read_text(encoding="utf-8"))
    assert saved.get("player_projection_keys", []) == [], (
        f"expected empty player_projection_keys with project_player_maps=False; "
        f"got {saved['player_projection_keys']!r}"
    )

    # NPC processing must still work normally.
    assert result["npc_updates"] == 1, (
        f"expected npc_updates==1 (NPC enabled), got {result['npc_updates']}"
    )
    assert obsidian.patch_heading.await_count == 1


@pytest.mark.asyncio
async def test_project_npc_history_false_player_maps_true_skips_npc_writes(tmp_path):
    """Fix 2 (b): project_npc_history=False with an npc-classified speaker →
    no append_npc_history_row call and no npc key saved to state.
    The player speaker must still be processed normally (project_player_maps=True).
    """
    from app.foundry_memory_projection import project_foundry_chat_memory

    state_path = tmp_path / ".foundry_chat_import_state.json"
    records = [
        _record(_id="p2", speaker="Merisiel", content="Sneaking...", timestamp=1710004000000),
        _record(_id="n2", speaker="Troll", content="Smash!", timestamp=1710004001000),
    ]
    resolver = _make_identity_resolver(
        alias_map={"Merisiel": "u2"},
        npc_roster={"troll": "troll"},
    )
    matcher = _make_npc_matcher({"troll": "troll"})

    obsidian = AsyncMock()
    obsidian.get_note = AsyncMock(return_value=None)
    obsidian.put_note = AsyncMock(return_value=None)
    obsidian.patch_heading = AsyncMock(return_value=None)

    result = await project_foundry_chat_memory(
        records=records,
        dry_run=False,
        obsidian_client=obsidian,
        dedupe_store_path=state_path,
        identity_resolver=resolver,
        npc_matcher=matcher,
        project_player_maps=True,
        project_npc_history=False,
    )

    # NPC writes must be completely absent.
    npc_put_calls = [
        c for c in obsidian.put_note.await_args_list
        if c.args and "/npcs/" in str(c.args[0])
    ]
    assert npc_put_calls == [], (
        f"expected no NPC put_note calls with project_npc_history=False; "
        f"got: {npc_put_calls}"
    )
    assert obsidian.patch_heading.await_count == 0, (
        f"expected no patch_heading calls with project_npc_history=False; "
        f"got: {obsidian.patch_heading.await_count}"
    )
    assert result["npc_updates"] == 0, (
        f"expected npc_updates==0, got {result['npc_updates']}"
    )

    # NPC key must not be saved in state.
    import json as _json
    saved = _json.loads(state_path.read_text(encoding="utf-8"))
    assert saved.get("npc_projection_keys", []) == [], (
        f"expected empty npc_projection_keys with project_npc_history=False; "
        f"got {saved['npc_projection_keys']!r}"
    )

    # Player processing must still work normally.
    assert result["player_updates"] == 1, (
        f"expected player_updates==1 (player maps enabled), got {result['player_updates']}"
    )
    player_put_calls = [
        c for c in obsidian.put_note.await_args_list
        if c.args and "/players/" in str(c.args[0])
    ]
    assert player_put_calls, (
        "expected a put_note call targeting mnemosyne/pf2e/players/ for the player record"
    )
