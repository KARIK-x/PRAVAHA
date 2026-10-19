"""Explainable trend / momentum / volatility summary built from verified indicators.

Provenance labels
-----------------
* Numbers produced by the indicator engines (``megatool.ta.trend``,
  ``momentum``, ``volatility``, ``volume``, ``core``) are **CALCULATED**.
* Structural labels (swing structure) and the swing list come from
  ``megatool.ta.swings`` and are **DETECTED** by its explicit rules.
* Trend-direction labels (``up`` / ``down`` / ``flat``), trend strength,
  momentum zones (``overbought`` / ``oversold`` / ``neutral``), the
  volatility regime, the MACD flip label and the divergence label are
  **DETECTED** by the documented thresholds below.
* The combined ``interpretation`` paragraph and the ``supporting`` /
  ``conflicting`` / ``ambiguous`` / ``missing`` breakdowns are
  **INTERPRETIVE**: they only place the detected values side by side.

No element of this module produces a probability or rating, and no element
produces a trading recommendation: the ``disclaimer`` field says so in plain
words.  Volatility, ATR and dispersion measures are risk context, not trade
signals.

Data policy
-----------
Every output of :func:`build_summary` is computed strictly from the arrays it
is given; the arrays end at the reported ``last_index``, so no future bar can
be read.  :func:`candidate_divergence` accepts an explicit ``last_index`` and
never reads swing or indicator values beyond it (tested by a prefix test).
Nothing is written to any database; callers pass series in and receive
dataclasses out.

Validation
----------
``SummaryError`` (a ``ValueError`` subclass) is raised for invalid input:
length mismatches, non-finite values, non-positive prices, invalid OHLC
relationships (via ``candles.validate_ohlc``), insufficient history, and
invalid parameters.

Not evaluated (always ``None`` / ``"not evaluated"``)
-----------------------------------------------------
* ``near_support``: the numeric proximity rule (distance from the last price
  to the nearest swing low as a percentage of price) is **not evaluated** by
  this module, so it is always ``None``.  Price-swing structure itself is
  still reported (``structure`` and the support/resistance levels).
* Divergence ``confirmed``: no confirmation rule (close beyond the swing
  level, holding for N bars, volume confirmation, ...) is implemented here,
  so every divergence candidate carries ``confirmed = None`` and
  ``status = "not evaluated"``, and its ``caveat`` states that no
  confirmation rule, no ``near_support`` evaluation and no prior-trend
  context were applied.
* Prior-trend context for divergence candidates: not required.  A candidate
  is reported whenever a qualifying swing pair and an indicator extreme
  coexist; whether the leg into the swing was itself a trend is not asserted.

Prior-trend rule (documented, explicit)
---------------------------------------
``trend`` reports the net close-to-close change over the short, intermediate
and long windows (``trend_short`` / ``trend_intermediate`` / ``trend_long``
bars, ending at the last bar: ``change_pct = 100 * (close[-1] - close[-1-w]) /
close[-1-w]``).  Each horizon is classified with the same rule:

* ``up`` when ``change_pct > flat_threshold_pct`` (strict),
* ``down`` when ``change_pct < -flat_threshold_pct`` (strict),
* ``flat`` otherwise (an exact tie with the threshold is ``flat``),
* ``None`` when the series is shorter than ``window + 1`` bars — reported as
  ``status = "insufficient_history"`` for the primary horizon; the series is
  never padded, extrapolated or back-filled.

Combined-direction rule (documented, explicit)
----------------------------------------------
``interpretation.trend_direction`` equals the **intermediate** horizon
classified by the rule above.  The intermediate window is the documented
primary horizon of this summary: short windows are dominated by noise, long
windows lag the current regime.  The short and long classifications are
reported next to it so a reader can see when horizons disagree — disagreement
is surfaced, never averaged away.  No weight or score is involved.

Trend-strength rule (documented, explicit)
------------------------------------------
``trend.strength`` derives **only** from ADX (``adx_period``):

* ``"not available"`` when ADX has no finite value (short series, or a
  degenerate series such as constant prices where DX is 0/0),
* ``"weak"`` when ``ADX < adx_developing`` (default 20),
* ``"developing"`` when ``adx_developing <= ADX < adx_strong`` (default 20..25),
* ``"strong"`` when ``ADX >= adx_strong`` (default 25).

Thresholds are configurable via :class:`SummaryParams`.  ``strength``
describes trend integrity as ADX measures it; it is not a rating.

Units
-----
* Prices, ``sma`` values, ``atr``, MACD lines: price units of the input.
* ``slope_per_bar``: price units per bar.
* ``change_pct``, ``roc_pct``, ``rsi``, ``stoch_k/d``, ``mfi``,
  ``bandwidth_pct``, ``bandwidth_rolling_stdev_pct``,
  ``rolling_stddev_pct_per_bar``, ``atr_pct``: percent on the named base
  (``12.5`` means 12.5 %; ``rolling_stddev_pct_per_bar`` is percent per bar,
  sample stdev ``ddof=1``, **not** annualised).
* ``historical_volatility_pct_annual``: annualised percent
  (``stdev(log return) * sqrt(hv_trading_days) * 100``).
* ``relative_volume``: multiple of the trailing baseline mean (2.0 = twice
  the recent average volume).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, fields
from typing import Any

import numpy as np

from megatool.ta import core, momentum, volatility
from megatool.ta import trend as trend_mod
from megatool.ta import volume as volume_mod
from megatool.ta.candles import CandleError, validate_ohlc
from megatool.ta.swings import Swing, classify_structure, find_swings

__all__ = [
    "SUMMARY_RULE_VERSION",
    "MIN_BARS",
    "SummaryError",
    "SummaryParams",
    "TrendView",
    "MomentumView",
    "VolatilityView",
    "VolumeView",
    "StructureView",
    "InterpretationView",
    "SummaryResult",
    "build_summary",
    "candidate_divergence",
]

#: Bumped when the documented rules in this module change; stored with results.
SUMMARY_RULE_VERSION = "summary-1.0"

#: Fewest bars ``build_summary`` accepts (a net change needs 2 bars).
MIN_BARS = 2


class SummaryError(ValueError):
    """Raised when OHLCV input or parameters are invalid for the summary."""


@dataclass(frozen=True)
class SummaryParams:
    """Configurable windows and thresholds; every default is documented here.

    Threshold fields (``flat_threshold_pct``, ``adx_strong``, ...) are
    classification cutoffs, not scores.  Validation rules: integer windows
    must be ``>= 1`` (``atr_period`` may be ``0`` to disable ATR),
    ``macd_fast < macd_slow``, ``flat_threshold_pct >= 0``, ADX thresholds
    non-negative with ``adx_developing <= adx_strong``, RSI/MFI zones must
    satisfy ``0 <= oversold < overbought <= 100``, ``bollinger_deviation >= 0``
    (``0`` disables bandwidth), and ``timeframe`` must be non-empty.
    """

    # --- trend horizons / classification
    trend_short: int = 20  # bars for the short-horizon net change.
    trend_intermediate: int = 60  # bars for the intermediate (primary) horizon.
    trend_long: int = 120  # bars for the long-horizon net change.
    flat_threshold_pct: float = 0.5  # |change_pct| <= this classifies "flat".
    sma_short: int = 10  # fast moving average.
    sma_long: int = 30  # slow moving average.
    slope_window: int = 30  # bars of the fast-SMA slope fit.
    adx_period: int = 14  # ADX / DI period.
    adx_strong: float = 25.0  # ADX >= this -> strength "strong".
    adx_developing: float = 20.0  # ADX >= this -> strength "developing".
    # --- structure (price swings feeding divergence candidates)
    swing_left: int = 5  # left bars of the swing fractal.
    swing_right: int = 5  # right bars of the swing fractal.
    # --- momentum indicators
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    roc_period: int = 12
    stoch_k: int = 14  # %K lookback.
    stoch_d: int = 3  # %D smoothing.
    stoch_smooth: int = 3  # raw-%K smoothing (slow stochastic).
    rsi_overbought: float = 70.0  # RSI >= this -> "overbought".
    rsi_oversold: float = 30.0  # RSI <= this -> "oversold".
    # --- volatility
    atr_period: int = 14  # Wilder ATR; 0 disables the ATR fields.
    hv_period: int = 20  # log-return window for historical vol.
    hv_trading_days: int = 250  # annualisation factor (square root).
    return_window: int = 20  # window of the rolling return stdev (%/bar).
    bollinger_period: int = 20  # middle-band window.
    bollinger_deviation: float = 2.0  # stddev multiplier; 0 disables bandwidth.
    # --- volume
    mfi_period: int = 14
    mfi_overbought: float = 80.0  # MFI >= this -> "overbought".
    mfi_oversold: float = 20.0  # MFI <= this -> "oversold".
    rvol_baseline: int = 20  # baseline bars for relative volume.
    # --- metadata
    timeframe: str = "unspecified"  # echoed into the result; not a prediction.

    def __post_init__(self) -> None:
        int_fields = (
            "trend_short",
            "trend_intermediate",
            "trend_long",
            "sma_short",
            "sma_long",
            "slope_window",
            "adx_period",
            "swing_left",
            "swing_right",
            "rsi_period",
            "macd_fast",
            "macd_slow",
            "macd_signal",
            "roc_period",
            "stoch_k",
            "stoch_d",
            "stoch_smooth",
            "atr_period",
            "hv_period",
            "hv_trading_days",
            "return_window",
            "bollinger_period",
            "mfi_period",
            "rvol_baseline",
        )
        for name in int_fields:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise SummaryError(f"{name} must be a non-negative int, got {value!r}")
        for name in int_fields:
            if name == "atr_period":
                continue  # 0 means "disabled by configuration".
            if getattr(self, name) < 1:
                raise SummaryError(f"{name} must be >= 1, got {getattr(self, name)!r}")
        float_fields = (
            "flat_threshold_pct",
            "adx_strong",
            "adx_developing",
            "rsi_overbought",
            "rsi_oversold",
            "bollinger_deviation",
            "mfi_overbought",
            "mfi_oversold",
        )
        for name in float_fields:
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise SummaryError(f"{name} must be a number, got {value!r}")
            if not math.isfinite(float(value)):
                raise SummaryError(f"{name} must be finite, got {value!r}")
            object.__setattr__(self, name, float(value))
        if self.macd_fast >= self.macd_slow:
            raise SummaryError("macd_fast must be < macd_slow")
        if self.flat_threshold_pct < 0:
            raise SummaryError("flat_threshold_pct must be >= 0")
        if self.adx_strong < 0 or self.adx_developing < 0:
            raise SummaryError("ADX thresholds must be >= 0")
        if self.adx_developing > self.adx_strong:
            raise SummaryError("adx_developing must be <= adx_strong")
        if not 0 <= self.rsi_oversold < self.rsi_overbought <= 100:
            raise SummaryError("need 0 <= rsi_oversold < rsi_overbought <= 100")
        if not 0 <= self.mfi_oversold < self.mfi_overbought <= 100:
            raise SummaryError("need 0 <= mfi_oversold < mfi_overbought <= 100")
        if self.bollinger_deviation < 0:
            raise SummaryError("bollinger_deviation must be >= 0")
        if not isinstance(self.timeframe, str) or self.timeframe == "":
            raise SummaryError("timeframe must be a non-empty string")


# ------------------------------------------------------------------ result views
@dataclass
class TrendView:
    """CALCULATED trend numbers plus DETECTED direction/strength labels."""

    label: str = "CALCULATED"
    classification_label: str = "DETECTED"
    short_change_pct: float | None = None
    short_direction: str | None = None  # DETECTED: up / down / flat.
    intermediate_change_pct: float | None = None
    intermediate_direction: str | None = None  # primary horizon of the summary.
    long_change_pct: float | None = None
    long_direction: str | None = None
    sma_short: float | None = None
    sma_long: float | None = None
    price_vs_sma_short_pct: float | None = None
    price_vs_sma_long_pct: float | None = None
    sma_short_vs_sma_long_pct: float | None = None  # (short - long)/long * 100.
    sma_slope_per_bar: float | None = None  # slope of the fast SMA.
    adx: float | None = None
    plus_di: float | None = None
    minus_di: float | None = None
    strength: str | None = None  # DETECTED: weak / developing / strong / not available.
    status: str = "ok"  # ok / insufficient_history (primary horizon).


@dataclass
class MomentumView:
    """CALCULATED oscillator values plus DETECTED threshold labels."""

    label: str = "CALCULATED"
    classification_label: str = "DETECTED"
    rsi: float | None = None
    rsi_zone: str | None = None  # DETECTED: overbought / oversold / neutral.
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    macd_cross: str | None = None  # DETECTED: bullish/bearish flip, none, not_available.
    roc_pct: float | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None
    status: str = "ok"


@dataclass
class VolatilityView:
    """CALCULATED dispersion numbers; ``regime`` is a DETECTED label."""

    label: str = "CALCULATED"
    classification_label: str = "DETECTED"
    atr: float | None = None  # price units.
    atr_pct: float | None = None  # 100 * ATR / close.
    historical_volatility_pct_annual: float | None = None
    rolling_stddev_pct_per_bar: float | None = None  # ddof=1, not annualised.
    bandwidth_pct: float | None = None  # 100 * (upper - lower)/middle.
    bandwidth_rolling_stdev_pct: float | None = None  # stdev of bandwidth_pct.
    regime: str | None = None  # DETECTED: expanding / contracting / stable.
    status: str = "ok"


@dataclass
class VolumeView:
    """CALCULATED volume statistics (absolute volume levels are not interpreted)."""

    label: str = "CALCULATED"
    classification_label: str = "DETECTED"
    mfi: float | None = None
    mfi_zone: str | None = None  # DETECTED: overbought / oversold / neutral.
    latest_volume: float | None = None
    volume_sma: float | None = None  # mean over the relative-volume baseline.
    relative_volume: float | None = None  # multiple of the baseline mean.
    status: str = "ok"


@dataclass
class StructureView:
    """DETECTED price-swing structure (megatool.ta.swings rules)."""

    label: str = "DETECTED"
    structure: str | None = None  # up / down / mixed / insufficient data.
    near_support: bool | None = None  # always None: not evaluated (see module doc).
    support_level: float | None = None  # last swing low price (if any).
    resistance_level: float | None = None  # last swing high price (if any).
    swing_count: int = 0
    status: str = "ok"


@dataclass
class InterpretationView:
    """INTERPRETIVE aggregation of the DETECTED / CALCULATED views."""

    label: str = "INTERPRETIVE"
    trend_direction: str | None = None  # intermediate-horizon rule (documented).
    trend_strength: str | None = None  # ADX bands only (documented).
    momentum_state: str | None = None  # RSI zone, or "not_available".
    volatility_regime: str | None = None
    supporting: list[str] = field(default_factory=list)
    conflicting: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    narrative: str = ""
    disclaimer: str = (
        "Interpretive summary of documented rules; no probability or rating "
        "is produced and no trading recommendation is implied."
    )


@dataclass
class SummaryResult:
    """Complete summary payload.  Deterministic given the same inputs and params."""

    rule_version: str
    generated_from: str
    last_index: int
    last_time: str | None
    timeframe: str
    trend: TrendView
    momentum: MomentumView
    volatility: VolatilityView
    volume_stats: VolumeView
    structure: StructureView
    interpretation: InterpretationView
    divergence_candidates: list[dict[str, Any]]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly dict: non-finite floats become ``None``."""
        return _jsonable(asdict(self))


