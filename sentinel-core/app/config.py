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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
