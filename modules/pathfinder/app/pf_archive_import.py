"""Pathfinder archive import compatibility interface.

Builds a side-effect-free PF Archive Import Plan, then delegates live write
policy to PF Archive Import Execution.
"""

from __future__ import annotations

from app.legendkeeper_image import download_token
from app.pf_archive_import_execution import (
    ImportReport,
    ObsidianLike,
    execute_pf_archive_import_plan,
)
from app.pf_archive_import_plan import (
    ImportCostGuardError,
    build_pf_archive_import_plan,
)

__all__ = ["ImportCostGuardError", "ImportReport", "run_import"]


async def run_import(
    *,
    archive_root: str,
    dry_run: bool,
    limit: int | None,
    force: bool,
    confirm_large: bool,
    obsidian_client: ObsidianLike,
    subfolder: str = "archive/cartosia",
) -> ImportReport:
    """Run the PF2e archive importer over ``archive_root``.

    ``subfolder`` is the logical archive identifier used for the
    ``imported_from`` frontmatter field and as the slug prefix for the report
    path. Defaults to ``archive/cartosia`` for backward compatibility with the
    original Cartosia-only importer.
    """
    plan = build_pf_archive_import_plan(
        archive_root=archive_root,
        dry_run=dry_run,
        limit=limit,
        confirm_large=confirm_large,
        subfolder=subfolder,
    )
    return await execute_pf_archive_import_plan(
        plan,
        force=force,
        obsidian_client=obsidian_client,
        token_downloader=download_token,
    )