# ------------------------------------------------------------------ helpers
def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def _resolve_params(params: SummaryParams | dict[str, Any] | None) -> SummaryParams:
    """Merge a dict of overrides onto the defaults; validate every field."""
    if params is None:
        return SummaryParams()
    if isinstance(params, SummaryParams):
        return params
    if isinstance(params, dict):
        known = {f.name for f in fields(SummaryParams)}
        unknown = set(params) - known
        if unknown:
            raise SummaryError(f"unknown parameter(s) {sorted(unknown)}; declared {sorted(known)}")
        return SummaryParams(**{**asdict(SummaryParams()), **params})
    raise SummaryError(
        f"params must be a SummaryParams, a dict, or None; got {type(params).__name__}"
    )


def _validated_inputs(
    open_: Any, high: Any, low: Any, close: Any, volume: Any, dates: Any
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None, Any]:
    """Validate OHLC via candles.validate_ohlc, then apply summary rules."""
    try:
        o, h, lo, c = validate_ohlc(open_, high, low, close, min_bars=MIN_BARS)
    except CandleError as exc:
        raise SummaryError(str(exc)) from None
    if np.any(lo <= 0):
        raise SummaryError(
            "summary requires strictly positive prices (log returns and "
            "percentage bases are undefined for low <= 0)"
        )
    v: np.ndarray | None = None
    if volume is not None:
        try:
            v = np.asarray(volume, dtype=float)
        except (TypeError, ValueError) as exc:
            raise SummaryError(f"`volume` could not be read as numbers: {exc}") from exc
        if v.ndim != 1 or v.size != c.size:
            raise SummaryError(
                f"volume must be one-dimensional and the same length as close "
                f"({c.size}), got shape {v.shape}"
            )
        if not np.all(np.isfinite(v)):
            raise SummaryError("volume must contain only finite values (NaN or inf found)")
        if np.any(v < 0):
            raise SummaryError("volume must be non-negative")
    if dates is not None:
        d = list(dates)
        if len(d) != c.size:
            raise SummaryError(f"dates must be the same length as close ({c.size}), got {len(d)}")
    else:
        d = None
    return o, h, lo, c, v, d


