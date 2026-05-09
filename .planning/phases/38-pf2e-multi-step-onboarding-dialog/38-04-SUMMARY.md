---
phase: 38-pf2e-multi-step-onboarding-dialog
plan: 04
subsystem: discord-pathfinder-onboarding
tags: [pathfinder, discord, dialog, wave-1, green]
requires: [38-01]
provides:
  - "STEPS, QUESTIONS module-level constants"
  - "draft_path / save_draft / load_draft / delete_draft (frontmatter draft I/O over Obsidian REST)"
  - "start_dialog / resume_dialog (thread creation + step re-post)"
  - "consume_as_answer (step machine + completion path to /player/onboard)"
  - "cancel_dialog (cleanup + archive)"
  - "PathfinderRequest.author_display_name (additive bridge field)"
affects:
  - "interfaces/discord/pathfinder_player_dialog.py (new file, 304 lines)"
  - "interfaces/discord/pathfinder_types.py (1-line additive field)"
tech-stack:
  added:
    - "PyYAML custom loader (subclassed SafeLoader without timestamp resolver) — keeps ISO-8601 strings as strings on draft round-trip"
  patterns:
    - "direct httpx-from-interface vault REST (mirrors bot.py:_persist_thread_id at bot.py:536)"
    - "lazy `from bot import ...` inside function bodies to avoid import cycle (bot.py imports the discord adapter graph)"
key-files:
  created:
    - interfaces/discord/pathfinder_player_dialog.py
  modified:
    - interfaces/discord/pathfinder_types.py
decisions:
  - "Used a custom yaml.SafeLoader subclass (`_NoTimestampLoader`) that drops the implicit `tag:yaml.org,2002:timestamp` resolver. The default SafeLoader auto-coerces `2026-05-08T00:00:00Z` to a `datetime` object, which broke the test asserting raw ISO strings round-trip. Plain values like ints and bools are still typed normally. This is the minimal deviation — the loader is private to this module and does not affect any other consumer of YAML."
metrics:
  duration_minutes: 8
  tasks_completed: 3
  tests_turned_green: 23
  files_created: 1
  files_modified: 1
  commits: 2
completed: 2026-05-09
---

# Phase 38 Plan 04: Wave 1 Dialog Module Implementation Summary

Implemented `interfaces/discord/pathfinder_player_dialog.py` — the multi-step PF2E onboarding state machine — and added the additive `author_display_name` field to `PathfinderRequest`. All 23 RED tests written in plan 38-01 are now GREEN. No existing test was modified (Test-Rewrite Ban honored). No code outside the two listed files was touched (Spec-Conflict Guardrail honored — `pathfinder_player_adapter.py` is untouched and reserved for plan 38-06).

## What Shipped

### `pathfinder_player_dialog.py` — 304 lines

Public surface:

| Symbol | Purpose |
|---|---|
| `STEPS` | `("character_name", "preferred_name", "style_preset")` — locked per D-13 |
| `QUESTIONS` | dict mapping each step to its prompt text — locked per D-13 |
| `draft_path(thread_id, user_id)` | Returns `mnemosyne/pf2e/players/_drafts/{thread_id}-{user_id}.md`; coerces user_id to str (Pitfall 6) |
| `save_draft(...)` | PUT frontmatter-only markdown body to vault REST |
| `load_draft(...)` | GET + parse frontmatter; returns None on 404 (Pitfall 4) |
| `delete_draft(...)` | DELETE; tolerates 404 |
| `start_dialog(invoking_channel, user_id, message_author_display_name, http_client)` | Creates public thread with `type=discord.ChannelType.public_thread, auto_archive_duration=60`, name truncated to 100 chars, registers in `SENTINEL_THREAD_IDS`, calls `_persist_thread_id`, saves first draft with `step="character_name"`, posts Q1 |
| `resume_dialog(thread, user_id, http_client)` | Re-posts the prompt for the draft's current step; does NOT mutate the draft |
| `consume_as_answer(...)` | Advances one step on each valid reply. Final step (`style_preset`) POSTs `modules/pathfinder/player/onboard` with the four-field payload, deletes draft, archives thread (HTTPException swallowed per Pitfall 2), discards from `SENTINEL_THREAD_IDS`, returns success text. Invalid style preset re-asks the same step without mutating the draft. |
| `cancel_dialog(thread, user_id, http_client)` | If draft exists: DELETE + archive + discard, returns "Onboarding cancelled. Run \`:pf player start\` to begin again." If no draft: returns exactly "No onboarding dialog in progress." |

