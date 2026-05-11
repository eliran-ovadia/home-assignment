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

## 4a. Portfolio-Value Simulation Indexing

**Current:** `src/domain/analytics.py`'s `_simulate_portfolio_extremes` revalues *every* client's portfolio after *every* transaction — O(n × c) where n is transaction count and c is client count. At assignment scale (≤ 200k rows × ~hundreds of clients) this is acceptable: even 200,000 × 500 = 100M `Decimal` operations runs in single-digit seconds.

**Production:** maintain an inverted index `isin → set[client_id holding it]` alongside the holdings dictionary. After each transaction, only the *trading* client (whose holdings just changed) and the clients in `isin_holders[tx.isin]` (whose mark-to-market value moved because the price moved) need revaluation. For sparse portfolios this collapses the inner loop from O(c) to O(holders-per-ISIN), often a handful instead of hundreds.

**Why deferred:** Adds bookkeeping (insert into / remove from the index every time a client's holding for an ISIN crosses zero) for a constant-factor win at this scale. Justified once the analytics walk shows up on a profile.

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

## 5a. Streaming File Upload + Decompression Guards

**Current:** `src/api/routes/upload.py` reads the entire request body into memory with `await file.read()`, then checks the 10 MB cap. The parser runs openpyxl in `read_only=True` mode (streaming inside the workbook) on the buffered bytes. Acceptable at the corporate-intranet scale and the 10 MB ceiling, but two production-shaped concerns remain:

1. **Whole-file buffering before the size check.** A client can transmit up to 10 MB into the server's RAM before we know it's too big (more, briefly, with backpressure). Under concurrent load the per-request memory cost is bounded but not minimal. A streaming read that increments a counter chunk-by-chunk and aborts the request at the first byte past the cap would be more robust:

   ```python
   chunks, total = [], 0
   async for chunk in file.stream():
       total += len(chunk)
       if total > MAX_FILE_BYTES:
           raise HTTPException(413, "File exceeds the 10MB limit")
       chunks.append(chunk)
   content = b"".join(chunks)
   ```

2. **Zip-bomb risk.** `.xlsx` is a zip archive. A maliciously compressed 10 MB file can expand to hundreds of MB. `read_only=True` mitigates by streaming inside the workbook, but openpyxl still incrementally decompresses the underlying zip. Hard caps available on the production path:
   - `zipfile.ZipFile` introspection before handing the bytes to openpyxl: sum of `ZipInfo.file_size` (uncompressed) must be under a ceiling (e.g. 200 MB).
   - Wall-clock budget on the parse via a worker process (not `asyncio.wait_for` on a thread — that cancels the *wait*, not the running thread; CPython has no portable way to kill a thread mid-call).

**Why deferred:** the 10 MB cap is the primary defense and is sufficient at the assignment scale and target deployment context (authenticated corporate users on managed devices, not the public internet). Both upgrades — streaming read and zip-introspection — are mechanical changes that don't affect the route's contract.

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

**Current:** `pydantic-settings` reads `.env` for local development; GitHub Actions Secrets are injected as env vars in CI; `docker-compose.yml` forwards the password from the host shell. The DB password is held in `pydantic.SecretStr`, which keeps it out of `repr` and accidental log output but does not provide rotation, audit trails, or per-environment access control.

**Production:** Move sensitive values out of env vars and into a managed secrets store:
- AWS: `boto3` + AWS Secrets Manager (or SSM Parameter Store)
- GCP: `google-cloud-secret-manager`
- HashiCorp Vault: `hvac` client

The cleanest implementation path is to introduce a small `SecretsProvider` Protocol in `src/core/` (one method, `get(key) -> SecretStr`) with the default reading from settings and a production implementation reading from the chosen store. `Settings.db_password` would then be populated from that provider during `init_db()` rather than at import time. This is a deliberate non-decision for the assignment scope — the abstraction was prototyped early in the project and removed once it became clear it added a layer that wasn't earning its keep without a real backend behind it.

**Why deferred:** Production secrets infrastructure is environment-specific (which cloud, which IAM model, which rotation policy). For the assignment, env-driven configuration is the right scope; the migration path is well understood and small.

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
