"""Gap detection and false-breakout classification over daily bars.

Two independent detectors, both deterministic and both explicitly
**described, not prophesied**:

GAPS
----
A gap is a *fact* of the stored series: a session whose low opened entirely
above the prior session's high (up-gap) or whose high sits entirely below the
prior session's low (down-gap). Every gap gets:

* its exact size and its size relative to ATR(14) (Wilder) at that bar — the
  scale the rest of the classification uses;
* a heuristic class among ``common`` / ``runaway`` / ``breakaway`` /
  ``exhaustion``, each derived from a stated rule and the trend context, with
  the honest caveat that gap classes are conventions of charting literature,
  not predictions — the detector labels *what the shape looks like by rule*;
* ``closed_within_bars`` — a pure, verifiable fact: how many later sessions
  traded back into the gap (``None`` = still open at the end of the window).

FALSE BREAKOUTS
---------------
An upside breakout is pre-above-threshold when a ``close`` exceeds the
greatest high of the prior ``window`` bars by at least ``min_frac``; a
breakout is *false* when a later close within ``confirm_bars`` sessions comes
back below that broken level. Downside breakouts are symmetric (NEPSE-retail
interest is longs, but the detector reports both sides factually). Each
breakout records the broken level, the confirmation/closure date and — for a
false breakout — whether the price generated a stop-run beyond the level
(the extremes reached before the reversal).

No look-ahead: every classification at bar ``t`` uses bars ``≤ t``;
``closed_within_bars`` is reported separately because it, by definition,
looks forward — it is a post-hoc fact about the stored history, never part of
the class label.
"""

from __future__ import annotations

import math
from typing import Any

__all__ = ["GapError", "detect_gaps", "detect_false_breakouts"]


class GapError(ValueError):
    """Invalid detector input."""


def _wilder_atrs(
    high: list[float], low: list[float], close: list[float], period: int
) -> list[float | None]:
    trs: list[float] = []
    for i, (h, lo_v) in enumerate(zip(high, low, strict=True)):
        tr = h - lo_v if i == 0 else max(h - lo_v, abs(h - close[i - 1]), abs(lo_v - close[i - 1]))
        trs.append(tr)
    out: list[float | None] = [None] * len(high)
    if len(high) < period:
        return out
    atr = sum(trs[:period]) / period
    out[period - 1] = atr
    for i in range(period, len(high)):
        atr = (atr * (period - 1) + trs[i]) / period
        out[i] = atr
    return out


def _clean_ohlc(
    high: list[float], low: list[float], close: list[float]
) -> list[tuple[float, float, float]]:
    rows: list[tuple[float, float, float]] = []
    for h, lo_c, c in zip(high, low, close, strict=True):
        if not (math.isfinite(h) and math.isfinite(lo_c) and math.isfinite(c)):
            rows.append((math.nan, math.nan, math.nan))
            continue
        rows.append((h, lo_c, c))
    return rows


def detect_gaps(
    high: list[float],
    low: list[float],
    close: list[float],
    *,
    atr_period: int = 14,
    common_max_atr: float = 0.25,
    big_min_atr: float = 0.75,
    extend_bars: int = 20,
) -> list[dict[str, Any]]:
    """Every session-to-session gap in the supplied series, classified.

    A bar whose low > prior high (or high < prior low) is a fact; the class
    is a rule-based label. Malformed bars are skipped: a gap is only computed
    across two *consecutive usable* rows, and the response carries the count
    of segments skipped so a data hole can never pose as a gap.
    """
    if not high or not (len(high) == len(low) == len(close)):
        raise GapError("high, low and close must be the same, nonempty length")
    if not 2 <= atr_period <= 500:
        raise GapError("atr_period must be within 2..500")
    if common_max_atr < 0.0 or big_min_atr < common_max_atr:
        raise GapError("class thresholds must satisfy 0 ≤ common_max_atr < big_min_atr")

    rows = _clean_ohlc(high, low, close)
    atrs = _wilder_atrs(high, low, close, atr_period)
    gaps: list[dict[str, Any]] = []
    skipped_segments = 0
    n = len(rows)
    # usable consecutive index pairs
    usable_idx = [i for i, r in enumerate(rows) if math.isfinite(r[0]) and r[0] > 0]
    for a, b in zip(usable_idx, usable_idx[1:], strict=False):
        if b != a + 1:
            skipped_segments += 1
            continue
        ph, pl, pc = rows[a]
        lh, ll, _ = rows[b]
        if ll > ph:
            direction, size = "up", ll - ph
        elif lh < pl:
            direction, size = "down", pl - lh
        else:
            continue
        atr = atrs[b]
        size_atr = size / atr if atr is not None and atr > 0 else None
        # context: net move of the previous `extend_bars` closes
        start_c = close[max(0, b - extend_bars - 1)]
        run = pc - start_c if b - 1 >= 0 else 0.0
        run_bars = min(extend_bars, b)
        ext_start = max(0, a - extend_bars + 1)
        at_extreme_up = (
            size_atr is not None
            and size_atr >= big_min_atr
            and run > 0
            and ph >= max(high[ext_start : a + 1])
        )
        at_extreme_down = (
            size_atr is not None
            and size_atr >= big_min_atr
            and run < 0
            and pl <= min(low[ext_start : a + 1])
        )
        if size_atr is not None and size_atr <= common_max_atr:
            cls = "common"
            basis = f"gap ≤ {common_max_atr}× ATR — noise-scale"
        elif at_extreme_up or at_extreme_down:
            cls = "exhaustion"
            basis = (
                f"≥ {big_min_atr}× ATR after a {run_bars}-bar move of "
                f"{round(run, 6)} into the window's extreme (late-run shape)"
            )
        elif size_atr is not None and size_atr >= big_min_atr:
            cls = "breakaway"
            basis = f"large gap ({round(size_atr, 2)}× ATR) leaving the prior range behind"
        else:
            cls = "runaway"
            basis = "mid-scale gap: larger than common, not at the run's extreme"
        # fact-only fields, computed afterwards (they may look ahead)
        close_idx = None
        for j in range(b + 1, n):
            lh, ll = rows[j][0], rows[j][1]
            if math.isfinite(lh):
                if direction == "up" and ll <= ph:
                    close_idx = j - b
                    break
                if direction == "down" and lh >= pl:
                    close_idx = j - b
                    break
        gaps.append(
            {
                "index": b,
                "direction": direction,
                "size": round(size, 6),
                "size_atr": None if size_atr is None else round(size_atr, 3),
                "class": cls,
                "class_basis": basis,
                "prior_high": round(ph, 6),
                "prior_low": round(pl, 6),
                "gap_low": round(ll, 6),
                "gap_high": round(lh, 6),
                "closed_within_bars": close_idx,
                "lookahead_note": (
                    "closed_within_bars is computed afterwards over the stored "
                    "history — it is a fact about the past, never part of the "
                    "class label, and unknown as of the gap bar itself"
                ),
            }
        )
    if skipped_segments or len(usable_idx) < n:
        gaps.insert(
            0,
            {
                "data_note": (
                    f"{len(usable_idx)} usable consecutive bars; "
                    f"{skipped_segments} segment(s) skipped around malformed or "
                    "missing rows — gaps are never computed across holes"
                )
            },
        )
    return gaps


