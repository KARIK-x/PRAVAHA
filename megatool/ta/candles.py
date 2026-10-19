"""Candlestick pattern detection with executable, documented rules.

Why this module exists
----------------------
Chart patterns are a mandatory feature of the Master Specification (§6), and
the project's honesty rules require that every claim carry the rule that
produced it (§9.2, §32.2). Candlestick patterns are notorious for being
described vaguely (``"a small body with a long wick"``) and then implemented
inconsistently. This module therefore defines **fifteen patterns as
executable predicates** — every threshold is a named, configurable parameter
with a documented default, and every pattern states its required context,
its gap requirement (or "none") and its invalidation conditions below.

Result label
------------
Every ``Pattern`` carries ``classification="DETECTED"``: an algorithm found a
candidate shape that satisfies explicit geometric rules on the bars supplied.
It is **not** a prediction, **not** a confirmed reversal, and **not** a
buy/sell recommendation. A bullish or bearish label describes the *shape of
the candles*, not what price will do next.

Confirmation
------------
Most of these patterns are *unconfirmed* on the bar they form: the classic
textbook rules require a further bar to close in the pattern's direction
before the signal is "confirmed". This module does **not** implement such a
confirmation rule, so ``confirmed`` is always ``None`` and
``confirmation_status`` is always ``"not evaluated"``. No confirmation is
ever implied.

Support / resistance
--------------------
This module has no access to support or resistance analysis. Every pattern's
context carries ``near_support = None`` meaning *not evaluated* — never a
fabricated claim that a pattern sits "near support".

Shared geometry (the vocabulary used by every rule)
----------------------------------------------------
For a bar with open ``O``, high ``H``, low ``L``, close ``C``:

* ``body``          = ``|C - O|`` (the real body)
* ``range``         = ``H - L`` (the full span)
* ``upper_shadow``  = ``H - max(O, C)``
* ``lower_shadow``  = ``min(O, C) - L``
* ``body_ratio``    = ``body / range``
* ``upper_ratio``   = ``upper_shadow / range``
* ``lower_ratio``   = ``lower_shadow / range``
* bar direction     = ``bullish`` if ``C > O``, ``bearish`` if ``C < O``,
  ``neutral`` if ``C == O``.

**Zero-range bars** (``H == L``, which forces ``H == L == O == C`` after
validation) have no defined ratios — ``0/0`` is not a number. They are
therefore *excluded from candidacy entirely*: a zero-range bar can never be
part of a detected pattern, and no division by zero ever occurs. This is a
deliberate rule, not an accident; the alternative (inventing a ratio for a
bar that has none) would be fabrication.

Prior trend (the explicit rule, because "downtrend" is otherwise hand-waving)
----------------------------------------------------------------------------
For a pattern whose window starts at bar ``s`` (its first candle):

* the window considered is the ``trend_bars`` closes ending at bar ``s-1``,
  i.e. from ``close[s - 1 - trend_bars]`` to ``close[s - 1]``;
* **up** if the later close is strictly higher, **down** if strictly lower,
  **flat** if equal;
* **"insufficient history"** when fewer than ``trend_bars`` closes exist
  before the pattern. When ``require_prior_trend`` is true (the default), a
  pattern whose required context is *insufficient* is **skipped**, not
  reported without its context.

Default ``trend_bars = 3``. The requirement is enforced per pattern in the
list below; ``PatternParams(require_prior_trend=False)`` disables gating
(context is then measured and reported but does not gate detection).

Causality (no future data)
--------------------------
A pattern reported at index ``i`` uses only bars ``[0 .. i]`` — ``i`` is the
bar on which the pattern *completes* (the second candle of a two-candle
pattern, the third of a three-candle pattern), which is also the earliest bar
at which the shape could be seen. This is proven by a prefix test in
``tests/test_candles.py``.

Executable pattern definitions
------------------------------
Every rule below is implemented exactly as written. "Invalidation" means the
pattern must **not** fire when the condition fails.

SINGLE-CANDLE (window = bar ``i``; pattern index = ``i``)

* ``doji`` — direction ``neutral``.
  Body: ``body_ratio <= doji_max_body_ratio`` (default **0.10**).
  Shadows: any. Gap: none. Context: none required.
  Invalidated when ``body_ratio > 0.10`` or the bar has zero range.

* ``hammer`` — direction ``bullish``.
  Body: ``body_ratio <= hammer_max_body_ratio`` (default **0.35**).
  Shadows: ``lower_shadow >= hammer_min_lower_multiple * body`` (default
  **2.0x** the body) and ``upper_ratio <= hammer_max_upper_ratio`` (default
  **0.10**). Gap: none. Context: **prior downtrend required**.
  Invalidated when the lower shadow is shorter than 2x the body, the upper
  shadow exceeds 10% of range, the body exceeds 35% of range, or the prior
  trend is not down.

* ``inverted_hammer`` — direction ``bullish``.
  Body: ``body_ratio <= inverted_max_body_ratio`` (default **0.35**).
  Shadows: ``upper_shadow >= inverted_min_upper_multiple * body`` (default
  **2.0x** the body) and ``lower_ratio <= inverted_max_lower_ratio`` (default
  **0.10**). Gap: none. Context: **prior downtrend required**.
  Invalidated by the mirror conditions of ``hammer``.

* ``shooting_star`` — direction ``bearish``.
  Identical geometry to ``inverted_hammer`` (same three tolerances); the only
  difference is context: **prior uptrend required**.

* ``spinning_top`` — direction ``neutral``.
  Body: ``spinning_min_body_ratio < body_ratio <= spinning_max_body_ratio``
  (defaults **> 0.10** and **<= 0.30** — the lower bound makes it disjoint
  from ``doji`` under default parameters).
  Shadows: ``upper_ratio >= spinning_min_shadow_ratio`` and
  ``lower_ratio >= spinning_min_shadow_ratio`` (defaults **0.20** each).
  Gap: none. Context: none required.
  Invalidated when the body is outside that band or either shadow is under
  20% of range.

* ``marubozu`` — direction follows the candle (``bullish`` / ``bearish``).
  Body: ``body > 0``. Shadows: ``upper_ratio <= marubozu_max_shadow_ratio``
  and ``lower_ratio <= marubozu_max_shadow_ratio`` (defaults **0.05** each),
  i.e. both shadows together may occupy at most 10% of the range.
  Gap: none. Context: none required. Invalidated by any shadow over 5% of
  range or an equal open/close.

TWO-CANDLE (window = bars ``[i-1, i]``; pattern index = ``i``, the completion
bar). Both bars must have positive range.

* ``bullish_engulfing`` — direction ``bullish``.
  First bar bearish, second bullish. Engulfment:
  ``open2 <= close1`` **and** ``close2 >= open1`` **and** ``body2 > body1``
  (strictly larger body — equal bodies do not engulf).
  Gap: none (the opens/closes must simply span the first body).
  Context: **prior downtrend required** (before bar ``i-1``).
  Invalidated by a non-engulfing span, equal-or-smaller second body, or a
  prior trend that is not down.

* ``bearish_engulfing`` — direction ``bearish``.
  Mirror: first bullish, second bearish; ``open2 >= close1`` **and**
  ``close2 <= open1`` **and** ``body2 > body1``.
  Gap: none. Context: **prior uptrend required**.

* ``harami`` — direction is the opposite of the *first* bar (first bearish
  -> ``bullish``; first bullish -> ``bearish``).
  First bar's ``body_ratio >= harami_min_first_body_ratio`` (default
  **0.50** — a substantial first candle). Second bar's real body contained
  within the first bar's real body: ``min(O2,C2) >= min(O1,C1)`` and
  ``max(O2,C2) <= max(O1,C1)``, **and** ``body2 < body1`` (strictly
  smaller). A direction-neutral first bar cannot produce a harami.
  Gap: none. Context: prior trend matching the first bar's direction is
  required (downtrend for a bullish harami, uptrend for a bearish one).
  Invalidated by a first body under 50% of its range, a second body
  escaping the first body, or an equal-sized second body.

* ``piercing_pattern`` — direction ``bullish``.
  First bar bearish, second bullish. ``open2 < close1`` (the second bar
  opens strictly below the first bar's close — the gap requirement) and
  ``close2 > midpoint(first body)`` where midpoint = ``(O1 + C1) / 2``, and
  ``close2 < open1`` (the pierce stops short of the first open; closing at
  or above it becomes an engulfing instead).
  Context: **prior downtrend required**. Invalidated by a close at or below
  the midpoint, a close at or above the first open, or an open at or above
  the first close.

* ``dark_cloud_cover`` — direction ``bearish``.
  Mirror of piercing: first bullish, second bearish; ``open2 > close1``;
  ``close2 < midpoint(first body)``; ``close2 > open1``.
  Gap: the second bar opens strictly above the first bar's close.
  Context: **prior uptrend required**.

THREE-CANDLE (window = bars ``[i-2, i]``; pattern index = ``i``). All three
bars must have positive range.

* ``morning_star`` — direction ``bullish``.
  First bar bearish with ``body_ratio >= star_min_first_body_ratio``
  (default **0.60** — a long first candle). Second bar ("star") with
  ``body_ratio <= star_max_middle_body_ratio`` (default **0.50**) whose
  **open is strictly below the first bar's close** (``O2 < C1`` — the gap
  requirement). Third bar bullish with ``close3 > midpoint(first body)``
  where midpoint = ``(O1 + C1) / 2``.
  Context: **prior downtrend required** (before bar ``i-2``).
  Invalidated by a small first body, a star opening at or above the first
  close, a star body over 50% of its range, a non-bullish third bar, or a
  third close at or below the first body's midpoint.

* ``evening_star`` — direction ``bearish``.
  Mirror: first bullish and substantial (same 0.60 ratio); star small
  (<= 0.50) with ``O2 > C1`` (gap up); third bar bearish with
  ``close3 < midpoint(first body)``. Context: **prior uptrend required**.

* ``three_white_soldiers`` — direction ``bullish``.
  All three bars bullish; strictly rising closes
  ``close1 < close2 < close3``; each bar opens *inside the previous bar's
  real body*: ``open2 in [open1, close1]`` and ``open3 in [open2, close2]``
  (endpoints inclusive); every bar's
  ``body_ratio >= soldiers_min_body_ratio`` (default **0.50**).
  Gap: none — by definition each bar opens back inside the prior body.
  Context: **prior downtrend required**.
  Invalidated by any non-bullish bar, a flat or lower close, an open
  outside the prior body, or any body under 50% of its range.

* ``three_black_crows`` — direction ``bearish``.
  Mirror: all three bearish; strictly falling closes
  ``close1 > close2 > close3``; ``open2 in [close1, open1]`` and
  ``open3 in [close2, open2]``; every body at least 50% of its range.
  Gap: none. Context: **prior uptrend required**.

Parameters and defaults
-----------------------
Tolerances live in :class:`PatternParams` (every field is documented there);
``detect_patterns`` accepts a ``PatternParams``, a ``dict`` of overrides, or
``None`` for defaults. Unknown keys and out-of-range values raise
:class:`CandleError` rather than being silently ignored.

Bad data, explicitly
--------------------
Invalid OHLC relationships (``high < low``, ``high`` below the open or
close, ``low`` above the open or close), non-finite values (NaN/inf),
mismatched or empty arrays, and series shorter than ``MIN_BARS = 3`` all
raise :class:`CandleError`. Zero-range bars never raise — they are excluded
from candidacy as documented above.

Determinism
-----------
Detection is a fixed sequence of comparisons in a fixed order (per bar:
single-candle patterns in the order listed in :data:`__all__`'s module
order, then two-candle, then three-candle), so equivalent inputs always
produce byte-identical output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

import numpy as np

__all__ = [
    "CANDLE_RULE_VERSION",
    "MIN_BARS",
    "CandleError",
    "Pattern",
    "PatternParams",
    "detect_patterns",
    "validate_ohlc",
]

#: Version tag stamped on every Pattern. Bump when any rule or default
#: changes, so stored detections remain traceable to the rule set that made them.
CANDLE_RULE_VERSION = "candles-1.0"

#: Fewest bars ``detect_patterns`` accepts (the largest window is three candles).
MIN_BARS = 3

#: Default trend context length, in bars, for patterns that require one.
DEFAULT_TREND_BARS = 3

#: Public catalogue of every pattern name :func:`detect_patterns` can emit, in
#: detection order (single-, then two-, then three-candle). Consumers (API,
#: frontend filter, research report) read this instead of re-deriving it, so a
#: new detector cannot become invisible to the UI. Grouped by candle count.
_SINGLE_PATTERNS: tuple[str, ...] = (
    "doji",
    "hammer",
    "inverted_hammer",
    "shooting_star",
    "spinning_top",
    "marubozu",
)
_TWO_PATTERNS: tuple[str, ...] = (
    "bullish_engulfing",
    "bearish_engulfing",
    "harami",
    "harami_cross",
    "piercing_pattern",
    "dark_cloud_cover",
    "tweezer_bottom",
    "tweezer_top",
)
_THREE_PATTERNS: tuple[str, ...] = (
    "morning_star",
    "evening_star",
    "three_white_soldiers",
    "three_black_crows",
)
PATTERN_NAMES: tuple[str, ...] = _SINGLE_PATTERNS + _TWO_PATTERNS + _THREE_PATTERNS

#: Candle-count class for each pattern name (for grouping in the UI). Derived
#: from the grouped tuples above, so it can never drift from ``PATTERN_NAMES``.
PATTERN_CANDLE_COUNT: dict[str, int] = {
    **{n: 1 for n in _SINGLE_PATTERNS},
    **{n: 2 for n in _TWO_PATTERNS},
    **{n: 3 for n in _THREE_PATTERNS},
}


class CandleError(ValueError):
    """Raised when the OHLC inputs or parameters cannot produce meaningful detections."""


# --------------------------------------------------------------- dataclasses
@dataclass(slots=True)
class Pattern:
    """One detected candidate pattern.

    ``index`` is the *completion* bar: the bar on which the shape becomes
    visible and therefore the earliest bar at which the detection could have
    been made. ``date`` is filled by the caller (``detect_patterns`` fills it
    when a ``dates`` sequence is supplied).

    ``classification`` is always ``"DETECTED"`` — an algorithm found a shape
    under the documented rules; it is not a prediction and not a validated
    signal.

    ``confirmed`` is always ``None`` and ``confirmation_status`` is always
    ``"not evaluated"``: this module implements no confirmation rule and
    never implies one.
    """

    name: str
    direction: str  # "bullish" | "bearish" | "neutral"
    index: int
    date: str = ""
    classification: str = "DETECTED"
    rule_version: str = CANDLE_RULE_VERSION
    #: The actual numbers that triggered the rule (body, range, shadows,
    #: ratios, and for multi-candle patterns the triggering comparisons).
    measurements: dict[str, Any] = field(default_factory=dict)
    #: Prior-trend evidence, window bounds, and ``near_support=None`` (not evaluated).
    context: dict[str, Any] = field(default_factory=dict)
    #: Stated limitations, e.g. "geometry only; not a confirmed reversal".
    notes: list[str] = field(default_factory=list)
    #: Always None: no confirmation rule is implemented here.
    confirmed: bool | None = None
    #: Always "not evaluated": no confirmation rule is implemented here.
    confirmation_status: str = "not evaluated"

    def to_dict(self) -> dict[str, Any]:
        """JSON-clean dict; floats rounded to 6 decimals for stable output."""
        return {
            "name": self.name,
            "direction": self.direction,
            "index": self.index,
            "date": self.date,
            "classification": self.classification,
            "rule_version": self.rule_version,
            "measurements": _round_nested(self.measurements),
            "context": _round_nested(self.context),
            "notes": list(self.notes),
            "confirmed": self.confirmed,
            "confirmation_status": self.confirmation_status,
        }


@dataclass(slots=True)
class PatternParams:
    """Configurable tolerances for :func:`detect_patterns`.

    Defaults implement the definitions in the module docstring. Ratio-valued
    fields must lie in ``[0, 1]``; multiple-valued fields must be ``> 0``;
    ``trend_bars`` must be an integer ``>= 1``.

    Notes on the defaults:

    * ``doji_max_body_ratio`` (0.10) and ``spinning_min_body_ratio`` (0.10)
      are equal, so with default parameters ``doji`` (``<= 0.10``) and
      ``spinning_top`` (``> 0.10``) are disjoint. Custom overrides may make
      them overlap; that is the caller's choice, not an error.
    * The hammer/inverted-hammer/shooting-star tolerances come in triples:
      a small-body cap, a 2.0x shadow-vs-body multiple, and a 10%-of-range
      cap on the *opposite* shadow.
    """

    # single-candle
    doji_max_body_ratio: float = 0.10
    spinning_min_body_ratio: float = 0.10  # exclusive lower bound
    spinning_max_body_ratio: float = 0.30
    spinning_min_shadow_ratio: float = 0.20
    hammer_max_body_ratio: float = 0.35
    hammer_min_lower_multiple: float = 2.0
    hammer_max_upper_ratio: float = 0.10
    inverted_max_body_ratio: float = 0.35
    inverted_min_upper_multiple: float = 2.0
    inverted_max_lower_ratio: float = 0.10
    marubozu_max_shadow_ratio: float = 0.05
    # two-candle
    harami_min_first_body_ratio: float = 0.50
    #: Two-candle "tweezer" tolerance: the two lows (bottom) or two highs (top)
    #: must agree to within this fraction of their mean price.
    tweezer_tolerance_ratio: float = 0.001
    # three-candle
    star_min_first_body_ratio: float = 0.60
    star_max_middle_body_ratio: float = 0.50
    soldiers_min_body_ratio: float = 0.50
    # context
    trend_bars: int = 3
    require_prior_trend: bool = True


_RATIO_PARAMS = frozenset(
    {
        "doji_max_body_ratio",
        "spinning_min_body_ratio",
        "spinning_max_body_ratio",
        "spinning_min_shadow_ratio",
        "hammer_max_body_ratio",
        "hammer_max_upper_ratio",
        "inverted_max_body_ratio",
        "inverted_max_lower_ratio",
        "marubozu_max_shadow_ratio",
        "harami_min_first_body_ratio",
        "tweezer_tolerance_ratio",
        "star_min_first_body_ratio",
        "star_max_middle_body_ratio",
        "soldiers_min_body_ratio",
    }
)
_MULTIPLE_PARAMS = frozenset({"hammer_min_lower_multiple", "inverted_min_upper_multiple"})


def _resolve_params(params: PatternParams | dict[str, Any] | None) -> PatternParams:
    """Merge user overrides onto the defaults and validate every field."""
    if params is None:
        return PatternParams()
    if isinstance(params, PatternParams):
        merged = asdict(params)
    elif isinstance(params, dict):
        known = {f.name for f in fields(PatternParams)}
        unknown = set(params) - known
        if unknown:
            raise CandleError(f"unknown parameter(s) {sorted(unknown)}; declared {sorted(known)}")
        merged = {**asdict(PatternParams()), **params}
    else:
        raise CandleError(
            f"params must be a PatternParams, a dict, or None; got {type(params).__name__}"
        )

    for key, value in merged.items():
        if key == "require_prior_trend":
            if not isinstance(value, bool):
                raise CandleError(f"`require_prior_trend` must be a bool, got {value!r}")
            continue
        if key == "trend_bars":
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise CandleError(f"`trend_bars` must be an integer >= 1, got {value!r}")
            if int(value) < 1:
                raise CandleError(f"`trend_bars` must be >= 1, got {value}")
            merged[key] = int(value)
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise CandleError(f"`{key}` must be numeric, got {value!r}")
        v = float(value)
        if not np.isfinite(v):
            raise CandleError(f"`{key}` must be finite, got {value!r}")
        if key in _RATIO_PARAMS and not 0.0 <= v <= 1.0:
            raise CandleError(f"`{key}` is a ratio and must be within [0, 1], got {v}")
        if key in _MULTIPLE_PARAMS and v <= 0.0:
            raise CandleError(f"`{key}` must be > 0, got {v}")
        merged[key] = v
    return PatternParams(**merged)


# ----------------------------------------------------------------- validation
def _as_prices(values: Any, name: str) -> np.ndarray:
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:  # pragma: no cover - message passthrough
        raise CandleError(f"`{name}` could not be read as numbers: {exc}") from exc
    if arr.ndim != 1:
        raise CandleError(f"`{name}` must be one-dimensional, got shape {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise CandleError(f"`{name}` must contain only finite values (NaN or inf found)")
    return arr


def validate_ohlc(
    open_: Any, high: Any, low: Any, close: Any, *, min_bars: int = 0
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Validate and convert OHLC arrays to 1-D float ndarrays.

    Raises :class:`CandleError` for non-numeric input, non-1-D input,
    non-finite values, mismatched lengths, empty input, invalid OHLC
    relationships (``high < low``, ``high`` below the open/close, ``low``
    above the open/close), or fewer than ``min_bars`` bars.

    Zero-range bars (``high == low``) are *valid* here; they are excluded
    from pattern candidacy later rather than rejected.
    """
    o = _as_prices(open_, "open")
    h = _as_prices(high, "high")
    lo = _as_prices(low, "low")
    c = _as_prices(close, "close")
    if not (o.shape == h.shape == lo.shape == c.shape):
        raise CandleError(
            "OHLC arrays must be the same length: "
            f"open={o.size}, high={h.size}, low={lo.size}, close={c.size}"
        )
    n = int(o.size)
    if n == 0:
        raise CandleError("insufficient history: OHLC arrays are empty")
    if np.any(h < lo):
        raise CandleError("invalid OHLC: `high` is below `low` on at least one bar")
    if np.any(h < np.maximum(o, c)):
        raise CandleError("invalid OHLC: `high` is below the open or close on at least one bar")
    if np.any(lo > np.minimum(o, c)):
        raise CandleError("invalid OHLC: `low` is above the open or close on at least one bar")
    if n < min_bars:
        raise CandleError(f"insufficient history: need at least {min_bars} bars, got {n}")
    return o, h, lo, c


