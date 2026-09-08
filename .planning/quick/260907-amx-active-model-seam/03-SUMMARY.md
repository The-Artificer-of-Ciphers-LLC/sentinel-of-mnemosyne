---
quick_id: 260907-amx
slug: active-model-seam
plan: "03"
adr_step: 4
status: complete
requirements: [ADR-0007-S4, ADR-0007-D4, ADR-0007-D7, ADR-0007-CONSEQ-DELETIONS]
worktree: .claude/worktrees/agent-a81c8c5a46b5b6d30
branch: worktree-agent-a81c8c5a46b5b6d30
base: 9c9cb79
commits:
  - f1289f0  # Task 1 — one implementation of which model is loaded
  - bb3ae5c  # Task 2 — pathfinder's drifted copy, and the 19-row mapping
  - d210ee5  # Task 3 — the startup-pinned scalar bundle
suite:
  core_in: "816 passed, 12 skipped"
  core_out: "820 passed, 12 skipped"
  pathfinder_in: "407 passed"
  pathfinder_out: "388 passed"
  shared_in: "50 passed"
  shared_out: "50 passed"
  N03_core: 4          # net; 23 deleted, 27 written
  N03pf: 0             # every replacement landed core-side
  deleted_tests: 42    # 23 core + 19 pathfinder
probe_coverage:
  before: 14           # Plan 01's recorded figure
  after: 15
key-files:
  created:
    - sentinel-core/app/services/structured_model.py
    - sentinel-core/tests/test_structured_model.py
  deleted:
    - sentinel-core/app/services/model_resolution.py
    - sentinel-core/tests/test_model_resolution.py
    - modules/pathfinder/app/model_selector.py
    - modules/pathfinder/app/resolve_model.py
    - modules/pathfinder/tests/test_model_selector.py
    - modules/pathfinder/tests/test_resolve_model.py
  modified:
    - sentinel-core/app/clients/litellm_provider.py
    - sentinel-core/app/composition.py
    - sentinel-core/app/model.py
    - sentinel-core/app/routes/status.py
    - sentinel-core/app/services/message_processing.py
    - sentinel-core/app/services/message_request_factory.py
    - sentinel-core/app/services/model_registry.py
    - sentinel-core/app/services/model_selector.py
    - sentinel-core/app/services/note_classifier.py
    - sentinel-core/app/services/pipeline_orchestrator.py
    - sentinel-core/app/services/six_rs/reduce.py
    - sentinel-core/app/services/six_rs/reflect.py
    - sentinel-core/app/services/six_rs/rethink.py
    - sentinel-core/app/state.py
    - sentinel-core/tests/conftest.py
    - sentinel-core/tests/test_composition.py
    - sentinel-core/tests/test_litellm_provider.py
    - sentinel-core/tests/test_message_processor.py
    - sentinel-core/tests/test_message_request_factory.py
    - sentinel-core/tests/test_model.py
    - sentinel-core/tests/test_model_registry.py
    - sentinel-core/tests/test_model_selector.py
    - sentinel-core/tests/test_model_selector_discovery.py
    - sentinel-core/tests/test_note_classifier.py
    - sentinel-core/tests/test_pipeline_orchestrator.py
    - sentinel-core/tests/test_recall.py
    - sentinel-core/tests/test_six_rs_reduce.py
    - sentinel-core/tests/test_six_rs_reflect.py
    - sentinel-core/tests/test_six_rs_rethink.py
    - sentinel-core/tests/test_status.py
    - sentinel-core/tests/test_vault_inventory.py
    - modules/pathfinder/app/routes/harvest.py
    - modules/pathfinder/app/routes/npc.py
    - modules/pathfinder/app/routes/rule.py
    - modules/pathfinder/app/routes/session.py
    - modules/pathfinder/app/rule_query.py
    - modules/pathfinder/tests/test_rule_query.py
---

# Plan 03 — the deletions

There is now exactly one implementation of "which model is loaded and what can
it do". The structured path resolves through the same `ActiveModel` the chat
path does; pathfinder holds no model-discovery and no model-selection code; and
the three scalars that used to be resolved once at startup and pinned for the
process lifetime are gone from `RouteContext`, `AppGraph` and `MessageRequest`.

## The numbers, with the arithmetic written out

Every count below was measured with the suite's own interpreter. The pathfinder
suite needs `modules/pathfinder/.venv/bin/python`; under the core venv it
collects ZERO tests and reports a pass.

| Suite | In | Out |
|---|---|---|
| sentinel-core | 816 passed, 12 skipped | **820 passed, 12 skipped** |
| modules/pathfinder | 407 passed | **388 passed** |
| shared | 50 passed | **50 passed** |

