"""The stored index series is actually *consumed*, honestly.

Two consumers are covered here:

1. the ``relative_strength`` ranking factor, which is measured against the
   official NEPSE composite index and nothing else (never a substitute proxy);
2. the ``/api/indices`` read-only endpoints that surface the supplied series.

Fixtures are synthetic and never presented as live evidence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore
from megatool.ranking import (
    RELATIVE_STRENGTH_KEY,
    IndexAvailability,
    RankConfig,
    build_factor_specs,
    index_availability,
    rank_universe,
)


def _frame(closes: np.ndarray, symbol: str = "AAA") -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=len(closes))
    return pd.DataFrame(
        {
            "symbol": symbol,
            "date": dates,
            "trading_date": dates,
            "open": closes,
            "high": closes * 1.02,
            "low": closes * 0.98,
            "close": closes,
            "volume": np.full(len(closes), 10_000.0),
        }
    )


def _benchmark(closes: np.ndarray) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=len(closes))
    return pd.DataFrame({"trading_date": dates, "close": closes})


# --------------------------------------------------------------- availability


def test_no_benchmark_is_unavailable_not_a_guess():
    status = index_availability(0, None, 60)
    assert status.available is False
    assert "composite index" in status.reason
    assert status.benchmark_return_60d is None


def test_short_benchmark_is_unavailable_with_the_measured_reason():
    status = index_availability(40, None, 60)
    assert status.available is False
    assert "40 bars" in status.reason and "60-bar floor" in status.reason


def test_uncomputable_benchmark_return_is_unavailable():
    status = index_availability(80, None, 60)
    assert status.available is False
    assert "could not be computed" in status.reason


def test_available_when_the_series_spans_the_window():
    status = index_availability(80, 0.12, 60)
    assert status.available is True
    assert status.reason == ""
    assert status.bars == 80
    assert status.benchmark_return_60d == pytest.approx(0.12)


def test_build_factor_specs_emits_a_data_driven_relative_strength():
    specs = build_factor_specs(index_status=index_availability(80, 0.05, 60))
    by_key = {s.key: s for s in specs}
    assert by_key[RELATIVE_STRENGTH_KEY].available is True
    assert by_key[RELATIVE_STRENGTH_KEY].weight == 0.0  # weightless by default


# ------------------------------------------------------------- the factor


def test_relative_strength_uses_the_composite_not_a_proxy():
    n = 80
    # AAA beats the index; BBB trails it; CCC matches it.
    bench = _benchmark(np.linspace(100.0, 110.0, n))  # +10% over the window
    frames = {
        "AAA": _frame(np.linspace(100.0, 140.0, n), "AAA"),  # +40%
        "BBB": _frame(np.linspace(100.0, 100.0, n), "BBB"),  # flat
        "CCC": _frame(np.linspace(100.0, 110.0, n), "CCC"),  # +10%
    }
    config = RankConfig(weights={RELATIVE_STRENGTH_KEY: 1.0})
    result = rank_universe(frames, config, benchmark=bench)
    assert RELATIVE_STRENGTH_KEY not in result.unavailable
    assert result.benchmark is not None
    assert result.benchmark["name"] == "NEPSE"
    assert result.benchmark["available"] is True
    # The excess-return ordering must be preserved: AAA > CCC > BBB.
    pct = {r.symbol: r.percentiles[RELATIVE_STRENGTH_KEY] for r in result.ranked}
    assert pct["AAA"] > pct["CCC"] > pct["BBB"]


def test_relative_strength_absent_without_a_benchmark_series():
    frames = {"AAA": _frame(np.linspace(100.0, 140.0, 80), "AAA")}
    result = rank_universe(frames, RankConfig())
    assert RELATIVE_STRENGTH_KEY in result.unavailable
    assert result.benchmark is None


def test_relative_strength_declines_a_too_short_benchmark():
    frames = {"AAA": _frame(np.linspace(100.0, 140.0, 80), "AAA")}
    result = rank_universe(frames, RankConfig(), benchmark=_benchmark(np.linspace(100, 101, 10)))
    assert RELATIVE_STRENGTH_KEY in result.unavailable
    assert "floor" in result.unavailable[RELATIVE_STRENGTH_KEY]


def test_benchmark_return_is_computed_over_the_same_window():
    n = 120
    # The index doubled long ago then went flat across the ranking window; the
    # factor must use the window, not the lifetime.
    idx = np.concatenate([np.linspace(50.0, 100.0, n - 63), np.full(63, 100.0)])
    frames = {"AAA": _frame(np.linspace(100.0, 100.0, n), "AAA")}
    result = rank_universe(
        frames, RankConfig(weights={RELATIVE_STRENGTH_KEY: 1.0}), benchmark=_benchmark(idx)
    )
    # Index window return ~0%, symbol window return 0% -> tiny or zero excess,
    # but crucially computed, not earned from the pre-window doubling.
    assert result.benchmark is not None
    assert result.benchmark["return_60d"] == pytest.approx(0.0, abs=1e-9)


# ------------------------------------------------------------------- the API


def _index_client(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    dates = pd.bdate_range("2026-01-01", periods=70)
    store.upsert_index_rows(
        [
            {"index_name": "NEPSE", "trading_date": d, "close": 2000.0 + i, "source": "fixture"}
            for i, d in enumerate(dates)
        ]
    )
    return store, create_app(store=store)


def test_indices_endpoint_lists_the_stored_series(tmp_path):
    store, app = _index_client(tmp_path)
    with TestClient(app) as c:
        d = c.get("/api/indices").json()
    assert d["count"] == 1
    assert d["series"][0]["name"] == "NEPSE"
    assert d["series"][0]["rows"] == 70
    assert d["benchmark"] == "NEPSE"
    assert d["benchmark_available"] is True
    assert "not a live feed" in d["source"]
    store.close()


def test_index_series_endpoint_returns_points(tmp_path):
    store, app = _index_client(tmp_path)
    with TestClient(app) as c:
        d = c.get("/api/indices/NEPSE").json()
    assert d["name"] == "NEPSE"
    assert d["rows_total"] == 70
    assert len(d["points"]) == 70
    assert set(d["points"][0]) == {"date", "close"}
    store.close()


def test_unknown_index_is_a_404_not_an_empty_success(tmp_path):
    store, app = _index_client(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/indices/DOES-NOT-EXIST")
    assert r.status_code == 404
    store.close()


def test_indices_endpoint_is_empty_when_no_series_stored(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.get("/api/indices").json()
    assert d["count"] == 0
    assert d["benchmark_available"] is False
    store.close()


def test_rank_endpoint_reports_the_composite_benchmark(tmp_path):
    """With an index series stored, /api/rank must use and disclose it."""
    store = MarketStore(tmp_path / "market.duckdb")
    n = 120
    dates = pd.bdate_range("2025-01-01", periods=n)
    for name, closes in (
        ("TEST1", np.linspace(100.0, 130.0, n)),
        ("TEST2", np.linspace(100.0, 105.0, n)),
    ):
        store.upsert_bars(
            pd.DataFrame(
                {
                    "symbol": name,
                    "trading_date": dates,
                    "open": closes,
                    "high": closes * 1.02,
                    "low": closes * 0.98,
                    "close": closes,
                    "volume": np.full(n, 10_000.0),
                    "turnover": closes * 10_000.0,
                    "percent_change": 1.0,
                    "source": "fixture",
                    "retrieved_at": pd.Timestamp("2026-10-11"),
                    "validation_status": "valid",
                }
            )
        )
    store.upsert_index_rows(
        [
            {
                "index_name": "NEPSE",
                "trading_date": d,
                "close": 2000.0 + i,
                "source": "fixture",
            }
            for i, d in enumerate(dates)
        ]
    )
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.post("/api/rank", json={"weights": {RELATIVE_STRENGTH_KEY: 1.0}}).json()
    assert d["benchmark"] is not None
    assert d["benchmark"]["available"] is True
    assert RELATIVE_STRENGTH_KEY not in d["unavailable"]
    store.close()


def test_index_availability_default_is_the_historical_behaviour():
    # A caller that passes nothing still gets the honest "no data" reason.
    status = index_availability(0, None, 0)
    assert isinstance(status, IndexAvailability)
    assert status.available is False


# ------------------------------------------- stock-vs-index relative strength
def _rs_client(tmp_path, *, stock_dates=None, index_dates=None, stock_closes=None):
    """A store with one stock and one index series on synthetic business days."""
    store = MarketStore(tmp_path / "market.duckdb")
    sd = stock_dates if stock_dates is not None else pd.bdate_range("2026-01-01", periods=90)
    idates = index_dates if index_dates is not None else sd
    sc = np.linspace(100.0, 160.0, len(sd)) if stock_closes is None else stock_closes
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": "AAA",
                "trading_date": sd,
                "open": sc,
                "high": sc * 1.01,
                "low": sc * 0.99,
                "close": sc,
                "volume": np.full(len(sd), 1000.0),
                "turnover": sc * 1000.0,
                "percent_change": 0.5,
                "source": "fixture",
                "retrieved_at": pd.Timestamp("2026-10-11"),
                "validation_status": "valid",
            }
        )
    )
    store.upsert_index_rows(
        [
            {"index_name": "NEPSE", "trading_date": d, "close": 2000.0, "source": "fixture"}
            for d in idates
        ]
    )
    return store, create_app(store=store)


def test_relative_strength_endpoint_reports_excess_return(tmp_path):
    store, app = _rs_client(tmp_path)
    with TestClient(app) as c:
        d = c.get("/api/bars/AAA/relative-strength", params={"window": 60}).json()
    assert d["available"] is True
    # Benchmark is flat, so the excess return equals the stock's own return.
    assert d["benchmark_return_pct"] == 0.0
    assert d["excess_return_pct"] == d["stock_return_pct"] > 0
    assert d["coverage"]["aligned_bars"] == 90
    assert d["coverage"]["stock_dates_without_benchmark"] == 0
    assert len(d["ratio_points"]) == 61
    assert d["ratio_points"][0]["ratio"] == 100.0
    assert "inner join" in d["calculation"]
    store.close()


def test_relative_strength_reports_missing_dates_not_filled(tmp_path):
    """Dates missing from the benchmark are counted, never forward-filled."""
    sd = pd.bdate_range("2026-01-01", periods=90)
    idates = sd.delete(range(0, 90, 3))  # drop every third benchmark date
    store, app = _rs_client(tmp_path, stock_dates=sd, index_dates=idates)
    with TestClient(app) as c:
        d = c.get("/api/bars/AAA/relative-strength", params={"window": 10}).json()
    assert d["coverage"]["aligned_bars"] == 60
    assert d["coverage"]["stock_dates_without_benchmark"] == 30
    assert d["coverage"]["benchmark_bars"] == 60
    store.close()


def test_relative_strength_unavailable_when_history_is_short(tmp_path):
    sd = pd.bdate_range("2026-01-01", periods=20)
    store, app = _rs_client(tmp_path, stock_dates=sd)
    with TestClient(app) as c:
        d = c.get("/api/bars/AAA/relative-strength", params={"window": 60, "min_bars": 2}).json()
    assert d["available"] is False
    assert "60-bar window" in d["unavailable_reason"]
    assert d["stock_return_pct"] is None
    assert d["ratio_points"]  # the ratio series still exists, clearly labelled
    store.close()


def test_relative_strength_unknown_benchmark_is_404(tmp_path):
    store, app = _rs_client(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/bars/AAA/relative-strength", params={"benchmark": "NOPE"})
    assert r.status_code == 404
    assert "NOPE" in r.json()["detail"]
    store.close()


def test_relative_strength_404s_on_unknown_symbol(tmp_path):
    store, app = _rs_client(tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/bars/ZZZ/relative-strength").status_code == 404
    store.close()


def test_screen_relative_strength_metric_uses_the_composite_benchmark(tmp_path):
    """The scanner metric is wired to the index, and unavailable without it."""
    from megatool.scanner import ScreenNode, run_screen

    store, app = _rs_client(tmp_path)
    tree = ScreenNode.from_dict(
        {"op": "AND", "conditions": [{"metric": "relative_strength", "operator": "gt", "value": 0}]}
    )
    results = run_screen(store, tree, ["AAA"], min_bars=2)
    assert len(results) == 1
    assert results[0].eligible is True
    assert results[0].passed is True
    assert any("relative_strength" in r for r in results[0].reasons)
    store.close()


def test_screen_relative_strength_is_ineligible_without_a_benchmark(tmp_path):
    from megatool.scanner import ScreenNode, run_screen

    store = MarketStore(tmp_path / "market.duckdb")
    sc = np.linspace(100.0, 160.0, 90)
    sd = pd.bdate_range("2026-01-01", periods=90)
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": "AAA",
                "trading_date": sd,
                "open": sc,
                "high": sc,
                "low": sc,
                "close": sc,
                "volume": np.full(90, 1000.0),
                "turnover": sc * 1000.0,
                "percent_change": 0.5,
                "source": "fixture",
                "retrieved_at": pd.Timestamp("2026-10-11"),
                "validation_status": "valid",
            }
        )
    )
    tree = ScreenNode.from_dict(
        {"op": "AND", "conditions": [{"metric": "relative_strength", "operator": "gt", "value": 0}]}
    )
    results = run_screen(store, tree, ["AAA"], min_bars=2)
    assert results[0].eligible is False
    combined = " ".join(results[0].reasons + results[0].failures + [results[0].note])
    assert "relative_strength unavailable" in combined
    store.close()
