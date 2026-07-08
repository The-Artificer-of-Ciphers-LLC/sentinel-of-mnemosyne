"""Music module configuration — pydantic-settings.

Reads from environment variables (injected by Docker Compose) and .env file.
All env vars are UPPER_CASE. pydantic-settings maps them automatically.

Trimmed to the fields the module actually needs (D-11): no LiteLLM/session/
Discord fields — those are pf2e-only surface this module never touches.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Sentinel Core — for startup registration
    sentinel_core_url: str = "http://sentinel-core:8000"
    sentinel_api_key: str  # Required — no default; startup fails fast if missing

    # Obsidian Local REST API — music calls directly via ObsidianClient (D-03)
    # Default: http://host.docker.internal:27123 (Docker → Mac host port 27123)
    obsidian_base_url: str = "http://host.docker.internal:27123"
    obsidian_api_key: str = ""  # blank if Obsidian REST API auth disabled

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
