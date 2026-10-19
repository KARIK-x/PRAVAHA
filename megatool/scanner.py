"""All-market stock scanner.

Evaluates a filter tree against every security in the store.

DESIGN
------
* **Explainable.** Every result carries the reason it passed, and every
  non-eligible security carries the reason it could not be evaluated. A screen
  you cannot audit is not worth running.
* **Eligibility separate from ranking.** A stock with insufficient history is
  marked ineligible rather than being silently dropped or given a zero score.
* **No look-ahead.** Every condition reads only the latest *available* bar and
  the history before it.
* **Reproducible.** The same store contents and the same filter always give
  the same answer; nothing depends on the wall clock except an explicit
  ``as_of`` parameter.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from megatool import corporate_actions
from megatool.market_store import MarketStore, eligibility_from_meta
from megatool.ta import compute as ta_compute

#: A security needs at least this many bars before most filters are meaningful.
MIN_BARS_FOR_SCREEN = 30

#: Operators every numeric condition supports.
OPERATORS = {
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "crosses_above": lambda a, b: a > b,  # evaluated specially, see below
    "crosses_below": lambda a, b: a < b,
}


@dataclass(slots=True)
class ScreenCondition:
    """One atomic filter, e.g. ``rsi < 30``."""

    metric: str
    operator: str
    value: float
    lookback: int | None = None  # for metrics computed over a window

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"metric": self.metric, "operator": self.operator, "value": self.value}
        if self.lookback is not None:
            d["lookback"] = self.lookback
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScreenCondition:
        op = d["operator"]
        if op not in OPERATORS:
            raise ValueError(f"unknown operator {op!r}; expected one of {sorted(OPERATORS)}")
        return cls(
            metric=str(d["metric"]),
            operator=op,
            value=float(d["value"]),
            lookback=int(d["lookback"]) if d.get("lookback") is not None else None,
        )

    def render(self) -> str:
        sym = {
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
            "eq": "=",
            "crosses_above": "crosses above",
            "crosses_below": "crosses below",
        }[self.operator]
        lb = f"({self.lookback})" if self.lookback is not None else ""
        return f"{self.metric}{lb} {sym} {self.value:g}"


@dataclass(slots=True)
class ScreenNode:
    """A node in the filter tree: either a group of conditions or a single one."""

    op: str = "AND"  # AND | OR
    conditions: list[ScreenCondition] = field(default_factory=list)
    children: list[ScreenNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if self.conditions and not self.children:
            return {"op": self.op, "conditions": [c.to_dict() for c in self.conditions]}
        return {
            "op": self.op,
            "children": [c.to_dict() for c in self.children],
            "conditions": [c.to_dict() for c in self.conditions] or None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScreenNode:
        op = str(d.get("op", "AND")).upper()
        if op not in ("AND", "OR"):
            raise ValueError(f"screen node op must be AND or OR, got {op!r}")
        node = cls(op=op)
        for c in d.get("conditions") or []:
            node.conditions.append(ScreenCondition.from_dict(c))
        for ch in d.get("children") or []:
            node.children.append(cls.from_dict(ch))
        if not node.conditions and not node.children:
            raise ValueError("screen node has neither conditions nor children")
        return node

    def render(self) -> str:
        parts = [c.render() for c in self.conditions] + [f"({ch.render()})" for ch in self.children]
        return f" {self.op} ".join(parts)


#: Metrics the scanner understands. Each maps to a callable over the symbol's
#: history, returning (value, human_readable_detail) or None when ineligible.
def _close_at(df: pd.DataFrame, n: int = 1) -> float | None:
    if len(df) < n:
        return None
    v = df["close"].iloc[-n]
    return None if pd.isna(v) else float(v)


def _return_over(df: pd.DataFrame, days: int) -> float | None:
    if len(df) <= days:
        return None
    end = df["close"].iloc[-1]
    start = df["close"].iloc[-1 - days]
    if pd.isna(end) or pd.isna(start) or start == 0:
        return None
    return float(end / start - 1.0)


def _benchmark_return(benchmark: pd.DataFrame, as_of: Any, days: int) -> float | None:
    """The benchmark's own return over *days* bars, truncated to *as_of*.

    Uses only benchmark closes on or before the security's latest date, so a
    historical screen never sees benchmark data the security could not have.
    """
    if benchmark is None or benchmark.empty:
        return None
    df = benchmark
    if as_of is not None and "trading_date" in df.columns:
        df = df[df["trading_date"] <= as_of]
    if len(df) <= days:
        return None
    return _return_over(df, days)


def _metric_value(
    metric: str,
    df: pd.DataFrame,
    lookback: int | None = None,
    benchmark: pd.DataFrame | None = None,
) -> float | None:
    """Compute one metric from a symbol's history (ascending, latest last).

    ``lookback`` is the window for period-parameterised metrics (sma, ema,
    close_vs_sma); when omitted the metric's own default applies.
    ``benchmark`` is only consulted by ``relative_strength`` — every other
    metric is unchanged and needs no benchmark.
    """
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float) if "high" in df else None
    low = df["low"].to_numpy(dtype=float) if "low" in df else None
    volume = df["volume"].to_numpy(dtype=float) if "volume" in df else None

    def _last(col: str) -> float | None:
        if col not in df.columns or not len(df):
            return None
        v = df[col].iloc[-1]
        return None if pd.isna(v) else float(v)

    if metric == "close":
        return _close_at(df)
    if metric == "volume":
        return _last("volume")
    if metric == "turnover":
        return _last("turnover")
    if metric == "return_1d":
        return _return_over(df, 1)
    if metric == "return_5d":
        return _return_over(df, 5)
    if metric == "return_20d":
        return _return_over(df, 20)
    if metric == "return_60d":
        return _return_over(df, 60)
    if metric == "return_120d":
        return _return_over(df, 120)

    if metric == "rsi":
        return ta_compute("rsi", {"close": close}, period=14).latest()["rsi"]
    if metric == "sma":
        return ta_compute("sma", {"close": close}, period=lookback or 50).latest()["sma"]
    if metric == "ema":
        return ta_compute("ema", {"close": close}, period=lookback or 20).latest()["ema"]
    if metric == "close_vs_sma":
        # Fractional distance of the last close from its SMA (positive = above).
        period = lookback or 50
        sma_v = ta_compute("sma", {"close": close}, period=period).latest()["sma"]
        last = _close_at(df)
        if not sma_v or last is None:
            return None
        return float(last / sma_v - 1.0)
    if metric == "atr_percent":
        atr = ta_compute("atr", {"high": high, "low": low, "close": close}, period=14).latest()[
            "atr"
        ]
        last = _close_at(df)
        if atr is None or not last:
            return None
        return float(atr / last * 100.0)
    if metric == "historical_volatility":
        r = ta_compute(
            "historical_volatility", {"close": close}, period=20, trading_days=250
        ).latest()["hv"]
        return r
    if metric == "relative_volume":
        r = ta_compute("relative_volume", {"volume": volume}, baseline=20).latest()["rvol"]
        return r
    if metric == "volume_sma_ratio":
        vs = ta_compute("volume_sma", {"volume": volume}, period=20).latest()["volume_sma"]
        last_v = (
            float(df["volume"].iloc[-1]) if len(df) and not pd.isna(df["volume"].iloc[-1]) else None
        )
        if not vs or last_v is None:
            return None
        return float(last_v / vs)
    if metric == "volume_ratio_50":
        # Latest volume versus its 50-bar baseline — the slower reference that
        # separates a genuinely abnormal day from a busy week.
        vs = ta_compute("volume_sma", {"volume": volume}, period=50).latest()["volume_sma"]
        last_v = (
            float(df["volume"].iloc[-1]) if len(df) and not pd.isna(df["volume"].iloc[-1]) else None
        )
        if vs is None or last_v is None or vs == 0:
            return None
        return float(last_v / vs)
    if metric == "volume_vs_20d_max":
        # Today's volume divided by the maximum volume of the last 20 sessions
        # (today included, so 1.0 means today is the biggest of the window).
        n = int(lookback) if lookback else 20
        if volume is None or len(volume) < n:
            return None
        window = volume[-n:]
        window = window[~np.isnan(window)]
        if not len(window) or np.isnan(volume[-1]):
            return None
        m = float(window.max())
        if m == 0:
            return None
        return float(volume[-1] / m)
    if metric == "volume_climax_5_20":
        # Biggest volume of the last 5 sessions versus the 20-bar mean — an
        # intensity reading, direction-agnostic by construction.
        if volume is None or len(volume) < 20:
            return None
        last5 = volume[-5:]
        last5 = last5[~np.isnan(last5)]
        base = volume[-20:]
        base = base[~np.isnan(base)]
        if not len(last5) or not len(base) or float(base.mean()) == 0:
            return None
        return float(last5.max() / base.mean())
    if metric == "updown_volume_ratio":
        # Up-day volume / down-day volume over `lookback` sessions (default 20).
        # Days where close is unchanged contribute to neither side.
        n = int(lookback) if lookback else 20
        if volume is None or len(close) < n + 1:
            return None
        c = close[-(n + 1) :]
        v = volume[-(n + 1) :]
        pair = ~np.isnan(c[1:]) & ~np.isnan(c[:-1]) & ~np.isnan(v[1:])
        if not pair.any():
            return None
        chg = c[1:][pair] - c[:-1][pair]
        vv = v[1:][pair]
        up = float(vv[chg > 0].sum())
        dn = float(vv[chg < 0].sum())
        if dn <= 0:
            return None  # undefined ratio; never reported as infinity
        return up / dn
    if metric == "obv_pressure_20":
        # Net directional volume over `lookback` sessions divided by the total
        # volume traded in the window: (ΔOBV) / Σvolume ∈ [-1, 1]. Normalises
        # the arbitrary OBV level into an interpretable fraction.
        n = int(lookback) if lookback else 20
        if volume is None or len(close) < n + 1:
            return None
        obv_vals = ta_compute("obv", {"close": close, "volume": volume}).values["obv"]
        if len(obv_vals) < n + 1 or np.isnan(obv_vals[-1]) or np.isnan(obv_vals[-1 - n]):
            return None
        total = float(np.nansum(volume[-n:]))
        if total <= 0:
            return None
        return float((obv_vals[-1] - obv_vals[-1 - n]) / total)
    if metric == "range_compression_20":
        # Today's high-low range divided by the mean range of the previous 20
        # sessions (today excluded so the ratio is not self-referential).
        n = int(lookback) if lookback else 20
        if high is None or low is None or len(close) < n + 1:
            return None
        rng = high - low
        today = rng[-1]
        prev = rng[-(n + 1) : -1]
        prev = prev[~np.isnan(prev)]
        if np.isnan(today) or not len(prev) or float(prev.mean()) == 0:
            return None
        return float(today / prev.mean())
    if metric == "pocket_pivot":
        # Moriarty/Kacher pocket pivot: today closes up and today's volume
        # exceeds the highest volume of any DOWN day in the prior 10 sessions.
        # 1.0 = today is a pocket-pivot day, 0.0 = not, None = not enough data.
        if volume is None or len(close) < 12:
            return None
        if np.isnan(close[-1]) or np.isnan(close[-2]):
            return None
        if not close[-1] > close[-2]:
            return 0.0
        prior_c = close[-12:-1]  # 11 closes -> 10 day-to-day changes
        prior_v = volume[-11:-1]  # volume of each of the 10 prior days
        down_vols = prior_v[prior_c[1:] < prior_c[:-1]]
        down_vols = down_vols[~np.isnan(down_vols)]
        if not len(down_vols) or np.isnan(volume[-1]):
            return None
        return 1.0 if volume[-1] > float(down_vols.max()) else 0.0
    if metric == "distance_from_high_52w":
        # Percent below the trailing 250-bar (52-week) high. Negative = at the high.
        if len(close) < 20:
            return None
        window = close[-250:]
        window = window[~np.isnan(window)]
        if not len(window):
            return None
        hh = float(window.max())
        last = _close_at(df)
        if not hh or last is None:
            return None
        return float(last / hh - 1.0)
    if metric == "distance_from_low_52w":
        if len(close) < 20:
            return None
        window = close[-250:]
        window = window[~np.isnan(window)]
        if not len(window):
            return None
        ll = float(window.min())
        last = _close_at(df)
        if not ll or last is None:
            return None
        return float(last / ll - 1.0)
    if metric in ("macd", "macd_signal", "macd_histogram"):
        res = ta_compute("macd", {"close": close}).latest()
        key = {"macd": "macd", "macd_signal": "signal", "macd_histogram": "histogram"}[metric]
        return res.get(key)
    if metric == "macd_cross":
        # +1 if the MACD line crossed above its signal line on the latest bar,
        # -1 if it crossed below, 0 if there was no cross on that bar.
        res = ta_compute("macd", {"close": close})
        macd_v, sig = res.values.get("macd"), res.values.get("signal")
        if macd_v is None or sig is None or len(macd_v) < 2:
            return None
        m1, s1, m0, s0 = macd_v[-2], sig[-2], macd_v[-1], sig[-1]
        if any(np.isnan(x) for x in (m1, s1, m0, s0)):
            return None
        if m1 <= s1 and m0 > s0:
            return 1.0
        if m1 >= s1 and m0 < s0:
            return -1.0
        return 0.0
    if metric == "sma_cross":
        # (SMA(fast) / SMA(slow)) - 1 with fast=5 and slow from `lookback` (20).
        slow = lookback or 20
        fast_v = ta_compute("sma", {"close": close}, period=5).latest()["sma"]
        slow_v = ta_compute("sma", {"close": close}, period=slow).latest()["sma"]
        if not fast_v or not slow_v:
            return None
        return float(fast_v / slow_v - 1.0)
    if metric == "bollinger_percent_b":
        res = ta_compute("bollinger", {"close": close}, period=lookback or 20).latest()
        return res.get("percent_b")
    if metric == "bollinger_bandwidth":
        res = ta_compute("bollinger", {"close": close}, period=lookback or 20).latest()
        return res.get("bandwidth")
    if metric in ("stochastic_k", "stochastic_d"):
        res = ta_compute("stochastic", {"high": high, "low": low, "close": close}).latest()
        return res.get("k" if metric == "stochastic_k" else "d")
    if metric == "mfi":
        return ta_compute(
            "mfi", {"high": high, "low": low, "close": close, "volume": volume}
        ).latest()["mfi"]
    if metric == "adx":
        return ta_compute("adx", {"high": high, "low": low, "close": close}).latest()["adx"]
    if metric == "donchian_position":
        # Where the latest close sits inside its Donchian channel: 0 = lower
        # band, 1 = upper band. NaN when the channel is degenerate.
        res = ta_compute("donchian", {"high": high, "low": low}, period=lookback or 20).latest()
        up, lo = res.get("upper"), res.get("lower")
        last = _close_at(df)
        if up is None or lo is None or last is None or up == lo:
            return None
        return float((last - lo) / (up - lo))
    if metric == "donchian_breakout":
        # +1 when the latest close exceeded the prior channel high (which
        # excludes that same bar), -1 for the prior channel low, else 0.
        p = lookback or 20
        if high is None or low is None or len(close) < p + 1:
            return None
        prior_hi = float(np.nanmax(high[-p - 1 : -1]))
        prior_lo = float(np.nanmin(low[-p - 1 : -1]))
        last = _close_at(df)
        if last is None:
            return None
        if last > prior_hi:
            return 1.0
        if last < prior_lo:
            return -1.0
        return 0.0
    if metric == "turnover_sma_ratio":
        if "turnover" not in df.columns:
            return None
        to = df["turnover"].to_numpy(dtype=float)
        to = to[~np.isnan(to)]
        if to.size < 2:
            return None
        base = float(np.mean(to[-21:-1])) if to.size > 21 else float(np.mean(to[:-1]))
        if base == 0:
            return None
        return float(to[-1] / base)
    if metric == "bars_listed":
        return float(len(df))
    if metric == "relative_strength":
        days = int(lookback) if lookback else 60
        own = _return_over(df, days)
        if own is None:
            return None
        as_of = df["trading_date"].max() if "trading_date" in df.columns else None
        bench = _benchmark_return(benchmark, as_of, days)
        if bench is None:
            return None
        return float((own - bench) * 100.0)
    raise ValueError(f"unknown metric {metric!r}. Known metrics: {', '.join(sorted(METRIC_HELP))}")


METRIC_HELP: dict[str, str] = {
    "close": "Latest closing price (NPR).",
    "volume": "Latest traded quantity (shares).",
    "turnover": "Latest traded amount (NPR).",
    "return_1d": "Close-to-close return over 1 trading day.",
    "return_5d": "Close-to-close return over 5 trading days.",
    "return_20d": "Close-to-close return over 20 trading days.",
    "return_60d": "Close-to-close return over 60 trading days.",
    "return_120d": "Close-to-close return over 120 trading days.",
    "rsi": "Relative Strength Index, period 14 (Wilder smoothing).",
    "sma": "Simple moving average of close; period from `lookback` (default 50).",
    "ema": "Exponential moving average of close; period from `lookback` (default 20).",
    "close_vs_sma": "Fractional distance of close from its SMA; period from "
    "`lookback` (default 50). Positive = above the average.",
    "atr_percent": "ATR(14) as a percentage of the latest close.",
    "historical_volatility": "Annualised close-to-close volatility, period 20 (%).",
    "relative_volume": "Latest volume / mean volume over the trailing 20 bars.",
    "volume_sma_ratio": "Latest volume / 20-bar volume moving average.",
    "volume_ratio_50": "Latest volume / 50-bar volume moving average.",
    "volume_vs_20d_max": "Latest volume / the maximum volume of the last 20 sessions "
    "(today included, so 1.0 = the biggest volume of the window).",
    "volume_climax_5_20": "Largest volume of the last 5 sessions / 20-bar mean volume. "
    "Direction-agnostic impulse reading.",
    "updown_volume_ratio": "Up-day volume / down-day volume over the trailing N sessions "
    "(default 20; unchanged days count on neither side).",
    "obv_pressure_20": "Change in OBV over N sessions / total volume traded in those "
    "sessions (default N=20), i.e. the net directional volume fraction in [-1, 1].",
    "range_compression_20": "Today's high-low range / mean range of the previous 20 "
    "sessions (today excluded). Below 1 = coiling.",
    "pocket_pivot": "1.0 when today closes up on volume above the highest down-day "
    "volume of the prior 10 sessions (Moriarty/Kacher pocket pivot), else 0.0.",
    "distance_from_high_52w": "Percent below the trailing 250-bar high (0 = at the high).",
    "distance_from_low_52w": "Percent above the trailing 250-bar low (0 = at the low).",
    "macd": "Latest MACD line (EMA12 - EMA26).",
    "macd_signal": "Latest MACD signal line (EMA9 of MACD).",
    "macd_histogram": "Latest MACD histogram (MACD - signal).",
    "macd_cross": "+1 if MACD crossed above its signal line on the latest bar, "
    "-1 if it crossed below, 0 otherwise.",
    "sma_cross": "(SMA5 / SMA(slow) - 1) with slow from `lookback` (default 20). "
    "Positive = the fast average is above the slow average.",
    "bollinger_percent_b": "Bollinger %B: 0 at the lower band, 1 at the upper band.",
    "bollinger_bandwidth": "Bollinger bandwidth (upper - lower) / middle.",
    "stochastic_k": "Latest stochastic %K (period 14, smoothed 3).",
    "stochastic_d": "Latest stochastic %D (3-period average of %K).",
    "mfi": "Money Flow Index, period 14 (0-100).",
    "adx": "Average Directional Index, period 14 (trend strength, not direction).",
    "donchian_position": "Where the close sits inside its Donchian channel "
    "(0 = lower band, 1 = upper band).",
    "donchian_breakout": "+1 on a new channel-high close, -1 on a new channel-low "
    "close (the channel excludes the latest bar), 0 otherwise.",
    "turnover_sma_ratio": "Latest turnover / the trailing 20-bar average turnover.",
    "bars_listed": "Number of bars in the symbol's stored history.",
    "relative_strength": "Close-to-close return in excess of the NEPSE composite "
    "index over `lookback` bars (default 60), in percentage points. Positive = "
    "the stock beat the index over the same window. Unavailable (ineligible, "
    "with a reason) when the benchmark series is missing or too short on or "
    "before the security's latest date — never computed against a substitute.",
}


@dataclass(slots=True)
class ScreenResult:
    """One security's evaluation."""

    symbol: str
    eligible: bool
    passed: bool
    reasons: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    metrics: dict[str, float | None] = field(default_factory=dict)
    note: str = ""
    last_date: str | None = None


