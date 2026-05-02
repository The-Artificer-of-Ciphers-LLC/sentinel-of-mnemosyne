---
quick_id: 260502-0vr
slug: execute-deepening-refactor-per-docs-adr-
date: 2026-05-02
status: planned
---

# Deepen MessageProcessor + Source Sentinel Persona from Vault

## Description

Collapse seven shallow extracted helpers back into `MessageProcessor` as private members, source the Sentinel persona from `sentinel/persona.md` in the Vault (read in parallel with the existing Hot tier `asyncio.gather`), and push session-summary swallow-and-log into `ObsidianClient.write_session_summary`. Replace the `app.state.message_processor_factory` lambda with a singleton `app.state.message_processor` built once during lifespan. Add a startup contract: Vault reachable + persona file 404 = hard fail; Vault unreachable = continue with hardcoded fallback. Add new behavioral tests for `MessageProcessor.process()`. All work commits directly to `main` (project override in CLAUDE.md).

## Decisions (locked)

All decisions below are locked. Source: `docs/adr/0001-sentinel-persona-source.md` and the in-turn grilling captured in `CONTEXT.md`. The planner does not re-litigate.

- Collapse `message_route_bridge`, `message_processor_factory`, `message_persistence`, `message_error_mapper`, `session_summary`, `context_budget_policy`, `message_prompt` into `MessageProcessor` (private members) or into `routes/message.py` where they're transport-shaped. Delete the seven files and their dedicated tests.
- Sentinel persona prompt sourced from `sentinel/persona.md`, read every message via the existing `_append_hot_tier` `asyncio.gather`. Hardcoded fallback = the existing `SYSTEM_PROMPT` string verbatim, kept as `MessageProcessor._FALLBACK_PERSONA`.
- Startup contract: Obsidian reachable AND `sentinel/persona.md` returns 404 → raise during lifespan (hard fail). Obsidian unreachable at startup → continue (preserves graceful-degrade).
- Per-request contract: persona read fails or returns empty → use `_FALLBACK_PERSONA` + log warning. Never 503 user traffic over a vault edit.
- `ObsidianClient.write_session_summary` swallows exceptions internally via `_safe_request` (matches `read_self_context`, `get_recent_sessions`). Docstring updated to remove "callers wrap in try/except".
- `app.state.message_processor_factory` lambda removed. Single `MessageProcessor` instance built during lifespan, pinned to `app.state.message_processor`. Tests overwrite the attribute directly (mirrors `obsidian_client`, `ai_provider` pattern).
- New `tests/test_message_processor.py` with direct behavioral tests of `MessageProcessor.process()` using fakes — covers context overflow → `context_overflow`, provider unavailable → `provider_unavailable`, security block → `security_blocked`, summary path/content shape, persona vault-read used, persona fallback when vault returns empty, LiteLLM context-length error string detection.
- `README.md` documents the operator setup: `sentinel/persona.md` must exist in the Vault before first run; suggested seed = the fallback persona string.

## Files modified

### Delete

- `sentinel-core/app/services/message_route_bridge.py` — body inlined into `routes/message.py`.
- `sentinel-core/tests/test_message_route_bridge.py` — covers a deleted module.
- `sentinel-core/app/services/message_processor_factory.py` — replaced by direct `app.state.message_processor` access.
- `sentinel-core/tests/test_message_processor_factory.py` — covers a deleted module.
- `sentinel-core/app/services/message_persistence.py` — swallow moved into `ObsidianClient.write_session_summary`.
- `sentinel-core/app/services/message_error_mapper.py` — match block inlined into the route.
- `sentinel-core/tests/test_message_error_mapper.py` — covers a deleted module.
- `sentinel-core/app/services/session_summary.py` — collapsed into `MessageProcessor`.
- `sentinel-core/tests/test_session_summary.py` — covers a deleted module.
- `sentinel-core/app/services/context_budget_policy.py` — collapsed into `MessageProcessor`.
- `sentinel-core/tests/test_context_budget_policy.py` — covers a deleted module.
- `sentinel-core/app/services/message_prompt.py` — replaced by `_FALLBACK_PERSONA` class constant + Vault read.
- `sentinel-core/tests/test_message_processing_module.py` — private-method tests; replaced by behavioral tests.

