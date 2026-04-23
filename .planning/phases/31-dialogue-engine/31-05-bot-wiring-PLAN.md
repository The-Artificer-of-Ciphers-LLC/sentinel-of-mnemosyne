---
plan_id: 31-05
phase: 31
wave: 3
depends_on: [31-01, 31-04]
files_modified:
  - interfaces/discord/bot.py
autonomous: true
requirements: [DLG-01, DLG-02, DLG-03]
must_haves:
  truths:
    - "interfaces/discord/bot.py has a `say` branch in _pf_dispatch that posts to modules/pathfinder/npc/say"
    - "Pipe-separator parsing matches `:pf npc say <Name>[,<Name>...] | <party line>` per D-01; empty payload after pipe sends party_line=''"
    - "Comma-split with trim: `Varek , Baron ` → names=['Varek','Baron']"
    - "Missing pipe returns a usage string; post_to_module NOT called"
    - "Empty names list (e.g., `npc say | hi`) returns a usage string; post_to_module NOT called"
    - "Reply rendering: each NPC reply prefixed with `> ` (markdown quote); multiple replies stacked one per line"
    - "When response.warning is non-null, the warning string is prepended to the rendered output (with blank-line separator before quote blocks)"
    - "Unknown verb help text in _pf_dispatch INCLUDES `say` in the Available list (D-04)"
    - "Top-level usage line in _pf_dispatch lists `say` as a verb option"
    - "_extract_thread_history exists at module level: walks thread.history(limit=50, oldest_first=True), pair-matches user :pf npc say messages with bot replies, filters to turns where any current NPC was named (D-13)"
    - "_render_say_response exists at module level"
    - "All 8 bot-layer tests in test_subcommands.py go GREEN"
  tests:
    - "cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' -q  # → 8 passed"
    - "cd interfaces/discord && python -m pytest tests/ -q  # → all green (no Phase 26-30 regressions)"
---

<plan_objective>
Wire the dialogue engine into the Discord bot. Adds the `say` verb to `_pf_dispatch`, the `_extract_thread_history` walker for D-11..D-14, the `_render_say_response` formatter for D-03 (quote-block rendering + warning preamble), and updates the unknown-verb help text to include `say` (D-04). After this plan, all 8 bot-layer tests turn GREEN and the end-to-end DLG-01..03 contract is shippable.
</plan_objective>

<threat_model>
## STRIDE Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-31-05-T01 | Tampering | Crafted Discord message with embedded `:pf npc say ... \|` patterns leaking into other users' history | accept | Single-DM personal use; thread is per-conversation; bot only walks the current thread's messages. |
| T-31-05-T02 | Tampering | Untrusted Discord-message content reaching the LLM via thread history | mitigate (delegated) | History payload is sent to /npc/say which already enforces party_line ≤ 2000 chars; per-name validation happens server-side in NPCSayRequest validator (Plan 31-04). Bot itself does no LLM call. |
| T-31-05-D01 | DoS | Bot walking unbounded thread history | mitigate | Hardcoded `limit=50` on `thread.history()` call (RESEARCH.md Recommended Defaults). Single API call upper-bounds the walk. |
| T-31-05-I01 | Information Disclosure | Bot replying with another bot's messages mistaken as our reply | mitigate | Filter on `next_msg.author.id == bot_user_id`, not `message.author.bot` (Pitfall 3). |
| T-31-05-D02 | DoS | Discord message_content intent revoked → walker reads empty `.content` strings | accept (graceful degrade) | Walker returns `[]`; dialogue still works without memory. Open Question 3 in RESEARCH.md. |

**Block level:** none HIGH. T-31-05-T02, T-31-05-D01, T-31-05-I01 are MITIGATED. T-31-05-T01 and T-31-05-D02 accepted with rationale (single-DM scope; graceful degradation). ASVS L1 satisfied.
</threat_model>

<tasks>

<task id="31-05-01" type="execute" autonomous="true">
  <name>Task 31-05-01: Add module-level helpers _extract_thread_history + _render_say_response + regex constants to bot.py</name>
  <read_first>
    - interfaces/discord/bot.py (lines 1-100 for imports + module-level helpers; lines 175-225 for build_stat_embed pattern as the analog placement; lines 654-706 for on_message thread access)
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md §7 (Analog C, signature change recommendation, _SAY_PATTERN/_QUOTE_PATTERN constants)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 671-738 (verbatim helper implementations)
    - .planning/phases/31-dialogue-engine/31-CONTEXT.md decisions D-11, D-12, D-13 (history walk + filter rules)
  </read_first>
  <action>