def validate_tree(node: ScreenNode) -> list[str]:
    """Return a list of problems with a screen definition.

    Used to reject a malformed screen up front (with a clear message) rather
    than letting every security quietly come back "ineligible".
    """
    problems: list[str] = []

    def walk(n: ScreenNode) -> None:
        for c in n.conditions:
            if c.metric not in METRIC_HELP:
                problems.append(
                    f"unknown metric {c.metric!r}; known metrics: {', '.join(sorted(METRIC_HELP))}"
                )
            if c.lookback is not None and c.lookback <= 0:
                problems.append(f"{c.metric}: lookback must be > 0, got {c.lookback}")
        for child in n.children:
            walk(child)

    walk(node)
    return problems


def _tree_uses(node: ScreenNode, metric: str) -> bool:
    """True when any condition in the tree names *metric* (recursive)."""
    return any(c.metric == metric for c in node.conditions) or any(
        _tree_uses(child, metric) for child in node.children
    )


def deduplicate_symbols(symbols: Iterable[str]) -> list[str]:
    """Order-preserving de-duplication of a symbol list.

    A symbol named twice should be screened once: repeating it would otherwise
    produce two identical rows and inflate the match count. Input order is kept
    so a scan remains reproducible for the same universe in the same order.
    """
    return list(dict.fromkeys(symbols))


