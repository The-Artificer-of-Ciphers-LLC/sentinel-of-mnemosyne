---
quick_id: 260907-amx
slug: active-model-seam
plan: 02
adr_step: 3
type: execute
wave: 2
depends_on: ["01"]
files_modified:
  - sentinel-core/app/clients/base.py
  - sentinel-core/app/clients/litellm_provider.py
  - sentinel-core/app/services/provider_router.py
  - sentinel-core/app/services/message_processing.py
  - sentinel-core/app/routes/provider.py
  - shared/sentinel_client.py
  - shared/sentinel_shared/llm_call.py
  - sentinel-core/app/services/note_classifier.py
  - sentinel-core/app/services/moc_maintenance.py
  - sentinel-core/app/services/pipeline_orchestrator.py
  - sentinel-core/app/services/six_rs/reduce.py
  - sentinel-core/app/services/six_rs/rethink.py
  - sentinel-core/tests/test_litellm_provider.py
  - sentinel-core/tests/test_provider_router.py
  - sentinel-core/tests/test_provider_route.py
  - sentinel-core/tests/test_llm_call_shared.py
  - sentinel-core/tests/conftest.py
  - sentinel-core/tests/test_message.py
  - sentinel-core/tests/test_auth.py
  - sentinel-core/tests/test_integration_obsidian_llm.py
  - modules/pathfinder/app/llm.py
  - modules/pathfinder/app/routes/rule.py
  - modules/pathfinder/app/routes/npc.py
  - modules/pathfinder/app/routes/session.py
  - modules/pathfinder/app/routes/harvest.py
  - modules/pathfinder/app/rule_query.py
  - modules/pathfinder/tests/test_rule_query.py
  - modules/pathfinder/tests/test_llm_core_handoff.py
