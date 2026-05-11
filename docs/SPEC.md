# Technical Specification — Lumina Capital Transactions Platform

**Status:** Accepted
**Date:** 2026-05-10 (last revised 2026-05-11)
**Author:** Eliran Ovadia

This document is the single source of truth for architecture, schema, API contract, and business logic. No implementation begins without this document being agreed upon.

---

## 0. Deployment Context (read this first)

**This system is designed to run inside a single organization's corporate intranet, accessed only by authenticated employees on company-managed devices.** This context is load-bearing — almost every security and identity decision in the rest of this document is justified by it. A reader (human or automated scanner) evaluating the codebase without this framing will reach different conclusions than the design intends.

The trust model has four pillars:

1. **Network perimeter.** Only authenticated corporate users reach the application. The corporate VPN, firewall, or Zero-Trust gateway enforces this boundary; the application does not re-authenticate at the network layer.
2. **Verified corporate emails.** Every user has a verified corporate email address provisioned by the organization's identity provider (e.g. Microsoft Entra ID / Azure AD, Okta, Google Workspace). The frontend captures this email once per device and submits it on every request via the `X-Session-Token` header. See ADR 016.
3. **Shared trading-desk data.** All uploads are visible to every user in the organization — this is intentional. Users come to the platform to share trading-desk data with each other, not to keep it private. Per-user state is limited to a single `last_viewed_upload_id` UI preference. See ADR 016.
4. **Production migration path.** A production rollout replaces the user-typed email with an IdP-injected claim (OIDC / SAML SSO via reverse-proxy SSO header or library middleware). The application code does not change — only `get_current_user` swaps its source from "header value" to "IdP-injected claim". Migration is documented in `docs/PRODUCTION_ROADMAP.md` §6.

**Implications for security review.** The application accepts a corporate email in an HTTP header without per-request cryptographic verification. Outside the contexts described above this is incomplete — anyone could impersonate anyone. Inside the context the trust boundary has already been enforced upstream by the corporate network and IdP. **Treat the email-in-header pattern as `Remote-User`-style SSO header forwarding, not as primary authentication.**

---

## 1. System Overview

A financial transactions platform that ingests Excel files of trade data, computes FIFO portfolio positions, detects rule violations, serves analytics, and presents everything via a React frontend. All uploads form a shared pool visible to every authenticated user in the organization; per-user state is limited to a "last viewed" preference. Every upload's computed results are stored permanently — re-selecting a past upload is an instant lookup, not a pipeline re-run.

### Data Flow

```
Every request includes X-Session-Token: <corporate-email>
        │
        ▼
get_current_user() resolves email → users row
(creates users row on first sight of a new email)
        │
        ▼
POST /api/v1/upload-transactions
        │
        ├─► Validate file: size ≤ 10MB, extension + MIME type is xlsx
        ├─► Stream-parse entire file (openpyxl read_only=True, data_only=True)
        ├─► Validate every row (types, required fields, domain values)
        │       └─► Any invalid rows → return 422 with error list
        │                              (nothing written to DB)
        │
        ├─► BEGIN TRANSACTION
        ├─► INSERT into uploads (filename, file_content, row_count ...) → upload_id
        ├─► UPDATE users SET last_viewed_upload_id = <new upload_id> WHERE id = me
        ├─► Bulk insert transactions (linked to this upload_id)
        │
        ├─► FIFO Engine (runs on THIS upload's transactions only, per client+ISIN)
        │       ├─► Compute realized P&L
        │       ├─► Detect SELL_BEFORE_BUY violations (log + skip, no short position)
        │       └─► Collect completed trades (for holding time analytics)
        │
        ├─► Compute unrealized P&L (last known price per ISIN across all clients in file)
        ├─► Bulk insert positions (with upload_id)
        ├─► Simulate portfolio value over time per client (for volatility analytics)
        ├─► Compute per-client analytics (avg_holding_days, value_range)
        ├─► Bulk insert client_analytics (with upload_id)
        ├─► Detect DAY_TRADING violations
        ├─► Detect RISK_CONCENTRATION violations
        ├─► Bulk insert all violations (with upload_id)
        ├─► COMMIT
        └─► Return summary

User queries UI (all requests include X-Session-Token)
        ├─► Resolve users row from email
        ├─► Read users.last_viewed_upload_id (the user's chosen view)
        └─► All reads filter by this upload_id:
            ├─► GET /api/v1/clients              → aggregate from transactions WHERE upload_id=?
            ├─► GET /api/v1/clients/{id}/positions → positions WHERE upload_id=?
            ├─► GET /api/v1/violations            → violations WHERE upload_id=?
            ├─► GET /api/v1/analytics             → precomputed + live queries WHERE upload_id=?
            └─► GET /api/v1/uploads              → every upload in the system (shared pool)

User switches to a different upload (instant — results already in DB)
        └─► PUT /api/v1/users/me/last-viewed   body: {"upload_id": <n>}
                ├─► UPDATE users SET last_viewed_upload_id = ? WHERE id = me
                └─► Return upload summary (no pipeline re-run)
```

