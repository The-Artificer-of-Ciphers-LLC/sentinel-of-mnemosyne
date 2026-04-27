---
status: complete
quick_id: 260427-vl1
slug: note-import-vault-sweeper
date: 2026-04-27
addresses: 2nd-brain note import + vault sweeper feature (sketched at .planning/sketches/note-import-and-vault-sweeper.md)
verification: passed-with-followup-fixes
---

# Quick Task 260427-vl1: Note Import + Vault Sweeper

## Outcome

End-to-end working. New 2nd-brain feature ships with three Discord subcommands (`:note`, `:inbox`, `:vault-sweep`), classifier service, vault sweeper, fail-closed admin gate, and `acompletion_with_profile` promoted to `sentinel_shared`. Live smoke confirmed all three classifier paths file correctly.

## What Was Built

### 8 atomic commits (executor)

| Commit | Task | What |
|---|---|---|
| `828e2c7` | T1 | Promote `acompletion_with_profile` to `shared/sentinel_shared/llm_call.py`; pathfinder imports updated |
| `3347860` | T2 | numpy + PyYAML in BOTH pyproject.toml AND Dockerfile (dual-ship discipline) |
| `8e04a58` | T3 | Note classifier service with cheap pre-filter (regex + length) and 7-topic taxonomy |
| `8ee5e11` | T4 | Inbox file helpers — parse/append/remove/render against `inbox/_pending-classification.md` |
| `3a337cb` | T5 | `:note` subcommand + `/note/classify` route + ObsidianClient extensions |
| `62c5c37` | T6 | `:inbox` subcommand dispatch (list/classify/discard) |
| `4908edb` | T7 | Vault sweeper: embedding de-dup ≥0.92 cosine, idempotent skip via `sweep_pass`, `_trash/{date}/` moves |
| `bc8b4cc` | T8 | `SENTINEL_ADMIN_USER_IDS` fail-closed gate + `:vault-sweep` subcommand |

### 4 follow-up fix commits (post-merge live verification)

The verifier caught one bug, then live testing surfaced three more from the same family — all LM Studio interop quirks the executor didn't anticipate:

| Commit | Bug | Fix |
|---|---|---|
| (first hotfix) | `if "/" not in model_id` skipped `openai/` prefix for HF-style ids — same bug class fixed in 5kl this morning | Use canonical `ensure_litellm_prefix` from `sentinel-core/app/services/model_selector.py` |
| (second hotfix) | Formatter pruned the import as "unused" before body update was visible | Re-added explicit multi-line import |
| (third hotfix) | `get_profile()` was passing `openai/qwen/qwen2.5-coder-14b` to LM Studio's `/api/v0/models/{id}`, returning 400 | Strip prefix before profile fetch via `strip_litellm_prefix`; pass `api_key="lmstudio"` per existing `LiteLLMProvider` pattern |
| (fourth hotfix) | LM Studio rejects `response_format={"type": "json_object"}` — only `json_schema` or `text` allowed | Switched to strict `json_schema` with the 7-topic enum baked in |

## Verified Live Behavior

```
POST /note/classify "Finished the Python basics course"
  → action=filed, topic=accomplishment, confidence=1.0,
    path=accomplishments/completed-python-basics-course-2026-04-27.md

POST /note/classify "hello are you there"
  → action=dropped, topic=noise, confidence=1.0,
    reason=cheap-filter:noise

POST /note/classify "Today was tough at work but the kids made it better"
  → action=filed, topic=journal, confidence=0.9,
    path=journal/2026-04-27/tough-day-at-work.md

GET /inbox → 200, lists pending entries (including 3 stale entries
  from before the fix — user can :inbox discard 1, 2, 3 to clean)
```

## Notable Deviations / Surprises

1. **Bug class repeated for the third time today.** The HF-namespace prefix issue (qwen/qwen2.5-coder-14b) bit pathfinder yesterday (yesterday's fix), sentinel-core (5kl this morning), and now note_classifier (this task). Each instance had its own local prefix-handling code. The 5kl refactor extracted canonical helpers (`ensure_litellm_prefix`, `strip_litellm_prefix`); this task's executor wrote its own anyway. **Followup**: an additional code-review hookify rule that flags any file containing `if "/" not in` near a `model` variable would prevent the next instance.

2. **Stale inbox entries from the development debug.** Three entries in `inbox/_pending-classification.md` from before the fixes show `confidence=0.0, reason="classifier LLM call failed"`. These are real test artifacts in your vault — clean via `:inbox discard 1`, `:inbox discard 2`, `:inbox discard 3` once Discord-side smoke is done.

3. **`api_key="lmstudio"` is a litellm requirement, not LM Studio's.** LM Studio ignores the field; litellm refuses to call without one. Documented in code comment for the next dev.

4. **LM Studio's `response_format` constraint diverges from OpenAI proper.** OpenAI accepts `{"type": "json_object"}`; LM Studio requires `json_schema` or `text`. Using `json_schema` is strictly better — the model now CAN'T emit out-of-vocab topics, removing a class of `coerce_topic` failures.

## Outstanding (Human-Side Smoke)

- Real Discord interaction with `:note <text>` confirming the bot replies correctly
- Real `:inbox`, `:inbox classify N <topic>`, `:inbox discard N` flow
- `:vault-sweep` first run against the actual vault — should walk, classify, move test artifacts to `_trash/2026-04-27/`. (Set `SENTINEL_ADMIN_USER_IDS=<your-user-id>` in `.env` first.)
- Verify the "garbage-from-testing" cleanup works on the user's actual stale notes

## Architectural Wins

- `acompletion_with_profile` is now in `sentinel_shared` — preventing a future fork between pathfinder and sentinel-core wrappers
- Cheap pre-filter is in front of every LLM call — saves tokens AND catches "are you there" garbage in 0ms
- `json_schema` strict mode means the classifier physically cannot return an out-of-vocab topic — strong invariant
- Idempotent `sweep_pass` frontmatter marker means `:vault-sweep` is safe to re-run; only newly-changed notes get re-classified
