"""Backtesting engine.

Design intent (see docs/TECH_STACK_DECISIONS.md): a small, fully readable engine
whose every rule can be inspected, rather than a large library whose default
assumptions would be invisible. There is no hidden fill model, no hidden
commission, and no lookahead: a signal computed on bar *i* can never fill
before bar *i+1* unless the caller explicitly asks for the optimistic mode.

WHAT THIS IS NOT
----------------
It is not evidence about future returns. Every result carries an ``assumptions``
list that must be shown next to any number derived from it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

#: Trading days per year used for annualising Sharpe. NEPSE trades Sun-Thu, so
#: the calendar has more trading days than a 250-day market; 250 is the common
#: convention and is stated in the assumptions rather than left implicit.
TRADING_DAYS_PER_YEAR = 250

SignalFn = Callable[[pd.DataFrame], np.ndarray]


@dataclass(frozen=True)
class BacktestConfig:
    """Execution and cost assumptions. Every field is user-visible."""

    initial_cash: float = 100_000.0
    #: Fraction of traded value charged **per side**. This is a configurable
    #: PLACEHOLDER covering commission and charges - confirm the real figure
    #: with your broker before trusting any P&L.
    fee_rate: float = 0.004
    #: Fraction of adverse price movement applied to fills (0 = none).
    slippage: float = 0.0
    #: ``next_open`` fills on the bar after the signal (no lookahead).
    #: ``same_close`` fills at the close of the bar that produced the signal
    #: and is deliberately optimistic - it exists to show how much that choice
    #: is worth, not to be the default.
    execution: Literal["next_open", "same_close"] = "next_open"
    #: Buy whole units only (cash remainder stays uninvested). NEPSE trades in
    #: board lots, which are company-specific and not modelled here.
    whole_units: bool = True
    allow_short: bool = False

    def validate(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be > 0")
        if self.fee_rate < 0:
            raise ValueError("fee_rate must be >= 0")
        if self.slippage < 0:
            raise ValueError("slippage must be >= 0")
        if self.execution not in ("next_open", "same_close"):
            raise ValueError("execution must be 'next_open' or 'same_close'")
        if self.allow_short:
            raise ValueError(
                "shorting is not supported: NEPSE has no retail shorting, and a "
                "short model that does not exist in the market would not be honest"
            )


@dataclass
class Trade:
    entry_date: str
    exit_date: str | None
    entry_price: float
    exit_price: float | None
    units: float
    fees_paid: float = 0.0
    pnl: float | None = None
    return_pct: float | None = None
    bars_held: int = 0


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    params: dict[str, Any]
    config: dict[str, Any]
    start: str
    end: str
    bars: int
    metrics: dict[str, Any]
    equity: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------- metrics
def max_drawdown(equity: Sequence[float]) -> float:
    """Largest peak-to-trough decline, as a negative fraction."""
    if not equity:
        return 0.0
    arr = np.asarray(equity, dtype=float)
    peak = np.maximum.accumulate(arr)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, arr / peak - 1.0, 0.0)
    return float(np.min(dd)) if len(dd) else 0.0


def sharpe_ratio(
    returns: Sequence[float], periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float | None:
    """Annualised Sharpe of a return series. ``None`` when it is undefined."""
    arr = np.asarray([r for r in returns if r is not None], dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return None
    sd = float(np.std(arr, ddof=1))
    if sd == 0.0:
        return None
    return float(np.mean(arr) / sd * math.sqrt(periods_per_year))


def cagr(start_value: float, end_value: float, days: float) -> float | None:
    if start_value <= 0 or end_value <= 0 or days <= 0:
        return None
    return float((end_value / start_value) ** (365.25 / days) - 1.0)


# ------------------------------------------------------------------- strategies
def sma_cross(fast: int = 20, slow: int = 50) -> SignalFn:
    """Long while the fast SMA is above the slow SMA (flat otherwise)."""
    if fast >= slow:
        raise ValueError("sma_cross: fast period must be < slow period")

    def sig(df: pd.DataFrame) -> np.ndarray:
        c = df["close"].astype(float)
        f = c.rolling(fast).mean()
        s = c.rolling(slow).mean()
        out = (f > s).to_numpy() & f.notna().to_numpy() & s.notna().to_numpy()
        return out.astype(np.int8)

    return sig


def rsi_threshold(period: int = 14, buy_below: float = 30.0, sell_above: float = 70.0) -> SignalFn:
    """Long while RSI is below ``buy_below``; exit above ``sell_above``.

    Hysteresis (two levels) so the strategy does not churn on every bar.
    """
    from megatool.ta import compute as ta_compute

    def sig(df: pd.DataFrame) -> np.ndarray:
        data = {
            "open": df["open"].to_numpy(float),
            "high": df["high"].to_numpy(float),
            "low": df["low"].to_numpy(float),
            "close": df["close"].to_numpy(float),
            "volume": df["volume"].to_numpy(float),
        }
        r = np.asarray(ta_compute("rsi", data, period=period).values["rsi"], dtype=float)
        out = np.zeros(len(df), dtype=np.int8)
        position = 0
        for i, v in enumerate(r):
            if np.isnan(v):
                out[i] = 0
                continue
            if position == 0 and v < buy_below:
                position = 1
            elif position == 1 and v > sell_above:
                position = 0
            out[i] = position
        return out

    return sig


def always_in(_df: pd.DataFrame) -> np.ndarray:
    """Invested for the whole window - the buy-and-hold control."""
    return np.ones(len(_df), dtype=np.int8)


def never_in(_df: pd.DataFrame) -> np.ndarray:
    return np.zeros(len(_df), dtype=np.int8)


def ma_slope_trend(period: int = 100, min_slope: float = 0.0) -> SignalFn:
    """Long while a long SMA is rising (a deliberately slow trend filter)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        ma = df["close"].astype(float).rolling(period).mean()
        slope = ma.diff()
        ok = (slope > min_slope).to_numpy() & ma.notna().to_numpy()
        ok &= slope.notna().to_numpy()
        return ok.astype(np.int8)

    return sig


