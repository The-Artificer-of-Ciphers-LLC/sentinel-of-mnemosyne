---
quick_id: 260907-amx
slug: active-model-seam
date: 2026-09-07
description: Implement ADR-0007 — the Active model becomes a seam resolved at request time, not three scalars pinned at startup
adr: docs/adr/0007-active-model-seam.md
branch: refactor/active-model-seam
worktree: .claude/worktrees/active-model-seam
---

# Active Model Seam — ADR-0007 implementation plans

## What this is

`docs/adr/0007-active-model-seam.md` is the **design of record**. It was converged
in a full architecture review and its decisions are settled. These plans are task
breakdown and sequencing only — they do not re-open any decision in the ADR.

The ADR replaces the three loose scalars (`model_name`, `context_window`,
`stop_sequences`) that `build_provider_router` pinned onto `app.state` at startup
with an **Active model seam** at `sentinel-core/app/model.py`: `ActiveModel.for_task(kind)`
answering through a `ModelSource` protocol with two adapters (`LMStudioModelSource`,
`StaticModelSource`), behind a 60s TTL with invalidate-and-retry-once.

## Why it sits outside the milestone

This is **out-of-milestone capability-seam work**, following the same precedent as
`.planning/quick/260513-pi4-import-music-vault` and ADR-0002's quick dir.

- It does **not** belong to the v0.6.0 Music Lesson Tracker milestone.
- The repo's `current_phase: 49` is an unrelated Music phase. **Nothing in this
  directory renumbers, inserts, or claims a phase slot.**
- `.planning/STATE.md`, `.planning/ROADMAP.md` and `.planning/phases/**` are
  deliberately untouched by this work.

## Where the work happens

Everything is done in the worktree
`/Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam`
on branch `refactor/active-model-seam`. The main checkout at
`/Users/trekkie/projects/sentinel-of-mnemosyne` is not touched.

The worktree has **no venv of its own**. Do not create or symlink one — the
`.venv` symlink pattern has destroyed the source venv before. Run the suites with
the main checkout's interpreters:

```
# sentinel-core (baseline entering this work: 717 passed, 12 skipped / 729 collected)
cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/sentinel-core \
  && /Users/trekkie/projects/sentinel-of-mnemosyne/sentinel-core/.venv/bin/python -m pytest tests/ -q

# pathfinder (baseline: 405 passed, 0 skipped)
cd /Users/trekkie/projects/sentinel-of-mnemosyne/.claude/worktrees/active-model-seam/modules/pathfinder \
  && /Users/trekkie/projects/sentinel-of-mnemosyne/modules/pathfinder/.venv/bin/python -m pytest tests/ -q
```

**Pathfinder needs its own interpreter.** The sentinel-core venv cannot import
`rapidfuzz`, so `modules/pathfinder` collected zero tests under it. Verified
2026-09-07.

## Plan set

Step 1 of the ADR's Sequencing — the stop-sequence defect fix — **is already
landed** at commit `93df616` (`fix(chat): actually send stop sequences on the
message path`). It also corrected the two docstrings that falsely claimed the chat
path pins temperature 0.4. Do not re-plan either.

| Plan | ADR step | What it does | Tasks |
|------|----------|--------------|-------|
| `01-PLAN.md` | 2 | `ActiveModel` + `ModelSource` + `LMStudioModelSource` + `StaticModelSource`; `build_provider_router` reduced to composing them; recorded-model-name fix (Defect B); `probe_classifier_model_ready` rewired | 3 |
| `02-PLAN.md` | 3 | `complete(messages, profile)` across `AIProvider` / `ProviderRouter` / `LiteLLMProvider` / `POST /provider/complete` / `SentinelCoreClient.complete()`; the six `content or reasoning_content` copies absorbed into one helper | 3 |
| `03-PLAN.md` | 4 | The deletions | 3 |
| `04-PLAN.md` | 5 | The cleanups (`FamilyProfile`, `anomaly_rate.py`, tokenizer name, seed trim) | 3 |

