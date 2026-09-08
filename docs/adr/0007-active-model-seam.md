# ADR-0007 — The Active model is a seam resolved at request time, not three scalars pinned at startup

**Status:** accepted (design converged in architecture review; implementation staged — see Sequencing)
**Date:** 2026-09-07
**Related:** ADR-0001 (Sentinel persona source), ADR-0002 (Vault seam location), ADR-0004 (Semantic recall)

## Context

The local model had no module. Its identity and capabilities existed as three loose scalars —
`model_name`, `context_window`, `stop_sequences` — resolved once by `build_provider_router`
(`composition.py:115-272`, ~158 lines making three separate HTTP fetches to the same backend),
bundled into a `ProviderRouterBundle`, and pinned onto `app.state` for the process lifetime.

The failure this produces was observed live on 2026-09-07: LM Studio was serving
`qwen/qwen3.8-27b` (arch `qwen3_5`, mlx, `loaded_context_length` 119552, `capabilities: ["tool_use"]`)
while the container — up since 2026-09-05 — was still naming `google/gemma-4-31b` on every
`litellm.acompletion` call, with gemma's `<end_of_turn>` stop sequence and a 262144-token context
window. Swapping the model in LM Studio is invisible to a running process.

Two defects were found in the same surface and are fixed as part of this work rather than tracked
separately:

- **The chat path never sent stop sequences.** `build_message_request` populated
  `MessageRequest.stop_sequences`; `MessageProcessor.process()` called
  `self._ai_provider.complete(messages)` with no `stop=`. `req.stop_sequences` was read by nothing.
  The only stop-sequence test (`test_llm_call_shared.py:27`) covers
  `sentinel_shared.llm_call.acompletion_with_profile`, which the chat path does not use. Note that
  `response_anomaly.py` was built to detect leaked turn delimiters in output — the characteristic
  signature of a model whose stop sequences are not being applied.
- **The recorded model name was the configured one.** `message_request_factory.py:13` set
  `model_name=ctx.settings.model_name` — the `MODEL_NAME` default — so Session summary frontmatter
  and anomaly logs recorded configuration rather than the model that actually answered.

The concept was additionally implemented twice in two wrong shapes. `resolve_structured_model`
(`model_resolution.py:35-146`) does the same job per-call but returns a 3-tuple, holds no cache
(re-fetching `/v1/models` plus one `/api/v0/models/{id}` per loaded model on every structured
completion, five times per 6 Rs pipeline run), and takes four dependency-injection keyword
overrides so tests can substitute fakes. `modules/pathfinder/app/model_selector.py` is an
independently drifted copy whose tests still assert the blind `loaded[0]` fallback that
sentinel-core removed as unsound after `exo-model-notfound-502`.

## Decision

Introduce an **Active model** seam at `sentinel-core/app/model.py` — top level, beside
`app/vault.py`, per ADR-0002's reasoning about capability seams in the domain language.

`ActiveModel.for_task(kind) -> ModelProfile`. Backends answer through a `ModelSource` seam with two
adapters: `LMStudioModelSource` (live, from `GET /api/v0/models`) and `StaticModelSource`
(config-derived; serves Claude and undiscoverable backends, and is the test substitute).

The `ModelProfile` value carries model id, api base, context window, stop sequences, and
capabilities — everything a call needs. Providers take it as one argument:
`complete(messages, profile)`.

### Decisions a future architecture review should not re-litigate

1. **Request-time resolution over startup pinning**, behind a 60s TTL, plus invalidate-and-retry-once
   when the backend reports the model is not served (hooking the `litellm.NotFoundError` path
   `ProviderRouter` already treats specially per Phase 42 D-06). A failed refresh serves
   last-known-good rather than failing the request. This is the posture ADR-0001 gave the Sentinel
   persona and ADR-0004 gave the Embedding sidecar index; the model is the operator-tunable input
   that never received it.

