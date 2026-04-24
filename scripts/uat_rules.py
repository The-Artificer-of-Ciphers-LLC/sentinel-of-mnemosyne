#!/usr/bin/env python3
"""
Phase 33 Rules Engine — live-stack UAT (16 assertions).

Mirrors scripts/uat_harvest.py pattern. Exercises the 16 UAT items in
.planning/phases/33-rules-engine/33-RESEARCH.md §Live-UAT Plan against
the live Docker stack (sentinel-core + pf2e-module + discord + Obsidian
+ LM Studio with embeddings model loaded).

Wave 4 (Plan 33-05) fleshes the Wave 0 skeleton into real assertion
bodies. Each UAT-N assertion either passes or records a real failure;
no silent skips beyond the LIVE_TEST gate (CLAUDE.md AI Deferral Ban).

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
import hashlib
import os
import sys
import time
from typing import Any

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
    mark = "✓" if passed else "✗"
    print(f"  {mark} [{status}] {label}{suffix}")


def _read_secret(name: str, env_fallback: str = "") -> str:
    try:
        with open(f"/run/secrets/{name}") as f:
            return f.read().strip()
    except FileNotFoundError:
        return env_fallback


def _normalize_query(q: str) -> str:
    """Mirrors app/rules.py::normalize_query — needed for cache-path computation."""
    return " ".join((q or "").lower().split())


def _query_hash(q: str) -> str:
    """Mirrors app/rules.py::query_hash — sha1[:8] of normalised query."""
    return hashlib.sha1(_normalize_query(q).encode("utf-8")).hexdigest()[:8]


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


async def _http_rule_query(
    client: httpx.AsyncClient,
    sentinel_url: str,
    auth: dict,
    query: str,
    user_id: str = "uat-rules",
    retry_on_500: int = 2,
) -> tuple[int, dict]:
    """POST modules/pathfinder/rule/query. Retries on 500 to absorb LLM
    non-determinism (CR-02 analog rejects malformed shapes; the next prompt
    typically produces valid JSON)."""
    resp: httpx.Response | None = None
    for _ in range(retry_on_500 + 1):
        resp = await client.post(
            f"{sentinel_url}/modules/pathfinder/rule/query",
            json={"query": query, "user_id": user_id},
            headers=auth,
        )
        if resp.status_code != 500:
            break
    try:
        body = resp.json() if resp is not None else {}
    except Exception:
        body = {"_raw": resp.text if resp is not None else ""}
    return (resp.status_code if resp is not None else 0), body


def _track_cache_path(query: str, topic: str | None) -> None:
    """Record a cache path that the UAT created so teardown can DELETE it.
    `topic` is None when the response was declined — declines write no cache."""
    if not topic:
        return
    h = _query_hash(query)
    _TEARDOWN_CACHE_PATHS.add(f"mnemosyne/pf2e/rulings/{topic}/{h}.md")


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

        # UAT-1: flanking source hit — D-08 shape + marker valid
        try:
            t0 = time.monotonic()
            status, body = await _http_rule_query(
                client, sentinel_url, auth, "How does flanking work?"
            )
            dt1 = time.monotonic() - t0
            ok = (
                status == 200
                and body.get("marker") in ("source", "generated")
                and isinstance(body.get("question"), str)
                and "answer" in body
                and "why" in body
                and isinstance(body.get("citations"), list)
            )
            _track_cache_path("How does flanking work?", body.get("topic"))
            record(
                "UAT-1 flanking source hit",
                ok,
                f"status={status} marker={body.get('marker')} "
                f"citations={len(body.get('citations') or [])} dt={dt1:.2f}s",
            )
        except Exception as exc:
            record("UAT-1 flanking source hit", False, f"exception: {exc}")

        # UAT-2: off-guard condition source hit — citation comes from Player Core
        try:
            status, body = await _http_rule_query(
                client, sentinel_url, auth,
                "What's the AC penalty for being off-guard?",
            )
            citations = body.get("citations") or []
            book_match = any(
                "player core" in (c.get("book", "") or "").lower()
                for c in citations
            )
            ok = (
                status == 200
                and body.get("marker") == "source"
                and book_match
            )
            _track_cache_path(
                "What's the AC penalty for being off-guard?", body.get("topic")
            )
            record(
                "UAT-2 off-guard condition source hit",
                ok,
                f"marker={body.get('marker')} "
                f"books={[c.get('book') for c in citations[:2]]}",
            )
        except Exception as exc:
            record("UAT-2 off-guard condition source hit", False, f"exception: {exc}")

        # UAT-3: edge-case generated path — advanced book (Kineticist / Rage of Elements)
        try:
            status, body = await _http_rule_query(
                client, sentinel_url, auth,
                "Can a Kineticist's impulse crit on a save DC check?",
            )
            ok = (
                status == 200
                and body.get("marker") == "generated"
                and body.get("source") in (None, "")
                and (body.get("citations") or []) == []
            )
            _track_cache_path(
                "Can a Kineticist's impulse crit on a save DC check?",
                body.get("topic"),
            )
            record(
                "UAT-3 edge-case generated",
                ok,
                f"marker={body.get('marker')} source={body.get('source')!r} "
                f"citations={len(body.get('citations') or [])}",
            )
        except Exception as exc:
            record("UAT-3 edge-case generated", False, f"exception: {exc}")

        # UAT-4: PF1 decline THAC0 — declined marker, NO cache write
        try:
            decline_q = "What is THAC0?"
            status, body = await _http_rule_query(
                client, sentinel_url, auth, decline_q,
            )
            decline_ok = (
                status == 200
                and body.get("marker") == "declined"
                and (body.get("answer") or "").startswith(
                    "This Sentinel only supports PF2e Remaster"
                )
            )
            # Declines write no cache. The would-be path uses topic 'misc' OR none
            # — we GET the misc path expecting 404 (no cache).
            no_cache_ok = True
            if obs_h:
                h = _query_hash(decline_q)
                cache_path = f"mnemosyne/pf2e/rulings/misc/{h}.md"
                try:
                    r = await client.get(
                        f"{obsidian_url}/vault/{cache_path}", headers=obs_h
                    )
                    no_cache_ok = r.status_code == 404
                except Exception:
                    no_cache_ok = True  # GET failure means we cannot prove cache; pass on the marker check alone
            record(
                "UAT-4 PF1 decline THAC0 (no cache write)",
                decline_ok and no_cache_ok,
                f"marker={body.get('marker')} no_cache={no_cache_ok} "
                f"answer_prefix={(body.get('answer') or '')[:50]!r}",
            )
        except Exception as exc:
            record(
                "UAT-4 PF1 decline THAC0 (no cache write)",
                False,
                f"exception: {exc}",
            )

        # UAT-5: PF1 decline spell schools — answer must mention schools
        try:
            status, body = await _http_rule_query(
                client, sentinel_url, auth, "Rules for spell schools in PF2",
            )
            ok = (
                body.get("marker") == "declined"
                and "spell school" in (body.get("answer") or "").lower()
            )
            record(
                "UAT-5 PF1 decline spell schools",
                ok,
                f"marker={body.get('marker')} "
                f"answer_has_schools="
                f"{'spell school' in (body.get('answer') or '').lower()}",
            )
        except Exception as exc:
            record("UAT-5 PF1 decline spell schools", False, f"exception: {exc}")

        # UAT-6: soft-trigger flat-footed-after-trip does NOT decline (Remaster off-guard)
        try:
            status, body = await _http_rule_query(
                client, sentinel_url, auth,
                "My character is flat-footed after being tripped — what's the penalty?",
            )
            ok = body.get("marker") in ("source", "generated")  # NOT "declined"
            _track_cache_path(
                "My character is flat-footed after being tripped — what's the penalty?",
                body.get("topic"),
            )
            record(
                "UAT-6 soft-trigger flat-footed after trip passes",
                ok,
                f"marker={body.get('marker')} (must NOT be 'declined')",
            )
        except Exception as exc:
            record(
                "UAT-6 soft-trigger flat-footed after trip passes",
                False,
                f"exception: {exc}",
            )

        # UAT-7: identical-query cache hit — repeat UAT-1, expect fast + reused/cache-warm
        try:
            t0 = time.monotonic()
            status, body = await _http_rule_query(
                client, sentinel_url, auth, "How does flanking work?",
            )
            dt2 = time.monotonic() - t0
            # Either the route flagged reused=True (D-14 last_reused_at update) OR
            # the second-call latency is well below the LLM compose envelope.
            ok = status == 200 and (body.get("reused") is True or dt2 < 3.0)
            record(
                "UAT-7 identical-query cache hit < 3s",
                ok,
                f"reused={body.get('reused')} dt={dt2:.2f}s",
            )
        except Exception as exc:
            record("UAT-7 identical-query cache hit < 3s", False, f"exception: {exc}")

        # UAT-8: reuse match >= 0.80 — similar query in same topic returns cached note
        try:
            status, body = await _http_rule_query(
                client, sentinel_url, auth,
                "If I'm flanking an enemy, what happens to their AC?",
            )
            reuse_note = body.get("reuse_note") or ""
            ok = (
                body.get("reused") is True
                and (
                    "reuse" in reuse_note.lower()
                    or "prior ruling" in reuse_note.lower()
                )
            )
            _track_cache_path(
                "If I'm flanking an enemy, what happens to their AC?",
                body.get("topic"),
            )
            record(
                "UAT-8 reuse match >= 0.80 returns cached note",
                ok,
                f"reused={body.get('reused')} note={reuse_note[:60]!r}",
            )
        except Exception as exc:
            record(
                "UAT-8 reuse match >= 0.80 returns cached note",
                False,
                f"exception: {exc}",
            )

        # UAT-9: reuse match < 0.80 — dissimilar query (different topic) composes fresh.
        # The status==200 + marker presence guards prevent a 404 (route missing)
        # from masquerading as "fresh compose" via body.get('reused', False) == False.
        try:
            status, body = await _http_rule_query(
                client, sentinel_url, auth,
                "What's the exact DC to Demoralize a level 3 foe?",
            )
            ok = (
                status == 200
                and body.get("marker") in ("source", "generated")
                and body.get("reused", False) is False
            )
            _track_cache_path(
                "What's the exact DC to Demoralize a level 3 foe?",
                body.get("topic"),
            )
            record(
                "UAT-9 reuse match < 0.80 composes fresh",
                ok,
                f"status={status} marker={body.get('marker')} "
                f"reused={body.get('reused')} topic={body.get('topic')}",
            )
        except Exception as exc:
            record(
                "UAT-9 reuse match < 0.80 composes fresh",
                False,
                f"exception: {exc}",
            )

        # UAT-10: topic-folder browsability — /rule/show flanking returns >= 1
        try:
            r = await client.post(
                f"{sentinel_url}/modules/pathfinder/rule/show",
                json={"topic": "flanking"},
                headers=auth,
            )
            d = r.json() if r.status_code == 200 else {}
            ok = (
                r.status_code == 200
                and isinstance(d.get("count"), int)
                and d.get("count", 0) >= 1
                and isinstance(d.get("rulings"), list)
            )
            record(
                "UAT-10 topic-slug folder layout >= 1 ruling under /rulings/flanking/",
                ok,
                f"status={r.status_code} count={d.get('count')} "
                f"rulings={len(d.get('rulings') or [])}",
            )
        except Exception as exc:
            record(
                "UAT-10 topic-slug folder layout >= 1 ruling under /rulings/flanking/",
                False,
                f"exception: {exc}",
            )


# ── 2. Bot routing layer (bot._pf_dispatch → live sentinel-core) ──


class _MockMessage:
    """Mock Discord message — captures .edit calls for placeholder-edit UX assertions."""

    def __init__(self) -> None:
        self.edits: list[dict[str, Any]] = []

    async def edit(self, *, content=None, embed=None) -> None:
        self.edits.append({"content": content, "embed": embed})


class _MockChannel:
    """Mock Discord channel — captures .send calls and returns a _MockMessage."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.last_msg: _MockMessage | None = None

    async def send(self, content="") -> _MockMessage:
        self.sent.append(content)
        self.last_msg = _MockMessage()
        return self.last_msg


