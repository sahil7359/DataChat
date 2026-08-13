"""Application configuration.

Loaded from the environment only — nothing secret lives in code or git. Defaults
are chosen so a fresh checkout runs against mocks and the local docker-compose
topology with **no real keys** (FR-25). Real values are supplied at go-live via
``.env`` (documented in ``.env.example`` / GOLIVE.md).
"""

from __future__ import annotations

import json
from contextlib import suppress
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.value_objects import Provider


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DATACHAT_",
        extra="ignore",
        frozen=True,
        # why: without this, pydantic-settings JSON-decodes any collection-typed
        # field at the *source* level, before validators run. So the obvious
        # DATACHAT_CORS_ORIGINS=https://app.vercel.app died with
        # `error parsing value for field "cors_origins"` — a message naming the
        # field but not the cause, mid-deploy, in a hosting dashboard. Decoding
        # off hands the raw string to _accept_comma_separated below, which takes
        # both comma-separated and JSON.
        enable_decoding=False,
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
    # Login password for the datachat_exec role, set by the roles migration. Must
    # match the credential embedded in executor_database_url. Overridden at
    # go-live; the dev default matches docker-compose.
    executor_role_password: SecretStr = SecretStr("datachat_exec")
    redis_url: str = "redis://localhost:6379/0"

    # --- LLM providers ---------------------------------------------------
    gemini_api_key: SecretStr = SecretStr("")
    groq_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    # OpenRouter stays off by default to remain strictly $0 (TechSpec §11).
    openrouter_enabled: bool = False

    # Ollama runs as a separate, network-boundary AI service (e.g. on a home GPU
    # behind a Cloudflare tunnel). ollama_api_key is the bearer token the tunnel
    # requires, so the exposed endpoint can't be abused. When enabled it is the
    # primary provider; Gemini/Groq remain automatic fallbacks (breaker-driven).
    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_api_key: SecretStr = SecretStr("")
    ollama_model: str = "llama3.2"

    provider_order: tuple[Provider, ...] = (Provider.GEMINI, Provider.GROQ)

    # --- Embeddings ------------------------------------------------------
    embedding_model: str = "text-embedding-004"
    embedding_dim: int = 768

    # --- Observability ---------------------------------------------------
    mlflow_tracking_uri: str = "http://localhost:5000"
    # Cap on how long startup may spend talking to the tracking server. Telemetry
    # must never gate readiness — an unreachable host used to add ~90s to boot,
    # long enough for a platform health check to fail the deploy.
    mlflow_startup_timeout_s: float = 5.0

    # --- Agent bounds (LLM10 / ASI08 — bounded consumption) --------------
    max_repair_attempts: int = 2
    row_cap: int = 1000
    statement_timeout_ms: int = 5000
    llm_timeout_s: float = 30.0
    retrieval_k: int = 8
    # Whole-answer cache TTL: repeat questions replay a stored answer for this long.
    answer_cache_ttl_s: int = 3600
    # Web-search fallback for questions with no answer in the governed data.
    # Off by default; results are untrusted and never touch the SQL path.
    web_search_enabled: bool = False
    web_search_provider: str = "mock"  # mock | ddgs

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

    @field_validator("cors_origins", "provider_order", mode="before")
    @classmethod
    def _accept_comma_separated(cls, value: object) -> object:
        """Let list-valued settings be written as ``a,b`` in the environment.

        why: pydantic-settings parses a collection-typed field from an env var as
        JSON, so the obvious `DATACHAT_CORS_ORIGINS=https://app.vercel.app` fails
        with `error parsing value for field "cors_origins"` — a message that
        points at the field but not at the cause, during a deploy, in a hosting
        dashboard. Nobody types a JSON array into a PaaS env box; comma-separated
        is the near-universal convention for this setting.

        JSON is still accepted, so an existing `["a","b"]` value keeps working.
        """
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            # Decoding is off at the source, so parse JSON here rather than
            # handing pydantic a string it will reject as "not a valid tuple".
            with suppress(json.JSONDecodeError):
                return json.loads(text)
        return [item.strip() for item in text.split(",") if item.strip()]

    @field_validator("cors_origins", mode="after")
    @classmethod
    def _normalise_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Drop trailing slashes from configured origins.

        why: a browser's ``Origin`` header is scheme + host + port and never has a
        path, so ``https://app.vercel.app/`` can never match one. Starlette
        compares exactly, and the failure is silent from the server's side — the
        API answers 200 to curl and the browser blocks it, which reads as "the
        frontend is broken". Copying a URL out of a hosting dashboard gives you
        the trailing slash every time, so normalise rather than expect care.
        """
        return tuple(origin.rstrip("/") for origin in value)


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton (scoped via DI, not a global)."""
    return Settings()
