"""Behavioural tests for the Active model seam (ADR-0007, app/model.py).

Every fixture in this file is built from the LIVE LM Studio payloads probed on
2026-09-07/08, not from an invented shape. That single live chat entry is
simultaneously the proof that a ``type == "llm"`` inclusion filter is wrong (v0
reports it as ``vlm``), that ``max`` and ``loaded`` context disagree by more
than 2x (262144 vs 119552), and that ``capabilities`` is the direct replacement
for the old ``_score`` function-calling guess.

Both API generations are covered deliberately. Building only from this box's
payload would bake its configuration into the suite: JIT auto-evict and TTL are
switched off here, so everything reports ``state: "loaded"``, whereas a stock
JIT-enabled LM Studio reports ``state: "not-loaded"`` until the first request
arrives. A suite built only from this box would ship the JIT defect green.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from app.config import Settings
from app.errors import ModelSelectorError
from app.model import (
    CONTEXT_SOURCE_DECLARED,
    CONTEXT_SOURCE_LOADED,
    CONTEXT_SOURCE_MAX,
    DECLARED_DEFAULT_CONTEXT_WINDOW,
    ActiveModel,
    LMStudioModelSource,
    ModelProfile,
    StaticModelSource,
    build_static_profiles,
    static_model_source,
)
from app.services.model_registry import ModelInfo

LOGGER_NAME = "app.model"
BASE_URL = "http://lmstudio.test/v1"

QWEN_ID = "qwen/qwen3.8-27b"
NOMIC_ID = "text-embedding-nomic-embed-text-v1.5"
CHATML_STOPS = ("<|im_end|>", "<|endoftext|>")


# ---------------------------------------------------------------------------
# Live payloads (verified ground truth — do not "tidy")
# ---------------------------------------------------------------------------


def v0_chat(**overrides) -> dict:
    entry = {
        "id": QWEN_ID,
        "object": "model",
        "type": "vlm",
        "publisher": "qwen",
        "arch": "qwen3_5",
        "compatibility_type": "mlx",
        "quantization": "4bit",
        "state": "loaded",
        "max_context_length": 262144,
        "loaded_context_length": 119552,
        "capabilities": ["tool_use"],
    }
    entry.update(overrides)
    return entry


def v0_embedding(**overrides) -> dict:
    entry = {
        "id": NOMIC_ID,
        "object": "model",
        "type": "embeddings",
        "arch": "nomic-bert",
        "compatibility_type": "gguf",
        "state": "loaded",
        "max_context_length": 2048,
    }
    entry.update(overrides)
    return entry


def v1_chat(**overrides) -> dict:
    entry = {
        "key": QWEN_ID,
        "type": "llm",
        "architecture": "qwen3_5",
        "format": "mlx",
        "display_name": "Qwen3.8 27B",
        "params_string": "27B",
        "publisher": "qwen",
        "quantization": "4bit",
        "selected_variant": f"{QWEN_ID}@4bit",
        "size_bytes": 17_000_000_000,
        "description": "",
        "variants": [f"{QWEN_ID}@4bit"],
        "max_context_length": 262144,
        "capabilities": {
            "vision": True,
            "trained_for_tool_use": True,
            "reasoning": {
                "allowed_options": ["off", "low", "medium", "xhigh", "on"],
                "default": "xhigh",
            },
        },
        "loaded_instances": [
            {
                "id": f"{QWEN_ID}:1",
                "config": {
                    "context_length": 119552,
                    "parallel": 4,
                    "reasoning_budget_message": "",
                },
            }
        ],
    }
    entry.update(overrides)
    return entry


def v1_embedding(**overrides) -> dict:
    entry = {
        "key": NOMIC_ID,
        "type": "embedding",
        "capabilities": None,
        "max_context_length": 2048,
        "loaded_instances": [],
    }
    entry.update(overrides)
    return entry


def v0_model(model_id: str, *, loaded: bool = True, tool_use: bool = True, **overrides) -> dict:
    """A generic v0 entry — the shape a JIT-enabled backend reports."""
    entry = {
        "id": model_id,
        "type": "llm",
        "arch": "qwen3_5",
        "state": "loaded" if loaded else "not-loaded",
        "max_context_length": 32768,
        "capabilities": ["tool_use"] if tool_use else [],
    }
    if loaded:
        entry["loaded_context_length"] = 8192
    entry.update(overrides)
    return entry


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeLMStudio:
    """A fake LM Studio serving whichever generation the test configures.

    ``v1=None`` means "this backend predates the v1 model API" and answers 404,
    which is the only response that selects the fallback path.
    """

    def __init__(self, *, v0=None, v1=None, v0_error=None, v1_error=None):
        self.v0 = v0
        self.v1 = v1
        self.v0_error = v0_error
        self.v1_error = v1_error
        self.calls: list[str] = []

    def _handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        if path.endswith("/api/v1/models"):
            if self.v1_error is not None:
                raise self.v1_error
            if self.v1 is None:
                return httpx.Response(404, json={"error": "unknown endpoint"})
            return httpx.Response(200, json={"data": self.v1})
        if path.endswith("/api/v0/models"):
            if self.v0_error is not None:
                raise self.v0_error
            if self.v0 is None:
                return httpx.Response(404, json={"error": "unknown endpoint"})
            return httpx.Response(200, json={"data": self.v0})
        return httpx.Response(404, json={"error": "unmocked"})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handler))

    def source(self, **kwargs) -> LMStudioModelSource:
        return LMStudioModelSource(self.client(), BASE_URL, **kwargs)

    def count(self, suffix: str) -> int:
        return sum(1 for path in self.calls if path.endswith(suffix))


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def settings(**overrides) -> Settings:
    """Settings with every model knob explicitly unset unless a test sets it.

    ``model_name=""`` is how "MODEL_NAME unset" is expressed: the field is a
    plain ``str`` with a tracked default, and an empty string is the only
    falsy value it can hold.
    """
    base: dict = {
        "sentinel_api_key": "test-key",
        "model_name": "",
        "model_preferred": None,
        "model_task_chat": None,
        "model_task_structured": None,
        "model_task_fast": None,
        "model_context_cap": None,
        "lmstudio_base_url": BASE_URL,
        "ai_provider": "lmstudio",
        "anthropic_api_key": "",
    }
    base.update(overrides)
    return Settings(**base)


def profile(model_id: str, *, capabilities=frozenset({"tool_use"}), **overrides) -> ModelProfile:
    fields = {
        "model_id": model_id,
        "litellm_model": f"openai/{model_id}",
        "api_base": BASE_URL,
        "context_window": 8192,
        "capabilities": capabilities,
    }
    fields.update(overrides)
    return ModelProfile(**fields)


def active(fake: FakeLMStudio, cfg: Settings | None = None, **kwargs) -> ActiveModel:
    return ActiveModel([fake.source()], cfg or settings(), **kwargs)


async def warm(model: ActiveModel, fake: FakeLMStudio, kind: str, payload: list[dict]):
    """Resolve once (seeding last-known-good), then swap in a new payload."""
    resolved = await model.for_task(kind)
    fake.v0 = payload
    model.invalidate()
    return resolved


# ===========================================================================
# Adapter — candidate filtering, both generations
# ===========================================================================


async def test_v0_candidate_filtering_keeps_vlm_and_drops_embeddings():
    """ADR decision 3's exclusion form: keep everything that is not embeddings.

    The live chat model reports ``type: "vlm"``. A ``type == "llm"`` inclusion
    filter would have dropped the only chat model this box serves.
    """
    fake = FakeLMStudio(v0=[v0_chat(), v0_embedding()])
    candidates = await fake.source().candidates()

    assert [p.model_id for p in candidates.reported] == [QWEN_ID]
    assert [p.model_id for p in candidates.loaded] == [QWEN_ID]


async def test_v0_candidate_filtering_keeps_an_unseen_future_type():
    """A type LM Studio has not shipped yet is kept, not dropped.

    This is the whole point of the exclusion form — it stays correct when the
    backend adds a type we have never seen.
    """
    fake = FakeLMStudio(v0=[v0_chat(id="future/omni-model", type="omni"), v0_embedding()])
    candidates = await fake.source().candidates()

    assert [p.model_id for p in candidates.reported] == ["future/omni-model"]


async def test_v1_entry_is_parsed_from_key_instances_and_capabilities():
    """v1 identity/loadedness/window/capabilities/reasoning all come off the entry."""
    fake = FakeLMStudio(v1=[v1_chat(), v1_embedding()])
    candidates = await fake.source().candidates()

    assert len(candidates.reported) == 1
    resolved = candidates.reported[0]
    assert resolved.model_id == QWEN_ID
    assert resolved.loaded is True
    assert resolved.context_window == 119552
    assert resolved.context_window_source == CONTEXT_SOURCE_LOADED
    assert "tool_use" in resolved.capabilities
    assert resolved.reasoning == {
        "allowed_options": ["off", "low", "medium", "xhigh", "on"],
        "default": "xhigh",
    }


async def test_v1_not_loaded_entry_keeps_its_capabilities():
    """Flagged call 12, answered by data rather than by widening the filter.

    On v1 ``capabilities`` is a property of the MODEL, not of a loaded
    instance, so a tier-two candidate carries them and ``for_task("structured")``
    can filter it correctly. Assert the capabilities SURVIVE — not merely that
    the entry appears.
    """
    fake = FakeLMStudio(v1=[v1_chat(loaded_instances=[])])
    candidates = await fake.source().candidates()

    assert candidates.loaded == ()
    assert len(candidates.reported) == 1
    assert candidates.reported[0].loaded is False
    assert "tool_use" in candidates.reported[0].capabilities


async def test_v1_404_falls_back_to_v0():
    """An older LM Studio with no v1 still works — vlm type, embeddings spelling."""
    fake = FakeLMStudio(v1=None, v0=[v0_chat(), v0_embedding()])
    source = fake.source()
    candidates = await source.candidates()

    assert source.generation == "v0"
    assert [p.model_id for p in candidates.reported] == [QWEN_ID]
    assert candidates.reported[0].context_window == 119552


async def test_v1_and_v0_produce_equivalent_profiles():
    """The same model, two payload shapes, one profile.

    Field by field rather than object equality, because ``reasoning`` is
    legitimately unset on v0. Two of these assertions are verified against the
    live box and are named explicitly rather than folded into the loop.
    """
    from_v1 = (await FakeLMStudio(v1=[v1_chat()]).source().candidates()).reported[0]
    from_v0 = (await FakeLMStudio(v1=None, v0=[v0_chat()]).source().candidates()).reported[0]

    # Verified live: loaded_instances[0].config.context_length == loaded_context_length.
    assert from_v1.context_window == 119552
    assert from_v0.context_window == 119552

    # Verified live: v1 `architecture` and v0 `arch` both read "qwen3_5", which
    # aliases to the qwen2 ChatML profile. The substring rung is never reached.
    assert from_v1.stop_sequences == CHATML_STOPS
    assert from_v0.stop_sequences == CHATML_STOPS

    for field in (
        "model_id",
        "litellm_model",
        "api_base",
        "context_window",
        "context_window_source",
        "stop_sequences",
        "capabilities",
        "family",
        "loaded",
    ):
        assert getattr(from_v1, field) == getattr(from_v0, field), field

    # The one legitimate difference.
    assert from_v1.reasoning is not None
    assert from_v0.reasoning is None


async def test_both_embedding_spellings_are_excluded():
    """v1 says ``embedding``; v0 says ``embeddings``. Both must be excluded.

    A filter written against one generation silently admits embedding models on
    the other, and an embedding model selected as a chat candidate is a hard
    failure at request time.
    """
    from_v1 = await FakeLMStudio(v1=[v1_chat(), v1_embedding()]).source().candidates()
    from_v0 = await FakeLMStudio(v1=None, v0=[v0_chat(), v0_embedding()]).source().candidates()

    assert NOMIC_ID not in {p.model_id for p in from_v1.reported}
    assert NOMIC_ID not in {p.model_id for p in from_v0.reported}


async def test_duplicate_identities_collapse_with_the_loaded_copy_winning():
    """The live v1 response really did return the nomic model twice.

    Without this, a loaded model can be demoted into tier two by its own stale
    duplicate.
    """
    fake = FakeLMStudio(v1=[v1_chat(loaded_instances=[]), v1_chat()])
    candidates = await fake.source().candidates()

    assert len(candidates.reported) == 1
    assert candidates.reported[0].loaded is True
    assert len(candidates.loaded) == 1


async def test_answered_generation_is_cached_and_v1_is_not_reprobed():
    """A 404 from v1 is a version signal, not a transient failure."""
    fake = FakeLMStudio(v1=None, v0=[v0_chat()])
    source = fake.source()

    await source.candidates()
    await source.candidates()
    await source.candidates()

    assert fake.count("/api/v1/models") == 1, "v1 must be probed once, not per refresh"
    assert fake.count("/api/v0/models") == 3, "one list fetch per refresh"


# ===========================================================================
# Context-window ladder — three rungs, no family constant
# ===========================================================================


async def test_context_window_resolves_from_loaded_context_length(caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        candidates = await FakeLMStudio(v1=None, v0=[v0_chat()]).source().candidates()

    resolved = candidates.reported[0]
    assert resolved.context_window == 119552, "must budget against loaded, not max"
    assert resolved.context_window_source == CONTEXT_SOURCE_LOADED
    assert any(CONTEXT_SOURCE_LOADED in r.getMessage() for r in caplog.records)


async def test_context_window_falls_back_to_max_context_length(caplog):
    entry = v0_chat()
    del entry["loaded_context_length"]
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        candidates = await FakeLMStudio(v1=None, v0=[entry]).source().candidates()

    resolved = candidates.reported[0]
    assert resolved.context_window == 262144
    assert resolved.context_window_source == CONTEXT_SOURCE_MAX
    assert any(CONTEXT_SOURCE_MAX in r.getMessage() for r in caplog.records)


async def test_context_window_falls_back_to_declared_4096(caplog):
    """No family-constant rung: a declared, logged 4096 beats a lying constant.

    The qwen2 family entry declares 32768 against this model's real
    262144/119552 — falling back to it would be worse than falling back to a
    floor that announces itself.
    """
    entry = v0_chat()
    del entry["loaded_context_length"]
    del entry["max_context_length"]
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        candidates = await FakeLMStudio(v1=None, v0=[entry]).source().candidates()

    resolved = candidates.reported[0]
    assert resolved.context_window == DECLARED_DEFAULT_CONTEXT_WINDOW == 4096
    assert resolved.context_window != 32768, "the family constant must not be consulted"
    assert resolved.context_window_source == CONTEXT_SOURCE_DECLARED
    assert any(CONTEXT_SOURCE_DECLARED in r.getMessage() for r in caplog.records)


async def test_not_loaded_candidate_context_window_comes_from_max_context_length():
    """A not-loaded entry carries no loaded window, so it resolves at rung two.

    That is correct, not a bug to fix: once JIT loads the model the next TTL
    refresh picks up the real (possibly smaller) loaded window. Budgeting
    against max for at most one TTL window is the accepted cost of the first
    request; the alternative is refusing to serve it at all.
    """
    fake = FakeLMStudio(v1=None, v0=[v0_model("solo/model", loaded=False)])
    resolved = await active(fake).for_task("chat")

    assert resolved.loaded is False
    assert resolved.context_window == 32768
    assert resolved.context_window_source == CONTEXT_SOURCE_MAX


async def test_model_context_cap_lowers_the_resolved_window(caplog):
    fake = FakeLMStudio(v1=None, v0=[v0_chat()])
    model = active(fake, settings(model_context_cap=32000))

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resolved = await model.for_task("chat")

    assert resolved.context_window == 32000
    assert any("MODEL_CONTEXT_CAP" in r.getMessage() for r in caplog.records)


async def test_unset_context_cap_leaves_the_resolved_window_alone():
    fake = FakeLMStudio(v1=None, v0=[v0_chat()])
    resolved = await active(fake).for_task("chat")

    assert resolved.context_window == 119552


async def test_context_cap_never_raises_a_lower_resolved_window():
    entry = v0_chat(loaded_context_length=8192)
    fake = FakeLMStudio(v1=None, v0=[entry])
    model = active(fake, settings(model_context_cap=200000))

    resolved = await model.for_task("chat")

    assert resolved.context_window == 8192, "the cap is a ceiling, never a floor"


# ===========================================================================
# Task-capability filter
# ===========================================================================


async def test_for_task_structured_requires_tool_use():
    capable = v0_model("capable/model", tool_use=True)
    incapable = v0_model("incapable/model", tool_use=False)
    fake = FakeLMStudio(v1=None, v0=[capable, incapable])

    resolved = await active(fake).for_task("structured")

    assert resolved.model_id == "capable/model"


async def test_for_task_chat_and_fast_impose_no_capability_requirement():
    fake = FakeLMStudio(v1=None, v0=[v0_model("plain/model", tool_use=False)])

    assert (await active(fake).for_task("chat")).model_id == "plain/model"
    assert (await active(fake).for_task("fast")).model_id == "plain/model"


# ===========================================================================
# Model-agnostic by default (ADR decision 4 as amended — acceptance criterion)
# ===========================================================================


async def test_model_agnostic_one_loaded_model_resolves_with_all_settings_unset():
    """MODEL_NAME, MODEL_PREFERRED and all three MODEL_TASK_* unset."""
    fake = FakeLMStudio(v1=None, v0=[v0_chat(), v0_embedding()])

    resolved = await active(fake).for_task("chat")

    assert resolved.model_id == QWEN_ID


async def test_model_agnostic_unfamiliar_model_resolves_with_all_settings_unset():
    """Swapping the loaded model needs no config change and no code change.

    The family table has never seen this id. If this test needed configuration
    to pass, the ladder would not be model-agnostic and the implementation
    would be wrong.
    """
    unfamiliar = v0_model("someorg/llama-4-unheard-of-70b", arch="not_a_known_arch")
    fake = FakeLMStudio(v1=None, v0=[unfamiliar, v0_embedding()])

    resolved = await active(fake).for_task("chat")

    assert resolved.model_id == "someorg/llama-4-unheard-of-70b"
    assert resolved.litellm_model == "openai/someorg/llama-4-unheard-of-70b"


# ===========================================================================
# Refuse to guess — rung 7 RAISES
# ===========================================================================


async def test_two_capable_candidates_and_an_unloaded_model_name_raises():
    """The bug this ADR exists to remove, asserted as absent.

    On 2026-09-08 the deployed container resolved ``google/gemma-4-31b`` because
    configuration named it, while LM Studio served only ``qwen/qwen3.8-27b`` and
    answered by silently substituting the model it actually had. A live backend
    whose candidates cannot be disambiguated is a loud failure, not a quiet
    substitution.

    The no-last-known-good clause is load-bearing: last-known-good sits at rung
    4, so a warm one would satisfy the request before the ladder ever reached
    the refusal rung. This ActiveModel starts cold.
    """
    fake = FakeLMStudio(
        v1=None, v0=[v0_model("first/capable"), v0_model("second/capable")]
    )
    model = active(fake, settings(model_name="google/gemma-4-31b"))

    with pytest.raises(ModelSelectorError) as excinfo:
        await model.for_task("structured")

    assert "google/gemma-4-31b" not in str(excinfo.value), (
        "the refusal must not name a model the backend never reported"
    )


async def test_two_capable_candidates_and_no_configuration_also_raises():
    fake = FakeLMStudio(
        v1=None, v0=[v0_model("first/capable"), v0_model("second/capable")]
    )

    with pytest.raises(ModelSelectorError):
        await active(fake).for_task("structured")


# ===========================================================================
# Ladder order — seven rungs, each decisive in turn
# ===========================================================================


async def test_rung_1_capability_filter_runs_before_preference():
    """The filter narrows the set BEFORE any preference rung is consulted.

    MODEL_NAME names the incapable model. Under a preference-first ladder it
    would win; under filter-first it is never a candidate for ``structured``.
    """
    fake = FakeLMStudio(
        v1=None,
        v0=[v0_model("capable/model"), v0_model("incapable/model", tool_use=False)],
    )
    model = active(fake, settings(model_name="incapable/model"))

    assert (await model.for_task("structured")).model_id == "capable/model"


async def test_rung_2_model_task_pin_decides():
    """The three MODEL_TASK_* settings gain their first consumer here."""
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model"), v0_model("b/model")])
    model = active(
        fake,
        settings(
            model_task_chat="a/model",
            model_preferred="b/model",
            model_name="b/model",
        ),
    )

    assert (await model.for_task("chat")).model_id == "a/model"


async def test_rung_3_model_preferred_decides():
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model"), v0_model("b/model")])
    model = active(fake, settings(model_preferred="b/model", model_name="a/model"))

    assert (await model.for_task("chat")).model_id == "b/model"


async def test_rung_4_last_known_good_decides():
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model")])
    model = active(fake, settings())
    await warm(model, fake, "chat", [v0_model("a/model"), v0_model("b/model")])

    assert (await model.for_task("chat")).model_id == "a/model"


async def test_rung_5_model_name_decides():
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model"), v0_model("b/model")])
    model = active(fake, settings(model_name="b/model"))

    assert (await model.for_task("chat")).model_id == "b/model"


async def test_rung_6_sole_surviving_candidate_decides():
    """With exactly one candidate there is nothing to guess between."""
    fake = FakeLMStudio(v1=None, v0=[v0_model("only/model"), v0_embedding()])

    assert (await active(fake).for_task("chat")).model_id == "only/model"


async def test_rung_7_refuses_by_raising_rather_than_returning_a_candidate():
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model"), v0_model("b/model")])

    with pytest.raises(ModelSelectorError):
        await active(fake).for_task("chat")


async def test_rung_4_beats_rung_5_last_known_good_outranks_model_name():
    """The case the earlier, wrong ordering got backwards.

    MODEL_NAME is a tracked DEFAULT that may name a model nobody has loaded
    (``exo-model-notfound-502``); last-known-good is verified still-loaded by
    construction. Verified-loaded evidence beats an unverified default, and a
    second model appearing in LM Studio must not make a running system abandon
    the model it has been successfully using.
    """
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model")])
    model = active(fake, settings(model_name="b/model"))
    await warm(model, fake, "chat", [v0_model("a/model"), v0_model("b/model")])

    assert (await model.for_task("chat")).model_id == "a/model"


# ===========================================================================
# Operator pins — absolute, but never silent
# ===========================================================================


async def test_pin_on_loaded_but_incapable_model_wins_and_warns(caplog):
    """An operator who names a model gets that model — loudly.

    Silently overriding an explicit pin is a worse failure than a degraded
    structured response, but the operator must find out from the log rather
    than from malformed output.
    """
    fake = FakeLMStudio(
        v1=None,
        v0=[v0_model("capable/model"), v0_model("pinned/model", tool_use=False)],
    )
    model = active(fake, settings(model_task_structured="pinned/model"))

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        resolved = await model.for_task("structured")

    assert resolved.model_id == "pinned/model"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "pinned/model" in warnings[0]
    assert "structured" in warnings[0]
    assert "tool_use" in warnings[0]


async def test_model_task_pin_naming_an_unreported_model_is_ignored():
    """The absolute-pin exception covers loaded-but-incapable ONLY.

    It never resurrects a model the backend has not reported at all.
    """
    fake = FakeLMStudio(v1=None, v0=[v0_model("only/model")])
    model = active(fake, settings(model_task_chat="ghost/model"))

    assert (await model.for_task("chat")).model_id == "only/model"


async def test_model_preferred_naming_an_unreported_model_is_ignored():
    fake = FakeLMStudio(v1=None, v0=[v0_model("only/model")])
    model = active(fake, settings(model_preferred="ghost/model"))

    assert (await model.for_task("chat")).model_id == "only/model"


async def test_model_name_naming_an_unreported_model_is_ignored():
    fake = FakeLMStudio(v1=None, v0=[v0_model("only/model")])
    model = active(fake, settings(model_name="ghost/model"))

    assert (await model.for_task("chat")).model_id == "only/model"


async def test_a_discarded_configured_value_logs_one_info_line(caplog):
    """Otherwise the operator gets a raise at rung 7 with no indication that
    the configuration they set was thrown away."""
    fake = FakeLMStudio(v1=None, v0=[v0_model("only/model")])
    model = active(fake, settings(model_task_chat="ghost/model"))

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await model.for_task("chat")

    ignored = [
        r.getMessage()
        for r in caplog.records
        if "ignored" in r.getMessage() and "ghost/model" in r.getMessage()
    ]
    assert len(ignored) == 1
    assert "MODEL_TASK_CHAT" in ignored[0]


async def test_a_used_configured_value_logs_no_ignored_line(caplog):
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model"), v0_model("b/model")])
    model = active(fake, settings(model_task_chat="a/model"))

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resolved = await model.for_task("chat")

    assert resolved.model_id == "a/model"
    assert not [r for r in caplog.records if "ignored" in r.getMessage()]


# ===========================================================================
# Last-known-good — tiebreaker and failure path
# ===========================================================================


async def test_last_known_good_tiebreaker_when_model_name_matches_neither():
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model")])
    model = active(fake, settings(model_name="ghost/model"))
    await warm(model, fake, "chat", [v0_model("a/model"), v0_model("b/model")])

    assert (await model.for_task("chat")).model_id == "a/model"


async def test_last_known_good_tiebreaker_when_model_name_names_the_other():
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model")])
    model = active(fake, settings(model_name="b/model"))
    await warm(model, fake, "chat", [v0_model("a/model"), v0_model("b/model")])

    assert (await model.for_task("chat")).model_id == "a/model"


async def test_last_known_good_is_discarded_once_it_is_no_longer_loaded():
    """JIT eviction must not resurrect a model; the ladder continues below."""
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model")])
    model = active(fake, settings(model_name="b/model"))
    await warm(model, fake, "chat", [v0_model("b/model"), v0_model("c/model")])

    assert (await model.for_task("chat")).model_id == "b/model"


async def test_rung_4_logs_divergence_from_model_name(caplog):
    """Config says A, the system has been running B, and nothing announces it.

    That is the same class of failure this ADR exists to fix. The line fires
    only on divergence.
    """
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model")])
    model = active(fake, settings(model_name="b/model"))
    await warm(model, fake, "chat", [v0_model("a/model"), v0_model("b/model")])

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await model.for_task("chat")

    lines = [
        r.getMessage() for r in caplog.records if "last-known-good" in r.getMessage()
    ]
    assert len(lines) == 1
    assert "a/model" in lines[0]
    assert "b/model" in lines[0]


async def test_rung_4_is_silent_when_last_known_good_and_model_name_agree(caplog):
    """The silent case is the common one. A line on every resolution is noise,
    and noise is how the real divergence gets missed."""
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model")])
    model = active(fake, settings(model_name="a/model"))
    await warm(model, fake, "chat", [v0_model("a/model"), v0_model("b/model")])

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resolved = await model.for_task("chat")

    assert resolved.model_id == "a/model"
    assert not [r for r in caplog.records if "last-known-good" in r.getMessage()]


async def test_failed_refresh_serves_last_known_good_with_a_warning(caplog):
    """ADR decision 1: a failed refresh serves last-known-good rather than
    failing the request — and unconditionally, because the capability data is
    stale too."""
    fake = FakeLMStudio(v1=None, v0=[v0_chat()])
    model = active(fake)
    first = await model.for_task("chat")

    fake.v0_error = httpx.ConnectError("connection refused")
    model.invalidate()

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        second = await model.for_task("chat")

    assert second.model_id == first.model_id
    assert second.context_window == 119552, "must not collapse to a 4096 default"
    assert any("last-known-good" in r.getMessage() for r in caplog.records)


async def test_cold_refresh_failure_falls_through_to_static_model_source():
    """With no last-known-good there is nothing to serve, so the next source
    answers rather than the request failing."""
    fake = FakeLMStudio(v1_error=httpx.ConnectError("refused"))
    fallback = StaticModelSource([profile("static/model", context_window=4096)])
    model = ActiveModel([fake.source(), fallback], settings())

    resolved = await model.for_task("chat")

    assert resolved.model_id == "static/model"


async def test_a_live_backend_reporting_nothing_does_not_fall_through_to_config():
    """A reachable backend that reports no usable model reaches the refusal rung.

    Falling through to StaticModelSource here would answer a live "I have
    nothing" with a model from configuration — the phantom ADR decision 4
    forbids. Only a source that RAISES hands over to the next one.
    """
    fake = FakeLMStudio(v1=None, v0=[])
    fallback = StaticModelSource([profile("configured/model")])
    model = ActiveModel([fake.source(), fallback], settings())

    with pytest.raises(ModelSelectorError):
        await model.for_task("chat")


async def test_cold_refresh_failure_with_no_fallback_source_raises():
    fake = FakeLMStudio(v1_error=httpx.ConnectError("refused"))

    with pytest.raises(ModelSelectorError):
        await active(fake).for_task("chat")


# ===========================================================================
# TTL and invalidate
# ===========================================================================


async def test_ttl_window_issues_one_fetch_and_refetches_after_expiry():
    """Driven by an injected clock, not by sleeping."""
    fake = FakeLMStudio(v1=None, v0=[v0_chat()])
    clock = FakeClock()
    model = ActiveModel([fake.source()], settings(), clock=clock, ttl_seconds=60.0)

    await model.for_task("chat")
    await model.for_task("chat")
    assert fake.count("/api/v0/models") == 1

    clock.advance(61.0)
    await model.for_task("chat")
    assert fake.count("/api/v0/models") == 2


async def test_invalidate_forces_a_refetch_inside_the_window():
    fake = FakeLMStudio(v1=None, v0=[v0_chat()])
    clock = FakeClock()
    model = ActiveModel([fake.source()], settings(), clock=clock, ttl_seconds=60.0)

    await model.for_task("chat")
    model.invalidate()
    await model.for_task("chat")

    assert fake.count("/api/v0/models") == 2


async def test_a_model_swapped_in_the_ui_is_picked_up_within_one_ttl_window():
    """ADR decision 1's headline truth, end to end, with no restart."""
    fake = FakeLMStudio(v1=None, v0=[v0_chat()])
    clock = FakeClock()
    model = ActiveModel([fake.source()], settings(), clock=clock, ttl_seconds=60.0)

    assert (await model.for_task("chat")).model_id == QWEN_ID

    fake.v0 = [v0_model("someone/else-27b", arch="llama3")]
    clock.advance(61.0)

    swapped = await model.for_task("chat")
    assert swapped.model_id == "someone/else-27b"
    assert swapped.stop_sequences == ("<|eot_id|>", "<|end_of_text|>")