Plans are strictly sequential — each depends on the one before, and **each must
leave both suites green on its own.** Every plan states its expected post-change
test counts.

## Standing constraints for every plan

- **`probe_classifier_model_ready` gates a destructive vault sweep.** It is
  rewired, never deleted. Its coverage is verified before and after every change
  that touches it. It is called from `sentinel-core/app/routes/note.py:169`.
- **Repo hook: no single indexed `.py` file as a bash operand.** Always use the
  directory form `pytest tests/ -q`. `pytest tests/test_x.py` will be refused.
- **Repo hook: code edits are delegated, not hand-written by the orchestrator.**
  Every code-producing task in these plans carries a `<delegation>` block naming
  the `sonnet-coder` subagent and the exact brief to hand it.
- **Lockstep deploy.** Plan 02 changes the `POST /provider/complete` request
  contract, which Pathfinder calls over HTTP. Core and pf2e deploy from one compose
  stack and restart together, so no optional-for-one-release shim is needed — but
  the two images must ship in the same deploy.

## Flagged interpretive calls

Places where ADR-0007 was ambiguous enough that a call had to be made are recorded
inline in each plan under a `## Flagged calls` heading. They are summarised here:

1. **Where the six `content or reasoning_content` copies converge** (Plan 02) —
   five of the six are on the `acompletion_with_profile` path, not
   `LiteLLMProvider.complete`. **Resolved (ruled 2026-09-07): one exported
   `extract_completion_text()` in `shared/sentinel_shared/llm_call.py`**, beside the
   `acompletion_with_profile` that produces the raw response those five parse,
   imported by all six — `litellm_provider.py` included. `acompletion_with_profile`'s
   raw-response contract is unchanged; the extractor is an added function, not a
   changed return type.
2. **What crosses the wire on `POST /provider/complete`** (Plan 02) — Pathfinder
   cannot supply a profile without becoming a second discoverer (violating ADR
   decision 7). Resolved as: the request gains a `task` field; core resolves the
   profile.
3. **The ADR's "Pathfinder continues to call LM Studio directly for rule_query" was
   stale and is ALREADY CORRECTED in the ADR** (commit `307b916`, ADR lines 157-169)
   — verified 2026-09-07 that Pathfinder has zero `litellm.acompletion` call sites
   and that its `model`/`api_base`/`profile` parameters are documented as vestigial
   and never forwarded. Deleting `resolve_model.py` therefore needs no new core
   endpoint. **No plan edits the ADR**; Plan 04 Task 3 verifies the correction is
   present and still true. ADR-0007 is read-only across the whole plan set.
4. **Scope of the `model_selector.py` teardown** (Plan 03) — the ADR names only
   `_score`. Resolved as: `select_model`, `get_loaded_models`, `discover_*` and
   `_fetch_live_capabilities` are absorbed into `app/model.py` too, because leaving
   them would preserve the two-shapes-one-concept split the ADR removes.
5. **Where invalidate-and-retry-once is wired** (Plans 01/02) — split: `ActiveModel`
   grows `invalidate()` in Plan 01; `ProviderRouter` calls it on
   `litellm.NotFoundError` in Plan 02, once `complete()` carries a profile.
   Related: the three `_LazyRouteCtx` fakes are replaced in **Plan 02**, not Plan 03
   (moved forward 2026-09-07) — Plan 02 makes `MessageProcessor` resolve from
   `ActiveModel`, so a fake without one cannot be green.
6. **The operator context cap's config name** (Plan 01) — ADR mandates the cap but
   does not name it. Resolved as `MODEL_CONTEXT_CAP`.
7. **Capability filters for `chat` and `fast`** (Plan 01) — ADR defines the filter
   only for `structured`. Resolved as: no capability requirement for `chat`/`fast`.
8. **ADR decision 5's "/health reports embedding disagreement"** — already
   satisfied by `probe_embedding_model_loaded` + the existing `/health`
   `embedding_model` field. Recorded as a must-have, not new work.