STRATEGIES: dict[str, dict[str, Any]] = {
    "sma_cross": {
        "label": "SMA crossover",
        "description": "Long while SMA(fast) > SMA(slow). Classic trend following.",
        "params": {"fast": 20, "slow": 50},
        "factory": sma_cross,
    },
    "rsi_threshold": {
        "label": "RSI mean-reversion",
        "description": "Buy below oversold, exit above overbought (two levels, "
        "so it does not churn every bar). RSI is a historical statistic, "
        "not a prediction.",
        "params": {"period": 14, "buy_below": 30.0, "sell_above": 70.0},
        "factory": rsi_threshold,
    },
    "ma_slope_trend": {
        "label": "Long-trend filter",
        "description": "Long while a 100-bar SMA is rising. Slow, low-turnover.",
        "params": {"period": 100, "min_slope": 0.0},
        "factory": ma_slope_trend,
    },
    "always_in": {
        "label": "Buy and hold",
        "description": "Invested for the whole window. The control every other "
        "result should be compared against.",
        "params": {},
        "factory": lambda: always_in,
    },
}


def build_strategy(key: str, **overrides: Any) -> tuple[SignalFn, str, dict[str, Any]]:
    if key not in STRATEGIES:
        raise ValueError(f"unknown strategy {key!r}; known: {', '.join(sorted(STRATEGIES))}")
    spec = STRATEGIES[key]
    params = {**spec["params"], **overrides}
    unknown = set(params) - set(spec["params"])
    if unknown:
        raise ValueError(
            f"{key}: unknown parameter(s) {sorted(unknown)}; allowed {sorted(spec['params'])}"
        )
    # Web forms and JSON send numbers as floats; a period of 20.5 would fail
    # deep inside pandas, so coerce (or reject) at the boundary instead.
    for name, default in spec["params"].items():
        value = params[name]
        if isinstance(default, bool):
            params[name] = bool(value)
        elif isinstance(default, int):
            if isinstance(value, bool):
                raise ValueError(f"{key}.{name} must be a whole number, got {value!r}")
            if isinstance(value, float) and float(value).is_integer():
                params[name] = int(value)
            elif isinstance(value, int):
                params[name] = value
            else:
                raise ValueError(f"{key}.{name} must be a whole number, got {value!r}")
        elif isinstance(default, float):
            params[name] = float(value)
    fn = spec["factory"](**params)
    return fn, spec["label"], params