# ------------------------------------------------------------------- geometry
@dataclass(slots=True)
class _Geometry:
    o: np.ndarray
    h: np.ndarray
    lo: np.ndarray
    c: np.ndarray
    body: np.ndarray
    rng: np.ndarray
    upper: np.ndarray
    lower: np.ndarray
    body_ratio: np.ndarray
    upper_ratio: np.ndarray
    lower_ratio: np.ndarray
    direction: np.ndarray  # +1 bullish, -1 bearish, 0 neutral (includes zero-range bars)


def _geometry(o: np.ndarray, h: np.ndarray, lo: np.ndarray, c: np.ndarray) -> _Geometry:
    body_top = np.maximum(o, c)
    body_bot = np.minimum(o, c)
    body = body_top - body_bot
    rng = h - lo
    upper = h - body_top
    lower = body_bot - lo
    with np.errstate(divide="ignore", invalid="ignore"):
        body_ratio = np.where(rng > 0, body / rng, np.nan)
        upper_ratio = np.where(rng > 0, upper / rng, np.nan)
        lower_ratio = np.where(rng > 0, lower / rng, np.nan)
    return _Geometry(
        o=o,
        h=h,
        lo=lo,
        c=c,
        body=body,
        rng=rng,
        upper=upper,
        lower=lower,
        body_ratio=body_ratio,
        upper_ratio=upper_ratio,
        lower_ratio=lower_ratio,
        direction=np.sign(c - o).astype(int),
    )


