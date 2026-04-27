---
status: complete
quick_id: 260427-5kl
slug: litellm-helpers-consolidation
date: 2026-04-27
addresses: DRY-H-1, DRY-H-2, DRY-H-3, DRY-H-4 (from .planning/reviews/2026-04-27-dry-audit.md)
verification: passed (12/12 must-haves verified)
---

# Quick Task 260427-5kl: LiteLLM Helpers Consolidation

## Outcome

Pure refactor — DRY violations identified in the 2026-04-27 audit eliminated. No behavior change. Live smoke tests confirm `/message` and `/modules/pathfinder/rule/query` work identically post-refactor.

## What Changed

### H-1 — Strip-prefix consolidation
- Canonical `strip_litellm_prefix(model_str, *, prefixes=_LITELLM_PROVIDER_PREFIXES)` lives in `sentinel-core/app/services/model_selector.py`
- `main.py` and `model_registry.py` define `_ORIGINAL_PREFIXES = ("openai/", "ollama/", "anthropic/")` and pass `prefixes=_ORIGINAL_PREFIXES` to preserve exact pre-refactor 3-prefix behavior
- pathfinder has its own local helper in `resolve_model.py` (single-source within pathfinder)
- Three duplicate implementations collapsed: `_strip_litellm_prefix`, the inline loop in `model_registry.py`, and `resolve_model.py`'s `startswith("openai/")` guard

### H-2 — Cross-container `model_profiles.py`
- Single canonical location: `shared/sentinel_shared/model_profiles.py`
- Old paths deleted: `modules/pathfinder/app/model_profiles.py`, `sentinel-core/app/services/model_profiles.py`
- Both `compose.yml` files declare `additional_contexts: { shared: ../[..]/shared }`
- Both `Dockerfile`s `COPY --from=shared sentinel_shared/ /app/sentinel_shared/`
- 6 source files migrated to `from sentinel_shared.model_profiles import ...`
- Pre-flight `diff -w` byte-equivalence gate confirmed both old copies were whitespace-identical

### H-3 — `ResolvedModel` + `resolve()`
- New dataclass `ResolvedModel(model, profile, api_base)` and `async def resolve(task_kind)` in `modules/pathfinder/app/resolve_model.py`
- 8 pair-construction sites in `routes/{rule,harvest,npc,session}.py` migrated from paired `resolve_model() + resolve_model_profile()` calls to single `resolve()` await
- Old `resolve_model()` and `resolve_model_profile()` exports preserved (additive, non-breaking)
- **Plan deviation:** plan listed 6 sites across rule/harvest/npc; executor's grep surfaced 2 additional sites in `routes/session.py` and migrated them too

### H-4 — `acompletion_with_profile` wrapper
- New module `modules/pathfinder/app/llm_call.py` with `acompletion_with_profile(model, messages, profile, api_base, timeout, **extra)`
- 10 sites in `llm.py` + 1 site in `foundry.py` migrated to use the wrapper
- Both duplicate `_stop_for(profile)` helpers deleted (one in `llm.py`, one in `foundry.py`)
- `litellm.acompletion(` no longer appears in any pathfinder production code (only test mocks)
- **Audit count discrepancy:** audit said 11 sites in llm.py; actual was 10 (one was a docstring reference). Executor used grep as source of truth, not the count.

## Commits (in order)

| Commit | Task | Description |
|--------|------|-------------|
| `b5a90ab` | T1 | refactor(sentinel-core): consolidate strip_litellm_prefix into model_selector |
| `170af5d` | T2 | refactor(pathfinder): add local strip_litellm_prefix helper |
| `ed03ab7` | T3 | feat(pathfinder): add ResolvedModel + resolve() unified entry point |
| `323bcbf` | T4 | refactor(pathfinder): migrate route pair sites to resolve() |
| `52690a6` | T5 | refactor(pathfinder): migrate llm.py acompletion sites to acompletion_with_profile |
| `86eecc6` | T6 | refactor(pathfinder): migrate foundry acompletion + delete duplicate _stop_for |
| `eec5524` | T7 | refactor(pathfinder): promote model_profiles to sentinel_shared + wire additional_contexts |

Merged to main via `chore: merge quick task 260427-5kl litellm helpers consolidation worktree`.

## Verification Results

All 12 must-haves passed:
- Static checks: zero `_strip_litellm_prefix`/`_LITELLM_PROVIDER_PREFIXES_TO_STRIP` in sentinel-core; zero `def _stop_for` in pathfinder; zero stale `from app.model_profiles` imports; exactly one `model_profiles.py` location; 6 `sentinel_shared.model_profiles` import sites
- Container builds: both pf2e-module and sentinel-core rebuild cleanly with `additional_contexts`
- Container starts: clean startup, no ImportError
- Runtime gates: `Context window: 32768 tokens`, `arch 'qwen2' → family 'qwen2'`, `Registered with Sentinel Core`
- Live smoke: `/health` 200, `/message` 200 with real qwen2.5-coder-14b response, `/modules/pathfinder/rule/query` 200 with valid PF2e rule answer

## Notable Deviations

1. **Executor caught 2 missing site references** — plan specified routes/{rule,harvest,npc} but session.py also had paired `resolve_model + resolve_model_profile` calls. Migrated those too. Documented in this summary.
2. **Audit count was off by one** — audit said 11 acompletion sites in llm.py; reality was 10. Executor used grep as source of truth (per the plan's instruction).
3. **Executor did not produce SUMMARY.md** — orchestrator wrote it post-merge.

## Outstanding (separate task)

`.planning/sketches/note-import-and-vault-sweeper.md` captures the next logical task: explicit `:note` subcommand + vault sweeper with auto-classification. Plan after this refactor lands as `/gsd-quick --discuss --research --validate`.
