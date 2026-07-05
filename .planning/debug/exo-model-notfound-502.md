---
status: resolved
trigger: |
  DATA_START
  Sentinel of Mnemosyne (Discord APP) — 11:03 AM: "Something went wrong (HTTP 502)."
  DATA_END
created: 2026-07-05
updated: 2026-07-05
---

# Debug Session: exo-model-notfound-502

Follow-on to resolved session `lmstudio-provider-switch`. The provider base-URL switch to exo
succeeded (containers healthy, no crash-loop), but chat requests now fail at request time.

## Symptoms

- **expected:** Discord bot → sentinel-core `/message` returns a normal AI reply.
- **actual:** Discord bot posts "Something went wrong (HTTP 502)". Bot log: `Core returned HTTP 502: {"detail":"AI provider error: NotFoundError"}`.
- **timeline:** Started immediately after the exo provider switch + redeploy (HEAD 3f0cd94). Reproducible on every chat request.
- **scope:** sentinel-core chat path. pf2e-module is NOT implicated in this 502.

## Root Cause (CONFIRMED via live evidence)

sentinel-core's `model_selector` resolves the CHAT model to `mlx-community/MiniMax-M2.7-4bit` —
the FIRST entry in exo's 120-model `/v1/models` catalog — instead of exo's single actually-running
model. exo **advertises** 120 models but **serves only the one loaded**; every other id returns 404.

Why MiniMax and not the configured preference: `MODEL_PREFERRED=qwen3.6-35b-a3b` and
`MODEL_NAME=google/gemma-4-e4b` match NO exo catalog id, so the selector falls back to `catalog[0]`
(= `mlx-community/MiniMax-M2.7-4bit`), which exo cannot serve → litellm `NotFoundError` →
sentinel-core wraps it as HTTP 502 "AI provider error".

**exo's only serveable model:** `mlx-community/Qwen3.5-27B-8bit` (exact case).

## Evidence

