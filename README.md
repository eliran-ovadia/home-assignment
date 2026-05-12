# Lumina Capital — Transactions Platform

A FastAPI + React application that ingests Excel transaction files, runs FIFO
position math, detects business-rule violations (sell-before-buy, day-trading,
risk concentration, invalid values), and surfaces per-client analytics.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy ORM + Alembic · PostgreSQL 16 ·
React 18 + Vite + Ant Design. Packaged as a multi-stage Docker build.

**Where to read more:** [`docs/SPEC.md`](docs/SPEC.md) (full spec) ·
[`docs/decisions/`](docs/decisions/) (ADRs) · [`API_EXAMPLES.md`](API_EXAMPLES.md) (every endpoint × every return code) ·
[`samples/`](samples/) (test files) · [`postman/`](postman/) (Postman collection) ·
[`developer_tips.md`](developer_tips.md) (Alembic + cleanup recipes).

Each "How to run …" section below is self-contained — pick one and follow it
top to bottom right after cloning the repo.

---

## How to run the full stack (recommended)

Brings up Postgres, runs migrations, and starts the API + UI on
`http://localhost:8000/` in a single command.

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Create the env file (defaults work as-is, also included with the zip already):
   ```bash
   cp .env.example .env
   ```
3. Boot everything:
   ```bash
   docker compose up --build
   ```

- App + UI → http://localhost:8000/
- Swagger → http://localhost:8000/api/docs

---

## How to run the backend locally (hot reload)

Uses Docker only for Postgres; runs uvicorn directly so backend code changes
trigger a reload.

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Create the env file (included with the zip:
   ```bash
   cp .env.example .env
   ```
3. Create a Python 3.12 virtual environment (or let your IDE create one):
   ```bash
   python -m venv .venv
   ```
4. Activate it:
   ```powershell
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   ```
   ```bash
   # macOS / Linux
   source .venv/bin/activate
   ```
5. Install the backend + dev dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
6. Start Postgres in the background and run the migrations:
   ```bash
   docker compose up db -d
   docker compose run --rm migrate
   ```
7. Run the API with hot reload:
   ```bash
   uvicorn src.api.app:app --reload --port 8000
   ```

→ API at http://localhost:8000/api/docs.

---

## How to run the frontend (Vite dev server)

The production bundle is built and served by FastAPI automatically when you
run `docker compose up`. The instructions below are for the dev server with
hot module reload — assumes the backend is already running on `:8000`.

1. Install [Node.js 20+](https://nodejs.org/).
2. Install the frontend dependencies:
   ```bash
   cd frontend
   npm install
   ```
3. Start the dev server:
   ```bash
   npm run dev
   ```

→ UI at http://localhost:5173 (proxies `/api` to the backend on `:8000`).

---

## How to run the tests

Unit tests need only Python. Integration tests additionally need a running
Postgres **and** the same `.env` the rest of the project uses (pytest imports
`Settings` at collection time and `DB_PASSWORD` is required).

1. Create the env file (included with the zip; defaults work as-is):
   ```bash
   cp .env.example .env
   ```
2. Create a Python 3.12 virtual environment (or let your IDE create one):
   ```bash
   python -m venv .venv
   ```
3. Activate it:
   ```powershell
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   ```
   ```bash
   # macOS / Linux
   source .venv/bin/activate
   ```
4. Install the backend + dev dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
5. Run the tests:
   ```bash
   # Unit tests — no DB required (53 tests)
   pytest tests/unit/

   # Integration tests — need a running DB first
   docker compose up db -d
   docker compose run --rm migrate
   pytest tests/integration/

   # Full suite (what CI runs)
   pytest
   ```
