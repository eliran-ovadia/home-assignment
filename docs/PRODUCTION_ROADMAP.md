# Production Roadmap

Features and architectural improvements that are out of scope for the assignment but represent the natural evolution of this system toward production readiness. These were identified and discussed during the design phase.

Each item includes why it was deferred and what it would take to implement.

---

## 1. Concurrent Upload Handling — Message Queue

**Current:** PostgreSQL advisory lock serialises uploads. A second upload while one is in progress returns HTTP 409.

**Production:** Replace the synchronous processing model with a task queue (Celery + Redis).
- `POST /upload-transactions` saves the file and returns a job ID immediately (HTTP 202 Accepted)
- A Celery worker processes the file asynchronously
- Client polls `GET /api/v1/jobs/{job_id}` for status, or uses a WebSocket for push notification
- Multiple workers can process different uploads in parallel (uploads for different datasets)

**Why deferred:** Adds Celery, Redis, and a job-status table to the infrastructure. Significant complexity for a demo that expects one user and one upload at a time.

---

## 2. Async Database I/O

**Current:** Synchronous SQLAlchemy with `psycopg2`. FastAPI runs sync route handlers in a thread pool (correct and safe, but not maximally efficient).

**Production:** Async SQLAlchemy with `asyncpg` driver.
- `async def` route handlers
- `AsyncSession` instead of `Session`
- True async DB calls — no thread pool overhead
- Enables higher throughput under concurrent load

**Why deferred:** Async SQLAlchemy requires different session management patterns and adds code complexity that would distract from the core business logic in a review context.

---

## 3. Faster Excel Parsing

**Current:** `openpyxl` in `read_only=True` streaming mode. Pure Python XML parsing — adequate for hundreds of thousands of rows but becomes a bottleneck beyond that.

**Production:** Replace with `python-calamine` — Python bindings for the Rust-based `calamine` library. 10–100× faster than openpyxl for large files. Drop-in replacement for reading; no API changes required.

**Why deferred:** openpyxl is the standard library, available in every Python environment. `python-calamine` is a binary dependency that requires Rust toolchain for compilation and adds Docker image complexity.

---

## 4. Parallel FIFO Computation

**Current:** FIFO engine processes `(client_id, isin)` pairs sequentially in a single thread.

**Production:** Each `(client_id, isin)` pair is fully independent — this is an embarrassingly parallel workload. Use `concurrent.futures.ProcessPoolExecutor` to distribute pairs across CPU cores.
- For N cores and M pairs, runtime drops from O(M) to O(M/N)
- Bypasses the GIL (separate processes, not threads)
- Results are merged after all workers complete

**Why deferred:** For realistic assignment datasets (hundreds of pairs), process spawn overhead exceeds computation time. Useful only at tens of thousands of pairs or more.

---

## 5. Aggregate Upload Mode

**Current:** Each upload replaces all existing data (replace-on-upload, ADR 009). The system analyses one file at a time.

**Production:** Transactions accumulate across uploads — every upload appends to the ledger rather than replacing it. Positions and violations are recomputed incrementally from the full transaction history.

Key changes required:
- `transactions.upload_id` foreign key to `uploads`
- FIFO engine must re-run only for `(client_id, isin)` pairs affected by the new upload
- Deduplication by `transaction_id` to prevent double-counting re-uploaded rows
- `GET /api/v1/clients/{id}/positions` computes from the full history, not just the last file

**Why deferred:** Cross-upload FIFO introduces ordering complexity and makes the system stateful in ways that are hard to test and debug. Replace-on-upload is the correct scope for a demo tool.

---

## 6. Authentication & Authorisation

**Current:** No authentication. The API is open — anyone with network access can upload files and read all client data.

**Production:**
- JWT-based authentication (FastAPI `python-jose` + `passlib`)
- Role-based access control: `admin` can upload, `viewer` can only query
- Per-client data isolation: a client user can only see their own positions/violations
- API key support for programmatic access
- Rate limiting on the upload endpoint (e.g. max 10 uploads per hour per user)

**Why deferred:** Out of scope for the assignment. Would be the first feature added before any real deployment.

---

## 7. Secrets Management — Cloud Provider

**Current:** `.env` file for local development; GitHub Actions Secrets for CI. The `SecretsProvider` protocol in `src/core/secrets.py` is already designed for a backend swap.

**Production:** Replace `EnvironmentSecretsProvider` with a cloud-provider implementation:
- AWS: `boto3` + AWS Secrets Manager
- GCP: `google-cloud-secret-manager`
- HashiCorp Vault: `hvac` client

No business logic changes required — only the provider passed to `configure_provider()` at startup changes.

**Why deferred:** Production secrets infrastructure is environment-specific. The abstraction is in place; the implementation is a one-file swap.

---

## 8. Analytics Caching

**Current:** Some analytics are precomputed at upload time (`client_analytics` table). Top ISINs and ISIN concentration are computed live on every `GET /analytics` call.

**Production:** Cache the full analytics response in Redis with a short TTL (e.g. 60 seconds). Invalidate the cache key on every successful upload or activation.
- Near-zero latency for repeated analytics queries
- Cache key: `analytics:current` (or `analytics:{upload_id}`)
- Fallback to live computation if Redis is unavailable

**Why deferred:** Adds Redis as a runtime dependency. Analytics queries are fast enough on realistic datasets without caching.

---

## 9. File Size and Row Count Scaling

**Current:** 10MB file size limit, 200,000 row limit. Sufficient for realistic financial transaction samples.

**Production path:**
- Increase file size limit to 100MB+ (requires streaming upload, not full file buffering)
- Remove row count limit — rely on processing time SLA instead
- Combine with items 1 (queue) and 3 (calamine) to make large file processing non-blocking and fast
- Store files in object storage (S3, GCS) instead of PostgreSQL BYTEA for files over 50MB

**Why deferred:** Requires the queue architecture from item 1. Without async processing, large files would time out HTTP connections.

---

## 10. Observability

**Current:** Standard uvicorn access logs only.

**Production:**
- Structured JSON logging (via `structlog`) — machine-parseable, filterable
- Request tracing (OpenTelemetry) — trace a request from API → domain → DB
- Metrics (Prometheus + Grafana) — request latency, upload processing time, violation counts
- Health check endpoint (`GET /health`) returning DB connectivity and processing status
- Alerting on upload failures or anomalous violation rates

**Why deferred:** Observability infrastructure is environment-specific and out of scope for a local demo.

---

## 11. Incremental Position Recomputation

**Current:** Every upload (or activation) recomputes positions for all clients across all ISINs from scratch.

**Production (aggregate mode only):** When a new upload adds transactions, only recompute positions for the `(client_id, isin)` pairs that appear in the new file. Unaffected pairs carry their existing computed values forward.

**Why deferred:** Only meaningful in aggregate mode (item 5). In replace-on-upload mode, a full recompute is always necessary.
