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
visible rather than implied.
"""

from __future__ import annotations

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
}

#: Factors the report recommends that this build cannot compute, with reasons.
UNAVAILABLE_FACTORS: dict[str, str] = {
    "pe_ratio": "Requires EPS. No verified fundamentals source is connected.",
    "pb_ratio": "Requires net worth per share. No verified fundamentals source is connected.",
    "dividend_yield": "Requires DPS. No verified fundamentals source is connected.",
    "relative_strength": (
        "Requires a published NEPSE index series. Index data is unavailable; "
        "no substitute index is asserted."
    ),
    "sector_percentile": (
        "Requires per-symbol sector classification. security_master.sector is "
        "NULL for every symbol in this store."
    ),
}

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
    as_of: str | None = None

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.min_bars < 1:
            problems.append("min_bars must be >= 1")
        if not 0.0 <= self.max_missing_fraction <= 1.0:
            problems.append("max_missing_fraction must be between 0 and 1")
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
        }


def build_factor_specs(weights: dict[str, float] | None = None) -> list[FactorSpec]:
    """Materialise factor specs from weights, including unavailable factors."""
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
) -> RankResult:
    """Rank a universe of symbols.

    Parameters
    ----------
    frames:
        symbol -> OHLCV frame, ascending by date, carrying a ``date`` column.
    config:
        Weights and thresholds; defaults to :data:`DEFAULT_WEIGHTS`.
    """
    cfg = config or RankConfig()
    problems = cfg.validate()
    if problems:
        raise ValueError("; ".join(problems))

    specs = build_factor_specs(cfg.weights)
    active = [s for s in specs if s.available and s.weight > 0]
    unavailable = {s.key: s.blurb for s in specs if not s.available}

    # ---- collect raw factor values, chronologically truncated -------------
    raw: dict[str, dict[str, float | None]] = {}
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
        raw[symbol] = {}
        for spec in active:
            try:
                raw[symbol][spec.key] = _metric_value(spec.metric, cut, lookback=spec.lookback)
            except Exception:
                raw[symbol][spec.key] = None

    notes: list[str] = []
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
        if spec.key not in medians:
            continue
        obs = {s.symbol: s.filled[spec.key] for s in ranked if spec.key in s.filled}
        if not obs:
            continue
        pct = _percentile_rank(obs)
        for sym, p in pct.items():
            entry = next(r for r in ranked if r.symbol == sym)
            entry.percentiles[spec.key] = p if spec.higher_is_better else 100.0 - p

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
    )
