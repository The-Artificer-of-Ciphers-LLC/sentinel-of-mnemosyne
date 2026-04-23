---
phase: 31
plan: 31-03
subsystem: pathfinder/llm
tags: [dialogue, llm, litellm, json-salvage, mood-delta]
requires: [31-01]
provides:
  - "generate_npc_reply(system_prompt, user_prompt, model, api_base) — async LiteLLM wrapper returning {reply, mood_delta}"
affects:
  - modules/pathfinder/app/llm.py
tech-stack:
  added: []
  patterns:
    - "Patterns S2: kwargs: dict = {...} + conditional api_base (mirrors extract_npc_fields lines 56-66)"
    - "Graceful JSON parse degradation via json.JSONDecodeError → salvage raw prose (RESEARCH.md Finding 7)"
    - "Defensive clamp: mood_delta in {-1, 0, 1} else coerce to 0"
    - "Reuse _strip_code_fences (no new fence stripper)"
key-files:
  created: []
  modified:
    - modules/pathfinder/app/llm.py
decisions:
  - "Salvage returns placeholder '...' when stripped content is empty (guards against empty-string replies rendering as blank Discord messages)"
  - "reply[:1500] truncate applied in BOTH happy and salvage paths, not only one (Discord 2000-char limit leaves headroom for quote-block markdown wrapper in 31-05)"
metrics:
  duration: "~5min"
  completed: "2026-04-23T20:13:45Z"
  tasks_completed: "1/1"
  files_changed: 1
  insertions: 46
  deletions: 0
---

# Phase 31 Plan 03: generate_npc_reply LLM Wrapper Summary

One-liner: Added `generate_npc_reply()` async LiteLLM wrapper to `modules/pathfinder/app/llm.py` — single chat-tier call extracting both in-character reply and mood_delta with graceful JSON-parse salvage (T-31-SEC-03) and defensive clamping (T-31-03-T02, T-31-03-D01).

## Commits

| Hash | Message |
|------|---------|
| `a6cd853` | feat(31-03): add generate_npc_reply LLM wrapper with JSON salvage |

## What Shipped

### `generate_npc_reply(system_prompt, user_prompt, model, api_base)`

Signature and behaviour per plan:

- **Async function** in `modules/pathfinder/app/llm.py` (inserted between `extract_npc_fields` and `generate_mj_description`).
- Calls `litellm.acompletion(**kwargs)` with `timeout=60.0`; `api_base` kwarg only passed when truthy (Patterns S2 — identical to `extract_npc_fields` / `update_npc_fields`).
- **Happy path:** `json.loads(_strip_code_fences(raw).strip())` → coerces `reply` to str, strips, truncates to 1500 chars; coerces `mood_delta` to int in `{-1, 0, 1}` else 0.
- **Salvage path:** on `json.JSONDecodeError`, logs `logger.warning("generate_npc_reply: JSON parse failed, salvaging reply text. raw_head=%r", raw[:200])` and returns `{"reply": stripped or "...", "mood_delta": 0}`. Never raises.

### Security mitigations delivered

| Threat ID | Mitigation in shipped code |
|-----------|----------------------------|
| T-31-03-T01 (prompt injection → malformed JSON) | JSONDecodeError branch returns LLM's own prose as `reply`, forces `mood_delta=0`, logs WARNING. No 500 propagates to user. |
| T-31-03-T02 (mood_delta=5 or "lots") | `if not isinstance(delta, int) or delta not in (-1, 0, 1): delta = 0` |
| T-31-03-D01 (overlong reply) | `[:1500]` truncate in both happy and salvage paths |
| T-31-03-D02 (LLM hang) | `timeout=60.0` in kwargs |
| T-31-03-I01 (raw log leak) | `raw[:200]` truncates WARNING log (accepted risk per plan) |

## Verification

### Smoke tests (9/9 OK)

All scenarios from plan action + 4 extras exercised via `unittest.mock.patch('app.llm.litellm.acompletion')`:

