# ADR 009: Replace-on-Upload (Idempotent Ingestion)

**Date:** 2026-05-09
**Status:** Accepted — extended by [ADR 014](014-per-upload-result-storage.md) (per-upload result storage replaces "truncate before write" with "scope by `upload_id`")

## Context

When a user uploads a new Excel file, the system must decide what to do with existing data. Two models were considered: replace all existing data with the new file's data, or aggregate (append) new transactions on top of existing ones.

## Decision

Each upload is processed **independently** — FIFO, violations, and analytics for one upload never see another upload's transactions. The same file uploaded twice produces identical results within its own scope.

The original formulation of this ADR called for truncating the result tables on every upload. ADR 014 refined this: instead of *deleting* old rows, every result table carries an `upload_id` FK and queries scope reads to the current user's `last_viewed_upload_id`. The semantic guarantee (each upload reflects exactly one file's worth of data) is unchanged; only the implementation moved from "delete + insert" to "insert with scope".

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Replace (idempotent)** | Simple, predictable, deterministic — same file = same result; no deduplication logic needed | No historical data retention across uploads |
| Aggregate (append) | System stays "alive" across multiple files; reflects real-world portfolio accumulation | Requires an `uploads` table, per-upload tracking, cross-upload FIFO recalculation, deduplication by `TransactionId`, and upload management UI — significant scope increase |

## Consequences

- FIFO cost basis and all derived computations are always run on a single coherent dataset — no risk of cross-upload ordering bugs.
- Upload is a safe, repeatable operation: the reviewer can upload the same file multiple times without corrupting state.
- The system is scoped correctly for the assignment: analytics and positions reflect one uploaded dataset at a time.
- If aggregate mode were needed in the future, the migration path is: add an `uploads` table, add `upload_id` FK to `transactions`, and move truncation logic to an explicit "reset" endpoint.