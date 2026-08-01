# Phase 48: Module Scaffold + Shared Vault Client - Pattern Map

**Mapped:** 2026-07-08
**Files analyzed:** 21
**Analogs found:** 19 / 21

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `shared/sentinel_shared/obsidian.py` | service (HTTP client library) | request-response | `modules/pathfinder/app/obsidian.py` | exact (split, not new logic) |
| `shared/sentinel_shared/graph_check.py` | utility (pure transform) | transform | `sentinel-core/app/services/graph_analysis.py` | exact (vendored copy) |
| `shared/tests/test_obsidian.py` | test | request-response | `modules/pathfinder/tests/test_aliases_path_probe.py` | exact |
| `shared/tests/test_graph_check.py` | test | transform | `sentinel-core/tests/test_graph_analysis.py` | exact |
| `modules/pathfinder/app/obsidian.py` (rewrite) | service (composition) | request-response | itself, pre-rewrite (227→6 lines) | exact |
| `modules/music/app/__init__.py` | config | — | `modules/pathfinder/app/__init__.py` | exact |
| `modules/music/app/main.py` | controller (FastAPI app) | request-response + event-driven (heartbeat) | `modules/pathfinder/app/main.py` | exact |
| `modules/music/app/config.py` | config | — | `modules/pathfinder/app/config.py` | exact |
| `modules/music/app/obsidian.py` | service (composition) | request-response | `modules/pathfinder/app/obsidian.py` (post-cutover) | exact |
| `modules/music/compose.yml` | config | — | `modules/pathfinder/compose.yml` | exact |
| `modules/music/Dockerfile` | config | — | `modules/pathfinder/Dockerfile` | exact |
| `modules/music/pyproject.toml` | config | — | `modules/pathfinder/pyproject.toml` | exact (trimmed deps) |
| `modules/music/tests/__init__.py` | test | — | `modules/pathfinder/tests/__init__.py` | exact |
| `modules/music/tests/conftest.py` | test | — | `modules/pathfinder/tests/conftest.py` | exact |
| `modules/music/tests/test_registration.py` | test | event-driven (retry/backoff) | `modules/pathfinder/tests/test_registration.py` | exact |
| `modules/music/tests/test_healthz.py` | test | request-response | `modules/pathfinder/tests/test_healthz.py` | exact |
| `modules/music/tests/test_music_vault_seed.py` | test | transform | `sentinel-core/tests/test_graph_analysis.py` (structure) | role-match, novel content |
| `docker-compose.yml` (edit: add `include:` line) | config | — | existing `include:` block itself | exact (additive one-liner) |
| env-override generation (`SWEEP_SKIP_PREFIXES`/`PROTECTED_NAMESPACES`) | utility (deploy script) | batch/transform | none | **no analog — greenfield** |
| `music/index.md` + 3 hub notes (vault content, not repo code) | — | file-I/O (vault write via REST) | Phase 45/47 note-quality contract; no single prior note file to copy verbatim | partial — schema-match only |
| `sentinel-core/tests/test_env_override_matches_core_defaults` (optional, Pitfall B guard) | test | transform | `sentinel-core/app/config.py` Settings fields | role-match |

## Pattern Assignments

### `shared/sentinel_shared/obsidian.py` (service, request-response)

**Analog:** `modules/pathfinder/app/obsidian.py` (227 lines, being split, not rewritten from scratch)

**Exact method→home split (line numbers from the live pf2e file):**

| Method | Current lines | New home |
|---|---|---|
| `__init__(self, http_client, base_url, api_key)` | 21-26 | `ObsidianClientCore.__init__` |
| `_safe_request(...)` | 28-35 | `ObsidianClientCore._safe_request` |
| `get_note(self, path)` | 37-51 | `ObsidianClientCore.get_note` |
| `put_note(self, path, content)` | 53-67 | `ObsidianClientCore.put_note` (120s timeout preserved verbatim) |
| `list_directory(...)` | 104-173 | `ObsidianClientCore.list_directory` (depth-8 recursion guard preserved verbatim) |
| `patch_frontmatter_field(...)` | 206-226 | `ObsidianClientCore.patch_frontmatter_field` |
| `put_binary(...)` | 69-82 | `ObsidianBinaryMixin.put_binary` |
| `get_binary(self, path)` | 84-102 | `ObsidianBinaryMixin.get_binary` |
| `patch_heading(...)` | 175-204 | `ObsidianHeadingMixin.patch_heading` |

