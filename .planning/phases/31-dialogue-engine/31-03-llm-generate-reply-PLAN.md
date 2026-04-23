---
plan_id: 31-03
phase: 31
wave: 1
depends_on: [31-01]
files_modified:
  - modules/pathfinder/app/llm.py
autonomous: true
requirements: [DLG-01, DLG-02]
must_haves:
  truths:
    - "generate_npc_reply(system_prompt, user_prompt, model, api_base) is an async function in modules/pathfinder/app/llm.py"
    - "Valid LLM JSON response {reply, mood_delta} parses cleanly and returns dict with both keys"
    - "Malformed LLM response (plain prose, no JSON) returns {reply: <salvaged prose>, mood_delta: 0} and logs WARNING — does NOT raise (T-31-SEC-03)"
    - "mood_delta values outside {-1, 0, 1} coerce to 0 (defence against bad LLM output)"
    - "litellm.acompletion called with timeout=60.0 and api_base only when truthy (consistent with extract_npc_fields)"
    - "_strip_code_fences (existing helper) reused; no new fence-stripper introduced"
  tests:
    - "pytest modules/pathfinder/tests/test_npc.py::test_npc_say_json_parse_salvage -x  # → GREEN once Plan 31-04 wires the route"
    - "Standalone smoke test: from app.llm import generate_npc_reply; callable(generate_npc_reply) is True"
---

<plan_objective>
Extend `modules/pathfinder/app/llm.py` with `generate_npc_reply()` — the thin LiteLLM wrapper for dialogue. Single-call structured-output extraction with graceful JSON-parse degradation per RESEARCH Finding 7. Plan 31-04 calls this from the route handler.
</plan_objective>

<threat_model>
## STRIDE Register

| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-31-03-T01 | Tampering | Prompt injection via party_line yielding malformed JSON or attempting to alter system intent (T-31-SEC-03) | mitigate | Salvage path returns the LLM's prose as `reply`, forces `mood_delta=0`, logs WARNING. No 500 to user; no automatic mood shift. |
| T-31-03-T02 | Tampering | LLM returns mood_delta=5 or "lots" or `{}` instead of integer | mitigate | `if delta not in (-1, 0, 1): delta = 0` clamp. Defensive even with chat-tier model. |
| T-31-03-D01 | DoS | Overlong reply consuming Discord's 2000-char message limit | mitigate | Hard truncate `reply[:1500]` post-parse — leaves headroom for quote-block markdown wrapping in Plan 31-05. |
| T-31-03-D02 | DoS | LLM hang | mitigate | `timeout=60.0` matches existing `extract_npc_fields` (line 60 of llm.py). |
| T-31-03-I01 | Information Disclosure | LLM raw output (which may contain system prompt fragments if model echoes) leaking via WARNING log | accept | `raw[:200]` truncates log line. Local-deployment risk only; no external log shipping in scope. |

**Block level:** none HIGH. T-31-03-T01 and T-31-03-T02 are MITIGATED. T-31-03-D01 and T-31-03-D02 are MITIGATED. T-31-03-I01 accepted with rationale. ASVS L1 satisfied.
</threat_model>

<tasks>

<task id="31-03-01" type="tdd" autonomous="true" tdd="true">
  <name>Task 31-03-01: Add generate_npc_reply to modules/pathfinder/app/llm.py</name>
  <read_first>
    - modules/pathfinder/app/llm.py (full file — 170 lines; lines 1-26 for module setup + _strip_code_fences; lines 29-69 for extract_npc_fields analog)
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md §3 (shape rules + Gotcha)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 446-461 (graceful-degrade reference impl) and lines 746-782 (full reference impl)
    - .planning/phases/31-dialogue-engine/31-CONTEXT.md decisions D-23 (JSON salvage), D-27 (model selection — caller passes model string, this function does not call resolve_model)
  </read_first>
  <behavior>
    - generate_npc_reply(sys, usr, model, api_base) returns dict with keys "reply" (str) and "mood_delta" (int in {-1, 0, 1})
    - Valid LLM JSON `{"reply": "*nods.* \"Aye.\"", "mood_delta": 1}` returns `{"reply": "*nods.* \"Aye.\"", "mood_delta": 1}` (parsed straight through)
    - Code-fence-wrapped JSON `\`\`\`json\n{"reply":"x","mood_delta":0}\n\`\`\`` parses correctly via `_strip_code_fences`
    - Malformed LLM output `"this is plain prose, no json"` returns `{"reply": "this is plain prose, no json", "mood_delta": 0}` and logs WARNING containing the substring "JSON parse failed" or "salvaging"
    - LLM returns `{"reply": "x", "mood_delta": 5}` returns `{"reply": "x", "mood_delta": 0}` (clamp out-of-range)
    - LLM returns `{"reply": "x", "mood_delta": "lots"}` returns `{"reply": "x", "mood_delta": 0}` (clamp non-int)
    - LLM returns `{"reply": "x" * 2000, "mood_delta": 0}` returns reply truncated to 1500 chars
    - Empty LLM response returns `{"reply": "...", "mood_delta": 0}` (placeholder string when nothing to salvage)
    - litellm.acompletion called with model=passed-in model, messages=[system, user], timeout=60.0
    - When api_base is None, no api_base kwarg passed; when api_base is non-empty string, api_base kwarg passed
  </behavior>
  <action>
