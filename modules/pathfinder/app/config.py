"""Pathfinder module configuration — pydantic-settings.

Reads from environment variables (injected by Docker Compose) and .env file.
All env vars are UPPER_CASE. pydantic-settings maps them automatically.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Sentinel Core — for startup registration
    sentinel_core_url: str = "http://sentinel-core:8000"
    sentinel_api_key: str  # Required — no default; startup fails fast if missing

    # Obsidian Local REST API — pathfinder calls directly (D-27)
    # Default: http://host.docker.internal:27123 (Docker → Mac host port 27123)
    obsidian_base_url: str = "http://host.docker.internal:27123"
    obsidian_api_key: str = ""  # blank if Obsidian REST API auth disabled

    # LiteLLM — model and API base for NPC field extraction
    litellm_model: str = "openai/local-model"
    litellm_api_base: str = "http://host.docker.internal:1234/v1"

    # Task-kind preferences (optional) — used by app.resolve_model to pick the best
    # loaded model for each task. If unset, the scorer falls back to litellm_model.
    litellm_model_chat: str | None = None
    litellm_model_structured: str | None = None
    litellm_model_fast: str | None = None

    # Phase 33 rules engine — embedding model loaded in LM Studio for corpus + query embeds.
    # Stored as the BARE model id (no provider prefix). The bare name is what
    # gets persisted in cached-ruling frontmatter (D-13), so reuse-match cache
    # comparisons work across processes. embed_texts() prepends "openai/" at
    # the litellm call site — see _resolve_embed_provider in app/llm.py.
    rules_embedding_model: str = "text-embedding-nomic-embed-text-v1.5"

    # Phase 34 session notes settings (D-10, D-13, D-37)
    session_auto_recap: bool = False  # SESSION_AUTO_RECAP env var (D-10)
    session_tz: str = "America/New_York"  # SESSION_TZ env var (D-13)
    session_recap_model: str | None = None  # SESSION_RECAP_MODEL; None falls back to litellm_model (D-37)

    # Phase 35 Foundry VTT event ingest settings (D-12, D-14)
    foundry_narration_model: str | None = None  # FOUNDRY_NARRATION_MODEL; None falls back to litellm_model
    discord_bot_internal_url: str = "http://discord-bot:8001"  # DISCORD_BOT_INTERNAL_URL

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
