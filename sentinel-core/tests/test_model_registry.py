"""Tests for the model registry — seed data plus what a provider API can add.

ADR-0007 step 4 removed the registry's LM Studio live path. Five of this file's
seven cases drove exactly that path (a ``/v1/models`` discovery call plus a
per-model ``/api/v0/models/{id}`` context fetch) and could not survive it. They
are replaced by the two cases below rather than dropped:

- ``test_lmstudio_registry_records_the_seam_resolved_model`` carries what
  ``test_lmstudio_registry_uses_fetched_context_window`` and
  ``test_lmstudio_registry_uses_discovered_model_name`` guarded — the registry
  records LM Studio's REAL window under the model that is actually loaded, not
  under MODEL_NAME.
- ``test_lmstudio_registry_is_seed_only_without_the_seam`` carries what
  ``test_lmstudio_registry_falls_back_to_seed_on_unavailable``,
  ``test_lmstudio_registry_fallback_when_discovery_fails`` and
  ``test_lmstudio_registry_no_discovery_when_disabled`` guarded — no discovery,
  no fetch, no invented entry, seed intact.

Both new cases assert something the originals could not: that
``build_model_registry`` issues NO LM Studio HTTP at all. The transport raises
on any request, so a re-introduced fetch fails the test rather than passing
quietly against a mock.
"""
import pytest
import httpx

from app.services.model_registry import build_model_registry


@pytest.fixture
def lmstudio_settings(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "lmstudio")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://test-lmstudio/v1")
    from app.config import Settings
    return Settings()


@pytest.fixture
def claude_settings_with_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-sk-ant")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-4-5")
    from app.config import Settings
    return Settings()


@pytest.fixture
def claude_settings_no_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from app.config import Settings
    return Settings()


def _forbidden_transport() -> httpx.MockTransport:
    """Any HTTP at all is a failure — the registry must issue none."""

    def handler(request):
        raise AssertionError(
            f"build_model_registry must not issue LM Studio HTTP; got {request.url}"
        )

    return httpx.MockTransport(handler)


async def test_lmstudio_registry_records_the_seam_resolved_model(lmstudio_settings):
    """The seam's answer is what the registry records — under its own key.

    MODEL_NAME is ``test-model`` and the seam resolved ``discovered-model``.
    The registry keys on the model that is actually loaded and carries its real
    window; MODEL_NAME contributes nothing, which is that setting's whole
    remaining posture under ADR decision 4 as amended.
    """
    async with httpx.AsyncClient(transport=_forbidden_transport()) as client:
        registry = await build_model_registry(
            lmstudio_settings,
            client,
            lmstudio_model="discovered-model",
            lmstudio_context_window=65536,
        )

    assert "discovered-model" in registry
    assert registry["discovered-model"].context_window == 65536
    assert "test-model" not in registry, (
        "MODEL_NAME must not become a registry entry of its own"
    )


async def test_lmstudio_registry_is_seed_only_without_the_seam(lmstudio_settings):
    """No seam answer → seed only, and still no HTTP.

    The registry used to attempt discovery here and invent a MODEL_NAME entry
    from whatever came back (or from MODEL_NAME itself on failure). It now
    contributes nothing for LM Studio without the seam, because the alternative
    is a second implementation of "which model is loaded".
    """
    async with httpx.AsyncClient(transport=_forbidden_transport()) as client:
        registry = await build_model_registry(lmstudio_settings, client)

    assert "claude-haiku-4-5" in registry, "the seed must survive intact"
    assert "test-model" not in registry, (
        "an unconfirmed MODEL_NAME must not be invented into the registry"
    )
    assert "local-model" not in registry, (
        "ADR-0007 step 5 trimmed the seed to cloud models — LM Studio's identity "
        "comes from LMStudioModelSource, never from seed data"
    )


async def test_claude_registry_skips_live_fetch_without_key(claude_settings_no_key):
    async with httpx.AsyncClient() as client:
        registry = await build_model_registry(claude_settings_no_key, client)
    # Seed models should be present
    assert "claude-haiku-4-5" in registry


async def test_seed_always_present_in_registry(lmstudio_settings):
    """The seed survives a dead network — on the TRIMMED seed's contents.

    ADR-0007 step 5 cut ``local-model`` (lmstudio) and ``qwen2.5:14b`` (ollama)
    from the seed, so the example model ids change. The property this case
    guards does not: whatever the seed holds is in the registry even when every
    live fetch fails.
    """
    def raise_connect_error(request):
        raise httpx.ConnectError("refused")
    transport = httpx.MockTransport(raise_connect_error)
    async with httpx.AsyncClient(transport=transport) as client:
        registry = await build_model_registry(lmstudio_settings, client)
    # The trimmed seed is cloud models only.
    assert "claude-haiku-4-5" in registry
    assert "claude-sonnet-4-5" in registry
    assert "claude-sonnet-4-6" in registry
    assert "local-model" not in registry
    assert "qwen2.5:14b" not in registry
