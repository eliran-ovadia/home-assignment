# Implementation Plan — Lumina Capital Transactions Platform

**Status:** Approved — waiting for first branch to be opened.
**Date agreed:** 2026-05-10
**Approach:** Branch-per-phase. Each branch is opened by the user, implemented by Claude, reviewed by the user, and merged before the next branch opens.

---

## Overview

7 pull requests. Each has a clear, independently reviewable scope. PRs 2 and 3 can be developed in parallel if desired (they have no dependency on each other).

```
PR 1: Foundation ──────────────────────────────────────────────────────┐
PR 2: Database layer ────────────────────────────────────────────────┐ │
PR 3: Domain logic + ingestion + unit tests ─────────────────────┐  │ │
PR 4: API layer (depends on 2 + 3) ─────────────────────────────┐│  │ │
PR 5: Integration tests (depends on 4) ────────────────────────┐││  │ │
PR 6: Frontend (depends on 4) ─────────────────────────────────│││  │ │
PR 7: Docker + CI finalization (depends on 5 + 6) ─────────────┘┘┘──┘─┘
```

---

## PR 1 — `feat/foundation`

**Goal:** Wire up all the shared infrastructure that every other PR imports from. No business logic, no routes.

**Files:**
- `pyproject.toml` — add runtime deps: `asyncpg`, `openpyxl`, `python-multipart`, `sqlalchemy[asyncio]`
- `requirements.txt` — sync with pyproject
- `.env.example` — template with all required env vars and comments
- `src/core/config.py` — pydantic-settings model for non-sensitive config (host, port, db name, log level)
- `src/core/database.py` — async SQLAlchemy engine factory, `init_db()`, `close_db()`, `get_session()` generator
- `alembic.ini` — Alembic config pointing `script_location = migrations`

**Definition of done:** `from src.core.config import settings` and `from src.core.database import get_session` both import cleanly. Ruff and ty pass.

---

## PR 2 — `feat/database-layer`

**Goal:** All database code — schema, migration, and repository functions. No routes, no business logic.

**Files:**
- `src/db/__init__.py`
- `src/db/models.py` — 6 ORM mapped classes: `User`, `Upload`, `Transaction`, `Position`, `Violation`, `ClientAnalytic`
- `migrations/env.py` — async Alembic env (uses asyncpg)
- `migrations/script.py.mako` — Alembic migration template
- `migrations/versions/0001_initial_schema.py` — all 6 tables with indexes and FK constraints
- `src/db/repositories/__init__.py`
- `src/db/repositories/users.py` — `get_or_create_by_token(session, token) → User`
- `src/db/repositories/uploads.py` — insert, get_all_by_user, get_by_id, set_active, get_active_for_user
- `src/db/repositories/transactions.py` — bulk_insert, get_by_upload
- `src/db/repositories/positions.py` — bulk_insert, get_by_upload_and_client, get_all_by_upload
- `src/db/repositories/violations.py` — bulk_insert, get_by_upload (filterable by client/type)
- `src/db/repositories/client_analytics.py` — bulk_insert, get_by_upload
- `src/db/repositories/analytics.py` — live SQL: top ISINs, ISIN concentration, most traded day, top P&L, win rates, client summary

**Definition of done:** `alembic upgrade head` creates all 6 tables. All repository functions are importable and type-clean.

---

## PR 3 — `feat/domain-and-ingestion`

**Goal:** All pure Python business logic and unit tests. Zero DB imports. Zero HTTP imports.

**Files:**
- `src/domain/__init__.py`
- `src/domain/models.py` — dataclasses: `RawRow`, `CompletedTrade`, `Position`, `ViolationRecord`, `FIFOResult`, `ClientAnalyticsData`, `ProcessingResult`, `RowError`
- `src/ingestion/__init__.py`
- `src/ingestion/parser.py` — openpyxl reader, streaming (read_only=True, data_only=True), validates headers
- `src/ingestion/validator.py` — normalise + type-check each row, returns `(valid_rows, errors)`
- `src/domain/fifo.py` — FIFO engine: deque-based lot matching, realized P&L, completed trades, SELL_BEFORE_BUY violations
- `src/domain/violations.py` — day trading detector (>3 pairs in 24h) + risk concentration detector (ISIN >50%)
- `src/domain/analytics.py` — portfolio value simulation (volatility), holding time, win rate
- `tests/__init__.py`
- `tests/unit/__init__.py`
- `tests/unit/test_fifo.py` — 9 test cases: basic buy/sell, FIFO ordering, partial sell, oversell, empty queue, unrealized P&L, multi-client independence, completed trades recorded
- `tests/unit/test_violations.py` — day trading threshold tests (4 trips flagged, 3 ok, outside window ok, one per client) + risk concentration tests
- `tests/unit/test_validation.py` — invalid qty/price/action/type + valid passthrough + row number in error

**Definition of done:** `pytest tests/unit/` passes green with no warnings.

---

## PR 4 — `feat/api-layer`

**Goal:** The fully runnable FastAPI backend. After this PR, all endpoints work and can be tested with curl or Swagger.

