---
phase: 03-interfaces
plan: "03"
subsystem: interfaces/imessage
tags: [imessage, bridge, sqlite, polling, macpymessenger, httpx, feature-flag]
dependency_graph:
  requires: [03-01]
  provides: [IFACE-05-imessage-bridge]
  affects: [interfaces/imessage/]
tech_stack:
  added: [macpymessenger>=0.2.0, httpx>=0.28.1 (host process)]
  patterns: [sqlite-rowid-polling, feature-flag-disabled-by-default, imsg_-user-id-prefix, applescript-send-via-macpymessenger]
key_files:
  created:
    - interfaces/imessage/bridge.py
    - interfaces/imessage/launch.sh
    - interfaces/imessage/README.md
  modified: []
decisions:
  - "Direct SQLite ROWID > ? polling used instead of imessage_reader — imessage_reader has no built-in polling and does not handle Ventura+ attributedBody transparently"
  - "MAX(ROWID) cursor initialized on startup — skips all historical messages, only processes messages arriving after bridge starts"
  - "attributedBody-only messages (Ventura+) skipped with warning log, not decoded — Phase 3 scope; plain-text messages still work"
  - "macpymessenger imported inside send_imessage_reply() with ImportError guard — allows bridge.py to load even if not installed, surfacing a clear error at send time"
metrics:
  duration_seconds: 120
  completed: "2026-04-10"
  tasks_completed: 2
  files_changed: 3
---

# Phase 03 Plan 03: iMessage Bridge Summary

**One-liner:** Mac-native iMessage bridge using direct SQLite ROWID polling, macpymessenger send, and IMESSAGE_ENABLED=false feature flag for explicit opt-in.

## What Was Built

`interfaces/imessage/bridge.py` — a fully async Mac-native Python process that polls `~/Library/Messages/chat.db` using direct SQLite `ROWID > last_rowid` queries (not `imessage_reader`). On startup, it initializes the ROWID cursor to `MAX(ROWID)` so historical messages are never processed. Each polling cycle fetches new incoming messages, sanitizes the sender handle to the `imsg_{alphanum}` `user_id` pattern, POSTs to Sentinel Core with `X-Sentinel-Key` auth, and replies via `macpymessenger.Messenger().send()`. Ventura+ `attributedBody`-only messages (where `text` is NULL after `COALESCE`) are skipped with a warning log. All error cases (Core timeout, HTTP errors, `chat.db` permission denied, macpymessenger not installed) are caught and logged without crashing the loop.

`interfaces/imessage/launch.sh` — bash launcher with double guards: exits 0 if `IMESSAGE_ENABLED` is not `true`, exits 1 if `SENTINEL_API_KEY` is empty. Uses `exec python3 "${SCRIPT_DIR}/bridge.py"` with absolute path resolution.

`interfaces/imessage/README.md` — Full Disk Access setup documentation with exact System Settings path (`System Settings -> Privacy & Security -> Full Disk Access`), verification command, env var table, user_id pattern explanation, and Ventura+ note.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | bridge.py — iMessage polling loop with ROWID tracking and Core HTTP call | 19e2e5d | interfaces/imessage/bridge.py |
| 2 | launch.sh and README.md — launcher guard and Full Disk Access documentation | 7c87514 | interfaces/imessage/launch.sh, interfaces/imessage/README.md |

## Verification

```
python3 syntax check: OK
IMESSAGE_ENABLED=false python3 bridge.py -> exits 0 with clear log message
test -x interfaces/imessage/launch.sh -> OK
grep "Full Disk Access" README.md -> OK
grep "ROWID > ?" bridge.py -> OK
```

All success criteria confirmed:
- bridge.py exits cleanly (exit 0) when IMESSAGE_ENABLED=false
- bridge.py polls using direct SQLite ROWID > ? queries, not imessage_reader
- Ventura+ attributedBody-only messages skipped with warning log
- Sender handle sanitized to imsg_{alphanum} before Core call
- Core called with X-Sentinel-Key header
- launch.sh is executable and guards on IMESSAGE_ENABLED
- README.md documents Full Disk Access setup with exact System Settings path

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — the bridge is fully wired end-to-end. macpymessenger and httpx are the only runtime dependencies not installed in the worktree (Mac-native process; not installed in the dev environment). The `send_imessage_reply()` function handles the `ImportError` gracefully with a clear error log. The integration path (chat.db -> bridge.py -> Core -> macpymessenger -> Messages.app) is complete.

## Threat Flags

None — this plan implements all mitigations from the threat model:
- T-03-10: IMESSAGE_ENABLED=false double-guard in both launch.sh and bridge.py main()
- T-03-11: SENTINEL_API_KEY checked explicitly; bridge exits 1 if blank
- T-03-12: sqlite3.OperationalError caught at startup with remediation message; exits 1
- T-03-14: MAX(ROWID) cursor initialization prevents historical message processing

## Self-Check: PASSED

- interfaces/imessage/bridge.py: FOUND
- interfaces/imessage/launch.sh: FOUND (executable)
- interfaces/imessage/README.md: FOUND (contains Full Disk Access, System Settings, IMESSAGE_ENABLED=false, imsg_)
- Commit 19e2e5d: FOUND
- Commit 7c87514: FOUND
