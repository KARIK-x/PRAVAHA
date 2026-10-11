"""Technical-indicator engine.

DESIGN
------
* **Causal by construction.** Every indicator uses only ``t`` and earlier
  observations. There is no centred window, no back-fill, no smoothing that
  reaches forward. A signal plotted on day *t* could genuinely have been known
  at the close of day *t*. This is enforced by tests that compare a full-series
  computation against a prefix recomputation.
* **NumPy in, NumPy out.** Implementations operate on ``np.ndarray`` of floats,
  not on DataFrames, so they are independent of pandas major-version semantics
  and are cheap on a memory-constrained machine.
* **NaN warm-up.** The first ``warmup`` outputs are ``np.nan``; consumers must
  handle them. Nothing is silently replaced with a fill value.
* **Registry.** New indicators register themselves with a decorator; nothing
  outside this package needs to change to add one.

Every indicator declares its parameters, inputs, warm-up length and a reference
so its formula can be checked.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

Price = np.ndarray  # float array, oldest -> newest


@dataclass(slots=True)
class IndicatorMeta:
    """Static description of an indicator - used by docs, the API and the UI."""

    name: str
    label: str
    category: str  # trend | momentum | volatility | volume | other
    params: dict[str, Any] = field(default_factory=dict)
    inputs: tuple[str, ...] = ("close",)
    outputs: tuple[str, ...] = ()
    #: Warm-up length. Either a fixed int, or a callable taking the resolved
    #: parameter dict and returning the warm-up for those parameters.
    warmup: int | Callable[[dict[str, Any]], int] = 0
    #: Per-output warm-up overrides, for indicators whose outputs stabilise at
    #: different times (e.g. MACD's line is ready before its signal line).
    #: Any output not listed here uses ``warmup``.
    output_warmup: dict[str, int | Callable[[dict[str, Any]], int]] | None = None
    reference: str = ""
    formula: str = ""
    notes: str = ""

    def resolved_output_warmup(self, params: dict[str, Any] | None = None) -> dict[str, int]:
        """Warm-up for every declared output, falling back to the overall figure.

        Always populated, so a consumer never has to guess whether a missing
        entry means "same as overall" or "not known".
        """
        p = params if params is not None else self.params
        default = _resolve_scalar(self.warmup, p)
        return {
            out: _resolve_scalar(self.output_warmup[out], p)
            if (self.output_warmup and out in self.output_warmup)
            else default
            for out in self.outputs
        }

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "category": self.category,
            "params": self.params,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "warmup": self.warmup(self.params) if callable(self.warmup) else self.warmup,
            "output_warmup": self.resolved_output_warmup(),
            "reference": self.reference,
            "formula": self.formula,
            "notes": self.notes,
        }


IndicatorFn = Callable[..., "IndicatorResult"]


@dataclass(slots=True)
class IndicatorResult:
    """One indicator's output for one series."""

    name: str
    params: dict[str, Any]
    #: column name -> values (same length as the input series)
    values: dict[str, np.ndarray]
    warmup: int = 0
    #: Per-output warm-up, for indicators whose outputs stabilise at different
    #: bars. Falls back to ``warmup`` for any column not listed.
    output_warmup: dict[str, int] = field(default_factory=dict)
    #: True when the series was too short to produce a meaningful result
    insufficient_data: bool = False
    message: str = ""

    def latest(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for k, v in self.values.items():
            if len(v) == 0:
                out[k] = None
            else:
                x = float(v[-1])
                out[k] = None if np.isnan(x) else x
        return out


_REGISTRY: dict[str, tuple[IndicatorMeta, IndicatorFn]] = {}


def register(meta: IndicatorMeta) -> Callable[[IndicatorFn], IndicatorFn]:
    """Decorator registering an indicator implementation."""

    def deco(fn: IndicatorFn) -> IndicatorFn:
        if meta.name in _REGISTRY:
            raise ValueError(f"indicator already registered: {meta.name}")
        _REGISTRY[meta.name] = (meta, fn)
        return fn

    return deco


def get(name: str) -> tuple[IndicatorMeta, IndicatorFn]:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown indicator '{name}'. Available: {', '.join(sorted(_REGISTRY))}"
        ) from None


