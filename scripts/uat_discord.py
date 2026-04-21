#!/usr/bin/env python3
"""
Discord UAT script — tests the live Sentinel Discord bot end-to-end.

Required environment variables:
    DISCORD_BOT_TOKEN      — bot token (or /run/secrets/discord_bot_token)
    UAT_DISCORD_CHANNEL_ID — test channel where bot can create threads
    UAT_SENTINEL_URL       — sentinel-core URL (e.g. http://localhost:8000)
    UAT_SENTINEL_KEY       — X-Sentinel-Key value
    UAT_OBSIDIAN_URL       — Obsidian REST API URL (e.g. http://localhost:27124)
    UAT_OBSIDIAN_KEY       — Obsidian API key
    LIVE_TEST=1            — must be set (prevents accidental execution)

Exit codes:
    0 — all tests passed
    1 — one or more tests failed or LIVE_TEST not set

Notes on bot token / UAT client:
    The UAT client connects with the same Discord bot token as the Sentinel bot.
    This means the UAT client IS the bot. After Task 1's owner_id fallback fix, any
    thread created by this client has owner_id == bot.user.id, so the running bot's
    on_message handler will accept messages sent to those threads — no need to seed
    ops/discord-threads.md manually.

    Slash commands (/sen) cannot be invoked by a bot client. Instead, this script:
    1. Creates a test thread directly via the Discord REST API (create_thread).
    2. Sends test messages to that thread as the bot (the bot can send messages).
    3. Polls thread history for a reply from the bot that was not the initial message.

    This pattern works because the on_message owner_id fallback (Task 1) accepts
    any thread created by the bot user, not just ones previously registered in
    SENTINEL_THREAD_IDS.
"""
import asyncio
import os
import sys
import time
import uuid

try:
    import discord
except ImportError:
    print("discord.py not installed. Run: pip install discord.py")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_secret(name: str, env_fallback: str = "") -> str:
    """Read a Docker secret from /run/secrets/<name>, fallback to env var."""
    path = f"/run/secrets/{name}"
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return env_fallback


_ERROR_STRINGS = (
    "Authentication error",
    "Cannot reach",
    "Something went wrong (HTTP",
    "unexpected error occurred",
)


def _is_error_response(text: str) -> bool:
    return any(e in text for e in _ERROR_STRINGS)


# ---------------------------------------------------------------------------
# Test cases: (label, message_to_send)
# ---------------------------------------------------------------------------

_TEST_CASES = [
    # No-arg standard commands
    (":help", ":help"),
    (":next", ":next"),
    (":health", ":health"),
    (":goals", ":goals"),
    (":ralph", ":ralph"),
    (":pipeline", ":pipeline"),
    (":reweave", ":reweave"),
    (":check", ":check"),
    (":rethink", ":rethink"),
    (":refactor", ":refactor"),
    (":tasks", ":tasks"),
    (":stats", ":stats"),
    # Arg commands
    (":graph orphans", ":graph orphans"),
    (":capture UAT test insight", ":capture UAT test insight"),
    (":seed UAT raw content", ":seed UAT raw content"),
    (":connect UAT Test Note", ":connect UAT Test Note"),
    (":review UAT Test Note", ":review UAT Test Note"),
    (":learn UAT topic", ":learn UAT topic"),
    (":remember UAT observation", ":remember UAT observation"),
    (":revisit UAT Note", ":revisit UAT Note"),
    # Plugin commands
    (":plugin:help", ":plugin:help"),
    (":plugin:setup", ":plugin:setup"),
    (":plugin:tutorial", ":plugin:tutorial"),
    (":plugin:ask what is PKM?", ":plugin:ask what is PKM?"),
    (":plugin:add-domain uat-domain", ":plugin:add-domain uat-domain"),
    # Edge cases
    ("bare colon", ":"),
    (":doesntexist (unknown)", ":doesntexist"),
    # Natural language
    ("natural language help", "what commands do you have?"),
    # Plain text to AI
    ("plain text AI", "Hello Sentinel, this is a UAT test message"),
]


