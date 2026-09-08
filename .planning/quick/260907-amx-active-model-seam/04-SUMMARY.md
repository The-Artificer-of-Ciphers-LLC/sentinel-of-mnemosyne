---
quick_id: 260907-amx
slug: active-model-seam
plan: "04"
adr_step: 5
status: complete
requirements: [ADR-0007-S5, ADR-0007-CONSEQ-FAMILYPROFILE, ADR-0007-LIMIT-TOKENIZER, ADR-0007-CONSEQ-SEED]
worktree: .claude/worktrees/agent-adea8dcd12a10da3f
branch: worktree-agent-adea8dcd12a10da3f
base: f9a7559
commits:
  - a41ec3b  # Task 1 — FamilyProfile, and the context_window field removed
  - b0c878b  # Task 2 — the tokenizer name on the profile, and the seed trim
  - 118eff3  # Task 3 — the per-model anomaly breakdown; ADR verified, not edited
suite:
  core_in: "820 passed, 12 skipped"
  core_out: "828 passed, 12 skipped"
  pathfinder_in: "388 passed"
  pathfinder_out: "388 passed"
  shared_in: "50 passed"
  shared_out: "50 passed"
  N04: 8
  deleted_tests: 0
probe_coverage:
  before: 15
  after: 15
adr_edited: false
key-files:
  created: []
  modified:
    - shared/sentinel_shared/model_profiles.py
    - shared/sentinel_shared/llm_call.py
    - sentinel-core/app/model.py
    - sentinel-core/app/services/token_budget.py
    - sentinel-core/app/services/message_processing.py
    - sentinel-core/app/services/model_registry.py
    - sentinel-core/models-seed.json
    - sentinel-core/scripts/anomaly_rate.py
    - sentinel-core/tests/test_model_profiles.py
    - sentinel-core/tests/test_llm_call_shared.py
    - sentinel-core/tests/test_token_budget.py
    - sentinel-core/tests/test_anomaly_rate.py
    - sentinel-core/tests/test_model_registry.py
    - sentinel-core/tests/test_model.py
---

# Plan 04 — the cleanups

The family-keyed constants table is named `FamilyProfile` and carries no
context window. Token counts name the encoding they were taken with and degrade
instead of raising. `models-seed.json` holds only what `StaticModelSource`
genuinely serves. The anomaly rate can be attributed to the model that produced
each response. ADR-0007 was verified and not edited.

## The numbers

| Suite | In | Out | Delta |
|---|---|---|---|
| sentinel-core | 820 passed, 12 skipped | **828 passed, 12 skipped** | **+8** |
| modules/pathfinder | 388 passed | **388 passed** | 0 |
| shared | 50 passed | **50 passed** | 0 |

Zero tests deleted. Zero skips or xfails added — the 12 skips are the same 12
that entered the plan.

**Pathfinder was run with its own interpreter** (`modules/pathfinder/.venv`),
which collects 388; under the core venv it collects zero and reports a
misleading pass.

### N04 = 8, itemised

| File | Before | After | Delta | What |
|---|---|---|---|---|
| `tests/test_model_profiles.py` | 3 | 4 | +1 | the context-window field is ABSENT |
| `tests/test_token_budget.py` | 12 | 15 | +3 | known / unknown / unnamed encoding |
| `tests/test_anomaly_rate.py` | 7 | 10 | +3 | breakdown, unknown bucket, aggregate unchanged |
| `tests/test_model.py` | 68 | 69 | +1 | the trimmed seed leaves offline structured work usable |
| **Total** | | | **+8** | |

The plan predicted 7 with a floor of 5 and called this "the least certain link
in the chain". It landed at 8. The extra one is the `test_model.py` case, which
the plan did not anticipate because it did not anticipate the seed trim's
interaction with `capabilities_observed` (see "Where the plan met the code",
item 3). The two `test_model_registry.py` cases were UPDATES contributing 0, as
the plan said.

