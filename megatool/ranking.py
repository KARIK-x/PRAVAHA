"""Transparent multi-factor ranking.

Priority 5 of ``MEGA_TOOL_RESEARCH_REPORT.md`` (section 8).

Design commitments
------------------
* **Explainable** - every score decomposes into per-factor percentile ranks and
  per-factor weighted contributions. Nothing is hidden inside a black box.
* **Configurable** - factors and weights are data, not code. The caller decides.
* **Explicit about missing data** - a factor that cannot be computed is never
  silently treated as zero. It is recorded as missing, substituted with the
  cross-sectional median, and the symbol is flagged incomplete. Symbols missing
  more than ``max_missing_fraction`` of factors are excluded from ranking and
  returned separately as "insufficient data".
* **Chronological** - ``as_of`` truncates every series before any factor is
  computed, so a factor can never see a bar after the ranking date.

What is and is not available
----------------------------
Only price/volume history exists in this project. Factors requiring
fundamentals (P/E, P/B, dividend yield) or a published index (relative strength
vs NEPSE) are declared ``available=False`` with a reason, are given zero weight
by default, and are surfaced in ``RankResult.unavailable`` so the omission is
visible rather than implied. ``sector_percentile`` is different: its availability
is derived from the sector data actually supplied for the run, so the reason is
always computed from live coverage — never a hard-coded assumption about the
store. With no sector data the factor is unavailable exactly as before; with
enough usable sectors it computes real within-sector percentiles.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .scanner import METRIC_HELP, _metric_value

#: Factors this build can actually compute from stored price/volume history.
PRICE_FACTORS: dict[str, dict[str, Any]] = {
    "momentum_3m": {
        "label": "3-month momentum",
        "metric": "return_60d",
        "lookback": None,
        "higher_is_better": True,
        "blurb": "Close-to-close return over 60 trading days.",
    },
    "momentum_6m": {
        "label": "6-month momentum",
        "metric": "return_120d",
        "lookback": None,
        "higher_is_better": True,
        "blurb": "Close-to-close return over 120 trading days.",
    },
    "volume_trend": {
        "label": "Volume trend",
        "metric": "volume_sma_ratio",
        "lookback": None,
        "higher_is_better": True,
        "blurb": "Latest volume / 20-bar volume moving average.",
    },
    "volatility": {
        "label": "Volatility (20d, annualised)",
        "metric": "historical_volatility",
        "lookback": None,
        "higher_is_better": False,
        "blurb": "Annualised close-to-close volatility; lower ranks higher.",
    },
    "near_52w_high": {
        "label": "Proximity to 52-week high",
        "metric": "distance_from_high_52w",
        "lookback": None,
        "higher_is_better": True,
        "blurb": "Percent from the trailing 250-bar high; 0 = at the high.",
    },
    "sector_percentile": {
        "label": "Sector Percentile",
        "metric": "return_60d",
        "lookback": None,
        "higher_is_better": True,
        "blurb": (
            "Percentile of 3-month momentum within the symbol's own sector "
            "(research report §8.2). Computed only when the usable sector "
            "coverage of the ranked universe meets the configured threshold."
        ),
    },
    "relative_strength": {
        "label": "Relative strength vs NEPSE composite",
        "metric": "return_60d",
        "lookback": None,
        "higher_is_better": True,
        "blurb": (
            "Percentile of 3-month return in excess of the official NEPSE "
            "composite index over the same 60-trading-day window. Computed only "
            "when the composite index series is connected to the run; no "
            "substitute benchmark is ever asserted."
        ),
    },
}

#: Factors the report recommends that this build cannot compute, with reasons.
#: ``relative_strength`` is deliberately **not** here: its availability is
#: data-driven (see :func:`index_availability`), exactly like the sector factor.
UNAVAILABLE_FACTORS: dict[str, str] = {
    "pe_ratio": "Requires EPS. No verified fundamentals source is connected.",
    "pb_ratio": "Requires net worth per share. No verified fundamentals source is connected.",
    "dividend_yield": "Requires DPS. No verified fundamentals source is connected.",
}

#: The sector factor's key. Its availability is data-driven (see
#: :func:`sector_availability`), unlike the static entries above.
SECTOR_FACTOR_KEY = "sector_percentile"

#: The relative-strength factor's key. Availability is data-driven (see
#: :func:`index_availability`).
RELATIVE_STRENGTH_KEY = "relative_strength"

#: The only permitted relative-strength benchmark: the official NEPSE composite
#: index, under the name the index loader stores it as. No substitute is ever
#: asserted, so a run without this exact series reports the factor unavailable.
NEPSE_COMPOSITE_INDEX = "NEPSE"


@dataclass(frozen=True, slots=True)
class SectorAvailability:
    """Computed availability of the sector factor for one ranking run.

    Three honest states, distinguished by ``reason``:

    * **unavailable data** — no usable sector mapping was supplied at all;
    * **insufficient coverage** — a mapping exists but the share of the ranked
      universe with a usable (non-blank) sector is below the threshold;
    * **available** — coverage meets the threshold and real within-sector
      percentiles are computed.
    """

    available: bool
    reason: str
    coverage: float
    classified: int
    universe_size: int
    threshold: float


def sector_availability(
    sectors: Mapping[str, str] | None,
    universe_symbols: list[str] | tuple[str, ...],
    threshold: float,
) -> SectorAvailability:
    """Derive sector-factor availability from the sector data actually supplied.

    Blank or missing sector values are never treated as a classification: a
    symbol counts as classified only when its sector is a non-empty string.
    """
    usable = {
        str(symbol).upper(): str(value).strip()
        for symbol, value in (sectors or {}).items()
        if value is not None and str(value).strip()
    }
    universe = [str(s).upper() for s in universe_symbols]
    classified = sum(1 for s in universe if usable.get(s))
    coverage = (classified / len(universe)) if universe else 0.0
    if not usable:
        return SectorAvailability(
            available=False,
            reason=(
                "No sector classification data is connected to this run; "
                "sector percentiles cannot be computed."
            ),
            coverage=0.0,
            classified=0,
            universe_size=len(universe),
            threshold=threshold,
        )
    if coverage < threshold:
        return SectorAvailability(
            available=False,
            reason=(
                f"Sector coverage {coverage:.0%} ({classified}/{len(universe)}) "
                f"is below the required {threshold:.0%}; sector percentiles are "
                "not computed rather than computed from too little data."
            ),
            coverage=coverage,
            classified=classified,
            universe_size=len(universe),
            threshold=threshold,
        )
    return SectorAvailability(
        available=True,
        reason="",
        coverage=coverage,
        classified=classified,
        universe_size=len(universe),
        threshold=threshold,
    )


@dataclass(frozen=True, slots=True)
class IndexAvailability:
    """Computed availability of the relative-strength factor for one run.

    Relative strength is measured against the **official NEPSE composite index**
    and nothing else. If that series is not connected, or is too short to span
    the ranking window, the factor is reported unavailable with the measured
    reason rather than computed against an invented proxy.
    """

    available: bool
    reason: str
    bars: int
    benchmark_return_60d: float | None


def index_availability(
    benchmark_bars: int,
    benchmark_return_60d: float | None,
    min_bars: int,
) -> IndexAvailability:
    """Derive the relative-strength factor's availability from real index data.

    ``benchmark_bars`` is the number of composite-index closes on or before the
    ranking date; ``benchmark_return_60d`` is the composite's own 60-day return
    over that window, or ``None`` when it cannot be computed.
    """
    if benchmark_bars <= 0:
        return IndexAvailability(
            available=False,
            reason=(
                "No NEPSE composite index series is connected to this run; "
                "relative strength is not computed against an invented substitute."
            ),
            bars=0,
            benchmark_return_60d=None,
        )
    if benchmark_bars < min_bars:
        return IndexAvailability(
            available=False,
            reason=(
                f"Composite index history ({benchmark_bars} bars) is below the "
                f"{min_bars}-bar floor on or before the ranking date; relative "
                "strength is not computed from too little benchmark data."
            ),
            bars=benchmark_bars,
            benchmark_return_60d=None,
        )
    if benchmark_return_60d is None:
        return IndexAvailability(
            available=False,
            reason=(
                "The composite index's 60-day return could not be computed from "
                "the connected series; relative strength is not computed."
            ),
            bars=benchmark_bars,
            benchmark_return_60d=None,
        )
    return IndexAvailability(
        available=True,
        reason="",
        bars=benchmark_bars,
        benchmark_return_60d=benchmark_return_60d,
    )


def _sector_percentiles(
    retained: dict[str, pd.DataFrame],
    base_metric: str,
    sectors: Mapping[str, str],
    min_group: int = 2,
) -> dict[str, float | None]:
    """Within-sector percentile (0-100) of ``base_metric`` for each symbol.

    Returns ``None`` — never a fabricated number — when a symbol has no usable
    sector, when its sector group has fewer than ``min_group`` members (a
    percentile within a group of one is not a percentile), or when the base
    metric cannot be computed for the symbol.
    """
    values: dict[str, float] = {}
    for symbol, frame in retained.items():
        if not sectors.get(symbol):
            continue
        try:
            values[symbol] = _metric_value(base_metric, frame)
        except Exception:
            continue
    by_sector: dict[str, list[str]] = {}
    for symbol in values:
        by_sector.setdefault(sectors[symbol], []).append(symbol)
    out: dict[str, float | None] = {symbol: None for symbol in retained}
    for members in by_sector.values():
        if len(members) < min_group:
            continue
        pct = _percentile_rank({m: values[m] for m in members})
        for member in members:
            out[member] = pct[member]
    return out


#: Default weights. Unavailable factors carry 0.0 and are renormalised out.
DEFAULT_WEIGHTS: dict[str, float] = {
    "momentum_3m": 0.25,
    "momentum_6m": 0.25,
    "volume_trend": 0.15,
    "volatility": 0.15,
    "near_52w_high": 0.20,
}


@dataclass(slots=True)
class FactorSpec:
    """One ranking factor: how to compute it and how to interpret it."""

    key: str
    label: str
    metric: str
    higher_is_better: bool
    weight: float
    lookback: int | None = None
    available: bool = True
    unavailable_reason: str = ""

    @property
    def blurb(self) -> str:
        if not self.available:
            return self.unavailable_reason
        return PRICE_FACTORS.get(self.key, {}).get("blurb", METRIC_HELP.get(self.metric, ""))


@dataclass(slots=True)
class RankedSymbol:
    """One symbol's ranking outcome with a full explanation."""

    symbol: str
    score: float | None
    rank: int | None
    percentiles: dict[str, float | None] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    raw_values: dict[str, float | None] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    complete: bool = True
    note: str = ""
    #: Factor values actually used for scoring (post median-substitution).
    #: Kept out of ``to_dict`` output only if empty; always populated for
    #: ranked symbols so a reviewer can reproduce the score by hand.
    filled: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "rank": self.rank,
            "percentiles": self.percentiles,
            "contributions": self.contributions,
            "raw_values": self.raw_values,
            "missing": self.missing,
            "complete": self.complete,
            "note": self.note,
            "filled": self.filled,
        }


