#!/usr/bin/env python
"""Independent quantitative cross-check harness.

This does NOT reuse the application's indicator or statistics primitives to
produce expected values. Every check compares the app's output against a
*separately written* reference: pandas rolling/ewm, scipy.stats, or a plain
Python loop transcribed from the published definition. Disagreement is a finding,
not a formatting difference.

Run::

    .venv/bin/python scripts/verify_quant.py

Exit code 0 = every check agreed within tolerance; 1 = at least one mismatch.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from megatool import stats as app_stats
from megatool import ta

# Independent reference libraries (different implementations on purpose).
try:
    import scipy.stats as ss

    HAVE_SCIPY = True
except Exception:  # pragma: no cover
    HAVE_SCIPY = False

TOL = 1e-8
FAILURES: list[str] = []


def check(name: str, got, want, tol: float = TOL) -> None:
    a = np.asarray(got, dtype=float)
    b = np.asarray(want, dtype=float)
    if a.shape != b.shape:
        FAILURES.append(f"{name}: shape {a.shape} != {b.shape}")
        return
    ok = np.allclose(a, b, rtol=tol, atol=tol, equal_nan=True)
    status = "ok " if ok else "FAIL"
    if not ok:
        diff = np.nanmax(np.abs(a - b)) if a.size else 0.0
        FAILURES.append(f"{name}: max abs diff {diff:.3e}")
    print(f"  [{status}] {name}")


def main() -> int:
    rng = np.random.default_rng(7)
    n = 400
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.017, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.006, n)))
    s = pd.Series(close)

    print("== moving averages vs pandas ==")
    period = 20
    check(
        "sma(20)",
        ta.compute("sma", {"close": close}, period=period).values["sma"],
        s.rolling(period).mean().to_numpy(),
    )
    # EMA convention note: the app documents an SMA-seeded EMA ("seeded with the
    # SMA of the first `period` values"), which is NOT pandas ewm's recursive
    # seed. Reference the DOCUMENTED convention with an independent loop rather
    # than comparing two different (both valid) EMA definitions.
    ema_ref = np.full(n, np.nan)
    ema_ref[period - 1] = close[:period].mean()
    alpha = 2.0 / (period + 1)
    for i in range(period, n):
        ema_ref[i] = ema_ref[i - 1] + alpha * (close[i] - ema_ref[i - 1])
    check(
        "ema(20) SMA-seeded",
        ta.compute("ema", {"close": close}, period=period).values["ema"],
        ema_ref,
        tol=1e-10,
    )
    w = np.arange(1, period + 1, dtype=float)
    check(
        "wma(20)",
        ta.compute("wma", {"close": close}, period=period).values["wma"],
        s.rolling(period).apply(lambda x: np.dot(x, w) / w.sum(), raw=True).to_numpy(),
    )

    print("== momentum/oscillators vs independent references ==")
    # RSI: Wilder, written as a loop from the definition.
    rsi_ref = np.full(n, np.nan)
    d = np.diff(close)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag, al = gain[:14].mean(), loss[:14].mean()
    rsi_ref[14] = 100 - 100 / (1 + ag / al)
    for i in range(15, n):
        ag = (ag * 13 + gain[i - 1]) / 14
        al = (al * 13 + loss[i - 1]) / 14
        rsi_ref[i] = 100 - 100 / (1 + ag / al)
    check(
        "rsi(14)", ta.compute("rsi", {"close": close}, period=14).values["rsi"], rsi_ref, tol=1e-9
    )

    # MACD: EMA(12)-EMA(26) with pandas ewm (different seeding -> past warm-up only).
    ema12 = s.ewm(span=12, adjust=False, min_periods=12).mean().to_numpy()
    ema26 = s.ewm(span=26, adjust=False, min_periods=26).mean().to_numpy()
    got = ta.compute("macd", {"close": close}).values["macd"]
    # Compare only the region where both are defined and seeded differences decay.
    mask = np.isfinite(got) & np.isfinite(ema12) & np.isfinite(ema26)
    idx = np.where(mask)[0]
    if idx.size > 50:
        tail = idx[-50:]
        check("macd line (tail vs pandas ewm)", got[tail], (ema12 - ema26)[tail], tol=5e-3)

    print("== volatility vs pandas ==")
    tr = np.full(n, np.nan)
    tr[1:] = np.maximum.reduce(
        [high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])]
    )
    rolling_std = pd.Series(close).rolling(20).std(ddof=0).to_numpy()  # Bollinger uses population
    bb = ta.compute("bollinger", {"close": close}, period=20, std_dev=2).values
    mid = pd.Series(close).rolling(20).mean().to_numpy()
    up_ref = mid + 2 * rolling_std
    lo_ref = mid - 2 * rolling_std
    check("bollinger middle", bb["middle"], mid)
    check("bollinger upper", bb["upper"], up_ref)
    check("bollinger lower", bb["lower"], lo_ref)

    print("== statistics vs scipy ==")
    x = rng.normal(0, 1, 250)
    y = 0.6 * x + rng.normal(0, 0.8, 250)
    got_p = app_stats.pearson(x, y)
    check("pearson r", [got_p["r"]], [np.corrcoef(x, y)[0, 1]])
    if HAVE_SCIPY:
        sp = ss.pearsonr(x, y)
        check("pearson p vs scipy", [got_p["p"]], [sp.pvalue], tol=1e-6)
        got_s = app_stats.spearman(x, y)
        check("spearman rho vs scipy", [got_s["rho"]], [ss.spearmanr(x, y).statistic], tol=1e-9)
        # Student-t two-sided p across several (t, df).
        for t, df in ((2.0, 10), (1.5, 30), (3.2, 5), (0.4, 100)):
            check(
                f"student_t p(t={t},df={df})",
                [app_stats.student_t_two_sided_p(t, df)],
                [2 * ss.t.sf(abs(t), df)],
                tol=1e-9,
            )
    ols = app_stats.ols(x, y)
    A = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    check("ols intercept/slope", [ols["intercept"], ols["slope"]], list(coef))
    resid = y - (coef[0] + coef[1] * x)
    r2 = 1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
    check("ols r2", [ols["r2"]], [r2], tol=1e-9)

    print("== return statistics recomputed ==")
    eq = np.array([100.0, 120.0, 90.0, 110.0, 130.0])
    rs = app_stats.return_statistics(eq)
    check("total_return", [rs["total_return"]], [eq[-1] / eq[0] - 1])
    peak = np.maximum.accumulate(eq)
    check("max_drawdown", [rs["max_drawdown"]], [(eq / peak - 1).min()])

    print("== backtest engine: hand-computed fixtures ==")
    from megatool.backtest import BacktestConfig, run_backtest

    # Fixture A: buy-and-hold, next-open fill, whole units, no fees.
    #  prices 100,110,105,120,115 ; cash 10_000 ; signal fires on bar 0 so the
    #  fill is bar 1's open (110). units = floor(10000/110) = 90 ; cash 100.
    #  final = 90*115 + 100 = 10_450 ; return = +4.50%.
    pxA = np.array([100.0, 110.0, 105.0, 120.0, 115.0])
    dfA = pd.DataFrame(
        {
            "trading_date": pd.bdate_range("2026-01-05", periods=5),
            "open": pxA,
            "high": pxA * 1.01,
            "low": pxA * 0.99,
            "close": pxA,
        }
    )
    resA = run_backtest(
        dfA,
        lambda d: np.ones(len(d)),
        BacktestConfig(
            initial_cash=10_000.0, fee_rate=0.0, whole_units=True, execution="next_open"
        ),
    )
    check("backtest final_equity (hand-computed)", [resA.metrics["final_equity"]], [10_450.0])
    check("backtest total_return_pct", [resA.metrics["total_return_pct"]], [4.5])
    # The position is still open at the end: it must NOT be counted as a closed trade.
    check("backtest open position is not a closed trade", [resA.metrics["trades"]], [0])

    # Fixture B: one round trip. The NEXT-OPEN convention means a signal on bar t
    #  fills at open[t+1]: entry signal on bar 0 fills at open[1]=110, and the exit
    #  signal on bar 3 fills at open[4]=115 (NOT bar 3's open of 120).
    #  units = floor(10000/110) = 90 ; pnl = 90*(115-110) = 450 ; final = 10_450.
    signal = np.array([1.0, 1.0, 1.0, 0.0, 0.0])
    pxB = np.array([100.0, 110.0, 105.0, 120.0, 115.0])
    dfB = pd.DataFrame(
        {
            "trading_date": pd.bdate_range("2026-01-05", periods=5),
            "open": pxB,
            "high": pxB * 1.01,
            "low": pxB * 0.99,
            "close": pxB,
        }
    )
    resB = run_backtest(
        dfB,
        lambda d: signal,
        BacktestConfig(
            initial_cash=10_000.0, fee_rate=0.0, whole_units=True, execution="next_open"
        ),
    )
    check("backtest closed-trade final_equity", [resB.metrics["final_equity"]], [10_450.0])
    check("backtest closed-trade count", [resB.metrics["trades"]], [1])

    # Fixture C: fees bite. Same trade as B at 1% per side, next-open fills.
    #  buy  90*110 = 9900, fee 99.00  -> cash 10000 - 9900 - 99.00 = 1.00
    #  sell 90*115 = 10350, fee 103.50 -> cash 1.00 + 10350 - 103.50 = 10247.50
    resC = run_backtest(
        dfB,
        lambda d: signal,
        BacktestConfig(
            initial_cash=10_000.0, fee_rate=0.01, whole_units=True, execution="next_open"
        ),
    )
    check(
        "backtest fee-adjusted final_equity", [resC.metrics["final_equity"]], [10_247.5], tol=1e-6
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} MISMATCH(ES):")
        for f in FAILURES:
            print("  -", f)
        return 1
    print(f"all independent checks agreed (scipy={'yes' if HAVE_SCIPY else 'no'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