def detect_false_breakouts(
    high: list[float],
    low: list[float],
    close: list[float],
    *,
    window: int = 20,
    min_frac: float = 0.005,
    confirm_bars: int = 3,
) -> list[dict[str, Any]]:
    """Breakouts beyond a rolling extremes-threshold, tagged true/false.

    A breakout at bar ``i``: ``close[i] ≥ (1+min_frac) × max(high[i-window:i])``
    (upside) or ``close[i] ≤ (1−min_frac) × min(low[i-window:i])`` (downside).
    **False** when a close within the next ``confirm_bars`` sessions returns
    to the other side of the level. Additional measured facts recorded per
    breakout: the run beyond the level (greatest/least extreme) and the number
    of sessions it held. The level is the *prior window's* extreme only — no
    clustered S/R zones are claimed here; those live in ``ta.levels``.
    """
    if not high or not (len(high) == len(low) == len(close)):
        raise GapError("high, low and close must be the same, nonempty length")
    if not 2 <= window <= 500:
        raise GapError("window must be within 2..500")
    if not 0.0 < min_frac < 0.5:
        raise GapError("min_frac must be within 0..0.5 (exclusive)")
    if not 1 <= confirm_bars <= 50:
        raise GapError("confirm_bars must be within 1..50")

    rows = _clean_ohlc(high, low, close)
    usable = [i for i, r in enumerate(rows) if math.isfinite(r[0]) and r[0] > 0]
    out: list[dict[str, Any]] = []
    for pos, i in enumerate(usable):
        if pos < window + 1:  # need `window` prior bars + at least one after
            continue
        prior = [rows[j] for j in usable[pos - window : pos]]
        h, lo_c, c = rows[i]
        up_level = max(r[0] for r in prior)
        dn_level = min(r[1] for r in prior)
        side = None
        if c >= up_level * (1.0 + min_frac):
            side, level = "up", up_level
        elif c <= dn_level * (1.0 - min_frac):
            side, level = "down", dn_level
        else:
            continue
        # confirm/closure within the next confirm_bars sessions
        reversed_at = None
        extreme = c
        for j in usable[pos + 1 :]:
            if j > i + confirm_bars:
                break
            cj = rows[j][2]
            if side == "up":
                extreme = max(extreme, rows[j][0])
                if cj < level:
                    reversed_at = j
                    break
            else:
                extreme = min(extreme, rows[j][1])
                if cj > level:
                    reversed_at = j
                    break
        run_beyond = round(extreme - level, 6) if side == "up" else round(level - extreme, 6)
        # still-open breakouts are reported without a verdict, not as "true"
        status = (
            "false"
            if reversed_at is not None
            else ("true" if i + confirm_bars < len(rows) else "unconfirmed (window end)")
        )
        out.append(
            {
                "index": i,
                "side": side,
                "level": round(level, 6),
                "close": round(c, 6),
                "close_beyond_frac": round(
                    (c - level) / level if side == "up" else (level - c) / level, 5
                ),
                "status": status,
                "reversed_index": reversed_at,
                "bars_beyond_level": None if reversed_at is None else reversed_at - i,
                "run_beyond_level": run_beyond,
                "rule": (
                    f"close beyond the prior {window}-bar extreme by ≥ {min_frac:.2%}; "
                    f"false when a later close within {confirm_bars} sessions returns "
                    "across that level"
                ),
            }
        )
    return out
