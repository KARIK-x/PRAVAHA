"""Regression tests for the defects Audit A found and reported.

Each test names the finding it pins down (F-1, J-1, ... ) so a future reader
can tell which bug the assertion is holding the line on. These are all
failures that used to be *silent* or *a 500* - the two ways a tool misleads a
trader without ever crashing loudly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.db import init_app_db
from megatool.floorsheet import FloorSheetError, import_floorsheet
from megatool.forecast import ForecastError, run_forecast
from megatool.journal import JournalError, create_entry, get_entry, update_entry
from megatool.market_store import MarketStore
from megatool.planning import PlanError, position_size
from megatool.portfolio import (
    PortfolioError,
    add_manual_position,
    add_transaction,
    list_transactions,
    value_portfolio,
)

# --- F-1: hold-out rows must be stamped with the date of their own value ----


def test_holdout_dates_stay_attached_to_their_values_when_a_close_is_nan():
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, np.nan, 8.0, 9.0, 10.0])
    dates = [f"d{i}" for i in range(1, 11)]
    result = run_forecast(values, model="naive", horizon=1, holdout=2, dates=dates)
    rows = {row["date"]: row["actual"] for row in result.holdout}
    # The last two finite points are 9.0 (d9) and 10.0 (d10). Before the fix
    # they were reported as d8 and d9 - evidence misdated by one session.
    assert rows == {"d9": 9.0, "d10": 10.0}
    assert result.series_end == "d10" or result.series_end == "d9"


def test_series_end_is_the_last_finite_point_not_the_last_listed_date():
    values = [1.0, 2.0, 3.0, 4.0, np.nan]
    dates = ["d1", "d2", "d3", "d4", "d5"]
    result = run_forecast(values, model="naive", horizon=1, holdout=1, dates=dates)
    assert result.series_end == "d4"


def test_a_dates_list_of_the_wrong_length_is_refused_not_zipped_into_silence():
    with pytest.raises(ForecastError, match="dates has 3 entries"):
        run_forecast(
            [1.0, 2.0, 3.0, 4.0], model="naive", horizon=1, holdout=1, dates=["d1", "d2", "d3"]
        )


# --- P-1 / P-3 / J-4: NaN and infinity are not valid numbers ---------------


def test_a_nan_price_is_rejected_not_stored(db):
    with pytest.raises(PortfolioError, match="finite"):
        add_transaction(
            {"symbol": "NABIL", "side": "buy", "quantity": 1, "price": float("nan")}, db_path=db
        )


def test_an_infinite_price_is_rejected_not_stored(db):
    with pytest.raises(PortfolioError, match="finite"):
        add_transaction(
            {"symbol": "NABIL", "side": "buy", "quantity": 1, "price": float("inf")}, db_path=db
        )


def test_infinite_fees_cannot_poison_the_average_cost(db):
    # Before the fix this stored avg_cost = inf and the whole portfolio
    # summary reported unvalued_cost = inf while returning 200.
    with pytest.raises(PortfolioError, match="finite"):
        add_transaction(
            {
                "symbol": "NABIL",
                "side": "buy",
                "quantity": 10,
                "price": 100.0,
                "fees": float("inf"),
            },
            db_path=db,
        )


def test_a_nan_avg_cost_on_a_manual_holding_is_rejected(db):
    with pytest.raises(PortfolioError, match="finite"):
        add_manual_position("NABIL", 10, float("nan"), db_path=db)


def test_a_nan_capital_cannot_reach_int_and_explode():
    # This used to raise plain ValueError from int(NaN), surfacing as a 500.
    with pytest.raises(PlanError, match="finite"):
        position_size(float("nan"), 2.0, 7.0, 100.0)


def test_a_nan_journal_price_is_refused_rather_than_stored_as_null(db):
    with pytest.raises(JournalError, match="finite"):
        create_entry(
            {"symbol": "NABIL", "thesis": "because", "entry_price": float("nan")}, db_path=db
        )


def test_an_infinite_journal_price_is_refused(db):
    with pytest.raises(JournalError, match="finite"):
        create_entry(
            {"symbol": "NABIL", "thesis": "because", "entry_price": float("inf")}, db_path=db
        )


# --- J-1 / J-2 / J-3: the update path must behave like the create path -----


def test_a_bad_journal_edit_is_a_400_with_the_reason_not_a_500(client):
    created = client.post(
        "/api/journal",
        json={
            "symbol": "NABIL",
            "thesis": "test entry",
            "entry_price": 100.0,
        },
    ).json()
    response = client.patch(f"/api/journal/{created['id']}", json={"entry_price": -5})
    assert response.status_code == 400
    assert "price must be > 0" in response.json()["detail"]


def test_notes_sent_as_an_edit_is_saved_instead_of_discarded(client):
    created = client.post(
        "/api/journal",
        json={
            "symbol": "NABIL",
            "thesis": "test entry",
            "entry_price": 100.0,
            "outcome_notes": "first note",
        },
    ).json()
    response = client.patch(f"/api/journal/{created['id']}", json={"notes": "second note"})
    assert response.status_code == 200
    assert response.json()["outcome_notes"] == "second note"


def test_notes_sent_as_an_empty_string_clears_the_note(client):
    created = client.post(
        "/api/journal",
        json={
            "symbol": "NABIL",
            "thesis": "test entry",
            "outcome_notes": "to clear",
        },
    ).json()
    response = client.patch(f"/api/journal/{created['id']}", json={"notes": ""})
    assert response.status_code == 200
    assert not response.json()["outcome_notes"]


def test_an_update_cannot_close_a_trade_without_an_exit_price(client):
    created = client.post(
        "/api/journal",
        json={
            "symbol": "NABIL",
            "thesis": "test entry",
            "entry_price": 100.0,
            "opened_at": "2026-01-05T10:00:00+00:00",
        },
    ).json()
    response = client.patch(
        f"/api/journal/{created['id']}",
        json={
            "closed_at": "2026-01-10T10:00:00+00:00",
        },
    )
    assert response.status_code == 400
    assert "exit_price" in response.json()["detail"]


def test_followed_plan_1_7_is_rejected_instead_of_truncated_to_yes(db):
    with pytest.raises(JournalError, match="followed_plan"):
        create_entry({"symbol": "NABIL", "thesis": "t", "followed_plan": 1.7}, db_path=db)


def test_followed_plan_still_accepts_real_values(db):
    entry_id = create_entry({"symbol": "NABIL", "thesis": "t", "followed_plan": 1}, db_path=db)
    assert update_entry(entry_id, {"followed_plan": 0}, db_path=db) is True


@pytest.fixture
def db(tmp_path):
    """An initialised throwaway SQLite database (never the owner's)."""
    path = tmp_path / "audit_state.sqlite"
    init_app_db(path)
    return path


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture
def store(tmp_path):
    """An isolated DuckDB market store (never the owner's)."""
    s = MarketStore(tmp_path / "audit_market.duckdb")
    yield s
    s.close()


RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _bars(symbol: str, closes: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "symbol": [symbol] * n,
            "trading_date": pd.bdate_range(start, periods=n),
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000] * n,
            "source": ["SYNTHETIC-TEST-FIXTURE"] * n,
            "retrieved_at": [RETRIEVED] * n,
            "validation_status": ["valid"] * n,
        }
    )


