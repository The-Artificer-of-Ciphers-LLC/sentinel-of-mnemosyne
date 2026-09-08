"""The Active model seam — which model is loaded, and what can it do.

ADR-0007. The local model's identity and capabilities used to exist as three
loose scalars (``model_name``, ``context_window``, ``stop_sequences``) resolved
once by ``build_provider_router`` and pinned onto ``app.state`` for the process
lifetime. Swapping the model in the LM Studio UI was invisible to a running
container: on 2026-09-07 the process was naming ``google/gemma-4-31b`` with
gemma's stop sequence and a 262144-token window while LM Studio was actually
serving ``qwen/qwen3.8-27b`` (ChatML stops, 119552 loaded window).

This module is the single place that answers "which model is loaded and what
can it do". It contains exactly four things:

- :class:`ModelProfile` — the value a call needs: id, litellm-prefixed id, api
  base, resolved context window, stop sequences, capabilities, the observed
  ``reasoning`` descriptor, family key, task kind, and which rung produced the
  context window.
- :class:`ModelSource` — the protocol backends answer through.
- :class:`LMStudioModelSource` / :class:`StaticModelSource` — the two adapters.
- :class:`ActiveModel` — the TTL'd resolver: ``for_task(kind) -> ModelProfile``.

Deliberate absences, each load-bearing:

- **No scoring.** Scoring always produces a winner, so keeping it would mean the
  refusal rung never fires (ADR decision 4).
- **No family-constant context rung.** The ladder is
  ``loaded window -> max_context_length -> a declared 4096``, each logged. A
  family rung would consume ``FamilyProfile.context_window``, and ADR-0007
  step 5 DELETED that field — it was unreachable in practice because both API
  generations always return ``max_context_length``, and the constants were
  wrong exactly where it would have mattered (the qwen2 entry declared 32768
  against a real 262144 max / 119552 loaded). ``FAMILY_PROFILES`` is read here
  for **stop sequences only**, and there is no longer a window on it to read.
- **No embedding re-pointing.** ADR decision 5: the embedding model is observed,
  never re-pointed. Nothing here touches ``settings.embedding_model``.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Protocol, Sequence

from app.errors import ModelSelectorError
from sentinel_shared.model_profiles import FAMILY_PROFILES, get_profile

if TYPE_CHECKING:  # pragma: no cover - typing only
    import httpx

logger = logging.getLogger(__name__)

#: The declared floor when a backend reports neither a loaded nor a maximum
#: context length. Declared and logged, deliberately not inferred from a family
#: constant — see the module docstring.
DECLARED_DEFAULT_CONTEXT_WINDOW = 4096

#: ADR decision 1 fixes the refresh window at 60 seconds.
DEFAULT_TTL_SECONDS = 60.0

CAPABILITY_TOOL_USE = "tool_use"
CAPABILITY_VISION = "vision"

#: The tiktoken encoding token counts are taken with, DECLARED on every profile
#: rather than derived per family. ADR-0007's Known Limitations accept the
#: approximation: cl100k_base is not Qwen's tokenizer, counting stays
#: approximate, and shipping a real per-family tokenizer is a container-weight
#: decision left deliberately open. Naming it on the profile is what changes —
#: an operator can now see which encoding produced a count instead of inferring
#: it, and ``TokenBudget`` degrades loudly on a name tiktoken does not know
#: rather than raising on the chat path.
DECLARED_TOKENIZER_ENCODING = "cl100k_base"

#: Which capabilities each task kind REQUIRES. ``structured`` needs tool use;
#: ``chat`` and ``fast`` impose no requirement, so every non-embedding model the
#: backend reports is a candidate for them (Flagged call 2).
TASK_CAPABILITY_REQUIREMENTS: dict[str, frozenset[str]] = {
    "chat": frozenset(),
    "structured": frozenset({CAPABILITY_TOOL_USE}),
    "fast": frozenset(),
}

#: Both spellings. ``/api/v1/models`` says ``embedding``, ``/api/v0/models``
#: says ``embeddings``. A filter written against one generation silently admits
#: embedding models on the other, and an embedding model selected as a chat
#: candidate is a hard failure at request time.
EMBEDDING_TYPES = frozenset({"embedding", "embeddings"})

# Context-window ladder rung names, recorded on the profile and logged.
CONTEXT_SOURCE_LOADED = "loaded_context_length"
CONTEXT_SOURCE_MAX = "max_context_length"
CONTEXT_SOURCE_DECLARED = "declared_default"

# API generations this adapter speaks. v1 is preferred; v0 is the fallback for
# an older LM Studio that has no v1.
GENERATION_V1 = "v1"
GENERATION_V0 = "v0"

_LITELLM_PROVIDER_PREFIXES: tuple[str, ...] = (
    "openai/",
    "ollama/",
    "anthropic/",
    "azure/",
    "bedrock/",
    "cohere/",
    "gemini/",
    "groq/",
    "huggingface/",
    "mistral/",
    "perplexity/",
    "replicate/",
    "together_ai/",
    "vertex_ai/",
)


def _prefixed(model_id: str, provider_prefix: str) -> str:
    """Return ``model_id`` carrying a litellm provider tag.

    A bare slash in the id (``qwen/qwen3.8-27b``) is a HuggingFace-style
    namespace, NOT a provider tag — returning it unchanged would make litellm
    raise "LLM Provider NOT provided".
    """
    if not provider_prefix:
        return model_id
    if model_id.startswith(_LITELLM_PROVIDER_PREFIXES):
        return model_id
    return f"{provider_prefix}{model_id}"


def _unprefixed(model_id: str) -> str:
    """Strip a leading litellm provider tag, preserving HF-style namespaces.

    The inverse of :func:`_prefixed`, and the reason configuration can be
    written either way: an operator who sets ``MODEL_NAME=openai/qwen/qwen3.8-27b``
    (copying what the logs print) means the same model LM Studio lists bare as
    ``qwen/qwen3.8-27b``. A naive ``split("/", 1)[-1]`` would mangle the
    HuggingFace namespace into ``qwen3.8-27b``, which matches nothing.
    """
    for prefix in _LITELLM_PROVIDER_PREFIXES:
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def _positive_int(value: Any) -> int | None:
    """Return ``value`` as a positive int, or None. Booleans are not ints here."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _resolve_context_window(
    loaded_window: Any, max_window: Any, *, model_id: str
) -> tuple[int, str]:
    """Three rungs, no family constant. Returns ``(window, rung_name)``."""
    resolved = _positive_int(loaded_window)
    if resolved is not None:
        source = CONTEXT_SOURCE_LOADED
    else:
        resolved = _positive_int(max_window)
        if resolved is not None:
            source = CONTEXT_SOURCE_MAX
        else:
            resolved = DECLARED_DEFAULT_CONTEXT_WINDOW
            source = CONTEXT_SOURCE_DECLARED
    logger.info(
        "Context window for %s: %d tokens (resolved from %s)",
        model_id,
        resolved,
        source,
    )
    return resolved, source


