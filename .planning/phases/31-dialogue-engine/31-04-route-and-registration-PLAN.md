---
plan_id: 31-04
phase: 31
wave: 2
depends_on: [31-01, 31-02, 31-03]
files_modified:
  - modules/pathfinder/app/routes/npc.py
  - modules/pathfinder/app/main.py
autonomous: true
requirements: [DLG-01, DLG-02, DLG-03]
must_haves:
  truths:
    - "POST /modules/pathfinder/npc/say is the 12th registered route — REGISTRATION_PAYLOAD['routes'] has length 12 and includes {'path': 'npc/say', 'description': 'In-character NPC dialogue with mood tracking (DLG-01..03)'}"
    - "Pydantic models NPCSayRequest, TurnHistory, NPCReply, NPCSayResponse exist in app/routes/npc.py"
    - "NPCSayRequest validates: names list non-empty, each name passes _validate_npc_name, party_line ≤ 2000 chars; otherwise 422"
    - "Handler loads each NPC via obsidian.get_note in given order; first missing NPC raises 404 with detail{slug, name}; LLM is NOT called before fail-fast"
    - "Handler calls generate_npc_reply once per NPC serially (no parallel asyncio.gather); each subsequent NPC's user_prompt contains prior NPCs' replies in this turn"
    - "Mood write uses GET-then-PUT via build_npc_markdown + obsidian.put_note (D-09); never uses patch_frontmatter_field"
    - "Mood write happens ONLY when new_mood != current_mood (D-07: zero-delta turns AND clamped no-ops both skip the write)"
    - "Obsidian put_note failure degrades gracefully (set new_mood = current_mood; log error; do NOT raise) — reply still returned"
    - "Response shape: {replies: [{npc, reply, mood_delta, new_mood}], warning: str | None}; warning populated when len(names) >= 5 with the EXACT string '⚠ {N} NPCs in scene — consider splitting for clarity.'"
    - "All 16 module-layer tests in test_npc.py go GREEN (DLG-01..03 unit coverage)"
    - "Both integration tests in test_npc_say_integration.py go GREEN (SC-1..4 round-trip)"
  tests:
    - "cd modules/pathfinder && python -m pytest tests/test_npc.py -k npc_say -q  # → 16 passed"
    - "cd modules/pathfinder && python -m pytest tests/test_npc_say_integration.py -q  # → 2 passed"
    - "cd modules/pathfinder && python -m pytest tests/ -q  # → all green (Phase 29/30/31 module tests)"
    - "python -c 'from app.main import REGISTRATION_PAYLOAD; assert len(REGISTRATION_PAYLOAD[\"routes\"]) == 12; assert any(r[\"path\"] == \"npc/say\" for r in REGISTRATION_PAYLOAD[\"routes\"])'"
---

<plan_objective>
Wire the dialogue engine into the pathfinder module's HTTP surface. This plan ships the `POST /npc/say` endpoint (request/response models + handler), hooks the new route into the module registration payload (12th route), and updates the module docstring. After this plan, all 16 module-layer unit tests AND both integration tests turn GREEN. The Discord bot wiring lands in Plan 31-05.
</plan_objective>

<threat_model>
## STRIDE Register