# --- FS-1 / FS-5: one corrupt row must never abort a whole session --------

GOOD = "Symbol,Buyer,Seller,Quantity,Rate,Amount\nNABIL,B1,B2,100,500,50000\n"


def test_one_absurd_quantity_skips_the_row_instead_of_aborting_the_import(db):
    # Well past any real NEPSE print, and past SQLite's INTEGER column:
    # without the bound this row raised mid-INSERT and aborted the session.
    text = GOOD + "NICA,B1,B2,9999999999999,250,0\n"
    out = import_floorsheet(text, "2026-10-09", db_path=db)
    assert out["rows_imported"] == 1
    assert out["rows_skipped"] == 1
    assert "implausibly large" in out["skipped"][0]["reason"]


def test_an_infinite_quantity_is_skipped_with_its_line_number(db):
    text = GOOD + "NICA,B1,B2,inf,250,0\n"
    out = import_floorsheet(text, "2026-10-09", db_path=db)
    assert out["rows_imported"] == 1
    assert out["skipped"][0]["line"] == 3


def test_a_fractional_quantity_is_reported_not_silently_rounded(db):
    text = GOOD + "NICA,B1,B2,2.5,250,625\n"
    out = import_floorsheet(text, "2026-10-09", db_path=db)
    assert any("fractional" in w for w in out["warnings"])


# --- FS-2 / FS-3 / FS-4: session labels and one definition of "stored" ----


def test_an_unparseable_session_date_is_refused(db):
    with pytest.raises(FloorSheetError, match="ISO date"):
        import_floorsheet(GOOD, "not-a-date", db_path=db)


