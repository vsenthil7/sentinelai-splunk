"""Application configuration. Real Splunk wiring is swapped in via env vars."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTINEL_", env_file=".env", extra="ignore")

    # App
    app_name: str = "SentinelAI"
    environment: Literal["dev", "test", "prod"] = "dev"

    # Auth
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    # Symmetric key for encrypting per-tenant credentials at rest (Fernet-derived).
    # In prod, source from a KMS/Key Vault and rotate. Defaults to jwt_secret-like.
    secret_key: str = "change-me-secret-key-in-prod"

    # Database
    database_url: str = "sqlite+aiosqlite:///./sentinel.db"
    db_echo: bool = False
    # When True, init_db creates tables from metadata (dev). In prod, run
    # `alembic upgrade head` instead and set this False.
    db_create_all: bool = True

    # Operations
    rate_limit_per_minute: int = 120
    log_json: bool = True

    # Notifications
    notify_webhook_url: str = ""
    notify_high_risk_threshold: int = 80

    # CORS (comma-separated origins; "*" allows all — tighten in prod)
    cors_origins: str = "*"

    # Splunk backend selection: "mock" (local/test), "live" (REST API),
    # or "mcp" (Splunk MCP Server — agent-to-Splunk over Model Context Protocol)
    splunk_backend: Literal["mock", "live", "mcp"] = "mock"
    splunk_host: str = "https://localhost:8089"
    splunk_token: str = ""
    splunk_mcp_url: str = ""
    # MCP search tool name (forward-compat across Splunk MCP TA versions)
    splunk_mcp_search_tool: str = "run_oneshot_search"

    # AI / hosted models
    ai_model: str = "Foundation-Sec-1.1-8B-Instruct"
    ai_backend: Literal["mock", "live"] = "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