2. **`loaded_context_length`, not `max_context_length`.** Resolution order is
   `loaded_context_length` → `max_context_length` → a declared `4096`, each logged, with an
   operator cap on top. `max` is what the model could do if reloaded at that size; `loaded` is what
   the running instance will honour. Taking `max` (today's behaviour, 262144 against a loaded
   119552) permits prompts more than twice what the backend accepts — an overrun caught only as a
   remote `BadRequestError`. The operator cap exists because "what the server accepts" and "what
   produces usable output" are different numbers: a 71936-token context on the 24 GB host drove the
   model into repetition loops and 200s timeouts. That ceiling is host- and model-specific and
   belongs in configuration, not code.

   *Amended 2026-09-07, during plan review.* The ladder originally read
   `loaded → max → family constant → 4096`, which contradicted decision 12's removal of
   `FamilyProfile.context_window` — the ladder consumed a field the same design deletes. Resolved by
   dropping the family rung rather than keeping the field. Two reasons: `/api/v0/models` always
   returns `max_context_length`, so the family rung is only reachable when the backend answers with
   neither field, which does not occur (an unreachable backend resolves through `StaticModelSource`
   instead); and the family constants are wrong where it matters — the qwen2 entry says 32768 against
   a real 262144/119552 — so falling back to a lying constant is worse than falling back to a
   declared, logged 4096. Decisions 2 and 12 are now consistent.

3. **Candidate filtering excludes embeddings rather than including LLMs.** The filter is
   `state == "loaded"` and `type != "embeddings"`. The intuitive `type == "llm"` form is wrong:
   `qwen/qwen3.8-27b` reports `type: "vlm"`, and multimodal weights are increasingly the default
   for local chat models. The exclusion form stays correct when LM Studio adds a type we have not
   seen.

4. **Refuse to guess survives; `select_model._score` does not.** With several capable models loaded
   and nothing disambiguating, resolution falls to configuration rather than picking one. Scoring
   always produces a winner, so keeping it would mean the refusal rung never fires. Task-capability
   *filtering* replaces scoring: `for_task("structured")` narrows to profiles whose capabilities
   support it, then the ladder runs. `_score` existed to compensate for `litellm.get_model_info`
   knowing nothing about local model ids; `/api/v0/models` supplies `capabilities` directly.

5. **The embedding model is observed, never re-pointed.** ADR-0004's exact-string `embedding_model`
   match and dimension checks stand unchanged, and embedding calls continue to use
   `settings.embedding_model`. The seam reports disagreement between the loaded embedding model and
   configuration loudly at `/health`. Re-pointing embedding calls at whatever is loaded would
   invalidate every entry in `ops/sweeps/embedding-index.json`, and ADR-0004's fail-soft posture
   would turn that into silently empty recall — a loud model swap converted into quiet memory loss.

6. **`response_anomaly`'s control-token detection stays broad.** The profile may *add* family-specific
   signals; it must not *replace* the general ones. Narrowing the regex to the loaded family would
   blind the detector to the wrong-family token leakage that motivated this ADR.

7. **Core is the only process that asks the backend which model is loaded.** Pathfinder receives
   model facts from core over HTTP rather than discovering independently. Placing the seam in
   `shared/` would relocate the fragmentation rather than remove it — two discoverers, two caches,
   free to disagree — and would require implementing the TTL-and-invalidate policy twice.

## Considered options

- **Adapter resolves the model internally** (`LiteLLMProvider` holds an `ActiveModel` reference).
  Rejected: inverts ADR-0002's layering by making a single-purpose HTTP adapter depend on a service
  module, leaves `MessageRequest`'s three scalars in place, and leaves `stop` a parameter nobody
  passes — fixing staleness while continuing to ship without stop sequences.
- **Rebuild `provider_map` when the model changes.** Rejected: makes the application graph mutable
  under live requests. `build_application` is deliberately construct-once.
- **`ActiveModel` in `shared/sentinel_shared/`.** Rejected — see decision 7.
- **One profile rather than one per task kind.** Rejected: the only shape under which
  `resolve_structured_model` survives beside the new module, preserving the two-shapes-one-concept
  split this ADR removes. `model_task_chat` / `model_task_structured` / `model_task_fast` already
  exist in config.
