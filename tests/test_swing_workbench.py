"""Swing Workbench tests.

Synthetic zigzag series with hand-computable pivots. The arithmetic
(measured move, risk, sizing) is re-derived in the test from the same raw
inputs the module used, so a formula change cannot pass silently.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.swing_workbench import swing_workbench

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _frame(closes: np.ndarray, start: str = "2026-01-05") -> pd.DataFrame:
    n = len(closes)
    dates = pd.bdate_range(start, periods=n)
    return pd.DataFrame(
        {
            "symbol": "X",
            "trading_date": dates,
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": np.full(n, 10_000, dtype=np.int64),
            "turnover": closes * 10_000,
            "percent_change": np.nan,
            "source": "test",
            "retrieved_at": RETRIEVED,
        }
    )


def _zigzag(segments: list[tuple[float, float, int]]) -> np.ndarray:
    """Piecewise-linear series; each segment is (from, to, bars)."""
    pieces = [np.linspace(a, b, bars) for a, b, bars in segments]
    return np.concatenate(pieces)


#: 100 -> 120 -> 110 -> 140 -> 125 -> 160 -> 158: three up-legs and two
#: pullbacks, then a gentle fade so the 160 peak is confirmable.
UP_DOWN = [
    (100, 119, 12),
    (119, 110, 10),
    (110, 139, 12),
    (139, 125, 10),
    (125, 159, 12),
    (159, 158, 10),
]


def test_uptrend_structure_and_levels():
    df = _frame(_zigzag(UP_DOWN))
    out = swing_workbench(df)
    assert out["structure"]["trend"] == "up"
    nl = out["nearest_levels"]
    assert (
        nl["support"] is not None and nl["support"]["price"] < out["reference_levels"]["last_close"]
    )
    assert (
        nl["resistance"] is not None
        and nl["resistance"]["price"] > out["reference_levels"]["last_close"]
    )
    # Level sources must be confirmed within the loaded window.
    for lvl in (nl["support"], nl["resistance"]):
        assert lvl["confirmed_date"] <= out["last_date"]
        assert lvl["swing_date"] <= lvl["confirmed_date"]


def test_reference_arithmetic_matches_raw_inputs():
    df = _frame(_zigzag(UP_DOWN))
    out = swing_workbench(df, account_size=100_000.0, risk_fraction=0.01)
    ref = out["reference_levels"]
    assert ref["framing"] == "long"
    close = float(df["close"].iloc[-1])
    support = ref["invalidation"]["price"]
    last_high = ref["last_swing_high"]["price"]
    last_low = ref["last_swing_low"]["price"]
    measured = abs(last_high - last_low)
    assert ref["risk_pct"] == pytest.approx(100.0 * (close - support) / close)
    assert ref["target"]["price"] == pytest.approx(close + measured)
    assert ref["reward_pct"] == pytest.approx(100.0 * measured / close)
    assert ref["reward_risk"] == pytest.approx(measured / (close - support))
    # Sizing: floor(risk_amount / per-share risk), re-derived here.
    per_share = close - support
    assert out["sizing"]["shares"] == int(np.floor((100_000.0 * 0.01) / per_share))
    assert out["sizing"]["notional"] == pytest.approx(out["sizing"]["shares"] * close)


def test_unconfirmed_final_spike_is_never_used_as_resistance():
    """A last-bars spike is not a swing until `right` bars fail to exceed it."""
    closes = np.concatenate([_zigzag(UP_DOWN), np.array([170.0, 175.0, 180.0])])
    df = _frame(closes)
    out = swing_workbench(df)
    nl = out["nearest_levels"]
    # The 180 spike is above every confirmed level, so resistance is honestly
    # absent rather than pointing at an unconfirmable pivot.
    assert nl["resistance"] is None
    assert "no confirmed swing high above" in nl["resistance_missing_reason"]
    assert out["structure"]["trend"] == "up"  # older confirmed structure unchanged


def test_downtrend_frames_short():
    segments = [
        (160, 141, 12),
        (141, 150, 10),
        (150, 121, 12),
        (121, 135, 10),
        (135, 106, 12),
        (106, 107, 10),
    ]
    df = _frame(_zigzag(segments))
    out = swing_workbench(df)
    assert out["structure"]["trend"] == "down"
    ref = out["reference_levels"]
    assert ref["framing"] == "short"
    close = float(df["close"].iloc[-1])
    resistance = ref["invalidation"]["price"]
    assert resistance > close
    measured = abs(ref["last_swing_high"]["price"] - ref["last_swing_low"]["price"])
    assert ref["target"]["price"] == pytest.approx(close - measured)
    assert out["sizing"]["per_share_risk"] == pytest.approx(resistance - close)


def test_insufficient_history_reports_missing_not_guessed():
    closes = np.linspace(100, 110, 12)  # no confirmable swings -> no structure
    df = _frame(closes)
    out = swing_workbench(df)
    assert out["structure"]["trend"] == "insufficient data"
    assert "insufficient data" in out["reference_levels"]["reason"]
    assert out["reference_levels"]["invalidation"] is None
    assert out["sizing"]["shares"] is None
    assert out["nearest_levels"]["support"] is None
    # Checklist rows that cannot be computed carry pass=None and a reason,
    # never a fabricated boolean.
    sma200_row = next(r for r in out["checklist"] if r["name"] == "close_vs_sma200")
    assert (
        sma200_row["value"] is None and sma200_row["pass"] is None and sma200_row["missing_reason"]
    )


def test_validate_parameter_bounds():
    df = _frame(_zigzag(UP_DOWN))
    with pytest.raises(ValueError):
        swing_workbench(df, risk_fraction=0.0)
    with pytest.raises(ValueError):
        swing_workbench(df, account_size=-1)
    with pytest.raises(ValueError):
        swing_workbench(pd.DataFrame())


def test_caveats_and_disclaimer_present():
    out = swing_workbench(_frame(_zigzag(UP_DOWN)))
    assert out["caveats"]
    assert "Not a signal" in out["disclaimer"]
    assert out["method"]["swings"].startswith("fractal pivot")
