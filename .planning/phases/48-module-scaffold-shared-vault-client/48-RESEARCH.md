# Phase 48: Module Scaffold + Shared Vault Client - Research

**Researched:** 2026-07-08
**Domain:** Python/FastAPI Docker module scaffolding + shared-library extraction (Obsidian REST client) inside the existing Sentinel of Mnemosyne monorepo
**Confidence:** HIGH — every claim below is grounded in direct reads of the live repo (`modules/pathfinder/`, `shared/`, `sentinel-core/app/`), not general framework knowledge. No external libraries are introduced in this phase.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Shared Vault Client (XMOD-01)**
- **D-01:** Promote the Obsidian client into `shared/` (`sentinel-shared`) as a composable core + mixins, built now (not deferred until 4 modules exist). Layout in `sentinel_shared`:
  - `ObsidianClientCore` — HTTP plumbing (httpx client, `Authorization: Bearer {OBSIDIAN_API_KEY}` against `OBSIDIAN_BASE_URL`, `_safe_request` graceful-degrade helper) + `get_note`, `put_note`, `list_directory`, `patch_frontmatter_field`.
  - `ObsidianHeadingMixin` — `patch_heading`.
  - `ObsidianBinaryMixin` — `put_binary`, `get_binary`.
- **D-02:** pf2e's client becomes pure composition: `class ObsidianClient(ObsidianClientCore, ObsidianBinaryMixin, ObsidianHeadingMixin)`. No duplicated client logic remains in pf2e's tree.
- **D-03:** Music consumes `ObsidianClientCore` only (no binary/heading). Never imports Core's `Vault` Protocol / `ObsidianVault` (MUS-02).
- **D-04:** Behavior-preserving lift, not redesign — copy pf2e's exact request semantics verbatim (120s `put_note` timeout, `list_directory` recursion/depth guard, content-type handling). Zero behavior drift.