The plan's own arithmetic assumed N01 = 37. Real: N01 = 75, N02 = 24, N03 net
+4. Recomputed from the real baseline: 820 + 8 = 828.

## Probe coverage — 15 before, 15 after

`probe_classifier_model_ready` gates a destructive vault sweep, so its coverage
is measured either side rather than assumed.

**Before: 15** — 14 `test_probe_classifier_*` cases plus
`test_probe_and_structured_resolution_agree_on_the_same_model`, all in
`tests/test_model_selector.py`. Matches 03-SUMMARY.md's recorded figure exactly.

**After: 15** — the same 14 plus the same parity case, counted the same way with
`pytest --collect-only`. No drop.

Nothing in this plan touched the probe, its module, or its tests. Worth stating
what the seed trim did NOT do to it: `probe_classifier_model_ready` builds a
seam over `LMStudioModelSource` alone with no static source, so removing the
seed's local entries cannot reach it. It still fails closed on an unreachable
backend, and the `capabilities_observed` leniency the trim made more
load-bearing is on a path the probe does not take.

## The three `context_window` precondition checks

Task 1's precondition is an ABSENCE check across the repository, not a check of
one known site. All three were run before the field was removed.

**1. `sentinel-core/app/model.py` — PASS.** The context-window ladder is THREE
rungs (`_resolve_context_window`, `app/model.py:141-161`): the answering
generation's loaded-window field → `max_context_length` → a declared, logged
4096. There is no family rung. `FAMILY_PROFILES` is read at
`app/model.py:179-181`, inside `resolve_stop_sequences`, and reads
`.stop_sequences` only — expected, correct, and left alone. No `.context_window`
read anywhere in the module on a family-profile value. Plan 01's amendment A1 is
what made this true, and it is what made the whole task safe: without it the
seam itself would have been consuming the field this plan deletes.

**2. `sentinel-core/app/services/model_registry.py` — PASS.** `_fetch_lmstudio`
and its family-aware fallback are gone with Plan 03 Task 1; the module no longer
imports `get_profile` or `FAMILY_PROFILES` at all. Its remaining
`context_window` references are its OWN `ModelInfo` dataclass field and the seed
loader — a different concept with a different source, not a family constant.

**3. Repo-wide — PASS.** A scan of every `context_window` occurrence under
`sentinel-core/app`, `shared/sentinel_shared` and `modules/pathfinder/app`
accounted for every occurrence: the seam's own `ModelProfile` field
and ladder, the registry's `ModelInfo` field and seed loader, `TokenBudget.check`
's parameter, `anthropic_registry`'s API field, `message_processing`'s local
variable, and prose. The only reads on a value obtained from `get_profile(...)` /
`FAMILY_PROFILES` / `SAFE_DEFAULT` were the definitions inside
`model_profiles.py` itself. **No third consumer existed.** The failure this
precondition is written to catch did not occur.

## The seed trim

**Removed — 2 entries:**

| Entry | Provider | Declared window | Why it went |
|---|---|---|---|
| `qwen2.5:14b` | ollama | 32768 | ollama gets a declared 4096 profile from `StaticModelSource` per the ADR's rejection of four adapters |
| `local-model` | lmstudio | 8192 | LM Studio's identity and window come from `LMStudioModelSource`; the entry's own note, "actual context window fetched at startup", described the behaviour this ADR replaced |

**Kept — the three Claude entries**, unchanged. The file is valid JSON with the
same top-level `models` array; a `_notes` key was added recording why the local
entries are absent, which `_load_seed` ignores (it reads `data["models"]` only).

**The two assertions, UPDATED not deleted.** Both still assert the property they
guarded — the seed is present in the registry even when the live fetch fails —
and only the example model id changed:

- `test_seed_always_present_in_registry` (was asserting `"local-model" in
  registry` at :121): now asserts all three Claude ids ARE present and that
  `local-model` and `qwen2.5:14b` are NOT. The negative half is the load-bearing
  addition: without it, restoring a local seed entry would pass silently.
