# ADR 012: .env File for Local Development (supersedes ADR 007 for local usage)

**Date:** 2026-05-09
**Status:** Accepted — supersedes ADR 007 local-dev guidance

## Context

ADR 007 chose GitHub Actions Secrets as the CI/CD secrets backend and instructed developers to `export VAR=value` in their shell for local development. This works but creates friction: a new developer must read the README, identify which variables are required, and manually export each one before the app starts. A reviewer evaluating this assignment should be able to get the system running with minimal friction.

`pydantic-settings` (already a project dependency) supports reading from a `.env` file natively with zero additional code.

## Decision

A `.env.example` file is committed to the repository listing every required variable with placeholder values. Developers copy it to `.env` (gitignored) and fill in their values. `pydantic-settings` reads `.env` automatically when `env_file=".env"` is set in the `Settings` model config.

The `SecretsProvider` abstraction in `src/core/secrets.py` is retained: in production, swap `EnvironmentSecretsProvider` for a Vault or cloud-provider implementation without touching any business logic. The `.env` approach is a developer convenience, not an architectural replacement.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **`.env` via pydantic-settings** | Minimal friction for local dev and reviewers; no new dependencies; gitignored | Values must still be manually set in `.env.example` |
| Manual `export VAR=value` (original ADR 007) | No files on disk | Friction for new developers; must be re-exported every shell session |
| `direnv` + `.envrc` | Auto-loads on `cd` | Requires installing direnv; adds a tool not everyone has |

## Consequences

- `.env.example` is committed. `.env` is gitignored (already in `.gitignore`).
- The reviewer runs `cp .env.example .env`, sets `DB_PASSWORD`, and the app starts.
- CI (GitHub Actions) continues to use repository secrets injected as environment variables — no change to the CI workflow.
- `pydantic-settings` model config: `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")`.
