---
quick_id: 260907-amx
slug: active-model-seam
plan: 04
adr_step: 5
type: execute
wave: 4
depends_on: ["03"]
files_modified:
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
# docs/adr/0007-active-model-seam.md is READ-ONLY in this plan. Task 3 verifies the
# already-landed correction (commit 307b916) rather than making it; see Flagged
# calls 4. It is deliberately NOT in files_modified.
autonomous: true
requirements: [ADR-0007-S5, ADR-0007-CONSEQ-FAMILYPROFILE, ADR-0007-LIMIT-TOKENIZER, ADR-0007-CONSEQ-SEED]
verification:
  core: "cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q"
  pathfinder: "cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/modules/pathfinder && /Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/.venv/bin/python -m pytest tests/ -q"
  baseline_in: "whatever 03-SUMMARY.md recorded"
  expected_out: "sentinel-core: baseline + N04 passed, 12 skipped, 0 failed. Pathfinder: unchanged from 03-SUMMARY.md — this plan touches shared/sentinel_shared/model_profiles.py, which pathfinder imported at modules/pathfinder/app/llm.py:37, so the pathfinder suite MUST be run and MUST be unchanged. This plan deletes NO tests; it renames a symbol and removes a field, so tests referencing either are updated in place. Record exact numbers in 04-SUMMARY.md."
must_haves:
  truths:
    - "The family-keyed constants table is named for what it is, and no longer carries a context_window field that disagrees with the registry and that nothing consumes."
    - "Token counting names the encoding it is using and degrades to cl100k_base when it does not recognise one, rather than raising."
    - "The anomaly rate can be broken down by the model that produced each response."
    - "models-seed.json contains only what StaticModelSource genuinely serves from data, and every test that asserted on a removed seed entry asserts on the trimmed reality instead."
    - "ADR-0007's Known-Limitations entry about Pathfinder is VERIFIED present and still true (it was corrected in commit 307b916); this plan edits no ADR text."
  artifacts:
    - shared/sentinel_shared/model_profiles.py
    - sentinel-core/scripts/anomaly_rate.py
  key_links:
    - "ModelProfile (the seam value) and FamilyProfile (the constants table) are distinguishable by name at every call site."
    - "anomaly_rate reads the session summary frontmatter model: line that Defect B's fix made truthful in Plan 01."
---

<objective>
The cleanups ADR-0007 step 5 names: rename `ModelProfile` to `FamilyProfile` in
`shared/` and drop its unused `context_window` field, make `anomaly_rate.py` read
the model from session summaries, and put the tokenizer name on the profile. Trim
`models-seed.json` to what `StaticModelSource` actually serves, and correct the one
stale line in the ADR that implementation disproved.

Purpose: ADR-0007 step 5. These are the loose ends the four preceding steps created
or exposed — none is load-bearing on its own, and doing them last keeps them out of
the way of the structural work.

Output: two distinguishable profile types, a per-model anomaly breakdown, an honest
tokenizer story, and an ADR that matches the code.
</objective>

<context>
@docs/adr/0007-active-model-seam.md
@.planning/quick/260907-amx-active-model-seam/README.md
@.planning/quick/260907-amx-active-model-seam/03-SUMMARY.md
@shared/sentinel_shared/model_profiles.py
@sentinel-core/app/services/token_budget.py
@sentinel-core/scripts/anomaly_rate.py
</context>

## Verified ground truth (2026-09-07 — do not re-derive)

**`shared/sentinel_shared/model_profiles.ModelProfile`** is a family-keyed constants
table: `FAMILY_PROFILES` maps LM Studio `arch` strings (and substring-match keys) to
one of seven profiles, with a long alias block (`qwen3_5` → the qwen2 ChatML profile,
`gemma4` → the gemma2 profile, and so on). Its `context_window` field is exactly the
misnomer symptom the ADR describes: `gemma2` declares 8192 while the live gemma-4
served 262144, and `qwen2` declares 32768 while the live qwen3.8 served 119552.

Importers of the name `ModelProfile` at the start of this work:

| File | Line | Status entering Plan 04 |
|---|---|---|
| `shared/sentinel_shared/llm_call.py` | 19 | live |
| `sentinel-core/tests/test_llm_call_shared.py` | 11 | live |
| `sentinel-core/tests/test_model_profiles.py` | 15 | live (3 collected tests) |
| `modules/pathfinder/app/llm.py` | 37 | live — **run the pathfinder suite** |
| `modules/pathfinder/app/resolve_model.py` | 30 | deleted in Plan 03 |