- `test_lmstudio_registry_is_seed_only_without_the_seam` (was asserting
  `"local-model" in registry` at :101): now asserts `claude-haiku-4-5` is present
  with the same "the seed must survive intact" message, plus the same negative.

Note the brief's correction 3 named this second test as
`test_lmstudio_registry_falls_back_to_seed_on_unavailable`. Plan 03 renamed it;
the assertion is the same one at the same place in the file.

**`config.py` was left alone, deliberately.** `llamacpp_model` still defaults to
`"local-model"` and `ollama_model` to `"qwen2.5:14b"`. Those are model ids an
operator points at a backend, not seed data — the trim is about what
`StaticModelSource` serves from a file, and changing the defaults would be a
behaviour change nothing in the plan asks for.

## The tokenizer

`ModelProfile` gained `tokenizer_encoding`, declared as `cl100k_base` via
`DECLARED_TOKENIZER_ENCODING` rather than derived per family. `TokenBudget` reads
it through `TokenBudget.for_profile()`, and the chat path budgets with the
resulting encoding.

**No tokenizer dependency was added and the approximation was not fixed.** ADR
Known Limitations accept it: `cl100k_base` is not Qwen's tokenizer, counting
stays approximate, and shipping a real tokenizer is a container-weight decision
left open. What changed is that the approximation is now *named* — a reader can
see which encoding produced a count instead of inferring it.

`TokenBudget.__init__` called `tiktoken.get_encoding` directly, which raises
`ValueError` on an unrecognised name. It is wrapped now: an unknown name logs a
WARNING and falls back. `encoding_name` reports the encoding **in use**, never
the one that was asked for — a budget claiming an encoding it is not using would
make the naming worthless.

Budgets are memoised per encoding name in `MessageProcessor`, under both the
requested and the effective name, so a degraded name does not re-warn on every
request and two models sharing an encoding share one budget object.

## ADR-0007 — verified present and true, NOT edited

`git diff --stat f9a7559 HEAD -- docs/adr/0007-active-model-seam.md` is **empty**.
No plan in this set edited the ADR.

Task 3 as written instructed correcting the "Pathfinder continues to call LM
Studio directly for `rule_query`" line. **That instruction is a no-op and was
executed as a verification instead** — the correction landed in commit `307b916`
before this plan began, and the quoted text does not exist in the file. What is
there, at `docs/adr/0007-active-model-seam.md:175-187`:

| Claim | Verdict | Evidence |
|---|---|---|
| The strike-through `~~Pathfinder continues to call LM Studio directly for `rule_query`.~~` is present | **PRESENT** | ADR:175 |
| A "Corrected 2026-09-07 during planning" block follows it | **PRESENT** | ADR:175-187 |
| Zero `litellm.acompletion` call sites under `modules/pathfinder/app/` | **TRUE** | repo scan returns none |
| Every completion routes through `SentinelCoreClient.complete()` | **TRUE** | 12 `_core_client.complete(...)` sites across the pf2e app; no other completion path |
| `embed_texts` routes through core's `POST /embeddings` | **TRUE** | `llm.py:406`, via `SentinelCoreClient.embed()` |
| Structured output over `POST /provider/complete` remains open and deferred | **TRUE** | no `response_format` / `json_schema` on the route or the shared client; Plan 02 added a `task` field, not structured output |

**Two citation drifts inside the correction, reported and not edited** — see
"Where the plan met the code", items 4 and 5. Neither changes the correction's
substance, and neither is an upstream divergence, so neither met the bar for the
"stop and report rather than silently re-editing" halt.

## Deviations

**1. [Delegation] Code was authored by this agent, not by a `sonnet-coder`
subagent.** Same as Plans 01, 02 and 03, and for the same reason: no `Agent` /
`Task` dispatch tool exists in this executor's toolset, so the `<delegation>`
blocks could not be honoured. `~/.claude/hooks/gsd-tier-guard.cjs:203` explicitly
exempts subagents ("Inside a subagent is exactly where code should be authored")
and this executor is one, so the constraint's own enforcement mechanism does not
apply. Flagged rather than silently absorbed, as the brief asked.