9. **Ladder shape** (Plan 01, amended 2026-09-07) — the capability filter runs FIRST
   and narrows the candidate set; preference applies within it. Order: filter →
   `model_task_{kind}` → `model_preferred` → **last-known-good** → `model_name` →
   sole candidate → **refuse by RAISING**. Every config-consulting rung (2, 3, 5) may
   only select a model that is IN the loaded candidate set; a configured value naming
   a non-loaded model is discarded, logged, and the ladder continues. Rung 7 raises —
   it never returns an unconfirmed `MODEL_NAME`, because a model the backend never
   said it had is the bug this ADR exists to remove, not a fallback (ADR decision 4
   as amended 2026-09-08). `MODEL_NAME`'s only surviving role is `StaticModelSource`'s
   data, for when there is no live backend at all. Candidates come in two tiers:
   LOADED first and strictly preferred, then merely DOWNLOADED (`state:
   "not-loaded"`) when nothing is loaded — without which a stock JIT-enabled LM
   Studio, where nothing loads until the first request, would resolve nothing and
   raise. Selecting a not-loaded model logs an INFO line and budgets against
   `max_context_length` until the next TTL refresh sees the real
   `loaded_context_length`. The adapter reads `GET /api/v1/models` by preference and
   falls back to `/api/v0/models` on a 404: v1 scopes `capabilities` to the MODEL
   rather than to a loaded instance, which is what makes JIT + structured work at
   all, and its `loaded_instances` makes the two-tier split fall out of the data.
   Mind the spelling — v1 `type: embedding`, v0 `type: embeddings`, both excluded.
   The requirement this protects is
   testable and tested: with all five model settings unset and one chat model loaded,
   resolution returns it — swapping the loaded model needs no config and no code
   change. Three further deliberate calls inside that: an operator pin
   naming a loaded-but-incapable model still wins but MUST log a WARNING;
   last-known-good is a normal-ladder tiebreaker as well as the failed-refresh path;
   and last-known-good outranks `model_name`, because `MODEL_NAME` is a tracked
   default that may name a model nobody has loaded (`exo-model-notfound-502`) while
   last-known-good is verified still-loaded by construction. Operator pins stay above
   both. Rung 4 logs at INFO when the model it picks differs from `MODEL_NAME`, and
   stays silent when they agree — the divergence case (config says A, the system has
   been running B, nothing announces it) is the one this ADR exists to stop. The
   changed-`MODEL_NAME` scenario is NOT the reason and cannot occur: `settings` is a
   module-level singleton read once at import, so `MODEL_NAME` only changes across a
   restart, and a restart clears last-known-good.
10. **No family-constant rung in the context-window ladder** (Plans 01/04, ADR
   decision 2 amended 2026-09-07) — the ladder is `loaded_context_length` →
   `max_context_length` → declared 4096. The family rung would have consumed
   `FamilyProfile.context_window`, the field Plan 04 deletes; it is unreachable
   because both `/api/v1/models` and `/api/v0/models` always return
   `max_context_length`; and the constants
   lie (qwen2 says 32768 against a real 262144/119552). `FAMILY_PROFILES` is still
   read for stop sequences only.
11. **The 19 deleted pathfinder tests are REPLACED, not dropped** (Plan 03, ruled
   2026-09-07) — Task 2 carries a 19-row disposition table: 15 named successors, 4
   explicit behaviour-deleted-with-the-module judgements, and 4 successors that have
   to be newly written (malformed-entry filtering plus three prefix-normalisation
   cases) in `sentinel-core/tests/test_model.py`.
12. **The cloud fallback resolves its own profile** (Plan 02) — the ADR is silent and
   decision 8 puts `api_base` on the profile, so forwarding the local profile would
   hand Anthropic LM Studio's base URL. Resolved as: the fallback leg resolves from
   `StaticModelSource`, asserted by test.