EDIT `interfaces/discord/bot.py`:

**Step 1 — Add `re` import** if not already present. Check the imports section at the top of the file. If `import re` is missing, add it alphabetically among the stdlib imports.

**Step 2 — Add module-level regex constants** after the existing `_VALID_RELATIONS` constant (around line 181 per PATTERNS.md):

```python
# Phase 31: dialogue thread history walker patterns
_SAY_PATTERN = re.compile(r"^:pf\s+npc\s+say\s+(.+?)\s*\|(.*)$", re.IGNORECASE | re.DOTALL)
_QUOTE_PATTERN = re.compile(r"^>\s+(.+)$", re.MULTILINE)
```

**Step 3 — Add `_render_say_response` helper.** Place it adjacent to `build_stat_embed` (around lines 184-226 per PATTERNS.md) as a sibling module-level helper:

```python
def _render_say_response(result: dict) -> str:
    """Format /npc/say response as stacked quote blocks with optional warning preamble (D-03, D-18)."""
    replies = result.get("replies", []) or []
    warning = result.get("warning")
    lines: list[str] = []
    if warning:
        lines.append(warning)
        lines.append("")  # blank-line separator before quote blocks
    for r in replies:
        # The reply text from the LLM already includes action + spoken parts per system prompt:
        #   *{action}.* "{spoken}"
        # We just prefix with "> " for Discord quote markdown.
        lines.append(f"> {r.get('reply', '')}")
    return "\n".join(lines) if lines else "_(no reply generated)_"
```

**Step 4 — Add `_extract_thread_history` helper.** Place it after `_render_say_response`:

```python
async def _extract_thread_history(
    thread,
    current_npc_names: set,
    bot_user_id: int,
    limit: int = 50,
) -> list:
    """Walk thread oldest→newest; pair `:pf npc say ...` user messages with the bot's
    immediate quote-block reply. Filter to turns where ANY currently-named NPC was in the
    original name list (D-13).

    Returns list of {party_line: str, replies: [{npc, reply}, ...]} ready to send to /npc/say.

    `thread` is duck-typed as anything with an async `history(limit, oldest_first)` method
    (in production, discord.Thread). Tests pass FakeThread shapes.
    """
    msgs = [m async for m in thread.history(limit=limit, oldest_first=True)]
    turns: list = []
    normalized_current = {n.lower() for n in current_npc_names}
    i = 0
    while i < len(msgs) - 1:
        m = msgs[i]
        if m.author.bot or not getattr(m, "content", None):
            i += 1
            continue
        match = _SAY_PATTERN.match(m.content.strip())
        if not match:
            i += 1
            continue
        name_list = [n.strip() for n in match.group(1).split(",") if n.strip()]
        name_list_lower = {n.lower() for n in name_list}
        party_line = match.group(2).strip()
        if not (name_list_lower & normalized_current):
            i += 1  # D-13: skip turns where no current NPC participated
            continue
        next_msg = msgs[i + 1]
        # Pitfall 3: filter on this bot's id, not generic .author.bot
        if getattr(next_msg.author, "id", None) != bot_user_id:
            i += 1
            continue
        quote_lines = _QUOTE_PATTERN.findall(getattr(next_msg, "content", "") or "")
        if not quote_lines:
            i += 2
            continue
        # Zip names to quote lines by position (best-effort; scenes reply in command-line order)
        replies = [
            {"npc": name_list[idx] if idx < len(name_list) else "?", "reply": line}
            for idx, line in enumerate(quote_lines)
        ]
        turns.append({"party_line": party_line, "replies": replies})
        i += 2
    return turns
```