def evaluate_condition(
    cond: ScreenCondition, df: pd.DataFrame, benchmark: pd.DataFrame | None = None
) -> tuple[bool | None, str]:
    """Evaluate one condition. Returns (result, explanation); result is None if ineligible."""
    try:
        actual = _metric_value(cond.metric, df, cond.lookback, benchmark)
    except ValueError as exc:
        return None, str(exc)
    if actual is None:
        return None, f"{cond.metric} unavailable for this security"
    ok = OPERATORS[cond.operator](actual, cond.value)
    return bool(ok), f"{cond.render()} -> actual {actual:.4g}"


def evaluate_node(
    node: ScreenNode, df: pd.DataFrame, benchmark: pd.DataFrame | None = None
) -> tuple[bool | None, list[str], list[str]]:
    """Evaluate a (possibly nested) node. Returns (result, passed_reasons, failed_reasons)."""
    results: list[bool] = []
    passed: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []

    for cond in node.conditions:
        ok, why = evaluate_condition(cond, df, benchmark)
        if ok is None:
            unknown.append(why)
            continue
        results.append(ok)
        (passed if ok else failed).append(why)

    for child in node.children:
        ok, cpass, cfail = evaluate_node(child, df, benchmark)
        if ok is None:
            unknown.extend(cfail)
            continue
        results.append(ok)
        label = child.render()
        if ok:
            passed.append(f"group ({label}) satisfied")
        else:
            failed.append(f"group ({label}) not satisfied")

    if not results:
        return None, passed, unknown

    # Three-valued logic. A condition that could not be computed is *unknown*,
    # and unknown must never be treated as true: that is how a flat/illiquid
    # symbol used to "pass" ``rsi < 30 AND bars_listed >= 60`` because only the
    # bars clause was evaluated (the RSI clause vanished from the reasons). A
    # missing metric must not silently qualify a security.
    if node.op == "AND":
        value = all(results)
        if value and unknown:
            # Every computable clause passed, but a required clause did not
            # compute — the gate is not satisfied.
            return None, passed, unknown
    else:
        value = any(results)
        if not value and unknown:
            # No clause is known true, so the OR result is unknown, not False.
            return None, passed, unknown
    return value, passed, failed


