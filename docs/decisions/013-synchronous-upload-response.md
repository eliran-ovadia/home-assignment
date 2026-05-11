# ADR 013: Synchronous Upload Response (Blocking HTTP)

**Date:** 2026-05-10
**Status:** Accepted

## Context

The upload endpoint processes an Excel file — parsing, validation, FIFO computation, and DB writes — and must return a result to the caller. There are two models for how the response is shaped:

1. **Synchronous (blocking):** The HTTP connection stays open. The client waits. When processing finishes, a single response arrives with the full result.
2. **Asynchronous (job queue):** The endpoint returns `202 Accepted` immediately with a `job_id`. Processing happens in the background (Celery worker). The client polls `GET /jobs/{id}` or listens on a WebSocket for the result.

## Decision

Use the synchronous model. The client waits for the full result in a single HTTP response.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Synchronous (chosen)** | No Celery, Redis, job table, or polling UI needed. Simpler error handling — the 422 comes back in the same call. | Long-running connection for large files (~10–30 seconds). Not suitable for very large files or high concurrency. |
| Async job queue | Returns immediately, scales to large files. Never blocks. Users never see 409. | Requires Celery + Redis + job status table + polling UI or WebSocket. Significant infrastructure overhead for a demo. |

## Consequences

- The frontend must show a loading state while the upload is being processed — a response will not arrive for several seconds on large files.
- A user who uploads the same file twice simultaneously receives a `409 Conflict` on the second request (per-user advisory lock — see ADR 014). The second request is rejected, not queued.
- The blocking model is correct for a single-operator tool. It is NOT correct for high-concurrency production use.

## Production Path

Documented in `docs/PRODUCTION_ROADMAP.md` §2: Celery + Redis task queue. The upload route changes to `POST → 202 + job_id`. The frontend polls `GET /api/v1/jobs/{id}` for status. Users never receive a 409 under concurrent load.
