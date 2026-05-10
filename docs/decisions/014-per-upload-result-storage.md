# ADR 014: Per-Upload Result Storage with Per-User Isolation

**Date:** 2026-05-10
**Status:** Accepted — extends ADR 009 (replace-on-upload)

## Context

ADR 009 established replace-on-upload: each new upload wiped `transactions`, `positions`, `violations`, and `client_analytics` and rebuilt them from scratch. The upload history was stored in the `uploads` table, but the *computed results* (positions, violations, analytics) were thrown away on the next upload. To re-analyse a past file the system re-ran the full pipeline from the stored `file_content` bytes.

This had two problems:

1. **Computed results were ephemeral.** Only the currently-active upload's results existed in the DB. Past results were gone. Activating a past upload was slow (full pipeline re-run on every activation).

2. **Global advisory lock.** `pg_try_advisory_lock(12345)` — a single fixed key — meant only one upload could run at a time across the entire system. With a target of 500–1000 concurrent users, 499 of them would receive `409 Conflict` during any active upload.

## Decision

Store every upload's computed results permanently, linked by `upload_id`. Isolate all data per user.

Specifically:

1. **Each upload owns its computed results.** `positions`, `violations`, and `client_analytics` gain an `upload_id FK → uploads.id` column. All rows written during an upload carry that upload's ID.
2. **Nothing is deleted on new upload.** Rows from previous uploads remain in the DB indefinitely, identified by their `upload_id`.
3. **Activate is just a flag flip.** `POST /api/v1/uploads/{id}/activate` sets `uploads.is_active = TRUE` for that upload and `FALSE` for all others belonging to the same user. No pipeline re-run. Response is instant.
4. **All GET queries filter by active upload.** The `get_current_user()` dependency resolves the session token to a `user_id`. Routes then find `upload_id WHERE user_id = ? AND is_active = TRUE` and filter all DB reads by it.
5. **Advisory lock is per-user.** `pg_try_advisory_lock(user_id)` — user 1 and user 2 can upload simultaneously.

## What Stays the Same

- Each upload is still processed independently — FIFO runs only on that upload's transactions, not accumulated history. Positions for Upload 3 reflect Upload 3's file only.
- The full-rejection model (ADR 011) is unchanged — any invalid row rejects the entire file.
- The `uploads` table still stores `file_content` as BYTEA (file is preserved).

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Per-upload storage (chosen)** | Instant activate (flag flip). All past results queryable. Per-user locking. Clean separation. | More rows in positions/violations over time. Queries need upload_id filter. |
| Re-run on activate (ADR 009) | Simpler schema (no upload_id on derived tables). | Slow activation. Results are not durable. |
| Aggregate mode | Full cross-file history. | FIFO complexity across files. Data cannot be isolated per-upload. Changes semantics fundamentally. |

## Schema Impact

| Table | Change |
|-------|--------|
| `users` | New table (ADR 015) |
| `uploads` | Add `user_id FK → users.id`. Keep `is_active`. |
| `transactions` | Already has `upload_id`. No change. |
| `positions` | Add `upload_id FK → uploads.id`. Change UNIQUE from `(client_id, isin)` to `(upload_id, client_id, isin)`. |
| `violations` | Add `upload_id FK → uploads.id`. |
| `client_analytics` | Add `upload_id FK → uploads.id`. Change PK from `client_id` to `(upload_id, client_id)`. |

## Consequences

- Activating a past upload is instant — it was already computed at upload time.
- 500 concurrent users can each upload simultaneously.
- DB grows linearly with the number of uploads. At 1,000 uploads × 200k rows each, the `transactions` table holds 200M rows — manageable in PostgreSQL with appropriate indexes. `positions` and `violations` are much smaller (one row per client+ISIN pair per upload).
- Cleanup policy (e.g., delete uploads older than 90 days) is a production concern documented in `PRODUCTION_ROADMAP.md`.
