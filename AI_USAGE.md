# AI Usage Documentation

This file describes how AI tools were used to build the Lumina Capital
Transactions Platform. It is structured for easy scanning — by a human
reviewer or by an automated agent reading on the reviewer's behalf.

---

## Summary for Reviewers

- **Spec-first development.** Architecture, schema, API contract, FIFO
  pseudocode, and 10 Architecture Decision Records (ADRs) were written
  before any production code.
- **Branch-per-phase implementation.** Seven sequential PRs, each with
  one bounded responsibility. Code did not race ahead of the user's
  review.
- **Two review layers.** I reviewed every spec change and challenged
  Claude's claims during conversation. A separate Claude PR-review
  agent reviewed every diff. Their catches were complementary, not
  overlapping — see [Who Caught What](#who-caught-what).
- **Every AI suggestion was triaged, not auto-applied.** Across three
  PR-review cycles, the reviewer raised ~45 points; ~28 were applied,
  ~17 were rejected with documented reasons. Auto-accepting everything
  would have introduced a `migrations/env.py` two PRs early and
  regressed correct type annotations.
- **Mistakes are recorded.** Both mine (the human's) and Claude's, with
  how each was discovered and what was changed.

---

## Tools Used

| Tool | Purpose |
|---|---|
| Claude (claude.ai web + Claude Code CLI) | Architecture design, specification writing, code generation, conversational review |
| Claude PR-Review Agent (CI workflow) | Automated review of every diff against `main` — correctness, security, style |
| Claude Design (claude.ai artifact mode) | Frontend wireframe and visual specification |

---

## Collaboration Model

**1. Spec before code.** No implementation began until `docs/SPEC.md`,
the schema, the API contract, the FIFO pseudocode, and the relevant
ADRs were complete. Design problems were caught in conversation, not
in code. ADR cleanup (kept 10 architecturally significant decisions,
discarded 5 toolchain-mechanics ones) made the ADR set defensible in
an interview.

**2. Branch per phase.** When Claude started generating implementation
code without being asked, I stopped it and reverted everything. We
then built `docs/IMPLEMENTATION_PLAN.md` together: 7 PRs in dependency
order. Each PR has one bounded job, opens only when the previous one
merges, and goes through a review cycle before the next branch begins.
This is the discipline that keeps a human in control of an
AI-generated codebase.

**3. Dual review.** Conversational challenge from me (the human) plus
the PR-review agent in CI. Different blind spots: I caught spec-level
misreads and unclear definitions; the agent caught race conditions,
ownership bugs, and missing null checks under specific concurrent
conditions.

**4. AI review treated as advisory.** Every reviewer comment was
triaged with a written reason for accept or reject. The triage record
sits in this file (per-PR review-cycle sections below).

---

## Who Caught What

### Catches I made (human review, conversational)

These were caught by reading the spec, re-reading the assignment, or
testing the running app — not by automated tools.

| What I caught | When | How it was fixed |
|---|---|---|
| Spec said "most volatile client = most stocks" — assignment actually defines it as largest portfolio-value range | During 27-question spec review | Spec updated to "max − min of total portfolio value across transaction timestamps" |
| File-size limit (50MB) and row-count limit (200k) were inconsistent — a 50MB xlsx fits ~2M rows | During spec review | Aligned to 10MB + 200k rows (~50 bytes/row compressed) |
| Original ADR 004 (SQLAlchemy Core) contradicted the assignment's ORM preference | After re-reading the assignment brief | Switched to ORM; ADR 010 supersedes ADR 004 |
| `ProcessPoolExecutor` parallel FIFO crept into the spec — scope creep for a junior assignment | While reviewing the spec draft | Removed from SPEC; moved to `PRODUCTION_ROADMAP.md` |
| Upload response originally included rejected-row details that the DB wouldn't reflect | During API contract review | Response now reports only confirmed DB state; rejected rows are queryable separately |
| **INVALID_VALUE was mis-classified as a 422 reason** — the assignment lists it as a flaggable violation | Manual testing after submission: uploaded a sample with price=0, got 422, quoted assignment Part D | Two-tier validation split: structural defects still 422; value defects (qty/price < 0) become `INVALID_VALUE` violations on a successful upload. See [Post-Submission Discoveries](#post-submission-discoveries) |
| Initial fix used `<= 0`; assignment says strictly `< 0` (zero is allowed) | Re-reading the assignment after the first fix landed | Changed both comparisons to `< 0`; renamed sample 06 from `zero_price` to `negative_price`; added `test_invalid_values_zero_is_allowed` |
| Identity model (UUID in localStorage) didn't follow users across devices and isolated data we actually wanted shared | During PR 2 reflection | Migrated to email-as-identity + shared pool; ADR 016 supersedes ADR 015 |
| Frontend called `/api/v1/clients` twice on every upload | Manual testing — opened DevTools after an upload | Lifted `clients` state to `App.tsx`; children receive it as a prop instead of fetching independently |
| `Makefile` and `.pre-commit-config.yaml` carried complexity for tools that didn't fit the workflow | During environment setup on Windows | Removed both; replaced with documented one-command `docker compose up --build` flow |
| Pre-existing `pyproject.toml` `build-backend` typo broke CI from before the project started | Asked why CI's `needs:` gate was commented out | One-line fix to `setuptools.build_meta`; re-enabled the CI gate |

### Catches the PR-review agent made (CI, automated)

These were race conditions, ownership bugs, and missing edge-case guards
that would be hard to spot in conversational review.

| What the agent caught | PR | Why it mattered |
|---|---|---|
| `set_active(user_id, upload_id)` activated by `upload_id` alone — a mismatched pair could activate someone else's upload | PR 2 | Real authorization bug. Rewrote as single atomic CASE-based UPDATE with explicit ownership SELECT |
| `get_or_create_by_token` was SELECT-then-INSERT — concurrent requests with the same token would race and the second INSERT would 500 | PR 2 | Real race condition. Rewrote with `INSERT … ON CONFLICT DO NOTHING RETURNING`, atomic at the statement level |
| `get_win_rates` filtered `total_trades > 0` but not `winning_trades IS NOT NULL` — a defensive gap that could `TypeError` on a future schema state | PR 2 | Added the missing null check; documented the defensive intent |
| `Settings(extra="ignore")` would silently swallow `.env` typos (e.g. `LOG_LEVL=DEBUG`) | PR 1 | Changed to `extra="forbid"` — unknown keys now raise at startup |
| `get_or_create_by_email`'s SELECT-then-INSERT fallback is only safe under READ COMMITTED — would silently break under stricter isolation | PR 2 (cycle 2) | Documented the isolation requirement and failure symptom |
| `Position` model uses `default=Decimal(0)` while migration uses `server_default=sa.text("0")` — undocumented dual-default | PR 2 (cycle 2) | Added a comment block explaining the dual-default intent and the sync requirement |
| `_sells_in_window` counted distinct sell-ISINs without requiring a matching Buy of the same ISIN — would have flagged DAY_TRADING for sells that are actually SELL_BEFORE_BUY | PR 3 | Renamed to `_matched_pairs_in_window`; returns `buys ∩ sells`. SPEC §5.3 clarified. New test locks the corrected behaviour |
| `_simulate_portfolio_extremes` seeded `min/max = 0` *before* any transaction — a buy-and-hold client whose portfolio rose from 0 to $10K would (wrongly) get `range = $10K` | PR 3 | Removed the pre-seed; min/max are lazily initialised on the first post-transaction observation. New test for buy-only clients |
| `src/domain/analytics.py` had **zero unit tests** despite being the most complex code in PR 3 | PR 3 | Added 11 tests covering cross-client market propagation, holding-time math, win-rate counting, and edge cases |

### Triage discipline

The PR-review agent raised ~17 points that did **not** hold up after
investigation. A few examples:

- Claimed `sa.func.now()` was a Python-evaluated default; in fact
  `alembic upgrade head --sql` emits `DEFAULT now()` (server-side).
- Claimed `DateTime(timezone=False)` was unsafe; in fact it matches
  SPEC §3's explicit choice of `TIMESTAMP` over `TIMESTAMPTZ`, with
  the UTC-naïve convention enforced by the ingestion validator.
- Claimed `_MONEY` / `_RATIO` duplication in the migration should be
  removed by importing from `models.py`; doing so would break the
  migration-as-immutable-snapshot guarantee.
- Misread `_ensure_client_row`'s body and claimed it would skip clients
  visible only in violations.

The discipline — triage, don't auto-apply — is itself part of the
process. Auto-accepting every comment would have made the codebase
worse in measurable ways.

---

## Phase 1 — Architecture and Design

### Process

Two sustained design sessions before any code was written:

- **Session 1**: assignment read together with Claude; conflicts with
  existing setup surfaced and resolved one by one (Postgres > SQLite,
  ORM switch, React frontend, last-price-per-ISIN proxy for unrealized
  P&L).
- **Session 2**: a 27-question formal spec review covering malicious
  Excel handling, large-file memory profile, volatile-client definition,
  design patterns by name, FK constraint mechanics, dependency
  injection vs imports.

### Key decisions and where they live

| Decision | ADR |
|---|---|
| Python 3.12 pinned in `.python-version` | ADR 001 |
| FastAPI + uvicorn over Flask / Django REST | ADR 002 |
| React built once and served as FastAPI static files (single URL, zero CORS) | ADR 008 |
| Replace-on-upload deliberately chosen over incremental ledger | ADR 009 |
| SQLAlchemy ORM after re-reading the assignment | ADR 010 (supersedes ADR 004) |
| Structural defects reject the upload; value defects flag as `INVALID_VALUE` | ADR 011 (refined post-submission) |
| Synchronous (blocking) upload response | ADR 013 |
| Per-upload result storage — activating a past upload is a flag flip, not a re-run | ADR 014 (extends ADR 009) |
| Email-as-identity, shared upload pool (corporate intranet context) | ADR 016 (supersedes ADR 015) |

### Frontend design

A wireframe was generated with Claude Design (artifact mode) and saved
to `docs/design/Lumina Capital.html`. It served as the visual
specification for every React component. Concrete design reference
before code made the frontend implementation faster and more coherent.

---

## Phase 2 — Implementation

### The branch strategy

When Claude started generating implementation code unprompted, I
stopped it, reverted everything, and built a proper implementation
plan together. Result: 7 PRs in dependency order, each with one
bounded job, each going through a review cycle before the next opens.

```
PR 1: Foundation ─────────────────────────────────────────────────┐
PR 2: Database layer ───────────────────────────────────────────┐ │
PR 3: Domain logic + ingestion + unit tests ──────────────────┐ │ │
PR 4: API layer (needs 2 + 3) ──────────────────────────────┐ │ │ │
PR 5: Integration tests (needs 4) ────────────────────────┐ │ │ │ │
PR 6: Frontend (needs 4) ─────────────────────────────────│ │ │ │ │
PR 7: Docker + CI finalisation (needs 5 + 6) ─────────────┘─┘─┘─┘─┘
```

### Per-PR summary

| PR | Branch | Real issues caught | Hygiene fixes |
|---|---|---|---|
| 1 | `feat/foundation` | `extra="forbid"` on Settings; load-bearing `# ty: ignore` made inline | 4 cosmetic improvements; 12 reviewer points rejected with reasons |
| 2 | `feat/database-layer` | 3 real bugs (ownership filter, race condition, missing null check) + 1 isolation-level assumption documented | 9 cleanups; 7 rejected with reasons |
| 2 (pivot) | identity model | Cross-device session continuity; data isolation we didn't want | Migrated to email-as-identity; ADR 016; downstream repositories unchanged (layering paid out) |
| 3 | `feat/domain-and-ingestion` | 2 real semantic bugs (day-trading pair definition; pre-seeded portfolio extremes); 1 coverage gap (analytics 0% → 11 tests) | 6 documentation/hygiene fixes; 1 rejected |
| 3 (readability) | same | User-driven refactor — `parse_workbook`, `run_fifo`, `compute_client_analytics` all decomposed; validator went 267→174 lines | I evaluated each candidate honestly: refactored what needed it, left `detect_risk_concentration` alone because it was already at the right granularity |
| 4 | `feat/api-layer` | `pydantic[email]` runtime dependency missing; leftover speculative imports | Pre-existing CI build-backend typo caught and fixed across the board |
| 5–7 | tests, frontend, Docker/CI | Thin integration over already-tested layers; no significant bugs | — |

### Readability refactor (PR 3)

After PR 3's implementation pass, I read the code and asked: are these
functions too long? Claude agreed on `parser.py`, `fifo.py`,
`analytics.py`, and `validator.py`; I asked the same question about
`detect_risk_concentration` and Claude honestly evaluated and pushed
back — it was already at the right level. That kind of "be honest
about whether this needs work" framing surfaced things the PR-review
agent hadn't flagged, and it avoided refactoring for the sake of
refactoring.

---

## Post-Submission Discoveries

### INVALID_VALUE was mis-classified from day one

The single biggest substantive mistake in the project. Worth recording
in full because it shows both how a spec-level error can hide for an
entire build cycle and how the user's manual testing catches what
automated review cannot.

**The original misread.** The assignment's Part D rule matrix lists
four violations: SELL_BEFORE_BUY, DAY_TRADING, RISK_CONCENTRATION, and
**Invalid Values: Price or Quantity < 0 → flag as ERROR**. When the
spec was drafted, Claude read Part D's INVALID_VALUE entry as a
*validation* rule and lumped it with structural defects. ADR 011 and
SPEC §3 both encoded that misreading: INVALID_VALUE → 422, nothing
saved.

**How it was caught.** I uploaded `samples/12_invalid_zero_price.xlsx`,
saw the 422, and quoted Part D back at Claude: this is not a
validation error — the assignment explicitly classifies it as a
violation we add to the violations table.

**Fix.** Two-tier validation split:

| Failure mode | Behaviour |
|---|---|
| **Structural defects** (wrong type, missing column, bad action, non-numeric in a numeric cell) | Still reject the whole file with 422 |
| **Value defects** (`quantity < 0` or `price < 0`) | Flag as `INVALID_VALUE` (severity ERROR), persist the row to `transactions` for audit, exclude from FIFO and analytics |

Implementation: new `detect_invalid_values(rows) -> (eligible, violations)`
in `domain/violations.py`; the upload route partitions inputs to
downstream layers. SPEC §3, SPEC §5.1, ADR 011 (refined),
`docs/CHECKLIST.md` D4, and the sample set were all updated. New
unit + integration tests lock the behaviour in.

**The second mistake on top of the first.** I implemented the boundary
as `<= 0`. The assignment says strictly `< 0`. I caught that too —
zero is permitted under a literal read of the brief. Changed both
comparisons to `< 0`, renamed sample 06 from `zero_price` to
`negative_price` (price = -50), and added
`test_invalid_values_zero_is_allowed` so the boundary doesn't drift
again.

**Lesson.** When a spec is derived from an assignment brief, the brief
is the ground truth and the spec is a translation. Translation errors
are invisible at code-review time — every layer downstream reads
coherent because it's faithful to the *spec*. The only way to catch a
mis-translation is a re-read of the brief with the spec open
side-by-side. That re-read didn't happen before submission, which is
why a sample-driven discovery caught it the morning after.

---

## Intentional Scope Decisions

Documented production gaps — known, defensible, listed in
`docs/PRODUCTION_ROADMAP.md`:

- **No authentication / authorisation.** The deployment context (SPEC §0)
  is a corporate intranet behind SSO; the `X-Session-Token: <email>`
  header is a Remote-User-style forward from the trusted perimeter.
  OIDC/SAML is the production swap-in and uses the same
  `get_current_user` dependency shape.
- **Replace-on-upload, not incremental ledger.** ADR 009 — explicit
  scope decision documented in conversation.
- **Single-threaded FIFO.** Per-(client, ISIN) groups are independent
  and trivially parallelisable; a `ProcessPoolExecutor` variant is
  documented in `PRODUCTION_ROADMAP.md` only.
- **Synchronous upload.** Celery + Redis queue is the production path;
  out of scope for this submission.

---

## How to Verify the Claims in This Document

| Claim | How to check |
|---|---|
| Spec was written before code | `git log --reverse -- docs/SPEC.md docs/decisions/` predates first code commit |
| ADRs document trade-offs, not just choices | Every ADR has an "Alternatives Considered" table |
| PR-review agent ran on every diff | `.github/workflows/` job + commit-level review records |
| Mistakes recorded here actually happened | Cross-reference commit messages and PR descriptions |
| Triage was real (not rubber-stamping) | Per-PR sections list both accepted and rejected points with reasons |
| Tests prove the post-submission fix | `pytest tests/unit/test_violations.py -k invalid_values` (5 tests) and `tests/integration/test_api.py::test_upload_non_positive_value_succeeds_and_flags_invalid_value` |

---

## Closing Note

The repository is the deliverable; this file is the audit trail. Every
non-trivial decision, every mistake, every review-cycle disagreement
is recorded so a reviewer can follow the reasoning and challenge it.
AI was used heavily — for design conversation, code generation, and
review — but every accepted output passed through human judgement, and
the disagreements with both Claude (the assistant) and the PR-review
agent are documented as faithfully as the agreements.
