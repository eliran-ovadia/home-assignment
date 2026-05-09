# ADR 011: Reject Entire Upload on Any Invalid Row

**Date:** 2026-05-09
**Status:** Accepted

## Context

When parsing an uploaded Excel file, some rows may fail format or type validation — a string where a number is expected, a missing required field, an unrecognised action value. A decision is required: should the system skip the bad rows and continue, ask the user to confirm, or reject the entire upload?

This ADR covers only **format and type errors** (wrong data type, missing field, value out of expected domain). Business-logic violations discovered after insertion (SELL_BEFORE_BUY, DAY_TRADING, RISK_CONCENTRATION) are handled separately and do not affect this decision.

## Decision

If **any row** fails format or type validation, the entire upload is rejected. The system returns HTTP 422 with a structured list of all bad rows (row number, column, expected type, actual value). Nothing is written to the database. The user must correct their Excel file and re-upload.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Reject entire upload** | Data integrity guaranteed; predictable; simple implementation; forces clean input | User must fix file even if only one row is bad |
| Skip invalid rows, process the rest | Partial data accepted | User may not notice rows were dropped; partial uploads break FIFO continuity |
| Two-phase (show errors, ask user to confirm) | User decides whether to proceed | Extra API call, frontend confirmation state, in-progress upload state — significant complexity with little benefit |

## Consequences

- The upload endpoint streams the entire file first, collecting all validation errors, before touching the database.
- If validation passes completely, the file is saved and processing begins atomically.
- The 422 response includes every bad row so the user can fix all issues in one pass.
- This decision aligns with financial data standards: partial or ambiguous ledger imports are not acceptable — the source data must be clean.
- Business-logic violations (SELL_BEFORE_BUY etc.) are intentionally excluded from this rule: those rows represent valid data that happens to violate business rules, so they are inserted and flagged.
