# Architecture

Four diagrams describing the system as built. Every node and edge maps
directly to a file in the repository — nothing here is aspirational.

## Contents

1. [Component graph](#1-component-graph) — every module and how it depends on the others
2. [Upload pipeline sequence](#2-upload-pipeline-sequence) — the request-time flow through every layer
3. [Database schema](#3-database-schema) — tables, columns, foreign keys
4. [Runtime topology](#4-runtime-topology) — Docker stack and startup gating

---

## 1. Component graph

Layered architecture (`api → domain → db`). The `domain/` layer has zero
imports from `api/` or `db/`; this is the property that lets the FIFO
engine be unit-tested without a database or HTTP client.

```mermaid
flowchart TB
    classDef browser fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
    classDef frontend fill:#fff3e0,stroke:#f57c00,color:#e65100
    classDef api fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
    classDef ingestion fill:#fff9c4,stroke:#fbc02d,color:#f57f17
    classDef domain fill:#f3e5f5,stroke:#7b1fa2,color:#4a148c
    classDef db fill:#e0f2f1,stroke:#00796b,color:#004d40
    classDef core fill:#eceff1,stroke:#455a64,color:#263238
    classDef external fill:#fce4ec,stroke:#c2185b,color:#880e4f

    Browser([User's Browser]):::browser
    PG[(PostgreSQL 16<br/>asyncpg driver)]:::external

    subgraph FE["Frontend — React 18 + Vite + Ant Design 5 · built once, served as static files"]
        direction TB
        Main[main.tsx<br/>ReactDOM root]:::frontend
        App[App.tsx<br/>top-level layout · shared clients state · refreshKey · theme]:::frontend
        EmailGate[EmailGate.tsx]:::frontend
        UploadSection[UploadSection.tsx<br/>Ant Upload.Dragger]:::frontend
        UploadHistory[UploadHistory.tsx]:::frontend
        ClientSelector[ClientSelector.tsx<br/>presentational]:::frontend
        PositionsTable[PositionsTable.tsx]:::frontend
        ViolationsTable[ViolationsTable.tsx<br/>filters: type + client]:::frontend
        AnalyticsPanel[AnalyticsPanel.tsx<br/>4-section grid + bonus]:::frontend
        APIClient[api/client.ts<br/>fetch wrapper · injects X-Session-Token]:::frontend
        Types[types.ts<br/>response type defs]:::frontend
    end

    subgraph APIL["API Layer — src/api"]
        direction TB
        AppPy[app.py<br/>create_app · lifespan · CORS · static mount]:::api
        Deps[deps.py<br/>get_current_user · SessionDep · CurrentUserDep]:::api
        Schemas[schemas.py<br/>request + response Pydantic models]:::api
        UploadRoute[routes/upload.py<br/>POST /upload-transactions]:::api
        UploadsRoute[routes/uploads.py<br/>GET /uploads · PUT /users/me/last-viewed]:::api
        ClientsRoute[routes/clients.py<br/>GET /clients · GET /clients/:id/positions]:::api
        ViolationsRoute[routes/violations.py<br/>GET /violations]:::api
        AnalyticsRoute[routes/analytics.py<br/>GET /analytics]:::api
    end

    subgraph INGL["Ingestion — src/ingestion"]
        direction TB
        Parser[parser.py<br/>openpyxl read_only streaming<br/>header validation · row builder]:::ingestion
        Validator[validator.py<br/>structural validation only<br/>type · format · required-field]:::ingestion
    end

    subgraph DOML["Domain — src/domain · pure logic, no infra imports"]
        direction TB
        DomModels[models.py<br/>RawRow · ValidatedRow · Position<br/>ViolationRecord · CompletedTrade<br/>FIFOResult · ClientAnalyticsData<br/>+ severity & action constants]:::domain
        FIFO[fifo.py<br/>run_fifo · _PairFIFO · _compute_last_prices<br/>emits SELL_BEFORE_BUY]:::domain
        Violations[violations.py<br/>detect_invalid_values · detect_day_trading<br/>detect_risk_concentration]:::domain
        AnalyticsDom[analytics.py<br/>compute_client_analytics<br/>portfolio extremes · holding-days · win-rate]:::domain
    end

    subgraph DBL["Data Access — src/db"]
        direction TB
        ORM[models.py<br/>Upload · User · Transaction<br/>Position · Violation · ClientAnalytic<br/>SQLAlchemy 2.0 Mapped declarative]:::db
        RepUploads[repositories/uploads.py]:::db
        RepUsers[repositories/users.py<br/>get_or_create_by_email<br/>INSERT … ON CONFLICT DO NOTHING]:::db
        RepTransactions[repositories/transactions.py]:::db
        RepPositions[repositories/positions.py]:::db
        RepViolations[repositories/violations.py<br/>filters: type · client]:::db
        RepClientAnalytics[repositories/client_analytics.py]:::db
        RepAnalytics[repositories/analytics.py<br/>cross-table aggregates for /analytics]:::db
    end

    subgraph COREL["Cross-Cutting — src/core"]
        direction TB
        Config[config.py<br/>pydantic-settings · SecretStr password<br/>reads .env / env vars]:::core
        Database[database.py<br/>async_sessionmaker · get_session<br/>init_db · close_db lifespan hooks]:::core
    end

    Migrations[migrations/versions/<br/>0001_initial_schema.py<br/>Alembic offline-capable]:::core

    Browser -.HTTPS.-> Main
    Main --> App
    App --> EmailGate
    App --> UploadSection
    App --> UploadHistory
    App --> ClientSelector
    App --> PositionsTable
    App --> ViolationsTable
    App --> AnalyticsPanel
    EmailGate --> APIClient
    UploadSection --> APIClient
    UploadHistory --> APIClient
    PositionsTable --> APIClient
    ViolationsTable --> APIClient
    AnalyticsPanel --> APIClient
    App --> APIClient
    ClientSelector -.props only.-> Types
    ViolationsTable --> Types
    APIClient --> Types

    APIClient -.X-Session-Token: email.-> AppPy

    AppPy --> UploadRoute
    AppPy --> UploadsRoute
    AppPy --> ClientsRoute
    AppPy --> ViolationsRoute
    AppPy --> AnalyticsRoute

    UploadRoute --> Deps
    UploadsRoute --> Deps
    ClientsRoute --> Deps
    ViolationsRoute --> Deps
    AnalyticsRoute --> Deps

    UploadRoute --> Schemas
    UploadsRoute --> Schemas
    ClientsRoute --> Schemas
    ViolationsRoute --> Schemas
    AnalyticsRoute --> Schemas

    UploadRoute --> Parser
    UploadRoute --> Validator
    UploadRoute --> FIFO
    UploadRoute --> Violations
    UploadRoute --> AnalyticsDom

    Parser --> DomModels
    Validator --> DomModels
    FIFO --> DomModels
    Violations --> DomModels
    AnalyticsDom --> DomModels

    UploadRoute --> RepUploads
    UploadRoute --> RepTransactions
    UploadRoute --> RepPositions
    UploadRoute --> RepViolations
    UploadRoute --> RepClientAnalytics
    UploadRoute --> RepUsers
    UploadsRoute --> RepUploads
    UploadsRoute --> RepUsers
    UploadsRoute --> RepPositions
    ClientsRoute --> RepAnalytics
    ClientsRoute --> RepPositions
    ViolationsRoute --> RepViolations
    AnalyticsRoute --> RepAnalytics
    Deps --> RepUsers

    RepUploads --> ORM
    RepUsers --> ORM
    RepTransactions --> ORM
    RepPositions --> ORM
    RepViolations --> ORM
    RepClientAnalytics --> ORM
    RepAnalytics --> ORM

    Deps --> Database
    RepUploads --> Database
    RepUsers --> Database
    RepTransactions --> Database
    RepPositions --> Database
    RepViolations --> Database
    RepClientAnalytics --> Database
    RepAnalytics --> Database

    Database --> Config
    Database -.SQLAlchemy 2.0 + asyncpg.-> PG
    ORM -.declarative mapping.-> PG
    Migrations -.alembic upgrade head.-> PG
```

### Reading the graph

- **Frontend block** — every component is a leaf consumer of `App.tsx`'s
  shared state. Only `App.tsx` and the components that *originate*
  side-effects call `APIClient`; `ClientSelector` is intentionally
  presentational (state hoisted in PR-6 readability pass to eliminate
  duplicate `/clients` fetches).
- **API block** — every route depends on `Deps` (for auth + session)
  and `Schemas` (for I/O shapes). Only `UploadRoute` touches the
  ingestion + domain layers; the GET routes orchestrate repositories
  directly.
- **Domain block** — every detector and the FIFO engine import from
  `DomModels` only. Zero edges leave this block downward toward `db/`
  or sideways into `api/`. That's the testability property.
- **DB block** — every repository depends on `ORM` (for the mapped
  classes) and `Database` (for the session); there are no
  cross-repository imports.

---

## 2. Upload pipeline sequence

The hottest path in the system — `POST /api/v1/upload-transactions` —
end to end. CPU-bound steps are offloaded with `asyncio.to_thread` so
GET requests on other endpoints stay responsive.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant FE as React App
    participant R as FastAPI Route<br/>(upload.py)
    participant D as get_current_user<br/>(deps.py)
    participant P as parser.py
    participant V as validator.py
    participant DOM as domain layer
    participant REPO as repositories/*
    participant DB as PostgreSQL

    U->>FE: pick .xlsx · click Upload
    FE->>R: POST /upload-transactions<br/>multipart + X-Session-Token: email

    R->>D: resolve current user
    D->>REPO: users.get_or_create_by_email
    REPO->>DB: INSERT INTO users … ON CONFLICT DO NOTHING RETURNING
    DB-->>REPO: User row
    REPO-->>D: User
    D-->>R: User

    R->>R: guard: .xlsx · non-empty · ≤ 10 MB

    R->>P: asyncio.to_thread(parse_workbook)
    Note over P: openpyxl read_only<br/>header validation<br/>RawRow per data row
    P-->>R: list[RawRow]

    R->>V: asyncio.to_thread(validate_rows)
    Note over V: structural only —<br/>type, format, required<br/>(non-positive qty/price<br/>passes through)
    V-->>R: (valid_rows, row_errors)

    alt structural errors found
        R-->>FE: 422 RejectedRowsResponse<br/>(no DB writes)
    else valid_rows is empty
        R-->>FE: 422 "no data rows"
    else clean parse
        R->>DOM: detect_invalid_values(valid_rows)
        Note over DOM: partition: eligible vs<br/>INVALID_VALUE violations
        DOM-->>R: (eligible, invalid_value_violations)

        R->>DOM: asyncio.to_thread(run_fifo, eligible)
        Note over DOM: group by (client, isin)<br/>FIFO lots · realized P&L<br/>last_price across upload
        DOM-->>R: FIFOResult<br/>(positions, completed_trades, sell_before_buy)

        R->>DOM: detect_day_trading(eligible)
        DOM-->>R: DAY_TRADING violations

        R->>DOM: detect_risk_concentration(positions)
        DOM-->>R: RISK_CONCENTRATION violations

        R->>DOM: compute_client_analytics(eligible, completed_trades)
        DOM-->>R: ClientAnalyticsData per client

        Note over R,DB: begin one DB transaction —<br/>any failure rolls back everything
        R->>REPO: uploads.insert(filename, bytes, counts)
        REPO->>DB: INSERT … RETURNING id<br/>(nextval('uploads_id_seq'))
        DB-->>REPO: upload_id

        R->>REPO: transactions.bulk_insert(all valid rows incl. invalid-value)
        REPO->>DB: executemany INSERT

        R->>REPO: positions.bulk_insert(fifo_result.positions)
        REPO->>DB: executemany INSERT

        R->>REPO: client_analytics.bulk_insert(per-client rows)
        REPO->>DB: executemany INSERT

        R->>REPO: violations.bulk_insert(all 4 types combined)
        REPO->>DB: executemany INSERT

        R->>REPO: users.update_last_viewed(user_id, upload_id)
        REPO->>DB: UPDATE users SET last_viewed_upload_id = …
        REPO->>DB: COMMIT

        R-->>FE: 200 UploadResponse<br/>{upload_id, status, summary}
    end
```

### Notes on the sequence

- **Step 4 (`ON CONFLICT DO NOTHING`)** is what makes first-sight user
  creation race-safe under concurrent requests with the same brand-new
  email.
- **Step 12** is the post-submission fix: rows with `quantity < 0` or
  `price < 0` partition out here as `INVALID_VALUE` violations rather
  than rejecting the file. The original row still goes into
  `transactions` for audit (step 21); FIFO and analytics see only the
  `eligible` subset.
- **Steps 20–26** all run inside one DB transaction. The
  `AsyncSession` dependency rolls back automatically on any raise.
- **`last_price`** for each ISIN (used in step 14) is computed *across
  the whole upload*, not per client — so a client holding AAPL is
  marked-to-market at whoever's most recent AAPL trade in the same file
  (`domain/fifo.py:_compute_last_prices`).

---

## 3. Database schema

All 6 tables, every FK, every nullable column. `upload_id` is the
partition key across the four result tables — switching the active
upload (`PUT /users/me/last-viewed`) is purely a flag on `users`, not
a re-run of the pipeline (ADR 014).

```mermaid
erDiagram
    USERS ||--o{ UPLOADS : "last_viewed_upload_id (nullable FK, SET NULL)"
    UPLOADS ||--o{ TRANSACTIONS : "upload_id (CASCADE)"
    UPLOADS ||--o{ POSITIONS : "upload_id (CASCADE)"
    UPLOADS ||--o{ VIOLATIONS : "upload_id (CASCADE)"
    UPLOADS ||--o{ CLIENT_ANALYTICS : "upload_id (CASCADE)"

    USERS {
        int id PK "SERIAL"
        text email UK "NOT NULL UNIQUE"
        int last_viewed_upload_id FK "NULLABLE"
        timestamp created_at "NOT NULL · DEFAULT now()"
    }

    UPLOADS {
        int id PK "SERIAL"
        text filename "NOT NULL"
        bytea file_content "NOT NULL · original .xlsx bytes"
        int row_count "NOT NULL"
        int violation_count "NOT NULL"
        timestamp uploaded_at "NOT NULL · DEFAULT now()"
    }

    TRANSACTIONS {
        int id PK "SERIAL"
        int upload_id FK "NOT NULL"
        text transaction_id "NOT NULL · business id"
        text client_id "NOT NULL"
        text isin "NOT NULL"
        text action "NOT NULL · CHECK in (Buy,Sell)"
        numeric quantity "NOT NULL · 18,6"
        numeric price "NOT NULL · 18,6"
        timestamp timestamp "NOT NULL · naive UTC"
    }

    POSITIONS {
        int id PK "SERIAL"
        int upload_id FK "NOT NULL"
        text client_id "NOT NULL"
        text isin "NOT NULL"
        numeric quantity "NOT NULL · 18,6"
        numeric avg_cost "NOT NULL · 18,6"
        numeric realized_pnl "NOT NULL · 18,6"
        numeric unrealized_pnl "NOT NULL · 18,6"
        numeric last_price "NOT NULL · 18,6"
    }

    VIOLATIONS {
        int id PK "SERIAL"
        int upload_id FK "NOT NULL"
        text client_id "NOT NULL"
        text isin "NULLABLE · null for client-level"
        text transaction_id "NULLABLE · null for client-level"
        text violation_type "NOT NULL · 4 known values"
        text severity "NOT NULL · ERROR/WARNING/FLAG"
        text description "NOT NULL"
        timestamp detected_at "NOT NULL · DEFAULT now()"
    }

    CLIENT_ANALYTICS {
        int id PK "SERIAL"
        int upload_id FK "NOT NULL"
        text client_id "NOT NULL"
        numeric avg_holding_days "NULLABLE · 10,4 · null if no completed trades"
        numeric max_portfolio_value "NOT NULL · 18,6"
        numeric min_portfolio_value "NOT NULL · 18,6"
        numeric value_range "NOT NULL · 18,6"
        int winning_trades "NULLABLE · null if no completed trades"
        int total_trades "NULLABLE · null if no completed trades"
    }
```

### Indexes (from `migrations/versions/0001_initial_schema.py`)

| Table | Index | Purpose |
|---|---|---|
| `transactions` | `(upload_id)` | upload-scoped scans |
| `transactions` | `(upload_id, client_id, isin, timestamp)` | FIFO group fetch |
| `positions` | `(upload_id)` | listing |
| `positions` | UNIQUE `(upload_id, client_id, isin)` | one position per pair |
| `violations` | `(upload_id, client_id)` | filtered listing |
| `violations` | `(upload_id, violation_type)` | type-filtered listing |
| `client_analytics` | UNIQUE `(upload_id, client_id)` | one analytic row per pair |

---

## 4. Runtime topology

`docker compose up --build` brings three services up in dependency
order. Migrations are a separate one-shot service gated behind the
database healthcheck — the app can never boot against an unmigrated
schema.

```mermaid
flowchart LR
    classDef svc fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
    classDef oneshot fill:#fff9c4,stroke:#fbc02d,color:#f57f17
    classDef db fill:#fce4ec,stroke:#c2185b,color:#880e4f
    classDef ext fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
    classDef img fill:#eceff1,stroke:#455a64,color:#263238

    Dev([Developer]):::ext

    subgraph build["Multi-stage Docker build (Dockerfile)"]
        direction TB
        S1[Stage 1<br/>node:20-alpine<br/>npm ci · npm run build<br/>→ frontend/dist/]:::img
        S2[Stage 2<br/>python:3.12-slim<br/>pip install · venv]:::img
        S3[Stage 3<br/>python:3.12-slim runtime<br/>copy venv + frontend/dist + src/]:::img
        S1 --> S3
        S2 --> S3
    end

    subgraph compose["docker compose · 3 services"]
        direction TB
        DB[(db service<br/>postgres:16-alpine<br/>healthcheck: pg_isready)]:::db
        MIG[migrate service<br/>one-shot · restart: no<br/>alembic upgrade head]:::oneshot
        APP[app service<br/>uvicorn :8000<br/>FastAPI + React static]:::svc
    end

    Dev -.docker compose up --build.-> compose
    Dev -.HTTP :8000.-> APP

    DB -.healthcheck passes.-> MIG
    MIG -.service_completed_successfully.-> APP

    APP -.asyncpg :5432.-> DB
    MIG -.alembic :5432.-> DB

    S3 -.image used by.-> APP
    S3 -.image used by.-> MIG
```

### Startup gate

1. `db` starts and waits for `pg_isready` to pass on its healthcheck.
2. `migrate` starts only after `db` is healthy. It runs
   `alembic upgrade head` against the live database and exits 0
   (`restart: "no"` so it doesn't loop).
3. `app` starts only after `migrate` exits successfully
   (`service_completed_successfully` condition). The FastAPI process
   binds `:8000` and serves both the API (`/api/v1/*`) and the React
   static bundle (everything else).

### Why a separate `migrate` service

- The app image is stateless — no migration logic embedded in the
  container entrypoint.
- The same `migrate` service can be run ad-hoc with
  `docker compose run --rm migrate alembic revision --autogenerate -m "…"`
  to generate new migrations against the running DB.
- Failures in migration surface as a non-zero exit on `migrate`, which
  prevents `app` from booting — a broken schema cannot serve traffic.

---

## File-to-diagram cross-reference

| Diagram node | Source path |
|---|---|
| `App.tsx` | `frontend/src/App.tsx` |
| `api/client.ts` | `frontend/src/api/client.ts` |
| `app.py` | `src/api/app.py` |
| `deps.py` | `src/api/deps.py` |
| `schemas.py` | `src/api/schemas.py` |
| `routes/upload.py` | `src/api/routes/upload.py` |
| `parser.py` | `src/ingestion/parser.py` |
| `validator.py` | `src/ingestion/validator.py` |
| `fifo.py` | `src/domain/fifo.py` |
| `violations.py` | `src/domain/violations.py` |
| `analytics.py` (domain) | `src/domain/analytics.py` |
| `models.py` (domain) | `src/domain/models.py` |
| `models.py` (db) | `src/db/models.py` |
| `repositories/*` | `src/db/repositories/` |
| `config.py` | `src/core/config.py` |
| `database.py` | `src/core/database.py` |
| `0001_initial_schema.py` | `migrations/versions/0001_initial_schema.py` |
| Docker stages 1–3 | `Dockerfile` |
| `db` / `migrate` / `app` services | `docker-compose.yml` |
