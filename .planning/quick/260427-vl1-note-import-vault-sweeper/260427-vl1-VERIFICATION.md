---
quick_task: 260427-vl1-note-import-vault-sweeper
verified: 2026-04-27T02:28:05Z
status: gaps_found
score: 9/10 must-haves verified
gaps:
  - truth: "User runs `:note <content>` and the classifier picks one of 7 taxonomy slugs; matching note is filed under the matching vault directory."
    status: failed
    reason: |
      Live POST /note/classify with a clean candidate ("Finished the Python basics course") returns
      action=inboxed, topic=unsure, confidence=0.0. Container logs show:
        WARNING:app.services.note_classifier:note_classifier: LLM call failed:
        litellm.BadRequestError: LLM Provider NOT provided. Pass in the LLM provider you are
        trying to call. You passed model=qwen/qwen2.5-coder-14b
      Root cause: sentinel-core/app/services/note_classifier.py:177 prepends `openai/` only when
      `"/" not in model_id`. LM Studio /v1/models returns the loaded model as
      `qwen/qwen2.5-coder-14b` (vendor-prefixed), which already contains `/`, so no prefix is
      added and litellm rejects it. Pathfinder's modules/pathfinder/app/resolve_model.py:66
      handles the same case correctly by ALWAYS prepending the openai/ prefix unless it already
      starts with `openai/`. The classifier did not replicate that pattern.

      Effect: every real-content note that survives the cheap pre-filter falls through to
      "unsure" inboxing in production. The :note happy-path documented in must-haves Truth 1
      ("Filed to learning/...") cannot be observed in the live stack. Idempotent sweep, inbox,
      and admin-gate features are unaffected.
    artifacts:
      - path: sentinel-core/app/services/note_classifier.py
        issue: "Line 176-178 only prepends `openai/` when no `/` exists in model_id; vendor-prefixed LM Studio IDs like `qwen/qwen2.5-coder-14b` slip through unprefixed and litellm refuses the call."
    missing:
      - "Replicate pathfinder's resolve_model.py:66 logic: always ensure `openai/` prefix unless model_id already starts with `openai/`. Suggested patch: `model_id = model_id if model_id.startswith('openai/') else f'openai/{model_id}'`."
      - "Add a regression test in tests/test_note_classifier.py that asserts a vendor-prefixed model id (e.g. `qwen/foo`) ends up as `openai/qwen/foo` when passed to acompletion_with_profile (mock and assert kwargs)."
human_verification:
  - test: "Once classifier prefix bug is fixed, run `:note Finished the Python basics course` from a real Discord client."
    expected: "Filed to `learning/<slug>-<date>.md` (confidence ≥ 0.5) message returned."
    why_human: "Confirms full Discord → sentinel-core → LM Studio → Obsidian round-trip."
  - test: "Run `:note hello` from Discord."
    expected: "Dropped as noise."
    why_human: "Cheap-filter behavior visible only via the Discord UI."
  - test: "As non-admin Discord user, run `:vault-sweep`."
    expected: "Refusal string: 'Admin only. Set SENTINEL_ADMIN_USER_IDS in your env to use this command.'"
    why_human: "Admin gate verified at unit-test level (7/7 pass) but bot-side dispatch needs live Discord confirmation."
  - test: "As admin Discord user, run `:vault-sweep`, then `:vault-sweep status`."
    expected: "Sweep starts; status reports running/complete with file counts."
    why_human: "End-to-end vault sweeper exercise against the real Obsidian vault — needs a real run-through, not a fake client."
  - test: "Confirm `:inbox`, `:inbox classify N <topic>`, `:inbox discard N` round-trip in Discord."
    expected: "Pending entries listed; classify files entry then renumbers; discard removes."
    why_human: "Discord-side dispatch + 409-on-concurrent-edit only observable end-to-end."
---

# Quick Task 260427-vl1: Note Import + Vault Sweeper — Verification Report

**Task Goal:** Add `:note`, `:inbox`, `:vault-sweep` Discord subcommands plus the classifier service and vault sweeper. 7-category taxonomy. Embedding ≥ 0.92 for de-dup. Idempotent sweeper. Fail-closed admin gate.

