# Quick Task 260426-2x1: Model Profile Library — Research

**Researched:** 2026-04-26
**Domain:** LLM model-specific parameters, LM Studio API, litellm integration
**Confidence:** HIGH (codebase verified, LM Studio API docs verified, Qwen2.5 HF model card verified)

---

## Summary

The goal is a model profile library that knows model-specific inference parameters (stop sequences,
context window, chat template family, capability flags) for common models, auto-discovers what it can
from LM Studio at runtime, and exposes a clean lookup API to the rest of the stack.

**Key finding:** LM Studio applies the chat template server-side automatically when using the
`/v1/chat/completions` endpoint — callers send standard `messages: [{role, content}]` objects and do
NOT need to manually inject `<|im_start|>` / `<|im_end|>` tokens. The critical thing LM Studio does
NOT expose via its API is stop sequences. Those must be supplied by the caller or inferred from the
model family. This is the main gap the profile library fills.

**Primary recommendation:** Ship `model_profiles.py` as a shared module that (1) pattern-matches
model IDs to a family profile, (2) fetches `arch` from LM Studio `/api/v0/models/{id}` to resolve
ambiguities, and (3) exposes `get_profile(model_id, api_base)` returning a `ModelProfile` dataclass.
Place it in both `modules/pathfinder/app/` and `sentinel-core/app/services/` (they are separate
containers with separate Python paths — no shared library mechanism exists yet).

---

## 1. Qwen2.5-Coder-14B — What the Caller Must Know

### Chat Template
Qwen2.5-Coder-14B-Instruct uses **ChatML format**. [VERIFIED: huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct]

```
<|im_start|>system
You are Qwen, created by Alibaba Cloud. You are a helpful assistant.<|im_end|>
<|im_start|>user
{user message}<|im_end|>
<|im_start|>assistant
```

**LM Studio handles this automatically.** When calling `/v1/chat/completions` with structured
`messages`, LM Studio reads the chat template from the GGUF metadata and applies it. The caller
sends plain OpenAI-format messages. [VERIFIED: lmstudio.ai/docs/app/advanced/prompt-template]

