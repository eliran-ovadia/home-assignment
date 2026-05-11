# Project Score Tracker

Updated after each significant milestone. Scores are 1–10.

**Current overall: 9.3 / 10**
Last updated: 2026-05-11 — post-submission cleanup pass (INVALID_VALUE
re-classification, API examples doc, Postman collection, roadmap trim,
README + AI_USAGE refactor).

---

## Scores by Criterion

| Criterion | Score | Notes |
|---|---|---|
| System Design | 9.6 | Layered architecture (api → domain → db) survived two pivots without churn — the identity model change in PR 2 and the INVALID_VALUE re-classification post-submission. Both fixes touched only the layer that owned the concept; downstream layers compiled unchanged. That property is what good layering buys you, and it actually paid out here. |
| Documentation | 9.6 | Full spec (`SPEC.md` with §0 deployment context), 10 ADRs covering every non-obvious choice, `API_EXAMPLES.md` covering every endpoint × every return code, Postman collection, sample-file README, refined ADR 011 explaining the structural-vs-value validation split. Trimmed for signal: README is ~60 lines, `PRODUCTION_ROADMAP.md` is the 5 actually-major items rather than a wish list. Held back from 9.8 by the original `INVALID_VALUE` mis-classification — a spec-translation error caught by the user, not by review. |
| AI Usage | 9.7 | `AI_USAGE.md` refactored for AI-friendly scanning: TL;DR up top, "Who Caught What" tables separating human review from CI agent review, per-PR triage with both accepts and rejects, explicit lesson from the post-submission discovery. Honest about both layers of the `INVALID_VALUE` mistake (≤ vs <), not just the first one. |
| Problem Solving | 9.5 | All four violation types correctly classified after the post-submission fix. FIFO handles partial sells / oversell / empty-queue / lot-boundary crossings, with unit tests for each. The two-tier validation split (structural defects reject; value defects flag) is now a documented design pattern rather than a special case. |
| Code Quality | 9.4 | SQLAlchemy 2.0 `Mapped[]` / `mapped_column` throughout, async-correct end-to-end, race-safe `INSERT … ON CONFLICT` for first-sight user lookup, dual-default (`Position`) documented inline. Ruff + ty pass clean. PR 3 readability pass collapsed the long functions; `detect_invalid_values` follows the same partition-style signature as the FIFO engine. |
| DevOps & Tooling | 9.4 | Three-stage Docker build (Node → Python builder → lean runtime), separate `migrate` one-shot compose service gated on db healthcheck via `service_completed_successfully`, env vars driven from a single `.env` (gitignored) with `.env.example` shipped. CI runs lint → ty → unit → integration on every PR; the build-backend typo that had been failing CI silently was found and fixed. Removed `Makefile` and `pre-commit` once it became clear they didn't fit the Windows workflow — kept the surface small. |
| Bonus Coverage | 9.7 | All four bonus items shipped: win rate per client, top realized P&L client, most-traded day, full per-endpoint analytics breakdown. Plus assignment-explicit bonuses: `docs/API_EXAMPLES.md` (every endpoint × every return code), Postman collection, 12 sample `.xlsx` files with a regenerator script, dark-mode toggle, loading states, error toasts, indexes on `(upload_id, *)` for every query path. |
| Test Coverage | 8.8 | 53 unit tests pass (validator, violations, FIFO, analytics — including 5 new ones for `detect_invalid_values`); 24 integration tests collected covering every endpoint × every return code (auth failure, structural 422, value flag, 404, success). Held back from 9+ because the full `pytest --cov-fail-under=80` run with a live DB was last verified before the INVALID_VALUE refactor; the post-fix coverage % hasn't been re-measured end-to-end. |
| Execution | 9.2 | `docker compose up --build` is the documented and tested happy path: db → migrate (`alembic upgrade head`) → app, all gated. The full end-to-end was manually verified with sample files 01–06 (including the post-fix `06_violation_invalid_negative_price.xlsx`). README is short enough to copy-paste from. Held back from 9.5 by integration tests requiring a running Postgres — fine in CI, one extra step locally. |
| Assignment Compliance | 9.7 | Every mandatory feature in the brief is implemented and behaves per the assignment text — including the post-submission INVALID_VALUE fix that aligned implementation with Part D's literal wording. Bonus requirements (extra analytics, example API requests) shipped. The original spec misread (treating INVALID_VALUE as a 422 reason instead of a flagged violation) was a real compliance gap; now closed, documented, and locked in by tests. |