| Threat ID | Category | Component | Disposition | Mitigation | Test Reference |
|-----------|----------|-----------|-------------|------------|----------------|
| T-31-04-T01 | Tampering | Path traversal via NPC name (T-31-SEC-01) | mitigate | `_validate_npc_name` applied per-element in `NPCSayRequest.names` validator (rejects control chars); `slugify` strips `..`/`/`. Test: `test_npc_say_invalid_name_control_char`. |
| T-31-04-T02 | Tampering | Mood poisoning via hand-edited frontmatter (T-31-SEC-02) | mitigate | `normalize_mood` from dialogue.py wraps every read of `fields.get("mood")`. Test: `test_npc_say_invalid_mood_normalized`. |
| T-31-04-T03 | Tampering | Prompt injection via party_line attempting to manipulate JSON output (T-31-SEC-03) | mitigate | `generate_npc_reply` salvage path absorbs malformed JSON; mood_delta clamped. Test: `test_npc_say_json_parse_salvage`. |
| T-31-04-D01 | DoS | Token-budget DoS via huge history payload (T-31-SEC-04) | mitigate | `cap_history_turns` from dialogue.py caps at 10 turns / 2000 tokens; party_line capped at 2000 chars in NPCSayRequest validator. Tests: `test_npc_say_party_line_too_long`. |
| T-31-04-D02 | DoS | Excessive LLM cost via many NPCs in a single scene | mitigate (warn) | Soft cap ≥5 NPCs surfaces `warning` field; serial within-turn limits concurrency. Test: `test_npc_say_five_npc_warning`. |
| T-31-04-D03 | DoS | Race condition: two rapid-fire `/npc/say` for same NPC lose mood updates | accept (documented limitation) | Discord on_message serializes per-channel; race window is 60s LLM call. Mild under-counting, no corruption. Documented in plan output (RESEARCH Finding 6). |
| T-31-04-I01 | Information Disclosure | NPC stats block contents being injected into LLM (could leak combat stats unnecessarily) | mitigate | Handler reads frontmatter via `_parse_frontmatter`, parses stats via `_parse_stats_block` only to preserve on round-trip write — stats are NEVER passed to `build_system_prompt`. |
| T-31-04-S01 | Spoofing | Module endpoint accepting calls without authentication | mitigate (inherited) | `X-Sentinel-Key` enforced upstream by sentinel-core's `proxy_module` middleware before this route is reached. No new auth code in this plan. |

**Block level:** none HIGH unmitigated. T-31-04-T01/T02/T03 are MITIGATED (tested). T-31-04-D01/D02 are MITIGATED (tested). T-31-04-D03 accepted with documentation. T-31-04-I01 is structural. T-31-04-S01 inherited from existing infrastructure. ASVS L1 satisfied.
</threat_model>

<tasks>

<task id="31-04-01" type="tdd" autonomous="true" tdd="true">
  <name>Task 31-04-01: Add NPCSayRequest / TurnHistory / NPCReply / NPCSayResponse models + imports to routes/npc.py</name>
  <read_first>
    - modules/pathfinder/app/routes/npc.py (lines 1-50 for existing imports; lines 76-121 for NPCCreateRequest/NPCOutputRequest model patterns)
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md §4 (Analog A pydantic + validator pattern; Gotcha 1)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 913-936 (model definitions reference)
    - .planning/phases/31-dialogue-engine/31-CONTEXT.md decisions D-24 (request/response shape), D-28 (party_line 2000-char cap)
  </read_first>
  <behavior>
    - NPCSayRequest accepts {names: ["Varek"], party_line: "hi", history: [], user_id: "u1"} → valid
    - NPCSayRequest with names=[] → ValidationError
    - NPCSayRequest with names=["bad\x00name"] → ValidationError (via _validate_npc_name)
    - NPCSayRequest with party_line of 2001 chars → ValidationError
    - NPCSayRequest with party_line="" → valid (scene-advance signal)
    - NPCSayRequest with missing user_id → ValidationError (required field)
    - TurnHistory accepts {party_line: "x", replies: [{npc: "V", reply: "y"}]} → valid
    - All 4 models importable from app.routes.npc
  </behavior>
  <action>
EDIT `modules/pathfinder/app/routes/npc.py`:

**Step 1 — Update imports** (top of file, around lines 1-30). Add imports for the dialogue helpers (which Plan 31-02 placed in app.dialogue). Find the existing `from app.llm import ...` line and ADD `generate_npc_reply` to it. Add a new import for the dialogue helpers:

```python
# Add to existing llm import line — currently:
#   from app.llm import extract_npc_fields, update_npc_fields, generate_mj_description
# Becomes:
from app.llm import extract_npc_fields, update_npc_fields, generate_mj_description, generate_npc_reply

# Add NEW import line after the llm import:
from app.dialogue import (
    apply_mood_delta,
    build_system_prompt,
    build_user_prompt,
    cap_history_turns,
    normalize_mood,
)
```

**Step 2 — Add the 4 Pydantic models.** Place these IMMEDIATELY AFTER the existing `class NPCOutputRequest(BaseModel)` block (currently around line 121) and BEFORE the first `@router.post(...)` decorator. Use `field_validator` (Pydantic v2 — already imported at the top of the file).