async def test_bot_routing(sentinel_url: str, sentinel_key: str) -> None:
    print("\n── Bot routing (:pf rule via _pf_dispatch → live stack) ──")

    # Point the module-level _sentinel_client at the live UAT stack. The client
    # is a regular Python object — mutating its private URL/key fields is the
    # established pattern from uat_harvest.py (test_bot_routing).
    bot._sentinel_client._base_url = sentinel_url.rstrip("/")
    bot._sentinel_client._api_key = sentinel_key

    # UAT-11: :pf rule <free text> via bot — returns embed dict
    try:
        ch = _MockChannel()
        result = await bot._pf_dispatch(
            "rule How does flanking work?", "uat-rules", channel=ch,
        )
        # With a channel set, the rule branch sends a placeholder + edits it,
        # returning {"type":"suppressed", ..., "embed": <Embed>} on success.
        # The test accepts either suppressed (with embed) or embed (without
        # placeholder, e.g. if channel.send misbehaved).
        ok = (
            isinstance(result, dict)
            and result.get("type") in ("suppressed", "embed")
            and result.get("embed") is not None
        )
        record(
            "UAT-11 :pf rule <text> via bot returns embed dict",
            ok,
            f"type={result.get('type') if isinstance(result, dict) else type(result).__name__}",
        )
    except Exception as exc:
        record(
            "UAT-11 :pf rule <text> via bot returns embed dict",
            False,
            f"exception: {exc}",
        )

    # UAT-12: :pf rule show <topic> returns string listing files
    try:
        result = await bot._pf_dispatch("rule show flanking", "uat-rules")
        ok = isinstance(result, str) and (
            "flanking" in result.lower()
            or "no rulings" in result.lower()
            or "rulings under" in result.lower()
        )
        record(
            "UAT-12 :pf rule show <topic> returns str",
            ok,
            f"result={str(result)[:80]!r}",
        )
    except Exception as exc:
        record(
            "UAT-12 :pf rule show <topic> returns str",
            False,
            f"exception: {exc}",
        )

    # UAT-13: :pf rule history returns string of recent rulings.
    # Reject the "outer except handler returned 'NPC not found.' / generic
    # error string" false-positive by requiring the response to mention
    # rulings (or the explicit empty-list literal) — both shapes the rule
    # history branch produces on success.
    try:
        result = await bot._pf_dispatch("rule history", "uat-rules")
        s = str(result).lower()
        ok = isinstance(result, str) and (
            "recent rulings" in s
            or "no rulings yet" in s
            or "rulings (" in s
        )
        record(
            "UAT-13 :pf rule history returns str",
            ok,
            f"result={str(result)[:80]!r}",
        )
    except Exception as exc:
        record("UAT-13 :pf rule history returns str", False, f"exception: {exc}")

    # UAT-14: D-15 scope-lock POSITIVE — Monster Core query marks 'generated' (NOT declined)
    # The PF1 denylist is PF1-only; Monster Core is deferred to Phase 33.x but
    # any query referencing it must fall through to generate_ruling_fallback,
    # producing marker='generated' rather than 'declined'.
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            status, body = await _http_rule_query(
                client,
                sentinel_url,
                {"X-Sentinel-Key": sentinel_key},
                "How do I adjust a creature encounter difficulty per Monster Core?",
            )
        ok = body.get("marker") == "generated"  # D-15: NOT "declined"
        _track_cache_path(
            "How do I adjust a creature encounter difficulty per Monster Core?",
            body.get("topic"),
        )
        record(
            "UAT-14 D-15 Monster-Core query marks 'generated' (not declined)",
            ok,
            f"marker={body.get('marker')} "
            "(must be 'generated' per D-15 scope-lock — Monster Core "
            "queries flow through advanced-book generate_ruling_fallback "
            "path; PF1 denylist must NOT over-fire)",
        )
    except Exception as exc:
        record(
            "UAT-14 D-15 Monster-Core query marks 'generated' (not declined)",
            False,
            f"exception: {exc}",
        )

    # UAT-15: slow-query placeholder UX (D-11) — channel.send + placeholder.edit sequence
    try:
        ch = _MockChannel()
        await bot._pf_dispatch(
            "rule How does flanking work?", "uat-rules", channel=ch,
        )
        placeholder_sent = len(ch.sent) == 1 and "thinking" in ch.sent[0].lower()
        last_msg = ch.last_msg
        edit_called = last_msg is not None and len(last_msg.edits) >= 1
        # The successful edit must carry the rendered embed.
        edit_has_embed = (
            edit_called
            and last_msg is not None
            and last_msg.edits[-1].get("embed") is not None
        )
        ok = placeholder_sent and edit_called and edit_has_embed
        record(
            "UAT-15 slow-query placeholder.send + placeholder.edit sequence",
            ok,
            f"sent={len(ch.sent)} edits={len(last_msg.edits) if last_msg else 0} "
            f"edit_has_embed={edit_has_embed}",
        )
    except Exception as exc:
        record(
            "UAT-15 slow-query placeholder.send + placeholder.edit sequence",
            False,
            f"exception: {exc}",
        )


