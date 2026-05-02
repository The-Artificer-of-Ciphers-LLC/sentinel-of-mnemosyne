"""
OutputScanner — regex-based secret detection + AI secondary classifier.

Per SEC-02: scans AI response before it leaves POST /message.
Fail-open design: timeout or error → log + allow (never block on infrastructure failure).

Pattern corpus: mazen160/secrets-patterns-db (github.com/mazen160/secrets-patterns-db)
+ project-specific secret names from .env.example.

Private IP patterns excluded from initial blocklist (see Research Pitfall 5).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.provider_router import ProviderRouter

logger = logging.getLogger(__name__)

# High-precision patterns tuned for this project's secret shapes.
# Each entry: (pattern_name, compiled_regex)
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("anthropic_api_key", re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}")),
    ("openai_style_key", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("bearer_token", re.compile(r"Bearer\s+[a-zA-Z0-9+/]{32,}={0,2}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("sentinel_key_name", re.compile(r"SENTINEL_API_KEY\s*[=:]\s*\S+")),
    ("obsidian_key_name", re.compile(r"OBSIDIAN_API_KEY\s*[=:]\s*\S+")),
    ("fs_path", re.compile(r"/etc/(?:passwd|shadow|sudoers|ssh/|ssl/private/)\S*")),
]

_CLASSIFIER_SYSTEM = """You are a security classifier. You will be shown a text excerpt that
triggered a secret-detection pattern. Respond with exactly one word:
LEAK — if the text contains an actual exposed secret, credential, or sensitive system detail
SAFE — if the text is discussing secrets in the abstract, explaining formats, or the match is a
       false positive

No other output."""

SECONDARY_TIMEOUT_S = 2.0


class OutputScanner:
    """
    Scan AI response output for secret leakage before the response leaves POST /message.
    Uses two-stage detection: fast regex → independent secondary classifier.

    The secondary classifier routes through the supplied ``ai_provider`` (a
    ``ProviderRouter``). The scanner builds a minimal two-message conversation
    (system + user) using ``classifier_system`` and calls
    ``ai_provider.complete(messages)``. Passing ``ai_provider=None`` disables
    the secondary stage (fail-open).
    """

    def __init__(
        self,
        ai_provider: "ProviderRouter | None" = None,
        classifier_system: str = _CLASSIFIER_SYSTEM,
    ) -> None:
        self._ai_provider = ai_provider
        self._classifier_system = classifier_system

    def _regex_scan(self, response: str) -> list[str]:
        """Return list of pattern names that fired."""
        return [name for name, pat in _SECRET_PATTERNS if pat.search(response)]

    async def scan(self, response: str) -> tuple[bool, str | None]:
        """
        Scan response for secret leakage.
        Returns (is_safe, reason).
        is_safe=True  → allow response
        is_safe=False → block response (confirmed leak)

        Fail-open: timeout, error, or missing classifier → is_safe=True (log only).
        """
        fired = self._regex_scan(response)
        if not fired:
            return True, None

        logger.warning(f"Output regex matched patterns: {fired} — routing to secondary classifier")

        if self._ai_provider is None:
            logger.warning("OutputScanner: no secondary classifier configured — failing open")
            return True, None

        try:
            verdict = await asyncio.wait_for(
                self._classify(response, fired),
                timeout=SECONDARY_TIMEOUT_S,
            )
            if verdict == "LEAK":
                logger.error(f"Output scanner: confirmed leak ({fired}) — blocking response")
                return False, f"Response blocked: potential secret leakage detected ({fired})"
            else:
                logger.info(f"Output scanner: secondary classifier returned SAFE for {fired}")
                return True, None

        except asyncio.TimeoutError:
            logger.warning(
                f"Output scanner: secondary classifier timed out after {SECONDARY_TIMEOUT_S}s"
                " — failing open (allowing response, incident logged)"
            )
            return True, None
        except Exception as exc:
            logger.warning(f"Output scanner: secondary classifier error ({exc}) — failing open")
            return True, None

    def _extract_excerpt(self, response: str, fired_patterns: list[str]) -> str:
        """
        Return a 2000-char window centered on the first regex match position.
        Centers 500 chars before the match start and 1500 chars after, so the
        matched secret is always visible to the secondary classifier regardless
        of where it appears in the response.
        Falls back to response[:2000] if no match is found (should not happen
        in practice since fired_patterns are derived from a prior regex scan).
        """
        for name, pat in _SECRET_PATTERNS:
            if name in fired_patterns:
                m = pat.search(response)
                if m:
                    start = max(0, m.start() - 500)
                    end = min(len(response), m.start() + 1500)
                    return response[start:end]
        return response[:2000]

    async def _classify(self, response: str, fired_patterns: list[str]) -> str:
        """
        Call the configured AI provider with the classifier system prompt and
        the matched excerpt. Returns 'LEAK' or 'SAFE'.

        Caller (``scan``) only invokes ``_classify`` when ``self._ai_provider``
        is not None, so this method does not re-check.
        """
        excerpt = self._extract_excerpt(response, fired_patterns)
        messages = [
            {"role": "system", "content": self._classifier_system},
            {
                "role": "user",
                "content": f"Triggered patterns: {fired_patterns}\n\nText excerpt:\n{excerpt}",
            },
        ]
        verdict = await self._ai_provider.complete(messages)
        normalised = verdict.strip().upper() if isinstance(verdict, str) else "SAFE"
        return normalised if normalised in ("LEAK", "SAFE") else "SAFE"