Importers of `get_profile`: `composition.py:40`, `note_classifier.py:31`,
`model_registry.py:24`, `model_resolution.py:30` (deleted in Plan 03).

**`context_window` consumers — there were TWO, and both are expected gone.** An
earlier draft of this plan asserted "the one `context_window` consumer is
`model_registry.py:88-104`", which was already false when written: Plan 01's original
ladder introduced a second consumer in `sentinel-core/app/model.py`
(`loaded → max → family constant → 4096`).

Both are removed upstream, by different mechanisms:

| Consumer | Removed by | Mechanism |
|---|---|---|
| `sentinel-core/app/model.py` — the context-window ladder's family rung | Plan 01, amendment A1 | ADR decision 2 was amended 2026-09-07 to drop the family rung entirely; the ladder is now `loaded_context_length → max_context_length → declared 4096`. **This is what makes the field removal safe at all** — without A1 the seam itself would be reading the field this plan deletes. |
| `sentinel-core/app/services/model_registry.py:88-104` — `_fetch_lmstudio`'s family-aware fallback | Plan 03 Task 1 | the registry's LM Studio live path is subsumed by `LMStudioModelSource`; the registry keeps only its seed role. |

Task 1's precondition is therefore a VERIFICATION that no consumer remains anywhere,
not a check of one known site. `app/model.py` may still read `FAMILY_PROFILES` — for
**stop sequences**, which is correct and stays. Only a read of `.context_window` off
a family profile is a blocker.

**`TokenBudget`** (`app/services/token_budget.py:28-45`) already takes an `encoding`
constructor argument defaulting to `cl100k_base`, but calls
`tiktoken.get_encoding(encoding)` directly, which raises on an unrecognised name.

**Session summaries** carry the model in frontmatter — `message_processing.py:235-239`
writes a `model:` line into every summary at `ops/sessions/<YYYY-MM-DD>/<user>-<HH-MM-SS>.md`.
Plan 01's Defect B fix is what made that line truthful; before it, every summary
recorded the `MODEL_NAME` default. `anomaly_rate.py` currently parses summaries via
`app.vault._parse_session_summary` and ignores the frontmatter entirely.

**`models-seed.json`** holds 5 entries: `qwen2.5:14b` (ollama), three Claude models,
and `local-model` (lmstudio, notes say "actual context window fetched at startup").

**The seed trim has a test consumer that no earlier draft listed:**
`sentinel-core/tests/test_model_registry.py` asserts `"local-model" in registry` in
TWO places — `test_seed_always_present_in_registry:63` (`assert "local-model" in
registry` alongside `assert "claude-haiku-4-5" in registry`) and
`test_lmstudio_registry_falls_back_to_seed_on_unavailable:44`. Both break the moment
`local-model` leaves the seed. Plan 03 Task 1 may already have rewritten the second
one with the registry's live path; the first is a pure seed test that survives Plan
03 and fails here. It is not optional collateral — the trim cannot be green without
touching it.

**Already done, do not redo:** commit `93df616` corrected the two docstrings claiming
the chat path pins temperature 0.4. ADR-0007's third Known Limitation is satisfied.

<tasks>