**Verified:** 2026-04-27T02:28:05Z
**Status:** gaps_found

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Task 1 — DRY port of `acompletion_with_profile` | VERIFIED | `shared/sentinel_shared/llm_call.py` exists; `modules/pathfinder/app/llm_call.py` deleted; pathfinder llm.py:23 + foundry.py:14 import `from sentinel_shared.llm_call import acompletion_with_profile`; `tests/test_llm_call_shared.py` exists and passes (4 tests). |
| 2 | Task 2 — Dual-ship deps | VERIFIED | `numpy>=1.26,<3.0` and `PyYAML>=6.0,<7.0` present in BOTH `sentinel-core/pyproject.toml` (lines 20–21) and `sentinel-core/Dockerfile` (lines 21–22). `tests/test_numpy_importable.py` imports `numpy` AND `yaml` and passes. Container build succeeded — no ModuleNotFoundError on startup. |
| 3 | Task 3 — Note classifier service | PARTIAL/FAILED | File present with correct 7-slug `TopicSlug` Literal, `_OPENERS` + `_TEST_FILENAME` regex pre-filter, `_apply_cheap_filter`, `classify_note`. Uses `select_model` + `get_profile` directly (no `app.resolve_model` import, per pre-plan decision 2). 8/8 unit tests pass. **However — live LLM call fails**: classifier produces "unsure"/0.0 in production because the openai/ provider prefix is only prepended when no `/` exists in the model id, and LM Studio returns vendor-prefixed ids like `qwen/qwen2.5-coder-14b`. See Gaps below. |
| 4 | Task 4 — Inbox helpers | VERIFIED | `services/inbox.py` exposes `PendingEntry`, `parse_inbox`, `append_entry`, `remove_entry`, `render_for_discord`, `build_initial_inbox`. 7/7 tests pass. |
| 5 | Task 5 — `:note` route + Discord | VERIFIED | `routes/note.py` defines `POST /note/classify`; router included in `app/main.py:30,261`; `interfaces/discord/bot.py:1424` has `:note` handler. Live `POST /note/classify` returns 200. |
| 6 | Task 6 — `:inbox` routes + bot | VERIFIED | `routes/note.py:175,187,227` provide `GET /inbox`, `POST /inbox/classify`, `POST /inbox/discard` with content-hash 409 precheck. `interfaces/discord/bot.py:1445` has `:inbox` handler. Live `GET /inbox` returns `{"entries":[],"rendered":"(inbox is empty)"}`. |
| 7 | Task 7 — Vault sweeper | VERIFIED | `services/vault_sweeper.py` defines `walk_vault`, `_should_skip`, `cosine_similarity`, `find_dup_clusters` (threshold 0.92), `move_to_trash` (PUT-then-DELETE to `_trash/{today}/`), idempotent `sweep_pass` check, lockfile, sweep-log writer. 12 vault-sweeper tests pass. |
| 8 | Task 8 — Admin gate + `:vault-sweep` | VERIFIED | `bot.py:95-110` defines `SENTINEL_ADMIN_USER_IDS_RAW`, wildcard handling, `_is_admin` (fail-closed when empty). `interfaces/discord/tests/test_discord_admin_gate.py` has 7 test cases, all pass. |
| 9 | Behavior preservation — containers + pathfinder | VERIFIED | `docker compose ps`: sentinel-core healthy, pf2e-module healthy. Logs show repeated `POST /modules/register` returning 200 (pathfinder lifespan heartbeat). No ModuleNotFoundError, no Traceback in logs. `GET /modules` returns 200. |
| 10 | Live smoke of new endpoints | PARTIAL | `GET /inbox` → 200, empty list. `POST /note/classify` → 200 (response shape correct), but classifier degrades to unsure/0.0 (see Truth 3 / Gap). `:vault-sweep` non-admin refusal verified at unit-test level only; live Discord verification needed (human). |

