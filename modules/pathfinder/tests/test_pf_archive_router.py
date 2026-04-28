"""Tests for the cartosia archive router (260427-czb Task 1).

The router is a pure function over a (Path, content) pair: it does NOT touch
the vault, the LLM, or the network. Each test calls `route()` directly and
asserts on the returned `RouteDecision` dataclass fields.

Per CLAUDE.md Behavioral-Test-Only Rule: every test exercises the function
under test with realistic inputs and asserts on observable outputs. No
source-grep, no `assert True`, no mock-only call shape assertions.

Fixtures live at tests/fixtures/cartosia/ — small but structurally faithful
to the real archive (path layout + first 10–30 lines of body content
preserved so content sniffs are exercised end-to-end).
"""
from __future__ import annotations

from pathlib import Path


from app.pf_archive_router import RouteDecision, route


FIXTURES = Path(__file__).parent / "fixtures" / "cartosia"


# ---------------------------------------------------------------------------
# Known-NPC slug set used by dialogue-owner inference. In production this is
# built by the importer's first pass over the archive; in tests we pin it so
# the router contract is hermetic.
# ---------------------------------------------------------------------------

KNOWN_NPC_SLUGS = frozenset({
    "fenn-the-beggar",
    "veela-and-tarek",
    "ashen-gorl-the-singed",
    "alice-twoorb",
})


def _read(rel: str) -> tuple[Path, str]:
    p = FIXTURES / rel
    return p, p.read_text(encoding="utf-8")


def _route(rel: str) -> RouteDecision:
    p, content = _read(rel)
    return route(p, content, archive_root=FIXTURES, known_npc_slugs=KNOWN_NPC_SLUGS)


# ---------------------------------------------------------------------------
# Bucket: Format A NPC (PF2e stat block in The NPCs/)
# ---------------------------------------------------------------------------


def test_format_a_npc_with_stat_block_routes_to_npc_a():
    decision = _route("The NPCs/Fenn the Beggar.md")
    assert decision.bucket == "npc_a"
    assert decision.slug == "fenn-the-beggar"
    assert decision.dest == "mnemosyne/pf2e/npcs/fenn-the-beggar.md"


def test_two_npc_file_imports_as_single_record():
    """Veela and Tarek - Street Hood Twins.md is one file with two NPCs in it.

    Research §Edge case 2 / Pitfall 6: import as a single NPC with the combined
    name verbatim. Slug = "veela-and-tarek".
    """
    decision = _route("The NPCs/Veela and Tarek - Street Hood Twins.md")
    assert decision.bucket == "npc_a"
    assert decision.slug == "veela-and-tarek"
    assert decision.dest == "mnemosyne/pf2e/npcs/veela-and-tarek.md"


# ---------------------------------------------------------------------------
# Bucket: Format B NPC (Cartosia/**/X.md with ### Biography + ### Appearance)
# ---------------------------------------------------------------------------


def test_format_b_npc_with_biography_and_appearance_routes_to_npc_b():
    decision = _route("Cartosia/Ostenwald/Otari/Alice Twoorb.md")
    assert decision.bucket == "npc_b"
    assert decision.slug == "alice-twoorb"
    assert decision.dest == "mnemosyne/pf2e/npcs/alice-twoorb.md"


# ---------------------------------------------------------------------------
# Bucket: NPC dialogue (orphan filename in The NPCs/)
# ---------------------------------------------------------------------------


def test_orphan_dialogue_resolves_owner_via_filename_prefix():
    """`Veela Dialogue - Goodbye.md` is a top-level dialogue file. Owner is
    inferred from the leading proper-noun token (`Veela`) prefix-matched
    against the known-NPC slug set; `veela` matches `veela-and-tarek`.
    """
    decision = _route("The NPCs/Veela Dialogue - Goodbye.md")
    assert decision.bucket == "npc_dialogue"
    assert decision.owner_slug == "veela-and-tarek"


def test_dialogue_inside_npc_as_folder_uses_parent_dir_as_owner():
    """`The NPCs/Ashen Gorl "The Singed"/Singed Dialogue - Party Acknowledgment.md`
    — parent dir is the NPC envelope; owner_slug = the dir slug.
    """
    decision = _route('The NPCs/Ashen Gorl "The Singed"/Singed Dialogue - Party Acknowledgment.md')
    assert decision.bucket == "npc_dialogue"
    assert decision.owner_slug == "ashen-gorl-the-singed"


