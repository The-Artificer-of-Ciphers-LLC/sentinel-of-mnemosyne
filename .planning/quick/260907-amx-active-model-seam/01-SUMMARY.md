---
quick_id: 260907-amx
slug: active-model-seam
plan: "01"
adr_step: 2
status: complete
requirements: [ADR-0007-S2, ADR-0007-D1, ADR-0007-D2, ADR-0007-D3, ADR-0007-D4, ADR-0007-D5, ADR-0007-D7, DEFECT-B]
worktree: .claude/worktrees/agent-a8c6e3a78deef65e0
branch: worktree-agent-a8c6e3a78deef65e0
base: b4472a3
commits:
  - 63cef47  # Task 1 — the seam
  - 802f141  # Task 2 — composition + Defect B
  - e3358bc  # Task 3 — the destructive-sweep gate
suite:
  baseline_in: "717 passed, 12 skipped (729 collected)"
  actual_out: "792 passed, 12 skipped (804 collected)"
  N01: 75
  deleted_tests: 0
  pathfinder: "not run — this plan touches no file under modules/pathfinder/"
probe_coverage:
  before: 10
  after: 14
key-files:
  created:
    - sentinel-core/app/model.py
    - sentinel-core/tests/test_model.py
  modified:
    - sentinel-core/app/config.py
    - sentinel-core/app/composition.py
    - sentinel-core/app/state.py
    - sentinel-core/app/routes/note.py
    - sentinel-core/app/services/message_request_factory.py
    - sentinel-core/app/services/model_registry.py
    - sentinel-core/app/services/model_selector.py
    - sentinel-core/tests/test_composition.py
    - sentinel-core/tests/test_message_processor.py
    - sentinel-core/tests/test_message_request_factory.py
    - sentinel-core/tests/test_model_resolution.py
    - sentinel-core/tests/test_model_selector.py
---

# Plan 01 — the Active model seam

`ActiveModel`, `ModelProfile`, the `ModelSource` protocol and both adapters now
exist at `sentinel-core/app/model.py`. `build_provider_router` composes them
instead of making three independent HTTP fetches, the recorded model name is
the one that answered (Defect B), and the destructive-sweep gate asks the seam.

## N01 — the number Plans 02, 03 and 04 chain off

**N01 = 75.** Suite went from **717 passed, 12 skipped** to
**792 passed, 12 skipped**. Zero tests were deleted.

| File | Before | After | Delta |
|---|---|---|---|
| `tests/test_model.py` | — | 62 | +62 |
| `tests/test_model_selector.py` | 10 | 14 | +4 |
| `tests/test_composition.py` | 16 | 20 | +4 |
| `tests/test_message_request_factory.py` | 1 | 4 | +3 |
| `tests/test_message_processor.py` | 13 | 15 | +2 |
| `tests/test_model_resolution.py` | 2 | 2 | 0 |
| **Total** | | | **+75** |

The plan predicted N01 >= 37. The 62 in `test_model.py` cover every case in
Task 1's `<behavior>` plus one added during Task 2 (see Deviations).

## Probe coverage — before and after

`probe_classifier_model_ready` gates a destructive vault sweep, so its coverage
is recorded either side rather than asserted to be fine.

**Before: 10.** Nine `test_probe_classifier_*` cases in
`tests/test_model_selector.py`, plus the probe/resolver parity case in
`tests/test_model_resolution.py`. (The plan said "10 collected tests, all of
this probe" for `test_model_selector.py`; the tenth collected test in that file
is actually `test_score_cloud_model_via_litellm_unchanged`, which tests `_score`
and not the probe. It is untouched — `_score` survives until Plan 03.)

**After: 14.** All nine original names and assertions preserved, four new cases
added, parity case preserved. No drop.

The nine preserved cases changed MECHANISM, not verdict. They previously served
a model list on the OpenAI-compatible endpoint and patched `_score` to force a
score; they now serve real `/api/v0/models` payloads and let the capability
data decide. Every one still asserts the same ready/not-ready answer.

The four new cases:

1. `..._false_when_capabilities_are_absent` — an entry carrying no capability
   data at all is not ready. Absent data is not permission.
2. `..._false_when_an_operator_pin_lacks_tool_use` — **the case the rewire
   created.** ADR-0007 makes an operator pin absolute over the capability
   filter, so resolution now RETURNS a pinned-but-incapable model. Answering on
   "did a model come back" would have turned `MODEL_PREFERRED` into a way to
   unlock destructive sweeps with a degraded classifier. The probe answers on
   the resolved profile's capability instead.
3. `..._false_when_resolution_raises` — the case Task 3's `<behavior>` names.
   An undisambiguatable live backend raises; the probe absorbs it and answers
   not-ready. An uncaught raise would have reached the sweep gate as a 500, and
   a 500 is not a refusal.
