"""Orchestration module for vault sweep route flows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from app.errors import SweepInProgressError
from app.services.task_runner import AsyncioTaskRunner, TaskRunner
from app.services.vault_sweeper import _set_status, get_status, run_sweep

logger = logging.getLogger(__name__)


def _new_status(sweep_id: str, status: str):
    return type(
        "S",
        (),
        {
            "sweep_id": sweep_id,
            "status": status,
            "files_processed": 0,
            "files_total": 0,
            "duplicates_moved": 0,
            "noise_moved": 0,
            "topic_moves": 0,
        },
    )()


async def start_sweep(
    *,
    vault,
    classifier: Callable[[str], Awaitable[object]],
    embedder: Callable[[list[str]], Awaitable[list[float]]],
    force_reclassify: bool,
    dry_run: bool,
    task_runner: TaskRunner | None = None,
) -> dict:
    sweep_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    runner = task_runner or AsyncioTaskRunner()

    if dry_run:
        id_part = sweep_id.replace(":", "-")
        report_path = f"ops/sweeps/dry-run-{id_part}.md"
        _set_status(_new_status(sweep_id, "dry-running"))

        async def _dry_runner():
            try:
                report = await run_sweep(
                    vault,
                    classifier,
                    embedder,
                    force_reclassify=force_reclassify,
                    status_callback=_set_status,
                    dry_run=True,
                )
                lines = [
                    f"# Dry-run sweep report — {sweep_id}",
                    "",
                    f"- Files scanned: {report.files_processed}/{report.files_total}",
                    f"- Topic relocations proposed: {report.topic_moves}",
                    f"- Noise→trash proposed: {report.noise_moved}",
                    f"- Duplicates→trash proposed: {report.duplicates_moved}",
                    f"- Errors: {len(report.errors)}",
                    "",
                ]
                topic_moves = [m for m in report.proposed_moves if m.get("kind") == "topic"]
                trash_moves = [m for m in report.proposed_moves if m.get("kind") == "trash"]
                if topic_moves:
                    lines.append("## Topic relocations")
                    lines.append("")
                    for m in topic_moves:
                        lines.append(f"- `{m['src']}` → `{m['dst']}` — {m.get('reason', '')}")
                    lines.append("")
                if trash_moves:
                    lines.append("## Trash moves")
                    lines.append("")
                    for m in trash_moves:
                        lines.append(f"- `{m['src']}` → `{m['dst']}` — {m.get('reason', '')}")
                    lines.append("")
                if report.errors:
                    lines.append("## Errors")
                    lines.append("")
                    for e in report.errors[:50]:
                        lines.append(f"- {e}")
                    lines.append("")
                await vault.write_note(report_path, "\n".join(lines))
                cur = get_status()
                cur["status"] = "dry-run-complete"
                cur["report_path"] = report_path
                cur["topic_moves"] = report.topic_moves
                cur["noise_moved"] = report.noise_moved
                cur["duplicates_moved"] = report.duplicates_moved
                cur["files_processed"] = report.files_processed
                cur["files_total"] = report.files_total
            except SweepInProgressError:
                get_status()["status"] = "blocked"
            except Exception as exc:
                logger.exception("dry-run sweep crashed: %s", exc)
                get_status()["status"] = "error"

        runner.schedule(_dry_runner())
        return {"sweep_id": sweep_id, "status": "dry-running", "report_path": report_path}

    _set_status(_new_status(sweep_id, "running"))

    async def _runner():
        try:
            report = await run_sweep(
                vault,
                classifier,
                embedder,
                force_reclassify=force_reclassify,
                status_callback=_set_status,
            )
            _set_status(report)
        except SweepInProgressError:
            get_status()["status"] = "blocked"
        except Exception as exc:
            logger.exception("vault sweep crashed: %s", exc)
            get_status()["status"] = "error"

    runner.schedule(_runner())
    return {"sweep_id": sweep_id, "status": "running"}
