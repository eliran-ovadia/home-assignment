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
| Lint + format | Ruff | — |
| Type checking | ty (Astral) | — |
| Database access | SQLAlchemy ORM + Alembic migrations | [ADR 010](docs/decisions/010-orm-switch.md) |
| Configuration & secrets | `pydantic-settings` reads `.env` locally; OS env vars in CI/Docker. `SecretStr` redacts the password in logs and `repr`. | — |
| Package manager | pip | |
| UI framework | Ant Design (React) | [ADR 008](docs/decisions/008-react-frontend-architecture.md) |
| Frontend delivery | React build served by FastAPI static files | [ADR 008](docs/decisions/008-react-frontend-architecture.md) |
| Upload behaviour | Per-upload result storage; activate = instant flag flip | [ADR 014](docs/decisions/014-per-upload-result-storage.md) extends [ADR 009](docs/decisions/009-replace-on-upload.md) |
| Upload validation | Reject entire file on any invalid row | [ADR 011](docs/decisions/011-reject-on-defective-row.md) |
| Upload response | Synchronous blocking HTTP | [ADR 013](docs/decisions/013-synchronous-upload-response.md) |
| Identity | Corporate email forwarded in `X-Session-Token` header (deployment context: corporate intranet — see [SPEC §0](docs/SPEC.md)) | [ADR 016](docs/decisions/016-email-as-identity.md) (supersedes [ADR 015](docs/decisions/015-uuid-anonymous-sessions.md)) |
| Data visibility | Shared upload pool — every user sees every upload; per-user `last_viewed_upload_id` preference | [ADR 016](docs/decisions/016-email-as-identity.md) |

## Domain Architecture

The full technical specification lives in [`docs/SPEC.md`](docs/SPEC.md). Summary:

```
src/
├── core/       # Cross-cutting infrastructure: config, DB engine
├── api/        # FastAPI routes, Pydantic response schemas, dependencies
├── domain/     # Pure business logic: FIFO engine, violation detectors, analytics
├── ingestion/  # Excel parsing and row-level validation
└── db/         # ORM models, repositories (all DB access)

frontend/       # React + Ant Design, built once and served by FastAPI
migrations/     # Alembic migration files
tests/          # unit/ (no DB) and integration/ (requires DB)
```

**Layer rule:** dependencies only point downward: `api → domain → db`. The `domain/` layer has zero imports from `api/` or `db/`.

**Async model:** All routes use `async def` with `AsyncSession` (asyncpg driver). CPU-bound sections (openpyxl parsing, FIFO computation) use `await asyncio.to_thread(fn, args)` to run in a thread pool without blocking the event loop. GET routes are pure async I/O. The upload route combines async DB calls with `asyncio.to_thread` for compute steps.

**Concurrency:** No application-level locking. Each upload writes its own `upload_id` in an independent transaction, so concurrent uploads from any users do not conflict.

**Identity (corporate intranet deployment):** Every request carries `X-Session-Token: <corporate-email>` (validated as `pydantic.EmailStr` at the API boundary). The `get_current_user()` FastAPI dependency resolves the email to a `users` row (creating one on first sight). All uploads are visible to every user; the only per-user state is `users.last_viewed_upload_id`, which is what makes a returning user (possibly on a new device) auto-load their last-selected upload. See `docs/SPEC.md` §0 for the trust model.

## Development Commands

```bash
make install                          # pip install -e ".[dev]" + pre-commit install
make check                            # ruff lint + ty type-check
make test                             # full test suite with coverage
make test-unit                        # unit tests only (no DB)
make test-integration                 # integration tests (requires DB)
make dev                              # docker compose up --build
make dev-db                           # start only postgres
make migrate                          # alembic upgrade head
make migration name="describe_change" # generate new migration
make clean                            # remove all caches

# Frontend (development only — production build is handled by Docker)
cd frontend && npm install            # install frontend dependencies
cd frontend && npm run dev            # Vite dev server (proxies /api to FastAPI)
cd frontend && npm run build          # build to frontend/dist/
```

## Infrastructure Map

When changing a tool or adding one, update **all** of these files. This map is the checklist:

| Tool / concern | Files that must stay in sync |
|----------------|------------------------------|
| Type checker (ty) | `pyproject.toml` `[tool.ty]` + dev dep, `Makefile` `typecheck`, `.pre-commit-config.yaml`, `ci.yml` |
| Linter / formatter (ruff) | `pyproject.toml` `[tool.ruff]` + dev dep, `Makefile` `lint`/`format`, `.pre-commit-config.yaml`, `ci.yml` |
| Test runner (pytest) | `pyproject.toml` `[tool.pytest.ini_options]`, `Makefile` test targets, `ci.yml` test job |
| Database engine | `docker-compose.yml`, `ci.yml` service block, `Dockerfile` (if driver needs OS libs), relevant ADR |
| Configuration | `src/core/config.py` (`Settings`), `.env.example`, `docker-compose.yml` env block, `README.md` setup section |
| Python version | `pyproject.toml` `requires-python`, `Dockerfile` base image, `ci.yml` `python-version`, `[tool.ruff] target-version`, `[tool.ty.environment] python-version`, `docs/decisions/001` |
| ORM models | `src/db/models.py`, `migrations/versions/`, `docs/decisions/010` |
| Identity / sessions | `src/api/deps.py` (`get_current_user`), `src/db/repositories/users.py`, `frontend/src/api/client.ts` (email-in-localStorage + header injection), `docs/decisions/016`, `docs/SPEC.md` §0 |

## Configuration & Secrets

All runtime configuration — including the database password — lives in `src/core/config.py` as a single `pydantic-settings` `Settings` model. Business code reads `from src.core.config import settings`; nothing else should call `os.environ` directly.

- **DB password** is held in `pydantic.SecretStr`, so it is automatically redacted in `repr(settings)` and accidental log output. Access the real value with `settings.db_password.get_secret_value()` (currently only `src/core/database.py` does this when composing the asyncpg URL).
- **Local dev**: copy `.env.example` to `.env` and fill in values. `pydantic-settings` reads `.env` automatically.
- **CI (GitHub Actions)**: env vars are injected from repository secrets by the workflow.
- **Docker**: env vars come from the `environment:` block in `docker-compose.yml`; the password is forwarded from the host shell.

## Git Discipline

Commits are part of the deliverable. Each commit must be atomic and explain **why**, not just what.

Format: `type(scope): description`
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

## Assignment Status

Assignment received 2026-05-09. Full domain architecture and specification defined in `docs/SPEC.md`. Implementation begins after spec is finalised.