def available(category: str | None = None) -> list[dict[str, Any]]:
    metas = [m for m, _ in _REGISTRY.values() if category is None or m.category == category]
    return [m.describe() for m in sorted(metas, key=lambda m: (m.category, m.name))]


def compute(name: str, data: dict[str, np.ndarray], **params: Any) -> IndicatorResult:
    """Compute one indicator by name.

    Parameters
    ----------
    data:
        Mapping of input column name -> 1-D float array. All arrays must be the
        same length and ordered oldest -> newest.
    params:
        Override the indicator's defaults.
    """
    meta, fn = get(name)
    arrays = {k: _as_float(v) for k, v in data.items()}
    lengths = {k: len(v) for k, v in arrays.items() if k in meta.inputs}
    if len(set(lengths.values())) > 1:
        raise ValueError(f"input arrays have different lengths: {lengths}")
    n = next(iter(lengths.values()), 0)

    merged = {**meta.params, **params}
    _validate_params(meta, merged)

    try:
        result = fn(arrays, **merged)
    except ValueError as exc:
        vals = {o: np.full(n, np.nan) for o in meta.outputs}
        return IndicatorResult(
            name=name,
            params=merged,
            values=vals,
            warmup=resolve_warmup(meta, merged),
            output_warmup={o: resolve_warmup(meta, merged, o) for o in vals},
            insufficient_data=True,
            message=str(exc),
        )
    result.params = merged
    result.warmup = resolve_warmup(meta, merged)
    result.output_warmup = {c: resolve_warmup(meta, merged, c) for c in result.values}
    return result


def _resolve_scalar(w: int | Callable[[dict[str, Any]], int], params: dict[str, Any]) -> int:
    return int(w(params)) if callable(w) else int(w)


def resolve_warmup(meta: IndicatorMeta, params: dict[str, Any], output: str | None = None) -> int:
    """Warm-up for the *resolved* parameters, optionally for one output column."""
    if output is not None and meta.output_warmup and output in meta.output_warmup:
        return _resolve_scalar(meta.output_warmup[output], params)
    return _resolve_scalar(meta.warmup, params)


def _validate_params(meta: IndicatorMeta, params: dict[str, Any]) -> None:
    unknown = set(params) - set(meta.params)
    if unknown:
        raise ValueError(
            f"{meta.name}: unknown parameter(s) {sorted(unknown)}; declared {sorted(meta.params)}"
        )
    for k, v in params.items():
        default = meta.params[k]
        if isinstance(default, (int, float)):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise ValueError(f"{meta.name}.{k} must be numeric, got {v!r}")
            if v <= 0:
                raise ValueError(f"{meta.name}.{k} must be > 0, got {v}")


def _as_float(a: np.ndarray | Sequence[float]) -> np.ndarray:
    arr = np.asarray(a, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"expected a 1-D array, got shape {arr.shape}")
    return arr


# ---------------------------------------------------------------- primitives
def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Wilder's true range. Element 0 has no prior close, so it is NaN."""
    n = len(close)
    tr = np.full(n, np.nan)
    if n < 2:
        return tr
    prev_close = close[:-1]
    tr[1:] = np.maximum.reduce(
        [
            high[1:] - low[1:],
            np.abs(high[1:] - prev_close),
            np.abs(low[1:] - prev_close),
        ]
    )
    return tr


