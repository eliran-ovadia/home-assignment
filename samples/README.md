# Sample upload files

Hand-curated `.xlsx` files for exercising `POST /api/v1/upload-transactions`
through the UI (or via `curl`). Regenerate with:

```bash
python scripts/generate_sample_xlsx.py
```

Every file targets one specific behaviour so you can verify the response
type and the per-row error table independently.

## Valid uploads — return 200

| File | What it demonstrates | Expected response |
|------|----------------------|-------------------|
| `01_valid_clean.xlsx` | 6 transactions across 3 clients, one completed AAPL trade (+$1000 realized P&L), open positions | `200`, no violations |
| `02_violation_sell_before_buy.xlsx` | C002 tries to sell AAPL with no prior buy | `200`, 1 × `SELL_BEFORE_BUY` (ERROR) |
| `03_violation_day_trading.xlsx` | C001 closes 4 distinct ISINs within one 24h window | `200`, 1 × `DAY_TRADING` (FLAG) |
| `04_violation_risk_concentration.xlsx` | C001 ends with ~91% of portfolio in AAPL | `200`, 1 × `RISK_CONCENTRATION` (WARNING) |

## Invalid uploads — return 422, nothing saved

| File | What's wrong | Expected error column |
|------|--------------|-----------------------|
| `10_invalid_missing_column.xlsx` | `Timestamp` column dropped | "Missing required columns" (file-level, not per-row) |
| `11_invalid_negative_quantity.xlsx` | One row with `quantity = -50` | `quantity` — "Expected a positive number" |
| `12_invalid_zero_price.xlsx` | `price = 0` | `price` — "Expected a positive number" |
| `13_invalid_bad_action.xlsx` | `Action = "Transfer"` | `action` — "Expected 'Buy' or 'Sell'" |
| `14_invalid_text_in_quantity.xlsx` | `quantity = "many"` | `quantity` — "Expected a number" |
| `15_invalid_missing_field.xlsx` | `client_id` is blank | `client_id` — "Missing required field" |
| `16_invalid_multiple_errors.xlsx` | Four rows, four distinct errors | Per-row table with `quantity`, `action`, `price`, `quantity` (text) |
| `17_empty_data_rows.xlsx` | Header present, no data rows | "Workbook contains a header row but no data rows" |

## Notes for manual demo

The valid files are designed to stack: uploading `01`, then `02`, then `03`
gives you four uploads visible in the history table, each with different
violation counts. Switching between them via the **Load** button proves
the per-user `last_viewed_upload_id` flip is O(1) — no pipeline rerun.

ISINs are real CUSIP-style codes (US0378331005 = AAPL, US5949181045 = MSFT,
US02079K3059 = GOOG, US88160R1014 = TSLA) — handy if the reviewer asks
"are these real instruments?".
