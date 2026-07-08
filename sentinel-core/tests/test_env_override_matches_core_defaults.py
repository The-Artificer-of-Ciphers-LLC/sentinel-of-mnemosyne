"""Drift/un-protect guard for music/'s generated sweeper-protection env override (Pitfall B).

`modules/music/scripts/gen_sweep_protection_env.py` derives
`SWEEP_SKIP_PREFIXES` / `PROTECTED_NAMESPACES` from this module's own
`Settings.model_fields[...].default` rather than a hand-copied literal
(D-13). This test binds the two together: it fails loudly the moment the
generator's output ever diverges from Core's committed defaults + `music/`,
or drops a critical protected prefix — the exact regression a stale,
hand-edited override would otherwise cause silently (both env vars use
pydantic-settings REPLACE semantics, so a dropped default un-protects that
namespace from the vault sweeper).

This file is a TEST, not `sentinel-core/app/*` code — MUS-01's "zero Core
code changes" scopes only the app package, not its test suite.
"""
import os
import sys

import pytest

from app.config import Settings

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_MUSIC_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "modules", "music", "scripts")
if _MUSIC_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _MUSIC_SCRIPTS_DIR)

from gen_sweep_protection_env import derive_override  # noqa: E402


@pytest.fixture(autouse=True)
def _sentinel_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # sentinel_api_key is a required Settings field; this test only reads
    # model_fields[...].default (class-level metadata), never depends on
    # any particular key value.
    monkeypatch.setenv("SENTINEL_API_KEY", "test-key")


def test_generated_skip_prefixes_matches_core_defaults_plus_music() -> None:
    """The generator's SWEEP_SKIP_PREFIXES == Core's default tuple + 'music/'."""
    expected = list(Settings.model_fields["sweep_skip_prefixes"].default) + ["music/"]
    actual = derive_override(Settings.model_fields["sweep_skip_prefixes"].default)
    assert actual == expected


def test_generated_protected_namespaces_matches_core_defaults_plus_music() -> None:
    """The generator's PROTECTED_NAMESPACES == Core's default tuple + 'music/'."""
    expected = list(Settings.model_fields["protected_namespaces"].default) + ["music/"]
    actual = derive_override(Settings.model_fields["protected_namespaces"].default)
    assert actual == expected


def test_generated_skip_prefixes_still_contains_critical_protected_prefixes() -> None:
    """Un-protect regression guard: dropping any of these from a future Core
    default change (or a stale hand-edit) must fail this test loudly."""
    generated = derive_override(Settings.model_fields["sweep_skip_prefixes"].default)
    for critical in ("security/", "self/", "pf2e/", "mnemosyne/", "templates/"):
        assert critical in generated, f"{critical} missing from generated skip-prefixes"


def test_generated_protected_namespaces_still_contains_critical_namespaces() -> None:
    """Un-protect regression guard for PROTECTED_NAMESPACES specifically."""
    generated = derive_override(Settings.model_fields["protected_namespaces"].default)
    for critical in ("security/", "self/", "templates/"):
        assert critical in generated, f"{critical} missing from generated protected namespaces"


def test_music_namespace_present_with_trailing_slash_in_both_lists() -> None:
    """Pitfall D: music/ must carry a trailing slash (a bare 'music' would
    only match the literal path, never the music/... subtree)."""
    skip = derive_override(Settings.model_fields["sweep_skip_prefixes"].default)
    protected = derive_override(Settings.model_fields["protected_namespaces"].default)
    assert "music/" in skip
    assert "music/" in protected
    assert "music" not in skip
    assert "music" not in protected
