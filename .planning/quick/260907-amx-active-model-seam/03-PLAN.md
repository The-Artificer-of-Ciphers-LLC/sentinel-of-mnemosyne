---
quick_id: 260907-amx
slug: active-model-seam
plan: 03
adr_step: 4
type: execute
wave: 3
depends_on: ["02"]
files_deleted:
  - sentinel-core/app/services/model_resolution.py
  - sentinel-core/tests/test_model_resolution.py
  - modules/pathfinder/app/model_selector.py
  - modules/pathfinder/app/resolve_model.py
  - modules/pathfinder/tests/test_model_selector.py
  - modules/pathfinder/tests/test_resolve_model.py
files_modified:
  - sentinel-core/app/services/model_selector.py
  - sentinel-core/app/services/note_classifier.py
  - sentinel-core/app/services/pipeline_orchestrator.py
  - sentinel-core/app/services/six_rs/reduce.py
  - sentinel-core/app/services/six_rs/reflect.py
  - sentinel-core/app/services/six_rs/rethink.py
  - sentinel-core/app/services/model_registry.py
  - sentinel-core/app/composition.py
  - sentinel-core/app/state.py
  - sentinel-core/app/services/message_processing.py
  - sentinel-core/app/services/message_request_factory.py
  - sentinel-core/tests/test_model_selector.py
  - sentinel-core/tests/test_model_selector_discovery.py
  - sentinel-core/tests/test_model_registry.py
  - sentinel-core/tests/test_model.py
  - sentinel-core/tests/conftest.py
  # The three former _LazyRouteCtx modules were converted to the shared conftest
  # helper in Plan 02 Task 1. They are listed here only because removing the two
  # RouteContext scalars may touch a direct assertion in them; if none does, they
  # are untouched by this plan and that is the expected outcome.
  - sentinel-core/tests/test_message.py
  - sentinel-core/tests/test_auth.py
  - sentinel-core/tests/test_integration_obsidian_llm.py
  - modules/pathfinder/app/rule_query.py
  - modules/pathfinder/app/routes/rule.py
  - modules/pathfinder/app/routes/npc.py
  - modules/pathfinder/app/routes/session.py
  - modules/pathfinder/app/routes/harvest.py
  - modules/pathfinder/tests/test_rule_query.py
autonomous: true
requirements: [ADR-0007-S4, ADR-0007-D4, ADR-0007-D7, ADR-0007-CONSEQ-DELETIONS]
verification:
  core: "cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q"
  pathfinder: "cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/modules/pathfinder && /Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/.venv/bin/python -m pytest tests/ -q"
  baseline_in: "whatever 02-SUMMARY.md recorded"
  expected_out: |
    PATHFINDER — one formula, no flat number. An earlier draft asserted "386 passed"
    flatly, which silently assumed Plan 02 added nothing to pathfinder; Plan 02
    predicts N02pf = 2. Corrected 2026-09-07:

      pathfinder = 405 + N02pf - 19 + N03pf

    where 19 = 16 (tests/test_model_selector.py) + 3 (tests/test_resolve_model.py),
    and N03pf is the count of REPLACEMENT tests this plan adds under the mapping
    table in Task 2. With Plan 02's predicted N02pf = 2 and N03pf = 0 (all 19
    replacements landing in sentinel-core's tests/test_model.py rather than in
    pathfinder — see the table), that is 405 + 2 - 19 = 388 passed, 0 failed.
    If 02-SUMMARY.md records a different N02pf, substitute it; the formula is the
    contract and 388 is only its current evaluation. Cross-check the number you get
    against 02-SUMMARY.md's recorded pathfinder total before running anything.

    SENTINEL-CORE = (02-SUMMARY.md total) - 2 (tests/test_model_resolution.py, whose
    probe/resolver parity guarantee was already re-landed against the seam in Plan 01
    Task 3) - (tests in tests/test_model_selector_discovery.py,
    tests/test_model_selector.py and tests/test_model_registry.py that exercised only
    deleted machinery; the registry file contributes up to 5, see the ground-truth
    table) + (the replacements this plan adds in tests/test_model.py, including the
    19-test mapping from Task 2 that lands core-side).

    Enumerate every removed test BY NAME in 03-SUMMARY.md with the reason it went and
    where its guarantee now lives. A removed test with no named successor is a
    coverage regression, not a deletion.
must_haves:
  truths:
    - "There is exactly one implementation of 'which model is loaded and what can it do' in the repository."
    - "Pathfinder holds no model-discovery code and no model-selection code (ADR decision 7)."
    - "The refuse-to-guess behaviour survives the removal of scoring — with several capable models loaded and nothing disambiguating, resolution RAISES rather than returning a configured model the backend never said it had (ADR decision 4 as amended 2026-09-08)."
    - "probe_classifier_model_ready still gates the destructive vault sweep and still fails closed, with coverage no lower than before this plan."
    - "No test was deleted without a named successor holding its guarantee."
  artifacts:
    - .planning/quick/260907-amx-active-model-seam/03-SUMMARY.md
  key_links:
    - "The five structured-completion call sites resolve through ActiveModel.for_task('structured') instead of resolve_structured_model."
    - "RouteContext no longer carries context_window / lmstudio_stop_sequences, and the shared conftest helper Plan 02 introduced (a real ActiveModel over a real StaticModelSource) stops setting them."
    - "build_model_registry keeps only its seed role, and tests/test_model_registry.py's five live-path tests are rewritten or mapped to successors in tests/test_model.py."
