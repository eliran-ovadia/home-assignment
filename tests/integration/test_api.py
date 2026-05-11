"""
End-to-end integration tests for every endpoint in SPEC §4 and every
scenario in SPEC §7.

Each test goes through the real ASGI app via `httpx.AsyncClient` and the
real per-test PostgreSQL schema. There are no mocks of the DB layer or the
domain layer — these tests are the gate that proves all four prior PRs
compose correctly.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.integration.conftest import (
    DEFAULT_USER_EMAIL,
    HEADER_ROW,
    OTHER_USER_EMAIL,
    auth_header,
    make_xlsx,
    row,
    ts,
    upload_files,
)

# ── reusable test data ───────────────────────────────────────────────────────


def _happy_path_rows() -> list[dict]:
    """
    Small but representative upload exercising every part of the pipeline:
      - C001 buys then sells ISIN_A → realized P&L + completed trade
      - C001 buys ISIN_B and holds → open position, unrealized P&L only
      - C002 sells ISIN_C without buying → SELL_BEFORE_BUY violation
    """
    return [
        row(
            client_id="C001",
            isin="ISIN_A",
            action="Buy",
            quantity=10,
            price=100,
            timestamp=ts(day=1, hour=9),
        ),
        row(
            client_id="C001",
            isin="ISIN_A",
            action="Sell",
            quantity=10,
            price=120,
            timestamp=ts(day=2, hour=9),
        ),
        row(
            client_id="C001",
            isin="ISIN_B",
            action="Buy",
            quantity=5,
            price=50,
            timestamp=ts(day=3, hour=9),
        ),
        row(
            client_id="C002",
            isin="ISIN_C",
            action="Sell",
            quantity=3,
            price=80,
            timestamp=ts(day=4, hour=9),
        ),
    ]


# ── 400 / 422 paths ──────────────────────────────────────────────────────────


async def test_upload_without_session_token_returns_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(_happy_path_rows())),
        # no X-Session-Token header
    )
    assert resp.status_code == 400
    assert "X-Session-Token" in resp.json()["detail"]


async def test_upload_with_malformed_email_returns_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(_happy_path_rows())),
        headers={"X-Session-Token": "not-an-email"},
    )
    assert resp.status_code == 400


async def test_upload_invalid_row_returns_422_and_does_not_persist(client: AsyncClient) -> None:
    rows = [
        row(client_id="C001", quantity=10, price=100),
        row(client_id="C002", quantity=-1, price=100),  # negative quantity
    ]
    resp = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(rows)),
        headers=auth_header(),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert any(e["column"] == "quantity" for e in body["rejected_rows"])

    # Nothing should have been written — uploads list is empty.
    uploads_resp = await client.get("/api/v1/uploads", headers=auth_header())
    assert uploads_resp.json() == []


async def test_upload_missing_columns_returns_422(client: AsyncClient) -> None:
    short_header = HEADER_ROW[:-1]  # drop "Timestamp"
    resp = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx([], header=short_header)),
        headers=auth_header(),
    )
    assert resp.status_code == 422
    assert "Missing required columns" in resp.json()["detail"]


async def test_upload_non_xlsx_filename_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/upload-transactions",
        files={"file": ("transactions.csv", b"client,txn,isin\n", "text/csv")},
        headers=auth_header(),
    )
    assert resp.status_code == 422
    assert "xlsx" in resp.json()["detail"].lower()


async def test_upload_empty_body_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(b""),
        headers=auth_header(),
    )
    assert resp.status_code == 422


# ── 200 path + downstream GETs ───────────────────────────────────────────────


async def test_valid_upload_returns_summary_and_persists(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(_happy_path_rows())),
        headers=auth_header(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["summary"]["transactions_loaded"] == 4
    # C001:ISIN_A (closed), C001:ISIN_B (open), C002:ISIN_C (sell-before-buy → opens at qty 0)
    assert body["summary"]["positions_computed"] >= 2
    assert body["summary"]["violations_detected"] >= 1  # at least the SELL_BEFORE_BUY

    # The upload row is queryable through GET /uploads.
    listing = await client.get("/api/v1/uploads", headers=auth_header())
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["is_last_viewed"] is True
    assert items[0]["row_count"] == 4


async def test_get_clients_returns_summary_per_client(client: AsyncClient) -> None:
    await _seed_happy_path(client)
    resp = await client.get("/api/v1/clients", headers=auth_header())
    assert resp.status_code == 200
    by_client = {row_["client_id"]: row_ for row_ in resp.json()}
    assert set(by_client) == {"C001", "C002"}
    assert by_client["C001"]["transaction_count"] == 3
    assert by_client["C002"]["transaction_count"] == 1


async def test_get_client_positions_returns_correct_pnl(client: AsyncClient) -> None:
    await _seed_happy_path(client)
    resp = await client.get("/api/v1/clients/C001/positions", headers=auth_header())
    assert resp.status_code == 200
    by_isin = {p["isin"]: p for p in resp.json()}

    # ISIN_A: bought 10 @ 100, sold 10 @ 120 → realized 200, position 0.
    # Compare as floats so the test survives Decimal-vs-float schema changes
    # (the current Pydantic schema serializes Decimal as "200.000000" but
    # that's brittle to assert against literally).
    assert float(by_isin["ISIN_A"]["realized_pnl"]) == pytest.approx(200.0)
    assert float(by_isin["ISIN_A"]["quantity"]) == pytest.approx(0.0)

    # ISIN_B: bought 5 @ 50, never sold → quantity 5, no realized PnL
    assert float(by_isin["ISIN_B"]["quantity"]) == pytest.approx(5.0)
    assert float(by_isin["ISIN_B"]["realized_pnl"]) == pytest.approx(0.0)


async def test_get_positions_unknown_client_returns_404(client: AsyncClient) -> None:
    await _seed_happy_path(client)
    resp = await client.get("/api/v1/clients/C999/positions", headers=auth_header())
    assert resp.status_code == 404


async def test_get_violations_includes_sell_before_buy(client: AsyncClient) -> None:
    await _seed_happy_path(client)
    resp = await client.get("/api/v1/violations", headers=auth_header())
    assert resp.status_code == 200
    types = {v["violation_type"] for v in resp.json()}
    assert "SELL_BEFORE_BUY" in types


async def test_get_violations_filter_by_type(client: AsyncClient) -> None:
    await _seed_happy_path(client)
    resp = await client.get(
        "/api/v1/violations",
        headers=auth_header(),
        params={"violation_type": "SELL_BEFORE_BUY"},
    )
    assert resp.status_code == 200
    assert all(v["violation_type"] == "SELL_BEFORE_BUY" for v in resp.json())
    # And the filter does narrow — DAY_TRADING shouldn't appear (none flagged here anyway).
    assert all("DAY_TRADING" not in v["violation_type"] for v in resp.json())


async def test_day_trading_violation_emitted_end_to_end(client: AsyncClient) -> None:
    """
    Four distinct ISINs with both a Buy and a Sell inside a single 24h
    window → DAY_TRADING is flagged once for the client. Proves the
    DAY_TRADING detector reaches the violations endpoint through the
    full pipeline.
    """
    rows = []
    for i, isin in enumerate(("ISIN_A", "ISIN_B", "ISIN_C", "ISIN_D")):
        rows.append(
            row(
                client_id="C001",
                isin=isin,
                action="Buy",
                quantity=10,
                price=100,
                timestamp=ts(day=1, hour=9, minute=i * 10),
            )
        )
        rows.append(
            row(
                client_id="C001",
                isin=isin,
                action="Sell",
                quantity=10,
                price=120,
                timestamp=ts(day=1, hour=10, minute=i * 10),
            )
        )
    upload = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(rows)),
        headers=auth_header(),
    )
    assert upload.status_code == 200, upload.text

    resp = await client.get(
        "/api/v1/violations",
        headers=auth_header(),
        params={"violation_type": "DAY_TRADING"},
    )
    assert resp.status_code == 200
    violations = resp.json()
    assert len(violations) == 1
    assert violations[0]["client_id"] == "C001"
    assert violations[0]["severity"] == "FLAG"


async def test_risk_concentration_violation_emitted_end_to_end(
    client: AsyncClient,
) -> None:
    """
    A client with 80% of portfolio market value in one ISIN → RISK_CONCENTRATION
    surfaces on the violations endpoint with severity WARNING.
    """
    rows = [
        # ISIN_A: quantity 80 × last_price 100 = 8000 (80% of total)
        row(
            client_id="C001",
            isin="ISIN_A",
            action="Buy",
            quantity=80,
            price=100,
            timestamp=ts(day=1, hour=9),
        ),
        # ISIN_B: quantity 20 × last_price 100 = 2000 (20% of total)
        row(
            client_id="C001",
            isin="ISIN_B",
            action="Buy",
            quantity=20,
            price=100,
            timestamp=ts(day=1, hour=10),
        ),
    ]
    upload = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(rows)),
        headers=auth_header(),
    )
    assert upload.status_code == 200, upload.text

    resp = await client.get(
        "/api/v1/violations",
        headers=auth_header(),
        params={"violation_type": "RISK_CONCENTRATION"},
    )
    assert resp.status_code == 200
    violations = resp.json()
    assert len(violations) == 1
    assert violations[0]["client_id"] == "C001"
    assert violations[0]["isin"] == "ISIN_A"
    assert violations[0]["severity"] == "WARNING"


async def test_get_violations_filter_by_client(client: AsyncClient) -> None:
    await _seed_happy_path(client)
    resp = await client.get(
        "/api/v1/violations",
        headers=auth_header(),
        params={"client_id": "C002"},
    )
    assert resp.status_code == 200
    assert all(v["client_id"] == "C002" for v in resp.json())


async def test_get_analytics_returns_all_four_sections(client: AsyncClient) -> None:
    await _seed_happy_path(client)
    resp = await client.get("/api/v1/analytics", headers=auth_header())
    assert resp.status_code == 200
    body = resp.json()
    # Four required top-level keys (SPEC §4).
    for key in (
        "top_traded_isins",
        "avg_holding_time_per_client",
        "most_volatile_client",
        "isin_concentration",
    ):
        assert key in body

    # Value assertions — proves the data is correctly threaded through the
    # whole pipeline, not just that the response shape is right.

    # Top traded ISIN should be ISIN_A (2 transactions: buy + sell).
    top = {entry["isin"]: entry["transaction_count"] for entry in body["top_traded_isins"]}
    assert top["ISIN_A"] == 2

    # C001 has exactly one completed trade (bought day 1, sold day 2 → 1 day).
    holding = {
        entry["client_id"]: entry["avg_holding_days"]
        for entry in body["avg_holding_time_per_client"]
    }
    assert float(holding["C001"]) == pytest.approx(1.0)
    # C002 only attempted a SELL_BEFORE_BUY — no completed trades → null.
    assert holding["C002"] is None


# ── upload history / last-viewed semantics (the ADR 016 surface) ─────────────


async def test_second_upload_updates_last_viewed_for_same_user(client: AsyncClient) -> None:
    # First upload
    first = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(_happy_path_rows())),
        headers=auth_header(),
    )
    first_id = first.json()["upload_id"]

    # Second upload (same user)
    second = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(_happy_path_rows())),
        headers=auth_header(),
    )
    second_id = second.json()["upload_id"]
    assert second_id != first_id

    # The user's last_viewed_upload_id should now point at the *second* upload.
    listing = await client.get("/api/v1/uploads", headers=auth_header())
    by_id = {item["id"]: item for item in listing.json()}
    assert by_id[second_id]["is_last_viewed"] is True
    assert by_id[first_id]["is_last_viewed"] is False


async def test_put_last_viewed_switches_data_instantly(client: AsyncClient) -> None:
    first = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(_happy_path_rows())),
        headers=auth_header(),
    )
    first_id = first.json()["upload_id"]
    # Second upload moves "last viewed" forward.
    await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(_happy_path_rows())),
        headers=auth_header(),
    )

    # Switch back to the first upload.
    switch = await client.put(
        "/api/v1/users/me/last-viewed",
        json={"upload_id": first_id},
        headers=auth_header(),
    )
    assert switch.status_code == 200
    assert switch.json()["upload_id"] == first_id

    # GET /uploads now reflects the switch.
    listing = await client.get("/api/v1/uploads", headers=auth_header())
    by_id = {item["id"]: item for item in listing.json()}
    assert by_id[first_id]["is_last_viewed"] is True


async def test_put_last_viewed_unknown_upload_returns_404(client: AsyncClient) -> None:
    # No uploads exist yet, but the user gets auto-created on first request.
    resp = await client.put(
        "/api/v1/users/me/last-viewed",
        json={"upload_id": 99999},
        headers=auth_header(),
    )
    assert resp.status_code == 404


async def test_two_users_see_same_uploads_but_independent_last_viewed(client: AsyncClient) -> None:
    # Alice uploads two files.
    alice_first = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(_happy_path_rows())),
        headers=auth_header(DEFAULT_USER_EMAIL),
    )
    alice_first_id = alice_first.json()["upload_id"]
    alice_second = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(_happy_path_rows())),
        headers=auth_header(DEFAULT_USER_EMAIL),
    )
    alice_second_id = alice_second.json()["upload_id"]

    # Bob arrives. He should see both of Alice's uploads in the shared pool.
    bob_listing = await client.get("/api/v1/uploads", headers=auth_header(OTHER_USER_EMAIL))
    assert bob_listing.status_code == 200
    bob_ids = {item["id"] for item in bob_listing.json()}
    assert {alice_first_id, alice_second_id} <= bob_ids

    # Bob's last_viewed is None (he hasn't picked one) — all is_last_viewed flags are False.
    assert all(item["is_last_viewed"] is False for item in bob_listing.json())

    # Bob picks Alice's first upload.
    await client.put(
        "/api/v1/users/me/last-viewed",
        json={"upload_id": alice_first_id},
        headers=auth_header(OTHER_USER_EMAIL),
    )

    # Now Bob's listing flags alice_first as his current view; Alice's listing
    # is unchanged (still flagging alice_second as her current view).
    bob_listing = await client.get("/api/v1/uploads", headers=auth_header(OTHER_USER_EMAIL))
    alice_listing = await client.get("/api/v1/uploads", headers=auth_header(DEFAULT_USER_EMAIL))
    bob_by_id = {item["id"]: item for item in bob_listing.json()}
    alice_by_id = {item["id"]: item for item in alice_listing.json()}

    assert bob_by_id[alice_first_id]["is_last_viewed"] is True
    assert bob_by_id[alice_second_id]["is_last_viewed"] is False
    assert alice_by_id[alice_second_id]["is_last_viewed"] is True
    assert alice_by_id[alice_first_id]["is_last_viewed"] is False


async def test_returning_user_on_fresh_client_sees_last_viewed_restored(
    app: FastAPI,
) -> None:
    """
    SPEC §7: "Returning user (same email on a fresh device) sees their
    last_viewed_upload_id restored."

    Instantiates two independent `AsyncClient`s against the same app. The
    first uploads as alice; the second — created from scratch, no shared
    state — sends only her email and reads her preferences back. Proves
    that identity follows the email, not the HTTP client object.
    """
    transport = ASGITransport(app=app)

    # First "device": Alice uploads.
    async with AsyncClient(transport=transport, base_url="http://test") as cli1:
        upload = await cli1.post(
            "/api/v1/upload-transactions",
            files=upload_files(make_xlsx(_happy_path_rows())),
            headers=auth_header(),
        )
        assert upload.status_code == 200
        upload_id = upload.json()["upload_id"]

    # Second "device": brand-new client, same email. Should see Alice's
    # last_viewed_upload_id pointing at the upload she made on the first.
    async with AsyncClient(transport=transport, base_url="http://test") as cli2:
        listing = await cli2.get("/api/v1/uploads", headers=auth_header())
        assert listing.status_code == 200
        items = listing.json()
        assert len(items) == 1
        assert items[0]["id"] == upload_id
        assert items[0]["is_last_viewed"] is True


async def test_get_uploads_for_user_with_no_uploads_returns_empty_list(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/v1/uploads", headers=auth_header())
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_clients_for_user_with_no_active_upload_returns_empty(
    client: AsyncClient,
) -> None:
    """A brand-new user (no last_viewed_upload_id) gets an empty client list, not a 500."""
    resp = await client.get("/api/v1/clients", headers=auth_header())
    assert resp.status_code == 200
    assert resp.json() == []


# ── helpers ──────────────────────────────────────────────────────────────────


async def _seed_happy_path(client: AsyncClient) -> int:
    """POST a happy-path upload and return the new upload_id."""
    resp = await client.post(
        "/api/v1/upload-transactions",
        files=upload_files(make_xlsx(_happy_path_rows())),
        headers=auth_header(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["upload_id"]
