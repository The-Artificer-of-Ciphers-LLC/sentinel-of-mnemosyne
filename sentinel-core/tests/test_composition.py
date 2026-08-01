"""Behavioral tests for the compose root (app.composition).

Each test CALLS ``build_application`` or ``build_provider_router`` directly and
asserts on observable graph state — no source-grep, no tautologies, no
mock-call-shape-only assertions (Behavioral-Test-Only Rule). Fakes are passed
via explicit kwargs (W1) so typos surface as TypeErrors rather than being
silently swallowed.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.composition import (
    AppGraph,
    build_application,
    build_provider_router,
    initialize_startup,
)
from app.vault import VaultUnreachableError
from app.config import Settings
from app.services.provider_router import ProviderRouter


def _settings(**overrides) -> Settings:
    """Build a Settings instance for tests with deterministic defaults.

    Uses a fixed sentinel_api_key (required field) and disables auto-discovery
    so model resolution short-circuits to ``settings.model_name`` and does not
    touch the network.
    """
    base: dict = {
        "sentinel_api_key": "test-key",
        "model_auto_discover": False,
        "model_name": "test-model",
        "embedding_model": "test-embedding-model",
        "lmstudio_base_url": "http://lmstudio.test/v1",
        "ai_provider": "lmstudio",
        "ai_fallback_provider": "none",
        "anthropic_api_key": "",
        "ollama_model": "ollama-test",
        "llamacpp_model": "llamacpp-test",
    }
    base.update(overrides)
    return Settings(**base)


def _empty_models_handler(request: httpx.Request) -> httpx.Response:
    """MockTransport handler that returns empty model lists / 404 for everything.

    Lets ``build_provider_router`` walk through model discovery + profile +
    embedding probe deterministically without any real network. Each branch
    falls into its non-fatal path and the function returns successfully.
    """
    # /v1/models or /api/v0/models — empty list
    if request.url.path.endswith("/models") or "/api/v0/models" in request.url.path:
        return httpx.Response(200, json={"data": []})
    # Anthropic registry
    if request.url.host == "api.anthropic.com":
        return httpx.Response(404, json={"error": "not used in test"})
    return httpx.Response(404, json={"error": "unmocked"})


@pytest.fixture
def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_empty_models_handler))


class _FakeVault:
    """Minimal in-memory vault double — implements only the surface we test."""

    async def read_persona(self) -> str | None:
        return "fake persona"

    async def check_health(self) -> bool:
        return True


# ---- Tests ----


async def test_build_application_uses_provided_vault_fake(http_client):
    """When ``vault=`` kwarg is supplied, the graph holds the same instance."""
    fake_vault = _FakeVault()
    settings = _settings()

    graph = await build_application(settings, http_client, vault=fake_vault)

    assert isinstance(graph, AppGraph)
    assert graph.vault is fake_vault


async def test_build_application_constructs_default_provider_when_not_overridden(
    http_client,
):
    """No ``ai_provider=`` kwarg → composition builds the production ProviderRouter."""
    settings = _settings(ai_provider="lmstudio")

    graph = await build_application(settings, http_client, vault=_FakeVault())

    assert isinstance(graph.ai_provider, ProviderRouter)
    assert graph.ai_provider_name == "lmstudio"
    # The graph should expose all 15 fields populated
    for field in (
        "settings",
        "http_client",
        "model_registry",
        "context_window",
        "lmstudio_stop_sequences",
        "ai_provider",
        "ai_provider_name",
        "vault",
        "embedding_model_loaded",
        "injection_filter",
        "output_scanner",
        "message_processor",
        "module_registry",
        "embeddings",
        "note_classifier_fn",
    ):
        assert getattr(graph, field) is not None or field in (
            "lmstudio_stop_sequences",
            "module_registry",
        )


async def test_build_provider_router_picks_primary_from_settings(http_client):
    """Two distinct settings configurations produce routers with matching ai_provider_name."""
    settings_lm = _settings(ai_provider="lmstudio", ai_fallback_provider="none")
    settings_ollama = _settings(ai_provider="ollama", ai_fallback_provider="none")

    bundle_lm = await build_provider_router(settings_lm, http_client)
    bundle_ollama = await build_provider_router(settings_ollama, http_client)

    assert isinstance(bundle_lm.router, ProviderRouter)
    assert isinstance(bundle_ollama.router, ProviderRouter)
    assert bundle_lm.ai_provider_name == "lmstudio"
    assert bundle_ollama.ai_provider_name == "ollama"
    # Distinct configurations produce distinct router instances
    assert bundle_lm.router is not bundle_ollama.router


async def test_lmstudio_provider_construction_args_pinned_after_openai_compatible_refactor(
    http_client, monkeypatch
):
    """D-02/Pitfall 5 regression: extends test_build_provider_router_picks_primary_from_settings's
    LM Studio coverage by PINNING the exact LiteLLMProvider(model_string=...,
    api_base=..., api_key=...) construction args — not just "a provider was
    returned" — proving the openai_compatible table-driven refactor (Task 2)
    did not silently change LM Studio's construction (e.g. dropping
    api_key="lmstudio", a common AuthenticationError symptom)."""
    captured: dict[str, "_CapturingProvider"] = {}

    class _CapturingProvider:
        def __init__(self, model_string, api_base=None, api_key=None):
            self.model_string = model_string
            self.api_base = api_base
            self.api_key = api_key
            captured[model_string] = self

        async def complete(self, messages, stop=None, temperature=None):
            return f"model={self.model_string}|api_base={self.api_base}|api_key={self.api_key}"

    monkeypatch.setattr("app.composition.LiteLLMProvider", _CapturingProvider)

    settings = _settings(
        ai_provider="lmstudio",
        ai_fallback_provider="none",
        lmstudio_base_url="http://lmstudio.test/v1",
    )
    bundle = await build_provider_router(settings, http_client)

    # model_auto_discover=False (see _settings()) short-circuits discovery to
    # "openai/{model_name}" without touching the network.
    lmstudio_key = "openai/test-model"
    assert lmstudio_key in captured
    result = await bundle.router.complete([{"role": "user", "content": "hi"}])
    assert result == (
        f"model={lmstudio_key}|api_base=http://lmstudio.test/v1|api_key=lmstudio"
    )


async def test_build_application_typo_kwarg_raises_typeerror(http_client):
    """Explicit-kwargs (W1) — a typo like ``vualt=`` must raise TypeError, not be swallowed."""
    settings = _settings()

    with pytest.raises(TypeError):
        # Intentional typo: 'vualt' instead of 'vault'. The signature is
        # explicit-kwargs (no **fakes bag), so Python rejects this at the
        # call boundary — exactly what W1 was designed to ensure.
        await build_application(  # type: ignore[call-arg]
            settings, http_client, vualt=_FakeVault()
        )


async def test_initialize_startup_pins_route_context_and_minimal_state(
    monkeypatch,
):
    """initialize_startup pins route_ctx + minimal non-route state onto app.state."""
    fake_vault = AsyncMock()
    fake_vault.read_persona = AsyncMock(return_value="persona")
    # read_note must return a real str (not an unconfigured AsyncMock) —
    # both startup rebuild background tasks (embedding-index + links-index)
    # call vault.read_note(...).strip(); an unconfigured AsyncMock's default
    # return_value is itself an AsyncMock, so `.strip()` on it silently
    # creates and discards a coroutine (RuntimeWarning: coroutine
    # 'AsyncMockMixin._execute_mock_call' was never awaited). Production
    # Vault implementations (ObsidianVault/FakeVault) always return str.
    fake_vault.read_note = AsyncMock(return_value="")
    fake_router = object()
    fake_graph = SimpleNamespace(
        vault=fake_vault,
        message_processor=object(),
        settings=SimpleNamespace(model_name="test-model"),
        http_client=object(),
        context_window=8192,
        lmstudio_stop_sequences=["</s>"],
        note_classifier_fn=AsyncMock(),
        embeddings=SimpleNamespace(embed=AsyncMock(return_value=[])),
        module_registry={},
        ai_provider_name="lmstudio",
        ai_provider=fake_router,
        recall=None,
    )

    async def _fake_build_application(_settings, _http_client):
        return fake_graph

    monkeypatch.setattr("app.composition.build_application", _fake_build_application)

    app = SimpleNamespace(state=SimpleNamespace())
    result = await initialize_startup(app, SimpleNamespace(), object())

    assert result.warnings == []
    assert app.state.route_ctx.vault is fake_vault
    assert app.state.settings is fake_graph.settings
    assert app.state.vault is fake_vault
    # D-09 prerequisite: RouteContext exposes the ProviderRouter itself, pinned
    # from graph.ai_provider (not just the ai_provider_name string).
    assert app.state.route_ctx.ai_provider is fake_router


async def test_initialize_startup_returns_warning_when_vault_unreachable(
    monkeypatch,
):
    """Vault transport failures are non-fatal and surfaced as warnings."""
    fake_vault = AsyncMock()
    fake_vault.read_persona = AsyncMock(side_effect=VaultUnreachableError("down"))
    # See test_initialize_startup_pins_route_context_and_minimal_state for
    # why read_note must return a real str.
    fake_vault.read_note = AsyncMock(return_value="")
    fake_graph = SimpleNamespace(
        vault=fake_vault,
        message_processor=object(),
        settings=SimpleNamespace(model_name="test-model"),
        http_client=object(),
        context_window=8192,
        lmstudio_stop_sequences=[],
        note_classifier_fn=AsyncMock(),
        embeddings=SimpleNamespace(embed=AsyncMock(return_value=[])),
        module_registry={},
        ai_provider_name="lmstudio",
        ai_provider=object(),
        recall=None,
    )

    async def _fake_build_application(_settings, _http_client):
        return fake_graph

    monkeypatch.setattr("app.composition.build_application", _fake_build_application)

    app = SimpleNamespace(state=SimpleNamespace())
    result = await initialize_startup(app, SimpleNamespace(), object())

    assert len(result.warnings) == 1
    assert "memory features degraded" in result.warnings[0]


async def test_initialize_startup_raises_when_persona_missing(monkeypatch):
    """Missing persona is a hard startup failure (ADR-0001)."""
    fake_vault = AsyncMock()
    fake_vault.read_persona = AsyncMock(return_value=None)
    fake_graph = SimpleNamespace(
        vault=fake_vault,
        message_processor=object(),
        settings=SimpleNamespace(model_name="test-model"),
        http_client=object(),
        context_window=8192,
        lmstudio_stop_sequences=[],
        note_classifier_fn=AsyncMock(),
        embeddings=SimpleNamespace(embed=AsyncMock(return_value=[])),
        module_registry={},
        ai_provider_name="lmstudio",
        ai_provider=object(),
        recall=None,
    )

    async def _fake_build_application(_settings, _http_client):
        return fake_graph

    monkeypatch.setattr("app.composition.build_application", _fake_build_application)

    app = SimpleNamespace(state=SimpleNamespace())
    with pytest.raises(RuntimeError, match="sentinel/persona.md missing"):
        await initialize_startup(app, SimpleNamespace(), object())


async def test_build_application_wires_semantic_recall_with_no_prefix_active_model(http_client):
    """Composition wiring assertion (T-40-11, D-12): build_application produces a Recall
    whose injected SemanticRecall.active_model equals settings.embedding_model (no 'openai/' prefix).

    Proves that the composition root uses settings.embedding_model (bare model id)
    and NOT embeddings._model (which carries the 'openai/' prefix). An 'openai/'
    prefix would make every exact-string model-match in SemanticRecall fail (D-12).
    """
    from app.services.recall import SemanticRecall

    settings = _settings(embedding_model="nomic-embed-text-v1.5")
    vault = _FakeVault()

    # Pass recall=None to exercise the full 'if recall is None:' wiring path
    graph = await build_application(
        settings, http_client, vault=vault, recall=None
    )

    assert isinstance(graph.recall, object), "graph.recall should be a Recall instance"
    # Access the injected semantic strategy
    semantic_strategy = graph.recall._semantic_strategy  # type: ignore[attr-defined]
    assert semantic_strategy is not None, (
        "Recall must have a SemanticRecall strategy wired by build_application"
    )
    assert isinstance(semantic_strategy, SemanticRecall), (
        f"Expected SemanticRecall, got {type(semantic_strategy)}"
    )
    # The active_model must be the bare settings value, NOT prefixed with 'openai/'
    assert semantic_strategy._active_model == settings.embedding_model, (
        f"SemanticRecall.active_model should be {settings.embedding_model!r} "
        f"(no 'openai/' prefix, D-12), got {semantic_strategy._active_model!r}"
    )
    assert not semantic_strategy._active_model.startswith("openai/"), (
        f"active_model must NOT have 'openai/' prefix (D-12, T-40-11), "
        f"got {semantic_strategy._active_model!r}"
    )


async def test_build_application_wires_embeddings_from_embedding_base_url(
    http_client, monkeypatch
):
    """D-02/D-04 (Pitfall 3): both embeddings call sites in build_application —
    the Embeddings(...) construction AND the probe_embedding_model_loaded(...)
    call — must read settings.embedding_base_url, NOT the chat backend's
    lmstudio_base_url. These are two independent reads; fixing only one
    leaves the other silently wired to the wrong backend.
    """
    import app.composition as composition_module

    settings = _settings(
        embedding_base_url="http://embeddings.test/v1",
        lmstudio_base_url="http://lmstudio.test/v1",
    )
    assert settings.embedding_base_url != settings.lmstudio_base_url

    construction_calls: list[dict] = []
    probe_calls: list[tuple] = []

    class _SpyEmbeddings:
        def __init__(self, http_client, base_url, model, api_key=""):
            construction_calls.append({"base_url": base_url, "model": model, "api_key": api_key})
            self.embed = AsyncMock(return_value=[])

    async def _spy_probe(http_client, base_url, model):
        probe_calls.append((base_url, model))
        return True

    monkeypatch.setattr(composition_module, "Embeddings", _SpyEmbeddings)
    monkeypatch.setattr(composition_module, "probe_embedding_model_loaded", _spy_probe)

    graph = await build_application(settings, http_client, vault=_FakeVault())

    assert len(construction_calls) == 1, "Embeddings(...) must be constructed exactly once"
    assert construction_calls[0]["base_url"] == settings.embedding_base_url, (
        f"Embeddings(...) construction must read settings.embedding_base_url, "
        f"got {construction_calls[0]['base_url']!r}"
    )

    assert len(probe_calls) == 1, "probe_embedding_model_loaded(...) must be called exactly once"
    assert probe_calls[0][0] == settings.embedding_base_url, (
        f"probe_embedding_model_loaded(...) must read settings.embedding_base_url, "
        f"got {probe_calls[0][0]!r}"
    )

    assert graph is not None


# Suppress unused-import warning when running with json available
_ = json


# ---------------------------------------------------------------------------
# Phase 40 Plan 04 — Task 4: startup rewire + admin probe wiring tests (RED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_startup_calls_rebuild_embedding_index_not_run_sweep(
    monkeypatch,
):
    """initialize_startup must schedule rebuild_embedding_index (NOT run_sweep).

    Monkeypatches BOTH:
    - vault_sweeper.run_sweep → assert never awaited
    - vault_sweeper.rebuild_embedding_index → assert awaited once with
      model_loaded=graph.embedding_model_loaded
    """
    import asyncio as _asyncio

    run_sweep_called = []
    rebuild_called = []

    async def _fake_run_sweep(*args, **kwargs):
        run_sweep_called.append((args, kwargs))

    async def _fake_rebuild(vault, embedder, *, model_loaded=True, source_folder=""):
        rebuild_called.append({"vault": vault, "embedder": embedder, "model_loaded": model_loaded})

    monkeypatch.setattr("app.services.vault_sweeper.run_sweep", _fake_run_sweep)
    monkeypatch.setattr("app.services.vault_sweeper.rebuild_embedding_index", _fake_rebuild)
    # This test is scoped to the embedding-index startup wiring; stub out
    # the (unrelated) links-index startup rebuild so it doesn't touch
    # fake_vault's unconfigured attributes on a real code path.
    monkeypatch.setattr(
        "app.services.links_sidecar_index.rebuild_links_index", AsyncMock(return_value={})
    )

    fake_vault = AsyncMock()
    fake_vault.read_persona = AsyncMock(return_value="persona")
    fake_embedder = AsyncMock(return_value=[])
    fake_graph = SimpleNamespace(
        vault=fake_vault,
        message_processor=object(),
        settings=SimpleNamespace(model_name="test-model"),
        http_client=object(),
        context_window=8192,
        lmstudio_stop_sequences=[],
        note_classifier_fn=AsyncMock(),
        embeddings=SimpleNamespace(embed=fake_embedder),
        module_registry={},
        ai_provider_name="lmstudio",
        ai_provider=object(),
        recall=None,
        embedding_model_loaded=True,
    )

    async def _fake_build_application(_settings, _http_client):
        return fake_graph

    monkeypatch.setattr("app.composition.build_application", _fake_build_application)

    app = SimpleNamespace(state=SimpleNamespace())
    await initialize_startup(app, SimpleNamespace(), object())

    # Allow background tasks to run
    await _asyncio.sleep(0)

    assert len(run_sweep_called) == 0, (
        f"run_sweep must NEVER be called by initialize_startup; was called {len(run_sweep_called)} times"
    )
    assert len(rebuild_called) == 1, (
        f"rebuild_embedding_index must be awaited once; was called {len(rebuild_called)} times"
    )
    assert rebuild_called[0]["model_loaded"] == fake_graph.embedding_model_loaded, (
        f"rebuild must be called with model_loaded=graph.embedding_model_loaded; "
        f"got model_loaded={rebuild_called[0]['model_loaded']!r}"
    )


@pytest.mark.asyncio
async def test_initialize_startup_passes_embedding_model_loaded_from_graph(
    monkeypatch,
):
    """When embedding_model_loaded is False on the graph, rebuild_embedding_index
    must be called with model_loaded=False — so the index rebuild skips embedding
    and no crash occurs (boot with model not loaded remains safe).
    """
    import asyncio as _asyncio

    rebuild_called = []

    async def _fake_rebuild(vault, embedder, *, model_loaded=True, source_folder=""):
        rebuild_called.append(model_loaded)

    monkeypatch.setattr("app.services.vault_sweeper.run_sweep", AsyncMock())
    monkeypatch.setattr("app.services.vault_sweeper.rebuild_embedding_index", _fake_rebuild)
    # This test is scoped to the embedding-index startup wiring; stub out
    # the (unrelated) links-index startup rebuild so it doesn't touch
    # fake_vault's unconfigured attributes on a real code path.
    monkeypatch.setattr(
        "app.services.links_sidecar_index.rebuild_links_index", AsyncMock(return_value={})
    )

    fake_vault = AsyncMock()
    fake_vault.read_persona = AsyncMock(return_value="persona")
    fake_graph = SimpleNamespace(
        vault=fake_vault,
        message_processor=object(),
        settings=SimpleNamespace(model_name="test-model"),
        http_client=object(),
        context_window=8192,
        lmstudio_stop_sequences=[],
        note_classifier_fn=AsyncMock(),
        embeddings=SimpleNamespace(embed=AsyncMock(return_value=[])),
        module_registry={},
        ai_provider_name="lmstudio",
        ai_provider=object(),
        recall=None,
        embedding_model_loaded=False,  # model NOT loaded
    )

    async def _fake_build_application(_settings, _http_client):
        return fake_graph

    monkeypatch.setattr("app.composition.build_application", _fake_build_application)

    app = SimpleNamespace(state=SimpleNamespace())
    await initialize_startup(app, SimpleNamespace(), object())

    await _asyncio.sleep(0)

    assert len(rebuild_called) == 1
    assert rebuild_called[0] is False, (
        f"rebuild must be called with model_loaded=False when graph.embedding_model_loaded=False; "
        f"got {rebuild_called[0]!r}"
    )
