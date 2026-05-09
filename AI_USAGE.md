# AI Usage Documentation

This file documents how AI tools were used throughout the development of the Lumina Capital Transactions Platform, as required by the assignment brief.

---

## AI Tools Used

| Tool | Purpose |
|------|---------|
| Claude (claude.ai / Claude Code CLI) | Architecture design, specification writing, code generation, code review |
| Claude Design (claude.ai artifact) | Frontend UI wireframe and design system |

---

## Phase 1 — Architecture & Design (Before Any Code)

### Approach

Rather than generating code immediately, we used Claude to design the system architecture entirely before a single line of implementation was written. Every significant decision was debated, alternatives were weighed, and the reasoning was locked into Architecture Decision Records (ADRs) in `docs/decisions/`. This is how real production teams operate — spec first, code second — and the depth of the discussion that follows reflects that commitment.

### The Design Session

The architecture was not handed to us — it was built through a sustained, critical conversation. Two major sessions shaped the project:

**Session 1 — Reading the assignment and resolving conflicts**

The first move was to share the assignment and explicitly ask Claude not to start generating code, but instead to think through every tension between the assignment's requirements and our existing setup, one item at a time. Claude's response immediately surfaced three real conflicts:

| Assignment says | We had | Resolution |
|-----------------|--------|------------|
| SQLite (minimum) | PostgreSQL | Keep Postgres — strictly better, already wired. Document the upgrade in an ADR. |
| ORM preferred | SQLAlchemy Core, no ORM | Initially challenged — we kept Core with a well-reasoned ADR 004. Later reversed (see below). |
| React preferred | Nothing yet | Open question sent to Session 2. |

Claude also spotted a critical domain ambiguity we hadn't considered: for unrealised P&L, there is no live market feed, so we had to decide how to compute "current price". We agreed to use the last transaction price per ISIN in the uploaded file — a pragmatic choice that we documented explicitly so the reviewer would see it was deliberate.

**Session 2 — 27-question spec review**

After the specification was drafted, we ran a formal review. Twenty-seven questions were posed, covering every layer of the system. A selection of the most significant ones:

*On malicious Excel files:* We asked how to protect against macro injection. Claude explained that `openpyxl` with `data_only=True` never executes macros or formulas — it reads raw cell values only. We added MIME type validation, a file size limit enforced before parsing begins, and full `try/except` coverage for corrupt files.

*On large files and memory:* We challenged whether the streaming mode was genuinely memory-constant. Claude confirmed `read_only=True` in openpyxl reads one row at a time — the whole file is never loaded into memory. Bulk inserts use SQLAlchemy's `bulk_insert_mappings` with `executemany`, which bypasses the PostgreSQL 65,535 bind-parameter ceiling.

*On the volatility definition:* We pushed back on Claude's initial interpretation of "most volatile client". Claude's first instinct was "client with the most stocks" — but we reread the assignment and corrected it: the spec asks for the client whose total portfolio value shows the largest variation over time (max − min across transaction timestamps). Claude updated the spec.

