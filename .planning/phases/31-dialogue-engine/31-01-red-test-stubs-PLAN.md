---
plan_id: 31-01
phase: 31
wave: 0
depends_on: []
files_modified:
  - modules/pathfinder/tests/test_npc.py
  - modules/pathfinder/tests/test_npc_say_integration.py
  - interfaces/discord/tests/test_subcommands.py
autonomous: true
requirements: [DLG-01, DLG-02, DLG-03]
must_haves:
  truths:
    - "16 test_npc_say_* stubs collected in modules/pathfinder/tests/test_npc.py"
    - "2 integration test stubs collected in modules/pathfinder/tests/test_npc_say_integration.py"
    - "8 test_pf_say_* / test_pf_unknown_verb_help_includes_say / test_thread_history_* stubs collected in interfaces/discord/tests/test_subcommands.py"
    - "All 26 stubs collect cleanly (no ImportError) and FAIL on run (RED — implementation not yet present)"
  tests:
    - "pytest modules/pathfinder/tests/test_npc.py -k npc_say --collect-only -q  # → 16 collected"
    - "pytest modules/pathfinder/tests/test_npc_say_integration.py --collect-only -q  # → 2 collected"
    - "pytest interfaces/discord/tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' --collect-only -q  # → 8 collected"
    - "pytest modules/pathfinder/tests/test_npc.py -k npc_say -q  # → 16 RED (failures, not errors)"
---

<plan_objective>
Wave 0 RED scaffolding for Phase 31. Create the 26 test stubs (16 module unit + 2 integration + 8 bot unit) enumerated in 31-VALIDATION.md so that downstream waves implement against an explicit test contract. Stubs MUST fail (not error on collection) — they reference symbols that will land in Wave 1+ and are import-protected so collection succeeds.
</plan_objective>

<threat_model>
## STRIDE Register (Wave 0 — test scaffolding only)

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-31-01-S01 | Spoofing | test fixtures using fake bot_user_id | accept | Test-only; fixtures never touch production auth path |
| T-31-01-T01 | Tampering | test fixtures referencing canned-LLM strings that may include prompt-injection-shaped content | accept | Strings are inert in test context (canned, not LLM-evaluated). Documents the shape Wave 1 must defend against. |

**Block level:** none — Wave 0 ships test scaffolding only; production code lands in Wave 1+. ASVS L1 enforcement begins at Plan 31-03 (LLM helper) and Plan 31-04 (route handler).

**Threats this scaffolding ANTICIPATES (not introduces):**
- T-31-SEC-01 (path traversal via name) — covered by `test_npc_say_unknown` and `test_npc_say_invalid_name_control_char`
- T-31-SEC-02 (mood poisoning) — covered by `test_npc_say_invalid_mood_frontmatter_normalized`
- T-31-SEC-03 (prompt injection via party_line) — covered by `test_npc_say_json_parse_salvage` (graceful degrade)
- T-31-SEC-04 (token-budget DoS) — covered by `test_npc_say_party_line_too_long_422`
</threat_model>

<tasks>

<task id="31-01-01" type="execute" autonomous="true">
  <name>Task 31-01-01: Append 16 test_npc_say_* stubs to modules/pathfinder/tests/test_npc.py</name>
  <read_first>
    - modules/pathfinder/tests/test_npc.py (full file — lines 1-83 for env-bootstrap pattern; lines 261-276 for NOTE constant pattern; lines 333-345 for happy-path test analog; lines 445-485 for full round-trip pattern)
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md §6 (table of 16 tests + analog blocks)
    - .planning/phases/31-dialogue-engine/31-VALIDATION.md (Module-layer tests table for exact test names)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 489-505 (test setup + asserts)
  </read_first>
  <action>
APPEND (do NOT rewrite the file) 16 test stubs to modules/pathfinder/tests/test_npc.py. Each stub is `async def test_npc_say_<name>():` and either calls `await client.post("/npc/say", json=...)` against the mocked ASGI app, or imports the (not-yet-existing) symbols from `app.dialogue` / `app.llm`.