def _last_finite(values: Any) -> float | None:
    """Last finite value of a series, or ``None`` when it is all warm-up NaN."""
    for value in reversed(list(values)):
        v = float(value)
        if math.isfinite(v):
            return v
    return None


def _net_change_pct(close: np.ndarray, window: int) -> float | None:
    """Net close-to-close change (percent) over ``window`` bars, ending last."""
    n = close.size
    if window < 1 or n <= window:
        return None
    start = float(close[n - window - 1])
    if start == 0:
        return None
    return (float(close[-1]) - start) / start * 100.0


def _direction(change_pct: float | None, flat_threshold_pct: float) -> str | None:
    """Documented classification: strict thresholds, exact ties are flat."""
    if change_pct is None:
        return None
    if change_pct > flat_threshold_pct:
        return "up"
    if change_pct < -flat_threshold_pct:
        return "down"
    return "flat"


def _flip_label(a: Any, b: Any) -> str:
    """DETECTED label of the flip between two lines at the newest defined bar.

    ``"bullish_cross"`` / ``"bearish_cross"`` when ``a`` crosses ``b`` at the
    newest bar where all four values (t and t-1 of both lines) are finite;
    ``"none"`` when no flip happens there; ``"not_available"`` when the pair is
    never jointly defined (insufficient history).
    """
    n = len(a)
    for i in range(n - 1, 0, -1):
        vals = (a[i], b[i], a[i - 1], b[i - 1])
        if not all(math.isfinite(float(x)) for x in vals):
            continue
        cur_a, cur_b, prev_a, prev_b = (float(x) for x in vals)
        if cur_a > cur_b and prev_a <= prev_b:
            return "bullish_cross"
        if cur_a < cur_b and prev_a >= prev_b:
            return "bearish_cross"
        return "none"
    return "not_available"