### Edit

- `sentinel-core/app/clients/obsidian.py` — wrap `write_session_summary` in `_safe_request`; update docstring; update module docstring to remove the `write_session_summary` exception note.
- `sentinel-core/app/services/message_processing.py` — absorb `ContextBudgetPolicy`, `build_session_summary`, `SYSTEM_PROMPT` (as `_FALLBACK_PERSONA`); add `sentinel/persona.md` read inside `_append_hot_tier`'s `asyncio.gather`; assign persona (or fallback) to `messages[0]`; emit warning on empty/failed read.
- `sentinel-core/app/routes/message.py` — inline `build_message_request` body and the `to_http_status` match block; read `request.app.state.message_processor` directly; call `obsidian.write_session_summary` directly in the background task (no wrapper).
- `sentinel-core/app/main.py` — add startup probe for `sentinel/persona.md` (raise if Obsidian healthy + file 404); replace `message_processor_factory` lambda with single `MessageProcessor` instance pinned to `app.state.message_processor`.
- `sentinel-core/tests/test_message.py` — autouse fixture mocks `obsidian.read_self_context("sentinel/persona.md")` to return a test persona; replace `app.state.message_processor_factory = ...` with direct `app.state.message_processor = ...` assignments; rewrite `test_post_message_uses_message_processor_factory_when_present` as `test_post_message_uses_app_state_processor`.
- `sentinel-core/tests/test_obsidian_client.py` — sweep for any assertion that `write_session_summary` raises on backend failure; update those assertions to reflect the new swallow contract (in lockstep with the approved feature change).
- `README.md` — add operator setup note for `sentinel/persona.md`.

### Create

- `sentinel-core/tests/test_message_processor.py` — direct behavioral tests of `MessageProcessor.process()` with fakes.

## Tasks

Each task is one atomic commit, in this order. Resequence only if a real dependency forces it.

### Task 1 — Push swallow into ObsidianClient; delete message_persistence

**Files:**
- Edit: `sentinel-core/app/clients/obsidian.py`
- Edit: `sentinel-core/app/routes/message.py`
- Edit: `sentinel-core/tests/test_obsidian_client.py` (only if it asserts the old raise-on-failure contract)
- Delete: `sentinel-core/app/services/message_persistence.py`

**Action:**
- Wrap the body of `ObsidianClient.write_session_summary` in `_safe_request(...)` returning `None` on failure, with `operation="write_session_summary"`. Mirror the existing `read_self_context` shape.
- Update `write_session_summary`'s docstring: remove "Callers wrap in try/except and log warning on failure". State that the method swallows transport errors and logs a warning, returning `None` on failure.
- Update the module docstring (lines 2–5 of `obsidian.py`) to remove the `write_session_summary` exception carve-out.
- In `routes/message.py`, change `_schedule_session_summary` to schedule `request.app.state.obsidian_client.write_session_summary` directly with `(result.summary_path, result.summary_content)`. Drop the `from app.services.message_persistence import write_session_summary_best_effort` import.
- Delete `sentinel-core/app/services/message_persistence.py`.
- Read `tests/test_obsidian_client.py`. If any test asserts that `write_session_summary` raises on a non-2xx backend response, update those assertions to expect a returned `None` and a logged warning. Document this rewrite in the commit message — it is in lockstep with the approved swallow change (see Guardrail Call-outs).

**Commit message:** `refactor(core): push session-summary swallow into ObsidianClient.write_session_summary`

### Task 2 — Inline route bridge + error mapper into routes/message.py

**Files:**
- Edit: `sentinel-core/app/routes/message.py`
- Delete: `sentinel-core/app/services/message_route_bridge.py`
- Delete: `sentinel-core/app/services/message_error_mapper.py`
- Delete: `sentinel-core/tests/test_message_route_bridge.py`
- Delete: `sentinel-core/tests/test_message_error_mapper.py`

**Action:**
- Inline the body of `build_message_request` directly into `post_message` (constructing a `MessageRequest` from `envelope` + `request.app.state` fields like `model`, `context_window`, stop sequences). Drop the `from app.services.message_route_bridge import build_message_request` import.
- Inline `to_http_status`'s `match` block as a local helper or as an inline `match` against `exc.code` inside the `except MessageProcessingError` arm. Map the same codes to the same HTTP statuses as today. Drop the `from app.services.message_error_mapper import to_http_status` import.
- Delete the four files listed above.

