---
quick_id: 260907-amx
slug: active-model-seam
plan: 01
adr_step: 2
type: execute
wave: 1
depends_on: []
files_modified:
  - sentinel-core/app/model.py
  - sentinel-core/app/config.py
  - sentinel-core/app/composition.py
  - sentinel-core/app/state.py
  - sentinel-core/app/services/message_request_factory.py
  - sentinel-core/app/services/model_selector.py
  - sentinel-core/app/routes/note.py
  - sentinel-core/tests/test_model.py
  - sentinel-core/tests/test_composition.py
  - sentinel-core/tests/test_model_selector.py
  - sentinel-core/tests/test_message_request_factory.py
  # Task 2's action calls for an end-to-end Defect B assertion here (recorded model
  # name reaching the session summary frontmatter and the anomaly warning); it was
  # named in the prose but missing from this list. Added 2026-09-07.
  - sentinel-core/tests/test_message_processor.py
autonomous: true
requirements: [ADR-0007-S2, ADR-0007-D1, ADR-0007-D2, ADR-0007-D3, ADR-0007-D4, ADR-0007-D5, ADR-0007-D7, DEFECT-B]
verification:
  core: "cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q"
  pathfinder: "not required — this plan touches no file under modules/pathfinder/"
  baseline_in: "sentinel-core 717 passed, 12 skipped (729 collected)"
  expected_out: "sentinel-core 717 + N01 passed, 12 skipped, 0 failed — where N01 is the count of NEW tests added by this plan (>= 20, in tests/test_model.py plus the Defect B and probe-parity regressions; the floor rose from 12 to 16 with the ladder-order, absolute-pin-warning and last-known-good-tiebreaker cases added 2026-09-07, then to 18 when last-known-good moved above model_name and the seven-rung ordering test plus the explicit rung-4-beats-rung-5 case were added, then to 20 with the rung-4 divergence-log pair (fires on divergence, silent on agreement)). ZERO existing tests are deleted by this plan; any pre-existing test that now fails is a regression, not an expected churn. Record the exact number in 01-SUMMARY.md as N01 — Plans 02, 03 and 04 all chain their arithmetic off it."
must_haves:
  truths:
    - "A model swapped in the LM Studio UI is picked up by a running container within one TTL window, with no restart (ADR decision 1)."
    - "The context window a request is budgeted against comes from loaded_context_length when the backend reports one, not max_context_length (ADR decision 2)."
    - "A loaded model reporting type 'vlm' is a valid chat candidate; a model reporting type 'embeddings' never is (ADR decision 3)."
    - "With two or more capable models loaded and no operator pin, resolution prefers the previously-resolved model whenever it is still loaded — ahead of the configured MODEL_NAME, because MODEL_NAME is a tracked default that may name a model nobody has loaded — and otherwise falls to configuration, never to an arbitrary candidate (ADR decision 4, refuse-to-guess preserved)."
    - "The task-capability filter narrows the candidate set BEFORE any preference rung is consulted; an operator pin naming a loaded-but-incapable model still wins, but never silently — it logs a WARNING naming the model, the task kind and the missing capability."
    - "A failed refresh serves last-known-good rather than failing the request (ADR decision 1)."
    - "When the model in use and the configured MODEL_NAME disagree, the log says so — silence means they agree, never that nobody checked."
    - "Session summary frontmatter and the response-anomaly log record the model that actually answered, not MODEL_NAME (Defect B)."
    - "probe_classifier_model_ready still fails closed on every path it failed closed on before, and still gates the destructive vault sweep at routes/note.py."
  artifacts:
    - sentinel-core/app/model.py
    - sentinel-core/tests/test_model.py
  key_links:
    - "build_provider_router composes ActiveModel + both ModelSource adapters and no longer performs three separate HTTP fetches of its own."
    - "app.state / RouteContext carries the ActiveModel instance; build_message_request reads the resolved profile from it."
    - "routes/note.py's destructive-sweep gate still calls probe_classifier_model_ready, now backed by ActiveModel."
---

<objective>
Introduce the Active model seam at `sentinel-core/app/model.py` — `ActiveModel`,
the `ModelProfile` value, the `ModelSource` protocol, and the two adapters
(`LMStudioModelSource`, `StaticModelSource`) — then reduce `build_provider_router`
from ~158 lines making three separate HTTP fetches to a function that composes
them. Fix the recorded-model-name defect (Defect B) in the same pass, and rewire
`probe_classifier_model_ready` onto the seam without weakening its fail-closed
contract.

Purpose: ADR-0007 step 2. Everything downstream (the `complete(messages, profile)`
signature in Plan 02, the deletions in Plan 03) depends on this module existing and
being the single place that answers "which model is loaded and what can it do".

