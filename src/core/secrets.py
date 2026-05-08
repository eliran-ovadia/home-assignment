"""
Secrets management abstraction.

Decouples secret retrieval from business logic so the backend can be swapped
(environment variables → Vault → AWS SSM) without touching any call sites.

See docs/decisions/005-secret-manager-over-dotenv.md for the full rationale.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretsProvider(Protocol):
    """Contract that every secrets backend must satisfy."""

    def get(self, key: str) -> str:
        """Return the secret value for *key*, or raise KeyError if absent."""
        ...


class EnvironmentSecretsProvider:
    """
    Reads secrets from OS environment variables.

    This is the default for local development and CI.
    In production, replace with a provider backed by Vault or a cloud
    secrets manager — no call-site changes required.
    """

    def get(self, key: str) -> str:
        try:
            return os.environ[key]
        except KeyError:
            raise KeyError(
                f"Required secret '{key}' is not set. "
                "Export it as an environment variable, or configure a "
                "production secrets backend via configure_provider()."
            ) from None


# Module-level singleton — override once at application startup for production.
_provider: SecretsProvider = EnvironmentSecretsProvider()


def get_secret(key: str) -> str:
    """Retrieve a secret through the active provider."""
    return _provider.get(key)


def configure_provider(provider: SecretsProvider) -> None:
    """
    Replace the global secrets provider.

    Call this once during application startup, before any secrets are read.
    Example production usage::

        from myapp.infra.vault import VaultSecretsProvider
        configure_provider(VaultSecretsProvider(address="https://vault.internal"))
    """
    global _provider
    _provider = provider
