---
phase: 48-module-scaffold-shared-vault-client
plan: 03
subsystem: infra
tags: [fastapi, pydantic-settings, sentinel-shared, module-registration, docker-compose, uv]

# Dependency graph
requires:
  - phase: 48-module-scaffold-shared-vault-client (Plan 01)
    provides: "sentinel_shared.obsidian: ObsidianClientCore (+ mixins pf2e uses)"
provides:
  - "modules/music/ standalone FastAPI module — structural mirror of modules/pathfinder/ with trimmed deps"
  - "music-module registers with sentinel-core (name=music, healthz-only payload, 5-attempt backoff + 30s heartbeat)"
  - "music's app/obsidian.py composes ObsidianClientCore only (core-only, D-03/MUS-02) — never imports Core's Vault Protocol"
  - "docker-compose.yml include for modules/music/compose.yml (profiles: [music])"
affects: [48-04-music-vault-seed, future-music-route-phases-49-plus]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module scaffold mirror: modules/music/ 1:1 structurally mirrors modules/pathfinder/ (app/main.py lifespan+registration+heartbeat, app/config.py pydantic-settings, compose.yml profile, Dockerfile, pyproject.toml, tests/) with pf2e-only surface (litellm/rapidfuzz/reportlab/beautifulsoup4/numpy/pillow, session/Discord settings, binary/heading mixins) trimmed."
    - "Registry name == Docker service/profile name (\"music\" everywhere) — no pf2e-style profile/registry split, since that split only exists because pf2e's Docker service predates its logical rename."

key-files:
  created:
    - modules/music/app/__init__.py
    - modules/music/app/config.py
    - modules/music/app/obsidian.py
    - modules/music/app/main.py
    - modules/music/compose.yml
    - modules/music/Dockerfile
    - modules/music/pyproject.toml
    - modules/music/uv.lock
    - modules/music/tests/__init__.py
    - modules/music/tests/conftest.py
    - modules/music/tests/test_registration.py
    - modules/music/tests/test_healthz.py
  modified:
    - docker-compose.yml

key-decisions:
  - "Trimmed pyproject.toml/Dockerfile deps to fastapi/uvicorn/httpx/pydantic-settings/pyyaml only — explicitly excluded pf2e-only litellm/rapidfuzz/reportlab/beautifulsoup4/numpy/pillow (RESEARCH.md anti-pattern)."
  - "music/app/obsidian.py composes ObsidianClientCore alone (no ObsidianBinaryMixin/ObsidianHeadingMixin) per D-03/MUS-02 — verified by an empty MUS-02 boundary grep."
  - "REGISTRATION_PAYLOAD carries only the healthz route for Phase 48 — test_registration_payload_routes_present_and_unique asserts the exact list equals ['healthz'] (not just 'contains'), so the test fails loudly the moment Phase 49+ adds routes without updating it."
  - "No volumes: mount in music's compose.yml (unlike pf2e) — the module has no filesystem-backed import flow; it persists solely via the Obsidian REST ObsidianClient."
  - "uv.lock committed alongside pyproject.toml, matching pf2e's convention; .venv/ self-excludes from git via its own .venv/.gitignore (uv convention), not the root .gitignore."

patterns-established:
  - "Core-only ObsidianClient composition: `class ObsidianClient(ObsidianClientCore): pass` is the reference shape for any future module (e.g. Finance, Stock Trader) that needs vault read/write but not binary/heading mixins."

requirements-completed: [MUS-01, MUS-02]

coverage:
  - id: D1
    description: "modules/music runs as a standalone Docker service with its own FastAPI app and compose profile music, mirroring modules/pathfinder exactly — zero Core code changes"
    requirement: "MUS-01"
    verification:
      - kind: integration
        ref: "docker compose --profile music config -q (exit 0, service music-module resolves with profiles:[music])"
        status: pass
      - kind: unit
        ref: "grep -c 'litellm|rapidfuzz|reportlab|beautifulsoup4|numpy|pillow' modules/music/pyproject.toml == 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "On startup the module posts REGISTRATION_PAYLOAD (name=music, healthz-only routes) with 5-attempt backoff + 30s heartbeat"
    requirement: "MUS-01"
    verification:
      - kind: unit
        ref: "tests/test_registration.py (5 tests: succeeds-first-attempt, retries-on-failure, exits-after-5-failures, payload-correct, routes-present-and-unique)"
        status: pass
    human_judgment: false
  - id: D3
    description: "The module owns a thin ObsidianClient composed only from ObsidianClientCore and never imports Core's Vault Protocol / ObsidianVault"
    requirement: "MUS-02"
    verification:
      - kind: unit
        ref: "grep -rn 'from app.vault import|import vault|sentinel_core.*vault' modules/music/ (empty)"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /healthz returns 200 and the music venv suite (registration + healthz) is green"
    requirement: "MUS-01"
    verification:
      - kind: unit
        ref: "tests/test_healthz.py#test_healthz_returns_ok"
        status: pass
      - kind: integration
        ref: "cd modules/music && .venv/bin/python -m pytest -q -> 6 passed, 0 warnings"
        status: pass
    human_judgment: false