async def resolve_stop_sequences(family: str, model_id: str) -> tuple[str, ...]:
    """Stop sequences for a model, keyed on the backend's family identifier.

    The family identifier was RENAMED between API generations, not dropped:
    ``/api/v0/models`` calls it ``arch`` and ``/api/v1/models`` calls it
    ``architecture``, carrying the identical value (``qwen3_5`` on the live
    box). Both feed the same ``FAMILY_PROFILES`` lookup, so the same model
    yields the same stop sequences on either generation and there is no
    precision loss on the preferred path.

    Only when the backend supplies no recognised family do we fall through to
    ``get_profile``'s substring rung — which is what that rung has always been
    for. ``api_base=None`` keeps it I/O-free: this seam owns the HTTP.
    """
    if family:
        family_profile = FAMILY_PROFILES.get(family)
        if family_profile is not None:
            return tuple(family_profile.stop_sequences or ())
    fallback = await get_profile(model_id, api_base=None)
    return tuple(fallback.stop_sequences or ())


@dataclass(frozen=True)
class ModelProfile:
    """Everything a completion call needs about the model that will answer it.

    ``reasoning`` is OBSERVED, never branched on. It is the ``capabilities
    .reasoning`` descriptor that ``/api/v1/models`` reports (absent on v0 and on
    :class:`StaticModelSource`) and it is the real signal behind the
    ``content or reasoning_content`` fallback that ADR-0007 step 3 consolidated
    from six copies into ``sentinel_shared.llm_call.extract_completion_text``.
    Recording it costs one field — and that extractor deliberately does NOT
    branch on it, because it is unset on exactly the backends with the thinnest
    metadata, where extraction still has to work.

    ``context_window_source`` names which rung of the context ladder produced
    ``context_window``, so an operator can tell a real loaded window from a
    declared floor without re-deriving it.

    ``capabilities_observed`` says whether ``capabilities`` came from a backend
    that was ASKED, or from configuration that merely declared. It is True for
    everything :class:`LMStudioModelSource` parses — including an entry that
    reports no capabilities at all, because a live backend staying silent about
    tool use IS an observation, and the destructive-sweep gate reads it as one.
    It is False for :class:`StaticModelSource`, where there is no backend to
    ask; see :meth:`ActiveModel._run_ladder` for what the distinction buys.

    ``tokenizer_encoding`` names the tiktoken encoding token counts against this
    profile are taken with. It is DECLARED, not observed — no backend reports a
    tiktoken name — and it exists so the approximation is stated rather than
    assumed. See :data:`DECLARED_TOKENIZER_ENCODING`.
    """

    model_id: str
    litellm_model: str
    api_base: str | None = None
    context_window: int = DECLARED_DEFAULT_CONTEXT_WINDOW
    stop_sequences: tuple[str, ...] = ()
    capabilities: frozenset[str] = frozenset()
    reasoning: Any | None = None
    family: str = ""
    task_kind: str = ""
    context_window_source: str = CONTEXT_SOURCE_DECLARED
    loaded: bool = True
    capabilities_observed: bool = True
    tokenizer_encoding: str = DECLARED_TOKENIZER_ENCODING

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True)
class ModelCandidates:
    """The two tiers a backend offers.

    ``loaded`` is what is running right now. ``reported`` is every non-embedding
    entry the backend listed, whatever its state — on a JIT-enabled LM Studio
    that is the set of DOWNLOADED models, most of them ``state: "not-loaded"``
    until the first request arrives.

    The tiers are NOT collapsed at the adapter: ``ActiveModel`` needs both to
    implement the loaded-first-then-downloaded rule, and an adapter that
    filtered the not-loaded entries away would make that rule impossible to
    write without a second HTTP call.
    """

    loaded: tuple[ModelProfile, ...] = ()
    reported: tuple[ModelProfile, ...] = ()