4. `test_probe_and_structured_resolution_agree_on_the_same_model` — parity
   against the seam, landed here so Plan 03's deletion of
   `test_model_resolution.py` leaves no unguarded window.

## Assertions replaced rather than kept

Two, both recorded here because the plan requires it.

**`tests/test_model_resolution.py::test_probe_and_resolve_structured_model_select_same_model_id_for_local_tool_use`.**
It asserted `len(recorded) == 2` — one `select_model` call per path — which
encoded the old divergence-prevention MECHANISM: probe and resolver both
reaching `select_model` with identical inputs. The probe no longer reaches
`select_model` at all, so that assertion is no longer expressible. Replaced
with the property it existed to protect: for one live payload the seam (which
the probe now asks) and `resolve_structured_model` land on the same model id,
and the probe reports ready. The fake backend gained the model-LIST endpoints
the seam reads; its per-model endpoint is unchanged and still serves the
resolver. This file is deleted by Plan 03.

**`tests/test_model_selector.py::test_probe_classifier_ready_false_when_capability_endpoint_unreachable`.**
Kept its name and its assertion ("an unreachable endpoint must never grant a
permissive default"), but the endpoint it makes unreachable changed from the
per-model capability endpoint to the model-list endpoint, because the per-model
fan-out no longer exists. The absent-capability-data half of what that test used
to cover is now its own case (new case 1 above), so nothing was lost.

No existing composition test changed. `build_provider_router`'s existing tests
pass unmodified because `MODEL_AUTO_DISCOVER=false` (which all of them set)
keeps its documented meaning under the seam.

## Deviations

**1. [Delegation] Code was authored by this agent, not by a `sonnet-coder`
subagent.** The brief requires dispatching `Agent(subagent_type: "sonnet-coder")`
per the plan's `<delegation>` blocks. No `Agent`/`Task` tool was available in
this agent's toolset, so dispatch was impossible. The hook that enforces the
rule — `~/.claude/hooks/gsd-tier-guard.cjs` — explicitly exempts subagents
(line 203: "Inside a subagent is exactly where code should be authored"), and
this executor IS a subagent, so the constraint's own enforcement mechanism does
not apply here. Proceeding was judged closer to the intent (keep hand-authoring
off the opus MAIN session) than halting. Flagged rather than silently absorbed.

**2. [Rule 3 — blocking] `sentinel-core/app/services/model_registry.py` was
modified, and it is not in Task 2's `<files>` list.** Task 2's acceptance
criterion requires the model id, context window and stop sequences to come from
one refresh "rather than from three independent fetches". Two of the three were
`build_provider_router`'s own; the third lived inside `build_model_registry`,
which called `discover_active_model` and then a per-model context fetch. The
test asserting the fan-out is gone failed on
`/api/v0/models/test-model` until this was addressed. `build_model_registry`
gained two optional keyword arguments (`lmstudio_model`,
`lmstudio_context_window`); when both are supplied it registers the seam's
answer and performs no LM Studio HTTP. Both default to `None`, so every other
caller — including all of `tests/test_model_registry.py` — is on the original
path unchanged.

*Consequence worth knowing:* on a DEAD backend the registry's LM Studio entry
now gets the seam's declared 4096 rather than `_fetch_lmstudio`'s
family-constant fallback (e.g. 32768 for a qwen id). Nothing reads that value
for LM Studio any more — `build_provider_router` takes the window from the
profile — so there is no live consumer difference, and Plan 04 owns the seed
trim anyway.

**3. [Rule 3 — blocking] `sentinel-core/tests/test_model_resolution.py` was
modified, and it is not in Task 3's `<files>` list.** Its parity test failed
after the rewire. Per the brief, a pre-existing test that now fails is a
regression to fix rather than to delete or skip. Fixed by re-expressing the
assertion (see "Assertions replaced" above). The second test in that file is
untouched.

**4. [Scope] `sentinel-core/app/routes/note.py` — comment only.** The block
above the sweep gate described the probe as checking whether a model "SCORES".
That is no longer what it does. Comment updated; no code change. Task 3's action
explicitly permits touching this call site.

**5. [Interpretation] `MODEL_AUTO_DISCOVER=false` is honoured by leaving the
live source out of the seam.** The plan does not say what becomes of this
setting. Silently ignoring it would have changed the behaviour of a documented
operator switch and broken the existing composition tests' premise. Composition
therefore builds `ActiveModel` with only the `StaticModelSource` when it is
false, which preserves the setting's meaning exactly.

**6. [Interpretation] `build_provider_router` keeps a non-fatal degrade to
`MODEL_NAME`.** Its documented contract is that it never raises, and its output
supplies the LM Studio provider's model string. When resolution raises at
startup, it logs a WARNING naming the model as NOT confirmed and builds with
`MODEL_NAME`. This is composition's startup posture, not a resolution rung —
the ladder itself still refuses, and Plan 02 makes the request path re-resolve
and surface the refusal properly. Flagged because it superficially resembles the
"return the configured model unconfirmed" behaviour A19 removed; it is not in
the ladder, it is loud, and it is not reachable while `MODEL_NAME` names
something.

## Where the plan met the code and was wrong

**1. The `<verify>` and frontmatter paths point at a worktree that is not the
one used.** Every `<automated>` block hard-codes
`.claude/worktrees/active-model-seam`. This ran in
`.claude/worktrees/agent-a8c6e3a78deef65e0`. Same command otherwise; the
interpreter path (the main checkout's core venv) was correct.

**2. "`tests/test_model_selector.py` (10 collected tests, all of this probe)" is
off by one.** Nine are the probe; the tenth is
`test_score_cloud_model_via_litellm_unchanged`, which tests `_score`. Recorded
so Plan 03 does not delete a `_score` test expecting it to be a probe test.

**3. `files_modified` is missing two files** that the plan's own acceptance
criteria force: `model_registry.py` (deviation 2) and
`tests/test_model_resolution.py` (deviation 3).

**4. `StaticModelSource` needed a per-provider constructor, which the plan does
not describe.** The plan says it "serves Claude from the model seed and serves
ollama/llamacpp as declared 4096-context profiles" — i.e. all of them at once.
Doing that literally would put four unrelated models in one candidate list and
make every resolution ambiguous at rung 7. Implemented as
`build_static_profiles(settings, provider=...)`, producing the ONE profile for
the named provider, which is both unambiguous and what composition actually
needs. Note also that `models-seed.json` already contains `qwen2.5:14b` (32768)
and `local-model` (8192), so the ollama/llamacpp default models are seed HITS,
not 4096 — the declared-4096 test uses ids the seed does not carry.

**5. "The seam is the ACTIVE provider's" is not compatible with SC-3.** The
plan has `build_provider_router` ask the seam for the facts it used to fetch,
but `provider_map["lmstudio"]`'s model string must be LM STUDIO's own model
regardless of `AI_PROVIDER` (the reason `discover_lmstudio_model` existed at
all). Resolved by making the seam LM Studio's seam unconditionally, and leaving
the non-LM-Studio providers' context window on the registry and their stop
sequences on the family table with `api_base=None` (no I/O). For the
`AI_PROVIDER=lmstudio` deployment — the real one — this is exactly one
metadata refresh and nothing else.

**6. The v1/v0 equivalence assertion needed `vision` derived on v0.** The plan
requires field-by-field equivalence with only `reasoning` legitimately
differing. v1 reports the live model as `type: llm` with
`capabilities.vision: true`; v0 reports the same model as `type: "vlm"` with
`capabilities: ["tool_use"]`. Mapping v1's `vision` capability without deriving
the same fact from v0's `type == "vlm"` would have made `capabilities` differ
between generations. Deriving it on v0 is the faithful reading of the plan's own
observation that "modality moved out of `type` between generations", and it
makes the equivalence real rather than achieved by discarding data.

## Known limitations, accepted

**The Flagged-call-12 JIT/structured hazard survives on the v0 fallback path.**
If an old LM Studio runs JIT and does not populate `capabilities` for not-loaded
entries, `for_task("structured")` on that backend filters tier two to empty and
raises while chat resolves. Not fixed here: fixing it would mean widening the
capability filter, letting a model without `tool_use` be selected for structured
work on EVERY backend to accommodate one old generation. Left degraded and
loud. If it is ever hit in practice the answer is to upgrade LM Studio, not to
loosen the filter.

## Not touched, deliberately

`.planning/STATE.md`, `.planning/ROADMAP.md` and everything under
`.planning/phases/` are unchanged — this work sits outside the v0.6.0 milestone
and claims no phase slot. `docs/adr/0007-active-model-seam.md` is unchanged; it
is read-only across the plan set. The embedding path
(`probe_embedding_model_loaded`, `settings.embedding_model`, ADR-0004's
exact-string match) is unchanged per ADR decision 5, and `response_anomaly`'s
control-token detection was not narrowed per ADR decision 6.

## Self-Check: PASSED

- `sentinel-core/app/model.py` and `sentinel-core/tests/test_model.py` present in
  the HEAD tree.
- Commits `63cef47`, `802f141`, `e3358bc` present on
  `worktree-agent-a8c6e3a78deef65e0`, based on `b4472a3`.
- Per-file collected counts verified against `pytest --collect-only`: 62 / 14 /
  20 / 4 / 15 / 2, summing to the +75 above.
- `app/model.py` contains zero literal `settings.model_name` reads; the two
  `_setting("model_name")` calls are rung 4's divergence log and rung 5, and
  `StaticModelSource` reads it via `build_static_profiles`.
- `app/routes/note.py` still gates the destructive sweep on
  `probe_classifier_model_ready`.
- No file under `.planning/phases/`, `.planning/STATE.md`, `.planning/ROADMAP.md`
  or `docs/adr/` was modified.