def run_screen(
    store: MarketStore,
    node: ScreenNode,
    symbols: Iterable[str] | None = None,
    as_of: date | None = None,
    min_bars: int = MIN_BARS_FOR_SCREEN,
    *,
    exclude_delisted: bool = True,
    instrument_types: Sequence[str] | None = None,
) -> list[ScreenResult]:
    """Screen the stored universe. ``as_of`` caps the history used (reproducibility).

    By default the screen excludes verified non-tradable securities
    (``DELISTED``, ``SUSPENDED`` and ``MERGED``) while keeping ``ACTIVE`` and
    ``UNKNOWN`` symbols visible. ``UNKNOWN`` symbols are allowed so that
    missing metadata does not silently erase valid securities, but the reason
    string notes the uncertainty so it is observable. Pass
    ``exclude_delisted=False`` to include every symbol with stored history
    (the pre-filter behaviour).

    ``instrument_types`` is an optional additional filter over
    ``security_master.instrument_type``. When either filter is active:

    * one metadata query is made for the whole run;
    * a symbol is marked ineligible — with the exact reason — when the field
      the filter needs is stored as a non-matching type or **unknown** (NULL /
      no row). Unknown metadata is never treated as eligible and is never
      replaced by a guessed classification;
    * stored bars are untouched, so an inactive security remains fully
      analysable via ``as_of`` or by naming it with ``exclude_delisted=False``.
    """
    # De-duplicate so a symbol named twice is screened once (order preserved).
    wanted = deduplicate_symbols(list(symbols) if symbols else store.symbols(min_bars=1))
    filters_active = exclude_delisted or instrument_types is not None
    # One metadata query for the whole run, and only when a filter needs it.
    # The corporate-action registry fills the gap an empty security_master
    # leaves, so a merged symbol without a stored row is still excluded.
    meta = (
        corporate_actions.merge_into_meta(store.securities_meta(wanted), wanted)
        if filters_active
        else {}
    )
    results: list[ScreenResult] = []

    # ``relative_strength`` needs the official composite index. Load it only
    # when the tree actually asks for it, so every other screen is unchanged
    # (and never pays for a benchmark query).
    benchmark: pd.DataFrame | None = None
    if _tree_uses(node, "relative_strength"):
        from megatool.ranking import NEPSE_COMPOSITE_INDEX

        try:
            bench = store.index_closes(NEPSE_COMPOSITE_INDEX)
        except Exception:  # pragma: no cover - defensive
            bench = None
        benchmark = bench if bench is not None and not bench.empty else None

    for symbol in wanted:
        eligibility_note = ""
        if filters_active:
            allowed, reason = eligibility_from_meta(
                meta.get(str(symbol).upper()),
                exclude_delisted=exclude_delisted,
                instrument_types=instrument_types,
            )
            if not allowed:
                results.append(ScreenResult(symbol, eligible=False, passed=False, note=reason))
                continue
            eligibility_note = reason
        df = store.get_bars(symbol, end=as_of)
        if df.empty:
            results.append(
                ScreenResult(
                    symbol, eligible=False, passed=False, note="no stored history for this security"
                )
            )
            continue
        if len(df) < min_bars:
            results.append(
                ScreenResult(
                    symbol,
                    eligible=False,
                    passed=False,
                    note=f"only {len(df)} bars stored; needs at least {min_bars}",
                    last_date=str(df["trading_date"].max().date()),
                )
            )
            continue

        value, passed_reasons, failed_reasons = evaluate_node(node, df, benchmark)
        if value is None:
            results.append(
                ScreenResult(
                    symbol,
                    eligible=False,
                    passed=False,
                    failures=failed_reasons,
                    note="one or more metrics could not be computed",
                    last_date=str(df["trading_date"].max().date()),
                )
            )
            continue

        results.append(
            ScreenResult(
                symbol=symbol,
                eligible=True,
                passed=bool(value),
                reasons=passed_reasons if value else [],
                failures=[] if value else failed_reasons,
                note=eligibility_note,
                last_date=str(df["trading_date"].max().date()),
            )
        )
    return results