### Key Architectural Decisions

| Concern | Decision | ADR |
|---------|----------|-----|
| Deployment context | Corporate intranet, behind IdP-controlled perimeter | §0 above, ADR 016 |
| Upload behaviour | Per-upload result storage; switching uploads is a per-user preference flip | ADR 014 |
| Identity | Corporate-email forwarded in `X-Session-Token` header (Remote-User-style) | ADR 016 |
| Data visibility | Shared upload pool — all users see all uploads | ADR 016 |
| Upload validation | Reject entire file if any row fails type/format check | ADR 011 |
| Upload response | Synchronous (blocking HTTP); client waits for full result | ADR 013 |
| Frontend delivery | React (Ant Design) built into FastAPI static files | ADR 008 |
| Database | PostgreSQL | — |
| ORM | SQLAlchemy ORM with mapped classes | ADR 010 |
| Unrealized P&L price | Last transaction price per ISIN in the uploaded file | — |
| API prefix | `/api/v1/` on all routes | — |
| Concurrency | Independent transactions per upload; no application-level locking | ADR 016 |
| Configuration & secrets | `pydantic-settings` reads `.env` locally and OS env vars in CI/Docker; DB password held in `SecretStr` | — |
| Async model | `async def` routes + `AsyncSession`; CPU-bound sections use `asyncio.to_thread()` | — |

---

## 2. Folder & File Structure

```
home-assignment/
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # pydantic-settings: DB host/port/name/user, password (SecretStr), log level
│   │   └── database.py         # SQLAlchemy engine factory, AsyncSession, get_session()
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI factory, lifespan, static files mount at "/"
│   │   ├── deps.py             # Depends: get_session, get_current_user
│   │   ├── schemas.py          # Pydantic response models for all endpoints
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── upload.py       # POST /api/v1/upload-transactions
│   │       ├── clients.py      # GET /api/v1/clients, GET /api/v1/clients/{id}/positions
│   │       ├── violations.py   # GET /api/v1/violations
│   │       ├── analytics.py    # GET /api/v1/analytics
│   │       └── uploads.py      # GET /api/v1/uploads, PUT /api/v1/users/me/last-viewed
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py           # Pydantic domain models: RawRow, CompletedTrade, etc.
│   │   ├── fifo.py             # FIFO engine: positions, realized P&L, completed trades
│   │   ├── violations.py       # Day trading + risk concentration detectors
│   │   └── analytics.py        # Portfolio value simulation, holding time, concentration
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── parser.py           # openpyxl read_only+data_only: .xlsx bytes → list[RawRow]
│   │   └── validator.py        # Row-level validation → (valid_rows, invalid_rows)
│   └── db/
│       ├── __init__.py
│       ├── models.py           # SQLAlchemy ORM mapped classes (all 6 tables)
│       └── repositories/
│           ├── __init__.py
│           ├── users.py        # get_or_create_by_token
│           ├── transactions.py # bulk_insert, get_by_upload
│           ├── positions.py    # bulk_insert, get_by_upload, get_by_client
│           ├── violations.py   # bulk_insert, get_by_upload, get_by_client_and_type
│           ├── analytics.py    # get_top_isins, get_isin_concentration (by upload_id)
│           ├── client_analytics.py  # bulk_insert, get_by_upload
│           └── uploads.py      # insert, get_all_by_user, get_by_id, set_active
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts          # dev proxy: /api → localhost:8000
│   └── src/
│       ├── main.tsx
│       ├── App.tsx             # layout, light/dark mode toggle, session token init
│       ├── types.ts            # TypeScript interfaces matching all API response shapes
│       ├── api/
│       │   └── client.ts       # All fetch() calls — injects X-Session-Token on every request
│       └── components/
│           ├── UploadSection.tsx    # Drag-and-drop file input, upload button, status/error
│           ├── UploadHistory.tsx    # Table of past uploads with "Load" button per row
│           ├── ClientSelector.tsx   # Ant Design Select populated from GET /clients
│           ├── PositionsTable.tsx   # Ant Design Table: ISIN, Qty, Avg Cost, P&L columns
│           ├── ViolationsTable.tsx  # Ant Design Table: Type badge, Severity, Description
│           └── AnalyticsPanel.tsx   # Four analytics sub-sections in a 2×2 grid
├── migrations/
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│       └── 0001_initial_schema.py  # All 6 tables
├── tests/
│   ├── conftest.py             # fixtures: test DB session, FastAPI TestClient, test user
│   ├── unit/
│   │   ├── test_fifo.py
│   │   ├── test_violations.py
│   │   └── test_validation.py
│   └── integration/
│       └── test_api.py
├── docs/
│   ├── SPEC.md                 # this file
│   └── decisions/              # ADRs 001–015
├── assignment/
├── .env.example
├── AI_USAGE.md
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── CLAUDE.md
└── README.md
```

