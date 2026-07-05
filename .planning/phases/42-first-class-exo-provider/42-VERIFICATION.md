---
phase: 42-first-class-exo-provider
verified: 2026-07-05T19:34:41Z
status: passed
score: 6/6 success criteria verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 5/6
  gaps_closed:
    - "SC-3: When the selected provider is unreachable, ProviderRouter falls back to the other configured local provider (LM Studio ↔ exo) — bidirectional"
  gaps_remaining: []
  regressions: []
---

# Phase 42: First-Class exo Provider Verification Report

**Phase Goal:** Make exo a first-class, independently-configured LLM provider inside the existing Phase 4 multi-provider framework (`AIProvider` Protocol / `LiteLLMProvider` / `ProviderRouter` / `ModelRegistry`), coexisting with LM Studio rather than replacing it. Dedicated exo config (not LMSTUDIO_* reuse), explicit provider selection, LM-Studio↔exo fallback, and removal of the hardcoded exo model default (resolve from config/catalog). Pays down debt from the reactive exo cutover.

**Verified:** 2026-07-05T19:34:41Z
**Status:** passed
**Re-verification:** Yes — after gap closure (fix commit 64d5781)

## Goal Achievement

### Observable Truths (Success Criteria SC-1..SC-6)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | exo configured through dedicated EXO_* settings, independent of LMSTUDIO_* — both configurable simultaneously | ✓ VERIFIED | Unchanged from prior verification. `sentinel-core/app/config.py` lines 71-80: `exo_base_url`, `exo_model` (default `""`, no hardcoded model id), `exo_api_key` are distinct fields; `secret_map` includes `exo_api_key` alongside `lmstudio_api_key`. `lmstudio_base_url`/`lmstudio_api_key` untouched. |
| SC-2 | Active provider selected explicitly via config/env; switching LM Studio ↔ exo requires only a config change, no code edit | ✓ VERIFIED | Unchanged from prior verification. `composition.py` `provider_map` is a plain dict keyed by provider name; `primary = provider_map.get(settings.ai_provider, lmstudio_provider)`. `grep -c 'ai_provider == "exo"' sentinel-core/app/composition.py` → **0**. |
| SC-3 | When the selected provider is unreachable, ProviderRouter falls back to the other configured local provider (LM Studio ↔ exo) — bidirectional | ✓ **VERIFIED (fixed)** | **Re-verified after fix 64d5781** — exo→LM Studio fallback now pairs LM Studio's api_base with LM Studio's own discovered model; reproduced behaviorally; regression test added. See "Reproduction" section below for independent confirmation of both directions plus the regression test result. |
| SC-4 | Hardcoded exo model default removed; model resolves from config/catalog; unavailable/misconfigured model surfaces a clear error, never a guessed catalog[0] | ✓ VERIFIED | Unchanged from prior verification. `exo_model: str = ""` (config.py, comment explicitly rejects a hardcoded id). `discover_via_exo_state()` walks `GET /state`; `select_model()` still refuses to guess `catalog[0]` — raises `ModelSelectorError` when ambiguous and no default. |
| SC-5 | exo OpenAI-compat quirks handled: embeddings paths degrade gracefully (503, no crash) where exo lacks /v1/embeddings; litellm model string uses `openai/` prefix | ✓ VERIFIED | Unchanged from prior verification. `provider_map["exo"]` uses `model_string=f"openai/{resolved_exo_model}"`. `model_registry.py`'s `_fetch_exo()` skips the LM-Studio-only endpoint, non-fatal. pf2e's embeddings path (503 on missing/failed index) untouched. |
| SC-6 | Both sentinel-core and pf2e-module resolve provider+model through unified configuration — no module hardcodes a chat endpoint/model | ✓ VERIFIED | Unchanged from prior verification. `grep -rn acompletion_with_profile modules/pathfinder/app/` → empty. All former direct-litellm chat call sites now route through `SentinelCoreClient.complete()` → `POST /provider/complete`. |

**Score:** 6/6 success criteria fully verified.

### Fix Verification (SC-3)

**Fix commit:** `64d5781`

**Code change confirmed by direct read:**
- `sentinel-core/app/services/model_selector.py`: `discover_active_model` was factored into a shared private `_discover_model_for_provider(settings, http_client, *, provider, base_url)`. A new public `discover_lmstudio_model(settings, http_client)` resolves LM Studio's own model **unconditionally** (`provider="lmstudio"`, `base_url=settings.lmstudio_base_url`), independent of `settings.ai_provider` — mirroring `discover_via_exo_state()`'s existing unconditional independence.
- `sentinel-core/app/composition.py` (lines 137-149): the `lmstudio_model_str` used to build `provider_map["lmstudio"]` is now produced by `await discover_lmstudio_model(settings, http_client)` instead of the ai_provider-keyed `discover_active_model(...)`. Inline comment explicitly documents the SC-3 rationale.
- `sentinel-core/tests/test_composition.py`: new regression test `test_exo_primary_lmstudio_fallback_resolves_lmstudios_own_model_with_auto_discover` uses `model_auto_discover=True` (the production default) with distinct mocked LM Studio `/v1/models` and exo `/state` responses, and asserts the LM Studio provider_map entry resolves LM Studio's own model, keyed by `api_base` (not `model_string`) so a model-string collision can't hide the regression.

**Independent behavioral reproduction** (not just trusting the SUMMARY/test — re-derived directly against `build_provider_router()` in a standalone script, mocking LM Studio `/v1/models` → `lmstudio-real-model` and exo `/state` → `mlx-community/EXO-MODEL`, with `model_auto_discover=True`):