class ModelSource(Protocol):
    """A backend that can say which models it offers."""

    async def candidates(self) -> ModelCandidates:  # pragma: no cover - protocol
        ...


def _entries(payload: Any) -> list[Any]:
    """Extract the model list from either envelope shape (or a bare list)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "models"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _dedupe(profiles: Iterable[ModelProfile]) -> tuple[ModelProfile, ...]:
    """Collapse duplicate identities, preferring the loaded copy.

    The live ``/api/v1/models`` response really did return the nomic model
    twice — once with zero ``loaded_instances`` and once with one. Without this,
    a loaded model can be demoted into the not-loaded tier by its own stale
    duplicate.
    """
    seen: dict[str, ModelProfile] = {}
    order: list[str] = []
    for profile in profiles:
        existing = seen.get(profile.model_id)
        if existing is None:
            seen[profile.model_id] = profile
            order.append(profile.model_id)
        elif profile.loaded and not existing.loaded:
            seen[profile.model_id] = profile
    return tuple(seen[model_id] for model_id in order)


class LMStudioModelSource:
    """One adapter, both LM Studio API generations.

    ``GET /api/v1/models`` is preferred and ``GET /api/v0/models`` is the
    fallback when v1 answers 404 (an older LM Studio). One attempt each, no
    retry loop — a 404 from v1 is a version signal, not a transient failure —
    and the generation that answered is cached so the fallback probe is not
    repeated on every refresh.

    v1 is strictly better for everything this seam needs. ``capabilities`` is a
    property of the MODEL rather than of a loaded instance, so a not-loaded
    entry still carries them and ``for_task("structured")`` can filter the
    second tier correctly; ``loaded_instances`` makes the two-tier split fall
    out of the data rather than being imposed on it; and
    ``loaded_instances[0].config.context_length`` is the real loaded window.

    | Fact | v1 | v0 |
    |---|---|---|
    | identity | ``key`` | ``id`` |
    | loaded? | ``len(loaded_instances) > 0`` | ``state == "loaded"`` |
    | window | ``loaded_instances[0].config.context_length`` | ``loaded_context_length`` |
    | tool use | ``capabilities.trained_for_tool_use`` | ``"tool_use"`` in ``capabilities`` |
    | vision | ``capabilities.vision`` | ``type == "vlm"`` |
    | family | ``architecture`` | ``arch`` (same values) |
    | reasoning | ``capabilities.reasoning`` | not reported |
    | embeddings | ``type == "embedding"`` | ``type == "embeddings"`` |

    Note what v1 proves about ADR decision 3: v0 reports the live chat model as
    ``type: "vlm"`` and v1 reports the SAME model as ``type: "llm"`` with
    ``capabilities.vision: true``. Modality moved out of ``type`` between
    generations, so a ``type == "llm"`` inclusion filter would have been wrong
    on v0 and right only by accident on v1. The exclusion form is required.

    ``format`` (v1) / ``compatibility_type`` (v0) both report the runtime/quant
    format (``mlx`` on the live box). Neither is consumed; they are named here
    only so a future reader does not go hunting for where they went. Likewise
    ``loaded_instances[0].config.parallel``, ``variants`` / ``selected_variant``
    and the descriptive metadata (``display_name``, ``params_string``,
    ``publisher``, ``quantization``, ``size_bytes``, ``description``) are
    deliberately off the profile: the seam resolves a model KEY and lets LM
    Studio pick the variant.
    """

    def __init__(
        self,
        http_client: "httpx.AsyncClient",
        base_url: str,
        *,
        provider_prefix: str = "openai/",
        timeout: float = 5.0,
    ) -> None:
        self._client = http_client
        self._base_url = base_url
        # base_url is the /v1 URL; the model-list endpoints live under /api/.
        self._api_root = base_url.rstrip("/").removesuffix("/v1")
        self._provider_prefix = provider_prefix
        self._timeout = timeout
        self._generation: str | None = None

    @property
    def generation(self) -> str | None:
        """Which API generation answered, once one has. None before first use."""
        return self._generation

    async def candidates(self) -> ModelCandidates:
        payload, generation = await self._fetch()
        parsed: list[ModelProfile] = []
        for entry in _entries(payload):
            if not isinstance(entry, dict):
                continue
            if generation == GENERATION_V1:
                profile = await self._parse_v1(entry)
            else:
                profile = await self._parse_v0(entry)
            if profile is not None:
                parsed.append(profile)

        deduped = _dedupe(parsed)
        loaded = tuple(profile for profile in deduped if profile.loaded)
        return ModelCandidates(loaded=loaded, reported=deduped)

    async def _fetch(self) -> tuple[Any, str]:
        """One list fetch per refresh, on the generation that answers.

        Only a 404 from v1 selects the fallback. Any other failure (connect
        error, 5xx, malformed JSON) propagates so ``ActiveModel`` can serve
        last-known-good rather than mistaking an outage for an old backend.
        """
        if self._generation != GENERATION_V0:
            url = f"{self._api_root}/api/v1/models"
            response = await self._client.get(url, timeout=self._timeout)
            if response.status_code == 404:
                logger.info(
                    "LM Studio %s answered 404 — this backend predates the v1 model "
                    "API; falling back to /api/v0/models for the rest of this process",
                    url,
                )
                self._generation = GENERATION_V0
            else:
                response.raise_for_status()
                self._generation = GENERATION_V1
                return response.json(), GENERATION_V1

        url = f"{self._api_root}/api/v0/models"
        response = await self._client.get(url, timeout=self._timeout)
        response.raise_for_status()
        self._generation = GENERATION_V0
        return response.json(), GENERATION_V0

    async def _build(
        self,
        *,
        model_id: str,
        loaded: bool,
        loaded_window: Any,
        max_window: Any,
        capabilities: frozenset[str],
        reasoning: Any,
        family: str,
    ) -> ModelProfile:
        window, source = _resolve_context_window(
            loaded_window, max_window, model_id=model_id
        )
        return ModelProfile(
            model_id=model_id,
            litellm_model=_prefixed(model_id, self._provider_prefix),
            api_base=self._base_url,
            context_window=window,
            stop_sequences=await resolve_stop_sequences(family, model_id),
            capabilities=capabilities,
            reasoning=reasoning,
            family=family,
            context_window_source=source,
            loaded=loaded,
        )

    async def _parse_v1(self, entry: Mapping[str, Any]) -> ModelProfile | None:
        model_id = entry.get("key")
        if not isinstance(model_id, str) or not model_id:
            return None
        if str(entry.get("type") or "").lower() in EMBEDDING_TYPES:
            return None

        instances = entry.get("loaded_instances")
        instances = instances if isinstance(instances, list) else []
        loaded = len(instances) > 0

        # More than one instance: take the first and do NOT try to reconcile
        # differing context_length values across instances. The rung recorded on
        # the profile makes the choice visible.
        loaded_window: Any = None
        if loaded and isinstance(instances[0], dict):
            config = instances[0].get("config")
            if isinstance(config, Mapping):
                loaded_window = config.get("context_length")

        raw_capabilities = entry.get("capabilities")
        capabilities: set[str] = set()
        reasoning: Any = None
        if isinstance(raw_capabilities, Mapping):
            if raw_capabilities.get("trained_for_tool_use"):
                capabilities.add(CAPABILITY_TOOL_USE)
            if raw_capabilities.get("vision"):
                capabilities.add(CAPABILITY_VISION)
            reasoning = raw_capabilities.get("reasoning")

        family = entry.get("architecture")
        return await self._build(
            model_id=model_id,
            loaded=loaded,
            loaded_window=loaded_window,
            max_window=entry.get("max_context_length"),
            capabilities=frozenset(capabilities),
            reasoning=reasoning,
            family=family if isinstance(family, str) else "",
        )

    async def _parse_v0(self, entry: Mapping[str, Any]) -> ModelProfile | None:
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id:
            return None
        entry_type = str(entry.get("type") or "").lower()
        if entry_type in EMBEDDING_TYPES:
            return None

        raw_capabilities = entry.get("capabilities")
        raw_capabilities = raw_capabilities if isinstance(raw_capabilities, list) else []
        capabilities: set[str] = set()
        if CAPABILITY_TOOL_USE in raw_capabilities:
            capabilities.add(CAPABILITY_TOOL_USE)
        # v0 reports modality through `type`; v1 moved it into `capabilities`.
        # Deriving it here is what makes the two generations produce equivalent
        # profiles for the same model.
        if entry_type == "vlm":
            capabilities.add(CAPABILITY_VISION)

        family = entry.get("arch")
        return await self._build(
            model_id=model_id,
            loaded=entry.get("state") == "loaded",
            loaded_window=entry.get("loaded_context_length"),
            max_window=entry.get("max_context_length"),
            capabilities=frozenset(capabilities),
            reasoning=None,  # v0 does not report a reasoning descriptor.
            family=family if isinstance(family, str) else "",
        )


class StaticModelSource:
    """Config-derived candidates — no I/O at all.

    Serves Claude from the model seed and the undiscoverable local backends
    (ollama, llama.cpp) as declared profiles, so their 4096 becomes DECLARED
    rather than accidental. Four adapters, one per backend, was rejected as
    speculative; a real adapter can be added later against this proven
    interface.

    It is also the test substitute, which is why it is constructible from a
    plain list of profiles.

    Profiles built by :func:`build_static_profiles` carry
    ``capabilities_observed=False``: this adapter asks nothing, so its
    capability set is a declaration rather than evidence, and the task filter
    treats it accordingly.
    """

    def __init__(self, profiles: Sequence[ModelProfile]) -> None:
        self._profiles = tuple(profiles)

    async def candidates(self) -> ModelCandidates:
        return ModelCandidates(loaded=self._profiles, reported=self._profiles)


_PROVIDER_STATIC_SPEC: dict[str, tuple[str, str, str]] = {
    # provider -> (settings attr for the model id, litellm prefix, settings attr for api base)
    "lmstudio": ("model_name", "openai/", "lmstudio_base_url"),
    "claude": ("claude_model", "", ""),
    "ollama": ("ollama_model", "ollama/", "ollama_base_url"),
    "llamacpp": ("llamacpp_model", "openai/", "llamacpp_base_url"),
}


async def build_static_profiles(
    settings: Any,
    *,
    provider: str | None = None,
    seed: Mapping[str, Any] | None = None,
) -> list[ModelProfile]:
    """Build the config-derived profile for ``provider`` (default: the active one).

    ``MODEL_NAME``'s only remaining role is this: data for the no-live-backend
    case. It is never how a live backend's model is chosen.
    """
    provider = provider or getattr(settings, "ai_provider", "lmstudio") or "lmstudio"
    model_attr, prefix, base_attr = _PROVIDER_STATIC_SPEC.get(
        provider, _PROVIDER_STATIC_SPEC["lmstudio"]
    )
    model_id = getattr(settings, model_attr, None) or getattr(settings, "model_name", "")
    if not model_id:
        return []

    if seed is None:
        # Imported lazily: model_registry imports the litellm client stack, and
        # this seam is imported by composition before that graph is built.
        from app.services.model_registry import _load_seed  # noqa: PLC0415

        seed = _load_seed()

    capabilities: set[str] = set()
    window = DECLARED_DEFAULT_CONTEXT_WINDOW
    window_source = CONTEXT_SOURCE_DECLARED
    seed_entry = seed.get(model_id) if seed else None
    if seed_entry is not None:
        seed_window = _positive_int(getattr(seed_entry, "context_window", None))
        if seed_window is not None:
            window = seed_window
            window_source = CONTEXT_SOURCE_MAX
        seed_capabilities = getattr(seed_entry, "capabilities", None) or {}
        if seed_capabilities.get("function_calling"):
            capabilities.add(CAPABILITY_TOOL_USE)
        if seed_capabilities.get("vision"):
            capabilities.add(CAPABILITY_VISION)

    api_base = getattr(settings, base_attr, None) if base_attr else None
    logger.info(
        "Static model profile for provider %r: %s (%d tokens, resolved from %s)",
        provider,
        model_id,
        window,
        window_source,
    )
    return [
        ModelProfile(
            model_id=model_id,
            litellm_model=_prefixed(model_id, prefix),
            api_base=api_base,
            context_window=window,
            stop_sequences=await resolve_stop_sequences("", model_id),
            capabilities=frozenset(capabilities),
            reasoning=None,  # never observed without a live backend
            family="",
            context_window_source=window_source,
            loaded=True,
            # Nothing was asked. ``models-seed.json``'s ``function_calling``
            # flags are a claim about a NAME (the seed's ``local-model`` entry
            # says false about a placeholder id), not an observation of the
            # model a backend is serving — so they must not be able to veto a
            # task the way a live backend's silence does.
            capabilities_observed=False,
        )
    ]


async def static_model_source(
    settings: Any,
    *,
    provider: str | None = None,
    seed: Mapping[str, Any] | None = None,
) -> StaticModelSource:
    """Async factory so :class:`StaticModelSource` itself stays I/O-free."""
    return StaticModelSource(
        await build_static_profiles(settings, provider=provider, seed=seed)
    )


class ActiveModel:
    """``for_task(kind) -> ModelProfile``, behind a TTL, refusing to guess.

    **The capability filter runs FIRST and narrows the candidate set;
    preference then applies within it.** The inverse — preference first, filter
    as a later rung — is a defect: a filter that only runs after preference has
    already chosen cannot narrow anything.

    1. Task-capability filter.
    2. ``model_task_{kind}``  (operator pin)
    3. ``model_preferred``    (operator pin)
    4. Last-known-good, when it is still among the filtered candidates.
    5. ``model_name``, when it is among the filtered candidates.
    6. The sole surviving candidate.
    7. Refuse to guess — RAISE.

    **When the backend is live, the loaded set is the sole source of truth**
    (ADR decision 4 as amended 2026-09-08). Configuration may only DISAMBIGUATE
    among candidates the backend reported; it may never name one that is not
    reported at all, which is why rungs 2, 3 and 5 all carry the same
    in-the-candidate-set guard and why rung 7 raises. An earlier draft had rung
    7 return the configured ``model_name`` unconfirmed. That is not a fallback;
    it is the bug this ADR exists to remove, wearing the fallback's clothes —
    the deployed container was resolving ``google/gemma-4-31b`` because
    configuration named it, while LM Studio served only ``qwen/qwen3.8-27b`` and
    answered by silently substituting the model it actually had.

    **Last-known-good sits ABOVE ``model_name``, deliberately.** ``MODEL_NAME``
    is documented in ``config.py`` as a tracked *default*, not an authoritative
    pin — it can name a model that is not loaded at all, which is exactly the
    ``exo-model-notfound-502`` failure. Last-known-good is verified
    still-loaded by construction, because rung 4 only fires when the remembered
    model survives the candidate filter. Verified-loaded evidence beats an
    unverified default, and the ordering buys continuity: a second model
    appearing in LM Studio must not make a running system abandon the model it
    has been successfully using. The operator keeps absolute control through
    rungs 2 and 3, which sit above it.

    **Two tiers.** The whole ladder runs against the LOADED tier. If — and only
    if — that tier is empty, the same ladder runs against the REPORTED tier.
    That is inside the refuse-to-guess rule, not an exception to it: a model the
    backend itself listed is not a model invented from configuration. Without
    it, a stock JIT-enabled LM Studio (where nothing loads until the first
    request arrives) resolves nothing and raises, and the system is unusable on
    a normal shipped configuration.

    **Operator pins are absolute** — the one deliberate exception to
    filter-first. A pin naming a model that IS reported but does NOT pass the
    capability filter still wins, because an operator who names a model gets
    that model; the cost is paid with a WARNING naming the model, the task kind
    and the missing capability. A pin naming a model the backend never reported
    is ignored and the ladder continues.

    **Every configured id is matched with the litellm provider tag normalised
    away** (rungs 2, 3 and 5). LM Studio lists ``qwen/qwen3.8-27b`` while the
    logs and every call string say ``openai/qwen/qwen3.8-27b``, so an operator
    who copies one form into configuration must not silently get the refusal
    rung. Normalisation decides only whether a configured id MATCHES a reported
    candidate; it never widens WHICH candidates exist, so a prefixed id that is
    not loaded still fails to match and still reaches rung 7.
    """

    def __init__(
        self,
        sources: Sequence[ModelSource],
        settings: Any = None,
        *,
        clock: Callable[[], float] | None = None,
        ttl_seconds: float | None = None,
    ) -> None:
        self._sources = tuple(sources)
        self._settings = settings
        self._clock = clock or time.monotonic
        if ttl_seconds is None:
            ttl_seconds = getattr(settings, "model_ttl_seconds", None) or DEFAULT_TTL_SECONDS
        self._ttl = float(ttl_seconds)
        self._candidates: ModelCandidates | None = None
        self._fetched_at: float | None = None
        self._last_known_good: dict[str, ModelProfile] = {}

    # ---- public surface -------------------------------------------------

    def invalidate(self) -> None:
        """Mark the cache stale so the next ``for_task`` refetches.

        Plan 02 calls this from ``ProviderRouter`` on the
        ``litellm.NotFoundError`` path (the backend saying "I do not serve that
        model" is the one signal worth spending a refresh on).
        """
        self._fetched_at = None

    def cached_profile(self, kind: str) -> ModelProfile | None:
        """The last profile successfully resolved for ``kind``, without refreshing.

        Synchronous on purpose: it is what a sync caller (the message-request
        factory) reads to record the model that will actually answer.
        """
        return self._last_known_good.get(kind)

    async def for_task(self, kind: str) -> ModelProfile:
        now = self._clock()
        fresh = (
            self._candidates is not None
            and self._fetched_at is not None
            and (now - self._fetched_at) < self._ttl
        )
        if not fresh:
            candidates, served = await self._refresh(kind)
            if served is not None:
                return served
            self._candidates = candidates
            self._fetched_at = now

        profile = self._resolve(kind, self._candidates)
        profile = replace(profile, task_kind=kind)
        profile = self._apply_cap(profile)
        self._last_known_good[kind] = profile
        return profile

    # ---- refresh --------------------------------------------------------

    async def _refresh(
        self, kind: str
    ) -> tuple[ModelCandidates, ModelProfile | None]:
        """Ask each source in turn. Returns ``(candidates, served_last_known_good)``.

        A source that RAISES is a failed refresh: per ADR decision 1 the
        previously-resolved profile is served rather than failing the request,
        and it is served UNCONDITIONALLY — the backend told us nothing, so the
        capability data is stale too and re-filtering against it would be
        pretending to know something we do not. Only when there is no
        last-known-good does resolution fall through to the next source
        (``StaticModelSource``).

        A source that ANSWERS is the end of the search, even when it reports
        nothing. When the backend is live the loaded set is the sole source of
        truth, so a reachable backend that reports no usable model must reach
        the refusal rung — falling through to ``StaticModelSource`` there would
        answer a live "I have nothing" with a model from configuration, which is
        exactly the phantom ADR decision 4 forbids.
        """
        errors: list[Exception] = []
        for source in self._sources:
            try:
                candidates = await source.candidates()
            except Exception as exc:  # noqa: BLE001 - every backend failure is equal here
                errors.append(exc)
                last_known_good = self._last_known_good.get(kind)
                if last_known_good is not None:
                    logger.warning(
                        "Model refresh failed (%s: %s) — serving last-known-good %r "
                        "for task %r rather than failing the request",
                        type(exc).__name__,
                        exc,
                        last_known_good.model_id,
                        kind,
                    )
                    return ModelCandidates(), last_known_good
                logger.warning(
                    "Model source %s failed (%s: %s) and there is no last-known-good "
                    "for task %r — trying the next source",
                    type(source).__name__,
                    type(exc).__name__,
                    exc,
                    kind,
                )
                continue
            return candidates, None

        if errors:
            raise ModelSelectorError(
                f"No model source could answer for task_kind={kind!r}: "
                f"{type(errors[0]).__name__}: {errors[0]}"
            ) from errors[0]
        return ModelCandidates(), None

    # ---- resolution -----------------------------------------------------

    def _resolve(self, kind: str, candidates: ModelCandidates | None) -> ModelProfile:
        if candidates is None or not candidates.reported:
            raise ModelSelectorError(
                f"No model candidates for task_kind={kind!r} — no source reported a "
                "non-embedding model. Refusing to invent one from configuration "
                "(ADR-0007 decision 4)."
            )

        reported_ids = {
            _unprefixed(profile.model_id) for profile in candidates.reported
        }

        if candidates.loaded:
            winner = self._run_ladder(kind, candidates.loaded, reported_ids)
            if winner is None:
                raise ModelSelectorError(
                    f"{len(candidates.loaded)} model(s) loaded for task_kind={kind!r} "
                    "and none could be disambiguated. Configuration may only "
                    "disambiguate among loaded candidates, never name one that is not "
                    "loaded — refusing to return a phantom (ADR-0007 decision 4)."
                )
            return winner

        winner = self._run_ladder(kind, candidates.reported, reported_ids)
        if winner is None:
            raise ModelSelectorError(
                f"Nothing is loaded and the {len(candidates.reported)} model(s) the "
                f"backend reports could not be disambiguated for task_kind={kind!r}."
            )
        logger.info(
            "Resolved %r for task %r from the reported tier — it is not currently "
            "loaded and the backend is expected to JIT-load it on first use",
            winner.model_id,
            kind,
        )
        return winner

    def _run_ladder(
        self,
        kind: str,
        tier: Sequence[ModelProfile],
        reported_ids: set[str],
    ) -> ModelProfile | None:
        required = TASK_CAPABILITY_REQUIREMENTS.get(kind, frozenset())
        filtered = [
            profile
            for profile in tier
            if required.issubset(profile.capabilities) or not profile.capabilities_observed
        ]
        if required:
            for profile in filtered:
                if not profile.capabilities_observed and not required.issubset(
                    profile.capabilities
                ):
                    logger.info(
                        "Config-derived candidate %r admitted for task %r without "
                        "evidence of %s — no backend was reachable to ask, and "
                        "refusing here would make an offline deployment unable to do "
                        "structured work at all. The destructive-sweep gate does NOT "
                        "take this path: probe_classifier_model_ready asks a live "
                        "backend only, so it still fails closed",
                        profile.model_id,
                        kind,
                        ", ".join(sorted(required - profile.capabilities)) or "unknown",
                    )
        filtered_ids = {profile.model_id for profile in filtered}

        # Configuration and the backend need not agree on the litellm provider
        # tag. LM Studio lists ``qwen/qwen3.8-27b``; the logs, the registry and
        # every litellm call string say ``openai/qwen/qwen3.8-27b``, and an
        # operator copying either into MODEL_NAME / MODEL_PREFERRED means the
        # same model. Both spellings resolve to the same candidate.
        #
        # This normalisation decides whether a configured id MATCHES a reported
        # candidate. It is emphatically NOT a way for a non-loaded id to be
        # returned: every rung still looks the result up in this map, which
        # contains only candidates the backend reported.
        by_id: dict[str, ModelProfile] = {}
        for profile in tier:
            by_id.setdefault(profile.model_id, profile)
            by_id.setdefault(_unprefixed(profile.model_id), profile)
            by_id.setdefault(profile.litellm_model, profile)

        # Rungs 2 and 3 — operator pins, in order. Both are absolute over the
        # capability filter and both are still bound by the candidate set.
        pins = (
            (f"MODEL_TASK_{kind.upper()}", self._setting(f"model_task_{kind}")),
            ("MODEL_PREFERRED", self._setting("model_preferred")),
        )
        for setting_name, pinned in pins:
            if not pinned:
                continue
            candidate = by_id.get(pinned)
            if candidate is None:
                self._log_ignored_config(setting_name, pinned, reported_ids)
                continue
            if candidate.model_id in filtered_ids:
                return candidate
            missing = ", ".join(sorted(required - candidate.capabilities)) or "unknown"
            logger.warning(
                "%s=%r pins %r for task %r but the backend does not report the %s "
                "capability for it — honouring the operator pin anyway; structured "
                "output from this model may be malformed",
                setting_name,
                pinned,
                candidate.model_id,
                kind,
                missing,
            )
            return candidate

        # Rung 4 — last-known-good, only while it is still a candidate.
        remembered = self._last_known_good.get(kind)
        if remembered is not None and remembered.model_id in filtered_ids:
            winner = by_id[remembered.model_id]
            configured = self._setting("model_name")
            if configured and _unprefixed(configured) != _unprefixed(winner.model_id):
                logger.info(
                    "Model %r selected for task %r as last-known-good, preferred over "
                    "MODEL_NAME=%r — configuration and the running system name "
                    "different models",
                    winner.model_id,
                    kind,
                    configured,
                )
            return winner

        # Rung 5 — the configured default, only when the backend reports it.
        configured = self._setting("model_name")
        if configured:
            candidate = by_id.get(configured)
            if candidate is None:
                self._log_ignored_config("MODEL_NAME", configured, reported_ids)
            elif candidate.model_id in filtered_ids:
                return candidate

        # Rung 6 — sole surviving candidate. With exactly one there is nothing
        # to guess between, so this is not a guess.
        if len(filtered) == 1:
            return filtered[0]

        # Rung 7 — refuse.
        return None

    # ---- helpers --------------------------------------------------------

    def _setting(self, name: str) -> str | None:
        value = getattr(self._settings, name, None)
        return value or None

    @staticmethod
    def _log_ignored_config(
        setting_name: str, value: str, reported_ids: set[str]
    ) -> None:
        """One INFO line when a configured value names a model nobody reported.

        Without it the operator gets a raise at rung 7 with no indication that
        the configuration they set was thrown away. Silent when the value names
        a model the backend DID report but that is not in the tier currently
        being searched — that is the ordinary JIT case, not a misconfiguration.
        """
        if _unprefixed(value) in reported_ids:
            return
        logger.info(
            "%s=%r ignored — the backend does not report that model, so it cannot be "
            "selected; continuing model resolution",
            setting_name,
            value,
        )

    def _apply_cap(self, profile: ModelProfile) -> ModelProfile:
        """Apply ``MODEL_CONTEXT_CAP`` as a ceiling. It never raises a window.

        "What the server accepts" and "what produces usable output" are
        different numbers: a 71936-token context on the 24 GB host drove the
        model into repetition loops and 200s timeouts. That ceiling is host- and
        model-specific and belongs in configuration, not code.
        """
        cap = _positive_int(getattr(self._settings, "model_context_cap", None))
        if cap is None or profile.context_window <= cap:
            return profile
        logger.info(
            "Context window for %s capped from %d to %d by MODEL_CONTEXT_CAP",
            profile.model_id,
            profile.context_window,
            cap,
        )
        return replace(profile, context_window=cap)
