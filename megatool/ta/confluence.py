"""Indicator confluence / descriptive technical rating.

A lightweight, *descriptive* composite that summarises the current state of a
handful of already-computed indicators into a single 0-100 score plus a
per-group breakdown. It is a summary of what the indicators say *right now*,
not a prediction and not a trading signal.

Design rules (see the mission spec)
-----------------------------------
* Each indicator is classified bullish / neutral / bearish with an explicit,
  published rule — no hidden thresholds.
* Groups (trend, momentum, volatility) are kept separate so one family cannot
  silently dominate: trend and momentum each contribute at most their own
  weight, and volatility is *informational* (it never flips the sign on its
  own).
* Missing components are reported, not imputed.
* The composite is the mean of the available group scores, so a missing group
  does not drag the score to zero.
* No third-party rating formula is copied; the rules below are the
  application's own, stated in full.
"""

from __future__ import annotations

from typing import Any

__all__ = ["technical_rating", "classify"]


def classify(value, lo, hi) -> str:
    """Classify a scalar against (lo, hi) thresholds.

    value < lo  -> 'bearish'
    value > hi  -> 'bullish'
    otherwise   -> 'neutral'
    A non-finite or None value -> 'unknown'.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if v != v:  # NaN
        return "unknown"
    if v < lo:
        return "bearish"
    if v > hi:
        return "bullish"
    return "neutral"


def technical_rating(latest: dict[str, Any]) -> dict[str, Any]:
    """Build a descriptive technical rating from a dict of latest indicator values.

    ``latest`` may contain any subset of these keys (all optional):

    Trend group
      - ``sma_fast``, ``sma_slow``  (fast vs slow moving average)
      - ``close``, ``sma_slow``     (price vs slow MA)
      - ``adx``                     (trend strength, 0-100)
      - ``plus_di``, ``minus_di``  (directional movement)

    Momentum group
      - ``rsi``                     (0-100)
      - ``macd_hist``               (MACD histogram)
      - ``stoch_k``                 (stochastic %K, 0-100)
      - ``cci``                     (CCI)

    Volatility group (informational only)
      - ``atr_pct``                 (ATR as % of price)
      - ``bb_percent_b``            (%B, 0-1 typical)

    Each group returns a score in [-1, +1] (bullish positive) and a list of
    the component readings that produced it. The composite is the mean of the
    available group scores, scaled to 0-100 (50 = neutral).
    """
    components: list[dict[str, Any]] = []

    # ---- trend group -------------------------------------------------------
    trend_votes: list[float] = []
    if "sma_fast" in latest and "sma_slow" in latest:
        sf, ss = latest["sma_fast"], latest["sma_slow"]
        if sf is not None and ss is not None and sf == sf and ss == ss and ss != 0:
            v = 1.0 if sf > ss else (-1.0 if sf < ss else 0.0)
            trend_votes.append(v)
            components.append({"group": "trend", "name": "MA alignment (fast vs slow)",
                              "value": v, "detail": f"fast {sf:.4g} vs slow {ss:.4g}"})
    if "close" in latest and "sma_slow" in latest:
        c, ss = latest["close"], latest["sma_slow"]
        if c is not None and ss is not None and c == c and ss == ss and ss != 0:
            v = 1.0 if c > ss else (-1.0 if c < ss else 0.0)
            trend_votes.append(v)
            components.append({"group": "trend", "name": "Price vs slow MA",
                              "value": v, "detail": f"close {c:.4g} vs {ss:.4g}"})
    if "adx" in latest:
        adx = latest["adx"]
        if adx is not None and adx == adx:
            # ADX only says "trending"; direction comes from +DI/-DI if present.
            if "plus_di" in latest and "minus_di" in latest:
                pdi, mdi = latest["plus_di"], latest["minus_di"]
                if pdi is not None and mdi is not None and pdi == pdi and mdi == mdi:
                    if adx >= 25:
                        v = 1.0 if pdi > mdi else (-1.0 if pdi < mdi else 0.0)
                        trend_votes.append(v)
                        components.append({"group": "trend", "name": "ADX direction",
                                          "value": v, "detail": f"ADX {adx:.2g}, +DI {pdi:.2g}, -DI {mdi:.2g}"})
                    else:
                        components.append({"group": "trend", "name": "ADX direction",
                                          "value": 0.0, "detail": f"ADX {adx:.2g} < 25 (no trend)"})
    trend_score = (sum(trend_votes) / len(trend_votes)) if trend_votes else None

    # ---- momentum group ----------------------------------------------------
    mom_votes: list[float] = []
    if "rsi" in latest:
        rsi = latest["rsi"]
        if rsi is not None and rsi == rsi:
            if rsi > 55:
                v = 1.0
            elif rsi < 45:
                v = -1.0
            else:
                v = 0.0
            mom_votes.append(v)
            components.append({"group": "momentum", "name": "RSI", "value": v,
                              "detail": f"RSI {rsi:.2g}"})
    if "macd_hist" in latest:
        h = latest["macd_hist"]
        if h is not None and h == h:
            v = 1.0 if h > 0 else (-1.0 if h < 0 else 0.0)
            mom_votes.append(v)
            components.append({"group": "momentum", "name": "MACD histogram", "value": v,
                              "detail": f"hist {h:.4g}"})
    if "stoch_k" in latest:
        k = latest["stoch_k"]
        if k is not None and k == k:
            if k > 80:
                v = 1.0
            elif k < 20:
                v = -1.0
            else:
                v = 0.0
            mom_votes.append(v)
            components.append({"group": "momentum", "name": "Stochastic %K", "value": v,
                              "detail": f"%K {k:.2g}"})
    if "cci" in latest:
        cci = latest["cci"]
        if cci is not None and cci == cci:
            if cci > 100:
                v = 1.0
            elif cci < -100:
                v = -1.0
            else:
                v = 0.0
            mom_votes.append(v)
            components.append({"group": "momentum", "name": "CCI", "value": v,
                              "detail": f"CCI {cci:.2g}"})
    mom_score = (sum(mom_votes) / len(mom_votes)) if mom_votes else None

    # ---- volatility group (informational) ----------------------------------
    vol_info: list[dict[str, Any]] = []
    if "atr_pct" in latest:
        ap = latest["atr_pct"]
        if ap is not None and ap == ap:
            vol_info.append({"name": "ATR % of price", "value": float(ap)})
    if "bb_percent_b" in latest:
        pb = latest["bb_percent_b"]
        if pb is not None and pb == pb:
            vol_info.append({"name": "%B", "value": float(pb)})

    # ---- composite ---------------------------------------------------------
    group_scores = [s for s in (trend_score, mom_score) if s is not None]
    composite = (sum(group_scores) / len(group_scores)) if group_scores else 0.0
    score_100 = 50.0 + 50.0 * composite

    if score_100 >= 65:
        verdict = "bullish"
    elif score_100 <= 35:
        verdict = "bearish"
    else:
        verdict = "neutral"

    missing = []
    if trend_score is None:
        missing.append("trend")
    if mom_score is None:
        missing.append("momentum")

    return {
        "score": round(score_100, 2),
        "verdict": verdict,
        "groups": {
            "trend": {"score": None if trend_score is None else round(trend_score, 4),
                      "n_components": len(trend_votes)},
            "momentum": {"score": None if mom_score is None else round(mom_score, 4),
                         "n_components": len(mom_votes)},
            "volatility": {"info": vol_info},
        },
        "components": components,
        "missing_groups": missing,
        "disclaimer": ("Descriptive summary of the supplied indicator values; "
                       "not a prediction, not a trading signal, and not financial advice."),
    }