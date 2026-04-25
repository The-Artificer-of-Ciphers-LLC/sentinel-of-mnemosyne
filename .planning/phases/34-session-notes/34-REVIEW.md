---
phase: 34-session-notes
reviewed: 2026-04-24T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - modules/pathfinder/app/session.py
  - modules/pathfinder/app/obsidian.py
  - modules/pathfinder/app/config.py
  - modules/pathfinder/app/routes/session.py
  - modules/pathfinder/tests/conftest.py
  - modules/pathfinder/app/llm.py
  - modules/pathfinder/app/main.py
  - interfaces/discord/bot.py
  - interfaces/discord/tests/conftest.py
findings:
  critical: 2
  warning: 6
  info: 3
  total: 11
status: issues_found
---

# Phase 34: Code Review Report

**Reviewed:** 2026-04-24
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 34 wires session notes (start/log/end/show/undo) through a new FastAPI router backed by Obsidian, with NPC auto-tagging, location stub creation, and LLM recap generation. The Discord side adds a `session` noun to `:pf` dispatch and a `RecapView` button. The pure-logic layer (`session.py`) is well-structured. The route layer and Discord bot contain two blockers: a string-replace corruption path that can silently mangle the persisted session note, and an empty-event text acceptance that bypasses the stated validation contract. Six warnings cover logic gaps in the conftest interception machinery, a silent empty-body patch, a candidate NPC slug set that is inflated with roster noise, a `begin_sent_at` field always reflecting midnight-UTC instead of session-start time, a `recap_text` key present with `None` value that the Discord bot misreads, and a router double-mount that registers every session route twice on the same FastAPI app.

---

## Critical Issues

### CR-01: `str.replace` corrupts note when recap text appears in another section

**File:** `modules/pathfinder/app/routes/session.py:573`

**Issue:** After injecting wikilinks into `recap_text`, the code does:
```python
full_note = full_note.replace(recap_text, recap_text_linked, 1)
```
`str.replace` matches the first literal occurrence of `recap_text` anywhere in the string. If `recap_text` also appears verbatim inside `## Events Log` (the player said the same thing the LLM echoed in the recap), the Events Log section gets silently rewritten, not the Recap section. The `maxreplace=1` only prevents replacing it twice — it does not ensure the replacement targets the correct section. This is a data-loss path: the persisted Obsidian note has its events log silently corrupted, and there is no error or warning emitted.

**Fix:** Build `full_note` with `recap_text_linked` in the first place rather than constructing it with `recap_text` and then searching-and-replacing. Pass `recap_text_linked` directly to `session_note_markdown`:
```python
if valid_npc_slugs:
    npc_link_pattern = build_npc_link_pattern(valid_npc_slugs)
    if npc_link_pattern is not None:
        slug_map = {s: s for s in valid_npc_slugs}
        recap_text = apply_npc_links(recap_text, npc_link_pattern, slug_map)

full_note = session_note_markdown(
    date=date_str,
    started_at=str(started_at),
    ended_at=ended_at,
    status="ended",
    event_count=len(event_lines),
    npcs=valid_npc_slugs,
    locations=location_slugs,
    recap=recap_text,          # already wikilink-rewritten
    npc_notes=npc_notes,
    events_log_lines=event_lines,
)
```
Remove lines 566-573 entirely (the after-the-fact replace block).

---

### CR-02: `log` verb accepts empty event text when event type prefix is present

**File:** `modules/pathfinder/app/routes/session.py:311-325`

**Issue:** When the user sends `args = "combat:"` (a valid event type followed by colon but no text), the parse produces:
- `colon_idx = 6` (> 0)
- `candidate_type = "combat"` (in `KNOWN_EVENT_TYPES`)
- `text = args[7:].strip()` → `text = ""`

`truncate_event_text("")` raises `ValueError("event text cannot be empty")` — so the route does return an error dict. However `_validate_session_event` (the Pydantic validator on `SessionRequest.args`) only validates event text when the field is used as an event body; `args` is not validated at the model level — it is a raw pass-through. The actual validator `truncate_event_text` is called in the route, so the error is caught. The bug is that `text = ""` passes to `truncate_event_text` which correctly rejects it, but the empty-text path after stripping the prefix is never tested via the model validator and can be confused with unvalidated callers.

More concretely: `_validate_session_event` exists as a standalone function but is never called on the `args` field in `SessionRequest`. There is no `@field_validator("args")` on the model. This means callers that bypass the route layer (direct Python, test fixtures) silently accept empty or control-character-containing `args` values.

**Fix:** Add a `@field_validator("args")` to `SessionRequest` that delegates to `_validate_session_event` when `verb == "log"`, or call `_validate_session_event` unconditionally from the model and rely on `truncate_event_text` inside the route to reject empties from typed prefixes. At minimum, document that `_validate_session_event` is a standalone helper and add a model-level validator:
```python
@field_validator("args")
@classmethod
def _validate_args(cls, v: str) -> str:
    # Raw pass-through — per-verb validation happens in route handlers.
    # Strip to prevent leading/trailing whitespace surprises.
    return v.strip()
```
Then explicitly test that `log` with `"combat:"` (no text after colon) returns `{"type": "error"}`.