---

<objective>
Delete the duplicated implementations the seam replaced: `model_resolution.py`,
`select_model._score`, pathfinder's `model_selector.py` and `resolve_model.py` and
their tests, the registry's LM Studio live path and the five
`test_model_registry.py` tests that drove it, and `ProviderRouterBundle` plus the
three provider-keyed tables inside `build_provider_router`. (The three duplicated
`_LazyRouteCtx` fixtures were moved forward to Plan 02 Task 1 on 2026-09-07; what
remains here is removing the two scalars from the shared helper that replaced them.)
Every pathfinder test deleted here has a named successor or an explicit
behaviour-deleted judgement — see the 19-row table in Task 2.

Purpose: ADR-0007 step 4. The ADR's core claim is that the concept was implemented
three times in three wrong shapes. Plans 01 and 02 built the right one; until the
other two are gone the fragmentation is worse, not better.

Output: one implementation, a smaller `model_selector.py`, and test fixtures that
substitute a real `StaticModelSource` instead of hand-rolling a fake route context
three times.
</objective>

<context>
@docs/adr/0007-active-model-seam.md
@.planning/quick/260907-amx-active-model-seam/README.md
@.planning/quick/260907-amx-active-model-seam/01-SUMMARY.md
@.planning/quick/260907-amx-active-model-seam/02-SUMMARY.md
@sentinel-core/app/services/model_resolution.py
@sentinel-core/app/services/model_selector.py
@sentinel-core/app/model.py
@modules/pathfinder/app/resolve_model.py
</context>

## Verified ground truth (2026-09-07 — do not re-derive)

Deletion targets and their exact blast radius:

**`sentinel-core/app/services/model_resolution.py`** — `resolve_structured_model`
returns a 3-tuple, holds no cache, and takes four dependency-injection keyword
overrides purely so tests can substitute fakes. Five call sites:

| Call site | Line |
|---|---|
| `app/services/pipeline_orchestrator.py` | 271 |
| `app/services/note_classifier.py` | 211 |
| `app/services/six_rs/rethink.py` | 114 |
| `app/services/six_rs/reduce.py` | 173 |
| `app/services/six_rs/reflect.py` | 65 |

Its test file `tests/test_model_resolution.py` holds 2 collected tests, one of
which is the probe/resolver parity guarantee. **Plan 01 Task 3 already re-landed
that guarantee against the seam**, which is why this file can go now and not before.

**`select_model._score`** (`model_selector.py:210-285`) — replaced by capability
filtering per ADR decision 4. Scoring always produces a winner, so keeping it means
the refusal rung never fires. `_score` is also called directly by
`probe_classifier_model_ready` at line 588 — Plan 01 Task 3 already moved the probe
off it.

**Also absorbed into `app/model.py` and therefore deletable** (see Flagged calls —
the ADR names only `_score`, this is an interpretation): `get_loaded_models`
(:99-127, process-lifetime dict cache with no TTL — the exact staleness the seam
exists to fix), `_fetch_live_capabilities` (:288-317, the one-request-per-model
fan-out the single `/api/v0/models` list call replaces), `discover_active_model`
(:325-364), `discover_lmstudio_model` (:367-390), `_discover_model_for_provider`
(:393-469), and `select_model` itself (:130-207) once nothing calls it.

**Must survive in `model_selector.py`:** `strip_litellm_prefix`,
`ensure_litellm_prefix`, `probe_embedding_model_loaded` (untouched per ADR decision
5), and `probe_classifier_model_ready` (rewired in Plan 01).

**Non-obvious consumer:** `model_registry.py:27,173-174` imports
`discover_active_model` and `strip_litellm_prefix`. `build_model_registry`'s LM
Studio live-fetch path is subsumed by `LMStudioModelSource`; the registry keeps only
its seed role, which becomes `StaticModelSource`'s data.

**`sentinel-core/tests/test_model_registry.py` — 7 collected tests, and it is a
first-class deletion target of Task 1, not collateral.** Five of the seven drive
`build_model_registry` through the LM Studio live path this task removes:

| Test | Line | What it drives |
|---|---|---|
| `test_lmstudio_registry_uses_fetched_context_window` | 34 | live `/api/v0/models` fetch → `registry[...].context_window == 32768` |
| `test_lmstudio_registry_falls_back_to_seed_on_unavailable` | 44 | live fetch raises → seed fallback + 4096 sentinel |
| `test_lmstudio_registry_uses_discovered_model_name` | 74 | `discover_active_model` via `/v1/models` → discovered key, 65536 window |
| `test_lmstudio_registry_fallback_when_discovery_fails` | 97 | discovery fails → `MODEL_NAME` key |
| `test_lmstudio_registry_no_discovery_when_disabled` | 115 | `MODEL_AUTO_DISCOVER=false` → no discovery attempt |

