# Phase 38: PF2E Multi-Step Onboarding Dialog - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-08
**Phase:** 38-pf2e-multi-step-onboarding-dialog
**Areas discussed:** Draft-check hook point, Mid-dialog rejection lookup, Thread lifecycle on completion / cancel, Question text ownership & step machine layout

---

## Draft-Check Hook Point (Router Seam)

| Option | Description | Selected |
|--------|-------------|----------|
| Inside `command_router.route_message`, before the `:`-prefix branch | One file edit; couples command_router to vault/Obsidian | |
| New `dialog_router` module wired BEFORE `command_router` | Bridge calls `dialog_router.maybe_consume_as_answer()` first; falls through on miss | ✓ |
| Inside `bot.py.on_message`, before `_route_message` | Earliest interception; bypasses the routing test seam | |

**User's choice:** New `dialog_router` module
**Notes:** Keeps `command_router` pure and trivially testable. New module owns the draft I/O concern in one place.

---

## Mid-Dialog Rejection Lookup

| Option | Description | Selected |
|--------|-------------|----------|
| GET vault listing of `_drafts/`, filter by `{user_id}` suffix | Authoritative; no cache invalidation; localhost latency negligible | ✓ |
| In-process dict `{user_id: [thread_ids]}` populated on draft create/delete | Faster but stale across restarts; coherence invariant easy to break | |
| Obsidian POST `/search/simple/` query | Indirect; wrong tool for known-prefix lookup | |

**User's choice:** Vault directory listing
**Notes:** Vault is the single source of truth for draft state. Surface every active thread in the rejection message, not just the first (D-08).

---

## Thread Lifecycle on Completion / Cancel

| Option | Description | Selected |
|--------|-------------|----------|
| Stays open as a regular Sentinel thread; final message + draft delete; no archive | Simplest; reuses existing thread infrastructure | |
| Auto-archive the thread on completion | Cleaner UI; requires `discord.Thread.edit(archived=True)`; symmetric on cancel | ✓ |
| Delete on cancel; keep open on completion | Asymmetric; needs Manage Threads permission | |

**User's choice:** Auto-archive on completion
**Notes:** Confirmed symmetric — cancel also archives the dialog thread (D-10). Once archived, thread is removed from `SENTINEL_THREAD_IDS` (D-11).

---

## Question Text Ownership & Step Machine

| Option | Description | Selected |
|--------|-------------|----------|
| New `pathfinder_player_dialog.py` module | Per-concern split mirrors npc_basic / npc_rich pattern | ✓ |
| Inline in `pathfinder_player_adapter.py` | Smaller diff but bloats an already 279-line file | |
| Step values as Python Enum class | Type-safe but adds indirection; round-trips as strings anyway | |

**User's choice:** New `pathfinder_player_dialog.py` module with literal-string step values
**Notes:** Step constants and questions ship as the preview from the question:
```python
STEPS = ("character_name", "preferred_name", "style_preset")
QUESTIONS = {
    "character_name": "What is your character's name?",
    "preferred_name": "How would you like me to address you?",
    "style_preset": "Pick a style: Tactician, Lorekeeper, Cheerleader, Rules-Lawyer Lite",
}
```
Style-preset validation reuses `_VALID_STYLE_PRESETS` from `pathfinder_player_adapter.py:22` (D-14). New `PlayerCancelCommand` lives in the adapter (D-16).

---

## Claude's Discretion

- Draft frontmatter field order / YAML formatting style
- Exact wording of rejection and cancel-acknowledgement messages (information content fixed by D-07/D-10; phrasing open)
- Exception handling around Obsidian I/O failures (follow existing adapter conventions)
- Test file naming under `interfaces/discord/tests/`

## Deferred Ideas

- 24h or operator-configured draft expiry sweep
- Slash-command Discord modal as an alternative onboarding UI
- Configurable question text / i18n
- Editing an already-onboarded profile (future verb, e.g. `:pf player edit`)
- Pipe-syntax deprecation (revisit after one full milestone of dialog dominance)