---

## 3. Database Schema

PostgreSQL. SQLAlchemy ORM (ADR 010). Results for every upload are stored permanently under that upload's `id`. Nothing is ever truncated. Uploads form a shared pool (ADR 016); per-user state is limited to a `last_viewed_upload_id` preference on `users`.

### `users`

One row per known corporate email (ADR 016).

| Column | Type | Constraints |
|--------|------|-------------|
| id | SERIAL | PRIMARY KEY |
| email | TEXT | NOT NULL, UNIQUE |
| last_viewed_upload_id | INT | NULL, FK → uploads.id ON DELETE SET NULL |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() |

Index: implicit unique index on `(email)` — hit on every request when resolving the session header.

### `uploads`

File history. Never deleted. One row per uploaded file — visible to every user in the organization (ADR 016).

| Column | Type | Constraints |
|--------|------|-------------|
| id | SERIAL | PRIMARY KEY |
| filename | TEXT | NOT NULL |
| file_content | BYTEA | NOT NULL |
| row_count | INT | NOT NULL |
| violation_count | INT | NOT NULL |
| uploaded_at | TIMESTAMP | NOT NULL, DEFAULT NOW() |

No `user_id` and no `is_active` column. Every upload is visible to every user; "which upload am I looking at right now" is a per-user preference stored on `users.last_viewed_upload_id`.

### `transactions`

Raw validated rows from the uploaded file. Linked to their upload; never modified after insert.

| Column | Type | Constraints |
|--------|------|-------------|
| id | SERIAL | PRIMARY KEY |
| upload_id | INT | NOT NULL, FK → uploads.id ON DELETE CASCADE |
| transaction_id | TEXT | NOT NULL |
| client_id | TEXT | NOT NULL |
| isin | TEXT | NOT NULL |
| action | TEXT | NOT NULL, CHECK IN ('Buy', 'Sell') |
| quantity | NUMERIC(18,6) | NOT NULL |
| price | NUMERIC(18,6) | NOT NULL |
| timestamp | TIMESTAMP | NOT NULL |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() |

Indexes: `(upload_id)`, `(upload_id, client_id, isin, timestamp)`.
Note: `transaction_id` is unique within an upload but not globally (same file can be re-uploaded).

### `positions`

One row per (upload, client, ISIN). Computed by the FIFO engine. Immutable after insert.

