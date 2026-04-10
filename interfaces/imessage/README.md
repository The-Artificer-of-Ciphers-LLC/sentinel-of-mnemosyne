# Sentinel iMessage Bridge

Mac-native process that bridges Apple Messages to the Sentinel AI. Polls `~/Library/Messages/chat.db` for new messages and replies via AppleScript.

**This is a tier-2 interface.** It is disabled by default (`IMESSAGE_ENABLED=false`). Discord is the primary interface.

## Requirements

- macOS (Ventura 13+ recommended)
- Python 3.12
- Full Disk Access granted to your terminal/Python interpreter
- Obsidian running (for memory features)
- Sentinel Core running (`docker compose up`)

## Installation

```bash
pip install "macpymessenger>=0.2.0" "httpx>=0.28.1"
```

## Full Disk Access Setup (Required)

The bridge reads `~/Library/Messages/chat.db`, which macOS protects with Full Disk Access.

**Grant Full Disk Access:**

1. Open **System Settings** -> **Privacy & Security** -> **Full Disk Access**
2. Click the `+` button
3. Add **Terminal.app** (or whichever terminal you use to run the bridge)
4. If you use a virtual environment, you may need to add the Python binary directly:
   `which python3` -> add that path
5. Toggle the switch to ON
6. Restart Terminal after granting access

**Verify access:**

```bash
sqlite3 ~/Library/Messages/chat.db "SELECT COUNT(*) FROM message;"
```

If this returns a number (not a permission error), Full Disk Access is working.

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `IMESSAGE_ENABLED` | Set to `true` to activate | `true` |
| `SENTINEL_API_KEY` | Must match Sentinel Core's `SENTINEL_API_KEY` | `my-secret-key` |
| `SENTINEL_CORE_URL` | URL of Sentinel Core | `http://localhost:8000` |
| `IMESSAGE_POLL_INTERVAL` | Seconds between polls (default: 3) | `3.0` |

## Running

```bash
# Load env vars and start bridge
source .env && ./launch.sh

# Or inline:
IMESSAGE_ENABLED=true SENTINEL_API_KEY=my-key SENTINEL_CORE_URL=http://localhost:8000 ./launch.sh
```

## .env.example

```bash
IMESSAGE_ENABLED=false
SENTINEL_API_KEY=your-sentinel-api-key-here
SENTINEL_CORE_URL=http://localhost:8000
IMESSAGE_POLL_INTERVAL=3.0
```

## User Identity

The bridge derives `user_id` from the sender's phone number or email handle:

- Phone: `+14155551234` -> `imsg_14155551234`
- Email: `user@example.com` -> `imsg_userexamplecom`

To set up memory context for an iMessage sender, create the corresponding file in your Obsidian vault:
`core/users/imsg_14155551234.md`

## macOS Ventura+ Note

On macOS Ventura and later, some messages store their text in a binary `attributedBody` field instead of the `text` column. The bridge will log a warning for these messages and skip them rather than attempting binary decoding:

```
WARNING Skipping attributedBody-only message ROWID 12345 from +14155551234
```

If you see this frequently, the messages may still be deliverable — the sender can try sending a plain-text message (no rich formatting).

## Stopping

Press `Ctrl+C` or kill the process. No cleanup required.