- **Four `ModelSource` adapters, one per backend.** Rejected as speculative: Ollama and llama.cpp are
  documented stubs with no live context-window lookup. Under `StaticModelSource` their 4096 default
  becomes declared rather than accidental, and a real adapter can be added later against a proven
  interface.

## Consequences

- `shared/sentinel_shared/model_profiles.ModelProfile` is renamed `FamilyProfile` — it is
  family-keyed constants, and the misnomer is plausibly why it grew a `context_window` field that
  disagrees with the registry and that nothing consumes. That field is removed.
- `AIProvider`, `ProviderRouter`, `LiteLLMProvider`, `POST /provider/complete` and
  `shared/sentinel_client.complete()` all gain the profile argument. Core and the pf2e module deploy
  from one compose stack and restart together; independent rollout would require the argument to be
  optional for one release.
- Deleted: `model_resolution.py`, `select_model._score`, `modules/pathfinder/app/model_selector.py`,
  `modules/pathfinder/app/resolve_model.py` and their tests, `ProviderRouterBundle` and the three
  provider-keyed tables in `build_provider_router`, and the three duplicated `_LazyRouteCtx` test
  fixtures (replaced by a real `StaticModelSource`).
- `probe_classifier_model_ready` is rewired onto `ActiveModel`, not deleted — it gates whether a
  destructive vault sweep may run, and its coverage is verified either side of the change.
- `models-seed.json` is trimmed to cloud models and becomes `StaticModelSource`'s data. Keeping it
  over litellm's static registry preserves offline operation and operator visibility.
- Structured-completion latency improves: metadata requests per 6 Rs pipeline run drop from roughly
  five times `(1 + N + 1)` to at most one per TTL window.

## Known limitations, accepted

- `TokenBudget` counts with `tiktoken.get_encoding("cl100k_base")`, which is not Qwen's tokenizer.
  The profile names an encoding and `TokenBudget` falls back to `cl100k_base` when it does not
  recognise one. Counting stays approximate; adding a real tokenizer is a container-weight decision
  deliberately left open.
- ~~Pathfinder continues to call LM Studio directly for `rule_query`.~~ **Corrected 2026-09-07 during
  planning:** this was factually wrong when written. `modules/pathfinder/app/` has **zero**
  `litellm.acompletion` call sites — every completion already goes through
  `SentinelCoreClient.complete()` to `POST /provider/complete`, and embeddings through core's
  `/embeddings`. `classify_rule_topic` (`llm.py:474-548`) calls `_core_client.complete(...)`; the
  `import litellm` at `llm.py:33` is vestigial, and `llm.py:432-440` documents its own
  `model`/`api_base`/`profile` parameters as accepted-but-not-forwarded.

  Consequences: decision 7 is already satisfied rather than aspirational; deleting
  `modules/pathfinder/app/resolve_model.py` is dead-parameter removal, not a rewrite, and needs no
  new model-facts endpoint on core. The design question this bullet raised — designing structured
  output into `POST /provider/complete` — is genuinely still open, but it is not blocking Pathfinder,
  because Pathfinder does not use structured output on that path.
- `LiteLLMProvider.complete`'s docstring claims "the chat path uses 0.4" for temperature. No such
  value exists anywhere in the codebase — the chat path pins no temperature. The docstring is
  corrected to match reality; whether to pin one is a product decision, not a defect.

## Sequencing

Each step keeps `main` green on its own.

1. Fix the stop-sequence defect alone, with its regression test. Isolated deliberately: the
   anomaly-rate instrumentation shipped in `e8bbcb3` / `dc4ee56` / `0356e0e` can then attribute any
   change in the rate to this fix rather than to a fifteen-file refactor.
2. `ActiveModel` + `ModelSource` + both adapters; `build_provider_router` reduced to composing them.
   Includes the recorded-model-name fix.
3. The `complete(messages, profile)` signature change, together with absorbing the six duplicated
   `content or reasoning_content` fallbacks into the provider adapter.
4. Deletions.
5. Cleanups: `FamilyProfile` trimming, `anomaly_rate.py` reading the model from session summaries,
   the tokenizer name on the profile.
