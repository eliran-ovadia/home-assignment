"""
Runtime configuration.

Reads non-sensitive values (host, port, log level) and the database password
from `.env` for local development, and from OS environment variables in CI
and production.

The DB password is held in `pydantic.SecretStr` so it is automatically
redacted in `repr(settings)` and in any accidental log output. Access the
real value with `settings.db_password.get_secret_value()`.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration."""

    app_env: str = Field(default="development", description="development | production")
    log_level: str = Field(default="INFO", description="DEBUG | INFO | WARNING | ERROR | CRITICAL")

    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="assignment")
    db_user: str = Field(default="postgres")
    db_password: SecretStr = Field(description="PostgreSQL password (required, never logged)")

    # `.env` is read for local dev. In CI/production these come from the OS env.
    # `extra="ignore"` keeps the model permissive — adding a new env var won't raise.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Module-level singleton — instantiated at import time so a misconfigured
# environment fails fast rather than after the first request lands.
# `db_password` is a required field; pydantic-settings populates it from the
# environment (`.env` or OS env var DB_PASSWORD), not from the constructor —
# the type checker can't see that, so we suppress the missing-argument warning.
settings = Settings()  # ty: ignore[missing-argument]