**Pathfinder — the plan's formula, evaluated.** `405 + N02pf - 19 + N03pf`.
02-SUMMARY.md records N02pf = 2, so the baseline entering this plan was 407,
not 405. `407 - 19 + 0 = 388`. Confirmed by measurement. N03pf is 0 because all
four replacement tests land in `sentinel-core/tests/test_model.py`, which is
where the behaviour now lives.

**Core — 23 deleted, 27 written, net +4.** `816 + 4 = 820`.

| File | Before | After | Delta |
|---|---|---|---|
| `tests/test_model_resolution.py` | 2 | — | **−2** (file deleted) |
| `tests/test_model_selector_discovery.py` | 18 | 6 | **−12** |
| `tests/test_model_registry.py` | 7 | 4 | **−3** |
| `tests/test_litellm_provider.py` | 15 | 13 | **−2** |
| `tests/test_model_selector.py` | 14 | 15 | +1 (−1 `_score`, +2 probe) |
| `tests/test_note_classifier.py` | 13 | 14 | +1 (−1, +2) |
| `tests/test_model.py` | 62 | 68 | +6 |
| `tests/test_structured_model.py` | — | 4 | +4 (new file) |
| `tests/test_six_rs_reduce.py` | 7 | 9 | +2 |
| `tests/test_six_rs_reflect.py` | 3 | 5 | +2 |
| `tests/test_six_rs_rethink.py` | 3 | 5 | +2 |
| `tests/test_pipeline_orchestrator.py` | 16 | 18 | +2 |
| `tests/test_message_processor.py` | 18 | 19 | +1 |
| `tests/test_composition.py` | 20 | 21 | +1 |
| `tests/test_status.py` | 8 | 9 | +1 |
| **Total** | | | **+4** |

## Probe coverage — 14 before, 15 after

`probe_classifier_model_ready` gates a destructive vault sweep, so its coverage
is recorded either side rather than assumed fine.

**Before: 14** — Plan 01's recorded figure: 13 probe cases in
`tests/test_model_selector.py` plus the probe/resolver parity case in
`tests/test_model_resolution.py`.

**After: 15** — all 14 `test_probe_classifier_*` cases plus
`test_probe_and_structured_resolution_agree_on_the_same_model`, all in
`tests/test_model_selector.py`.

Deleting `test_model_resolution.py` removes one of the fourteen, so the naive
outcome was a drop to 13 — the guarantee duplicated, the count reduced. Two
cases were added rather than explaining that away, and they are not padding:
**every pre-existing probe case reaches the backend through the v0 FALLBACK.**
`lmstudio_handler` answers 404 on `/api/v1/models` on purpose, because that is
the shape the probe's original tests were written against. v1 is the preferred
generation and the one the live box answers on, so until now the destructive
sweep gate had never been exercised on the path production actually takes. v1
nests tool use at `capabilities.trained_for_tool_use` where v0 puts the string
`"tool_use"` in a list; a probe that only ran against v0 could keep passing
while answering not-ready on every modern backend.

- `test_probe_classifier_ready_true_on_the_v1_generation`
- `test_probe_classifier_ready_false_on_the_v1_generation_without_tool_use`

Nothing in this plan touched the nine original probe assertions or the four
Plan 01 added.

## The 19-row disposition table, honoured row by row

Reproduced from Task 2 with a mark per row. **PASS** = the named successor
exists and passes. **JUSTIFIED** = behaviour deleted with the module, with the
reason. No row is blank; no row's premise turned out false.