# ===========================================================================
# Two candidate tiers — a JIT-enabled backend must resolve
# ===========================================================================


async def test_jit_zero_loaded_one_downloaded_resolves_and_logs(caplog):
    """A stock JIT-enabled LM Studio is never unusable.

    ``GET /api/v0/models`` lists DOWNLOADED models and most report
    ``state: "not-loaded"`` until a request arrives. A strict loaded-only filter
    yields zero candidates and raises.
    """
    fake = FakeLMStudio(
        v1=None, v0=[v0_model("only/downloaded", loaded=False), v0_embedding()]
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resolved = await active(fake).for_task("chat")

    assert resolved.model_id == "only/downloaded"
    assert resolved.loaded is False
    jit = [r.getMessage() for r in caplog.records if "JIT-load" in r.getMessage()]
    assert len(jit) == 1
    assert "only/downloaded" in jit[0]


async def test_jit_zero_loaded_two_downloaded_and_no_config_raises():
    fake = FakeLMStudio(
        v1=None,
        v0=[v0_model("a/model", loaded=False), v0_model("b/model", loaded=False)],
    )

    with pytest.raises(ModelSelectorError):
        await active(fake).for_task("chat")


async def test_one_loaded_beats_three_downloaded():
    """Ordering is strict: tier two is only consulted when tier one is empty."""
    fake = FakeLMStudio(
        v1=None,
        v0=[
            v0_model("down/one", loaded=False),
            v0_model("live/model", loaded=True),
            v0_model("down/two", loaded=False),
            v0_model("down/three", loaded=False),
        ],
    )

    assert (await active(fake).for_task("chat")).model_id == "live/model"


async def test_a_pin_disambiguates_within_the_reported_tier():
    """Pins disambiguate in tier two exactly as in tier one — and must still
    name a model the backend actually reported."""
    fake = FakeLMStudio(
        v1=None,
        v0=[v0_model("a/model", loaded=False), v0_model("b/model", loaded=False)],
    )
    model = active(fake, settings(model_task_chat="b/model"))

    assert (await model.for_task("chat")).model_id == "b/model"


async def test_a_pin_on_a_downloaded_model_does_not_beat_a_loaded_one():
    """Pins are not exempt from the tier ordering; they win only when nothing
    is loaded."""
    fake = FakeLMStudio(
        v1=None,
        v0=[v0_model("downloaded/model", loaded=False), v0_model("live/model")],
    )
    model = active(fake, settings(model_task_chat="downloaded/model"))

    assert (await model.for_task("chat")).model_id == "live/model"


async def test_zero_downloaded_non_embedding_models_raises():
    fake = FakeLMStudio(v1=None, v0=[v0_embedding()])

    with pytest.raises(ModelSelectorError):
        await active(fake).for_task("chat")


async def test_last_known_good_is_valid_in_the_reported_tier():
    """JIT eviction must not cost continuity."""
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model")])
    model = active(fake, settings())
    await warm(
        model,
        fake,
        "chat",
        [v0_model("a/model", loaded=False), v0_model("b/model", loaded=False)],
    )

    resolved = await model.for_task("chat")
    assert resolved.model_id == "a/model"
    assert resolved.loaded is False


async def test_a_remembered_downloaded_model_does_not_beat_a_loaded_one():
    """...and must not beat a live model either."""
    fake = FakeLMStudio(v1=None, v0=[v0_model("a/model")])
    model = active(fake, settings())
    await warm(
        model, fake, "chat", [v0_model("a/model", loaded=False), v0_model("b/model")]
    )

    assert (await model.for_task("chat")).model_id == "b/model"


# ===========================================================================
# StaticModelSource
# ===========================================================================


async def test_static_model_source_serves_claude_from_the_seed():
    profiles = await build_static_profiles(
        settings(ai_provider="claude", claude_model="claude-haiku-4-5"),
        provider="claude",
    )

    assert len(profiles) == 1
    assert profiles[0].model_id == "claude-haiku-4-5"
    assert profiles[0].context_window == 200000, "from models-seed.json"
    assert "tool_use" in profiles[0].capabilities


async def test_static_model_source_serves_declared_4096_for_ollama_and_llamacpp():
    """Under StaticModelSource their 4096 becomes DECLARED rather than accidental."""
    ollama = await build_static_profiles(
        settings(ai_provider="ollama", ollama_model="ollama-only-model"),
        provider="ollama",
    )
    llamacpp = await build_static_profiles(
        settings(ai_provider="llamacpp", llamacpp_model="llamacpp-only-model"),
        provider="llamacpp",
    )

    assert ollama[0].context_window == DECLARED_DEFAULT_CONTEXT_WINDOW
    assert ollama[0].context_window_source == CONTEXT_SOURCE_DECLARED
    assert ollama[0].litellm_model == "ollama/ollama-only-model"
    assert llamacpp[0].context_window == DECLARED_DEFAULT_CONTEXT_WINDOW
    assert llamacpp[0].litellm_model == "openai/llamacpp-only-model"


async def test_static_model_source_alone_resolves_when_there_is_no_backend():
    """MODEL_NAME's only remaining role: StaticModelSource's data."""
    source = await static_model_source(
        settings(model_name="google/gemma-4-31b"), provider="lmstudio"
    )
    model = ActiveModel([source], settings(model_name="google/gemma-4-31b"))

    resolved = await model.for_task("chat")

    assert resolved.model_id == "google/gemma-4-31b"
    assert resolved.litellm_model == "openai/google/gemma-4-31b"
    assert resolved.stop_sequences == ("<end_of_turn>",), "substring rung, gemma family"
    assert resolved.reasoning is None


async def test_a_declared_capability_set_cannot_veto_a_task(caplog):
    """A capability set nobody OBSERVED must not filter a candidate out.

    ADR-0007 step 4 moved the five structured call sites onto the seam and this
    was the first thing that broke: ``models-seed.json``'s ``local-model`` entry
    declared ``function_calling: false``, so an offline deployment resolved
    ``for_task("structured")`` to nothing and RAISED — the six_rs stages fell
    back on every entry and note_classifier could not classify at all. A live
    backend's silence about tool use is evidence and still vetoes; a seed file's
    claim about a name is not.

    Step 5 then trimmed ``local-model`` out of the seed, which would have made
    this case pass for the WRONG reason — an id with no seed entry has no
    declared capabilities to be vetoed by, so the distinction under test would
    never be exercised. The declaring seed entry is therefore supplied
    EXPLICITLY here rather than read off the shipped file. That is stronger
    than the original: the property is "a declared false cannot veto", and this
    now tests exactly that instead of depending on which ids happen to be in a
    data file.
    """
    declaring_seed = {
        "declared-no-tools": ModelInfo(
            id="declared-no-tools",
            provider="lmstudio",
            context_window=8192,
            capabilities={"chat": True, "function_calling": False, "vision": False},
            notes="Declares no function calling — and must not be able to veto",
        )
    }
    config = settings(model_name="declared-no-tools")
    source = await static_model_source(
        config, provider="lmstudio", seed=declaring_seed
    )
    profiles = await build_static_profiles(
        config, provider="lmstudio", seed=declaring_seed
    )
    assert "tool_use" not in profiles[0].capabilities, (
        "premise: the seed entry genuinely declares no function calling"
    )
    assert profiles[0].capabilities_observed is False

    model = ActiveModel([source], config)
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resolved = await model.for_task("structured")

    assert resolved.model_id == "declared-no-tools"
    assert "no backend was reachable to ask" in caplog.text, (
        "admitting an unevidenced candidate must be logged, never silent"
    )


async def test_the_trimmed_seed_still_leaves_an_offline_local_model_usable(caplog):
    """The other half of the trim: no seed entry at all is also not a veto.

    After step 5 no local id has a seed entry, so an offline LM Studio /
    llama.cpp deployment resolves ``for_task("structured")`` against a profile
    with an EMPTY capability set. ``capabilities_observed=False`` is what keeps
    that admissible — without it the trim would reproduce the step-4 breakage it
    was written to fix, and every six_rs stage would fall back on every entry.
    """
    config = settings(model_name="local-model")
    profiles = await build_static_profiles(config, provider="lmstudio")
    assert profiles[0].capabilities == frozenset(), (
        "premise: the trimmed seed carries nothing for this id"
    )
    assert profiles[0].capabilities_observed is False

    source = await static_model_source(config, provider="lmstudio")
    model = ActiveModel([source], config)
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resolved = await model.for_task("structured")

    assert resolved.model_id == "local-model"
    assert resolved.context_window == DECLARED_DEFAULT_CONTEXT_WINDOW, (
        "the trim removed this id's 8192 seed window; it is a declared floor now"
    )


async def test_a_live_backend_reporting_no_tool_use_still_vetoes_structured():
    """The other half: OBSERVED absence of tool_use is still disqualifying.

    Without this, the leniency above would be a hole rather than a distinction
    — and ``probe_classifier_model_ready``, which gates a destructive vault
    sweep, would be answering about a model the backend said cannot do the job.
    """
    backend = FakeLMStudio(v0=[v0_chat(capabilities=[])])
    model = ActiveModel([backend.source()], settings(model_name=QWEN_ID))

    with pytest.raises(ModelSelectorError):
        await model.for_task("structured")


# ===========================================================================
# Replacements for pathfinder's deleted model_selector / resolve_model tests
# (ADR-0007 step 4, Task 2 disposition table rows 4, 14, 15 and 16).
#
# The other fifteen rows already had successors above. These four did not exist
# anywhere: pathfinder's copy guarded malformed-entry filtering and three
# prefix-normalisation cases, and the guarantees are real even though the module
# that held them was an independently drifted duplicate. They land here because
# this is where the behaviour lives now.
# ===========================================================================


async def test_malformed_entries_are_filtered_on_both_api_generations():
    """Row 4. A junk entry must be skipped, not raise and not become a candidate.

    Written for BOTH generations deliberately. v1 keys identity on ``key`` and
    v0 on ``id``, so a guard written against one generation protects only that
    one — and since v1 is PREFERRED, a v0-only guard would leave the path the
    live box actually takes unprotected.

    Four shapes, each seen or plausible in a real payload: an entry with no
    identity field at all, one whose identity is ``null``, a non-dict entry, and
    one with an empty-string identity.
    """
    junk_v1 = [
        {"type": "llm", "max_context_length": 4096},  # no identity field
        {"key": None, "type": "llm"},  # null identity
        "not-a-dict-at-all",
        {"key": "", "type": "llm"},  # empty identity
        v1_chat(),
    ]
    junk_v0 = [
        {"type": "llm", "max_context_length": 4096},
        {"id": None, "type": "llm"},
        "not-a-dict-at-all",
        {"id": "", "type": "llm"},
        v0_chat(),
    ]

    from_v1 = await FakeLMStudio(v1=junk_v1).source().candidates()
    from_v0 = await FakeLMStudio(v0=junk_v0).source().candidates()

    assert [p.model_id for p in from_v1.reported] == [QWEN_ID], (
        "v1 must yield only the valid candidate"
    )
    assert [p.model_id for p in from_v0.reported] == [QWEN_ID], (
        "v0 must yield only the valid candidate"
    )


async def test_a_prefixed_preference_matches_a_bare_candidate_id():
    """Row 14. MODEL_PREFERRED may carry the litellm tag; candidates do not.

    ``strip_litellm_prefix`` / ``ensure_litellm_prefix`` survived the teardown
    and ``ModelProfile`` carries both spellings, but nothing tested that the
    seam normalises before COMPARING — which is the only place it matters.
    """
    fake = FakeLMStudio(v0=[v0_model("mlx-community/foo"), v0_model("other/model")])
    model = active(fake, settings(model_preferred="openai/mlx-community/foo"))

    resolved = await model.for_task("chat")

    assert resolved.model_id == "mlx-community/foo"
    assert resolved.litellm_model == "openai/mlx-community/foo", (
        "ensure_litellm_prefix must not double-prefix (row 18's guarantee)"
    )


async def test_a_prefixed_default_matches_a_bare_loaded_candidate():
    """Row 15. The same normalisation on rung 5 (MODEL_NAME).

    Run against a COLD ``ActiveModel``: rung 4 (last-known-good) sits above
    rung 5, so a warm seam would decide before MODEL_NAME was ever consulted
    and the test would pass without exercising the rung it names.

    The prefixed default must be LOADED. Prefix normalisation decides whether a
    configured id MATCHES a candidate — never whether a non-loaded id may be
    returned.
    """
    fake = FakeLMStudio(v0=[v0_model("mlx-community/foo"), v0_model("other/model")])
    model = active(fake, settings(model_name="openai/mlx-community/foo"))

    resolved = await model.for_task("chat")

    assert resolved.model_id == "mlx-community/foo"
    assert model.cached_profile("chat") is not None, "premise: this was a cold resolve"


async def test_a_prefixed_default_that_is_loaded_wins_and_one_that_is_not_raises():
    """Row 16, the highest-value of the three — a live regression guard.

    The original (``..._previously_fell_through_to_arbitrary_first_loaded``)
    pinned the case where a prefix mismatch made the configured default look
    absent and pathfinder's copy silently returned ``loaded[0]``. Under the new
    ladder the fall-through target is the REFUSAL rung rather than an arbitrary
    candidate, so both halves are asserted:

    - a prefixed MODEL_NAME that IS among three loaded candidates is honoured
      and does not fall through to any of the other two;
    - the same prefixed MODEL_NAME when it is NOT loaded RAISES. Prefix
      normalisation must not become a back door for a phantom.
    """
    loaded = [
        v0_model("mlx-community/MiniMax-M2.7-4bit"),  # would be loaded[0]
        v0_model("mlx-community/Some-Other-Model-4bit"),
        v0_model("mlx-community/Qwen3.5-27B-8bit"),
    ]
    cfg = settings(model_name="openai/mlx-community/Qwen3.5-27B-8bit")

    honoured = await active(FakeLMStudio(v0=loaded), cfg).for_task("chat")

    assert honoured.model_id == "mlx-community/Qwen3.5-27B-8bit"
    assert honoured.model_id != loaded[0]["id"], (
        "must never fall through to an arbitrary candidate"
    )

    absent = active(
        FakeLMStudio(v0=loaded),
        settings(model_name="openai/mlx-community/Not-Loaded-At-All"),
    )
    with pytest.raises(ModelSelectorError):
        await absent.for_task("chat")


async def test_static_model_source_does_no_io():
    """It is the test substitute, so it must be constructible from a plain list."""
    source = StaticModelSource([profile("a/model"), profile("b/model")])
    candidates = await source.candidates()

    assert [p.model_id for p in candidates.loaded] == ["a/model", "b/model"]
    assert candidates.loaded == candidates.reported


# ===========================================================================
# ModelProfile shape
# ===========================================================================


async def test_resolved_profile_carries_the_task_kind_it_was_resolved_for():
    """Plan 02 needs it to re-resolve the same kind after an invalidate."""
    fake = FakeLMStudio(v1=None, v0=[v0_chat()])
    model = active(fake)

    assert (await model.for_task("chat")).task_kind == "chat"
    assert (await model.for_task("structured")).task_kind == "structured"


async def test_cached_profile_exposes_the_resolved_model_without_refreshing():
    fake = FakeLMStudio(v1=None, v0=[v0_chat()])
    model = active(fake)

    assert model.cached_profile("chat") is None
    await model.for_task("chat")
    assert model.cached_profile("chat").model_id == QWEN_ID
    assert fake.count("/api/v0/models") == 1
