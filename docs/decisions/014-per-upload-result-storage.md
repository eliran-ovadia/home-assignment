# ADR 014: Per-Upload Result Storage with Per-User Isolation

**Date:** 2026-05-10
**Status:** Accepted — extends ADR 009 (replace-on-upload). The identity-related parts of this ADR (per-user advisory lock, `uploads.user_id`, `uploads.is_active`, per-user ownership) were **superseded by [ADR 016](016-email-as-identity.md)** on 2026-05-11. The per-upload result storage decision itself stands; only how "which upload am I looking at" is identified has changed (from user-owned `is_active` to a per-user `last_viewed_upload_id` preference, shared pool).

## Context

ADR 009 established replace-on-upload: each new upload wiped `transactions`, `positions`, `violations`, and `client_analytics` and rebuilt them from scratch. The upload history was stored in the `uploads` table, but the *computed results* (positions, violations, analytics) were thrown away on the next upload. To re-analyse a past file the system re-ran the full pipeline from the stored `file_content` bytes.

This had two problems:

1. **Computed results were ephemeral.** Only the currently-active upload's results existed in the DB. Past results were gone. Activating a past upload was slow (full pipeline re-run on every activation).

2. **Global advisory lock.** `pg_try_advisory_lock(12345)` — a single fixed key — meant only one upload could run at a time across the entire system. With a target of 500–1000 concurrent users, 499 of them would receive `409 Conflict` during any active upload.

## Decision

Store every upload's computed results permanently, linked by `upload_id`. Switching the "currently viewed" upload is an O(1) preference flip — no pipeline re-run.

Specifically (current implementation, post ADR 016):

1. **Each upload owns its computed results.** `positions`, `violations`, and `client_analytics` carry an `upload_id FK → uploads.id` column with `ON DELETE CASCADE`. All rows written during an upload carry that upload's ID.
2. **Nothing is deleted on new upload.** Rows from previous uploads remain in the DB indefinitely, identified by their `upload_id`.
3. **Switching uploads is a per-user preference, not a global flag.** `PUT /api/v1/users/me/last-viewed` updates `users.last_viewed_upload_id`. No pipeline re-run; the response is instant.
4. **All GET queries scope by the current user's last-viewed upload.** The `get_current_user()` dependency returns a `User` row whose `last_viewed_upload_id` (nullable) is the read scope; the route filters every DB read by that ID.
5. **Concurrent uploads do not need a lock.** Each upload writes its own `upload_id` in an independent transaction; PostgreSQL's `uploads_id_seq` serialises the ID assignment at the sequence level. No application-level mutex is required.

## What Stays the Same

- Each upload is still processed independently — FIFO runs only on that upload's transactions, not accumulated history. Positions for Upload 3 reflect Upload 3's file only.
- The validation model from ADR 011 (refined post-submission) — structural defects reject; value defects flag as `INVALID_VALUE` — is unchanged.
- The `uploads` table still stores `file_content` as BYTEA (file is preserved).

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Per-upload storage (chosen)** | Instant activate (flag flip). All past results queryable. Per-user locking. Clean separation. | More rows in positions/violations over time. Queries need upload_id filter. |
| Re-run on activate (ADR 009) | Simpler schema (no upload_id on derived tables). | Slow activation. Results are not durable. |
| Aggregate mode | Full cross-file history. | FIFO complexity across files. Data cannot be isolated per-upload. Changes semantics fundamentally. |

## Schema Impact (final, post ADR 016)

| Table | Shape |
|-------|-------|
| `users` | `id`, `email UNIQUE`, `last_viewed_upload_id NULL FK → uploads.id ON DELETE SET NULL`, `created_at`. No `session_token`, no `user_id` ownership of uploads. |
| `uploads` | `id`, `filename`, `file_content BYTEA`, `row_count`, `violation_count`, `uploaded_at`. **No** `user_id`, **no** `is_active` — uploads are a shared pool. |
| `transactions` | `upload_id FK → uploads.id ON DELETE CASCADE`. |
| `positions` | `upload_id FK → uploads.id ON DELETE CASCADE`. UNIQUE `(upload_id, client_id, isin)`. |
| `violations` | `upload_id FK → uploads.id ON DELETE CASCADE`. |
| `client_analytics` | `upload_id FK → uploads.id ON DELETE CASCADE`. UNIQUE `(upload_id, client_id)`. |

## Consequences

- Switching to a past upload is instant — its results were computed at upload time and persist in the per-table partitions.
- Concurrent uploads are not blocked. Each runs in its own DB transaction with its own `upload_id` from `uploads_id_seq`.
- DB grows linearly with the number of uploads. At 1,000 uploads × 200k rows each, `transactions` holds 200M rows — manageable in PostgreSQL with the composite indexes on `(upload_id, client_id, isin, timestamp)` / `(upload_id, violation_type)` etc. `positions` and `violations` are much smaller (one row per client+ISIN pair per upload).
- A retention policy (e.g. drop uploads older than 90 days) is a deployment-time concern and is documented as a production gap.