| # | Deleted test | Mark | Outcome |
|---|---|---|---|
| 1 | `test_model_selector.py::test_get_loaded_models_queries_and_caches` | **PASS** | `test_model.py::test_two_resolutions_inside_the_ttl_window_issue_one_fetch` (Plan 01), and now also `test_structured_model.py::test_a_multi_stage_run_issues_one_model_list_fetch_per_ttl_window`. |
| 2 | `::test_get_loaded_models_force_refresh_bypasses_cache` | **PASS** | `test_model.py`'s `invalidate()` case (Plan 01); `test_structured_model.py::test_the_ttl_expiring_costs_exactly_one_more_fetch` covers the expiry half. |
| 3 | `::test_get_loaded_models_returns_empty_on_network_error` | **PASS** | `test_model.py`'s cold last-known-good case — HTTP raises, resolution falls through to `StaticModelSource`, nothing raises. Also asserted end-to-end at all five call sites (see below). |
| 4 | `::test_get_loaded_models_filters_malformed_entries` | **WRITTEN + PASS** | `test_model.py::test_malformed_entries_are_filtered_on_both_api_generations`. Four shapes (no identity field, `null` identity, non-dict entry, empty-string identity) against both a v1 payload keyed on `key` and a v0 payload keyed on `id`. |
| 5 | `::test_select_chat_prefers_large_context` | **JUSTIFIED** | `_score`'s max_tokens ranking. ADR decision 4: scoring always produces a winner, so keeping it means the refusal rung never fires. |
| 6 | `::test_select_structured_requires_function_calling` | **PASS** | `test_model.py`'s `for_task("structured")` capability-filter cases (Plan 01). The one scoring behaviour that survives, as a filter. |
| 7 | `::test_select_fast_prefers_smaller_context_above_minimum` | **JUSTIFIED** | The fast-tier 4K floor was a scoring heuristic. `fast` imposes no capability requirement (Plan 01 Flagged calls 2); an operator expresses a fast tier with `model_task_fast`. |
| 8 | `::test_preference_overrides_scoring` | **PASS** | `test_model.py`'s absolute-pin case — a `model_task_{kind}` naming a loaded-but-incapable model still wins and logs a WARNING (Plan 01, amended). |
| 9 | `::test_falls_back_to_default_when_in_loaded_and_no_match` | **PASS** | `test_model.py`'s rung-5 case (Plan 01), run cold and keeping the `in_loaded` premise. Row 15's new test is a second instance of the same rung with the prefix twist. |
| 10 | `::test_falls_back_to_first_loaded_when_default_not_in_loaded` | **JUSTIFIED (double inversion)** | The successor asserts the OPPOSITE, twice over: resolution returns neither `loaded[0]` nor the configured model — it RAISES. Under decision 4 as amended a non-loaded `MODEL_NAME` is discarded like any other non-loaded config value, so there is nothing left to return. `test_model.py`'s refuse-to-guess case, and the second half of row 16's new test. |
| 11 | `::test_uses_default_when_loaded_is_empty` | **PASS (split in two)** | NO live backend → `test_model.py::test_static_model_source_alone_resolves_when_there_is_no_backend`. LIVE backend reporting zero candidates → the refusal case. Both assert; asserting only the first would let a live-but-empty backend quietly resurrect the phantom. |
| 12 | `::test_raises_when_no_loaded_and_no_default` | **PASS** | `test_model.py`'s "with no configured model either, it raises" (Plan 01). |
| 13 | `::test_preference_skipped_when_not_in_loaded` | **PASS** | `test_model.py`'s "a pin naming a model that is not loaded at all is ignored and the ladder continues" (Plan 01, amended). |
| 14 | `::test_preference_matches_when_prefixed_but_loaded_is_bare` | **WRITTEN + PASS** | `test_model.py::test_a_prefixed_preference_matches_a_bare_candidate_id`. Also asserts `ensure_litellm_prefix` does not double-prefix (row 18). **Needed an implementation change, not just a test — see below.** |
| 15 | `::test_default_matches_when_prefixed_but_loaded_is_bare` | **WRITTEN + PASS** | `test_model.py::test_a_prefixed_default_matches_a_bare_loaded_candidate`, cold so rung 4 cannot pre-empt rung 5, with the prefixed default LOADED. |
| 16 | `::test_default_prefix_mismatch_previously_fell_through_to_arbitrary_first_loaded` | **WRITTEN + PASS** | `test_model.py::test_a_prefixed_default_that_is_loaded_wins_and_one_that_is_not_raises`. Three candidates loaded, the pinned one honoured and not `loaded[0]`; and the mirror case — the same prefixed id when NOT loaded RAISES. Prefix normalisation is not a back door for a phantom. |
| 17 | `test_resolve_model.py::test_resolve_model_adds_openai_prefix_to_bare_name` | **PASS** | Covered by rows 14/15 plus `ModelProfile.litellm_model`, asserted in Plan 01's end-to-end `for_task("chat")` case and in `test_static_model_source_alone_resolves_when_there_is_no_backend` (`openai/google/gemma-4-31b`). |
| 18 | `::test_resolve_model_preserves_existing_prefix` | **PASS** | Asserted inside row 14's test: `resolved.litellm_model == "openai/mlx-community/foo"`, with the message naming the no-double-prefix guarantee. |
| 19 | `::test_resolve_model_falls_back_to_placeholder_when_discovery_empty` | **JUSTIFIED** | The inert `openai/unused-core-resolves-model` placeholder existed only so pathfinder could name *something*. After Plan 02 pathfinder names a task, not a model. Successor: Plan 02's acceptance criterion "no model, api_base or profile value originates in pathfinder", now structurally true — the module that produced the placeholder is deleted. |

**15 PASS / 4 JUSTIFIED**, matching the plan's own split. Four rows (4, 14, 15,
16) were written here.

## Every other removed test, by name, with its successor

### `tests/test_model_resolution.py` — file deleted (2)

