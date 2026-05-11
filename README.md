# Home Assignment — Lumina Capital Transactions Platform

A financial transactions platform built to professional standards. Every architectural decision is documented and justified in `docs/decisions/`.

---

## At a glance

| Concern | Choice | Decision record |
|---------|--------|-----------------|
| Language | Python 3.12 | [ADR 001](docs/decisions/001-python-version.md) |
| HTTP framework | FastAPI + uvicorn | [ADR 002](docs/decisions/002-fastapi-over-alternatives.md) |
| Lint & format | Ruff | — |
| Type checking | ty (Astral) | — |
| Database access | SQLAlchemy ORM | [ADR 010](docs/decisions/010-orm-switch.md) |
| Migrations | Alembic | [ADR 010](docs/decisions/010-orm-switch.md) |
| Configuration & secrets | `pydantic-settings` + `.env` (DB password held in `SecretStr`) | — |
| Package manager | pip | |
| UI framework | React + Ant Design | [ADR 008](docs/decisions/008-react-frontend-architecture.md) |
| Frontend delivery | React build served by FastAPI | [ADR 008](docs/decisions/008-react-frontend-architecture.md) |
| Upload behaviour | Per-upload result storage; instant activate | [ADR 014](docs/decisions/014-per-upload-result-storage.md) |
| User sessions | UUID anonymous sessions | [ADR 015](docs/decisions/015-uuid-anonymous-sessions.md) |
| Upload validation | Reject file on any invalid row | [ADR 011](docs/decisions/011-reject-on-defective-row.md) |
| Container | Docker multi-stage (Node build + Python runtime) | `Dockerfile` |
| CI | GitHub Actions | `.github/workflows/ci.yml` |

---

## Project structure

```
home-assignment/
├── src/                        # Python backend
│   ├── core/                   # Config + DB engine
│   ├── api/                    # FastAPI routes + Pydantic response schemas
│   │   └── routes/             # One file per endpoint group
│   ├── domain/                 # Pure business logic (FIFO, violations, analytics)
│   ├── ingestion/              # Excel parsing and row validation
│   └── db/                     # ORM models + repositories
│       └── repositories/       # All DB access — one file per table
├── frontend/                   # React + Ant Design
│   └── src/
│       ├── api/client.ts       # All fetch() calls live here
│       └── components/         # UploadSection, PositionsTable, ViolationsTable, etc.
├── migrations/                 # Alembic migration files
├── tests/
│   ├── unit/                   # No DB required — domain logic only
│   └── integration/            # Requires running PostgreSQL
└── docs/decisions/             # Architecture Decision Records (ADR 001–012)
```

See [`docs/SPEC.md`](docs/SPEC.md) for the full technical specification: database schema, API contract, business logic algorithms, and architecture patterns.

---

## Setup

```bash
# 1. Install backend dependencies (only needed if running locally without Docker)
pip install -e ".[dev]"
cd frontend && npm install && cd ..

# 2. Configure environment
cp .env.example .env
# Edit .env and set DB_PASSWORD (Docker Compose reads .env automatically)

# 3. Start the full environment (app + database, three-stage Docker build)
docker compose up --build
# → App + UI at http://localhost:8000/
# → Swagger at  http://localhost:8000/api/docs
```

First boot pulls the `node:20-alpine` + `python:3.12-slim` + `postgres:16-alpine`
base images and runs `npm install` + `npm run build` + `pip install` once;
subsequent boots reuse the cached image layers. Migrations are a one-shot
`migrate` service that runs `alembic upgrade head` after the DB reports
healthy; the `app` service depends on it with
`service_completed_successfully` so the API can never boot against an
unmigrated schema. No manual migration step.

---

## Development commands

```bash
# Quality checks
ruff check .                            # lint
ruff format .                           # auto-format
ty check src/                           # type-check

# Tests
pytest tests/unit/                      # unit only — no database needed
pytest tests/integration/               # integration — requires running DB
pytest --cov-fail-under=80              # full suite + 80% coverage gate (what CI runs)

# Migrations
alembic upgrade head                                       # apply pending migrations
alembic revision --autogenerate -m "describe the change"   # generate new migration

# Frontend (local development only — Docker handles the production build)
cd frontend && npm run dev          # Vite dev server with /api proxy to FastAPI
cd frontend && npm run build        # build to frontend/dist/
```

---

## How to run backend (without Docker)

```bash
# Requires a running PostgreSQL instance and a configured .env file
uvicorn src.api.app:app --reload --port 8000
```

## How to run frontend (without Docker)

```bash
cd frontend
npm run dev
# → Frontend at http://localhost:5173 (proxies /api to localhost:8000)
```

## How to run tests

```bash
pytest --cov-fail-under=80    # all tests + 80% coverage gate (what CI runs)
pytest tests/unit/            # unit only (no DB)
pytest tests/integration/     # integration (requires DB — `docker compose up db -d`)
```

---

## API documentation

FastAPI generates interactive docs automatically. With the server running:

| URL | Description |
|-----|-------------|
| `http://localhost:8000/api/docs` | Swagger UI — try every endpoint in the browser |
| `http://localhost:8000/api/redoc` | ReDoc — clean reference documentation |

### Example requests

```bash
# Upload a transactions file
curl -X POST http://localhost:8000/api/v1/upload-transactions \
  -H "X-Session-Token: your-uuid-here" \
  -F "file=@transactions_sample.xlsx"

# List clients
curl http://localhost:8000/api/v1/clients \
  -H "X-Session-Token: your-uuid-here"

# Get analytics
curl http://localhost:8000/api/v1/analytics \
  -H "X-Session-Token: your-uuid-here"
```

---

## Configuration & secrets

No secrets are hardcoded. All runtime values — including the database password — live in `src/core/config.py` as a `pydantic-settings` `Settings` model.

- **Local dev:** copy `.env.example` to `.env` and fill in your values; `pydantic-settings` reads it automatically.
- **CI (GitHub Actions):** values are injected as environment variables from repository secrets.
- **Docker:** values come from the `environment:` block in `docker-compose.yml`; the password is forwarded from the host shell.

The DB password is held in `pydantic.SecretStr`, so it is redacted in `repr(settings)` and any accidental log output. Access the real value with `settings.db_password.get_secret_value()` (currently only `src/core/database.py` does this, when composing the asyncpg URL).

For a production deployment, the natural next step is swapping `.env` / OS env vars for a managed store (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault). See `docs/PRODUCTION_ROADMAP.md` §7.

---

## Architecture Decision Records

Every non-obvious technical choice is documented in [`docs/decisions/`](docs/decisions/):

| # | Decision |
|---|----------|
| [001](docs/decisions/001-python-version.md) | Python 3.12 |
| [002](docs/decisions/002-fastapi-over-alternatives.md) | FastAPI over Flask / Django REST |
| [008](docs/decisions/008-react-frontend-architecture.md) | React served as FastAPI static files |
| [009](docs/decisions/009-replace-on-upload.md) | Replace-on-upload (historical — led to ADR 014) |
| [010](docs/decisions/010-orm-switch.md) | SQLAlchemy ORM |
| [011](docs/decisions/011-reject-on-defective-row.md) | Reject upload on structural defects; flag value defects as INVALID_VALUE |
| [013](docs/decisions/013-synchronous-upload-response.md) | Synchronous (blocking) upload response |
| [014](docs/decisions/014-per-upload-result-storage.md) | Per-upload result storage; instant activate |
| [015](docs/decisions/015-uuid-anonymous-sessions.md) | UUID anonymous user sessions |
