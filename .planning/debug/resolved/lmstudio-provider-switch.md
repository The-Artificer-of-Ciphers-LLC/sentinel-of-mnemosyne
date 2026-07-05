---
status: resolved
trigger: |
  DATA_START
  2026-07-05 10:03:06    sentinel-of-mnemosyne/pf2e-module      File "/usr/local/lib/python3.12/site-packages/litellm/litellm_core_utils/exception_mapping_utils.py", line 597, in exception_type
  DATA_END
created: 2026-07-05
updated: 2026-07-05
---

# Debug Session: lmstudio-provider-switch

## Symptoms

- **expected:** pf2e-module completes its LLM calls through litellm successfully.
- **actual:** litellm raises a mapped exception at `exception_mapping_utils.py:597` (`exception_type`). The user reports the underlying cause is that the local **LM Studio** endpoint "is not working." The traceback frame shown is litellm re-wrapping the provider-side failure (most consistent with an `APIConnectionError`/`Timeout` from an unreachable local server).
- **error:** `2026-07-05 10:03:06  sentinel-of-mnemosyne/pf2e-module  File ".../litellm/litellm_core_utils/exception_mapping_utils.py", line 597, in exception_type`
- **timeline:** Reproducible every run.
- **reproduction:** Any pf2e-module LLM call routed through litellm to the configured LM Studio endpoint.
- **provider:** Local / self-hosted (LM Studio). **Desired remediation:** switch the provider `api_base` to `http://localhost:52415/v1`.

## Current Focus

```yaml
reasoning_checkpoint:
  hypothesis: >
    The reported litellm exception is the pf2e-module FastAPI *startup* crash-loop
    (not a scattered per-request error). main.py's lifespan() unconditionally calls
    build_rules_index() -> embed_texts() against settings.litellm_api_base with no
    try/except; that value (env LITELLM_API_BASE=http://192.168.0.50:1234/v1, live
    .env) is an unreachable LM Studio host, so the exception propagates out of
    lifespan, ASGI startup fails, and Docker's `restart: unless-stopped` policy
    crash-loops the whole container forever -- matching "reproducible every run"
    and taking down ALL endpoints, not just /rule/query.
    Naively repointing LITELLM_API_BASE to http://localhost:52415/v1 (user's literal
    ask) would NOT fix this: (a) pf2e-module runs inside a Docker container per
    compose.yml, so "localhost" resolves to the container itself, not the host
    running the new endpoint -- must be host.docker.internal:52415 to match the
    existing convention (obsidian_base_url, old LM Studio default); (b) the new
    local endpoint is "exo" (exo-explore/exo), which supports /v1/chat/completions
    but NOT /v1/embeddings -- so a wholesale switch would just trade one startup
    crash (unreachable host) for another (405 on the startup embedding call).
    A third, independent latent bug in app/model_selector.py::select_model compares
    provider-prefixed settings values ("openai/...") against BARE ids from
    {api_base}/models -- never matches -- previously masked because LM Studio only
    ever lists one loaded model, but exo's /v1/models lists its full 120-model
    catalog regardless of which model actually has a running instance, so the
    fallback loaded[0] is arbitrary and will almost certainly 404 "No instance found".
  confirming_evidence:
    - "curl http://192.168.0.50:1234/v1/models -> curl exit 7 (connection refused): confirms LM Studio host is down, matches user's stated root cause"
    - "curl http://localhost:52415/v1/models -> HTTP 200, valid OpenAI-shaped model list, owned_by:'exo', 120 models, all tasks=['TextGeneration'] only"
    - "curl -X POST http://localhost:52415/v1/embeddings -> {'detail':'Method Not Allowed'}; corroborated by open GitHub issue exo-explore/exo#1047 (embeddings not yet supported)"
    - "main.py:208-214 code comment (L-10) explicitly documents the fail-fast design: build_rules_index failure -> SystemExit -> Docker restart-loop"
    - "main.py:223-235 shows the established resilience PATTERN already used elsewhere in the same lifespan() for an equally-optional subsystem (NPC roster cache): try/except Exception, log warning, degrade to empty/None rather than crash"
    - "routes/rule.py:181 already catches RuleQueryNotInitialized and returns HTTP 503 when rules_index is None -- the graceful-degradation destination already exists and is tested"
    - "litellm.get_model_info(model='mlx-community/Qwen3.5-27B-8bit') and model='google/gemma-4-e4b' both raise 'This model isn't mapped yet' -- confirms model_selector.py's scoring step is a no-op for every real id this codebase has ever used, so the broken default/preferences prefix-match was ALWAYS the deciding path, just silently masked by LM Studio's single-model /v1/models list"
    - "exo /state endpoint: only instance with RunnerReady is mlx-community/Qwen3.5-27B-8bit; requesting mlx-community/gemma-4-e4b-it-4bit (present in /v1/models catalog) returned 404 'No instance found' -- proves catalog membership != ready-to-serve on exo"
    - "lsof confirms exo process listening on *:52415 (all interfaces, not just 127.0.0.1) -- host.docker.internal:52415 will reach it from inside a container"
  falsification_test: >
    If the pf2e-module container currently starts and stays up (no restart-loop) despite
    LITELLM_API_BASE pointing at an unreachable host, the startup fail-fast hypothesis
    is wrong and the exception must be a per-request path instead. Not directly
    observable from this checkout (containers run on the operational checkout /Volumes/Mini Me,
    not inspected for live container status in this session) -- flagged as a checkpoint
    item for the user to confirm post-fix via `docker compose logs pf2e-module`.
  fix_rationale: >
    Fix addresses all three root causes together, not just the symptom: (1) repoints
    litellm_api_base to the Docker-reachable form of the new working chat endpoint,
    (2) makes the startup embedding-index build non-fatal so the module actually starts
    and serves the ~25 non-RAG endpoints even though embeddings are currently unavailable
    on any backend, (3) fixes the prefix-comparison bug so LITELLM_MODEL can actually pin
    a real, currently-running exo model instance instead of silently falling through to
    an arbitrary, likely-not-running catalog entry.
  blind_spots: >
    Cannot verify actual chat-completion success end-to-end from this checkout: a manual
    curl against the live 27B-8bit exo model returned HTTP 200 (request accepted) but did
    not complete within 180s (large model, single-request first-token latency on this
    hardware) -- did not confirm full token output. Cannot rebuild/redeploy the operational
    Docker container from this session (that requires the documented dev-checkout-build +
    operational-checkout-recreate flow using the user's own docker access). sentinel-core's
    own lmstudio_base_url has the identical dead-host problem but is explicitly out of scope
    per the orchestrator's task framing (pf2e-module only) -- flagged, not fixed here.
```

