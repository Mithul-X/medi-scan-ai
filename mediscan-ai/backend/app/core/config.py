"""
Application configuration.

All settings load from environment variables (.env locally, platform env
vars on Render). Nothing here depends on a local machine — the backend
runs entirely off free hosted APIs.

Model names live here, not buried in service code, so they're easy to bump
when providers deprecate things. As of this writing (mid-2026):
  - Gemini 2.0 Flash / 2.0 Flash-Lite are END OF LIFE (shut down June 1, 2026).
  - Gemini 2.5 Flash is the current free-tier workhorse with vision support.
  - OpenRouter's old `:free`-tagged experimental Gemini models are gone.
    `openrouter/free` is now a router that auto-selects a capable free model
    (vision-aware), which is more resilient than hardcoding one model id
    that might get retired without notice.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App metadata ---
    app_name: str = "MediScan AI"
    app_env: Literal["development", "production"] = "development"
    api_v1_prefix: str = "/api/v1"

    # --- CORS ---
    # Comma-separated origins, e.g. "https://mediscan-ai.vercel.app,http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # --- Gemini (primary LLM provider) ---
    gemini_api_key: str = Field(default="", description="Google AI Studio API key")
    gemini_model_text: str = "gemini-2.5-flash"
    gemini_model_vision: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # --- OpenRouter (fallback provider chain) ---
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Ordered fallback chain. The smart "openrouter/free" router goes first
    # (auto-picks a free model that fits the request, vision-aware). Named
    # models behind it are a safety net if the router itself errors out.
    openrouter_fallback_models: list[str] = [
        "openrouter/free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "deepseek/deepseek-r1:free",
    ]
    openrouter_site_url: str = "https://mediscan-ai.vercel.app"
    openrouter_app_name: str = "MediScan AI"

    # --- Rate limiting / retry strategy ---
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 1.5
    llm_request_timeout_seconds: float = 45.0

    # --- File handling ---
    max_upload_size_mb: int = 10
    allowed_mime_types: list[str] = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/webp",
        "text/plain",
    ]
    image_compress_max_dimension: int = 1600
    image_compress_target_kb: int = 900

    # --- Database (SQLite, file-based, free, no external service) ---
    database_url: str = "sqlite+aiosqlite:///./mediscan.db"

    # --- History / persistence scope ---
    max_sessions_history: int = 3
    max_analyses_per_session: int = 3

    # --- Logging ---
    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — avoids re-parsing env on every request."""
    return Settings()