def test_dialogue_filename_typo_is_matched_case_insensitively():
    """Real archive has `THings Said.md` (capital H). Detection must be
    case-insensitive on the filename keywords.
    """
    decision = _route(
        'Cartosia/Ostenwald/Otari/The Bleating Gate/The Embercloaks/'
        'The NPCs/Ashen Gorl "The Singed"/THings Said.md'
    )
    assert decision.bucket == "npc_dialogue"
    assert decision.owner_slug == "ashen-gorl-the-singed"


# ---------------------------------------------------------------------------
# Edge case: Adventure Hooks under The NPCs/ — filename keyword overrides
# the parent-dir heuristic.
# ---------------------------------------------------------------------------


def test_adventure_hooks_under_the_npcs_routes_to_arc_not_npc():
    decision = _route("The Embercloaks/The NPCs/Adventure Hooks.md")
    assert decision.bucket == "arc"
    assert decision.dest == "mnemosyne/pf2e/lore/arcs/adventure-hooks-embercloaks.md"


# ---------------------------------------------------------------------------
# Edge case: Talons of the Claw — no PF2e stat block + no Format B → faction.
# ---------------------------------------------------------------------------


def test_talons_of_the_claw_with_no_npc_sniff_routes_to_faction():
    decision = _route("The Embercloaks/The NPCs/Talons of the Claw.md")
    assert decision.bucket == "faction"
    assert decision.dest == "mnemosyne/pf2e/lore/factions/talons-of-the-claw.md"


# ---------------------------------------------------------------------------
# Bucket: Location (Cartosia/** with no NPC sniff).
# ---------------------------------------------------------------------------


def test_location_under_cartosia_routes_to_locations():
    decision = _route("Cartosia/Ostenwald/Otari/The Bleating Gate/The Bleating Gate.md")
    assert decision.bucket == "location"
    assert decision.dest == "mnemosyne/pf2e/locations/the-bleating-gate.md"


# ---------------------------------------------------------------------------
# Bucket: Homebrew (Decided Rules/) — sibling of rulings/, NOT under it.
# ---------------------------------------------------------------------------


def test_decided_rules_routes_to_homebrew_sibling_not_under_rulings():
    decision = _route("Decided Rules/Movement Rules.md")
    assert decision.bucket == "homebrew"
    # CRITICAL: must be sibling of rulings/, not rulings/homebrew/, so the
    # Phase 33 rules engine does not surface a phantom 'homebrew' topic.
    assert decision.dest == "mnemosyne/pf2e/homebrew/movement-rules.md"
    assert "rulings/" not in decision.dest


# ---------------------------------------------------------------------------
# Bucket: Harvest table (Crafting System/Harvest Table - X.md).
# ---------------------------------------------------------------------------


def test_harvest_table_filename_routes_to_harvest_cache():
    decision = _route("Crafting System/Harvest Table - Grizzly Bear.md")
    assert decision.bucket == "harvest"
    assert decision.dest == "mnemosyne/pf2e/harvest/cache/grizzly-bear.md"


# ---------------------------------------------------------------------------
# Bucket: Lore (Codex of Elemental Gateways/).
# ---------------------------------------------------------------------------


def test_codex_lore_routes_to_lore_with_topic_subdir():
    decision = _route("Codex of Elemental Gateways/Codex Contents - Lore and Structure.md")
    assert decision.bucket == "lore"
    assert decision.dest.startswith("mnemosyne/pf2e/lore/codex/")
    assert decision.dest.endswith(".md")


# ---------------------------------------------------------------------------
# Bucket: Session.
# ---------------------------------------------------------------------------


def test_session_log_routes_to_archive_import_filename():
    """Per Pitfall 9: `as of YYYY-MM-DD` is session prep, not session date.
    `session-log.md` always lands at `sessions/_archive-import.md` literally.
    """
    decision = _route("session-log.md")
    assert decision.bucket == "session"
    assert decision.dest == "mnemosyne/pf2e/sessions/_archive-import.md"


# ---------------------------------------------------------------------------
# Bucket: Skip — body shorter than 200 chars.
# ---------------------------------------------------------------------------


def test_short_readme_stub_routes_to_skip():
    decision = _route("Cartosia - The Dawn Lands.md")
    assert decision.bucket == "skip"


