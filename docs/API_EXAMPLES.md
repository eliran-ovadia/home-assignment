# API Examples

Every endpoint, every response code, with copy-pasteable `curl` commands and
real JSON bodies. The server URL is `http://localhost:8000` (Docker) or
whatever you configured.

## Identity

Every request must include the header **`X-Session-Token: <corporate-email>`**.
The value is validated as an email and looked up (or created) in the `users`
table on first sight. There is no login — this is a Remote-User-style header
forward from a corporate intranet (see SPEC §0 and ADR 016).

```
X-Session-Token: eliranovadia7@gmail.com
```

Omitting or malforming this header returns **400 Bad Request** on every endpoint.

```json
{ "detail": "Missing X-Session-Token header (expected corporate email)" }
```

```json
{ "detail": "X-Session-Token must be a valid corporate email address" }
```

For brevity the examples below omit the auth-failure branch on every
endpoint — it behaves identically everywhere.

---

## 1. `POST /api/v1/upload-transactions`

Ingests an `.xlsx` file end-to-end (parse → validate → FIFO → detectors →
analytics → DB insert) inside one transaction.

### Request

```bash
curl -X POST http://localhost:8000/api/v1/upload-transactions \
  -H "X-Session-Token: eliranovadia7@gmail.com" \
  -F "file=@samples/01_valid_clean.xlsx"
```

### 200 OK — file accepted

```json
{
  "upload_id": 3,
  "status": "success",
  "summary": {
    "transactions_loaded": 6,
    "positions_computed": 4,
    "violations_detected": 0
  }
}
```

> Note: `transactions_loaded` includes any rows flagged as `INVALID_VALUE`
> — they are recorded in the transactions table for audit but excluded
> from FIFO/analytics. `violations_detected` covers all four violation
> types from SPEC §3.

### 422 — file is not an `.xlsx`

```json
{ "detail": "Expected an .xlsx file" }
```

### 422 — file is empty

```json
{ "detail": "Uploaded file is empty" }
```

### 422 — file exceeds the 10 MB limit

```json
{ "detail": "File exceeds the 10MB limit" }
```

### 422 — missing required column in the header

```json
{ "detail": "Missing required columns: Timestamp" }
```

### 422 — header is present but there are no data rows

```json
{ "detail": "Workbook contains a header row but no data rows" }
```

### 422 — one or more rows fail structural validation

Triggers for this branch: bad `Action` value (not Buy/Sell), non-numeric in
`Quantity`/`Price`, missing required field, non-datetime in `Timestamp`,
duplicate column header. **Non-positive quantity/price does NOT trigger
this branch** — it returns 200 with an `INVALID_VALUE` violation.

```json
{
  "detail": "Upload rejected: file contains invalid rows",
  "rejected_rows": [
    {
      "row_number": 3,
      "transaction_id": "TXN002",
      "column": "action",
      "reason": "Expected 'Buy' or 'Sell', got: 'HOLD'"
    },
    {
      "row_number": 5,
      "transaction_id": "TXN004",
      "column": "quantity",
      "reason": "Expected a number, got: 'many'"
    }
  ]
}
```

---

## 2. `GET /api/v1/uploads`

List every upload in the shared pool, newest first.

### Request

```bash
curl http://localhost:8000/api/v1/uploads \
  -H "X-Session-Token: eliranovadia7@gmail.com"
```

### 200 OK — uploads exist

`is_last_viewed` is computed per-current-user against
`users.last_viewed_upload_id`, so two users browsing the same list see
different flags.

```json
[
  {
    "id": 3,
    "filename": "01_valid_clean.xlsx",
    "row_count": 6,
    "violation_count": 0,
    "uploaded_at": "2026-05-11T20:14:32",
    "is_last_viewed": true
  },
  {
    "id": 2,
    "filename": "02_violation_sell_before_buy.xlsx",
    "row_count": 3,
    "violation_count": 1,
    "uploaded_at": "2026-05-11T19:55:08",
    "is_last_viewed": false
  }
]
```