# ----------------------------------------------------------------------- engine
def run_backtest(
    df: pd.DataFrame,
    signal_fn: SignalFn,
    config: BacktestConfig | None = None,
    symbol: str = "",
    strategy: str = "",
    params: dict[str, Any] | None = None,
) -> BacktestResult:
    """Run a long/flat strategy over ``df`` (ascending dates).

    Returns metrics, an equity curve, the closed trades, and the list of
    assumptions the numbers depend on.
    """
    cfg = config or BacktestConfig()
    cfg.validate()

    required = {"trading_date", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"backtest input is missing columns: {sorted(missing)}")

    data = df.sort_values("trading_date").reset_index(drop=True).copy()
    n = len(data)
    warnings: list[str] = []

    if n < 2:
        raise ValueError(f"need at least 2 bars to backtest, got {n}")

    raw = signal_fn(data)
    if len(raw) != n:
        raise ValueError(f"signal length {len(raw)} does not match bars {n}")
    signal = np.asarray(raw, dtype=float)
    if not np.all(np.isin(signal[np.isfinite(signal)], (0.0, 1.0, -1.0))):
        raise ValueError("signal must contain only 0 (flat), 1 (long) or -1 (short)")
    if np.any(signal < 0):
        raise ValueError("short signals are not supported (see BacktestConfig.allow_short)")

    dates = [str(d.date()) if hasattr(d, "date") else str(d) for d in data["trading_date"]]
    opens = data["open"].to_numpy(dtype=float)
    closes = data["close"].to_numpy(dtype=float)

    cash = float(cfg.initial_cash)
    units = 0.0
    entry_index = 0
    fees_total = 0.0
    open_trade: Trade | None = None
    trades: list[Trade] = []
    equity: list[float] = []
    position_hist: list[int] = []
    skipped_fills = 0

    pending = 0.0  # signal from the previous bar, filled on this bar (next_open)
    for i in range(n):
        if cfg.execution == "next_open":
            target = pending
            fill = opens[i]
        else:
            target = signal[i]
            fill = closes[i]

        if not np.isfinite(fill) or fill <= 0:
            # Source occasionally publishes a bad/absent open: fall back to the
            # close of the same bar and count it, rather than silently skipping.
            fill = closes[i]
            if not np.isfinite(fill) or fill <= 0:
                skipped_fills += 1
                fill = np.nan

        current = 1.0 if units > 0 else 0.0
        if np.isfinite(fill) and target != current:
            if target > current:
                price = fill * (1.0 + cfg.slippage)
                affordable = cash / (price * (1.0 + cfg.fee_rate))
                take = math.floor(affordable) if cfg.whole_units else affordable
                if take > 0:
                    cost = take * price
                    fee = cost * cfg.fee_rate
                    cash -= cost + fee
                    fees_total += fee
                    units = take
                    entry_index = i
                    open_trade = Trade(
                        entry_date=dates[i],
                        exit_date=None,
                        entry_price=price,
                        exit_price=None,
                        units=take,
                        fees_paid=fee,
                    )
            else:
                price = fill * (1.0 - cfg.slippage)
                proceeds = units * price
                fee = proceeds * cfg.fee_rate
                cash += proceeds - fee
                fees_total += fee
                if open_trade is not None:
                    # Cost basis already includes the entry fee paid on entry,
                    # so the round-trip P&L counts both sides exactly once.
                    entry_fee = open_trade.fees_paid
                    cost_basis = open_trade.entry_price * open_trade.units + entry_fee
                    open_trade.exit_date = dates[i]
                    open_trade.exit_price = price
                    open_trade.fees_paid = entry_fee + fee
                    open_trade.pnl = (proceeds - fee) - cost_basis
                    open_trade.return_pct = (open_trade.pnl / cost_basis) if cost_basis else None
                    open_trade.bars_held = i - entry_index
                    trades.append(open_trade)
                    open_trade = None
                units = 0.0

        equity.append(cash + (units * closes[i] if np.isfinite(closes[i]) else 0.0))
        position_hist.append(1 if units > 0 else 0)
        pending = signal[i]

    if skipped_fills:
        warnings.append(
            f"{skipped_fills} bar(s) had no usable price for a fill; those fills were skipped"
        )

    # Close any still-open position for accounting purposes (marked, not sold).
    open_at_end = units > 0
    if open_trade is not None:
        open_trade.exit_date = None
        open_trade.exit_price = None
        open_trade.bars_held = n - 1 - entry_index
        trades.append(open_trade)

    final_equity = equity[-1]
    days = 0.0
    try:
        d0 = pd.Timestamp(dates[0])
        d1 = pd.Timestamp(dates[-1])
        days = float((d1 - d0).days)
    except (ValueError, TypeError):
        days = float(n)

    daily_returns = (
        np.diff(equity) / np.asarray(equity[:-1], dtype=float) if n > 1 else np.array([])
    )
    daily_returns = daily_returns[np.isfinite(daily_returns)]

    exposure = float(np.mean(position_hist)) if position_hist else 0.0
    closed = [t for t in trades if t.exit_date is not None and t.pnl is not None]
    wins = [t for t in closed if (t.pnl or 0) > 0]

    # Benchmark: buy and hold with the same cost model.
    benchmark = _buy_and_hold_benchmark(opens, closes, cfg, n)
    cagr_value = cagr(cfg.initial_cash, final_equity, days)
    sharpe_value = sharpe_ratio(daily_returns)

    metrics: dict[str, Any] = {
        "initial_cash": cfg.initial_cash,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity / cfg.initial_cash - 1.0) * 100.0, 4),
        "cagr_pct": None if cagr_value is None else round(cagr_value * 100.0, 4),
        "max_drawdown_pct": round(max_drawdown(equity) * 100.0, 4),
        "sharpe": None if sharpe_value is None else round(sharpe_value, 4),
        "trades": len(closed),
        "open_position_at_end": open_at_end,
        "win_rate_pct": None if not closed else round(100.0 * len(wins) / len(closed), 2),
        "exposure_pct": round(exposure * 100.0, 2),
        "fees_paid": round(fees_total, 2),
        "avg_trade_pct": None
        if not closed
        else round(float(np.mean([(t.return_pct or 0.0) for t in closed])), 4),
        "benchmark_total_return_pct": benchmark["total_return_pct"],
        "benchmark_final_equity": benchmark["final_equity"],
        "active_days": int(np.sum(position_hist)),
        "total_days": n,
    }

    assumptions = _assumptions(cfg, dates, days, n)
    if open_at_end:
        warnings.append(
            "a position was still open at the end of the sample; it is marked to "
            "market, not closed, so it contributes no realised trade"
        )
    if len(closed) < 5:
        warnings.append(
            f"only {len(closed)} completed trade(s): win rate and average trade are "
            "not statistically meaningful"
        )
    if days < 365:
        warnings.append("sample shorter than one year: annualised figures are unreliable")

    return BacktestResult(
        symbol=symbol,
        strategy=strategy or "custom",
        params=params or {},
        config=asdict(cfg),
        start=dates[0],
        end=dates[-1],
        bars=n,
        metrics=metrics,
        equity=[
            {"date": d, "equity": round(e, 2), "position": p}
            for d, e, p in zip(dates, equity, position_hist, strict=True)
        ],
        trades=[asdict(t) for t in trades],
        assumptions=assumptions,
        warnings=warnings,
    )


