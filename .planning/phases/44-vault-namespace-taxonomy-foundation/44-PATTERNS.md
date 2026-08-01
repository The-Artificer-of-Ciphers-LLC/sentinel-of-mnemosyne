# Phase 44: Vault Namespace + Taxonomy Foundation - Pattern Map

**Mapped:** 2026-07-06
**Files analyzed:** 8 (all edits; no wholly-new files except possibly a small taxonomy-consumer import in `recall.py`, per D-03b discretion)
**Analogs found:** 8 / 8 (this phase edits existing files; each file's own established local conventions are its own best analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `sentinel-core/app/services/note_classifier.py` (`TOPIC_VAULT_PATH`, `topic_dir_for()`) | utility / routing-table | transform (pure, no I/O) | itself — single source-of-truth table already exists; extend in place | exact |
| `sentinel-core/app/services/vault_sweep_plan.py` (`is_in_topic_dir()`, `propose_topic_move()`) | service / planner | transform, consumes routing table | `propose_topic_move()`'s own existing lazy-import-of-`topic_dir_for` idiom | exact — reuse own pattern |
| `sentinel-core/app/services/vault_sweeper.py` (`SWEEP_SKIP_PREFIXES`, `_active_skip_prefixes()`) | service / config-gated denylist | batch (vault walk) | itself — module-constant + settings-override + backstop-function shape | exact |
| `sentinel-core/app/config.py` (`sweep_skip_prefixes`) | config | CRUD (settings) | itself — existing `Settings` field with inline comment convention | exact |
| `sentinel-core/app/services/recall.py` (`_CARRIER_NAMESPACE_PREFIXES`, warm-tier recency block, `_WARM_TIER_EXCLUDE_PREFIXES`, self-path stub-ensure) | service | request-response (recall assembly) + new file-I/O (stub-create) | `note_intake.classify_and_apply`'s `INBOX_PATH` read-then-conditionally-write (for the new stub-ensure code); `vault_sweep_plan.propose_topic_move`'s lazy import (for D-03b coupling) | role-match (mixed: two different sub-patterns borrowed) |
| `sentinel-core/app/services/note_intake.py` (`_topic_target_path()` journal literal, `_safe_file_chat_note` redirect decision) | service | request-response / file-I/O | itself — `classify_and_apply`'s existing `INBOX_PATH` lazy-create block is the reference shape for any other stub-style write in this phase | exact |
| `sentinel-core/app/vault.py` (`PROTECTED_NAMESPACES`) | config / guard | request-response (path-guard predicate) | itself — additive tuple entry, segment-boundary-matched | exact |
| Test files (`test_recall.py`, `test_vault_sweep_plan.py`, `test_vault_sweeper.py`, `test_message.py`, `test_note_classifier.py`) | test | request-response / unit | existing sibling tests in the same file (see per-file excerpts below) | exact |

## Pattern Assignments

### `sentinel-core/app/services/vault_sweeper.py` — module-constant + settings-override + backstop (D-02 removal target, and the shape D-03b should mirror)

**Analog:** itself, lines 69-92 (already the canonical shape in this codebase)

```python
# vault_sweeper.py:69-80
SWEEP_SKIP_PREFIXES: tuple[str, ...] = (
    "_trash/",
    "pf2e/",
    "ops/sessions/",
    "ops/sweeps/",
    "inbox/",
)
"""Module-level fallback default. The runtime denylist is read from
``settings.sweep_skip_prefixes`` via ``_active_skip_prefixes()`` so operators
can extend it via env without code change. This constant is preserved as a
backstop in case settings import fails (and to keep the existing public
import surface stable for callers that referenced it directly)."""


def _active_skip_prefixes() -> tuple[str, ...]:
    """Return the live skip-prefix tuple from settings, falling back to the
    module-level default if settings is unimportable (e.g. during isolated
    unit tests of the helpers).
    """
    try:
        from app.config import settings
        return tuple(settings.sweep_skip_prefixes)
    except Exception:
        return SWEEP_SKIP_PREFIXES
```

**How to apply (D-02):** Remove `"inbox/"` from both this tuple (line 74) AND `config.py`'s `sweep_skip_prefixes` (line 150, see below) — same task/commit, both edits or neither, per the dual-maintenance shape this pattern itself embodies (settings overrides the constant at runtime; leaving only one edited produces divergent behavior between settings-present and settings-absent code paths).

**Config counterpart** (`sentinel-core/app/config.py:137-152`):
```python
sweep_skip_prefixes: tuple[str, ...] = (
    "_trash/",
    "pf2e/",            # legacy entry — covered by `mnemosyne/` for the
                        # actual NPC path; kept for defense-in-depth and
                        # to avoid weakening the shipped denylist.
    "mnemosyne/",       # covers mnemosyne/pf2e/, mnemosyne/self/, etc.
    "core/",
    "self/",
    "templates/",
    "archive/",
    "security/",
    "ops/sessions/",
    "ops/sweeps/",
    "inbox/",
    ".obsidian/",
)
```
Both tuples list `inbox/` today; both must drop it. Follow the existing inline-comment convention (each entry explains *why* it's there) when editing — add a one-line comment at the removal site explaining D-02, not just a silent deletion, so a future reader doesn't reintroduce it by "restoring symmetry."

**D-03b shared-source-of-truth extraction should mirror this exact shape**: a module-level constant/table in `note_classifier.py` (`TOPIC_VAULT_PATH`) is already the "module-level default"; `recall.py` should gain its own thin accessor analogous to `_active_skip_prefixes()` (or simply import `TOPIC_VAULT_PATH`/`topic_dir_for` directly) rather than re-declaring a second hardcoded tuple. Do NOT invent a settings-override layer for the taxonomy table — that is out of scope; only the skip-prefix mechanism needs the settings indirection, because operators tune it via env. The taxonomy table has no such requirement.

---

### `sentinel-core/app/services/vault_sweep_plan.py` — lazy-import single-source-of-truth consumption (the D-03b template)

**Analog:** itself, `propose_topic_move()` (already does this correctly)

```python
# app/services/vault_sweep_plan.py:41-53 (per RESEARCH.md verified excerpt)
def propose_topic_move(
    src_path: str, topic: str, *, today: str | None = None
) -> str | None:
    """Return the destination path a topic move would use."""
    from app.services.note_classifier import topic_dir_for   # import at call time

    topic_dir = topic_dir_for(topic, today=today)
    if not topic_dir:
        return None
    if is_in_topic_dir(src_path, topic_dir):
        return None
    filename = src_path.rsplit("/", 1)[-1]
    return f"{topic_dir}/{filename}"
```

**How to apply (D-03b in `recall.py`):** `recall.py` should import from `note_classifier` the same way — either `from app.services.note_classifier import TOPIC_VAULT_PATH` at module level (no circular-import risk confirmed — `note_classifier.py`'s own imports are `app.config`, `app.services.model_selector`, `sentinel_shared.llm_call`, `sentinel_shared.model_profiles`, none of which import `recall.py`), or lazily inside the function if module-level import order is ever a concern. Since D-01 collapses `_CARRIER_NAMESPACE_PREFIXES` to the empty set entirely (no consumer left, block removed), D-03b's practical scope in `recall.py` is narrower than in `vault_sweep_plan.py`: primarily reconciling `_WARM_TIER_EXCLUDE_PREFIXES` (line 51) with `RecallConfig.exclude_prefixes` (line 247) so a second drift-prone duplicate doesn't survive next to the one being fixed.

**`is_in_topic_dir()` family-root fix (Pitfall 2)** — current buggy single-segment truncation vs. the fix:
```python
# CURRENT (buggy under shared ops/ parent):
family_root = topic_dir.split("/", 1)[0] + "/"

# FIX:
def is_in_topic_dir(path: str, topic_dir: str) -> bool:
    if not topic_dir:
        return False
    if topic_dir.startswith("ops/journal/"):
        family_root = "ops/journal/"          # nested-date family, any day matches
    else:
        family_root = topic_dir.rstrip("/") + "/"   # exact-match family
    return path.startswith(family_root)
```

---

### `sentinel-core/app/services/note_intake.py` — D-14 lazy-create-if-missing through the REST-only Vault seam (the reusable shape for D-04 self/ stubs)

**Analog:** `classify_and_apply()`, lines 53-63 (exact excerpt, read this session)

```python
# note_intake.py:53-63
if result.topic == "unsure" or result.confidence < 0.5:
    body = await self._vault.read_note(INBOX_PATH)
    if not body or not body.strip():
        body = build_initial_inbox()
    new_body = append_entry(
        body,
        content,
        result,
        suggested=[result.topic] if result.topic != "unsure" else [],
    )
    await self._vault.write_note(INBOX_PATH, new_body)
    return {
        "action": "inboxed",
        "topic": result.topic,
        "confidence": result.confidence,
        "path": INBOX_PATH,
    }
```

**Shape to copy for D-04 (`self/*.md` stub creation):**
1. `body = await self._vault.read_note(path)`
2. `if not body or not body.strip(): body = build_self_stub(path)` — a **pure**, no-I/O builder function (mirrors `build_initial_inbox()` in `app/services/inbox.py`), token-bounded per D-04's discretion note
3. `await self._vault.write_note(path, body)` — this is the entire "lazy create" mechanism; `write_note`'s underlying transport is an unconditional `PUT /vault/{path}` (confirmed at `vault.py:507-515`), and Obsidian's Local REST API creates-if-missing on PUT. **No local-fs existence check anywhere — REST PUT is the primitive.**

**Where to wire it (per RESEARCH.md guidance):** at the call site inside `Recall` where `RecallConfig.self_paths` are gathered (recall.py, inside `Recall.assemble()`'s self-context loop) — NOT inside `read_self_context()` itself. `read_self_context()` (vault.py:367-386) is deliberately read-only and silently returns `""` on 404; do not change its contract. Add a small dedicated wrapper/method that composes `read_note` + conditional `write_note`, called once per `self_paths` entry, keeping `read_self_context`'s existing graceful-skip behavior for any other callers untouched.

**Journal-literal fix to land in the same file/commit (Pitfall 1):**
```python
# note_intake.py:150 BEFORE
return f"journal/{today}/{slug}.md"     # hardcoded, ignores TOPIC_VAULT_PATH["journal"]

# AFTER
return f"{base}/{today}/{slug}.md"      # derives from the dict value already fetched into `base`
```
Apply identically in `note_classifier.py`'s `topic_dir_for()` (same bug, same fix shape) — both must land together with the `TOPIC_VAULT_PATH["journal"]` dict-value edit, per RESEARCH.md's Execution-Ordering Hazard #1.

**`_safe_file_chat_note` / `searchable_only` redirect (D-06) — full current logic to retire, lines 75-82:**
```python
# For the chat-sourced filing path, guarantee the note lands on a
# warm-tier-searchable path.  If the resolved destination starts with
# any excluded prefix (e.g. "observation" → "ops/observations/…"),
# redirect to a journal entry for today so the content stays findable.
if searchable_only and target.startswith(_WARM_TIER_EXCLUDE_PREFIXES):
    target = await self._resolve_target_with_collision_suffix(
        "journal", result.title_slug or "untitled"
    )
```
D-06 removes this block entirely (the redirect target, `journal`, is itself excluded post-D-03, so the guarantee is structurally unsatisfiable). Also drop the now-unused `_WARM_TIER_EXCLUDE_PREFIXES` import at line 24 once nothing in this file references it, or repoint it if `recall.py`'s reconciliation keeps the name alive as an alias for `RecallConfig.exclude_prefixes`.

---

### `sentinel-core/app/services/recall.py` — carrier allowlist removal (D-01) and warm-tier exclude reconciliation

**Analog:** itself, lines 46-72 (module-level constants) and the warm-tier recency block (~L795-819)

```python
# recall.py:51 — the SECOND, narrower, stale duplicate (Pitfall 3 root cause)
_WARM_TIER_EXCLUDE_PREFIXES = ("ops/", "_trash/", "self/")   # missing "inbox/"

# recall.py:67-72 — the allowlist D-01 removes entirely
_CARRIER_NAMESPACE_PREFIXES: tuple[str, ...] = (
    "journal/",
    "learning/",
    "accomplishments/",
    "references/",
)
```

**D-01 removal pattern (BEFORE → AFTER), from RESEARCH.md's verified Code Examples section:**
```python
# BEFORE — inside the warm-tier assembly
for r in merged:
    if r.path.startswith(_CARRIER_NAMESPACE_PREFIXES):
        date_str = _path_date(r.path)
        w = recency_weight(date_str if date_str is not None else "", now=now)
        reweighted.append(SearchResult(path=r.path, score=r.score * w, body=r.body))
    else:
        reweighted.append(r)
reweighted.sort(key=lambda r: (-r.score, r.path))

# AFTER — D-01: no carrier namespaces survive migration
reweighted = merged
reweighted.sort(key=lambda r: (-r.score, r.path))  # tie-break stays deterministic
```
Also delete `_CARRIER_NAMESPACE_PREFIXES` and `_path_date()` (dead code, no other caller). **Do not remove `recency_weight()` itself** — still used by the hot-tier session sort (~L747, MEM-09 place (a)).

**Reconciliation target for `_WARM_TIER_EXCLUDE_PREFIXES` vs `RecallConfig.exclude_prefixes` (line 247, confirmed already includes `inbox/`):** either delete `_WARM_TIER_EXCLUDE_PREFIXES` and repoint its one remaining consumer (`note_intake.py`, if D-06 doesn't remove the need entirely) to import `RecallConfig.exclude_prefixes`, or update the tuple literal to match. Prefer deletion — this is exactly the dual-source-of-truth shape the phase exists to close, per Pitfall 3.

---

### Test files — module-level constant/singleton patching convention

The existing test suite patches module-level singletons/constants directly rather than using DI containers. Use this same convention for the phase's new Wave-0 characterizing tests:

- **Pattern:** `patch('app.services.<module>.<CONSTANT_OR_SINGLETON>', ...)` or direct call against the pure function with a monkeypatched settings object, matching how `test_vault_sweeper.py::test_sweep_skip_prefixes_constant` (L462-467) and `test_vault_sweep_plan.py::test_plan_topic_move_skips_existing_topic_family` (L23-25) already assert against the live constants/functions directly (no additional mocking layer needed for pure functions like `topic_dir_for`, `is_in_topic_dir`, `propose_topic_move`).
- **For vault-backed tests** (`self/` stub creation, `INBOX_PATH` writes): follow the existing convention of patching `self._vault` (an injected `ObsidianVault`-shaped object) with an in-memory fake exposing `read_note`/`write_note` async methods — the same fake used by `test_message.py`'s and `note_intake.py`'s existing test fixtures for `classify_and_apply`. Do not add a real REST call in unit tests; the Vault seam is always faked at this layer.

**New tests required (Wave 0), each following the sibling-test-in-same-file convention:**
- `test_note_classifier.py::test_topic_dir_for_journal_derives_from_dict` — plain function-call assertion, no mocking, mirrors existing `test_note_classifier.py` style (vocabulary-only assertions today; this adds a path assertion)
- `test_vault_sweep_plan.py::test_is_in_topic_dir_does_not_conflate_ops_subdirs` — same direct-call style as `test_plan_topic_move_describes_destination_and_reason`
- `test_vault_sweeper.py::test_sweep_never_relocates_pending_classification_file` — same fixture shape as other `run_sweep`/`_should_skip` tests in the file
- `test_recall.py::test_recency_applies_only_to_session_summaries` — replaces the 3 tests below; same `Recall.assemble()` fixture-and-assert shape already used by `test_recency_warm_carrier_journal` (L1464)

## Shared Patterns

### Module-constant + settings-override + module-level backstop
**Source:** `vault_sweeper.py:69-92` (`SWEEP_SKIP_PREFIXES` / `_active_skip_prefixes()`), config counterpart `config.py:137-152`
**Apply to:** Any place a denylist/allowlist needs both a safe hardcoded default and env-tunability. NOT needed for the D-03b taxonomy table itself (no settings-override requirement there) — only for `sweep_skip_prefixes`.

### D-14 lazy-create-if-missing via REST PUT
**Source:** `note_intake.py:53-63` (`INBOX_PATH` read-then-conditionally-write), `vault.py:507-515` (`write_note`'s unconditional PUT primitive), `app/services/inbox.py` (`build_initial_inbox()` as the pure-builder-function precedent)
**Apply to:** `self/identity.md`, `self/methodology.md`, `self/goals.md`, `self/relationships.md` stub creation (D-04). No local filesystem existence check anywhere — Vault is REST-only; `read_note` returning empty/falsy IS the "missing" signal, `write_note`'s PUT IS the create.

### Single source of truth via lazy/module import, never a second hardcoded tuple
**Source:** `vault_sweep_plan.py:41-53` (`propose_topic_move`'s existing `from app.services.note_classifier import topic_dir_for` at call time)
**Apply to:** `recall.py`'s D-03b coupling to `note_classifier.TOPIC_VAULT_PATH`; also apply to reconciling `_WARM_TIER_EXCLUDE_PREFIXES` vs `RecallConfig.exclude_prefixes`.

### Positive-allowlist / no-weight-by-omission invariant (T-41-08)
**Source:** `recall.py:53-66` (comment block above `_CARRIER_NAMESPACE_PREFIXES`, being removed) — the PRINCIPLE survives the removal even though the code doesn't: "a future non-ops/non-inbox namespace is never silently weighted."
**Apply to:** The new `test_recency_applies_only_to_session_summaries` regression test — assert positively that only `result.sessions`-tier items are recency-weighted, not merely that the old tuple is gone.

## No Analog Found

None. Every file in this phase's scope is an edit to an existing module, and each module's own established local shape (constant+backstop, lazy-import, read-then-write) is the correct analog to reuse. No wholly new module is created; D-03b's "possible new shared taxonomy module" was resolved by CONTEXT.md's own discretion note toward extending `note_classifier.py` in place rather than creating a new file, which this pattern map follows.

## Metadata

**Analog search scope:** `sentinel-core/app/services/{recall,vault_sweeper,vault_sweep_plan,note_classifier,note_intake,inbox}.py`, `sentinel-core/app/{config,vault}.py`, `sentinel-core/tests/{test_recall,test_vault_sweep_plan,test_vault_sweeper,test_note_classifier,test_message}.py`
**Files scanned:** 8 source + 5 test files (all directly Read this session; line numbers cross-verified against 44-RESEARCH.md's own verified citations)
**Pattern extraction date:** 2026-07-06