```python
class TurnHistory(BaseModel):
    """One prior dialogue turn (D-11): user :pf npc say + bot's quote-block reply.

    Bot-sourced from thread.history walk; no field validation here (names already
    sanitised when the original message was issued).
    """
    party_line: str = ""
    replies: list[dict] = []  # [{npc: str, reply: str}, ...]


class NPCSayRequest(BaseModel):
    """Request shape for POST /npc/say (D-24).

    party_line == "" is the SCENE ADVANCE signal (D-02).
    history is bot-assembled from Discord thread (D-11..D-14); empty when first turn.
    """
    names: list[str]
    party_line: str = ""
    history: list[TurnHistory] = []
    user_id: str

    @field_validator("names")
    @classmethod
    def sanitize_names(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one NPC name required")
        return [_validate_npc_name(n) for n in v]

    @field_validator("party_line")
    @classmethod
    def check_party_length(cls, v: str) -> str:
        if len(v) > 2000:
            raise ValueError("party_line too long (max 2000 chars)")
        return v


class NPCReply(BaseModel):
    """One NPC's response within a /npc/say turn (D-24)."""
    npc: str
    reply: str
    mood_delta: int
    new_mood: str


class NPCSayResponse(BaseModel):
    """Response shape for POST /npc/say (D-24).

    Per Patterns S6, the route returns JSONResponse({...}) directly rather than
    setting response_model — kept for documentation/typing consistency.
    """
    replies: list[NPCReply]
    warning: str | None = None
```

**Smoke test** (run after edit; verifies models load + basic validation):
```bash
cd modules/pathfinder && python -c "
from pydantic import ValidationError
from app.routes.npc import NPCSayRequest, TurnHistory, NPCReply, NPCSayResponse

# Valid
r = NPCSayRequest(names=['Varek'], party_line='hi', history=[], user_id='u1')
assert r.names == ['Varek'] and r.party_line == 'hi'

# Empty party_line valid (scene advance)
r2 = NPCSayRequest(names=['Varek'], party_line='', history=[], user_id='u1')
assert r2.party_line == ''

# Empty names rejected
try:
    NPCSayRequest(names=[], party_line='x', history=[], user_id='u1')
    assert False, 'should have raised'
except ValidationError:
    pass

# Party line too long rejected
try:
    NPCSayRequest(names=['V'], party_line='x' * 2001, history=[], user_id='u1')
    assert False, 'should have raised'
except ValidationError:
    pass

# Control-char in name rejected
try:
    NPCSayRequest(names=['bad\x00name'], party_line='x', history=[], user_id='u1')
    assert False, 'should have raised'
except ValidationError:
    pass

# TurnHistory shape
th = TurnHistory(party_line='Q', replies=[{'npc': 'V', 'reply': 'A'}])
assert th.replies[0]['npc'] == 'V'

print('OK')
"
```
  </action>
  <acceptance_criteria>
    - grep -E '^class NPCSayRequest\(BaseModel\)' modules/pathfinder/app/routes/npc.py matches
    - grep -E '^class TurnHistory\(BaseModel\)' modules/pathfinder/app/routes/npc.py matches
    - grep -E '^class NPCReply\(BaseModel\)' modules/pathfinder/app/routes/npc.py matches
    - grep -E '^class NPCSayResponse\(BaseModel\)' modules/pathfinder/app/routes/npc.py matches
    - grep -F 'generate_npc_reply' modules/pathfinder/app/routes/npc.py matches (import added)
    - grep -F 'from app.dialogue import' modules/pathfinder/app/routes/npc.py matches
    - grep -F 'apply_mood_delta' modules/pathfinder/app/routes/npc.py matches
    - grep -F 'cap_history_turns' modules/pathfinder/app/routes/npc.py matches
    - grep -F 'party_line too long (max 2000 chars)' modules/pathfinder/app/routes/npc.py matches
    - grep -F 'at least one NPC name required' modules/pathfinder/app/routes/npc.py matches
    - Smoke test exits 0 with output `OK`
    - Existing tests still pass: `cd modules/pathfinder && python -m pytest tests/ -q -k "not npc_say"` exit 0 (no regressions on Phase 29/30 tests)
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -c "
from pydantic import ValidationError
from app.routes.npc import NPCSayRequest, TurnHistory, NPCReply, NPCSayResponse
r = NPCSayRequest(names=['Varek'], party_line='hi', history=[], user_id='u1')
assert r.names == ['Varek']
try:
    NPCSayRequest(names=[], party_line='x', history=[], user_id='u1')
    assert False