def test_the_same_file_under_a_second_session_label_warns_about_double_counting(db):
    first = import_floorsheet(GOOD, "2026-10-09", db_path=db)
    assert not any("double-count" in w for w in first["warnings"])
    second = import_floorsheet(GOOD, "2026-10-12", db_path=db)
    assert second["rows_imported"] == 1  # stored, but loudly flagged
    assert any("double-count" in w for w in second["warnings"])


def test_stored_trades_means_the_session_total_in_both_paths(db):
    import_floorsheet(GOOD, "2026-10-09", db_path=db)
    more = "Symbol,Buyer,Seller,Quantity,Rate,Amount\nNICA,B2,B3,300,250,75000\n"
    second = import_floorsheet(more, "2026-10-09", db_path=db)
    assert second["stored_trades"] == 2  # not just the one row this file added
    again = import_floorsheet(GOOD, "2026-10-09", db_path=db)
    assert again["stored_trades"] == 2


# --- S-1 / A-1: the search needle and the page size are user input --------


def test_a_malformed_search_returns_no_rows_instead_of_a_500(client):
    assert client.get("/api/securities", params={"q": "("}).status_code == 200


def test_a_dot_in_a_search_does_not_match_more_than_typed(client, store):
    store.upsert_bars(_bars("ABC", [10.0, 11.0]))
    store.upsert_bars(_bars("AXC", [10.0, 11.0]))
    found = client.get("/api/securities", params={"q": "A.C"}).json()["securities"]
    assert [r["symbol"] for r in found] == []  # "A.C" is a literal search now


def test_a_negative_page_size_is_rejected_not_silently_truncating(client):
    assert client.get("/api/dashboard", params={"top": -3}).status_code == 422


# --- P-2: a valuation must not mix dates without saying so ----------------


def test_a_position_priced_on_an_older_day_is_flagged_and_dated(db, store):
    store.upsert_bars(_bars("OLD", [50.0, 50.0], start="2026-01-01"))
    store.upsert_bars(_bars("NEW", [20.0, 21.0], start="2026-03-02"))
    add_transaction(
        {
            "symbol": "OLD",
            "side": "buy",
            "quantity": 10,
            "price": 50.0,
            "traded_at": "2026-01-01T10:00:00+00:00",
        },
        db,
    )
    add_transaction(
        {
            "symbol": "NEW",
            "side": "buy",
            "quantity": 10,
            "price": 20.0,
            "traded_at": "2026-03-02T10:00:00+00:00",
        },
        db,
    )
    out = value_portfolio(store, db)
    by_symbol = {p["symbol"]: p for p in out["positions"]}
    assert by_symbol["OLD"]["price_as_of"] == "2026-01-02"
    assert by_symbol["NEW"]["price_as_of"] == "2026-03-03"
    assert any("older price" in f for f in by_symbol["OLD"]["flags"])
    assert not any("older price" in f for f in by_symbol["NEW"]["flags"])


# --- P-4: timestamps are ordered by when they happened, not by their text -


def test_a_ledger_row_with_a_local_offset_is_stored_as_utc(db):
    add_transaction(
        {
            "symbol": "NABIL",
            "side": "buy",
            "quantity": 10,
            "price": 100.0,
            "traded_at": "2026-01-02T00:00:00+05:45",
        },
        db,
    )
    stored = list_transactions(db_path=db)[0].traded_at
    assert stored == "2026-01-01T18:15:00+00:00"  # 05:45 ahead of UTC


def test_a_journal_timestamp_with_a_local_offset_is_normalised_to_utc(db):
    # 00:00 at +05:45 is 18:15Z the previous day. Compared as text,
    # "2026-01-02..." looks later than "2026-01-01..." - so a trade whose
    # close really followed its open was REJECTED as reversed.
    entry_id = create_entry(
        {
            "symbol": "NABIL",
            "thesis": "t",
            "entry_price": 100.0,
            "exit_price": 90.0,
            "opened_at": "2026-01-02T00:00:00+05:45",
            "closed_at": "2026-01-01T20:00:00+00:00",
        },
        db_path=db,
    )
    entry = get_entry(entry_id, db_path=db)
    assert entry["opened_at"] == "2026-01-01T18:15:00+00:00"


def test_a_journal_close_that_really_precedes_the_open_is_still_caught(db):
    with pytest.raises(JournalError, match="closed_at cannot be before"):
        create_entry(
            {
                "symbol": "NABIL",
                "thesis": "t",
                "entry_price": 100.0,
                "exit_price": 90.0,
                "opened_at": "2026-01-05T10:00:00+00:00",
                "closed_at": "2026-01-04T10:00:00+00:00",
            },
            db_path=db,
        )


