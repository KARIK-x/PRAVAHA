"""Deterministic market-regime detection (Phase 2, feature 8).

The market is characterised by three causal, explainable labels computed from
an equal-weighted market proxy:

* **trend** — proxy level vs its own 200-session SMA (``bull`` above, ``bear``
  below), with the 50/200 SMA relation reported as context;
* **volatility** — annualised 20-session realised volatility placed by the
  proxy's own causal rolling terciles (``low`` / ``normal`` / ``high``);
* **momentum** — trailing 60-session proxy return (``positive`` above +5%,
  ``negative`` below -5%, else ``neutral``).

Look-ahead discipline: every label at date *t* uses only data up to *t*
(rolling windows and quantiles end at *t*). Truncating the series after *t*
never changes the label at *t* — that property is pinned by a test.

The proxy is the equal-weighted mean of per-symbol daily returns across the
stored universe. It is **not** the official NEPSE index (which is
capitalisation-weighted and currently unavailable, blocker B-10); it is a
transparent stand-in and is labelled as one everywhere it is reported.

Insufficient data is an explicit status, never a guessed label: series shorter
than ``min_bars`` yield ``insufficient_data``, and warmup rows inside a long
series carry ``insufficient`` per component until their window is fillable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

#: Session count required before any label is reported.
MIN_BARS = 260
#: Minimum symbols with a valid return on a date for the proxy to exist.
MIN_SYMBOLS = 10
FAST_SMA = 50
SLOW_SMA = 200
VOL_WINDOW = 20
VOL_LOOKBACK = 250
VOL_MIN_PERIODS = 120
MOMENTUM_WINDOW = 60
MOMENTUM_BAND = 0.05

_TREND = ("bull", "bear")
_VOL = ("low", "normal", "high")
_MOMENTUM = ("positive", "neutral", "negative")


@dataclass(slots=True)
class RegimeResult:
    """Outcome of a regime scan: current labels, history, and their limits."""

    status: str  # "ok" | "insufficient_data"
    reason: str
    last_date: str | None
    bars: int
    symbols: int
    params: dict[str, Any] = field(default_factory=dict)
    current: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "last_date": self.last_date,
            "bars": self.bars,
            "symbols": self.symbols,
            "params": self.params,
            "current": self.current,
            "history": self.history,
            "summary": self.summary,
        }


def market_proxy(closes: pd.DataFrame, min_symbols: int = MIN_SYMBOLS) -> pd.Series:
    """Equal-weighted market proxy level from a dates × symbols close matrix.

    Each date's proxy return is the mean of per-symbol simple returns over
    symbols with both closes present; dates with fewer than ``min_symbols``
    valid returns are dropped rather than computed from too little data.
    """
    if closes is None or closes.empty:
        return pd.Series(dtype=float, name="proxy_level")
    # ``all_closes`` returns a ``trading_date`` datetime column next to the
    # float symbol columns; the proxy needs numerics only (pct_change on a
    # datetime column is a type error).
    numeric = closes.select_dtypes(include=[np.number])
    pct = numeric.pct_change(fill_method=None)
    counts = pct.notna().sum(axis=1)
    mean_ret = pct.mean(axis=1, skipna=True).where(counts >= min_symbols)
    level = 100.0 * (1.0 + mean_ret).cumprod()
    level = level[mean_ret.notna()]
    level.name = "proxy_level"
    # ``all_closes`` returns ``trading_date`` as a column over a positional
    # index; without aligning to it, every reported date would be a row
    # number (seen live as ``last_date: "5195"``). Fixtures that already
    # carry a DatetimeIndex are left untouched.
    if "trading_date" in closes.columns and not isinstance(level.index, pd.DatetimeIndex):
        level = level.copy()
        level.index = pd.DatetimeIndex(closes.loc[level.index, "trading_date"])
    return level


def _labels_for(level: pd.Series) -> pd.DataFrame:
    """Causal per-date labels for a proxy level series."""
    idx = level.index
    out = pd.DataFrame(index=idx)

    sma_fast = level.rolling(FAST_SMA, min_periods=FAST_SMA).mean()
    sma_slow = level.rolling(SLOW_SMA, min_periods=SLOW_SMA).mean()
    out["trend"] = np.where(
        sma_slow.isna(),
        "insufficient",
        np.where(level > sma_slow, "bull", "bear"),
    )
    out["sma_above"] = sma_fast > sma_slow  # False while either is NaN

    vol = level.pct_change(fill_method=None).rolling(
        VOL_WINDOW, min_periods=VOL_WINDOW
    ).std() * np.sqrt(250)
    q_low = vol.rolling(VOL_LOOKBACK, min_periods=VOL_MIN_PERIODS).quantile(1 / 3)
    q_high = vol.rolling(VOL_LOOKBACK, min_periods=VOL_MIN_PERIODS).quantile(2 / 3)
    out["volatility"] = np.select(
        [q_low.isna(), vol <= q_low, vol >= q_high],
        ["insufficient", "low", "high"],
        default="normal",
    )
    out["vol_value"] = vol

    trailing = level / level.shift(MOMENTUM_WINDOW) - 1.0
    out["momentum"] = np.select(
        [trailing.isna(), trailing > MOMENTUM_BAND, trailing < -MOMENTUM_BAND],
        ["insufficient", "positive", "negative"],
        default="neutral",
    )
    out["momentum_value"] = trailing
    out["proxy_level"] = level
    return out


def detect_regimes(
    closes: pd.DataFrame,
    *,
    min_bars: int = MIN_BARS,
    min_symbols: int = MIN_SYMBOLS,
    limit: int | None = None,
) -> RegimeResult:
    """Detect trend/volatility/momentum regimes from stored closes.

    ``closes`` is a dates × symbols matrix (e.g. from
    :meth:`~megatool.market_store.MarketStore.all_closes`). Returns explicit
    ``insufficient_data`` when the usable series is shorter than ``min_bars``.
    """
    params = {
        "proxy": "equal-weighted mean of per-symbol daily returns (NOT the official NEPSE index)",
        "min_symbols": min_symbols,
        "fast_sma": FAST_SMA,
        "slow_sma": SLOW_SMA,
        "vol_window": VOL_WINDOW,
        "vol_lookback": VOL_LOOKBACK,
        "momentum_window": MOMENTUM_WINDOW,
        "momentum_band": MOMENTUM_BAND,
        "trading_days_per_year": 250,
    }
    level = market_proxy(closes, min_symbols=min_symbols)
    numeric_cols = 0 if closes is None else closes.select_dtypes(include=[np.number]).shape[1]
    if len(level) < min_bars:
        return RegimeResult(
            status="insufficient_data",
            reason=(
                f"market proxy has {len(level)} usable sessions; "
                f"{min_bars} are required before regime labels are reported"
            ),
            last_date=None,
            bars=len(level),
            symbols=numeric_cols,
            params=params,
        )

    labels = _labels_for(level)
    history = labels.iloc[-limit:].reset_index() if limit else labels.reset_index()
    date_col = history.columns[0]
    rows = [
        {
            "date": str(r[date_col])[:10],
            "proxy_level": round(float(r["proxy_level"]), 4),
            "trend": r["trend"],
            "sma_above": bool(r["sma_above"]),
            "volatility": r["volatility"],
            "vol_value": None if pd.isna(r["vol_value"]) else round(float(r["vol_value"]), 4),
            "momentum": r["momentum"],
            "momentum_value": (
                None if pd.isna(r["momentum_value"]) else round(float(r["momentum_value"]), 4)
            ),
        }
        for _, r in history.iterrows()
    ]
    tail = rows[-1]
    current = {
        "date": tail["date"],
        "trend": tail["trend"],
        "volatility": tail["volatility"],
        "momentum": tail["momentum"],
        "sma_above": tail["sma_above"],
        "vol_value": tail["vol_value"],
        "momentum_value": tail["momentum_value"],
    }
    summary = {
        "days": {
            "trend": {k: int((labels["trend"] == k).sum()) for k in (*_TREND, "insufficient")},
            "volatility": {
                k: int((labels["volatility"] == k).sum()) for k in (*_VOL, "insufficient")
            },
            "momentum": {
                k: int((labels["momentum"] == k).sum()) for k in (*_MOMENTUM, "insufficient")
            },
        },
        "transitions": {
            "trend": int((labels["trend"] != labels["trend"].shift()).sum()) - 1,
            "momentum": int((labels["momentum"] != labels["momentum"].shift()).sum()) - 1,
        },
    }
    return RegimeResult(
        status="ok",
        reason="regimes computed causally from the equal-weighted market proxy",
        last_date=tail["date"],
        bars=len(level),
        symbols=numeric_cols,
        params=params,
        current=current,
        history=rows,
        summary=summary,
    )
