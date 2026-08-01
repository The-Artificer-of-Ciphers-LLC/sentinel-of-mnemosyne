---
phase: 48-module-scaffold-shared-vault-client
plan: 05
type: execute
completed: 2026-08-01
requirements: [MUS-01, MUS-02, MUS-05]
---

# 48-05 Summary — Phase gate: 4-venv regression + live-Docker smoke

Phase gate passed. Both tasks complete. The live smoke was deferred in the
previous session pending a Phase 47+48 deploy; that deploy happened this
session, unblocking it.

## Task 1 — Consolidated 4-venv regression gate — PASS

| Suite | Result |
|---|---|
| `sentinel-core` | 606 passed, 12 skipped |
| `modules/pathfinder` | 405 passed |
| `shared` | 49 passed |
| `modules/music` | 10 passed |

All four exit 0 together. Zero failures.

**Baseline deviation (expected, not a regression).** The plan anticipates
`sentinel-core` at ~605 and the prior handoff recorded 598. The count moved
during this session for deliberate reasons: 15 exo-dedicated tests were
DELETED when the retired exo backend was removed, and 23 new tests were added
across the defects listed below. The acceptance criterion gates on "no new
failures in the unchanged suites", which holds — `modules/pathfinder` is
unchanged at exactly its 405 baseline.

## Task 2 — Live-Docker smoke — PASS (operator-gated)

Run against the live stack from the deploy checkout (`/Volumes/Mini Me/...`),
never from the dev tree — per the two blocking anti-patterns recorded in
`.continue-here.md`, both of which were verified satisfied before starting
(deploy-checkout ancestry assertion for Phase 47+48; all compose invocations
prefixed with an explicit `cd` into the deploy checkout).

| # | Check | Result |
|---|---|---|
| 1 | Sweeper protection applied before first write | PASS |
| 2 | `music-module` container up | PASS |
| 3 | Registered; Core registry lists `music` | PASS |
| 4 | `healthz` 200 via Core proxy | PASS (see deviation) |
| 5 | 4-note hub-mesh present in live vault | PASS |
| 6 | Survives a live sweep | PASS |

1. `SWEEP_SKIP_PREFIXES` and `PROTECTED_NAMESPACES` appended to the deploy
   `.env` (backup `.env.bak-48-05-smoke-20260801`), both JSON-valid, with
   `security/ self/ pf2e/ music/` all present in the skip list and `music/`
   in the protected list. Verified present in the RUNNING container's env
   before any sweep — closing T-48-11 by assertion rather than assumption.
2. `music-module` healthy, `8000/tcp` (internal only; reached via Core).
3. `GET /modules` -> `['music', 'pathfinder']`. Registered on attempt 1.
4. `{"status":"ok","module":"music"}` HTTP 200.
5. All four notes HTTP 200; seeded 204 on first write.
6. A REAL sweep (`dry_run=false`) moved 28 files — 22 topic relocations,
   2 noise->trash, 4 duplicates->trash. All four `music/` notes remained
   HTTP 200. Pitfall-1 protection proven end-to-end against an actually
   mutating sweep.

## Deviations from the plan text

**Step 1's documented command is wrong.** The plan says
`python3 modules/music/scripts/gen_sweep_protection_env.py >> .env`. That
fails: the script imports sentinel-core's `Settings`, which needs pydantic,
absent from system python3. Ran with a venv interpreter instead. The plan's
step-1 command needs correcting.

**Step 4's premise is wrong, and so is T-48-12.** The plan expects an
UNAUTHENTICATED 200 from `/modules/music/healthz`, citing "pf2e precedent".
Core's `APIKeyMiddleware` exempts only `/health`, so the proxied `healthz` is
auth-gated — and pf2e behaves identically (401 without key, 200 with). The
substantive requirement (200 with the correct payload via the Core proxy) is
met. The threat-model note claiming healthz "stays intentionally
unauthenticated" is inaccurate for BOTH modules.

**Step 6 evidence is stronger than a single pass.** An initial live sweep
appeared to pass but had in fact moved nothing at all — see D-2 below. The
recorded PASS is from the sweep run AFTER that defect was fixed, which really
did move 28 files.

## Defects found and fixed during this gate

The live smoke did what unit tests could not — four production defects, all
fixed, released and redeployed before this gate was recorded.

- **D-1 (v0.53.3) — dry-run reported protected paths as proposed moves.**
  The dry-run listed `sentinel/persona.md -> _trash/` — a boot-critical file.
  Live behavior was never at risk (`move_to_trash` raises `ProtectedPathError`
  first), but the planner never consulted `is_protected_path`, so the preview
  advertised moves the system would refuse. Relocations were affected in both
  directions (protected src, and namespace-poisoning dst). Report now carries
  a `## Refused (protected namespace)` section.

- **D-2 (v0.53.4) — live sweeps performed ZERO moves on any local LLM.**
  `_score` scored models via litellm's static CLOUD registry, which has no
  entry for an LM Studio model id, so every local model scored 0 ->
  `probe_classifier_model_ready` False -> `_is_safe()` False before every
  destructive move. A real sweep reported `complete` and moved nothing. This
  predated the gemma switch. `_score` now consults LM Studio's live
  `/api/v0/models/{id}` capabilities for local ids; cloud scoring unchanged;
  fail-closed preserved.

- **D-3 (v0.53.4) — sweeper silence.** A suppressed destructive move logged
  nothing. Now warns per skip plus an aggregate count.

- **D-4 (v0.53.4) — stale sweep status.** `GET /vault/sweep/status` leaked the
  previous run's `topic_moves`/`report_path`, making a zero-move sweep look
  like it moved 22 files. A new sweep now resets both.

## Known issue (NOT fixed — needs a decision)

**The dry-run cannot preview duplicate detection.** The dry-run predicted 0
duplicates; the live sweep trashed 4. Mechanism: dedup compares stored
embeddings, which the dry-run deliberately does not write — so on a vault
whose notes lack embeddings, no duplicate can be detected in preview. The
live run's topic moves write embeddings, enabling dedup in the same pass.

No data was lost — every trashed duplicate records `original_path`, `reason`
(naming the survivor) and `sweep_at`, and all four survivors are in place.
But the dry-run silently reporting `Duplicates→trash proposed: 0` reads as a
promise that no duplicates will be trashed. Same broken-preview contract class
as D-1. The report should at minimum disclose that duplicate detection is not
previewable.

## Verification

- Four venvs green together; `modules/pathfinder` at exact baseline.
- Live: container up, registered, healthz 200, hub-mesh present, and all four
  `music/` notes survived a sweep that really moved 28 files.
- MUS-01 criterion #1 (starts + registers + registry lists `music` with zero
  Core code changes) and MUS-05 + Pitfall 1 both satisfied.
