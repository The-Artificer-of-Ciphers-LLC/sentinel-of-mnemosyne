"""
Sentinel Core configuration.
All settings loaded from environment variables via pydantic-settings.
Never call os.getenv() directly — use settings singleton instead.

Secret fields (API keys, tokens) are read from /run/secrets/<name> files when running
in Docker. Falls back to environment variables for local development without Docker secrets.
"""
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings


def _read_secret(name: str, env_fallback: str = "") -> str:
    """Read a Docker secret from /run/secrets/<name>.
    Falls back to env_fallback value (for local dev without Docker secrets)."""
    path = f"/run/secrets/{name}"
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return env_fallback


class Settings(BaseSettings):
    lmstudio_base_url: str = "http://host.docker.internal:1234/v1"
    sentinel_api_key: str  # Required — no default. Startup fails fast if missing.
    model_name: str = "gemma-4-e4b-it-mlx"
    # LM Studio embedding model id (no provider prefix — `openai/` is added at
    # the litellm call site). Single source of truth: previously duplicated as
    # hardcoded constants in app/clients/embeddings.py and
    # app/services/vault_sweeper.py (260502-1zv D-03).
    embedding_model: str = "text-embedding-nomic-embed-text-v1.5"
    log_level: str = "INFO"
    obsidian_api_url: str = "http://host.docker.internal:27123"  # HTTP mode (port 27123, not 27124)
    obsidian_api_key: str = ""  # blank = no Authorization header sent

    # AI provider selection (PROV-01, PROV-02)
    ai_provider: str = "lmstudio"  # lmstudio | claude | ollama | llamacpp
    ai_fallback_provider: str = "none"  # claude | none

    # Claude / Anthropic (PROV-02)
    anthropic_api_key: str = ""  # blank = Claude provider disabled
    claude_model: str = "claude-haiku-4-5"  # runtime configurable

    # Ollama (stub — Linux workstation LAN)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b"

    # llama.cpp (stub — OpenAI-compatible server)
    llamacpp_base_url: str = "http://localhost:8080"
    llamacpp_model: str = "local-model"

    # LM Studio API key (optional — only if LM Studio auth is enabled)
    lmstudio_api_key: str = ""

    # Model auto-discovery (lcl-model-agnostic)
    model_auto_discover: bool = True
    model_preferred: str | None = None
    model_task_chat: str | None = None
    model_task_structured: str | None = None
    model_task_fast: str | None = None

    # Alpaca trading keys (optional — trading module only)
    alpaca_paper_api_key: str = ""
    alpaca_paper_secret_key: str = ""
    alpaca_live_api_key: str = ""
    alpaca_live_secret_key: str = ""

    @model_validator(mode="before")
    @classmethod
    def load_secrets(cls, values: Any) -> Any:
        """Populate secret fields from /run/secrets/ files.
        File value wins over env var; falls back to whatever env var provides."""
        secret_map = {
            "sentinel_api_key": "sentinel_api_key",
            "obsidian_api_key": "obsidian_api_key",
            "lmstudio_api_key": "lmstudio_api_key",
            "anthropic_api_key": "anthropic_api_key",
            "alpaca_paper_api_key": "alpaca_paper_api_key",
            "alpaca_paper_secret_key": "alpaca_paper_secret_key",
            "alpaca_live_api_key": "alpaca_live_api_key",
            "alpaca_live_secret_key": "alpaca_live_secret_key",
        }
        if not isinstance(values, dict):
            return values
        for field, secret_name in secret_map.items():
            file_val = _read_secret(secret_name)
            if file_val:
                values[field] = file_val
        return values

    # CORS — Foundry VTT / browser interface (Phase 28, MOD-02)
    cors_allow_origins: str = "http://localhost:30000"
    cors_allow_origin_regex: str = r"https://.*\.forge-vtt\.com"

    # Vault sweeper skip-prefix denylist (260427-cza). Any vault path that
    # startswith one of these prefixes is excluded from sweep walks. Defaults
    # cover every module-managed subtree as of 2026-04-27. Override via env
    # SWEEP_SKIP_PREFIXES (JSON list) when a new module mounts a curated dir.
    sweep_skip_prefixes: tuple[str, ...] = (
        "_trash/",
        "pf2e/",            # legacy entry — covered by `mnemosyne/` for the
                            # actual NPC path; kept for defense-in-depth and
                            # to avoid weakening the shipped denylist.
        "mnemosyne/",       # covers mnemosyne/pf2e/, mnemosyne/self/, etc.
        "core/",
        "self/",
        "templates/",
        "archive/",
        "security/",
        "ops/sessions/",
        "ops/sweeps/",
        "inbox/",
        ".obsidian/",
    )

    # MEM-06 hot-window retention knobs (D-04).
    # These two fields make RetentionPolicy operator-tunable without a redeploy.
    # Defaults (3 / 2) preserve the "today+yesterday, top-3 sessions" behavior
    # shipped in plan 41-01.  A wider window surfaces more of the operator's own
    # session history; see T-41-06 in the threat model for the negative-value
    # degradation note (empty-slice, never unbounded read).
    retention_hot_limit: int = 3          # env: RETENTION_HOT_LIMIT
    retention_hot_window_days: int = 2    # env: RETENTION_HOT_WINDOW_DAYS

    # Protected-namespace allowlist (40-05 gap closure, MEM-05).
    # Operator-critical paths that the Vault seam REFUSES to relocate or trash.
    # These are NOT the same as sweep_skip_prefixes (which governs PROCESSING):
    # protected_namespaces governs whether a file may EVER be physically moved.
    #
    # Scope decision (round-2 item F, plan 40-05):
    #   sentinel/ — non-negotiable: persona.md crash-loops boot if missing.
    #   self/     — identity context; RecallConfig.self_paths depends on it;
    #               identity-critical even if not boot-halting.
    #   security/ — explicit operator security namespace; already skip-prefix;
    #               protected so a sweep can never accidentally move it.
    # Override via env PROTECTED_NAMESPACES (JSON list) to extend or narrow.
    protected_namespaces: tuple[str, ...] = (
        "sentinel/",   # boot-critical: persona.md absence crash-loops composition.py:424
        "self/",       # identity-critical: self/identity.md is the operator identity context
        "security/",   # operator-curated security namespace: never swept, never moved
    )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
