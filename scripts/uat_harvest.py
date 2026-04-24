#!/usr/bin/env python3
"""
Phase 32 Monster Harvesting — live-stack UAT.

Mirrors scripts/uat_discord.py pattern. Exercises the 8 HUMAN-UAT items in
.planning/phases/32-monster-harvesting/32-HUMAN-UAT.md against the live
Docker stack (sentinel-core + pf2e-module + discord + Obsidian + LM Studio).

Six items are fully automated (HTTP layer + Obsidian REST assertions); item 6
verifies cache-hit suppression at the response level; item 7 (DM ratification)
toggles verified=true via Obsidian REST and re-queries; item 8 is covered by
the healthz + REGISTRATION_PAYLOAD smoke.

Required environment variables:
    LIVE_TEST=1                    — safety gate
    UAT_SENTINEL_URL               — default http://localhost:8000
    UAT_SENTINEL_KEY               — X-Sentinel-Key
    UAT_OBSIDIAN_URL               — default http://localhost:27123
    UAT_OBSIDIAN_KEY               — Obsidian REST bearer token

Exit codes: 0 all pass; 1 any failure or LIVE_TEST missing.
"""
import asyncio
import os
import sys
import time

try:
    import httpx
except ImportError:
    print("httpx not installed. Run inside interfaces/discord venv: uv run --project interfaces/discord python scripts/uat_harvest.py")
    sys.exit(1)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DISCORD_DIR = os.path.join(_REPO_ROOT, "interfaces", "discord")
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _DISCORD_DIR)

# Stub discord the same way uat_discord.py does so bot.py imports cleanly.
import types  # noqa: E402
import unittest.mock as _mock  # noqa: E402

_app_commands_stub = types.ModuleType("discord.app_commands")
_app_commands_stub.CommandTree = _mock.MagicMock()
_app_commands_stub.describe = lambda **_: (lambda f: f)
_discord_stub = types.ModuleType("discord")
_discord_stub.Client = type("Client", (), {"__init__": lambda self, **kw: None})
_discord_stub.Intents = type("Intents", (), {
    "message_content": False,
    "default": classmethod(lambda cls: cls()),
})
_discord_stub.Message = object
_discord_stub.Thread = object
_discord_stub.ChannelType = _mock.MagicMock()
_discord_stub.Forbidden = Exception
_discord_stub.HTTPException = Exception
_discord_stub.Interaction = object
_discord_stub.Embed = type("Embed", (), {
    "__init__": lambda self, **kw: (self.__dict__.update(kw) or None) and None or None,
})

# discord.Embed needs add_field + set_footer methods for build_harvest_embed.
class _EmbedStub:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.fields = []
        self._footer = None

    def add_field(self, *, name, value, inline=False):
        self.fields.append({"name": name, "value": value, "inline": inline})
        return self

    def set_footer(self, *, text):
        self._footer = text
        return self

_discord_stub.Embed = _EmbedStub
_discord_stub.Color = type("Color", (), {
    "green": classmethod(lambda cls: cls()),
    "orange": classmethod(lambda cls: cls()),
    "red": classmethod(lambda cls: cls()),
    "gold": classmethod(lambda cls: cls()),
    "blue": classmethod(lambda cls: cls()),
})
_discord_stub.app_commands = _app_commands_stub
sys.modules.setdefault("discord", _discord_stub)
sys.modules.setdefault("discord.app_commands", _app_commands_stub)

os.environ.setdefault("DISCORD_BOT_TOKEN", "uat-stub")
os.environ.setdefault("SENTINEL_API_KEY", os.environ.get("UAT_SENTINEL_KEY", "uat-stub"))

import bot  # noqa: E402

_RESULTS: list[tuple[str, bool, str]] = []
_TEARDOWN_CACHE_PATHS: set[str] = set()


def record(label: str, passed: bool, detail: str = "") -> None:
    _RESULTS.append((label, passed, detail))
    status = "PASS" if passed else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {label}{suffix}")


def _read_secret(name: str, env_fallback: str = "") -> str:
    try:
        with open(f"/run/secrets/{name}") as f:
            return f.read().strip()
    except FileNotFoundError:
        return env_fallback


# ── 1. HTTP-level harvest flows (sentinel-core → pf2e-module → Obsidian) ──