def _rolling_sd_last(values: np.ndarray, window: int) -> float | None:
    """Last value of the trailing sample stdev (ddof=1) over ``window`` points.

    Warm-up NaNs at the head are dropped first, so the window shrinks to the
    real amount of available data instead of being back-filled.
    """
    finite = values[np.isfinite(values)]
    w = min(window, int(finite.size))
    if w < 2:
        return None
    sd = core.rolling_std(finite, w, ddof=1)[-1]
    return float(sd) if np.isfinite(sd) else None


# ------------------------------------------------------------------ divergence
_HIGHER_HIGH = "higher_high"
_LOWER_LOW = "lower_low"


def _swing_pairs(
    swings: Sequence[Swing],
    kind: str,
    last_index: int,
    max_lookback: int,
    min_move_pct: float,
) -> list[tuple[Swing, Swing]]:
    """Select consecutive same-kind swing pairs for divergence screening.

    * only swings of ``kind`` ending at or before ``last_index`` are used;
    * only the most recent ``max_lookback + 1`` swings of that kind are
      examined (bounded work); pairs among older swings are ignored;
    * the price leg between the pair must move at least ``min_move_pct``
      (percent of the earlier price), so a flat drift is not screened;
    * pairs are consecutive in the same-kind subsequence: with the alternating
      swing list that means "two successive highs" or "two successive lows".
    """
    same = [s for s in swings if s.kind == kind and s.index <= last_index]
    start = max(0, len(same) - (max_lookback + 1))
    pairs: list[tuple[Swing, Swing]] = []
    for i in range(start, len(same) - 1):
        a, b = same[i], same[i + 1]
        if a.price == 0:
            continue
        move_pct = abs(b.price - a.price) / abs(a.price) * 100.0
        if move_pct < min_move_pct:
            continue
        pairs.append((a, b))
    return pairs


