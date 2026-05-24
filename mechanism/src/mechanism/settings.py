"""Runtime configuration for mechanism.

Configuration is loaded by Pydantic Settings from the process environment,
falling back to a `.env` file at the repo root if present. In production
the env vars are exported by Claude Code from `settings.local.json`'s
`env` block; in dev they live in a `.env` file at the repo root.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Self

from pydantic import HttpUrl, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env file (if any) lives at the repo root, two levels above this
# package: mechanism/src/mechanism/settings.py → repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Configuration for mechanism."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    chat_api_key: str
    chat_base_url: HttpUrl
    chat_model: str
    database_url: PostgresDsn
    embedding_api_key: str
    embedding_base_url: HttpUrl
    embedding_model: str
    logfire_token: str | None = None
    mechanism_token: str | None = None
    otel_service_name: str | None = None
    redis_url: RedisDsn
    timezone: str

    @model_validator(mode="after")
    def _logfire_requires_service_name(self) -> Self:
        """Refuse to start if LOGFIRE_TOKEN is set without OTEL_SERVICE_NAME.

        Service identity is explicit per deploy, never inferred — silently
        reporting telemetry under a wrong default is worse than not running.
        """
        if self.logfire_token and not self.otel_service_name:
            msg = "OTEL_SERVICE_NAME is required when LOGFIRE_TOKEN is set."
            raise ValueError(msg)
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-singleton Settings instance."""
    return Settings()  # pyright: ignore[reportCallIssue]
