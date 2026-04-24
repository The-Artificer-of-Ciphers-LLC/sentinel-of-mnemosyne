#!/usr/bin/env python3
"""
Phase 33 Rules Engine — live-stack UAT.

Mirrors scripts/uat_harvest.py pattern. Exercises the 16 UAT items in
.planning/phases/33-rules-engine/33-RESEARCH.md §Live-UAT Plan against
the live Docker stack (sentinel-core + pf2e-module + discord + Obsidian
+ LM Studio with embeddings model loaded).

Wave 0 skeleton — 16 assertion stubs land here now so the shell harness
is buildable. Wave 4 (Plan 33-05) fills in the actual HTTP + Obsidian +
embedding probes. Running this in Wave 0 produces 16 FAILs with
"stub — Wave 3/4 fills in" details.

Required environment variables:
    LIVE_TEST=1                    — safety gate
    UAT_SENTINEL_URL               — default http://localhost:8000
    UAT_SENTINEL_KEY               — X-Sentinel-Key
    UAT_OBSIDIAN_URL               — default http://localhost:27123
    UAT_OBSIDIAN_KEY               — Obsidian REST bearer token
    UAT_LMSTUDIO_URL               — default http://localhost:1234/v1 (L-10)

Exit codes: 0 all pass; 1 any failure or LIVE_TEST missing.
"""
# Sentinel-core proxy paths (L-7 — paths MUST include a sub-verb; never end at
# modules/pathfinder/rule alone):
#   modules/pathfinder/rule/query      — POST {query, user_id}  → ruling (RUL-01..04)
#   modules/pathfinder/rule/show       — POST {topic}           → list of files
#   modules/pathfinder/rule/history    — POST {n}               → recent rulings
#   modules/pathfinder/rule/list       — POST {}                → topic folders
#
# Obsidian cache prefix:
#   mnemosyne/pf2e/rulings/{topic-slug}/{sha1(normalize_query(q))[:8]}.md
import asyncio
import os
import sys

try:
    import httpx
except ImportError:
    print(
        "httpx not installed. Run inside interfaces/discord venv: "
        "uv run --project interfaces/discord python scripts/uat_rules.py"
    )
    sys.exit(1)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DISCORD_DIR = os.path.join(_REPO_ROOT, "interfaces", "discord")
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _DISCORD_DIR)

# Stub discord the same way uat_harvest.py does so bot.py imports cleanly.
import types  # noqa: E402
import unittest.mock as _mock  # noqa: E402

_app_commands_stub = types.ModuleType("discord.app_commands")
_app_commands_stub.CommandTree = _mock.MagicMock()
_app_commands_stub.describe = lambda **_: (lambda f: f)
_discord_stub = types.ModuleType("discord")
_discord_stub.Client = type("Client", (), {"__init__": lambda self, **kw: None})
_discord_stub.Intents = type(
    "Intents",
    (),
    {"message_content": False, "default": classmethod(lambda cls: cls())},
)
_discord_stub.Message = object
_discord_stub.Thread = object
_discord_stub.ChannelType = _mock.MagicMock()
_discord_stub.Forbidden = Exception
_discord_stub.HTTPException = Exception
_discord_stub.Interaction = object


# discord.Embed needs add_field + set_footer methods for build_ruling_embed.
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
# Color shim must mirror interfaces/discord/tests/conftest.py — Phase 33 adds
# dark_gold + red for build_ruling_embed marker branching.
_discord_stub.Color = type(
    "Color",
    (),
    {
        "green": classmethod(lambda cls: cls()),
        "dark_green": classmethod(lambda cls: cls()),
        "orange": classmethod(lambda cls: cls()),
        "red": classmethod(lambda cls: cls()),
        "gold": classmethod(lambda cls: cls()),
        "dark_gold": classmethod(lambda cls: cls()),
        "blue": classmethod(lambda cls: cls()),
    },
)
_discord_stub.app_commands = _app_commands_stub
sys.modules.setdefault("discord", _discord_stub)
sys.modules.setdefault("discord.app_commands", _app_commands_stub)