@dataclass(slots=True)
class RankConfig:
    """User-adjustable ranking configuration."""

    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    min_bars: int = 60
    #: Above this fraction of missing factors, a symbol is not ranked at all.
    max_missing_fraction: float = 0.5
    #: Minimum share of the ranked universe that must carry a usable sector
    #: classification before ``sector_percentile`` is computed at all. Below
    #: this the factor is reported unavailable with the measured coverage.
    sector_min_coverage: float = 0.5
    as_of: str | None = None

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.min_bars < 1:
            problems.append("min_bars must be >= 1")
        if not 0.0 <= self.max_missing_fraction <= 1.0:
            problems.append("max_missing_fraction must be between 0 and 1")
        if not 0.0 <= self.sector_min_coverage <= 1.0:
            problems.append("sector_min_coverage must be between 0 and 1")
        for key, w in self.weights.items():
            if key not in PRICE_FACTORS:
                problems.append(f"unknown factor {key!r}")
            elif w < 0:
                problems.append(f"weight for {key!r} must be >= 0")
        if sum(v for v in self.weights.values() if v > 0) == 0:
            problems.append("at least one factor must have a positive weight")
        return problems


@dataclass(slots=True)
class RankResult:
    """Ranked universe plus everything needed to audit it."""

    ranked: list[RankedSymbol]
    excluded: list[RankedSymbol]
    factors: list[FactorSpec]
    weights: dict[str, float]
    unavailable: dict[str, str]
    as_of: str | None
    universe_size: int
    notes: list[str] = field(default_factory=list)
    benchmark: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranked": [r.to_dict() for r in self.ranked],
            "excluded": [e.to_dict() for e in self.excluded],
            "factors": [
                {
                    "key": f.key,
                    "label": f.label,
                    "weight": f.weight,
                    "available": f.available,
                    "higher_is_better": f.higher_is_better,
                    "blurb": f.blurb,
                }
                for f in self.factors
            ],
            "weights": self.weights,
            "unavailable": self.unavailable,
            "as_of": self.as_of,
            "universe_size": self.universe_size,
            "notes": self.notes,
            "benchmark": self.benchmark,
        }