autonomous: true
requirements: [ADR-0007-S3, ADR-0007-D1, ADR-0007-CONSEQ-SIGNATURE]
verification:
  core: "cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q"
  pathfinder: "cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/modules/pathfinder && /Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/.venv/bin/python -m pytest tests/ -q"
  baseline_in: "whatever 01-SUMMARY.md recorded (717 + N01 passed, 12 skipped; N01 >= 24); pathfinder 405 passed"
  expected_out: |
    Concrete arithmetic, not a placeholder. Taking N01 = 24 (Plan 01's floor):

      sentinel-core = 717 + N01 + N02  = 741 + 15 = 756 passed, 12 skipped, 0 failed
      pathfinder    = 405 + N02pf      = 405 + 2  = 407 passed, 0 failed

    N02 = 15 expected, floor 13, itemised: Task 1 adds 6 (404-with-ActiveModel
    retries exactly once then falls back; 404-without-ActiveModel goes straight to
    fallback; ConnectError does not re-resolve; the cloud fallback receives its OWN
    StaticModelSource profile and never the local one; a resolution raise surfaces on
    the chat path; a resolution raise never reaches the cloud provider). Task 2 adds
    4 (task="structured" resolves the structured profile; an unrecognised task is 422
    before any LLM call; the response `model` field is the resolved id and differs
    from the provider name; a resolution raise becomes a 503 that leaks no model ids
    or api_base). Task 3 adds 5 (the extraction helper's five shapes).
    N02pf = 2 expected: the `task` keyword reaches the wire, and no model/api_base/
    profile value appears in the request body.
    If N01 differs from 24, substitute it — the formula, not the literal, is the
    contract. ZERO tests are deleted by this plan; the three _LazyRouteCtx fakes are
    REPLACED in place, not removed, so they contribute 0 to the delta. Record exact
    numbers in 02-SUMMARY.md as N02 and N02pf — Plan 03 chains off both.
deploy_note: |
  This plan changes the POST /provider/complete REQUEST CONTRACT, which the pf2e
  module calls over HTTP via SentinelCoreClient.complete(). Core and pf2e deploy
  from ONE compose stack and restart together, so lockstep deploy is assumed and no
  optional-for-one-release shim is built. The two images MUST ship in the same
  deploy. If they are ever split, the new field must be made optional for one
  release first — see ADR-0007 Consequences.
must_haves:
  truths:
    - "Every completion call carries the model facts it needs as one argument rather than three loose scalars threaded separately."
    - "A backend reporting the model is not served causes exactly one invalidate-and-retry against a freshly resolved model before fallback is attempted (ADR decision 1)."
    - "The empty-content / reasoning_content fallback exists in exactly one place and every completion call site uses it."
    - "POST /provider/complete reports the model that actually answered, not the provider name."
    - "Pathfinder still never asks the backend which model is loaded — it names a task and core resolves (ADR decision 7)."
    - "The cloud fallback provider is called with a profile it resolved itself; the local profile's api_base and model id never cross to it."
    - "No test module hand-rolls a route context: all three former _LazyRouteCtx sites build a real ActiveModel over a real StaticModelSource."
  artifacts:
    - shared/sentinel_shared/llm_call.py
    - sentinel-core/app/clients/litellm_provider.py
    - sentinel-core/tests/conftest.py
  key_links:
    - "ProviderRouter holds the ActiveModel reference and is the only thing that re-resolves; LiteLLMProvider stays a single-purpose adapter."
    - "SentinelCoreClient.complete() sends a task name; POST /provider/complete resolves the profile core-side."
    - "The single extract_completion_text lives beside acompletion_with_profile in shared/sentinel_shared/llm_call.py, which is where five of its six callers get their raw response from."
---

<objective>
Change `complete(messages)` to `complete(messages, profile)` across the whole
completion path — `AIProvider`, `ProviderRouter`, `LiteLLMProvider`,
`POST /provider/complete`, and `shared/sentinel_client.complete()` — so a call
carries the model facts it needs as one value instead of three scalars threaded
separately. Wire the invalidate-and-retry-once behaviour ADR decision 1 specifies
onto the `litellm.NotFoundError` path `ProviderRouter` already treats specially.
Absorb the six duplicated `content or reasoning_content` fallbacks into one helper.

Purpose: ADR-0007 step 3. Until the profile is the argument, `MessageRequest`'s
three scalars have nowhere to go and Plan 03's deletions cannot land.

Output: one signature across the completion path, one extraction helper, and an
HTTP contract that names a task instead of leaking model resolution into pf2e.
</objective>

<context>
@docs/adr/0007-active-model-seam.md
@.planning/quick/260907-amx-active-model-seam/README.md
@.planning/quick/260907-amx-active-model-seam/01-SUMMARY.md
@sentinel-core/app/clients/base.py
@sentinel-core/app/clients/litellm_provider.py
@sentinel-core/app/services/provider_router.py
@sentinel-core/app/routes/provider.py
@shared/sentinel_client.py
</context>

## Verified ground truth (2026-09-07 — do not re-derive)

The six duplicated `content or reasoning_content` fallbacks:

| # | Location | Reached via |
|---|----------|-------------|
| 1 | `sentinel-core/app/clients/litellm_provider.py:126-140` | `LiteLLMProvider.complete` |
| 2 | `sentinel-core/app/services/note_classifier.py:296-322` | `acompletion_with_profile` |
| 3 | `sentinel-core/app/services/moc_maintenance.py:320-338` | `acompletion_with_profile` |
| 4 | `sentinel-core/app/services/six_rs/reduce.py:93-133` | `acompletion_with_profile` |
| 5 | `sentinel-core/app/services/six_rs/rethink.py:71-91` | `acompletion_with_profile` |
| 6 | `sentinel-core/app/services/pipeline_orchestrator.py:227-256` | `acompletion_with_profile` |

**Only copy 1 is on the `LiteLLMProvider` path.** The other five go through
`shared/sentinel_shared/llm_call.py::acompletion_with_profile`, which returns the
raw litellm response and leaves extraction to each caller. This is why the ADR's
phrase "into the provider adapter" needs the interpretation recorded under Flagged
calls: five call sites cannot reach `LiteLLMProvider.complete` without designing
structured output (`response_format`) into it, which the ADR explicitly defers.

Pathfinder facts (verified by exhaustive search of `modules/pathfinder/app/`):

- Pathfinder has **zero** `litellm.acompletion` call sites. Every completion goes
  through `SentinelCoreClient.complete()`.
- `llm.py`'s `model` / `api_base` / `profile` parameters are documented as
  vestigial and are never forwarded (`llm.py:432-440` says so explicitly for
  `embed_texts`; `generate_npc_reply`, `generate_mj_description`,
  `classify_rule_topic`, `generate_ruling_from_passages` and
  `generate_ruling_fallback` all accept them and all call `_core_client.complete`).
- Consequence: pathfinder has no profile to send and must not acquire one — that
  would make it a second discoverer and violate ADR decision 7.

<tasks>

<task type="tracer">
  <name>Task 1: complete(messages, profile) through the core stack, one path end to end</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<behavior>`, `<action>` and `<verify>` verbatim,
    plus the "Verified ground truth" section.
  </delegation>

  <read_first>
    - sentinel-core/app/clients/base.py (the whole Protocol — 31 lines; note its
      docstring already records that the Protocol drifted behind its implementations
      once before, which is the defect commit 93df616 fixed)
    - sentinel-core/app/clients/litellm_provider.py:65-140 (constructor, retry
      decorator, kwargs assembly, ContextLengthError translation, extraction)
    - sentinel-core/app/services/provider_router.py (the whole file — the
      _FALLBACK_TRIGGERS tuple including litellm.NotFoundError per Phase 42 D-06,
      and the deliberate decision not to send stop sequences to the cloud fallback)
    - sentinel-core/app/services/message_processing.py:150-210 (the chat call site
      and how req.stop_sequences reaches it since 93df616)
    - sentinel-core/app/model.py (Plan 01's ModelProfile — the value being passed)
  </read_first>

  <files>sentinel-core/app/clients/base.py, sentinel-core/app/clients/litellm_provider.py, sentinel-core/app/services/provider_router.py, sentinel-core/app/services/message_processing.py, sentinel-core/tests/test_litellm_provider.py, sentinel-core/tests/test_provider_router.py, sentinel-core/tests/conftest.py, sentinel-core/tests/test_message.py, sentinel-core/tests/test_auth.py, sentinel-core/tests/test_integration_obsidian_llm.py</files>

  <behavior>
    - `LiteLLMProvider.complete(messages, profile)` sends the profile's litellm id as
      the model, the profile's api base, and the profile's stop sequences. With a
      profile carrying no stop sequences, no stop kwarg is sent at all.
    - `ProviderRouter.complete(messages, profile)` forwards the profile to primary.
      The cloud fallback still receives no stop sequences — that behaviour is
      deliberate and predates this change.
    - **The cloud fallback receives its OWN profile, never the local one.** Assert it
      directly: drive a fallback with a local profile whose `api_base` is LM Studio's
      and whose model id is `qwen/qwen3.8-27b`, and assert the profile the fallback
      provider was called with has neither — it carries the Claude model id and
      Anthropic's base (or none), resolved from `StaticModelSource`. This is the
      test that fails loudly if someone "simplifies" the router by forwarding one
      profile to both legs.
    - The three route-context fakes are gone: `tests/test_message.py`,
      `tests/test_auth.py` and `tests/test_integration_obsidian_llm.py` each build
      their route context from the shared conftest helper over a real
      `StaticModelSource`, and each of their existing tests still passes with the
      same assertions.
    - On `litellm.NotFoundError` from primary with an ActiveModel wired: the router
      invalidates, re-resolves the same task kind, retries primary exactly ONCE, and
      only attempts fallback if the retry also fails. Assert the retry count is
      exactly one — an unbounded retry against a backend that keeps 404ing is the
      failure mode.
    - On `litellm.NotFoundError` with no ActiveModel wired: behaviour is unchanged
      from today — straight to fallback.
    - On `httpx.ConnectError` / `httpx.TimeoutException`: unchanged — no re-resolve,
      straight to fallback. Only the not-served signal justifies re-resolving.
    - Context-length rejections still translate to `ContextLengthError` and still do
      not trigger fallback.
    - The chat path budgets against `profile.context_window`, which for the live
      backend is 119552 rather than 262144.
    - **An unresolvable model surfaces as a clean error, not an unhandled 500.**
      Under ADR decision 4 as amended 2026-09-08, `for_task(kind)` RAISES when a live
      backend's candidates cannot be disambiguated, where an earlier draft would have
      returned a config-named phantom. `MessageProcessor.process` must therefore
      handle a raise from resolution. It is NOT added to `_FALLBACK_TRIGGERS`: a
      resolution failure is a local misconfiguration or an ambiguous backend, not a
      backend outage, and silently diverting it to the paid cloud provider would
      convert an operator error into a bill and hide the very condition the raise
      exists to announce. Surface it; do not fall back on it. Assert both halves —
      the error surfaces, and the cloud provider is never called.
  </behavior>

  <action>
    Widen `AIProvider.complete` in `app/clients/base.py` to take the profile. The
    Protocol's own docstring already records that it drifted behind its
    implementations once — `stop` existed on both `LiteLLMProvider` and
    `ProviderRouter` since Phase 42 while the Protocol declared only `messages`, so
    `MessageProcessor`, typed against the Protocol, silently dropped it. Widen the
    Protocol FIRST and let the implementations follow it, not the other way round.

    In `LiteLLMProvider.complete`, take the profile and read the model string, api
    base and stop sequences off it. The provider keeps its constructor arguments for
    the api key and for the static cloud case; what it stops doing is holding a
    model string pinned at construction time for the local backend. Do NOT give
    `LiteLLMProvider` an `ActiveModel` reference — the ADR explicitly rejected that,
    because it inverts ADR-0002's layering by making a single-purpose HTTP adapter
    depend on a service module.

    In `ProviderRouter`, accept an optional `active_model` constructor argument and
    forward the profile to the primary provider. `litellm.NotFoundError` is already
    in `_FALLBACK_TRIGGERS` per Phase 42 D-06 precisely because a model-not-served
    backend can fail with a plain 404 rather than a connectivity error. That is the
    hook ADR decision 1 names: when the 404 arrives and an ActiveModel is wired,
    invalidate it, resolve the profile's own task kind again, and retry the primary
    once with the fresh profile. Bound it at one retry. If the retry fails, or if no
    ActiveModel is wired, continue into the existing fallback path unchanged. The
    router is a service, not an adapter, so holding the reference here does not
    inherit the layering objection that killed the adapter-side variant.

    **Decide explicitly which profile the cloud fallback gets: its own.** ADR
    decision 8 puts `api_base` on the profile, so forwarding the local profile to the
    Claude fallback would hand Anthropic LM Studio's base URL and LM Studio's model
    id — a fallback that cannot succeed, arriving exactly when the primary is already
    down. The router therefore resolves the FALLBACK's profile separately, from the
    `StaticModelSource` leg (the Claude seed entry), and passes that. The local
    profile is an argument to the primary call only and must not leak across. Cover
    it with the assertion in `<behavior>`; a fallback that is merely "not asserted
    about" is how this regresses.

    Replace the three `_LazyRouteCtx` fakes — `tests/test_message.py:90`,
    `tests/test_auth.py:92`, `tests/test_integration_obsidian_llm.py:107`, each
    followed by `app.state.route_ctx = _LazyRouteCtx()`. This is NOT deferrable to
    Plan 03: this task makes `MessageProcessor` resolve its profile from the route
    context's `ActiveModel`, and a hand-rolled fake that has no `ActiveModel` cannot
    satisfy that — Plan 02 would not be green on its own, which breaks the plan
    set's central rule. Put one shared helper in `sentinel-core/tests/conftest.py`
    that builds a real route context around a real `ActiveModel` over a
    `StaticModelSource`, and point all three modules at it. This is the ADR's stated
    reason for `StaticModelSource` being a first-class adapter rather than a test
    double. Keep every existing assertion in those three modules unchanged — the
    fixture changes, the tests do not. Plan 03 Task 3 then only removes the two
    RouteContext scalars from that one helper.

    Update `MessageProcessor.process` to resolve the profile from the route context's
    ActiveModel and pass it, and to budget against `profile.context_window`. The
    `req.stop_sequences` field becomes redundant here because the profile carries
    them — leave the field in place, since `MessageRequest`'s scalars are Plan 03's
    to remove, but stop being the thing that reads it if the profile supersedes it.
    Do not reintroduce the 93df616 defect: whichever source wins, stop sequences must
    still reach `litellm.acompletion` on the chat path, and the regression test for
    that must still pass.

    Update `tests/test_litellm_provider.py` (11 collected tests) to the new
    signature. Add the retry-once tests described in `<behavior>`.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - `AIProvider`, `ProviderRouter` and `LiteLLMProvider` all declare and honour the
      profile argument.
    - `LiteLLMProvider` holds no `ActiveModel` reference.
    - A not-served 404 produces exactly one invalidate-and-retry before fallback,
      asserted by call count.
    - Connectivity errors still go straight to fallback with no re-resolve.
    - The cloud fallback is called with a profile carrying neither the local
      `api_base` nor the local model id, asserted directly.
    - No `_LazyRouteCtx` class remains in any of the three test modules; all three
      build their context from the shared conftest helper over a real
      `StaticModelSource`, and every pre-existing assertion in them is unchanged.
    - The 93df616 stop-sequence regression test still passes.
    - Suite green; no test deleted.
  </acceptance_criteria>

  <done>
    POST /message runs end to end with the profile as the argument, budgets against
    the loaded context length, and recovers from a model swap mid-flight by
    invalidating and retrying once.
  </done>
</task>

<task type="auto">
  <name>Task 2: the HTTP contract — POST /provider/complete and SentinelCoreClient.complete()</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<action>` and `<verify>` verbatim, plus the
    Pathfinder facts under "Verified ground truth" and the `deploy_note` from this
    plan's frontmatter.
  </delegation>

  <read_first>
    - sentinel-core/app/routes/provider.py (the whole file — the request/response
      models, the _MAX_MESSAGES DoS guard, the generic-detail 503 per T-42-08, and
      the response's `model` field currently sourced from ctx.ai_provider_name)
    - shared/sentinel_client.py:74-108 (complete(), and its documented
      raise-on-error posture which deliberately differs from send_message())
    - modules/pathfinder/app/llm.py:100-206 and :419-444 (the vestigial
      model/api_base/profile parameters and the explicit note that they are not
      forwarded)
    - modules/pathfinder/app/rule_query.py:118-136 and :165-175 (the fifth call site
      — where r_chat/r_structured are unpacked into model/api_base/profile kwargs on
      classify_rule_topic and embed_texts)
    - modules/pathfinder/tests/test_llm_core_handoff.py (the contract tests for the
      pf2e-to-core handoff)
    - modules/pathfinder/tests/test_rule_query.py (assertions on those call shapes)
  </read_first>

  <files>sentinel-core/app/routes/provider.py, shared/sentinel_client.py, sentinel-core/tests/test_provider_route.py, modules/pathfinder/app/llm.py, modules/pathfinder/app/rule_query.py, modules/pathfinder/app/routes/rule.py, modules/pathfinder/app/routes/npc.py, modules/pathfinder/app/routes/session.py, modules/pathfinder/app/routes/harvest.py, modules/pathfinder/tests/test_rule_query.py, modules/pathfinder/tests/test_llm_core_handoff.py</files>

  <behavior>
    - `POST /provider/complete` with no task field behaves exactly as before for the
      caller: core resolves the chat profile and answers.
    - `POST /provider/complete` with `task: "structured"` resolves the structured
      profile. An unrecognised task value is rejected with 422 before any LLM call —
      same posture as the existing message-count and content-length guards.
    - The response's `model` field carries the resolved model id, not the provider
      name. Assert with a configured provider name that differs from the model id.
    - A `ProviderUnavailableError` still produces a 503 with generic detail only —
      the provider api_base and api key must never appear in the response body
      (T-42-08).
    - A resolution raise from `ActiveModel.for_task(task)` — the amended ADR
      decision 4 case, a live backend whose candidates cannot be disambiguated —
      produces a 503 with generic detail, not an unhandled 500 and not a phantom
      model. Same leak rules as T-42-08: the loaded model ids and the api_base must
      not appear in the response body, however tempting it is to "help" the caller
      by listing what WAS loaded. Log the detail server-side instead.
    - `SentinelCoreClient.complete()` still raises on 4xx/5xx rather than swallowing
      to a string, matching `post_to_module` and not `send_message`.
    - Pathfinder call sites compile and pass with no model, api_base or profile
      argument reaching the wire.
  </behavior>

  <action>
    Add a task field to `ProviderCompleteRequest` — a closed set of `chat`,
    `structured`, `fast`, defaulting to `chat`. The route resolves the profile
    core-side from the route context's ActiveModel and passes it to
    `ctx.ai_provider.complete`. This is the interpretation recorded under Flagged
    calls: the ADR says this endpoint "gains the profile argument", but pathfinder
    cannot supply a profile without becoming a second discoverer, which ADR decision
    7 forbids. What crosses the wire is therefore the task name; the profile is
    resolved on the core side, where the ADR says the only discoverer lives.

    Validate the task value with the same fail-before-cost posture the endpoint
    already uses for message count and content length — reject unrecognised values
    with 422 before any LLM call, not by falling back to chat.

    Change the response's `model` field to report the resolved model id instead of
    `ctx.ai_provider_name`. This is the HTTP-path analogue of Defect B: today a
    caller asking core what answered gets back `lmstudio`, which is the backend
    name, not the model. Keep `ai_provider_name` on the route context — `/status`
    reads it (`routes/status.py:24`) and that is a legitimate different question.

    Mirror the field in `SentinelCoreClient.complete()` as a `task` keyword
    defaulting to `chat`. Keep its raise-on-error posture exactly as documented —
    pf2e call sites depend on getting real exceptions.

    Then strip the dead `model` / `api_base` / `profile` parameters from the
    pathfinder `llm.py` functions that accept them and never forward them, and from
    their call sites. Verified: `generate_npc_reply`, `generate_mj_description`,
    `classify_rule_topic`, `generate_ruling_from_passages`, `generate_ruling_fallback`
    and `embed_texts` all accept them; none forwards them; `embed_texts`' own
    docstring calls them vestigial. Removing them here is what makes Plan 03's
    deletion of `resolve_model.py` a clean removal rather than a rewrite. Where a
    pathfinder call site wants a non-chat tier, pass the task name through to
    `SentinelCoreClient.complete()` instead — that is the supported way for a module
    to express a tier without discovering anything.

    `modules/pathfinder/app/rule_query.py` is a fifth call site and is NOT optional.
    `execute_rule_query` reads `r_chat.model` / `r_structured.model` /
    `r_chat.profile` / `r_structured.profile` at `rule_query.py:120-126` and threads
    them into `deps.classify_rule_topic(...)` at `:130-135` and `deps.embed_texts(...)`
    at `:166-170`. Once `llm.py` stops accepting those kwargs, those calls stop
    passing them. `modules/pathfinder/tests/test_rule_query.py` asserts on some of
    those call shapes and is updated with them — updated, never deleted.

    Scope boundary with Plan 03: this task removes the dead *parameters* and stops
    the four route modules (`npc.py`, `session.py`, `harvest.py`, `rule.py` — all
    four are in `files_modified`, `rule.py` included) plus `rule_query.py` from
    threading `r.model` / `r.api_base` / `r.profile` into them. It does NOT delete
    `resolve_model.py`, `model_selector.py`, or the `resolve_model` field on
    `RuleQueryDependencies` — those are Plan 03's, and `rule_query.py:120-121`'s two
    `await deps.resolve_model(...)` calls stay put here. After this task the
    `await resolve(...)` calls resolve values nobody consumes; that is the intended
    intermediate state and it is what makes Plan 03 a pure deletion. Expect a lint
    complaint about the now-unused `model_chat` / `profile_chat` locals — leave them,
    they go with `resolve_model` in Plan 03.

    Record the lockstep requirement in the SUMMARY: core and pf2e images must ship in
    the same deploy, because the request contract changed and they run from one
    compose stack.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/modules/pathfinder && /Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - The endpoint accepts a closed-set task field defaulting to chat and rejects
      unrecognised values with 422 before any LLM call.
    - The response `model` field carries the resolved model id; a test asserts it
      differs from the provider name.
    - The 503 path still leaks no provider configuration, and a resolution raise
      lands on it rather than escaping as a 500 or being converted into a cloud call.
    - No model, api_base or profile value originates in pathfinder.
    - Both suites green; pathfinder delta is from added tests only.
  </acceptance_criteria>

  <done>
    pf2e names a task and core answers with the model that actually ran, and no
    pathfinder code carries a model argument any more.
  </done>
</task>

<task type="auto">
  <name>Task 3: one extraction helper replaces six copies of the empty-content fallback</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<action>` and `<verify>` verbatim, plus the
    six-copies table from "Verified ground truth".
  </delegation>

  <read_first>
    - All six locations in the six-copies table above, in order. They are not
      identical: note_classifier's copy has an extra JSON-mode comment and an extra
      guard, and reduce/rethink each wrap theirs in a module-private
      `_extract_completion_content`. Read all six before writing one.
    - shared/sentinel_shared/llm_call.py (all 51 lines — `acompletion_with_profile`
      returns the RAW litellm response, which is why extraction fell to callers)
    - sentinel-core/tests/test_litellm_provider.py:71-95 (the existing reasoning
      -content regression, bug #1773 — the behaviour the single helper must keep)
  </read_first>

  <files>shared/sentinel_shared/llm_call.py, sentinel-core/app/clients/litellm_provider.py, sentinel-core/app/services/note_classifier.py, sentinel-core/app/services/moc_maintenance.py, sentinel-core/app/services/pipeline_orchestrator.py, sentinel-core/app/services/six_rs/reduce.py, sentinel-core/app/services/six_rs/rethink.py, sentinel-core/tests/test_llm_call_shared.py</files>

  <behavior>
    One helper, tested once, covering every shape the six copies covered between them:

    - A response whose message is a dict with populated content returns that content.
    - A response whose message is a dict with empty content and populated
      reasoning_content returns the reasoning content (bug #1773 — LM Studio plus a
      Qwen3 thinking-mode model puts the JSON there when a json_schema response
      format is applied).
    - A response whose message is an object rather than a dict behaves the same for
      both fields.
    - Both fields empty or absent returns the empty string, never None —
      `ProviderCompleteResponse.content` is declared `str` and must never receive None.
    - A malformed response with no choices returns the empty string rather than
      raising an IndexError.
  </behavior>

  <action>
    **RULED: the helper's home is `shared/sentinel_shared/llm_call.py`, NOT
    `app/clients/litellm_provider.py`.** Add one exported function there that takes a
    litellm response and returns the completion text, handling both the dict-message
    and object-message shapes and flooring at the empty string. Then delete the
    inline copies at all six locations and have every one of them call it —
    `litellm_provider.py`'s own copy (#1) **imports** the shared extractor rather
    than defining its own. The two module-private `_extract_completion_content`
    helpers in `six_rs/reduce.py` and `six_rs/rethink.py` go with them; if either has
    its own tests, repoint those tests at the shared helper rather than deleting the
    coverage.

    The reason is the six-copies table: `llm_call.py` is where the raw litellm
    response is *created* for five of the six. Those five call
    `acompletion_with_profile` with a `response_format` schema and then extract from
    the raw response it hands back. Putting the extractor anywhere else means five of
    six call sites import across a package boundary
    (`shared/` → `sentinel-core/app/clients/`) to parse a value `shared/` produced,
    which inverts the dependency. Putting it beside the producer means each caller
    imports one module, not two.

    This does NOT change `acompletion_with_profile`'s contract. It still returns the
    raw response; the extractor is a *separate exported function* in the same module,
    and callers opt into it. That was the real concern behind the earlier reading —
    it is addressed by adding a function, not by changing a return type.
    `litellm_provider.py` already depends on `shared/`, so no new layering exception
    is created in that direction either.

    Keep the reasoning-content behaviour exactly. It exists because reasoning models
    return content empty with the actual text in reasoning_content, and because when
    a json_schema response format is applied the schema constraint lands on
    reasoning_content instead. Both are load-bearing; neither is a workaround to be
    tidied away.

    This task deletes no tests. If consolidating makes an existing per-module
    extraction test redundant, repoint it rather than removing it — six call sites
    sharing one implementation is exactly the situation where losing a call site's
    own coverage hides a wiring mistake.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - One exported extraction function exists in `shared/sentinel_shared/llm_call.py`
      and all six former copies call it, `litellm_provider.py` included (it imports,
      it does not redefine).
    - `acompletion_with_profile` still returns the raw response — its contract is
      unchanged and no caller's error handling moved in this commit.
    - Its tests cover all five shapes in `<behavior>`.
    - No per-call-site extraction test was deleted; any that became redundant was
      repointed at the shared helper.
    - Suite green.
  </acceptance_criteria>

  <done>
    The empty-content fallback lives in one place, every completion call site reads
    its result through it, and the bug #1773 behaviour is unchanged.
  </done>
</task>

</tasks>

## Flagged calls

1. **RULED 2026-09-07: "into the provider adapter" means one exported helper in
   `shared/sentinel_shared/llm_call.py`, not in `litellm_provider.py`, and not
   routing five call sites through `LiteLLMProvider.complete`.** Only one of the six
   copies is on the `complete()` path; the other five reach litellm through
   `acompletion_with_profile` with a `response_format`, and `llm_call.py` is where
   that raw response is created. Routing them through `complete()` would require
   designing structured output into the provider interface, which ADR-0007's "Known
   limitations, accepted" explicitly defers. Siting the extractor beside its producer
   keeps five of six call sites importing one module instead of two and avoids
   `shared/` code parsing a value via a `sentinel-core/app/clients/` import.
   `litellm_provider.py` imports the shared function for copy #1.
   `acompletion_with_profile`'s raw-response contract is untouched — the extractor is
   an additional exported function, not a change to that return type.
2. **What crosses the wire on `POST /provider/complete` is a `task`, not a
   profile.** The ADR says the endpoint "gains the profile argument", but decision 7
   says core is the only process that asks the backend which model is loaded. A
   pathfinder that constructs a profile would be a second discoverer. Sending the
   task name and resolving core-side satisfies both. The field is defaulted rather
   than required, which also means the lockstep deploy is a belt-and-braces
   requirement rather than a hard breakage — but it is still required, because the
   response's `model` semantics change.
3. **The response `model` field's meaning changes** from provider name to resolved
   model id. Not named in the ADR, but it is the same defect as Defect B on the HTTP
   path: a caller asking what answered currently gets `lmstudio`.
4. **The retry-once bound.** ADR decision 1 says "invalidate-and-retry-once". This
   plan reads that literally: exactly one retry, asserted by call count, then the
   existing fallback path.
5. **`MessageRequest`'s scalars survive this plan.** Superseded by the profile but
   not removed — removal is Plan 03's, together with `ProviderRouterBundle`.
6. **The three `_LazyRouteCtx` fakes are replaced HERE, not in Plan 03.** They were
   originally scheduled with the other test-side cleanups in Plan 03, but this task
   makes `MessageProcessor` resolve from `ActiveModel`, and a fake with no
   `ActiveModel` cannot satisfy that — Plan 02 would not be green on its own. Moved
   forward 2026-09-07. Plan 03 Task 3's share of that work shrinks to removing the
   two RouteContext scalars from the one shared conftest helper.
7. **The cloud fallback resolves its own profile.** The ADR does not say which
   profile the fallback leg receives, and decision 8 puts `api_base` on the profile —
   so forwarding the local profile would send Anthropic LM Studio's base URL and
   model id at precisely the moment the primary is already failing. Ruled: the
   fallback resolves from `StaticModelSource`, and a test asserts the local profile
   never reaches it.
8. **A resolution failure is NOT a fallback trigger.** ADR decision 4 as amended
   2026-09-08 makes `for_task` raise instead of returning an unconfirmed
   `model_name`, which gives `ProviderRouter` a new failure mode it did not have
   before. Ruled: it does not join `_FALLBACK_TRIGGERS`. Those exist for a backend
   that is down; this is an ambiguous or misconfigured local backend, and routing it
   to the paid cloud provider would turn an operator error into a bill while hiding
   the condition the raise exists to announce. It surfaces as a 503 on the HTTP path
   and as an exception on the chat path. N02 rises by 3 for these cases (chat-path
   surface, cloud-never-called, route 503).
9. **`rule_query.py` is a call site of the vestigial parameters, not just a holder of
   `resolve_model`.** Verified at `rule_query.py:120-135,166-170`. It is edited in
   this plan for the kwargs and again in Plan 03 for the `RuleQueryDependencies`
   field; the two edits do not overlap.

<output>
Create `.planning/quick/260907-amx-active-model-seam/02-SUMMARY.md` when done,
recording: both suites' exact post-change counts, the pathfinder delta and which
added tests produced it, and an explicit restatement of the lockstep deploy
requirement for the next deploy.
</output>