def wilder_smooth(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothing (equivalent to EMA with alpha = 1/period).

    The seed is the arithmetic mean of the first *complete* window of
    ``period`` non-NaN values, so the output stays NaN until a full window
    exists. Using a NaN-skipping mean here would quietly start the series
    earlier than the declared warm-up, which is why it is deliberately avoided.
    """
    n = len(values)
    out = np.full(n, np.nan)
    if period <= 0 or n < period:
        return out
    start = _first_full_window(values, period)
    if start is None:
        return out
    seed_idx = start + period - 1
    out[seed_idx] = float(values[start : seed_idx + 1].mean())
    alpha = 1.0 / period
    for i in range(seed_idx + 1, n):
        v = values[i]
        prev = out[i - 1]
        if np.isnan(v):
            out[i] = prev
        elif np.isnan(prev):
            out[i] = v
        else:
            out[i] = prev + alpha * (v - prev)
    return out


def rolling_sum(values: np.ndarray, period: int) -> np.ndarray:
    n = len(values)
    out = np.full(n, np.nan)
    if period <= 0 or n < period:
        return out
    c = np.cumsum(np.where(np.isnan(values), 0.0, values))
    out[period - 1 :] = c[period - 1 :]
    out[period - 1 :] -= np.concatenate(([0.0], c[:-period]))
    # Only valid once every window element is non-NaN.
    valid = ~np.isnan(values)
    cv = np.cumsum(valid.astype(int))
    cnt = np.empty(n, dtype=int)
    cnt[period - 1 :] = cv[period - 1 :] - np.concatenate(([0], cv[:-period]))
    out[cnt < period] = np.nan
    return out


def rolling_mean(values: np.ndarray, period: int) -> np.ndarray:
    s = rolling_sum(values, period)
    with np.errstate(invalid="ignore"):
        return s / period


def rolling_std(values: np.ndarray, period: int, ddof: int = 1) -> np.ndarray:
    """Population/sample rolling standard deviation, NaN until a full window."""
    n = len(values)
    out = np.full(n, np.nan)
    if period <= 1 or n < period:
        return out
    for i in range(period - 1, n):
        w = values[i - period + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        out[i] = float(np.std(w, ddof=ddof))
    return out


def ema(values: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average seeded with the first ``period`` values.

    Standard seeding (SMA of the first ``period``) is used so results are
    reproducible and match common references once past warm-up.
    """
    n = len(values)
    out = np.full(n, np.nan)
    if period <= 0 or n < period:
        return out
    # Find the first index with `period` consecutive non-NaN values.
    start = _first_full_window(values, period)
    if start is None:
        return out
    seed_idx = start + period - 1
    out[seed_idx] = np.nanmean(values[start : seed_idx + 1])
    alpha = 2.0 / (period + 1)
    for i in range(seed_idx + 1, n):
        v = values[i]
        prev = out[i - 1]
        out[i] = prev if np.isnan(v) else (v if np.isnan(prev) else prev + alpha * (v - prev))
    return out


def _first_full_window(values: np.ndarray, period: int) -> int | None:
    run = 0
    for i, v in enumerate(values):
        run = 0 if np.isnan(v) else run + 1
        if run >= period:
            return i - period + 1
    return None


def rolling_max(values: np.ndarray, period: int) -> np.ndarray:
    n = len(values)
    out = np.full(n, np.nan)
    if period <= 0 or n < period:
        return out
    for i in range(period - 1, n):
        w = values[i - period + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        out[i] = np.max(w)
    return out


def rolling_min(values: np.ndarray, period: int) -> np.ndarray:
    n = len(values)
    out = np.full(n, np.nan)
    if period <= 0 or n < period:
        return out
    for i in range(period - 1, n):
        w = values[i - period + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        out[i] = np.min(w)
    return out


def shift(values: np.ndarray, periods: int) -> np.ndarray:
    """Lag/lead by whole periods. Positive ``periods`` looks *back* (causal)."""
    out = np.full(len(values), np.nan)
    if periods == 0:
        return values.copy()
    if periods > 0:
        out[periods:] = values[:-periods]
    else:
        k = -periods
        out[:-k] = values[k:]
    return out


def crosses_above(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Boolean array: ``a`` crosses above ``b`` on this bar (causal)."""
    prev_a, prev_b = shift(a, 1), shift(b, 1)
    with np.errstate(invalid="ignore"):
        return (a > b) & (prev_a <= prev_b) & ~np.isnan(a) & ~np.isnan(b)


def crosses_below(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    prev_a, prev_b = shift(a, 1), shift(b, 1)
    with np.errstate(invalid="ignore"):
        return (a < b) & (prev_a >= prev_b) & ~np.isnan(a) & ~np.isnan(b)