| Column | Type | Constraints |
|--------|------|-------------|
| id | SERIAL | PRIMARY KEY |
| upload_id | INT | NOT NULL, FK → uploads.id ON DELETE CASCADE |
| client_id | TEXT | NOT NULL |
| isin | TEXT | NOT NULL |
| quantity | NUMERIC(18,6) | NOT NULL, DEFAULT 0 |
| avg_cost | NUMERIC(18,6) | NOT NULL, DEFAULT 0 |
| realized_pnl | NUMERIC(18,6) | NOT NULL, DEFAULT 0 |
| unrealized_pnl | NUMERIC(18,6) | NOT NULL, DEFAULT 0 |
| last_price | NUMERIC(18,6) | NOT NULL, DEFAULT 0 |

Constraint: UNIQUE `(upload_id, client_id, isin)`. Index: `(upload_id, client_id)`.

### `violations`

All detected violations for a given upload. Immutable after insert.

| Column | Type | Constraints |
|--------|------|-------------|
| id | SERIAL | PRIMARY KEY |
| upload_id | INT | NOT NULL, FK → uploads.id ON DELETE CASCADE |
| transaction_id | TEXT | NULLABLE |
| client_id | TEXT | NOT NULL |
| isin | TEXT | NULLABLE |
| violation_type | TEXT | NOT NULL |
| severity | TEXT | NOT NULL |
| description | TEXT | NOT NULL |
| detected_at | TIMESTAMP | NOT NULL, DEFAULT NOW() |

Indexes: `(upload_id, client_id)`, `(upload_id, violation_type)`.

**Violation matrix:**

| violation_type | severity | Transaction inserted? | Processing continues? |
|---|---|---|---|
| INVALID_VALUE | ERROR | No | No — entire upload rejected (ADR 011) |
| SELL_BEFORE_BUY | ERROR | Yes | Yes — FIFO match skipped, no short position |
| DAY_TRADING | FLAG | Yes | Yes |
| RISK_CONCENTRATION | WARNING | Yes | Yes |

### `client_analytics`

Precomputed per-client values. One row per (upload, client).

| Column | Type | Constraints |
|--------|------|-------------|
| id | SERIAL | PRIMARY KEY |
| upload_id | INT | NOT NULL, FK → uploads.id ON DELETE CASCADE |
| client_id | TEXT | NOT NULL |
| avg_holding_days | NUMERIC(10,4) | NULLABLE (null = no completed trades) |
| max_portfolio_value | NUMERIC(18,6) | NOT NULL |
| min_portfolio_value | NUMERIC(18,6) | NOT NULL |
| value_range | NUMERIC(18,6) | NOT NULL |
| winning_trades | INT | NULLABLE (null = no completed trades) |
| total_trades | INT | NULLABLE (null = no completed trades) |

Constraint: UNIQUE `(upload_id, client_id)`. Index: `(upload_id)`.

`winning_trades` / `total_trades` are populated by the FIFO engine to support the bonus win-rate analytic. `win_rate` itself is derived in the API response (winning / total).

### Insert Order (per upload)

1. `uploads` (get upload_id)
2. `transactions` (reference upload_id)
3. `positions` (reference upload_id)
4. `client_analytics` (reference upload_id)
5. `violations` (reference upload_id)

All inserts happen inside a **single database transaction**. If any step fails, the entire upload rolls back and the DB is unchanged (the uploads row is also rolled back).

---

## 4. API Contract

Base path: `/api/v1/`. All responses: `application/json`. All response shapes are defined as Pydantic models in `src/api/schemas.py`. Every request must include `X-Session-Token: <corporate-email>` — missing or malformed value returns `400 Bad Request`. The email is validated as a `pydantic.EmailStr` at the API boundary; see §0 and ADR 016 for the trust model.

### POST `/api/v1/upload-transactions`

**Request:** `multipart/form-data`, field `file` (`.xlsx`, max 10MB)

**Response 200** — all rows valid, successfully processed:
```json
{
  "upload_id": 3,
  "status": "success",
  "summary": {
    "transactions_loaded": 150,
    "positions_computed": 45,
    "violations_detected": 7
  }
}
```

