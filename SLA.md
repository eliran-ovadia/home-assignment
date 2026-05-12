# Service Level Agreement — Lumina Capital Transactions Platform

A one-page description of what the system does, who it serves, and the
performance you can expect.

---

## What you can do with it

| Capability | Endpoint | Notes |
|---|---|---|
| Upload an `.xlsx` of transactions | `POST /api/v1/upload-transactions` | Validates, runs FIFO, detects violations, stores results |
| List past uploads | `GET /api/v1/uploads` | Shared pool — every user sees every upload |
| Switch the active upload | `PUT /api/v1/users/me/last-viewed` | Instant — no pipeline re-run |
| List clients in the active upload | `GET /api/v1/clients` | Per-client transaction / position / violation counts |
| View one client's positions | `GET /api/v1/clients/{id}/positions` | Quantity, avg cost, realized + unrealized P&L |
| View all rule violations | `GET /api/v1/violations` | Filter by type and/or client |
| View analytics for the active upload | `GET /api/v1/analytics` | Top ISINs, holding times, most-volatile client, concentration, plus bonus stats |

What it is **not** for: real-time market data, trade execution, position
limits enforcement, deletion of past uploads (audit-trail retention is
intentional), or anonymous / public-internet access.

---

## Who it serves

- **Deployment context:** single organization's corporate intranet, behind SSO.
- **Audience:** trading desk operators, risk analysts, compliance reviewers.
- **Identity:** corporate email forwarded in `X-Session-Token` header (production swap-in: OIDC / SAML).
- **Data visibility:** shared pool — every upload is visible to every authenticated user.

---

## Capacity

| Dimension | Capacity (single uvicorn worker) | How to scale |
|---|---|---|
| Concurrent authenticated users browsing (GETs) | ~200–500 | GETs are pure async I/O — limit is connection pool size, not CPU |
| Concurrent uploads in flight | 1–2 | Uploads are CPU-bound (parser + FIFO + analytics on the thread pool). Add `uvicorn --workers N` to multiply linearly |
| Total stored uploads | No hard cap | Retention is a deployment-time policy; DB grows linearly with upload count |
| Max file size per upload | **10 MB** | Hard limit at the API layer |
| Max rows per upload | **200,000** | Soft limit per the spec; larger files succeed but exceed the SLA time targets below |

A single 4-vCPU host running `uvicorn --workers 4` comfortably handles
~4 concurrent uploads plus all the GET traffic a department of ~50
analysts generates.

---

## Processing time targets

Indicative times on a 4-vCPU / 8 GB host with a local PostgreSQL,
measured end-to-end from upload click to response.

| File size | Approx. rows | P50 | P95 | Notes |
|---|---|---|---|---|
| 10 KB | ~50 | 0.2 s | 0.5 s | Demo / smoke-test scale |
| 100 KB | ~1,000 | 0.7 s | 1.5 s | Typical daily desk file |
| 1 MB | ~10,000 | 3 s | 6 s | Weekly batch |
| 5 MB | ~100,000 | 15 s | 25 s | Monthly batch |
| 10 MB | ~200,000 | 35 s | 60 s | Spec maximum |

GET requests (clients, positions, violations, analytics) return in
**<100 ms P95** regardless of upload size — results are precomputed at
upload time and read via indexed lookups on `upload_id`.

### Why it scales the way it does

The dominant cost on large files is the per-client portfolio-value
simulation in `src/domain/analytics.py`: O(n × c) where `n` is the row
count and `c` is the distinct client count. At 200k rows × 500 clients
this is ~100M Decimal operations and accounts for most of the wall-clock
time. Inverted-index optimisation is documented as a production upgrade
in `docs/PRODUCTION_ROADMAP.md`.

---

## Failure modes and escalation

| Symptom | Likely cause | Action |
|---|---|---|
| `422 Upload rejected: file contains invalid rows` | Structural error in the .xlsx (bad column, non-numeric, missing field) | Fix the file per the row-level error list and re-upload |
| `422 Expected an .xlsx file` / `File exceeds the 10MB limit` | Wrong format or oversize | Use the [samples](samples/) as templates |
| `200` with `INVALID_VALUE` violations | Rows have negative quantity or price | Expected behaviour — the row is stored for audit but excluded from FIFO. See assignment Part D |
| Upload timeout (>2 min) | File substantially exceeds 10 MB / 200k rows | Split the file or escalate for async-queue rollout (production path) |
| `400 Missing X-Session-Token` | Not signed in via the email gate | Refresh the page and re-enter your corporate email |

For anything else, attach the request ID from the response headers and
file a ticket to the platform team.

---

## What changes are not covered by this SLA

- Adding new violation types or analytics — requires a spec change and a code release.
- Bulk delete / retention policy — currently retain-forever; production change requires sign-off.
- Real-time price feed integration — out of scope; the system uses
  per-upload last-trade as the mark-to-market proxy (see `docs/SPEC.md` §5.5).