def _bar_measure(g: _Geometry, i: int) -> dict[str, float]:
    """The full geometry of one bar, as stored in ``measurements``."""
    return {
        "open": float(g.o[i]),
        "high": float(g.h[i]),
        "low": float(g.lo[i]),
        "close": float(g.c[i]),
        "body": float(g.body[i]),
        "range": float(g.rng[i]),
        "upper_shadow": float(g.upper[i]),
        "lower_shadow": float(g.lower[i]),
        "body_ratio": float(g.body_ratio[i]),
        "upper_ratio": float(g.upper_ratio[i]),
        "lower_ratio": float(g.lower_ratio[i]),
    }


def _prior_trend(closes: np.ndarray, s: int, p: PatternParams) -> tuple[str, float | None]:
    """Net close change over the ``trend_bars`` steps ending at bar ``s-1``.

    Returns ``(direction, pct_change)`` where direction is "up", "down",
    "flat", or "insufficient history" when fewer than ``trend_bars`` closes
    precede the pattern window. Uses only closes at indices ``< s``.
    """
    start = s - 1 - p.trend_bars
    if s < 1 or start < 0:
        return "insufficient history", None
    base = float(closes[start])
    last = float(closes[s - 1])
    change = last - base
    pct = None if base == 0.0 else 100.0 * change / base
    if change > 0:
        return "up", pct
    if change < 0:
        return "down", pct
    return "flat", pct