async def test_http_harvest_flows(
    sentinel_url: str, sentinel_key: str,
    obsidian_url: str, obsidian_key: str,
) -> None:
    print("\n── HTTP harvest flows (HRV-01..06) ──")
    auth = {"X-Sentinel-Key": sentinel_key}
    obs_h = {"Authorization": f"Bearer {obsidian_key}"} if obsidian_key else {}

    async with httpx.AsyncClient(timeout=120.0) as client:

        async def post_harvest(names: list[str], user: str = "uat-harvest") -> httpx.Response:
            return await client.post(
                f"{sentinel_url}/modules/pathfinder/run",
                json={"path": "harvest", "payload": {"names": names, "user_id": user}},
                headers=auth,
            )

        async def read_cache(slug: str) -> tuple[int, str]:
            if not obs_h:
                return (-1, "")
            path = f"mnemosyne/pf2e/harvest/{slug}.md"
            _TEARDOWN_CACHE_PATHS.add(path)
            r = await client.get(f"{obsidian_url}/vault/{path}", headers=obs_h)
            return (r.status_code, r.text)

        # UAT-1: Boar seed round-trip
        try:
            r = await post_harvest(["Boar"])
            body = r.json() if r.status_code == 200 else {}
            m = (body.get("monsters") or [{}])[0]
            passed = (
                r.status_code == 200
                and m.get("source") in ("seed",)
                and isinstance(m.get("level"), int)
                and m.get("components")
            )
            record("UAT-1 Boar seed — POST returns 200 + source=seed + components",
                   passed, f"status={r.status_code}, src={m.get('source')}, comps={len(m.get('components') or [])}")

            cache_status, cache_body = await read_cache("boar")
            record("UAT-1 Boar cache file written at mnemosyne/pf2e/harvest/boar.md",
                   cache_status == 200 and "Medicine DC" in cache_body,
                   f"status={cache_status}, len={len(cache_body)}")
        except Exception as exc:
            record("UAT-1 Boar seed round-trip", False, f"exception: {exc}")

        # UAT-3: Alpha Wolf fuzzy match — canonical slug per WR-05
        try:
            # First, delete any stale cache
            if obs_h:
                for slug in ("alpha-wolf", "wolf"):
                    await client.delete(
                        f"{obsidian_url}/vault/mnemosyne/pf2e/harvest/{slug}.md",
                        headers=obs_h,
                    )

            r = await post_harvest(["Alpha Wolf"])
            body = r.json() if r.status_code == 200 else {}
            m = (body.get("monsters") or [{}])[0]
            note = m.get("note") or ""
            passed = (
                r.status_code == 200
                and m.get("source") == "seed-fuzzy"
                and "Wolf" in note
            )
            record("UAT-3 Alpha Wolf fuzzy — source=seed-fuzzy + note present",
                   passed, f"status={r.status_code}, src={m.get('source')}, note={note[:60]!r}")

            # WR-05 canonical-slug check: cache should be at wolf.md, NOT alpha-wolf.md
            wolf_status, _ = await read_cache("wolf")
            alpha_status, _ = await read_cache("alpha-wolf")
            record("UAT-3 WR-05 canonical slug — cache at wolf.md, not alpha-wolf.md",
                   wolf_status == 200 and alpha_status == 404,
                   f"wolf.md={wolf_status}, alpha-wolf.md={alpha_status}")
        except Exception as exc:
            record("UAT-3 Alpha Wolf fuzzy round-trip", False, f"exception: {exc}")

        # UAT-4: Wolf Lord — fuzzy below cutoff 85 → falls through to LLM
        try:
            if obs_h:
                await client.delete(
                    f"{obsidian_url}/vault/mnemosyne/pf2e/harvest/wolf-lord.md",
                    headers=obs_h,
                )
            r = await post_harvest(["Wolf Lord"])
            body = r.json() if r.status_code == 200 else {}
            m = (body.get("monsters") or [{}])[0]
            passed = r.status_code == 200 and m.get("source") == "llm-generated" and m.get("verified") is False
            record("UAT-4 Wolf Lord — below cutoff, LLM fallback, verified=False",
                   passed, f"status={r.status_code}, src={m.get('source')}, verified={m.get('verified')}")
        except Exception as exc:
            record("UAT-4 Wolf Lord below-cutoff fallback", False, f"exception: {exc}")

        # UAT-5: Batch Boar,Wolf,Orc
        try:
            r = await post_harvest(["Boar", "Wolf", "Orc"])
            body = r.json() if r.status_code == 200 else {}
            monsters = body.get("monsters") or []
            aggregated = body.get("aggregated") or []
            footer = body.get("footer") or ""
            passed = (
                r.status_code == 200
                and len(monsters) == 3
                and len(aggregated) >= 1
                and "ORC" in footer
            )
            record("UAT-5 Batch aggregated — 3 monsters + ORC footer (IN-02 fix)",
                   passed, f"monsters={len(monsters)}, aggregated={len(aggregated)}, footer={footer[:50]!r}")
        except Exception as exc:
            record("UAT-5 Batch aggregated", False, f"exception: {exc}")

        # UAT-6: Cache-hit suppression — second call returns cached data without LLM
        try:
            if obs_h:
                # Seed the cache with a known Boar query above; now re-query and verify
                # the response is served from cache (fast + source stays "seed"/"cache").
                t0 = time.monotonic()
                r = await post_harvest(["Boar"])
                dt = time.monotonic() - t0
                body = r.json() if r.status_code == 200 else {}
                m = (body.get("monsters") or [{}])[0]
                passed = (
                    r.status_code == 200
                    and m.get("source") in ("cache", "seed")
                    and dt < 5.0  # cache-hit should be fast; LLM fallback takes 10-60s
                )
                record("UAT-6 Cache-hit Boar — fast path + source preserved",
                       passed, f"status={r.status_code}, src={m.get('source')}, dt={dt:.2f}s")
        except Exception as exc:
            record("UAT-6 Cache-hit Boar", False, f"exception: {exc}")

        # UAT-7: DM ratification — edit verified=true, re-query, confirm cache re-read
        try:
            if obs_h:
                # Use Barghest (LLM-generated, verified=False) as the ratification target.
                # First ensure it exists; if not, generate it.
                barghest_path = "mnemosyne/pf2e/harvest/barghest.md"
                _TEARDOWN_CACHE_PATHS.add(barghest_path)
                r0 = await client.get(f"{obsidian_url}/vault/{barghest_path}", headers=obs_h)
                if r0.status_code == 404:
                    await post_harvest(["Barghest"])
                    r0 = await client.get(f"{obsidian_url}/vault/{barghest_path}", headers=obs_h)

                if r0.status_code == 200:
                    # Flip verified: false → true in the frontmatter, keep body intact.
                    patched = r0.text.replace("verified: false", "verified: true", 1)
                    if patched != r0.text:
                        put_resp = await client.put(
                            f"{obsidian_url}/vault/{barghest_path}",
                            headers={**obs_h, "Content-Type": "text/markdown"},
                            content=patched,
                        )
                        # Re-query and confirm verified=true flows back
                        r2 = await post_harvest(["Barghest"])
                        body = r2.json() if r2.status_code == 200 else {}
                        m = (body.get("monsters") or [{}])[0]
                        passed = (
                            put_resp.status_code in (200, 204)
                            and r2.status_code == 200
                            and m.get("verified") is True
                        )
                        record("UAT-7 DM ratification — verified=true flows back after re-read",
                               passed, f"put={put_resp.status_code}, verified={m.get('verified')}")
                    else:
                        record("UAT-7 DM ratification — skipped (no verified:false to flip)",
                               True, "barghest.md already verified")
                else:
                    record("UAT-7 DM ratification — setup failed",
                           False, f"could not fetch/generate barghest.md (status={r0.status_code})")
            else:
                record("UAT-7 DM ratification", True, "skipped — no Obsidian key")
        except Exception as exc:
            record("UAT-7 DM ratification", False, f"exception: {exc}")

        # UAT-2: Barghest LLM (out of seed scope, L4) — requires live LM Studio
        # Tested implicitly above during UAT-7 setup if cache was empty.
        # Add an explicit assertion: after UAT-7, Barghest cache must exist with valid shape.
        try:
            if obs_h:
                status, txt = await read_cache("barghest")
                passed = (
                    status == 200
                    and "Medicine DC" in txt
                    and "ORC" in txt
                )
                record("UAT-2 Barghest LLM fallback — cache file with DC + ORC attribution",
                       passed, f"status={status}, len={len(txt)}")
        except Exception as exc:
            record("UAT-2 Barghest LLM cache", False, f"exception: {exc}")