APPEND to `modules/pathfinder/app/llm.py` (after the existing `update_npc_fields` function — currently the last function in the file). Use the `kwargs: dict = {...}` conditional pattern from `extract_npc_fields` lines 56-66 (Patterns S2 — applies to all LLM call sites):

```python
async def generate_npc_reply(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_base: str | None = None,
) -> dict:
    """LLM dialogue call — returns {reply: str, mood_delta: int} for one NPC turn (DLG-01, DLG-02).

    Single chat call extracts both the in-character reply and the mood shift signal.
    Graceful degradation on JSON parse failure (T-31-SEC-03):
    - Returns {reply: <salvaged prose>, mood_delta: 0}; does NOT raise.
    - Logs WARNING with raw[:200] for diagnosis.

    Caller is responsible for selecting the model (D-27 — chat tier from resolve_model("chat")).
    """
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "timeout": 60.0,
    }
    if api_base:
        kwargs["api_base"] = api_base

    response = await litellm.acompletion(**kwargs)
    raw = response.choices[0].message.content or ""
    stripped = _strip_code_fences(raw).strip()

    try:
        parsed = json.loads(stripped)
        reply = str(parsed.get("reply", stripped)).strip()[:1500]
        delta = parsed.get("mood_delta", 0)
        if not isinstance(delta, int) or delta not in (-1, 0, 1):
            delta = 0
        return {"reply": reply, "mood_delta": delta}
    except json.JSONDecodeError:
        logger.warning(
            "generate_npc_reply: JSON parse failed, salvaging reply text. raw_head=%r",
            raw[:200],
        )
        salvaged = (stripped or "...")[:1500]
        return {"reply": salvaged, "mood_delta": 0}
```

**Imports check:** `json`, `litellm`, `logger`, and `_strip_code_fences` are already imported at the top of llm.py (lines 1-15). No new imports required.

