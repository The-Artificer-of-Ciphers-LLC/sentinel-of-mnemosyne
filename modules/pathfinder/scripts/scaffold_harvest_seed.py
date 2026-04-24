"""One-shot scaffolder — prints YAML skeleton + roster for level-1-3 monsters from Foundry pf2e.

Usage:
    # Default: write YAML scaffold to stdout (DM pipes to harvest-tables.yaml.scaffold)
    cd modules/pathfinder && uv run python scripts/scaffold_harvest_seed.py > data/harvest-tables.yaml.scaffold

    # --output <path>: write the plain roster (one monster per line: "<name>\tlevel") to <path>
    cd modules/pathfinder && uv run python scripts/scaffold_harvest_seed.py --output data/harvest-roster.txt

Downloads the GitHub directory index for packs/pathfinder-monster-core, reads each JSON
file's `system.details.level.value` field, filters to levels 1-3, and:
  - stdout mode: prints a YAML scaffold the DM hand-edits to fill in `components`
  - --output mode: writes a simple "<Name>\t<level>" roster file (Task 32-02-03 input)

This script is NOT imported by app.main and does NOT need to run inside the Docker
container. It is a DM convenience tool — the authoritative seed is the DM-curated
harvest-tables.yaml, not the script output.

Per S7 (HTTP client — httpx ONLY): uses httpx.Client (sync) for consistency with the
rest of the project. No requests, no aiohttp, no urllib.
"""

from __future__ import annotations

import argparse
import sys

import httpx

# The foundryvtt/pf2e repo restructured packs in 2024: bestiary packs live at
# packs/pf2e/<pack-name>/. Default branch is v14-dev (not master); using the
# Contents API and following each entry's `download_url` insulates the script
# from future branch renames.
#   https://github.com/foundryvtt/pf2e/tree/v14-dev/packs/pf2e/pathfinder-monster-core
REPO_API = "https://api.github.com/repos/foundryvtt/pf2e/contents/packs/pf2e/pathfinder-monster-core"


def fetch_level_1_to_3_monsters() -> list[dict]:
    """Return [{name, level, slug}] for all L1-L3 monsters in pathfinder-monster-core."""
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        listing_resp = client.get(REPO_API)
        listing_resp.raise_for_status()
        listing = listing_resp.json()
        if not isinstance(listing, list):
            raise RuntimeError(
                f"GitHub Contents API returned non-list at {REPO_API}: {listing!r}"
            )
        out: list[dict] = []
        for entry in listing:
            if entry.get("type") != "file":
                continue
            name = entry.get("name", "")
            if not name.endswith(".json"):
                continue
            slug = name[:-5]
            raw_url = entry.get("download_url")
            if not raw_url:
                print(f"# skipped {slug}: no download_url", file=sys.stderr)
                continue
            try:
                doc = client.get(raw_url).json()
            except Exception as exc:  # noqa: BLE001 — best-effort scaffolder
                print(f"# skipped {slug}: {exc}", file=sys.stderr)
                continue
            level = (
                doc.get("system", {})
                .get("details", {})
                .get("level", {})
                .get("value")
            )
            if not isinstance(level, int) or level < 1 or level > 3:
                continue
            out.append({"name": doc.get("name", slug), "level": level, "slug": slug})
    out.sort(key=lambda m: (m["level"], m["name"]))
    return out


def render_roster(monsters: list[dict]) -> str:
    """Emit a deterministic roster for Task 32-02-03 hand-curation.

    One monster per line: '<Name>\t<level>'. Sorted by (level, name).
    Task 32-02-03 binds the YAML entries line-by-line to this file.
    """
    return "\n".join(f"{m['name']}\t{m['level']}" for m in monsters) + "\n"


def render_yaml_scaffold(monsters: list[dict]) -> str:
    """Emit a YAML scaffold to stdout — DM hand-fills components per monster.

    Each entry omits the `components:` key entirely, AND emits a fully-commented-out
    example block showing the shape the DM should uncomment and fill in. This
    guarantees the file is Pydantic-valid at all DM-edit intermediate states:
      - A fresh scaffold (no components key) loads because `components` defaults to [].
      - A half-uncommented entry still has NO top-level components key until the DM
        uncomments ALL of the example lines together — no partial-component crash path.
    """
    lines = [
        "# modules/pathfinder/data/harvest-tables.yaml",
        "# Hand-curated harvest table for PF2e level 1-3 monsters.",
        "# Medicine DCs from Table 10-5 DCs by Level (GM Core pg. 52).",
        "# Craftable vendor values from Foundry VTT pf2e equipment pack (ORC license).",
        "# Derived from Foundry VTT pf2e system — ORC license, see github.com/foundryvtt/pf2e.",
        "",
        'version: "1.0"',
        'source: "foundryvtt-pf2e"',
        "levels: [1, 2, 3]",
        "monsters:",
    ]
    for m in monsters:
        lines.append(f'  - name: "{m["name"]}"')
        lines.append(f"    level: {m['level']}")
        lines.append("    traits: []        # DM: fill from Foundry JSON system.traits.value")
        # DO NOT emit the empty-list form as a live key: if the DM later adds a
        # nested entry lacking required fields, Pydantic validation crashes the
        # lifespan. Instead, emit a fully-commented-out example block. The DM
        # uncomments the entire block together, preserving Pydantic validity at
        # every intermediate step. The module loads fine with no `components`
        # key — Pydantic default_factory supplies the empty list.
        lines.append("    # components:")
        lines.append('    #   - name: "Hide"')
        lines.append("    #     medicine_dc: 15    # L1→15, L2→16, L3→18 (Table 10-5)")
        lines.append("    #     craftable:")
        lines.append('    #       - name: "Waterskin"')
        lines.append("    #         crafting_dc: 10")
        lines.append('    #         value: "5 sp"')
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=None,
        help="If set, write a plain roster (name\\tlevel per line) to this path. Otherwise print YAML scaffold to stdout.",
    )
    args = parser.parse_args()

    monsters = fetch_level_1_to_3_monsters()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fp:
            fp.write(render_roster(monsters))
        print(f"# wrote {len(monsters)} monsters to {args.output}", file=sys.stderr)
    else:
        print(render_yaml_scaffold(monsters))
        print(f"# {len(monsters)} monsters scaffolded (levels 1-3)", file=sys.stderr)


if __name__ == "__main__":
    main()
