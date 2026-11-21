"""CrowdVision AI Agent - Application Configuration."""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────
    app_name: str = "crowdvision-ai-agent"
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8100
    app_workers: int = 1
    app_log_level: str = "INFO"

    # ── API Authentication ───────────────────────────────────────
    api_secret_key: str = "CHANGE_ME_TO_A_RANDOM_SECRET_KEY"
    api_token_expire_minutes: int = 60
    api_allowed_origins: str = "http://localhost:3000,http://localhost:8000"

    # ── Database ─────────────────────────────────────────────────
    # Defaults to async sqlite for instant out-of-the-box local operation;
    # overrides with PostgreSQL in production via env var DATABASE_URL
    database_url: str = "sqlite+aiosqlite:///./crowdvision_agent.db"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30
    database_echo: bool = False

    # ── Redis ────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 20
    redis_socket_timeout: float = 5.0
    redis_retry_on_timeout: bool = True

    # ── LLM Provider ─────────────────────────────────────────────
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout: int = 30
    llm_max_retries: int = 3
    llm_enabled: bool = True

    # ── Agent Processing ─────────────────────────────────────────
    agent_analysis_interval: float = 5.0
    agent_max_queue_size: int = 1000
    agent_batch_size: int = 20
    agent_dedup_window: float = 2.0
    agent_llm_cooldown: float = 10.0
    agent_history_window_minutes: int = 30
    agent_max_context_items: int = 100

    # ── Alert Configuration ──────────────────────────────────────
    alert_dedup_window: int = 60
    alert_escalation_timeout: int = 300
    alert_max_active: int = 500
    alert_retention_hours: int = 168

    # ── Performance ──────────────────────────────────────────────
    perf_request_timeout: float = 10.0
    perf_ws_heartbeat: int = 30
    perf_circuit_breaker_threshold: int = 5
    perf_circuit_breaker_timeout: int = 60

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnv.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