**Response 422** — file has invalid rows (nothing was saved):
```json
{
  "detail": "Upload rejected: file contains invalid rows",
  "rejected_rows": [
    {
      "row_number": 5,
      "transaction_id": "TXN005",
      "column": "quantity",
      "reason": "Expected a positive number, got: 'abc'"
    }
  ]
}
```

**Response 422** — file is not `.xlsx`, is empty, or has wrong column headers.
**Response 500** — unexpected processing error.

---

### GET `/api/v1/clients`

Returns all distinct clients in the active upload.

**Response 200:**
```json
[
  {
    "client_id": "C001",
    "transaction_count": 25,
    "position_count": 5,
    "violation_count": 2
  }
]
```

---

### GET `/api/v1/clients/{client_id}/positions`

**Response 200:**
```json
[
  {
    "isin": "US0378331005",
    "quantity": 100.0,
    "avg_cost": 150.25,
    "realized_pnl": 500.00,
    "unrealized_pnl": -200.00,
    "last_price": 148.25
  }
]
```

**Response 404:** `{"detail": "Client C001 not found in active upload"}`

---

### GET `/api/v1/violations`

**Query params:** `client_id` (optional), `violation_type` (optional)

**Response 200:**
```json
[
  {
    "id": 1,
    "transaction_id": "TXN042",
    "client_id": "C001",
    "isin": "US0378331005",
    "violation_type": "SELL_BEFORE_BUY",
    "severity": "ERROR",
    "description": "Client C001 attempted to sell 50 units of US0378331005 with no open position",
    "detected_at": "2026-05-10T10:30:00"
  }
]
```

---

### GET `/api/v1/analytics`

All analytics computed from the active upload's data.

**Response 200:**
```json
{
  "top_traded_isins": [
    {"isin": "US0378331005", "transaction_count": 45},
    {"isin": "GB0002634946", "transaction_count": 30},
    {"isin": "DE0005140008", "transaction_count": 25}
  ],
  "avg_holding_time_per_client": [
    {"client_id": "C001", "avg_holding_days": 12.5},
    {"client_id": "C002", "avg_holding_days": null}
  ],
  "most_volatile_client": {
    "client_id": "C003",
    "max_portfolio_value": 150000.00,
    "min_portfolio_value": 50000.00,
    "value_range": 100000.00
  },
  "isin_concentration": [
    {
      "isin": "US0378331005",
      "client_count": 8,
      "total_clients": 10,
      "concentration_pct": 0.80,
      "clients": ["C001", "C002", "C003", "C004", "C005", "C006", "C007", "C008"]
    }
  ],
  "bonus": {
    "top_realized_pnl_client": {"client_id": "C001", "realized_pnl": 12500.00},
    "win_rate_per_client": [
      {"client_id": "C001", "win_rate": 0.67, "winning_trades": 4, "total_trades": 6}
    ],
    "most_traded_day": {"date": "2024-01-15", "transaction_count": 42}
  }
}
```

`isin_concentration`: only ISINs present in >70% of clients with open positions.
`avg_holding_days`: null for clients with no completed buy→sell trades.
`most_volatile_client`: null if no data has been uploaded.
`bonus`: omitted if no data.

---

### GET `/api/v1/uploads`

Returns every upload in the system (shared pool, ADR 016). The `is_last_viewed` flag is computed against the *current* user's `users.last_viewed_upload_id`.

**Response 200:**
```json
[
  {
    "id": 3,
    "filename": "transactions_january.xlsx",
    "row_count": 150,
    "violation_count": 7,
    "uploaded_at": "2026-05-10T10:00:00",
    "is_last_viewed": true
  },
  {
    "id": 2,
    "filename": "transactions_sample.xlsx",
    "row_count": 80,
    "violation_count": 2,
    "uploaded_at": "2026-05-10T09:30:00",
    "is_last_viewed": false
  }
]
```

---

### PUT `/api/v1/users/me/last-viewed`

Sets the current user's `last_viewed_upload_id` preference. The pipeline does not re-run — analytics for the selected upload are already in the DB.

**Request body:** `{"upload_id": 3}`