The other two — `test_claude_registry_skips_live_fetch_without_key` (:56) and
`test_seed_always_present_in_registry` (:63) — cover the seed role, which survives
this plan. (`test_seed_always_present_in_registry` and
`test_lmstudio_registry_falls_back_to_seed_on_unavailable` both assert
`"local-model" in registry`, which is what Plan 04's seed trim then breaks — that
is Plan 04's problem and it is flagged there.)

**`sentinel-core/tests/test_model_selector.py` — 10 collected tests**, all of
`probe_classifier_model_ready`, rewired in Plan 01 Task 3. They are edited here only
where they still reach `select_model` / `get_loaded_models` machinery this task
deletes. Naming it here because Task 1's prose referenced it while its `<files>` did
not.

**`modules/pathfinder/app/model_selector.py`** — an independently drifted copy whose
tests still assert the blind `loaded[0]` fallback sentinel-core removed as unsound
after `exo-model-notfound-502`. 16 collected tests in
`tests/test_model_selector.py`.

**`modules/pathfinder/app/resolve_model.py`** — 3 collected tests in
`tests/test_resolve_model.py`. Imported by four route modules
(`rule.py:32`, `npc.py:42`, `session.py:31`, `harvest.py:36`) and passed into
`RuleQueryDependencies.resolve_model` at `rule.py:173`. Call sites:
`session.py:440,510`, `npc.py:365,419,713,913`, `harvest.py:186`.
Plan 02 already stopped the resolved values being consumed.

**The three `_LazyRouteCtx` fixtures:** `tests/test_message.py:90`,
`tests/test_auth.py:92`, `tests/test_integration_obsidian_llm.py:107` — each
followed by `app.state.route_ctx = _LazyRouteCtx()`. **These are Plan 02 Task 1's
work, not this plan's** (moved forward 2026-09-07: Plan 02 makes `MessageProcessor`
resolve from `ActiveModel`, and a fake without one cannot be green, so Plan 02 could
not have satisfied the green-on-its-own rule while leaving them). By the time this
plan runs they are already a shared helper in `tests/conftest.py` over a real
`StaticModelSource`; Task 3's residue is only removing the two scalars from it.

**`ProviderRouterBundle`** — defined at `composition.py:75-112`, consumed at
`composition.py:309-332,414-417,441-446`. Referenced nowhere else in the repo
outside `composition.py` and the ADR itself.

<tasks>