**Import-protection rule (so collection succeeds despite missing modules):**
At the top of the new test block (after the existing imports), add:
```python
# Wave 0 RED scaffolding — implementation lands in Wave 1
# Stubs reference app.dialogue and app.llm.generate_npc_reply which do not yet exist.
# Tests are expected to FAIL on run (RED), but MUST collect cleanly.
```
Do NOT use `try/except ImportError` to skip — tests must run and FAIL so the RED→GREEN signal is honest.

**New module-scope NOTE constants** (place after existing `NOTE_NO_STATS` constant near line 276):
```python
NOTE_VAREK_NEUTRAL = (
    "---\n"
    "name: Varek\nlevel: 1\nancestry: Gnome\nclass: Rogue\n"
    "traits:\n- sneaky\npersonality: Nervous and twitchy.\n"
    "backstory: Fled the thieves' guild after stealing a ledger.\n"
    "mood: neutral\nrelationships: []\nimported_from: null\n"
    "---\n"
)
NOTE_VAREK_HOSTILE = NOTE_VAREK_NEUTRAL.replace("mood: neutral", "mood: hostile")
NOTE_VAREK_WARY = NOTE_VAREK_NEUTRAL.replace("mood: neutral", "mood: wary")
NOTE_VAREK_ALLIED = NOTE_VAREK_NEUTRAL.replace("mood: neutral", "mood: allied")
NOTE_VAREK_INVALID_MOOD = NOTE_VAREK_NEUTRAL.replace("mood: neutral", "mood: grumpy")
NOTE_BARON_HOSTILE = (
    "---\n"
    "name: Baron Aldric\nlevel: 5\nancestry: Human\nclass: Fighter\n"
    "traits:\n- arrogant\npersonality: Cold and calculating.\n"
    "backstory: A noble who seized the keep through betrayal.\n"
    "mood: hostile\nrelationships: []\nimported_from: null\n"
    "---\n"
)
NOTE_VAREK_FEARS_BARON = NOTE_VAREK_NEUTRAL.replace(
    "relationships: []",
    "relationships:\n- target: Baron Aldric\n  relation: fears",
)
```

**The 16 tests** — implement EXACTLY these names (matches 31-VALIDATION.md verbatim):

1. `test_npc_say_solo_happy` — DLG-01. mock get_note → NOTE_VAREK_NEUTRAL; patch `app.routes.npc.generate_npc_reply` → AsyncMock(return_value={"reply": "*nods.* \"Aye.\"", "mood_delta": 0}); POST `/npc/say` `{"names": ["Varek"], "party_line": "hello", "history": [], "user_id": "u1"}`. Assert 200, `replies[0]["npc"] == "Varek"`, `replies[0]["new_mood"] == "neutral"`, `mock_obs.put_note.await_count == 0`, `result["warning"] is None`.

2. `test_npc_say_unknown` — DLG-01. mock get_note → None. POST same shape with name "Ghost". Assert 404, response JSON detail contains slug="ghost" and name="Ghost".

3. `test_npc_say_system_prompt_has_personality` — DLG-01. Spy on `generate_npc_reply` (capture call args). Assert `mock_gen.call_args.kwargs["system_prompt"]` (or positional) contains "Nervous and twitchy" (substring of NOTE_VAREK_NEUTRAL personality).

4. `test_npc_say_mood_increment` — DLG-02. mood:neutral, LLM returns mood_delta=+1. Assert put_note called once; the second positional arg (content) contains the substring `mood: friendly`. Assert `replies[0]["new_mood"] == "friendly"`.

5. `test_npc_say_mood_decrement` — DLG-02. NOTE_VAREK_WARY, LLM returns mood_delta=-1. Assert put_note content contains `mood: hostile`; `new_mood == "hostile"`.

6. `test_npc_say_mood_zero_no_write` — DLG-02. LLM returns mood_delta=0. Assert `mock_obs.put_note.await_count == 0`; `new_mood == "neutral"`.

7. `test_npc_say_mood_clamp_hostile` — DLG-02. NOTE_VAREK_HOSTILE, mood_delta=-1. Assert put_note NOT called; `new_mood == "hostile"`.

8. `test_npc_say_mood_clamp_allied` — DLG-02. NOTE_VAREK_ALLIED, mood_delta=+1. Assert put_note NOT called; `new_mood == "allied"`.