**Smoke test (without discord.py — exercises both helpers via duck-typing):**
```bash
cd interfaces/discord && python -c "
import asyncio
import bot

# _render_say_response
out = bot._render_say_response({'replies': [{'npc': 'V', 'reply': '*nods.* \"Aye.\"'}], 'warning': None})
assert out == '> *nods.* \"Aye.\"', repr(out)

out2 = bot._render_say_response({
    'replies': [{'npc': 'V', 'reply': 'r1'}, {'npc': 'B', 'reply': 'r2'}],
    'warning': '⚠ 5 NPCs in scene — consider splitting for clarity.',
})
assert out2.startswith('⚠'), out2
assert '> r1' in out2 and '> r2' in out2, out2

# _extract_thread_history
class _FakeAuthor:
    def __init__(self, bot_flag, id_):
        self.bot = bot_flag
        self.id = id_
class _FakeMsg:
    def __init__(self, content, author):
        self.content = content
        self.author = author
class _FakeThread:
    def __init__(self, msgs):
        self._msgs = msgs
    def history(self, *, limit=50, oldest_first=False):
        async def gen():
            for m in self._msgs:
                yield m
        return gen()

USER = _FakeAuthor(False, 1)
BOT = _FakeAuthor(True, 999)
msgs = [
    _FakeMsg(':pf npc say Varek | hi', USER),
    _FakeMsg('> *nods.* \"Aye.\"', BOT),
    _FakeMsg('random text', USER),
    _FakeMsg(':pf npc say Varek,Baron | hi2', USER),
    _FakeMsg('> *V says.* \"y\"\n> *B says.* \"n\"', BOT),
]
async def t():
    turns = await bot._extract_thread_history(_FakeThread(msgs), {'Varek'}, 999, limit=50)
    return turns
turns = asyncio.run(t())
assert len(turns) == 2, turns
assert turns[0]['party_line'] == 'hi'
assert turns[1]['party_line'] == 'hi2'
assert turns[1]['replies'][0]['npc'] == 'Varek'
assert turns[1]['replies'][1]['npc'] == 'Baron'

# Filter to non-overlapping name set returns 0 turns
turns2 = asyncio.run(bot._extract_thread_history(_FakeThread(msgs), {'Miralla'}, 999, limit=50))
assert turns2 == [], turns2
print('OK')
"
```
  </action>
  <acceptance_criteria>
    - grep -E '^_SAY_PATTERN = re\.compile' interfaces/discord/bot.py matches
    - grep -E '^_QUOTE_PATTERN = re\.compile' interfaces/discord/bot.py matches
    - grep -E '^def _render_say_response\(' interfaces/discord/bot.py matches
    - grep -E '^async def _extract_thread_history\(' interfaces/discord/bot.py matches
    - grep -F 'oldest_first=True' interfaces/discord/bot.py matches
    - grep -F 'bot_user_id' interfaces/discord/bot.py occurs ≥ 2 times (function signature + filter check)
    - Smoke test exits 0 with output `OK`
    - No regression: `cd interfaces/discord && python -m pytest tests/ -q -k "not say and not thread_history"` exit 0
  </acceptance_criteria>
  <automated>cd interfaces/discord && python -c "
import asyncio
import bot
out = bot._render_say_response({'replies': [{'npc': 'V', 'reply': 'foo'}], 'warning': None})
assert out == '> foo', out
out2 = bot._render_say_response({'replies': [{'npc': 'V', 'reply': 'r1'}, {'npc': 'B', 'reply': 'r2'}], 'warning': '⚠ 5 NPCs in scene — consider splitting for clarity.'})
assert out2.startswith('⚠') and '> r1' in out2 and '> r2' in out2
class A:
    def __init__(self, b, i): self.bot, self.id = b, i
class M:
    def __init__(self, c, a): self.content, self.author = c, a
class T:
    def __init__(self, m): self.m = m
    def history(self, *, limit=50, oldest_first=False):
        async def g():
            for x in self.m: yield x
        return g()
USER = A(False, 1); BOT = A(True, 999)
msgs = [M(':pf npc say Varek | hi', USER), M('> *nods.* \"Aye.\"', BOT)]
turns = asyncio.run(bot._extract_thread_history(T(msgs), {'Varek'}, 999, 50))
assert len(turns) == 1 and turns[0]['party_line'] == 'hi'
print('OK')
"</automated>
</task>