<task type="auto">
  <name>Task 1: delete model_resolution.py and _score; move the five structured call sites onto the seam</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<action>` and `<verify>` verbatim, plus the
    deletion-target table above. Tell it explicitly that `probe_classifier_model_ready`
    gates a destructive vault sweep and is not in scope for deletion.
  </delegation>

  <read_first>
    - sentinel-core/app/services/model_resolution.py (all 146 lines, including every
      except-warn fallback — each one is a graceful-degrade path that must have an
      equivalent on the seam, not just disappear)
    - sentinel-core/app/services/model_selector.py:99-317 (get_loaded_models,
      select_model, _score, _fetch_live_capabilities)
    - sentinel-core/app/services/model_selector.py:325-469 (the three discovery
      functions)
    - The five call sites in the table above, each in its surrounding function
    - sentinel-core/app/services/model_registry.py:160-180 (the discover_active_model
      consumer)
    - sentinel-core/tests/test_model_registry.py (all 133 lines, 7 tests — five of
      them drive the live path being deleted; see the table in ground truth)
    - sentinel-core/tests/test_model_selector.py (10 tests — named in this task's
      prose and now in its `<files>`)
    - sentinel-core/app/model.py (Plan 01's seam — the replacement)
  </read_first>

  <files>sentinel-core/app/services/model_resolution.py, sentinel-core/app/services/model_selector.py, sentinel-core/app/services/note_classifier.py, sentinel-core/app/services/pipeline_orchestrator.py, sentinel-core/app/services/six_rs/reduce.py, sentinel-core/app/services/six_rs/reflect.py, sentinel-core/app/services/six_rs/rethink.py, sentinel-core/app/services/model_registry.py, sentinel-core/tests/test_model_resolution.py, sentinel-core/tests/test_model_selector_discovery.py, sentinel-core/tests/test_model_selector.py, sentinel-core/tests/test_model_registry.py, sentinel-core/tests/test_model.py</files>

  <behavior>
    - Each of the five structured-completion call sites resolves its model through
      `ActiveModel.for_task("structured")` and still calls
      `acompletion_with_profile` with its own `response_format` unchanged.
    - Each call site still degrades gracefully when the backend is unreachable:
      whatever `resolve_structured_model`'s except-warn path produced for that call
      site, the seam's last-known-good or static fallback must produce an equivalent.
      `note_classifier` in particular must still coerce to its safe default rather
      than raising.
    - A 6 Rs pipeline run issues at most one `/api/v0/models` metadata fetch per TTL
      window, down from roughly five times (1 + N + 1). Assert this with a
      call-counting fake across a simulated multi-stage run — this is the ADR's
      stated latency consequence and the only place it is directly observable.
    - Refuse to guess still holds with `_score` gone: two `tool_use`-capable models
      loaded, nothing disambiguating, resolution RAISES (ADR decision 4 as amended
      2026-09-08 — never a configured model the backend did not offer).
    - Keep the two failure modes distinct at every one of the five call sites. An
      UNREACHABLE backend still degrades gracefully through `StaticModelSource` and
      must not raise — `note_classifier` in particular still coerces to its safe
      default. An AMBIGUOUS LIVE backend raises. Same call, opposite handling, and
      conflating them would either resurrect the phantom or make an offline dev box
      unusable. Test both per call site, not just the graceful one.
  </behavior>

  <action>
    Move each of the five structured call sites onto `ActiveModel.for_task("structured")`,
    then delete `app/services/model_resolution.py` and `tests/test_model_resolution.py`.
    The four dependency-injection keyword overrides on `resolve_structured_model`
    exist only so tests can substitute fakes; the seam's replacement for that is
    `StaticModelSource`, which is a real implementation rather than a patch surface.
    Do not carry the keyword-override pattern onto the seam.

    Delete `_score` and the scoring branch of `select_model`. Per ADR decision 4,
    task-capability filtering replaces scoring: `_score` existed to compensate for
    `litellm.get_model_info` knowing nothing about local model ids, and
    `/api/v0/models` supplies `capabilities` directly. Once `_score` is gone,
    `select_model` has no reason to exist beside `ActiveModel.for_task` — delete it
    too, along with `get_loaded_models`, `_fetch_live_capabilities`,
    `discover_active_model`, `discover_lmstudio_model` and
    `_discover_model_for_provider`, all of which the seam absorbed. See Flagged
    calls: the ADR names only `_score`, but leaving the rest would preserve exactly
    the two-shapes-one-concept split the ADR removes.

    Leave `strip_litellm_prefix`, `ensure_litellm_prefix`, `probe_embedding_model_loaded`
    and `probe_classifier_model_ready` in place. The embedding probe is untouched per
    ADR decision 5 — the embedding model is observed, never re-pointed, and
    re-pointing it would invalidate every entry in `ops/sweeps/embedding-index.json`
    and, under ADR-0004's fail-soft posture, turn a loud model swap into quiet memory
    loss.

    Rework `build_model_registry`'s use of `discover_active_model`. The registry's
    live LM Studio path is now `LMStudioModelSource`'s job; the registry keeps its
    seed role only. Do not delete `models-seed.json` or trim it here — trimming it to
    cloud models is Plan 04's cleanup.

    **`sentinel-core/tests/test_model_registry.py` moves with that rework and is in
    this task's `<files>`.** Five of its seven tests
    (`test_lmstudio_registry_uses_fetched_context_window:34`,
    `test_lmstudio_registry_falls_back_to_seed_on_unavailable:44`,
    `test_lmstudio_registry_uses_discovered_model_name:74`,
    `test_lmstudio_registry_fallback_when_discovery_fails:97`,
    `test_lmstudio_registry_no_discovery_when_disabled:115`) drive exactly the live
    path being removed and cannot pass unchanged; they were absent from every earlier
    draft of this plan's file lists and expected-count arithmetic. For each, either
    rewrite it against the seed-only registry or name its successor in
    `tests/test_model.py` — the fetched-context-window case in particular is now
    covered by Plan 01's three-rung ladder test and the discovery cases by Plan 01's
    candidate-filtering and TTL tests. The two seed tests (`:56`, `:63`) survive
    unchanged here.

    Before deleting any test, list what it asserts. `tests/test_model_selector_discovery.py`
    holds 18 collected tests, `tests/test_model_selector.py` holds 10, and
    `tests/test_model_registry.py` holds 7; some cover machinery being deleted and
    some cover the two probes and the seed role, which survive. For every test you
    remove, name in the SUMMARY the successor that now holds its guarantee. If there
    is no successor, write one first — a removed test with no named successor is a
    coverage regression dressed as a deletion.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - `app/services/model_resolution.py` no longer exists and nothing imports it.
    - `_score` and `select_model` no longer exist; the refusal behaviour is covered
      by a test against `ActiveModel`.
    - `probe_embedding_model_loaded` and `probe_classifier_model_ready` both still
      exist and both still pass their full test sets.
    - The one-fetch-per-TTL-window assertion passes.
    - Every removed test is named in the SUMMARY with its successor.
    - Suite green.
  </acceptance_criteria>

  <done>
    The structured path resolves through the same object the chat path does, the
    scoring rubric is gone, and the refusal rung is reachable for the first time.
  </done>
</task>

<task type="auto">
  <name>Task 2 (CROSS-SUITE — verify core AND pathfinder): delete pathfinder's model_selector.py and resolve_model.py, and land the 19 replacement tests</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<action>` and `<verify>` verbatim, plus the
    pathfinder blast-radius facts above and the note that Plan 02 already stopped
    the resolved values being consumed. Tell it explicitly that this task spans BOTH
    codebases — deletions in `modules/pathfinder/`, four replacement tests in
    `sentinel-core/tests/test_model.py` — and that both suites must be run with their
    own interpreters before it reports done.
  </delegation>

  <read_first>
    - modules/pathfinder/app/resolve_model.py (all 123 lines — especially its own
      docstring, which already states that Phase 42 made its return value discarded
      at every call site)
    - modules/pathfinder/app/model_selector.py (the drifted copy; its tests still
      assert the blind loaded[0] fallback sentinel-core removed as unsound)
    - modules/pathfinder/app/rule_query.py:52-66 and :118-136 (RuleQueryDependencies
      and the resolve_model call pair)
    - modules/pathfinder/app/routes/rule.py:32,173 (the deps wiring)
    - The seven `await resolve(...)` call sites listed in the ground-truth section
    - modules/pathfinder/tests/test_rule_query.py:25,48 (which asserts resolve_model
      is NOT awaited on the cache-hit path — that intent survives, its mechanism does not)
  </read_first>

  <files>modules/pathfinder/app/resolve_model.py, modules/pathfinder/app/model_selector.py, modules/pathfinder/app/rule_query.py, modules/pathfinder/app/routes/rule.py, modules/pathfinder/app/routes/npc.py, modules/pathfinder/app/routes/session.py, modules/pathfinder/app/routes/harvest.py, modules/pathfinder/tests/test_model_selector.py, modules/pathfinder/tests/test_resolve_model.py, modules/pathfinder/tests/test_rule_query.py, sentinel-core/tests/test_model.py</files>

  <behavior>
    - No module under `modules/pathfinder/` performs model discovery or model
      selection. Pathfinder receives model facts from core over HTTP or not at all
      (ADR decision 7).
    - The rule-query cache-hit path still short-circuits before any avoidable work,
      which is what `test_rule_query.py`'s "must not resolve model" assertion was
      protecting. Preserve that intent against whatever the path now does first.
    - Every pathfinder route that previously called `resolve(...)` still works and
      still reaches core.
  </behavior>

  <action>
    Delete `modules/pathfinder/app/model_selector.py`, `modules/pathfinder/app/resolve_model.py`,
    `modules/pathfinder/tests/test_model_selector.py` and
    `modules/pathfinder/tests/test_resolve_model.py`. Remove the four
    `from app.resolve_model import resolve` imports and the seven `await resolve(...)`
    call sites, and remove the `resolve_model` field from `RuleQueryDependencies`
    together with the `resolve_model=resolve` wiring at `rule.py:173`.

    This is a clean removal, not a rewrite. Verified 2026-09-07: pathfinder has zero
    `litellm.acompletion` call sites, every completion goes through
    `SentinelCoreClient.complete()`, and `llm.py`'s own docstrings describe its
    `model` / `api_base` / `profile` parameters as vestigial and not forwarded. Plan
    02 already removed the parameters. **No new core endpoint is required** — see
    Flagged calls, where the ADR's stale "Pathfinder continues to call LM Studio
    directly for rule_query" line is recorded.

    **RULED 2026-09-07: the 19 tests are REPLACED, not dropped.** An earlier draft
    deleted all 19 as "the one unreplaced deletion in the plan set". That is not
    acceptable: most of them guard behaviour that still exists, just in a different
    module. Work the table below top to bottom. Every row is either a named successor
    test that must exist and pass when this task is done, or an explicit
    behaviour-deleted-with-the-module justification. Reproduce the table with a
    PASS/WRITTEN mark per row in 03-SUMMARY.md.

    | # | Deleted test | Disposition |
    |---|---|---|
    | 1 | `test_model_selector.py::test_get_loaded_models_queries_and_caches` | **Replaced** — `test_model.py` TTL case (two `for_task` calls inside the window issue one `/api/v0/models` fetch). Plan 01. |
    | 2 | `::test_get_loaded_models_force_refresh_bypasses_cache` | **Replaced** — `test_model.py` `invalidate()` case. Plan 01. |
    | 3 | `::test_get_loaded_models_returns_empty_on_network_error` | **Replaced** — `test_model.py` cold last-known-good case (HTTP raises → falls through to `StaticModelSource`, never raises). Plan 01. |
    | 4 | `::test_get_loaded_models_filters_malformed_entries` | **Replaced — WRITE IT HERE.** Plan 01 has no malformed-entry case. Add to `test_model.py`: an `/api/v0/models` payload containing an entry with no `id`, an entry with `id: null`, a non-dict entry and an empty-string `id` yields only the valid candidates, and does not raise. |
    | 5 | `::test_select_chat_prefers_large_context` | **Behaviour deleted with the module** — `_score`'s max_tokens ranking. ADR decision 4: scoring always produces a winner, so keeping it means the refusal rung never fires. |
    | 6 | `::test_select_structured_requires_function_calling` | **Replaced** — `test_model.py` `for_task("structured")` includes a `tool_use` candidate and excludes one without. Plan 01. The one scoring behaviour that survives, as a filter. |
    | 7 | `::test_select_fast_prefers_smaller_context_above_minimum` | **Behaviour deleted with the module** — the fast-tier 4K floor was a scoring heuristic. `fast` now imposes no capability requirement (Plan 01 Flagged calls 2) and the operator expresses a fast tier with `model_task_fast`. |
    | 8 | `::test_preference_overrides_scoring` | **Replaced** — `test_model.py` absolute-pin case: a `model_task_{kind}` naming a loaded-but-incapable model still wins and logs a WARNING. Plan 01 (amended). |
    | 9 | `::test_falls_back_to_default_when_in_loaded_and_no_match` | **Replaced** — `test_model.py` rung 5 (`model_name` among the filtered candidates). Plan 01. Two constraints on the successor: run it against a COLD `ActiveModel`, or rung 4 decides first; and keep the original's `in_loaded` premise, which is now load-bearing rather than incidental — under the amended decision 4 rung 5 fires ONLY when `model_name` is among the loaded candidates, so a successor that drops that premise is testing a rung that no longer exists. |
    | 10 | `::test_falls_back_to_first_loaded_when_default_not_in_loaded` | **Replaced by its inverse, deliberately** — `test_model.py` refuse-to-guess case asserts the OPPOSITE: resolution RAISES. It returns neither `loaded[0]` nor the configured model. Under ADR decision 4 as amended 2026-09-08 a non-loaded `MODEL_NAME` is discarded like any other non-loaded config value, so there is nothing left to return. Record in the SUMMARY that this is now a DOUBLE inversion against the original: not `loaded[0]`, and not the default either. |
    | 11 | `::test_uses_default_when_loaded_is_empty` | **Replaced, and split in two** — the original conflated two cases the amended decision 4 separates. NO live backend (adapter unreachable) → `StaticModelSource` serves `MODEL_NAME` as its data, which is that setting's only surviving role: Plan 01's `StaticModelSource`-alone case. LIVE backend returning zero candidates → raises, not a default. Assert both; asserting only the first would let a live-but-empty backend quietly resurrect the phantom. |
    | 12 | `::test_raises_when_no_loaded_and_no_default` | **Replaced** — `test_model.py` "with no configured model either, it raises". Plan 01. |
    | 13 | `::test_preference_skipped_when_not_in_loaded` | **Replaced** — `test_model.py` "a pin naming a model that is not loaded at all is ignored and the ladder continues". Plan 01 (amended). |
    | 14 | `::test_preference_matches_when_prefixed_but_loaded_is_bare` | **Replaced — WRITE IT HERE.** Add to `test_model.py`: `model_preferred="openai/mlx-community/foo"` matches a bare candidate id `mlx-community/foo`. `strip_litellm_prefix` / `ensure_litellm_prefix` survive in `model_selector.py` and `ModelProfile` carries both ids — but nothing currently tests that `ActiveModel` normalises before comparing. |
    | 15 | `::test_default_matches_when_prefixed_but_loaded_is_bare` | **Replaced — WRITE IT HERE.** Same as 14 for the `model_name` rung (rung 5); start the `ActiveModel` cold so rung 4 does not pre-empt it. The prefixed default must be LOADED — prefix normalisation decides whether a configured id *matches* a candidate, never whether a non-loaded id may be returned. |
    | 16 | `::test_default_prefix_mismatch_previously_fell_through_to_arbitrary_first_loaded` | **Replaced — WRITE IT HERE, highest value of the three.** This is a live regression guard: a prefixed `MODEL_NAME` that IS loaded must be honoured and must not fall through to an arbitrary candidate. Under the new ladder the fall-through target is the refusal rung rather than `loaded[0]`, so assert the pinned model is returned with three candidates loaded — again from a cold `ActiveModel`, since `MODEL_NAME` is rung 5 and last-known-good is rung 4. Add the mirror case the amended decision 4 makes newly important: the same prefixed `MODEL_NAME` when it is NOT among the three loaded candidates must RAISE, not return the phantom. Prefix normalisation must not become a back door for a non-loaded id. |
    | 17 | `test_resolve_model.py::test_resolve_model_adds_openai_prefix_to_bare_name` | **Replaced** — covered by 14/15 plus `ModelProfile`'s litellm-prefixed id field, asserted in Plan 01's end-to-end `for_task("chat")` case. |
    | 18 | `::test_resolve_model_preserves_existing_prefix` | **Replaced** — same; `ensure_litellm_prefix` must not double-prefix. Assert it in the 14/15 test. |
    | 19 | `::test_resolve_model_falls_back_to_placeholder_when_discovery_empty` | **Behaviour deleted with the module** — the inert `openai/unused-core-resolves-model` placeholder existed only so pathfinder could name *something*. After Plan 02 pathfinder names a task, not a model. Successor: Plan 02's acceptance criterion "no model, api_base or profile value originates in pathfinder". |

    Rows 4, 14, 15 and 16 are the four that must actually be WRITTEN in this task —
    everything else already exists or is a justified deletion. They land in
    `sentinel-core/tests/test_model.py`, not in pathfinder, because that is where the
    behaviour now lives; that is why the pathfinder arithmetic uses N03pf = 0.
    Do not skip 14–16 on the grounds that the prefix helpers "still exist" — they
    exist untested at the point that matters, which is `ActiveModel`'s comparison.

    **This task is deliberately CROSS-SUITE and its `<verify>` runs BOTH suites with
    BOTH interpreters.** Its deletions are pathfinder-side; four of its replacement
    tests are sentinel-core-side. That pairing is intentional — it is what keeps the
    19-row mapping a single reviewable unit instead of a deletion here and a promise
    of coverage somewhere else. The consequence for an executor: running only
    `modules/pathfinder`'s suite and seeing green proves nothing about rows 4, 14, 15
    and 16, and running only `sentinel-core`'s proves nothing about the deletions.
    Both commands, both interpreters, every time. `modules/pathfinder` needs its OWN
    `modules/pathfinder/.venv/bin/python` — the core venv cannot import `rapidfuzz`
    and silently collects ZERO pathfinder tests, which looks like a pass.

    `test_rule_query.py`'s two tests must be updated, not deleted. Its
    `AsyncMock(side_effect=AssertionError("must not resolve model"))` guard and its
    `assert_not_awaited()` were protecting a real property: the cache-hit path must
    not do avoidable work before returning. Re-express that against whatever the path
    now does first.
  </action>

  <verify>
    <!-- CROSS-SUITE TASK. Both commands are REQUIRED and neither substitutes for the
         other: the deletions are pathfinder-side, the row 4/14/15/16 replacements are
         sentinel-core-side. Note the two DIFFERENT interpreters — the core venv
         cannot import rapidfuzz and collects zero pathfinder tests, which reports as
         a pass. Do not run one, see green, and call the task done. -->
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/modules/pathfinder && /Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/.venv/bin/python -m pytest tests/ -q</automated>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - The four pathfinder files are gone and nothing imports them.
    - `RuleQueryDependencies` has no `resolve_model` field.
    - The pathfinder suite reports `405 + N02pf - 19 + N03pf` passed — 388 with Plan
      02's predicted N02pf = 2 and N03pf = 0 — 0 failed, with the arithmetic written
      out in the SUMMARY against the number 02-SUMMARY.md actually recorded.
    - The 19-row disposition table is reproduced in the SUMMARY with every row marked
      PASS (successor exists and passes) or JUSTIFIED (behaviour deleted with the
      module). No row is blank.
    - Rows 4, 14, 15 and 16 exist as new tests in `sentinel-core/tests/test_model.py`
      and pass.
    - The cache-hit short-circuit property is still asserted by a test.
    - BOTH suites were run, each with its own interpreter, and both counts are in the
      SUMMARY. A pathfinder-only run is not evidence this task is done; neither is a
      core-only run. A pathfinder collection count of 0 means the wrong interpreter
      was used, not that the suite passed.
  </acceptance_criteria>

  <done>
    Pathfinder holds no model-discovery or model-selection code, and the drifted copy
    that still believed in the unsound `loaded[0]` fallback is gone.
  </done>
