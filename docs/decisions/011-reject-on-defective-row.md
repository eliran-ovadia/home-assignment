# ADR 011: Reject Entire Upload on Structural Defects; Flag Value Defects

**Date:** 2026-05-09
**Status:** Accepted (refined 2026-05-10 — see *Refinement*)

## Context

When parsing an uploaded Excel file, some rows may fail validation. A
decision is required: should the system skip the bad rows and continue,
ask the user to confirm, or reject the entire upload? And does that
decision apply to **every** kind of failure, or do different failure modes
deserve different handling?

The relevant failure modes are:

1. **Structural defects** — the row can't be parsed into the canonical
   types the rest of the pipeline expects. Examples: string in the
   `Quantity` column, missing required field, `Action = "Transfer"`,
   non-datetime in `Timestamp`.
2. **Value defects** — the row parses cleanly into the right types but
   the *values* break a business rule. Examples: `Quantity = -50`,
   `Price = 0`.
3. **Business-logic violations** discovered after FIFO processing —
   SELL_BEFORE_BUY, DAY_TRADING, RISK_CONCENTRATION. These are recorded
   as violations and never affected this ADR; listed for completeness.

## Decision

**Structural defects** reject the entire upload. The system returns HTTP
422 with a structured list of all bad rows (row number, column, expected
type, actual value). Nothing is written. The user must correct the file
and re-upload.

**Value defects** (non-positive quantity or price) do *not* block the
upload. They are flagged as `INVALID_VALUE` violations (severity ERROR)
on a successful 200 response: the bad row lands in the transactions
table for audit, and `detect_invalid_values` in `domain/violations.py`
emits the violation. The row is excluded from FIFO / analytics / other
detectors so its bad values can't corrupt downstream math.

## Refinement (2026-05-10)

The original version of this ADR treated all validation failures
identically — any defect rejected the file. Re-reading the assignment's
Part D rule matrix made it clear that non-positive quantity/price is
explicitly defined as an `INVALID_VALUE` violation to be flagged in the
violations table, *not* a parse failure. The behaviour was changed to
match the spec; this ADR was rewritten to preserve the two-tier split
above. Structural rejection is unchanged.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Two-tier (current)** — reject structural defects, flag value defects | Matches the assignment's Part D rule matrix; preserves audit trail of bad rows; FIFO is fed only well-formed data | Slightly more nuance in the validator/detector split |
| Reject everything | Predictable; simplest implementation | Contradicts the assignment's explicit Part D classification of `INVALID_VALUE` as a flaggable violation |
| Skip invalid rows silently, process the rest | Partial data accepted | User may not notice rows were dropped; no audit trail |
| Two-phase (show errors, ask user to confirm) | User decides whether to proceed | Extra API call, frontend confirmation state, in-progress upload state — significant complexity with little benefit |

## Consequences

- The upload endpoint streams the entire file first, collecting all
  structural validation errors, before touching the database.
- If structural validation passes, the route partitions rows by value
  validity (`detect_invalid_values`) and feeds only the eligible subset
  to FIFO / day-trading / risk-concentration / analytics.
- All rows that pass structural validation — *including* value-defective
  ones — are inserted into the `transactions` table for audit. The
  violations table explains why each value-defective row was excluded
  from downstream computation.
- The 422 response for structural failures includes every bad row so
  the user can fix all issues in one pass.
- Business-logic violations (SELL_BEFORE_BUY etc.) are unaffected:
  those rows represent valid data that happens to violate business
  rules, and are inserted and flagged as before.