**Skeleton to write (verbatim bodies copied from the line ranges above, D-04 behavior-preserving lift):**
```python
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

    async def get_note(self, path: str) -> str | None: ...       # verbatim body :37-51
    async def put_note(self, path: str, content: str) -> None: ...  # verbatim body :53-67, 120s timeout
    async def list_directory(self, prefix: str, *, _depth: int = 0, _max_depth: int = 8) -> list[str]: ...  # verbatim :104-173
    async def patch_frontmatter_field(self, path: str, field: str, value) -> None: ...  # verbatim :206-226


class ObsidianHeadingMixin:
    async def patch_heading(self, path: str, heading: str, content: str, operation: str = "append") -> None: ...  # verbatim :175-204


class ObsidianBinaryMixin:
    async def put_binary(self, path: str, data: bytes, content_type: str) -> None: ...  # verbatim :69-82
    async def get_binary(self, path: str) -> bytes | None: ...  # verbatim :84-102
```

**Docstring convention to follow (flat-module style, matches `similarity.py`'s SPOT-violation-closing docstring precedent):** open with a one-paragraph "why this exists / what it closes" note, same tone as `shared/sentinel_shared/similarity.py`'s header.

**Import/package convention** — no `__init__.py` re-export changes needed; `sentinel_shared` is flat, add `obsidian.py` alongside `llm_call.py`/`similarity.py`/`embedding_codec.py`/`model_profiles.py`, no new dependency (`httpx>=0.28.1` already in `shared/pyproject.toml`).

---

### `shared/sentinel_shared/graph_check.py` (utility, transform, pure)

**Analog:** `sentinel-core/app/services/graph_analysis.py` (128 lines) — pure computation, zero I/O, explicitly documented as portable.

**Functions to vendor verbatim (same algorithm, `hub_count` param dropped as Core-only):**
```python
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
    note_paths = list(notes.keys())
    outlinks: dict[str, set[str]] = {}
    backlinks: dict[str, list[str]] = {path: [] for path in notes}
    for path, body in notes.items():
        resolved = {
            resolve_wikilink(target, note_paths)
            for target in extract_wikilinks(body)
        }
        resolved.discard(None)
        resolved.discard(path)
        outlinks[path] = resolved
    for src, targets in outlinks.items():
        for target_path in targets:
            backlinks[target_path].append(src)
    orphans = [p for p in notes if not outlinks[p] and not backlinks[p]]
    total_edges = sum(len(v) for v in outlinks.values())
    note_count = len(notes)
    return GraphReport(
        note_count=note_count, orphans=orphans, backlinks=backlinks,
        link_density=(total_edges / note_count) if note_count else 0.0,
    )
```

Orphan rule: `orphan ⇔ not outlinks[path] and not backlinks[path]`. `resolve_wikilink` only creates an edge when the target already exists in the given notes map — this is why a lone hub is self-orphaning and why the hub-mesh (4 mutually-linked notes) is the minimum provably-compliant seed.

---

### `modules/pathfinder/app/obsidian.py` (rewrite, service, composition)

**Analog:** none needed — this IS the source being split; post-rewrite it becomes pure composition:
```python
from sentinel_shared.obsidian import (
    ObsidianBinaryMixin,
    ObsidianClientCore,
    ObsidianHeadingMixin,
)

class ObsidianClient(ObsidianClientCore, ObsidianBinaryMixin, ObsidianHeadingMixin):
    """pf2e needs the full surface: core methods + patch_heading + binary I/O."""
    pass
```

**Coupling-site verification (NOT edit targets — confirmed no diff needed, D-05/Pitfall C):**
- `modules/pathfinder/app/main.py:57` (`from app.obsidian import ObsidianClient`) — unchanged, same import path resolves.
- `modules/pathfinder/app/main.py:203` (`lifespan()` instantiation) — unchanged, `ObsidianClientCore.__init__` signature identical, no mixin defines `__init__`, so MRO resolves correctly without edits.
- `modules/pathfinder/tests/test_aliases_path_probe.py:28,36-40` — unchanged, tests through the public `ObsidianClient` name only.
- **Regression guard (mandatory, D-06):** `cd modules/pathfinder && .venv/bin/python -m pytest -q` must stay at 405 tests green. Grep check for dedup: `grep -c "async def get_note" modules/pathfinder/app/obsidian.py` must return `0`.

---

### `modules/music/app/main.py` (controller, request-response + event-driven)

**Analog:** `modules/pathfinder/app/main.py` (379 lines) — FastAPI app + `lifespan()` + registration/heartbeat.

**Registration payload (Phase-48 minimal scope, D-12):**
```python
REGISTRATION_PAYLOAD = {
    "name": "music",
    "base_url": "http://music-module:8000",
    "routes": [
        {"path": "healthz", "description": "music module health check"},
    ],
}
```

**Backoff + heartbeat (copy verbatim shape from `main.py:117-161`, only payload/name differ):**
```python
async def _register_with_retry(client: httpx.AsyncClient) -> None:
    """5 attempts, exponential backoff 1s->2s->4s->8s->16s. SystemExit(1) on total failure."""
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

Only wire `healthz` route + `lifespan()` register/heartbeat startup — no NPC/harvest/rules-style route modules to mirror (out of scope, phases 49+).

---

### `modules/music/app/config.py` (config)

**Analog:** `modules/pathfinder/app/config.py` (pydantic-settings pattern). Trim to: `sentinel_core_url`, `sentinel_api_key` (required), `obsidian_base_url`, `obsidian_api_key`. Drop pf2e-specific fields (`litellm_api_base`, session settings, `discord_bot_internal_url`).

---

### `modules/music/app/obsidian.py` (service, composition)

**Analog:** `modules/pathfinder/app/obsidian.py` (post-cutover), but core-only per D-03/MUS-02:
```python
from sentinel_shared.obsidian import ObsidianClientCore

class ObsidianClient(ObsidianClientCore):
    pass
```
**Import-boundary check (MUS-02):** `grep -rn "from app.vault import\|sentinel_core.*vault\|import vault" modules/music/` must return empty — module must never import Core's `Vault` Protocol / `ObsidianVault`.

---

### `modules/music/compose.yml` / `Dockerfile` / `pyproject.toml` (config)

**Analog:** `modules/pathfinder/compose.yml`, `Dockerfile`, `pyproject.toml` — mirror structure, trim pf2e-only surface:
- compose.yml: same `additional_contexts: {shared: ../../shared}`, `profiles: ["music"]`, service `music-module`, `depends_on: sentinel-core (service_healthy)`, `secrets: [sentinel_api_key]`, healthcheck curl on `/healthz`.
- Dockerfile: drop pf2e-only apt packages (`libleveldb-dev` for `plyvel`); keep both `COPY --from=shared` lines.
- pyproject.toml: `pythonpath = [".", "../../shared"]`; deps trimmed to `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic-settings`, `pyyaml` — explicitly do NOT copy pf2e's `litellm`/`rapidfuzz`/`reportlab`/`beautifulsoup4`/`numpy`/`pillow` (anti-pattern, unused bloat).

**docker-compose.yml edit** — one additive line in the existing `include:` block:
```yaml
include:
  - path: sentinel-core/compose.yml
  - path: interfaces/discord/compose.yml
  - path: security/pentest-agent/compose.yml
  - path: modules/pathfinder/compose.yml
  - path: modules/music/compose.yml   # NEW
```
This mirrors exactly how pf2e was originally added (settled by precedent, not a Core code change).

---

### `modules/music/tests/*` (test)

**Analogs, 1:1 file mirrors:**
- `tests/__init__.py` ← `modules/pathfinder/tests/__init__.py` (empty)
- `tests/conftest.py` ← `modules/pathfinder/tests/conftest.py` (sys.path shim for `../../shared`; `os.environ.setdefault` for `SENTINEL_API_KEY`/`SENTINEL_CORE_URL`/`OBSIDIAN_BASE_URL`/`OBSIDIAN_API_KEY`)
- `tests/test_registration.py` ← `modules/pathfinder/tests/test_registration.py` (142 lines, 5 tests: succeeds-first-attempt / retries-on-failure / exits-after-5-failures / payload-correct). Excerpt:
```python
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
- `tests/test_healthz.py` ← `modules/pathfinder/tests/test_healthz.py` — trivial `GET /healthz` → `{"status": "ok", "module": "music"}`
- `tests/test_music_vault_seed.py` — NO pf2e equivalent (new). Structural shape mirrors `sentinel-core/tests/test_graph_analysis.py`'s pure-unit style:
```python
from sentinel_shared.graph_check import build_graph_report, extract_wikilinks

HUB_NOTES = {
    "music/index.md": "...",
    "music/lessons/index.md": "...",
    "music/practice-log/index.md": "...",
    "music/ideas/index.md": "...",
}

def test_hub_mesh_has_zero_orphans():
    report = build_graph_report(HUB_NOTES)
    assert report.orphans == []

def test_every_hub_has_schema_block_and_wikilinks():
    for path, body in HUB_NOTES.items():
        assert "```_schema" in body, f"{path} missing trailing _schema block"
        assert extract_wikilinks(body), f"{path} has no resolvable wikilink"
```

**`shared/tests/test_obsidian.py`** ← MockTransport pattern from `modules/pathfinder/tests/test_aliases_path_probe.py`:
```python
def _make_client(handler, ClientClass, base_url="https://obsidian.test:27124", api_key="test-key"):
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return ClientClass(http_client, base_url, api_key), http_client
```

---

### `music/index.md` + 3 hub notes (vault content, file-I/O via REST)

**No single prior note is a byte-level analog** — this is the first `music/`-namespace write. Follow the Phase-45/47 note-quality contract (frontmatter + H1 + ≥1 resolvable wikilink + trailing `_schema` block, `listenbrainz_context`/`discogs_context` null) rather than copying an existing note verbatim. Exact 4-note hub-mesh content (mutually wikilinked, provably zero-orphan under `build_graph_report`) is fully specified in RESEARCH.md Pattern 4 — planner should treat that content as ready-to-use, not to be re-derived.

---

## Shared Patterns

### Module registration + heartbeat
**Source:** `modules/pathfinder/app/main.py:80-161`
**Apply to:** `modules/music/app/main.py`
Registry name / Docker service name recommendation: keep both `"music"` (no pf2e-style profile/registry-name split — that split only exists because pf2e's Docker service predates its logical rename).

### httpx MockTransport testing
**Source:** `modules/pathfinder/tests/test_aliases_path_probe.py`
**Apply to:** `shared/tests/test_obsidian.py`, any music client tests needing a fake Obsidian endpoint.

### Flat single-purpose-module convention
**Source:** `shared/sentinel_shared/similarity.py`, `llm_call.py`
**Apply to:** `shared/sentinel_shared/obsidian.py`, `shared/sentinel_shared/graph_check.py` — no new subpackage, single file per concern, SPOT-closing docstring header style (similarity.py already documents itself as closing a cross-package duplication — same rhetorical pattern to reuse for both new files).

### pytest asyncio_mode=auto
**Source:** `modules/pathfinder/pyproject.toml`, `shared/pyproject.toml` `[tool.pytest.ini_options]`
**Apply to:** `modules/music/pyproject.toml` (new, same shape) — no explicit `@pytest.mark.asyncio` needed anywhere.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| Env-override generation script for `SWEEP_SKIP_PREFIXES`/`PROTECTED_NAMESPACES` | utility (deploy script) | batch/transform | Nothing like this exists in the repo today — greenfield. RESEARCH.md recommends (option 1, Pitfall B) a small deploy-time Python one-liner that imports `sentinel-core.app.config.Settings` field defaults directly and prints `json.dumps(list(defaults) + ["music/"])`, piped into the deploy `.env`. No prior deploy-time codegen script pattern exists in this repo to mirror; planner should treat this as new infrastructure, following only the general principle (derive from Settings defaults, never hand-copy) rather than an existing analog file. Optional companion: a Core-side test (`test_env_override_matches_core_defaults_plus_music`, analog: any existing `sentinel-core/tests/test_config.py`-style unit test) asserting the generated value stays in sync. |
| `music/index.md` hub-mesh notes (vault content) | — | file-I/O | No prior note in this repo is a structural byte-level twin (first `music/`-namespace write) — schema contract match only, not a file analog. |

## Metadata

**Analog search scope:** `modules/pathfinder/` (app/, tests/, compose.yml, Dockerfile, pyproject.toml), `shared/sentinel_shared/` (existing flat modules), `sentinel-core/app/services/graph_analysis.py`, `sentinel-core/app/config.py`, `docker-compose.yml`
**Files scanned:** ~15 (all read directly per RESEARCH.md's verified-against-live-code claims; this pattern map derives from that research rather than re-reading, since RESEARCH.md already contains line-numbered excerpts and full verbatim skeletons)
**Pattern extraction date:** 2026-07-08