9. `test_npc_say_invalid_mood_normalized` — DLG-02 (T-31-SEC-02). NOTE_VAREK_INVALID_MOOD, mood_delta=+1. Use `caplog` fixture, assert at WARNING level "invalid" or "treating as 'neutral'" appears, and `new_mood == "friendly"` (neutral + 1).

10. `test_npc_say_scene_order` — DLG-03. Two NPCs [Varek, Baron]. `mock_obs.get_note = AsyncMock(side_effect=[NOTE_VAREK_NEUTRAL, NOTE_BARON_HOSTILE])`. Patch generate_npc_reply with `side_effect=[{"reply": "V says", "mood_delta": 0}, {"reply": "B says", "mood_delta": 0}]`. Assert `replies[0]["npc"] == "Varek"` and `replies[1]["npc"] == "Baron Aldric"`.

11. `test_npc_say_scene_context_awareness` — DLG-03. Same setup as above; capture all `generate_npc_reply` call args via `mock_gen.call_args_list`. Assert second call's user_prompt contains the substring `"V says"` (Varek's reply visible to Baron).

12. `test_npc_say_scene_advance` — DLG-03. POST with `party_line=""`, names=[Varek, Baron]. Capture user_prompt of first call. Assert it contains the substring `"silent"` AND `"Continue the scene"`.

13. `test_npc_say_five_npc_warning` — DLG-03. names=[A,B,C,D,E] (use 5 distinct NOTE constants — reuse NOTE_VAREK_NEUTRAL by patching get_note via side_effect of 5 copies with different names embedded; or build a small helper that returns NOTE_VAREK_NEUTRAL.replace("name: Varek", f"name: {n}")). Assert `result["warning"] == "⚠ 5 NPCs in scene — consider splitting for clarity."` (exact string per CONTEXT.md D-18).

14. `test_npc_say_scene_missing_fails_fast` — DLG-03 (D-29). names=[Varek, Ghost], get_note side_effect=[NOTE_VAREK_NEUTRAL, None]. Patch generate_npc_reply but assert `mock_gen.await_count == 0` (no LLM call before 404). Assert 404, detail name=="Ghost".

15. `test_npc_say_json_parse_salvage` — DLG-01 (T-31-SEC-03). Don't patch `generate_npc_reply` — instead patch lower-level `app.llm.litellm.acompletion` to return a SimpleNamespace mocking `response.choices[0].message.content = "this is plain prose, no JSON at all"`. POST `/npc/say` `{"names":["Varek"], ...}`. Assert 200, `replies[0]["reply"]` is non-empty (salvaged prose), `replies[0]["mood_delta"] == 0`. NOTE: requires importing the real `generate_npc_reply` flow. If `app.llm.generate_npc_reply` not yet present, this stub will fail with ImportError which is acceptable RED behavior — Wave 1 lands the symbol.

16. `test_npc_say_party_line_too_long` — DLG-01 (T-31-SEC-04). POST with `party_line = "x" * 2001`. Assert 422 (Pydantic validation error). NO mocks needed beyond the standard register/obsidian patches.

**Scaffolding contract:**
- Use `mock_obs = MagicMock(); mock_obs.get_note = AsyncMock(...); mock_obs.put_note = AsyncMock(return_value=None)` per Patterns S6.
- Always patch `app.main._register_with_retry` AND `app.routes.npc.obsidian` inside the same `with` block; `from app.main import app` MUST be inside that `with` block.
- For LLM mocks, target `app.routes.npc.generate_npc_reply` (the import the route uses), not `app.llm.generate_npc_reply` (the source).
- Use `AsyncMock(side_effect=[...])` for multiple sequential calls (per analog `test_npc_import_collision_skipped` line 243).