def _buy_and_hold_benchmark(
    opens: np.ndarray, closes: np.ndarray, cfg: BacktestConfig, n: int
) -> dict[str, Any]:
    """Same cost model, invested on the first bar and held."""
    fill = opens[0] if np.isfinite(opens[0]) and opens[0] > 0 else closes[0]
    if not np.isfinite(fill) or fill <= 0:
        return {"total_return_pct": None, "final_equity": None}
    price = fill * (1.0 + cfg.slippage)
    affordable = cfg.initial_cash / (price * (1.0 + cfg.fee_rate))
    units = math.floor(affordable) if cfg.whole_units else affordable
    invested = units * price
    fee = invested * cfg.fee_rate
    cash = cfg.initial_cash - invested - fee
    last = closes[-1]
    if not np.isfinite(last):
        return {"total_return_pct": None, "final_equity": None}
    final = cash + units * last
    return {
        "total_return_pct": round((final / cfg.initial_cash - 1.0) * 100.0, 4),
        "final_equity": round(final, 2),
    }


def _assumptions(cfg: BacktestConfig, dates: list[str], days: float, bars: int) -> list[str]:
    exec_note = (
        "Signals fill on the NEXT bar's open - no lookahead."
        if cfg.execution == "next_open"
        else "OPTIMISTIC MODE: signals fill at the close of the bar that produced "
        "them, which a real order could not have done. Compare against next_open."
    )
    return [
        exec_note,
        f"Cost model: {cfg.fee_rate:.4%} of traded value per side, "
        f"slippage {cfg.slippage:.4%}. The fee is a PLACEHOLDER - confirm real "
        "NEPSE commission and charges with your broker.",
        "Prices are UNADJUSTED for bonus/rights issues, so long-horizon returns "
        "are price returns, not total returns. Dividends are not modelled.",
        "Filled in whole units (cash remainder stays uninvested). NEPSE board "
        "lots are company-specific and are NOT modelled."
        if cfg.whole_units
        else "Fractional units are filled - NEPSE does not actually allow this.",
        "Long/flat only. Shorting is not modelled because NEPSE has no retail shorting.",
        "No partial fills, order queues, circuit-breaker limits, suspension days, "
        "liquidity limits or T+2 settlement delays are modelled.",
        f"Annualisation uses {TRADING_DAYS_PER_YEAR} trading days/year; the "
        "Sharpe ratio has no risk-free rate subtracted.",
        f"Sample: {bars} bars, {dates[0]} to {dates[-1]} ({days:.0f} calendar days).",
        "Past performance does not indicate future results. This is a research "
        "calculation, not a forecast or advice.",
    ]