Private helpers:

- `_split_frontmatter` / `_join_frontmatter` — inlined per RESEARCH §Anti-Patterns (markdown_frontmatter.py is sentinel-core-only).
- `_NoTimestampLoader` — yaml.SafeLoader subclass that preserves ISO-8601 timestamps as strings on parse.
- `_vault_url` / `_vault_headers` — mirrors bot.py:_persist_thread_id verbatim (env `OBSIDIAN_API_URL`, bearer from `_read_secret("obsidian_api_key", env_fallback)`).
- `_archive_and_discard` — wraps `Thread.edit(archived=True)` with `discord.HTTPException` swallow + `SENTINEL_THREAD_IDS.discard`.
- `_normalise_style_preset` — case-insensitive match against `_VALID_STYLE_PRESETS` imported from `pathfinder_player_adapter`. Returns canonical-case string or None.

Style preset normalisation: lowercase input `"lorekeeper"` is stored and posted as canonical `"Lorekeeper"`. Pipe-syntax in `PlayerStartCommand` is left strict (38-06 will preserve that path verbatim).

### `pathfinder_types.py` — 1 line added

```python
author_display_name: str | None = None  # bridge-supplied: message.author.display_name (Phase 38)
```

Default `None` preserves all existing test fixtures that construct `PathfinderRequest` without the kwarg. The bridge layer (38-06) populates it from `message.author.display_name`.

## Test Outcomes

| Suite | Before | After |
|---|---|---|
| `test_pathfinder_player_dialog.py` | 23 RED (ImportError) | **23 GREEN** |
| `test_pathfinder_player_adapter.py` | 22 RED + 38 GREEN (pre-existing 38-05/06 RED tests) | 22 RED + 42 GREEN (4 additional passes resolved by import availability) |
| `test_pathfinder_dispatch.py` | (some RED tied to 38-05/06) | unchanged |
| `test_dialog_router.py` | 8 RED (ModuleNotFoundError on dialog_router) | unchanged — still 8 RED, exactly as expected for plan 38-05 |

No regressions. The 22 pre-existing RED tests in `test_pathfinder_player_adapter.py` are downstream-plan tests for `PlayerCancelCommand` and verb-blocking-when-draft-open; they remain RED and will turn GREEN in plan 38-06.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] YAML SafeLoader auto-coerces ISO-8601 timestamps to datetime objects**

- **Found during:** Task 1 verification (`test_load_draft_returns_frontmatter_dict` failed)
- **Issue:** The plan called for `yaml.safe_load`, but PyYAML's SafeLoader resolves the implicit `tag:yaml.org,2002:timestamp` tag. The test asserts the round-trip preserves `started_at` as the literal ISO string `"2026-05-08T00:00:00Z"`, but SafeLoader returned `datetime.datetime(2026, 5, 8, 0, 0, tzinfo=datetime.timezone.utc)`.
- **Fix:** Subclassed `yaml.SafeLoader` as `_NoTimestampLoader`, dropping the timestamp implicit resolver. Plain types (int, bool, float) still resolve normally; only ISO timestamps remain strings. Switched the parse call from `yaml.safe_load(...)` to `yaml.load(..., Loader=_NoTimestampLoader)`.
- **Files modified:** `interfaces/discord/pathfinder_player_dialog.py`
- **Commit:** d44b007

No other deviations.

## Auth Gates

None — all execution was code-only.

## Threat Flags

None. The new file shells calls through `_read_secret` with the same bearer token as `bot.py:_persist_thread_id`; no new auth or trust boundary introduced. The new dataclass field is bridge-internal, never serialised to network.

## Self-Check: PASSED

- `interfaces/discord/pathfinder_player_dialog.py` exists (verified, 304 lines).
- `interfaces/discord/pathfinder_types.py` contains `author_display_name` (verified via diff).
- Commit d44b007 exists in git log (verified).
- Commit bd47831 exists in git log (verified).
- All 23 tests in `test_pathfinder_player_dialog.py` pass (verified by pytest run).
- No regressions outside the pre-existing downstream-plan RED tests (verified by baseline diff).
- No `# TODO`, no `pass` stubs, no `NotImplementedError`, no `# type: ignore`, no `# noqa` (AI Deferral Ban honored).
- `_VALID_STYLE_PRESETS` is imported, not duplicated (verified by `from pathfinder_player_adapter import _VALID_STYLE_PRESETS`).
