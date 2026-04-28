"""POST /cartosia route — bulk archive importer (260427-czb Task 3).

Wraps :func:`app.pf_archive_import.run_import` in a FastAPI POST handler.
Mounts at /cartosia (proxied as /modules/pathfinder/cartosia by sentinel-core).

Body shape:
  {
    "archive_root": "<absolute or container-mounted path>",
    "dry_run": true,            # default
    "limit": null,              # int | null
    "force": false,
    "confirm_large": false,
    "user_id": "<discord user id>"
  }

Response:
  {
    "report_path": "ops/sweeps/cartosia-...-<ts>.md",
    "npc_count": int,
    "location_count": int,
    "homebrew_count": int,
    "harvest_count": int,
    "lore_count": int,
    "session_count": int,
    "arc_count": int,
    "faction_count": int,
    "dialogue_count": int,
    "skip_count": int,
    "skipped_existing": int,
    "errors": list[str]
  }
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.pf_archive_import import ImportCostGuardError, run_import

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singleton — wired by app.main lifespan.
obsidian = None  # type: ignore[assignment]


class IngestRequest(BaseModel):
    archive_root: str
    subfolder: str = "archive/cartosia"
    dry_run: bool = True
    limit: int | None = None
    force: bool = False
    confirm_large: bool = False
    user_id: str = Field(default="")


@router.post("/ingest")
async def ingest(req: IngestRequest) -> dict:
    if obsidian is None:
        raise HTTPException(
            status_code=503,
            detail="ingest route not initialised (obsidian client missing)",
        )
    try:
        report = await run_import(
            archive_root=req.archive_root,
            subfolder=req.subfolder,
            dry_run=req.dry_run,
            limit=req.limit,
            force=req.force,
            confirm_large=req.confirm_large,
            obsidian_client=obsidian,
        )
    except ImportCostGuardError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # surface unexpected errors
        logger.exception("pathfinder ingest failed")
        raise HTTPException(status_code=500, detail=f"pathfinder ingest failed: {exc}")
    return report.asdict()