def build_factor_specs(
    weights: dict[str, float] | None = None,
    sector_status: SectorAvailability | None = None,
    index_status: IndexAvailability | None = None,
) -> list[FactorSpec]:
    """Materialise factor specs from weights, including unavailable factors.

    ``sector_percentile`` and ``relative_strength`` are emitted from their
    computed availability objects when given (default ``None``: no data,
    unavailable — the historical behaviour); the static entries are
    unconditional.
    """
    merged = dict(DEFAULT_WEIGHTS)
    if weights:
        merged.update(weights)
    specs = [
        FactorSpec(
            key=key,
            label=cfg["label"],
            metric=cfg["metric"],
            higher_is_better=cfg["higher_is_better"],
            weight=float(merged.get(key, 0.0)),
            lookback=cfg["lookback"],
            available=True,
        )
        for key, cfg in PRICE_FACTORS.items()
        if key not in (SECTOR_FACTOR_KEY, RELATIVE_STRENGTH_KEY)
    ]
    for key, reason in UNAVAILABLE_FACTORS.items():
        specs.append(
            FactorSpec(
                key=key,
                label=key.replace("_", " ").title(),
                metric="",
                higher_is_better=True,
                weight=0.0,
                available=False,
                unavailable_reason=reason,
            )
        )
    status = sector_status or SectorAvailability(
        available=False,
        reason=(
            "No sector classification data is connected to this run; "
            "sector percentiles cannot be computed."
        ),
        coverage=0.0,
        classified=0,
        universe_size=0,
        threshold=0.0,
    )
    sector_cfg = PRICE_FACTORS[SECTOR_FACTOR_KEY]
    if status.available:
        specs.append(
            FactorSpec(
                key=SECTOR_FACTOR_KEY,
                label=sector_cfg["label"],
                metric=sector_cfg["metric"],
                higher_is_better=sector_cfg["higher_is_better"],
                weight=float(merged.get(SECTOR_FACTOR_KEY, 0.0)),
                lookback=sector_cfg["lookback"],
                available=True,
            )
        )
    else:
        specs.append(
            FactorSpec(
                key=SECTOR_FACTOR_KEY,
                label=sector_cfg["label"],
                metric="",
                higher_is_better=True,
                weight=0.0,
                available=False,
                unavailable_reason=status.reason,
            )
        )
    index_stat = index_status or index_availability(0, None, 0)
    index_cfg = PRICE_FACTORS[RELATIVE_STRENGTH_KEY]
    if index_stat.available:
        specs.append(
            FactorSpec(
                key=RELATIVE_STRENGTH_KEY,
                label=index_cfg["label"],
                metric=index_cfg["metric"],
                higher_is_better=index_cfg["higher_is_better"],
                weight=float(merged.get(RELATIVE_STRENGTH_KEY, 0.0)),
                lookback=index_cfg["lookback"],
                available=True,
            )
        )
    else:
        specs.append(
            FactorSpec(
                key=RELATIVE_STRENGTH_KEY,
                label=index_cfg["label"],
                metric="",
                higher_is_better=True,
                weight=0.0,
                available=False,
                unavailable_reason=index_stat.reason,
            )
        )
    return specs


