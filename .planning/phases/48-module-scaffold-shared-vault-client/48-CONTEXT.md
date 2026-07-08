# Phase 48: Module Scaffold + Shared Vault Client - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Stand up the **Music module** as a standalone, registered Docker service with its own vault-write foundation and note-schema contract, AND consolidate the duplicated per-module Obsidian client into the shared package **before a second copy accumulates**.

In scope: the `modules/music/` scaffold (FastAPI app, config, compose profile, healthz, `POST /modules/register` + heartbeat); a shared composable `ObsidianClient` in `sentinel_shared`; pf2e migrated onto it; a first real `music/` vault write proving the `_schema`/wikilink/zero-orphan contract; sweeper protection for `music/`.

Out of scope (later phases 49+): practice-logging / idea-capture / history-query / routine-builder routes; Discord command wiring; ListenBrainz/Discogs integrations; warm-tier recall tuning for `music/`.
</domain>

<decisions>
## Implementation Decisions

### Shared Vault Client (XMOD-01)
- **D-01:** Promote the Obsidian client into the existing `shared/` package (`sentinel-shared`, already consumed by pf2e via `pythonpath = [".", "../../shared"]`) as a **composable core + mixins, built now**. Rationale (validated against the 6-module PRD — pf2e, music, Coder Interface, Personal Finance, Autonomous Stock Trader, Media/Discovery): the core methods are shared by *all* modules, so build the common core now rather than combining copies once four modules are running. Layout in `sentinel_shared`:
  - `ObsidianClientCore` — HTTP plumbing (httpx client, `Authorization: Bearer {OBSIDIAN_API_KEY}` against `OBSIDIAN_BASE_URL`, the `_safe_request` graceful-degrade helper) + the four universally-common methods: `get_note`, `put_note`, `list_directory`, `patch_frontmatter_field`.
  - `ObsidianHeadingMixin` — `patch_heading` (shared: pf2e uses it today; Music "Listening Log" / Finance appends may want it later).
  - `ObsidianBinaryMixin` — `put_binary`, `get_binary` (shared but pf2e-only today; kept composable so no future media module has to copy pf2e).
- **D-02:** pf2e's client becomes **pure composition**: `class ObsidianClient(ObsidianClientCore, ObsidianBinaryMixin, ObsidianHeadingMixin)`. No duplicated client *logic* remains anywhere in pf2e's tree.
- **D-03:** Music consumes `ObsidianClientCore` (core-only; no binary/heading). It **never** imports Core's `Vault` Protocol / `ObsidianVault` (`sentinel-core/app/vault.py`) — MUS-02.
- **D-04:** Behavior-preserving lift, not redesign. Copy pf2e's exact request semantics verbatim into the core (120s `put_note` timeout, the `list_directory` recursion/depth guard, content-type handling) so migration carries zero behavior drift.

### pf2e Cutover (criterion #4)
- **D-05:** **Strict — no re-export shim.** Delete pf2e's standalone client logic and rewrite the two real coupling sites: the import + instantiation in `modules/pathfinder/app/main.py` (~`:57` import, ~`:203` `lifespan()` instantiation onto `app.state.obsidian_client`) and the direct construct in `modules/pathfinder/tests/test_aliases_path_probe.py` (~`:28`). The ~10 duck-typed consumers (they take `obsidian_client` as an untyped param) need no change; the 7 local `FakeObsidian` doubles are structurally decoupled and stay put. A file still named `obsidian.py` exporting `ObsidianClient` would read as "pf2e still owns a client" — not acceptable; only a legitimate composition subclass may remain.
- **D-06:** Regression guard is an **acceptance criterion, not a follow-up**: the pf2e change is not done until the full `modules/pathfinder/tests/` suite passes (pytest, `asyncio_mode=auto`), with explicit attention to `test_aliases_path_probe.py` (builds the client against a `MockTransport`) and the `lifespan()`/`app.state.obsidian_client` wiring tests.