DO NOT add any production code. DO NOT skip stubs because a symbol doesn't exist — write the stub assuming Wave 1 will land the symbol.
  </action>
  <acceptance_criteria>
    - `grep -c '^async def test_npc_say_' modules/pathfinder/tests/test_npc.py` → exactly 16
    - `pytest modules/pathfinder/tests/test_npc.py -k npc_say --collect-only -q` → "16 tests collected" (no errors during collection)
    - `pytest modules/pathfinder/tests/test_npc.py -k npc_say -q` → exit code != 0 (RED — failures expected)
    - `grep -c '^NOTE_VAREK_NEUTRAL = ' modules/pathfinder/tests/test_npc.py` → 1
    - `grep -c '^NOTE_VAREK_HOSTILE = ' modules/pathfinder/tests/test_npc.py` → 1
    - `grep -c '^NOTE_VAREK_WARY = ' modules/pathfinder/tests/test_npc.py` → 1
    - `grep -c '^NOTE_VAREK_ALLIED = ' modules/pathfinder/tests/test_npc.py` → 1
    - `grep -c '^NOTE_VAREK_INVALID_MOOD = ' modules/pathfinder/tests/test_npc.py` → 1
    - `grep -c '^NOTE_BARON_HOSTILE = ' modules/pathfinder/tests/test_npc.py` → 1
    - `grep -F '⚠ 5 NPCs in scene — consider splitting for clarity.' modules/pathfinder/tests/test_npc.py` returns 1+ matches (test 13 references the exact warning string)
    - File still ends with newline; existing tests in file unchanged (`grep -c '^async def test_' modules/pathfinder/tests/test_npc.py` increased by exactly 16)
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -m pytest tests/test_npc.py -k npc_say --collect-only -q</automated>
</task>

<task id="31-01-02" type="execute" autonomous="true">
  <name>Task 31-01-02: Create modules/pathfinder/tests/test_npc_say_integration.py with 2 scenario stubs</name>
  <read_first>
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md §2 (env-bootstrap + integration test skeleton)
    - .planning/phases/31-dialogue-engine/31-VALIDATION.md (Integration tests section)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 1142-1165 (Scenario specifications)
    - modules/pathfinder/tests/test_npc.py lines 1-12 (env-bootstrap to copy verbatim)
  </read_first>
  <action>
CREATE the new file `modules/pathfinder/tests/test_npc_say_integration.py`.

**Top of file** — verbatim env-bootstrap from test_npc.py lines 1-12 (per Patterns §2):
```python
"""Integration tests for /npc/say — full vault round-trip with canned LLM (DLG-01..03, SC-1..4)."""
import os

os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")
os.environ.setdefault("LITELLM_MODEL", "openai/local-model")
os.environ.setdefault("LITELLM_API_BASE", "http://localhost:1234/v1")

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
```

**Module-level NOTE constants** — copy from Task 31-01-01 (NOTE_VAREK_NEUTRAL, NOTE_BARON_HOSTILE) verbatim, OR add a `from .test_npc import NOTE_VAREK_NEUTRAL, NOTE_BARON_HOSTILE` import (PATTERNS.md §2 says copy the literal — choose copy for test isolation).

**Stateful mock vault helper** — required for round-trip:
```python
class StatefulMockVault:
    """In-memory vault: get_note returns last put_note content per path."""

    def __init__(self, initial: dict[str, str]):
        self._store: dict[str, str] = dict(initial)
        self.get_note = AsyncMock(side_effect=self._get)
        self.put_note = AsyncMock(side_effect=self._put)

    async def _get(self, path: str) -> str | None:
        return self._store.get(path)

    async def _put(self, path: str, content: str) -> None:
        self._store[path] = content
```

**Test 1: `test_solo_mood_roundtrip_through_vault`** — covers SC-1, SC-2, SC-3 (DLG-01, DLG-02).
Steps per RESEARCH.md lines 1148-1157:
1. Build StatefulMockVault with `{"mnemosyne/pf2e/npcs/varek.md": NOTE_VAREK_NEUTRAL}`.
2. Build a scripted `generate_npc_reply` AsyncMock with `side_effect=[{"reply": "*scowls.* \"You'll regret that.\"", "mood_delta": -1}, {"reply": "*pauses.* \"...maybe I was wrong.\"", "mood_delta": +1}]`.
3. With both patches active (`app.main._register_with_retry`, `app.routes.npc.obsidian`, `app.routes.npc.generate_npc_reply`), POST `/npc/say` with names=["Varek"], party_line="Why did you take the coin?", history=[].
4. Assert call 1: 200, `replies[0]["new_mood"] == "wary"`, `vault._store["mnemosyne/pf2e/npcs/varek.md"]` now contains `mood: wary`.
5. POST again with names=["Varek"], party_line="I'm sorry, please trust us.", history=[{"party_line":"Why did you take the coin?", "replies":[{"npc":"Varek","reply":"*scowls.* \"You'll regret that.\""}]}].
6. Capture the second call's system_prompt (via `mock_gen.call_args_list[1].kwargs["system_prompt"]` or positional). Assert it contains "WARY" (the tone-guidance keyword for wary mood — uppercase per Finding 5 wording).
7. Assert call 2: 200, `replies[0]["new_mood"] == "neutral"`, vault now contains `mood: neutral`.