<task id="31-05-02" type="execute" autonomous="true">
  <name>Task 31-05-02: Add `say` verb branch to _pf_dispatch + extend _pf_dispatch signature with optional channel kwarg</name>
  <read_first>
    - interfaces/discord/bot.py (lines 229-473 for _pf_dispatch full body; lines 251-268 for create-verb pipe-parsing analog; lines 383-416 for token-image branch analog; lines 442-473 for the unknown-verb help text + error-handling stanza)
    - interfaces/discord/bot.py line 242 — exact current top-level usage line: `return "Usage: \`:pf npc <create|update|show|relate|import> ...\`"` (verbatim — Step 5 below replaces this)
    - interfaces/discord/bot.py line 450 — exact current Available: line: `"Available: \`create\`, \`update\`, \`show\`, \`relate\`, \`import\`, \`export\`, \`token\`, \`token-image\`, \`stat\`, \`pdf\`."` (verbatim — Step 4 below replaces this)
    - interfaces/discord/bot.py lines 479-501 — `_route_message(user_id, message, attachments=None)` signature + body (Step 2 channel propagation: add `channel` kwarg here and forward to `handle_sentask_subcommand`)
    - interfaces/discord/bot.py lines 504-510 — `handle_sentask_subcommand(subcmd, args, user_id, attachments=None)` + the `if subcmd == "pf": return await _pf_dispatch(args, user_id, attachments=attachments)` line (Step 2 channel propagation: add `channel` kwarg here and forward to `_pf_dispatch`)
    - interfaces/discord/bot.py — every call site of `_route_message(...)` (use `grep -n "_route_message(" interfaces/discord/bot.py` to enumerate; canonical caller is `on_message` and the `/sen` slash handler around line 713; both pass `message.channel` / `interaction.channel` as the new `channel` kwarg)
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md §7 (Analog A + B + signature-change recommendation + Gotchas 1-3)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 630-666 (full say-branch reference impl)
    - .planning/phases/31-dialogue-engine/31-CONTEXT.md decisions D-01 (syntax), D-02 (empty-payload scene-advance), D-03 (rendering), D-04 (help text), D-25 (bot owns Discord side)
  </read_first>
  <action>
EDIT `interfaces/discord/bot.py`:

**Step 1 — Extend `_pf_dispatch` signature** (around line 229) to accept an optional `channel` kwarg. The existing signature is something like `async def _pf_dispatch(args: str, user_id: str, attachments: list | None = None) -> str:`. Change it to:

```python
async def _pf_dispatch(args: str, user_id: str, attachments=None, channel=None) -> str:
```

(Backward-compatible — every existing call site that does not pass `channel` continues to work; tests stub `channel=None`.)

**Step 2 — Plumb `channel` through the 3-layer call chain.** The existing dispatch chain is `on_message`/`sen` → `_route_message` (line 479) → `handle_sentask_subcommand` (line 504) → `_pf_dispatch` (line 229). The channel reference (`message.channel` from `on_message` / `interaction.channel` from `sen`) must flow through all three layers as a backward-compatible optional kwarg. Apply the following surgical edits:

**(a) `_route_message` signature + forward (line 479-492):**
```python
# BEFORE:
async def _route_message(user_id: str, message: str, attachments: list | None = None) -> str:
    ...
    if message.startswith(":"):
        parts = message[1:].split(" ", 1)
        subcmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return await handle_sentask_subcommand(subcmd, args, user_id, attachments=attachments)

# AFTER:
async def _route_message(user_id: str, message: str, attachments: list | None = None, channel=None) -> str:
    ...
    if message.startswith(":"):
        parts = message[1:].split(" ", 1)
        subcmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return await handle_sentask_subcommand(subcmd, args, user_id, attachments=attachments, channel=channel)
```

**(b) `handle_sentask_subcommand` signature + forward (line 504-510):**
```python
# BEFORE:
async def handle_sentask_subcommand(subcmd: str, args: str, user_id: str, attachments: list | None = None) -> str:
    ...
    if subcmd == "pf":
        return await _pf_dispatch(args, user_id, attachments=attachments)

# AFTER:
async def handle_sentask_subcommand(subcmd: str, args: str, user_id: str, attachments: list | None = None, channel=None) -> str:
    ...
    if subcmd == "pf":
        return await _pf_dispatch(args, user_id, attachments=attachments, channel=channel)
```

**(c) Every `_route_message(...)` call site (enumerated via `grep -n "_route_message(" interfaces/discord/bot.py`):**
- In `on_message`: append `, channel=message.channel`
- In the `/sen` slash command handler (`async def sen(interaction, message)` around line 713): append `, channel=interaction.channel`

(Backward-compatible — every call site that omits `channel` continues to work; the kwarg defaults to `None` at every layer. Do NOT change any other semantics — channel is a pure pass-through. Tests stub `channel=None`.)

**Step 3 — Add the `say` branch.** Insert this branch into the verb dispatch chain in `_pf_dispatch` AFTER the existing `pdf` branch and BEFORE the unknown-verb fallback. The existing chain looks like `if verb == "create": ... elif verb == "update": ... elif verb == "show": ... elif verb == "relate": ... elif verb == "import": ... elif verb == "export": ... elif verb == "token": ... elif verb == "token-image": ... elif verb == "stat": ... elif verb == "pdf": ... else: <unknown verb>`. Insert AFTER `elif verb == "pdf"` block:

```python
elif verb == "say":
    # D-01..D-03: parse `<Name>[,<Name>...] | <party line>` (empty payload after pipe = SCENE ADVANCE).
    name_list_str, sep, payload = rest.partition("|")
    if not sep:
        return (
            "Usage: `:pf npc say <Name>[,<Name>...] | <party line>`\n"
            "Scene advance: `:pf npc say <N1>,<N2> |` (empty after pipe)"
        )
    names = [n.strip() for n in name_list_str.split(",") if n.strip()]
    if not names:
        return "Usage: `:pf npc say <Name>[,<Name>...] | <party line>`"
    party_line = payload.strip()  # "" signals SCENE ADVANCE per D-02

    # D-11..D-14: walk thread history when channel is a discord.Thread; otherwise empty history.
    history: list = []
    try:
        # Test stub (test_subcommands.py line 33-34) sets discord.Thread = object — isinstance check
        # returns False; channel will be None in unit tests. In production, channel is the live Thread.
        if channel is not None and isinstance(channel, discord.Thread):
            bot_user = bot.user
            if bot_user is not None:
                history = await _extract_thread_history(
                    thread=channel,
                    current_npc_names=set(names),
                    bot_user_id=bot_user.id,
                    limit=50,
                )
    except Exception as exc:
        logger.warning("Thread history walk failed (degrading to empty): %s", exc)
        history = []

    say_payload = {
        "names": names,
        "party_line": party_line,
        "history": history,
        "user_id": user_id,
    }
    result = await _sentinel_client.post_to_module(
        "modules/pathfinder/npc/say", say_payload, http_client
    )
    return _render_say_response(result)
```

**Step 4 — Update unknown-verb help text (line 450, verbatim).** The current text is exactly:
```python
            else:
                return (
                    f"Unknown npc command `{verb}`. "
                    "Available: `create`, `update`, `show`, `relate`, `import`, `export`, `token`, `token-image`, `stat`, `pdf`."
                )
```
Replace by appending `, \`say\`` to the inside-quotes verb list (preserve every existing verb — order matters, formatting matters):
```python
            else:
                return (
                    f"Unknown npc command `{verb}`. "
                    "Available: `create`, `update`, `show`, `relate`, `import`, `export`, `token`, `token-image`, `stat`, `pdf`, `say`."
                )
```

**Step 5 — Update top-level usage line (line 242, verbatim).** The current text is exactly:
```python
    if len(parts) < 2:
        return "Usage: `:pf npc <create|update|show|relate|import> ...`"
```
Replace by appending `|say` after `import` (do not invent additional verbs into this line — it is intentionally short):
```python
    if len(parts) < 2:
        return "Usage: `:pf npc <create|update|show|relate|import|say> ...`"
```

**Step 6 — Verify all 8 bot-layer tests pass:**
```bash
cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' -v
# Expected: 8 passed
```

**Verify no regressions in existing tests:**
```bash
cd interfaces/discord && python -m pytest tests/ -q
# Expected: all tests green
```
  </action>
  <acceptance_criteria>
    - grep -F 'elif verb == "say":' interfaces/discord/bot.py matches
    - grep -F 'modules/pathfinder/npc/say' interfaces/discord/bot.py matches
    - grep -F '_render_say_response' interfaces/discord/bot.py occurs ≥ 2 times (definition in Task 31-05-01 + usage here)
    - grep -F '_extract_thread_history' interfaces/discord/bot.py occurs ≥ 2 times (definition + usage)
    - grep -F 'channel=None' interfaces/discord/bot.py matches (signature change)
    - grep -F 'rest.partition("|")' interfaces/discord/bot.py occurs ≥ 2 times (existing create + new say branch)
    - grep -E "Available:.*\`say\`" interfaces/discord/bot.py matches (D-04 — help text includes say)
    - grep -F "Available: \`create\`, \`update\`, \`show\`, \`relate\`, \`import\`, \`export\`, \`token\`, \`token-image\`, \`stat\`, \`pdf\`, \`say\`." interfaces/discord/bot.py matches (full Available list intact + say appended — guards against accidental truncation)
    - grep -F 'Usage: `:pf npc <create|update|show|relate|import|say> ...`' interfaces/discord/bot.py matches (top-level usage updated; no other verb invented)
    - All 8 bot tests pass: `cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' -q` exit 0
    - No regression: `cd interfaces/discord && python -m pytest tests/ -q` exit code 0
    - grep -vE '^\s*#' interfaces/discord/bot.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' returns 0 NEW matches in lines added by this task (existing pre-Phase-31 markers, if any, are out of scope)
  </acceptance_criteria>
  <automated>cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' -q && python -m pytest tests/ -q</automated>