**Response 200:** the same summary shape as a successful `POST /upload-transactions` response, but computed against the newly-selected upload.
**Response 404:** the upload ID does not exist (FK constraint rejection).

---

## 5. Business Logic Specification

### 5.1 Validation (`ingestion/validator.py`)

Applied by streaming through the entire file before any DB write. If `invalid_rows` is non-empty → HTTP 422, nothing written.

| Rule | Condition | Error |
|------|-----------|-------|
| Positive quantity | `quantity > 0` | "Expected a positive number" |
| Positive price | `price > 0` | "Expected a positive number" |
| Valid action | `action in {'Buy', 'Sell'}` | "Expected 'Buy' or 'Sell'" |
| Numeric types | quantity and price must be numeric | "Expected a number, got: '{value}'" |
| Required fields | all 7 columns present and non-null | "Missing required field: {field}" |
| Expected columns | all 7 headers must exist | HTTP 422 before row iteration |

Expected columns: `ClientId`, `TransactionId`, `ISIN`, `Action`, `Quantity`, `Price`, `Timestamp`.

Normalisation applied before validation:
- Strip whitespace from all string fields
- `action` is title-cased (`buy` → `Buy`)
- `timestamp` parsed; if no timezone, treated as UTC

### 5.2 FIFO Engine (`domain/fifo.py`)

Input: all valid transactions for one `(client_id, isin)` pair **within the current upload**, sorted by `timestamp ASC`.
Output: one `Position` + a list of `CompletedTrade` tuples + any `SELL_BEFORE_BUY` violations.

```
lot_queue = deque()   # entries: {quantity, price, timestamp}
realized_pnl = 0.0
completed_trades = []

for tx in sorted_transactions:
    if tx.action == "Buy":
        lot_queue.append({qty: tx.quantity, price: tx.price, ts: tx.timestamp})

    elif tx.action == "Sell":
        if lot_queue is empty:
            emit SELL_BEFORE_BUY violation (full tx.quantity, no short position created)
            continue

        remaining_sell = tx.quantity
        while remaining_sell > 0 and lot_queue not empty:
            lot = lot_queue[0]
            matched = min(remaining_sell, lot.quantity)
            realized_pnl += matched * (tx.price - lot.price)
            completed_trades.append(CompletedTrade(
                buy_ts=lot.timestamp, sell_ts=tx.timestamp, quantity=matched
            ))
            lot.quantity -= matched
            remaining_sell -= matched
            if lot.quantity == 0:
                lot_queue.popleft()

        if remaining_sell > 0:
            emit SELL_BEFORE_BUY violation (remaining_sell units, no short position)

net_quantity = sum(lot.quantity for lot in lot_queue)
avg_cost = weighted_average(lot_queue) if net_quantity > 0 else 0.0
```

**Unrealized P&L:** after all positions computed, `last_price[isin]` = price of the most recent transaction for that ISIN across all clients in the file. `unrealized_pnl = net_quantity * (last_price - avg_cost)`.

### 5.3 Day Trading Detection (`domain/violations.py`)

**Rule:** Per client, more than 3 buy/sell pairs within any 24-hour window → `DAY_TRADING` (FLAG).

A **pair** is an ISIN that has *both* a Buy *and* a Sell within the window — this matches the industry meaning of a "day-trading pair". An anchor Buy whose window contains sells of *other* ISINs (with no Buy of those ISINs in the same window) does **not** count toward the pair total; those sells are typically `SELL_BEFORE_BUY` situations, not day-trading.

```
for each client:
    transactions_sorted = sort by timestamp
    for each Buy transaction t:
        window_end = t.timestamp + 24h
        buys_in_window  = { ISIN of every Buy  in [t.timestamp, window_end] }
        sells_in_window = { ISIN of every Sell in [t.timestamp, window_end] }
        pairs = buys_in_window ∩ sells_in_window
        if |pairs| > 3:
            emit DAY_TRADING violation
            break  # one violation per client
```

### 5.4 Risk Concentration Detection (`domain/violations.py`)

**Rule:** Per client, if a single ISIN's market value exceeds 50% of total portfolio → `RISK_CONCENTRATION` (WARNING).