- **next_action:** DONE. User approved the deviated values; live .env applied, sentinel-core fixed (config default + fallback constants synced; confirmed no eager-init crash and no analogous model_selector bug existed there), incidental test-recall.py time-bomb defect fixed inline, both test suites green (pathfinder 382 passed / sentinel-core 415 passed, 0 failed each), code committed. Session resolved. Remaining step is the user's own manual container rebuild + redeploy + live end-to-end confirmation (outside this session's reach) — see the calling agent's rebuild instructions.

## Evidence

- timestamp: 2026-07-05 — User confirmed via symptom gathering: LM Studio is not working; wants to switch providers to `http://localhost:52415/v1`; reproducible every run; provider is local/self-hosted.
- timestamp: 2026-07-05 — checked: `modules/pathfinder/app/config.py` — found: `litellm_api_base` default `http://host.docker.internal:1234/v1`; live operational `.env` (`/Volumes/Mini Me/.../sentinel-of-mnemosyne/.env`) overrides via `LITELLM_API_BASE=http://192.168.0.50:1234/v1` and `LITELLM_MODEL=openai/google/gemma-4-e4b` — implication: the env var on the OPERATIONAL checkout is the actual single source of truth driving the live bug, not the dev checkout (which has no `.env`).
- timestamp: 2026-07-05 — checked: reachability of `http://192.168.0.50:1234/v1/models` — found: curl exit 7, connection refused — implication: confirms user's stated root cause (LM Studio down) with direct evidence.
- timestamp: 2026-07-05 — checked: reachability of `http://localhost:52415/v1/models` — found: HTTP 200, OpenAI-shaped response, `owned_by:"exo"`, 120 models, all `tasks:["TextGeneration"]` — implication: new endpoint is up and OpenAI-compatible for chat, confirms it is "exo" not LM Studio.
- timestamp: 2026-07-05 — checked: `POST http://localhost:52415/v1/embeddings` — found: `{"detail":"Method Not Allowed"}`; web search corroborates via open GitHub issue exo-explore/exo#1047 ("Add support for embedding models") — implication: exo cannot serve the rules-engine's embedding calls; any code path depending on embeddings against this host will fail.
- timestamp: 2026-07-05 — checked: `modules/pathfinder/app/main.py` lines 185-218 (lifespan) — found: `build_rules_index()` called with zero exception handling; comment explicitly documents fail-fast-to-SystemExit-to-Docker-restart-loop design (L-10) — implication: this is the actual mechanism producing "reproducible every run"; a wholesale api_base switch to exo would still crash startup (405 instead of connection-refused) unless this is also fixed.
- timestamp: 2026-07-05 — checked: `modules/pathfinder/app/main.py` lines 223-235 — found: an existing, already-accepted resilience pattern (try/except around NPC roster cache load, degrade to empty dict) in the exact same function — implication: precedent exists in this codebase for exactly the fix needed; not introducing a new architectural pattern.
- timestamp: 2026-07-05 — checked: `modules/pathfinder/app/routes/rule.py` lines 161-190 — found: `/rule/query` already catches `RuleQueryNotInitialized` and returns HTTP 503 when `rules_index is None` — implication: the graceful-degradation destination state is already fully supported and tested; no route-layer change needed.
- timestamp: 2026-07-05 — checked: compose.yml networking + `obsidian_base_url`/old `litellm_api_base` defaults — found: both consistently use `host.docker.internal`, never bare `localhost`, for host-reachable services — implication: `http://localhost:52415/v1` (user's literal request) would silently fail to reach the host from inside the container; must be `http://host.docker.internal:52415/v1`.
- timestamp: 2026-07-05 — checked: `lsof -iTCP -sTCP:LISTEN` on the host — found: `exo` process listening on `*:52415` (all interfaces) — implication: `host.docker.internal:52415` will correctly reach it from a container (not bound to loopback-only).
- timestamp: 2026-07-05 — checked: `modules/pathfinder/app/model_selector.py::select_model` + `resolve_model.py` call sites — found: `preferences`/`default` settings values are documented and stored with an `openai/` provider prefix (e.g. `.env.example`'s `LITELLM_MODEL_CHAT=openai/qwen2.5-14b-instruct`), but `select_model` compares them directly against `loaded`, which holds BARE ids from `{api_base}/models` — prefix mismatch means this membership check can never succeed — implication: latent, pre-existing selection bug.
- timestamp: 2026-07-05 — checked: `litellm.get_model_info(model=...)` for both `mlx-community/Qwen3.5-27B-8bit` and the old `google/gemma-4-e4b` — found: both raise `"This model isn't mapped yet"` — implication: the scoring step (`_score`) always yields 0 candidates for every real model id this codebase has ever used; the broken default/preference prefix-match was always the actual deciding path, silently masked because LM Studio's `/v1/models` typically lists only the one model an operator has loaded (so the final arbitrary `loaded[0]` fallback happened to coincidentally be correct).
- timestamp: 2026-07-05 — checked: exo `/state` endpoint — found: only `mlx-community/Qwen3.5-27B-8bit` has `RunnerReady`; requesting `mlx-community/gemma-4-e4b-it-4bit` (present in the `/v1/models` catalog) returned `404 "No instance found"` — implication: exo's catalog (`/v1/models`) lists far more models than are actually running; catalog membership does not imply readiness, unlike LM Studio. `select_model`'s `loaded[0]` fallback is effectively random relative to which model can actually serve a request.
- timestamp: 2026-07-05 — checked: `POST /v1/chat/completions` against `mlx-community/Qwen3.5-27B-8bit` (the one ready instance) — found: HTTP 200 returned immediately (request accepted, connection/protocol layer works); full response body did not arrive within 180s (large 27B/8bit model, first-token latency) — implication: chat plumbing is structurally correct end-to-end; full-response timing/timeout tuning is a separate, hardware-bound concern flagged for the user, not a code defect.
- timestamp: 2026-07-05 — checked: `modules/pathfinder/tests/test_model_selector.py` and `test_resolve_model.py` — found: all existing fixtures use bare (unprefixed) ids consistently in both `loaded` and `preferences`/`default`, so the prefix-mismatch bug was never exercised by the existing suite — implication: safe to fix without touching existing test expectations; new tests needed to cover the real-world prefixed-vs-bare scenario.
- timestamp: 2026-07-05 — checked: `sentinel-core/app/config.py` — found: `lmstudio_base_url` default also `http://host.docker.internal:1234/v1`, and the live `.env`'s `LMSTUDIO_BASE_URL=http://192.168.0.50:1234/v1` is consumed by `sentinel-core`, a separate service — implication: sentinel-core likely has the identical dead-host problem, but the orchestrator explicitly scoped this session to pf2e-module only; flagged for the user's awareness, not fixed here (out of scope, not silently dropped).

## Continuation (2026-07-05, post-checkpoint) — user approved deviated values; sentinel-core fix + live .env edit

- timestamp: 2026-07-05 — checked: live `.env` at `/Volumes/Mini Me/Users/trekkie/projects/sentinel-of-mnemosyne/.env` lines 97-98 — found: verbatim match to the values documented in this file's earlier evidence (`LITELLM_API_BASE=http://192.168.0.50:1234/v1`, `LITELLM_MODEL=openai/google/gemma-4-e4b`) — implication: safe to apply the user-approved 2-line edit exactly as proposed (no STOP-and-report trigger).
- timestamp: 2026-07-05 — checked: `sentinel-core/app/main.py` lifespan, `app/composition.py` (`build_provider_router`, `build_application`, `initialize_startup`), `app/services/model_registry.py`, `app/services/model_selector.py::discover_active_model`, `app/clients/litellm_provider.py::get_context_window_from_lmstudio` — found: EVERY startup call that touches `lmstudio_base_url` already has non-fatal error handling (returns defaults / empty / False / logs a warning) — model registry fetch, active-model discovery, context-window fetch, stop-sequence profile fetch, and the embedding-model-loaded probe are all documented as "non-fatal" / "never raises" in their own docstrings; the one operation that could be slow/failing (`_startup_rebuild` embedding-index rebuild) runs as a fire-and-forget `asyncio.create_task` wrapped in its own try/except, never awaited synchronously by `initialize_startup` — implication: sentinel-core has **no eager-init crash path** analogous to pathfinder's pre-fix `build_rules_index()` — the FastAPI app already starts and stays up regardless of `lmstudio_base_url` reachability. No `_build_rules_index_safely()`-style resilience change is needed or was invented.
- timestamp: 2026-07-05 — checked: `sentinel-core/app/services/model_selector.py::select_model` prefix-comparison logic vs. `.env`/`.env.example` (`MODEL_NAME=gemma-4-e4b-it-mlx` / `google/gemma-4-e4b`, `MODEL_PREFERRED=qwen3.6-35b-a3b`, both dev and operational `.env.example`) — found: unlike pathfinder's convention, sentinel-core's `model_name`/`model_preferred` settings are stored **bare** (no `openai/` prefix) by convention; the `openai/` prefix is added later, only at the litellm call site via `_prefixed()` — implication: the provider-prefix-vs-bare-id mismatch bug fixed in pathfinder's `model_selector.py` does **not** exist in sentinel-core under its own convention; no analogous fix needed (confirmed, not assumed).
- timestamp: 2026-07-05 — checked: full sentinel-core test suite BEFORE any sentinel-core code edit — found: 2 pre-existing failures unrelated to lmstudio/provider config: `tests/test_recall.py::test_recency_order_hot` and `::test_recency_order_is_blend_not_filter`, both asserting on hardcoded absolute date literals (`"2026-06-12"` / `"2026-06-02"`) that `FakeVault.get_recent_sessions()` filters against the REAL wall clock (`datetime.now(timezone.utc)`) via `hot_window_days` — implication: as real calendar time (now 2026-07-05) passed the hardcoded dates' `hot_window_days=30` window, the fixtures silently fell out of range; this is a time-bomb test defect, not a flake — root-caused via direct comparison against the correctly-written sibling test `test_retention_window_excludes_out_of_window_sessions` (same file), which already computes dates relative to `datetime.now(timezone.utc)` at test-run time instead of hardcoding literals. Per project policy (no waving off warnings/errors, no deferring discovered defects), fixed inline: rewrote both failing tests plus a third (`test_retention_window_tunable`, same hardcoded-literal pattern, not yet failing but would break automatically at 30 days past 2026-06-12, i.e. ~2026-07-12) to derive dates from real `datetime.now(timezone.utc)` + `timedelta`, matching the established safe pattern.
- timestamp: 2026-07-05 — checked: `sentinel-core` full test suite AFTER config.py/embeddings.py/composition.py/note_classifier.py edits + the 3 test_recall.py fixes + 3 new regression tests (test_config.py, test_embeddings.py) — found: 415 passed, 12 skipped, 0 failed (was 2 failed / 413 passed / 12 skipped before) — implication: sentinel-core's lmstudio_base_url default change is safe, the incidental time-bomb test defect is fully fixed, and no regressions were introduced.
- timestamp: 2026-07-05 — checked: `modules/pathfinder` full test suite (unchanged this continuation) — found: 382 passed, 0 failed — implication: pathfinder's earlier fix remains stable; nothing in this continuation touched pathfinder code.

## Eliminated

- hypothesis: "Simply setting `LITELLM_API_BASE=http://localhost:52415/v1` fully resolves the reported bug."
  evidence: Would still crash-loop at startup (embeddings unsupported by exo -> `build_rules_index` still raises), and `localhost` is unreachable from inside the pf2e-module Docker container regardless (must be `host.docker.internal`). Confirmed via direct endpoint testing and compose.yml networking review.
  timestamp: 2026-07-05

## Resolution

root_cause: |
  Three compounding issues in modules/pathfinder (pf2e-module), plus one shared
  config default in sentinel-core:
  1. `litellm_api_base` (live .env: LITELLM_API_BASE=http://192.168.0.50:1234/v1) points at
     an unreachable LM Studio host.
  2. `app/main.py`'s `lifespan()` builds the RAG rules-embedding index at startup with NO
     exception handling around `build_rules_index()` -> `embed_texts()`; any failure there
     (unreachable host, or an embeddings-incompatible endpoint) propagates out of `lifespan`,
     crashing FastAPI/ASGI startup entirely and triggering Docker's `restart: unless-stopped`
     crash-loop -- taking down the ENTIRE module (not just RAG), reproducing "every run".
  3. `app/model_selector.py::select_model` compares provider-prefixed settings values
     (`openai/...`) against bare ids from `{api_base}/models`, which never match -- a latent
     bug masked under LM Studio (single-model `/v1/models` list) but actively bug-causing
     against exo (120-model catalog where most entries have no running instance).
  4. `sentinel-core/app/config.py`'s `lmstudio_base_url` default and 3 dead-fallback
     constants shared the identical stale `http://host.docker.internal:1234` value.
     UNLIKE pathfinder, sentinel-core's startup path already wraps every
     `lmstudio_base_url`-dependent call in non-fatal error handling (confirmed by
     direct code read of composition.py / model_registry.py / model_selector.py /
     litellm_provider.py — every one returns a default/empty/False and logs a
     warning rather than raising) — so there was no eager-init crash to fix here,
     only the stale default value itself (chat completions would silently keep
     failing at request time, retrying against a dead host, once actually invoked).
fix: |
  1. `modules/pathfinder/app/config.py`: `litellm_api_base` default -> `http://host.docker.internal:52415/v1`
     (Docker-reachable form of the new local "exo" OpenAI-compatible chat endpoint; NOT bare
     `localhost`, matching this file's existing `host.docker.internal` convention).
  2. `modules/pathfinder/app/main.py`: extracted `_build_rules_index_safely()` helper; lifespan
     now catches embedding-index build failures, logs an ERROR (preserving L-10's operator-
     visibility intent), and leaves `rules_index=None` instead of crashing -- module now starts
     and serves all non-RAG endpoints even when no embeddings backend is available. `/rule/query`
     already returns HTTP 503 via the existing `RuleQueryNotInitialized` handling.
  3. `modules/pathfinder/app/model_selector.py`: `select_model` now bare-normalizes (`openai/`
     prefix stripped) before comparing `preferred`/`default` against `loaded`, so explicit
     model pins actually take effect instead of silently falling through to an arbitrary
     (possibly non-running) catalog entry.
  4. Live operational `.env` (`/Volumes/Mini Me/Users/trekkie/projects/sentinel-of-mnemosyne/.env`,
     not tracked in git) — APPLIED this continuation, user-approved:
     `LITELLM_API_BASE=http://host.docker.internal:52415/v1`,
     `LITELLM_MODEL=openai/mlx-community/Qwen3.5-27B-8bit` (the one exo instance confirmed
     `RunnerReady` via exo's `/state` endpoint at fix time).
  5. `sentinel-core/app/config.py`: `lmstudio_base_url` default -> `http://host.docker.internal:52415/v1`,
     with a comment mirroring pathfinder's T-lmstudio-provider-switch note. Same value also
     synced in 3 dead/defensive fallback constants that only fire when `lmstudio_base_url`
     is falsy (never true in normal operation, but were carrying the stale value):
     `app/clients/embeddings.py::DEFAULT_LMSTUDIO_BASE_URL`, `app/composition.py`'s
     `lmstudio_api_base` fallback in `build_provider_router`, and
     `app/services/note_classifier.py::_resolve_model_for_classification`'s fallback.
     Confirmed NO eager-init crash exists in sentinel-core -- every startup call site
     touching `lmstudio_base_url` (model registry fetch, active-model discovery,
     context-window fetch, stop-sequence profile fetch, embedding-model-loaded probe,
     startup embedding-index rebuild) is already non-fatal by design; no
     `_build_rules_index_safely()`-style resilience change was needed or invented.
     Also confirmed sentinel-core's `model_selector.py::select_model` does NOT have
     pathfinder's provider-prefix-vs-bare-id bug: sentinel-core's own convention
     stores `MODEL_NAME`/`MODEL_PREFERRED` bare (no `openai/` prefix), so the
     comparison against bare `loaded` ids already works correctly. No fix invented
     where none was needed.
  6. Incidental defect found and fixed inline while running the full sentinel-core
     suite (not deferred): `sentinel-core/tests/test_recall.py` had 2 actively-failing
     tests (`test_recency_order_hot`, `test_recency_order_is_blend_not_filter`) plus one
     latent time-bomb (`test_retention_window_tunable`, not yet failing but would break
     ~2026-07-12) — all three hardcoded absolute date literals (`"2026-06-12"` /
     `"2026-06-02"`) that `FakeVault.get_recent_sessions()` filters against the REAL
     wall clock via `hot_window_days`. Rewrote all three to derive dates from
     `datetime.now(timezone.utc)` + `timedelta` at test-run time, matching the
     already-correct sibling pattern in `test_retention_window_excludes_out_of_window_sessions`.
     Unrelated to the lmstudio/provider bug mechanically, but surfaced during this
     session's verification work and fixed per policy (no deferring discovered defects).
verification: |
  Self-verified: exo endpoint reachability + OpenAI-compat shape (curl), embeddings
  unsupported (curl + corroborating GitHub issue), Docker networking requirement
  (compose.yml + lsof), model_selector prefix bug (litellm.get_model_info repro),
  exo instance-readiness gap (exo /state). New unit tests added and run for the
  model_selector fix and the main.py graceful-degradation helper; full pathfinder
  test suite run (382 passed, 0 failures) to confirm no regressions.

  Continuation (post-checkpoint, user-approved): live `.env` lines re-read and
  confirmed byte-for-byte matching this file's documented expectation immediately
  before editing (no STOP-and-report trigger). Two-line edit applied. sentinel-core's
  entire lmstudio_base_url-dependent startup path read in full and confirmed already
  non-fatal (no resilience change invented). sentinel-core's model_selector prefix
  logic read and confirmed NOT affected by the pathfinder-style bug (sentinel-core's
  own convention stores model settings bare). config.py default + 3 fallback constants
  updated for consistency. New regression tests added
  (test_config.py::test_lmstudio_base_url_default_is_docker_reachable,
  test_embeddings.py::test_default_lmstudio_base_url_is_docker_reachable,
  test_embeddings.py::test_embeddings_falls_back_to_default_base_url_when_falsy).
  Full sentinel-core suite run before AND after the fix: before = 2 failed / 413
  passed / 12 skipped (pre-existing, unrelated time-bomb tests); after = 415 passed /
  12 skipped / 0 failed. Full pathfinder suite re-run this continuation: 382 passed,
  0 failed (unchanged).

  NOT yet verified (requires the user's own docker access, outside this session's reach):
    - Real container rebuild + redeploy from the operational checkout for BOTH
      pf2e-module and sentinel-core.
    - A live end-to-end call (e.g. `/npc/say` for pathfinder, a real Discord/`/message`
      turn for sentinel-core) succeeding against the running exo instance post-redeploy.
    See the calling agent's rebuild/redeploy instructions for the exact steps.
files_changed:
  - modules/pathfinder/app/config.py
  - modules/pathfinder/app/main.py
  - modules/pathfinder/app/model_selector.py
  - modules/pathfinder/tests/test_model_selector.py
  - modules/pathfinder/tests/test_main.py (new)
  - sentinel-core/app/config.py
  - sentinel-core/app/clients/embeddings.py
  - sentinel-core/app/composition.py
  - sentinel-core/app/services/note_classifier.py
  - sentinel-core/app/clients/litellm_provider.py (docstring example only)
  - sentinel-core/tests/test_config.py
  - sentinel-core/tests/test_embeddings.py
  - sentinel-core/tests/test_recall.py (3 time-bomb tests fixed — incidental, found during this session)
  - /Volumes/Mini Me/Users/trekkie/projects/sentinel-of-mnemosyne/.env (APPLIED — LITELLM_API_BASE, LITELLM_MODEL)