def candidate_divergence(
    swings: Sequence[Swing],
    indicator: Sequence[float | None],
    *,
    indicator_name: str = "",
    last_index: int | None = None,
    min_move_pct: float = 0.0,
    max_lookback: int = 5,
) -> list[dict[str, Any]]:
    """Screen for divergence candidates between price swings and an indicator.

    This is a **candidate** screen, not a validated signal: it reports where a
    price swing extreme coincides with an indicator extreme moving the other
    way.  Every result carries ``label = "CANDIDATE"`` and
    ``classification = "DETECTED"`` (the rules below fired).  No probability,
    rating or trading recommendation follows from a candidate.

    Rules (documented, deterministic, causal)
    ------------------------------------------
    * A ``"bearish"`` candidate needs two consecutive **swing highs** at
      indices ``h1 < h2 <= last_index`` with ``h2.price > h1.price`` (price
      makes a higher high) while ``indicator[h2] < indicator[h1]`` (the
      indicator fails to confirm).
    * A ``"bullish"`` candidate needs two consecutive **swing lows** with
      ``l2.price < l1.price`` (lower low) while ``indicator[l2] > indicator[l1]``
      (higher indicator low).
    * Strict inequalities throughout: exact ties are **not** reported.
    * Both swings must end at or before ``last_index`` and both indicator
      values must be non-``None`` (finite); otherwise the pair is skipped.
    * ``min_move_pct`` (default ``0.0``) drops pairs whose price leg moves
      less than that percentage of the earlier price.  ``max_lookback``
      (default ``5``) bounds the screen to the most recent ``max_lookback + 1``
      swings of each kind; older pairs are ignored.
    * The ``caveat`` of every candidate states that no prior-trend context,
      no ``near_support`` evaluation and no confirmation rule was applied
      (``confirmed`` is always ``None`` with ``status = "not evaluated"``).

    Returned dicts contain: ``indicator``, ``classification``, ``label``,
    ``direction``, ``price_pattern``, ``indicator_pattern``, ``price_index``,
    ``indicator_index``, ``price_move``, ``indicator_move``,
    ``indicator_value_at_index``, ``confirmed``, ``status``, ``caveat``.

    Parameters
    ----------
    swings:
        Swing list, e.g. from ``megatool.ta.swings.find_swings``.
    indicator:
        Per-bar values of any indicator series (``None`` = not available).
    indicator_name:
        Name echoed into each candidate (e.g. ``"rsi"``).
    last_index:
        Last bar index allowed to be read; defaults to ``len(indicator) - 1``.
        Nothing at an index > ``last_index`` is ever read or reported.
    """
    n = len(indicator)
    if n == 0:
        raise SummaryError("indicator series must be non-empty")
    if last_index is None:
        last_index = n - 1
    if not isinstance(last_index, int) or isinstance(last_index, bool):
        raise SummaryError(f"last_index must be an int, got {last_index!r}")
    if last_index < 0 or last_index >= n:
        raise SummaryError(f"last_index {last_index} out of range for indicator of length {n}")
    if min_move_pct < 0:
        raise SummaryError("min_move_pct must be >= 0")
    if max_lookback < 0:
        raise SummaryError("max_lookback must be >= 0")

    out: list[dict[str, Any]] = []
    screens = (
        # (direction, swing kind, sign that defines a bullish price leg)
        ("bearish", "high", -1),
        ("bullish", "low", 1),
    )
    for direction, swing_kind, price_sign in screens:
        for a, b in _swing_pairs(swings, swing_kind, last_index, max_lookback, min_move_pct):
            if b.index >= n:
                continue
            ind_a, ind_b = indicator[a.index], indicator[b.index]
            if ind_a is None or ind_b is None:
                continue
            if not (math.isfinite(float(ind_a)) and math.isfinite(float(ind_b))):
                continue
            price_delta = float(b.price) - float(a.price)
            ind_delta = float(ind_b) - float(ind_a)
            if price_sign < 0:  # bearish: higher high with a lower indicator
                if not (price_delta > 0 and ind_delta < 0):
                    continue
                price_pattern, indicator_pattern = _HIGHER_HIGH, "lower_high"
            else:  # bullish: lower low with a higher indicator
                if not (price_delta < 0 and ind_delta > 0):
                    continue
                price_pattern, indicator_pattern = _LOWER_LOW, "higher_low"
            out.append(
                {
                    "indicator": indicator_name,
                    "classification": "DETECTED",
                    "label": "CANDIDATE",
                    "direction": direction,
                    "price_pattern": price_pattern,
                    "indicator_pattern": indicator_pattern,
                    "price_index": int(b.index),
                    "indicator_index": int(b.index),
                    "price_move": price_delta,
                    "indicator_move": ind_delta,
                    "indicator_value_at_index": float(ind_b),
                    "confirmed": None,
                    "status": "not evaluated",
                    "caveat": (
                        "Candidate only: no confirmation rule, near_support "
                        "evaluation or prior-trend context applied."
                    ),
                }
            )
    out.sort(key=lambda item: (item["price_index"], item["indicator"]))
    return out


# ------------------------------------------------------------------ view builders
def _build_trend_view(data: dict[str, np.ndarray], c: np.ndarray, p: SummaryParams) -> TrendView:
    view = TrendView()
    n = int(c.size)
    view.short_change_pct = _net_change_pct(c, p.trend_short)
    view.short_direction = _direction(view.short_change_pct, p.flat_threshold_pct)
    view.intermediate_change_pct = _net_change_pct(c, p.trend_intermediate)
    view.intermediate_direction = _direction(view.intermediate_change_pct, p.flat_threshold_pct)
    view.long_change_pct = _net_change_pct(c, p.trend_long)
    view.long_direction = _direction(view.long_change_pct, p.flat_threshold_pct)

    fast = trend_mod.sma(data, p.sma_short).values["sma"]
    slow = trend_mod.sma(data, p.sma_long).values["sma"]
    view.sma_short = _last_finite(fast)
    view.sma_long = _last_finite(slow)
    if view.sma_short is not None and view.sma_short != 0:
        view.price_vs_sma_short_pct = (float(c[-1]) - view.sma_short) / view.sma_short * 100.0
    if view.sma_long is not None and view.sma_long != 0:
        view.price_vs_sma_long_pct = (float(c[-1]) - view.sma_long) / view.sma_long * 100.0
        if view.sma_short is not None:
            view.sma_short_vs_sma_long_pct = (
                (view.sma_short - view.sma_long) / view.sma_long * 100.0
            )

    # Slope of the fast SMA over the newest `slope_window` defined points.
    idx = [i for i in range(n) if math.isfinite(float(fast[i]))]
    if len(idx) >= 2:
        xs = idx[-min(p.slope_window, len(idx)) :]
        ys = [float(fast[i]) for i in xs]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        denom = sum((x - x_mean) ** 2 for x in xs)
        if denom > 0:
            view.sma_slope_per_bar = (
                sum((xs[k] - x_mean) * (ys[k] - y_mean) for k in range(len(xs))) / denom
            )

    adx = trend_mod.adx(data, p.adx_period).values
    view.adx = _last_finite(adx["adx"])
    view.plus_di = _last_finite(adx["plus_di"])
    view.minus_di = _last_finite(adx["minus_di"])
    if view.adx is None:
        view.strength = "not available"
    elif view.adx >= p.adx_strong:
        view.strength = "strong"
    elif view.adx >= p.adx_developing:
        view.strength = "developing"
    else:
        view.strength = "weak"

    # Status refers to the primary (intermediate) horizon of the summary.
    if view.intermediate_change_pct is None:
        view.status = "insufficient_history"
    return view