```
for each client:
    total_value = sum(position.quantity * position.last_price)
    if total_value == 0: skip
    for each position:
        if (position.quantity * position.last_price) / total_value > 0.50:
            emit RISK_CONCENTRATION violation
```

### 5.5 Analytics (`domain/analytics.py`)

**Top 3 most traded ISINs**
SQL: `GROUP BY isin ORDER BY COUNT(*) DESC LIMIT 3` on `transactions WHERE upload_id = ?`.

**Average holding time per client**
From `CompletedTrade` records collected during FIFO:
`avg_holding_days = mean((sell_ts - buy_ts).days for all completed trades per client)`
Stored in `client_analytics.avg_holding_days` during upload processing.

**Most volatile client**
For each client, simulate portfolio value after every transaction (using last known price per ISIN at that timestamp). `value_range = max(values) - min(values)`. Client with highest `value_range` is returned. Stored in `client_analytics`.

**ISIN concentration**
Computed at query time from `positions WHERE upload_id = ?`:
`total_clients` = DISTINCT client count with any position.
ISINs where `DISTINCT client_count / total_clients > 0.70` → included with client list.

**Bonus analytics**

| Metric | Computation |
|--------|-------------|
| Top realized P&L client | `SELECT client_id, SUM(realized_pnl) FROM positions WHERE upload_id=? GROUP BY client_id ORDER BY SUM DESC LIMIT 1` |
| Win rate per client | % of CompletedTrades where sell_price > avg buy_price of that trade |
| Most traded day | `SELECT DATE(timestamp), COUNT(*) FROM transactions WHERE upload_id=? GROUP BY date ORDER BY COUNT DESC LIMIT 1` |

---

## 6. Frontend Component Tree

Library: **Ant Design**. Light/dark mode toggle in the top nav bar.

On first visit the user enters their corporate email into a small landing form. The email is stored in `localStorage` and injected into every `fetch()` call as the `X-Session-Token` header by `frontend/src/api/client.ts`. All API calls in `client.ts` — no `fetch()` calls anywhere else. A returning user on a fresh device types the same email and the backend auto-loads their `last_viewed_upload_id`.

```
App
├── TopNav
│   ├── "Lumina Capital" logo
│   └── Light/Dark mode toggle (Ant Design Switch)
│
├── UploadSection
│   ├── Ant Design Upload (drag-and-drop, accepts .xlsx)
│   ├── "Upload & Process" button
│   └── Status display:
│       ├── Idle: instruction text
│       ├── Loading: Ant Design Spin
│       ├── Success: summary (X transactions, Y violations)
│       └── Error (422): Ant Design Table of rejected rows
│
├── UploadHistory              ← GET /api/v1/uploads
│   Ant Design Table: Filename | Date | Rows | Violations | Status badge | "Load" button
│   "Load" → POST /api/v1/uploads/{id}/activate (instant, no spinner needed)
│
├── ClientSelector             ← GET /api/v1/clients
│   Ant Design Select dropdown (client_id options)
│
├── PositionsTable             ← GET /api/v1/clients/{id}/positions
│   Columns: ISIN | Quantity | Avg Cost | Realized P&L | Unrealized P&L | Last Price
│   P&L values: green (positive) / red (negative)
│
├── ViolationsTable            ← GET /api/v1/violations
│   Columns: Client | ISIN | Type (Ant Design Badge) | Severity | Description
│   Filters: client_id select, violation_type select
│
└── AnalyticsPanel             ← GET /api/v1/analytics
    ├── TopISINs: Ant Design Table (ISIN, transaction count)
    ├── HoldingTime: Ant Design Table (client, avg days)
    ├── MostVolatileClient: Ant Design Card (client ID, value range)
    └── ISINConcentration: Ant Design Table (ISIN, %, client list as tags)
```

---

## 7. Testing Plan

### Unit Tests (no DB required)

**test_fifo.py**
- Basic buy → sell: correct realized P&L
- Multiple lots: FIFO ordering (oldest lot consumed first)
- Partial sell spanning two lots
- Sell with empty queue → SELL_BEFORE_BUY violation emitted, no position change
- Oversell (sell more than held) → SELL_BEFORE_BUY for excess quantity
- Buy only (no sell) → open position, unrealized P&L only