def to_dataframe(results: list[ScreenResult]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": r.symbol,
                "eligible": r.eligible,
                "passed": r.passed,
                "last_date": r.last_date,
                "note": r.note,
                "passed_reasons": " | ".join(r.reasons),
                "failed_reasons": " | ".join(r.failures),
            }
            for r in results
        ]
    )


#: Ready-made screens the owner can start from and edit.
PRESET_SCREENS: dict[str, dict[str, Any]] = {
    "oversold_rsi": {
        "name": "Oversold momentum",
        "description": "RSI below 30 with at least 60 bars of history. "
        "An RSI reading is a historical statistic, not a prediction.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "rsi", "operator": "lt", "value": 30},
                {"metric": "bars_listed", "operator": "gte", "value": 60},
            ],
        },
    },
    "volume_surge": {
        "name": "Unusual volume",
        "description": "Today's volume at least 2x the 20-bar average.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "volume_sma_ratio", "operator": "gte", "value": 2.0},
                {"metric": "bars_listed", "operator": "gte", "value": 25},
            ],
        },
    },
    "near_52w_high": {
        "name": "Within 5% of 250-bar high",
        "description": "Proximity to a multi-month high. Breakouts are "
        "descriptive, not confirmations of future returns.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "distance_from_high_52w", "operator": "gte", "value": -0.05},
                {"metric": "bars_listed", "operator": "gte", "value": 250},
            ],
        },
    },
    "above_sma50": {
        "name": "Above 50-day SMA",
        "description": "Close more than 5% above its 50-bar simple moving average.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "close_vs_sma", "operator": "gt", "value": 0.05, "lookback": 50},
                {"metric": "bars_listed", "operator": "gte", "value": 60},
            ],
        },
    },
    "rsi_overbought": {
        "name": "Overbought momentum",
        "description": "RSI above 70 with at least 60 bars of history. Overbought "
        "is a historical reading, not a prediction of a reversal.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "rsi", "operator": "gt", "value": 70},
                {"metric": "bars_listed", "operator": "gte", "value": 60},
            ],
        },
    },
    "macd_bullish_cross": {
        "name": "MACD bullish cross",
        "description": "The MACD line crossed above its signal line on the most "
        "recent bar (single-bar event, not a trend).",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "macd_cross", "operator": "gt", "value": 0},
                {"metric": "bars_listed", "operator": "gte", "value": 60},
            ],
        },
    },
    "macd_bearish_cross": {
        "name": "MACD bearish cross",
        "description": "The MACD line crossed below its signal line on the most recent bar.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "macd_cross", "operator": "lt", "value": 0},
                {"metric": "bars_listed", "operator": "gte", "value": 60},
            ],
        },
    },
    "above_sma20": {
        "name": "Above 20-day SMA",
        "description": "Close above its 20-bar simple moving average.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "close_vs_sma", "operator": "gt", "value": 0.0, "lookback": 20},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "above_sma200": {
        "name": "Above 200-day SMA",
        "description": "Close above its 200-bar simple moving average (long-term "
        "trend filter; needs a long history).",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "close_vs_sma", "operator": "gt", "value": 0.0, "lookback": 200},
                {"metric": "bars_listed", "operator": "gte", "value": 220},
            ],
        },
    },
    "sma5_above_sma20": {
        "name": "SMA5 above SMA20",
        "description": "Short-term average above the intermediate average "
        "(a descriptive trend alignment, not a signal to trade).",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "sma_cross", "operator": "gt", "value": 0.0, "lookback": 20},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "bollinger_lower_band": {
        "name": "At the lower Bollinger Band",
        "description": "Bollinger %B at or below 0.1 (close near the lower band, "
        "period 20, 2 std).",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "bollinger_percent_b", "operator": "lte", "value": 0.1},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "bollinger_upper_band": {
        "name": "At the upper Bollinger Band",
        "description": "Bollinger %B at or above 0.9 (close near the upper band).",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "bollinger_percent_b", "operator": "gte", "value": 0.9},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "bollinger_squeeze": {
        "name": "Bollinger squeeze",
        "description": "Bollinger bandwidth below the listed value (volatility "
        "contraction). Squeezes do not predict the direction of the next move.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "bollinger_bandwidth", "operator": "lt", "value": 0.08},
                {"metric": "bars_listed", "operator": "gte", "value": 40},
            ],
        },
    },
    "stochastic_oversold": {
        "name": "Stochastic oversold",
        "description": "Stochastic %K below 20 (period 14, smoothed 3).",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "stochastic_k", "operator": "lt", "value": 20},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "stochastic_overbought": {
        "name": "Stochastic overbought",
        "description": "Stochastic %K above 80.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "stochastic_k", "operator": "gt", "value": 80},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "mfi_oversold": {
        "name": "Money Flow oversold",
        "description": "Money Flow Index below 20 (volume-weighted, period 14). "
        "Requires volume history.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "mfi", "operator": "lt", "value": 20},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "donchian_breakout_up": {
        "name": "Donchian channel breakout (up)",
        "description": "Latest close above the prior 20-bar channel high. The "
        "channel excludes the latest bar to avoid look-ahead.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "donchian_breakout", "operator": "gt", "value": 0},
                {"metric": "bars_listed", "operator": "gte", "value": 40},
            ],
        },
    },
    "breakout_with_volume": {
        "name": "Channel breakout with volume",
        "description": "A new 20-bar channel high confirmed by volume at least "
        "1.5x its 20-bar average.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "donchian_breakout", "operator": "gt", "value": 0},
                {"metric": "relative_volume", "operator": "gte", "value": 1.5},
                {"metric": "bars_listed", "operator": "gte", "value": 40},
            ],
        },
    },
    "near_52w_low": {
        "name": "Within 5% of 250-bar low",
        "description": "Close within 5% of its trailing 250-bar low.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "distance_from_low_52w", "operator": "lte", "value": 0.05},
                {"metric": "bars_listed", "operator": "gte", "value": 250},
            ],
        },
    },
    "momentum_20d": {
        "name": "20-day momentum",
        "description": "Close-to-close return over 20 trading days above 10%.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "return_20d", "operator": "gt", "value": 0.10},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "strong_trend_adx": {
        "name": "Strong trend (ADX)",
        "description": "ADX at or above 25 with the close above its 50-bar "
        "average. ADX measures trend strength, not direction.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "adx", "operator": "gte", "value": 25},
                {"metric": "close_vs_sma", "operator": "gt", "value": 0.0, "lookback": 50},
                {"metric": "bars_listed", "operator": "gte", "value": 60},
            ],
        },
    },
    "low_volatility": {
        "name": "Low volatility",
        "description": "Annualised 20-bar close-to-close volatility below 20%.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "historical_volatility", "operator": "lt", "value": 20},
                {"metric": "bars_listed", "operator": "gte", "value": 40},
            ],
        },
    },
    "liquid_turnover": {
        "name": "Liquid by turnover",
        "description": "Latest turnover at least NPR 1,000,000 and at least 1.5x "
        "its 20-bar average.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "turnover", "operator": "gte", "value": 1_000_000},
                {"metric": "turnover_sma_ratio", "operator": "gte", "value": 1.5},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    # ------------------------------------------------------ volume scanner set
    # Part 15: dedicated volume-analysis screens. Each condition reads only the
    # latest stored bar and the history before it; descriptions state the exact
    # definition so a result can be audited bar by bar.
    "volume_dryup": {
        "name": "Volume dry-up (quiet coiling)",
        "description": "Volume at most 60% of its 20-bar average AND today's range "
        "at most 70% of the previous 20-bar mean range. A contraction reading, "
        "not a prediction of direction.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "volume_sma_ratio", "operator": "lte", "value": 0.6},
                {"metric": "range_compression_20", "operator": "lte", "value": 0.7},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "accumulation_20d": {
        "name": "20-session accumulation",
        "description": "Up-day volume at least 1.5x down-day volume over the last "
        "20 sessions — accumulation pressure visible in the historical tape.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "updown_volume_ratio", "operator": "gte", "value": 1.5},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "distribution_20d": {
        "name": "20-session distribution",
        "description": "Down-day volume at least 1.5x up-day volume over the last "
        "20 sessions — the mirror of the accumulation screen. A ratio, so it is "
        "expressed as up/down volume at most 1/1.5.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "updown_volume_ratio", "operator": "lte", "value": 1 / 1.5},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "pocket_pivot": {
        "name": "Pocket pivot day",
        "description": "Close up with volume above the highest down-day volume of "
        "the prior 10 sessions (Moriarty/Kacher pocket pivot). Single-bar event.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "pocket_pivot", "operator": "gte", "value": 1},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "obv_accumulation_20d": {
        "name": "OBV accumulation (20 sessions)",
        "description": "Net directional volume over the last 20 sessions at least "
        "+30% of total traded volume (ΔOBV / Σvolume ≥ 0.3).",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "obv_pressure_20", "operator": "gte", "value": 0.3},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "volume_climax": {
        "name": "Volume climax (5 vs 20)",
        "description": "The largest volume of the last 5 sessions is at least 3x "
        "the 20-bar mean. Climaxes mark exhaustion or initiation — direction is "
        "not implied.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "volume_climax_5_20", "operator": "gte", "value": 3.0},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "biggest_volume_20d": {
        "name": "Biggest volume in 20 sessions, up day",
        "description": "Today's volume is the highest of the last 20 sessions and "
        "today's close is up versus the previous session.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "volume_vs_20d_max", "operator": "gte", "value": 0.999},
                {"metric": "return_1d", "operator": "gt", "value": 0.0},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        },
    },
    "unusual_volume_50": {
        "name": "Unusual volume vs 50-bar baseline",
        "description": "Today's volume at least 2x its 50-bar moving average — "
        "filters out weeks that were merely busy.",
        "tree": {
            "op": "AND",
            "conditions": [
                {"metric": "volume_ratio_50", "operator": "gte", "value": 2.0},
                {"metric": "bars_listed", "operator": "gte", "value": 60},
            ],
        },
    },
}
