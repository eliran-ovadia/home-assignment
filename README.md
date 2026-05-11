# Lumina Capital — Transactions Platform

A FastAPI + React application that ingests Excel transaction files, runs FIFO
position math, detects business-rule violations (sell-before-buy, day-trading,
risk concentration, invalid values), and surfaces per-client analytics.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy ORM + Alembic · PostgreSQL 16 ·
React 18 + Vite + Ant Design. Packaged as a multi-stage Docker build.

**Where to read more:** [`docs/SPEC.md`](docs/SPEC.md) (full spec) ·
[`docs/decisions/`](docs/decisions/) (ADRs) · [`samples/`](samples/) (test files) ·
[`postman/`](postman/) (Postman collection).

---

## Setup

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Create the env file (defaults work as-is):
   ```bash
   cp .env.example .env
   ```
3. *(Optional — only if running outside Docker)* install local deps:
   ```bash
   pip install -e ".[dev]"
   cd frontend && npm install && cd ..
   ```

---

## How to run the backend

**Recommended — full stack in one command** (db + migrations + api):

```bash
docker compose up --build
```

- App + UI → http://localhost:8000/
- Swagger → http://localhost:8000/api/docs

**Local uvicorn** (DB still in Docker, hot-reload for backend code):

```bash
docker compose up db -d
docker compose run --rm migrate
uvicorn src.api.app:app --reload --port 8000
```

---

## How to run the frontend

The production bundle is built and served by FastAPI automatically when you
run `docker compose up`. For frontend-only iteration with hot-reload:

```bash
cd frontend
npm run dev
```

→ http://localhost:5173 (proxies `/api` to the backend on `:8000`).

---

## How to run tests

```bash
pytest tests/unit/           # unit tests — no DB required
pytest tests/integration/    # integration tests — needs DB: docker compose up db -d
pytest                       # full suite (what CI runs)
```