### Stop Sequences
Two stop tokens are relevant: [VERIFIED: QwenLM/Qwen3 GitHub issue #927 + llama.cpp issue #9606]

| Token | ID | When it fires |
|-------|----|---------------|
| `<\|im_end\|>` | 151645 | End of any role turn in ChatML (primary stop for instruct) |
| `<\|endoftext\|>` | 151643 | EOS in base models; also fires in instruct generation in some runtimes |

**Recommendation:** Pass `stop=["<|im_end|>", "<|endoftext|>"]` to `litellm.acompletion()` for Qwen
instruct models. LM Studio should handle termination via the embedded chat template, but explicit
stop sequences are a safety net against runaway generation where the model echoes the next turn.
Neither sentinel-core's `LiteLLMProvider.complete()` nor pathfinder's `llm.py` pass stop sequences
today — this is the gap. [VERIFIED: codebase grep confirmed zero stop= kwargs across all
acompletion call sites]

### Context Window
- **Model-declared maximum:** 131,072 tokens (128K)
  [VERIFIED: huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct]
- **Default config (tokenizer_config.json max_position_embeddings):** 32,768 tokens
- **LM Studio loaded context:** LM Studio may cap at the GGUF metadata value, typically 32,768 for
  Q4_K_M variants unless the user explicitly sets a higher context in the LM Studio UI.
  The `/api/v0/models/{id}` `max_context_length` field reflects what is currently loaded.
- **Seed file today:** `qwen2.5:14b` is seeded at 32,768 in `models-seed.json`. This is correct
  for the Ollama GGUF default but may differ from what LM Studio loads.

### System Prompt Support
Yes — Qwen2.5-Coder-14B-Instruct natively supports system prompts via the ChatML `system` role.
[VERIFIED: HF model card, default system prompt is "You are Qwen, created by Alibaba Cloud..."]

### litellm.get_model_info() for local models
`litellm.get_model_info("qwen2.5-coder-14b")` returns nothing useful for bare local model IDs —
litellm's internal model cost map only covers known cloud-hosted models. For LM Studio models
prefixed `openai/`, it falls through to generic OpenAI defaults. The `_score()` function in
`model_selector.py` already handles this gracefully (returns 0 on exception). [ASSUMED — based on
reading the existing code path; verified that litellm does not know about arbitrary local model IDs]

---

## 2. LM Studio Auto-Discovery — What the API Provides

### Available Endpoints (verified)
[VERIFIED: lmstudio.ai/docs/developer/rest/endpoints]

| Endpoint | Returns |
|----------|---------|
| `GET /api/v0/models` | All downloaded models (loaded + not-loaded) |
| `GET /api/v0/models/{model_id}` | Single model details |
| `GET /v1/models` | OpenAI-compat — loaded models only |

### `/api/v0/models/{id}` Response Fields
```json
{
  "id": "qwen2.5-coder-14b-instruct",
  "object": "model",
  "type": "llm",
  "publisher": "qwen",
  "arch": "qwen2",
  "compatibility_type": "gguf",
  "quantization": "Q4_K_M",
  "state": "loaded",
  "max_context_length": 32768
}
```

**The `arch` field is the key.** It gives us a family string (`qwen2`, `llama`, `mistral`,
`gemma2`, `phi3`, etc.) directly from LM Studio without any string parsing. The profile library
should use this to look up the right family profile, then fall back to model ID substring matching
if the `/api/v0/models/{id}` call fails. [VERIFIED: lmstudio.ai/docs/developer/rest/endpoints]

**Not available via API:** chat_template text, stop token IDs, capability flags (tool use,
vision). These must be inferred from the arch family.

### Architecture → Family Mapping
Based on LM Studio docs and the arch strings visible in their API examples:

| LM Studio `arch` | Family | Stop Sequences | Context (typical default) |
|------------------|--------|----------------|--------------------------|
| `qwen2`, `qwen2_5`, `qwen2_vl` | Qwen2.x | `<\|im_end\|>`, `<\|endoftext\|>` | 32768 (128K capable) |
| `llama` | Llama 2 | `[INST]`, `[/INST]`, `</s>` | 4096 |
| `llama3`, `llama3_1`, `llama3_2` | Llama 3.x | `<\|eot_id\|>`, `<\|end_of_text\|>` | 8192–128K |
| `mistral`, `mistral_nemo` | Mistral | `[INST]`, `[/INST]`, `</s>` | 32768 |
| `gemma2`, `gemma3` | Gemma | `<end_of_turn>` | 8192 |
| `phi3`, `phi3_5` | Phi-3/3.5 | `<\|end\|>`, `<\|endoftext\|>` | 4096–131072 |
| `deepseek2` | DeepSeek | `<\|end▁of▁sentence\|>` | 32768 |

[ASSUMED for the full table — `qwen2` arch string confirmed via LM Studio docs example;
other arch strings are training-knowledge inference, not verified from a canonical list.
The implementation should treat all non-qwen2 entries as ASSUMED defaults pending live
LM Studio testing.]

---

## 3. Profile Library Design

### ModelProfile Dataclass

```python
@dataclass
class ModelProfile:
    family: str                      # e.g. "qwen2", "llama3", "mistral"
    stop_sequences: list[str]        # caller passes these to acompletion(stop=...)
    context_window: int              # tokens; runtime fetch from LM Studio overrides this
    supports_system_prompt: bool
    chat_template_format: str        # "chatml" | "llama2" | "llama3" | "mistral" | "gemma" | "phi3"
    task_kind_caps: list[str]        # ["chat", "structured", "fast"] — what this family is good for
    notes: str = ""
```

### Profile Resolution Order

```
get_profile(model_id, api_base=None) → ModelProfile

1. Exact match in KNOWN_PROFILES dict (keyed by bare model ID)
2. LM Studio /api/v0/models/{model_id} → arch → arch_to_family → FAMILY_PROFILES[family]
   (only if api_base provided)
3. Substring pattern match on model_id (qwen → qwen2, llama-3 → llama3, etc.)
4. Return SAFE_DEFAULT profile (conservative: no stop sequences, 4096 context)
```

Step 2 is the auto-discovery hook — it uses what LM Studio actually knows about the loaded
model's architecture. Steps 3 and 4 are pure string-matching fallbacks for when LM Studio
is unreachable or the model ID string doesn't hit an arch entry.

### Where It Lives

Both `modules/pathfinder/app/model_profiles.py` and `sentinel-core/app/services/model_profiles.py`
need the file. The two containers are isolated Python environments with no shared package — there
is no existing shared library mechanism. Copy is the correct approach for now.

The file is ~100 lines of pure data + one async lookup function. Duplication is tolerable.
If a shared package is introduced later (v0.6+), this is a natural candidate to move there.

### Integration: resolve_model.py (pathfinder)

`resolve_model()` currently returns just the model string. It should optionally also return
the profile, OR a companion `resolve_model_profile(model_id, api_base)` function should exist
that call sites invoke after `resolve_model()`. The profile is not needed for every call — only
calls that want to pass `stop=` or check context window. A separate function avoids a breaking
change to the existing `resolve_model()` signature.

### Integration: LiteLLMProvider (sentinel-core)

`LiteLLMProvider.complete()` builds a `kwargs` dict and calls `litellm.acompletion(**kwargs)`.
The cleanest integration: accept an optional `stop: list[str] | None = None` parameter in
`complete()`, pass it through to kwargs if provided. Call sites that want model-aware stop
sequences fetch the profile and pass it explicitly. This keeps the provider generic.

### Integration: pathfinder llm.py

All 9 `litellm.acompletion()` call sites in `llm.py` build their own `kwargs` dicts inline.
Stop sequences should be added to kwargs at each call site once a profile lookup helper exists.
The simplest pattern: a module-level `_get_stop_sequences(model: str, api_base: str | None)`
that calls `get_profile()` synchronously (profiles are cached after first async fetch).

---

## 4. litellm.get_model_info() — What It Actually Returns for Local Models

`litellm.get_model_info(model="openai/qwen2.5-coder-14b")` returns generic OpenAI defaults
(max_tokens=4096, supports_function_calling=True) because litellm's model cost map does not
contain local LM Studio model IDs. The `_score()` function in both `model_selector.py` copies
already handles this correctly by catching the exception and returning 0. The profile library
is NOT a replacement for `get_model_info()` — it is orthogonal: `get_model_info` is used for
scoring/selection; the profile library is used for inference-time parameter passing.

---

## 5. Pitfalls

**Pitfall 1: Stop sequences vs. chat template — double-applying**
LM Studio applies the chat template server-side. If you also manually inject `<|im_start|>` tokens
into the message content, the model sees them twice. Do NOT put ChatML tokens in message content —
use the standard `messages` array only.

**Pitfall 2: Qwen base vs. instruct — different EOS**
`qwen2.5-coder-14b` (base) uses `<|endoftext|>` (151643) as EOS; the instruct variant uses
`<|im_end|>` (151645). If LM Studio loads the base model without the instruct suffix, the profile
must use a different stop list. The `/api/v0/models/{id}` response does not distinguish base vs.
instruct — this must be inferred from the model ID string (presence of "instruct" or "-it").

**Pitfall 3: context_window from LM Studio vs. model max**
`max_context_length` in the LM Studio API reflects what is **loaded**, not the model's theoretical
maximum. A user running Q4_K_M with default settings sees 32768 even though the model supports 128K.
The profile library should use the LM Studio-fetched value for context budgeting (it's what the
server actually accepts), not the model's theoretical max.

**Pitfall 4: Profile cache invalidation**
If the user swaps models in LM Studio without restarting the container, the profile cache is stale.
The existing `force_refresh=True` pattern in `model_selector.py`'s `get_loaded_models()` applies
here too. Use the same cache-per-api_base pattern with a `force_refresh` escape hatch.

---

## 6. Call Site Inventory (Stop Sequences Gap)

Neither container currently passes stop sequences. All `acompletion` calls verified:

| File | Call sites | Stop sequences passed? |
|------|-----------|----------------------|
| `sentinel-core/app/clients/litellm_provider.py` | 1 | No |
| `modules/pathfinder/app/llm.py` | 9 | No |
| `modules/pathfinder/app/foundry.py` | 1 | No |

For the sentinel-core `LiteLLMProvider`, stop sequences matter most when `ai_provider=lmstudio`
and a Qwen or Llama3 model is loaded. With Claude or Ollama, the server handles termination
correctly without explicit stop sequences. So the integration is only strictly necessary for the
LM Studio path, but a clean design passes it at every call site and lets it be `None` for cloud
providers.

---

## Assumptions Log

| # | Claim | Risk if Wrong |
|---|-------|---------------|
| A1 | LM Studio applies chat template server-side for /v1/chat/completions | If wrong, Qwen responses will have garbled role-boundary tokens in content; trivially detectable in testing |
| A2 | arch strings for non-Qwen families (llama3, mistral, gemma2, phi3) are as listed | If wrong, family lookup falls through to substring match or safe default — no hard failure |
| A3 | litellm.get_model_info returns nothing useful for local model IDs | If wrong, could use it as a stop-sequence source; current code already guards against this |

---

## Sources

### PRIMARY (HIGH confidence)
- [LM Studio REST API v0 Endpoints](https://lmstudio.ai/docs/developer/rest/endpoints) — confirmed `arch` field in model response; confirmed no `chat_template` field returned
- [LM Studio Prompt Template docs](https://lmstudio.ai/docs/app/advanced/prompt-template) — server-side template application confirmed
- [Qwen/Qwen2.5-Coder-14B-Instruct HF model card](https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct) — context window 131072, ChatML format, system prompt support
- Codebase (`modules/pathfinder/app/llm.py`, `sentinel-core/app/clients/litellm_provider.py`) — confirmed zero stop= kwargs in all acompletion call sites

### SECONDARY (MEDIUM confidence)
- [QwenLM/Qwen3 GitHub issue #927](https://github.com/QwenLM/Qwen3/issues/927) — token ID 151643 `<|endoftext|>` vs 151645 `<|im_end|>` inconsistency documented
- [llama.cpp issue #9606](https://github.com/ggml-org/llama.cpp/issues/9606) — Qwen2.5-Coder FIM stop token behavior
- [Ollama qwen2.5-coder:14b](https://ollama.com/library/qwen2.5-coder:14b) — default system prompt, FIM template tokens

### ASSUMED (LOW confidence)
- Non-Qwen arch string names for LM Studio response (`llama3`, `gemma2`, `phi3`, `deepseek2`) — not verified against a live LM Studio instance