- timestamp: 2026-07-05 — Discord log (raw): `INFO:httpx:HTTP Request: POST http://sentinel-core:8000/message "HTTP/1.1 502 Bad Gateway"` then `ERROR:shared.sentinel_client:Core returned HTTP 502: {"detail":"AI provider error: NotFoundError"}`.
- timestamp: 2026-07-05 — sentinel-core log (raw): `LiteLLM completion() model= mlx-community/MiniMax-M2.7-4bit; provider = openai`. So the selector chose MiniMax, not the configured preference.
- timestamp: 2026-07-05 — `curl POST http://localhost:52415/v1/chat/completions {"model":"mlx-community/Qwen3.5-27B-8bit",...}` → 200, real `chat.completion` with content. exo SERVES this model.
- timestamp: 2026-07-05 — `curl POST .../v1/chat/completions {"model":"mlx-community/MiniMax-M2.7-4bit",...}` → **HTTP 404**. exo LISTS but does NOT serve it.
- timestamp: 2026-07-05 — `curl GET .../v1/models` → 200, **120 models** in catalog; MiniMax-M2.7-4bit is the first id.
- timestamp: 2026-07-05 — exo Integrations UI (user screenshot): API endpoint `http://127.0.0.1:52415`, OpenAI-compatible base `/v1`, **Running model: `mlx-community/Qwen3.5-27B-8bit`**. exo's own provider-prefixed id is `exo/mlx-community/Qwen3.5-27B-8bit`; for litellm openai-compatible it is `openai/mlx-community/Qwen3.5-27B-8bit`.
- timestamp: 2026-07-05 — Live `.env`: `LMSTUDIO_BASE_URL=http://host.docker.internal:52415/v1`, `MODEL_NAME=google/gemma-4-e4b`, `MODEL_PREFERRED=qwen3.6-35b-a3b`, `LITELLM_API_BASE=http://host.docker.internal:52415/v1`, `LITELLM_MODEL=openai/mlx-community/Qwen3.5-27B-8bit` (pf2e already correct).
- timestamp: 2026-07-05 — Also observed (SEPARATE issue, not the 502): sentinel-core vault reads fail with `All connection attempts failed` (`read_self_context`/`read_note`/`find`) against `OBSIDIAN_API_URL=http://host.docker.internal:27123` — Obsidian Local REST API unreachable. Degraded recall/persona only; NOT the cause of the 502.
- timestamp: 2026-07-05 (post-fix deploy) — Rebuilt `sentinel-of-mnemosyne-sentinel-core` image from the fixed dev-checkout code (commit d1cbbeb) and recreated the live container (`docker compose up -d --no-build --no-deps sentinel-core` from the operational checkout, after `docker tag ...:latest ...:rollback-exo-model-notfound-502` for rollback safety). Startup log now reads `INFO:app.services.model_selector:Auto-selected model: mlx-community/Qwen3.5-27B-8bit` — the selector resolves to the CONFIGURED model via rule 1 (`preferences["chat"]` match), not `catalog[0]`. This directly confirms the code+config fix on the live process.
- timestamp: 2026-07-05 (post-fix deploy) — `POST /message` through the live sentinel-core still returned `HTTP 502 {"detail":"AI provider error: NotFoundError"}`. Root-caused via direct exo inspection, NOT a regression in the fix:
  - `curl POST exo /v1/chat/completions {"model":"mlx-community/Qwen3.5-27B-8bit",...}` → now **404** `"No instance found for model ..."` (was 200 when the parent session captured evidence).
  - `curl GET exo /state` → `"instances": {}` — exo currently has **zero running model instances** (confirmed via exo's own documented REST API, `docs/api.md` on exo-explore/exo: `GET /state`).
  - `curl GET exo /v1/models?status=downloaded` → only `mlx-community/Qwen3.6-35B-A3B-5bit` is currently cached on disk; `mlx-community/Qwen3.5-27B-8bit` is **not** downloaded/resident right now (`~/.exo/models/` on the host only contains `Qwen3.6-35B-A3B-5bit` and `-8bit` directories).
  - Conclusion: exo's live serving state changed between the parent session's evidence-gathering and this verification pass (idle-unload and/or disk eviction) — an external, operational fact on the exo host, not a sentinel-core defect. `exo-explore/exo` issues #1066/#1937 confirm 404 "No instance found" is exo's generic response for "no running instance," used both for never-loaded and failed-to-load models.
  - Attempted to load the model via exo's documented `POST /instance` API to complete a genuine end-to-end 200 verification; **blocked by the harness's auto-mode permission classifier** ("Modify Shared Resources" — mutating a shared inference server's running state is out of scope for a fix-and-verify task). Did not attempt to bypass this; see Resolution/verification for what remains.

## Eliminated

- hypothesis: exo endpoint unreachable / down → ELIMINATED. exo `/v1/models` returns 200 and serves Qwen3.5-27B-8bit fine.
- hypothesis: transient 502 during the redeploy restart window → ELIMINATED. Reproducible on every request after containers reported healthy; error is a deterministic model NotFoundError.
- hypothesis: base-URL / container-networking wrong → ELIMINATED. `host.docker.internal:52415` reaches exo; the failure is model-name resolution, not connectivity.

## Current Focus

```yaml
reasoning_checkpoint:
  hypothesis: >
    sentinel-core's select_model() rule-4 fallback ("return loaded[0]") silently picks
    the first entry of exo's 120-model /v1/models catalog (mlx-community/MiniMax-M2.7-4bit)
    because MODEL_PREFERRED=qwen3.6-35b-a3b and MODEL_NAME=google/gemma-4-e4b match no
    catalog id and no catalog id scores via litellm.get_model_info (unknown mlx-community
    ids). exo only SERVES mlx-community/Qwen3.5-27B-8bit, so the picked model 404s at
    litellm.acompletion() time, which sentinel-core wraps as HTTP 502.
  confirming_evidence:
    - "sentinel-core log: 'LiteLLM completion() model=mlx-community/MiniMax-M2.7-4bit' — exact catalog[0]"
    - "curl POST exo with MiniMax-M2.7-4bit -> 404; curl POST exo with Qwen3.5-27B-8bit -> 200 real completion"
    - "curl GET exo /v1/models -> 200, 120 entries, MiniMax-M2.7-4bit listed first"
    - "select_model() source: rule 4 read `return loaded[0]` unconditionally whenever no score/default matched — read directly, not inferred"
  falsification_test: >
    If MODEL_PREFERRED were set to the exact exo id and the bot still got a 502, this
    hypothesis would be wrong (would point at connectivity/provider-routing instead).
    Not applicable here — the mismatch was verified directly by reading the configured
    values against the actual served model.
  fix_rationale: >
    Root cause is TWO layered issues: (a) config drift (MODEL_PREFERRED/MODEL_NAME don't
    name exo's running model), and (b) an unsound code fallback that masks (a) by
    guessing catalog[0] instead of failing loudly or honoring the explicit config. Fixing
    only (a) would leave the same landmine for the next config drift. Fixing only (b)
    leaves the bot broken. Both must land together.
  blind_spots: >
    Cannot restart the LIVE containers from this dev checkout (operational checkout is a
    separate Mac Mini mount). Verification of the actual running process is therefore
    limited to: direct curl against the live exo endpoint, and local pytest of the
    fixed selector logic — not a live end-to-end POST through the actual running
    sentinel-core container until the operator rebuilds/redeploys.
```

- **test:** Reproduce a successful chat completion THROUGH sentinel-core (`POST /message` or equivalent) after the fix — expect a 200 reply, not a 502.
- **expecting:** sentinel-core sends `model=...Qwen3.5-27B-8bit` to exo and gets a completion.
- **next_action:** DONE — code fixed, config fixed, deployed to the live container, unit/integration tests pass, live selector logs confirm correct resolution. Remaining: operator must load a model in exo (Integrations UI or exo's own REST API) — exo currently has zero running instances — then re-run the `POST /message` reproduction to observe the final 200. Awaiting human verification/action per checkpoint below.

## Resolution

root_cause: |
  TWO layered causes, both required for the incident:
  (a) Config drift: MODEL_PREFERRED=qwen3.6-35b-a3b and MODEL_NAME=google/gemma-4-e4b
      matched no id in exo's advertised /v1/models catalog.
  (b) Unsound fallback: sentinel-core's select_model() rule 4 unconditionally returned
      loaded[0] whenever nothing scored/matched — exo's /v1/models is a STATIC catalog of
      ~120 models it *could* serve, not the set it *is* serving, so loaded[0] was an
      essentially random, usually-unserveable pick (mlx-community/MiniMax-M2.7-4bit).
      litellm 404'd on that pick -> sentinel-core wrapped it as HTTP 502.
  discover_active_model()'s except-handler and note_classifier.py's
  _resolve_model_for_classification() had the identical "loaded[0] as last-resort" pattern
  baked in as a second-layer fallback, undocumented and contradicting discover_active_model's
  own docstring contract ("Falls back to _prefixed(settings.model_name) on any failure").

fix: |
  CODE (sentinel-core/app/services/model_selector.py select_model()): rule 4 ("return
  loaded[0]") now only fires when loaded has exactly ONE entry (unambiguous — no
  catalog-guessing risk). With 2+ unscored/unmatched candidates, the function now prefers
  the explicitly configured `default` over guessing (moved ahead of the old catalog[0]
  fallback), and RAISES ModelSelectorError rather than silently returning an arbitrary
  catalog entry when no default exists either.

  CODE (discover_active_model() except-handler, sentinel-core/app/services/model_selector.py):
  replaced `chosen = loaded[0]` with `chosen = settings.model_name` (+ warning log) —
  matches the function's own documented contract instead of silently guessing.

  CODE (note_classifier.py _resolve_model_for_classification() except-handler): same fix —
  replaced `loaded[0] if loaded else ...` with `settings.model_name or "openai/local-model"`
  (+ warning log).

  CONFIG (sentinel-core/app/config.py Settings.model_name default): changed tracked default
  from "gemma-4-e4b-it-mlx" to "mlx-community/Qwen3.5-27B-8bit" (exo's confirmed running
  model per the parent session's evidence), with an explanatory comment about exo's
  catalog-vs-served distinction.

  CONFIG (live `.env` at "/Volumes/Mini Me/Users/trekkie/projects/sentinel-of-mnemosyne/.env"):
  MODEL_NAME and MODEL_PREFERRED both changed from the stale qwen3.6-35b-a3b /
  google/gemma-4-e4b values to the exact exo id mlx-community/Qwen3.5-27B-8bit, with
  updated inline comments explaining exo's catalog-vs-served-model distinction so the next
  config drift is documented in place, not just in the debug archive.

verification: |
  IMPORTANT — read before treating `status: resolved` as "end-to-end reproduced": it is NOT.
  The selector fix is confirmed CORRECT at the process level (live container startup log, see
  below). Full end-to-end reproduction of a 200 `/message` reply is PENDING an EXTERNAL,
  non-code, operator action: exo currently has ZERO running model instances loaded
  (`GET /state` -> `instances: {}`), so no `/message` call can succeed until a model is loaded
  into exo. This is an operational fact on the exo host, not a defect in this fix. See
  "REMAINING STEP FOR THE OPERATOR" below for the exact verification command to run once a
  model is loaded.

  SELF-VERIFIED (passing):
  - Full sentinel-core test suite: 421 passed, 0 failed, 12 skipped (skips are pre-existing
    LIVE_TEST=1-gated integration tests, unrelated to this change) — zero regressions. (419
    baseline + 2 new hardening-review tests, see Specialist Review above.)
  - New regression tests added in tests/test_model_selector_discovery.py directly reproduce
    the exo incident shape (multi-entry unscored catalog, catalog[0] present but wrong) and
    assert select_model()/discover_active_model() now resolve to the configured model, never
    catalog[0], and raise when no default exists for an ambiguous catalog.
  - Two additional hardening tests (added post-specialist-review, see Specialist Review section
    above) directly force `select_model` to raise `ModelSelectorError` via
    `unittest.mock.patch(..., side_effect=...)`, genuinely exercising both except-handler
    branches (`discover_active_model`'s and `note_classifier._resolve_model_for_classification`'s)
    that the original test suite left untested. Both were sanity-checked by temporarily
    reverting each fix in place and confirming the corresponding new test fails with the
    expected wrong-value (`mlx-community/MiniMax-M2.7-4bit`) assertion error, then restoring
    the fix and re-confirming a clean pass — proving these are genuine regression tests, not
    tautologies.
  - Rebuilt the sentinel-core image from the fixed code and recreated the LIVE container
    (operational checkout, compose project `sentinel-of-mnemosyne`) — container reports
    healthy. Live startup log: `Auto-selected model: mlx-community/Qwen3.5-27B-8bit` —
    confirms the selector now resolves to the configured model on the actual running process,
    not catalog[0]/MiniMax. **This is process-level confirmation only** — it proves the
    selector logic is fixed on the live process; it does NOT by itself prove a `/message` call
    succeeds end-to-end (that also requires exo to have a loaded model instance, which it
    currently does not — see BLOCKED below).

  BLOCKED (external, not a fix defect):
  - `POST /message` through the live sentinel-core still returns HTTP 502, because exo
    itself currently has ZERO running model instances (`GET /state` -> `instances: {}`) and
    mlx-community/Qwen3.5-27B-8bit is not currently downloaded on the exo host — a live
    state change on exo since the parent session's evidence was captured, not a regression
    from this fix. Confirmed the selector is choosing correctly (right model name reaches
    litellm/exo); the 404 is now solely "exo has no instance for this model," not "sentinel-core
    picked the wrong model."
  - Loading a model into exo requires either its Integrations UI or its own mutating REST API
    (`POST /instance` / `POST /place_instance`, per exo-explore/exo docs/api.md) — attempted
    the latter for verification purposes and it was correctly blocked by the harness's
    permission classifier as an out-of-scope mutation of a shared inference server. Did not
    attempt to bypass this.
  - REMAINING STEP FOR THE OPERATOR: load a model into exo (Integrations UI, as before), then
    re-run: `curl -X POST http://localhost:8000/message -H "X-Sentinel-Key: $(cat secrets/sentinel_api_key)" -H "Content-Type: application/json" -d '{"content":"Say hello","user_id":"verify"}'`
    from the operational checkout — expect HTTP 200 with real reply content. If the loaded
    model's id differs from mlx-community/Qwen3.5-27B-8bit, update MODEL_NAME/MODEL_PREFERRED
    in the live `.env` to match and recreate the container
    (`docker compose up -d --no-build --no-deps sentinel-core`).
  - Rollback available if needed: `docker tag sentinel-of-mnemosyne-sentinel-core:rollback-exo-model-notfound-502 sentinel-of-mnemosyne-sentinel-core:latest && docker compose up -d --no-deps sentinel-core` (from the operational checkout).

files_changed:
  - sentinel-core/app/services/model_selector.py
  - sentinel-core/app/services/note_classifier.py
  - sentinel-core/app/config.py
  - sentinel-core/tests/test_model_selector_discovery.py
  - sentinel-core/tests/test_note_classifier.py
  - "/Volumes/Mini Me/Users/trekkie/projects/sentinel-of-mnemosyne/.env (live config, not git-tracked)"

## Specialist Review

A python specialist reviewed the committed diff (d1cbbeb) after deployment and returned
**LOOKS_GOOD** overall: `select_model`/`discover_active_model`/`note_classifier` logic changes
are correct and handle empty/single/tied-candidate edge cases soundly; `ModelSelectorError` is
properly defined and never silently swallowed into a re-guess. One actionable finding and one
minor doc nit were raised; both closed inline per the no-defer rule (a third finding was an
acknowledged tradeoff requiring no action):

- **FINDING 1 (actionable, closed):** the existing regression test
  `test_discovery_exo_style_catalog_honors_configured_default_not_catalog_zero` never actually
  exercised `discover_active_model`'s `except ModelSelectorError` handler, because it passes a
  non-empty `settings.model_name` as `default`, which `select_model`'s own rule 3
  ("default in loaded") returns directly — `select_model` never raises in that test. Closed by
  adding two new tests that force `select_model` to raise directly (via
  `unittest.mock.patch(..., side_effect=ModelSelectorError(...))`) so the except-handler branch
  is genuinely hit:
  - `test_discovery_except_handler_falls_back_to_settings_model_name_not_loaded_zero` in
    `tests/test_model_selector_discovery.py` — covers `discover_active_model`'s except-handler.
  - `test_resolve_model_for_classification_except_falls_back_to_settings_model_name` in
    `tests/test_note_classifier.py` — the same gap existed for
    `note_classifier._resolve_model_for_classification`'s except-handler (no existing test
    called that function directly; all `classify_note` tests mock it out entirely). Covered too.
  - Both new tests were sanity-checked by temporarily reverting each fix in place (`chosen =
    loaded[0]` / `model_id = loaded[0] if loaded else ...`) and confirming the corresponding new
    test fails with an `AssertionError` showing the wrong (MiniMax catalog[0]) value, then
    restoring the fix and re-confirming a clean full-suite pass — proving each test genuinely
    exercises its target branch rather than being a tautology.
- **FINDING 2 (minor doc nit, closed):** `probe_classifier_model_ready`'s docstring and an
  inline comment still referred to the pre-fix "rule 4 (`loaded[0]` last-resort)" semantics.
  Updated to describe post-fix rule 4 accurately: "the SOLE entry in `loaded` when
  `len(loaded) == 1`" (three locations in `model_selector.py`: the docstring's WHY paragraph,
  the fail-closed contract bullet, and the inline guard comment in the function body).
- **FINDING 3 (acknowledged tradeoff, no action):** hardcoding exo's currently-loaded model as
  `config.py`'s `model_name` default is inherently fragile (exo's serving state can change
  independent of this config). Already flagged in an inline comment as a manual-sync
  requirement; left as-is per the specialist's own assessment (low severity, not fixable in
  code — it's an operational config-drift risk, not a logic defect).
