"""Generate the music/-protecting vault-sweeper env override (D-13, D-14, Pitfall B).

`music/` must be excluded from the vault sweeper's walk (``SWEEP_SKIP_PREFIXES``)
and from any physical relocation (``PROTECTED_NAMESPACES``) BEFORE the first
`music/` write ever reaches a deploy build (Pitfall 1) — see
``48-04-PLAN.md``'s commit-discipline section for why this script's output
lands in the SAME commit as ``app/seed.py``.

Both env vars are pydantic-settings REPLACE-semantics overrides on
sentinel-core's ``Settings`` (``sentinel-core/app/config.py``): setting
either one REPLACES Core's entire committed default tuple, it does not
append to it. A hand-maintained literal is therefore a live footgun — the
next time Core's defaults change (a new module, a renamed prefix), the
hand-copied override silently drops it and un-protects that namespace. This
script instead DERIVES the override values from Core's own
``Settings.model_fields[...].default`` at generation time, so the generated
value is always Core's real current defaults plus ``music/`` (trailing
slash mandatory, Pitfall D — a bare ``music`` would only match the exact
literal string, not the ``music/...`` subtree, via the sweeper's
``str.startswith`` prefix check).

``derive_override`` is the pure, hand-copy-free transform both this
script's ``__main__`` entrypoint and sentinel-core's
``tests/test_env_override_matches_core_defaults.py`` drift guard call —
sharing one code path is what makes "generate, never hand-copy" a provable
invariant rather than a comment.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Iterable

# Pitfall D: the sweeper's skip check is a plain str.startswith(prefix) test —
# a bare "music" would match the literal path "music" only, never the
# "music/..." subtree. Every entry in these lists (Core's own defaults
# included) carries a trailing slash for exactly this reason.
_MUSIC_NAMESPACE = "music/"


def derive_override(core_default: Iterable[str]) -> list[str]:
    """Return Core's committed default tuple + the trailing-slash `music/` entry.

    Pure — no I/O, no ``Settings`` import, no hardcoded prefix list. Callers
    supply Core's live default (read via ``Settings.model_fields[...].default``);
    this function only appends the one entry `music/` adds.
    """
    return list(core_default) + [_MUSIC_NAMESPACE]


def _load_core_settings_class():
    """Import sentinel-core's ``Settings`` class via a repo-relative sys.path insert.

    The music module's own dependency tree and runtime code never depend on
    sentinel-core (MUS-01/MUS-02) — this reaches across the repo, from this
    generator script ONLY, solely to READ Core's committed default tuples at
    generation time. No music app/runtime module does this.
    """
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    core_dir = os.path.join(repo_root, "sentinel-core")
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    # sentinel-core/app/config.py instantiates a module-level `settings =
    # Settings()` on import, and `sentinel_api_key` is a required field with
    # no default. We only need the CLASS (for model_fields[...].default),
    # never that singleton instance's values, so a dummy placeholder that
    # satisfies validation is sufficient and never used for anything else.
    os.environ.setdefault("SENTINEL_API_KEY", "gen-sweep-protection-env-placeholder")
    from app.config import Settings  # noqa: E402  (import deferred to path setup above)

    return Settings


def main() -> None:
    """Print the two generated deploy-.env lines for the sweeper override."""
    settings_cls = _load_core_settings_class()
    skip_prefixes = derive_override(
        settings_cls.model_fields["sweep_skip_prefixes"].default
    )
    protected_namespaces = derive_override(
        settings_cls.model_fields["protected_namespaces"].default
    )
    print(f"SWEEP_SKIP_PREFIXES={json.dumps(skip_prefixes)}")
    print(f"PROTECTED_NAMESPACES={json.dumps(protected_namespaces)}")


if __name__ == "__main__":
    main()
