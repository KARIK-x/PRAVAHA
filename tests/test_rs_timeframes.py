"""Multi-timeframe relative strength: exact arithmetic + endpoint contract.

The stock/index fixtures here are **synthetic** (business-day ranges with
hand-set closes); nothing in this file is live-market evidence. The live
behaviour of the same endpoint is separately pinned by tests/test_index_consumer.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore
from megatool.rs_timeframes import MAX_LOOKBACKS, parse_lookbacks, timeframe_rows

# ------------------------------------------------------------------ parsing


def test_parse_lookbacks_none_and_blank_is_none():
    assert parse_lookbacks(None) is None
    assert parse_lookbacks("") is None
    assert parse_lookbacks("   ") is None


def test_parse_lookbacks_valid_list_is_deduplicated_in_order():
    assert parse_lookbacks("20, 60,120,250") == [20, 60, 120, 250]
    assert parse_lookbacks("60,60,20") == [60, 20]


def test_parse_lookbacks_rejects_non_integers_and_bounds():
    with pytest.raises(ValueError, match="not an integer"):
        parse_lookbacks("60,abc")
    with pytest.raises(ValueError, match="out of bounds"):
        parse_lookbacks("1")
    with pytest.raises(ValueError, match="out of bounds"):
        parse_lookbacks("2001")
    with pytest.raises(ValueError, match="empty lookback"):
        parse_lookbacks("60,,20")


def test_parse_lookbacks_rejects_more_than_the_cap():
    values = ",".join(str(v) for v in range(10, 10 + MAX_LOOKBACKS + 1))
    with pytest.raises(ValueError, match=f"at most {MAX_LOOKBACKS} lookbacks"):
        parse_lookbacks(values)


# ----------------------------------------------------------------- arithmetic


def _merged(dates: pd.DatetimeIndex, stock: np.ndarray, bench: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trading_date": dates,
            "stock": stock,
            "bench": bench,
        }
    )


def test_timeframe_rows_returns_exact_percentages():
    # closes grow 1%/bar; the lookback-L return is therefore exactly
    # (1.01**L - 1) * 100 for every L, against ANY flat benchmark.
    n = 40
    dates = pd.bdate_range("2025-01-01", periods=n)
    stock = 100.0 * (1.01 ** np.arange(n))
    bench = np.full(n, 2000.0)
    rows = timeframe_rows(_merged(dates, stock, bench), [5, 20])
    by_lb = {r["lookback"]: r for r in rows}
    assert by_lb[5]["stock_return_pct"] == pytest.approx((1.01**5 - 1) * 100, abs=1e-3)
    assert by_lb[5]["benchmark_return_pct"] == 0.0
    assert by_lb[5]["excess_return_pct"] == pytest.approx((1.01**5 - 1) * 100, abs=1e-3)
    assert by_lb[20]["excess_return_pct"] == pytest.approx(by_lb[20]["stock_return_pct"], abs=1e-6)
    assert by_lb[5]["window_bars_used"] == 6
    assert by_lb[5]["base_date"] == dates[-6].date().isoformat()
    assert by_lb[5]["last_date"] == dates[-1].date().isoformat()


def test_timeframe_rows_underperformer_has_negative_excess():
    # stock falls while the index is flat: every row's excess must be negative.
    n = 30
    dates = pd.bdate_range("2025-01-01", periods=n)
    stock = 100.0 * (0.99 ** np.arange(n))
    bench = np.full(n, 1000.0)
    rows = timeframe_rows(_merged(dates, stock, bench), [5, 10, 20])
    for r in rows:
        assert r["available"] is True
        assert r["excess_return_pct"] < 0
        assert r["benchmark_return_pct"] == 0.0
        # difference of the two returned returns, to the printed precision
        assert r["excess_return_pct"] == pytest.approx(
            r["stock_return_pct"] - r["benchmark_return_pct"], abs=1e-6
        )


def test_timeframe_rows_outperformed_benchmark_has_positive_excess():
    n = 30
    dates = pd.bdate_range("2025-01-01", periods=n)
    stock = np.full(n, 100.0)
    bench = 5000.0 * (1.01 ** np.arange(n))
    rows = timeframe_rows(_merged(dates, stock, bench), [10])
    assert rows[0]["stock_return_pct"] == 0.0
    assert rows[0]["benchmark_return_pct"] == pytest.approx((1.01**10 - 1) * 100, abs=1e-3)
    assert rows[0]["excess_return_pct"] == pytest.approx(-(1.01**10 - 1) * 100, abs=1e-3)


def test_timeframe_rows_lookback_longer_than_history_is_unavailable_with_reason():
    n = 12
    dates = pd.bdate_range("2025-01-01", periods=n)
    rows = timeframe_rows(_merged(dates, np.linspace(100, 110, n), np.full(n, 999.0)), [20, 10])
    long, short = rows[0], rows[1]
    assert long["available"] is False
    assert "12 aligned dates" in long["unavailable_reason"]
    assert "needs at least 21" in long["unavailable_reason"]
    assert long["stock_return_pct"] is None and long["excess_return_pct"] is None
    # the shorter request still computes — availability is per-lookback
    assert short["available"] is True and short["window_bars_used"] == 11


def test_timeframe_rows_on_empty_frame_reports_each_row_unavailable():
    rows = timeframe_rows(pd.DataFrame({"trading_date": [], "stock": [], "bench": []}), [20, 60])
    assert [r["lookback"] for r in rows] == [20, 60]
    assert all(r["available"] is False for r in rows)
    assert all(r["unavailable_reason"] == "no dates are present in both series" for r in rows)


def test_timeframe_rows_excess_is_a_percentage_difference_not_annualised():
    # A 20-bar +10% stock against a 20-bar -10% index is +20 pp excess —
    # NOT (1.10/0.90 - 1) = +22.2% geometric and NOT annualised either.
    n = 21
    dates = pd.bdate_range("2025-01-01", periods=n)
    stock = np.linspace(100.0, 110.0, n)  # +10% exactly over 20 bars
    bench = np.linspace(2000.0, 1800.0, n)  # −10% exactly over 20 bars
    rows = timeframe_rows(_merged(dates, stock, bench), [20])
    assert rows[0]["stock_return_pct"] == pytest.approx(10.0, abs=1e-6)
    assert rows[0]["benchmark_return_pct"] == pytest.approx(-10.0, abs=1e-6)
    assert rows[0]["excess_return_pct"] == pytest.approx(20.0, abs=1e-6)


# ------------------------------------------------------------------- the API


def _rs_client(tmp_path, n_stock=90, n_index=90, index_close=2000.0):
    store = MarketStore(tmp_path / "market.duckdb")
    dates = pd.bdate_range("2026-01-01", periods=n_stock)
    stock = 100.0 * (1.01 ** np.arange(n_stock))
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": "AAA",
                "trading_date": dates,
                "open": stock,
                "high": stock * 1.01,
                "low": stock * 0.99,
                "close": stock,
                "volume": 1000.0,
                "turnover": stock * 1000.0,
                "percent_change": 0.5,
                "source": "fixture",
                "retrieved_at": pd.Timestamp("2026-10-11"),
                "validation_status": "valid",
            }
        )
    )
    idates = pd.bdate_range("2026-01-01", periods=n_index)
    store.upsert_index_rows(
        [
            {"index_name": "NEPSE", "trading_date": d, "close": index_close, "source": "fixture"}
            for d in idates
        ]
    )
    return store, create_app(store=store)


def test_endpoint_lookbacks_return_per_lookback_rows(tmp_path):
    store, app = _rs_client(tmp_path)
    with TestClient(app) as c:
        d = c.get(
            "/api/bars/AAA/relative-strength",
            params={"window": 60, "lookbacks": "5,20", "min_bars": 60},
        ).json()
    assert d["timeframes_calculation"]
    tf = {r["lookback"]: r for r in d["timeframes"]}
    assert tf[5]["available"] is True
    # stock compounds 1% per bar; index is flat at 2000 → excess ≡ stock return
    assert tf[5]["stock_return_pct"] == pytest.approx((1.01**5 - 1) * 100, abs=1e-3)
    assert tf[5]["benchmark_return_pct"] == 0.0
    assert tf[20]["excess_return_pct"] == pytest.approx(tf[20]["stock_return_pct"], abs=1e-6)
    # the single-window contract is unchanged at the same time
    assert d["available"] is True
    assert d["window"] == 60
    store.close()


def test_endpoint_without_lookbacks_keeps_the_old_shape(tmp_path):
    store, app = _rs_client(tmp_path)
    with TestClient(app) as c:
        d = c.get("/api/bars/AAA/relative-strength", params={"window": 60}).json()
    assert "timeframes" not in d
    store.close()


def test_endpoint_lookback_longer_than_history_is_reported_not_shortened(tmp_path):
    store, app = _rs_client(tmp_path, n_stock=30, n_index=30)
    with TestClient(app) as c:
        d = c.get(
            "/api/bars/AAA/relative-strength",
            params={"window": 10, "lookbacks": "5,250", "min_bars": 10},
        ).json()
    tf = {r["lookback"]: r for r in d["timeframes"]}
    assert tf[5]["available"] is True
    assert tf[250]["available"] is False
    assert "250-bar comparison" in tf[250]["unavailable_reason"]
    store.close()


@pytest.mark.parametrize(
    "bad",
    ["3.5", "60,abc", "1", "2001", "60,,20", "60,60,60,60,60,60,60"],
)
def test_endpoint_rejects_bad_lookback_lists_with_400(tmp_path, bad):
    store, app = _rs_client(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/bars/AAA/relative-strength", params={"lookbacks": bad})
    assert r.status_code == 400
    assert "lookback" in r.json()["detail"].lower()
    store.close()


def test_endpoint_deduplicates_repeated_lookbacks(tmp_path):
    store, app = _rs_client(tmp_path)
    with TestClient(app) as c:
        d = c.get(
            "/api/bars/AAA/relative-strength",
            params={"window": 10, "lookbacks": "10,10,20", "min_bars": 10},
        ).json()
    assert [r["lookback"] for r in d["timeframes"]] == [10, 20]
    store.close()
