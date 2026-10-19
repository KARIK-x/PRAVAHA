"""Portfolio ledger and valuation tests (throwaway SQLite + DuckDB)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from megatool.db import init_app_db
from megatool.market_store import MarketStore
from megatool.portfolio import (
    PortfolioError,
    add_manual_position,
    add_transaction,
    cash_flows,
    delete_transaction,
    derive_positions,
    list_transactions,
    remove_manual_position,
    value_portfolio,
)

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "state.sqlite"
    init_app_db(path)
    return path


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


# ----------------------------------------------------------------- validation
def test_missing_symbol_rejected(db):
    with pytest.raises(PortfolioError, match="symbol is required"):
        add_transaction({"symbol": "  ", "side": "buy", "quantity": 1, "price": 10}, db)


def test_bad_side_rejected(db):
    with pytest.raises(PortfolioError, match="side must be one of"):
        add_transaction({"symbol": "AAA", "side": "hold", "quantity": 1, "price": 10}, db)


@pytest.mark.parametrize("qty", [0, -5, 2.5, "lots"])
def test_bad_quantity_rejected(db, qty):
    with pytest.raises(PortfolioError):
        add_transaction({"symbol": "AAA", "side": "buy", "quantity": qty, "price": 10}, db)


def test_non_positive_price_rejected(db):
    with pytest.raises(PortfolioError, match="price must be > 0"):
        add_transaction({"symbol": "AAA", "side": "buy", "quantity": 1, "price": 0}, db)


def test_negative_fees_rejected(db):
    with pytest.raises(PortfolioError, match="cannot be negative"):
        add_transaction(
            {"symbol": "AAA", "side": "buy", "quantity": 1, "price": 10, "fees": -1}, db
        )


def test_unparseable_timestamp_rejected(db):
    with pytest.raises(PortfolioError, match="not an ISO timestamp"):
        add_transaction(
            {
                "symbol": "AAA",
                "side": "buy",
                "quantity": 1,
                "price": 10,
                "traded_at": "last Tuesday",
            },
            db,
        )


def test_symbol_is_normalised_to_upper_case(db):
    tx = add_transaction({"symbol": "  nabil ", "side": "buy", "quantity": 1, "price": 10}, db)
    assert tx.symbol == "NABIL"
    assert list_transactions(db_path=db)[0].symbol == "NABIL"


# ---------------------------------------------------------------- derivation
def test_avg_cost_includes_fees(db):
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "fees": 20,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    p = derive_positions(db)[0]
    # (10*100 + 20) / 10 = 102
    assert p.avg_cost == pytest.approx(102.0)
    assert p.quantity == 10
    assert p.origin == "transactions"


def test_second_buy_averages_costs(db):
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 200,
            "traded_at": "2026-01-02T10:00:00",
        },
        db,
    )
    p = derive_positions(db)[0]
    assert p.avg_cost == pytest.approx(150.0)
    assert p.quantity == 20


def test_sell_realises_pnl_and_shrinks_position(db):
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    add_transaction(
        {
            "symbol": "AAA",
            "side": "sell",
            "quantity": 5,
            "price": 120,
            "traded_at": "2026-01-05T10:00:00",
        },
        db,
    )
    p = derive_positions(db)[0]
    assert p.quantity == 5
    assert p.avg_cost == pytest.approx(100.0)
    assert p.realized_pnl == pytest.approx(100.0)  # (120-100) * 5


def test_sell_fees_reduce_realised_pnl(db):
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    add_transaction(
        {
            "symbol": "AAA",
            "side": "sell",
            "quantity": 10,
            "price": 100,
            "fees": 30,
            "traded_at": "2026-01-05T10:00:00",
        },
        db,
    )
    p = derive_positions(db)[0]
    assert p.realized_pnl == pytest.approx(-30.0)
    assert p.quantity == 0


def test_closing_everything_resets_avg_cost(db):
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    add_transaction(
        {
            "symbol": "AAA",
            "side": "sell",
            "quantity": 10,
            "price": 90,
            "traded_at": "2026-01-05T10:00:00",
        },
        db,
    )
    p = derive_positions(db)[0]
    assert p.quantity == 0
    assert p.avg_cost == 0.0
    assert p.realized_pnl == pytest.approx(-100.0)


def test_overselling_is_rejected(db):
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 5,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    with pytest.raises(PortfolioError, match="only 5 held"):
        add_transaction(
            {
                "symbol": "AAA",
                "side": "sell",
                "quantity": 6,
                "price": 110,
                "traded_at": "2026-01-02T10:00:00",
            },
            db,
        )


def test_deleted_transaction_is_removed_from_ledger(db):
    tx = add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 5,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    assert delete_transaction(tx.id, db) is True
    assert derive_positions(db) == []
    assert delete_transaction(99999, db) is False


def test_multiple_symbols_stay_separate(db):
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 1,
            "price": 10,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    add_transaction(
        {
            "symbol": "BBB",
            "side": "buy",
            "quantity": 2,
            "price": 20,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    out = derive_positions(db)
    assert {p.symbol for p in out} == {"AAA", "BBB"}


# ------------------------------------------------------------ manual positions
def test_manual_position_is_labelled(db):
    add_manual_position("CCC", 100, 50.0, "inherited", db)
    p = derive_positions(db)[0]
    assert p.origin == "manual"
    assert p.notes == "inherited"
    assert p.quantity == 100


def test_manual_position_rejected_when_ledger_has_trades(db):
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 1,
            "price": 10,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    with pytest.raises(PortfolioError, match="single source of truth"):
        add_manual_position("AAA", 10, 10.0, db_path=db)


def test_manual_and_ledger_conflict_is_flagged_not_merged(db):
    # Insert the manual row directly to simulate pre-existing conflicting data.
    from megatool.db import get_conn, now_iso

    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 5,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    with get_conn(db) as conn:
        conn.execute(
            "INSERT INTO portfolio_positions (symbol, quantity, avg_cost, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            ("AAA", 999, 1.0, now_iso(), now_iso()),
        )
    p = derive_positions(db)[0]
    assert p.quantity == 5  # the ledger wins
    assert any("manual position row also exists" in f for f in p.flags)


def test_manual_position_can_be_removed(db):
    add_manual_position("CCC", 100, 50.0, db_path=db)
    assert remove_manual_position("ccc", db) is True
    assert derive_positions(db) == []


def test_bad_manual_position_inputs(db):
    with pytest.raises(PortfolioError, match="quantity"):
        add_manual_position("CCC", 0, 50.0, db_path=db)
    with pytest.raises(PortfolioError, match="avg_cost"):
        add_manual_position("CCC", 10, 0.0, db_path=db)


# ----------------------------------------------------------------- valuation
@pytest.fixture
def store(tmp_path):
    s = MarketStore(tmp_path / "market.duckdb")
    yield s
    s.close()


def test_valuation_marks_to_latest_stored_close(db, store):
    store.upsert_bars(_bars("AAA", [100.0, 110.0, 120.0]))
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    out = value_portfolio(store, db)
    p = out["positions"][0]
    assert p["last_price"] == 120.0
    assert p["market_value"] == pytest.approx(1200.0)
    assert p["unrealized_pnl"] == pytest.approx(200.0)
    assert out["summary"]["valued_market_value"] == pytest.approx(1200.0)
    assert out["data_as_of"] == "2026-01-05"
    assert out["live"] is False


def test_symbol_without_a_price_is_left_unvalued(db, store):
    store.upsert_bars(_bars("AAA", [100.0, 100.0]))
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    add_transaction(
        {
            "symbol": "ZZZ",
            "side": "buy",
            "quantity": 10,
            "price": 50,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    out = value_portfolio(store, db)
    by_symbol = {p["symbol"]: p for p in out["positions"]}
    assert by_symbol["ZZZ"]["market_value"] is None
    assert any("no stored price" in f for f in by_symbol["ZZZ"]["flags"])
    assert out["summary"]["unvalued_cost"] == pytest.approx(500.0)
    # ZZZ must never be counted in the valued total
    assert out["summary"]["valued_market_value"] == pytest.approx(1000.0)


def test_zero_close_never_marks_a_position_to_zero(db, store):
    """A zero close is not a price: valuing at it would invent a -100% day.

    The stored row is preserved exactly as it came in; only the calculation
    refuses to treat 0 as a market value (B-21 / register R1 leaves the
    policy question open - this test pins the unambiguous safety property).
    """
    store.upsert_bars(_bars("AAA", [100.0, 110.0, 0.0]))
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    out = value_portfolio(store, db)
    p = out["positions"][0]
    assert p["market_value"] is None
    assert p["last_price"] is None
    assert p["weight_pct"] is None
    assert any("not a usable price" in f for f in p["flags"])
    assert out["summary"]["valued_market_value"] == 0.0
    assert out["summary"]["unvalued_cost"] == pytest.approx(1000.0)
    assert out["summary"]["unvalued_positions"] == 1
    # only the newest bar per symbol is considered, and its close is unusable:
    # there is no valuation date to report rather than a fabricated one
    assert out["data_as_of"] is None
    # and the historical row itself is untouched
    bars = store.get_bars("AAA")
    assert float(bars["close"].iloc[-1]) == 0.0


def test_zero_close_flag_is_distinct_from_a_missing_price(db, store):
    """Two different causes, two different explanations - not one vague flag."""
    store.upsert_bars(_bars("AAA", [100.0, 0.0]))
    for sym, price in (("AAA", 100), ("ZZZ", 50)):
        add_transaction(
            {
                "symbol": sym,
                "side": "buy",
                "quantity": 10,
                "price": price,
                "traded_at": "2026-01-01T10:00:00",
            },
            db,
        )
    out = value_portfolio(store, db)
    by_symbol = {p["symbol"]: p for p in out["positions"]}
    aaa_flags = " ".join(by_symbol["AAA"]["flags"])
    zzz_flags = " ".join(by_symbol["ZZZ"]["flags"])
    assert "not a usable price" in aaa_flags and "no stored price" not in aaa_flags
    assert "no stored price" in zzz_flags and "not a usable price" not in zzz_flags
    # both are unvalued, so the weights only ever describe valued positions
    assert by_symbol["AAA"]["market_value"] is None
    assert by_symbol["ZZZ"]["market_value"] is None


def test_negative_close_is_never_used_as_a_mark(db, store):
    # A negative close is flagged `invalid` at ingest and therefore filtered
    # from the read path; either way the position must not be marked to it.
    store.upsert_bars(_bars("AAA", [100.0, -5.0]))
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    out = value_portfolio(store, db)
    p = out["positions"][0]
    assert p["market_value"] is None
    assert any("left unvalued" in f for f in p["flags"])
    assert out["summary"]["valued_market_value"] == 0.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_close_never_becomes_a_mark(db, store, bad):
    """B-35: NaN and +/-infinity are not prices either.

    The zero/negative guards alone would let ``+inf`` through ``> 0`` and
    poison every portfolio total with infinity (which is not even valid
    JSON). All three must leave the position unvalued with a finite,
    serializable payload.
    """
    store.upsert_bars(_bars("AAA", [100.0, 105.0, bad]))
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    out = value_portfolio(store, db)
    p = out["positions"][0]
    assert p["market_value"] is None
    assert p["last_price"] is None
    assert p["weight_pct"] is None
    assert any("not a usable price" in f for f in p["flags"])
    assert out["summary"]["valued_market_value"] == 0.0
    assert out["summary"]["unvalued_cost"] == pytest.approx(1000.0)
    # every numeric field actually present in the payload must be finite
    assert math.isfinite(out["summary"]["unvalued_positions"])
    assert math.isfinite(out["summary"]["unvalued_cost"])


def test_concentration_warning(db, store):
    store.upsert_bars(_bars("AAA", [100.0, 100.0]))
    store.upsert_bars(_bars("BBB", [100.0, 100.0]))
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 90,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    add_transaction(
        {
            "symbol": "BBB",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    out = value_portfolio(store, db)
    assert out["summary"]["largest_weight_pct"] == pytest.approx(90.0)
    assert out["summary"]["concentration_warning"] is True
    assert out["summary"]["realized_pnl"] == 0.0


def test_empty_portfolio_is_reported_as_empty(db, store):
    out = value_portfolio(store, db)
    assert out["positions"] == []
    assert out["summary"]["open_positions"] == 0
    assert out["data_as_of"] is None
    assert "not a live quote" in out["note"]


def test_valuation_is_deterministic(db, store):
    store.upsert_bars(_bars("AAA", [100.0, 110.0]))
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 3,
            "price": 100,
            "traded_at": "2026-01-01T10:00:00",
        },
        db,
    )
    assert value_portfolio(store, db) == value_portfolio(store, db)


def test_numpy_sixty_bars_fixture_is_finite():
    # Guard against NaN sneaking into a fixture and poisoning valuation.
    closes = list(np.linspace(100, 150, 60))
    df = _bars("AAA", closes)
    assert np.isfinite(df["close"].to_numpy()).all()


# ------------------------------------------------------------------ cash flow
def test_cash_flow_empty_ledger_is_explicit_zeros(db):
    out = cash_flows(db_path=db)
    assert out["flows"] == []
    s = out["summary"]
    assert s["transactions"] == 0
    assert s["total_invested"] == 0
    assert s["total_proceeds"] == 0
    assert s["total_fees"] == 0
    assert s["net_cash_flow"] == 0
    assert s["per_symbol_net"] == {}
    # The distinction that keeps this honest: a trade-derived net is not a
    # cash balance.
    assert "not an account cash balance" in out["note"]


def test_cash_flow_buy_then_sell_signs_fees_and_cumulative(db):
    # Buy 100 @ 250 with 50 fees -> 25,050 out.
    add_transaction(
        {
            "symbol": "NABIL",
            "side": "buy",
            "quantity": 100,
            "price": 250,
            "fees": 50,
            "traded_at": "2026-01-02T10:00:00+00:00",
        },
        db_path=db,
    )
    # Sell 40 @ 300 with 30 fees -> 11,970 in.
    add_transaction(
        {
            "symbol": "NABIL",
            "side": "sell",
            "quantity": 40,
            "price": 300,
            "fees": 30,
            "traded_at": "2026-02-02T10:00:00+00:00",
        },
        db_path=db,
    )
    out = cash_flows(db_path=db)
    flows = out["flows"]
    assert [(f["side"], f["net"]) for f in flows] == [("buy", -25050.0), ("sell", 11970.0)]
    assert [f["gross"] for f in flows] == [25000.0, 12000.0]
    assert [f["cumulative"] for f in flows] == [-25050.0, -13080.0]
    s = out["summary"]
    assert s["total_invested"] == 25050.0
    assert s["total_proceeds"] == 11970.0
    assert s["total_fees"] == 80.0
    assert s["net_cash_flow"] == -13080.0
    assert s["per_symbol_net"] == {"NABIL": -13080.0}


def test_cash_flow_replays_in_ledger_order_not_insert_order(db):
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "traded_at": "2026-03-01T00:00:00+00:00",
        },
        db_path=db,
    )
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 5,
            "price": 100,
            "traded_at": "2026-01-01T00:00:00+00:00",
        },
        db_path=db,
    )
    out = cash_flows(db_path=db)
    assert [f["traded_at"][:10] for f in out["flows"]] == ["2026-01-01", "2026-03-01"]
    assert [f["cumulative"] for f in out["flows"]] == [-500.0, -1500.0]


def test_cash_flow_covers_multiple_symbols(db):
    # AAA: buy 10 @ 10 (100 out), sell 10 @ 20 (200 in) -> +100 net.
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 10,
            "traded_at": "2026-01-01T00:00:00+00:00",
        },
        db_path=db,
    )
    add_transaction(
        {
            "symbol": "AAA",
            "side": "sell",
            "quantity": 10,
            "price": 20,
            "traded_at": "2026-01-02T00:00:00+00:00",
        },
        db_path=db,
    )
    # BBB: buy 5 @ 10 with 5 fees -> -55 net.
    add_transaction(
        {
            "symbol": "BBB",
            "side": "buy",
            "quantity": 5,
            "price": 10,
            "fees": 5,
            "traded_at": "2026-01-03T00:00:00+00:00",
        },
        db_path=db,
    )
    s = cash_flows(db_path=db)["summary"]
    assert s["per_symbol_net"] == {"AAA": 100.0, "BBB": -55.0}
    assert s["total_fees"] == 5.0
    assert s["net_cash_flow"] == 45.0


def test_valuation_embeds_the_same_cash_flow_summary(db, store):
    add_transaction(
        {
            "symbol": "NABIL",
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "fees": 5,
            "traded_at": "2026-01-01T00:00:00+00:00",
        },
        db_path=db,
    )
    val = value_portfolio(store, db_path=db)
    assert val["cash_flow"] == cash_flows(db_path=db)["summary"]
    assert val["cash_flow"]["net_cash_flow"] == -1005.0
    # The original honesty statement must survive: no cash *balance* is modelled.
    assert "Cash balances are not modelled" in val["note"]