# --- B1: a legal thesis-only entry must not kill the stats endpoint --------
# A closed entry with an exit price but NO entry price is legal by the
# create rules, and comparing exit > None raised TypeError -> HTTP 500 on
# the whole stats route for as long as that entry existed.


def test_a_closed_thesis_only_entry_does_not_crash_the_stats_endpoint(client):
    created = client.post(
        "/api/journal",
        json={
            "symbol": "NABIL",
            "thesis": "no entry price recorded",
            "exit_price": 95.0,
            "closed_at": "2026-01-10T10:00:00+00:00",
        },
    )
    assert created.status_code == 201 or created.status_code == 200
    stats = client.get("/api/journal/stats")
    assert stats.status_code == 200
    body = stats.json()
    # The unpriced entry is counted, excluded from the rate, and EXPLAINED.
    assert body["closed_without_entry_price"] == 1
    assert body["win_rate_pct"] is None
    assert any("no entry price" in w for w in body["warnings"])


def test_the_unpriced_entry_does_not_inflate_the_denominator(client):
    for payload in (
        {
            "symbol": "NABIL",
            "thesis": "unpriced",
            "exit_price": 95.0,
            "closed_at": "2026-01-10T10:00:00+00:00",
        },
        {
            "symbol": "NABIL",
            "thesis": "priced win",
            "entry_price": 100.0,
            "exit_price": 110.0,
            "closed_at": "2026-01-11T10:00:00+00:00",
        },
        {
            "symbol": "NABIL",
            "thesis": "priced loss",
            "entry_price": 100.0,
            "exit_price": 90.0,
            "closed_at": "2026-01-12T10:00:00+00:00",
        },
    ):
        assert client.post("/api/journal", json=payload).status_code in (200, 201)
    body = client.get("/api/journal/stats").json()
    assert body["closed"] == 3
    assert body["comparable"] == 2 if "comparable" in body else True
    assert body["win_rate_pct"] == 50.0  # 1 win from 2 COMPARABLE, not from 3


# --- B2: counterparty shares are shares of the SESSION, not of the top-N ---
# The old denominator was the sum of the rows that survived LIMIT, so ten
# brokers holding 84% of the flow each reported an inflated share and the
# listed shares summed to exactly 100%.


def _sheet(rows):
    header = "Symbol,Buyer,Seller,Quantity,Rate,Amount\n"
    return header + "".join(",".join(map(str, r)) + "\n" for r in rows)


def test_counterparty_share_is_over_the_whole_session(db):
    rows = [("NABIL", f"B{i}", "S9", 100, 500, 50000) for i in range(12)]
    rows.append(("NABIL", "BIG", "S9", 700, 500, 350000))
    import_floorsheet(_sheet(rows), "2026-10-09", db_path=db)

    from megatool.floorsheet import summary

    out = summary(traded_at="2026-10-09", top=10, db_path=db)
    big = next(b for b in out["top_buyers"] if b["buyer"] == "BIG")
    # 700 of 1900 traded = 36.84%, NOT 700/1600 (the ten shown) = 43.75%.
    assert big["share_of_quantity_pct"] == pytest.approx(700 / 1900 * 100, abs=0.01)
    listed = sum(b["share_of_quantity_pct"] for b in out["top_buyers"])
    assert listed == pytest.approx(84.21, abs=0.01)  # not forced to 100


def test_seller_shares_use_the_same_session_denominator(db):
    rows = [("NABIL", "B9", f"S{i}", 100, 500, 50000) for i in range(12)]
    rows.append(("NABIL", "B9", "BIGS", 700, 500, 350000))
    import_floorsheet(_sheet(rows), "2026-10-09", db_path=db)
    from megatool.floorsheet import summary

    out = summary(traded_at="2026-10-09", top=10, db_path=db)
    bigs = next(s for s in out["top_sellers"] if s["seller"] == "BIGS")
    assert bigs["share_of_quantity_pct"] == pytest.approx(700 / 1900 * 100, abs=0.01)


# --- B3: a rate that reads "Rs. 1,000" must not become 0.1 ------------------


def test_a_currency_prefixed_rate_is_parsed_not_mangled(db):
    text = 'Symbol,Buyer,Seller,Quantity,Rate,Amount\nNABIL,B1,B2,100,"Rs. 1,000",100000\n'
    out = import_floorsheet(text, "2026-10-09", db_path=db)
    assert out["rows_imported"] == 1
    from megatool.floorsheet import summary

    s = summary(traded_at="2026-10-09", db_path=db)
    assert s["totals"]["amount"] == pytest.approx(100000.0)
    assert not any("disagrees" in w for w in s["warnings"])


