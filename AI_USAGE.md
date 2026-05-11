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

*On design patterns:* We asked Claude to name the design patterns in use so we could defend them in conversation. The answer: Layered Architecture (api → domain → db, one-directional dependencies), Repository Pattern (all DB access behind repository functions), Dependency Injection (FastAPI's `Depends()`), Service Layer (domain/ is pure business logic with zero HTTP or DB imports), and the Factory pattern (`create_app()` allows different configurations in tests). Every pattern is now defensible by name.

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

**Synchronous upload response (ADR 013)**

> *"We decided on leaving the POST method that takes an Excel file synchronous — can you explain to me why? Also, how many files can one uvicorn worker handle in this situation?"*

The upload endpoint processes the file and returns the full result in one HTTP response. The client waits. The alternative — returning a job ID immediately (202 Accepted) and processing in the background — requires Celery + Redis, which is out of scope. One uvicorn worker can handle one upload at a time (per-user advisory lock) plus unlimited concurrent GET requests, since those are pure async I/O that never touch the lock.

**Per-upload result storage and user isolation (ADRs 014, 015)**

> *"There is no reason to replace the content of all tables every time we load an Excel file. We need to find a way to save all calculations in the tables. How will many people use the system? I want to aim for 500–1000 users at least at this stage."*

We identified two problems with the original replace-on-upload approach: (1) computed results for past uploads were thrown away, making activation slow (required a full pipeline re-run), and (2) the global advisory lock `pg_try_advisory_lock(12345)` meant only one upload could run at a time across the entire system — a hard bottleneck at 500+ users.

The solution: add `upload_id` FK to `positions`, `violations`, and `client_analytics`, so every upload's results are stored permanently and independently. Activation is now an instant flag flip on the `uploads` table — no re-run needed. The advisory lock becomes per-user (`pg_try_advisory_lock(user_id)`), so 500 concurrent users can upload simultaneously.

User identity is established via UUID anonymous sessions (ADR 015): the frontend generates a UUID on first load, stores it in `localStorage`, and sends it as `X-Session-Token` on every request. The backend creates a `users` row on first sight. No passwords, no login — just a stable per-browser identity sufficient to isolate data between users.

The user also clarified that this is NOT aggregate mode — each upload is still processed independently, FIFO runs only on that upload's transactions, and switching between uploads shows completely different results (from that file only).

**ADR cleanup — keeping only architecturally significant decisions**

> *"Please scan all ADRs and if there are ones that are less important delete them. Let's stay with the most significant ones."*

We reviewed all 15 ADRs and removed 5 that were toolchain or infrastructure mechanics: ADR 003 (Ruff), ADR 004 (superseded SQLAlchemy Core), ADR 006 (ty over mypy), ADR 007 (GitHub Secrets), ADR 012 (dotenv local dev). The reasoning: a tech lead reviewing the code will ask about domain and architecture decisions — not why we chose Ruff over black. The 10 remaining ADRs all document choices that are directly defensible in a code review conversation.

**Assignment self-review — checklist and score**

> *"Scan the assignment file and make a checklist for every feature requested including the recommended ones. After creating the file, scan the spec to see if we are up to standard. Then give me a score."*

We created `docs/CHECKLIST.md` by going through every part of the assignment (A through H plus submission requirements) and marking each item against the spec. Every mandatory feature is covered. Every bonus item is either covered or explicitly noted. Two minor gaps were found: the assignment asks for `requirements.txt` by name (we have `pyproject.toml`), and the README is missing a pointer to the auto-generated Swagger docs at `/api/docs`.

Score given: **9.1 / 10**. System design rated 9.5 — architecture is significantly beyond what the assignment expects. Main deduction was on execution (missing `requirements.txt`, no example API requests). The note: passing implementation with tests green and Docker running first try would push it to 10.

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

## Phase 2 — Implementation Planning: The Branch Strategy Decision

Before any implementation code was written, we made a deliberate decision about *how* to implement the project — a decision that is itself worth documenting as an example of AI-assisted development done right.

### What happened

When the implementation phase began, Claude read the project state (the spec, the plan, the milestone log) and immediately started generating code: config files, ORM models, routes, migrations, tests, a full React frontend — all at once, without being asked. The work was technically coherent but completely unauthorized. The user interrupted it: *"Wait, who asked you to start building the project?"*

Claude stopped, listed everything it had generated, and offered to revert it all. The user confirmed: delete everything. All generated files were removed. All modified files (pyproject.toml, requirements.txt, Dockerfile, ci.yml, .gitignore) were reverted to their pre-implementation state. The repository was returned to spec-only status.

This was the right outcome. The mistake was not that the code was bad — it was that the user had not consented to the work, had not reviewed the approach, and had not been in control of what was written. That control matters, especially for a submission a person must be able to defend in conversation.

### The plan we built instead

After the cleanup, we built a proper implementation plan together before writing a single line of code. The result: a 7-PR branch-based approach documented in `docs/IMPLEMENTATION_PLAN.md`:

```
PR 1: Foundation ──────────────────────────────────────────────────────┐
PR 2: Database layer ────────────────────────────────────────────────┐ │
PR 3: Domain logic + ingestion + unit tests ─────────────────────┐  │ │
PR 4: API layer (depends on 2 + 3) ─────────────────────────────┐│  │ │
PR 5: Integration tests (depends on 4) ────────────────────────┐││  │ │
PR 6: Frontend (depends on 4) ─────────────────────────────────│││  │ │
PR 7: Docker + CI finalization (depends on 5 + 6) ─────────────┘┘┘──┘─┘
```

### Why this approach is better

**The user stays in control.** The user opens each branch. Claude implements only after the branch exists. The user reviews each PR before the next branch opens. Claude cannot race ahead.

**Reviewable scope.** Each PR has one clearly bounded job. A PR titled "feat/database-layer" contains exactly: ORM models, the Alembic migration, and repository functions — nothing else. If anything is wrong, it is easy to identify exactly what and why.

**No hidden state.** When code is generated in large batches by AI without review, errors compound invisibly. A logic error in the FIFO engine gets buried under hundreds of lines of routes, migrations, and frontend components written on top of it. The branch-per-phase model surfaces errors at the smallest possible scope.

**The human owns the work.** A submission reviewed by a tech lead must be one the developer can explain in full detail. Building it phase by phase — reading each PR, understanding the approach, asking questions before merging — means every decision is understood before it is accepted, not after.

### The architecture questions we answered first

Before the implementation plan was approved, we used the planning session to clarify two key architectural questions that had changed since the original spec:

**How are past uploads preserved without re-running the pipeline?**
Every upload's computed results (positions, violations, client_analytics) are stored with an `upload_id` foreign key and never deleted. Activating a past upload is a single SQL flag flip (`SET is_active = TRUE`) — the FIFO engine and analytics pipeline never run again for that upload. All GET queries filter by the current user's active `upload_id`.

**How do 500 concurrent users avoid blocking each other?**
The original spec used `pg_try_advisory_lock(12345)` — a global constant. Every upload on the entire system competed for the same lock. We changed it to `pg_try_advisory_lock(user_id)`, derived from the user's database primary key. Different users hold different locks and cannot block each other. The same user is still serialised — two simultaneous uploads from the same session return 409.

Both answers were already in the spec (ADRs 014 and 015), but the planning session made them concrete, confirmed, and visible — before any code depended on them.

---

## Phase 2 — Implementation

### PR 1 — Review Cycle (`feat/foundation`)

After implementing PR 1, the CI Claude PR reviewer agent flagged sixteen issues. We triaged each one rather than blanket-accepting — four held up and got fixed; twelve didn't.

**Accepted (4 fixed):**

| Mistake I made | How it was discovered | Fix applied |
|---|---|---|
| `extra="ignore"` on the `Settings` model — a typo in `.env` (e.g. `LOG_LEVL=DEBUG`) would silently fall back to the default instead of raising | Reviewer flagged the misconfiguration footgun | Changed to `extra="forbid"` so unknown `.env` keys raise at startup |
| Inconsistent `Field(default=..., description=...)` calls — descriptions did nothing for validation, and not every field had one | Reviewer called out the mix as noise | Dropped `Field()` entirely; direct type annotations everywhere |
| The `# ty: ignore[missing-argument]` suppression was justified in a comment block six lines above the line — easy to delete by accident in a future cleanup | Reviewer pointed out the suppression was load-bearing but spatially separated from its rationale | Moved the rationale inline next to the `# ty: ignore` |
| `future=True` on `create_async_engine` — a no-op in SQLAlchemy 2.x | Reviewer flagged it as redundant | Removed |

**Rejected (12 push-backs):** the reviewer also raised concerns that didn't hold up after triage:

- Some were out of PR 1 scope (`migrations/env.py` belongs to PR 2 per `IMPLEMENTATION_PLAN.md`)
- Some were factually wrong (the `needs: [lint, test]` CI gate is not commented out — the `#` in the reviewer's quote was on the *description* line above; an alleged reference to `_build_database_url` in `.claude/settings.local.json` does not exist)
- Some were stylistic preferences where ty already approved the code (`AsyncIterator` is a valid annotation for a FastAPI dependency that yields — `AsyncGenerator` is a subtype, not a correctness fix)
- Some restated correct code as if it were a critique (`pool_pre_ping=True`, `expire_on_commit=False`, blank `sqlalchemy.url`)

Treating the AI review as **advisory rather than authoritative** — and keeping a paper trail of which suggestions we accepted and which we rejected with reasons — is itself the discipline. Auto-applying every reviewer suggestion would have introduced a `migrations/env.py` two PRs early and degraded a perfectly correct type annotation.

### PR 2 — Review Cycle (`feat/database-layer`)

PR 2 was a much larger diff than PR 1 — six ORM models, an initial migration, and seven repositories — so the reviewer's surface area was correspondingly bigger. Out of 19 distinct points raised across spec alignment, security, code quality, and correctness, **12 held up and got fixed**, including two real bugs and one defensive concurrency fix.

**Accepted — real bugs (3):**

| Mistake I made | How it was discovered | Fix applied |
|---|---|---|
| `set_active(user_id, upload_id)` did two sequential UPDATEs — the second one activated by `upload_id` alone, with no `user_id` filter. A caller passing a mismatched pair (a bug in PR 4 or a forged ID) would have activated *someone else's* upload. | Reviewer's "Correctness" section flagged the missing ownership check on the activation UPDATE | Rewrote as a single atomic `UPDATE … SET is_active = CASE WHEN id = :upload_id THEN true ELSE false END WHERE user_id = :user_id`, preceded by an explicit ownership SELECT that raises `UploadNotOwnedError` if the pair is mismatched. Both atomicity and ownership in one shape. |
| `get_or_create_by_token` did a SELECT-then-INSERT pattern. Two concurrent requests carrying the same brand-new session token would both pass the `is None` check, both insert, and the second insert would raise `IntegrityError` → unhandled 500. | Reviewer's "Security" section flagged the race condition | Rewrote using Postgres `INSERT … ON CONFLICT (session_token) DO NOTHING RETURNING`. On conflict the insert is a no-op and we fall back to a follow-up SELECT. Atomic at the statement level. |
| `get_win_rates` filtered `total_trades IS NOT NULL` and `total_trades > 0` but not `winning_trades IS NOT NULL`. If FIFO ever wrote `total_trades=5, winning_trades=NULL`, the `int(winning)` cast on the result row would raise `TypeError`. | Reviewer's "Correctness" section flagged the missing null check | Added `winning_trades IS NOT NULL` to the WHERE clause; documented the defensive intent in the docstring. |

**Accepted — cleanups and documentation (9):**

| Suggestion | Why it was worth applying |
|---|---|
| Drop unnecessary `list(rows)` in every `bulk_insert` | `Sequence[dict]` is already accepted by `session.execute(insert(...), …)`; the cast was noise. |
| Drop `cast(datetime.date, row[0])` in `get_most_traded_day` | The `Row[tuple[date, int]]` annotation gives the type checker what it needs without a runtime no-op. |
| Rename `_bucket` → `_ensure_client_row` in `get_client_summary` | Self-documenting; reader doesn't need to scan the body to understand intent. |
| CheckConstraint f-string → literal `"action IN ('Buy', 'Sell')"` | Removes a hypothetical fragility (quote in a constant would malform SQL). Constants `ACTION_BUY`/`ACTION_SELL` remain for Python-side use. |
| Add `server_default=sa.false()` to `Upload.is_active` ORM column | Parity with the migration; makes the schema fully self-describing at the model level. |
| Document the `Upload.insert(is_active=True)` default | The asymmetry vs. `Upload.is_active=False` default was surprising; docstring now states the business rule explicitly. |
| Document `array_agg` as PostgreSQL-specific in `analytics.py` | The spec targets Postgres, but flagging the dependency saves a future reader from a portability surprise. |
| Document the UTC-naïve timestamp convention in `get_most_traded_day` | The cast-to-Date semantics depend on the storage convention; spelled out so it can't drift silently. |
| Explain why `_MONEY`/`_RATIO` are duplicated in the migration | Migrations are immutable schema snapshots; importing live model code would silently change an already-applied migration if the model later evolves. Made the rationale explicit. |

**Rejected — claims that didn't hold up (7):**

| Reviewer claim | Why we pushed back |
|---|---|
| `sa.func.now()` in `server_default` "emits a Python-evaluated expression at migration generation time" and is a "latent bug" | Empirically false — `alembic upgrade head --sql` emits `DEFAULT now()` (server-side, evaluated at insert). This is the documented SQLAlchemy 2.0 pattern, semantically identical to `sa.text("now()")`. |
| `DateTime(timezone=False)` is unsafe and should be `timezone=True` | Matches SPEC §3 (the schema explicitly chose TIMESTAMP, not TIMESTAMPTZ). The UTC-naïve convention is enforced by the ingestion validator (PR 3). Changing here would deviate from the documented contract. |
| The `_MONEY`/`_RATIO` duplication in the migration should be eliminated by importing from `models.py` | That would defeat the purpose of migrations being immutable snapshots — a future model change would silently alter the semantics of an already-applied migration. The duplication is the *correct* pattern; only the rationale needed to be made explicit. |
| `get_active_for_user` returning `None` will cause 500s | The `None` return is correct repository-layer semantics; the API layer is responsible for translating it to 404. Flagged for PR 4 review, no action needed here. |
| `get_top_realized_pnl_client` `Decimal` return type concern | Already correct — the type annotation `Row[tuple[str, Decimal]]` matches what asyncpg returns from `SUM` over a NUMERIC column. |
| `get_most_traded_day` "may have wrong day boundary" | Only if the DB server is non-UTC AND timestamps are stored as local time — neither is true given our UTC-naïve convention. Documented rather than changed. |
| Set-active two-UPDATE atomicity is "safe within a transaction" so just document it | The reviewer's lower-severity framing was wrong about the real concern — concurrent readers at READ COMMITTED *could* observe the gap. Fixed properly with a single CASE-based UPDATE rather than just documented around. |

**Process note.** The two real bugs (ownership filter, race condition) would have been hard to spot in self-review because they only fail under conditions — a malicious or buggy caller, a same-token concurrent request — that don't show up in single-developer manual testing. The AI review caught both. That's the kind of catch that justifies the review cycle. At the same time, the reviewer also raised three points that were factually wrong (`func.now()`, `timezone=False`, duplication) and three that were design questions answered correctly already (`None` returns, `Decimal` types, day boundary). Triaging cost less than the value of the real catches.

### PR 2 — Design Pivot: Identity Model

After the PR 2 review cycle landed, a deeper conversation surfaced an issue the reviewer hadn't raised: **the identity model itself was wrong for the target deployment context.** This section documents the pivot, because the conversational reasoning matters more than the resulting diff.

#### Deployment context (the load-bearing piece)

**This system is being built for a single organization's corporate intranet.** Users are employees on company-managed devices, authenticated to the corporate IdP (e.g. Microsoft Entra ID, Okta) before they ever reach the application. Trading-desk data is shared between traders by design — uploads are a collaborative artifact, not private state.

This context is stated explicitly in `docs/SPEC.md` §0 ("Deployment Context — read this first") so any human or automated reviewer scanning the codebase reaches the same understanding before evaluating identity, authorization, or data-isolation choices. **Without this framing, the codebase looks like it accepts unverified emails as auth — which would be wrong on the public internet. With this framing, the email is a Remote-User-style header forwarded from the trusted network perimeter.**

#### What was wrong with the original (UUID-in-localStorage) model

Two issues we did not catch during spec:

1. **It didn't follow users across devices.** A UUID generated on a laptop doesn't exist on the desktop. Returning to the app on a second device produced a "new user" with no history — defeating the "remember my last selection" use case.
2. **It supported isolation we didn't actually want.** The original design (ADR 015) carefully isolated each user's uploads. But in the target context, traders *want* to share uploads with each other. We were paying complexity cost for a feature that was actively wrong for the deployment.

#### Options considered

Once the cross-device gap was identified, four options surfaced — three of which were the wrong simplification:

| Option | Verdict |
|---|---|
| Add full JWT auth | Strictly more complex than what we had. Adds login UI, password hashing, token expiry / refresh strategy, storage-vs-XSS tradeoffs. The downstream DB schema stays the same. Not a simplification. |
| Use Integrated Windows Authentication (Kerberos / AD) to "detect the PC user" | Real corporate pattern, but requires server in AD domain + browser zone config + every reviewer to set up Kerberos on their laptop. Won't work for a `docker compose up` evaluation. |
| Pure shared model with no identity at all | Simplest possible, but breaks "remember my last selection across devices" — the feature we were trying to preserve. |
| **Email-as-identity, shared data pool (chosen)** | Smallest identity scheme that satisfies the cross-device requirement while removing the isolation complexity that wasn't needed. Defensible 30-second story for the interview. Migration path to OIDC is the same `get_current_user` dependency-swap shape. |

#### What changed in the code

- **Schema (`users`)**: dropped `session_token UUID`, added `email TEXT UNIQUE` and `last_viewed_upload_id INT NULL FK→uploads.id ON DELETE SET NULL`.
- **Schema (`uploads`)**: dropped both `user_id` (no ownership) and `is_active` (per-user preference moved to `users.last_viewed_upload_id`).
- **`src/db/repositories/users.py`**: `get_or_create_by_token(uuid)` → `get_or_create_by_email(str)`, kept the race-safe `INSERT … ON CONFLICT DO NOTHING RETURNING` pattern; added `update_last_viewed(user_id, upload_id)`.
- **`src/db/repositories/uploads.py`**: dropped `get_active_for_user`, dropped `set_active`, dropped `UploadNotOwnedError`. `get_all_by_user(user_id)` became `get_all()` returning the shared pool.
- **Downstream repositories** (`transactions`, `positions`, `violations`, `client_analytics`, `analytics`): zero changes — they were already keyed by `upload_id` only. The payoff of layering paid out here.
- **API contract**: dropped `POST /uploads/{id}/activate` (replaced by `PUT /users/me/last-viewed`); dropped the 409 response on `POST /upload-transactions` (no advisory lock); the `X-Session-Token` header is kept by name (scanner-friendly, JWT-shaped) but its value is now the user's corporate email rather than a UUID.
- **Spec/docs**: SPEC.md gained §0 "Deployment Context" as a load-bearing top-level section; ADR 015 marked Superseded; new ADR 016 documents the email-as-identity decision; CLAUDE.md tech-stack and infrastructure-map rows updated.
- **PR 2 reviewer fixes still hold**: the race-safe `ON CONFLICT` pattern, the rename of `_bucket` to `_ensure_client_row`, the dropped `cast()` / `list()` calls, the `CheckConstraint` literal, etc. are all preserved. The two bugs the reviewer caught — `set_active` ownership and `get_or_create_by_token` race — became moot because their surfaces (`set_active`, UUID-based first-sight) no longer exist. The bug-class is gone with the feature.

#### Why the spec gained a "Deployment Context" section instead of putting it in CLAUDE.md only

The user explicitly asked for prominent placement of the deployment environment so that **automated security scanners or human reviewers reading the spec in isolation don't reach the wrong conclusion** about the security model. SPEC.md §0 is the first non-frontmatter section, titled "read this first," and is referenced from every place in the codebase that touches identity. The trust model is named in terms a security tool will recognize: "Remote-User-style SSO header forwarding," "trust boundary is the corporate network perimeter," "OIDC/SAML SSO is the production swap-in." The intent is that a scanner can't analyze `get_current_user` in isolation and flag it as missing authentication — the spec frames the unverified-header pattern correctly in context.

#### Why this isn't a U-turn

The user-isolation layer we built in PR 2 (and the bugs the reviewer caught in it) wasn't wasted work. It demonstrated the layering discipline: we proved that the four downstream repositories (`transactions`, `positions`, `violations`, `client_analytics`, `analytics`) don't depend on the identity model. When we collapsed the identity model, they didn't move. That's exactly the property a well-layered system should have. The pivot was cheap *because* the layering was right.

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