### Music namespace, first write & schema proof (MUS-02, MUS-05)
- **D-07:** `/music/` is a new module-owned **top-level** namespace (sibling to `self/`, `notes/`, `ops/`, `inbox/`, `templates/`, `mnemosyne/pf2e/`) — not PARA-classified. Subfolders: `music/lessons/`, `music/practice-log/`, `music/ideas/`.
- **D-08:** First write = a **cross-linked hub mesh**, not a single hub and not a throwaway. Write `music/index.md` plus `music/lessons/index.md`, `music/practice-log/index.md`, `music/ideas/index.md`, mutually wikilinked. This is the only seed that is *provably* zero-orphan under the real rule (see D-10), and it leaves durable link targets so Phase 49+ practice/idea/lesson notes resolve immediately instead of being born orphans.
- **D-09:** Every music note follows the Phase-45/47 note-quality contract: leading YAML frontmatter + H1 claim title + ≥1 **resolvable** `[[wikilink]]` + a trailing ` ```_schema ` fenced block carrying `title` and `wikilinks`, with reserved `listenbrainz_context` / `discogs_context` fields **null by default**.
- **D-10:** Compliance is **proven structurally in-module**, not via Core. Core's `:graph`/`:check` walk is hard-scoped to `NOTES_ROOT="notes"` (`links_sidecar_index.py` → `walk_vault(root=NOTES_ROOT)`), so `music/` is invisible to Core's REST checker today. The verified orphan rule (`graph_analysis.build_graph_report`) is `orphan ⇔ not outlinks[path] and not backlinks[path]`, and `resolve_wikilink` only creates an edge when the target file **already exists** — which is exactly why a lone hub pointing at not-yet-written notes would self-flag as an orphan. Phase 48 asserts compliance with a **module-side test** that builds the `music/` notes-map and checks zero orphans + schema shape. Do **not** extend Core's `NOTES_ROOT` walk (that is a Core change → violates MUS-01). Full Core-side `:graph`/`:check` participation for `music/` is deferred.

### Module scaffold + registration (MUS-01)
- **D-11:** `modules/music/` mirrors `modules/pathfinder/`'s skeleton exactly — `app/main.py` (FastAPI + lifespan), `app/config.py` (pydantic-settings), `app/obsidian.py` (thin wrapper over `ObsidianClientCore`), `compose.yml` with `profiles: ["music"]`, `healthz` route, `Dockerfile`, `pyproject.toml` (`pythonpath = [".", "../../shared"]`). **Zero Core code changes.**
- **D-12:** Registration mirrors pf2e: `lifespan()` posts `REGISTRATION_PAYLOAD` (`name: "music"`, `base_url`, `routes`) to `POST /modules/register` with 5-attempt exponential backoff (1s→16s) + a 30s heartbeat re-register so a Core restart self-heals. Phase-48 payload declares a **minimal** route set (`healthz` only) — real practice/idea/history routes are added in phases 49+.

### Sweeper protection + warm-tier (MUS-01, Pitfall 1)
- **D-13:** Protect `music/` from the vault sweeper via **deploy-env only, no Core code change**, in the **same commit** as the first `music/` write (Pitfall 1: an unprotected `music/` gets relocated to `_trash/` on the next sweep). Set both `SWEEP_SKIP_PREFIXES` **and** `PROTECTED_NAMESPACES` (JSON-list env vars) in the module's compose/deploy env. Both are pydantic-settings **REPLACE**-semantics overrides — the value MUST reproduce Core's full committed default tuple **plus** `music/`. **Do not hand-copy** the defaults — generate the override value from Core's current defaults so a future Core default change cannot silently drop `pf2e/`/`security/`/etc. Core defaults today:
  - `sweep_skip_prefixes = ("_trash/","pf2e/","mnemosyne/","core/","self/","templates/","archive/","security/","ops/sessions/","ops/sweeps/",".obsidian/")` (env `SWEEP_SKIP_PREFIXES`, `sentinel-core/app/config.py` ~137–154)
  - `protected_namespaces = ("sentinel/","self/","security/","templates/")` (env `PROTECTED_NAMESPACES`, ~177–183)
- **D-14:** Belt-and-suspenders rationale: `SWEEP_SKIP_PREFIXES` skips the walk/classify pass; `PROTECTED_NAMESPACES` independently blocks any physical move (`ProtectedPathError`, already caught non-fatally by the sweeper) if the skip list is ever misconfigured.
- **D-15:** Warm-tier recall exclusion for `music/` is **deferred**. `RecallConfig.exclude_prefixes` (`sentinel-core/app/services/recall.py` ~:249) is instantiated with no args in `composition.py` (~:409) and has **no env path** — adding `music/` needs a Core change, which MUS-01 forbids here. Accept that music notes may surface in generic warm-tier recall for now; wire exclusion deliberately alongside the future deterministic `:music history` feature.

### Claude's Discretion
- Exact file layout of the client inside `sentinel_shared` (single `obsidian.py` holding core+mixins vs. an `obsidian/` subpackage) — planner's call, following the existing flat single-purpose-module convention (`llm_call.py`, `similarity.py`).
- Whether Music's `app/obsidian.py` is a trivial `ObsidianClientCore` subclass or a direct alias.
- Exact hub-note prose and frontmatter fields beyond the mandated schema shape.
- The mechanism that generates the env-override value (compose templating vs. a small deploy-time script) — as long as it derives from Core's committed defaults rather than a hand-maintained literal.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase build order & module reference
- `.planning/research/ARCHITECTURE.md` — Suggested Build Order step 1 (module scaffold first); module registration + generic-proxy pattern; the `app/obsidian.py`-duplicated-not-shared note.
- `.planning/research/PITFALLS.md` §Pitfall 1 — `/music/` must be in the sweeper skip-prefixes in the same commit as the first write (else practice logs get trashed).
- `.planning/research/STACK.md` — module tech stack (fastapi, uvicorn, httpx, pydantic-settings, pyyaml; `shared/sentinel_shared` is a *different* surface = LLM/embedding helpers).
- `.planning/research/FEATURES.md` — music P1/P2/P3 prioritization (plain-text notation, no audio/art in vault).
- `docs/PRD-Sentinel-of-Mnemosyne.md` §6.1–6.6 — the full 6-module roadmap that validated the shared-core-now decision (D-01).

### Reference implementation (pf2e)
- `modules/pathfinder/app/obsidian.py` — the `ObsidianClient` being promoted (method split: core 4 vs `patch_heading` vs `put_binary`/`get_binary`).
- `modules/pathfinder/app/main.py` — registration payload + 5-attempt backoff + 30s heartbeat; `lifespan()` client wiring (the coupling site to rewrite).
- `modules/pathfinder/pyproject.toml` — `pythonpath = [".", "../../shared"]`, compose profile convention, deps.
- `modules/pathfinder/tests/` — pytest `asyncio_mode=auto`, `test_aliases_path_probe.py`, `FakeObsidian` doubles (regression guard for D-06).
- `shared/` + `shared/sentinel_shared/` — the package to extend; existing flat modules (`llm_call.py`, `similarity.py`, `embedding_codec.py`, `model_profiles.py`), `pyproject.toml`, `shared/tests/`.

### Vault contract & Core internals (read-only — do NOT modify per MUS-01)
- `sentinel-core/app/vault.py` — `ObsidianVault` (~:273): Core's own client that music must NOT import (MUS-02); `is_protected_path` / protected-namespace enforcement.
- `sentinel-core/app/config.py` — `Settings.sweep_skip_prefixes` (~137–154), `protected_namespaces` (~177–183); env vars + REPLACE semantics (D-13).
- `sentinel-core/app/services/vault_sweeper.py` — the sweep walk + non-fatal `ProtectedPathError` handling (D-14).
- `sentinel-core/app/services/graph_analysis.py` — `build_graph_report` orphan rule (pure, I/O-free) + `resolve_wikilink` existing-file resolution (D-08, D-10).
- `sentinel-core/app/services/links_sidecar_index.py` — `walk_vault(root=NOTES_ROOT)` = why `music/` is invisible to Core's `:graph`/`:check` (D-10).
- `sentinel-core/app/services/note_schema.py` — the `_schema` block contract helpers (D-09).
- `sentinel-core/app/services/recall.py` — `RecallConfig.exclude_prefixes` (~:249), no env path (D-15).

### Prior-phase decisions carried forward
- `.planning/phases/44-vault-namespace-taxonomy-foundation/44-CONTEXT.md` — namespace taxonomy, sweeper skip-prefix + protected-namespace mechanisms.
- `.planning/phases/45-note-quality-schema-graph-analysis/` — origin of the `_schema`/wikilink/graph-analysis machinery.
- `.planning/phases/47-migration-cutover-hardening/47-CONTEXT.md` — the note-quality schema contract (frontmatter + H1 + wikilinks + `_schema`; reserved null fields), frontmatter-preserving moves.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `shared/sentinel_shared` package already exists and is on pf2e's pythonpath — extend it in place; follow its flat single-purpose-module convention.
- `modules/pathfinder/` is a complete, shipped reference for every scaffold artifact (app skeleton, registration+heartbeat, compose profile, Dockerfile, pyproject, tests).
- `graph_analysis.build_graph_report` is a pure, vault-I/O-free function — reusable pattern for the module-side zero-orphan self-check (vendor a tiny equivalent, since the module container can't import sentinel-core at runtime).
- `note_schema.py` documents the exact `_schema` block shape music notes must emit.

### Established Patterns
- Note-quality schema (Ph 45/47): frontmatter + H1 + ≥1 resolvable wikilink + trailing `_schema` block; frontmatter-preserving moves protect embedding sidecars.
- Namespace taxonomy (Ph 44): top-level, module-owned namespaces sit beside `self/`/`notes/`/`ops/`; sweeper skip-prefix + protected-namespace are the two independent protection mechanisms.
- Module registration + 30s heartbeat is the **only** registration seam in the codebase; the generic Core proxy forwards `X-Sentinel-Key`.

### Integration Points
- `POST /modules/register` on Core (unchanged) — music registers here.
- Obsidian Local REST API (Bearer auth via `OBSIDIAN_API_KEY`/`OBSIDIAN_BASE_URL`) — the shared client's target.
- Deploy/compose **env** (not the dev tree) — where the `SWEEP_SKIP_PREFIXES` / `PROTECTED_NAMESPACES` overrides land; the live stack builds from the deploy checkout that holds `secrets`/`.env`.
</code_context>

<specifics>
## Specific Ideas

- Guiding principle for XMOD-01 (user's words): build the common **core now**, not "when you have four things going and then decide to combine." The composable core + mixins design serves that directly, and the 6-module PRD confirms the core methods are universally shared.
- The env-var override must be **generated** from Core's committed default tuples (not a hand-copied literal) because both `SWEEP_SKIP_PREFIXES` and `PROTECTED_NAMESPACES` use pydantic REPLACE semantics — a hand-copied list is a live footgun that silently un-protects `pf2e/`/`security/` on the next edit.
</specifics>

<deferred>
## Deferred Ideas

- **Warm-tier recall exclusion for `music/`** — needs a Core `RecallConfig.exclude_prefixes` change (no env path); wire it deliberately alongside the future deterministic `:music history` feature, not silently here (would break MUS-01's "zero Core changes").
- **Binary vault storage** — `ObsidianBinaryMixin` is built and composable, but no roadmapped module stores binaries in the vault (Media/Discovery, PRD §6.4/v2+, fetches art from Discogs). Left unused by music.
- **`patch_heading` in music** (e.g. a "Listening Log" append section) — the shared mixin is ready; adopt in a later music phase if desired.
- **Real module routes** — practice logging, idea capture, history queries, routine builder, Discord wiring, ListenBrainz/Discogs — Phases 49+.
</deferred>

---

*Phase: 48-module-scaffold-shared-vault-client*
*Context gathered: 2026-07-08*
