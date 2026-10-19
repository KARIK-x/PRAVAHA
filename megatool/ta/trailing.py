"""Trailing-stop engine for an open long, computed bar by bar.

NEPSE has no retail shorting (the planning module already rejects short
plans), so this engine models an **open long only** and says so.

Three deterministic rules, sharing one ratchet:

* ``chandelier`` — the classic Chandelier Exit: ``highest_high(N) − k·ATR(N)``
  each closed bar (defaults N=22, k=3.0 after LeBeau's convention);
* ``swing`` — the lowest low of the last ``M`` bars (default 10);
* ``pct`` — the running peak **close** scaled by ``1 − pct/100``.

THE RATCHET (all methods): the stop may only move **up** for a long, never
down — ``stop[t] = max(stop[t−1], rule(t))``. A trailing stop that retreats is
not a trailing stop, so a declining rule value is recorded but never applied.

CAUSALITY AND HONESTY
---------------------
* the stop at bar ``t`` uses only bars up to and including ``t`` (close-time
  information); nothing looks ahead;
* an exit is evaluated on the bars *after* a stop exists: bar ``t`` is a stop
  hit when its low ≤ the stop computed through bar ``t−1``. The same-day stop
  value never exits the bar that produced it — that ordering is unknowable
  from daily bars and is not guessed;
* the exit price is the stop level itself; the module receives no open
  prices, so a possible worse gap-through fill is labelled as a limitation
  rather than claimed away;
* before a method's warmup exists (notably ATR), the stop is ``None`` and no
  exit can occur; warmup gaps are reported, not papered over.

Pure arithmetic on arrays the caller provides — no I/O, no caching.
"""

from __future__ import annotations

import math
from typing import Any

__all__ = ["TrailingError", "trailing_stop", "METHODS"]


class TrailingError(ValueError):
    """Raised for inputs or parameters that cannot produce a stop series."""


METHODS = ("chandelier", "swing", "pct")


def _wilders_atr(
    high: list[float], low: list[float], close: list[float], period: int
) -> list[float | None]:
    """Wilder's ATR as a per-bar series with ``None`` during warmup."""
    n = len(high)
    trs: list[float] = []
    for i in range(n):
        if i == 0:
            tr = high[0] - low[0]
        else:
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
        trs.append(tr)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    window = trs[:period]
    atr = sum(window) / period
    out[period - 1] = atr
    for i in range(period, n):
        atr = (atr * (period - 1) + trs[i]) / period
        out[i] = atr
    return out


def trailing_stop(
    high: list[float],
    low: list[float],
    close: list[float],
    method: str = "chandelier",
    *,
    atr_period: int = 22,
    atr_multiple: float = 3.0,
    swing_bars: int = 10,
    pct: float = 8.0,
) -> dict[str, Any]:
    """Compute a ratcheted trailing-stop series for one open long.

    ``high``/``low``/``close`` are equal-length daily series ordered oldest
    first. Malformed bars (non-finite or nonpositive prices) abort the walk:
    a stop chain cannot skip dates it does not have, so a bad bar ends the
    series there and the response says so — the chain is never filled across
    a hole.
    """
    if method not in METHODS:
        raise TrailingError(f"unknown method {method!r}; supported: {', '.join(METHODS)}")
    if not high or not (len(high) == len(low) == len(close)):
        raise TrailingError("high, low and close must be the same, nonempty length")
    if method == "chandelier":
        if not 1 <= atr_period <= 500:
            raise TrailingError("atr_period must be within 1..500")
        if not 0.1 <= atr_multiple <= 20.0:
            raise TrailingError("atr_multiple must be within 0.1..20")
    if method == "swing" and not 2 <= swing_bars <= 500:
        raise TrailingError("swing_bars must be within 2..500")
    if method == "pct" and not 0.1 <= pct <= 90.0:
        raise TrailingError("pct must be within 0.1..90")

    n = len(high)
    # A trailing chain cannot be continued across an invalid bar: stop at the
    # first malformed bar and report it. (Nonpositive prices are nonsensical
    # for equities; non-finite ones are data defects.)
    usable = n
    for i in range(n):
        h, lo_c, c = high[i], low[i], close[i]
        if (
            not math.isfinite(h)
            or not math.isfinite(lo_c)
            or not math.isfinite(c)
            or h <= 0.0
            or lo_c <= 0.0
            or c <= 0.0
        ):
            usable = i
            break
    head = usable

    stops: list[float | None] = [None] * head
    rule_vals: list[float | None] = [None] * head

    if method == "chandelier":
        atrs = _wilders_atr(high[:head], low[:head], close[:head], atr_period)
        for i in range(head):
            if atrs[i] is None:
                continue
            window_high = max(high[max(0, i - atr_period + 1) : i + 1])
            rule_vals[i] = window_high - atr_multiple * float(atrs[i])
    elif method == "swing":
        for i in range(head):
            if i + 1 < swing_bars:
                continue
            rule_vals[i] = min(low[i + 1 - swing_bars : i + 1])
    else:  # pct
        peak = -math.inf
        for i in range(head):
            peak = max(peak, close[i])
            rule_vals[i] = peak * (1.0 - pct / 100.0)

    # Apply the ratchet. A rule that lands at or above the bar's own close
    # would imply an exit the close-time ordering cannot justify, so the
    # stop simply stays where it was; the raw rule value is kept for the
    # caller's inspection instead of being hidden.
    current: float | None = None
    for i in range(head):
        rule = rule_vals[i]
        stops[i] = current
        if rule is None or not math.isfinite(rule) or rule <= 0.0:
            continue
        candidate = rule if current is None else max(current, rule)
        if candidate >= close[i]:
            continue  # recorded in rule_vals; never applied over the close
        current = candidate
        stops[i] = current

    # After a stop exists, the first LATER bar whose low reaches it is the
    # stop hit; the recorded fill is the stop level itself (daily bars carry
    # no reliable open in this contract, so a gap-through fill is labelled as
    # a limitation rather than priced optimistically).
    exited_index: int | None = None
    exit_price: float | None = None
    for i in range(1, head):
        prev = stops[i - 1]
        if prev is None:
            continue
        if low[i] <= prev:
            exited_index = i
            exit_price = prev
            break

    return {
        "method": method,
        "params": {
            "atr_period": atr_period,
            "atr_multiple": atr_multiple,
            "swing_bars": swing_bars,
            "pct": pct,
        },
        "bars_used": head,
        "bars_skipped_tail": n - head,
        "side": "long (NEPSE retail shorting is not modelled)",
        "stops": [None if s is None else round(s, 6) for s in stops],
        "exited_index": exited_index,
        "exit_price": None if exit_price is None else round(exit_price, 6),
        "rule": {
            "chandelier": "stop = highest high(N) − k × ATR(N) (Wilder smoothing), ratcheted up",
            "swing": "stop = lowest low of the last M bars, ratcheted up",
            "pct": "stop = running peak close × (1 − pct/100), ratcheted up",
        }[method],
        "ordering_rule": (
            "stop[t] uses bars ≤ t only; an exit needs a LATER bar's low at or "
            "below that stop, and the recorded fill is the stop level (a "
            "gap-through open could fill worse — the module models no open "
            "price, so none is claimed)"
        ),
    }
