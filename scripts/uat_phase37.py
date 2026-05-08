#!/usr/bin/env python3
"""Phase 37 — full :pf player verb family live-stack UAT.

Exercises the full Discord-adapter -> sentinel-core proxy -> pf2e-module ->
Obsidian path that Phase 37 verifier missed (mock-at-the-HTTP-boundary blind
spot, see CONTEXT.md session_issues PHASE37-A).

Coverage:
  start (onboard):
    01 adapter: empty rest -> usage, no POST
    02 adapter: pipe-args -> full PlayerOnboardRequest payload
    03 adapter: invalid preset -> client-side reject, no POST
    04 route: full payload -> 200 onboarded
    05 route: partial payload -> 422 with field-level missing detail
    06 route: invalid preset -> 422 with style_preset error
    07 route: distinct user_ids -> distinct slugs
    08 vault: profile.md exists with onboarded:true + Tactician

  onboarding gate:
    09 route: /player/note before onboarding -> 409 (gate rejection)

  capture verbs (after onboarding):
    10 route: /player/note appends to inbox.md
    11 route: /player/ask appends to questions.md (no LLM call)
    12 route: /player/npc writes per-player npcs/{npc_slug}.md (PVL-07)
    13 route: /player/todo appends to todo.md

  recall + style + canonize:
    14 route: /player/recall returns ranked snippets from player namespace
    15 route: /player/style action=list returns presets (gate-exempt)
    16 route: /player/style action=set persists preset
    17 route: /player/canonize records yellow/green/red with provenance

  adapter contract drift surface (regression guard for Phase 37 verifier blind spot):
    18 adapter: PlayerAskCommand payload key matches PlayerAskRequest schema

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


# ----- Onboarding gate ------------------------------------------------------


_GATE_USER = "uat-player-gate-09"


async def uat_09_gate_blocks_unboarded_capture(client: httpx.AsyncClient) -> None:
    """Pre-onboarding /player/note must return 409 (orchestrator gate)."""
    resp = await client.post(
        f"{_SENTINEL_URL}/modules/pathfinder/player/note",
        json={"user_id": _GATE_USER, "text": "should be blocked"},
        headers={"X-Sentinel-Key": _SENTINEL_KEY},
        timeout=30.0,
    )
    ok = resp.status_code == 409
    record(
        "09 gate: /player/note before onboarding -> 409",
        ok,
        f"status={resp.status_code}",
    )


# ----- Capture verbs (require onboarding) ----------------------------------

_CAPTURE_USER = "uat-player-capture"


async def _ensure_onboarded(client: httpx.AsyncClient, user_id: str) -> str:
    resp = await _post_onboard(client, {
        "user_id": user_id,
        "character_name": "Test Character",
        "preferred_name": "Test",
        "style_preset": "Tactician",
    })
    body = resp.json() if resp.status_code == 200 else {}
    slug = body.get("slug", "")
    path = body.get("path", "")
    if path:
        _TEARDOWN_PATHS.add(path)
    return slug


async def _post(client: httpx.AsyncClient, route_path: str, payload: dict) -> httpx.Response:
    return await client.post(
        f"{_SENTINEL_URL}/modules/pathfinder/{route_path}",
        json=payload,
        headers={"X-Sentinel-Key": _SENTINEL_KEY},
        timeout=30.0,
    )


async def uat_10_route_note(client: httpx.AsyncClient, slug: str) -> None:
    resp = await _post(client, "player/note", {"user_id": _CAPTURE_USER, "text": "Found a hidden door behind the tapestry."})
    body = resp.json() if resp.status_code == 200 else {}
    expected_path = f"mnemosyne/pf2e/players/{slug}/inbox.md"
    ok = resp.status_code == 200 and body.get("path") == expected_path
    if body.get("path"):
        _TEARDOWN_PATHS.add(body["path"])
    record("10 route: /player/note appends to inbox.md", ok, f"status={resp.status_code} path={body.get('path')}")


async def uat_11_route_ask(client: httpx.AsyncClient, slug: str) -> None:
    """Direct route hit with the schema-correct payload key (text)."""
    resp = await _post(client, "player/ask", {"user_id": _CAPTURE_USER, "text": "Does Sneak Attack work on grabbed targets?"})
    body = resp.json() if resp.status_code == 200 else {}
    expected_path = f"mnemosyne/pf2e/players/{slug}/questions.md"
    ok = resp.status_code == 200 and body.get("path") == expected_path
    if body.get("path"):
        _TEARDOWN_PATHS.add(body["path"])
    record("11 route: /player/ask appends to questions.md", ok, f"status={resp.status_code} path={body.get('path')}")


async def uat_12_route_npc(client: httpx.AsyncClient, slug: str) -> None:
    resp = await _post(client, "player/npc", {"user_id": _CAPTURE_USER, "npc_name": "Varek", "note": "Allied — owes me a favor."})
    body = resp.json() if resp.status_code == 200 else {}
    path = body.get("path", "")
    expected_prefix = f"mnemosyne/pf2e/players/{slug}/npcs/"
    expected_global = "mnemosyne/pf2e/npcs/varek.md"
    ok = resp.status_code == 200 and path.startswith(expected_prefix) and path != expected_global
    if path:
        _TEARDOWN_PATHS.add(path)
    record("12 route: /player/npc writes per-player npcs/ (PVL-07 isolation)", ok, f"status={resp.status_code} path={path}")


async def uat_13_route_todo(client: httpx.AsyncClient, slug: str) -> None:
    resp = await _post(client, "player/todo", {"user_id": _CAPTURE_USER, "text": "Buy alchemist's fire."})
    body = resp.json() if resp.status_code == 200 else {}
    expected_path = f"mnemosyne/pf2e/players/{slug}/todo.md"
    ok = resp.status_code == 200 and body.get("path") == expected_path
    if body.get("path"):
        _TEARDOWN_PATHS.add(body["path"])
    record("13 route: /player/todo appends to todo.md", ok, f"status={resp.status_code} path={body.get('path')}")


async def uat_14_route_recall(client: httpx.AsyncClient, slug: str) -> None:
    """After 10/11/12/13 wrote four items, recall should find the 'door' note."""
    resp = await _post(client, "player/recall", {"user_id": _CAPTURE_USER, "query": "door"})
    body = resp.json() if resp.status_code == 200 else {}
    results = body.get("results") or []
    snippets_text = " ".join(
        (item.get("snippet") or item.get("text") or str(item)) if isinstance(item, dict) else str(item)
        for item in results
    )
    ok = resp.status_code == 200 and len(results) >= 1 and "door" in snippets_text.lower()
    record("14 route: /player/recall returns ranked snippets matching keyword", ok, f"status={resp.status_code} hits={len(results)}")


async def uat_15_route_style_list(client: httpx.AsyncClient) -> None:
    """style action=list is gate-exempt — works for non-onboarded user too."""
    resp = await _post(client, "player/style", {"user_id": "uat-style-list-15", "action": "list"})
    body = resp.json() if resp.status_code == 200 else {}
    presets = body.get("presets") or []
    expected = {"Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"}
    ok = resp.status_code == 200 and set(presets) == expected
    record("15 route: /player/style action=list (gate-exempt) returns 4 presets", ok, f"status={resp.status_code} presets={presets}")


async def uat_16_route_style_set(client: httpx.AsyncClient, slug: str) -> None:
    resp = await _post(client, "player/style", {"user_id": _CAPTURE_USER, "action": "set", "preset": "Lorekeeper"})
    body = resp.json() if resp.status_code == 200 else {}
    # Route returns the field as `style_preset` (frontmatter-aligned), not `preset`.
    ok = resp.status_code == 200 and body.get("style_preset") == "Lorekeeper" and body.get("status") == "set"
    record(
        "16 route: /player/style action=set persists preset",
        ok,
        f"status={resp.status_code} style_preset={body.get('style_preset')}",
    )


async def uat_17_route_canonize(client: httpx.AsyncClient, slug: str) -> None:
    payload = {
        "user_id": _CAPTURE_USER,
        "outcome": "green",
        "question_id": "q-uat-17",
        "rule_text": "Sneak Attack triggers on grabbed targets per RAW.",
    }
    resp = await _post(client, "player/canonize", payload)
    body = resp.json() if resp.status_code == 200 else {}
    expected_path = f"mnemosyne/pf2e/players/{slug}/canonization.md"
    ok = resp.status_code == 200 and body.get("path") == expected_path
    if body.get("path"):
        _TEARDOWN_PATHS.add(body["path"])
    record("17 route: /player/canonize records green outcome with provenance", ok, f"status={resp.status_code} path={body.get('path')}")


# ----- Adapter contract drift surface (regression guard) --------------------


async def uat_18_adapter_ask_payload_matches_route() -> None:
    """Captures the Phase 37 PHASE37-A blind spot: adapter→route key drift.

    PlayerAskCommand should send the same key the route's Pydantic model
    requires. As of v0.5 the route requires `text` (per plan-37-08 SUMMARY:
    'Plan text specified PlayerAskRequest{question} but plan-02 RED test
    sends text — followed Test-Rewrite Ban and matched the test'). If the
    adapter sends `question` while the route requires `text`, every live
    :pf player ask will 422.
    """
    from pathfinder_player_adapter import PlayerAskCommand

    cmd = PlayerAskCommand()
    client = AsyncMock()
    client.post_to_module = AsyncMock(return_value={"ok": True, "slug": "p-x", "path": "mnemosyne/pf2e/players/p-x/questions.md"})
    req = PathfinderRequest(
        noun="player", verb="ask",
        rest="Does Sneak Attack work on grabbed targets?",
        user_id="u-uat", sentinel_client=client,
    )
    await cmd.handle(req)
    payload = client.post_to_module.call_args[0][1]
    ok = "text" in payload and payload["text"] == "Does Sneak Attack work on grabbed targets?"
    record(
        "18 adapter: PlayerAskCommand sends 'text' (matches PlayerAskRequest)",
        ok,
        "" if ok else f"payload keys={list(payload.keys())} (expected 'text')",
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

    print("-- Phase 37 UAT: :pf player verb family --")
    print(f"  sentinel: {_SENTINEL_URL}")
    print(f"  obsidian: {_OBSIDIAN_URL}")
    print()

    print("start (adapter, no HTTP):")
    await uat_01_adapter_empty_rest_returns_usage()
    await uat_02_adapter_full_args_builds_payload()
    await uat_03_adapter_rejects_invalid_preset()

    print("\nstart (route, live HTTP):")
    async with httpx.AsyncClient() as client:
        await uat_04_route_accepts_full_payload(client)
        await uat_05_route_rejects_partial_payload(client)
        await uat_06_route_rejects_invalid_preset(client)
        await uat_07_distinct_user_ids_distinct_slugs(client)
        await uat_08_vault_note_exists(client)

        print("\nonboarding gate:")
        await uat_09_gate_blocks_unboarded_capture(client)

        print("\ncapture verbs (after onboarding):")
        capture_slug = await _ensure_onboarded(client, _CAPTURE_USER)
        if not capture_slug:
            print("  ERROR: could not onboard capture user; skipping verb tests")
        else:
            await uat_10_route_note(client, capture_slug)
            await uat_11_route_ask(client, capture_slug)
            await uat_12_route_npc(client, capture_slug)
            await uat_13_route_todo(client, capture_slug)

            print("\nrecall + style + canonize:")
            await uat_14_route_recall(client, capture_slug)
            await uat_15_route_style_list(client)
            await uat_16_route_style_set(client, capture_slug)
            await uat_17_route_canonize(client, capture_slug)

        print("\nadapter contract drift regression guard:")
        await uat_18_adapter_ask_payload_matches_route()

        await _teardown(client)

    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)
    print(f"\n-- Result: {passed}/{total} passed --")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
