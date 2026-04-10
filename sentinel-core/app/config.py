"""
Sentinel Core configuration.
All settings loaded from environment variables via pydantic-settings.
Never call os.getenv() directly — use settings singleton instead.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    lmstudio_base_url: str = "http://host.docker.internal:1234/v1"
    pi_harness_url: str = "http://pi-harness:3000"
    sentinel_api_key: str  # Required — no default. Startup fails fast if missing.
    model_name: str = "local-model"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
