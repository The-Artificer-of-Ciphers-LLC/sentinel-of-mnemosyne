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

import httpx

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
    Skips attributedBody-only messages (text is empty after COALESCE) with a warning.
    """
    rows = conn.execute(
        """
        SELECT m.ROWID, h.id, COALESCE(m.text, '') AS text
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
    for rowid, handle, text in rows:
        if not text.strip():
            # Ventura+ attributedBody-only message — text is NULL or empty
            # Full attributedBody decoding not implemented in Phase 3
            logger.warning(
                f"Skipping attributedBody-only message ROWID {rowid} from {handle} "
                "(Ventura+ message with no plain-text field)"
            )
            continue
        results.append((rowid, handle, text))
    return results


async def call_core(client: httpx.AsyncClient, user_id: str, content: str) -> str:
    """
    POST message to Sentinel Core. Returns AI response content string.
    Handles timeouts and HTTP errors gracefully.
    """
    try:
        resp = await client.post(
            f"{SENTINEL_CORE_URL}/message",
            json={"content": content, "user_id": user_id},
            headers={"X-Sentinel-Key": SENTINEL_API_KEY},
            timeout=200.0,
        )
        resp.raise_for_status()
        return resp.json()["content"]
    except httpx.TimeoutException:
        logger.warning(f"Core timeout for user {user_id}")
        return "The Sentinel took too long to respond. Please try again."
    except httpx.HTTPStatusError as exc:
        logger.error(f"Core HTTP error {exc.response.status_code} for user {user_id}")
        if exc.response.status_code == 401:
            return "Authentication error — check SENTINEL_API_KEY configuration."
        if exc.response.status_code == 422:
            return "Your message is too long for the current context window."
        return f"The Sentinel encountered an error (HTTP {exc.response.status_code})."
    except httpx.RequestError as exc:
        logger.error(f"Core unreachable: {exc}")
        return "The Sentinel Core is unreachable. Check that it is running."


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

                    ai_response = await call_core(http_client, user_id, text)
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