os.environ.setdefault("DISCORD_BOT_TOKEN", "uat-stub")
os.environ.setdefault(
    "SENTINEL_API_KEY", os.environ.get("UAT_SENTINEL_KEY", "uat-stub")
)

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


# ── L-10: LM Studio embedding model must be loaded before any UAT runs ──


async def test_lm_studio_embeddings_reachable(lmstudio_url: str) -> None:
    """L-10 pre-check: LM Studio /v1/embeddings is reachable + nomic-embed-text-v1.5 loaded.

    Catches the scenario where LM Studio is running chat but the embeddings
    model was never pulled / is not loaded. Without this, Wave 1's corpus
    build at module startup fails silently and every UAT flow degrades to
    404/timeout.
    """
    print("\n── LM Studio pre-check (UAT pre-requisite) ──")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{lmstudio_url}/embeddings",
                json={
                    "model": "text-embedding-nomic-embed-text-v1.5",
                    "input": "probe",
                },
            )
        passed = (
            r.status_code == 200
            and isinstance(r.json().get("data"), list)
            and len(r.json()["data"]) >= 1
            and isinstance(r.json()["data"][0].get("embedding"), list)
            and len(r.json()["data"][0]["embedding"]) > 0
        )
        detail = (
            f"status={r.status_code}, dim={len(r.json()['data'][0]['embedding'])}"
            if passed
            else (
                "LM Studio /v1/embeddings not reachable or model not loaded — "
                "download text-embedding-nomic-embed-text-v1.5 in LM Studio"
            )
        )
        record("LM Studio embeddings reachable (L-10 pre-check)", passed, detail)
    except Exception as exc:
        record(
            "LM Studio embeddings reachable (L-10 pre-check)",
            False,
            f"exception: {exc}",
        )


# ── 1. HTTP-level rule flows (sentinel-core → pf2e-module → Obsidian) ──


async def test_http_rule_flows(
    sentinel_url: str,
    sentinel_key: str,
    obsidian_url: str,
    obsidian_key: str,
) -> None:
    print("\n── HTTP rule flows (RUL-01..04) ──")
    auth = {"X-Sentinel-Key": sentinel_key}
    obs_h = {"Authorization": f"Bearer {obsidian_key}"} if obsidian_key else {}

    async with httpx.AsyncClient(timeout=120.0) as client:

        async def post_rule(
            sub_verb: str,
            payload: dict,
            retry_on_500: int = 2,
        ) -> httpx.Response:
            """POST to modules/pathfinder/rule/{sub_verb}. Retries on 500 to
            absorb LLM non-determinism (CR-02 analog correctly rejects
            malformed shapes, but the next prompt often produces valid JSON).
            """
            resp: httpx.Response | None = None
            for _ in range(retry_on_500 + 1):
                resp = await client.post(
                    f"{sentinel_url}/modules/pathfinder/rule/{sub_verb}",
                    json=payload,
                    headers=auth,
                )
                if resp.status_code != 500:
                    return resp
            return resp  # exhausted retries

        # UAT-1..10 — RUL-01..04 HTTP-level assertions. Wave 4 fills bodies.

        record(
            "UAT-1 flanking source hit",
            False,
            "stub — Wave 3/4 fills in POST rule/query + marker=='source' + citation assertions",
        )
        record(
            "UAT-2 off-guard condition source hit",
            False,
            "stub — Wave 3/4 fills in POST rule/query + book=='Pathfinder Player Core'",
        )
        record(
            "UAT-3 edge-case generated",
            False,
            "stub — Wave 3/4 fills in corpus-miss path → marker=='generated', citations=[]",
        )
        record(
            "UAT-4 PF1 decline THAC0 (no cache write)",
            False,
            "stub — Wave 3/4 asserts marker=='declined' AND Obsidian GET 404 at would-be cache path",
        )
        record(
            "UAT-5 PF1 decline spell schools",
            False,
            "stub — Wave 3/4 asserts marker=='declined', answer mentions 'spell schools'",
        )
        record(
            "UAT-6 soft-trigger flat-footed after trip passes",
            False,
            "stub — Wave 3/4 asserts marker != 'declined' for Remaster off-guard rephrasing",
        )
        record(
            "UAT-7 identical-query cache hit < 2s",
            False,
            "stub — Wave 3/4 asserts dt<2s + reused=True on second identical query",
        )
        record(
            "UAT-8 reuse match >= 0.80 returns cached note",
            False,
            "stub — Wave 3/4 asserts reused=True + reuse_note contains 'reusing prior ruling on'",
        )
        record(
            "UAT-9 reuse match < 0.80 composes fresh",
            False,
            "stub — Wave 3/4 asserts new file written in different topic when cosine<0.80",
        )
        record(
            "UAT-10 topic-slug folder layout >= 2 files under /rulings/flanking/",
            False,
            "stub — Wave 3/4 asserts Obsidian LIST under rulings/flanking/ returns >=2 files",
        )

        # Track cache paths for teardown (populated once Wave 4 fills in writes).
        for topic in ("flanking", "off-guard", "misc", "combat", "dying"):
            # Placeholder: Wave 4 will add ACTUAL written paths to this set as
            # each assertion executes, so teardown can clean them.
            _TEARDOWN_CACHE_PATHS.add(f"mnemosyne/pf2e/rulings/{topic}/.uat-marker")

        # Reference mirrors to silence unused-variable warnings during Wave 0:
        _ = (auth, obs_h, post_rule)


