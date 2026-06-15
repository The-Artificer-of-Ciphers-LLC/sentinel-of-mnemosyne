"""Catalog of Discord ``:pf`` command nouns, verbs, and usage text."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PathfinderCommandCatalogEntry:
    """Facts about one top-level Pathfinder command noun."""

    noun: str
    help_example: str
    usage: str
    verbs: tuple[str, ...] = ()
    wildcard: bool = False
    admin_only: bool = False
    deprecated: bool = False

    @property
    def registry_verbs(self) -> frozenset[str]:
        verbs = set(self.verbs)
        if self.wildcard:
            verbs.add("*")
        return frozenset(verbs)


HARVEST_USAGE = "Usage: `:pf harvest <Name>[,<Name>...]`"
RULE_QUERY_USAGE = (
    "Usage: `:pf rule <question>` | "
    "`:pf rule show <topic>` | "
    "`:pf rule history [N]` | "
    "`:pf rule list`"
)
INGEST_USAGE = (
    "Usage: `:pf ingest <subfolder> [--live] [--dry-run] "
    "[--limit N] [--force] [--confirm-large]` (admin-only)"
)
CARTOSIA_USAGE = (
    "Usage: `:pf cartosia <archive_path> [--live] [--dry-run] "
    "[--limit N] [--force] [--confirm-large]` (admin-only)"
)
FOUNDRY_IMPORT_MESSAGES_USAGE = (
    "Usage: `:pf foundry import-messages <inbox_dir> "
    "[--dry-run|--live] [--limit N]` (admin-only)"
)
PLAYER_USAGE = (
    "Usage: `:pf player <start|note|ask|npc|recall|todo|style|canonize|cancel> ...`"
)


COMMAND_CATALOG: dict[str, PathfinderCommandCatalogEntry] = {
    "npc": PathfinderCommandCatalogEntry(
        noun="npc",
        help_example=(
            "`:pf npc <create|update|show|relate|import|export|token|token-image|stat|pdf|say> ...`"
        ),
        usage=(
            "Usage: `:pf npc <create|update|show|relate|import|export|token|token-image|stat|pdf|say> ...`"
        ),
        verbs=(
            "create",
            "update",
            "show",
            "relate",
            "import",
            "export",
            "token",
            "token-image",
            "stat",
            "pdf",
            "say",
        ),
    ),
    "harvest": PathfinderCommandCatalogEntry(
        noun="harvest",
        help_example="`:pf harvest <Name>[,<Name>...]`",
        usage=HARVEST_USAGE,
        wildcard=True,
    ),
    "rule": PathfinderCommandCatalogEntry(
        noun="rule",
        help_example="`:pf rule <question>|show <topic>|history [N]|list`",
        usage=RULE_QUERY_USAGE,
        verbs=("query", "list", "show", "history"),
        wildcard=True,
    ),
    "session": PathfinderCommandCatalogEntry(
        noun="session",
        help_example="`:pf session <start|show|end> ...`",
        usage="Usage: `:pf session <start|show|end> ...`",
        verbs=("start", "show", "end"),
    ),
    "ingest": PathfinderCommandCatalogEntry(
        noun="ingest",
        help_example="`:pf ingest <subfolder> [--live] [--limit N]` (admin-only)",
        usage=INGEST_USAGE,
        wildcard=True,
        admin_only=True,
    ),
    "cartosia": PathfinderCommandCatalogEntry(
        noun="cartosia",
        help_example="`:pf cartosia <archive_path> [--live] [--limit N]` (deprecated, admin-only)",
        usage=CARTOSIA_USAGE,
        wildcard=True,
        admin_only=True,
        deprecated=True,
    ),
    "foundry": PathfinderCommandCatalogEntry(
        noun="foundry",
        help_example=(
            "`:pf foundry import-messages <inbox_dir> [--dry-run|--live] [--limit N]` "
            "(admin-only)"
        ),
        usage=FOUNDRY_IMPORT_MESSAGES_USAGE,
        verbs=("import-messages",),
        admin_only=True,
    ),
    "player": PathfinderCommandCatalogEntry(
        noun="player",
        help_example="`:pf player <start|note|ask|npc|recall|todo|style|canonize|cancel> ...`",
        usage=PLAYER_USAGE,
        verbs=(
            "start",
            "note",
            "ask",
            "npc",
            "recall",
            "todo",
            "style",
            "canonize",
            "cancel",
        ),
    ),
}

PF_NOUNS = frozenset(COMMAND_CATALOG)
CATALOG_REGISTRY_VERBS = {
    noun: entry.registry_verbs for noun, entry in COMMAND_CATALOG.items()
}
TOP_LEVEL_HELP_NOUNS = (
    "npc",
    "harvest",
    "rule",
    "session",
    "player",
    "ingest",
    "cartosia",
    "foundry",
)


def top_level_usage_message() -> str:
    examples = [COMMAND_CATALOG[noun].help_example for noun in TOP_LEVEL_HELP_NOUNS]
    return "Usage: " + " or ".join(examples)