except ValidationError:
    pass
try:
    NPCSayRequest(names=['V'], party_line='x' * 2001, history=[], user_id='u1')
    assert False
except ValidationError:
    pass
print('OK')
"</automated>
</task>

<task id="31-04-02" type="tdd" autonomous="true" tdd="true">
  <name>Task 31-04-02: Add POST /npc/say handler to routes/npc.py</name>
  <read_first>
    - modules/pathfinder/app/routes/npc.py (full file — lines 331-379 for `update_npc` GET-then-PUT analog; lines 143-202 for slugify/_parse_frontmatter/_parse_stats_block/build_npc_markdown)
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md §4 (Analog B + Gotchas 1-3)
    - .planning/phases/31-dialogue-engine/31-RESEARCH.md lines 939-1026 (full handler reference impl)
    - .planning/phases/31-dialogue-engine/31-CONTEXT.md decisions D-07 (zero-delta no-write), D-09 (GET-then-PUT), D-19 (serial), D-29 (404 fail-fast)
    - modules/pathfinder/app/resolve_model.py (resolve_model("chat") signature)
  </read_first>
  <behavior>
    - POST /npc/say with valid solo request returns 200 with replies[0] = {npc, reply, mood_delta, new_mood}
    - First missing NPC in given order returns 404; LLM is NOT called for any NPC
    - Mood unchanged (delta=0 OR clamp no-op) → put_note NOT called
    - Mood changed (e.g., neutral + 1 = friendly) → put_note called once with content containing `mood: friendly`
    - 5 NPCs → response.warning == "⚠ 5 NPCs in scene — consider splitting for clarity." (exact string per CONTEXT.md D-18)
    - Empty party_line ("") → user_prompt to LLM contains "silent" / "Continue the scene" framing (verified via spy on generate_npc_reply call args)
    - Second NPC in scene receives first NPC's reply text in user_prompt (verified via spy)
    - put_note exception → log error, set new_mood = current_mood, return 200 with original mood (graceful degrade per RESEARCH.md lines 1007-1012)
    - Stats block preserved: when handler writes mood, it MUST pass `stats=current_stats if current_stats else None` to build_npc_markdown
    - Relationship edges filtered: only relationships where target is in scene_roster appear in system_prompt
  </behavior>
  <action>
APPEND to `modules/pathfinder/app/routes/npc.py` (place after the last existing `@router.post(...)` handler in the file). Use the GET-then-PUT pattern from `update_npc` (lines 331-379) and the full reference impl from RESEARCH.md lines 939-1026:

```python
@router.post("/say")
async def say_npc(req: NPCSayRequest) -> JSONResponse:
    """In-character NPC dialogue with mood tracking and multi-NPC scenes (DLG-01..03).

    - Solo or scene mode (≥2 names) determined by len(req.names).
    - Empty req.party_line == "" triggers SCENE ADVANCE framing (D-02).
    - First missing NPC fails fast with 404 (D-29) before any LLM call.
    - Mood writes use GET-then-PUT via build_npc_markdown (D-09) — only when mood changes.
    - Soft warning when ≥5 NPCs (D-18).
    """
    # Step 1: Load each NPC in order; fail fast on first missing (D-29).
    npcs_data: list[dict] = []
    for name in req.names:
        slug = slugify(name)
        path = f"{_NPC_PATH_PREFIX}/{slug}.md"
        note_text = await obsidian.get_note(path)
        if note_text is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "NPC not found", "slug": slug, "name": name},
            )
        fields = _parse_frontmatter(note_text)
        stats = _parse_stats_block(note_text)
        npcs_data.append({
            "name": name,
            "slug": slug,
            "path": path,
            "fields": fields,
            "stats": stats,
        })

    # Step 2: Cap thread-scoped history (D-14).
    capped_history = cap_history_turns([h.model_dump() for h in req.history])

    # Step 3: Scene roster in canonical order.
    scene_roster = [n["name"] for n in npcs_data]
    scene_name_set_lower = {n.lower() for n in scene_roster}

    # Step 3b: Debug-only scene_id (RESEARCH.md Recommended Defaults — logged only, not user-visible).
    scene_id = "-".join(sorted(slugify(n) for n in scene_roster))
    logger.info("npc/say scene_id=%s names=%s party_line_len=%d history_turns=%d",
                scene_id, scene_roster, len(req.party_line), len(capped_history))

    # Step 4: Resolve chat-tier model (D-27). Single call up front; same model used per turn.
    model = await resolve_model("chat")
    api_base = settings.litellm_api_base or None

    # Step 5: Serial round-robin (D-19) — each NPC sees prior NPCs' replies in this turn.
    this_turn_replies: list[dict] = []
    response_replies: list[dict] = []
    for npc in npcs_data:
        # Filter relationship edges to scene members only (Pitfall 7 in PATTERNS.md / RESEARCH.md Finding 7).
        all_rels = npc["fields"].get("relationships") or []
        scene_rels = [
            r for r in all_rels
            if isinstance(r, dict)
            and str(r.get("target", "")).lower() in scene_name_set_lower
        ]

        sys_prompt = build_system_prompt(npc["fields"], scene_roster, scene_rels)
        usr_prompt = build_user_prompt(
            history=capped_history,
            this_turn_replies=this_turn_replies,
            party_line=req.party_line,
            npc_name=npc["name"],
        )

        llm_result = await generate_npc_reply(
            system_prompt=sys_prompt,
            user_prompt=usr_prompt,
            model=model,
            api_base=api_base,
        )

        # Mood math (D-07): zero or clamped no-op skips the vault write.
        current_mood = normalize_mood(npc["fields"].get("mood") or "neutral")
        new_mood = apply_mood_delta(current_mood, llm_result["mood_delta"])

        if new_mood != current_mood:
            updated_fields = dict(npc["fields"])
            updated_fields["mood"] = new_mood
            new_content = build_npc_markdown(
                updated_fields,
                stats=npc["stats"] if npc["stats"] else None,
            )
            try:
                await obsidian.put_note(npc["path"], new_content)
                logger.info("NPC mood updated: %s %s -> %s", npc["name"], current_mood, new_mood)
            except Exception as exc:
                logger.error("Mood write failed for %s: %s", npc["name"], exc)
                # Degrade per RESEARCH.md lines 1007-1012: keep reply, revert reported mood.
                new_mood = current_mood

        this_turn_replies.append({"npc": npc["name"], "reply": llm_result["reply"]})
        response_replies.append({
            "npc": npc["name"],
            "reply": llm_result["reply"],
            "mood_delta": llm_result["mood_delta"],
            "new_mood": new_mood,
        })

    # Step 6: Soft cap warning (D-18) — exact string per CONTEXT.md D-18.
    warning = None
    if len(scene_roster) >= 5:
        warning = f"⚠ {len(scene_roster)} NPCs in scene — consider splitting for clarity."

    return JSONResponse({"replies": response_replies, "warning": warning})
```