| # | Scenario | Result |
|---|----------|--------|
| 1 | Valid JSON `{"reply": "hello", "mood_delta": 1}` | Returns `{"reply": "hello", "mood_delta": 1}` |
| 2 | Plain prose (no JSON) | Returns `{"reply": "just prose, no json here", "mood_delta": 0}`; WARNING logged |
| 3 | `mood_delta: 5` | Clamps to 0 |
| 4 | Code-fenced JSON ` ```json\n{...}\n``` ` | Parses via `_strip_code_fences` |
| 5 | `api_base=None` vs `api_base="http://x:1234/v1"` | First call omits `api_base` kwarg; second includes it |
| 6 | `mood_delta: "lots"` (non-int) | Clamps to 0 |
| 7 | 2000-char reply | Truncates to exactly 1500 chars |
| 8 | Empty LLM response | Returns `{"reply": "...", "mood_delta": 0}` |
| 9 | Kwargs include `timeout=60.0` | Verified |

### Acceptance grep checks (all pass)

- `^async def generate_npc_reply\(` → 1 match
- `_strip_code_fences` → 4 occurrences (2 defining, 2 calling: extract_npc_fields + generate_npc_reply)
- `"timeout": 60.0` → 3 occurrences (extract_npc_fields + update_npc_fields + generate_npc_reply)
- `kwargs["api_base"] = api_base` → 4 occurrences (all 4 LLM functions conditionally assign)
- `mood_delta` → 5 occurrences (docstring + parse + clamp check + return happy + return salvage)
- `salvaging` → 1 match (WARNING log substring)
- `[:1500]` → 2 occurrences (happy + salvage truncate)
- `json.JSONDecodeError` → 2 occurrences (import path appears twice: try/except + existing extract_npc_fields raise-path reference)
- TODO/FIXME/NotImplementedError outside comments → 0 (AI Deferral Ban satisfied)

### Existing test suite

`cd modules/pathfinder && uv run pytest tests/ -q -k "not npc_say"` → **42 passed, 18 deselected** (no regression from Phase 29/30 tests).

### Symbol import

```
from app.llm import generate_npc_reply, extract_npc_fields, update_npc_fields, generate_mj_description
```
All four LLM helpers importable and callable.

### Targeted test `test_npc_say_json_parse_salvage` status

Still **FAILS with 404** — expected. The RED stub hits `/npc/say` which doesn't exist until Plan 31-04 wires the route. Once 31-04 lands, this test should transition RED→GREEN because the salvage path delivered here returns `{"reply": non-empty, "mood_delta": 0}` which is exactly what the assertions demand.

## Deviations from Plan

None — plan executed exactly as written. Zero auto-fixes triggered. The action block's reference code was copied verbatim with matching signature, docstring, kwargs shape, and error handling.

## Parallel-Worktree Notes

- Worktree rebased to expected base `2c7f2af` at start (was previously at `d83793b` — behind by the Wave-0 merge commit and the Wave-1 test stubs).
- Only `modules/pathfinder/app/llm.py` touched — no overlap with Plan 31-02's `modules/pathfinder/app/dialogue.py` (separate new file). Merge conflict risk: **nil**.
- `modules/pathfinder/uv.lock` was generated during dev-environment sync (`uv sync --extra dev`) required to run the baseline test suite; left uncommitted as it's pre-existing untracked per worktree initial state and out of scope for this plan.

## Follow-Ups for Plan 31-04 / 31-05

- **31-04** will import `generate_npc_reply` in `app/routes/npc.py` and call it inside the `/npc/say` handler after resolving `model = await resolve_model("chat")` (D-27).
- **31-05** will wrap `reply` text in Discord blockquote markdown (`> {reply}`) — the 1500-char truncate leaves 500 chars of headroom under Discord's 2000-char limit for markdown wrapper + attribution.
- No contract change needed: the return shape `{"reply": str, "mood_delta": int}` is the final contract.

## Self-Check: PASSED

- File `modules/pathfinder/app/llm.py` exists and contains `generate_npc_reply` — FOUND.
- Commit `a6cd853` — FOUND in `git log`.
- All acceptance grep patterns satisfy their thresholds.
- All 42 pre-existing pathfinder tests still pass.
- Smoke suite 9/9 OK.