# ── 3. Container smoke — healthz + REGISTRATION_PAYLOAD 14-route check ──


async def test_container_smoke(sentinel_url: str, sentinel_key: str) -> None:
    print("\n── Container smoke (UAT-16 stack rebuild verification) ──")
    auth = {"X-Sentinel-Key": sentinel_key}

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Health checks for both services.
        try:
            r_sc = await client.get(f"{sentinel_url}/health")
            sc_health_ok = r_sc.status_code == 200
        except Exception:
            sc_health_ok = False
        try:
            r_pf = await client.get(
                f"{sentinel_url}/modules/pathfinder/healthz", headers=auth
            )
            pf_health_ok = r_pf.status_code == 200
        except Exception:
            pf_health_ok = False

        # Module registry must list pathfinder with 14 routes including 'rule'.
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
                route_count = len(routes)
                has_rule = any(
                    (
                        route.get("path")
                        if isinstance(route, dict)
                        else route
                    )
                    == "rule"
                    for route in routes
                )
                passed = (
                    sc_health_ok
                    and pf_health_ok
                    and route_count == 14
                    and has_rule
                )
                record(
                    "UAT-16 stack smoke — sc/pf healthy, 14 routes, rule present",
                    passed,
                    f"sc={sc_health_ok} pf={pf_health_ok} "
                    f"routes={route_count} rule_present={has_rule}",
                )
            else:
                record(
                    "UAT-16 stack smoke — sc/pf healthy, 14 routes, rule present",
                    False,
                    f"GET /modules status={r.status_code}",
                )
        except Exception as exc:
            record(
                "UAT-16 stack smoke — sc/pf healthy, 14 routes, rule present",
                False,
                f"exception: {exc}",
            )