**Final test gate** (after this task all 16 module unit tests AND both integration tests should be GREEN):
```bash
cd modules/pathfinder && python -m pytest tests/test_npc.py -k npc_say -v
# Expected: 16 passed

cd modules/pathfinder && python -m pytest tests/test_npc_say_integration.py -v
# Expected: 2 passed

cd modules/pathfinder && python -m pytest tests/ -q
# Expected: all green (Phase 29 + 30 + 31 module-side)
```
  </action>
  <acceptance_criteria>
    - grep -E '^@router\.post\("/say"\)' modules/pathfinder/app/routes/npc.py matches
    - grep -E '^async def say_npc\(' modules/pathfinder/app/routes/npc.py matches
    - grep -F 'cap_history_turns' modules/pathfinder/app/routes/npc.py matches (used in handler)
    - grep -F 'build_system_prompt' modules/pathfinder/app/routes/npc.py matches
    - grep -F 'build_user_prompt' modules/pathfinder/app/routes/npc.py matches
    - grep -F 'apply_mood_delta' modules/pathfinder/app/routes/npc.py matches
    - grep -F 'normalize_mood' modules/pathfinder/app/routes/npc.py matches
    - grep -F '⚠ {len(scene_roster)} NPCs in scene — consider splitting for clarity.' modules/pathfinder/app/routes/npc.py matches (exact warning fstring)
    - grep -F 'await resolve_model("chat")' modules/pathfinder/app/routes/npc.py matches (D-27)
    - grep -F 'build_npc_markdown' modules/pathfinder/app/routes/npc.py occurs ≥ 2 times (existing update_npc + new say handler)
    - grep -c 'patch_frontmatter_field' modules/pathfinder/app/routes/npc.py — must NOT increase from baseline (mood write uses PUT not PATCH per D-09; this verifies no regression to PATCH for the new handler)
    - grep -F 'this_turn_replies' modules/pathfinder/app/routes/npc.py matches (scene context awareness)
    - grep -F 'scene_id' modules/pathfinder/app/routes/npc.py matches (debug log per RESEARCH.md Recommended Defaults)
    - All 16 npc_say tests pass: `cd modules/pathfinder && python -m pytest tests/test_npc.py -k npc_say -q` exit code 0
    - Both integration tests pass: `cd modules/pathfinder && python -m pytest tests/test_npc_say_integration.py -q` exit code 0
    - No Phase 29/30 regressions: `cd modules/pathfinder && python -m pytest tests/ -q -k "not npc_say"` exit code 0
    - grep -vE '^\s*#' modules/pathfinder/app/routes/npc.py | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' returns 0 matches (AI Deferral Ban — verify ONLY in lines added by this plan; if existing pre-Phase-31 markers exist they are out of scope)
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -m pytest tests/test_npc.py -k npc_say -q && python -m pytest tests/test_npc_say_integration.py -q</automated>
</task>

<task id="31-04-03" type="execute" autonomous="true">
  <name>Task 31-04-03: Add npc/say to REGISTRATION_PAYLOAD + module docstring in main.py</name>
  <read_first>
    - modules/pathfinder/app/main.py (full 130 lines — focus on REGISTRATION_PAYLOAD lines 47-63 and module docstring lines 1-16)
    - .planning/phases/31-dialogue-engine/31-PATTERNS.md §5 (verbatim entry text + Pitfall 7 reminder)
    - .planning/phases/31-dialogue-engine/31-CONTEXT.md decision D-26 (registry goes 11 → 12)
  </read_first>
  <action>
EDIT `modules/pathfinder/app/main.py`:

**Step 1 — Append the npc/say route entry to REGISTRATION_PAYLOAD.**
Find the existing `REGISTRATION_PAYLOAD` dict (around line 47). The `routes` list currently has 11 entries. Add EXACTLY this entry as the 12th, after the `npc/pdf` entry (verbatim per D-26 / PATTERNS.md §5):

```python
{"path": "npc/say", "description": "In-character NPC dialogue with mood tracking (DLG-01..03)"},
```

**Step 2 — Update the module docstring.**
Find the docstring at the top of main.py (lines 4-16) listing the endpoints. Append one line after the existing `/npc/pdf` entry:

```
  POST /npc/say            — in-character NPC dialogue with mood tracking (DLG-01..03)
```

(Match the formatting style of the existing docstring entries — 2-space indent, padded `POST /npc/<verb>` followed by em-dash separator and description. Inspect the existing entries to confirm exact spacing.)