---

## Warnings

### WR-01: Conftest metaclass interception does not handle nested patches (multiple inner mocks)

**File:** `modules/pathfinder/tests/conftest.py:86-96`

**Issue:** `_state["inner_mock"]` holds exactly one inner mock. If a test patches `litellm.acompletion` twice in sequence (or a helper patches it inside the outer `with patch(...)` block), the second assign overwrites `_state["inner_mock"]` and the first inner mock's `await_count` is lost. The restoration logic on line 89-96 reads `_state["inner_mock"]` once — if a second patch was entered, `_state["inner_mock"]` now points to the second mock and the first mock's calls are silently dropped. This produces false-low `await_count` assertions in any test with nested patches, making test coverage assertions unreliable rather than noisy-failing.

**Fix:** Use a stack instead of a single slot:
```python
_state = {"stack": []}
# In __setattr__:
if value is not tracker and value is not original_acompletion:
    _state["stack"].append(value)
elif value is tracker and _state["stack"]:
    inner = _state["stack"].pop()
    try:
        tracker.await_count += getattr(inner, "await_count", 0)
    except (AttributeError, TypeError):
        pass
```

---

### WR-02: `patch_heading` called with empty body silently clears the target section

**File:** `modules/pathfinder/app/routes/session.py:370-373`

**Issue:** In `_handle_undo`, when all events are removed and `remaining_lines` is empty:
```python
new_events_body = "\n".join(remaining_lines) if remaining_lines else ""
await obsidian.patch_heading(path, "Events Log", new_events_body, operation="replace")
```
`patch_heading` sends the empty string as the section body. The Obsidian REST API `replace` operation with an empty body deletes the section content entirely. This is arguably intentional — you've undone the last event and the log is now empty — but the comment says "replace the Events Log section" and the empty string is indistinguishable from an API error or a silent truncation. There is no confirmation or guard, and the GET-then-PUT fallback path also replaces with `""`.

**Fix:** If `remaining_lines` is empty, replace the section content with a placeholder rather than an empty string, matching the template behavior:
```python
new_events_body = "\n".join(remaining_lines) if remaining_lines else ""
# Empty is valid but send a sentinel so Obsidian doesn't strip the heading entirely.
body_to_send = new_events_body if new_events_body else "\n"
await obsidian.patch_heading(path, "Events Log", body_to_send, operation="replace")
```
Or, if deleting the content is intentional, add a comment making that explicit.

---

### WR-03: `candidate_npc_slugs` in `_handle_end` inflates the LLM context with the entire NPC roster

**File:** `modules/pathfinder/app/routes/session.py:471-476`

**Issue:**
```python
wikilink_slugs = set(re.findall(r"\[\[([^\]]+)]]", events_log))
roster_slugs = set(npc_roster_cache.keys()) if npc_roster_cache else set()
candidate_npc_slugs = list(wikilink_slugs | roster_slugs)
npc_frontmatter_block = await _build_npc_frontmatter_block(candidate_npc_slugs, obsidian)
```
`roster_slugs` is the union of all lowercase NPC names AND slugs from the entire vault NPC roster. A campaign with 40+ NPCs will cause `_build_npc_frontmatter_block` to fetch and concatenate all 40+ NPC notes into the LLM context, even if only 3 appeared in the session. This sends a huge prompt to the LLM (and will likely exceed context window limits for smaller local models), and sends NPC data for characters who were absent — misleading the LLM about who appeared this session.

The intent is clearly to include only NPCs who appeared in _this session_, not every NPC ever created.

**Fix:** Use only `wikilink_slugs` as the candidate set — these are the NPCs actually mentioned in the events log by name (the log verb wikilinks them). The roster is for fast-pass linking, not for LLM context:
```python
wikilink_slugs = set(re.findall(r"\[\[([^\]]+)]]", events_log))
candidate_npc_slugs = list(wikilink_slugs)
npc_frontmatter_block = await _build_npc_frontmatter_block(candidate_npc_slugs, obsidian)
```

---

### WR-04: `started_at` in the session note always records the `end` time on `--retry-recap`

**File:** `modules/pathfinder/app/routes/session.py:465`

**Issue:**
```python
started_at = str(fm.get("started_at", utc_now_iso()))
```
When `--retry-recap` is used on an already-ended note, the existing `started_at` from the frontmatter is correctly read back. But on the normal end path, `started_at` is read from the frontmatter of the open note — which was written when `session start` ran. This is correct.

However, when `_handle_end` calls `session_note_markdown(..., started_at=str(started_at), ...)` and the frontmatter was originally produced by `session_note_markdown` using `utc_now_iso()`, that timestamp is an ISO 8601 string (e.g. `2026-04-24T18:00:00+00:00`). When YAML loads it back via `yaml.safe_load`, it returns a `datetime.datetime` object — not a string. The `str()` call on line 465 serializes it as `2026-04-24 18:00:00+00:00` (space-separated, not `T`-separated), which is not ISO 8601. This changes the format on every `session end` call compared to what `utc_now_iso()` originally wrote.

