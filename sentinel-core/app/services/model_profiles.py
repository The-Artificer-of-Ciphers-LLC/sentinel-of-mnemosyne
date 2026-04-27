"""Model profile library — stop sequences and context metadata per model family.

Resolution order for get_profile(model_id, api_base):
  1. LM Studio /api/v0/models/{model_id} → arch field → FAMILY_PROFILES[arch]
  2. Substring match on model_id → FAMILY_PROFILES[matched_family]
  3. SAFE_DEFAULT (no stop sequences, 4096 context)

Profiles are cached per (model_id, api_base) after first fetch. Use
force_refresh=True to invalidate (e.g., after model swap in LM Studio UI).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_profile_cache: dict[tuple[str, str], "ModelProfile"] = {}
_profile_cache_lock = asyncio.Lock()


@dataclass
class ModelProfile:
    family: str
    stop_sequences: list[str]
    context_window: int
    supports_system_prompt: bool
    chat_template_format: str
    notes: str = ""


# Keyed by the LM Studio `arch` field value AND by substring match keys.
# arch strings: qwen2 confirmed via LM Studio docs; others are best-effort
# based on common GGUF metadata conventions — safe default applies if wrong.
FAMILY_PROFILES: dict[str, ModelProfile] = {
    "qwen2": ModelProfile(
        family="qwen2",
        stop_sequences=["<|im_end|>", "<|endoftext|>"],
        context_window=32768,
        supports_system_prompt=True,
        chat_template_format="chatml",
        notes="Qwen2/2.5 ChatML — instruct variant; base models only need <|endoftext|>",
    ),
    "llama3": ModelProfile(
        family="llama3",
        stop_sequences=["<|eot_id|>", "<|end_of_text|>"],
        context_window=8192,
        supports_system_prompt=True,
        chat_template_format="llama3",
    ),
    "llama": ModelProfile(
        family="llama",
        stop_sequences=["[INST]", "[/INST]", "</s>"],
        context_window=4096,
        supports_system_prompt=False,
        chat_template_format="llama2",
    ),
    "mistral": ModelProfile(
        family="mistral",
        stop_sequences=["[INST]", "[/INST]", "</s>"],
        context_window=32768,
        supports_system_prompt=False,
        chat_template_format="mistral",
    ),
    "gemma2": ModelProfile(
        family="gemma2",
        stop_sequences=["<end_of_turn>"],
        context_window=8192,
        supports_system_prompt=True,
        chat_template_format="gemma",
    ),
    "phi3": ModelProfile(
        family="phi3",
        stop_sequences=["<|end|>", "<|endoftext|>"],
        context_window=131072,
        supports_system_prompt=True,
        chat_template_format="phi3",
    ),
    "deepseek2": ModelProfile(
        family="deepseek2",
        stop_sequences=["<|end▁of▁sentence|>"],
        context_window=32768,
        supports_system_prompt=True,
        chat_template_format="deepseek",
    ),
}

# Aliases — additional arch strings that map to the same profile
FAMILY_PROFILES["qwen2_5"] = FAMILY_PROFILES["qwen2"]
FAMILY_PROFILES["qwen2_vl"] = FAMILY_PROFILES["qwen2"]
FAMILY_PROFILES["llama3_1"] = FAMILY_PROFILES["llama3"]
FAMILY_PROFILES["llama3_2"] = FAMILY_PROFILES["llama3"]
FAMILY_PROFILES["mistral_nemo"] = FAMILY_PROFILES["mistral"]
FAMILY_PROFILES["gemma3"] = FAMILY_PROFILES["gemma2"]
FAMILY_PROFILES["phi3_5"] = FAMILY_PROFILES["phi3"]

# Conservative default — no stop sequences (LM Studio handles termination via chat template)
SAFE_DEFAULT = ModelProfile(
    family="unknown",
    stop_sequences=[],
    context_window=4096,
    supports_system_prompt=True,
    chat_template_format="unknown",
    notes="No recognized arch — relying on server-side chat template termination",
)

# Substring patterns for model_id fallback (longest match wins; order matters)
_SUBSTRING_PATTERNS: list[tuple[str, str]] = [
    ("llama-3", "llama3"),
    ("llama3", "llama3"),
    ("llama-2", "llama"),
    ("llama2", "llama"),
    ("llama", "llama"),
    ("mistral-nemo", "mistral_nemo"),
    ("mistral", "mistral"),
    ("qwen2.5", "qwen2"),
    ("qwen2", "qwen2"),
    ("qwen", "qwen2"),
    ("gemma-3", "gemma3"),
    ("gemma-2", "gemma2"),
    ("gemma", "gemma2"),
    ("phi-3.5", "phi3_5"),
    ("phi-3", "phi3"),
    ("phi3", "phi3"),
    ("deepseek", "deepseek2"),
]


def _substring_match(model_id: str) -> ModelProfile | None:
    """Try longest-pattern-first substring match on model_id (case-insensitive)."""
    lower = model_id.lower()
    for pattern, family_key in _SUBSTRING_PATTERNS:
        if pattern in lower:
            profile = FAMILY_PROFILES.get(family_key)
            if profile:
                logger.debug(
                    "model_profiles: substring match '%s' → family '%s' for model_id=%r",
                    pattern,
                    family_key,
                    model_id,
                )
                return profile
    return None


async def get_profile(
    model_id: str,
    api_base: str | None = None,
    *,
    force_refresh: bool = False,
) -> ModelProfile:
    """Return ModelProfile for model_id, fetching arch from LM Studio if possible.

    Resolution order:
      1. LM Studio /api/v0/models/{model_id} → arch → FAMILY_PROFILES[arch]
         (only attempted when api_base is provided and not None)
      2. Substring pattern match on model_id
      3. SAFE_DEFAULT (no stop sequences)

    Results are cached per (model_id, api_base). Pass force_refresh=True if the
    user has swapped models in LM Studio without restarting the container.
    """
    cache_key = (model_id, api_base or "")
    async with _profile_cache_lock:
        if not force_refresh and cache_key in _profile_cache:
            return _profile_cache[cache_key]

    profile: ModelProfile | None = None

    # Step 1: LM Studio arch lookup
    if api_base:
        # Strip /v1 suffix to reach the /api/v0/ base — same pattern as
        # get_context_window_from_lmstudio in litellm_provider.py
        v0_base = api_base.rstrip("/").removesuffix("/v1")
        url = f"{v0_base}/api/v0/models/{model_id}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                arch = resp.json().get("arch", "")
                if arch:
                    profile = FAMILY_PROFILES.get(arch)
                    if profile:
                        logger.info(
                            "model_profiles: arch '%s' → family '%s' for model_id=%r",
                            arch,
                            profile.family,
                            model_id,
                        )
                    else:
                        logger.warning(
                            "model_profiles: arch '%s' not in FAMILY_PROFILES for model_id=%r — trying substring match",
                            arch,
                            model_id,
                        )
        except Exception as exc:
            logger.warning(
                "model_profiles: LM Studio arch fetch failed for model_id=%r (%s) — falling back to substring match",
                model_id,
                exc,
            )

    # Step 2: substring fallback
    if profile is None:
        profile = _substring_match(model_id)

    # Step 3: safe default
    if profile is None:
        logger.warning(
            "model_profiles: no profile found for model_id=%r — using SAFE_DEFAULT (no stop sequences)",
            model_id,
        )
        profile = SAFE_DEFAULT

    async with _profile_cache_lock:
        _profile_cache[cache_key] = profile

    return profile