**Smoke test:**
```bash
cd modules/pathfinder && python -c "
from app.main import REGISTRATION_PAYLOAD
routes = REGISTRATION_PAYLOAD['routes']
assert len(routes) == 12, f'expected 12 routes, got {len(routes)}'
say = [r for r in routes if r['path'] == 'npc/say']
assert len(say) == 1, f'expected exactly one npc/say route, got {len(say)}'
assert say[0]['description'] == 'In-character NPC dialogue with mood tracking (DLG-01..03)', say[0]
print('OK — 12 routes registered, npc/say present')
"
```
  </action>
  <acceptance_criteria>
    - Smoke test exits 0 with output containing `OK — 12 routes registered, npc/say present`
    - grep -F '"npc/say"' modules/pathfinder/app/main.py matches
    - grep -F '"In-character NPC dialogue with mood tracking (DLG-01..03)"' modules/pathfinder/app/main.py matches
    - grep -E '^\s*POST /npc/say' modules/pathfinder/app/main.py matches (docstring updated)
    - python -c 'from app.main import REGISTRATION_PAYLOAD; print(len(REGISTRATION_PAYLOAD["routes"]))' outputs `12`
    - All module tests still green: `cd modules/pathfinder && python -m pytest tests/ -q` exit code 0
  </acceptance_criteria>
  <automated>cd modules/pathfinder && python -c "from app.main import REGISTRATION_PAYLOAD; routes = REGISTRATION_PAYLOAD['routes']; assert len(routes) == 12, f'expected 12, got {len(routes)}'; say = [r for r in routes if r['path'] == 'npc/say']; assert len(say) == 1; assert say[0]['description'] == 'In-character NPC dialogue with mood tracking (DLG-01..03)'; print('OK')"</automated>
</task>

</tasks>

<verification>
Phase-31 module-side gate (after all 3 tasks complete):

```bash
# 1. All 16 unit tests + 2 integration tests GREEN
cd modules/pathfinder && python -m pytest tests/test_npc.py -k npc_say -v
# Expected: 16 passed

cd modules/pathfinder && python -m pytest tests/test_npc_say_integration.py -v
# Expected: 2 passed

# 2. No Phase 29/30 regressions
cd modules/pathfinder && python -m pytest tests/ -q
# Expected: all green

# 3. Registration payload has 12 routes including npc/say
cd modules/pathfinder && python -c "from app.main import REGISTRATION_PAYLOAD; assert len(REGISTRATION_PAYLOAD['routes']) == 12 and any(r['path'] == 'npc/say' for r in REGISTRATION_PAYLOAD['routes']); print('REGISTRATION OK')"

# 4. Mood write path uses PUT not PATCH (D-09 + memory invariant)
grep -A 5 'async def say_npc' modules/pathfinder/app/routes/npc.py | grep -F 'patch_frontmatter_field' && echo "FAIL — PATCH used in say handler" || echo "PASS — no PATCH in say handler"

# 5. AI Deferral Ban scan on the new handler region only
sed -n '/async def say_npc/,/^async def\|^def /p' modules/pathfinder/app/routes/npc.py | grep -vE '^\s*#' | grep -E '(TODO|FIXME|NotImplementedError|raise NotImplementedError)' && echo "FAIL" || echo "PASS"
```
</verification>

<success_criteria>
- POST /npc/say endpoint exists with the exact request shape from D-24.
- All 16 module-layer unit tests + 2 integration tests pass (RED → GREEN transition complete for module side).
- REGISTRATION_PAYLOAD has 12 routes including the npc/say entry with the exact description from D-26.
- Mood write path uses GET-then-PUT (build_npc_markdown + put_note); no `patch_frontmatter_field` introduced for mood.
- Stats block preserved on every mood-write round-trip (verified by integration test that the stats survive).
- Graceful degradation on put_note failure: reply still returned, new_mood reverts to current_mood.
- Phase 29 and Phase 30 tests unbroken.
- AI Deferral Ban: zero TODO/FIXME/NotImplementedError introduced.
- DLG-01, DLG-02, DLG-03 satisfied at the HTTP layer (Discord rendering follows in Plan 31-05).
</success_criteria>

<output>
Create `.planning/phases/31-dialogue-engine/31-31-04-SUMMARY.md` documenting:
- Files modified: routes/npc.py (+ 4 models, + say_npc handler), main.py (+ 1 route registration, + docstring entry)
- Test results: 16/16 unit + 2/2 integration green; full module suite green; no Phase 29/30 regressions
- REGISTRATION_PAYLOAD route count: 12 (was 11)
- Documented limitation: rapid-fire mood race condition (RESEARCH Finding 6) — accepted, not mitigated in v1
- Note: HTTP layer complete; Discord bot wiring (verb dispatch + thread history walker + render) lands in Plan 31-05.
</output>
