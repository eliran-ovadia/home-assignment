# Assignment Checklist — Lumina Capital Transactions Platform

Derived from `assignment/Final_Assignment.md`. Each item is marked against the current specification in `docs/SPEC.md`.

Legend (Spec): ✅ Covered in spec | ⚠️ Gap or concern | ❌ Missing
Legend (Impl): ⬜ Not started | 🔄 In progress | ✅ Done

---

## Part A — Data Ingestion & Validation

| # | Requirement | Spec | Impl | Notes |
|---|-------------|------|------|-------|
| A1 | Load and parse the Excel file | ✅ | ⬜ | `ingestion/parser.py` — openpyxl `read_only=True` streaming |
| A2 | Normalize data | ✅ | ⬜ | Whitespace strip, title-case action, UTC timestamp normalisation |
| A3 | Validate: Quantity > 0 | ✅ | ⬜ | `ingestion/validator.py` — full row validation before any DB write |
| A4 | Validate: Price > 0 | ✅ | ⬜ | Same |
| A5 | Validate: Action must be Buy or Sell | ✅ | ⬜ | Same |

---

## Part B — Backend API

| # | Requirement | Spec | Impl | Notes |
|---|-------------|------|------|-------|
| B1 | POST /upload-transactions | ✅ | ⬜ | Full spec including 200, 409, 422, 500 responses |
| B2 | GET /clients | ✅ | ⬜ | Returns client list with transaction/position/violation counts |
| B3 | GET /clients/{client_id}/positions | ✅ | ⬜ | Returns FIFO-computed positions per ISIN |
| B4 | GET /violations | ✅ | ⬜ | Filterable by client_id and violation_type |
| B5 | GET /analytics | ✅ | ⬜ | All 4 required analytics + bonus section |
| — | GET /api/v1/uploads | ✅ | ⬜ | Beyond requirement — upload history per user |
| — | POST /api/v1/uploads/{id}/activate | ✅ | ⬜ | Beyond requirement — instant past-upload reload |

---

## Part C — Business Logic

| # | Requirement | Spec | Impl | Notes |
|---|-------------|------|------|-------|
| C1 | FIFO cost calculation | ✅ | ⬜ | Full pseudocode in SPEC §5.2 — deque-based lot matching |
| C2 | Realized P&L | ✅ | ⬜ | Computed per (client, ISIN) during FIFO pass |
| C3 | Unrealized P&L | ✅ | ⬜ | Last price per ISIN × remaining quantity |
| C4 | Positions per ISIN | ✅ | ⬜ | One position row per (upload, client, ISIN) |

---

## Part D — Rule Violations

| # | Requirement | Spec | Impl | Notes |
|---|-------------|------|------|-------|
| D1 | Day Trading (>3 pairs in 24h → flag) | ✅ | ⬜ | SPEC §5.3 — per-client 24h sliding window |
| D2 | Risk Concentration (ISIN > 50% → warning) | ✅ | ⬜ | SPEC §5.4 — market value weighting |
| D3 | Sell Before Buy → ERROR | ✅ | ⬜ | FIFO engine emits violation, skips match, no short position |
| D4 | Invalid Values (price/qty ≤ 0 → ERROR) | ✅ | ⬜ | Caught in validation pass — entire upload rejected |

---

## Part E — Storage

| # | Requirement | Spec | Impl | Notes |
|---|-------------|------|------|-------|
| E1 | Persist data in a database | ✅ | ⬜ | PostgreSQL (exceeds SQLite minimum) |
| E2 | Use an ORM | ✅ | ⬜ | SQLAlchemy ORM — ADR 010 |
| E3 | `transactions` table | ✅ | ⬜ | Full schema in SPEC §3 |
| E4 | `positions` table | ✅ | ⬜ | Full schema in SPEC §3 |
| E5 | `violations` table | ✅ | ⬜ | Full schema in SPEC §3 |
| E6 | Data survives restart | ✅ | ⬜ | Stored in PostgreSQL, not in memory |
| E7 | API reads from database | ✅ | ⬜ | All routes use repositories, no in-memory state |
| — | Separation of raw vs computed (BONUS) | ✅ | ⬜ | `transactions` = raw; `positions`, `client_analytics` = computed |
| — | Basic indexing (BONUS) | ✅ | ⬜ | Indexes defined on all FK and filter columns in SPEC §3 |