- `test_probe_and_resolve_structured_model_select_same_model_id_for_local_tool_use`
  → `test_model_selector.py::test_probe_and_structured_resolution_agree_on_the_same_model`.
  Plan 01 Task 3 landed that case specifically so this deletion leaves no
  unguarded window; **verified present and passing before the file was
  removed.**
- `test_resolve_structured_model_capability_fetch_failure_is_non_fatal`
  → the guarantee ("a failed capability fetch must not raise") is now "an
  UNREACHABLE backend degrades through `StaticModelSource` and never raises",
  asserted at **all five** structured call sites (listed below) plus
  `test_model.py`'s cold last-known-good case. The per-model capability fetch
  it guarded no longer exists at all.

### `tests/test_model_selector.py` — 1 removed

- `test_score_cloud_model_via_litellm_unchanged` → **no successor, deliberately.**

  This is the one the brief flagged, and it is recorded explicitly rather than
  swept out. It is NOT a probe test: it tests `_score`, and it was the tenth
  collected test in a file the plan described as "10 collected, all of this
  probe". It is deleted **with its subject** — ADR decision 4 removes scoring
  entirely, so "a cloud model keeps scoring via litellm" is not a property
  anything in the repository still has. Nothing was lost that still exists.

### `tests/test_model_selector_discovery.py` — 12 removed, 6 survive

The six survivors are the five `probe_embedding_model_loaded` cases (untouched
per ADR decision 5) and `test_ai_provider_rejects_unknown_value_at_settings_construction`.

