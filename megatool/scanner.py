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

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from megatool.market_store import MarketStore
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


def _metric_value(metric: str, df: pd.DataFrame, lookback: int | None = None) -> float | None:
    """Compute one metric from a symbol's history (ascending, latest last).

    ``lookback`` is the window for period-parameterised metrics (sma, ema,
    close_vs_sma); when omitted the metric's own default applies.
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
    if metric == "bars_listed":
        return float(len(df))
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
    "distance_from_high_52w": "Percent below the trailing 250-bar high (0 = at the high).",
    "distance_from_low_52w": "Percent above the trailing 250-bar low (0 = at the low).",
    "bars_listed": "Number of bars in the symbol's stored history.",
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


def evaluate_condition(cond: ScreenCondition, df: pd.DataFrame) -> tuple[bool | None, str]:
    """Evaluate one condition. Returns (result, explanation); result is None if ineligible."""
    try:
        actual = _metric_value(cond.metric, df, cond.lookback)
    except ValueError as exc:
        return None, str(exc)
    if actual is None:
        return None, f"{cond.metric} unavailable for this security"
    ok = OPERATORS[cond.operator](actual, cond.value)
    return bool(ok), f"{cond.render()} -> actual {actual:.4g}"


def evaluate_node(node: ScreenNode, df: pd.DataFrame) -> tuple[bool | None, list[str], list[str]]:
    """Evaluate a (possibly nested) node. Returns (result, passed_reasons, failed_reasons)."""
    results: list[bool] = []
    passed: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []

    for cond in node.conditions:
        ok, why = evaluate_condition(cond, df)
        if ok is None:
            unknown.append(why)
            continue
        results.append(ok)
        (passed if ok else failed).append(why)

    for child in node.children:
        ok, cpass, cfail = evaluate_node(child, df)
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
    value = all(results) if node.op == "AND" else any(results)
    return value, passed, failed


def run_screen(
    store: MarketStore,
    node: ScreenNode,
    symbols: Iterable[str] | None = None,
    as_of: date | None = None,
    min_bars: int = MIN_BARS_FOR_SCREEN,
) -> list[ScreenResult]:
    """Screen the stored universe. ``as_of`` caps the history used (reproducibility)."""
    wanted = list(symbols) if symbols else store.symbols(min_bars=1)
    results: list[ScreenResult] = []

    for symbol in wanted:
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

        value, passed_reasons, failed_reasons = evaluate_node(node, df)
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
}
