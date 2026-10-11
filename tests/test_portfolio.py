"""Portfolio ledger and valuation tests (throwaway SQLite + DuckDB)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.db import init_app_db
from megatool.market_store import MarketStore
from megatool.portfolio import (
    PortfolioError,
    add_manual_position,
    add_transaction,
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
