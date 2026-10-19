"""Focused tests for market-regime detection (Phase 2, feature 8).

All series are synthetic and deterministic. The suite pins the three-label
definition (trend / volatility / momentum), explicit insufficient-data
handling, and — critically — the no-look-ahead property: a label at date T
depends only on data up to T, so truncating the series after T must not
change the label at T.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.regime import (
    MIN_BARS,
    MOMENTUM_WINDOW,
    SLOW_SMA,
    VOL_MIN_PERIODS,
    VOL_WINDOW,
    detect_regimes,
    market_proxy,
)

N_SYMBOLS = 12


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-01", periods=n)


def _trending(
    drift: float, n: int = MIN_BARS + 100, vol: float = 0.001, seed: int = 7
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    shocks = rng.normal(drift, vol, size=(n, N_SYMBOLS))
    closes = 100.0 * np.exp(np.cumsum(shocks, axis=0))
    return pd.DataFrame(closes, index=_dates(n), columns=[f"S{i}" for i in range(N_SYMBOLS)])


def _volatile_switch(n: int = MIN_BARS + 100, seed: int = 11) -> pd.DataFrame:
    """Low-vol first half, ten-times vol second half."""
    rng = np.random.default_rng(seed)
    half = n // 2
    low = rng.normal(0.0005, 0.002, size=(half, N_SYMBOLS))
    high = rng.normal(0.0005, 0.02, size=(n - half, N_SYMBOLS))
    closes = 100.0 * np.exp(np.cumsum(np.vstack([low, high]), axis=0))
    return pd.DataFrame(closes, index=_dates(n), columns=[f"S{i}" for i in range(N_SYMBOLS)])


def test_uptrend_is_bull_downtrend_is_bear():
    up = detect_regimes(_trending(0.002))
    assert up.status == "ok"
    assert up.current["trend"] == "bull"
    assert up.current["momentum"] == "positive"
    down = detect_regimes(_trending(-0.002))
    assert down.current["trend"] == "bear"
    assert down.current["momentum"] == "negative"


def test_volatility_regime_switches_with_the_vol_regime():
    res = detect_regimes(_volatile_switch())
    assert res.status == "ok"
    high_vol_days = res.summary["days"]["volatility"]["high"]
    normal_vol_days = res.summary["days"]["volatility"]["normal"]
    # The second half is far more volatile, so 'high' must dominate the tail
    # of the history while 'low'/'normal' appear early.
    tail = res.history[len(res.history) // 2 :]
    assert sum(1 for r in tail if r["volatility"] == "high") > len(tail) * 0.8
    assert high_vol_days > 0 and normal_vol_days > 0


def test_momentum_band_marks_neutral_in_a_flat_market():
    # ~0%/day drift: trailing 60-session return stays inside ±5% → neutral.
    flat = detect_regimes(_trending(0.0001, vol=0.0005))
    assert flat.current["momentum"] == "neutral"


def test_insufficient_data_is_explicit_not_guessed():
    short = _trending(0.002, n=MIN_BARS - 5)
    res = detect_regimes(short)
    assert res.status == "insufficient_data"
    assert res.current is None
    # The reason names the usable proxy length (input rows minus the first,
    # which has no prior close) and the requirement.
    assert str(res.bars) in res.reason and str(MIN_BARS) in res.reason
    assert res.summary == {}


def test_labels_are_causal_no_look_ahead():
    """Truncating the series after T must not change the label at T."""
    closes = _trending(0.002, n=MIN_BARS + 100)
    full = detect_regimes(closes)
    t_pos = 300  # past every warmup window, inside the 359-bar history
    t_date = full.history[t_pos]["date"]
    # proxy index i corresponds to closes index i+1, so keep one extra row.
    truncated = detect_regimes(closes.iloc[: t_pos + 2])
    row = next(r for r in truncated.history if r["date"] == t_date)
    full_row = full.history[t_pos]
    assert row["trend"] == full_row["trend"]
    assert row["volatility"] == full_row["volatility"]
    assert row["momentum"] == full_row["momentum"]
    assert row["proxy_level"] == pytest.approx(full_row["proxy_level"], abs=1e-9)


def test_warmup_rows_are_labeled_insufficient_not_dropped_or_faked():
    closes = _trending(0.002, n=MIN_BARS + 50)
    res = detect_regimes(closes)
    first = res.history[0]
    assert first["trend"] == "insufficient"
    assert first["volatility"] == "insufficient"
    assert first["momentum"] == "insufficient"
    # After each component's window the labels become concrete.
    past_warmup = res.history[max(SLOW_SMA, VOL_MIN_PERIODS + VOL_WINDOW, MOMENTUM_WINDOW)]
    assert past_warmup["trend"] in ("bull", "bear")
    assert past_warmup["volatility"] in ("low", "normal", "high")
    assert past_warmup["momentum"] in ("positive", "neutral", "negative")


def test_proxy_drops_dates_with_too_few_symbols():
    closes = _trending(0.002, n=MIN_BARS + 10)
    level = market_proxy(closes, min_symbols=N_SYMBOLS)
    # The first date has no prior close, so it never enters the proxy.
    assert len(level) == len(closes) - 1
    # Blank out 3 symbols on one date: that date must vanish (12-3=9 < 10),
    # and so must the NEXT date, whose return also uses the blanked cells.
    closes.iloc[10, :3] = np.nan
    level2 = market_proxy(closes, min_symbols=N_SYMBOLS)
    assert len(level2) == len(closes) - 3
    # Dates before the blanked cell are untouched (level2.iloc[8] is the same
    # session as level.iloc[8]: closes.index[9]).
    assert level2.iloc[8] == pytest.approx(level.iloc[8], abs=1e-9)


def test_proxy_is_the_equal_weighted_mean_return():
    closes = pd.DataFrame(
        {
            "A": [100.0, 110.0, 121.0],
            "B": [200.0, 190.0, 180.0],
        },
        index=_dates(3),
    )
    level = market_proxy(closes, min_symbols=2)
    # day2: mean(10%, -5%) = 2.5% → 102.5; day3: mean(10%, -5.263%) ≈ 2.368%
    assert level.iloc[0] == pytest.approx(102.5, abs=1e-6)
    assert level.iloc[1] == pytest.approx(102.5 * 1.023684, rel=1e-4)


def test_history_limit_parameter():
    closes = _trending(0.002, n=MIN_BARS + 100)
    res = detect_regimes(closes, limit=30)
    assert len(res.history) == 30
    full = detect_regimes(closes)
    assert res.current == full.current  # limiting history never changes "now"
    assert res.summary["days"]["trend"]["bull"] > 0


def test_empty_and_tiny_inputs_are_safe():
    assert detect_regimes(pd.DataFrame()).status == "insufficient_data"
    one_symbol = _trending(0.002).iloc[:, :1]
    # Fewer than MIN_SYMBOLS symbols → proxy empty → insufficient.
    assert detect_regimes(one_symbol).status == "insufficient_data"


# ------------------------------------------------------------------ API routes
def _client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from megatool.api import create_app
    from megatool.market_store import MarketStore

    store = MarketStore(tmp_path / "market.duckdb")
    closes = 100.0 + np.arange(MIN_BARS + 60, dtype=float)
    for i in range(N_SYMBOLS):
        store.upsert_bars(
            pd.DataFrame(
                {
                    "symbol": f"S{i}",
                    "trading_date": pd.bdate_range("2024-01-01", periods=len(closes)),
                    "open": closes * (1 + i * 0.001),
                    "high": closes * 1.02,
                    "low": closes * 0.98,
                    "close": closes * (1 + i * 0.001),
                    "volume": 10_000,
                    "turnover": closes * 10_000,
                    "source": "SYNTHETIC-TEST-FIXTURE",
                    "retrieved_at": pd.Timestamp("2026-10-11"),
                    "validation_status": "valid",
                }
            )
        )
    app = create_app(store=store)
    client = TestClient(app)
    return client, store


def test_regime_route_reports_current_labels(tmp_path, monkeypatch):
    client, store = _client(tmp_path, monkeypatch)
    try:
        r = client.get("/api/regime")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["current"]["trend"] == "bull"
        assert d["current"]["momentum"] == "positive"
        assert d["symbols"] == N_SYMBOLS
        assert "NOT the official NEPSE index" in d["params"]["proxy"]
        assert "not evidence of future performance" in d["disclaimer"]
    finally:
        store.close()


def test_regime_route_is_explicit_when_data_is_short(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from megatool.api import create_app
    from megatool.market_store import MarketStore

    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": "ONLY",
                "trading_date": pd.bdate_range("2024-01-01", periods=50),
                "open": [100.0] * 50,
                "high": [100.0] * 50,
                "low": [100.0] * 50,
                "close": [100.0] * 50,
                "volume": [1000] * 50,
                "source": "SYNTHETIC-TEST-FIXTURE",
                "retrieved_at": pd.Timestamp("2026-10-11"),
                "validation_status": "valid",
            }
        )
    )
    app = create_app(store=store)
    with TestClient(app) as client:
        d = client.get("/api/regime").json()
        assert d["status"] == "insufficient_data"
        assert d["current"] is None
        assert "260" in d["reason"]
    store.close()


def test_regime_history_route_respects_limit(tmp_path, monkeypatch):
    client, store = _client(tmp_path, monkeypatch)
    try:
        d = client.get("/api/regime/history", params={"limit": 5}).json()
        assert d["status"] == "ok"
        assert len(d["history"]) == 5
        assert d["history"][-1]["date"] == d["current"]["date"]
    finally:
        store.close()


def test_dates_come_from_trading_date_column_not_row_positions():
    """``all_closes()`` returns trading_date as a column over a positional index.

    The proxy must date its labels from that column: with the positional index
    kept, live responses reported row numbers as dates (observed
    ``last_date``: "5195" on production data).
    """
    base = _trending(0.001)
    prod = base.reset_index(drop=True)  # production shape: RangeIndex
    prod.insert(0, "trading_date", base.index)
    res = detect_regimes(prod)
    assert res.status == "ok"
    expected = str(base.index[-1])[:10]
    assert res.last_date == expected
    assert res.current["date"] == expected
    # every history row is a real session date (YYYY-MM-DD), never a row number
    assert all(len(r["date"]) == 10 and r["date"][4] == "-" for r in res.history)