def _context_block(
    closes: np.ndarray, s: int, p: PatternParams, want: str | None
) -> tuple[bool, dict[str, Any], list[str]]:
    """Build the context dict and decide whether the trend gate passes.

    ``want`` is the required prior-trend direction ("up"/"down"), or ``None``
    when the pattern has no context requirement.
    """
    trend, pct = _prior_trend(closes, s, p)
    ctx: dict[str, Any] = {
        "prior_trend": trend,
        "prior_trend_required": want is not None,
        "prior_trend_window": p.trend_bars,
        "prior_trend_change_pct": pct,
        "bars_before_pattern": s,
        "pattern_window_start": s,
        # This module never runs support analysis; an explicit None, never a claim.
        "near_support": None,
    }
    notes: list[str] = []
    if want is None:
        return True, ctx, notes
    if not p.require_prior_trend:
        notes.append("prior-trend requirement disabled by params; context measured but not gating")
        return True, ctx, notes
    if trend != want:
        return False, ctx, notes
    notes.append(
        f"prior {want} trend required by rule and satisfied over the "
        f"{p.trend_bars} bars before the pattern"
    )
    return True, ctx, notes


_BASE_NOTES = [
    "geometry only; not a confirmed reversal",
    "confirmation status: not evaluated",
]


def _emit(
    name: str,
    direction: str,
    i: int,
    measurements: dict[str, Any],
    context: dict[str, Any],
    notes: list[str],
) -> Pattern:
    return Pattern(
        name=name,
        direction=direction,
        index=i,
        measurements=measurements,
        context=context,
        notes=[*_BASE_NOTES, *notes],
    )


