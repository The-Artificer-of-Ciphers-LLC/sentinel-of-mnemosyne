"""Pytest configuration and shared fixtures for music module tests.

Test-time sys.path setup: the music Dockerfile copies shared/sentinel_shared
into /app at build time, but local pytest runs from the host where the
repo's `shared/` dir is at ../../shared/ relative to this module. Insert
that path before any other test code imports from sentinel_shared
(otherwise `app.obsidian`'s `from sentinel_shared.obsidian import
ObsidianClientCore` fails at import time).
"""
import os
import sys

# Make the repo's shared/ package importable for local pytest runs.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SHARED = os.path.join(_REPO_ROOT, "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

# Required env vars are read via pydantic-settings at import time
# (app/config.py's Settings()); set defaults here so import succeeds
# regardless of which test module runs first.
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")
os.environ.setdefault("SENTINEL_CORE_URL", "http://sentinel-core:8000")
os.environ.setdefault("OBSIDIAN_BASE_URL", "http://localhost:27123")
os.environ.setdefault("OBSIDIAN_API_KEY", "")

# Pre-import app.main so mock.patch("app.main.<symbol>") can resolve the
# attribute at __enter__ time without each test having to import app.main
# above the patch context (mirrors modules/pathfinder/tests/conftest.py).
import app.main  # noqa: E402,F401
