"""Fibonacci retracement and extension levels anchored on detected swings.

Why this exists
---------------
The Master Specification (§5) requires Fibonacci analysis as part of the
mandatory advanced-analysis engine. This module is the calculation half of it:
it turns two anchor prices into a level table. The anchors come from
:mod:`megatool.ta.swings`, so Fibonacci, support/resistance and the chart all
agree on what a turning point is.

One convention, stated once
---------------------------
Let ``start`` be the price where the measured move began, ``end`` the price
where it ended, and ``range = end - start`` (signed). Then::

    retracement(r) = end - range * r
    extension(r)    = end + range * r

That single pair of formulas is used everywhere — module, API, chart and tests
— so no two surfaces can drift apart (§28.2).

* A retracement at ``r`` lands *inside* the move when ``0 <= r <= 1``.
* An extension at ``r`` lands *beyond* ``end`` when ``r > 0``.
* Direction is derived from the sign of ``range``. Reversing the two anchors
  reverses the direction and produces the mirrored levels; the module never
  asks the caller which way the market went.

Worked example (independently hand-checked, and asserted in the tests)::

    start = 100 (low), end = 150 (high), range = +50
      retracement 0.618 -> 150 - 50*0.618 = 119.1
      extension    1.618 -> 150 + 50*1.618 = 230.9

    start = 150 (high), end = 100 (low), range = -50
      retracement 0.618 -> 100 - (-50)*0.618 = 130.9
      extension    1.618 -> 100 + (-50)*1.618 = 19.1

The 50% level
-------------
50% is **not** a Fibonacci ratio — ``sqrt(5)``-based ratios never produce it. It
is included because traders have watched it for a century, and it is labelled
``"convention"`` in every response rather than being quietly presented as one
of the family. §5.2 requires that distinction to be visible.

Result label
------------
These outputs are **CALCULATED**: arithmetic on two chosen anchor prices. They
are not predictions, not validated levels, and carry no claim that price will
respect them (§32.2, §32.7). Anchor choice is a judgement, so it is reported
alongside the numbers rather than hidden behind them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DEFAULT_EXTENSIONS",
    "DEFAULT_RETRACEMENTS",
    "FibonacciError",
    "FibonacciLevels",
    "levels_for",
]

#: Retracement ratios, as percentages of the measured move. ``0.5`` is the
#: documented non-Fibonacci convention (see module docstring).
DEFAULT_RETRACEMENTS: tuple[float, ...] = (0.236, 0.382, 0.5, 0.618, 0.786)

#: Extension/projection ratios, as multiples of the measured move.
DEFAULT_EXTENSIONS: tuple[float, ...] = (1.272, 1.382, 1.5, 1.618, 2.0, 2.618)

#: Retracement ratios that are genuinely Fibonacci (``phi``-derived) versus the
#: conventional midpoint. Kept explicit so a report can never label 50% as one.
_FIBONACCI_RETRACEMENTS = {0.236, 0.382, 0.618, 0.786}


class FibonacciError(ValueError):
    """Raised when the anchors cannot produce a meaningful Fibonacci study."""


def _ratio(r: float, name: str) -> float:
    """Validate one ratio, naming the offending value back to the caller."""
    value = float(r)
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        raise FibonacciError(f"`{name}` must be finite, got {r!r}")
    if value < 0:
        raise FibonacciError(f"`{name}` must be non-negative, got {r!r}")
    return value


@dataclass(slots=True)
class FibonacciLevels:
    """A computed level table plus the anchors and conventions that made it."""

    start: float
    end: float
    start_index: int | None
    end_index: int | None
    direction: str  # "up" (start < end) | "down" (start > end)
    retracements: list[dict[str, Any]] = field(default_factory=list)
    extensions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def range(self) -> float:
        """Signed size of the measured move."""
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchors": {
                "start_price": round(float(self.start), 4),
                "end_price": round(float(self.end), 4),
                "start_index": self.start_index,
                "end_index": self.end_index,
                "range": round(float(self.range), 4),
            },
            "direction": self.direction,
            "formula": {
                "retracement": "end - range * r",
                "extension": "end + range * r",
                "range": "end - start (signed)",
            },
            "retracements": self.retracements,
            "extensions": self.extensions,
        }


def levels_for(
    start: float,
    end: float,
    retracements: tuple[float, ...] | list[float] | None = None,
    extensions: tuple[float, ...] | list[float] | None = None,
    start_index: int | None = None,
    end_index: int | None = None,
) -> FibonacciLevels:
    """Compute retracement and extension levels for one measured move.

    Parameters
    ----------
    start, end
        The two anchor prices. Order matters only in that it fixes direction;
        swapping them mirrors the result, which the tests assert.
    retracements, extensions
        Ratios to compute. ``None`` selects the documented defaults. An empty
        sequence is legal and simply yields no levels of that kind.
    start_index, end_index
        Optional bar indices of the anchors, carried through for the UI.

    Raises
    ------
    FibonacciError
        If an anchor is non-finite, non-positive, or the two anchors are equal.
        Equal anchors are rejected rather than returning a flat, meaningless
        table where every level collapses onto one price.
    """
    lo = float(start)
    hi = float(end)
    for value, name in ((lo, "start"), (hi, "end")):
        if value != value or value in (float("inf"), float("-inf")):
            raise FibonacciError(f"`{name}` anchor must be finite, got {start!r}/{end!r}")
        if value <= 0:
            raise FibonacciError(f"`{name}` anchor must be a positive price, got {value!r}")

    span = hi - lo
    if span == 0:
        raise FibonacciError(
            "anchors are equal, so the measured move is zero and every level "
            "would collapse onto one price; choose two distinct swings"
        )

    ret_ratios = DEFAULT_RETRACEMENTS if retracements is None else retracements
    ext_ratios = DEFAULT_EXTENSIONS if extensions is None else extensions

    direction = "up" if span > 0 else "down"

    def build(ratios: Any, kind: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in ratios:
            r = _ratio(raw, kind)
            price = hi - span * r if kind == "retracement" else hi + span * r
            rows.append(
                {
                    "ratio": r,
                    "percent": round(r * 100, 3),
                    "price": round(price, 4),
                    "kind": kind,
                    # 50% is a market convention, not a Fibonacci ratio.
                    "family": ("convention" if kind == "retracement" and r == 0.5 else "fibonacci"),
                }
            )
        return rows

    return FibonacciLevels(
        start=lo,
        end=hi,
        start_index=start_index,
        end_index=end_index,
        direction=direction,
        retracements=build(ret_ratios, "retracement"),
        extensions=build(ext_ratios, "extension"),
    )