**Score:** 9/10 truths verified (Truth 3's PARTIAL state — implementation correct, live integration broken — is the single FAILED item).

### Required Artifacts

All 7 artifacts exist, are substantive, are wired:

| Artifact | Status | Notes |
|----------|--------|-------|
| `shared/sentinel_shared/llm_call.py` | VERIFIED | 1582 bytes; imported by pathfinder llm.py + foundry.py + sentinel-core note_classifier.py. |
| `sentinel-core/app/services/note_classifier.py` | VERIFIED-with-gap | 10.3K. Wired into `routes/note.py`. Live LLM call fails — see gap. |
| `sentinel-core/app/services/inbox.py` | VERIFIED | 8.2K. Pure functions. Wired into `routes/note.py`. |
| `sentinel-core/app/services/vault_sweeper.py` | VERIFIED | 16.7K. Wired into `routes/note.py:276,324`. |
| `sentinel-core/app/routes/note.py` | VERIFIED | 9.6K. Included in main.py:261. Live endpoints respond 200. |
| `sentinel-core/app/clients/obsidian.py` | VERIFIED | Extended with list_directory/read_note/write_note/delete_note/patch_append. |
| `interfaces/discord/bot.py` | VERIFIED | `:note`, `:inbox`, `:vault-sweep` subcommands present at L1424,1433,1445; SENTINEL_ADMIN_USER_IDS env handling at L95-110. |

### Key Link Verification

| From | To | Via | Status |
|------|-----|-----|--------|
| `modules/pathfinder/app/llm.py` | `shared/sentinel_shared/llm_call.py` | `from sentinel_shared.llm_call import acompletion_with_profile` | WIRED (L23) |
| `modules/pathfinder/app/foundry.py` | `shared/sentinel_shared/llm_call.py` | same | WIRED (L14) |
| `sentinel-core/app/services/note_classifier.py` | `shared/sentinel_shared/llm_call.py` | same | WIRED (L30) |
| `interfaces/discord/bot.py` | sentinel-core `/note/classify` | `_call_core_note` HTTP | WIRED |
| `sentinel-core/app/routes/note.py` | `note_classifier.classify_note` | direct call | WIRED |
| `vault_sweeper.py` | `obsidian.py` (list_directory, read_note, write_note, delete_note) | direct call | WIRED |
| `sentinel-core/Dockerfile` | numpy + PyYAML at image-build time | RUN pip install | WIRED (L21–22) |

### Test Suite Results (run inside `sentinel-core` container with deps installed)

```
tests/test_llm_call_shared.py   — passed
tests/test_numpy_importable.py  — passed
tests/test_note_classifier.py   — passed
tests/test_inbox.py             — passed
tests/test_note_routes.py       — passed
tests/test_vault_sweeper.py     — passed
==========================================
53 passed in 1.90s
```

`interfaces/discord/tests/test_discord_admin_gate.py` — 7 test cases (covers the 7 documented behaviors).

### Live Stack Probes

| Probe | Command | Result |
|-------|---------|--------|
| Container health | `docker compose ps` | sentinel-core: healthy; pf2e-module: healthy |
| Container errors | `docker compose logs sentinel-core` | 0 errors, 0 ModuleNotFoundError |
| GET /inbox | live curl | 200, `{"entries":[],"rendered":"(inbox is empty)"}` |
| POST /note/classify | live curl with "Finished the Python basics course" | 200, `{"action":"inboxed","topic":"unsure","confidence":0.0,...}` ← **wrong topic, wrong action, due to litellm provider error** |
| GET /modules | live curl | 200 (pathfinder still registered) |
| LM Studio /v1/models | live curl | Returns vendor-prefixed `qwen/qwen2.5-coder-14b` — confirms root cause |

### Anti-Patterns Found

None blocking. The classifier's `if "/" not in model_id` guard at note_classifier.py:177 is a logic bug — see Gaps.

### Gaps Summary

A single high-impact bug renders the headline `:note <content>` happy-path inoperable in production. All eight tasks landed structurally correct: artifacts exist, are substantive, are wired, all 53 unit tests + 7 admin-gate tests pass, containers run clean, pathfinder unaffected. But the classifier's openai/ prefix-prepend at note_classifier.py:177 mirrors a buggy variant of pathfinder's resolve_model logic — it only prepends when no `/` exists, missing the case where LM Studio returns vendor-prefixed model ids like `qwen/qwen2.5-coder-14b`. Live calls fall back to "unsure" / inbox every time, so the user-visible promise "filed to `learning/...`" is never observed. The fix is one line plus a regression test, but it is real production breakage and must close before this task can claim its primary goal.

---

## VERIFICATION COMPLETE

**Status:** gaps_found
**Score:** 9/10 must-haves verified
**Report:** `.planning/quick/260427-vl1-note-import-vault-sweeper/260427-vl1-VERIFICATION.md`

### Executive Summary

Eight tasks landed structurally correct — artifacts exist, are substantive, are wired; 53 unit tests + 7 admin-gate tests pass; containers run clean; pathfinder regression-free; live `GET /inbox` and `POST /note/classify` return 200. But a one-line bug in `sentinel-core/app/services/note_classifier.py:177` (`if "/" not in model_id: model_id = f"openai/{model_id}"`) fails to handle LM Studio's vendor-prefixed model ids (`qwen/qwen2.5-coder-14b`) — the prefix is only added when no `/` exists, so litellm receives a raw `qwen/...` and rejects it with "LLM Provider NOT provided". Every real-content `:note` falls through to inbox/"unsure"/0.0, which means must-have Truth 1 ("note is created in the matching vault directory") cannot be observed in the live stack. Pathfinder's `resolve_model.py:66` solves the same problem by always prepending `openai/` unless already prefixed; the classifier needs the same. Single-line fix plus a regression test will close the gap.