---

## Part F — Analytics

| # | Requirement | Spec | Impl | Notes |
|---|-------------|------|------|-------|
| F1 | Top 3 most traded ISINs | ✅ | ⬜ | GROUP BY isin ORDER BY COUNT DESC LIMIT 3 |
| F2 | Average holding time per client | ✅ | ⬜ | From CompletedTrade records collected during FIFO |
| F3 | Most volatile client (largest value range) | ✅ | ⬜ | Simulated portfolio value over time, stored in client_analytics |
| F4 | ISIN concentration (ISINs in >70% of clients) | ✅ | ⬜ | Computed at query time from positions |
| F5 | Concentration includes client list | ✅ | ⬜ | Response includes `clients: [...]` array |
| — | Additional insights (BONUS) | ✅ | ⬜ | Top realized P&L client, win rate per client, most traded day |
| — | Caching/optimization (BONUS) | ✅ | ⬜ | `client_analytics` table precomputes heavy values at upload time |

---

## Part G — Frontend

| # | Requirement | Spec | Impl | Notes |
|---|-------------|------|------|-------|
| G1 | File upload button | ✅ | ⬜ | Ant Design Upload drag-and-drop in UploadSection |
| G2 | Positions table per client | ✅ | ⬜ | PositionsTable with ClientSelector |
| G3 | Violations table | ✅ | ⬜ | ViolationsTable with type/client filters |
| G4 | Analytics section | ✅ | ⬜ | AnalyticsPanel — 2×2 grid with all 4 analytics |
| G5 | Frontend communicates via HTTP | ✅ | ⬜ | All calls through `frontend/src/api/client.ts` |
| G6 | Data not hardcoded | ✅ | ⬜ | All data fetched from API |
| — | Loading indicators (BONUS) | ✅ | ⬜ | Ant Design Spin during upload and data fetch |
| — | Error handling (BONUS) | ✅ | ⬜ | 422 rejection table with row-level error details |
| — | Basic styling (BONUS) | ✅ | ⬜ | Ant Design — light/dark mode toggle, P&L color coding |

---

## Part H — Testing

| # | Requirement | Spec | Impl | Notes |
|---|-------------|------|------|-------|
| H1 | At least 1 API endpoint test | ✅ | ⬜ | `tests/integration/test_api.py` — multiple endpoint tests |
| H2 | At least 2 business logic tests | ✅ | ⬜ | `tests/unit/test_fifo.py`, `test_violations.py`, `test_validation.py` |
| H3 | Tests runnable via simple command | ✅ | ⬜ | `make test` — single command, coverage report included |
| — | Edge cases (BONUS) | ✅ | ⬜ | Partial sells, oversells, empty queues, wrong-column Excel |
| — | Improved coverage (BONUS) | ✅ | ⬜ | 80% coverage threshold enforced via `--cov-fail-under=80` |

---

## Submission Requirements

| # | Requirement | Spec | Impl | Notes |
|---|-------------|------|------|-------|
| S1 | Full source code | ✅ | ⬜ | — |
| S2 | requirements.txt | ✅ | ✅ | File exists with all runtime deps |
| S3 | README.md — project overview | ✅ | ✅ | Done |
| S4 | README.md — setup instructions | ✅ | ✅ | `make install`, `.env.example` → `.env` |
| S5 | README.md — how to run backend | ✅ | ✅ | `uvicorn` command documented |
| S6 | README.md — how to run frontend | ✅ | ✅ | `npm run dev` documented |
| S7 | README.md — how to run tests | ✅ | ✅ | `make test` documented |
| S8 | AI_USAGE.md | ✅ | 🔄 | Phase 1 fully documented; Phase 2 filled in as we implement |
| — | Dockerfile / docker-compose (BONUS) | ✅ | ⬜ | Dockerfile exists but not finalized (PR 7) |
| — | Example API requests (BONUS) | ✅ | ✅ | curl examples + Swagger link in README |

---

## Identified Gaps

| Gap | Severity | Fix | Fixed? |
|-----|----------|-----|--------|
| `requirements.txt` not generated | Medium | File now exists with runtime deps | ✅ |
| Example API requests not in README | Low | curl examples added to README | ✅ |
| `/api/docs` Swagger URL not mentioned | Low | Added to README API docs section | ✅ |