Output: `sentinel-core/app/model.py` + `sentinel-core/tests/test_model.py`, a
composed `build_provider_router`, and a `probe_classifier_model_ready` that no
longer depends on `_score`.
</objective>

<context>
@docs/adr/0007-active-model-seam.md
@.planning/quick/260907-amx-active-model-seam/README.md
@sentinel-core/app/composition.py
@sentinel-core/app/services/model_selector.py
@sentinel-core/app/services/model_registry.py
@sentinel-core/app/clients/litellm_provider.py
@shared/sentinel_shared/model_profiles.py
@sentinel-core/app/state.py
@sentinel-core/app/services/message_request_factory.py
</context>

## Verified ground truth (2026-09-07 — do not re-derive)

Live LM Studio on `:1234` currently serves:

- `qwen/qwen3.8-27b` — `type: "vlm"`, `arch: qwen3_5`, `compatibility_type: mlx`,
  `state: "loaded"`, `max_context_length: 262144`, `loaded_context_length: 119552`,
  `capabilities: ["tool_use"]`
- `text-embedding-nomic-embed-text-v1.5` — `type: "embeddings"`, 2048

That single live entry is the fixture every adapter test should be built from: it
is simultaneously the proof that `type == "llm"` filtering is wrong (it reports
`vlm`), that `max` and `loaded` disagree by more than 2x, and that
`capabilities` is the direct replacement for `_score`'s function-calling guess.

Existing shapes worth reading before writing anything:

- `composition.py:115-272` — `build_provider_router`, three fetches, returns `ProviderRouterBundle`
- `model_selector.py:99-127` — `get_loaded_models`, process-lifetime dict cache, no TTL
- `model_selector.py:130-207` — `select_model`, the 6-rule ladder whose refusal rung survives
- `model_selector.py:210-285` — `_score`, which does not survive (deleted in Plan 03)
- `model_selector.py:472-595` — `probe_classifier_model_ready`
- `model_selector.py:598-651` — `probe_embedding_model_loaded` (untouched; ADR decision 5)
- `litellm_provider.py:163-220` — `get_model_capabilities_from_lmstudio`, the existing `/api/v0/models/{id}` seam
- `model_profiles.py:38-131` — `FAMILY_PROFILES` + `SAFE_DEFAULT` (renamed in Plan 04, read-only here)
- `config.py:82-86` — `model_auto_discover`, `model_preferred`, `model_task_chat`,
  `model_task_structured`, `model_task_fast`. **The three `model_task_*` settings
  exist and currently have no consumer anywhere in the codebase.** This plan gives
  them one.

<tasks>