# ----------------------------------------------------------------- detectors
def _positive_range(g: _Geometry, *idxs: int) -> bool:
    """True when every listed bar has a positive range (zero-range excluded)."""
    return all(g.rng[i] > 0 for i in idxs)


# single-candle -------------------------------------------------------------
def _detect_doji(i: int, g: _Geometry, p: PatternParams, closes: np.ndarray) -> Pattern | None:
    if not _positive_range(g, i) or g.body_ratio[i] > p.doji_max_body_ratio:
        return None
    _, ctx, notes = _context_block(closes, i, p, want=None)
    return _emit("doji", "neutral", i, _bar_measure(g, i), ctx, notes)


def _detect_hammer(i: int, g: _Geometry, p: PatternParams, closes: np.ndarray) -> Pattern | None:
    if not _positive_range(g, i):
        return None
    if g.body_ratio[i] > p.hammer_max_body_ratio:
        return None
    if g.lower[i] < p.hammer_min_lower_multiple * g.body[i]:
        return None
    if g.upper_ratio[i] > p.hammer_max_upper_ratio:
        return None
    ok, ctx, notes = _context_block(closes, i, p, want="down")
    if not ok:
        return None
    return _emit("hammer", "bullish", i, _bar_measure(g, i), ctx, notes)


def _long_upper_shadow_geometry(i: int, g: _Geometry, p: PatternParams) -> bool:
    """Shared geometry of inverted hammer and shooting star."""
    if not _positive_range(g, i):
        return False
    if g.body_ratio[i] > p.inverted_max_body_ratio:
        return False
    if g.upper[i] < p.inverted_min_upper_multiple * g.body[i]:
        return False
    return g.lower_ratio[i] <= p.inverted_max_lower_ratio