| Removed | Successor |
|---|---|
| `test_discovery_off_returns_model_name_prefixed` | `test_model.py::test_static_model_source_alone_resolves_when_there_is_no_backend`; `MODEL_AUTO_DISCOVER=false` keeps its meaning by composition leaving the live source out (`test_composition.py`'s existing cases all set it false). |
| `test_discovery_off_no_double_prefix` | Row 14's new test, which asserts the no-double-prefix outcome directly. |
| `test_discovery_on_single_model` | `test_model.py`'s rung-6 sole-candidate case, plus `test_composition.py::test_build_provider_router_names_the_discovered_model_and_loaded_window`. |
| `test_discovery_honors_model_preferred` | `test_model.py`'s `MODEL_PREFERRED` pin cases (Plan 01) and row 14. |
| `test_discovery_unreachable_falls_back` | `test_model.py::test_static_model_source_alone_resolves_when_there_is_no_backend` and the cold last-known-good case. |
| `test_discovery_empty_models_falls_back` | **Inverted successor.** `test_model.py`'s live-but-empty refusal. A reachable backend reporting nothing now RAISES rather than answering from configuration — decision 4 as amended. Recorded as an inversion, not a like-for-like replacement. |
| `test_discovery_ollama_provider` | `test_model.py::test_static_model_source_serves_declared_4096_for_ollama_and_llamacpp` (asserts the `ollama/` tag), plus `test_composition.py::test_build_provider_router_picks_primary_from_settings`, which now asserts an ollama primary gets its own seam. |
| `test_discovery_no_double_prefix_with_slash_in_discovered` | Row 14, plus the v0/v1 parse tests in `test_model.py` that assert `litellm_model` on an HF-namespaced id. |
| `test_select_model_ambiguous_catalog_prefers_configured_default_over_catalog_zero` | **Inverted successor.** `test_model.py`'s refuse-to-guess raise. The "never `loaded[0]`" half survives verbatim in row 16's new test; the "prefer the configured default" half is exactly what decision 4 as amended removed. |
| `test_select_model_ambiguous_catalog_no_default_raises_loudly` | `test_model.py`'s "with no configured model either, it raises" (Plan 01). |
| `test_select_model_sole_candidate_is_unambiguous` | `test_model.py`'s rung-6 sole-candidate case. |
| `test_discovery_except_handler_falls_back_to_settings_model_name_not_loaded_zero` | Deleted with `discover_active_model`. The "never `loaded[0]`" guarantee is row 16; composition's own non-fatal degrade is covered by `test_composition.py::test_build_provider_router_never_raises_on_unreachable_backend`. |

### `tests/test_model_registry.py` — 5 removed, 2 written, 2 survive unchanged

Rewritten rather than dropped, and each new case asserts something the original
could not: that `build_model_registry` issues **no LM Studio HTTP at all** (the
transport raises on any request, so a re-introduced fetch fails the test rather
than passing quietly against a mock).

- `test_lmstudio_registry_uses_fetched_context_window` and
  `test_lmstudio_registry_uses_discovered_model_name`
  → `test_lmstudio_registry_records_the_seam_resolved_model`. One case carries
  both: the seam resolves `discovered-model` while `MODEL_NAME` is
  `test-model`, and the registry keys on the model actually loaded, carries its
  real 65536 window, and does not invent a `MODEL_NAME` entry.
- `test_lmstudio_registry_falls_back_to_seed_on_unavailable`,
  `test_lmstudio_registry_fallback_when_discovery_fails` and
  `test_lmstudio_registry_no_discovery_when_disabled`
  → `test_lmstudio_registry_is_seed_only_without_the_seam`. No discovery, no
  fetch, no invented entry, seed intact. The third row's guarantee
  (`MODEL_AUTO_DISCOVER=false` → no discovery attempt) is now structural: there
  is no discovery code left to attempt.
- `test_claude_registry_skips_live_fetch_without_key` and
  `test_seed_always_present_in_registry` survive unchanged, as the plan predicted.

**One behaviour change worth stating.** Without seam values the registry no
longer contributes a `MODEL_NAME` entry for LM Studio. No live consumer notices:
`build_provider_router` always supplies them (its `_resolve_lmstudio_profile`
degrade returns `MODEL_NAME` + the declared 4096 rather than raising), and the
non-LM-Studio registry lookup is the only other reader.

### `tests/test_litellm_provider.py` — 2 removed

- `test_get_context_window_from_lmstudio_returns_value`
  → `test_model.py::test_context_window_falls_back_to_max_context_length` —
  same `max_context_length` field, same backend, read through the seam.
- `test_get_context_window_from_lmstudio_returns_4096_on_error`
  → `test_model.py::test_context_window_falls_back_to_declared_4096` plus the
  cold last-known-good case: the same conservative floor, without pretending a
  failed fetch produced a real number.

Both were deleted with their subject — see deviation 6.

### `tests/test_note_classifier.py` — 1 removed, 2 written

- `test_resolve_model_for_classification_except_falls_back_to_settings_model_name`
  → its subject (`_resolve_model_for_classification`'s except-handler, which
  returned `settings.model_name` when `select_model` raised) no longer exists.
  Its guarantee — "never fall back to an arbitrary catalog entry" — is now
  stronger and inverted: the ambiguous case returns nothing at all, not even the
  configured default. That inversion is asserted in `test_model.py` (rows 10 and
  16). What is asserted at this call site is the half only this call site can
  answer: what `classify_note` does with each outcome.

## The two backend failure modes, tested at all five call sites

Task 1's `<behavior>` requires the UNREACHABLE and AMBIGUOUS-LIVE cases to be
kept distinct and tested per call site, "not just the graceful one". Ten tests,
two per site. Four of the five stages have a documented never-raises contract,
so the safe result on its own proves nothing about which failure occurred — the
load-bearing assertion in each ambiguous case is that **no completion was
issued**, because no model was chosen.

| Call site | UNREACHABLE (must not raise) | AMBIGUOUS LIVE (refuses) |
|---|---|---|
| `note_classifier.classify_note` | `test_classify_note_coerces_to_unsure_when_the_backend_is_unreachable` | `test_classify_note_propagates_an_ambiguous_live_backend` |
| `six_rs/reduce.reduce_entry` | `test_reduce_completes_against_the_static_profile_when_backend_unreachable` | `test_reduce_falls_back_without_completing_on_an_ambiguous_live_backend` |
| `six_rs/rethink._triage_one` | `test_rethink_triages_against_the_static_profile_when_backend_unreachable` | `test_rethink_coerces_to_keep_without_completing_on_an_ambiguous_backend` |
| `six_rs/reflect._default_completion_fn` | `test_reflect_completion_resolves_through_the_seam_when_backend_unreachable` | `test_reflect_completion_refuses_an_ambiguous_live_backend` |
| `pipeline_orchestrator._draft_reweave_addition` | `test_reweave_draft_completes_against_the_static_profile_when_unreachable` | `test_reweave_draft_falls_back_without_completing_on_an_ambiguous_backend` |

`classify_note` is the one that PROPAGATES the ambiguous case rather than
coercing. Coercing it to `unsure` would file vault notes classified by whatever
model happened to answer, which is the phantom-model failure the ADR exists to
remove. The destructive sweep is separately gated by
`probe_classifier_model_ready`, which fails closed on the same condition.

## The one-fetch-per-TTL-window assertion

`tests/test_structured_model.py::test_a_multi_stage_run_issues_one_model_list_fetch_per_ttl_window`.
A call-counting fake backend, five simulated stages, one shared seam: exactly
one `/api/v0/models` request and **zero** per-model requests. The companion
case asserts the window is a refresh interval and not a permanent cache — the
deleted `get_loaded_models` dict had no TTL at all, which is the staleness the
ADR opens with.

## Deviations

**1. [Delegation] Code was authored by this agent, not by a `sonnet-coder`
subagent.** Same as Plans 01 and 02, and for the same reason: no `Agent`/`Task`
dispatch tool exists in this executor's toolset, so the `<delegation>` blocks
could not be honoured. `~/.claude/hooks/gsd-tier-guard.cjs:203` explicitly
exempts subagents ("Inside a subagent is exactly where code should be
authored") and this executor is one, so the constraint's own enforcement
mechanism does not apply. Flagged rather than silently absorbed, as the brief
asked.

**2. [Rule 3 — blocking] A new module,
`sentinel-core/app/services/structured_model.py`.** The plan deletes
`model_resolution.py` and requires the five call sites to resolve through
`ActiveModel.for_task("structured")`, but they are module-level coroutines with
no graph reference to thread a seam through — and the "one model-list fetch per
TTL window across a whole 6 Rs run" assertion requires them to share ONE object,
not build five. This module is a one-object registry holding **no resolution
logic**: `composition.initialize_startup` registers the same seam the chat path
uses, and a lazy fallback delegates to `composition.build_active_model` rather
than assembling sources a second time. The four dependency-injection keyword
overrides `resolve_structured_model` carried were deliberately NOT carried
forward, per the plan.

**3. [Rule 3] A new test file, `sentinel-core/tests/test_structured_model.py`
(4 tests).** The plan's action requires the one-fetch-per-TTL-window assertion
but names no home for it. Putting it in `test_model.py` would have made that
file test a module it does not cover.

**4. [Rule 2 — missing critical functionality] `ModelProfile.capabilities_observed`.**
The first thing that broke when the structured path moved onto the seam: the
seed declares `function_calling: false` for the placeholder `local-model` id, so
an offline deployment resolved `for_task("structured")` to nothing and **RAISED**
— every six_rs stage fell back on every entry and `note_classifier` could not
classify at all. That directly contradicts the plan's own requirement that an
unreachable backend "must not raise".

The fix distinguishes evidence from declaration. A live backend's silence about
tool use is an OBSERVATION and still vetoes (asserted by
`test_a_live_backend_reporting_no_tool_use_still_vetoes_structured`); a seed
file's claim about a name is not, and is admitted with an INFO log naming what
it could not evidence (`test_a_declared_capability_set_cannot_veto_a_task`).
**The destructive-sweep gate never takes this path** —
`probe_classifier_model_ready` builds a seam over `LMStudioModelSource` alone,
with no static source, so it still fails closed on an unreachable backend.

**5. [Rule 3] Rows 14–16 needed an implementation change, not just tests.** The
plan says `strip_litellm_prefix` / `ensure_litellm_prefix` "survive in
`model_selector.py`" and that "nothing currently tests that `ActiveModel`
normalises before comparing". It did not normalise at all: rungs 2, 3 and 5
compared configured ids verbatim, so `MODEL_NAME=openai/qwen/qwen3.8-27b` —
the spelling the logs and every litellm call string use — would not have matched
the bare `qwen/qwen3.8-27b` LM Studio lists, and an operator copying it out of
the logs would have hit the refusal rung. `app/model.py` gained `_unprefixed`
and a candidate map keyed on both spellings. It widens only MATCHING, never
which candidates exist, which is why row 16's not-loaded half still raises.

**6. [Scope] Two LM Studio metadata helpers deleted from
`app/clients/litellm_provider.py`, and their 2 tests.** Deleting `_score` left
`get_model_capabilities_from_lmstudio` with zero references and zero tests; the
registry rework left `get_context_window_from_lmstudio` with tests but no
production caller. Both issued a per-model `GET /api/v0/models/{id}` — one
answering "how big is this model's window", the other "can it do tool use" —
which is precisely the fan-out `app/model.py` replaced with a single LIST call.
This is Flagged call 1's reasoning applied to a second module: leaving them
would preserve the same two-shapes-one-concept split, and leaving dead code with
live tests would pretend it still matters. Successors named above.

**7. [Interpretation] Every primary provider now gets a seam, not just LM
Studio.** Task 3 requires `RouteContext.context_window` to go and consumers to
"read the profile instead". For a non-LM-Studio primary, Plan 02 deliberately
left `primary_model = None`, and the window came from the registry via the
scalar. Removing the scalar with no replacement would have dropped every ollama
/ llamacpp / claude deployment to a declared 4096-token window — silently, with
a green suite. `_build_primary_model` gives a non-LM-Studio primary its own
I/O-free seam over that provider's config-derived profile, **seeded from the
model registry**, so a live Anthropic fetch still supplies Claude's real window
rather than the seed's. LM Studio's seam stays LM Studio's (SC-3), so the
404-retry hazard Plan 02 identified is unchanged.

**8. [Interpretation] A `MessageProcessor` with no seam refuses rather than
bridging.** `_profile_from_request` read `MessageRequest`'s scalars; with those
gone, the tempting replacement is a declared-4096 profile, which would truncate
context on a real deployment while every test stayed green. It raises
`model_unresolved` instead, with its own test. Composition always wires a seam,
so reaching that path is a wiring bug and now says so.

**9. [Scope] `app/routes/status.py` is in no task's `<files>`.** `GET
/context/{user_id}` read `ctx.context_window` for its recall budget. It now asks
the seam — showing what the real chat path would assemble rather than what
configuration said at boot — and degrades to the declared floor with a WARNING
rather than 500-ing a debug endpoint. Covered by
`test_status.py::test_context_budgets_from_the_seam_not_a_startup_scalar`.

**10. [Rule 3] Test modules touched beyond the plan's lists.** All forced, none
optional: `test_note_classifier.py` and `test_litellm_provider.py` imported
deleted names; `test_six_rs_reduce/reflect/rethink.py` and
`test_pipeline_orchestrator.py` host the required per-call-site tests;
`test_recall.py` and `test_vault_inventory.py` each build a `MessageRequest` in
a helper; `test_message_processor.py`, `test_message_request_factory.py`,
`test_composition.py` and `test_status.py` assert on removed fields.

**11. [Interpretation] `ProviderRouterBundle` is replaced by `ProviderGraph`,
not by a bare tuple.** The plan says `build_provider_router` should "return the
router and the `ActiveModel`", but `build_application` also needs the model
registry, and both seams are distinct objects. A four-value return is clearer as
a named frozen dataclass than as a tuple. The class the plan names is gone, and
so is what made it a *bundle of pinned scalars* — nothing `ProviderGraph`
carries is a fact about which model is loaded. `build_application`'s
`provider_bundle=` keyword became `provider_graph=`; no test used it.
`ai_provider_name` left the return value entirely because it is
`settings.ai_provider`, which every caller already has — it survives on
`AppGraph` and `RouteContext`, and `/status` still reports it.

**12. [Plan instruction followed] `strip_litellm_prefix` kept although it now
has no caller.** The plan lists it under "must survive". After the registry
rework nothing in either tree calls it, and it has no direct test. Kept as
instructed rather than overridden; flagged here so Plan 04 can decide.

**13. [Environment] The plan's `<verify>` paths point at a worktree that is not
the one used** — same as Plans 01 and 02. Every `<automated>` block hard-codes
`.claude/worktrees/active-model-seam`; this ran in
`.claude/worktrees/agent-a81c8c5a46b5b6d30`. Same commands otherwise, and both
interpreter paths were correct.

## Where the plan met the code and was wrong

**1. There are TWO provider-keyed tables in `build_provider_router`, not
three.** The plan names `active_model_table`, `stop_seq_base_url_table` and
`stop_seq_model_table`. `stop_seq_base_url_table` does not exist anywhere in the
file; the base-URL table with the Pitfall-2 comment lives inside
`model_selector.discover_active_model`, which Task 1 deletes. Both tables that
did exist are gone, and the third's guarantee is gone with its function.

**2. Rows 14–16 are described as if only tests were missing.** "Do not skip
14–16 on the grounds that the prefix helpers still exist — they exist untested
at the point that matters." The stronger statement is true: they existed
*unused* at the point that matters. See deviation 5.

**3. `test_rule_query.py`'s assertion protects the PF1-decline ordering, not
"the cache-hit path".** The plan says the `assert_not_awaited()` guard was
protecting "the rule-query cache-hit path". It is one of five assertions in
`test_pf1_decline_is_before_cache_embedding_and_llm_cost`, all pinning one
property: the PF1 decline precedes every avoidable cost. And the deleted
`resolve_model` calls sat *before* the cache read, so they were not on the
cache-hit path's short-circuit at all. Re-expressed against the one cost that
property never actually covered — the vault read, which `obsidian` being a bare
`object()` made unassertable. (Plan 02's summary already recorded that this file
does not assert what the plan claims; this is the same file, a second time.)

**4. The plan's file lists are missing six test modules and one route module**
that its own acceptance criteria force. See deviations 9 and 10.

**5. "An UNREACHABLE backend still degrades gracefully through
`StaticModelSource` and must not raise" was not satisfiable as the seam stood.**
See deviation 4. The plan states the requirement correctly; the code could not
meet it, and the plan does not say so.

**6. Plan 01's probe-coverage figure of 14 counts a test in a file this plan
deletes.** Honouring "nothing in this plan may reduce that" therefore required
adding coverage, not merely preserving it. Recorded because the naive reading —
"the parity guarantee is duplicated, so the count may fall to 13" — is exactly
the explaining-away the brief forbids.

**7. Removing `MessageRequest`'s scalars is not possible without giving every
provider a seam.** See deviation 7. The plan treats the removal as a local edit
to `RouteContext` and `MessageRequest`.

**8. The four dependency-injection keyword overrides had a consumer the plan
does not mention.** `note_classifier._resolve_model_for_classification` existed
solely to forward this module's own `get_loaded_models` / `select_model` /
`get_profile` bindings into the shared helper, preserving a `mock.patch` surface
for `test_note_classifier.py`. Deleting the overrides deletes that wrapper and
one test with it; both are accounted for above.

## Known stubs

None. No hardcoded empty value, placeholder string, or unwired component was
introduced. Every deletion is either a row in the disposition table above or
enumerated by name with a successor.

## Deferred, and why

Nothing was deferred from this plan's scope. Three items belong to Plan 04 and
were deliberately not touched: trimming `models-seed.json` to cloud models (the
plan's Flagged call 5), verifying pathfinder makes no direct LM Studio calls
(already true — zero `litellm.acompletion` call sites under
`modules/pathfinder/app/`), and the seed-trim's interaction with
`test_seed_always_present_in_registry`, which still asserts
`"local-model" in registry`.

## Deploy

**No lockstep requirement of its own.** This plan changes no HTTP contract:
`POST /provider/complete`'s request and response shapes are untouched, and
pathfinder's calls into core are unchanged (Plan 02's `task` field is what
crosses the boundary, and its lockstep note still stands). The `/context/{user_id}`
debug endpoint's recall budget now comes from the seam rather than a startup
scalar, which changes what it shows on a deployment whose loaded window differs
from its configured one — that is the fix, not a regression.

## Not touched, deliberately

`.planning/STATE.md`, `.planning/ROADMAP.md` and everything under
`.planning/phases/` are unchanged — this work sits outside the v0.6.0 milestone
and claims no phase slot. `docs/adr/0007-active-model-seam.md` is unchanged; it
is read-only across the plan set. `probe_embedding_model_loaded`,
`settings.embedding_model` and ADR-0004's exact-string match are unchanged per
ADR decision 5. `build_application` is still construct-once — no mutability was
added to the application graph; all of it lives inside `ActiveModel`'s TTL cache.
`ai_provider_name` survives on `AppGraph` and `RouteContext` and `/status` still
reports it (Flagged call 4).

`git stash` was never run, in any form.

## Self-Check: PASSED

- Commits `f1289f0`, `bb3ae5c`, `d210ee5` present on
  `worktree-agent-a81c8c5a46b5b6d30`, based on `9c9cb79`.
- Six deletion targets absent from the HEAD tree:
  `sentinel-core/app/services/model_resolution.py`,
  `sentinel-core/tests/test_model_resolution.py`,
  `modules/pathfinder/app/model_selector.py`,
  `modules/pathfinder/app/resolve_model.py`,
  `modules/pathfinder/tests/test_model_selector.py`,
  `modules/pathfinder/tests/test_resolve_model.py`.
- `sentinel-core/app/services/structured_model.py` and
  `sentinel-core/tests/test_structured_model.py` present.
- Repo-wide search finds no definition of `select_model`, `_score`,
  `get_loaded_models`, `discover_active_model`, `discover_lmstudio_model`,
  `_discover_model_for_provider`, `_fetch_live_capabilities`,
  `get_context_window_from_lmstudio`, `get_model_capabilities_from_lmstudio`,
  `ProviderRouterBundle`, or `resolve_structured_model`.
- No module under `modules/pathfinder/app/` imports `resolve_model` or
  `model_selector`; the only remaining textual match is a comment in
  `tests/test_rule_query.py` explaining the re-expressed assertion.
- `app/routes/note.py` still gates the destructive sweep on
  `probe_classifier_model_ready`.
- Per-file collected counts verified with `pytest --collect-only`; the +4
  table above sums correctly, and 14 `test_probe_classifier_*` cases plus the
  parity case give the 15 recorded.
- Three suites re-run with their own interpreters after the final commit:
  core 820 passed / 12 skipped, pathfinder 388 passed (non-zero collection
  confirms the right interpreter), shared 50 passed.
- `ruff check --select F401,F811,F821,F841` over all three trees reports 18
  findings, every one pre-existing and none in a line this plan wrote. (One,
  `tests/test_recall.py`'s unused `policy`, moved from line 1879 to 1883 because
  this plan's edit to that module's request helper is four lines longer; it is
  the same finding, not a new one.)
- No file under `.planning/phases/`, `.planning/STATE.md`,
  `.planning/ROADMAP.md` or `docs/adr/` was modified.