# ── 2. Bot routing layer (bot._pf_dispatch → live sentinel-core) ──


async def test_bot_routing(sentinel_url: str, sentinel_key: str) -> None:
    print("\n── Bot routing (:pf rule via _pf_dispatch → live stack) ──")

    bot._sentinel_client._base_url = sentinel_url.rstrip("/")
    bot._sentinel_client._api_key = sentinel_key

    # UAT-11..15 — bot dispatch assertions. Wave 4 fills bodies.

    record(
        "UAT-11 :pf rule <text> via bot returns embed dict",
        False,
        "stub — Wave 4 fills in bot._pf_dispatch('rule ...') → {type:'embed', embed: Embed}",
    )
    record(
        "UAT-12 :pf rule show <topic> returns str",
        False,
        "stub — Wave 4 fills in bot._pf_dispatch('rule show flanking') → string listing files",
    )
    record(
        "UAT-13 :pf rule history returns str with N=10 entries",
        False,
        "stub — Wave 4 fills in bot._pf_dispatch('rule history') → string with 10 entries",
    )
    record(
        "UAT-14 :pf rule list returns str enumerating topics",
        False,
        "stub — Wave 4 fills in bot._pf_dispatch('rule list') → string of topic folders",
    )
    record(
        "UAT-15 slow-query placeholder.send + placeholder.edit sequence",
        False,
        "stub — Wave 4 simulates 5s delay; mock channel.send then placeholder.edit",
    )


# ── 3. Container smoke — healthz + REGISTRATION_PAYLOAD 14-route check ──