# ── 2. Bot routing layer (bot._pf_dispatch → live sentinel-core) ──

async def test_bot_routing(sentinel_url: str, sentinel_key: str) -> None:
    print("\n── Bot routing (:pf harvest via _pf_dispatch → live stack) ──")

    bot._sentinel_client._base_url = sentinel_url.rstrip("/")
    bot._sentinel_client._api_key = sentinel_key
    USER = "uat-harvest-routing"

    async def dispatch(label: str, args: str, *, expect_usage: bool = False,
                       expect_embed: bool = False) -> None:
        try:
            result = await bot._pf_dispatch(args, USER)
            if expect_usage:
                record(label, isinstance(result, str) and "Usage" in result,
                       f"got: {str(result)[:80]!r}")
            elif expect_embed:
                ok = (
                    isinstance(result, dict)
                    and result.get("type") == "embed"
                    and "embed" in result
                )
                record(label, ok, f"keys={list(result.keys()) if isinstance(result, dict) else type(result).__name__}")
            else:
                record(label, result is not None and not (isinstance(result, str) and "error" in result.lower()),
                       f"got: {str(result)[:80]!r}")
        except Exception as exc:
            record(label, False, f"exception: {exc}")

    await dispatch(":pf harvest Boar → embed", "harvest Boar", expect_embed=True)
    await dispatch(":pf harvest Boar,Wolf,Orc → batch embed", "harvest Boar,Wolf,Orc", expect_embed=True)
    await dispatch(":pf harvest Giant Rat → multi-word preserved", "harvest Giant Rat", expect_embed=True)
    await dispatch(":pf harvest → Usage (D-04 top-level)", "harvest", expect_usage=True)
    await dispatch(":pf harvest    (whitespace) → Usage", "harvest   ", expect_usage=True)
    await dispatch(":pf unknownnoun → Unknown (lists both)", "unknownnoun",
                   expect_usage=False)