**pf2e Cutover (criterion #4)**
- **D-05:** Strict — no re-export shim. Delete pf2e's standalone client logic; rewrite the two real coupling sites: `modules/pathfinder/app/main.py` (~:57 import, ~:203 `lifespan()` instantiation onto `app.state.obsidian_client`) and `modules/pathfinder/tests/test_aliases_path_probe.py` (~:28 direct construct). The ~10 duck-typed consumers need no change; the 7 local `FakeObsidian` doubles stay put. A file still named `obsidian.py` exporting `ObsidianClient` in pf2e must be a legitimate composition subclass, not "still owns a client."
- **D-06:** Regression guard is an acceptance criterion, not a follow-up — the full `modules/pathfinder/tests/` suite (pytest, `asyncio_mode=auto`) must pass, with explicit attention to `test_aliases_path_probe.py` (builds client against `MockTransport`) and `lifespan()`/`app.state.obsidian_client` wiring.

**Music namespace, first write & schema proof (MUS-02, MUS-05)**
- **D-07:** `/music/` is a new module-owned top-level namespace (sibling to `self/`, `notes/`, `ops/`, `inbox/`, `templates/`, `mnemosyne/pf2e/`) — not PARA-classified. Subfolders: `music/lessons/`, `music/practice-log/`, `music/ideas/`.
- **D-08:** First write = a cross-linked hub mesh, not a single hub. Write `music/index.md` plus `music/lessons/index.md`, `music/practice-log/index.md`, `music/ideas/index.md`, mutually wikilinked. This is the only seed provably zero-orphan under the real rule (D-10).
- **D-09:** Every music note follows the Phase-45/47 contract: leading YAML frontmatter + H1 claim title + ≥1 resolvable `[[wikilink]]` + trailing ` ```_schema ` fenced block carrying `title` and `wikilinks`, with `listenbrainz_context`/`discogs_context` fields null by default.
- **D-10:** Compliance is proven structurally in-module, not via Core. Core's `:graph`/`:check` walk is hard-scoped to `NOTES_ROOT="notes"` (`links_sidecar_index.py` → `walk_vault(root=NOTES_ROOT)`), so `music/` is invisible to Core's REST checker today. The verified orphan rule (`graph_analysis.build_graph_report`) is `orphan ⇔ not outlinks[path] and not backlinks[path]`; `resolve_wikilink` only creates an edge when the target file already exists. Phase 48 asserts compliance with a module-side test that builds the `music/` notes-map and checks zero orphans + schema shape. Do NOT extend Core's `NOTES_ROOT` walk (violates MUS-01). Full Core-side `:graph`/`:check` participation for `music/` is deferred.

**Module scaffold + registration (MUS-01)**
- **D-11:** `modules/music/` mirrors `modules/pathfinder/`'s skeleton exactly — `app/main.py`, `app/config.py`, `app/obsidian.py`, `compose.yml` (`profiles: ["music"]`), `healthz` route, `Dockerfile`, `pyproject.toml` (`pythonpath = [".", "../../shared"]`). Zero Core code changes.
- **D-12:** Registration mirrors pf2e: `lifespan()` posts `REGISTRATION_PAYLOAD` (`name: "music"`, `base_url`, `routes`) to `POST /modules/register` with 5-attempt exponential backoff (1s→16s) + 30s heartbeat re-register. Phase-48 payload declares a minimal route set (`healthz` only) — real routes come in phases 49+.

**Sweeper protection + warm-tier (MUS-01, Pitfall 1)**
- **D-13:** Protect `music/` from the vault sweeper via deploy-env only, no Core code change, in the SAME commit as the first `music/` write. Set both `SWEEP_SKIP_PREFIXES` and `PROTECTED_NAMESPACES` (JSON-list env vars). Both are pydantic-settings REPLACE-semantics overrides — must reproduce Core's full committed default tuple plus `music/`. Do NOT hand-copy the defaults — generate the override value from Core's current defaults.
- **D-14:** Belt-and-suspenders rationale: `SWEEP_SKIP_PREFIXES` skips the walk/classify pass; `PROTECTED_NAMESPACES` independently blocks any physical move (`ProtectedPathError`, already caught non-fatally by the sweeper).
- **D-15:** Warm-tier recall exclusion for `music/` is deferred. `RecallConfig.exclude_prefixes` (`sentinel-core/app/services/recall.py` ~:249) is instantiated with no args in `composition.py` (~:409) and has no env path — adding `music/` needs a Core change, forbidden here.

### Claude's Discretion
- Exact file layout of the client inside `sentinel_shared` (single `obsidian.py` holding core+mixins vs. an `obsidian/` subpackage) — following the flat single-purpose-module convention (`llm_call.py`, `similarity.py`).
- Whether Music's `app/obsidian.py` is a trivial `ObsidianClientCore` subclass or a direct alias.
- Exact hub-note prose and frontmatter fields beyond the mandated schema shape.
- The mechanism that generates the env-override value (compose templating vs. a small deploy-time script) — must derive from Core's committed defaults rather than a hand-maintained literal.

### Deferred Ideas (OUT OF SCOPE)
- Warm-tier recall exclusion for `music/` — needs a Core `RecallConfig.exclude_prefixes` change (no env path); wire deliberately alongside future deterministic `:music history` feature.
- Binary vault storage — `ObsidianBinaryMixin` built and composable but unused by music (no roadmapped module stores binaries yet).
- `patch_heading` in music (e.g. "Listening Log" append) — mixin ready, adopt later if desired.
- Real module routes — practice logging, idea capture, history queries, routine builder, Discord wiring, ListenBrainz/Discogs — Phases 49+.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MUS-01 | Music module runs as standalone Docker service, registers via `POST /modules/register`, zero Core code changes | §3 Module Scaffold, §5 Sweeper Protection — exact file list, compose/Dockerfile templates, registration payload/backoff pattern extracted verbatim from pf2e |
| MUS-02 | Module persists to `music/` via its own thin `ObsidianClient`, never imports Core's `Vault` Protocol | §1 Mixin Extraction, §3 Music Scaffold — `ObsidianClientCore`-only composition for music/app/obsidian.py |
| MUS-05 | Every music note carries `_schema` block + wikilinks, zero orphans | §4 First Write + Orphan Self-Check — exact hub-mesh note contents + vendored orphan-checker recommendation |
| XMOD-01 | Duplicated per-module `ObsidianClient` promoted into shared `sentinel_shared` package | §1 Mixin Extraction, §2 pf2e Cutover — exact class skeletons, exact coupling sites to rewrite, regression-guard command |
</phase_requirements>

## Summary

This phase is a pure refactor + scaffold exercise inside a codebase that already has one complete reference implementation (`modules/pathfinder/`) to mirror byte-for-byte. There are no new external dependencies, no new frameworks, and no ecosystem risk — every technology involved (FastAPI, httpx, pydantic-settings, pyyaml, pytest-asyncio) is already pinned and running in this repo. The work is 100% "verify against the live code and produce an exact diff," not "research an unfamiliar library."

The two hard architectural problems this research resolves are: (1) how to split `modules/pathfinder/app/obsidian.py`'s 227 lines into a composable core + two mixins that pf2e can recompose with zero behavior drift, and (2) how the music container — which structurally CANNOT import `sentinel-core` at runtime (separate Docker process, no shared Python runtime) — proves its own zero-orphan compliance using the exact same rule Core's `graph_analysis.build_graph_report` implements, without duplicating that logic by copy-paste-and-drift. The answer to (2) is to vendor a tiny (~15-line) pure copy of the orphan/wikilink-resolution logic into `sentinel_shared` itself (not into the music module), so both a future Core-side test and the music module's test import the *same* pure function — turning a "copy that will drift" into "shared code that can't drift," which is exactly the D-01 rationale applied recursively to a second cross-cutting concern discovered during this research.

**Primary recommendation:** Extract `ObsidianClientCore` + `ObsidianHeadingMixin` + `ObsidianBinaryMixin` into a single new file `shared/sentinel_shared/obsidian.py` (flat-module convention, matching `llm_call.py`/`similarity.py`), rewire pf2e's two coupling sites to `from sentinel_shared.obsidian import ObsidianClientCore, ObsidianHeadingMixin, ObsidianBinaryMixin` + a thin one-line composition subclass, scaffold `modules/music/` as an exact structural mirror of `modules/pathfinder/`, and land the `music/` sweeper skip-prefix + protected-namespace env overrides in the SAME commit as the first `music/index.md` hub-mesh write.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Obsidian REST HTTP plumbing (auth, timeouts, safe-degrade) | Shared library (`shared/sentinel_shared`) | — | Consumed identically by every module process; owning it once in a library both pf2e and music import at build time is the only way to avoid a second copy (XMOD-01) |
| pf2e's NPC/session/rules domain logic | API/Backend (pf2e module container) | — | Unaffected by this phase; only its `obsidian.py` import site changes |
| Music module's FastAPI app + lifespan + registration | API/Backend (music module container) | — | New standalone Docker service, structurally identical tier to pf2e — Core never imports it (module isolation invariant) |
| Module registry + generic HTTP proxy (`/modules/register`, `/modules/{name}/{path}`) | API/Backend (sentinel-core) | — | Already built, reused verbatim — zero Core changes this phase |
| Vault sweeper skip-prefix / protected-namespace enforcement | API/Backend (sentinel-core) | Database/Storage (Obsidian vault via REST) | Core-side config governs what the sweeper touches; the *values* are generated from Core's committed defaults but the enforcement mechanism itself is unchanged Core code |
| Zero-orphan / `_schema` structural self-check for `music/` notes | API/Backend (music module container, module-side test) | Shared library (vendored pure orphan-checker in `sentinel_shared`) | Core's own `:graph`/`:check` is hard-scoped to `NOTES_ROOT="notes"` and cannot see `music/`; the check must run inside the module's own test suite, but the *rule* it applies should be shared code, not a hand-copied drift risk |
| Obsidian vault persistence (actual note storage) | Database/Storage (Obsidian Local REST API) | — | Single external service both Core and every module talk to directly over HTTP; no local filesystem writes anywhere |

## Standard Stack

### Core
No new dependencies. Every library this phase touches is already pinned in the repo:

| Library | Version (verified in repo) | Purpose | Why Standard |
|---------|-----|---------|--------------|
| `httpx` | `>=0.28.1` (pf2e/shared pyproject.toml) | Async HTTP client underlying `ObsidianClientCore` | Already the house standard for every HTTP boundary (`Vault`, `ObsidianClient`, `SentinelCoreClient`) |
| `fastapi` | `>=0.135.0` | Music module's own ASGI app | Matches pf2e's pinned floor exactly — zero new stack surface |
| `uvicorn[standard]` | `>=0.44.0` | ASGI server for the music container | Matches pf2e |
| `pydantic-settings` | `>=2.13.0` — **confirmed installed: 2.13.1** `[VERIFIED: sentinel-core/.venv, python -c "import pydantic_settings; print(__version__)"]` | Music's `app/config.py`; also governs `SWEEP_SKIP_PREFIXES`/`PROTECTED_NAMESPACES` env parsing on the Core side | Already validated — `tuple[str, ...]` fields parse a JSON-array-shaped env string (empirically confirmed: `SWEEP_SKIP_PREFIXES='["a/","b/"]'` → `('a/', 'b/')`) `[VERIFIED: local repl against sentinel-core's actual Settings class]` |
| `pyyaml` | `>=6.0.0` | `_schema` block YAML parsing (already used by `note_schema.py`) | Same dialect vault-wide |

**Installation:** none — no `pip install` needed for this phase. `shared/pyproject.toml` already lists `httpx>=0.28.1` and `numpy>=1.26,<3.0`; the new `obsidian.py` module needs only `httpx`, already present. `[VERIFIED: read shared/pyproject.toml directly]`

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` / `pytest-asyncio` | pf2e: `pytest>=9.0.3`/`pytest-asyncio>=1.3.0` (dependency-groups); shared: `pytest>=8.0`/`pytest-asyncio>=0.23` | Regression suites for pf2e cutover (D-06) and the new `shared/tests/test_obsidian.py` + `modules/music/tests/` | Both already `asyncio_mode = "auto"` — no explicit `@pytest.mark.asyncio` needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Vendoring a tiny pure orphan-checker into `sentinel_shared` for MUS-05's self-check | Duplicate ~15 lines of `graph_analysis.py` logic directly inside `modules/music/` | Rejected: this is the EXACT XMOD-01 problem recurring one level down — a second copy that can drift the moment Core's orphan rule changes. Shared-now is cheaper than shared-later, same rationale as D-01 |
| Single `obsidian.py` file for core+mixins in `sentinel_shared` | `obsidian/` subpackage (`core.py`, `heading.py`, `binary.py`) | Rejected for this phase: `sentinel_shared` has zero subpackages today (`llm_call.py`, `similarity.py`, `embedding_codec.py`, `model_profiles.py` are all flat single files); introducing the first subpackage here breaks convention consistency for a ~230-line total surface that doesn't need it |

## Package Legitimacy Audit

**Not applicable — this phase installs zero new external packages.** All libraries used (`httpx`, `fastapi`, `uvicorn`, `pydantic-settings`, `pyyaml`, `pytest`, `pytest-asyncio`) are already present in `modules/pathfinder/pyproject.toml` and `shared/pyproject.toml`, verified by direct read. No `npm view` / `pip index versions` / package-legitimacy check is warranted since no new package name is being introduced anywhere in this phase's scope.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│ shared/sentinel_shared/obsidian.py  (NEW — this phase)                  │
│                                                                           │
│   ObsidianClientCore(http_client, base_url, api_key)                    │
│     ._safe_request()  .get_note()  .put_note()                          │
│     .list_directory()  .patch_frontmatter_field()                       │
│                                                                           │
│   ObsidianHeadingMixin  →  .patch_heading()                             │
│   ObsidianBinaryMixin   →  .put_binary()  .get_binary()                 │
└───────────────┬───────────────────────────────────┬─────────────────────┘
                │ imported at container BUILD time   │ imported at build time
                │ (Docker COPY --from=shared)         │
                ▼                                     ▼
┌───────────────────────────────────┐   ┌─────────────────────────────────┐
│ modules/pathfinder/app/obsidian.py │   │ modules/music/app/obsidian.py   │
│                                     │   │ (NEW)                           │
│ class ObsidianClient(              │   │ ObsidianClientCore only          │
│   ObsidianClientCore,               │   │ (no heading/binary mixin)       │
│   ObsidianBinaryMixin,               │   │                                  │
│   ObsidianHeadingMixin):             │   │                                  │
│   pass  # pure composition          │   │                                  │
└──────────────┬──────────────────────┘   └──────────────┬───────────────────┘
               │ HTTP (Obsidian Local REST API)           │ HTTP (same API)
               ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Obsidian Local REST API  (host.docker.internal:27123 / 27124)           │
│  reads/writes  mnemosyne/pf2e/...  |  music/lessons/ music/practice-log/│
│                                       music/ideas/  music/index.md      │
└─────────────────────────────────────────────────────────────────────────┘

Registration + proxy path (unchanged, reused verbatim):
┌──────────────────┐  POST /modules/register   ┌───────────────────────┐
│ music-module      │ ───────────────────────▶  │ sentinel-core          │
│ lifespan():        │  (5x backoff, 30s heartbeat)│ routes/modules.py     │
│  register+heartbeat│                            │ module_registry.py    │
└──────────────────┘                            └───────────────────────┘
```

### Recommended Project Structure
```
shared/sentinel_shared/
├── obsidian.py           # NEW: ObsidianClientCore + ObsidianHeadingMixin + ObsidianBinaryMixin
├── llm_call.py           # unchanged
├── similarity.py         # unchanged
├── embedding_codec.py    # unchanged
├── model_profiles.py     # unchanged
└── __init__.py           # unchanged

modules/music/             # NEW — mirrors modules/pathfinder/ exactly
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app + lifespan (register + heartbeat)
│   ├── config.py           # pydantic-settings: SENTINEL_CORE_URL, OBSIDIAN_BASE_URL, OBSIDIAN_API_KEY
│   └── obsidian.py         # thin ObsidianClientCore subclass/alias (Claude's discretion)
├── compose.yml              # profiles: ["music"], mirrors pathfinder/compose.yml
├── Dockerfile
├── pyproject.toml           # pythonpath = [".", "../../shared"]
└── tests/
    ├── __init__.py
    ├── conftest.py           # sys.path shim for ../../shared, matches pf2e's conftest.py
    ├── test_registration.py  # mirrors pf2e's test_registration.py structure
    ├── test_healthz.py
    └── test_music_vault_seed.py   # MUS-05 zero-orphan + _schema structural self-check
```

### Pattern 1: Composable core + mixins for the shared Obsidian client (D-01, D-02)

**What:** Split `modules/pathfinder/app/obsidian.py`'s single `ObsidianClient` class into a base class carrying shared HTTP plumbing + the four universally-common methods, plus two independently-composable mixins for the less-universal capabilities.

**When to use:** Any module that needs Obsidian REST access — pf2e recomposes all three; music composes only the core.

**Exact split (verified against the live 227-line file, line numbers from `modules/pathfinder/app/obsidian.py`):**

| Method / attribute | Current lines | New home |
|---|---|---|
| `__init__(self, http_client, base_url, api_key)` | 21–26 | `ObsidianClientCore.__init__` |
| `_safe_request(self, coro, default, operation, silent=False)` | 28–35 | `ObsidianClientCore._safe_request` |
| `get_note(self, path)` | 37–51 | `ObsidianClientCore.get_note` |
| `put_note(self, path, content)` | 53–67 | `ObsidianClientCore.put_note` (120s timeout preserved verbatim per D-04) |
| `list_directory(self, prefix, *, _depth=0, _max_depth=8)` | 104–173 | `ObsidianClientCore.list_directory` (recursion/depth guard preserved verbatim) |
| `patch_frontmatter_field(self, path, field, value)` | 206–226 | `ObsidianClientCore.patch_frontmatter_field` |
| `put_binary(self, path, data, content_type)` | 69–82 | `ObsidianBinaryMixin.put_binary` |
| `get_binary(self, path)` | 84–102 | `ObsidianBinaryMixin.get_binary` |
| `patch_heading(self, path, heading, content, operation="append")` | 175–204 | `ObsidianHeadingMixin.patch_heading` |

**Class skeletons (exact code to write into `shared/sentinel_shared/obsidian.py`):**
```python
"""Obsidian Local REST API client — composable core + mixins (Phase 48, XMOD-01).

Promoted from modules/pathfinder/app/obsidian.py. ObsidianClientCore carries the
HTTP plumbing and the four universally-shared methods (get_note, put_note,
list_directory, patch_frontmatter_field). ObsidianHeadingMixin and
ObsidianBinaryMixin add capabilities only some modules need. Compose per module:

    class ObsidianClient(ObsidianClientCore, ObsidianBinaryMixin, ObsidianHeadingMixin):
        pass  # pf2e — needs all three

    class ObsidianClient(ObsidianClientCore):
        pass  # music — core only, per D-03/MUS-02

All request semantics (timeouts, recursion guard, content-type handling) are
copied VERBATIM from the pf2e original — this is a behavior-preserving lift,
not a redesign (D-04).
"""
import json
import logging

import httpx

logger = logging.getLogger(__name__)


class ObsidianClientCore:
    """HTTP plumbing + the four methods every module needs."""

    def __init__(self, http_client: httpx.AsyncClient, base_url: str, api_key: str) -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")
        self._headers: dict[str, str] = (
            {"Authorization": f"Bearer {api_key}"} if api_key else {}
        )

    async def _safe_request(self, coro, default, operation: str, silent: bool = False):
        try:
            return await coro
        except Exception as exc:
            if not silent:
                logger.warning("%s failed: %s", operation, exc)
            return default

    async def get_note(self, path: str) -> str | None:
        # ... verbatim body from modules/pathfinder/app/obsidian.py:37-51
        ...

    async def put_note(self, path: str, content: str) -> None:
        # ... verbatim body, 120s timeout preserved, from :53-67
        ...

    async def list_directory(self, prefix: str, *, _depth: int = 0, _max_depth: int = 8) -> list[str]:
        # ... verbatim body from :104-173, including the depth-8 recursion guard
        ...

    async def patch_frontmatter_field(self, path: str, field: str, value) -> None:
        # ... verbatim body from :206-226
        ...


class ObsidianHeadingMixin:
    """patch_heading — used by pf2e today; Music/Finance may adopt later."""

    async def patch_heading(self, path: str, heading: str, content: str, operation: str = "append") -> None:
        # ... verbatim body from :175-204
        ...


class ObsidianBinaryMixin:
    """put_binary / get_binary — pf2e-only today (token images), kept composable
    so no future media module has to copy pf2e."""

    async def put_binary(self, path: str, data: bytes, content_type: str) -> None:
        # ... verbatim body from :69-82
        ...

    async def get_binary(self, path: str) -> bytes | None:
        # ... verbatim body from :84-102
        ...
```

pf2e's new `modules/pathfinder/app/obsidian.py` (post-cutover) becomes exactly:
```python
"""pf2e's ObsidianClient — pure composition of the shared core + mixins (D-02).

No client logic lives here. All request semantics come from sentinel_shared.obsidian.
"""
from sentinel_shared.obsidian import (
    ObsidianBinaryMixin,
    ObsidianClientCore,
    ObsidianHeadingMixin,
)


class ObsidianClient(ObsidianClientCore, ObsidianBinaryMixin, ObsidianHeadingMixin):
    """pf2e needs the full surface: core methods + patch_heading + binary I/O."""
    pass
```

Music's `modules/music/app/obsidian.py` (Claude's discretion resolved — recommend a thin subclass, not a bare re-export, so future mixins can be added without touching call sites):
```python
"""Music module's ObsidianClient — core-only composition (D-03, MUS-02).

Music never imports Core's Vault Protocol; it never needs patch_heading or
binary I/O today (no roadmapped binary storage — see Deferred Ideas).
"""
from sentinel_shared.obsidian import ObsidianClientCore


class ObsidianClient(ObsidianClientCore):
    pass
```

`shared/pyproject.toml` needs **no new dependencies** — `httpx>=0.28.1` is already declared `[VERIFIED: read shared/pyproject.toml directly]`.

### Pattern 2: pf2e cutover — exact coupling sites (D-05, D-06)

**Two real coupling sites**, confirmed by direct read:

1. **`modules/pathfinder/app/main.py`**
   - Line 57: `from app.obsidian import ObsidianClient` — stays the same import path (pf2e's `app/obsidian.py` still exports `ObsidianClient`, now as a composition subclass) — **no change needed here** as long as pf2e's own `app/obsidian.py` is rewritten per Pattern 1 above. This is the key insight: D-05's "rewrite the import + instantiation" is really "rewrite what `app/obsidian.py` contains," not "change the main.py import line."
   - Line 203 (`lifespan()`): `obsidian_client = ObsidianClient(http_client=obsidian_http_client, base_url=settings.obsidian_base_url, api_key=settings.obsidian_api_key)` — constructor signature is unchanged (`ObsidianClientCore.__init__` has the identical signature), so **this call site needs zero changes** either, provided the composition subclass's MRO resolves `__init__` to `ObsidianClientCore.__init__` (guaranteed — none of the mixins define `__init__`).
   - **Net effect:** `main.py` requires ZERO line changes. The entire cutover is contained in `app/obsidian.py` itself. This is a stronger and simpler outcome than D-05's framing implies — worth flagging explicitly to the planner so a task isn't wasted "rewriting main.py" when the real work is deleting 200 lines from `obsidian.py` and replacing them with the composition subclass shown above.

2. **`modules/pathfinder/tests/test_aliases_path_probe.py:28`**
   - `from app.obsidian import ObsidianClient` then `ObsidianClient(http_client, BASE_URL, API_KEY)` (see `_make_client` helper, lines 36-40). Same reasoning: since `app.obsidian.ObsidianClient` remains importable from the same path with the same constructor, this test file needs **zero changes** either — it was already testing through the public `ObsidianClient` name, not an internal implementation detail. `[VERIFIED: read modules/pathfinder/tests/test_aliases_path_probe.py in full]`

**Implication for the planner:** D-05's file list is correct about WHERE the risk lives, but the actual code diff is smaller than "rewrite main.py + test file" — it's "replace `app/obsidian.py`'s body, leave every consumer import untouched." Still verify both files unchanged after the cutover (that's the regression guard, D-06) — but don't plan wasted edit-tasks against files that don't need to change.

**~10 duck-typed consumers** (untyped `obsidian_client` param) — confirmed via architecture pattern (routes/npc.py, routes/harvest.py, routes/rule.py, routes/session.py, routes/foundry.py, routes/npcs.py, routes/player.py, routes/ingest.py wire `_module.obsidian = obsidian_client` in `main.py`'s lifespan, lines 209-280). None of these import `ObsidianClient` directly — they receive the instance via module-level singleton assignment — so **zero changes** needed, consistent with D-05.

**7 local `FakeObsidian` doubles** — structurally decoupled test doubles (duck-typed fakes, not subclasses of the real client) — stay put unchanged, per D-05.

**Regression-guard command (D-06):**
```bash
cd modules/pathfinder && .venv/bin/python -m pytest -q
# 405 tests collected as of this research (2026-07-08) — must remain fully green.
# Highest-risk files to watch: tests/test_aliases_path_probe.py, tests/test_registration.py,
# tests/test_main.py (lifespan wiring), and any test using FakeObsidian doubles
# (grep -rl "FakeObsidian" modules/pathfinder/tests/).
```
`[VERIFIED: ran modules/pathfinder/.venv/bin/python -m pytest --collect-only -q — 405 tests collected]`

### Pattern 3: Music module scaffold (MUS-01, D-11, D-12)

**Every file to create**, mirroring `modules/pathfinder/`'s skeleton:

| File | Mirrors | Notes |
|---|---|---|
| `modules/music/app/__init__.py` | `modules/pathfinder/app/__init__.py` | empty |
| `modules/music/app/main.py` | `modules/pathfinder/app/main.py` | FastAPI app + `lifespan()` — registration + heartbeat only (no NPC/harvest/rules wiring); `healthz` route |
| `modules/music/app/config.py` | `modules/pathfinder/app/config.py` | `sentinel_core_url`, `sentinel_api_key` (required), `obsidian_base_url`, `obsidian_api_key` — trim everything pf2e-specific (litellm_api_base, session settings, discord_bot_internal_url) since none apply yet |
| `modules/music/app/obsidian.py` | `modules/pathfinder/app/obsidian.py` (post-cutover) | thin `ObsidianClientCore`-only subclass, see Pattern 1 |
| `modules/music/compose.yml` | `modules/pathfinder/compose.yml` | `profiles: ["music"]`, service name `music-module`, `additional_contexts: {shared: ../../shared}` |
| `modules/music/Dockerfile` | `modules/pathfinder/Dockerfile` | trim pf2e-only apt packages (`libleveldb-dev`, `plyvel` — pf2e-specific, music needs neither); keep the two `COPY --from=shared` lines |
| `modules/music/pyproject.toml` | `modules/pathfinder/pyproject.toml` | `name = "music-module"`, deps trimmed to `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic-settings`, `pyyaml` (STACK.md's recommendation — no `litellm`/`rapidfuzz`/`reportlab`/`beautifulsoup4`/`numpy`/`pillow` needed for scaffold-only scope); `pythonpath = [".", "../../shared"]` |
| `modules/music/tests/__init__.py` | pf2e's | empty |
| `modules/music/tests/conftest.py` | `modules/pathfinder/tests/conftest.py` | sys.path shim inserting `../../shared`; `os.environ.setdefault` for `SENTINEL_API_KEY`, `SENTINEL_CORE_URL`, `OBSIDIAN_BASE_URL`, `OBSIDIAN_API_KEY` |
| `modules/music/tests/test_registration.py` | `modules/pathfinder/tests/test_registration.py` | same 4-test shape: succeeds-first-attempt, retries-on-failure, exits-after-5-failures, payload-correct |
| `modules/music/tests/test_healthz.py` | `modules/pathfinder/tests/test_healthz.py` | trivial `GET /healthz` → `{"status": "ok", "module": "music"}` |
| `modules/music/tests/test_music_vault_seed.py` | new (no pf2e equivalent) | MUS-05 zero-orphan + `_schema` structural check — see Pattern 4 |

**Registration payload template (extracted verbatim shape from pf2e's `main.py:80-114`, trimmed to Phase-48 scope per D-12):**
```python
REGISTRATION_PAYLOAD = {
    "name": "music",
    "base_url": "http://music-module:8000",
    "routes": [
        {"path": "healthz", "description": "music module health check"},
    ],
}
```

**Backoff + heartbeat (copy verbatim from `modules/pathfinder/app/main.py:117-161`, only the payload/module name differ):**
```python
async def _register_with_retry(client: httpx.AsyncClient) -> None:
    """5 attempts, exponential backoff 1s->2s->4s->8s->16s. SystemExit(1) on
    total failure so Docker restart policy can recover."""
    delays = [1, 2, 4, 8, 16]
    for attempt, delay in enumerate(delays, start=1):
        try:
            resp = await client.post(
                f"{settings.sentinel_core_url}/modules/register",
                json=REGISTRATION_PAYLOAD,
                headers={"X-Sentinel-Key": os.environ.get("SENTINEL_API_KEY", "")},
                timeout=10.0,
            )
            resp.raise_for_status()
            return
        except Exception:
            if attempt < len(delays):
                await asyncio.sleep(delay)
    raise SystemExit(1)


async def _registration_heartbeat() -> None:
    """Re-register every 30s so a Core restart self-heals."""
    while True:
        await asyncio.sleep(30)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.sentinel_core_url}/modules/register",
                    json=REGISTRATION_PAYLOAD,
                    headers={"X-Sentinel-Key": os.environ.get("SENTINEL_API_KEY", "")},
                    timeout=10.0,
                )
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Heartbeat: re-registration failed: %s", exc)
```

**Naming conventions (D-11/D-12, mirrored from pf2e's D-11/D-12 precedent):** module registry name `"music"` (matches Docker profile name this time — unlike pf2e's `"pathfinder"`/`"pf2e"` split, there is no reason to diverge names for a brand-new module; recommend keeping profile=`music`, registry name=`music`, service name=`music-module`, `base_url="http://music-module:8000"` for simplicity, since the pf2e split existed only because pf2e's Docker service predates its logical rename).

**compose.yml (exact template, mirrors `modules/pathfinder/compose.yml` structure):**
```yaml
# modules/music/compose.yml
services:
  music-module:
    build:
      context: .
      dockerfile: Dockerfile
      additional_contexts:
        shared: ../../shared
    profiles:
      - music
    env_file:
      - ../../.env
    secrets:
      - sentinel_api_key
    environment:
      - SENTINEL_CORE_URL=http://sentinel-core:8000
    depends_on:
      sentinel-core:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 30s

secrets:
  sentinel_api_key:
    file: ../../secrets/sentinel_api_key
```

Add one line to the root `docker-compose.yml`'s `include:` block (this is the ONLY root-level file this phase touches, and it's additive, not a Core code change — `include:` wiring is compose-level, not app code):
```yaml
include:
  - path: sentinel-core/compose.yml
  - path: interfaces/discord/compose.yml
  - path: security/pentest-agent/compose.yml
  - path: modules/pathfinder/compose.yml
  - path: modules/music/compose.yml   # NEW — profiles: [music] inside — activate with --profile music up
```
`[VERIFIED: read docker-compose.yml directly — confirmed include: pattern and comment convention "Future modules: add include entries here"]`

### Pattern 4: First `music/` write + zero-orphan self-check (MUS-02, MUS-05, D-08, D-09, D-10)

**The core problem:** the music container cannot `import sentinel-core` at runtime (separate Docker process/image, no shared Python runtime — this is the same isolation invariant that makes MUS-02 forbid importing the `Vault` Protocol). But MUS-05's zero-orphan proof needs the EXACT rule `sentinel-core/app/services/graph_analysis.py`'s `build_graph_report`/`resolve_wikilink`/`extract_wikilinks` implement — a hand-copied reimplementation is exactly the kind of drift risk XMOD-01 already identifies for the Obsidian client.

**Recommendation: vendor a tiny pure orphan-checker into `sentinel_shared` (option (a) from the brief), not a hand-copy inside the music module.**

Rationale: `graph_analysis.py` is explicitly documented as "pure computation... performs NO vault I/O of its own" (`[VERIFIED: read sentinel-core/app/services/graph_analysis.py header docstring]`) — it is already shaped as a portable, dependency-free function (`extract_wikilinks`, `_slugify`, `resolve_wikilink`, `build_graph_report`, all pure `re`/string operations, zero imports beyond `re`/`dataclasses`/`typing`). Copying ~70 lines of pure computation into `shared/sentinel_shared/graph_check.py` is a one-time move that then serves BOTH Core (which could import it from `sentinel_shared` too, though that's out of scope for this phase and not required by any locked decision) and the music module's own test — with a single source of truth instead of two independently-maintained copies of the same orphan rule. This is the SAME pattern this repo already used for `cosine_similarity` (`shared/sentinel_shared/similarity.py`'s own docstring: "Closes the cross-package SPOT violation between sentinel-core's `vault_sweeper.cosine_similarity`... and pathfinder's `rules.cosine_similarity`") `[VERIFIED: read shared/sentinel_shared/similarity.py header]` — i.e. this project has an established precedent for exactly this move when the same pure logic exists (or is about to exist) in two places.

**Scope discipline:** this vendoring does NOT require Core to import from `sentinel_shared` in this phase (D-10 says "Do not extend Core's `NOTES_ROOT` walk" and MUS-01 says "zero Core code changes" — vendoring a copy into `sentinel_shared` that Core doesn't yet consume satisfies both; a FUTURE phase extending Core's own `:graph`/`:check` to also import from `sentinel_shared` instead of its local `graph_analysis.py` is an optional follow-on refactor, not required here).

**Vendored module — `shared/sentinel_shared/graph_check.py` (pure copy of the verified rule, no Core import):**
```python
"""Pure wikilink-orphan check, vendored from sentinel-core's graph_analysis.py
(Phase 48, MUS-05). Modules cannot import sentinel-core at runtime (separate
container/process) — this lets any module prove its own zero-orphan compliance
against the SAME rule Core's :graph/:check uses, instead of hand-copying it
into module-local test code where it can silently drift.

orphan <=> not outlinks[path] and not backlinks[path]. Links resolve only to
paths that exist in the given notes map (see resolve_wikilink) — a hub
pointing at not-yet-written notes self-flags as an orphan, same as Core's rule.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

_MD_EXT = ".md"
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


def extract_wikilinks(body: str) -> set[str]:
    return {m.group(1).strip() for m in _WIKILINK_RE.finditer(body or "")}


def _slugify(text: str) -> str:
    return (text or "").strip().lower().replace(" ", "-").replace("_", "-")


def resolve_wikilink(target: str, note_paths: Iterable[str]) -> str | None:
    target_slug = _slugify(target)
    for path in note_paths:
        stem = path.rsplit("/", 1)[-1]
        if stem.endswith(_MD_EXT):
            stem = stem[: -len(_MD_EXT)]
        if _slugify(stem) == target_slug:
            return path
    return None


@dataclass
class GraphReport:
    note_count: int = 0
    orphans: list[str] = field(default_factory=list)
    backlinks: dict[str, list[str]] = field(default_factory=dict)
    link_density: float = 0.0


def build_graph_report(notes: dict[str, str]) -> GraphReport:
    """Identical algorithm to sentinel-core's build_graph_report, minus the
    hub_count parameter (Core-only concept not needed for a module self-check)."""
    note_paths = list(notes.keys())
    outlinks: dict[str, set[str]] = {}
    backlinks: dict[str, list[str]] = {path: [] for path in notes}

    for path, body in notes.items():
        resolved: set[str] = set()
        for target in extract_wikilinks(body):
            resolved_path = resolve_wikilink(target, note_paths)
            if resolved_path is not None and resolved_path != path:
                resolved.add(resolved_path)
        outlinks[path] = resolved

    for src, targets in outlinks.items():
        for target_path in targets:
            backlinks[target_path].append(src)

    orphans = [path for path in notes if not outlinks[path] and not backlinks[path]]
    total_edges = sum(len(v) for v in outlinks.values())
    note_count = len(notes)

    return GraphReport(
        note_count=note_count,
        orphans=orphans,
        backlinks=backlinks,
        link_density=(total_edges / note_count) if note_count else 0.0,
    )
```

**Exact hub-mesh note contents (D-08) — provably zero-orphan under the rule above** (4 notes, each linking to at least one other, each resolved by filename-stem match):

`music/index.md`:
```markdown
---
type: module-hub
title: Music Module Index
---

# Music Module Index

Top-level hub for the Music Lesson Tracker module's vault namespace.

- [[music/lessons/index]] — lesson records
- [[music/practice-log/index]] — practice session log
- [[music/ideas/index]] — chord/melody idea capture

```_schema
title: "Music Module Index"
wikilinks: ["music/lessons/index", "music/practice-log/index", "music/ideas/index"]
listenbrainz_context: null
discogs_context: null
```
```

`music/lessons/index.md`:
```markdown
---
type: module-hub
title: Music Lessons Index
---

# Music Lessons Index

Lesson records for the Music module. See [[music/index]] for the module root.

```_schema
title: "Music Lessons Index"
wikilinks: ["music/index"]
listenbrainz_context: null
discogs_context: null
```
```

`music/practice-log/index.md`:
```markdown
---
type: module-hub
title: Practice Log Index
---

# Practice Log Index

Practice session records for the Music module. See [[music/index]] for the module root.

```_schema
title: "Practice Log Index"
wikilinks: ["music/index"]
listenbrainz_context: null
discogs_context: null
```
```

`music/ideas/index.md`:
```markdown
---
type: module-hub
title: Music Ideas Index
---

# Music Ideas Index

Chord/melody idea captures for the Music module. See [[music/index]] for the module root.

```_schema
title: "Music Ideas Index"
wikilinks: ["music/index"]
listenbrainz_context: null
discogs_context: null
```
```

**Why this is provably zero-orphan:** `music/index.md` has 3 outlinks (all resolve, since the other 3 files exist in the same write batch) and 3 backlinks (each subfolder hub links back to it) → not an orphan. Each subfolder hub has 1 outlink to `music/index` (resolves) and 1 backlink from `music/index` (resolves) → not an orphan. Apply `build_graph_report({path: body for the 4 notes above})` → `orphans == []`. This matches D-08's requirement exactly ("mutually wikilinked... provably zero-orphan").

**Module-side test (`modules/music/tests/test_music_vault_seed.py`) — asserts structurally, no live Obsidian, no Core import:**
```python
from sentinel_shared.graph_check import build_graph_report
from sentinel_shared.obsidian import ObsidianClientCore  # only if reading via a live probe; omit for pure structural test

HUB_NOTES = {
    "music/index.md": "...",             # exact bodies from Pattern 4 above
    "music/lessons/index.md": "...",
    "music/practice-log/index.md": "...",
    "music/ideas/index.md": "...",
}

def test_hub_mesh_has_zero_orphans():
    report = build_graph_report(HUB_NOTES)
    assert report.orphans == []

def test_every_hub_has_schema_block_and_wikilinks():
    from sentinel_shared.graph_check import extract_wikilinks
    for path, body in HUB_NOTES.items():
        assert "```_schema" in body, f"{path} missing trailing _schema block"
        assert extract_wikilinks(body), f"{path} has no resolvable wikilink"
```

### Anti-Patterns to Avoid
- **Hand-copying the orphan rule into `modules/music/` test code:** creates a second independently-drifting copy of the exact logic XMOD-01 already flags as a duplication risk one layer up — vendor into `sentinel_shared` instead (Pattern 4).
- **Extending `NOTES_ROOT` or Core's `links_sidecar_index.walk_vault()` to include `music/`:** explicitly forbidden by D-10/MUS-01 ("zero Core code changes"). Full Core-side `:graph`/`:check` participation for `music/` is deferred to a future phase.
- **Rewriting `main.py`'s import or `lifespan()` instantiation line as if the constructor signature changed:** it didn't (Pattern 2) — the actual work is entirely inside `app/obsidian.py`.
- **Copying pf2e's full `pyproject.toml` dependency list into `modules/music/pyproject.toml`:** pf2e's `litellm`, `rapidfuzz`, `reportlab`, `beautifulsoup4`, `numpy`, `pillow` are NPC/rules/PDF-specific and unused by the Phase-48 scaffold — bloats the music image and the Dockerfile's `apt-get` list (`libleveldb-dev` for `plyvel` is pf2e-only too).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Module registration + Core proxy | A second registration mechanism | `POST /modules/register` + `module_registry.py`/`module_gateway.py` (already built, zero Core changes needed) `[VERIFIED: read sentinel-core/app/routes/modules.py, module_registry.py]` | This is documented as "the only registration seam in the codebase" — a second mechanism would fork an already-generic, already-proven pattern |
| Zero-orphan wikilink-graph computation | A bespoke music-module orphan checker | Vendor `graph_analysis.build_graph_report`'s exact algorithm into `sentinel_shared` (Pattern 4) | Prevents the exact drift risk this phase already exists to eliminate for the Obsidian client (XMOD-01) — don't reintroduce the same anti-pattern for a second concern |
| Env-var override values for `SWEEP_SKIP_PREFIXES`/`PROTECTED_NAMESPACES` | A hand-typed JSON literal in `.env` | Generate the value from Core's committed default tuples (see §5 below) | D-13 explicitly warns a hand-copied literal is "a live footgun that silently un-protects `pf2e/`/`security/` on the next edit" |

**Key insight:** this phase's dominant theme is "don't create a second copy of logic that already exists once — either promote it to shared code (Obsidian client, orphan checker) or generate it from its single source of truth (sweeper env overrides)." Every one of the four locked-decision groups (D-01/02, D-08/09/10, D-13/14) is the same anti-duplication principle applied to a different artifact.

## Runtime State Inventory

Not applicable — this phase is additive scaffold + refactor-in-place, not a rename/refactor/migration of existing runtime state. pf2e's cutover (D-05/D-06) changes *where* client logic lives, not any existing stored data, keys, IDs, or registered OS/service state. Confirmed by direct inspection:

| Category | Finding |
|----------|---------|
| Stored data | None — no existing `music/` data exists yet (first write in this phase); pf2e's existing vault content (`mnemosyne/pf2e/...`) is untouched — only the *client code* that writes it moves, not the data itself |
| Live service config | None — no n8n/Datadog/Tailscale-style external service config references `ObsidianClient` by name; the Docker Compose `include:` addition is the only config-surface change and is purely additive |
| OS-registered state | None — no Task Scheduler/pm2/launchd/systemd entries reference pf2e's `obsidian.py` internals |
| Secrets/env vars | `SENTINEL_API_KEY` (Docker secret, unchanged), `OBSIDIAN_API_KEY`/`OBSIDIAN_BASE_URL` (env, unchanged) — the music module reuses the SAME root `.env`/secrets, no new secret names introduced this phase |
| Build artifacts | pf2e's `.venv`/`uv.lock` will need a dependency-group refresh only if `sentinel_shared`'s `obsidian.py` addition changes what pf2e imports at runtime (it imports `sentinel_shared.obsidian`, already on `pythonpath` — no new pip package, so `uv.lock` likely doesn't need regeneration, but confirm the pf2e test run — Pattern 2's regression guard — surfaces no import errors) |

## Common Pitfalls

### Pitfall A: `/music/` isn't in the sweeper's skip-prefix denylist by default `[CITED: .planning/research/PITFALLS.md Pitfall 1]`
**What goes wrong:** The vault sweeper walks the entire vault on every sweep and (non-destructively) relocates unrecognized content to `_trash/{date}/`. Without a `music/` skip-prefix entry, the first scheduled sweep after the first `music/` write relocates the brand-new hub-mesh notes.
**Why it happens:** The skip-prefix list is hand-maintained in `sentinel-core/app/config.py`, not auto-derived from `POST /modules/register` — there is no mechanism today by which a module announces "this subtree is mine."
**How to avoid:** Land the `music/` skip-prefix (and `PROTECTED_NAMESPACES`) env override in the SAME commit as the first `music/index.md` write — this is D-13's explicit requirement, not optional sequencing.
**Warning signs:** A `:vault-sweep` run reports moves for `music/` paths; a note that existed yesterday is missing today (check `_trash/`).

### Pitfall B: hand-copying Core's default tuples into the env override risks silent regression `[VERIFIED: sentinel-core/app/config.py lines 137-183, cross-checked against sentinel-core/app/vault.py's PROTECTED_NAMESPACES literal]`
**What goes wrong:** `SWEEP_SKIP_PREFIXES`/`PROTECTED_NAMESPACES` are pydantic-settings fields with **REPLACE semantics** — setting the env var doesn't append, it OVERWRITES the whole tuple. A hand-typed `.env` literal that's correct today silently drops `pf2e/`/`security/`/etc. protection the next time someone edits Core's Python-side defaults without also updating the `.env` literal.
**Why it happens:** Two independent files (`sentinel-core/app/config.py`'s Python literal, and the deploy `.env`'s JSON-string literal) have to stay byte-for-byte in sync forever, with nothing enforcing it.
**How to avoid:** Generate the env value programmatically rather than hand-typing it. Two viable mechanisms (Claude's discretion, D-13):
  1. **Deploy-time script** (recommended — simplest, no new build-time coupling): a small Python one-liner run at deploy time that imports `sentinel-core`'s `Settings` class defaults directly and prints the JSON-encoded tuple-plus-`"music/"`, piped into the deploy `.env`:
     ```bash
     # run from the deploy checkout, sentinel-core/ on PYTHONPATH
     python3 -c "
     import json, sys
     sys.path.insert(0, 'sentinel-core')
     from app.config import Settings
     defaults = Settings.model_fields['sweep_skip_prefixes'].default
     print(json.dumps(list(defaults) + ['music/']))
     "
     ```
     This must be re-run (or a checked test asserts it stays current) any time `sentinel-core/app/config.py`'s defaults change.
  2. **Compose templating** (alternative, more moving parts): a Jinja/envsubst-rendered `.env` fragment — rejected as the primary recommendation since it introduces a new templating dependency this repo doesn't otherwise use; the deploy-time Python script reuses only what's already installed.
- Recommend option 1. Whichever mechanism is chosen, add a **CI-adjacent check** (or at minimum a checked-in comment + a `test_env_override_matches_core_defaults_plus_music` unit test on the Core side, run in `sentinel-core`'s own suite) asserting that `json.loads(os.environ["SWEEP_SKIP_PREFIXES"])` (as it would land in the deploy `.env`) equals `list(Settings.model_fields["sweep_skip_prefixes"].default) + ["music/"]` — this converts "silent footgun" into "test fails loudly when someone edits one side and not the other."
**Warning signs:** A future Core config edit (e.g. adding a 12th skip-prefix for a new module) doesn't trigger any corresponding `.env` update, and nobody notices until content under the newly-added-but-forgotten prefix gets swept.

### Pitfall C: assuming `main.py` needs an import/instantiation rewrite for the pf2e cutover (this phase's own scope-estimation risk)
**What goes wrong:** Following D-05's literal wording ("rewrite the import + instantiation... in `main.py`") could lead to planning an edit task against `main.py:57` and `:203` that turns out to be a no-op, because the constructor signature and import path are both preserved by the composition-subclass design (Pattern 2).
**Why it happens:** D-05 was written before the exact mixin/composition shape was nailed down at research time; the CONTEXT.md decision correctly identifies the RISK surface (these two files must still pass their tests) but slightly over-specifies the MECHANISM (an actual line-level rewrite).
**How to avoid:** Plan the pf2e cutover as "delete `app/obsidian.py`'s ~200 lines of client logic, replace with the composition subclass" + "run the full test suite to CONFIRM `main.py`/`test_aliases_path_probe.py` still pass unmodified" — not as two separate edit tasks against files that don't need edits. If MRO resolution surprises occur (it shouldn't — no mixin defines `__init__`), THEN `main.py` needs a real change; treat "no diff needed" as the expected, verified-by-test outcome, not an assumption to skip verifying.
**Warning signs:** Test suite fails after the `obsidian.py` rewrite with an unexpected `TypeError` on `ObsidianClient(...)` construction — would indicate an MRO/`__init__` conflict the class skeletons above don't anticipate; re-check mixin base-class ordering (`ObsidianClientCore` must come first in the MRO for `__init__` to resolve there without `super().__init__()` calls being required elsewhere).

### Pitfall D: sweeper skip-prefix segment-boundary matching is `startswith`, not path-prefix-safe by default `[VERIFIED: sentinel-core/app/services/vault_sweeper.py:180-183, sentinel-core/app/vault.py:87-101]`
**What goes wrong:** `_should_skip` uses `path.startswith(p)` directly (no segment-boundary guard) for `sweep_skip_prefixes`, while `is_protected_path` DOES use segment-boundary matching (`normalised == bare or normalised.startswith(prefix)` where `prefix` always ends in `/`). A skip-prefix value without a trailing slash (e.g. `"music"` instead of `"music/"`) would also match an unrelated `musicology/` note — a subtle near-miss bug.
**Why it happens:** The two mechanisms (`sweep_skip_prefixes` vs `protected_namespaces`) were built at different times with slightly different rigor; `is_protected_path`'s docstring explicitly documents guarding against "near-misses like `notessentinel/x.md` matching `sentinel/`" but `_should_skip`'s prefix check has no equivalent comment/guard.
**How to avoid:** Always use the trailing-slash form `"music/"` (matching every existing entry in both tuples) — never a bare `"music"`. This is what D-13's exact literal already specifies; just don't "simplify" it during implementation.
**Warning signs:** A future note under an unrelated path sharing the same first 6 characters as `"music"` mysteriously gets skip-treated too.

### Pitfall E: pf2e's own skip-prefix already had a documented path-mismatch gap (now fixed — verify it stays fixed) `[CITED: .planning/research/ARCHITECTURE.md "Verify at implementation time, do not assume" section]`
**What goes wrong:** Prior research flagged that `sweep_skip_prefixes`'s bare `"pf2e/"` entry does NOT match pf2e's actual write paths (`mnemosyne/pf2e/npcs/...`), because `path.startswith("pf2e/")` is false for a path starting `mnemosyne/pf2e/...`.
**Current status:** Already resolved in the live code — `sentinel-core/app/config.py`'s `sweep_skip_prefixes` tuple contains BOTH `"pf2e/"` (kept "for defense-in-depth," per its inline comment) AND `"mnemosyne/"` (which correctly covers `mnemosyne/pf2e/...` by prefix) `[VERIFIED: read sentinel-core/app/config.py lines 137-154 directly]`. No action needed for Phase 48 — flagged here only so the planner doesn't rediscover this as a "new" bug; it's prior-phase debt that's already closed.
**Relevance to this phase:** confirms the correct mental model for `music/`'s own skip-prefix — since Music writes DIRECTLY to `music/lessons/`, `music/practice-log/`, `music/ideas/` (no `mnemosyne/`-style nesting per D-07), a single `"music/"` entry is sufficient and needs no `mnemosyne/`-style redundant second entry.

## Code Examples

### Registration retry test pattern (mirror for `modules/music/tests/test_registration.py`)
```python
# Source: modules/pathfinder/tests/test_registration.py (verified, 142 lines, 5 tests)
import os
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")

import httpx, pytest
from unittest.mock import AsyncMock, MagicMock, patch

async def test_registration_succeeds_on_first_attempt():
    from app.main import REGISTRATION_PAYLOAD, _register_with_retry
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await _register_with_retry(mock_client)
    mock_client.post.assert_called_once()
    assert mock_client.post.call_args.kwargs["json"] == REGISTRATION_PAYLOAD
    mock_sleep.assert_not_called()
```

### httpx.MockTransport pattern for testing `ObsidianClientCore` without a live vault (mirror for `shared/tests/test_obsidian.py`)
```python
# Source: modules/pathfinder/tests/test_aliases_path_probe.py (verified, 132 lines)
import httpx

def _make_client(handler, ClientClass, base_url="https://obsidian.test:27124", api_key="test-key"):
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return ClientClass(http_client, base_url, api_key), http_client

# handler captures requests for assertion; verifies exact URL path + headers round-trip.
```

## State of the Art

| Old Approach (before this phase) | Current Approach (after this phase) | When Changed | Impact |
|--------------------------------|--------------------------------------|---------------|--------|
| Each module (currently just pf2e) hand-rolls its own `ObsidianClient` copy | `ObsidianClientCore` + mixins live once in `shared/sentinel_shared`, every module composes from it | This phase | Eliminates the exact duplication-before-it-accumulates risk the 6-module PRD identified; music is the FIRST module to consume the shared client from day one instead of copying |
| Core's `graph_analysis.build_graph_report` is the only implementation of the orphan rule | A pure vendored copy lives in `sentinel_shared.graph_check`, importable by any module container that can't reach Core's Python code | This phase | Lets module-side tests prove MUS-05-style compliance without either duplicating logic ad hoc or requiring a cross-container import that isn't possible |

**Deprecated/outdated:** none — this phase deprecates no public interface. pf2e's OLD `app/obsidian.py` (227 lines of client logic) is deleted and replaced by a 6-line composition subclass; this is an internal refactor with no external API change (pf2e's `ObsidianClient` remains importable from the same module path with the same constructor signature).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The deploy-time Python script mechanism (Pitfall B, option 1) is the right generation mechanism for the `SWEEP_SKIP_PREFIXES`/`PROTECTED_NAMESPACES` env override — this is explicitly Claude's discretion per CONTEXT.md, not a locked decision | Pitfall B, §5 | Low — CONTEXT.md explicitly delegates this choice; if the planner/user prefers compose templating instead, the alternative is documented as a fallback in the same section, not a hard blocker |
| A2 | Module registry name `"music"` and Docker service name `"music-module"` should be the SAME logical concept (no pf2e-style profile/registry-name split) | §3 Pattern 3 | Low — this is a naming convenience recommendation, not a functional requirement; either naming scheme works with the generic proxy since `base_url` is independent of the registry `name` field |
| A3 | `modules/music/pyproject.toml` should trim pf2e's NPC/rules-specific dependencies (`litellm`, `rapidfuzz`, `reportlab`, `beautifulsoup4`, `numpy`, `pillow`, `plyvel`) rather than copy them wholesale | §3 Pattern 3 | Low — if a later phase (49+) needs one of these (e.g. `litellm` for the routine builder), it's a one-line addition then; starting minimal avoids an unused, unexplained dependency surface in Phase 48's scope |

**If this table is empty:** N/A — see entries above; all are LOW risk and explicitly scoped as discretion, not disputed facts.

## Open Questions

1. **Should `sentinel-core` itself eventually import `sentinel_shared.graph_check` to de-duplicate its own `graph_analysis.py`?**
   - What we know: the vendored copy in Pattern 4 is a byte-for-byte-equivalent pure function; Core's `graph_analysis.py` explicitly states it's pure computation with no I/O.
   - What's unclear: whether a future phase should retrofit Core to import from `sentinel_shared` (eliminating the two-copies-of-the-same-function state this phase creates) or whether Core's copy should simply be left alone indefinitely since it's Core-internal and not itself a duplication BETWEEN modules (only between Core and one module).
   - Recommendation: leave Core's `graph_analysis.py` untouched in this phase (MUS-01's "zero Core code changes" already forbids touching it) — flag as a possible future cleanup phase, not a Phase 48 blocker. Two copies of ~70 lines of pure logic is an acceptable interim state; XMOD-01 only requires collapsing MODULE-to-MODULE duplication (pf2e + music), not Core-to-module duplication.

2. **Does the root `docker-compose.yml`'s `include:` addition for `modules/music/compose.yml` count as a "Core code change" under MUS-01's "Core needs no code changes to host it"?**
   - What we know: MUS-01's exact wording is "Core needs no code changes to host it (mirrors `modules/pathfinder/`)" — and pf2e's own inclusion required the identical one-line `include:` addition when pf2e was first scaffolded, which was NOT considered a Core code change at the time (it's Compose orchestration config, not `sentinel-core/app/*.py`).
   - What's unclear: nothing, actually — this is settled by precedent (pf2e already did exactly this), included here only so the planner doesn't hesitate on it.
   - Recommendation: proceed with the one-line `docker-compose.yml` addition; it is compose-level infrastructure wiring, not Core application code, consistent with how pf2e was integrated.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.3.0 (pf2e), pytest 8.0 + pytest-asyncio 0.23 (shared) — `asyncio_mode = "auto"` in both, no explicit `@pytest.mark.asyncio` needed |
| Config file | `modules/pathfinder/pyproject.toml` (`[tool.pytest.ini_options]`), `shared/pyproject.toml` (same), `modules/music/pyproject.toml` (NEW — same shape) |
| Quick run command | `cd shared && .venv/bin/python -m pytest -q tests/test_obsidian.py` (new file) |
| Full suite command | `cd modules/pathfinder && .venv/bin/python -m pytest -q` (405 tests baseline); `cd shared && .venv/bin/python -m pytest -q` (35 tests baseline + new obsidian/graph_check tests); `cd modules/music && .venv/bin/python -m pytest -q` (new venv, new suite) |

**Three separate venvs, confirmed live:**
```bash
sentinel-core/.venv/bin/python -m pytest --collect-only -q   # 605 tests (unaffected by this phase — no Core code changes)
modules/pathfinder/.venv/bin/python -m pytest --collect-only -q   # 405 tests (regression guard, D-06)
shared/.venv/bin/python -m pytest --collect-only -q   # 35 tests (grows with new test_obsidian.py, test_graph_check.py)
```
`modules/music/` needs its OWN new `.venv` (created via `uv sync` or `pip install -e .[dev]` inside `modules/music/`, mirroring how pf2e's `.venv` was set up) — there is no existing venv for it since the module doesn't exist yet.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MUS-01 | music-module container starts, registers with Core, Core's registry lists `music`, zero Core code changes | integration (live-Docker smoke) + unit (registration retry logic) | Unit: `cd modules/music && .venv/bin/python -m pytest -q tests/test_registration.py`. Live smoke: `docker compose --profile music up -d && curl http://localhost:8000/modules` (assert `"music"` present in registry JSON) | ❌ Wave 0 — new test file |
| MUS-02 | Module reads/writes `music/` via its OWN `ObsidianClientCore`; never imports Core's `Vault` Protocol | unit (import-boundary check) + unit (client behavior via MockTransport) | `grep -rn "from app.vault import\|sentinel_core.*vault\|import vault" modules/music/` must return empty; `cd shared && .venv/bin/python -m pytest -q tests/test_obsidian.py` | ❌ Wave 0 — new test file + new grep-based boundary check |
| MUS-05 | Every music note carries `_schema` + wikilinks, zero orphans | unit (pure structural, Pattern 4) | `cd modules/music && .venv/bin/python -m pytest -q tests/test_music_vault_seed.py` | ❌ Wave 0 — new test file |
| XMOD-01 | pf2e + music both consume ONE shared `ObsidianClient`; no duplicated client logic remains | unit (pf2e full regression suite, D-06) + structural (grep for duplicated method bodies) | `cd modules/pathfinder && .venv/bin/python -m pytest -q` (405 tests must stay green); `grep -c "async def get_note" modules/pathfinder/app/obsidian.py` must be `0` (method lives only in `sentinel_shared.obsidian` now) | ✅ pf2e suite exists (405 tests); ❌ new grep-based dedup check |

### Sampling Rate
- **Per task commit:** run the venv's own suite for whichever files changed (`shared`'s suite after `obsidian.py`/`graph_check.py` land; pf2e's suite after the cutover; music's suite after each scaffold file lands).
- **Per wave merge:** run all three suites (`sentinel-core`, `modules/pathfinder`, `shared`) plus the new `modules/music` suite — confirm 605+405+35(+N)+M all green with zero regressions in the two UNCHANGED suites (sentinel-core, and pf2e's route-level tests unrelated to `obsidian.py`).
- **Phase gate:** full 4-venv suite green, PLUS one live-Docker smoke test (`docker compose --profile music up`, confirm `/healthz` 200 and `/modules` lists `"music"`) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `shared/tests/test_obsidian.py` — covers XMOD-01 (ObsidianClientCore + both mixins, MockTransport-based, mirrors `test_aliases_path_probe.py`'s pattern)
- [ ] `shared/tests/test_graph_check.py` — covers MUS-05's vendored orphan rule (pure unit tests over the 4 hub-mesh notes + edge cases: unresolved wikilink, self-link exclusion)
- [ ] `modules/music/tests/conftest.py` — shared fixtures (sys.path shim, env defaults), mirrors `modules/pathfinder/tests/conftest.py`
- [ ] `modules/music/tests/test_registration.py`, `test_healthz.py`, `test_music_vault_seed.py` — new module's entire test suite (no prior art to extend, only pf2e's shape to mirror)
- [ ] `modules/music/.venv` — new venv creation (no framework install needed beyond what `pyproject.toml` declares — `uv sync` or equivalent)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `X-Sentinel-Key` header check on inbound module routes (mirrors pf2e's `foundry.py` pattern) — not exercised by Phase 48's `healthz`-only route set, but the config field (`sentinel_api_key`) must be wired now since MUS-01's registration payload requires it |
| V3 Session Management | no | No user sessions in this phase — machine-to-machine registration only |
| V4 Access Control | yes | `Authorization: Bearer {OBSIDIAN_API_KEY}` on every `ObsidianClientCore` request; Docker secrets file pattern (`secrets/sentinel_api_key`) for the registration key, never a plaintext compose `environment:` value |
| V5 Input Validation | n/a this phase | No user-facing routes beyond `healthz` in Phase 48's scope; deferred to Phase 49's practice-log routes |
| V6 Cryptography | no | No new cryptographic operations — reuses existing Bearer-token auth already validated in pf2e |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secrets committed to `compose.yml` or `.env` in plaintext | Information Disclosure | Docker secrets file (`secrets/sentinel_api_key`) referenced via compose `secrets:` block, never a plaintext `environment:` value — this phase's `compose.yml` template already follows this (Pattern 3) |
| Unauthenticated module registration spoofing | Spoofing | `X-Sentinel-Key` header required on `POST /modules/register` — already enforced Core-side, unchanged by this phase (zero Core changes, MUS-01) |
| A future module route trusting unauthenticated inbound requests | Spoofing/Tampering | Not exercised by Phase 48 (only `healthz` exists, which is intentionally unauthenticated per pf2e's own precedent) — flagged for Phase 49+ when real routes are added: those MUST validate `X-Sentinel-Key` on inbound requests, per `.planning/research/PITFALLS.md`'s Security Mistakes table |

## Sources

### Primary (HIGH confidence — direct code reads this session)
- `modules/pathfinder/app/obsidian.py` (227 lines, read in full) — exact method bodies, line numbers, timeout values for the mixin split
- `modules/pathfinder/app/main.py` (379 lines, read in full) — registration payload shape, backoff/heartbeat implementation, lifespan wiring
- `modules/pathfinder/pyproject.toml`, `shared/pyproject.toml` — dependency floors, pytest config, `pythonpath` convention
- `modules/pathfinder/tests/test_aliases_path_probe.py`, `test_registration.py`, `conftest.py` — MockTransport pattern, registration test shape, sys.path shim convention
- `shared/sentinel_shared/__init__.py`, `similarity.py` — flat-module convention, Docker `additional_contexts`/`COPY --from=shared` build-time mechanism, cross-package SPOT precedent
- `sentinel-core/app/config.py` (188 lines, read in full) — `sweep_skip_prefixes`/`protected_namespaces` exact literals, line numbers, env-var names, REPLACE semantics
- `sentinel-core/app/vault.py` (relevant sections read) — `is_protected_path`'s segment-boundary matching logic, `ProtectedPathError`
- `sentinel-core/app/services/vault_sweeper.py` (relevant sections read) — `_should_skip`'s bare `startswith` (contrast with `is_protected_path`'s stricter matching — Pitfall D)
- `sentinel-core/app/services/graph_analysis.py` (128 lines, read in full) — exact orphan rule, `resolve_wikilink`, `extract_wikilinks` — vendored verbatim into Pattern 4
- `sentinel-core/app/services/note_schema.py` (159 lines, read in full) — `_schema` trailing-block contract, parser behavior
- `sentinel-core/app/services/links_sidecar_index.py` (183 lines, read in full) — confirms `NOTES_ROOT="notes"` scoping, why `music/` is invisible to Core's checker
- `sentinel-core/app/services/recall.py`, `sentinel-core/app/composition.py` — confirmed `RecallConfig.exclude_prefixes` has no env override path (D-15)
- `modules/pathfinder/compose.yml`, `docker-compose.yml`, `sentinel-core/compose.yml`, `modules/pathfinder/Dockerfile` — exact compose/Dockerfile templates, `additional_contexts`/`COPY --from=shared` mechanism, `include:` pattern
- `sentinel-core/app/routes/modules.py`, `module_gateway.py` — confirmed generic proxy, `X-Sentinel-Key` forwarding, 120s proxy timeout
- Live command: `pydantic_settings.__version__` → `2.13.1`, plus a live repl confirming `tuple[str,...]` env parsing accepts a JSON array string
- Live command: pytest `--collect-only` counts — sentinel-core 605, pf2e 405, shared 35

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md`, `ARCHITECTURE.md`, `PITFALLS.md` — prior-session research for this milestone, itself HIGH-confidence-labeled for direct-code-read claims but produced in an earlier session; cross-checked against this session's direct reads where overlapping (e.g. confirmed the `pf2e/`-vs-`mnemosyne/pf2e/` skip-prefix concern ARCHITECTURE.md flagged is ALREADY resolved in the live config.py — Pitfall E)

### Tertiary (LOW confidence)
- None — this phase required no external web research; every claim traces to a direct repo read or a live command run this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, every version verified against the actual installed venv or pyproject.toml
- Architecture: HIGH — every pattern is a direct mirror of a shipped, tested reference implementation (pf2e) already running in this repo
- Pitfalls: HIGH — all five pitfalls trace to direct code reads (config.py, vault.py, vault_sweeper.py) plus one already-resolved prior-research flag (Pitfall E), not speculative external-domain risk

**Research date:** 2026-07-08
**Valid until:** 60 days — this is an internal-refactor phase with no external dependency drift risk; the only thing that could invalidate this research is a Core-side change to `sweep_skip_prefixes`/`protected_namespaces`/`graph_analysis.py` landing before Phase 48 executes (unlikely mid-milestone, but re-verify line numbers if a large gap elapses before implementation)
