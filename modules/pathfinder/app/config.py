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

    # LiteLLM — API base for the embeddings/rules-index path (Phase 33/43).
    # Local OpenAI-compatible inference backend (e.g. exo, LM Studio) reached via
    # Docker's host-gateway alias -- NOT "localhost", which inside this container
    # resolves to the container itself rather than the host machine running the
    # backend (T-lmstudio-provider-switch). Override via LITELLM_API_BASE in .env.
    #
    # Phase 42 (D-09, SC-6): the chat-only default model field and the
    # per-task-kind chat/structured/fast override fields are REMOVED — every
    # pf2e chat/completion call site now reaches the LLM through
    # sentinel-core's POST /provider/complete (SentinelCoreClient.complete()),
    # which resolves provider+model itself. `litellm_api_base` is RETAINED
    # because the embeddings path (embed_texts, below) still calls
    # litellm.aembedding directly against it (Phase 43 scope; D-02 embeddings
    # stay on litellm).
    litellm_api_base: str = "http://host.docker.internal:1234/v1"

    # Phase 33 rules engine — embedding model for corpus + query embeds, served from
    # litellm_api_base above. Stored as the BARE model id (no provider prefix). The
    # bare name is what gets persisted in cached-ruling frontmatter (D-13), so
    # reuse-match cache comparisons work across processes. embed_texts() prepends
    # "openai/" at the litellm call site — see _resolve_embed_provider in app/llm.py.
    # NOTE (T-lmstudio-provider-switch): the default now points at LM Studio:1234,
    # which serves the nomic embedding model, so the rules-index path works by
    # default. If litellm_api_base is overridden to point at a backend that lacks
    # POST /v1/embeddings, the startup rules-index build degrades gracefully (see
    # main.py lifespan) rather than crashing the module; /rule/query returns 503
    # until an embeddings-capable backend is configured.
    rules_embedding_model: str = "text-embedding-nomic-embed-text-v1.5"

    # Phase 34 session notes settings (D-10, D-13, D-37)
    session_auto_recap: bool = False  # SESSION_AUTO_RECAP env var (D-10)
    session_tz: str = "America/New_York"  # SESSION_TZ env var (D-13)

    # Phase 35 Foundry VTT event ingest settings (D-12, D-14)
    discord_bot_internal_url: str = "http://discord-bot:8001"  # DISCORD_BOT_INTERNAL_URL

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
