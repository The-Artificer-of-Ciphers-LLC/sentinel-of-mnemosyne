---
name: block-litellm-prefix-bug
enabled: true
event: file
action: block
conditions:
  - field: file_path
    operator: regex_match
    pattern: (sentinel-core|modules/pathfinder|shared/sentinel_shared).*\.py$
  - field: file_path
    operator: not_contains
    pattern: model_selector.py
  - field: file_path
    operator: not_contains
    pattern: resolve_model.py
  - field: new_text
    operator: regex_match
    pattern: if\s+["']/["']\s+not\s+in\s+(model_id|model_name|model_string|chosen)
---

🚫 **LiteLLM provider-prefix bug class detected**

The pattern `if "/" not in <model_var>` shipped a runtime bug **three times in one day** (2026-04-27) — pathfinder, sentinel-core, and the note classifier each carried their own copy. The guard fails on HuggingFace-style model IDs like `qwen/qwen2.5-coder-14b` because the `/` is a model-family separator, not a litellm provider tag, and litellm rejects the call with `LLM Provider NOT provided`.

**Use the canonical helpers instead:**

```python
# sentinel-core
from app.services.model_selector import ensure_litellm_prefix, strip_litellm_prefix

# pathfinder
from app.resolve_model import strip_litellm_prefix  # plus resolve()/resolve_model_profile()
```

`ensure_litellm_prefix(model_id)` checks `startswith()` against the full set of known litellm provider tags (`openai/`, `ollama/`, `anthropic/`, plus 11 more) — HF namespaces pass through unchanged and bare names get the `openai/` default.

`strip_litellm_prefix(model_id)` removes only those known tags, preserving HF namespaces (needed when calling LM Studio's `/api/v0/models/{id}` which wants the bare ID).

**Context:** `.planning/quick/260427-vl1-note-import-vault-sweeper/260427-vl1-SUMMARY.md` (the four-hotfix chain that surfaced this), `.planning/reviews/2026-04-27-dry-audit.md` (H-1 finding).

If you have a legitimate need for the literal pattern (a test asserting the bug's symptom, for example), add a `# noqa: hookify-block-litellm-prefix-bug` comment on the same line and re-run.
