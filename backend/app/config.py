"""Application configuration.

Loaded from the environment only — nothing secret lives in code or git. Defaults
are chosen so a fresh checkout runs against mocks and the local docker-compose
topology with **no real keys** (FR-25). Real values are supplied at go-live via
``.env`` (documented in ``.env.example`` / GOLIVE.md).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.value_objects import Provider


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DATACHAT_",
        extra="ignore",
        frozen=True,
    )

    # --- App -------------------------------------------------------------
    app_name: str = "DataChat"
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # When true, provider/embedding/DB adapters resolve to in-repo fakes so the
    # app runs end-to-end without any external accounts.
    use_mocks: bool = True

    # --- Data stores -----------------------------------------------------
    # app_rw role: migrations + app-schema CRUD.
    database_url: str = "postgresql+asyncpg://datachat:datachat@localhost:5432/datachat"
    # datachat_exec role: read-only executor pool (Bulkhead, separate engine).
    executor_database_url: str = (
        "postgresql+asyncpg://datachat_exec:datachat_exec@localhost:5432/datachat"
    )
    redis_url: str = "redis://localhost:6379/0"

    # --- LLM providers ---------------------------------------------------
    gemini_api_key: SecretStr = SecretStr("")
    groq_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    # OpenRouter stays off by default to remain strictly $0 (TechSpec §11).
    openrouter_enabled: bool = False
    provider_order: tuple[Provider, ...] = (Provider.GEMINI, Provider.GROQ)

    # --- Embeddings ------------------------------------------------------
    embedding_model: str = "text-embedding-004"
    embedding_dim: int = 768

    # --- Observability ---------------------------------------------------
    mlflow_tracking_uri: str = "http://localhost:5000"

    # --- Agent bounds (LLM10 / ASI08 — bounded consumption) --------------
    max_repair_attempts: int = 2
    row_cap: int = 1000
    statement_timeout_ms: int = 5000
    llm_timeout_s: float = 30.0
    retrieval_k: int = 8

    # --- HITL ------------------------------------------------------------
    approve_sql_default: bool = False

    # --- Abuse limits ----------------------------------------------------
    rate_limit_per_min: int = 20
    global_daily_quota: int = 1000

    # --- Circuit breaker -------------------------------------------------
    breaker_fail_threshold: int = 5
    breaker_cooldown_s: int = 30

    # --- Privacy ---------------------------------------------------------
    data_retention_days: int = 90

    # --- Edge ------------------------------------------------------------
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton (scoped via DI, not a global)."""
    return Settings()
