# `generate_sample_xlsx.py`

Builds 12 hand-curated `.xlsx` files under `samples/` for manual testing
of `POST /api/v1/upload-transactions`. Each file targets exactly one
upload behaviour so you can verify response codes and per-row error
tables independently.

## Run

```bash
python scripts/generate_sample_xlsx.py
```

Output overwrites `samples/*.xlsx`. The script is idempotent.

## What it produces

| Range | Outcome | Examples |
|---|---|---|
| `01–06` | **Valid uploads** — return `200` | clean file, SELL_BEFORE_BUY, DAY_TRADING, RISK_CONCENTRATION, INVALID_VALUE (negative qty), INVALID_VALUE (negative price) |
| `10–15` | **Structural failures** — return `422`, nothing saved | missing column, bad action, non-numeric quantity, missing field, multiple errors, empty data rows |

See [`samples/README.md`](../samples/README.md) for the full file-by-file
table with expected responses.

## Why a script and not just checked-in files

The `.xlsx` files are binary; a generator script makes them
human-readable in git history (the script changes, not the bytes), and
keeps every sample consistent with the current schema (e.g. when the
assignment's `Quantity < 0` rule was clarified, only the generator
needed editing — the regenerated files updated automatically).