**Test 2: `test_scene_distinct_voices_and_awareness`** — covers SC-4 (DLG-03).
Steps per RESEARCH.md lines 1160-1164:
1. StatefulMockVault with both NOTE_VAREK_NEUTRAL (mood neutral) and NOTE_BARON_HOSTILE (mood hostile).
2. Scripted generate_npc_reply: `side_effect=[{"reply": "*shrinks.* \"P-please...\"", "mood_delta": 0}, {"reply": "*sneers.* \"He's lying.\"", "mood_delta": 0}]`.
3. POST with names=["Varek", "Baron Aldric"], party_line="We mean no harm.", history=[].
4. Assert `replies[0]["npc"] == "Varek"` and `replies[1]["npc"] == "Baron Aldric"` (order preserved).
5. Capture both call args. Assert call[0].system_prompt contains "NEUTRAL" tone-guidance keyword (Varek's mood) AND call[1].system_prompt contains "HOSTILE" tone-guidance keyword (Baron's mood). This proves distinct system prompts per NPC.
6. Assert call[1].user_prompt contains the substring `"P-please"` (from Varek's reply text — proves in-turn awareness).

**Mock pattern** — wrap each test in:
```python
async def test_solo_mood_roundtrip_through_vault():
    vault = StatefulMockVault({"mnemosyne/pf2e/npcs/varek.md": NOTE_VAREK_NEUTRAL})
    mock_gen = AsyncMock(side_effect=[...])
    with patch("app.main._register_with_retry", new=AsyncMock(return_value=None)), \
         patch("app.routes.npc.obsidian", vault), \
         patch("app.routes.npc.generate_npc_reply", new=mock_gen):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp1 = await client.post("/npc/say", json={...})
            ...
```

Both tests are async (no `@pytest.mark.asyncio` decoration — pyproject.toml has `asyncio_mode = "auto"` per Patterns §2 Gotcha).
  </action>
  <acceptance_criteria>
    - `test -f modules/pathfinder/tests/test_npc_say_integration.py` exits 0
    - `grep -c '^async def test_' modules/pathfinder/tests/test_npc_say_integration.py` → exactly 2
    - `grep -F 'test_solo_mood_roundtrip_through_vault' modules/pathfinder/tests/test_npc_say_integration.py` matches
    - `grep -F 'test_scene_distinct_voices_and_awareness' modules/pathfinder/tests/test_npc_say_integration.py` matches
    - `grep -c 'class StatefulMockVault' modules/pathfinder/tests/test_npc_say_integration.py` → 1
    - `pytest modules/pathfinder/tests/test_npc_say_integration.py --collect-only -q` → "2 tests collected" (collection succeeds)
    - `pytest modules/pathfinder/tests/test_npc_say_integration.py -q` → exit code != 0 (RED expected)
    - File begins with the env-bootstrap stanza identical to test_npc.py lines 3-9 (verify with `head -10 modules/pathfinder/tests/test_npc_say_integration.py | grep -c "os.environ.setdefault"` → 6)
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -m pytest tests/test_npc_say_integration.py --collect-only -q</automated>
</task>

<task id="31-01-03" type="execute" autonomous="true">
  <name>Task 31-01-03: Append 8 test_pf_say_* / test_thread_history_* / test_pf_unknown_verb_help_includes_say stubs to interfaces/discord/tests/test_subcommands.py</name>
  <read_first>
    - interfaces/discord/tests/test_subcommands.py (full file — lines 13-50 for discord stub pattern; lines 206-225 for `test_pf_dispatch_create` analog)
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md §8 (table of 8 tests)
    - .planning/phases/31-dialogue-engine/31-VALIDATION.md (Bot-layer tests section)
  </read_first>
  <action>
APPEND 8 test stubs to interfaces/discord/tests/test_subcommands.py. Patch target for ALL bot-side LLM dispatch tests is `bot._sentinel_client.post_to_module` (per Patterns §8 Gotcha 2: module-level client instantiated at import).

**The 8 tests** (names match 31-VALIDATION.md verbatim):

1. `test_pf_say_solo_dispatch` — DLG-01.
   ```python
   async def test_pf_say_solo_dispatch():
       mock_result = {"replies": [{"npc": "Varek", "reply": "> *nods.* \"Aye.\"", "mood_delta": 0, "new_mood": "neutral"}], "warning": None}
       with patch.object(bot._sentinel_client, "post_to_module", new=AsyncMock(return_value=mock_result)) as mock_ptm:
           result = await bot._pf_dispatch("npc say Varek | hello there", "user123")
       mock_ptm.assert_called_once()
       assert mock_ptm.call_args[0][0] == "modules/pathfinder/npc/say"
       payload = mock_ptm.call_args[0][1]
       assert payload["names"] == ["Varek"]
       assert payload["party_line"] == "hello there"
       assert payload["user_id"] == "user123"
       assert payload["history"] == []  # no channel passed → empty history
   ```

2. `test_pf_say_scene_dispatch` — DLG-03.
   Input: `"npc say Varek,Baron | what do you want?"`. Assert `payload["names"] == ["Varek", "Baron"]`, `payload["party_line"] == "what do you want?"`.

3. `test_pf_say_scene_advance_dispatch` — DLG-03 (D-02). Input: `"npc say Varek,Baron |"`. Assert `payload["party_line"] == ""` AND post_to_module IS called (empty payload is valid scene-advance, NOT a usage error).

4. `test_pf_unknown_verb_help_includes_say` — DLG-01 (D-04). Input: `"npc bogus"`. No post_to_module patch needed (it should not be called). Assert returned string contains the substring `"say"` AND contains `"Available:"`.

5. `test_pf_say_render_two_quote_blocks` — DLG-03.
   ```python
   mock_result = {
       "replies": [
           {"npc": "Varek", "reply": "*shrinks.* \"P-please...\"", "mood_delta": 0, "new_mood": "neutral"},
           {"npc": "Baron", "reply": "*sneers.* \"He's lying.\"", "mood_delta": 0, "new_mood": "hostile"},
       ],
       "warning": None,
   }
   ```
   Assert `result.count("> ") == 2` AND `"shrinks" in result` AND `"sneers" in result`.

6. `test_pf_say_render_warning_preamble` — DLG-03 (D-18). mock_result with `"warning": "⚠ 5 NPCs in scene — consider splitting for clarity."` and 5 replies. Assert `result.startswith("⚠")` AND `"5 NPCs" in result` AND `result.count("> ") == 5`.

7. `test_thread_history_pairing` — DLG-01/03 (D-11). This tests `_extract_thread_history()`, the new bot helper.
   - Build a list of fake messages using SimpleNamespace or MagicMock with `.author.id`, `.author.bot`, `.content` attributes.
   - `bot_id = 999`. Messages: [user_msg(":pf npc say Varek | hi", author_bot=False), bot_msg("> *nods.* \"Aye.\"", author_id=999), user_msg("random other text", author_bot=False), user_msg(":pf npc say Varek | hi again", author_bot=False), bot_msg("> *grunts.* \"Mm.\"", author_id=999)].
   - Build a fake thread:
     ```python
     class _FakeThread:
         def __init__(self, msgs):
             self._msgs = msgs
         def history(self, *, limit=50, oldest_first=False):
             async def _gen():
                 for m in self._msgs:
                     yield m
             return _gen()
     ```
   - Call `await bot._extract_thread_history(thread=fake, current_npc_names={"Varek"}, bot_user_id=999, limit=50)`.
   - Assert returns 2 turns; each turn has `party_line` and `replies`. The "random other text" message is excluded (no `:pf npc say` pattern).
   - This stub will fail with `AttributeError: module 'bot' has no attribute '_extract_thread_history'` until Wave 3 lands the helper — RED is acceptable.

8. `test_thread_history_filter_scene` — DLG-03 (D-13). Same fake-thread pattern. 3 turns: turn1=[Varek solo], turn2=[Baron solo], turn3=[Varek,Baron]. Pass `current_npc_names={"Varek", "Baron"}`. Assert all 3 turns kept (each had at least one currently-named NPC). Then call again with `current_npc_names={"Miralla"}`. Assert 0 turns (no overlap).

**Stub contract (Patterns §8 Gotcha 1):** `discord.Thread` is stubbed at module-import time as `object` (test_subcommands.py lines 33-34). For tests 1-6, do NOT pass a `channel=` kwarg — the dispatch path defaults to no history. For tests 7-8, build the FakeThread inline; do NOT rely on `isinstance(channel, discord.Thread)` returning True (the stub makes it False). The `_extract_thread_history` helper itself MUST work without the isinstance check (it accepts any duck-typed object with `.history()`).

DO NOT add any production code to bot.py. Tests reference `bot._extract_thread_history` and the new "say" verb dispatch which Wave 3 will land — failures expected.
  </action>
  <acceptance_criteria>
    - `grep -c '^async def test_pf_say_' interfaces/discord/tests/test_subcommands.py` → exactly 5 (solo, scene, scene_advance, render_two, render_warning) [the other 3 are test_pf_unknown_verb_help_includes_say and 2× test_thread_history_*]
    - `grep -c '^async def test_thread_history_' interfaces/discord/tests/test_subcommands.py` → exactly 2
    - `grep -c '^async def test_pf_unknown_verb_help_includes_say' interfaces/discord/tests/test_subcommands.py` → exactly 1
    - Total new test functions: 8 (verify: test count delta vs pre-task)
    - `pytest interfaces/discord/tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' --collect-only -q` → "8 tests collected"
    - `pytest interfaces/discord/tests/test_subcommands.py -k 'say or thread_history' -q` → exit code != 0 (RED expected)
    - Existing tests in file unchanged: `grep -c '^async def test_pf_dispatch_create' interfaces/discord/tests/test_subcommands.py` → 1 (unchanged)
  </acceptance_criteria>
  <automated>cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' --collect-only -q</automated>
</task>

</tasks>

<verification>
Run the three collect-only commands and confirm 16 + 2 + 8 = 26 stubs collected:

```bash
cd modules/pathfinder && python -m pytest tests/test_npc.py -k npc_say --collect-only -q
# Expected: "16 tests collected"

cd modules/pathfinder && python -m pytest tests/test_npc_say_integration.py --collect-only -q
# Expected: "2 tests collected"

cd interfaces/discord && python -m pytest tests/test_subcommands.py -k 'say or thread_history or unknown_verb_help_includes_say' --collect-only -q
# Expected: "8 tests collected"
```

RED proof — run each suite and confirm failures (NOT collection errors):
```bash
cd modules/pathfinder && python -m pytest tests/test_npc.py -k npc_say -q
# Expected: 16 failed, 0 errors during collection. Exit code != 0.
```

After execution, mark `wave_0_complete: true` in 31-VALIDATION.md frontmatter (executor responsibility).
</verification>

<success_criteria>
- 16 + 2 + 8 = 26 RED test stubs exist and collect cleanly across the 3 test files.
- Stubs reference symbols (`app.dialogue.normalize_mood`, `app.llm.generate_npc_reply`, `bot._extract_thread_history`, etc.) that Waves 1-3 will land.
- No production code modified in this plan.
- Each test has a clear assertion target — no `pass` stubs, no `assert True`.
- All 5 NOTE_* constants present in test_npc.py for use by Wave 1+ implementations.
</success_criteria>

<output>
Create `.planning/phases/31-dialogue-engine/31-31-01-SUMMARY.md` documenting:
- Test file paths + test count per file (16 / 2 / 8)
- Verification commands run + their output
- Confirmation that all 26 tests are RED (failing for the expected reason: missing implementation symbols)
- Note: Wave 0 complete; Waves 1-3 implement against this contract.
</output>
