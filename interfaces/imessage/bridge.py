"""
Sentinel iMessage Bridge — Phase 3 Interface (Tier-2, feature-flagged).

Mac-native process. NOT a Docker container.
Requires: Full Disk Access granted to Python interpreter in System Settings.
Requires: IMESSAGE_ENABLED=true env var to activate.

Polls ~/Library/Messages/chat.db for new incoming messages using direct SQLite
ROWID queries. Sends messages to Sentinel Core. Replies via macpymessenger.

Libraries:
  macpymessenger>=0.2.0  — send iMessages via AppleScript
  httpx>=0.28.1          — async HTTP client for Core calls

Note: imessage_reader is NOT used for polling — it has no built-in ROWID tracking
and does not handle Ventura+ attributedBody transparently. Direct SQLite queries
with ROWID > last_rowid is the correct pattern.
"""
import asyncio
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

import httpx
from shared.sentinel_client import SentinelCoreClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [imessage-bridge] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — all from environment variables
# ---------------------------------------------------------------------------
IMESSAGE_ENABLED: bool = os.environ.get("IMESSAGE_ENABLED", "false").lower() == "true"
SENTINEL_API_KEY: str = os.environ.get("SENTINEL_API_KEY", "")
SENTINEL_CORE_URL: str = os.environ.get("SENTINEL_CORE_URL", "http://localhost:8000")
POLL_INTERVAL_SECONDS: float = float(os.environ.get("IMESSAGE_POLL_INTERVAL", "3.0"))
DB_PATH: str = os.path.expanduser("~/Library/Messages/chat.db")

# Module-level SentinelCoreClient — initialized after env vars are set
_sentinel_client = SentinelCoreClient(
    base_url=SENTINEL_CORE_URL,
    api_key=SENTINEL_API_KEY,
    timeout=200.0,
)


def _decode_attributed_body(blob: bytes) -> str | None:
    """Decode macOS Ventura+ NSKeyedArchiver attributedBody blob to plain text."""
    try:
        import plistlib

        plist = plistlib.loads(blob)
        return plist.get("NS.string", None)
    except Exception:
        return None


def sanitize_imessage_handle(handle: str) -> str:
    """
    Convert iMessage handle to a valid user_id matching ^[a-zA-Z0-9_-]+$.
    Phone "+14155551234" -> "imsg_14155551234"
    Email "user@example.com" -> "imsg_userexamplecom"
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", handle)
    return f"imsg_{sanitized}"


def poll_new_messages(conn: sqlite3.Connection, last_rowid: int) -> list[tuple[int, str, str]]:
    """
    Fetch incoming messages with ROWID > last_rowid from chat.db.
    Returns list of (rowid, handle, text) tuples.
    Falls back to attributedBody decoding when text column is NULL (Ventura+).
    Skips messages where both text and attributedBody are NULL.
    """
    rows = conn.execute(
        """
        SELECT m.ROWID, h.id, m.text, m.attributedBody
        FROM message m
        JOIN handle h ON m.handle_id = h.ROWID
        WHERE m.is_from_me = 0
          AND m.ROWID > ?
          AND (m.text IS NOT NULL OR m.attributedBody IS NOT NULL)
        ORDER BY m.ROWID ASC
        """,
        (last_rowid,),
    ).fetchall()

    results: list[tuple[int, str, str]] = []
    for rowid, handle, raw_text, attributed_body in rows:
        text = raw_text or _decode_attributed_body(attributed_body or b"")
        if not text or not text.strip():
            # Skip truly empty messages (both text and attributedBody are NULL or empty)
            continue
        results.append((rowid, handle, text))
    return results


def send_imessage_reply(handle: str, text: str) -> None:
    """Send AI response back to sender via macpymessenger (AppleScript wrapper)."""
    try:
        from macpymessenger import Messenger  # type: ignore[import]

        messenger = Messenger()
        messenger.send(handle, text)
        logger.info(f"Reply sent to {handle}")
    except ImportError:
        logger.error(
            "macpymessenger not installed. Install with: pip install macpymessenger>=0.2.0"
        )
    except Exception as exc:
        logger.error(f"Failed to send reply to {handle}: {exc}")


async def run_bridge() -> None:
    """Main polling loop. Runs until interrupted."""
    # Full Disk Access guard — fail-closed before any polling begins (D-05)
    chat_db = Path.home() / "Library" / "Messages" / "chat.db"
    try:
        chat_db.open("rb").close()
    except PermissionError:
        sys.stderr.write(
            "\n[iMessage Bridge] Full Disk Access required.\n"
            "macOS protects ~/Library/Messages/chat.db with SIP.\n"
            "To grant access:\n"
            "  1. Open System Settings -> Privacy & Security -> Full Disk Access\n"
            "  2. Enable access for Terminal (or whichever app runs this bridge)\n"
            "  3. Restart this process\n\n"
        )
        sys.exit(1)

    logger.info(f"iMessage bridge starting. Polling {DB_PATH} every {POLL_INTERVAL_SECONDS}s.")
    last_rowid: int = 0

    # Initialize last_rowid to current max — don't process historical messages on startup
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT MAX(ROWID) FROM message").fetchone()
        if row and row[0] is not None:
            last_rowid = row[0]
        conn.close()
        logger.info(f"Initialized ROWID cursor at {last_rowid} (skipping historical messages).")
    except sqlite3.OperationalError as exc:
        logger.error(
            f"Cannot open {DB_PATH}: {exc}\n"
            "Ensure Full Disk Access is granted to Python in System Settings -> Privacy & Security."
        )
        sys.exit(1)

    async with httpx.AsyncClient() as http_client:
        while True:
            try:
                conn = sqlite3.connect(DB_PATH)
                messages = poll_new_messages(conn, last_rowid)
                conn.close()

                for rowid, handle, text in messages:
                    last_rowid = max(last_rowid, rowid)
                    user_id = sanitize_imessage_handle(handle)
                    logger.info(f"New message from {handle} (user_id={user_id}): {text[:80]}")

                    ai_response = await _sentinel_client.send_message(user_id, text, http_client)
                    send_imessage_reply(handle, ai_response)

            except sqlite3.Error as exc:
                logger.error(f"SQLite error during poll: {exc}")
            except Exception as exc:
                logger.error(f"Unexpected error in poll loop: {exc}", exc_info=True)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    """Entry point — guards on IMESSAGE_ENABLED before starting."""
    if not IMESSAGE_ENABLED:
        logger.info(
            "IMESSAGE_ENABLED=false — iMessage bridge is disabled. "
            "Set IMESSAGE_ENABLED=true to activate. "
            "See interfaces/imessage/README.md for Full Disk Access setup."
        )
        sys.exit(0)

    if not SENTINEL_API_KEY:
        logger.error("SENTINEL_API_KEY is not set. Cannot authenticate with Sentinel Core.")
        sys.exit(1)

    try:
        asyncio.run(run_bridge())
    except KeyboardInterrupt:
        logger.info("iMessage bridge stopped.")


if __name__ == "__main__":
    main()
