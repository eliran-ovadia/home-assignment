# ADR 009: Replace-on-Upload (Idempotent Ingestion)

**Date:** 2026-05-09
**Status:** Accepted

## Context

When a user uploads a new Excel file, the system must decide what to do with existing data. Two models were considered: replace all existing data with the new file's data, or aggregate (append) new transactions on top of existing ones.

## Decision

Each upload **replaces** all existing data. The system truncates the `transactions`, `positions`, and `violations` tables before processing the new file. The same file uploaded twice produces identical results.

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