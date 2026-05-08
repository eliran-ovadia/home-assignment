# Home Assignment

A Python backend project built to professional standards, with every tooling and architectural decision documented and justified.

---

## At a glance

| Concern | Choice | Decision record |
|---------|--------|-----------------|
| Language | Python 3.12 | [ADR 001](docs/decisions/001-python-version.md) |
| HTTP framework | FastAPI + uvicorn | [ADR 002](docs/decisions/002-fastapi-over-alternatives.md) |
| Lint & format | Ruff | [ADR 003](docs/decisions/003-ruff-toolchain.md) |
| Type checking | ty (Astral) | [ADR 006](docs/decisions/006-ty-over-mypy.md) |
| Database access | SQLAlchemy Core + raw SQL | [ADR 004](docs/decisions/004-sqlalchemy-core-pure-sql.md) |
| Migrations | Alembic (raw SQL scripts) | [ADR 004](docs/decisions/004-sqlalchemy-core-pure-sql.md) |
| Secrets | `SecretsProvider` abstraction | [ADR 005](docs/decisions/005-secret-manager-over-dotenv.md) |
| Package manager | uv | Fast, lock-file based; `.python-version` pins 3.12 |
| Container | Docker (multi-stage, non-root user) | `Dockerfile` |
| CI | GitHub Actions (lint + unit tests) | `.github/workflows/ci.yml` |
| Pre-commit | ruff + ty on every commit | `.pre-commit-config.yaml` |

---

## Setup

```bash
# 1. Install dependencies and wire up pre-commit hooks
make install

# 2. Export required secrets as environment variables (no .env files — see ADR 005)
export DB_PASSWORD=your_local_password

# 3. Start the full local environment (app + database via Docker Compose)
make dev
```

---

## Development commands

```bash
make check                          # ruff lint + ty type-check
make test                           # full test suite with coverage report
make test-unit                      # unit tests only — no database needed
make test-integration               # integration tests — requires running DB
make migrate                        # apply all pending Alembic migrations
make migration name="add_users"     # generate a new migration file
make format                         # auto-format with ruff
make clean                          # remove all caches and build artefacts
```

---

## Secrets & configuration

No `.env` files are created or committed. Secrets are injected via OS environment variables:

- **Local development**: `export VAR=value` in your shell (or use `direnv` with a gitignored `.envrc`)
- **CI (GitHub Actions)**: secrets are configured in the repository settings and automatically injected as environment variables by the workflow
- **Production**: swap `EnvironmentSecretsProvider` for a Vault or cloud-provider implementation — no business logic changes required

See `src/core/secrets.py` for the `SecretsProvider` protocol and [ADR 005](docs/decisions/005-secret-manager-over-dotenv.md) for the full rationale.

---

## Why no ORM?

The database layer uses **SQLAlchemy Core** with hand-written SQL queries. SQLAlchemy is responsible for connection pooling, transaction management, and parameterised queries (preventing SQL injection) — not for generating SQL. Every query in this codebase is explicit and can be read, reviewed, and optimised directly.

See [ADR 004](docs/decisions/004-sqlalchemy-core-pure-sql.md).

---

## Architecture Decision Records

Every non-obvious technical choice is documented in [`docs/decisions/`](docs/decisions/):

| # | Decision |
|---|----------|
| [001](docs/decisions/001-python-version.md) | Python 3.12 |
| [002](docs/decisions/002-fastapi-over-alternatives.md) | FastAPI over Flask / Django REST |
| [003](docs/decisions/003-ruff-toolchain.md) | Ruff as unified lint + format tool |
| [004](docs/decisions/004-sqlalchemy-core-pure-sql.md) | SQLAlchemy Core with raw SQL — no ORM |
| [005](docs/decisions/005-secret-manager-over-dotenv.md) | SecretsProvider over .env files |
| [006](docs/decisions/006-ty-over-mypy.md) | ty over mypy for type checking |
| [007](docs/decisions/007-github-secrets-as-backend.md) | GitHub Actions Secrets as the CI/CD secrets backend |
