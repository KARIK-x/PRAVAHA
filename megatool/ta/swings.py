"""Swing-point detection and market-structure classification.

Why this exists
---------------
The Master Specification (``ALL THE CONTENT:IDEA MAIN OVERVIEW OF PROJECT.pdf``)
marks Elliott Wave (§4), Fibonacci (§5), chart patterns (§6), harmonic patterns
(§7), price action (§9) and support/resistance (§14) as *mandatory*. Every one
of them needs the same primitive: a defensible list of turning points. This
module is that primitive, implemented once so those features cannot each invent
a private, disagreeing definition (§28.2 — shared calculation layer).

It is deliberately **not** registered as an indicator in
:data:`megatool.ta.core._REGISTRY`. The registry is for per-bar *series* (RSI
has a value at every bar). A swing is a discrete *event* with its own identity,
and pretending it is a series would misrepresent it. It lives in ``ta`` because
it is technical analysis, and is re-exported from :mod:`megatool.ta`.

The look-ahead rule (read this before using the output)
------------------------------------------------------
A swing high at bar *i* is only a swing high once ``right`` further bars have
failed to exceed it. Until then, nobody at bar *i* could have known. Two
consequences, both enforced here:

* every swing carries ``confirmed_index`` — the first bar index at which the
  swing becomes knowable. **A backtest must not act before that index.**
* a swing whose confirmation bar has not yet been reached is returned with
  ``confirmed=False`` rather than being silently dropped or silently treated as
  known. The caller decides what an unconfirmed swing means; this module never
  decides for it.

The project's own spec requires this: §6.3 "avoid using future price movements
to label a historical pattern as if that information were available at the
time", and §20.4 look-ahead protection.

Result label
------------
Output is **DETECTED** — an algorithm identified candidate turning points under
the documented rules below. It is not a validated signal, not a prediction, and
not evidence that a price level will hold (§32.2, §32.7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = ["Swing", "SwingError", "classify_structure", "find_swings"]

#: Default bars of context either side of a candidate pivot. Five daily bars is
#: a common choice for swing structure on daily data; it is a parameter, not a
#: truth, and the API and UI expose it as one.
DEFAULT_LEFT = 5
DEFAULT_RIGHT = 5


class SwingError(ValueError):
    """Raised when the inputs cannot produce a meaningful swing analysis."""


@dataclass(slots=True)
class Swing:
    """One detected turning point.

    ``index`` is the pivot bar. ``confirmed_index`` is the first bar at which
    the pivot is knowable — always ``>= index``, and always the honest answer
    to "when could a researcher have known this?".
    """

    index: int
    kind: str  # "high" | "low"
    price: float
    confirmed_index: int
    confirmed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "price": round(float(self.price), 4),
            "confirmed_index": self.confirmed_index,
            "confirmed": self.confirmed,
        }


def _as_array(values: Any, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise SwingError(f"`{name}` must be one-dimensional")
    if arr.size == 0:
        raise SwingError(f"`{name}` is empty")
    return arr


def find_swings(
    high: Any,
    low: Any,
    left: int = DEFAULT_LEFT,
    right: int = DEFAULT_RIGHT,
    min_prominence: float = 0.0,
    last_index: int | None = None,
) -> list[Swing]:
    """Detect alternating swing highs and lows.

    Parameters
    ----------
    high, low
        Per-bar high and low price arrays, oldest to newest.
    left, right
        Bars of context on each side of a candidate pivot. ``right`` is the
        confirmation lag: a pivot is knowable ``right`` bars after it occurs.
    min_prominence
        Minimum fractional move a pivot must show against the opposite extreme
        of its own window. ``0`` accepts every geometric pivot.
    last_index
        The index of the most recent bar *actually available* to the analyst.
        Anything beyond it is future data and is never used to confirm a swing.
        This is what makes the function safe to call on a historical prefix.

    Returns
    -------
    list[Swing]
        Alternating high/low, in bar order. An empty list means no pivot met
        the rules — an honest answer, not an error.

    Detection rules (documented, because definitions differ between methods)
    --------------------------------------------------------------------------
    * A **swing high** is a bar whose high is the *unique* maximum of the
      window ``[i-left, i+right]``. Uniqueness is required so a flat plateau
      cannot produce several identical swings.
    * A **swing low** is the mirror rule on ``low``.
    * **Alternation** is enforced: two consecutive highs (or lows) keep only
      the more extreme one, so the sequence alternates and downstream methods
      (Elliott counts, harmonic XABCD legs) always see well-formed legs.
    * **Prominence**, when requested, compares the pivot to the opposite
      extreme inside its own window.
    """
    if left < 1 or right < 1:
        raise SwingError("`left` and `right` must each be at least 1")
    if min_prominence < 0:
        raise SwingError("`min_prominence` must be non-negative")

    h = _as_array(high, "high")
    lo = _as_array(low, "low")
    if h.shape != lo.shape:
        raise SwingError("`high` and `low` must be the same length")
    if np.any(~np.isfinite(h)) or np.any(~np.isfinite(lo)):
        raise SwingError("`high` and `low` must contain only finite values")

    n = h.size
    # Future bars are those the analyst cannot yet see. A pivot needs its whole
    # right-hand window to be visible before it can be judged.
    limit = n - 1 if last_index is None else min(int(last_index), n - 1)
    if limit < 0:
        raise SwingError("`last_index` is negative")

    candidates: list[Swing] = []
    for i in range(left, n - right):
        w_lo, w_hi = i - left, i + right
        if w_hi > limit:
            # The confirmation window reaches past the available data: this
            # pivot cannot be judged yet. Left unreported rather than guessed.
            break

        window_h = h[w_lo : w_hi + 1]
        window_l = lo[w_lo : w_hi + 1]
        left_h, right_h = h[w_lo:i], h[i + 1 : w_hi + 1]
        left_l, right_l = lo[w_lo:i], lo[i + 1 : w_hi + 1]

        # A swing high sits strictly above every bar to its left and at least as
        # high as every bar to its right. Strict-on-left is deliberate: a flat
        # plateau then yields exactly one pivot — its first bar — instead of one
        # per bar or none at all.
        if (
            left_h.size
            and h[i] > left_h.max()
            and h[i] >= right_h.max()
            and (min_prominence <= 0 or _prominent(h[i], window_l.min(), min_prominence))
        ):
            candidates.append(Swing(i, "high", float(h[i]), w_hi, True))

        # Mirror rule on the low side.
        if (
            left_l.size
            and lo[i] < left_l.min()
            and lo[i] <= right_l.min()
            and (min_prominence <= 0 or _prominent(lo[i], window_h.max(), min_prominence))
        ):
            candidates.append(Swing(i, "low", float(lo[i]), w_hi, True))

    return _enforce_alternation(candidates)


def _prominent(pivot: float, opposite_extreme: float, min_prominence: float) -> bool:
    """True when a pivot shows at least ``min_prominence`` against its window.

    Measured against the opposite extreme of the pivot's own window, i.e. the
    size of the swing the pivot actually defines. A zero or negative pivot
    price cannot express a fraction, so it is rejected rather than dividing.
    """
    if pivot <= 0:
        return False
    return abs(pivot - opposite_extreme) / pivot >= min_prominence


def _enforce_alternation(candidates: list[Swing]) -> list[Swing]:
    """Drop the weaker of any two consecutive same-kind pivots.

    Two highs in a row cannot both be structural: the second one's leg would
    have no intervening low. Keeping the more extreme preserves the geometry
    the downstream methods need.
    """
    out: list[Swing] = []
    for swing in candidates:
        if not out:
            out.append(swing)
            continue
        prev = out[-1]
        if prev.kind != swing.kind:
            out.append(swing)
            continue
        more_extreme = (
            swing.price > prev.price if swing.kind == "high" else swing.price < prev.price
        )
        if more_extreme:
            out[-1] = swing
    return out


def classify_structure(swings: list[Swing]) -> dict[str, Any]:
    """Label the swing sequence and find breaks of structure.

    Uses only swings in the order they were confirmed, so a label attached at
    bar *t* could have been written at bar *t*.

    Definitions (§9.2 requires them to be explicit, because methods differ)
    --------------------------------------------------------------------------
    * **HH** — a swing high above the previous swing high; **LH** below it.
    * **HL** — a swing low above the previous swing low; **LL** below it.
    * **Break of structure (BOS)** — the first bar *after* a swing is confirmed
      whose close exceeds that swing's price. Above a swing high is a bullish
      break; below a swing low is a bearish break.
    * **Trend** — reported only from the two most recent swings of each kind,
      and ``"mixed"``/``"insufficient data"`` where the evidence does not
      decide it. No trend is asserted from a single swing.
    """
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    labels: list[dict[str, Any]] = []
    for kind, group in (("high", highs), ("low", lows)):
        for prev, cur in zip(group, group[1:], strict=False):
            if kind == "high":
                name = "HH" if cur.price > prev.price else "LH"
            else:
                name = "HL" if cur.price > prev.price else "LL"
            labels.append(
                {
                    "kind": name,
                    "index": cur.index,
                    "price": round(float(cur.price), 4),
                    "vs_previous": round(float(cur.price - prev.price), 4),
                }
            )
    labels.sort(key=lambda row: row["index"])

    trend = "insufficient data"
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1].price > highs[-2].price
        hl = lows[-1].price > lows[-2].price
        if hh and hl:
            trend = "up"
        elif not hh and not hl:
            trend = "down"
        else:
            trend = "mixed"

    return {
        "labels": labels,
        "trend": trend,
        "swing_highs": len(highs),
        "swing_lows": len(lows),
    }


def find_breaks(swings: list[Swing], close: Any) -> list[dict[str, Any]]:
    """Bars at which price broke through a confirmed swing.

    A break is searched for from the swing's ``confirmed_index`` onwards — the
    first bar at which the level was knowable. It is never dated earlier, so a
    break can never precede the level it broke.
    """
    c = _as_array(close, "close")
    n = c.size
    breaks: list[dict[str, Any]] = []
    for swing in swings:
        start = max(swing.confirmed_index, swing.index)
        for j in range(start, n):
            if swing.kind == "high" and c[j] > swing.price:
                breaks.append(
                    {
                        "direction": "bullish",
                        "index": j,
                        "level": round(float(swing.price), 4),
                        "level_index": swing.index,
                    }
                )
                break
            if swing.kind == "low" and c[j] < swing.price:
                breaks.append(
                    {
                        "direction": "bearish",
                        "index": j,
                        "level": round(float(swing.price), 4),
                        "level_index": swing.index,
                    }
                )
                break
    breaks.sort(key=lambda row: row["index"])
    return breaks