*On design patterns:* We asked Claude to name the design patterns in use so we could defend them in conversation. The answer: Layered Architecture (api → domain → db, one-directional dependencies), Repository Pattern (all DB access behind repository functions), Dependency Injection (FastAPI's `Depends()`), Service Layer (domain/ is pure business logic with zero HTTP or DB imports), and Strategy/Protocol (SecretsProvider protocol for swappable secret backends). Every pattern is now defensible by name.

*On testability:* We asked whether the architecture is modular enough to be independently testable at each layer. The answer was yes by construction: `domain/` and `ingestion/` are pure Python functions with no framework imports — unit tests need no DB, no HTTP client, no fixtures. `db/repositories/` needs a DB but no HTTP. `api/routes/` uses FastAPI's `TestClient` with a test DB. The dependency injection model (not import model) is what makes this possible.

*On FK constraints:* We asked Claude to explain FK constraint errors and why truncation order matters. Claude explained: a Foreign Key constraint means "column A in table X must reference an existing row in table Y." Violating insert/delete order causes constraint failures. We follow the correct child-before-parent truncation order even though not all FK constraints are currently declared — so adding them later doesn't break anything.

*On dependency injection vs import:* We asked Claude to explain the practical difference between injected and imported dependencies. With imports, a function reaches into the global environment for its dependency — you can't test it without a real database. With injection, the caller hands the dependency in — you swap the test DB session in without touching route code. FastAPI's `Depends()` is the injection mechanism.

### Key Decisions Made Together

**Frontend architecture — FastAPI-served React (ADR 008)**

> *"Regarding the front end, I would like to execute it with React. I just don't know if we should start it as a separate service with Node.js or from FastAPI."*

We debated three options: plain HTML/JS, React as a separate Node.js service, or React built and served by FastAPI. We chose the third: a clean multi-stage Docker build (Stage 1: Node → `npm run build`, Stage 2: Python → copies `frontend/dist/`) with FastAPI mounting the output as static files at `/`. One URL, zero CORS, one `docker compose up`. Claude called it "the standard pattern for containerized full-stack apps" — and it is. This is the right call and we stand by it.

**Spec-first development**

> *"Maybe we can make a more detailed file with the literal specification of the project like real production teams work — specifications, design, and only then we will implement it."*

Claude agreed immediately and proposed the structure: `docs/SPEC.md` for the full technical spec (schema, API contract, FIFO pseudocode, violation rules, analytics), `README.md` for structure and references, `CLAUDE.md` for domain architecture. This approach paid off — design problems were caught in conversation, not in code.

**Upload behaviour — replace-on-upload (ADR 009)**

> *"How hard will it be to build the system such that it will aggregate all data it receives and also give the option to get analytics regarding a single file upload?"*

This triggered the most substantive debate of the design phase. Claude laid out the aggregate model honestly, including the complexity it would add (cross-upload FIFO is stateful, per-file P&L is meaningless in isolation, deduplication by TransactionId, multi-upload schema design). We chose to validate this ourselves before accepting the recommendation, rephrasing the question to confirm our own understanding. We concluded that replace-on-upload is the right scope for this assignment: clean, predictable, and focused on what the reviewers are actually evaluating. Claude's summary was accurate: *"The replace-on-upload model treats each file as a complete dataset rather than an incremental ledger update. This is a deliberate scope decision — a production portfolio system would accumulate transactions and recompute positions incrementally."*

**Defective row handling — reject entire file (ADR 011)**

> *"If we encounter a rejected row, should we tell the user and ask if he would like to continue, or reject the file entirely?"*

We considered a two-phase approach (validate, show errors, ask to continue). Claude recommended single-pass rejection: stream the whole file once, collect every error, return 422 with the full list. No data is saved. The reasoning we found compelling: *"If you've got a 10,000 row file with 50 bad rows, the right answer is 'fix your data', not 'continue with 9,950 rows'."* A real financial system never processes partially corrupt input. We agreed and documented it in ADR 011.

**Async model — async def + AsyncSession + asyncio.to_thread()**

> *"Don't you think the backend should be async?"*

We asked Claude to explain the I/O-bound vs CPU-bound distinction precisely, because the two are often confused. The answer was that FastAPI routes are I/O bound (they wait for PostgreSQL) and genuinely benefit from `async def` + `AsyncSession`. But the upload pipeline also contains CPU-bound work (openpyxl parsing, FIFO computation) that async cannot speed up — for those sections, we use `asyncio.to_thread()` to push them into a thread pool without blocking the event loop. This is the correct and complete picture: async where it helps, threads where async doesn't apply. A well-understood and defensible choice.

**Race conditions — PostgreSQL advisory locks**

> *"Do we need to handle race conditions? I think we have the notion the home assignment will be used by one user, but don't we want to develop the project for some scale resilience?"*

We asked this because even for a demo, showing awareness of concurrency is the professional move. Claude recommended PostgreSQL advisory locks: `SELECT pg_try_advisory_lock(12345)` at the start of the upload pipeline. If it returns false, another upload is in progress — return 409 Conflict. The lock releases automatically when the transaction ends. Zero new infrastructure, one line of SQL. We added this to the spec and it stands as a good example of proportionate engineering — addressing the real risk without over-building the solution.

**ORM switch (ADR 010 supersedes ADR 004)**

> *"I will want to use ORM instead of full SQL queries."*

Our initial ADR 004 chose SQLAlchemy Core (no ORM) with a well-reasoned argument. When we revisited this after the assignment explicitly said ORM is preferred, we switched. ADR 010 supersedes ADR 004 and documents the change. The switch simplifies repositories significantly: `Table()` definitions become mapped classes, `conn.execute(select(...).where(...))` becomes `session.query(Model).filter(...)`, and `session.add()` replaces manual INSERT construction.

**Upload history (uploads table + activate endpoint)**

> *"We were asked in the assignment to save all uploaded files after parsing them, so we need to do that."*

Claude proposed storing file content as BYTEA in PostgreSQL — no filesystem, no object storage, no extra infrastructure, works for files up to ~100MB. We designed the `uploads` table together (id, filename, file\_content, row\_count, violation\_count, uploaded\_at, is\_active) and two new endpoints: `GET /api/v1/uploads` (history list) and `POST /api/v1/uploads/{id}/activate` (re-run the pipeline for a past upload). The upload history component in the frontend lets users switch between past uploads and see different results for each file.

### Frontend Design

We provided the following prompt to Claude Design (claude.ai artifact) to generate the UI wireframe:

> *"Design a web UI for 'Lumina Capital', a financial transactions platform. Use Ant Design components. The UI must support both light and dark mode with a toggle in the top navigation. Layout includes: Upload Panel, Upload History, Positions Table, Violations Table, Analytics Panel (2×2 grid). P&L values should be color-coded (green positive, red negative). Tables should have alternating row colors and hover states. Financial figures should be right-aligned."*

The output (saved in `docs/design/Lumina Capital.html`) served as the visual specification for all React component implementation. Having a concrete design reference before writing a single React component made the frontend implementation substantially faster and more coherent.

---

## Mistakes Claude Made and How We Fixed Them

| Mistake | How it was caught | Fix applied |
|---------|-------------------|-------------|
| Proposed `def` (sync) routes with FastAPI thread pool initially | We asked directly: "Don't you think the backend should be async?" | Upgraded to full `async def` + `AsyncSession` + `asyncio.to_thread()` for CPU-bound sections |
| Inconsistent file size vs row count limit (50MB file limit but 200k row cap — a 50MB xlsx can hold ~2M rows) | We questioned the numbers directly: "You said 50MB file size but only 200,000 rows — it seems conflicting" | Aligned to 10MB file limit + 200k row limit, consistent at ~50 bytes/row compressed |
| Proposed SQLAlchemy Core (ADR 004) while assignment prefers ORM | We re-read the assignment and asked for the switch | ADR 010 written, superseding ADR 004; `db/schema.py` becomes `db/models.py` with mapped classes |
| Volatile client definition ("most different stocks") | We re-read the assignment and corrected it in conversation | Spec updated: "largest variation in total portfolio value" (max − min across transaction timestamps) |
| Added `ProcessPoolExecutor` parallel FIFO to the spec | We caught scope creep: "Do not add it to the spec" | Removed from `docs/SPEC.md`; moved to `docs/PRODUCTION_ROADMAP.md` only |
| Upload response included inline rejected row details | We identified the inconsistency: the DB wouldn't contain that data yet, so the response would show data that doesn't exist in the DB | Redesigned: upload response shows only confirmed DB state (`transactions_loaded`, `violations_detected`); rejected rows are stored as `INVALID_VALUE` violations and queried separately |

---

## Phase 2 — Implementation

*This section will be filled in as each component is implemented.*

### Backend

| Component | What Claude generated | What we modified |
|-----------|----------------------|------------------|
| `src/core/config.py` | | |
| `src/core/database.py` | | |
| `src/db/models.py` | | |
| `src/ingestion/parser.py` | | |
| `src/ingestion/validator.py` | | |
| `src/domain/fifo.py` | | |
| `src/domain/violations.py` | | |
| `src/domain/analytics.py` | | |
| `src/api/routes/upload.py` | | |
| `src/api/routes/clients.py` | | |
| `src/api/routes/violations.py` | | |
| `src/api/routes/analytics.py` | | |
| `src/api/routes/uploads.py` | | |

### Frontend

| Component | What Claude generated | What we modified |
|-----------|----------------------|------------------|
| `frontend/src/api/client.ts` | | |
| `frontend/src/components/UploadSection.tsx` | | |
| `frontend/src/components/UploadHistory.tsx` | | |
| `frontend/src/components/PositionsTable.tsx` | | |
| `frontend/src/components/ViolationsTable.tsx` | | |
| `frontend/src/components/AnalyticsPanel.tsx` | | |

### Tests

| Test file | What Claude generated | What we modified |
|-----------|-----------------------|------------------|
| `tests/unit/test_fifo.py` | | |
| `tests/unit/test_violations.py` | | |
| `tests/unit/test_validation.py` | | |
| `tests/integration/test_api.py` | | |

---

## What We Understood and Validated

Every architectural decision went through a challenge-and-confirm cycle, not a passive accept cycle. When Claude proposed something, we asked why. When numbers seemed inconsistent, we called it out. When definitions were ambiguous, we re-read the assignment ourselves and corrected the spec.

Every piece of generated code will be reviewed against `docs/SPEC.md` before being accepted. The FIFO algorithm, violation detection rules, and analytics computation were independently verified against the assignment brief during the spec phase, before implementation begins.

Known production gaps (intentional scope decisions):
- No authentication or authorisation — would be the first feature added before any real deployment
- Replace-on-upload rather than incremental ledger — a deliberate simplification documented in ADR 009 and `docs/PRODUCTION_ROADMAP.md`
- Single-threaded FIFO — parallel `ProcessPoolExecutor` is documented as the production path in `PRODUCTION_ROADMAP.md` only
- Single upload at a time (advisory lock + 409) — Celery + Redis queue is the production path documented in `PRODUCTION_ROADMAP.md`
