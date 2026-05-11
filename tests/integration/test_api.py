"""
End-to-end integration tests for every endpoint in SPEC §4 and every
scenario in SPEC §7.

Each test goes through the real ASGI app via `httpx.AsyncClient` and the
real per-test PostgreSQL schema. There are no mocks of the DB layer or the
domain layer — these tests are the gate that proves all four prior PRs
compose correctly.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import (
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

    # ISIN_A: bought 10 @ 100, sold 10 @ 120 → realized 200, position 0
    assert by_isin["ISIN_A"]["realized_pnl"] == "200.000000"
    assert by_isin["ISIN_A"]["quantity"] == "0.000000"

    # ISIN_B: bought 5 @ 50, never sold → quantity 5, no realized PnL
    assert by_isin["ISIN_B"]["quantity"] == "5.000000"
    assert by_isin["ISIN_B"]["realized_pnl"] == "0.000000"


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
    # Top ISINs: each ISIN was traded at most twice — we should see at least one entry.
    assert len(body["top_traded_isins"]) >= 1


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