**Commit message:** `refactor(core): inline message route bridge + error mapper into route`

### Task 3 — Collapse budget policy, session summary, message prompt into MessageProcessor

**Files:**
- Edit: `sentinel-core/app/services/message_processing.py`
- Delete: `sentinel-core/app/services/context_budget_policy.py`
- Delete: `sentinel-core/app/services/session_summary.py`
- Delete: `sentinel-core/app/services/message_prompt.py`
- Delete: `sentinel-core/tests/test_context_budget_policy.py`
- Delete: `sentinel-core/tests/test_session_summary.py`
- Delete: `sentinel-core/tests/test_message_processing_module.py`

**Action:**
- Move `ContextBudgetPolicy` (whatever its current shape is) into `MessageProcessor` as a private nested class or as private methods on `MessageProcessor` (e.g. `_allocate_budgets(context_window) -> Budgets`). Drop the `budget_policy` constructor parameter; the policy is internal.
- Move `build_session_summary` into `MessageProcessor` as a private static method `_build_session_summary(user_id, user_content, ai_content, model_name) -> tuple[str, str]`.
- Move `SYSTEM_PROMPT` from `message_prompt.py` into `MessageProcessor` as the class constant `_FALLBACK_PERSONA`. (The Vault-read wiring lands in Task 4; for this commit the constant simply replaces the imported `SYSTEM_PROMPT` reference in `process()`.)
- Drop the three module-level imports that no longer resolve.
- Delete the six files listed.

**Commit message:** `refactor(core): collapse budget policy, session summary, prompt into MessageProcessor`

### Task 4 — Source Sentinel persona from Vault inside _append_hot_tier

**Files:**
- Edit: `sentinel-core/app/services/message_processing.py`

**Action:**
- In `_append_hot_tier`, add `"sentinel/persona.md"` to the parallel reads. Easiest shape: keep `self_paths` as the user/self list and add a separate parallel call so the persona result is addressable by name — e.g. extend the `asyncio.gather(...)` to include `self._obsidian.read_self_context("sentinel/persona.md")` and bind the result to a local `persona_text` variable.
- After gather, if `persona_text` is a non-empty string, set `messages[0] = {"role": "system", "content": persona_text}`. If empty or an exception, log a warning ("Sentinel persona vault read returned empty; using fallback") and leave `messages[0]` set to `_FALLBACK_PERSONA` (which `process()` already initializes).
- The persona read must not block startup or per-request flow on transport errors — `read_self_context` already returns `""` on failure via `_safe_request`. The fallback path covers both empty file and transport failure.
- Do not change anything else in `_append_hot_tier` beyond what's needed to wire the persona read.

**Commit message:** `feat(core): source Sentinel persona from sentinel/persona.md vault file`

### Task 5 — Lifespan startup probe + singleton MessageProcessor

**Files:**
- Edit: `sentinel-core/app/main.py`
- Edit: `sentinel-core/app/routes/message.py`
- Delete: `sentinel-core/app/services/message_processor_factory.py`
- Delete: `sentinel-core/tests/test_message_processor_factory.py`

**Action:**
- In `lifespan`, after `obsidian_ok = await obsidian_client.check_health()`, add: if `obsidian_ok` is true, perform a probe read of `sentinel/persona.md` via `obsidian_client.read_self_context("sentinel/persona.md")`. If the probe returns `""`, do a strict GET against the same path to distinguish 404 from empty-file. The simplest shape that works: do a direct `httpx` GET on `f"{obsidian_api_url}/vault/sentinel/persona.md"` with the bearer header — on 404, raise `RuntimeError("sentinel/persona.md missing from Vault — operator setup required (see README)")`. Any other error is non-fatal (matches the existing graceful-degrade posture). If `obsidian_ok` is false, skip the probe entirely.
- Replace the `app.state.message_processor_factory = lambda: MessageProcessor(...)` block with a single instantiation: `app.state.message_processor = MessageProcessor(obsidian=app.state.obsidian_client, ai_provider=app.state.ai_provider, injection_filter=app.state.injection_filter, output_scanner=app.state.output_scanner)`. Drop the `budget_policy` argument (removed in Task 3).
- In `routes/message.py`, replace `processor = from_app_state(request.app.state)` with `processor = request.app.state.message_processor`. Drop the `from app.services.message_processor_factory import from_app_state` import.
- Delete `app/services/message_processor_factory.py` and `tests/test_message_processor_factory.py`.