</task>

<task type="auto">
  <name>Task 3: delete ProviderRouterBundle, the three provider-keyed tables, and the two RouteContext scalars</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<action>` and `<verify>` verbatim.
  </delegation>

  <read_first>
    - sentinel-core/app/composition.py:75-112 (ProviderRouterBundle) and :115-272
      (the three provider-keyed tables: active_model_table, stop_seq_base_url_table,
      stop_seq_model_table — each carrying its own Pitfall-fix comment explaining
      why the table form replaced a ternary chain)
    - sentinel-core/app/composition.py:275-450 (every bundle consumer)
    - sentinel-core/app/state.py:50-70 (the RouteContext scalars being removed)
    - sentinel-core/app/services/message_request_factory.py and
      app/services/message_processing.py:20-40 (MessageRequest's context_window and
      stop_sequences fields)
    - sentinel-core/tests/conftest.py — the shared route-context helper Plan 02 Task 1
      landed to replace the three `_LazyRouteCtx` fakes. Read it before touching the
      three test modules; the two scalars come out of THIS file, not out of them.
    - tests/test_message.py, tests/test_auth.py,
      tests/test_integration_obsidian_llm.py — skim only, to confirm no `_LazyRouteCtx`
      class survives and no test asserts on the two removed scalars directly.
  </read_first>

  <files>sentinel-core/app/composition.py, sentinel-core/app/state.py, sentinel-core/app/services/message_processing.py, sentinel-core/app/services/message_request_factory.py, sentinel-core/tests/conftest.py, sentinel-core/tests/test_composition.py, sentinel-core/tests/test_message.py, sentinel-core/tests/test_auth.py, sentinel-core/tests/test_integration_obsidian_llm.py</files>

  <behavior>
    - `build_provider_router` returns the router and the ActiveModel, with no
      three-scalar bundle.
    - `RouteContext` no longer carries `context_window` or `lmstudio_stop_sequences`;
      consumers read the profile instead. `ai_provider_name` STAYS — `/status` reads
      it at `routes/status.py:24` and that is a different question from which model
      answered.
    - The three test modules still construct their route context from the shared
      conftest helper (a real `ActiveModel` over a real `StaticModelSource`, landed
      in Plan 02) and keep passing once the two scalars leave that helper.
    - An unknown `AI_PROVIDER` value still logs a warning rather than silently
      adopting another provider's model or base URL — that is what the three tables'
      Pitfall-1/2/3 fixes bought, and removing the tables must not sell it back.
  </behavior>

  <action>
    Delete `ProviderRouterBundle` and have `build_provider_router` return the router
    and the `ActiveModel`. Delete the three provider-keyed tables — `active_model_table`,
    `stop_seq_base_url_table` and `stop_seq_model_table` — whose whole job was
    reconciling three separately-fetched scalars against `settings.ai_provider`. The
    seam answers that question once. But keep the warning behaviour their Pitfall
    fixes introduced: an unrecognised `AI_PROVIDER` must still produce a WARNING and
    must not silently fall through to another backend's model name or base URL. Carry
    that check into the composition path explicitly rather than letting it vanish with
    the tables.

    Remove `context_window` and `lmstudio_stop_sequences` from `RouteContext` and
    from `MessageRequest`, and delete the `getattr(ctx, "lmstudio_stop_sequences", ...)`
    defensiveness in `message_request_factory.py` — that shape existed only because
    the three fake route contexts might not define the attribute, and those fakes
    were replaced in Plan 02 Task 1. Keep `ai_provider_name`.

    **The three `_LazyRouteCtx` fixtures were already replaced in Plan 02 Task 1** —
    moved forward 2026-09-07 because Plan 02 makes `MessageProcessor` resolve from
    `ActiveModel`, which a fake with no `ActiveModel` cannot satisfy, so Plan 02
    could not have been green on its own otherwise. The shared helper already exists
    in `sentinel-core/tests/conftest.py`, building a real route context around a real
    `ActiveModel` over a `StaticModelSource`. This task's remaining share is only to
    drop `context_window` and `lmstudio_stop_sequences` from that one helper when the
    scalars leave `RouteContext`. If any `_LazyRouteCtx` class is still present when
    this task starts, that is a Plan 02 leftover — fix Plan 02's work, do not
    re-implement the replacement here. The three test modules themselves should need
    no edit; if one does, it is because it asserted on a removed scalar directly, and
    that single assertion is what changes.

    Do not make the application graph mutable to accommodate any of this.
    `build_application` is deliberately construct-once; the ADR rejected rebuilding
    `provider_map` on model change for exactly that reason. All the mutability lives
    inside `ActiveModel`'s TTL cache.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - `ProviderRouterBundle` and the three provider-keyed tables no longer exist.
    - `RouteContext` and `MessageRequest` no longer carry the two scalars;
      `ai_provider_name` still exists and `/status` still reports it.
    - An unrecognised `AI_PROVIDER` still produces a warning, covered by a test.
    - The Plan 02 conftest helper no longer sets `context_window` or
      `lmstudio_stop_sequences`, and no hand-rolled route-context class remains in
      any of the three modules (verify — this was Plan 02's job, not this task's).
    - `build_application` is still construct-once.
    - Suite green.
  </acceptance_criteria>

  <done>
    The startup-pinned three-scalar bundle is gone from production code and from the
    tests that had been imitating it, and the tests substitute a real adapter instead
    of a fake.
  </done>
</task>

</tasks>

## Flagged calls

1. **The teardown of `model_selector.py` goes beyond `_score`.** ADR-0007's
   Consequences name only `select_model._score` among that module's contents. This
   plan also deletes `select_model`, `get_loaded_models`, `_fetch_live_capabilities`,
   `discover_active_model`, `discover_lmstudio_model` and
   `_discover_model_for_provider`, because `app/model.py` absorbed all of them and
   leaving them would preserve the two-shapes-one-concept split the ADR set out to
   remove. `strip_litellm_prefix`, `ensure_litellm_prefix` and both probes stay.
   If this is wrong, the correction is to keep them — nothing downstream depends on
   their absence.
2. **ADR-0007's "Pathfinder continues to call LM Studio directly for rule_query" was
   stale and is ALREADY CORRECTED in the ADR** — struck through and rewritten in
   commit `307b916`, ADR lines 157-169. Verified 2026-09-07: zero
   `litellm.acompletion` call sites anywhere in `modules/pathfinder/app/`; every
   completion routes through `SentinelCoreClient.complete()`; `embed_texts` routes
   through core's `POST /embeddings` and its own docstring calls its `model` and
   `api_base` parameters vestigial and not forwarded. The practical effect is
   favourable — deleting `resolve_model.py` needs no new core model-facts endpoint.
   No plan in this set needs to make that edit; Plan 04 Task 3 now only verifies it.
3. **RULED 2026-09-07: the 19 deleted pathfinder tests are REPLACED, not dropped.**
   An earlier draft called this "the only unreplaced deletion in the plan set". Task
   2 now carries a 19-row disposition table: 15 rows have a named successor, 4
   (`test_select_chat_prefers_large_context`,
   `test_select_fast_prefers_smaller_context_above_minimum`,
   `test_resolve_model_falls_back_to_placeholder_when_discovery_empty`, and the
   inverted `test_falls_back_to_first_loaded_when_default_not_in_loaded`) are
   explicit behaviour-deleted-with-the-module judgements. Four successors
   (malformed-entry filtering and the three prefix-normalisation cases) did not
   previously exist anywhere and are written in Task 2.
4. **`ai_provider_name` survives the bundle.** The ADR lists the bundle as deleted
   but `/status` reads `ai_provider_name` for a legitimately different question
   (which backend, not which model). Keeping it.
5. **`models-seed.json` is not trimmed here.** The ADR pairs the trim with
   `StaticModelSource`, but doing it in the same plan as the deletions would couple a
   data change to a large structural change. It is Plan 04's.

<output>
Create `.planning/quick/260907-amx-active-model-seam/03-SUMMARY.md` when done,
recording: both suites' exact post-change counts with the arithmetic written out,
EVERY removed test by name with its successor (or an explicit "no successor,
because…"), and the probe test count compared against Plan 01's recorded figure.
</output>
