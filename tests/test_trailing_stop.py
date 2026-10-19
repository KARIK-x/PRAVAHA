"""Trailing-stop engine: exact hand-checkable stop chains + endpoint contract.

All price fixtures are synthetic; nothing here is live market evidence.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore
from megatool.ta.trailing import TrailingError, trailing_stop

# ------------------------------------------------------------------ arithmetic


def test_pct_method_is_the_running_peak_close_scaled():
    close = [100.0, 110.0, 105.0, 120.0, 90.0]
    high = [c * 1.01 for c in close]
    low = [c * 0.99 for c in close]
    r = trailing_stop(high, low, close, "pct", pct=10.0)
    # peak closes: 100, 110, 110, 120, 120 → stops 90, 99, 99, 108, 108
    assert r["stops"] == [90.0, 99.0, 99.0, 108.0, 108.0]
    assert r["exited_index"] == 4  # bar 4 low 89.1 ≤ stop 108
    assert r["exit_price"] == 108.0


def test_ratchet_never_moves_the_stop_down():
    close = [100.0, 120.0, 60.0, 130.0, 140.0]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    r = trailing_stop(high, low, close, "pct", pct=10.0)
    flat = [s for s in r["stops"] if s is not None]
    assert flat == sorted(flat)  # stops are nondecreasing once they exist


def test_swing_method_is_the_lowest_low_of_the_window():
    low = [10.0, 9.0, 11.0, 8.0, 12.0]
    high = [lv + 1.0 for lv in low]
    close = [lv + 0.5 for lv in low]
    r = trailing_stop(high, low, close, "swing", swing_bars=3)
    # swing_bars=3: first value at bar 2 (needs 3 bars): min(10,9,11)=9;
    # bar 3: min(9,11,8)=8 < 9 → the ratchet keeps 9; bar 4: min(11,8,12)=8
    # → still 9.
    assert r["stops"] == [None, None, 9.0, 9.0, 9.0]


def test_chandelier_on_smooth_bars():
    # rising bars +0.5 each: high=close+0.25, low=close−0.25. The true ranges
    # are 0.75 (bar 0: 0.5, then overlap 0.75), so Wilder ATR(3) seeds at
    # (0.5+0.75+0.75)/3 = 2/3 and decays toward 0.75 — hand-recomputed below.
    close = [100.0, 100.5, 101.0, 101.5, 102.0, 102.5, 103.0]
    high = [c + 0.25 for c in close]
    low = [c - 0.25 for c in close]
    r = trailing_stop(high, low, close, "chandelier", atr_period=3, atr_multiple=2.0)
    assert r["stops"][:2] == [None, None]
    for got, want in zip(
        r["stops"][2:], [99.9167, 100.3611, 100.8241, 101.2994, 101.7829], strict=True
    ):
        assert got == pytest.approx(want, abs=1e-3)
    assert r["exited_index"] is None  # never touched


def test_chandelier_exit_registers_on_a_later_bar_not_the_same_one():
    close = [100.0, 100.5, 101.0, 101.5, 80.0]
    high = [c + 0.25 for c in close]
    low = [c - 0.25 for c in close]
    r = trailing_stop(high, low, close, "chandelier", atr_period=3, atr_multiple=2.0)
    assert r["exited_index"] is not None
    assert r["exited_index"] > 2  # a later bar, not the bar that set the stop
    stop_at = r["stops"][r["exited_index"] - 1]
    assert r["exit_price"] == pytest.approx(stop_at, abs=1e-9)
    # the final TR bar (80) is a crash — no stop is claimed for it
    assert r["stops"][-1] == stop_at


def test_warmup_has_no_stop_and_reports_it():
    close = [100.0 + i for i in range(5)]
    high = [c + 0.25 for c in close]
    low = [c - 0.25 for c in close]
    r = trailing_stop(high, low, close, "chandelier", atr_period=10)
    assert all(s is None for s in r["stops"])
    assert r["exited_index"] is None
    assert r["bars_used"] == 5


def test_method_going_above_close_is_never_applied():
    # pct=1 on a crash: rule = 100·0.99 = 99 at bar 0… then close 50 bar 1:
    # peak stays 100 → rule 99 ≥ close 50 → not applied; stop becomes None.
    high = [101.0, 51.0]
    low = [99.0, 49.0]
    close = [100.0, 50.0]
    r = trailing_stop(high, low, close, "pct", pct=1.0)
    # bar 0: rule 99 < close 100 → applied. bar 1: rule 99 ≥ 50 → NOT applied.
    assert r["stops"] == [99.0, 99.0]
    # the stop from bar 0 exits at bar 1 (low 49 ≤ 99)
    assert r["exited_index"] == 1 and r["exit_price"] == 99.0


def test_errors():
    with pytest.raises(TrailingError, match="unknown method"):
        trailing_stop([1.0], [1.0], [1.0], "nope")
    with pytest.raises(TrailingError, match="same, nonempty length"):
        trailing_stop([], [], [])
    with pytest.raises(TrailingError, match="same"):
        trailing_stop([1.0, 2.0], [1.0], [1.0, 2.0])
    with pytest.raises(TrailingError, match="atr_period"):
        trailing_stop([1.0], [1.0], [1.0], "chandelier", atr_period=0)
    with pytest.raises(TrailingError, match="swing_bars"):
        trailing_stop([1.0], [1.0], [1.0], "swing", swing_bars=1)
    with pytest.raises(TrailingError, match="pct"):
        trailing_stop([1.0], [1.0], [1.0], "pct", pct=200.0)


def test_malformed_bar_ends_the_chain():
    close = [100.0, 101.0, float("nan"), 102.0]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    r = trailing_stop(high, low, close, "pct", pct=5.0)
    assert r["bars_used"] == 2  # the NaN bar ends the usable chain
    assert r["bars_skipped_tail"] == 2
    assert len(r["stops"]) == 2


# ------------------------------------------------------------------- the API


def _client(tmp_path, n=60, base=100.0):
    import pandas as pd

    store = MarketStore(tmp_path / "market.duckdb")
    dates = pd.bdate_range("2026-01-01", periods=n)
    close = [base + i * 0.5 for i in range(n)]
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": "AAA",
                "trading_date": dates,
                "open": close,
                "high": [c * 1.01 for c in close],
                "low": [c * 0.99 for c in close],
                "close": close,
                "volume": 1000.0,
                "turnover": [c * 1000.0 for c in close],
                "percent_change": 0.4,
                "source": "fixture",
                "retrieved_at": pd.Timestamp("2026-10-11"),
                "validation_status": "valid",
            }
        )
    )
    return store, create_app(store=store)


def test_trailing_endpoint_chandelier(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        d = c.get(
            "/api/bars/AAA/trailing-stop",
            params={"method": "chandelier", "atr_period": 14, "atr_multiple": 3.0},
        ).json()
    assert d["symbol"] == "AAA"
    r = d["result"]
    assert r["method"] == "chandelier"
    assert r["side"].startswith("long")
    assert len(r["stops"]) == r["bars_used"] == 60
    assert d["last_date"] == r["dates"][-1]
    values = [s for s in r["stops"] if s is not None]
    assert values == sorted(values)
    assert d["first_date"] == "2026-01-01"
    assert "not a forecast" in d["source"]
    store.close()


def test_trailing_endpoint_unknown_method_422(tmp_path):
    # the route's pattern rejects an unknown method before the engine runs
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/bars/AAA/trailing-stop", params={"method": "magic"}).status_code == 422
    store.close()


def test_trailing_endpoint_unknown_symbol_404(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/bars/ZZZ/trailing-stop").status_code == 404
    store.close()