### 200 OK — no uploads yet

```json
[]
```

---

## 3. `PUT /api/v1/users/me/last-viewed`

Set the current user's active upload. Instant — no pipeline re-run, the
results were stored when the upload happened (ADR 014).

### Request

```bash
curl -X PUT http://localhost:8000/api/v1/users/me/last-viewed \
  -H "X-Session-Token: eliranovadia7@gmail.com" \
  -H "Content-Type: application/json" \
  -d '{"upload_id": 2}'
```

### 200 OK — switched

Response shape matches `POST /upload-transactions` so the frontend can
swap one handler for the other.

```json
{
  "upload_id": 2,
  "status": "success",
  "summary": {
    "transactions_loaded": 3,
    "positions_computed": 2,
    "violations_detected": 1
  }
}
```

### 404 — upload does not exist

```json
{ "detail": "Upload 9999 not found" }
```

### 422 — request body is malformed (missing or wrong type)

FastAPI default validation error — emitted when `upload_id` is missing,
isn't an integer, or the JSON is unparseable.

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "upload_id"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

---

## 4. `GET /api/v1/clients`

One summary row per client in the **active** upload (the current user's
`last_viewed_upload_id`).

### Request

```bash
curl http://localhost:8000/api/v1/clients \
  -H "X-Session-Token: eliranovadia7@gmail.com"
```

### 200 OK — active upload selected

```json
[
  {
    "client_id": "C001",
    "transaction_count": 2,
    "position_count": 1,
    "violation_count": 0
  },
  {
    "client_id": "C002",
    "transaction_count": 2,
    "position_count": 2,
    "violation_count": 0
  }
]
```

### 200 OK — user has not selected an upload yet

A brand-new user with no `last_viewed_upload_id` gets an empty list,
not a 404. The UI uses this to render the "no clients yet" empty state.

```json
[]
```

---

## 5. `GET /api/v1/clients/{client_id}/positions`

Every position for one client, ordered by ISIN.

### Request

```bash
curl http://localhost:8000/api/v1/clients/C001/positions \
  -H "X-Session-Token: eliranovadia7@gmail.com"
```

### 200 OK — client has positions in the active upload

```json
[
  {
    "isin": "US0378331005",
    "quantity": "0.000000",
    "avg_cost": "0.000000",
    "realized_pnl": "1000.000000",
    "unrealized_pnl": "0.000000",
    "last_price": "160.000000"
  },
  {
    "isin": "US5949181045",
    "quantity": "50.000000",
    "avg_cost": "300.000000",
    "realized_pnl": "0.000000",
    "unrealized_pnl": "0.000000",
    "last_price": "300.000000"
  }
]
```

> `last_price` is the most recent price for that ISIN observed anywhere
> in the upload — not just this client's trades. See `domain/fifo.py:202`
> (`_compute_last_prices`).

### 404 — no active upload selected

```json
{ "detail": "No active upload selected" }
```

### 404 — client is not in the active upload

```json
{ "detail": "Client 'C999' not found in active upload" }
```

---

## 6. `GET /api/v1/violations`

Violations for the active upload. Both filters are optional and combine
with AND.

### Request — no filters

```bash
curl http://localhost:8000/api/v1/violations \
  -H "X-Session-Token: eliranovadia7@gmail.com"
```

### Request — filter by type

```bash
curl "http://localhost:8000/api/v1/violations?violation_type=DAY_TRADING" \
  -H "X-Session-Token: eliranovadia7@gmail.com"
```

Valid `violation_type` values: `INVALID_VALUE` · `SELL_BEFORE_BUY` ·
`DAY_TRADING` · `RISK_CONCENTRATION`. Any other value just returns `[]`.

### Request — filter by client + type

```bash
curl "http://localhost:8000/api/v1/violations?client_id=C001&violation_type=RISK_CONCENTRATION" \
  -H "X-Session-Token: eliranovadia7@gmail.com"
```

### 200 OK — violations exist