def _date_column(df: pd.DataFrame) -> str | None:
    """Return the frame's date column name.

    Synthetic frames and this module's tests use ``date``; bars loaded from
    ``MarketStore.get_bars`` arrive as ``trading_date``. Supporting both means
    the ranker cannot silently skip truncation because of a naming mismatch.
    """
    for candidate in ("trading_date", "date"):
        if candidate in df.columns:
            return candidate
    return None


def _truncate(df: pd.DataFrame, as_of: str | None) -> pd.DataFrame:
    """Drop every bar after ``as_of`` so no factor can look ahead."""
    if not as_of:
        return df
    col = _date_column(df)
    if col is None:
        return df
    return df[df[col] <= pd.Timestamp(as_of)]


def _percentile_rank(values: dict[str, float]) -> dict[str, float]:
    """Cross-sectional percentile (0-100) of each symbol's factor value."""
    keys = list(values)
    series = pd.Series({k: values[k] for k in keys}, dtype=float)
    ranks = series.rank(method="average", pct=True) * 100.0
    return {k: float(ranks[k]) for k in keys}


def rank_universe(
    frames: dict[str, pd.DataFrame],
    config: RankConfig | None = None,
    *,
    sectors: Mapping[str, str] | None = None,
    benchmark: pd.DataFrame | None = None,
) -> RankResult:
    """Rank a universe of symbols.

    Parameters
    ----------
    frames:
        symbol -> OHLCV frame, ascending by date, carrying a ``date`` column.
    config:
        Weights and thresholds; defaults to :data:`DEFAULT_WEIGHTS`.
    sectors:
        Optional ``symbol -> sector`` mapping used only to derive the sector
        factor's availability. Blank or missing values are ignored (a symbol
        without a usable sector is never classified). When ``None`` or empty
        the sector factor is unavailable with a stated reason, exactly as
        before sector data existed; when the usable coverage of the retained
        universe meets ``config.sector_min_coverage``, real within-sector
        percentiles of 3-month momentum are computed.
    benchmark:
        Optional composite-index frame (``trading_date``/``date`` + ``close``,
        ascending) used only to derive and compute the ``relative_strength``
        factor. It must be the official NEPSE composite; no substitute
        benchmark is asserted. When ``None`` or too short the factor is
        unavailable with a stated reason, exactly as before index data existed.
    """
    cfg = config or RankConfig()
    problems = cfg.validate()
    if problems:
        raise ValueError("; ".join(problems))

    sectors_map: dict[str, str] = {
        str(symbol).upper(): str(value).strip()
        for symbol, value in (sectors or {}).items()
        if value is not None and str(value).strip()
    }

    # ---- gate on history length, chronologically truncated ------------------
    retained: dict[str, pd.DataFrame] = {}
    too_short: list[RankedSymbol] = []
    for symbol, frame in frames.items():
        if frame is None or not len(frame):
            too_short.append(
                RankedSymbol(
                    symbol=symbol,
                    score=None,
                    rank=None,
                    complete=False,
                    note="insufficient data: no price history stored",
                )
            )
            continue
        cut = _truncate(frame, cfg.as_of)
        if len(cut) < cfg.min_bars:
            too_short.append(
                RankedSymbol(
                    symbol=symbol,
                    score=None,
                    rank=None,
                    complete=False,
                    note=(
                        f"insufficient data: {len(cut)} bars on or before "
                        f"{cfg.as_of or 'the latest date'}, needs {cfg.min_bars}"
                    ),
                )
            )
            continue
        retained[symbol] = cut

    # ---- sector-factor availability is computed from live data, never assumed
    sector_status = sector_availability(
        sectors_map,
        sorted(retained) if retained else sorted(frames),
        cfg.sector_min_coverage,
    )
    # ---- relative-strength availability likewise: real composite or nothing
    bench_cut = _truncate(benchmark, cfg.as_of) if benchmark is not None else None
    bench_bars = int(len(bench_cut)) if bench_cut is not None else 0
    bench_return: float | None = None
    if bench_bars >= cfg.min_bars:
        try:
            bench_return = _metric_value(PRICE_FACTORS[RELATIVE_STRENGTH_KEY]["metric"], bench_cut)
        except Exception:
            bench_return = None
    index_status = index_availability(bench_bars, bench_return, cfg.min_bars)
    specs = build_factor_specs(cfg.weights, sector_status, index_status)
    active = [s for s in specs if s.available and s.weight > 0]
    unavailable = {s.key: s.blurb for s in specs if not s.available}
    sector_values: dict[str, float | None] = {}
    if any(s.key == SECTOR_FACTOR_KEY for s in active):
        sector_values = _sector_percentiles(
            retained, PRICE_FACTORS[SECTOR_FACTOR_KEY]["metric"], sectors_map
        )
    relative_values: dict[str, float | None] = {}
    if any(s.key == RELATIVE_STRENGTH_KEY for s in active):
        base = PRICE_FACTORS[RELATIVE_STRENGTH_KEY]["metric"]
        excess: dict[str, float] = {}
        for symbol, cut in retained.items():
            try:
                value = _metric_value(base, cut)
            except Exception:
                value = None
            if value is not None and index_status.benchmark_return_60d is not None:
                excess[symbol] = value - index_status.benchmark_return_60d
        relative_values = _percentile_rank(excess) if excess else {}
    benchmark_info: dict[str, Any] | None = None
    if benchmark is not None or index_status.bars:
        benchmark_info = {
            "name": NEPSE_COMPOSITE_INDEX,
            "policy": (
                "the official NEPSE composite is the only benchmark; no substitute is asserted"
            ),
            "bars": index_status.bars,
            "return_60d": index_status.benchmark_return_60d,
            "available": index_status.available,
        }

    # ---- collect raw factor values ------------------------------------------
    raw: dict[str, dict[str, float | None]] = {}
    for symbol, cut in retained.items():
        raw[symbol] = {}
        for spec in active:
            if spec.key == SECTOR_FACTOR_KEY:
                # The raw value IS the within-sector percentile; None when the
                # symbol has no usable sector (median substitution applies).
                raw[symbol][spec.key] = sector_values.get(symbol)
                continue
            if spec.key == RELATIVE_STRENGTH_KEY:
                # The raw value IS the cross-sectional percentile of the
                # symbol's 3-month return in excess of the composite index.
                raw[symbol][spec.key] = relative_values.get(symbol)
                continue
            try:
                raw[symbol][spec.key] = _metric_value(spec.metric, cut, lookback=spec.lookback)
            except Exception:
                raw[symbol][spec.key] = None

    notes: list[str] = []
    if index_status.available:
        notes.append(
            "relative_strength computed against the official NEPSE composite "
            f"({index_status.bars} bars, 60d return "
            f"{index_status.benchmark_return_60d:.4f})"
        )
    if unavailable:
        notes.append(
            "Unavailable factors (weight 0, excluded from scoring): "
            + ", ".join(sorted(unavailable))
        )

    # Nothing survived the as_of/min_bars gate. That is a normal, reportable
    # outcome (e.g. ranking at a date too early for the stored history), not a
    # malformed request - say so instead of erroring.
    if not retained:
        too_short.sort(key=lambda e: e.symbol)
        return RankResult(
            ranked=[],
            excluded=too_short,
            factors=specs,
            weights={s.key: s.weight for s in active},
            unavailable=unavailable,
            as_of=cfg.as_of,
            universe_size=len(frames),
            notes=notes
            + [
                f"no symbol has at least {cfg.min_bars} bars on or before "
                f"{cfg.as_of or 'the latest date'}; nothing could be ranked"
            ],
            benchmark=benchmark_info,
        )

    # ---- cross-sectional median substitution for missing factors ----------
    medians: dict[str, float] = {}
    for spec in active:
        observed = [v for v in (raw[s].get(spec.key) for s in raw) if v is not None]
        if observed:
            medians[spec.key] = float(np.median(observed))

    effective = {s.key: s.weight for s in active if s.key in medians}
    weight_sum = sum(effective.values())
    if weight_sum <= 0:
        raise ValueError("no factor has both a positive weight and observed data")

    ranked: list[RankedSymbol] = []
    excluded: list[RankedSymbol] = []

    for symbol in sorted(retained):
        values = raw[symbol]
        missing = [k for k in effective if values.get(k) is None]
        n_factors = len(effective)
        missing_fraction = (len(missing) / n_factors) if n_factors else 1.0

        complete = missing_fraction <= cfg.max_missing_fraction
        if not complete:
            excluded.append(
                RankedSymbol(
                    symbol=symbol,
                    score=None,
                    rank=None,
                    percentiles={k: None for k in effective},
                    contributions={},
                    raw_values=dict(values),
                    missing=missing,
                    complete=False,
                    note=(
                        f"insufficient data: {len(missing)}/{n_factors} factors "
                        f"missing ({missing_fraction:.0%}), threshold "
                        f"{cfg.max_missing_fraction:.0%}"
                    ),
                )
            )
            continue

        # Substitute the cross-sectional median for anything still missing,
        # and record it so the substitution is auditable.
        filled = {
            k: (values.get(k) if values.get(k) is not None else medians.get(k)) for k in effective
        }
        ranked.append(
            RankedSymbol(
                symbol=symbol,
                score=None,
                rank=None,
                percentiles={},
                contributions={},
                raw_values=dict(values),
                missing=missing,
                complete=not missing,
                filled={k: float(v) for k, v in filled.items() if v is not None},
                note=("median-substituted for: " + ", ".join(missing) if missing else ""),
            )
        )

    # ---- percentile rank each factor across the retained universe ---------
    for spec in active:
        if spec.key == SECTOR_FACTOR_KEY:
            # Ranked within each sector, not across the universe; the values
            # were computed that way in the collection stage.
            continue
        if spec.key == RELATIVE_STRENGTH_KEY:
            # Already a cross-sectional percentile of excess return, computed
            # in the collection stage; re-ranking would distort it.
            continue
        obs = {s.symbol: s.filled[spec.key] for s in ranked if spec.key in s.filled}
        if not obs:
            continue
        pct = _percentile_rank(obs)
        for sym, p in pct.items():
            entry = next(r for r in ranked if r.symbol == sym)
            entry.percentiles[spec.key] = p if spec.higher_is_better else 100.0 - p

    if sector_values:
        for entry in ranked:
            entry.percentiles[SECTOR_FACTOR_KEY] = raw[entry.symbol].get(SECTOR_FACTOR_KEY)
    if relative_values:
        for entry in ranked:
            entry.percentiles[RELATIVE_STRENGTH_KEY] = raw[entry.symbol].get(RELATIVE_STRENGTH_KEY)

    # ---- weighted composite + per-factor contribution ---------------------
    for entry in ranked:
        score = 0.0
        contributions: dict[str, float] = {}
        for spec in active:
            p = entry.percentiles.get(spec.key)
            if p is None or spec.key not in effective:
                continue
            share = effective[spec.key] / weight_sum
            contrib = share * p
            contributions[spec.key] = round(contrib, 4)
            score += contrib
        entry.score = round(score, 4)
        entry.contributions = contributions

    ranked.sort(key=lambda r: r.score if r.score is not None else -1.0, reverse=True)
    for i, entry in enumerate(ranked, start=1):
        entry.rank = i

    excluded.extend(too_short)
    excluded.sort(key=lambda e: e.symbol)
    return RankResult(
        ranked=ranked,
        excluded=excluded,
        factors=specs,
        weights=dict(effective),
        unavailable=unavailable,
        as_of=cfg.as_of,
        universe_size=len(frames),
        notes=notes,
        benchmark=benchmark_info,
    )
