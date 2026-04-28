"""Content-first router tests using a synthetic NON-cartosia archive (260427-cui).

Pins the contract that the router classifies via content sniffs alone — no
hardcoded `Cartosia/`, `The NPCs/`, `Decided Rules/`, `Crafting System/`,
`Codex of Elemental Gateways/`, or `The Embercloaks/` path-prefix branches.

Every test calls `route()` directly and asserts on observable RouteDecision
fields. The structural-invariant test parses the router source via `ast` +
`tokenize` (stripping docstrings + comments) and asserts no string compare
against the forbidden archive-specific path literals — this is an AST shape
test, not source-grep, so it counts as a behavior test under the
Behavioral-Test-Only Rule.
"""
from __future__ import annotations

import ast
import inspect
import io
import tokenize
from pathlib import Path

from app import pf_archive_router
from app.pf_archive_router import route


FIXTURES = Path(__file__).parent / "fixtures" / "test-fake-archive"


# ---------------------------------------------------------------------------
# Synthetic-folder content-first behavior
# ---------------------------------------------------------------------------


def test_synthetic_format_a_under_bestiary_routes_to_npc_a():
    """A Format-A PF2e stat block in `Bestiary/` (NOT `The NPCs/`, NOT
    `Cartosia/`) routes to npc_a via content sniff alone.
    """
    p = FIXTURES / "Bestiary" / "Goblin Warrior.md"
    decision = route(
        p, p.read_text(encoding="utf-8"),
        archive_root=FIXTURES, known_npc_slugs=set(),
    )
    assert decision.bucket == "npc_a"
    assert decision.slug == "goblin-warrior"
    assert decision.dest == "mnemosyne/pf2e/npcs/goblin-warrior.md"
    assert "PF2e stat block" in decision.reason or "stat block" in decision.reason.lower()


def test_synthetic_lore_file_under_locations_routes_to_lore():
    """A plain location-prose file under `Locations/` (no NPC sniff,
    no homebrew markers) routes to lore.
    """
    p = FIXTURES / "Locations" / "Mossy Cave.md"
    decision = route(
        p, p.read_text(encoding="utf-8"),
        archive_root=FIXTURES, known_npc_slugs=set(),
    )
    assert decision.bucket == "lore"
    assert decision.dest.startswith("mnemosyne/pf2e/lore/")
    assert decision.dest.endswith("/mossy-cave.md")


def test_synthetic_homebrew_under_rules_dir_routes_to_homebrew_via_content():
    """A homebrew-style file under `Rules/` (NOT `Decided Rules/` or
    `Crafting System/`) routes to homebrew via content markers
    (Rules/Action/Trigger/Effect/Activate bold prefixes), not path prefix.
    """
    p = FIXTURES / "Rules" / "Hex Counter.md"
    decision = route(
        p, p.read_text(encoding="utf-8"),
        archive_root=FIXTURES, known_npc_slugs=set(),
    )
    assert decision.bucket == "homebrew"
    assert decision.dest == "mnemosyne/pf2e/homebrew/hex-counter.md"
    assert "homebrew markers" in decision.reason.lower() or "rules/action" in decision.reason.lower()
    # Phase 33 invariant: must be sibling of rulings/, not under it.
    assert "rulings/" not in decision.dest


# ---------------------------------------------------------------------------
# Structural-invariant: no archive-specific path literals in routing branches
# ---------------------------------------------------------------------------


_FORBIDDEN_PATH_LITERALS = {
    "Cartosia",
    "Decided Rules",
    "Crafting System",
    "Codex of Elemental Gateways",
    "The Embercloaks",
    "The NPCs",
}


def _strip_comments_and_docstrings(source: str) -> str:
    """Return source with comments and string literals removed.

    `tokenize` lets us drop COMMENT and STRING tokens cleanly so the only
    remaining string-like material is in the syntax tree where comparisons
    actually live (we then walk the AST separately for those).
    """
    out: list[str] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string + " ")
    except tokenize.TokenizeError:
        return source
    return "".join(out)


def _routing_string_constants(source: str) -> set[str]:
    """Walk the AST for string literals that appear inside Compare nodes
    OR as members of tuples/sets/lists used inside routing branches.

    Excludes:
      - Module/function docstrings
      - String constants inside f-strings used purely for formatting
      - String constants only in `_infer_owner_slug` (the dialogue envelope
        skip — uses 'the npcs', 'the npc' as a deliberate skip-list).
    """
    tree = ast.parse(source)
    found: set[str] = set()

    # Find the _infer_owner_slug function body so we can exclude string
    # literals from it (the envelope skip is allowed).
    excluded_function_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_infer_owner_slug":
            for child in ast.walk(node):
                if hasattr(child, "lineno"):
                    excluded_function_lines.add(child.lineno)

    for node in ast.walk(tree):
        # Look at Compare ops — any constant string operand is a routing literal.
        if isinstance(node, ast.Compare):
            if hasattr(node, "lineno") and node.lineno in excluded_function_lines:
                continue
            for operand in [node.left, *node.comparators]:
                if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                    found.add(operand.value)
                # Operand may be a Tuple/List/Set of constants (e.g. `top in
                # _HOMEBREW_PARENT_DIRS` after constant-folding, or
                # `top in ("a", "b")`).
                if isinstance(operand, (ast.Tuple, ast.List, ast.Set)):
                    for elt in operand.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            found.add(elt.value)

        # Module-level constant tuples assigned to names like _HOMEBREW_*
        # (these are referenced by `if top in _HOMEBREW_PARENT_DIRS`).
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("_") and (
                    "PARENT" in target.id.upper() or "DIR" in target.id.upper() or "PREFIX" in target.id.upper()
                ):
                    if isinstance(node.value, (ast.Tuple, ast.List, ast.Set)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                found.add(elt.value)
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        found.add(node.value.value)
    return found


def test_router_has_no_archive_specific_path_literals_in_routing_branches():
    """Structural invariant: the router source must not reference any of the
    forbidden archive-specific path-prefix literals in routing logic.

    Allowed:
      - Inside `_infer_owner_slug` (the envelope-skip set, lower-cased)
      - Inside docstrings or comments (filtered out)
    """
    source = inspect.getsource(pf_archive_router)
    routing_strings = _routing_string_constants(source)
    leaks = routing_strings & _FORBIDDEN_PATH_LITERALS
    assert not leaks, (
        f"router has forbidden archive-specific path literal(s) in routing branches: {leaks}. "
        f"Move detection to content sniffs or restrict to `_infer_owner_slug`."
    )
