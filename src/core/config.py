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

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration."""

    app_env: str = "development"
    log_level: str = "INFO"

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "assignment"
    db_user: str = "postgres"
    db_password: SecretStr  # required — populated from DB_PASSWORD

    # `extra="forbid"` rejects any unknown key in `.env` so a typo such as
    # `DB_PASWORD=...` raises at startup instead of silently using the default.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )


# Instantiated at import so a misconfigured environment fails fast.
settings = Settings()  # ty: ignore[missing-argument] — db_password populated from env
