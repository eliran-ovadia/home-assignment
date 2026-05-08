# ADR 005: SecretsProvider Abstraction Instead of .env Files

**Date:** 2026-05-06
**Status:** Accepted

## Context

`.env` files are a common development shortcut but carry real risks: they are accidentally committed to version control, their contents appear in process listings, they provide no audit trail, and they cannot support secret rotation. A professional codebase should treat secrets as a first-class concern from day one.

## Decision

Define a `SecretsProvider` protocol in `src/core/secrets.py`. The default implementation reads from **OS environment variables** only — never from a file on disk. For local development, variables are exported in the shell (or via `direnv` with a gitignored `.envrc`). In CI, they are injected as GitHub Actions secrets. In production, the provider is swapped for a dedicated backend.

`.env` files are explicitly excluded via `.gitignore` as a safety net, but none are created or expected.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **SecretsProvider + OS env** | Secure by default; no sensitive files on disk; swappable backend; audit-friendly | Slightly more setup for local dev compared to `.env` |
| `.env` + python-dotenv | Simple; widely understood | Accidental commits; secrets visible in filesystem; no rotation; not production-safe |
| Full HashiCorp Vault | Industry gold standard; full audit trail; dynamic secrets | Significant infrastructure overhead; overkill for an assignment scope |
| AWS Secrets Manager | Managed; integrates with IAM | Requires AWS account; adds cloud dependency |

## Consequences

- `SecretsProvider` is a Protocol — any backend (Vault, AWS SSM, GCP Secret Manager) can be plugged in by implementing a single `get(key: str) -> str` method
- Business logic never calls `os.environ` directly — it goes through `get_secret()`
- `.gitignore` includes `.env*` as a blanket catch-all
- Local dev setup is documented in `README.md`: which variables must be exported before running the app