# ---------------------------------------------------------------------------
# UAT runner
# ---------------------------------------------------------------------------


async def run_uat(
    bot_token: str,
    channel_id: int,
    sentinel_url: str,
    sentinel_key: str,
    obsidian_url: str,
    obsidian_key: str,
) -> tuple[int, int, list[tuple[str, str]]]:
    """Run all UAT test cases. Returns (passed, failed, failures)."""

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    passed = 0
    failed = 0
    failures: list[tuple[str, str]] = []
    created_threads: list[discord.Thread] = []
    test_thread: discord.Thread | None = None
    ready_event = asyncio.Event()

    @client.event
    async def on_ready() -> None:
        ready_event.set()

    async def wait_for_bot_reply(
        thread: discord.Thread,
        after_ts: float,
        timeout: float = 15.0,
    ) -> str | None:
        """Poll thread history for a bot reply after after_ts. Returns reply text or None."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            try:
                messages = [
                    m
                    async for m in thread.history(limit=10)
                    if m.author.bot
                    and m.author.id != client.user.id  # reply from the Sentinel bot instance
                    and m.created_at.timestamp() > after_ts
                ]
            except Exception:
                messages = []
            # The UAT client IS the bot — look for any message from a bot (the running
            # Sentinel instance) with content posted after our send timestamp.
            # In practice, the Sentinel bot process and the UAT client share the same token,
            # so both messages come from the same user ID. We fall back to checking for ANY
            # new message after after_ts (excluding our own send).
            if not messages:
                # Broader check: any new message (bot or not) after our sent message
                try:
                    all_recent = [
                        m
                        async for m in thread.history(limit=10)
                        if m.created_at.timestamp() > after_ts + 0.1
                    ]
                    if all_recent:
                        return all_recent[0].content
                except Exception:
                    pass
            else:
                return messages[0].content

        return None

    # Start client in background, wait for ready
    client_task = asyncio.ensure_future(client.start(bot_token))
    try:
        await asyncio.wait_for(ready_event.wait(), timeout=30.0)
    except asyncio.TimeoutError:
        print("ERROR: Discord client did not become ready within 30 seconds.", file=sys.stderr)
        await client.close()
        await client_task
        return 0, len(_TEST_CASES), [(label, "timeout: bot never ready") for label, _ in _TEST_CASES]

    try:
        # Get the test channel
        channel = client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(channel_id)
            except Exception as exc:
                raise RuntimeError(f"Cannot fetch channel {channel_id}: {exc}") from exc

        # Create a fresh test thread for this UAT run
        uat_id = uuid.uuid4().hex[:8]
        test_thread = await channel.create_thread(
            name=f"sentinel-uat-{uat_id}",
            type=discord.ChannelType.public_thread,
            auto_archive_duration=60,
        )
        created_threads.append(test_thread)

        # Run test cases
        for label, message in _TEST_CASES:
            try:
                sent = await test_thread.send(message)
                send_ts = sent.created_at.timestamp()
                reply = await wait_for_bot_reply(test_thread, send_ts, timeout=15.0)

                if reply is None:
                    failed += 1
                    failures.append((label, "no reply within 15s"))
                elif _is_error_response(reply):
                    failed += 1
                    failures.append((label, f"error response: {reply[:120]!r}"))
                elif label == ":doesntexist (unknown)" and "Unknown command" not in reply:
                    failed += 1
                    failures.append((label, f"expected 'Unknown command', got: {reply[:120]!r}"))
                else:
                    passed += 1
            except Exception as exc:
                failed += 1
                failures.append((label, f"exception: {exc}"))

    finally:
        # Teardown — must run even on failure
        await _teardown(
            client=client,
            threads=created_threads,
            obsidian_url=obsidian_url,
            obsidian_key=obsidian_key,
        )
        await client.close()
        client_task.cancel()
        try:
            await client_task
        except (asyncio.CancelledError, Exception):
            pass

    return passed, failed, failures


async def _teardown(
    client: discord.Client,
    threads: list[discord.Thread],
    obsidian_url: str,
    obsidian_key: str,
) -> None:
    """Delete created Discord threads and clean up Obsidian artifacts. Swallows all errors."""

    # Delete Discord test threads
    thread_ids = {t.id for t in threads}
    for thread in threads:
        try:
            await thread.delete()
        except Exception as exc:
            print(f"[teardown] Could not delete thread {thread.id}: {exc}", file=sys.stderr)

    if not obsidian_url or not obsidian_key:
        return

    # Clean ops/discord-threads.md — remove lines that are our thread IDs
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(
                f"{obsidian_url}/vault/ops/discord-threads.md",
                headers={"Authorization": f"Bearer {obsidian_key}"},
            )
            if resp.status_code == 200:
                original_lines = resp.text.splitlines()
                cleaned_lines = [
                    line for line in original_lines
                    if not (line.strip().isdigit() and int(line.strip()) in thread_ids)
                ]
                if len(cleaned_lines) != len(original_lines):
                    await http.put(
                        f"{obsidian_url}/vault/ops/discord-threads.md",
                        headers={
                            "Authorization": f"Bearer {obsidian_key}",
                            "Content-Type": "text/markdown",
                        },
                        content="\n".join(cleaned_lines).encode("utf-8"),
                    )
    except Exception as exc:
        print(f"[teardown] Could not clean discord-threads.md: {exc}", file=sys.stderr)

    # Delete UAT-tagged notes from inbox/
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            search_resp = await http.post(
                f"{obsidian_url}/search/simple/?query=UAT",
                headers={"Authorization": f"Bearer {obsidian_key}"},
            )
            if search_resp.status_code == 200:
                results = search_resp.json()
                for item in results:
                    path = item.get("filename") or item.get("path") or ""
                    if path.startswith("inbox/"):
                        try:
                            await http.delete(
                                f"{obsidian_url}/vault/{path}",
                                headers={"Authorization": f"Bearer {obsidian_key}"},
                            )
                        except Exception as exc:
                            print(
                                f"[teardown] Could not delete vault note {path}: {exc}",
                                file=sys.stderr,
                            )
    except Exception as exc:
        print(f"[teardown] Could not search/delete UAT notes: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    if not os.getenv("LIVE_TEST"):
        print("LIVE_TEST=1 must be set to run UAT. Exiting.")
        sys.exit(1)

    bot_token = _read_secret("discord_bot_token", os.environ.get("DISCORD_BOT_TOKEN", ""))
    if not bot_token:
        print("ERROR: DISCORD_BOT_TOKEN or /run/secrets/discord_bot_token is required.")
        sys.exit(1)

    channel_id_raw = os.environ.get("UAT_DISCORD_CHANNEL_ID", "")
    if not channel_id_raw.isdigit():
        print("ERROR: UAT_DISCORD_CHANNEL_ID must be set to a valid Discord channel snowflake.")
        sys.exit(1)
    channel_id = int(channel_id_raw)

    sentinel_url = os.environ.get("UAT_SENTINEL_URL", "http://localhost:8000")
    sentinel_key = os.environ.get("UAT_SENTINEL_KEY", "")
    obsidian_url = os.environ.get("UAT_OBSIDIAN_URL", "http://localhost:27124")
    obsidian_key = os.environ.get("UAT_OBSIDIAN_KEY", "")

    passed, failed, failures = asyncio.run(
        run_uat(
            bot_token=bot_token,
            channel_id=channel_id,
            sentinel_url=sentinel_url,
            sentinel_key=sentinel_key,
            obsidian_url=obsidian_url,
            obsidian_key=obsidian_key,
        )
    )

    total = passed + failed
    print()
    print("=== Sentinel Discord UAT Report ===")
    print(f"Total: {total}  Passed: {passed}  Failed: {failed}")
    if failures:
        print("FAILED tests:")
        for label, reason in failures:
            print(f"  - {label} — {reason}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
