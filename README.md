# Home Assignment — Lumina Capital Transactions Platform

A financial transactions platform built to professional standards. Every architectural decision is documented and justified in `docs/decisions/`.

---

## At a glance

| Concern | Choice | Decision record |
|---------|--------|-----------------|
| Language | Python 3.12 | [ADR 001](docs/decisions/001-python-version.md) |
| HTTP framework | FastAPI + uvicorn | [ADR 002](docs/decisions/002-fastapi-over-alternatives.md) |
| Lint & format | Ruff | [ADR 003](docs/decisions/003-ruff-toolchain.md) |
| Type checking | ty (Astral) | [ADR 006](docs/decisions/006-ty-over-mypy.md) |
| Database access | SQLAlchemy ORM | [ADR 010](docs/decisions/010-orm-switch.md) |
| Migrations | Alembic | [ADR 010](docs/decisions/010-orm-switch.md) |
| Secrets | `SecretsProvider` abstraction | [ADR 005](docs/decisions/005-secret-manager-over-dotenv.md) |
| Local secrets | `.env` via pydantic-settings | [ADR 012](docs/decisions/012-dotenv-local-development.md) |
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
│   ├── core/                   # Config, secrets, DB engine
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
# 1. Install Python dependencies and wire up pre-commit hooks
make install

# 2. Install frontend dependencies
cd frontend && npm install && cd ..

# 3. Configure secrets
cp .env.example .env
# Edit .env and set DB_PASSWORD (and any other required values)

# 4. Start the full environment (app + database)
make dev
# → App available at http://localhost:8000
# → API docs at http://localhost:8000/api/docs
```

---

## Development commands

```bash
make check                          # ruff lint + ty type-check
make test                           # full test suite with coverage report
make test-unit                      # unit tests — no database needed
make test-integration               # integration tests — requires running DB
make migrate                        # apply all pending Alembic migrations
make migration name="add_uploads"   # generate a new migration file
make format                         # auto-format with ruff
make clean                          # remove all caches and build artefacts

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
make test                 # all tests
make test-unit            # unit only (no DB)
make test-integration     # integration (requires DB)
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

## Secrets & configuration

No secrets are hardcoded. For local development, copy `.env.example` to `.env` and fill in your values — `pydantic-settings` reads it automatically.

In CI (GitHub Actions), secrets are injected as environment variables from repository settings. In production, swap `EnvironmentSecretsProvider` for a Vault or cloud-provider implementation — no business logic changes required.

See `src/core/secrets.py` and [ADR 005](docs/decisions/005-secret-manager-over-dotenv.md).

---

## Architecture Decision Records

Every non-obvious technical choice is documented in [`docs/decisions/`](docs/decisions/):

| # | Decision |
|---|----------|
| [001](docs/decisions/001-python-version.md) | Python 3.12 |
| [002](docs/decisions/002-fastapi-over-alternatives.md) | FastAPI over Flask / Django REST |
| [001](docs/decisions/001-python-version.md) | Python 3.12 |
| [002](docs/decisions/002-fastapi-over-alternatives.md) | FastAPI over Flask / Django REST |
| [005](docs/decisions/005-secret-manager-over-dotenv.md) | SecretsProvider protocol |
| [008](docs/decisions/008-react-frontend-architecture.md) | React served as FastAPI static files |
| [009](docs/decisions/009-replace-on-upload.md) | Replace-on-upload (historical — led to ADR 014) |
| [010](docs/decisions/010-orm-switch.md) | SQLAlchemy ORM |
| [011](docs/decisions/011-reject-on-defective-row.md) | Reject entire upload on any invalid row |
| [013](docs/decisions/013-synchronous-upload-response.md) | Synchronous (blocking) upload response |
| [014](docs/decisions/014-per-upload-result-storage.md) | Per-upload result storage; instant activate |
| [015](docs/decisions/015-uuid-anonymous-sessions.md) | UUID anonymous user sessions |