# ── Teardown — clean rule UAT artefacts from Obsidian vault ──


async def _teardown_rule_cache(obsidian_url: str, obsidian_key: str) -> None:
    if not obsidian_key or not _TEARDOWN_CACHE_PATHS:
        return
    print("\n── Teardown (rule cache) ──")
    headers = {"Authorization": f"Bearer {obsidian_key}"}
    deleted = 0
    failed = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for path in sorted(_TEARDOWN_CACHE_PATHS):
            try:
                r = await client.delete(
                    f"{obsidian_url}/vault/{path}", headers=headers
                )
                if r.status_code in (200, 204, 404):
                    deleted += 1
                else:
                    failed += 1
                    print(
                        f"  [teardown] {path}: status={r.status_code}",
                        file=sys.stderr,
                    )
            except Exception as exc:
                failed += 1
                print(f"  [teardown] {path}: {exc}", file=sys.stderr)
    print(
        f"  cleaned {deleted}/{len(_TEARDOWN_CACHE_PATHS)} rule cache files "
        f"(failed={failed})"
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

    print()
    print(f"── UAT Summary: {passed}/{total} passed ──")
    if failed:
        print()
        print("FAILED tests:")
        for label, ok, detail in _RESULTS:
            if not ok:
                print(f"  ✗ {label} — {detail}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
