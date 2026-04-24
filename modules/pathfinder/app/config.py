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
    # Must match a model identifier that LM Studio's /v1/models endpoint reports as loaded.
    rules_embedding_model: str = "text-embedding-nomic-embed-text-v1.5"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