**test_violations.py**
- 4 round-trips in 24h → DAY_TRADING flagged
- 3 round-trips in 24h → not flagged
- ISIN at 60% of portfolio → RISK_CONCENTRATION flagged
- ISIN at 40% → not flagged

**test_validation.py**
- `quantity = 0` → INVALID_VALUE, upload rejected
- `price = -5` → INVALID_VALUE, upload rejected
- `action = "HOLD"` → INVALID_VALUE, upload rejected
- String in quantity column → INVALID_VALUE, upload rejected
- Valid row → passes through unchanged

### Integration Tests (requires DB)

**test_api.py**
- Upload valid `.xlsx` without session token → 400
- Upload valid `.xlsx` with session token (= corporate email) → 200, correct summary, data in DB
- Upload `.xlsx` with one invalid row → 422, nothing written to DB
- Upload `.xlsx` with missing expected columns → 422 before row processing
- Upload non-xlsx file → 422
- `GET /clients` after upload → correct client list (for the user's `last_viewed_upload_id`)
- `GET /clients/{id}/positions` → correct positions
- `GET /violations` → violations list
- `GET /analytics` → all four required analytics sections present
- `GET /uploads` → returns every upload in the system (shared pool)
- Upload second file → user's `last_viewed_upload_id` updates to the new upload
- `PUT /users/me/last-viewed` with a past upload id → reads switch instantly
- Two users see the same uploads list — but each user's `last_viewed_upload_id` is independent
- Returning user (same email on a fresh device) sees their `last_viewed_upload_id` restored

---

## 8. Architecture Patterns

| Pattern | Where |
|---------|-------|
| **Layered Architecture** | `api/` → `domain/` → `db/` — dependencies only point downward |
| **Repository Pattern** | `db/repositories/` — all DB access behind named functions, no SQL in routes |
| **Dependency Injection** | FastAPI `Depends(get_session)`, `Depends(get_current_user)` — injected into routes, swappable in tests |
| **Service Layer** | `domain/` — pure business logic with no HTTP or DB imports |
| **Factory** | `src/api/app.py` — `create_app()` factory allows different configs in tests |

---

## 9. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| Malicious Excel macros | `openpyxl` with `data_only=True` — formulas and macros are never executed |
| Oversized file upload | 10MB limit enforced before file is opened |
| Wrong file type | Validate both file extension AND MIME type (Content-Type header) |
| Corrupt Excel file | Entire parse wrapped in try/except → 422 with clear message |
| SQL injection | SQLAlchemy ORM uses parameterised queries exclusively |
| Concurrent uploads | Each upload writes its own `upload_id` in an independent DB transaction — no shared rows are mutated, so no application-level lock is needed |
| Cross-user data leakage | All queries filter by upload_id owned by the current user. A user cannot request another user's upload_id without knowing it (and there is no endpoint that lists other users' uploads). |
| Sensitive data in logs | No transaction data or secrets logged; only counts and status codes |

---

## 10. Production Scaling Notes

These are documented for interview discussion — not implemented in the assignment.

| Concern | Assignment approach | Production path |
|---------|--------------------|----|
| Concurrent uploads | Independent transactions per upload, no lock | Celery + Redis queue: return job ID immediately, client polls |
| Large file parsing | openpyxl read_only streaming, 10MB limit | `python-calamine` (Rust-based, 10–100× faster) + 100MB limit |
| CPU-bound FIFO | Single-threaded via `asyncio.to_thread()` | `ProcessPoolExecutor` across (client, ISIN) pairs — see `PRODUCTION_ROADMAP.md` |
| DB growth | Rows accumulate per upload indefinitely | Retention policy: archive or delete uploads older than N days |
| Analytics latency | Precomputed on upload | Redis cache keyed by `upload_id`; invalidate on new upload |
| Identity | Corporate email in `X-Session-Token` (ADR 016) | OIDC/SAML SSO with IdP-injected claim. `get_current_user()` is the only code that changes. |