**2. [Rule 1 — bug] `shared/sentinel_shared/llm_call.py` declared the WRONG
profile type, and the rename exposed it.** Its `profile` parameter was annotated
`ModelProfile` imported from `model_profiles` — the family constants table —
while every production caller passes `app.model.ModelProfile`, the per-request
seam value (`six_rs/reflect.py:71`, `reduce.py:176`, `rethink.py:105`,
`note_classifier.py:248`, `pipeline_orchestrator.py:268`, all passing the result
of a `structured_profile()` / seam resolution).

A mechanical rename would have made it say `FamilyProfile` — still wrong, and
now *legibly* wrong, defeating the plan's own key link that the two types are
"distinguishable by name at every call site". They are not distinguishable at a
call site that names the wrong one.

`shared/` cannot import from `sentinel-core/app/` without inverting the
dependency, so the parameter is now a structural `HasStopSequences` Protocol
declaring the single attribute the wrapper reads. The module depends on neither
concrete type. This is exactly the defect the two-types-one-name collision was
always going to produce, and it went unnoticed for the three steps the collision
existed.

`extract_completion_text`'s docstring reference to `ModelProfile.reasoning` was
restored to name `app.model.ModelProfile` explicitly — `reasoning` is a seam
field and has never existed on the family table.

**3. [Rule 3 — blocking] `sentinel-core/tests/test_model.py` was modified, and it
is in no task's `<files>` list.** `test_a_declared_capability_set_cannot_veto_a_task`
(Plan 03's deviation 4) reads the SHIPPED seed and asserts, as an explicit
premise, "the seed genuinely declares no function calling for this id" — using
`local-model`, one of the two ids this plan removes. After the trim that test
would still pass, but for a different and weaker reason: an id with no seed entry
has no declared capabilities, so the distinction under test (a DECLARED false
must not veto; an OBSERVED absence must) would never be exercised. A test that
passes without testing its subject is worse than one that fails.

Fixed by supplying the declaring seed entry EXPLICITLY through
`build_static_profiles(seed=...)` rather than reading it off the data file. That
is strictly stronger: the property is "a declared false cannot veto", and it now
tests exactly that instead of depending on which ids happen to be in a JSON file.

**4. [Rule 2 — missing critical functionality] A test pinning that the trim
leaves offline structured work possible.** Correction 4 in the brief is right
that the `capabilities_observed` interaction is load-bearing for offline
operation, and the trim makes it MORE so, not less: with no local id left in the
seed, `capabilities_observed=False` is now the *only* reason an offline LM Studio
or llama.cpp deployment can resolve `for_task("structured")` at all. Before the
trim, an id with a seed entry declaring `function_calling: true` would also have
passed. Nothing asserted this. Without a test, the next person to "tighten" the
capability filter would reproduce the exact step-4 breakage Plan 03 fixed — every
6 Rs stage falling back on every entry, `note_classifier` unable to classify —
and the suite would stay green. `test_the_trimmed_seed_still_leaves_an_offline_local_model_usable`
now pins it, including that the removed 8192 seed window is a declared 4096 floor.

**5. [Rule 1 — bug] Two registry log lines claimed to be "using seed data" that
the trim removed.** `build_model_registry`'s ollama and llamacpp branches logged
"stub only — using seed data" at INFO. After the trim there is no seed data for
either provider, so an operator reading that line would look for a seed entry
that cannot exist. Both lines and the module docstring's per-provider table now
say what is actually true: those providers contribute no registry entry, and
their profile is a declared 4096 from `StaticModelSource`.

**6. [Scope] `sentinel-core/app/model.py`'s module docstring was updated in Task
1.** It already anticipated the rename — it named `FamilyProfile.context_window`
as the field "this same design removes" — but that sentence was written in the
future tense about work this plan performs. Corrected to past tense with the
statement that there is no longer a window on the table to read. Prose only.

**7. [Scope — declined] `strip_litellm_prefix` was left alone.** 03-SUMMARY.md's
deviation 12 records that it survives with no caller and no direct test, and
explicitly flags it "so Plan 04 can decide". This plan does not name it, so per
the brief's scope discipline it was left in place and is recorded here rather
than deleted opportunistically. **It is still uncalled and untested.** See
"Left undone" below.

## Where the plan met the code and was wrong

**1. The importer table is stale in two rows.** It lists
`modules/pathfinder/app/llm.py:37` as a live importer of `ModelProfile` and says
"run the pathfinder suite" because of it. Plans 02 and 03 stripped that import;
no module under `modules/pathfinder/` references `ModelProfile`, `get_profile`,
`FAMILY_PROFILES` or `SAFE_DEFAULT` at all. The table also omits nothing else —
the four real importers at the start of this plan were `llm_call.py:34`,
`test_llm_call_shared.py:17`, `test_model_profiles.py` (which imports
`FAMILY_PROFILES` and `get_profile`, not the class) and `app/model.py:44`.

**The pathfinder suite was still run**, three times, and came back at 388 every
time. The reason to run it survives the table being wrong: pathfinder imports
`sentinel_shared` at package level and shares the tree.

**2. "Importers of `get_profile`: `composition.py:40`, `note_classifier.py:31`,
`model_registry.py:24`" — all three are gone.** Plan 03 removed every one. The
sole remaining importer of `get_profile` in the repository is `app/model.py:44`,
inside `resolve_stop_sequences`.

**3. The plan does not anticipate the seed trim's interaction with
`capabilities_observed`, in either direction.** It gets the mechanism right in
Task 2's `<behavior>` ("StaticModelSource still serves every Claude model after
the seed trim") but does not notice that (a) removing `local-model` guts the
premise of an existing test that names it, and (b) the trim makes
`capabilities_observed` the sole guarantor of offline structured work. Both are
handled above as deviations 3 and 4. The brief's correction 4 caught (a) in
spirit; neither the plan nor the brief caught (b).

**4. The ADR correction's `import litellm` claim is imprecise, and its line
number has drifted.** ADR:180 says "the `import litellm` at `llm.py:33` is
vestigial". The import is now at `llm.py:41` and it is NOT unused: `llm.py:63`
does `litellm.suppress_debug_info = True`. Nothing else in the pf2e app touches
the module. The correction's substantive claim — pathfinder does not use litellm
for completions — holds exactly. This imprecision predates ADR-0007 (line 63 is
older), so nothing upstream diverged and the halt condition was not met. **No ADR
edit was made.** Recorded here so a future reader does not delete that import
expecting it to be dead.

**5. The ADR correction's other two line citations have drifted.** It cites
`classify_rule_topic` at `llm.py:474-548` (now `:474-548`-ish, with its
`_core_client.complete` at `:497`) and `llm.py:432-440` as "documenting its own
`model`/`api_base`/`profile` parameters as accepted-but-not-forwarded". Plan 02
DELETED those parameters from all eleven helpers, so that passage now describes
evidence that no longer exists in the file. It made the correction's conclusion
*more* true, not less. Again: no ADR edit made.

**6. The `<verify>` and frontmatter paths point at a worktree that is not the one
used** — the same defect Plans 01, 02 and 03 all recorded. Every `<automated>`
block hard-codes `.claude/worktrees/active-model-seam`; this ran in
`.claude/worktrees/agent-adea8dcd12a10da3f`. Same commands, correct interpreter
paths. Four for four across the plan set.

**7. `files_modified` is missing two files** the plan's own acceptance criteria
force: `sentinel-core/tests/test_model.py` (deviations 3 and 4) and
`sentinel-core/app/services/model_registry.py` (deviation 5 — it IS listed in
Task 2's `<files>`, but only as the seed loader to read, not to modify).

## Known stubs

None. `tokenizer_encoding` defaults to a DECLARED `cl100k_base` rather than being
left empty and unwired — it is the encoding actually in use, read by the chat
path on every request, and asserted in three tests. It is a declaration in the
same sense as `DECLARED_DEFAULT_CONTEXT_WINDOW`, not a placeholder awaiting a
future plan.

## Left undone — what a reader of ADR-0007 would expect to be finished

This closes the set, so these are the open ends, not deferrals within a plan.

**1. `strip_litellm_prefix` is dead code.** No caller in either tree, no direct
test. Plan 03 kept it because its plan said to; this plan does not name it, so it
was left. Deleting it is a one-line change nobody has been given the authority to
make. `ensure_litellm_prefix` is live (`app/model.py`'s `_prefixed`/`_unprefixed`
are the seam's own, distinct implementations).

**2. Structured output over `POST /provider/complete` is still an open design
question**, and the ADR says so. Plan 02 added a closed-set `task` field; nothing
in the set added a response-format contract. Not blocking pathfinder, which does
not use structured output on that path.

**3. The ADR's third Known Limitation names a real tokenizer as deliberately
open**, and it stays open. This plan named the encoding; it did not add one.

**4. The per-model anomaly breakdown has not been run against the live vault.**
The instrument exists and is tested; the measurement ADR-0007's sequencing was
staged to enable — comparing the degenerate-response rate before and after the
cutover, per model — has not been taken. It needs the deployed stack and vault
access. That is the first thing to do after this ships.

**5. Deploy lockstep from Plan 02 still stands.** This plan changes no HTTP
contract, but `POST /provider/complete`'s `task` field and the changed meaning of
its `model` field cross the core/pf2e boundary and both images must ship
together.

## Not touched, deliberately

`.planning/STATE.md`, `.planning/ROADMAP.md` and everything under
`.planning/phases/` are unchanged. `docs/adr/0007-active-model-seam.md` is
unchanged and was verified rather than edited. `response_anomaly`'s detection was
not narrowed to the loaded family (ADR decision 6). `probe_embedding_model_loaded`
and `settings.embedding_model` are unchanged (ADR decision 5). The seven family
profiles' stop-sequence data, the alias block, the substring patterns,
`SAFE_DEFAULT`'s empty stop list and `get_profile`'s cache are all untouched — in
particular the mistral and llama profiles still do NOT list their template
delimiters as stop tokens, which is the April mid-generation-garbage regression.
`capabilities_observed` was neither undone nor bypassed.

`git stash` was never run, in any form. The pre-existing `WIP on main` entry
belonging to the user was never listed, popped, applied or dropped.

## Self-Check: PASSED

- Commits `a41ec3b`, `b0c878b`, `118eff3` present on
  `worktree-agent-adea8dcd12a10da3f`, based on `f9a7559`.
- `shared/sentinel_shared/model_profiles.py` defines `FamilyProfile` and no
  `ModelProfile`; `dataclasses.fields(FamilyProfile)` contains no
  `context_window`, asserted by a test.
- `app/model.py`'s `ModelProfile` is the only type by that name in the
  repository.
- `sentinel-core/models-seed.json` parses as JSON and contains exactly the three
  Claude ids.
- Three suites re-run with their own interpreters after the final commit: core
  828 passed / 12 skipped, pathfinder 388 passed (non-zero collection confirms
  the right interpreter), shared 50 passed.
- Probe coverage counted with `pytest --collect-only` either side: 15 → 15.
- `ruff check --select F401,F811,F821,F841` over all three trees reports 18
  findings — the same count 03-SUMMARY.md recorded, every one pre-existing, none
  in a line this plan wrote.
- `git diff --stat f9a7559 HEAD -- docs/adr/0007-active-model-seam.md` is empty.
- No file under `.planning/phases/`, `.planning/STATE.md` or
  `.planning/ROADMAP.md` was modified.