**Files:**
- `src/api/__init__.py`
- `src/api/schemas.py` — all Pydantic response models (UploadResponse, ClientSummary, PositionResponse, ViolationResponse, AnalyticsResponse, UploadHistoryItem, etc.)
- `src/api/deps.py` — `get_current_user`: resolve X-Session-Token header → User row (create on first sight)
- `src/api/app.py` — FastAPI factory, lifespan (init DB engine, close on shutdown), register all routers, mount React static files
- `src/api/routes/__init__.py`
- `src/api/routes/upload.py` — `POST /api/v1/upload-transactions`: advisory lock → parse → validate → FIFO → analytics → atomic DB write
- `src/api/routes/clients.py` — `GET /api/v1/clients`, `GET /api/v1/clients/{id}/positions`
- `src/api/routes/violations.py` — `GET /api/v1/violations` (client_id, violation_type filters)
- `src/api/routes/analytics.py` — `GET /api/v1/analytics`
- `src/api/routes/uploads.py` — `GET /api/v1/uploads`, `POST /api/v1/uploads/{id}/activate`

**Definition of done:** `uvicorn src.api.app:app --reload` starts. Upload a sample xlsx via Swagger UI at `localhost:8000/api/docs`. All endpoints return expected responses.

---

## PR 5 — `feat/integration-tests`

**Goal:** Prove the backend works end-to-end with a real PostgreSQL database.

**Files:**
- `tests/conftest.py` — pytest fixtures: test DB session (creates schema, tears down after each test), FastAPI TestClient wired to test DB, `make_xlsx()` helper that builds a valid `.xlsx` in memory
- `tests/integration/__init__.py`
- `tests/integration/test_api.py` — all scenarios from SPEC §7:
  - Upload without token → 400
  - Valid upload → 200, correct summary, data in DB
  - Invalid row → 422, nothing written
  - Missing columns → 422
  - Wrong file type → 422
  - GET /clients after upload → correct list
  - GET /clients/{id}/positions → correct positions with P&L
  - GET /violations → SELL_BEFORE_BUY present
  - GET /analytics → all 4 sections present
  - GET /uploads → only current user's uploads
  - Second upload becomes active
  - POST /uploads/{id}/activate → switches data instantly
  - Two users → each sees only their own data

Also updates:
- `.github/workflows/ci.yml` — add PostgreSQL service, run full `pytest` (not just `tests/unit/`)

**Definition of done:** `make test` passes green at ≥80% coverage.

---

## PR 6 — `feat/frontend`

**Goal:** The complete React frontend. After this PR, opening `localhost:5173` gives a fully functional UI.

**Files:**
- `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/index.html`
- `frontend/src/types.ts` — TypeScript interfaces matching all API response shapes
- `frontend/src/api/client.ts` — all fetch() calls, UUID session token management (generated on first load, stored in localStorage, injected on every request)
- `frontend/src/main.tsx` — React entry point
- `frontend/src/App.tsx` — layout, dark/light mode toggle, refresh key state management
- `frontend/src/components/UploadSection.tsx` — drag-and-drop .xlsx upload, loading spinner, success summary, 422 error table
- `frontend/src/components/UploadHistory.tsx` — table of past uploads with Load button (instant switch)
- `frontend/src/components/ClientSelector.tsx` — Ant Design Select populated from GET /clients
- `frontend/src/components/PositionsTable.tsx` — P&L color-coded green/red, financial numbers right-aligned
- `frontend/src/components/ViolationsTable.tsx` — type badge, severity, client/type filter selects
- `frontend/src/components/AnalyticsPanel.tsx` — 2×2 grid: top ISINs, holding time, volatile client, ISIN concentration + bonus cards
- Updates `.gitignore` — exclude `frontend/node_modules/` and `frontend/dist/`

**Definition of done:** `cd frontend && npm run dev` starts. Upload a sample file. All 6 components render with real data. Dark mode toggle works.

---

## PR 7 — `feat/docker-finalize`

**Goal:** `docker compose up --build` works on a clean machine in one command.

**Files:**
- `Dockerfile` — 3-stage build: Stage 1 (Node 20 Alpine → `npm run build`), Stage 2 (Python 3.12 slim → install deps), Stage 3 (lean runtime → copy venv + src + migrations + frontend/dist)
- `docker-compose.yml` — verify app service (depends_on with healthcheck), db service (postgres:16-alpine), persistent volume
- `README.md` — final check: all instructions are literally copy-pasteable, Swagger link confirmed

**Definition of done:** `DB_PASSWORD=test docker compose up --build` starts cleanly. `localhost:8000` serves the React UI. `localhost:8000/api/docs` shows Swagger.

---

## Progress Tracker

| PR | Branch | Status | Merged |
|----|--------|--------|--------|
| 1 | `feat/foundation` | ✅ Done | 2026-05-10 |
| 2 | `feat/database-layer` | ⬜ Not started | — |
| 3 | `feat/domain-and-ingestion` | ⬜ Not started | — |
| 4 | `feat/api-layer` | ⬜ Not started | — |
| 5 | `feat/integration-tests` | ⬜ Not started | — |
| 6 | `feat/frontend` | ⬜ Not started | — |
| 7 | `feat/docker-finalize` | ⬜ Not started | — |