**Commit message:** `feat(core): startup probe for persona file + singleton MessageProcessor on app.state`

### Task 6 — Update test_message.py for new fixture pattern

**Files:**
- Edit: `sentinel-core/tests/test_message.py`

**Action:**
- In the autouse fixture (or wherever the `obsidian` mock is wired), add a return-value mapping for `read_self_context("sentinel/persona.md")` that returns a test persona string, e.g. `"You are the test Sentinel."`. Existing `self/*` and `ops/reminders.md` mocks remain unchanged.
- Replace every `app.state.message_processor_factory = lambda: ...` (and any `from_app_state` invocation) with direct `app.state.message_processor = <built MessageProcessor>` assignments. The build pattern matches the lifespan one.
- Rewrite `test_post_message_uses_message_processor_factory_when_present` as `test_post_message_uses_app_state_processor`: assert that overwriting `app.state.message_processor` with a stub processor causes `POST /message` to call that stub's `process()` method. The test exercises the new seam (direct attribute), not the deleted factory seam.
- Document in the commit message that the rewrite is in lockstep with the factory removal approved by the operator (Test-Rewrite Ban — see Guardrail Call-outs).

**Commit message:** `test(core): wire persona mock + replace factory seam with app.state.message_processor`

### Task 7 — Add behavioral tests for MessageProcessor.process()

**Files:**
- Create: `sentinel-core/tests/test_message_processor.py`

**Action:**
Build fakes for `obsidian`, `ai_provider`, `injection_filter`, `output_scanner` (plain classes with the methods `MessageProcessor` calls). Construct a real `MessageProcessor` against the fakes and call `processor.process(MessageRequest(...))` directly in each test. Assertions are on the observable result, the raised exception's `code`, or the fakes' recorded calls — never on source code.

Required scenarios (each in its own `async def test_*`):
1. **Context overflow → `context_overflow`**: configure `check_token_limit` (or a fake injection that drives the token guard) so the message exceeds capacity. Assert `MessageProcessingError` raised with `.code == "context_overflow"`.
2. **Provider unavailable → `provider_unavailable`**: fake `ai_provider.complete` raises `ProviderUnavailableError`. Assert `.code == "provider_unavailable"`.
3. **Security block → `security_blocked`**: fake `output_scanner.scan` returns `(False, "blocked-reason")`. Assert `.code == "security_blocked"` (note: route maps this to 500-domain HTTP status, but here we assert the domain code, not HTTP).
4. **Summary path/content shape**: happy-path call returns a `MessageResult`. Assert `result.summary_path` matches the documented vault path shape and `result.summary_content` contains both the user message and the AI response.
5. **Persona vault-read used**: fake `obsidian.read_self_context("sentinel/persona.md")` returns `"TEST PERSONA"`. Assert that the messages passed to `ai_provider.complete` have `messages[0]["content"] == "TEST PERSONA"`.
6. **Persona fallback when vault returns empty**: fake returns `""` for the persona path. Assert `messages[0]["content"] == MessageProcessor._FALLBACK_PERSONA` and that a warning was logged (use `caplog`).
7. **LiteLLM context-length error string detection**: fake `ai_provider.complete` raises `LiteLLMBadRequestError("This model's maximum context length is 4096 tokens. However, you requested...")`. Assert `.code == "context_overflow"` (not `provider_misconfigured`).

All tests must call `processor.process()`. No `grep` on source files. No tautological assertions. Each assertion must be strict enough to detect a real behavioral regression (per CLAUDE.md Behavioral-Test-Only rule).

**Commit message:** `test(core): add behavioral tests for MessageProcessor.process()`

### Task 8 — README operator setup note

**Files:**
- Edit: `README.md`

