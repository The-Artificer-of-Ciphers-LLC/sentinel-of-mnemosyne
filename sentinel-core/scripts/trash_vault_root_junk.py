"""One-shot trash script for vault-root junk files (260427-cza).

Moves five named files from the vault root into ``_trash/{today}/`` via
the existing sweeper trash mechanism. Missing files are skipped silently.

Usage:
    uv run python scripts/trash_vault_root_junk.py            # live trash
    uv run python scripts/trash_vault_root_junk.py --dry-run  # preview only

The script connects to the Obsidian REST API using the same settings the
sentinel-core service uses (``OBSIDIAN_API_URL`` / ``OBSIDIAN_API_KEY``).
The Mac host's Obsidian must be running for the REST API to be reachable.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import httpx

from app.config import settings
from app.services.vault_sweeper import _today_str
from app.vault import ObsidianVault

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("trash_vault_root_junk")


JUNK_FILES: list[str] = [
    "CLAUDE.md",
    "PROJECT.md",
    "README.md",
    "AGENTS.md",
    "index.md",
]

TRASH_REASON = "vault-root junk from another project (260427-cza cleanup)"


async def _run(dry_run: bool) -> int:
    """Returns process exit code (0 always — missing files are not errors)."""
    base_url = settings.obsidian_api_url
    api_key = settings.obsidian_api_key
    today = _today_str()

    trashed = 0
    skipped = 0
    failed = 0

    async with httpx.AsyncClient() as http_client:
        vault = ObsidianVault(http_client, base_url, api_key)

        for filename in JUNK_FILES:
            try:
                body = await vault.read_note(filename)
            except Exception as exc:
                logger.warning("error: read failed for %s: %s", filename, exc)
                failed += 1
                continue

            if not body:
                logger.info("skipped (missing): %s", filename)
                skipped += 1
                continue

            dst = f"_trash/{today}/{filename}"
            if dry_run:
                logger.info("WOULD trash: %s -> %s", filename, dst)
                trashed += 1
                continue

            try:
                actual_dst = await vault.move_to_trash(filename, reason=TRASH_REASON)
                logger.info("trashed: %s -> %s", filename, actual_dst)
                trashed += 1
            except Exception as exc:
                logger.warning("error: trash failed for %s: %s", filename, exc)
                failed += 1

    label = "Would trash" if dry_run else "Trashed"
    logger.info(
        "%s %d of %d vault-root junk files (skipped %d, failed %d).",
        label,
        trashed,
        len(JUNK_FILES),
        skipped,
        failed,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trash vault-root junk files (CLAUDE.md, PROJECT.md, README.md, AGENTS.md, index.md)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only — do not move any files.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
