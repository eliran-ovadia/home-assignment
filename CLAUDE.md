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
| Secrets (abstraction) | `SecretsProvider` protocol in `src/core/secrets.py` | [ADR 005](docs/decisions/005-secret-manager-over-dotenv.md) |
| Local development secrets | `.env` via pydantic-settings; `.env.example` committed | — |
| CI secrets | GitHub Actions Secrets → `EnvironmentSecretsProvider` | — |
| Package manager | pip | |
| UI framework | Ant Design (React) | [ADR 008](docs/decisions/008-react-frontend-architecture.md) |
| Frontend delivery | React build served by FastAPI static files | [ADR 008](docs/decisions/008-react-frontend-architecture.md) |
| Upload behaviour | Per-upload result storage; activate = instant flag flip | [ADR 014](docs/decisions/014-per-upload-result-storage.md) extends [ADR 009](docs/decisions/009-replace-on-upload.md) |
| Upload validation | Reject entire file on any invalid row | [ADR 011](docs/decisions/011-reject-on-defective-row.md) |
| Upload response | Synchronous blocking HTTP | [ADR 013](docs/decisions/013-synchronous-upload-response.md) |
| User sessions | UUID anonymous sessions; X-Session-Token header | [ADR 015](docs/decisions/015-uuid-anonymous-sessions.md) |

## Domain Architecture

The full technical specification lives in [`docs/SPEC.md`](docs/SPEC.md). Summary:

```
src/
├── core/       # Cross-cutting infrastructure: config, secrets, DB engine
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

**Concurrency:** Per-user PostgreSQL advisory lock (`pg_try_advisory_lock(user_id)`). Different users can upload simultaneously; the same user cannot. Concurrent same-user uploads receive HTTP 409.

**User isolation:** Every request carries `X-Session-Token: <uuid>`. The `get_current_user()` FastAPI dependency resolves this to a `users` row (creating one on first sight). All DB queries filter by the active `upload_id` for the current user — no user can read another user's data.

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
| Secrets pattern | `src/core/secrets.py`, `.env.example`, `docker-compose.yml` env notes, `docs/decisions/005`, `README.md` secrets section |
| Python version | `pyproject.toml` `requires-python`, `Dockerfile` base image, `ci.yml` `python-version`, `[tool.ruff] target-version`, `[tool.ty] python-version`, `docs/decisions/001` |
| ORM models | `src/db/models.py`, `migrations/versions/`, `docs/decisions/010` |
| User sessions | `src/api/deps.py` (`get_current_user`), `src/db/repositories/users.py`, `frontend/src/api/client.ts` (localStorage + header injection), `docs/decisions/015` |

## Secrets & Configuration

- **Secrets** (DB password, API keys): retrieved via `get_secret(key)` from `src.core.secrets`. Never call `os.environ` directly in business logic.
- **Non-sensitive config** (port, log level, env name): use `pydantic-settings` in `src/core/config.py`.
- **Local dev**: copy `.env.example` to `.env` and fill in values. `pydantic-settings` reads it automatically.
- **CI (GitHub Actions)**: secrets are configured in repository settings and injected as env vars by the workflow.

## Git Discipline

Commits are part of the deliverable. Each commit must be atomic and explain **why**, not just what.

Format: `type(scope): description`
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

## Assignment Status

Assignment received 2026-05-09. Full domain architecture and specification defined in `docs/SPEC.md`. Implementation begins after spec is finalised.
