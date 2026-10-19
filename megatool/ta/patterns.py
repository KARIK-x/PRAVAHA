"""Rule-based chart-pattern recognition (deterministic, pivot-driven).

Patterns are detected geometrically from confirmed swing pivots and are
**descriptive**, never predictive. Every match reports the pivot evidence that
produced it, a documented rule set, a rule-based quality score, and its
confirmation state. A shape is not labelled "confirmed" unless price has closed
beyond the pattern's own trigger level within the data actually available.

Look-ahead discipline: all pivots come from :func:`megatool.ta.swings.find_swings`
with ``last_index`` set to the last available bar, so a pivot is only used once
its confirmation window has closed. Breakout checks only read closes at or
before ``last_index``.

Definitions are documented per detector because chart-pattern definitions differ
between practitioners. Tolerances are explicit and configurable; nothing here is
a guarantee of future price behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from megatool.ta.swings import Swing, find_swings

__all__ = ["PatternConfig", "PatternMatch", "detect_patterns", "PATTERN_TYPES"]


#: Every pattern this module can emit, with its bias. Kept explicit so callers
#: (and tests) can enumerate the supported set instead of guessing.
PATTERN_TYPES: dict[str, str] = {
    "double_top": "bearish",
    "double_bottom": "bullish",
    "triple_top": "bearish",
    "triple_bottom": "bullish",
    "head_and_shoulders": "bearish",
    "inverse_head_and_shoulders": "bullish",
    "ascending_triangle": "bullish",
    "descending_triangle": "bearish",
    "symmetrical_triangle": "neutral",
    "rising_wedge": "bearish",
    "falling_wedge": "bullish",
    "bull_flag": "bullish",
    "bear_flag": "bearish",
    "channel_breakout_up": "bullish",
    "channel_breakout_down": "bearish",
}


@dataclass(frozen=True, slots=True)
class PatternConfig:
    """Detection parameters (all explicit, so a result is reproducible).

    ``level_tol`` is the fractional distance within which two pivot touches are
    considered "the same" level. ``right`` is the pivot confirmation lag: it is
    the honest delay before a turning point is knowable. ``min_bars`` gates the
    whole analysis on enough history rather than guessing from a stub.
    """

    left: int = 3
    right: int = 3
    min_prominence: float = 0.03
    level_tol: float = 0.035
    min_bars: int = 60
    lookback_swings: int = 12
    flag_pole_bars: int = 15
    flag_min_pole: float = 0.10
    flag_max_range: float = 0.06
    channel_period: int = 20
    max_patterns: int = 8


@dataclass(slots=True)
class PatternMatch:
    """One detected pattern with its evidence and confirmation state."""

    pattern: str
    direction: str
    start_index: int
    end_index: int
    pivots: list[dict[str, Any]] = field(default_factory=list)
    status: str = "forming"
    breakout_level: float | None = None
    invalidation_level: float | None = None
    target_level: float | None = None
    quality: float = 0.0
    evidence: list[str] = field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "direction": self.direction,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "pivots": self.pivots,
            "status": self.status,
            "breakout_level": _r(self.breakout_level),
            "invalidation_level": _r(self.invalidation_level),
            "target_level": _r(self.target_level),
            "quality": round(float(self.quality), 1),
            "evidence": list(self.evidence),
        }


def _r(value: float | None) -> float | None:
    return None if value is None else round(float(value), 4)


def _close_ratio(a: float, b: float) -> float:
    """Fractional difference between two positive levels (0 = identical)."""
    m = max(abs(a), abs(b))
    return 0.0 if m == 0 else abs(a - b) / m


def _pivot_dict(s: Swing, dates: Sequence[str] | None) -> dict[str, Any]:
    return {
        "kind": s.kind,
        "index": s.index,
        "date": dates[s.index] if dates is not None and s.index < len(dates) else None,
        "price": round(float(s.price), 4),
    }


def _date(dates: Sequence[str] | None, index: int) -> str | None:
    if dates is None or index < 0 or index >= len(dates):
        return None
    return str(dates[index])


def _break_state(
    close: np.ndarray,
    after: int,
    level: float,
    direction: str,
    last_index: int,
) -> bool:
    """True if ``close`` closed beyond ``level`` in ``direction`` after ``after``."""
    lo = max(after + 1, 0)
    hi = min(last_index, len(close) - 1)
    if lo > hi:
        return False
    window = close[lo : hi + 1]
    if direction == "below":
        return bool(np.any(window < level))
    return bool(np.any(window > level))


# --------------------------------------------------------------------------- tops/bottoms


def _double_pattern(
    swings: list[Swing],
    close: np.ndarray,
    dates: Sequence[str] | None,
    cfg: PatternConfig,
    last_index: int,
    kind: str,
) -> list[PatternMatch]:
    """Double top (two swing highs) / double bottom (two swing lows)."""
    out: list[PatternMatch] = []
    legs = [s for s in swings if s.kind == kind]
    opp = "low" if kind == "high" else "high"
    # A pair of same-kind pivots must be separated by exactly one opposite pivot.
    for a, b in zip(legs, legs[1:], strict=False):
        between = [s for s in swings if s.kind == opp and a.index < s.index < b.index]
        if len(between) != 1:
            continue
        neck = between[0].price
        dev = _close_ratio(a.price, b.price)
        if dev > cfg.level_tol:
            continue
        if kind == "high":
            avg = (a.price + b.price) / 2.0
            if neck >= avg:  # a "top" whose neck is above the tops is not one
                continue
            height = avg - neck
            direction = "below"
            breakout = neck
            target = neck - height
            invalidation = max(a.price, b.price)
            pattern, bias = "double_top", "bearish"
        else:
            avg = (a.price + b.price) / 2.0
            if neck <= avg:
                continue
            height = neck - avg
            direction = "above"
            breakout = neck
            target = neck + height
            invalidation = min(a.price, b.price)
            pattern, bias = "double_bottom", "bullish"
        confirmed = _break_state(close, b.confirmed_index, breakout, direction, last_index)
        quality = _quality_symmetry(dev, cfg.level_tol)
        out.append(
            PatternMatch(
                pattern=pattern,
                direction=bias,
                start_index=a.index,
                end_index=b.index,
                pivots=[
                    _pivot_dict(a, dates),
                    _pivot_dict(between[0], dates),
                    _pivot_dict(b, dates),
                ],
                status="confirmed" if confirmed else "forming",
                breakout_level=breakout,
                invalidation_level=invalidation,
                target_level=target,
                quality=quality,
                evidence=[
                    f"two {'highs' if kind == 'high' else 'lows'} within "
                    f"{dev * 100:.1f}% (tolerance {cfg.level_tol * 100:.1f}%)",
                    f"neckline {neck:.2f} between them",
                    "confirmed by a close beyond the neckline"
                    if confirmed
                    else "not yet confirmed: no close beyond the neckline",
                ],
                start_date=_date(dates, a.index),
                end_date=_date(dates, b.index),
            )
        )
    return out


def _triple_pattern(
    swings: list[Swing],
    close: np.ndarray,
    dates: Sequence[str] | None,
    cfg: PatternConfig,
    last_index: int,
    kind: str,
) -> list[PatternMatch]:
    """Triple top / bottom: three near-equal pivots with two necks."""
    out: list[PatternMatch] = []
    legs = [s for s in swings if s.kind == kind]
    opp = "low" if kind == "high" else "high"
    for i in range(len(legs) - 2):
        a, b, c = legs[i], legs[i + 1], legs[i + 2]
        necks = [s for s in swings if s.kind == opp and a.index < s.index < c.index]
        if len(necks) != 2:
            continue
        prices = [a.price, b.price, c.price]
        if (
            _close_ratio(prices[0], prices[1]) > cfg.level_tol
            or _close_ratio(prices[1], prices[2]) > cfg.level_tol
        ):
            continue
        neck = float(np.mean([n.price for n in necks]))
        avg = float(np.mean(prices))
        if kind == "high":
            if neck >= avg:
                continue
            height = avg - neck
            direction, pattern, bias = "below", "triple_top", "bearish"
            breakout, target = neck, neck - height
            invalidation = max(prices)
        else:
            if neck <= avg:
                continue
            height = neck - avg
            direction, pattern, bias = "above", "triple_bottom", "bullish"
            breakout, target = neck, neck + height
            invalidation = min(prices)
        confirmed = _break_state(close, c.confirmed_index, breakout, direction, last_index)
        dev = max(_close_ratio(prices[0], prices[1]), _close_ratio(prices[1], prices[2]))
        out.append(
            PatternMatch(
                pattern=pattern,
                direction=bias,
                start_index=a.index,
                end_index=c.index,
                pivots=[_pivot_dict(s, dates) for s in (a, b, c)],
                status="confirmed" if confirmed else "forming",
                breakout_level=breakout,
                invalidation_level=invalidation,
                target_level=target,
                quality=_quality_symmetry(dev, cfg.level_tol),
                evidence=[
                    f"three {'highs' if kind == 'high' else 'lows'} within {dev * 100:.1f}%",
                    f"average neckline {neck:.2f}",
                    "confirmed" if confirmed else "forming, no breakout close yet",
                ],
                start_date=_date(dates, a.index),
                end_date=_date(dates, c.index),
            )
        )
    return out


def _head_shoulders(
    swings: list[Swing],
    close: np.ndarray,
    dates: Sequence[str] | None,
    cfg: PatternConfig,
    last_index: int,
    inverted: bool,
) -> list[PatternMatch]:
    """Head-and-shoulders (bearish) or its inverse (bullish)."""
    out: list[PatternMatch] = []
    leg_kind = "low" if inverted else "high"
    neck_kind = "high" if inverted else "low"
    legs = [s for s in swings if s.kind == leg_kind]
    for i in range(len(legs) - 2):
        ls, head, rs = legs[i], legs[i + 1], legs[i + 2]
        necks = [s for s in swings if s.kind == neck_kind and ls.index < s.index < rs.index]
        if len(necks) != 2:
            continue
        if not inverted:
            if not (head.price > ls.price and head.price > rs.price):
                continue
        else:
            if not (head.price < ls.price and head.price < rs.price):
                continue
        shoulder_dev = _close_ratio(ls.price, rs.price)
        if shoulder_dev > cfg.level_tol:
            continue
        neck = float(np.mean([n.price for n in necks]))
        if not inverted:
            height = head.price - neck
            if height <= 0:
                continue
            direction, pattern, bias = "below", "head_and_shoulders", "bearish"
            breakout, target = neck, neck - height
            invalidation = head.price
        else:
            height = neck - head.price
            if height <= 0:
                continue
            direction, pattern, bias = "above", "inverse_head_and_shoulders", "bullish"
            breakout, target = neck, neck + height
            invalidation = head.price
        confirmed = _break_state(close, rs.confirmed_index, breakout, direction, last_index)
        out.append(
            PatternMatch(
                pattern=pattern,
                direction=bias,
                start_index=ls.index,
                end_index=rs.index,
                pivots=[_pivot_dict(s, dates) for s in (ls, head, rs)],
                status="confirmed" if confirmed else "forming",
                breakout_level=breakout,
                invalidation_level=invalidation,
                target_level=target,
                quality=_quality_symmetry(shoulder_dev, cfg.level_tol),
                evidence=[
                    f"middle {'low' if inverted else 'high'} (head) is the most extreme",
                    f"shoulders within {shoulder_dev * 100:.1f}%",
                    f"neckline {neck:.2f}",
                    "confirmed by a close beyond the neckline"
                    if confirmed
                    else "forming: neckline not yet closed through",
                ],
                start_date=_date(dates, ls.index),
                end_date=_date(dates, rs.index),
            )
        )
    return out


# --------------------------------------------------------------------------- triangles/wedges


def _triangle_wedge(
    swings: list[Swing],
    dates: Sequence[str] | None,
    cfg: PatternConfig,
    last_index: int,
) -> list[PatternMatch]:
    """Ascending/descending/symmetrical triangles and rising/falling wedges.

    Built from the two most recent swing highs and the two most recent swing
    lows, in chronological order. The shape is classified by the slopes of the
    upper and lower pivot lines.
    """
    out: list[PatternMatch] = []
    highs = [s for s in swings if s.kind == "high"][-2:]
    lows = [s for s in swings if s.kind == "low"][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return out
    h1, h2 = highs
    l1, l2 = lows
    if not (h1.index < h2.index and l1.index < l2.index):
        return out
    up_slope = h2.price - h1.price
    lo_slope = l2.price - l1.price
    flat = cfg.level_tol
    rising_hi = up_slope > flat * h1.price
    falling_hi = up_slope < -flat * h1.price
    rising_lo = lo_slope > flat * l1.price
    falling_lo = lo_slope < -flat * l1.price
    flat_hi = not rising_hi and not falling_hi
    flat_lo = not rising_lo and not falling_lo
    start = min(h1.index, l1.index)
    end = max(h2.index, l2.index)
    upper = max(h1.price, h2.price)
    lower = min(l1.price, l2.price)
    width0 = h1.price - l1.price
    width1 = h2.price - l2.price
    converging = width0 > 0 and width1 < width0

    def add(pattern: str, bias: str, breakout: float, invalidation: float, why: str) -> None:
        out.append(
            PatternMatch(
                pattern=pattern,
                direction=bias,
                start_index=start,
                end_index=end,
                pivots=[
                    _pivot_dict(s, dates) for s in sorted((h1, h2, l1, l2), key=lambda s: s.index)
                ],
                status="forming",
                breakout_level=breakout,
                invalidation_level=invalidation,
                target_level=None,
                quality=60.0 if converging else 40.0,
                evidence=[
                    why,
                    f"upper line from {h1.price:.2f}→{h2.price:.2f}",
                    f"lower line from {l1.price:.2f}→{l2.price:.2f}",
                ],
                start_date=_date(dates, start),
                end_date=_date(dates, end),
            )
        )

    if flat_hi and rising_lo and converging:
        add(
            "ascending_triangle", "bullish", upper, lower, "flat highs with rising lows, converging"
        )
    elif flat_lo and falling_hi and converging:
        add(
            "descending_triangle",
            "bearish",
            lower,
            upper,
            "flat lows with falling highs, converging",
        )
    elif rising_hi and falling_lo and converging:
        add(
            "symmetrical_triangle",
            "neutral",
            upper,
            lower,
            "falling highs with rising lows, converging",
        )
    elif rising_hi and rising_lo and converging:
        add(
            "rising_wedge",
            "bearish",
            lower,
            upper,
            "both lines rising and converging (rising wedge)",
        )
    elif falling_hi and falling_lo and converging:
        add(
            "falling_wedge",
            "bullish",
            upper,
            lower,
            "both lines falling and converging (falling wedge)",
        )
    return out


# --------------------------------------------------------------------------- flags


def _flag(
    close: np.ndarray,
    dates: Sequence[str] | None,
    cfg: PatternConfig,
    last_index: int,
) -> list[PatternMatch]:
    """Bull/bear flags: a strong pole then a tight consolidation."""
    out: list[PatternMatch] = []
    n = last_index + 1
    pole_bars = cfg.flag_pole_bars
    cons_bars = 10
    # The pole must END before the consolidation begins; overlapping them would
    # compare a rising pole against itself and never look like a flag.
    if n < pole_bars + cons_bars + 1:
        return out
    pole_end = n - 1 - cons_bars
    pole_start = pole_end - pole_bars
    pole_move = close[pole_end] / close[pole_start] - 1.0
    cons = close[pole_end + 1 : n]
    cons_range = (cons.max() - cons.min()) / cons.mean() if cons.size else 1.0
    if cons_range > cfg.flag_max_range:
        return out
    hi, lo = float(close[pole_start]), float(close[pole_end])
    pivots = [
        {
            "kind": "pole_start",
            "index": pole_start,
            "date": _date(dates, pole_start),
            "price": round(hi, 4),
        },
        {
            "kind": "pole_end",
            "index": pole_end,
            "date": _date(dates, pole_end),
            "price": round(lo, 4),
        },
    ]
    if pole_move >= cfg.flag_min_pole:
        out.append(
            PatternMatch(
                pattern="bull_flag",
                direction="bullish",
                start_index=pole_start,
                end_index=n - 1,
                pivots=pivots,
                status="forming",
                breakout_level=float(cons.max()),
                invalidation_level=float(cons.min()),
                target_level=float(cons.max() + (cons.max() - cons.min())),
                quality=min(100.0, pole_move / cfg.flag_min_pole * 50.0),
                evidence=[
                    f"pole +{pole_move * 100:.1f}% over {pole_bars} bars",
                    f"consolidation range {cons_range * 100:.1f}% (max {cfg.flag_max_range * 100:.1f}%)",
                ],
                start_date=_date(dates, pole_start),
                end_date=_date(dates, n - 1),
            )
        )
    elif pole_move <= -cfg.flag_min_pole:
        out.append(
            PatternMatch(
                pattern="bear_flag",
                direction="bearish",
                start_index=pole_start,
                end_index=n - 1,
                pivots=pivots,
                status="forming",
                breakout_level=float(cons.min()),
                invalidation_level=float(cons.max()),
                target_level=float(cons.min() - (cons.max() - cons.min())),
                quality=min(100.0, abs(pole_move) / cfg.flag_min_pole * 50.0),
                evidence=[
                    f"pole {pole_move * 100:.1f}% over {pole_bars} bars",
                    f"consolidation range {cons_range * 100:.1f}%",
                ],
                start_date=_date(dates, pole_start),
                end_date=_date(dates, n - 1),
            )
        )
    return out


# --------------------------------------------------------------------------- channel breakout


def _channel_breakout(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    dates: Sequence[str] | None,
    cfg: PatternConfig,
    last_index: int,
) -> list[PatternMatch]:
    """Donchian channel breakout on the last available bar (excludes that bar)."""
    out: list[PatternMatch] = []
    p = cfg.channel_period
    i = last_index
    if i < p:
        return out
    prior_hi = float(np.max(high[i - p : i]))
    prior_lo = float(np.min(low[i - p : i]))
    if close[i] > prior_hi:
        out.append(
            PatternMatch(
                pattern="channel_breakout_up",
                direction="bullish",
                start_index=i - p,
                end_index=i,
                pivots=[
                    {
                        "kind": "channel_high",
                        "index": i - p,
                        "date": _date(dates, i - p),
                        "price": round(prior_hi, 4),
                    }
                ],
                status="confirmed",
                breakout_level=prior_hi,
                invalidation_level=prior_lo,
                target_level=None,
                quality=100.0 * min(1.0, (close[i] / prior_hi - 1.0) / 0.02),
                evidence=[f"close {close[i]:.2f} above the prior {p}-bar high {prior_hi:.2f}"],
                start_date=_date(dates, i - p),
                end_date=_date(dates, i),
            )
        )
    elif close[i] < prior_lo:
        out.append(
            PatternMatch(
                pattern="channel_breakout_down",
                direction="bearish",
                start_index=i - p,
                end_index=i,
                pivots=[
                    {
                        "kind": "channel_low",
                        "index": i - p,
                        "date": _date(dates, i - p),
                        "price": round(prior_lo, 4),
                    }
                ],
                status="confirmed",
                breakout_level=prior_lo,
                invalidation_level=prior_hi,
                target_level=None,
                quality=100.0 * min(1.0, (prior_lo / close[i] - 1.0) / 0.02),
                evidence=[f"close {close[i]:.2f} below the prior {p}-bar low {prior_lo:.2f}"],
                start_date=_date(dates, i - p),
                end_date=_date(dates, i),
            )
        )
    return out


def _quality_symmetry(dev: float, tol: float) -> float:
    """A transparent 0-100 quality score from how close two touches are.

    ``dev`` is the fractional difference between the touches. At ``dev == 0``
    the score is 100; at ``dev == tol`` it is 50; beyond tolerance the pattern is
    not emitted at all. This is a *documented rule*, not a calibrated
    probability of a successful trade.
    """
    if tol <= 0:
        return 100.0
    return float(max(0.0, 100.0 - 50.0 * (dev / tol)))


# --------------------------------------------------------------------------- entrypoint


def detect_patterns(
    high: Any,
    low: Any,
    close: Any,
    *,
    dates: Sequence[str] | None = None,
    config: PatternConfig | None = None,
    last_index: int | None = None,
) -> dict[str, Any]:
    """Detect chart patterns in one OHLC series.

    Returns a dict with ``patterns`` (list of :class:`PatternMatch` dicts),
    ``parameters`` (the exact config used), ``bars`` and ``notes``. Insufficient
    history is reported as an explicit ``unavailable`` reason, never as "no
    patterns found", so an absence of evidence is never misread as a clean chart.
    """
    cfg = config or PatternConfig()
    h = np.asarray(high, dtype=float)
    lo = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    n = len(c)
    base: dict[str, Any] = {
        "patterns": [],
        "parameters": {
            "left": cfg.left,
            "right": cfg.right,
            "min_prominence": cfg.min_prominence,
            "level_tol": cfg.level_tol,
            "min_bars": cfg.min_bars,
            "channel_period": cfg.channel_period,
        },
        "bars": n,
        "available": False,
        "unavailable_reason": None,
        "notes": [
            "Detections are descriptive geometric matches, not predictions.",
            "Quality is a documented symmetry rule, not a probability of profit.",
        ],
    }
    if n < cfg.min_bars:
        base["unavailable_reason"] = (
            f"only {n} bars available; {cfg.min_bars} are required before "
            "chart patterns are reported (too little history to form a shape)"
        )
        return base
    if not (np.all(np.isfinite(h)) and np.all(np.isfinite(lo)) and np.all(np.isfinite(c))):
        base["unavailable_reason"] = "series contains non-finite values; refusing to detect"
        return base

    li = n - 1 if last_index is None else min(int(last_index), n - 1)
    swings = find_swings(
        h[: li + 1],
        lo[: li + 1],
        left=cfg.left,
        right=cfg.right,
        min_prominence=cfg.min_prominence,
        last_index=li,
    )
    swings = swings[-cfg.lookback_swings :]

    found: list[PatternMatch] = []
    found += _double_pattern(swings, c, dates, cfg, li, "high")
    found += _double_pattern(swings, c, dates, cfg, li, "low")
    found += _triple_pattern(swings, c, dates, cfg, li, "high")
    found += _triple_pattern(swings, c, dates, cfg, li, "low")
    found += _head_shoulders(swings, c, dates, cfg, li, inverted=False)
    found += _head_shoulders(swings, c, dates, cfg, li, inverted=True)
    found += _triangle_wedge(swings, dates, cfg, li)
    found += _flag(c, dates, cfg, li)
    found += _channel_breakout(h, lo, c, dates, cfg, li)

    found.sort(key=lambda p: (-p.quality, p.start_index))
    found = found[: cfg.max_patterns]
    base["patterns"] = [p.to_dict() for p in found]
    base["available"] = True
    base["swings_used"] = len(swings)
    return base