def _detect_inverted_hammer(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    if not _long_upper_shadow_geometry(i, g, p):
        return None
    ok, ctx, notes = _context_block(closes, i, p, want="down")
    if not ok:
        return None
    return _emit("inverted_hammer", "bullish", i, _bar_measure(g, i), ctx, notes)


def _detect_shooting_star(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    if not _long_upper_shadow_geometry(i, g, p):
        return None
    ok, ctx, notes = _context_block(closes, i, p, want="up")
    if not ok:
        return None
    return _emit("shooting_star", "bearish", i, _bar_measure(g, i), ctx, notes)


def _detect_spinning_top(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    if not _positive_range(g, i):
        return None
    ratio = g.body_ratio[i]
    if not (p.spinning_min_body_ratio < ratio <= p.spinning_max_body_ratio):
        return None
    if g.upper_ratio[i] < p.spinning_min_shadow_ratio:
        return None
    if g.lower_ratio[i] < p.spinning_min_shadow_ratio:
        return None
    _, ctx, notes = _context_block(closes, i, p, want=None)
    return _emit("spinning_top", "neutral", i, _bar_measure(g, i), ctx, notes)


def _detect_marubozu(i: int, g: _Geometry, p: PatternParams, closes: np.ndarray) -> Pattern | None:
    if not _positive_range(g, i) or g.body[i] <= 0:
        return None
    if g.upper_ratio[i] > p.marubozu_max_shadow_ratio:
        return None
    if g.lower_ratio[i] > p.marubozu_max_shadow_ratio:
        return None
    _, ctx, notes = _context_block(closes, i, p, want=None)
    direction = "bullish" if g.direction[i] > 0 else "bearish"
    return _emit("marubozu", direction, i, _bar_measure(g, i), ctx, notes)


# two-candle ---------------------------------------------------------------
def _detect_bullish_engulfing(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    a, b = i - 1, i
    if not _positive_range(g, a, b):
        return None
    if g.direction[a] != -1 or g.direction[b] != 1:
        return None
    if not (g.o[b] <= g.c[a] and g.c[b] >= g.o[a] and g.body[b] > g.body[a]):
        return None
    ok, ctx, notes = _context_block(closes, a, p, want="down")
    if not ok:
        return None
    measurements = {
        "first": _bar_measure(g, a),
        "second": _bar_measure(g, b),
        "open2_minus_close1": float(g.o[b] - g.c[a]),
        "close2_minus_open1": float(g.c[b] - g.o[a]),
        "body2_minus_body1": float(g.body[b] - g.body[a]),
    }
    return _emit("bullish_engulfing", "bullish", i, measurements, ctx, notes)


def _detect_bearish_engulfing(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    a, b = i - 1, i
    if not _positive_range(g, a, b):
        return None
    if g.direction[a] != 1 or g.direction[b] != -1:
        return None
    if not (g.o[b] >= g.c[a] and g.c[b] <= g.o[a] and g.body[b] > g.body[a]):
        return None
    ok, ctx, notes = _context_block(closes, a, p, want="up")
    if not ok:
        return None
    measurements = {
        "first": _bar_measure(g, a),
        "second": _bar_measure(g, b),
        "open2_minus_close1": float(g.o[b] - g.c[a]),
        "close2_minus_open1": float(g.c[b] - g.o[a]),
        "body2_minus_body1": float(g.body[b] - g.body[a]),
    }
    return _emit("bearish_engulfing", "bearish", i, measurements, ctx, notes)


def _detect_harami(i: int, g: _Geometry, p: PatternParams, closes: np.ndarray) -> Pattern | None:
    a, b = i - 1, i
    if not _positive_range(g, a, b):
        return None
    first_dir = int(g.direction[a])
    if first_dir == 0:
        return None
    want = "down" if first_dir == -1 else "up"
    if g.body_ratio[a] < p.harami_min_first_body_ratio:
        return None
    bot1, top1 = min(g.o[a], g.c[a]), max(g.o[a], g.c[a])
    bot2, top2 = min(g.o[b], g.c[b]), max(g.o[b], g.c[b])
    if not (bot2 >= bot1 and top2 <= top1 and g.body[b] < g.body[a]):
        return None
    ok, ctx, notes = _context_block(closes, a, p, want=want)
    if not ok:
        return None
    measurements = {
        "first": _bar_measure(g, a),
        "second": _bar_measure(g, b),
        "body1_minus_body2": float(g.body[a] - g.body[b]),
        "containment_margin_low": float(bot2 - bot1),
        "containment_margin_high": float(top1 - top2),
    }
    direction = "bullish" if first_dir == -1 else "bearish"
    return _emit("harami", direction, i, measurements, ctx, notes)


def _detect_harami_cross(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    """A harami whose second candle is a doji (open ≈ close).

    Same containment rule as ``harami``, but the second real body is a doji, so
    the two-candle "cross" form is reported distinctly rather than merged with
    an ordinary harami.
    """
    a, b = i - 1, i
    if not _positive_range(g, a, b):
        return None
    first_dir = int(g.direction[a])
    if first_dir == 0:
        return None
    if g.body_ratio[a] < p.harami_min_first_body_ratio:
        return None
    # second candle must itself be a doji by the module's doji rule
    if g.body_ratio[b] > p.doji_max_body_ratio:
        return None
    bot1, top1 = min(g.o[a], g.c[a]), max(g.o[a], g.c[a])
    bot2, top2 = min(g.o[b], g.c[b]), max(g.o[b], g.c[b])
    if not (bot2 >= bot1 and top2 <= top1):
        return None
    want = "down" if first_dir == -1 else "up"
    ok, ctx, notes = _context_block(closes, a, p, want=want)
    if not ok:
        return None
    measurements = {
        "first": _bar_measure(g, a),
        "second": _bar_measure(g, b),
        "second_body_ratio": float(g.body_ratio[b]),
        "containment_margin_low": float(bot2 - bot1),
        "containment_margin_high": float(top1 - top2),
    }
    direction = "bullish" if first_dir == -1 else "bearish"
    return _emit("harami_cross", direction, i, measurements, ctx, notes)


def _tweezer_pair_ok(g: _Geometry, a: int, b: int, leg: str, p: PatternParams) -> float | None:
    """Return the relative gap between two matching lows/highs, or None if unmatched."""
    v1, v2 = (g.lo[a], g.lo[b]) if leg == "low" else (g.h[a], g.h[b])
    mean = (float(v1) + float(v2)) / 2.0
    if mean <= 0.0:
        return None
    gap = abs(float(v1) - float(v2)) / mean
    return gap if gap <= p.tweezer_tolerance_ratio else None


def _detect_tweezer_bottom(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    """Bearish candle then bullish candle with near-equal lows, in a downtrend."""
    a, b = i - 1, i
    if not _positive_range(g, a, b):
        return None
    if g.direction[a] != -1 or g.direction[b] != 1:
        return None
    gap = _tweezer_pair_ok(g, a, b, "low", p)
    if gap is None:
        return None
    ok, ctx, notes = _context_block(closes, a, p, want="down")
    if not ok:
        return None
    measurements = {
        "first": _bar_measure(g, a),
        "second": _bar_measure(g, b),
        "low_gap_ratio": gap,
        "tolerance_ratio": float(p.tweezer_tolerance_ratio),
    }
    return _emit("tweezer_bottom", "bullish", i, measurements, ctx, notes)


def _detect_tweezer_top(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    """Bullish candle then bearish candle with near-equal highs, in an uptrend."""
    a, b = i - 1, i
    if not _positive_range(g, a, b):
        return None
    if g.direction[a] != 1 or g.direction[b] != -1:
        return None
    gap = _tweezer_pair_ok(g, a, b, "high", p)
    if gap is None:
        return None
    ok, ctx, notes = _context_block(closes, a, p, want="up")
    if not ok:
        return None
    measurements = {
        "first": _bar_measure(g, a),
        "second": _bar_measure(g, b),
        "high_gap_ratio": gap,
        "tolerance_ratio": float(p.tweezer_tolerance_ratio),
    }
    return _emit("tweezer_top", "bearish", i, measurements, ctx, notes)


def _detect_piercing_pattern(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    a, b = i - 1, i
    if not _positive_range(g, a, b):
        return None
    if g.direction[a] != -1 or g.direction[b] != 1:
        return None
    midpoint = (g.o[a] + g.c[a]) / 2.0
    if not (g.o[b] < g.c[a] and g.c[b] > midpoint and g.c[b] < g.o[a]):
        return None
    ok, ctx, notes = _context_block(closes, a, p, want="down")
    if not ok:
        return None
    measurements = {
        "first": _bar_measure(g, a),
        "second": _bar_measure(g, b),
        "first_body_midpoint": float(midpoint),
        "open2_minus_close1": float(g.o[b] - g.c[a]),
        "close2_minus_midpoint": float(g.c[b] - midpoint),
        "close2_minus_open1": float(g.c[b] - g.o[a]),
    }
    return _emit("piercing_pattern", "bullish", i, measurements, ctx, notes)


def _detect_dark_cloud_cover(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    a, b = i - 1, i
    if not _positive_range(g, a, b):
        return None
    if g.direction[a] != 1 or g.direction[b] != -1:
        return None
    midpoint = (g.o[a] + g.c[a]) / 2.0
    if not (g.o[b] > g.c[a] and g.c[b] < midpoint and g.c[b] > g.o[a]):
        return None
    ok, ctx, notes = _context_block(closes, a, p, want="up")
    if not ok:
        return None
    measurements = {
        "first": _bar_measure(g, a),
        "second": _bar_measure(g, b),
        "first_body_midpoint": float(midpoint),
        "open2_minus_close1": float(g.o[b] - g.c[a]),
        "close2_minus_midpoint": float(g.c[b] - midpoint),
        "close2_minus_open1": float(g.c[b] - g.o[a]),
    }
    return _emit("dark_cloud_cover", "bearish", i, measurements, ctx, notes)


# three-candle -------------------------------------------------------------
def _detect_morning_star(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    x, y, z = i - 2, i - 1, i
    if not _positive_range(g, x, y, z):
        return None
    if g.direction[x] != -1 or g.direction[z] != 1:
        return None
    if g.body_ratio[x] < p.star_min_first_body_ratio:
        return None
    if g.body_ratio[y] > p.star_max_middle_body_ratio:
        return None
    if not (g.o[y] < g.c[x] and g.c[z] > (g.o[x] + g.c[x]) / 2.0):
        return None
    ok, ctx, notes = _context_block(closes, x, p, want="down")
    if not ok:
        return None
    midpoint = (g.o[x] + g.c[x]) / 2.0
    measurements = {
        "first": _bar_measure(g, x),
        "second": _bar_measure(g, y),
        "third": _bar_measure(g, z),
        "first_body_midpoint": float(midpoint),
        "open2_minus_close1": float(g.o[y] - g.c[x]),
        "close3_minus_midpoint": float(g.c[z] - midpoint),
    }
    return _emit("morning_star", "bullish", i, measurements, ctx, notes)


def _detect_evening_star(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    x, y, z = i - 2, i - 1, i
    if not _positive_range(g, x, y, z):
        return None
    if g.direction[x] != 1 or g.direction[z] != -1:
        return None
    if g.body_ratio[x] < p.star_min_first_body_ratio:
        return None
    if g.body_ratio[y] > p.star_max_middle_body_ratio:
        return None
    if not (g.o[y] > g.c[x] and g.c[z] < (g.o[x] + g.c[x]) / 2.0):
        return None
    ok, ctx, notes = _context_block(closes, x, p, want="up")
    if not ok:
        return None
    midpoint = (g.o[x] + g.c[x]) / 2.0
    measurements = {
        "first": _bar_measure(g, x),
        "second": _bar_measure(g, y),
        "third": _bar_measure(g, z),
        "first_body_midpoint": float(midpoint),
        "open2_minus_close1": float(g.o[y] - g.c[x]),
        "close3_minus_midpoint": float(g.c[z] - midpoint),
    }
    return _emit("evening_star", "bearish", i, measurements, ctx, notes)


def _detect_three_white_soldiers(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    x, y, z = i - 2, i - 1, i
    if not _positive_range(g, x, y, z):
        return None
    if not (g.direction[x] == 1 and g.direction[y] == 1 and g.direction[z] == 1):
        return None
    if not (g.c[x] < g.c[y] and g.c[y] < g.c[z]):
        return None
    if not (g.o[y] >= g.o[x] and g.o[y] <= g.c[x]):
        return None
    if not (g.o[z] >= g.o[y] and g.o[z] <= g.c[y]):
        return None
    if min(g.body_ratio[x], g.body_ratio[y], g.body_ratio[z]) < p.soldiers_min_body_ratio:
        return None
    ok, ctx, notes = _context_block(closes, x, p, want="down")
    if not ok:
        return None
    measurements = {
        "first": _bar_measure(g, x),
        "second": _bar_measure(g, y),
        "third": _bar_measure(g, z),
        "close2_minus_close1": float(g.c[y] - g.c[x]),
        "close3_minus_close2": float(g.c[z] - g.c[y]),
        "open2_minus_open1": float(g.o[y] - g.o[x]),
        "open3_minus_open2": float(g.o[z] - g.o[y]),
    }
    return _emit("three_white_soldiers", "bullish", i, measurements, ctx, notes)


def _detect_three_black_crows(
    i: int, g: _Geometry, p: PatternParams, closes: np.ndarray
) -> Pattern | None:
    x, y, z = i - 2, i - 1, i
    if not _positive_range(g, x, y, z):
        return None
    if not (g.direction[x] == -1 and g.direction[y] == -1 and g.direction[z] == -1):
        return None
    if not (g.c[x] > g.c[y] and g.c[y] > g.c[z]):
        return None
    if not (g.o[y] <= g.o[x] and g.o[y] >= g.c[x]):
        return None
    if not (g.o[z] <= g.o[y] and g.o[z] >= g.c[y]):
        return None
    if min(g.body_ratio[x], g.body_ratio[y], g.body_ratio[z]) < p.soldiers_min_body_ratio:
        return None
    ok, ctx, notes = _context_block(closes, x, p, want="up")
    if not ok:
        return None
    measurements = {
        "first": _bar_measure(g, x),
        "second": _bar_measure(g, y),
        "third": _bar_measure(g, z),
        "close2_minus_close1": float(g.c[y] - g.c[x]),
        "close3_minus_close2": float(g.c[z] - g.c[y]),
        "open2_minus_open1": float(g.o[y] - g.o[x]),
        "open3_minus_open2": float(g.o[z] - g.o[y]),
    }
    return _emit("three_black_crows", "bearish", i, measurements, ctx, notes)


# Detection order within a bar: singles, then two-candle, then three-candle.
_SINGLE_DETECTORS = (
    _detect_doji,
    _detect_hammer,
    _detect_inverted_hammer,
    _detect_shooting_star,
    _detect_spinning_top,
    _detect_marubozu,
)
_TWO_DETECTORS = (
    _detect_bullish_engulfing,
    _detect_bearish_engulfing,
    _detect_harami,
    _detect_harami_cross,
    _detect_piercing_pattern,
    _detect_dark_cloud_cover,
    _detect_tweezer_bottom,
    _detect_tweezer_top,
)
_THREE_DETECTORS = (
    _detect_morning_star,
    _detect_evening_star,
    _detect_three_white_soldiers,
    _detect_three_black_crows,
)


# -------------------------------------------------------------------- public
def detect_patterns(
    open_: Any,
    high: Any,
    low: Any,
    close: Any,
    params: PatternParams | dict[str, Any] | None = None,
    dates: Any = None,
) -> list[Pattern]:
    """Detect candlestick patterns in OHLC arrays.

    Parameters
    ----------
    open_, high, low, close
        1-D numeric arrays (oldest to newest), same length, finite values.
    params
        ``PatternParams``, a dict of overrides, or ``None`` for defaults.
        Unknown keys and out-of-range values raise :class:`CandleError`.
    dates
        Optional per-bar date labels (same length). When given, each
        pattern's ``date`` is filled from ``dates[pattern.index]``.

    Returns
    -------
    list[Pattern]
        Detected candidates ordered by completion index; within a bar the
        order is single-candle patterns (doji, hammer, inverted hammer,
        shooting star, spinning top, marubozu), then two-candle, then
        three-candle. Each entry is labelled ``classification="DETECTED"``
        — a candidate found by the documented rules, not a prediction.

    Raises
    ------
    CandleError
        Invalid parameters, non-finite or invalid OHLC data, mismatched
        lengths, empty input, or fewer than ``MIN_BARS`` bars.

    Notes
    -----
    A pattern at index ``i`` uses only bars ``[0..i]`` (causality — proven
    by test). Zero-range bars are excluded from candidacy. Patterns whose
    required prior-trend context cannot be evaluated are skipped rather than
    reported without context. No confirmation rule is implemented:
    ``confirmed`` is ``None`` for every result.
    """
    p = _resolve_params(params)
    o, h, lo, c = validate_ohlc(open_, high, low, close, min_bars=MIN_BARS)
    n = int(o.size)

    date_list: list[str] | None = None
    if dates is not None:
        date_list = [str(d) for d in np.asarray(dates, dtype=object).reshape(-1)]
        if len(date_list) != n:
            raise CandleError(
                f"`dates` must have one entry per bar; got {len(date_list)} dates for {n} bars"
            )

    g = _geometry(o, h, lo, c)
    out: list[Pattern] = []
    for i in range(n):
        for fn in _SINGLE_DETECTORS:
            pat = fn(i, g, p, c)
            if pat is not None:
                out.append(pat)
        if i >= 1:
            for fn in _TWO_DETECTORS:
                pat = fn(i, g, p, c)
                if pat is not None:
                    out.append(pat)
        if i >= 2:
            for fn in _THREE_DETECTORS:
                pat = fn(i, g, p, c)
                if pat is not None:
                    out.append(pat)
    if date_list is not None:
        for pat in out:
            pat.date = date_list[pat.index]
    return out


def _round_nested(value: Any, digits: int = 6) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (float, np.floating)):
        return round(float(value), digits)
    if isinstance(value, dict):
        return {k: _round_nested(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round_nested(v, digits) for v in value]
    return value
