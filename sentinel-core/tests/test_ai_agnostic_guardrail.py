"""
Guardrail: enforce AI-agnostic architecture in app/.

All AI calls must route through app.state.ai_provider (injected at startup).
Direct vendor SDK imports in app/ are a design violation — they couple the
codebase to a specific AI vendor and bypass the provider abstraction layer.

This test scans every .py file under app/ (excluding app/config.py and
app/clients/ which legitimately configure providers) and fails if any file
contains:
  - Direct vendor SDK imports: from anthropic import, import anthropic,
    from openai import, import openai, etc.
  - Hardcoded vendor model strings: claude-*, gpt-*, gemini-*, mistral-*
    appearing as string literals.
"""
import re
from pathlib import Path

import pytest

# Root of the app package relative to this test file.
APP_DIR = Path(__file__).parent.parent / "app"

# Files/directories excluded from the scan — these legitimately reference
# provider configuration and are allowed to name vendors/models.
EXCLUDED_PATHS = {
    APP_DIR / "config.py",
    APP_DIR / "clients",
}

# Vendor SDK import patterns that are forbidden in app/ business logic.
VENDOR_IMPORT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("anthropic SDK import", re.compile(r"^\s*(import anthropic|from anthropic\s+import)", re.MULTILINE)),
    ("openai SDK import", re.compile(r"^\s*(import openai|from openai\s+import)", re.MULTILINE)),
    ("litellm SDK import", re.compile(r"^\s*(import litellm|from litellm\s+import)", re.MULTILINE)),
    ("cohere SDK import", re.compile(r"^\s*(import cohere|from cohere\s+import)", re.MULTILINE)),
    ("google.generativeai SDK import", re.compile(r"^\s*(import google\.generativeai|from google\.generativeai\s+import)", re.MULTILINE)),
]

# Hardcoded vendor model string patterns (as string literals).
# Matches quoted strings containing the vendor prefix anywhere in the file.
VENDOR_MODEL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("hardcoded claude model string", re.compile(r'["\']claude-[^"\']*["\']')),
    ("hardcoded gpt model string", re.compile(r'["\']gpt-[^"\']*["\']')),
    ("hardcoded gemini model string", re.compile(r'["\']gemini-[^"\']*["\']')),
    ("hardcoded mistral model string", re.compile(r'["\']mistral-[^"\']*["\']')),
]


def _is_excluded(path: Path) -> bool:
    """Return True if the path falls under any excluded path."""
    for excluded in EXCLUDED_PATHS:
        if path == excluded:
            return True
        try:
            path.relative_to(excluded)
            return True
        except ValueError:
            pass
    return False


def _collect_py_files() -> list[Path]:
    """Return all .py files under APP_DIR that are not excluded."""
    return [
        p for p in APP_DIR.rglob("*.py")
        if not _is_excluded(p)
    ]


def _find_violations(path: Path) -> list[str]:
    """
    Scan a single file for vendor import and hardcoded model string violations.
    Returns a list of human-readable violation descriptions (empty if clean).
    """
    source = path.read_text(encoding="utf-8")
    violations: list[str] = []

    for label, pattern in VENDOR_IMPORT_PATTERNS:
        for match in pattern.finditer(source):
            line_no = source[: match.start()].count("\n") + 1
            violations.append(
                f"{label} at line {line_no}: {match.group().strip()!r}"
            )

    for label, pattern in VENDOR_MODEL_PATTERNS:
        for match in pattern.finditer(source):
            line_no = source[: match.start()].count("\n") + 1
            violations.append(
                f"{label} at line {line_no}: {match.group()!r}"
            )

    return violations


def test_no_vendor_ai_imports_or_hardcoded_models() -> None:
    """
    Fail if any app/ file (outside config.py and clients/) directly imports a
    vendor AI SDK or hardcodes a vendor model string literal.

    FIX: Remove the import / hardcoded string and route the AI call through
    app.state.ai_provider instead.
    """
    py_files = _collect_py_files()
    assert py_files, f"No .py files found under {APP_DIR} — check APP_DIR path"

    all_violations: list[str] = []
    for path in sorted(py_files):
        file_violations = _find_violations(path)
        for v in file_violations:
            relative = path.relative_to(APP_DIR.parent)
            all_violations.append(f"  {relative}: {v}")

    if all_violations:
        violation_list = "\n".join(all_violations)
        pytest.fail(
            "AI-agnostic guardrail violation(s) detected.\n\n"
            "All AI calls must route through app.state.ai_provider.\n"
            "Direct vendor SDK imports and hardcoded model strings in app/ are\n"
            "a design violation (see tests/test_ai_agnostic_guardrail.py).\n\n"
            f"Violations:\n{violation_list}\n\n"
            "To fix: remove the import/string and use app.state.ai_provider instead."
        )