**Standalone smoke test (uses real `litellm.acompletion` patched at the test boundary; no actual model call):**
```bash
cd modules/pathfinder && python -c "
import asyncio
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from app.llm import generate_npc_reply

# Test 1: valid JSON parse
async def t1():
    fake_resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{\"reply\": \"hello\", \"mood_delta\": 1}'))])
    with patch('app.llm.litellm.acompletion', new=AsyncMock(return_value=fake_resp)):
        r = await generate_npc_reply('sys', 'usr', 'openai/local-model')
    assert r == {'reply': 'hello', 'mood_delta': 1}, r

# Test 2: salvage on plain prose
async def t2():
    fake_resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='just prose, no json here'))])
    with patch('app.llm.litellm.acompletion', new=AsyncMock(return_value=fake_resp)):
        r = await generate_npc_reply('sys', 'usr', 'openai/local-model')
    assert r['reply'] == 'just prose, no json here', r
    assert r['mood_delta'] == 0, r

# Test 3: clamp out-of-range delta
async def t3():
    fake_resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{\"reply\": \"x\", \"mood_delta\": 5}'))])
    with patch('app.llm.litellm.acompletion', new=AsyncMock(return_value=fake_resp)):
        r = await generate_npc_reply('sys', 'usr', 'openai/local-model')
    assert r == {'reply': 'x', 'mood_delta': 0}, r

# Test 4: code-fence stripping
async def t4():
    fake_resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='\`\`\`json\n{\"reply\": \"y\", \"mood_delta\": -1}\n\`\`\`'))])
    with patch('app.llm.litellm.acompletion', new=AsyncMock(return_value=fake_resp)):
        r = await generate_npc_reply('sys', 'usr', 'openai/local-model')
    assert r == {'reply': 'y', 'mood_delta': -1}, r

# Test 5: api_base conditional
async def t5():
    fake_resp = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{\"reply\": \"z\", \"mood_delta\": 0}'))])
    mock_acomp = AsyncMock(return_value=fake_resp)
    with patch('app.llm.litellm.acompletion', new=mock_acomp):
        await generate_npc_reply('sys', 'usr', 'openai/local-model', api_base=None)
        await generate_npc_reply('sys', 'usr', 'openai/local-model', api_base='http://x:1234/v1')
    # First call: no api_base kwarg
    assert 'api_base' not in mock_acomp.call_args_list[0].kwargs, mock_acomp.call_args_list[0]
    # Second call: api_base kwarg present
    assert mock_acomp.call_args_list[1].kwargs.get('api_base') == 'http://x:1234/v1'

asyncio.run(t1())
asyncio.run(t2())
asyncio.run(t3())
asyncio.run(t4())
asyncio.run(t5())
print('OK')
"
```
  </action>
  <acceptance_criteria>
    - grep -E '^async def generate_npc_reply\(' modules/pathfinder/app/llm.py matches
    - grep -F '_strip_code_fences' modules/pathfinder/app/llm.py occurs ≥ 2 times (existing usage in extract_npc_fields + new usage in generate_npc_reply)
    - grep -F '"timeout": 60.0' modules/pathfinder/app/llm.py occurs ≥ 2 times (existing + new)
    - grep -F 'kwargs["api_base"] = api_base' modules/pathfinder/app/llm.py occurs ≥ 2 times (Patterns S2 conditional)
    - grep -F 'mood_delta' modules/pathfinder/app/llm.py occurs ≥ 3 times (helper docstring + parse + clamp + salvage return)
    - grep -F 'salvaging' modules/pathfinder/app/llm.py matches (WARNING log substring)
    - grep -F '[:1500]' modules/pathfinder/app/llm.py occurs ≥ 2 times (truncate in both happy and salvage paths)
    - grep -F 'json.JSONDecodeError' modules/pathfinder/app/llm.py matches (the salvage trigger)
    - Smoke test command exits 0 with output `OK`
    - Existing tests still green: `cd modules/pathfinder && python -m pytest tests/ -q -k "not npc_say"` exit code 0 (don't break Phase 29/30 tests)
    - grep -vE '^\s*#' modules/pathfinder/app/llm.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' returns 0 matches
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -c "
import asyncio
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from app.llm import generate_npc_reply

async def t1():
    fake = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{\"reply\": \"hello\", \"mood_delta\": 1}'))])
    with patch('app.llm.litellm.acompletion', new=AsyncMock(return_value=fake)):
        r = await generate_npc_reply('sys', 'usr', 'openai/x')
    assert r == {'reply': 'hello', 'mood_delta': 1}

async def t2():
    fake = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='just prose'))])
    with patch('app.llm.litellm.acompletion', new=AsyncMock(return_value=fake)):
        r = await generate_npc_reply('sys', 'usr', 'openai/x')
    assert r == {'reply': 'just prose', 'mood_delta': 0}

async def t3():
    fake = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{\"reply\": \"x\", \"mood_delta\": 5}'))])
    with patch('app.llm.litellm.acompletion', new=AsyncMock(return_value=fake)):
        r = await generate_npc_reply('sys', 'usr', 'openai/x')
    assert r == {'reply': 'x', 'mood_delta': 0}

asyncio.run(t1()); asyncio.run(t2()); asyncio.run(t3()); print('OK')
"</automated>
</task>

</tasks>

<verification>
After Task 31-03-01:

```bash
# 1. New symbol importable
cd modules/pathfinder && python -c "from app.llm import generate_npc_reply; assert callable(generate_npc_reply); print('OK')"

# 2. Existing Phase 29/30 LLM functions still work
cd modules/pathfinder && python -c "from app.llm import extract_npc_fields, update_npc_fields, generate_mj_description; print('OK')"

# 3. Existing tests unbroken
cd modules/pathfinder && python -m pytest tests/ -q -k "not npc_say"

# 4. AI Deferral Ban
grep -vE '^\s*#' modules/pathfinder/app/llm.py | grep -E '(TODO|FIXME|NotImplementedError)' && echo "FAIL" || echo "PASS"
```
</verification>

<success_criteria>
- modules/pathfinder/app/llm.py contains the `generate_npc_reply` async function.
- All 5 smoke-test scenarios in the action section pass.
- The existing module symbols (`extract_npc_fields`, `update_npc_fields`, `generate_mj_description`, `_strip_code_fences`) are unchanged.
- Existing pathfinder tests not affected: `pytest tests/ -q -k "not npc_say"` still exit code 0.
- AI Deferral Ban: zero TODO/FIXME/NotImplementedError/raise NotImplementedError outside comments.
</success_criteria>

<output>
Create `.planning/phases/31-dialogue-engine/31-31-03-SUMMARY.md` documenting:
- File modified: modules/pathfinder/app/llm.py — added 1 function (generate_npc_reply)
- Smoke test scenarios (5/5 OK)
- Confirmation that existing pathfinder tests unaffected
- Note: LLM wrapper ready; Plan 31-04 wires it into the route handler.
</output>