async def test_container_smoke(sentinel_url: str, sentinel_key: str) -> None:
    print("\n── Container smoke (UAT-16 rebuild verification) ──")
    auth = {"X-Sentinel-Key": sentinel_key}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(f"{sentinel_url}/health")
            health_ok = r.status_code == 200
        except Exception:
            health_ok = False

        # Module registry lists pathfinder with 14 routes — GET /modules returns
        # the in-memory registry list (Phase 27 module proxy pattern).
        try:
            r = await client.get(f"{sentinel_url}/modules", headers=auth)
            if r.status_code == 200:
                modules = r.json() or []
                pf = (
                    next(
                        (m for m in modules if m.get("name") == "pathfinder"),
                        None,
                    )
                    or {}
                )
                routes = pf.get("routes") or []
                has_rule = any(
                    (route.get("path") if isinstance(route, dict) else route) == "rule"
                    for route in routes
                )
                passed = health_ok and len(routes) == 14 and has_rule
                record(
                    "UAT-16 pathfinder registered with 14 routes incl. rule",
                    passed,
                    f"health={health_ok}, routes={len(routes)}, rule_present={has_rule}",
                )
            else:
                record(
                    "UAT-16 pathfinder registered with 14 routes incl. rule",
                    False,
                    f"GET /modules status={r.status_code}",
                )
        except Exception as exc:
            record(
                "UAT-16 pathfinder registered with 14 routes incl. rule",
                False,
                f"exception: {exc}",
            )


# ── Teardown — clean rule UAT artefacts ──


async def _teardown_rule_cache(obsidian_url: str, obsidian_key: str) -> None:
    if not obsidian_key or not _TEARDOWN_CACHE_PATHS:
        return
    print("\n── Teardown (rule cache) ──")
    headers = {"Authorization": f"Bearer {obsidian_key}"}
    deleted = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for path in _TEARDOWN_CACHE_PATHS:
            try:
                r = await client.delete(
                    f"{obsidian_url}/vault/{path}", headers=headers
                )
                if r.status_code in (200, 204, 404):
                    deleted += 1
            except Exception as exc:
                print(f"  [teardown] {path}: {exc}", file=sys.stderr)
    print(
        f"  cleaned {deleted}/{len(_TEARDOWN_CACHE_PATHS)} rule cache files "
        "(Wave 0 placeholders — Wave 4 adds real paths)"
    )


# ── Entry ──


async def run_all(
    sentinel_url: str,
    sentinel_key: str,
    obsidian_url: str,
    obsidian_key: str,
    lmstudio_url: str,
) -> None:
    try:
        await test_lm_studio_embeddings_reachable(lmstudio_url)
        await test_container_smoke(sentinel_url, sentinel_key)
        await test_http_rule_flows(
            sentinel_url, sentinel_key, obsidian_url, obsidian_key
        )
        await test_bot_routing(sentinel_url, sentinel_key)
    finally:
        await _teardown_rule_cache(obsidian_url, obsidian_key)


def main() -> None:
    if not os.getenv("LIVE_TEST"):
        print("LIVE_TEST=1 must be set to run rules UAT. Exiting.")
        sys.exit(1)

    sentinel_url = os.environ.get("UAT_SENTINEL_URL", "http://localhost:8000")
    sentinel_key = _read_secret(
        "sentinel_api_key", os.environ.get("UAT_SENTINEL_KEY", "")
    )
    obsidian_url = os.environ.get("UAT_OBSIDIAN_URL", "http://localhost:27123")
    obsidian_key = _read_secret(
        "obsidian_api_key", os.environ.get("UAT_OBSIDIAN_KEY", "")
    )
    lmstudio_url = os.environ.get("UAT_LMSTUDIO_URL", "http://localhost:1234/v1")

    if not sentinel_key:
        print(
            "ERROR: UAT_SENTINEL_KEY or /run/secrets/sentinel_api_key required."
        )
        sys.exit(1)

    asyncio.run(
        run_all(sentinel_url, sentinel_key, obsidian_url, obsidian_key, lmstudio_url)
    )

    total = len(_RESULTS)
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    failed = total - passed

    print("\n=== Phase 33 Rules UAT Report ===")
    print(f"Total: {total}  Passed: {passed}  Failed: {failed}")
    if failed:
        print("FAILED tests:")
        for label, ok, detail in _RESULTS:
            if not ok:
                print(f"  - {label} — {detail}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