def _build_momentum_view(
    data: dict[str, np.ndarray], p: SummaryParams, constant_close: bool
) -> MomentumView:
    view = MomentumView()
    rsi = momentum.rsi(data, p.rsi_period).values["rsi"]
    macd = momentum.macd(data, p.macd_fast, p.macd_slow, p.macd_signal).values
    roc = momentum.roc(data, p.roc_period).values["roc"]
    stoch = momentum.stochastic(data, p.stoch_k, p.stoch_d, p.stoch_smooth).values

    if constant_close:
        # The RSI engine maps a 0/0 average gain/loss to 100 (documented engine
        # behaviour, left unchanged): mask it rather than report a misleading
        # overbought zone.  See `limitations`.
        view.rsi = None
        view.rsi_zone = None
    else:
        view.rsi = _last_finite(rsi)
        if view.rsi is not None:
            if view.rsi >= p.rsi_overbought:
                view.rsi_zone = "overbought"
            elif view.rsi <= p.rsi_oversold:
                view.rsi_zone = "oversold"
            else:
                view.rsi_zone = "neutral"
    view.macd = _last_finite(macd["macd"])
    view.macd_signal = _last_finite(macd["signal"])
    view.macd_histogram = _last_finite(macd["histogram"])
    view.macd_cross = _flip_label(macd["macd"], macd["signal"])
    view.roc_pct = _last_finite(roc)
    view.stoch_k = _last_finite(stoch["k"])
    view.stoch_d = _last_finite(stoch["d"])
    if view.rsi is None and view.roc_pct is None and view.macd is None:
        view.status = "insufficient_history"
    return view


def _build_volatility_view(
    data: dict[str, np.ndarray], c: np.ndarray, p: SummaryParams
) -> VolatilityView:
    view = VolatilityView()
    if p.atr_period >= 1:
        atr = trend_mod.atr(data, p.atr_period).values["atr"]
        view.atr = _last_finite(atr)
        if view.atr is not None and float(c[-1]) != 0:
            view.atr_pct = view.atr / float(c[-1]) * 100.0

    view.historical_volatility_pct_annual = _last_finite(
        volatility.historical_volatility(data, p.hv_period, p.hv_trading_days).values["hv"]
    )

    # Rolling close-to-close percent stdev over the same window, ddof=1,
    # NOT annualised.  The window shrinks to the returns actually available.
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = 100.0 * (c[1:] - c[:-1]) / c[:-1]
    view.rolling_stddev_pct_per_bar = _rolling_sd_last(rets, p.return_window)

    boll = volatility.bollinger(data, p.bollinger_period, p.bollinger_deviation).values
    bandwidth = 100.0 * boll["bandwidth"]
    view.bandwidth_pct = _last_finite(bandwidth)
    view.bandwidth_rolling_stdev_pct = _rolling_sd_last(
        bandwidth[np.isfinite(bandwidth)], p.bollinger_period
    )

    # Regime: last bandwidth vs the mean bandwidth over the preceding bars of
    # the same series (documented 10% bands around that mean).
    finite_bw = bandwidth[np.isfinite(bandwidth)]
    if finite_bw.size >= 3:
        prev = finite_bw[-min(p.bollinger_period, int(finite_bw.size) - 1) : -1]
        mean_prev = float(prev.mean()) if prev.size else 0.0
        if mean_prev > 0:
            last = float(finite_bw[-1])
            if last > mean_prev * 1.10:
                view.regime = "expanding"
            elif last < mean_prev * 0.90:
                view.regime = "contracting"
            else:
                view.regime = "stable"

    if view.historical_volatility_pct_annual is None and (view.rolling_stddev_pct_per_bar is None):
        view.status = "insufficient_history"
    return view


def _build_volume_view(
    data: dict[str, np.ndarray],
    v: np.ndarray | None,
    p: SummaryParams,
    constant_tp: bool,
    zero_flow: bool,
) -> VolumeView:
    view = VolumeView()
    if v is None:
        view.status = "no_volume"
        return view
    if constant_tp or zero_flow:
        # No positive and no negative money flow makes the money ratio 0/0,
        # which is undefined, so there is nothing to zone. The engine now
        # returns NaN for that case itself; this guard short-circuits the
        # calculation and is what emits the `limitations` entry.
        view.mfi = None
        view.mfi_zone = None
    else:
        mfi = volume_mod.mfi(data, p.mfi_period).values["mfi"]
        view.mfi = _last_finite(mfi)
        if view.mfi is not None:
            if view.mfi >= p.mfi_overbought:
                view.mfi_zone = "overbought"
            elif view.mfi <= p.mfi_oversold:
                view.mfi_zone = "oversold"
            else:
                view.mfi_zone = "neutral"
    view.latest_volume = float(v[-1])
    if p.rvol_baseline >= 2:
        # A one-bar baseline is not a reference mean: documented as not evaluated.
        view.volume_sma = _last_finite(
            volume_mod.volume_sma(data, p.rvol_baseline).values["volume_sma"]
        )
        view.relative_volume = _last_finite(
            volume_mod.relative_volume(data, p.rvol_baseline).values["rvol"]
        )
    view.status = "ok" if view.mfi is not None else "insufficient_history"
    return view


def _build_structure_view(
    h: np.ndarray, lo: np.ndarray, p: SummaryParams, n: int
) -> tuple[StructureView, list[Swing]]:
    view = StructureView()
    swings = find_swings(h, lo, left=p.swing_left, right=p.swing_right, last_index=n - 1)
    info = classify_structure(swings)
    view.structure = str(info["trend"])
    view.swing_count = len(swings)
    lows = [s for s in swings if s.kind == "low"]
    highs = [s for s in swings if s.kind == "high"]
    if lows:
        view.support_level = float(lows[-1].price)
    if highs:
        view.resistance_level = float(highs[-1].price)
    # Documented: proximity-to-support is not evaluated by this module.
    view.near_support = None
    if view.structure == "insufficient data":
        view.status = "insufficient_history"
    return view, swings


# ------------------------------------------------------------------ interpretation
def _bucket(view: InterpretationView, text: str, agree: bool | None) -> None:
    """Sort one line into supporting / conflicting / ambiguous."""
    if agree is True:
        view.supporting.append(text)
    elif agree is False:
        view.conflicting.append(text)
    else:
        view.ambiguous.append(text)