<task type="auto">
  <name>Task 1: ModelProfile in shared/ becomes FamilyProfile and loses its context_window field</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<action>` and `<verify>` verbatim, plus the importer
    table above. Tell it that `modules/pathfinder/app/llm.py` is an importer and that
    the pathfinder suite must be run.
  </delegation>

  <read_first>
    - shared/sentinel_shared/model_profiles.py (all 241 lines — the dataclass, the
      seven profiles, the alias block, SAFE_DEFAULT, the substring patterns, and
      get_profile's three-rung resolution and forever-cache)
    - sentinel-core/app/model.py (the seam's own ModelProfile — the type this rename
      is disambiguating from — AND the context-window ladder, which is consumer #1
      and must be three rungs after Plan 01's A1 amendment)
    - sentinel-core/app/services/model_registry.py:75-130 (consumer #2; confirm Plan
      03 removed it)
    - Every importer in the table above
  </read_first>

  <files>shared/sentinel_shared/model_profiles.py, shared/sentinel_shared/llm_call.py, sentinel-core/tests/test_model_profiles.py, sentinel-core/tests/test_llm_call_shared.py, modules/pathfinder/app/llm.py</files>

  <behavior>
    - `get_profile` still resolves in the same three rungs: LM Studio `arch` lookup,
      then substring match on the model id, then `SAFE_DEFAULT`. The rename changes
      no resolution semantics.
    - Every existing alias still resolves: `qwen3_5` and `qwen3_5_moe` to the ChatML
      stop sequences, `gemma4` to `<end_of_turn>`, `mistral_nemo` to `</s>` only.
      The mistral and llama profiles must still NOT list their template delimiters as
      stop tokens — that produced mid-generation garbage on a live model in April.
    - Nothing reads a context window off a family profile. A test asserting the field
      is absent is fine; a test asserting a particular numeric value is not.
    - Pathfinder imports and passes its type checks with the new name.
  </behavior>

  <action>
    First confirm the precondition, and confirm it as an ABSENCE across the whole
    repository rather than at one known site. There were two consumers, not one.
    Check all three of these and record each result in the SUMMARY:

    1. `sentinel-core/app/model.py` — the context-window ladder must have three rungs
       (`loaded_context_length → max_context_length → declared 4096`) and must not
       read `.context_window` off a family profile. Plan 01 amendment A1 is what
       removed this consumer, and it is what makes this whole task safe: before A1
       the seam itself consumed the field this task deletes, so the deletion would
       have broken the ladder that had just been built on it. A read of
       `FAMILY_PROFILES` for **stop sequences** is expected and correct — leave it.
    2. `sentinel-core/app/services/model_registry.py` — `_fetch_lmstudio`'s
       family-aware fallback (was :88-104) must be gone with Plan 03 Task 1's removal
       of the registry's LM Studio live path.
    3. Repo-wide: no remaining read of `.context_window` on a value obtained from
       `get_profile(...)` / `FAMILY_PROFILES` / `SAFE_DEFAULT`, anywhere under
       `sentinel-core/`, `shared/` or `modules/`. Search for the attribute access on
       a family-profile-typed value, not just for the two file paths above — the
       failure this precondition exists to catch is a THIRD consumer nobody listed.

    If any of the three still holds a consumer, stop and report — removing the field
    under a live consumer would be a silent behaviour change to context budgeting,
    and the right move is to fix the upstream plan's leftover rather than to route
    around it here.

    Rename the dataclass in `shared/sentinel_shared/model_profiles.py` from
    `ModelProfile` to `FamilyProfile`, and update every importer in the table. Per
    ADR-0007's Consequences, the name is the point: it is a family-keyed constants
    table, and the misnomer is plausibly why it grew a `context_window` field that
    disagrees with the registry and that nothing consumes. The rename also removes a
    real hazard introduced by Plan 01 — until now there are two live types called
    `ModelProfile` in the same codebase, one of them the seam value that Plan 02
    threaded through every completion call.

    Remove the `context_window` field from the dataclass and from all seven profiles
    and `SAFE_DEFAULT`. Context windows come from the backend now, resolved by
    `LMStudioModelSource` in the order `loaded_context_length` →
    `max_context_length` → a declared, logged 4096. **There is no family-constant
    rung** — ADR decision 2 was amended 2026-09-07 to remove it precisely so this
    field could be deleted without the ladder consuming it. Leaving a second,
    disagreeing source of the same number is how the 8192-declared / 262144-served
    divergence happened, and the qwen2 entry's 32768 against a real 262144 max /
    119552 loaded is the same failure a second time.

    Leave everything else in this module alone: the seven profiles, the alias block,
    the substring patterns, `SAFE_DEFAULT`'s empty stop-sequence list, and
    `get_profile`'s cache. Do not narrow or restructure the stop-sequence data — ADR
    decision 6's warning about not narrowing detection to the loaded family applies to
    the same instinct.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/modules/pathfinder && /Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - The shared dataclass is named `FamilyProfile` and every importer uses that name.
    - The dataclass has no context-window field, and no code reads one from it.
    - All three precondition checks are recorded in the SUMMARY with their results:
      `app/model.py`'s ladder is three rungs, `model_registry.py`'s consumer is gone,
      and the repo-wide search for a family-profile `.context_window` read is empty.
    - Every alias still resolves to the same stop sequences it did before.
    - `app/model.py`'s `ModelProfile` is now the only type by that name in the repo.
    - Both suites green; pathfinder count unchanged from 03-SUMMARY.md.
  </acceptance_criteria>

  <done>
    The constants table is named for what it is, carries only family constants, and no
    longer shares a name with the per-request seam value.
  </done>
</task>

<task type="auto">
  <name>Task 2: the tokenizer name on the profile, and models-seed.json trimmed</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<action>` and `<verify>` verbatim.
  </delegation>

  <read_first>
    - sentinel-core/app/services/token_budget.py (the whole file — the cached
      encoding, count(), check(), truncate(), and the module docstring's honest note
      that cl100k_base is a safe over-estimate whose false negatives are bounded by
      LM Studio's own rejection)
    - sentinel-core/app/model.py (ModelProfile — where the encoding name goes)
    - sentinel-core/app/services/message_processing.py (where TokenBudget is
      constructed and where check() is called against the profile's context window)
    - sentinel-core/models-seed.json (5 entries)
    - sentinel-core/app/services/model_registry.py (the seed loader)
  </read_first>

  <files>sentinel-core/app/model.py, sentinel-core/app/services/token_budget.py, sentinel-core/app/services/message_processing.py, sentinel-core/models-seed.json, sentinel-core/app/services/model_registry.py, sentinel-core/tests/test_token_budget.py, sentinel-core/tests/test_model_registry.py</files>

  <behavior>
    - A profile naming a tiktoken encoding tiktoken knows produces a `TokenBudget`
      using it, and `encoding_name` reports it.
    - A profile naming an encoding tiktoken does not know produces a `TokenBudget`
      using `cl100k_base`, reports `cl100k_base` from `encoding_name`, and logs a
      warning. It does not raise — an unknown encoding name must never take down the
      message path.
    - A profile naming no encoding produces `cl100k_base` with no warning.
    - `StaticModelSource` still serves every Claude model after the seed trim, and
      still serves the declared 4096 ollama and llamacpp profiles.
    - The seed file remains valid JSON with the same top-level shape.
  </behavior>

  <action>
    Add a tokenizer-encoding field to `app/model.py`'s `ModelProfile` and have
    `TokenBudget` accept it, falling back to `cl100k_base` when tiktoken does not
    recognise the name. Per ADR-0007's Known Limitations this is accepted as
    approximate: `cl100k_base` is not Qwen's tokenizer, counting stays approximate,
    and adding a real tokenizer is a container-weight decision deliberately left
    open. What this change buys is that the approximation is now *named* rather than
    assumed — the profile says which encoding was used, and an unrecognised name
    degrades loudly instead of raising. `TokenBudget.__init__` currently calls
    `tiktoken.get_encoding` directly and will raise on an unknown name; wrap it.

    Do not add a real Qwen tokenizer, and do not add a tokenizer dependency. The
    limitation is accepted, not being fixed.

    Then trim `models-seed.json` to the cloud models. Per ADR-0007's Consequences the
    seed becomes `StaticModelSource`'s data, and it is kept over litellm's static
    registry because it preserves offline operation and operator visibility. The
    `qwen2.5:14b` ollama entry and the `local-model` lmstudio entry both describe
    backends the seam now discovers or declares: LM Studio comes from
    `LMStudioModelSource`, and ollama and llamacpp get declared 4096 profiles in
    `StaticModelSource` per the ADR's rejection of four adapters. The `local-model`
    entry's own note — "actual context window fetched at startup" — is a description
    of the behaviour this whole ADR replaced.

    `sentinel-core/tests/test_model_registry.py` is in this task's `<files>` because
    of the trim, not by accident. `test_seed_always_present_in_registry:63` asserts
    `"local-model" in registry` and `test_lmstudio_registry_falls_back_to_seed_on_unavailable:44`
    asserts the same; `local-model` is one of the two entries being removed. Update
    both to assert on what the trimmed seed actually contains — the Claude entries —
    rather than deleting them. The property they guard (the seed is always present in
    the registry even when the live fetch fails) survives the trim intact; only the
    example model id changes.

    Verify after trimming that `StaticModelSource` still serves everything it is
    supposed to. If any code path still expects a seed entry that was removed, that
    is a real coupling and must be fixed, not papered over by restoring the entry.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - `ModelProfile` names an encoding; `TokenBudget` uses it or degrades to
      `cl100k_base` with a warning, and never raises on an unknown name.
    - No new tokenizer dependency was added.
    - `models-seed.json` holds only cloud models and is valid JSON.
    - `StaticModelSource` still serves Claude from the seed and ollama/llamacpp as
      declared 4096 profiles.
    - `test_seed_always_present_in_registry` and
      `test_lmstudio_registry_falls_back_to_seed_on_unavailable` were UPDATED to the
      trimmed seed, not deleted, and both still assert the seed-always-present
      property.
    - Suite green.
  </acceptance_criteria>

  <done>
    Token counting names its encoding and degrades instead of raising, and the seed
    file holds only what it genuinely serves.
  </done>
</task>

<task type="auto">
  <name>Task 3: anomaly_rate.py reads the model from session summaries; ADR corrected</name>

  <delegation>
    Dispatch to `Agent(subagent_type: "sonnet-coder", model: "sonnet")`. Hand it
    this task's `<read_first>`, `<action>` and `<verify>` verbatim. Tell it the
    script's module docstring is a deliberate warning against a specific past mistake
    and must survive the change.
  </delegation>

  <read_first>
    - sentinel-core/scripts/anomaly_rate.py (all 227 lines — especially the module
      docstring explaining why this reads vault session summaries and NOT container
      logs: Docker destroys container logs on every recreate, so a log grep kept
      reporting messages=0 anomalies=0 during a day of deploys)
    - sentinel-core/app/services/message_processing.py:228-250 (_build_session_summary
      — the frontmatter this will read, including the model: line)
    - sentinel-core/app/vault.py (_parse_session_summary — the existing adapter-edge
      parser the script reuses, and what it does and does not return)
    - docs/adr/0007-active-model-seam.md, "Known limitations, accepted" (the stale
      Pathfinder entry)
  </read_first>

  <files>sentinel-core/scripts/anomaly_rate.py, sentinel-core/tests/test_anomaly_rate.py</files>
  <read_only>docs/adr/0007-active-model-seam.md — verified, never edited (see action)</read_only>

  <behavior>
    - Scanning a set of summaries written by two different models produces a
      per-model breakdown: responses scanned, flagged, and rate, for each model.
    - The existing overall total, flagged, percentage, skipped, excluded,
      signal_counts and flagged_files outputs are unchanged. This is an addition.
    - A summary whose frontmatter has no model line, or is malformed, is counted
      under an explicit unknown bucket rather than being dropped or crashing the run.
      The script's never-raises contract holds: a malformed summary is skipped and
      counted, not fatal.
    - The JSON output gains the breakdown; the human table gains a section for it.
  </behavior>

  <action>
    Add a per-model breakdown to `anomaly_rate.py`. Read the `model:` frontmatter line
    from each session summary and group the existing scan results by it. This is the
    measurement the whole ADR was staged around: step 1 landed the stop-sequence fix
    alone specifically so the anomaly rate could attribute a change to it rather than
    to a fifteen-file refactor, and step 2's Defect B fix is what made the recorded
    model name truthful in the first place. Before that fix every summary recorded the
    `MODEL_NAME` default, so a per-model breakdown taken over old summaries will show
    the configured name for everything written before Plan 01 landed. Note that
    explicitly in the output or the docstring — an operator reading a breakdown across
    the cutover needs to know the older rows are not trustworthy.

    Preserve the module docstring's warning verbatim in substance: this script reads
    vault session summaries and not container logs, because Docker destroys container
    logs on every recreate and the log-grep version kept reporting zero during a day
    of deploys. Do not simplify the summary walk into anything log-based.

    Keep the never-raises contract. A summary with no model line, malformed
    frontmatter, or an unreadable body is skipped and counted, never fatal.

    Then VERIFY — do not re-make — the ADR correction. An earlier draft of this task
    instructed rewriting ADR-0007's "Pathfinder continues to call LM Studio directly
    for rule_query" line. **That edit already landed in commit `307b916`.** The
    quoted text no longer exists in the file: the claim is struck through and
    followed by a "Corrected 2026-09-07 during planning" block at
    `docs/adr/0007-active-model-seam.md:157-169`. An instruction to change text that
    is not there is a no-op with an unsatisfiable acceptance criterion, so it is
    replaced by a check:

    - Confirm `docs/adr/0007-active-model-seam.md` contains the struck-through
      `~~Pathfinder continues to call LM Studio directly for `rule_query`.~~` and the
      correction that follows it, and that the correction's factual claims still
      match the code as this plan leaves it: zero `litellm.acompletion` call sites
      under `modules/pathfinder/app/`; every completion routing through
      `SentinelCoreClient.complete()`; `embed_texts` routing through core's
      `POST /embeddings`.
    - Confirm the correction still records that structured output over
      `POST /provider/complete` remains an open, deferred decision — Plan 02 added a
      `task` field, not structured output, so that limitation is still true.
    - Record the confirmation in the SUMMARY. **Make no edit to the ADR.** If the
      verification FAILS — the strike-through is missing, or a factual claim in it no
      longer holds — stop and report rather than silently re-editing the ADR; a
      mismatch there means something upstream diverged from the design of record.

    This plan therefore edits no ADR text at all. `docs/adr/0007-active-model-seam.md`
    is read-only in every plan of this set.
  </action>

  <verify>
    <automated>cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q</automated>
  </verify>

  <acceptance_criteria>
    - The scan output carries a per-model breakdown in both JSON and human forms.
    - Summaries with a missing or malformed model line land in an explicit unknown
      bucket and the run completes.
    - The overall aggregate figures are byte-identical to before for a fixture with
      one model.
    - The module docstring still warns against the log-grep approach.
    - ADR-0007's already-landed Pathfinder correction (lines 157-169, commit
      `307b916`) is confirmed present and still factually true, and NO ADR text is
      edited by this plan. `git diff --stat` shows no change to
      `docs/adr/0007-active-model-seam.md`.
    - Suite green.
  </acceptance_criteria>

  <done>
    The degenerate-response rate can be attributed to the model that produced it, and
    the ADR no longer claims something the implementation disproved.
  </done>
</task>

</tasks>

## Flagged calls

1. **The `models-seed.json` trim lives here, not in Plan 01.** The ADR pairs it with
   `StaticModelSource`, which Plan 01 builds. Deferring the trim means Plan 01's
   adapter is written against the seed as it stands and the data change is isolated
   here, where a mistake is cheap to spot.
2. **The `context_window` field removal has a precondition, and it is an ABSENCE
   check, not a single-site check.** There were two consumers, not one: the earlier
   draft named only `model_registry.py:88-104` and missed the family rung Plan 01's
   original context-window ladder put in `app/model.py`. Plan 01 amendment A1 removed
   the second one by dropping the family rung from ADR decision 2 — that amendment is
   the load-bearing precondition for this task, and without it this plan would delete
   a field the seam had just been built to read. Task 1 now checks `app/model.py`,
   `model_registry.py` and the whole repo, and stops rather than proceeding on any
   hit. Reads of `FAMILY_PROFILES` for stop sequences are expected and are not hits.
3. **A per-model breakdown across the cutover is partly untrustworthy by
   construction.** Every summary written before Plan 01's Defect B fix records the
   `MODEL_NAME` default rather than the answering model. The breakdown is still worth
   having — it is the instrument the ADR's staged sequencing exists to feed — but the
   pre-cutover rows must be labelled, not silently averaged in.
4. **This plan does NOT edit the ADR — corrected 2026-09-07.** An earlier draft
   carried the one Known-Limitations correction as work. That correction already
   landed in commit `307b916` (ADR lines 157-169), so the instruction had become a
   no-op with an unsatisfiable acceptance criterion: it quoted text that no longer
   exists. Task 3 now verifies the correction is present and still true and makes no
   edit. ADR-0007 is read-only in every plan of this set.
5. **`response_anomaly`'s detection is not narrowed.** ADR decision 6 is explicit:
   the profile may add family-specific signals but must not replace the general ones,
   because narrowing the regex to the loaded family would blind the detector to the
   wrong-family token leakage that motivated the ADR. No plan in this set adds a
   family-specific signal; this is recorded so a later reader does not mistake the
   omission for an oversight.

<output>
Create `.planning/quick/260907-amx-active-model-seam/04-SUMMARY.md` when done,
recording: both suites' exact post-change counts, confirmation that the pathfinder
count is unchanged from 03-SUMMARY.md, the three context_window precondition check
results, the seed entries removed together with the two `test_model_registry.py`
assertions updated for them, and confirmation that ADR-0007's Known-Limitations
correction is present and unedited (`git diff --stat` clean for that file).
</output>