**Fix:** When reading `started_at` back from frontmatter, normalize to ISO 8601:
```python
raw_started_at = fm.get("started_at")
if isinstance(raw_started_at, datetime.datetime):
    started_at = raw_started_at.isoformat()
elif raw_started_at is not None:
    started_at = str(raw_started_at)
else:
    started_at = utc_now_iso()
```

---

### WR-05: `build_session_embed` for `"end"` uses `data.get('date', data.get('path', '?'))` — path fallback is wrong

**File:** `interfaces/discord/bot.py:468`

**Issue:**
```python
title=f"Session ended — {data.get('date', data.get('path', '?'))}",
```
The `_handle_end` return dict has a `"path"` key but no `"date"` key — see `routes/session.py:588-594`:
```python
return {
    "type": "end",
    "path": path,
    "recap": recap_text[:500],
    "npcs": valid_npc_slugs,
    "locations": location_slugs,
}
```
`date` is absent from the `"end"` response. So `data.get('date', ...)` always falls through to `data.get('path', '?')`, and the embed title becomes `Session ended — mnemosyne/pf2e/sessions/2026-04-24.md` rather than `Session ended — 2026-04-24`. The path fallback is technically readable but is unintentional and leaks internal vault structure to the Discord user.

**Fix:** Add `"date"` to the `_handle_end` return dict in `routes/session.py`:
```python
return {
    "type": "end",
    "path": path,
    "date": date_str,
    "recap": recap_text[:500],
    "npcs": valid_npc_slugs,
    "locations": location_slugs,
}
```

---

### WR-06: Session router double-mounted — every session route registers twice

**File:** `modules/pathfinder/app/main.py:211-214`

**Issue:**
```python
app.include_router(session_router)
# Also mount at /modules/pathfinder/session so integration tests that simulate
# the sentinel-core proxy path work against the pathfinder app directly.
app.include_router(session_router, prefix="/modules/pathfinder")
```
FastAPI re-uses the same `router` object and registers its routes on the app twice. Both mounts share the same singleton references (`obsidian`, `npc_roster_cache`), so they are functionally equivalent. However, OpenAPI will list `POST /session` and `POST /modules/pathfinder/session` as two separate operations with the same operationId, which causes an OpenAPI spec validation error and confuses `doc` / `redoc` renderers. More importantly, when the route is hit on either path, both paths consume the same `obsidian` singleton — if lifespan fails partially, both paths silently degrade together with no separation.

For test integration purposes the intent is sound, but the production app should not mount the same router twice. Use `APIRouter` prefix override at include time only for the test/proxy mount:

**Fix:** For the test path, use `include_router` with `prefix` only in the test harness or create a thin test-only router that delegates. In production `main.py`, mount once:
```python
app.include_router(session_router)  # /session
# Remove the duplicate: app.include_router(session_router, prefix="/modules/pathfinder")
```
If the proxy path is genuinely needed in production, create a separate lightweight router or use an `APIRouter` with `prefix="/modules/pathfinder"` defined in a test-specific conftest.

---

## Info

### IN-01: `_slugify` duplicates rather than imports from `app.routes.npc`

**File:** `modules/pathfinder/app/session.py:17-25`

**Issue:** The comment correctly explains why `_slugify` is inlined (to avoid heavy imports from `app.routes.npc`). However, if the normalization rule ever changes in `app.routes.npc.slugify`, this inline copy will silently diverge. The two slugifiers are currently identical, but there is no automated check to keep them in sync.

**Fix:** Add a comment referencing the exact version: `# Inline copy of app.routes.npc.slugify — last synced Phase 34. Update both if normalization rule changes.` Consider a module-level unit test that asserts `_slugify("Test Name") == slugify("Test Name")` to catch divergence at CI time.

---

### IN-02: `_persist_thread_id` uses f-string in logger.warning instead of % formatting

**File:** `interfaces/discord/bot.py:1249`

**Issue:**
```python
logger.warning(f"Failed to persist thread ID {thread_id}: {exc}")
```
Python logging best practice is to use `%`-style formatting so the string is only interpolated if the log level is active. This is consistent with the rest of the file (e.g. line 109 uses `%` style) but is inconsistent in several other spots (lines 1268, 1289, 1295, 1331).

**Fix:**
```python
logger.warning("Failed to persist thread ID %s: %s", thread_id, exc)
```

---

### IN-03: `build_npc_roster_cache` silently skips non-`.md` files but logs nothing

**File:** `modules/pathfinder/app/session.py:311`

**Issue:**
```python
for path in npc_paths:
    if not path.endswith(".md"):
        continue
```
Non-`.md` files (e.g. `tokens/` image files if the listing returns them) are silently skipped with no log. This is fine for images, but if a misconfigured NPC note has a `.yaml` extension it will be silently excluded from the roster without any diagnostic. The rest of the function logs warnings for per-note failures.

**Fix:** Add a debug-level log for skipped non-`.md` entries to aid diagnosing missing NPCs in the roster:
```python
if not path.endswith(".md"):
    logger.debug("build_npc_roster_cache: skipping non-markdown path %s", path)
    continue
```

---

_Reviewed: 2026-04-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