def _build_interpretation(
    t: TrendView,
    m: MomentumView,
    vol: VolatilityView,
    vs: VolumeView,
    struct: StructureView,
    divergence: list[dict[str, Any]],
    p: SummaryParams,
    constant_close: bool,
) -> InterpretationView:
    view = InterpretationView()
    d = t.intermediate_direction
    view.trend_direction = d
    view.trend_strength = t.strength
    view.momentum_state = m.rsi_zone if m.rsi_zone else "not_available"
    view.volatility_regime = vol.regime

    # --- trend anchor
    if d is None:
        view.missing.append(
            f"trend: insufficient history for the {p.trend_intermediate}-bar window"
        )
    elif d == "flat":
        view.ambiguous.append(
            f"trend: flat over {p.trend_intermediate} bars (|change| <= {p.flat_threshold_pct:g}%)"
        )
    else:
        view.supporting.append(
            f"trend: {d} over {p.trend_intermediate} bars ({t.intermediate_change_pct:+.2f}%)"
        )

    # --- trend strength (ADX bands only)
    if t.strength is None or t.strength == "not available":
        view.missing.append("strength: ADX not available")
    elif t.strength == "strong":
        _bucket(
            view,
            f"strength: strong (ADX >= {p.adx_strong:g})",
            d in ("up", "down"),
        )
    elif t.strength == "developing":
        view.ambiguous.append(
            f"strength: developing ({p.adx_developing:g} <= ADX < {p.adx_strong:g})"
        )
    else:
        view.ambiguous.append(f"strength: weak (ADX < {p.adx_developing:g})")

    # --- ROC sign against the trend direction
    if m.roc_pct is None:
        view.missing.append("momentum: ROC not available")
    elif d in ("up", "down"):
        if m.roc_pct == 0:
            view.ambiguous.append(f"momentum: ROC {m.roc_pct:.2f}% (flat move)")
        else:
            _bucket(
                view,
                f"momentum: ROC {m.roc_pct:+.2f}% agrees with the {d} trend"
                if (m.roc_pct > 0) == (d == "up")
                else f"momentum: ROC {m.roc_pct:+.2f}% conflicts with the {d} trend",
                (m.roc_pct > 0) == (d == "up"),
            )
    else:
        view.ambiguous.append(f"momentum: ROC {m.roc_pct:+.2f}% (trend {d or 'undetermined'})")

    # --- MACD flip at the last bar
    if m.macd_cross == "not_available":
        view.missing.append("momentum: MACD flip not available")
    elif m.macd_cross == "none":
        view.ambiguous.append("momentum: no MACD flip at the last bar")
    elif d in ("up", "down"):
        bull = m.macd_cross == "bullish_cross"
        agree = bull == (d == "up")
        _bucket(
            view,
            f"momentum: {m.macd_cross} at the last bar "
            f"({('aligned with' if agree else 'against')} the {d} trend)",
            agree,
        )
    else:
        view.ambiguous.append(f"momentum: {m.macd_cross} at the last bar")

    # --- RSI zone (a threshold state, never directional on its own)
    if m.rsi is None:
        reason = "constant price series masked" if constant_close else "not available"
        view.missing.append(f"momentum: RSI {reason}")
    elif m.rsi_zone == "neutral":
        view.ambiguous.append(f"momentum: RSI neutral ({m.rsi:.1f})")
    else:
        view.ambiguous.append(
            f"momentum: RSI {m.rsi_zone} ({m.rsi:.1f}); threshold state, not directional"
        )

    # --- swing structure against the trend direction
    if struct.structure is None or struct.structure == "insufficient data":
        view.missing.append("structure: not enough confirmed swings")
    elif struct.structure == "mixed":
        view.ambiguous.append("structure: mixed (swing highs and lows disagree)")
    elif d in ("up", "down"):
        agree = struct.structure == d
        _bucket(
            view,
            f"structure: {struct.structure} "
            f"({('aligned with' if agree else 'against')} the {d} trend)",
            agree,
        )
    else:
        view.ambiguous.append(f"structure: {struct.structure}")

    # --- volatility regime (non-directional context)
    if vol.regime is None:
        view.missing.append("volatility: regime not available")
    else:
        view.ambiguous.append(f"volatility: {vol.regime} (non-directional context)")

    # --- volume (non-directional context)
    if vs.status == "no_volume":
        view.missing.append("volume: not supplied")
    elif vs.mfi is None:
        view.missing.append("volume: MFI not available")
    else:
        view.ambiguous.append(f"volume: MFI {vs.mfi_zone} ({vs.mfi:.1f}); non-directional")

    # --- divergence candidates against the trend direction
    if not divergence:
        view.ambiguous.append("divergence: no candidate detected")
    else:
        n_bear = sum(1 for c in divergence if c["direction"] == "bearish")
        n_bull = len(divergence) - n_bear
        opposing = "bearish" if d == "up" else ("bullish" if d == "down" else None)
        if opposing is None:
            view.ambiguous.append(f"divergence: {len(divergence)} candidate(s), trend undetermined")
        else:
            n_opp = n_bear if opposing == "bearish" else n_bull
            n_agr = len(divergence) - n_opp
            if n_opp:
                view.conflicting.append(
                    f"divergence: {n_opp} {opposing} candidate(s) against the {d} trend"
                )
            if n_agr:
                view.supporting.append(
                    f"divergence: {n_agr} candidate(s) aligned with the {d} trend"
                )

    view.narrative = (
        "INTERPRETIVE summary: "
        f"trend {d or 'unknown'} over {p.trend_intermediate} bars; "
        f"strength {t.strength or 'unknown'} (ADX); "
        f"momentum {view.momentum_state}; "
        f"volatility {vol.regime or 'unknown'}; "
        f"structure {struct.structure or 'unknown'}; "
        f"{len(divergence)} divergence candidate(s). "
        "Classified by documented thresholds only."
    )
    return view