<task type="tracer">
  <name>Task 1: app/model.py — the Active model seam, wired end to end on one path</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. The
    orchestrator does not write this code itself. Hand the subagent this task's
    `<read_first>`, `<behavior>`, `<action>` and `<verify>` verbatim, plus the
    "Verified ground truth" section above.
  </delegation>

  <read_first>
    - sentinel-core/app/services/model_selector.py (the whole file — the ladder, the
      cache, the two probes, and the exo-model-notfound-502 refusal rationale that
      must survive)
    - sentinel-core/app/clients/litellm_provider.py:143-220 (both `/api/v0/models/{id}`
      fetchers — reuse this seam, do not add a third HTTP client)
    - shared/sentinel_shared/model_profiles.py (FAMILY_PROFILES keyed by `arch`;
      `qwen3_5` is already an alias to the qwen2 ChatML profile)
    - sentinel-core/app/services/model_registry.py (build_model_registry + models-seed.json,
      which becomes StaticModelSource's data)
  </read_first>

  <files>sentinel-core/app/model.py, sentinel-core/app/config.py, sentinel-core/tests/test_model.py</files>

  <behavior>
    Tests to write before the implementation, all against a fake HTTP client seeded
    with the live two-entry `/api/v0/models` payload from "Verified ground truth":

    - Candidate filtering keeps the `vlm` entry and drops the `embeddings` entry.
      A hypothetical future `type: "omni"` entry is also kept (ADR decision 3 —
      exclusion form, not inclusion form).
    - Context window resolves to 119552, not 262144, and the resolution rung is
      logged. With `loaded_context_length` absent it resolves to `max_context_length`;
      with both absent, to a declared 4096. Three cases, three rungs, each logged.
      There is deliberately NO family-constant rung — see Flagged calls 7.
    - `MODEL_CONTEXT_CAP=32000` caps the resolved 119552 down to 32000. An unset cap
      leaves it at 119552. The cap never raises a lower resolved value.
    - `for_task("structured")` includes a candidate whose capabilities contain
      `tool_use` and excludes one whose capabilities do not. `for_task("chat")` and
      `for_task("fast")` apply no capability requirement.
    - Refuse to guess: with two `tool_use`-capable candidates loaded, no
      `model_task_structured`, no `model_preferred`, NO last-known-good, and a
      configured `MODEL_NAME` that is not among them, resolution returns the
      configured model rather than picking a candidate. With no configured model
      either, it raises rather than returning an arbitrary entry.
      The no-last-known-good clause is still load-bearing under the corrected order,
      for a different reason than before: last-known-good now sits ABOVE `model_name`,
      so a warm last-known-good would satisfy the request at rung 4 and this test
      would never reach the `model_name` rung it exists to exercise. Start the
      `ActiveModel` cold.
    - Ladder order — the capability filter runs FIRST and narrows the candidate set;
      preference then applies WITHIN the filtered set, and verified-loaded evidence
      outranks the unverified configured default:
      capability filter → `model_task_{kind}` → `model_preferred` → **last-known-good**
      → `model_name` → sole surviving candidate → refuse. Assert the order with a
      case where each rung in turn is the one that decides — seven cases, and the
      rung-4-beats-rung-5 case (warm last-known-good present AND `MODEL_NAME` naming
      a different loaded candidate → last-known-good wins) is the one that would have
      passed under the earlier, wrong order and must not be omitted.
    - Operator pins are absolute, and that is a deliberate exception to
      filter-first. A `model_task_{kind}` or `model_preferred` naming a model that
      IS loaded but does NOT pass the capability filter still wins — and MUST emit a
      WARNING naming the pinned model, the task kind, and the missing capability.
      Assert that the warning fires (caplog), not merely that the pin won.
    - A pin naming a model that is not loaded at all is ignored and the ladder
      continues — the absolute-pin exception covers loaded-but-incapable only.
    - Last-known-good tiebreaker: two candidates loaded, both surviving the filter,
      no `model_task_{kind}`, no `model_preferred`, and one of the two previously
      resolved for this task kind → the previously-resolved one wins. Assert this
      BOTH with `MODEL_NAME` matching neither candidate AND with `MODEL_NAME` naming
      the *other* loaded candidate — last-known-good outranks `model_name`, so it
      wins in both cases. It must still be among the loaded candidates; a
      last-known-good that has since been unloaded is discarded and the ladder
      continues to `model_name` and below.
    - Rung 4 announces divergence, and only divergence. When last-known-good decides
      AND the winning model id differs from the configured `model_name`, an INFO line
      fires naming the model that won, that it won as last-known-good, and the
      `model_name` it was preferred over. Two tests, caplog-asserted: it FIRES when
      the two differ, and it does NOT fire when last-known-good and `model_name` name
      the same model. The silent case is the common one and must stay silent — a line
      on every resolution is noise, and noise is how the real divergence gets missed.
    - TTL: two `for_task` calls inside the window issue one `/api/v0/models` fetch;
      a third after the window advances issues a second fetch. Drive the clock with
      an injected time function, not `sleep`.
    - `invalidate()` forces the next `for_task` to refetch even inside the window.
    - Last-known-good: after one successful resolution, a refresh whose HTTP call
      raises returns the previously-resolved profile and logs a warning — it does
      not raise and does not return a 4096 default.
    - Cold last-known-good: a first-ever resolution whose HTTP call raises falls
      through to StaticModelSource rather than raising.
    - `StaticModelSource` alone (no LM Studio at all) resolves a Claude profile from
      the seed and a declared 4096 profile for ollama/llamacpp.
  </behavior>

  <action>
    Create `sentinel-core/app/model.py` at the top level of the app package, beside
    `app/vault.py` — per ADR-0002's reasoning about capability seams living in the
    domain language. It contains four things and nothing else.

    First, a frozen dataclass `ModelProfile` carrying everything a call needs:
    the bare model id, the litellm-prefixed id, the api base, the resolved context
    window, the stop sequences, a frozenset of capabilities, the family/arch key,
    the task kind it was resolved for, and a field naming which rung produced the
    context window. Include the task kind — Plan 02 needs it to re-resolve the same
    kind after an invalidate.

    Second, a `ModelSource` Protocol with one async method returning the list of
    candidate profiles the backend currently offers.

    Third, `LMStudioModelSource`, reading `GET /api/v0/models` once per refresh and
    building one candidate per entry. Filter candidates by `state == "loaded"` AND
    `type != "embeddings"` — per ADR decision 3 the exclusion form is required and
    the inclusion form is a defect, because the live chat model reports `vlm`.
    Resolve each candidate's context window in the order `loaded_context_length`,
    then `max_context_length`, then a declared 4096 — logging which rung fired, per
    ADR decision 2 *as amended 2026-09-07*. There is deliberately no family-constant
    rung. Three reasons, all in the amended ADR: it would consume
    `FamilyProfile.context_window`, the field ADR Consequences / Plan 04 delete —
    a ladder that reads a field the same design removes; `/api/v0/models` always
    returns `max_context_length`, so the family rung is only reachable when the
    backend answers with neither field, which does not happen (an unreachable
    backend resolves through `StaticModelSource` instead); and the family constants
    are wrong exactly where it would matter — the qwen2 entry declares 32768 against
    a real 262144/119552 — so falling back to a lying constant is worse than falling
    back to a declared, logged 4096. Read
    `capabilities` straight off the entry; this is what replaces `_score`'s
    `litellm.get_model_info` guessing, per ADR decision 4. Read stop sequences by
    mapping the entry's `arch` through the existing FAMILY_PROFILES table. This
    adapter reuses the `/api/v0/models` seam that
    `litellm_provider.get_model_capabilities_from_lmstudio` already uses — it must
    not construct its own long-lived httpx client, and the single list fetch
    replaces the previous one-request-per-model fan-out.

    Fourth, `StaticModelSource`, config-derived. It serves Claude from the model
    seed and serves ollama/llamacpp as declared 4096-context profiles with no
    capabilities — per ADR's rejection of four adapters, their 4096 becomes declared
    rather than accidental. It is also the test substitute, which is why it must be
    constructible from a plain list of profiles with no I/O at all.

    Then `ActiveModel`, holding an ordered list of sources, the settings, a clock
    function, and a TTL defaulting to 60 seconds. `for_task(kind)` returns a
    `ModelProfile`. It refreshes candidates when the TTL has expired or
    `invalidate()` was called, then runs the ladder.

    **The capability filter runs FIRST and narrows the candidate set. Preference
    then applies within the filtered set.** This ordering is the agreed design and
    the inverse — preference first, filter as a later rung — is a defect: a filter
    that only runs after preference has already chosen cannot narrow anything. Full
    order:

    1. **Task-capability filter.** `structured` requires `tool_use`; `chat` and
       `fast` impose no capability requirement (Flagged calls 2). Everything below
       operates on the surviving set.
    2. **`model_task_{kind}`** — `model_task_chat` / `model_task_structured` /
       `model_task_fast`. These settings already exist and this is their first
       consumer.
    3. **`model_preferred`.**
    4. **Last-known-good**, when it is STILL among the filtered candidates. A
       last-known-good that has since been unloaded is discarded, not resurrected.
       When this rung decides and the model it names differs from the configured
       `model_name`, log at INFO: the winning model id, that it won as
       last-known-good, and the `model_name` it was preferred over. Log nothing when
       the two agree. See Flagged calls 10 — and read the rationale there before
       changing anything about this line or this rung's position.
    5. **`model_name`**, if it is among the filtered candidates.
    6. **Sole surviving candidate**, when exactly one does.
    7. **Refuse to guess** — return the configured `model_name` unconfirmed, and
       raise if there is no configured model. Never return an arbitrary candidate.

    **Last-known-good sits ABOVE `model_name`, deliberately.** `MODEL_NAME` is
    documented in `config.py` as a tracked *default*, not an authoritative pin: it
    can name a model that is not loaded at all, which is exactly the
    `exo-model-notfound-502` failure this ladder exists to prevent. Last-known-good
    is verified still-loaded by construction — rung 4 only fires when the remembered
    model is in the filtered candidate set. Verified-loaded evidence beats an
    unverified default. It also buys continuity: a second model appearing in LM
    Studio must not make a running system abandon the model it has been successfully
    using. The operator keeps absolute control through rungs 2 and 3, which are
    above it.

    **Deliberate exception: an operator pin is absolute.** If `model_task_{kind}` or
    `model_preferred` names a model that is loaded but does NOT survive the
    capability filter, the pin still wins — an operator who names a model gets that
    model. It MUST log a WARNING naming the pinned model, the task kind, and the
    capability it lacks, so the operator finds out from the log rather than from a
    malformed structured response. A pin naming a model that is not loaded at all is
    ignored and the ladder continues. See Flagged calls 8.

    Scoring is deliberately absent — per ADR decision 4, scoring always produces a
    winner, so keeping it would mean the refusal rung never fires.

    `invalidate()` marks the cache stale so the next `for_task` refetches. A refresh
    that raises must not propagate: hold the last successfully-resolved profile per
    task kind and serve it with a warning, per ADR decision 1. Only when there is no
    last-known-good does resolution fall through to `StaticModelSource`.

    That same stored last-known-good is what rung 4 reads. One value, two roles:
    on a FAILED refresh it is served unconditionally (the backend told us nothing,
    so the previous answer is the best answer); on a SUCCESSFUL refresh it is only a
    tiebreaker, and only if the model it names is still among the filtered
    candidates. Do not let the second role weaken the first — a failed refresh must
    still serve last-known-good even if that model would not have survived the
    filter, because a failed refresh means the capability data is stale too.

    Add two settings to `sentinel-core/app/config.py`: `model_context_cap`
    (`MODEL_CONTEXT_CAP`, `int | None`, default None) and `model_ttl_seconds`
    (`MODEL_TTL_SECONDS`, float, default 60.0). The cap is applied as a ceiling on
    top of the resolved window and never raises it. ADR decision 2 requires the cap
    to exist because "what the server accepts" and "what produces usable output"
    are different numbers — a 71936-token context on the 24 GB host drove the model
    into repetition loops and 200s timeouts. The ADR does not name the setting; this
    plan names it `MODEL_CONTEXT_CAP` (see Flagged calls).

    Do not touch the embedding path. Per ADR decision 5 the embedding model is
    observed, never re-pointed: `probe_embedding_model_loaded`,
    `settings.embedding_model`, and ADR-0004's exact-string match and dimension
    checks all stand unchanged. Re-pointing embedding calls at whatever is loaded
    would invalidate every entry in `ops/sweeps/embedding-index.json`, and
    ADR-0004's fail-soft posture would turn that into silently empty recall.

    Do not narrow `response_anomaly`'s control-token detection to the loaded
    family. Per ADR decision 6 the profile may add family-specific signals; it must
    not replace the general ones, because narrowing the regex would blind the
    detector to the wrong-family token leakage that motivated the ADR. This plan
    adds no signal at all — it just leaves the detector alone.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - `sentinel-core/app/model.py` exists and defines `ModelProfile`, `ModelSource`,
      `LMStudioModelSource`, `StaticModelSource`, `ActiveModel`.
    - `sentinel-core/tests/test_model.py` covers every case listed in `<behavior>`.
    - The suite reports `717 + N passed, 12 skipped, 0 failed`; no previously-passing
      test fails.
    - `ActiveModel` has no scoring function and no rubric — the refusal rung is
      reachable.
    - The capability filter runs BEFORE the preference rungs and narrows the
      candidate set; a test asserts each of the seven rungs in turn is the one that
      decides.
    - A loaded-but-incapable operator pin wins AND emits a WARNING naming the model,
      the task kind and the missing capability — asserted via caplog, not inferred.
    - Last-known-good (rung 4) beats `model_name` (rung 5): a warm last-known-good
      wins even when `MODEL_NAME` names a different loaded candidate. Asserted
      directly — this is the case the earlier, wrong ordering got backwards.
    - The last-known-good tiebreaker fires with two live candidates and no pin, and
      is discarded when the remembered model is no longer loaded, falling through to
      `model_name` and below.
    - Rung 4 logs an INFO divergence line naming the winner, the reason
      (last-known-good) and the `model_name` it beat — and logs nothing when the two
      agree. Both directions asserted via caplog.
    - The context-window ladder has exactly three rungs and no family-constant rung;
      no code in `app/model.py` reads `context_window` off a family profile.
    - The LM Studio adapter issues exactly one `/api/v0/models` request per refresh,
      asserted by counting fake-client calls in the TTL test.
  </acceptance_criteria>

  <done>
    `ActiveModel.for_task("chat")` resolves the live loaded model end to end from a
    fake `/api/v0/models` payload — right id, 119552 context, ChatML stop sequences,
    `tool_use` capability — behind a 60s TTL with working invalidate and
    last-known-good, and the suite is green.
  </done>
</task>

<task type="auto">
  <name>Task 2: build_provider_router reduced to composing the seam; recorded model name fixed (Defect B)</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<action>` and `<verify>` verbatim.
  </delegation>

  <read_first>
    - sentinel-core/app/composition.py:75-272 (ProviderRouterBundle and the whole of
      build_provider_router — the registry build, the discovery call, the
      active_model table, the context-window lookup, the stop-sequence profile fetch,
      the provider map, and primary/fallback selection)
    - sentinel-core/app/composition.py:275-450 (build_application's consumption of the
      bundle and the RouteContext construction)
    - sentinel-core/app/state.py:50-70 (the RouteContext fields the bundle populates)
    - sentinel-core/app/services/message_request_factory.py (all 17 lines)
    - sentinel-core/app/services/message_processing.py:150-210 (where req.model_name
      reaches the anomaly log and the session summary frontmatter)
    - sentinel-core/tests/test_composition.py (16 collected tests — the contract this
      refactor must keep)
  </read_first>

  <files>sentinel-core/app/composition.py, sentinel-core/app/state.py, sentinel-core/app/services/message_request_factory.py, sentinel-core/tests/test_composition.py, sentinel-core/tests/test_message_request_factory.py, sentinel-core/tests/test_message_processor.py</files>

  <behavior>
    - Given a fake `/api/v0/models` serving the live payload, `build_provider_router`
      produces a router whose LM Studio provider names the discovered model, and a
      bundle whose context window is 119552.
    - Given an unreachable backend, `build_provider_router` still returns — it never
      raises, matching its existing documented contract.
    - `build_message_request` sets `model_name` to the id of the model that will
      actually answer, not `settings.model_name`. Assert this with a settings
      `MODEL_NAME` that deliberately differs from the resolved model id, so a
      regression cannot pass by coincidence.
    - The session summary frontmatter `model:` line and the `response-anomaly:`
      warning's `model=` field both carry that same resolved id.
  </behavior>

  <action>
    Reduce `build_provider_router` to composition. It constructs an
    `LMStudioModelSource` and a `StaticModelSource`, wraps them in one `ActiveModel`,
    and asks that object for the facts it used to fetch three separate times. The
    three provider-keyed tables inside it — `active_model_table`,
    `stop_seq_base_url_table`, `stop_seq_model_table` — become redundant once the
    seam answers; leave them in place for now only where removing them would change
    behaviour, since Plan 03 owns their deletion along with `ProviderRouterBundle`.
    The goal of this task is that the function performs **one** metadata refresh
    through `ActiveModel`, not three independent HTTP fetches.

    Keep `ProviderRouterBundle` for now. It is on the ADR's deletion list, but that
    is step 4 — deleting it here would drag the RouteContext rewiring into this plan
    and break the "each step green on its own" rule. Populate its `context_window`
    and `lmstudio_stop_sequences` fields from the resolved chat profile instead of
    from the two separate lookups.

    Carry the `ActiveModel` instance onto `app.state` / `RouteContext` as a new
    field. This is what Plan 02 reads to resolve a profile per request and what
    Plan 03 reads when the bundle's three scalars go away. Do not make the
    application graph mutable to do it — per the ADR's rejected options,
    `build_application` is deliberately construct-once, and the mutability lives
    inside `ActiveModel`'s cache, not in the graph.

    Fix Defect B in `message_request_factory.py`. Line 13 currently sets
    `model_name` from `ctx.settings.model_name`, which is the `MODEL_NAME` default —
    so session summary frontmatter and anomaly logs have been recording
    configuration rather than the model that answered. This is the same class of
    failure as the ADR's opening observation: the container named `google/gemma-4-31b`
    for two days while LM Studio served `qwen/qwen3.8-27b`. Read the resolved chat
    profile off the route context and use its id. Keep the existing
    `getattr(ctx, ..., None) or None` defensive shape for the stop sequences — the
    three `_LazyRouteCtx` test fixtures rely on attributes being absent, and those
    fixtures are not replaced until Plan 02 Task 1.

    Update `tests/test_composition.py` where it asserts the old three-fetch shape,
    and add the Defect B regression to `tests/test_message_request_factory.py`
    (the factory's own test file), with an end-to-end assertion in
    `tests/test_message_processor.py` that the recorded name reaches the session
    summary frontmatter and the anomaly warning. Do not weaken any
    existing assertion to make it pass — if an existing test genuinely encoded the
    three-fetch behaviour, replace it with an assertion about the one-refresh
    behaviour and say so in the SUMMARY.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - `build_provider_router` obtains its model id, context window and stop sequences
      from one `ActiveModel` refresh rather than from three independent fetches.
    - `RouteContext` exposes the `ActiveModel` instance.
    - A test with `MODEL_NAME` deliberately differing from the resolved model id
      asserts that the recorded name is the resolved one.
    - `build_provider_router` still never raises on an unreachable backend.
    - Suite green, no previously-passing test lost.
  </acceptance_criteria>

  <done>
    Composition asks the seam once instead of fetching three times, the ActiveModel
    is reachable from the route context, and the model recorded in session summaries
    and anomaly logs is the one that actually answered.
  </done>
</task>

<task type="auto">
  <name>Task 3: probe_classifier_model_ready rewired onto ActiveModel — coverage verified either side</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<action>` and `<verify>` verbatim, and tell it
    explicitly that this probe gates a destructive vault sweep and that weakening
    its fail-closed contract is the failure mode to avoid.
  </delegation>

  <read_first>
    - sentinel-core/app/services/model_selector.py:472-595 (the probe, its
      fail-closed contract, and the documented deliberate divergence from
      resolve_structured_model)
    - sentinel-core/app/routes/note.py:140-180 (the destructive-sweep gate — the
      probe's only production caller)
    - sentinel-core/tests/test_model_selector.py (10 collected tests, all of this
      probe — this is the before-coverage baseline)
    - sentinel-core/tests/test_model_resolution.py (2 collected tests, one of which
      is the probe/resolver parity guarantee)
  </read_first>

  <files>sentinel-core/app/services/model_selector.py, sentinel-core/tests/test_model_selector.py</files>

  <behavior>
    Record the before-coverage explicitly, then preserve every case:

    - Empty loaded set returns not-ready.
    - Loaded models present but none supporting the structured task returns
      not-ready — the sole-candidate rung must NOT be treated as ready.
    - Any HTTP, JSON or schema failure returns not-ready; the probe never raises.
    - A genuinely loaded `tool_use`-capable model returns ready.
    - New: the probe and the structured resolution path agree on the same model id
      for the live payload. This replaces the parity guarantee currently held by
      `tests/test_model_resolution.py`, which Plan 03 deletes; landing the
      replacement here means Plan 03 never has an unguarded window.
  </behavior>

  <action>
    Rewire `probe_classifier_model_ready` to answer from `ActiveModel` instead of
    from `get_loaded_models` + `_fetch_live_capabilities` + `select_model` + `_score`.
    Per the ADR the probe is rewired, never deleted — it gates whether a destructive
    vault sweep may run, and its coverage is verified either side of the change.

    Keep the signature callable from `routes/note.py:169` or update that call site
    in the same change; either is fine, but the gate must remain in place and must
    remain the thing `routes/note.py` consults before a sweep. Do not relax it into
    a truthiness check on a resolved model string: the whole point of the existing
    contract is that a model can be *resolvable* without being *ready*, and a
    degraded classifier must never drive vault mutations.

    With capabilities read directly from the backend, the probe's readiness question
    becomes: does the profile `ActiveModel` would hand the structured path actually
    carry the `tool_use` capability? That is a stronger and simpler test than
    `_score(...) > 0` and it removes the documented deliberate divergence between
    the probe and the real resolver — both now ask the same object the same
    question. Say so in the docstring, and delete the paragraph describing the
    divergence, since it will no longer be true.

    Preserve the fail-closed posture exactly. Every rung that returned not-ready
    before must still return not-ready: no models loaded, models loaded but none
    capable, and any exception at all. A probe that starts reporting ready in a case
    where it previously reported not-ready is a regression even if the suite passes.

    Before editing, run the suite and record how many tests currently exercise this
    probe. After editing, record the same number. Put both numbers in the SUMMARY.
    A drop is a coverage regression and must be restored, not explained.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - The probe resolves through `ActiveModel` and no longer calls `_score`.
    - `routes/note.py` still gates the destructive sweep on the probe.
    - Probe test count after >= probe test count before, both recorded in the SUMMARY.
    - All four fail-closed cases still return not-ready.
    - The probe/resolver parity case is covered against the seam.
    - Suite green.
  </acceptance_criteria>

  <done>
    The destructive-sweep gate asks `ActiveModel` whether the structured-task profile
    carries `tool_use`, fails closed on every path it failed closed on before, and
    is covered by at least as many tests as it was.
  </done>
</task>

</tasks>

## Flagged calls

1. **`MODEL_CONTEXT_CAP` naming.** ADR decision 2 mandates an operator cap on top of
   the resolution order but does not name the setting. Chosen: `MODEL_CONTEXT_CAP`,
   alongside `MODEL_TTL_SECONDS` for the TTL the ADR fixes at 60s.
2. **Capability filters for `chat` and `fast`.** ADR decision 4 defines the filter
   only for `structured`. Chosen: `chat` and `fast` impose no capability
   requirement, so every loaded non-embedding model is a candidate for them. This
   keeps the refusal rung meaningful for those kinds too.
3. **`invalidate()` here, retry-once in Plan 02.** ADR decision 1 pairs the TTL with
   invalidate-and-retry-once on the `litellm.NotFoundError` path. The retry belongs
   in `ProviderRouter`, which cannot re-resolve until `complete()` carries a profile
   — that is Plan 02. This plan ships and unit-tests `invalidate()`; Plan 02 calls it.
4. **`ProviderRouterBundle` survives this plan.** The ADR lists it as deleted, but
   under step 4. Deleting it here would pull the RouteContext rewiring forward and
   break the green-on-its-own rule.
5. **ADR decision 5's `/health` disagreement report is already satisfied.**
   `probe_embedding_model_loaded` does an exact-string match against
   `settings.embedding_model` and `/health` already surfaces the result as a
   non-blocking field (`main.py:129-151`). No new work; recorded as a must-have so a
   future change cannot silently drop it.
6. **The three `model_task_*` settings gain their first consumer.** They exist in
   `config.py:84-86` with no reader anywhere. ADR decision 4's rejected alternative
   ("one profile rather than one per task kind") notes they already exist; this plan
   wires them as the top *preference* rung of the ladder (below the capability
   filter — see 8).
7. **The context-window ladder has no family-constant rung.** ADR decision 2 as
   originally written read `loaded → max → family constant → 4096`. It was amended
   2026-09-07 during plan review and the family rung was dropped, because it
   contradicted the same design's removal of `FamilyProfile.context_window`; because
   `/api/v0/models` always returns `max_context_length`, making the rung unreachable
   in practice (a backend that answers with neither field is an unreachable backend,
   which resolves through `StaticModelSource`); and because the family constants are
   wrong where it would matter — qwen2 declares 32768 against a real 262144 max /
   119552 loaded. A declared, logged 4096 is a better floor than a lying constant.
   `FAMILY_PROFILES` is still read here, but only for **stop sequences**, never for
   a context window. Decisions 2 and 12 are now consistent and Plan 04's field
   removal has no live consumer to trip over.
8. **Capability filter first; operator pins are absolute anyway.** The filter is rung
   0, not a late rung: a filter that runs after preference has already chosen cannot
   narrow anything. The one exception is deliberate — a `model_task_*` or
   `model_preferred` naming a loaded-but-incapable model still wins, because an
   operator who names a model gets that model, and silently overriding an explicit
   pin is a worse failure than a degraded structured response. The cost of the
   exception is paid with a WARNING naming the model, the task kind and the missing
   capability, and that warning is asserted by a test rather than assumed.
9. **Last-known-good is both a failure path and a tiebreaker, and it outranks
   `model_name`.** ADR decision 1 names it only as the failed-refresh path. This plan
   also makes it **rung 4** of the normal ladder — above `model_name`, below the two
   operator pins. Corrected 2026-09-07: an intermediate draft had it at rung 6,
   below both `model_name` and the sole-candidate rung. That was wrong.
   `MODEL_NAME` is documented in `config.py` as a tracked *default*, not an
   authoritative pin, and it can name a model that is not loaded at all — precisely
   the `exo-model-notfound-502` failure. Last-known-good is verified still-loaded by
   construction, because rung 4 only fires when the remembered model survives the
   candidate filter. Verified-loaded evidence beats an unverified default, and the
   ordering buys continuity: a second model appearing in LM Studio must not make a
   running system abandon the model it has been successfully using. Operator control
   is unaffected — `model_task_{kind}` and `model_preferred` are both above it. The
   two roles share one stored value but not one rule: the failed-refresh path serves
   it unconditionally, the tiebreaker only while it is still loaded.
10. **Rung 4 logs when it diverges from `model_name` — and the reason is NOT what it
   might look like.** Record the correct rationale, because the wrong one is
   available and plausible and would get someone to "fix" the ordering.

   **NOT the reason:** "a running system will keep ignoring a *changed* `MODEL_NAME`
   until the remembered model is unloaded." That scenario cannot occur. `settings` is
   a module-level pydantic singleton read once at import (`config.py`), so
   `MODEL_NAME` cannot change within a running process; changing it requires a
   restart, and a restart clears last-known-good. Rung 4 can never shadow a *changed*
   `MODEL_NAME`. Do not reorder the ladder to solve this — there is nothing here to
   solve.

   **The actual reason, which does occur:** `MODEL_NAME` names model A; the system
   resolves model B at some rung; B becomes last-known-good; from then on rung 4
   keeps selecting B while an operator reading `.env` sees A. Nothing announces the
   divergence. That is the same class of failure this entire ADR exists to fix — a
   config value and the live system disagreeing with nothing saying so, which is how
   the container spent two days naming `google/gemma-4-31b` while LM Studio served
   `qwen/qwen3.8-27b`. The line is logged only when the two differ, so the common
   case stays quiet and the divergence is the thing that stands out.

<output>
Create `.planning/quick/260907-amx-active-model-seam/01-SUMMARY.md` when done,
recording: the exact post-change suite counts, the probe test count before and
after, N (new tests added), and any existing test whose assertion was replaced
rather than kept.
</output>