```json
[
  {
    "id": 12,
    "transaction_id": "TXN003",
    "client_id": "C002",
    "isin": "US0378331005",
    "violation_type": "SELL_BEFORE_BUY",
    "severity": "ERROR",
    "description": "Client C002 attempted to sell 50 units of US0378331005 with no open position",
    "detected_at": "2026-05-11T20:14:32"
  },
  {
    "id": 13,
    "transaction_id": null,
    "client_id": "C001",
    "isin": "US0378331005",
    "violation_type": "RISK_CONCENTRATION",
    "severity": "WARNING",
    "description": "Client C001 holds 90.91% of portfolio in US0378331005 (threshold: > 50%)",
    "detected_at": "2026-05-11T20:14:32"
  }
]
```

### 200 OK — no violations match

Empty list. The endpoint never 404s on an empty result.

```json
[]
```

---

## 7. `GET /api/v1/analytics`

The full dashboard payload — four required sections (SPEC §5.5) plus a
`bonus` block.

### Request

```bash
curl http://localhost:8000/api/v1/analytics \
  -H "X-Session-Token: eliranovadia7@gmail.com"
```

### 200 OK — active upload has data

```json
{
  "top_traded_isins": [
    { "isin": "US0378331005", "transaction_count": 3 },
    { "isin": "US02079K3059", "transaction_count": 2 },
    { "isin": "US5949181045", "transaction_count": 1 }
  ],
  "avg_holding_time_per_client": [
    { "client_id": "C001", "avg_holding_days": "4.0000" },
    { "client_id": "C002", "avg_holding_days": null },
    { "client_id": "C003", "avg_holding_days": "4.0000" }
  ],
  "most_volatile_client": {
    "client_id": "C003",
    "max_portfolio_value": "30000.000000",
    "min_portfolio_value": "0.000000",
    "value_range": "30000.000000"
  },
  "isin_concentration": [
    {
      "isin": "US0378331005",
      "client_count": 2,
      "total_clients": 3,
      "concentration_pct": 66.67,
      "clients": ["C001", "C002"]
    }
  ],
  "bonus": {
    "top_realized_pnl_client": {
      "client_id": "C001",
      "realized_pnl": "1000.000000"
    },
    "win_rate_per_client": [
      {
        "client_id": "C001",
        "win_rate": 1.0,
        "winning_trades": 1,
        "total_trades": 1
      },
      {
        "client_id": "C003",
        "win_rate": 1.0,
        "winning_trades": 1,
        "total_trades": 1
      }
    ],
    "most_traded_day": {
      "date": "2026-01-01",
      "transaction_count": 2
    }
  }
}
```

### 200 OK — user has no active upload

Every section is empty / null; the endpoint still returns 200.

```json
{
  "top_traded_isins": [],
  "avg_holding_time_per_client": [],
  "most_volatile_client": null,
  "isin_concentration": [],
  "bonus": {
    "top_realized_pnl_client": null,
    "win_rate_per_client": [],
    "most_traded_day": null
  }
}
```

---

## Quick reference — return codes per endpoint

| Endpoint | 200 | 400 | 404 | 422 |
|---|:-:|:-:|:-:|:-:|
| `POST /upload-transactions` | ✅ accepted | ✅ auth | — | ✅ file/row validation |
| `GET /uploads` | ✅ list (may be `[]`) | ✅ auth | — | — |
| `PUT /users/me/last-viewed` | ✅ switched | ✅ auth | ✅ upload missing | ✅ bad body |
| `GET /clients` | ✅ list (may be `[]`) | ✅ auth | — | — |
| `GET /clients/{id}/positions` | ✅ list | ✅ auth | ✅ no upload / wrong client | — |
| `GET /violations` | ✅ list (may be `[]`) | ✅ auth | — | — |
| `GET /analytics` | ✅ payload (may be empty) | ✅ auth | — | — |

> Anywhere a 400 is shown, the cause is always the `X-Session-Token` header
> being missing or not a valid email. The detail message distinguishes the
> two cases.
