# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This is a home assignment submission for a junior Python developer role. The primary audience is a technical team lead who will review the code, ask detailed questions, and evaluate decision-making depth — not just whether the code works.

Every technical choice must be conscious, documented, and defensible in conversation.

## Decision-Making Standard

Before introducing any library, pattern, or architectural choice, document **why** it was chosen and what the alternatives were. Non-trivial decisions live in `docs/decisions/` as Architecture Decision Records (ADRs). An ADR template is at `docs/decisions/000-template.md`.

## Tech Stack

| Concern | Choice | ADR |
|---------|--------|-----|
| Language | Python 3.12 (pinned in `.python-version`) | [ADR 001](docs/decisions/001-python-version.md) |
| HTTP framework | FastAPI + uvicorn | [ADR 002](docs/decisions/002-fastapi-over-alternatives.md) |
| Lint + format | Ruff | [ADR 003](docs/decisions/003-ruff-toolchain.md) |
| Type checking | ty (Astral) | [ADR 006](docs/decisions/006-ty-over-mypy.md) |
| Database access | SQLAlchemy Core, raw SQL, Alembic migrations | [ADR 004](docs/decisions/004-sqlalchemy-core-pure-sql.md) |
| Secrets (abstraction) | `SecretsProvider` protocol in `src/core/secrets.py` | [ADR 005](docs/decisions/005-secret-manager-over-dotenv.md) |
| Secrets (backend) | GitHub Actions Secrets → `EnvironmentSecretsProvider` | [ADR 007](docs/decisions/007-github-secrets-as-backend.md) |
| Package manager | uv |  |

Key constraint: **no ORM**. Every query is written in SQL. SQLAlchemy is used only for connection pooling, transaction management, and parameterised queries.

## Development Commands

```bash
make install                          # uv sync + pre-commit install
make check                            # ruff lint + ty type-check
make test                             # full test suite with coverage
make test-unit                        # unit tests only (no DB)
make test-integration                 # integration tests (requires DB)
make dev                              # docker compose up --build
make dev-db                           # start only postgres
make migrate                          # alembic upgrade head
make migration name="describe_change" # generate new migration
make clean                            # remove all caches
```

## Infrastructure Map

When changing a tool or adding one, update **all** of these files. This map is the checklist:

| Tool / concern | Files that must stay in sync |
|----------------|------------------------------|
| Type checker (ty) | `pyproject.toml` `[tool.ty]` + dev dep, `Makefile` `typecheck`, `.pre-commit-config.yaml`, `ci.yml`, `CLAUDE.md` table, `README.md` table, `docs/decisions/006` |
| Linter / formatter (ruff) | `pyproject.toml` `[tool.ruff]` + dev dep, `Makefile` `lint`/`format`, `.pre-commit-config.yaml`, `ci.yml`, `CLAUDE.md` table, `README.md` table, `docs/decisions/003` |
| Test runner (pytest) | `pyproject.toml` `[tool.pytest.ini_options]`, `Makefile` test targets, `ci.yml` test job |
| Database engine | `docker-compose.yml`, `ci.yml` service block, `Dockerfile` (if driver needs OS libs), relevant ADR |
| Secrets pattern | `src/core/secrets.py`, `docker-compose.yml` env notes, `docs/decisions/005`, `README.md` secrets section |
| Python version | `.python-version`, `pyproject.toml` `requires-python`, `Dockerfile` base image, `ci.yml` `python-version`, `[tool.ruff] target-version`, `[tool.ty] python-version`, `docs/decisions/001` |

## Secrets & Configuration

- **Secrets** (DB password, API keys): retrieved via `get_secret(key)` from `src.core.secrets`. Never call `os.environ` directly in business logic.
- **Non-sensitive config** (port, log level, env name): use `pydantic-settings`.
- **Local dev**: export required variables in your shell. No `.env` file is created or expected.
- **CI (GitHub Actions)**: secrets are configured in repository settings and injected as env vars by the workflow — `EnvironmentSecretsProvider` picks them up automatically, no special provider needed.

## Git Discipline

Commits are part of the deliverable. Each commit must be atomic and explain **why**, not just what.

Format: `type(scope): description`
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

## Assignment Status

Assignment not yet received (as of 2026-05-06). This file will be updated with domain-specific architecture once the assignment brief arrives.