```
Direction 1: ai_provider="exo", ai_fallback_provider="lmstudio"
  primary  (exo):      model_string=openai/mlx-community/EXO-MODEL   api_base=http://exo.test/v1
  fallback (lmstudio): model_string=openai/lmstudio-real-model       api_base=http://lmstudio.test/v1
  -> LM Studio fallback now correctly pairs its own api_base with its own model (previously: openai/mlx-community/EXO-MODEL — WRONG, now fixed)

Direction 2: ai_provider="lmstudio", ai_fallback_provider="exo"  (regression check — reverse direction, previously working)
  primary  (lmstudio):  model_string=openai/lmstudio-real-model       api_base=http://lmstudio.test/v1
  fallback (exo):       model_string=openai/mlx-community/EXO-MODEL   api_base=http://exo.test/v1
  -> No regression: exo fallback still resolves its own model correctly.
```

Both directions now correctly pair each provider's own api_base with that same provider's own discovered model — the bidirectional fallback promised by SC-3 is achieved.

**Test evidence:**
- `cd sentinel-core && .venv/bin/python -m pytest -q tests/test_composition.py` → **14 passed** (includes the new regression test).
- Full suite: `cd sentinel-core && .venv/bin/python -m pytest -q` → **448 passed, 12 skipped** — matches the expected count, no new failures, no warnings surfaced (re-ran with `-W error::DeprecationWarning` to force warning visibility — still clean).

No debt markers (`TBD`/`FIXME`/`XXX`) found in the touched files (`model_selector.py`, `composition.py`, `test_composition.py`).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sentinel-core/app/config.py` | exo_* Settings fields + secret_map entry | ✓ VERIFIED | Unchanged. |
| `sentinel-core/app/services/provider_router.py` | `_FALLBACK_TRIGGERS` includes `litellm.NotFoundError` | ✓ VERIFIED | Unchanged. |
| `sentinel-core/app/state.py` | `RouteContext.ai_provider` field | ✓ VERIFIED | Unchanged. |
| `sentinel-core/app/composition.py` | table-driven active_model/provider_map/fallback/stop-seq | ✓ VERIFIED | LM Studio provider_map entry now built from `discover_lmstudio_model()` — independent of active provider. Gap closed. |
| `sentinel-core/app/services/model_selector.py` | `discover_via_exo_state` + generalized base_url resolution + independent LM Studio discovery | ✓ VERIFIED | `discover_lmstudio_model()` added, shares `_discover_model_for_provider()` pipeline with `discover_active_model()`. |
| `sentinel-core/app/services/model_registry.py` | exo context-window branch | ✓ VERIFIED | Unchanged. |
| `sentinel-core/app/routes/provider.py` | `POST /provider/complete` route | ✓ VERIFIED | Unchanged. |
| `shared/sentinel_client.py` | `SentinelCoreClient.complete()` | ✓ VERIFIED | Unchanged. |
| `modules/pathfinder/app/llm.py`, `foundry.py`, `pf_npc_extract.py` | migrated chat call sites | ✓ VERIFIED | Unchanged. |
| `modules/pathfinder/app/config.py` | chat-only litellm config removed, embeddings config retained | ✓ VERIFIED | Unchanged. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `litellm.NotFoundError` | `_FALLBACK_TRIGGERS` only | provider_router.py | ✓ WIRED | Unchanged. |
| `RouteContext.ai_provider` | `graph.ai_provider` | `initialize_startup()` | ✓ WIRED | Unchanged. |
| `provider_map["exo"]` | `resolved_exo_model` (independent `/state` discovery) | composition.py | ✓ WIRED | Unchanged — always correctly discovered regardless of active provider. |
| `provider_map["lmstudio"]` | `lmstudio_model_str` (independent `discover_lmstudio_model()`) | composition.py lines 137-149 | ✓ **WIRED (fixed)** | Now unconditionally discovers LM Studio's own `/v1/models`, regardless of `settings.ai_provider`. Reproduced behaviorally above. |
| pf2e `llm.py`/`foundry.py`/`pf_npc_extract.py` | `SentinelCoreClient.complete()` → `POST /provider/complete` | HTTP, X-Sentinel-Key | ✓ WIRED | Unchanged. |
| `POST /provider/complete` | `ctx.ai_provider.complete()` | routes/provider.py | ✓ WIRED | Unchanged. |
| `provider_router.py` | `litellm.acompletion` (vendor call) | — | ✓ CONFIRMED ABSENT | Unchanged. |

### Anti-Patterns Found

None blocking. No `TBD`/`FIXME`/`XXX` unresolved markers in the fix's touched files (`model_selector.py`, `composition.py`, `test_composition.py`).

### Requirements Coverage

No REQ-IDs are assigned to this phase (RESEARCH.md states "No REQ-IDs assigned yet for Phase 42"; ROADMAP.md lists `Requirements: TBD`). Acceptance is tracked via ROADMAP.md Success Criteria SC-1..SC-6, all now verified.

### Human Verification Required

None required — the SC-3 fix was reproduced and confirmed programmatically (independent behavioral reproduction against the real `build_provider_router()` function, plus a passing regression test and a clean full-suite run).

### Gaps Summary

No gaps remain. The single gap from the prior verification (SC-3's exo→LM Studio fallback direction pairing LM Studio's api_base with exo's discovered model under `model_auto_discover=True`) has been closed by commit `64d5781`, which gives `provider_map["lmstudio"]`'s model resolution the same independent, unconditional discovery treatment the exo entry already had. Independently reproduced both fallback directions against the live object graph: each now correctly pairs its own api_base with its own discovered model. `test_composition.py` (14/14) and the full suite (448 passed, 12 skipped) are green with no warnings.

---

*Verified: 2026-07-05T19:34:41Z*
*Verifier: Claude (gsd-verifier)*
