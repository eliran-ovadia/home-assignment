# Production Roadmap

Five upgrades that are out of scope for the assignment but represent the
real next steps for a production rollout. Each entry states the current
state of the codebase, the production target, and why the upgrade was
deferred.

---

## 1. SSO / OIDC Authentication

**Current.** Every request carries `X-Session-Token: <corporate-email>`,
validated as an email at the API boundary. The deployment context is a
corporate intranet behind an existing IdP, so the email is treated as a
Remote-User-style forward from the trusted perimeter rather than as a
verified credential. See SPEC §0 and ADR 016.

**Production.** Replace the header trust with a signed token from the
corporate IdP (Microsoft Entra ID, Okta, Auth0 — OIDC / SAML). The only
code that changes is `src/api/deps.py::get_current_user`: it stops
reading `X-Session-Token` directly and starts reading the verified
claim from the JWT (validated against the IdP's JWKS). Add per-user
audit logging on `users` writes. Optionally introduce role-based access
control (admin / viewer) if the business case requires it.

**Why deferred.** Standing up an IdP integration requires an IdP. The
email-as-identity model is the smallest scheme that supports the
"recognise the user across devices" requirement while keeping the
production migration path to one function.

---

## 2. Asynchronous Upload Queue

**Current.** `POST /upload-transactions` is synchronous (ADR 013): the
HTTP connection is held open for the full pipeline — parse, validate,
FIFO, detectors, analytics, DB insert. A 10 MB / 200 k-row upload can
take meaningful wall-clock time, and the client has no progress
feedback. There is no application-level lock, so concurrent uploads
from different users do not block each other, but a single user's
upload still blocks one HTTP worker per upload.

**Production.** Move the pipeline to a job queue (Celery + Redis, or
RQ). The endpoint changes to:

- `POST /upload-transactions` saves the bytes, enqueues a job, and
  returns `202 Accepted` with a job ID.
- Workers process uploads off-thread; multiple workers run in parallel.
- `GET /api/v1/jobs/{job_id}` exposes status; a WebSocket or SSE channel
  pushes progress events.
- The frontend renders a progress bar; users can navigate away and come
  back.

**Why deferred.** Adds Redis + a worker process + a `jobs` table. The
synchronous model is correct at assignment scale; this is the upgrade
that unlocks larger files and concurrent uploads-per-user without
timing out HTTP connections.

---

## 3. Managed Secrets Store

**Current.** `pydantic-settings` reads `.env` locally and OS env vars in
CI / Docker. The DB password is held in `pydantic.SecretStr`, which
redacts it from `repr` and accidental log output but provides no
rotation, no audit trail, and no per-environment access control.

**Production.** Move secrets out of env vars and into a managed store:

| Cloud | Service | Client |
|---|---|---|
| AWS | Secrets Manager / SSM Parameter Store | `boto3` |
| GCP | Secret Manager | `google-cloud-secret-manager` |
| Self-hosted | HashiCorp Vault | `hvac` |

Implementation shape: introduce a `SecretsProvider` Protocol in
`src/core/` (single method, `get(key) -> SecretStr`). The default
implementation reads from `Settings`; the production implementation
reads from the chosen store. `Settings.db_password` becomes a property
that resolves through the provider at request time rather than at
import time, enabling rotation without restart.

**Why deferred.** Choice of secrets store is environment-specific
(which cloud, which IAM model, which rotation policy). The migration
path is well understood and the change surface is small.

---

## 4. Observability

**Current.** Standard uvicorn access logs to stdout. No structured
logging, no metrics, no tracing, no health endpoint.

**Production.**

- **Structured JSON logs** via `structlog` — machine-parseable, filterable
  by request ID / user ID / upload ID.
- **Distributed tracing** with OpenTelemetry — a single trace spans API
  route → domain layer → DB calls, making slow-upload investigations
  trivial.
- **Metrics** exported in Prometheus format: request latency, upload
  processing time, violation counts per type, queue depth. Visualised
  in Grafana; alerted on via Alertmanager.
- **`GET /health`** that returns DB connectivity and (in production)
  queue connectivity. Wired into the orchestrator's liveness probe.
- **Sentry** (or equivalent) for unhandled-exception capture with stack
  traces and breadcrumbs.

**Why deferred.** Observability infrastructure is environment-specific
and adds runtime dependencies. None of these changes require code
restructuring — they're additive.

---

## 5. Aggregate Ledger Mode

**Current.** Each upload is processed as its own independent dataset
(ADR 009 / ADR 014). Past uploads are preserved on disk and in the
results tables, but switching between them via
`PUT /users/me/last-viewed` shows the single file's view — there is no
cross-upload reconciliation.

**Production.** Treat transactions as an append-only ledger that
accumulates across uploads. Concrete changes:

- A new upload deduplicates rows by `(transaction_id)` against the
  existing ledger before processing.
- FIFO re-runs only for the `(client_id, ISIN)` pairs touched by the
  new upload, carrying unaffected positions forward.
- `GET /clients/{id}/positions` computes from the full history, not
  the most recent upload.
- A separate `POST /api/v1/uploads/{id}/revert` endpoint removes one
  upload's contribution from the ledger and recomputes affected pairs.

**Why deferred.** Cross-upload FIFO introduces subtle ordering issues
(transactions with overlapping timestamps in different files, what to
do when re-uploading a corrected file). Replace-on-upload is the right
scope for the assignment; aggregate mode is the next product step once
the user base needs continuity rather than isolated runs.
