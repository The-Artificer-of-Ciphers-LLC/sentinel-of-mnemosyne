# Phase 42: First-Class exo Provider - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-05
**Phase:** 42-first-class-exo-provider
**Areas discussed:** Provider modeling, Fallback semantics, Model resolution, pf2e-module routing, Migration scope, No-instance behavior, Embeddings sequencing

---

## Provider modeling

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated `exo` type | exo as its own provider_map key mirroring ollama/llamacpp pattern | |
| Generic `openai_compatible` type | One parametrized OpenAI-compatible type; exo (and LM Studio) become configs of it | ✓ |
| Keep exo in lmstudio slot | Leave the debug-time hack | |

**User's choice:** Generic `openai_compatible` type.
**Notes:** More reusable end-state; the more ambitious of the two viable options.

## Migration scope (follow-up to Provider modeling)

| Option | Description | Selected |
|--------|-------------|----------|
| exo now, LM Studio later | Add generic type, wire exo, leave working lmstudio path untouched this phase | |
| Unify both now | Migrate LM Studio onto the generic type in this phase too | ✓ |

**User's choice:** Unify both now.
**Notes:** Flagged — puts the currently-working LM Studio chat path in the blast radius; plan must include LM Studio regression coverage.

## Fallback semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Generalize + add NotFound trigger | Any provider as fallback; NotFoundError/404 triggers fallback alongside ConnectError/Timeout | ✓ |
| Generalize provider, keep ConnectError-only | exo↔lmstudio allowed, but 404 still hard-errors | |
| No fallback changes | exo primary, no cross-fallback | |

**User's choice:** Generalize + add NotFound trigger.
**Notes:** exo's real failure mode is a 404, so ConnectError-only fallback would never fire for it.

## Model resolution (exo)

| Option | Description | Selected |
|--------|-------------|----------|
| Pin exo_model + skip auto-discover | exo_model authoritative; no /v1/models discovery | |
| Exo-aware discovery via /state | Auto-detect exo's loaded instance via GET /state | ✓ |
| Reuse model_auto_discover | Keep discovery against /v1/models | |

**User's choice:** Exo-aware discovery via /state.
**Notes:** /v1/models lists ~120 non-serveable ids (root cause of exo-model-notfound-502); /state reports the actually-loaded instance.

## No-instance behavior (follow-up to Model resolution)

| Option | Description | Selected |
|--------|-------------|----------|
| Fallback, else clear error | Zero instances → fallback per fallback decision; else clear "no loaded model" error | ✓ |
| Request configured model to trigger load | Send configured model to force on-demand load | |
| Clear error only | Surface error, no fallback/auto-load | |

**User's choice:** Fallback, else clear error. Never guess a model / never pick catalog[0].

## pf2e-module routing

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated exo vars, keep independent | pf2e keeps own litellm config, cleaned up | |
| Route pf2e LLM calls through sentinel-core | pf2e delegates to core's provider layer | ✓ |
| Core only — defer pf2e | Phase 42 touches core only | |

**User's choice:** Route pf2e through sentinel-core.
**Notes:** User clarified the north-star design: *"everything goes through the sentinel (hence the name) but something drifted and put it in pf2e. pf2e is supposed to handle the local logic and hand off to sentinel."* pf2e's direct LLM config is drift being corrected. Asked to explain embeddings (see below).

## Embeddings sequencing

| Option | Description | Selected |
|--------|-------------|----------|
| Split: chat handoff now, embeddings = Phase 43 | Phase 42 = providers + chat handoff; Phase 43 = embeddings + backend | ✓ |
| All in Phase 42 | chat + embeddings handoff + embeddings backend in one phase | |
| Chat handoff only, embeddings unscoped | No committed follow-up | |

**User's choice:** Split — chat handoff in Phase 42, embeddings handoff + non-exo embeddings backend in Phase 43.
**Notes:** exo has no /v1/embeddings (405), so embeddings need a separate backend decision. The split also isolates the fix for core's own Phase-40 semantic recall (also broken against exo) into Phase 43. Phase 43 added to ROADMAP.md.

---

## Claude's Discretion

- Exact `openai_compatible` config schema / field names.
- Shape of the sentinel-core provider-completion endpoint that pf2e-module calls for chat.
- How `/state` discovery feeds `model_selector.select_model()`.

## Deferred Ideas

- **Phase 43 — Embeddings Through Sentinel:** pf2e embeddings/RAG retrieval handed off to core + non-exo embeddings backend wired; restores pf2e `:pf rule` RAG index and core's Phase-40 semantic recall. Added to ROADMAP.md.