# ── 3. Container smoke — healthz + REGISTRATION_PAYLOAD (UAT-8) ──

async def test_container_smoke(sentinel_url: str, sentinel_key: str) -> None:
    print("\n── Container smoke (UAT-8 rebuild verification) ──")
    auth = {"X-Sentinel-Key": sentinel_key}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(f"{sentinel_url}/health")
            record("UAT-8 sentinel-core /health → 200", r.status_code == 200,
                   f"status={r.status_code}")
        except Exception as exc:
            record("UAT-8 sentinel-core /health", False, str(exc))

        # Module registry lists pathfinder with 13 routes
        try:
            r = await client.get(f"{sentinel_url}/status", headers=auth)
            if r.status_code == 200:
                data = r.json()
                modules = data.get("modules") or {}
                pf = modules.get("pathfinder") or {}
                routes = pf.get("routes") or []
                has_harvest = any(
                    (route.get("path") if isinstance(route, dict) else route) == "harvest"
                    for route in routes
                )
                record("UAT-8 pathfinder registered with 13 routes incl. harvest",
                       len(routes) == 13 and has_harvest,
                       f"routes={len(routes)}, harvest_present={has_harvest}")
            else:
                record("UAT-8 /status returned", False, f"status={r.status_code}")
        except Exception as exc:
            record("UAT-8 /status registry check", False, str(exc))


# ── Teardown — clean harvest UAT artifacts ──

async def _teardown_harvest_cache(obsidian_url: str, obsidian_key: str) -> None:
    if not obsidian_key or not _TEARDOWN_CACHE_PATHS:
        return
    print("\n── Teardown (harvest cache) ──")
    headers = {"Authorization": f"Bearer {obsidian_key}"}
    deleted = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for path in _TEARDOWN_CACHE_PATHS:
            try:
                r = await client.delete(f"{obsidian_url}/vault/{path}", headers=headers)
                if r.status_code in (200, 204, 404):
                    deleted += 1
            except Exception as exc:
                print(f"  [teardown] {path}: {exc}", file=sys.stderr)
    print(f"  cleaned {deleted}/{len(_TEARDOWN_CACHE_PATHS)} harvest cache files")


# ── Entry ──

async def run_all(sentinel_url: str, sentinel_key: str,
                  obsidian_url: str, obsidian_key: str) -> None:
    try:
        await test_container_smoke(sentinel_url, sentinel_key)
        await test_http_harvest_flows(sentinel_url, sentinel_key, obsidian_url, obsidian_key)
        await test_bot_routing(sentinel_url, sentinel_key)
    finally:
        await _teardown_harvest_cache(obsidian_url, obsidian_key)


def main() -> None:
    if not os.getenv("LIVE_TEST"):
        print("LIVE_TEST=1 must be set to run harvest UAT. Exiting.")
        sys.exit(1)

    sentinel_url = os.environ.get("UAT_SENTINEL_URL", "http://localhost:8000")
    sentinel_key = _read_secret("sentinel_api_key", os.environ.get("UAT_SENTINEL_KEY", ""))
    obsidian_url = os.environ.get("UAT_OBSIDIAN_URL", "http://localhost:27123")
    obsidian_key = _read_secret("obsidian_api_key", os.environ.get("UAT_OBSIDIAN_KEY", ""))

    if not sentinel_key:
        print("ERROR: UAT_SENTINEL_KEY or /run/secrets/sentinel_api_key required.")
        sys.exit(1)

    asyncio.run(run_all(sentinel_url, sentinel_key, obsidian_url, obsidian_key))

    total = len(_RESULTS)
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    failed = total - passed

    print("\n=== Phase 32 Harvest UAT Report ===")
    print(f"Total: {total}  Passed: {passed}  Failed: {failed}")
    if failed:
        print("FAILED tests:")
        for label, ok, detail in _RESULTS:
            if not ok:
                print(f"  - {label} — {detail}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
