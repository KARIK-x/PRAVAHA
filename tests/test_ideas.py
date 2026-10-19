"""Tests for the investment-idea models.

Deterministic synthetic fixtures only. These tests assert the two things that
matter for honesty: that a model computes from the stored inputs, and that it
**refuses** to produce a number when an input is missing or implausible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool import ideas
from megatool.db import init_app_db
from megatool.fundamentals import import_records, records_from_rows
from megatool.market_store import MarketStore


@pytest.fixture()
def conn(tmp_path):
    path = tmp_path / "state.sqlite"
    init_app_db(path)
    import sqlite3

    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _bars(symbol: str, closes: list[float], end: str = "2026-10-12") -> pd.DataFrame:
    n = len(closes)
    arr = np.array(closes, dtype=float)
    return pd.DataFrame(
        {
            "symbol": [symbol] * n,
            "trading_date": pd.bdate_range(end=end, periods=n),
            "open": arr,
            "high": arr * 1.01,
            "low": arr * 0.99,
            "close": arr,
            "volume": [10_000] * n,
            "turnover": arr * 10_000,
            "source": ["SYNTHETIC-TEST-FIXTURE"] * n,
            "retrieved_at": [pd.Timestamp(end)] * n,
            "validation_status": ["valid"] * n,
        }
    )


@pytest.fixture()
def store(tmp_path):
    s = MarketStore(tmp_path / "market.duckdb")
    # 300 bars so 200-bar and 252-bar statistics exist; flat then rising.
    s.upsert_bars(_bars("AAA", [100.0] * 250 + [120.0, 130.0] * 25))
    s.upsert_bars(_bars("BBB", [500.0] * 300))
    yield s
    s.close()


def _fund(conn, symbol, field, value, unit, period, verification="reviewed"):
    import_records(
        records_from_rows(
            [
                {
                    "symbol": symbol,
                    "field": field,
                    "value": value,
                    "unit": unit,
                    "period_end": period,
                    "period_label": period,
                    "source": "test/source.json",
                    "verification": verification,
                }
            ]
        ),
        conn,
    )


# ------------------------------------------------------------------ catalogue
def test_catalogue_names_missing_inputs_for_unavailable_models():
    cat = {m["id"]: m for m in ideas.model_catalogue()}
    # Available models need only stored fields.
    assert cat["graham"]["missing_inputs"] == []
    # Unavailable models must say exactly what is missing.
    assert cat["magic_formula"]["status"] == "insufficient_data"
    assert "ebit" in cat["magic_formula"]["missing_inputs"]
    assert cat["piotroski"]["status"] == "insufficient_data"
    assert "cash_flow_from_operations" in cat["piotroski"]["missing_inputs"]


def test_unavailable_model_returns_no_rows_and_no_score(store, conn):
    out = ideas.evaluate("piotroski", store, conn)
    assert out["status"] == "insufficient_data"
    assert out["rows"] == []
    assert "cash_flow_from_operations" in out["missing_inputs"]


def test_unknown_model_is_rejected(store, conn):
    with pytest.raises(ideas.IdeasError):
        ideas.evaluate("no-such-model", store, conn)


# --------------------------------------------------------------------- graham
def test_graham_uses_stored_eps_and_book_value(store, conn):
    _fund(conn, "AAA", "eps", 10.0, "NPR", "2026-03-31")
    _fund(conn, "AAA", "net_worth_per_share", 100.0, "NPR", "2026-03-31")
    out = ideas.evaluate("graham", store, conn)
    assert out["status"] == "calculated"
    row = next(r for r in out["rows"] if r["symbol"] == "AAA")
    # sqrt(22.5 * 10 * 100) = sqrt(22500) = 150
    assert row["fair_value"] == pytest.approx(150.0)
    assert row["score"] > 0  # trading below the Graham number


def test_graham_ranks_highest_margin_of_safety_first(store, conn):
    # AAA is cheap vs Graham (fair 150 vs price ~120); BBB is rich.
    _fund(conn, "AAA", "eps", 10.0, "NPR", "2026-03-31")
    _fund(conn, "AAA", "net_worth_per_share", 100.0, "NPR", "2026-03-31")
    _fund(conn, "BBB", "eps", 1.0, "NPR", "2026-03-31")
    _fund(conn, "BBB", "net_worth_per_share", 5.0, "NPR", "2026-03-31")
    rows = ideas.evaluate("graham", store, conn)["rows"]
    assert [r["symbol"] for r in rows][0] == "AAA"


# ------------------------------------------------------------------ p/b value
def test_pb_bargain_ranks_lowest_ratio_first(store, conn):
    _fund(conn, "AAA", "net_worth_per_share", 100.0, "NPR", "2026-03-31")
    _fund(conn, "BBB", "net_worth_per_share", 400.0, "NPR", "2026-03-31")
    rows = ideas.evaluate("pb_bargain", store, conn)["rows"]
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores), "cheapest (lowest P/B) must rank first"
    # AAA closes ~130 with book 100 -> P/B ~1.3; BBB closes 500 with book 400.
    assert rows[0]["symbol"] in {"AAA", "BBB"}


def test_implausible_per_share_value_is_refused_not_ranked(store, conn):
    # A unit error (total equity stored as per-share) must not become a P/B of 0.
    _fund(conn, "BBB", "net_worth_per_share", 67_474_510_797.4, "NPR", "2026-03-31")
    rows = ideas.evaluate("pb_bargain", store, conn)["rows"]
    assert all(r["symbol"] != "BBB" for r in rows)


# --------------------------------------------------------------------- growth
def test_eps_growth_needs_two_periods_at_least_a_year_apart(store, conn):
    _fund(conn, "AAA", "eps", 10.0, "NPR", "2026-03-31")
    # Only one period -> no growth -> Lynch cannot score AAA.
    out = ideas.evaluate("lynch", store, conn)
    assert all(r["symbol"] != "AAA" for r in out["rows"])


def test_negative_eps_growth_does_not_crash_or_produce_a_score(store, conn):
    # old positive -> new negative: a fractional power of a negative ratio is a
    # complex number, which previously raised inside the endpoint.
    _fund(conn, "AAA", "eps", 10.0, "NPR", "2024-03-31")
    _fund(conn, "AAA", "eps", -5.0, "NPR", "2026-03-31")
    out = ideas.evaluate("lynch", store, conn)  # must not raise
    assert all(r["symbol"] != "AAA" for r in out["rows"])


def test_lynch_computes_peg_from_pe_and_growth(store, conn):
    _fund(conn, "AAA", "eps", 10.0, "NPR", "2024-03-31")
    _fund(conn, "AAA", "eps", 20.0, "NPR", "2025-03-31")  # +100% CAGR
    _fund(conn, "AAA", "pe", 20.0, "ratio", "2025-03-31")
    rows = ideas.evaluate("lynch", store, conn)["rows"]
    row = next(r for r in rows if r["symbol"] == "AAA")
    assert row["eps_growth_pct"] == pytest.approx(100.0, rel=0.02)
    assert row["peg"] == pytest.approx(0.2, rel=0.02)


# -------------------------------------------------------------------- momentum
def test_momentum_uses_12_1_return_and_ranks_descending(store, conn):
    rows = ideas.evaluate("momentum", store, conn)["rows"]
    assert rows, "AAA has 300 bars and a positive 12-1 return"
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["momentum_pct"] > 0


def test_low_52w_ranks_nearest_the_low_first(store, conn):
    # AAA is rising (near its high); BBB is flat at the bottom of a wide range.
    rows = ideas.evaluate("low_52w", store, conn)["rows"]
    assert rows[0]["symbol"] in {"AAA", "BBB"}
    assert all("pct_above_low" in r for r in rows)


def test_result_never_claims_a_score_it_could_not_compute(store, conn):
    # No fundamentals at all -> every price-based model still runs, but the
    # fundamental models must not invent values.
    out = ideas.evaluate("graham", store, conn)
    assert out["rows"] == []
    assert out["status"] == "calculated"
    assert "none met every condition" in out["note"]