def _limitations(
    t: TrendView,
    m: MomentumView,
    vol: VolatilityView,
    vs: VolumeView,
    struct: StructureView,
    divergence: list[dict[str, Any]],
    p: SummaryParams,
    constant_close: bool,
    constant_tp: bool,
    zero_flow: bool,
) -> list[str]:
    out: list[str] = [
        "Trend, momentum and volatility labels are DETECTED by documented "
        "thresholds; the combined interpretation is INTERPRETIVE. No "
        "probability or rating is produced and no trading recommendation "
        "is implied.",
        "near_support is not evaluated by this module (always None); "
        "price-swing structure is reported instead.",
        "Divergence findings are CANDIDATE pairs only: confirmed is None "
        "(not evaluated); no confirmation rule and no prior-trend context "
        "were applied.",
        "Warm-up bars are reported as None (insufficient_history) rather "
        "than being back-filled or extrapolated.",
    ]
    if constant_close:
        out.append(
            "RSI masked on a constant close series: the RSI engine returns "
            "100 for a 0/0 average gain/loss, which would read as a "
            "misleading overbought zone; the stochastic engine also falls "
            "back to its neutral 50 on a zero-range window."
        )
    if constant_tp:
        out.append(
            "MFI masked on a constant typical-price series: all money flow "
            "is zero there, and the engine reports 100 for a 0/0 ratio."
        )
    if zero_flow:
        out.append(
            "MFI masked on a zero-volume window: money flow is zero there, "
            "and the engine reports 100 for a 0/0 ratio."
        )
    if t.adx is None:
        out.append(
            "ADX unavailable: trend strength is 'not available' rather than "
            "estimated from a degenerate series."
        )
    if m.macd_cross == "not_available":
        out.append(
            "MACD flip not available: the MACD and signal lines are never "
            "jointly defined on this series."
        )
    if vs.status == "no_volume":
        out.append("No volume series supplied: MFI and relative volume not evaluated.")
    elif vs.relative_volume is None:
        out.append(
            f"relative_volume not evaluated (baseline {p.rvol_baseline} bar(s) "
            "is below the 2-bar minimum for a reference mean)."
        )
    if p.atr_period < 1:
        out.append("atr_period is 0: ATR fields disabled by configuration.")
    if p.bollinger_deviation == 0:
        out.append("bollinger_deviation is 0: bandwidth not defined by configuration.")
    if vol.regime is None:
        out.append(
            "Volatility regime not evaluated: the bandwidth history is too "
            "short to form a baseline."
        )
    if struct.structure == "insufficient data":
        out.append(
            "Swing structure not evaluated: too few confirmed swings for the "
            "configured left/right context."
        )
    if not divergence:
        out.append(
            "No divergence candidate: absence is not evidence of momentum "
            "agreement; the screen only reports qualifying swing pairs."
        )
    return out


# ------------------------------------------------------------------ public API
def build_summary(
    open_: Any,
    high: Any,
    low: Any,
    close: Any,
    volume: Any = None,
    dates: Any = None,
    params: SummaryParams | dict[str, Any] | None = None,
) -> SummaryResult:
    """Build the explainable trend / momentum / volatility summary.

    Pure and deterministic: the same series and params always yield the same
    result.  All reported values are trailing-window functions of the given
    arrays, and the arrays end at the reported ``last_index``, so no bar after
    ``last_index`` can influence the output (prefix tests in
    ``tests/test_summary.py``).

    Parameters
    ----------
    open_, high, low, close:
        OHLC series of equal length (``open_`` because ``open`` is a builtin).
        Validated by ``candles.validate_ohlc``; lows must be strictly positive.
    volume:
        Optional volume series (same length, finite, non-negative).  When it
        is ``None`` the volume statistics report ``status = "no_volume"`` and
        the interpretation lists volume under ``missing``.
    dates:
        Optional timestamp series (same length); only ``dates[-1]`` is echoed
        into ``last_time``.
    params:
        :class:`SummaryParams` instance, a dict of overrides, or ``None``.

    Raises
    ------
    SummaryError
        Invalid OHLCV data, fewer than ``MIN_BARS`` bars, non-positive
        prices, or invalid parameters.
    """
    p = _resolve_params(params)
    o, h, lo, c, v, d = _validated_inputs(open_, high, low, close, volume, dates)

    data: dict[str, np.ndarray] = {"open": o, "high": h, "low": lo, "close": c}
    if v is not None:
        data["volume"] = v

    constant_close = bool(np.all(c == c[0]))
    tp = (h + lo + c) / 3.0
    constant_tp = bool(np.all(tp == tp[0]))
    window = min(p.mfi_period, int(c.size))
    zero_flow = bool(v is not None and np.all(v[-window:] == 0))

    trend_view = _build_trend_view(data, c, p)
    momentum_view = _build_momentum_view(data, p, constant_close)
    volatility_view = _build_volatility_view(data, c, p)
    volume_view = _build_volume_view(data, v, p, constant_tp, zero_flow)
    structure_view, swings = _build_structure_view(h, lo, p, int(c.size))

    # Divergence candidates: RSI against price swings.  NaN warm-up entries
    # become None so the screen skips them instead of comparing garbage.
    rsi_series: list[float | None] = [
        float(x) if math.isfinite(float(x)) else None
        for x in momentum.rsi(data, p.rsi_period).values["rsi"]
    ]
    divergence = candidate_divergence(
        swings, rsi_series, indicator_name="rsi", last_index=int(c.size) - 1
    )

    interpretation = _build_interpretation(
        trend_view,
        momentum_view,
        volatility_view,
        volume_view,
        structure_view,
        divergence,
        p,
        constant_close,
    )
    limitations = _limitations(
        trend_view,
        momentum_view,
        volatility_view,
        volume_view,
        structure_view,
        divergence,
        p,
        constant_close,
        constant_tp,
        zero_flow,
    )

    return SummaryResult(
        rule_version=SUMMARY_RULE_VERSION,
        generated_from=f"ohlc({int(c.size)} bars)",
        last_index=int(c.size) - 1,
        last_time=str(d[-1]) if d else None,
        timeframe=p.timeframe,
        trend=trend_view,
        momentum=momentum_view,
        volatility=volatility_view,
        volume_stats=volume_view,
        structure=structure_view,
        interpretation=interpretation,
        divergence_candidates=divergence,
        limitations=limitations,
    )
