---
status: abandoned
abandoned_date: 2026-04-27
reason: |
  User clarified the original intent was vault import/cleanup ONLY, with the
  v0.2-shipped 2nd-brain auto-write behavior preserved unchanged. This task
  proposed a chat-path tool-use restoration which would have CHANGED chat
  behavior — that was scope creep, not what was asked for.

  The auto-file gap surfaced earlier today is real but should be addressed
  by running the existing vault sweeper (vl1) against the live vault to
  retroactively classify, NOT by injecting tool-use into the chat path.

  The original work in this directory (CONTEXT + RESEARCH) is preserved
  for forensic reference. Do not resume without an explicit operator
  decision logged in PROJECT.md "Key Decisions".
---

# Quick Task 260427-opl: Restore Tool-Use to Chat Path - Context

**Gathered:** 2026-04-27
**Status:** Decisions locked, ready for research

<domain>
## Task Boundary

Restore tool-use loop to sentinel-core's `/message` chat path. The user message that triggered this debug session ("finished day 19 of the 30 day bass level 2 course") got a generic "here's how YOU could organize this" reply because the chat LLM has no tools — it can only emit text, not call into the system. Pi was the original tool-use mediator and got bypassed in Phase 25; the chat path was simplified to a single litellm call and lost the capability.

Path C from tonight's design discussion: give the chat LLM tools (`file_note`, `search_vault`, `recall_recent_sessions`) so it can decide inline to file events, fetch context, etc. The existing `:note`/`:inbox`/`:vault-sweep` slash commands keep working as explicit triggers.

</domain>

<decisions>
## Implementation Decisions (Locked)

### Tool kit at v1 (Q1 → B + auto-link expansion)

**Four tools exposed.** The `link_related` addition closes the auto-link gap surfaced during the post-vl1 product-design audit (PROJECT.md core value: "what mattered gets written" + REQUIREMENTS.md SES-02: "automatically tag and link").

- **`file_note(content: str, suggested_topic: str | None = None)`** — wraps existing `classify_note()` + filer. **Auto-chains to `link_related` on success** so a single LLM tool call gets file + link without the LLM needing to call both. Returns `{"action": "filed"|"inboxed"|"dropped", "path": str|None, "topic": str, "confidence": float, "links": ["path1", "path2", ...] | []}`.
- **`search_vault(query: str, limit: int = 5)`** — wraps existing `obsidian.search_vault()`. Returns array of `{"path", "snippet", "score"}`.
- **`recall_recent_sessions(limit: int = 3)`** — wraps existing `obsidian.get_recent_sessions(user_id, limit)`. Returns the same recent-session strings already injected as warm-tier context today.
- **`link_related(note_path: str, max_links: int = 3, threshold: float = 0.75)`** — finds the top-N existing notes most similar to the target by embedding cosine similarity, inserts a `## Related` section at the bottom of the note with `[[wiki-link]]` entries, and writes the result back via Obsidian PUT. Reuses the embedding service vl1 added for the sweeper. Returns `{"linked": ["path1", "path2", ...], "skipped_below_threshold": int}`.

**Threshold note:** `link_related` uses a lower cosine threshold (0.75) than the sweeper's de-dup pass (0.92). De-dup wants "essentially the same"; linking wants "related enough to surface." Tunable via the kwarg.

**Auto-link is automatic, not optional.** When `file_note` succeeds with `action=filed`, the filer immediately invokes `link_related` on the new path. The LLM does not need to call both — the chain happens server-side. The LLM gets a single tool result with both `path` and `links` populated. This delivers the spec's "auto-file AND link" behavior in a single LLM tool call.

Out of scope for v1: `update_note`, `move_to_trash`, `vault_sweep`, NPC operations, anything pf2e. Those can land as a v2 expansion.

### Filing flow (Q2 → A)

Fire-and-forget. When the LLM calls `file_note`, the tool runs synchronously, the result is fed back into the LLM, and the LLM's final natural-language reply mentions the filing (e.g. "Filed under `accomplishments/...`"). No separate confirm-yes/no round trip.

This matches the existing `:note` behavior — explicit notes also fire-and-forget. Confirm flow can be a v2 if it turns out the LLM mis-files too often.

### Tool-use loop iteration cap

Max 5 iterations. After 5, force-terminate with whatever text content the LLM has produced. Prevents runaway loops if the LLM keeps calling tools without converging.

### Model capability fallback

If the active model's `supports_function_calling` capability flag is false, the chat path skips tool injection entirely and falls back to today's plain-LLM behavior. Verified via `model_selector.py`'s existing capability metadata. qwen2.5-coder-14b — the current default — supports function calling per its model card.

### Coexistence with slash commands

`:note`, `:inbox`, `:vault-sweep` keep working unchanged. Tool-use is additive. The user can still bypass the LLM and file directly via `:note` if they want full control.

### Streaming

Non-streaming for v1. Tool-use with streaming is messy (chunked tool_calls assembly); single-pass loop is fine. Streaming can land as v2 if response latency becomes painful.

### System prompt update

The chat path's system prompt (`message.py:137-142`) gets updated to advertise the tools and instruct the LLM not to lecture the user about note organization:

> "You are the Sentinel — the user's 2nd brain. You have tools available: `file_note` to save events/facts/completions the user mentions, `search_vault` to retrieve relevant existing notes, and `recall_recent_sessions` to see recent conversation history. When the user shares something note-worthy (a completion, milestone, fact, accomplishment, journal-style reflection), call `file_note` directly — do not lecture them about how to organize their own notes. Respond naturally; only describe internal tools when the user asks."

### Auto-classify Q4=B is now superseded

Yesterday's Q4=B "implicit messages stay transcript-only" decision was correct given the tool-less architecture, but is now superseded by tool-use: implicit messages still don't run a separate classifier pass, but the LLM in the chat path can autonomously decide to call `file_note`. The transcript-only path becomes the FALLBACK when the LLM doesn't call any tools.

</decisions>

<specifics>
## Specific References

- `sentinel-core/app/routes/message.py:202-206` — current chat call site (must change)
- `sentinel-core/app/clients/litellm_provider.py::complete()` — must accept `tools=` param
- `sentinel-core/app/services/note_classifier.py` — `classify_note()` is the engine; tool wrapper just calls it
- `sentinel-core/app/services/model_selector.py:177-179` — `supports_function_calling` capability check (already in model registry)
- `shared/sentinel_shared/llm_call.py::acompletion_with_profile` — pass-through `**extra` accepts `tools`/`tool_choice`; no wrapper changes needed
- litellm tool-use docs: https://docs.litellm.ai/docs/completion/function_call

</specifics>

<canonical_refs>
## Canonical References

- `.planning/quick/260427-vl1-note-import-vault-sweeper/260427-vl1-SUMMARY.md` — original `:note` feature; tools wrap its services
- `.planning/sketches/note-import-and-vault-sweeper.md` — original sketch (Q4 was here)
- Project memory `Architecture Crisis — Pi harness bypassed` — context for why tool-use was lost

</canonical_refs>