---

## What Moves Each Score

### System Design → 9.8
- Add an integration test that proves layering: changing a domain
  function never requires touching `db/` or `api/`. Run the suite, swap
  a function body, run again, observe localised diff.

### Documentation → 9.8
- Inline `examples` blocks in Pydantic response models so Swagger UI
  shows real bodies (currently it shows the inferred schema only).

### AI Usage → 9.8
- Add a "What I would do differently next time" section to
  `AI_USAGE.md` — pre-commit re-read of the assignment brief against the
  spec, side-by-side, before locking ADRs.

### Code Quality → 9.6
- Replace the `Decimal | int` overload sites in test helpers with a
  single canonical helper. Drop the `cast()` calls in `validator.py`
  by reshaping `_take` to return `T` instead of `T | None`.

### Test Coverage → 9.3
- Re-run `pytest --cov-fail-under=80` end-to-end against a live DB
  after the INVALID_VALUE refactor. Confirm the gate still passes.
- Add a property test (Hypothesis) that random buy/sell sequences
  never produce a negative position or NaN P&L.

### DevOps & Tooling → 9.7
- Pin `pyproject.toml` dev-tool versions; right now `ruff` / `ty` /
  `pytest` use floating versions, so a CI run a year from now could
  drift.
- Add a `make demo` or shell script that uploads sample 01 via curl
  immediately after `docker compose up` so the reviewer sees output
  on first launch with no manual steps.

### Execution → 9.5
- Verify on a *clean* machine (fresh clone, fresh Docker volumes, no
  cached images) that `docker compose up --build` reaches the UI in
  one command and the upload of `samples/01_valid_clean.xlsx` produces
  the documented response.

### Assignment Compliance → 10
- One more pass with the assignment open side-by-side: for every line
  in the brief, find the corresponding line in `CHECKLIST.md` and the
  code reference. Verify nothing else has drifted the way INVALID_VALUE
  did.

---

## Milestone Log

| Date | Event | Score before | Score after |
|---|---|---|---|
| 2026-05-09 | Spec started | — | — |
| 2026-05-10 | Spec complete, 10 ADRs, checklist | — | 9.1 |
| 2026-05-10 | PR 1 (`feat/foundation`) merged | 9.1 | 9.3 |
| 2026-05-11 | PR 2 (`feat/database-layer`) merged | 9.3 | 9.3 |
| 2026-05-11 | PR 2 identity-model pivot (ADR 016 supersedes 015) | 9.3 | 9.4 |
| 2026-05-11 | PR 3 (`feat/domain-and-ingestion`) — 49 unit tests | 9.4 | 9.4 |
| 2026-05-11 | PR 4 (`feat/api-layer`) — all 7 endpoints | 9.4 | 9.4 |
| 2026-05-11 | PR 5 (`feat/integration-tests`) — 24 endpoint tests | 9.4 | 9.4 |
| 2026-05-11 | PR 6 (`feat/frontend`) — React + AntD shipped | 9.4 | 9.5 |
| 2026-05-11 | PR 7 (`feat/docker-finalize`) — separate `migrate` compose service | 9.5 | 9.5 |
| 2026-05-11 | Submission prepared | 9.5 | 9.5 |
| 2026-05-11 | **Post-submission: INVALID_VALUE mis-classification discovered** (sample-driven, by the user). Spec, ADR 011, validator, samples, tests, and SPEC §3/§5.1 all updated. Second slip (`≤ 0` vs `< 0`) caught and fixed in the same pass. | 9.5 | **9.3** |
| 2026-05-11 | Cleanup pass: `API_EXAMPLES.md` (assignment bonus), Postman collection, README trim, `AI_USAGE.md` refactor, `PRODUCTION_ROADMAP.md` trimmed to the 5 actually-major items | 9.3 | **9.3** |

The post-submission step is deliberately a *downgrade*, not an upgrade,
even though the fix was clean and well-documented. A spec-translation
error that survived the entire build cycle is itself a process gap, and
honest scoring should not hide that. The cleanup work that followed
restored some signal (better docs, better tests) but did not erase the
underlying mistake.
