"""Swing Trading Workbench: one auditable payload per symbol.

This module composes primitives that are each tested elsewhere — fractal swing
detection, structure labels, break of structure, and the indicator engine —
into the context a swing trader checks before a decision. It *computes and
labels*; it never recommends. Two rules shape every block:

* **No look-ahead.** Swings come from :func:`megatool.ta.swings.find_swings`
  and carry their ``confirmed_index``; only swings confirmed by the last bar
  are used for levels. Every indicator uses the data up to the last bar.
* **Missing evidence stays missing.** Where a computation lacks the required
  swings or bars, the field is ``None`` with a stated reason — never a filled
  default.

Blocks produced
---------------
* ``structure`` — swing list (recent slice), HH/HL/LH/LL labels, trend, breaks.
* ``nearest_levels`` — nearest confirmed support below / resistance above the
  last close, each with the date it became knowable.
* ``reference_levels`` — invalidation and measured-move arithmetic from the
  last confirmed swing of each kind, framed for the current structure.
* ``checklist`` — mechanical readings (each row: value, condition, pass,
  definition). A "pass" is the stated inequality, not a recommendation.
* ``sizing`` — position-size arithmetic for a supplied account size and risk
  fraction; pure division, no opinion.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from megatool.ta import compute as ta_compute
from megatool.ta.swings import (
    DEFAULT_LEFT,
    DEFAULT_RIGHT,
    classify_structure,
    find_breaks,
    find_swings,
)

DISCLAIMER = (
    "Mechanical aggregation of historical readings for research. Not a signal, "
    "not advice, and no statement here predicts future prices."
)


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) else v


def _last(array: np.ndarray) -> float | None:
    return _f(array[-1]) if len(array) else None


def _checklist_row(
    name: str, value: float | None, condition: str, definition: str
) -> dict[str, Any]:
    ok: bool | None
    if value is None:
        ok = None
    elif condition == "above_zero":
        ok = value > 0
    elif condition == "below_zero":
        ok = value < 0
    elif condition == "between_30_70":
        ok = 30.0 <= value <= 70.0
    elif condition == "at_least_one":
        ok = value >= 1.0
    elif condition == "within_2pct_of_high":
        ok = value >= -0.02
    elif condition == "above_3pct_from_low":
        ok = value >= 0.03
    else:  # pragma: no cover - guard against typos in condition names
        raise ValueError(f"unknown checklist condition {condition!r}")
    return {
        "name": name,
        "value": value,
        "condition": definition,
        "pass": ok,
        "missing_reason": None if value is not None else "not computable from the loaded bars",
    }


def swing_workbench(
    df: pd.DataFrame,
    *,
    left: int = DEFAULT_LEFT,
    right: int = DEFAULT_RIGHT,
    min_prominence: float = 0.0,
    recent_swings: int = 8,
    account_size: float = 100_000.0,
    risk_fraction: float = 0.01,
) -> dict[str, Any]:
    """Assemble the workbench payload from an ascending OHLCV frame."""
    if df is None or df.empty:
        raise ValueError("no bars supplied")
    if not 0 < risk_fraction <= 1:
        raise ValueError("risk_fraction must be in (0, 1]")
    if account_size <= 0:
        raise ValueError("account_size must be positive")

    df = df.sort_values("trading_date").reset_index(drop=True)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    volume = df["volume"].to_numpy(float) if "volume" in df else np.full(len(df), np.nan)
    dates = [str(pd.Timestamp(d).date()) for d in df["trading_date"]]

    swings = find_swings(high, low, left=left, right=right, min_prominence=min_prominence)
    structure = classify_structure(swings)
    breaks = find_breaks(swings, close)
    last_close = _last(close)

    confirmed = [s for s in swings if s.confirmed_index is not None and s.confirmed_index < len(df)]
    swing_highs = [s for s in confirmed if s.kind == "high"]
    swing_lows = [s for s in confirmed if s.kind == "low"]

    recent = [
        {
            "kind": s.kind,
            "date": dates[s.index],
            "price": _f(s.price),
            "confirmed_date": dates[s.confirmed_index],
        }
        for s in swings[-recent_swings:]
    ]

    # ---- nearest levels (confirmed swings only) ---------------------------
    support = None
    if last_close is not None:
        below = [s for s in swing_lows if _f(s.price) is not None and s.price < last_close]
        if below:
            support = max(below, key=lambda s: (s.price, s.confirmed_index))
    resistance = None
    if last_close is not None:
        above = [s for s in swing_highs if _f(s.price) is not None and s.price > last_close]
        if above:
            resistance = min(above, key=lambda s: (s.price, -s.confirmed_index))

    def _level_dict(s) -> dict[str, Any] | None:
        if s is None:
            return None
        return {
            "price": _f(s.price),
            "swing_date": dates[s.index],
            "confirmed_date": dates[s.confirmed_index],
        }

    nearest_levels = {
        "support": _level_dict(support),
        "resistance": _level_dict(resistance),
        "support_missing_reason": None
        if support is not None
        else "no confirmed swing low below the last close in the loaded window",
        "resistance_missing_reason": None
        if resistance is not None
        else "no confirmed swing high above the last close in the loaded window",
    }

    # ---- reference levels --------------------------------------------------
    trend = structure.get("trend")
    last_high = swing_highs[-1] if swing_highs else None
    last_low = swing_lows[-1] if swing_lows else None
    measured_range = None
    if last_high is not None and last_low is not None:
        measured_range = abs(_f(last_high.price) - _f(last_low.price))

    reference: dict[str, Any] = {
        "last_close": last_close,
        "last_swing_high": _level_dict(last_high),
        "last_swing_low": _level_dict(last_low),
        "measured_move_range": measured_range,
        "framing": None,
        "invalidation": None,
        "target": None,
        "risk_pct": None,
        "reward_pct": None,
        "reward_risk": None,
        "reason": None,
    }
    if last_close is None:
        reference["reason"] = "no valid close in the loaded window"
    elif trend == "up":
        reference["framing"] = "long"
        inval = _f(support.price) if support is not None else None
        reference["invalidation"] = nearest_levels["support"]
        if inval is not None and inval < last_close and measured_range:
            target = last_close + measured_range
            risk = last_close - inval
            reference["target"] = {
                "price": target,
                "method": "close + measured move (last high - last low)",
            }
            reference["risk_pct"] = 100.0 * risk / last_close
            reference["reward_pct"] = 100.0 * (target - last_close) / last_close
            reference["reward_risk"] = (target - last_close) / risk if risk > 0 else None
        else:
            reference["reason"] = (
                "an up structure needs a confirmed support below the close and a "
                "confirmed high-low pair for the measured move"
            )
    elif trend == "down":
        reference["framing"] = "short"
        inval = _f(resistance.price) if resistance is not None else None
        reference["invalidation"] = nearest_levels["resistance"]
        if inval is not None and inval > last_close and measured_range:
            target = last_close - measured_range
            risk = inval - last_close
            reference["target"] = {
                "price": target,
                "method": "close - measured move (last high - last low)",
            }
            reference["risk_pct"] = 100.0 * risk / last_close
            reference["reward_pct"] = 100.0 * (last_close - target) / last_close
            reference["reward_risk"] = (last_close - target) / risk if risk > 0 else None
        else:
            reference["reason"] = (
                "a down structure needs a confirmed resistance above the close and a "
                "confirmed high-low pair for the measured move"
            )
    else:
        reference["reason"] = (
            f"structure trend is '{trend}'; reference levels are only framed for "
            "decided up/down structures"
        )

    # ---- mechanical checklist ---------------------------------------------
    sma50 = _last(ta_compute("sma", {"close": close}, period=50).values["sma"])
    sma200 = _last(ta_compute("sma", {"close": close}, period=200).values["sma"])
    ema20 = _last(ta_compute("ema", {"close": close}, period=20).values["ema"])
    ema50 = _last(ta_compute("ema", {"close": close}, period=50).values["ema"])
    rsi14 = _last(ta_compute("rsi", {"close": close}, period=14).values["rsi"])
    atr14 = _last(
        ta_compute("atr", {"high": high, "low": low, "close": close}, period=14).values["atr"]
    )
    vol_ratio = _last(ta_compute("volume_sma", {"volume": volume}, period=20).values["volume_sma"])
    vol_ratio = (_f(volume[-1]) / vol_ratio) if (vol_ratio and _f(volume[-1]) is not None) else None

    window = close[-250:]
    window = window[~np.isnan(window)]
    dist_high = None
    dist_low = None
    if len(window) and last_close is not None:
        hh, ll = float(window.max()), float(window.min())
        if hh:
            dist_high = last_close / hh - 1.0
        if ll:
            dist_low = last_close / ll - 1.0

    checklist = [
        _checklist_row(
            "close_vs_sma50",
            _f(last_close - sma50) if (last_close is not None and sma50 is not None) else None,
            "above_zero",
            "close > SMA(50)",
        ),
        _checklist_row(
            "close_vs_sma200",
            _f(last_close - sma200) if (last_close is not None and sma200 is not None) else None,
            "above_zero",
            "close > SMA(200)",
        ),
        _checklist_row(
            "ema_stack",
            _f(ema20 - ema50) if (ema20 is not None and ema50 is not None) else None,
            "above_zero",
            "EMA(20) > EMA(50)",
        ),
        _checklist_row("rsi14", rsi14, "between_30_70", "RSI(14) within 30..70 (no extreme)"),
        _checklist_row(
            "atr_percent",
            _f(100.0 * atr14 / last_close) if (atr14 and last_close) else None,
            "above_zero",
            "ATR(14) percent of close is computed",
        ),
        _checklist_row(
            "volume_vs_20d_avg", vol_ratio, "at_least_one", "today's volume >= 20-bar average"
        ),
        _checklist_row(
            "distance_from_250d_high",
            dist_high,
            "within_2pct_of_high",
            "close within 2% of the 250-bar high",
        ),
        _checklist_row(
            "distance_from_250d_low",
            dist_low,
            "above_3pct_from_low",
            "close at least 3% above the 250-bar low",
        ),
    ]

    # ---- position sizing ---------------------------------------------------
    per_share_risk = None
    if reference["invalidation"] is not None and last_close is not None:
        inval = _f(reference["invalidation"]["price"])
        if inval is not None:
            per_share_risk = (
                last_close - inval if reference["framing"] == "long" else inval - last_close
            )
            if per_share_risk is not None and per_share_risk <= 0:
                per_share_risk = None
    risk_amount = account_size * risk_fraction
    sizing: dict[str, Any] = {
        "account_size": account_size,
        "risk_fraction": risk_fraction,
        "risk_amount": risk_amount,
        "per_share_risk": per_share_risk,
        "shares": None,
        "notional": None,
        "reason": None,
    }
    if per_share_risk is None:
        sizing["reason"] = (
            "no valid invalidation distance (framed structure with a positive per-share risk)"
        )
    else:
        shares = int(np.floor(risk_amount / per_share_risk))
        sizing["shares"] = shares
        sizing["notional"] = _f(shares * last_close) if last_close is not None else None

    return {
        "symbol": None,  # filled by callers who know it
        "bars": int(len(df)),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "method": {
            "swings": f"fractal pivot (unique extreme over left={left}/right={right} window)",
            "confirmation": "a swing is only used once `right` further bars have failed to exceed it",
            "structure": "HH/HL/LH/LL from consecutive confirmed swings; trend from the two most recent of each kind",
            "measured_move": "absolute distance between the last confirmed swing high and low",
        },
        "params": {
            "left": left,
            "right": right,
            "min_prominence": min_prominence,
            "recent_swings": recent_swings,
            "account_size": account_size,
            "risk_fraction": risk_fraction,
        },
        "counts": {
            "bars": int(len(df)),
            "swings": len(swings),
            "swing_highs": len(swing_highs),
            "swing_lows": len(swing_lows),
        },
        "structure": {
            "trend": structure.get("trend"),
            "labels": structure.get("labels", [])[-recent_swings:],
            "breaks": breaks[-recent_swings:],
            "recent_swings": recent,
        },
        "nearest_levels": nearest_levels,
        "reference_levels": reference,
        "checklist": checklist,
        "sizing": sizing,
        "caveats": [
            "MECHANICAL: every row states its inequality; the checklist reports "
            "readings, not recommendations.",
            "Support/resistance come only from swings CONFIRMED by the last loaded "
            "bar; an unconfirmed pivot is never used as a level.",
            "Prices are unadjusted for corporate actions; levels derived from "
            "pre-action bars may be inconsistent with post-action prices.",
            "A measured move is a projection convention, not evidence the target will be reached.",
        ],
        "disclaimer": DISCLAIMER,
    }