**Action:**
Add an "Operator setup" subsection (or extend the existing one) stating: before first run, the operator must create `sentinel/persona.md` in the Obsidian Vault. Include the suggested seed content — the literal string of `MessageProcessor._FALLBACK_PERSONA` (or a reference to `sentinel-core/app/services/message_processing.py` where the constant lives). State the startup contract plainly: if Obsidian is reachable and the file is missing, sentinel-core will fail to start.

**Commit message:** `docs: document sentinel/persona.md operator setup`

## Verification

Run before declaring done:

- `cd sentinel-core && uv run pytest -x` — all tests pass, including the new `test_message_processor.py`.
- `cd sentinel-core && uv run ruff check .` — clean.
- `cd sentinel-core && uv run mypy app/` — clean (if mypy is configured for the project; skip if not).
- `rg -n "message_processor_factory|message_route_bridge|message_error_mapper|message_persistence|context_budget_policy|message_prompt" sentinel-core/` — zero matches. Note: `session_summary` may match unrelated docstrings/variables; check that no `from app.services.session_summary` or `import session_summary` references remain.
- `rg -n "from app.services.session_summary|import session_summary" sentinel-core/` — zero matches.
- `ls sentinel-core/app/services/message*.py` — only `message_processing.py` should be listed.
- Manual: open `sentinel-core/app/services/message_processing.py` and confirm `_FALLBACK_PERSONA`, `_allocate_budgets` (or equivalent), and `_build_session_summary` are present as private members of `MessageProcessor`.
- Manual: open `sentinel-core/app/main.py` and confirm `app.state.message_processor` is assigned once (not a lambda factory) and the `sentinel/persona.md` startup probe is present.
- Manual: open `sentinel-core/app/clients/obsidian.py` `write_session_summary` — confirm it goes through `_safe_request` and the docstring no longer says callers must wrap in try/except.

## Guardrail call-outs

These are real and apply to this work. Each call-out below is a contract the executor must honor.

### Spec-Conflict Guardrail (CLAUDE.md)

This refactor touches shipped behavior:
- The session-summary write contract (Validated v0.2 "Session summary written to vault after each interaction") changes from "route catches and logs" to "client swallows and logs" — same observable behavior (no 5xx on vault failure, summary written when vault is up), different layering. Operator consent for this layering change was given in the grilling session and is recorded in `docs/adr/0001-sentinel-persona-source.md`.
- The Sentinel persona is now Vault-sourced rather than hardcoded — operator consent recorded in the same ADR.
- The startup contract gains one strict failure mode (Obsidian up + persona file missing → fail). Operator consent recorded in the ADR.

The executor does not need to re-ask for consent on these. If the executor encounters any *other* shipped behavior at risk during the work (e.g. a route returning a different HTTP code, a previously-passing test changing meaning), STOP and surface — do not silently change.

### Test-Rewrite Ban (CLAUDE.md)

Two test rewrites are in-scope and pre-authorized:

1. **`test_post_message_uses_message_processor_factory_when_present`** (Task 6): the factory seam is being removed. The test protects an obsolete contract. Rewrite as `test_post_message_uses_app_state_processor`. Document this in the Task 6 commit message.
2. **Any test in `test_obsidian_client.py` that asserts `write_session_summary` raises on backend failure** (Task 1): the raise-on-failure contract is being replaced by swallow-and-log. Rewrite those assertions to expect `None` + a logged warning. Document this in the Task 1 commit message.

No other test rewrites are authorized. If any other previously-passing test starts failing during this work, STOP and surface it — do not weaken or skip it. The seven `test_*.py` files listed under "Delete" are deletions of tests for deleted modules, not rewrites of tests for shipped contracts; they are in-scope.

### Behavioral-Test-Only (CLAUDE.md)

The new `tests/test_message_processor.py` (Task 7) must:
- Call `processor.process()` in every test.
- Assert on observable results: return value, raised exception's `.code`, recorded calls on the fakes, `caplog` records.
- Never `grep` source code. Never `assert True` or `assert x == x`. Never assert only `mock.assert_called_with(...)` without an accompanying behavioral assertion.

If any scenario above turns out to be impractical to express as a strict behavioral test (e.g. a private method's behavior that's only observable through a 5-step setup), STOP and surface the specific case — do not paper over with a vacuous assertion.
