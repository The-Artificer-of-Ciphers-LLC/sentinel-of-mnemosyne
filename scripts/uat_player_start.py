#!/usr/bin/env python3
"""Phase 37 :pf player start — live-stack UAT.

Exercises the full Discord-adapter -> sentinel-core proxy -> pf2e-module ->
Obsidian path that Phase 37 verifier missed (mock-at-the-HTTP-boundary blind
spot, see CONTEXT.md session_issues PHASE37-A).

Coverage:
  1. Adapter empty-rest returns usage hint, no POST issued
  2. Adapter pipe-args build correct route payload (PlayerOnboardRequest shape)
  3. Adapter rejects invalid style preset client-side
  4. Live route accepts full payload, persists profile.md to vault
  5. Live route 422s on incomplete payload (mitigation contract guard)
  6. Live route rejects invalid style preset (server-side validator)
  7. Two distinct user_ids -> two distinct slugs (cross-user isolation)
  8. Vault note exists at expected path with onboarded:true frontmatter

Required env vars:
    LIVE_TEST=1                    safety gate
    UAT_SENTINEL_URL               default http://localhost:8000
    UAT_SENTINEL_KEY               X-Sentinel-Key (required)
    UAT_OBSIDIAN_URL               default http://localhost:27123
    UAT_OBSIDIAN_KEY               Obsidian REST bearer (required for vault check + cleanup)

Exit codes: 0 all pass; 1 any failure or LIVE_TEST missing.
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock

try:
    import httpx
except ImportError:
    print("httpx not installed. Run via: uv run --project interfaces/discord python scripts/uat_player_start.py")
    sys.exit(1)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DISCORD_DIR = os.path.join(_REPO_ROOT, "interfaces", "discord")
sys.path.insert(0, _DISCORD_DIR)

from pathfinder_player_adapter import PlayerStartCommand  # noqa: E402
from pathfinder_types import PathfinderRequest  # noqa: E402

_SENTINEL_URL = os.environ.get("UAT_SENTINEL_URL", "http://localhost:8000")
_SENTINEL_KEY = os.environ.get("UAT_SENTINEL_KEY", "")
_OBSIDIAN_URL = os.environ.get("UAT_OBSIDIAN_URL", "http://localhost:27123")
_OBSIDIAN_KEY = os.environ.get("UAT_OBSIDIAN_KEY", "")

_TEARDOWN_PATHS: set[str] = set()
_RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, passed: bool, detail: str = "") -> None:
    _RESULTS.append((label, passed, detail))
    mark = "PASS" if passed else "FAIL"
    suffix = f" -- {detail}" if detail else ""
    print(f"  [{mark}] {label}{suffix}")


# ----- Adapter-level (no live HTTP) -----------------------------------------


async def uat_01_adapter_empty_rest_returns_usage() -> None:
    cmd = PlayerStartCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock()
    req = PathfinderRequest(noun="player", verb="start", rest="", user_id="u-uat", sentinel_client=client)
    response = await cmd.handle(req)
    ok = (
        client.post_to_module.await_count == 0
        and response.kind == "text"
        and "Usage" in response.content
        and "character_name" in response.content
    )
    record(
        "01 adapter: empty rest -> usage, no POST",
        ok,
        "" if ok else f"posted={client.post_to_module.await_count} content={response.content!r}",
    )


async def uat_02_adapter_full_args_builds_payload() -> None:
    cmd = PlayerStartCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"path": "mnemosyne/pf2e/players/p-x/profile.md"})
    req = PathfinderRequest(
        noun="player", verb="start",
        rest="Kael Stormblade | Kael | Tactician",
        user_id="u-uat", sentinel_client=client,
    )
    await cmd.handle(req)
    payload = client.post_to_module.call_args[0][1]
    ok = payload == {
        "user_id": "u-uat",
        "character_name": "Kael Stormblade",
        "preferred_name": "Kael",
        "style_preset": "Tactician",
    }
    record(
        "02 adapter: pipe-args -> full PlayerOnboardRequest payload",
        ok,
        "" if ok else f"payload={payload}",
    )


async def uat_03_adapter_rejects_invalid_preset() -> None:
    cmd = PlayerStartCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock()
    req = PathfinderRequest(
        noun="player", verb="start",
        rest="K | K | Bard-Mode", user_id="u-uat", sentinel_client=client,
    )
    response = await cmd.handle(req)
    ok = (
        client.post_to_module.await_count == 0
        and "Invalid style preset" in response.content
    )
    record(
        "03 adapter: invalid preset -> client-side reject, no POST",
        ok,
        "" if ok else response.content,
    )


# ----- Route-level (live HTTP through sentinel-core proxy) ------------------


async def _post_onboard(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    return await client.post(
        f"{_SENTINEL_URL}/modules/pathfinder/player/onboard",
        json=payload,
        headers={"X-Sentinel-Key": _SENTINEL_KEY},
        timeout=30.0,
    )


async def uat_04_route_accepts_full_payload(client: httpx.AsyncClient) -> str:
    payload = {
        "user_id": "uat-player-start-04",
        "character_name": "Kael Stormblade",
        "preferred_name": "Kael",
        "style_preset": "Tactician",
    }
    resp = await _post_onboard(client, payload)
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    slug = body.get("slug", "")
    path = body.get("path", "")
    ok = resp.status_code == 200 and body.get("status") == "onboarded" and slug.startswith("p-") and path
    if path:
        _TEARDOWN_PATHS.add(path)
    record("04 route: full payload -> 200 onboarded", ok, f"status={resp.status_code} slug={slug}")
    return slug


async def uat_05_route_rejects_partial_payload(client: httpx.AsyncClient) -> None:
    resp = await _post_onboard(client, {"user_id": "uat-player-start-05"})
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    missing = {item.get("loc", [None, None])[1] for item in body.get("detail", []) if isinstance(item, dict)}
    expected = {"character_name", "preferred_name", "style_preset"}
    ok = resp.status_code == 422 and expected.issubset(missing)
    record(
        "05 route: partial payload -> 422 with the right missing fields",
        ok,
        f"status={resp.status_code} missing={missing}",
    )


async def uat_06_route_rejects_invalid_preset(client: httpx.AsyncClient) -> None:
    payload = {
        "user_id": "uat-player-start-06",
        "character_name": "X",
        "preferred_name": "X",
        "style_preset": "Bard-Mode",
    }
    resp = await _post_onboard(client, payload)
    ok = resp.status_code == 422 and "style_preset" in resp.text
    record("06 route: invalid preset -> 422 with style_preset error", ok, f"status={resp.status_code}")


async def uat_07_distinct_user_ids_distinct_slugs(client: httpx.AsyncClient) -> None:
    base = {"character_name": "X", "preferred_name": "X", "style_preset": "Tactician"}
    r1 = await _post_onboard(client, {**base, "user_id": "uat-player-start-07a"})
    r2 = await _post_onboard(client, {**base, "user_id": "uat-player-start-07b"})
    s1 = r1.json().get("slug", "")
    s2 = r2.json().get("slug", "")
    for r in (r1, r2):
        p = r.json().get("path")
        if p:
            _TEARDOWN_PATHS.add(p)
    ok = r1.status_code == 200 and r2.status_code == 200 and s1 and s2 and s1 != s2
    record("07 route: distinct user_ids -> distinct slugs", ok, f"s1={s1} s2={s2}")


async def uat_08_vault_note_exists(client: httpx.AsyncClient) -> None:
    if not _OBSIDIAN_KEY:
        record("08 vault: profile.md exists with onboarded:true", False, "UAT_OBSIDIAN_KEY not set")
        return
    path = next((p for p in _TEARDOWN_PATHS if "uat-player-start-04" in p), None)
    if not path:
        path = next(iter(_TEARDOWN_PATHS), None)
    if not path:
        record("08 vault: profile.md exists with onboarded:true", False, "no path tracked")
        return
    resp = await client.get(
        f"{_OBSIDIAN_URL}/vault/{path}",
        headers={"Authorization": f"Bearer {_OBSIDIAN_KEY}"},
        timeout=10.0,
    )
    body = resp.text
    ok = resp.status_code == 200 and "onboarded: true" in body and "Tactician" in body
    record(
        "08 vault: profile.md exists with onboarded:true + Tactician",
        ok,
        f"status={resp.status_code}",
    )


# ----- Teardown -------------------------------------------------------------


async def _teardown(client: httpx.AsyncClient) -> None:
    if not _OBSIDIAN_KEY or not _TEARDOWN_PATHS:
        return
    print("\n-- Teardown --")
    for path in sorted(_TEARDOWN_PATHS):
        try:
            await client.delete(
                f"{_OBSIDIAN_URL}/vault/{path}",
                headers={"Authorization": f"Bearer {_OBSIDIAN_KEY}"},
                timeout=10.0,
            )
            print(f"  deleted {path}")
        except Exception as exc:
            print(f"  could not delete {path}: {exc}")


# ----- Main -----------------------------------------------------------------


async def main() -> int:
    if os.environ.get("LIVE_TEST") != "1":
        print("ERROR: LIVE_TEST=1 required (safety gate)")
        return 1
    if not _SENTINEL_KEY:
        print("ERROR: UAT_SENTINEL_KEY required")
        return 1

    print("-- Phase 37 UAT: :pf player start --")
    print(f"  sentinel: {_SENTINEL_URL}")
    print(f"  obsidian: {_OBSIDIAN_URL}")
    print()

    print("Adapter (no HTTP):")
    await uat_01_adapter_empty_rest_returns_usage()
    await uat_02_adapter_full_args_builds_payload()
    await uat_03_adapter_rejects_invalid_preset()

    print("\nRoute (live HTTP):")
    async with httpx.AsyncClient() as client:
        await uat_04_route_accepts_full_payload(client)
        await uat_05_route_rejects_partial_payload(client)
        await uat_06_route_rejects_invalid_preset(client)
        await uat_07_distinct_user_ids_distinct_slugs(client)
        await uat_08_vault_note_exists(client)
        await _teardown(client)

    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)
    print(f"\n-- Result: {passed}/{total} passed --")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
