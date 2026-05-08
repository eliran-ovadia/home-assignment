# ADR 007: GitHub Actions Secrets as the CI/CD Secrets Backend

**Date:** 2026-05-06
**Status:** Accepted

## Context

The `SecretsProvider` abstraction (ADR 005) decouples the application from any specific secrets backend. A concrete backend must still be chosen for CI and for local development. The chosen backend should require no additional infrastructure, cost nothing, and be something any developer working in the industry will already be familiar with.

## Decision

Use **GitHub Actions Secrets** for CI/CD and the project's primary secrets management layer.

GitHub injects repository secrets as plain OS environment variables during workflow runs, which means the existing `EnvironmentSecretsProvider` handles them automatically — no additional code or provider implementation is needed.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **GitHub Actions Secrets** | **Free**; built into the repository — zero additional infrastructure; industry standard for open-source and commercial projects; secrets are encrypted at rest and masked in logs; widely known by any developer who has used GitHub | CI/CD only — secrets cannot be pulled by a running server at runtime |
| HashiCorp Vault (free tier) | Full audit trail; dynamic secrets; runtime-capable | Requires running a server or paying for HCP Vault; significant setup overhead |
| AWS Secrets Manager | Managed; runtime-capable; integrates with IAM | Not free (charged per secret per month + API calls); requires an AWS account |
| GCP Secret Manager | Managed; runtime-capable | Not free; requires a GCP project |
| Azure Key Vault | Managed; runtime-capable | Not free; requires an Azure account |

## Consequences

- Secrets are stored in GitHub repository Settings → Secrets and referenced in workflow files as `${{ secrets.MY_KEY }}`
- GitHub automatically injects them as environment variables, so `EnvironmentSecretsProvider` requires no changes
- Secrets are **masked** in all GitHub Actions log output — they will never appear in plaintext in CI logs
- For local development, the same variable names are exported manually in the shell (`export MY_KEY=value`) or managed via `direnv`
- If the project is ever deployed as a long-running service, the `SecretsProvider` abstraction allows swapping in Vault or a cloud provider without touching any business logic