# ---------------------------------------------------------------------------
# RouteDecision shape sanity (no internal fields leaking).
# ---------------------------------------------------------------------------


def test_route_decision_exposes_expected_fields():
    decision = _route("The NPCs/Fenn the Beggar.md")
    assert isinstance(decision, RouteDecision)
    # Every decision must carry a non-empty reason for the dry-run report.
    assert isinstance(decision.reason, str) and decision.reason


def test_route_returns_stable_slug_for_same_input():
    """Idempotency at the routing layer — calling route() twice on the same
    input must yield the same slug + dest (used by the importer's dedupe pass).
    """
    a = _route("The NPCs/Fenn the Beggar.md")
    b = _route("The NPCs/Fenn the Beggar.md")
    assert a.slug == b.slug
    assert a.dest == b.dest
    assert a.bucket == b.bucket


# ---------------------------------------------------------------------------
# Real-archive corner cases discovered in Task 5 dry-run.
# ---------------------------------------------------------------------------


def test_format_a_accepts_level_n_npc_title_in_lieu_of_creature_marker(tmp_path):
    """Real archive uses 'Level N NPC[s]' in titles instead of '**Creature N**'.

    `Veela & Tarek` is the canonical example — has `**AC** 18` and
    'Level 2 NPCs' in the H1, but no '**Creature N**' marker. Must
    classify as npc_a, not faction.
    """
    p = tmp_path / "The NPCs" / "Veela and Tarek - Street Hood Twins.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "# Veela & Tarek, the Street Hood Twins (Level 2 NPCs)\n\n"
        "*Identical Tricksters & Local Shadows*\n\n"
        "**AC** 18 | **HP** 32 (each) | **Speed** 30 ft.\n\n"
        + ("body " * 60)
    )
    decision = route(p, p.read_text(), archive_root=tmp_path, known_npc_slugs=set())
    assert decision.bucket == "npc_a"
    assert decision.slug == "veela-and-tarek"


def test_format_b_accepts_bold_appearance_paired_with_biography(tmp_path):
    """Real archive uses `### Biography` + `**Appearance:**` (bold prefix,
    not header). Provost Marshall Silas is the canonical example.
    """
    p = tmp_path / "Cartosia" / "Otari" / "Silas.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "Main\n====\n\n### Biography\n\n"
        "**Appearance:** Silas is gnarled and weathered, with a salt-and-pepper beard.\n\n"
        "Personality\n===========\n"
        + ("body text " * 40)
    )
    decision = route(p, p.read_text(), archive_root=tmp_path, known_npc_slugs=set())
    assert decision.bucket == "npc_b"
    assert decision.slug == "silas"


def test_personal_npc_markers_under_the_npcs_route_to_npc_b(tmp_path):
    """Under `The NPCs/` with no Biography/Appearance/stat-block but with
    Role/Function/Personality markers → npc_b, NOT faction.
    """
    p = tmp_path / "Cartosia" / "X" / "The NPCs" / "Apprentice Aldric.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "# Apprentice Aldric\n\n"
        "**Role:** Front-shop contact at the Viremount\n"
        "**Function:** Gatekeeper\n\n"
        + ("body " * 60)
    )
    decision = route(p, p.read_text(), archive_root=tmp_path, known_npc_slugs=set())
    assert decision.bucket == "npc_b"
    assert decision.slug == "apprentice-aldric"


def test_factional_file_under_the_npcs_still_routes_to_faction(tmp_path):
    """`Talons of the Claw.md` lacks personal-NPC markers → still faction."""
    p = tmp_path / "The NPCs" / "Talons of the Claw.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "# Talons of the Claw\n\nA clandestine faction of dragon cultists.\n"
        + ("body " * 80)
    )
    decision = route(p, p.read_text(), archive_root=tmp_path, known_npc_slugs=set())
    assert decision.bucket == "faction"


def test_personal_npc_markers_under_cartosia_route_to_npc_b(tmp_path):
    """Under Cartosia/** with personal-NPC markers but no Biography/stat-block
    → npc_b, NOT location."""
    p = tmp_path / "Cartosia" / "Otari" / "Some Person.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "# Some Person\n\n### Personality\n\n"
        "She is cheerful.\n\n### Goals\n\nFind the lost ring.\n"
        + ("body " * 50)
    )
    decision = route(p, p.read_text(), archive_root=tmp_path, known_npc_slugs=set())
    assert decision.bucket == "npc_b"