duration: 22min
completed: 2026-07-08
status: complete
---

# Phase 48 Plan 03: Music Module Scaffold + Shared Vault Client Summary

**Scaffolded modules/music/ as a structural mirror of modules/pathfinder/ — trimmed FastAPI app with registration/heartbeat, a core-only ObsidianClient composed from sentinel_shared, and a music Docker Compose profile — with a green 6-test venv suite and zero Core code changes.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-07-08T02:56:00Z (first task commit `661b2e1`)
- **Completed:** 2026-07-08T03:18:00Z
- **Tasks:** 3
- **Files modified:** 12 (11 new + 1 edited)

## Accomplishments
- `modules/music/` scaffolded end-to-end: `pyproject.toml` (trimmed deps: fastapi, uvicorn, httpx, pydantic-settings, pyyaml), `Dockerfile` (mirrors pf2e's shared-context COPY lines, drops pf2e-only apt packages), `compose.yml` (`profiles: ["music"]`, service `music-module`, Docker secret for the registration key, `/healthz` healthcheck), and its own `.venv` installed via `uv sync` (uv.lock committed).
- `app/config.py` — trimmed pydantic-settings `Settings` (sentinel_core_url, sentinel_api_key required, obsidian_base_url, obsidian_api_key only).
- `app/obsidian.py` — `class ObsidianClient(ObsidianClientCore): pass`, core-only composition per D-03/MUS-02; MUS-02 import-boundary grep confirmed empty.
- `app/main.py` — `REGISTRATION_PAYLOAD` (name=music, base_url=http://music-module:8000, healthz-only route), `_register_with_retry` (5 attempts, 1/2/4/8/16s backoff, `SystemExit(1)` on total failure), `_registration_heartbeat` (30s re-register), `lifespan` wiring `app.state.obsidian_client`, `GET /healthz` → `{"status": "ok", "module": "music"}`.
- `docker-compose.yml` — one additive `include:` line for `modules/music/compose.yml`; verified with `docker compose --profile music config -q` (exit 0) and the pre-existing Discord include untouched.
- `tests/` — `conftest.py` (sys.path shim + env defaults + pre-import), `test_registration.py` (5 tests mirroring pf2e's shape, adapted to the music payload), `test_healthz.py` (AsyncClient/ASGITransport, no deprecated TestClient). Full suite: **6 passed, 0 warnings** (`cd modules/music && .venv/bin/python -m pytest -q`, also re-verified under `-W error`).

## Task Commits

Each task was committed atomically:

1. **Task 1: Music packaging + compose + venv** - `661b2e1` (feat)
2. **Task 2: Music app core — config, ObsidianClient, FastAPI app** - `4d19224` (feat)
3. **Task 3: Music module test suite — conftest + registration + healthz** - `5f42f26` (test)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `modules/music/pyproject.toml` - `music-module`, trimmed runtime deps, `pythonpath = [".", "../../shared"]`, `asyncio_mode = "auto"`
- `modules/music/uv.lock` - generated by `uv sync`, committed per pf2e convention
- `modules/music/Dockerfile` - trimmed pf2e Dockerfile (no plyvel/libleveldb-dev), keeps `COPY --from=shared` lines
- `modules/music/compose.yml` - `profiles: ["music"]`, service `music-module`, `additional_contexts: {shared: ../../shared}`, Docker secret `sentinel_api_key`, `/healthz` healthcheck
- `modules/music/app/__init__.py` - empty package marker
- `modules/music/app/config.py` - trimmed pydantic-settings `Settings`
- `modules/music/app/obsidian.py` - `ObsidianClient(ObsidianClientCore)` core-only composition
- `modules/music/app/main.py` - FastAPI app, registration + heartbeat, `GET /healthz`
- `modules/music/tests/__init__.py` - empty package marker
- `modules/music/tests/conftest.py` - sys.path shim + env defaults + `app.main` pre-import
- `modules/music/tests/test_registration.py` - 5 registration/backoff tests
- `modules/music/tests/test_healthz.py` - healthz endpoint test
- `docker-compose.yml` - additive `include:` line for `modules/music/compose.yml`

## Decisions Made
- Trimmed `pyproject.toml`/`Dockerfile` dependencies to exactly the five packages the module needs (fastapi, uvicorn, httpx, pydantic-settings, pyyaml) — explicitly excluded pf2e-only libraries (litellm, rapidfuzz, reportlab, beautifulsoup4, numpy, pillow) per RESEARCH.md's anti-pattern guidance.
- `app/obsidian.py` composes `ObsidianClientCore` alone — no `ObsidianBinaryMixin`/`ObsidianHeadingMixin` — matching D-03/MUS-02's "core-only" requirement; verified with an empty import-boundary grep.
- `REGISTRATION_PAYLOAD['routes']` is asserted to equal exactly `["healthz"]` (not "contains") in `test_registration_payload_routes_present_and_unique`, so the test will fail loudly and require deliberate updating once Phase 49+ adds real routes — this makes the Phase-48 minimal-scope boundary an enforced contract, not a comment.
- Omitted the `volumes:` vault mount that pf2e's `compose.yml` has — music has no filesystem-backed import flow in this phase; it persists solely through the Obsidian REST `ObsidianClient`. Can be added in a later phase if a filesystem-backed flow is ever needed.
- `uv.lock` committed alongside `pyproject.toml` (matches pf2e's existing convention); `.venv/` need not be gitignored explicitly at the root — uv writes its own `.venv/.gitignore` (`*`) inside the venv directory, confirmed via `git check-ignore -v`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `python -c` ad-hoc verification needed explicit `PYTHONPATH=../../shared`**
- **Found during:** Task 2 acceptance-criteria verification
- **Issue:** The plan's `<verify>` commands for Task 2 run `.venv/bin/python -c "from app.main import ..."` directly. Unlike `pytest` (which reads `pythonpath` from `pyproject.toml`'s `[tool.pytest.ini_options]`), a bare `python -c` invocation does not consult that config, so `import sentinel_shared.obsidian` failed with `ModuleNotFoundError` on the first attempt.
- **Fix:** Re-ran the identical verification with `PYTHONPATH=../../shared` set in the environment. No code change was needed — this is purely a difference between how `pytest` and bare `python` resolve import paths; the actual test suite (`pytest`, Task 3) does not need this workaround since `pythonpath` in `pyproject.toml` applies automatically there.
- **Files modified:** None.
- **Verification:** `PYTHONPATH=../../shared .venv/bin/python -c "from app.main import app, REGISTRATION_PAYLOAD, ..."` — passed.
- **Committed in:** N/A (verification-only, no code change required).

---

**Total deviations:** 1 auto-fixed (1 blocking, verification-only — no code change)
**Impact on plan:** None on shipped code. Purely a nuance of how the plan's ad-hoc CLI verification snippet resolves imports versus pytest; the committed test suite is unaffected.

## Issues Encountered
- An ad-hoc verification script (not committed) that used `fastapi.testclient.TestClient` emitted a `StarletteDeprecationWarning` about `httpx`+`starlette.testclient`. This did not leak into shipped code — `tests/test_healthz.py` uses the `httpx.AsyncClient` + `ASGITransport` pattern (matching pf2e's established `test_healthz.py` convention) exclusively, and the committed test suite runs clean under `pytest -q -W error` with zero warnings.

## User Setup Required
None - no external service configuration required. (`secrets/sentinel_api_key` and the deploy `.env` are provisioned on the deploy checkout per existing project convention — not part of this dev-tree scaffold.)

## Next Phase Readiness
- `modules/music/` is a registrable, health-checkable module with a core-only `ObsidianClient` ready for Plan 48-04's first `music/` vault write (hub-mesh notes, zero-orphan self-check via `sentinel_shared.graph_check`).
- The `music` Docker Compose profile is wired into the root `docker-compose.yml`; `docker compose --profile music config -q` confirms the service resolves cleanly once a deploy `.env`/`secrets/sentinel_api_key` are present (this dev checkout has neither — expected, per the two-checkout deploy topology).
- `REGISTRATION_PAYLOAD`'s minimal healthz-only route list, and its enforcing test, mean Phase 49+ must deliberately touch `test_registration_payload_routes_present_and_unique` when adding real routes — no silent scope drift.
- No blockers.

---
*Phase: 48-module-scaffold-shared-vault-client*
*Completed: 2026-07-08*

## Self-Check: PASSED

All created files verified present on disk (`modules/music/app/{__init__,config,obsidian,main}.py`, `modules/music/{pyproject.toml,uv.lock,Dockerfile,compose.yml}`, `modules/music/tests/{__init__,conftest,test_registration,test_healthz}.py`, `docker-compose.yml` modified). All 3 task commits (`661b2e1`, `4d19224`, `5f42f26`) confirmed present in `git log --oneline`. Re-ran the full music venv suite as part of self-check: `cd modules/music && .venv/bin/python -m pytest -q` → 6 passed, 0 warnings. Re-ran `docker compose --profile music config -q` → exit 0. Re-ran the MUS-02 boundary grep → empty.