</task>

</tasks>

<verification>
End-of-Phase-31 gate (after this plan completes the bot wiring):

```bash
# 1. Bot tests all green (8 new + existing)
cd interfaces/discord && python -m pytest tests/ -q
# Expected: all green

# 2. Module tests still green
cd modules/pathfinder && python -m pytest tests/ -q
# Expected: all green (16 new npc_say + 2 integration + Phase 29/30 unbroken)

# 3. Full Phase 31 contract verification
cd modules/pathfinder && python -m pytest tests/test_npc.py -k npc_say -v
# Expected: 16 passed
cd modules/pathfinder && python -m pytest tests/test_npc_say_integration.py -v
# Expected: 2 passed
cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' -v
# Expected: 8 passed

# 4. Help text + usage line include `say`
grep -E "Available:.*\`say\`" interfaces/discord/bot.py && echo "PASS — help text" || echo "FAIL"
grep -E "Usage: \`:pf npc.*\|say" interfaces/discord/bot.py && echo "PASS — usage line" || echo "FAIL"

# 5. Mood write path uses GET-then-PUT (D-09); no PATCH for mood
grep -B 2 -A 8 'async def say_npc' modules/pathfinder/app/routes/npc.py | grep -F 'patch_frontmatter_field' && echo "FAIL" || echo "PASS"

# 6. REGISTRATION_PAYLOAD has 12 routes
cd modules/pathfinder && python -c "from app.main import REGISTRATION_PAYLOAD; print('routes:', len(REGISTRATION_PAYLOAD['routes']))"
# Expected: routes: 12

# 7. Manual smoke test checklist (from 31-VALIDATION.md Manual-Only):
#    Run sentinel.sh up, send each of these in a Sentinel-managed Discord thread:
#      :pf npc say <known NPC> | <question matching their backstory>
#      Hostile-shift: insult NPC; verify :pf npc show reports moved-down mood
#      Scene with two distinct-personality NPCs; verify replies feel distinct
#      Scene advance: send `:pf npc say A,B |` after prior scene; verify continuation
```

After all 7 gates pass, mark `wave_0_complete: true` in 31-VALIDATION.md (already done in Plan 31-01 verification) AND mark Phase 31 ready for `/gsd-verify-work`.
</verification>

<success_criteria>
- All 8 bot-layer tests pass.
- All 16 module-layer tests + 2 integration tests still pass.
- Existing Discord tests not regressed.
- `say` verb is dispatchable from `:pf npc say` in Discord.
- Help text and usage line both include `say`.
- Thread history walker pairs user-say with bot-reply correctly and filters per D-13.
- Quote-block rendering matches D-03; warning preamble appears for ≥5-NPC scenes.
- DLG-01, DLG-02, DLG-03 satisfied end-to-end (HTTP + Discord).
- AI Deferral Ban: zero TODO/FIXME/NotImplementedError introduced in bot.py changes.
</success_criteria>

<output>
Create `.planning/phases/31-dialogue-engine/31-31-05-SUMMARY.md` documenting:
- Files modified: interfaces/discord/bot.py — added _SAY_PATTERN/_QUOTE_PATTERN constants, _render_say_response helper, _extract_thread_history helper, say verb branch, signature change to _pf_dispatch, updated help+usage text
- Test results: 8 bot tests + 16 module tests + 2 integration tests all green
- Documented deferred items (carried forward from CONTEXT Deferred Ideas): cross-session memory (Phase 34); tool-augmented dialogue (Phase 33); Foundry VTT dialogue ingest (Phase 35); voice I/O; mood-change visibility flag (--verbose); inter-NPC party-name addressing
- Documented limitation (RESEARCH Finding 6): rapid-fire mood race condition — accepted, single-DM low-impact
- Documented limitation (RESEARCH Open Q3): if message_content intent is revoked, history walker degrades to empty (dialogue still works, no memory)
- Manual smoke test checklist (4 items per 31-VALIDATION.md Manual-Only Verifications) — for human to run after deployment.
- Note: Phase 31 ready for `/gsd-verify-work`. Run `/gsd-verify-work 31` next.
</output>
