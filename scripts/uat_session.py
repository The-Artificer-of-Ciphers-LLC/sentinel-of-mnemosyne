#!/usr/bin/env python3
"""
Phase 34 Session Notes — live-stack UAT (≥11 assertions).

Mirrors scripts/uat_rules.py pattern. Exercises the UAT items in
.planning/phases/34-session-notes/34-CONTEXT.md against the live Docker
stack (sentinel-core + pf2e-module + Obsidian + LM Studio).

Wave 0 skeleton — assertion bodies are stubs (raise NotImplementedError)
until Wave 4 (Plan 34-05) fleshes them out. Each stub is an honest RED
placeholder: the function exists, is labelled, and _TEARDOWN_PATHS is
populated so cleanup runs even against a stub body.

Required environment variables:
    LIVE_TEST=1                    — safety gate (refuses to run without it)
    UAT_SENTINEL_URL               — default http://localhost:8000
    UAT_SENTINEL_KEY               — X-Sentinel-Key
    UAT_OBSIDIAN_URL               — default http://localhost:27123
    UAT_OBSIDIAN_KEY               — Obsidian REST bearer token

Exit codes: 0 all pass; 1 any failure or LIVE_TEST missing.
"""
# Obsidian vault paths written by this UAT run — cleaned up in teardown.
# Wave 4 populates entries as each test writes notes.
_TEARDOWN_PATHS: set[str] = set()

import asyncio
import os
import sys

try:
    import httpx
except ImportError:
    print(
        "httpx not installed. Run inside interfaces/discord venv: "
        "uv run --project interfaces/discord python scripts/uat_session.py"
    )
    sys.exit(1)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DISCORD_DIR = os.path.join(_REPO_ROOT, "interfaces", "discord")
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _DISCORD_DIR)

_UAT_SENTINEL_URL = os.environ.get("UAT_SENTINEL_URL", "http://localhost:8000")
_UAT_SENTINEL_KEY = os.environ.get("UAT_SENTINEL_KEY", "")
_UAT_OBSIDIAN_URL = os.environ.get("UAT_OBSIDIAN_URL", "http://localhost:27123")
_UAT_OBSIDIAN_KEY = os.environ.get("UAT_OBSIDIAN_KEY", "")

_RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, passed: bool, detail: str = "") -> None:
    _RESULTS.append((label, passed, detail))
    status = "PASS" if passed else "FAIL"
    suffix = f" — {detail}" if detail else ""
    mark = "✓" if passed else "✗"
    print(f"  {mark} [{status}] {label}{suffix}")


async def _sentinel_post(
    client: httpx.AsyncClient,
    path: str,
    payload: dict,
) -> dict:
    resp = await client.post(
        f"{_UAT_SENTINEL_URL}/{path.lstrip('/')}",
        json=payload,
        headers={"X-Sentinel-Key": _UAT_SENTINEL_KEY},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


async def _obsidian_delete(client: httpx.AsyncClient, vault_path: str) -> None:
    try:
        await client.delete(
            f"{_UAT_OBSIDIAN_URL}/vault/{vault_path.lstrip('/')}",
            headers={"Authorization": f"Bearer {_UAT_OBSIDIAN_KEY}"},
            timeout=10.0,
        )
    except Exception:
        pass  # best-effort teardown


# ---------------------------------------------------------------------------
# UAT-01 — start: creates open session note in Obsidian
# ---------------------------------------------------------------------------
async def uat_01_start_creates_open_note(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# UAT-02 — start: collision detection (existing open note returns error)
# ---------------------------------------------------------------------------
async def uat_02_start_collision(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# UAT-03 — log: appends event line to Events Log heading
# ---------------------------------------------------------------------------
async def uat_03_log_appends_event(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# UAT-04 — log: NPC fast-pass resolves NPC name to wikilink
# ---------------------------------------------------------------------------
async def uat_04_log_npc_fastpass(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# UAT-05 — undo: removes last Events Log bullet
# ---------------------------------------------------------------------------
async def uat_05_undo_removes_last_event(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# UAT-06 — show: returns narrative text from LLM (Story So Far)
# ---------------------------------------------------------------------------
async def uat_06_show_returns_narrative(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# UAT-07 — end: closes note with structured recap + status:ended
# ---------------------------------------------------------------------------
async def uat_07_end_closes_note(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# UAT-08 — end: LLM failure writes skeleton note (D-31)
# ---------------------------------------------------------------------------
async def uat_08_end_llm_failure_writes_skeleton(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# UAT-09 — end --retry-recap: regenerates recap on existing ended note
# ---------------------------------------------------------------------------
async def uat_09_retry_recap(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# UAT-10 — location stub: creates stub note for unknown location (SES-02)
# ---------------------------------------------------------------------------
async def uat_10_location_stub_created(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# UAT-11 — Discord: show/end use placeholder→edit UX (D-11 slow-query pattern)
# ---------------------------------------------------------------------------
async def uat_11_discord_placeholder_edit_ux(client: httpx.AsyncClient) -> None:
    raise NotImplementedError("Wave 4 / Plan 34-05 will implement this assertion body")


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------
async def _teardown(client: httpx.AsyncClient) -> None:
    for path in _TEARDOWN_PATHS:
        await _obsidian_delete(client, path)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
async def main() -> int:
    if os.environ.get("LIVE_TEST") != "1":
        print("ERROR: LIVE_TEST=1 required — refusing to run against live stack without opt-in")
        return 1

    print("── Phase 34 Session Notes UAT ──")
    print(f"Sentinel: {_UAT_SENTINEL_URL}")
    print(f"Obsidian: {_UAT_OBSIDIAN_URL}")
    print()

    async with httpx.AsyncClient() as client:
        tests = [
            ("UAT-01 start creates open note", uat_01_start_creates_open_note),
            ("UAT-02 start collision detected", uat_02_start_collision),
            ("UAT-03 log appends event", uat_03_log_appends_event),
            ("UAT-04 log NPC fast-pass", uat_04_log_npc_fastpass),
            ("UAT-05 undo removes last event", uat_05_undo_removes_last_event),
            ("UAT-06 show returns narrative", uat_06_show_returns_narrative),
            ("UAT-07 end closes note", uat_07_end_closes_note),
            ("UAT-08 end LLM failure writes skeleton", uat_08_end_llm_failure_writes_skeleton),
            ("UAT-09 end --retry-recap", uat_09_retry_recap),
            ("UAT-10 location stub created", uat_10_location_stub_created),
            ("UAT-11 Discord placeholder→edit UX", uat_11_discord_placeholder_edit_ux),
        ]

        for label, fn in tests:
            try:
                await fn(client)
                record(label, True)
            except NotImplementedError:
                record(label, False, "stub — Wave 4 not yet executed")
            except Exception as exc:
                record(label, False, str(exc)[:120])

        await _teardown(client)

    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)
    print()
    print(f"Results: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