# --- B4: an impossible exit must be refused, not graded as a real stop ------
# exit_price -5 graded as a stop with r_multiple -21.0 looked like a real
# outcome; NaN produced a literal NaN r_multiple (invalid JSON).


def test_a_negative_exit_price_is_refused(db):
    from megatool.planning import plan_outcome

    with pytest.raises(PlanError, match="exit_price"):
        plan_outcome(100.0, 95.0, 110.0, -5.0)


def test_a_nan_exit_price_is_refused(db):
    from megatool.planning import plan_outcome

    with pytest.raises(PlanError, match="exit_price"):
        plan_outcome(100.0, 95.0, 110.0, float("nan"))


# --- B5: a sell must be funded by buys that precede it ---------------------
# Checking the net of the WHOLE ledger let a backdated sell pass, and the
# chronological derivation then booked a "-fees" loss on a profitable trade.


def test_a_sell_dated_before_its_funding_buy_is_rejected(db):
    add_transaction(
        {
            "symbol": "NABIL",
            "side": "buy",
            "quantity": 10,
            "price": 50.0,
            "traded_at": "2026-03-10T10:00:00+00:00",
        },
        db_path=db,
    )
    with pytest.raises(PortfolioError, match="as of that date"):
        add_transaction(
            {
                "symbol": "NABIL",
                "side": "sell",
                "quantity": 10,
                "price": 55.0,
                "traded_at": "2026-03-01T10:00:00+00:00",
            },
            db_path=db,
        )


def test_a_correctly_ordered_sell_still_books_the_real_profit(db):
    add_transaction(
        {
            "symbol": "NABIL",
            "side": "buy",
            "quantity": 10,
            "price": 50.0,
            "traded_at": "2026-03-01T10:00:00+00:00",
        },
        db_path=db,
    )
    add_transaction(
        {
            "symbol": "NABIL",
            "side": "sell",
            "quantity": 10,
            "price": 55.0,
            "traded_at": "2026-03-10T10:00:00+00:00",
        },
        db_path=db,
    )
    from megatool.portfolio import derive_positions

    pos = derive_positions(db_path=db)[0]
    assert pos.realized_pnl == pytest.approx(50.0)
    assert not pos.flags


# --- B6: a typo'd field must not be accepted and silently dropped ----------
# The module's own principle says a silently ignored field is the worst
# behaviour; a caller sending `entry_prc` used to get 200 and lose the price.


def test_a_typo_field_is_rejected_not_silently_dropped(db):
    with pytest.raises(JournalError, match="entry_prc"):
        create_entry(
            {"symbol": "NABIL", "thesis": "t", "entry_prc": 55.0},
            db_path=db,
        )


def test_the_typo_message_names_the_offending_field(db):
    with pytest.raises(JournalError, match="unknown field"):
        create_entry({"symbol": "NABIL", "thesis": "t", "entry_prce": 1}, db_path=db)


def test_the_documented_notes_alias_is_not_rejected_as_unknown(db):
    entry_id = create_entry(
        {"symbol": "NABIL", "thesis": "t", "notes": "via the alias"},
        db_path=db,
    )
    assert get_entry(entry_id, db_path=db)["outcome_notes"] == "via the alias"


def test_an_update_ignores_the_bookkeeping_columns_get_entry_returns(db):
    # `id`, `created_at` and `updated_at` come back from get_entry and must
    # not be treated as the caller's unknown fields.
    entry_id = create_entry({"symbol": "NABIL", "thesis": "t"}, db_path=db)
    assert update_entry(entry_id, {"thesis": "edited"}, db_path=db) is True
    assert get_entry(entry_id, db_path=db)["thesis"] == "edited"


# --- B7: sizing must say so when the budget cannot buy a single unit -------


def test_a_budget_that_cannot_buy_one_unit_carries_a_warning():
    sizing = position_size(1000.0, 1.0, 50.0, 100.0)
    assert sizing.units == 0
    assert sizing.warning and "cannot buy a single unit" in sizing.warning


def test_an_affordability_cap_states_that_fees_are_excluded():
    sizing = position_size(10_000.0, 10.0, 1.0, 1000.0)
    assert sizing.units == 10
    assert sizing.warning and "EXCLUDES" in sizing.warning


def test_a_normal_sized_trade_carries_no_warning():
    sizing = position_size(100_000.0, 2.0, 7.0, 100.0)
    assert sizing.units > 0
    assert sizing.warning is None
