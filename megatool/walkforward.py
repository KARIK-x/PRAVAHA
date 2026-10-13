"""Walk-forward validation of the multi-factor ranking.

The question this module answers
--------------------------------
``/api/rank`` ranks the universe **today**. That is a description of the
present, not evidence that the ranking is any use. The honest test is:
*at every past date*, rank using only the data available then, hold the top
quantile for one rebalance period, and measure what actually happened next.

What it deliberately does **not** do
-----------------------------------
It does not claim the ranking works. It reports a number, a random baseline to
compare it against, and the reasons the number is optimistic. The three that
matter most:

* **Survivorship bias.** The store holds the companies that still exist. Any
  symbol delisted before the present day is simply absent from its own past,
  which flatters every historical result. This cannot be corrected from inside
  this dataset; it can only be disclosed. It is reported on every result.
* **No costs.** Spreads are gross. ``BacktestConfig.fee_rate`` is a PLACEHOLDER
  (KNOWN_BUGS B-11) and nothing here charges brokerage, the SEBON fee or the
  Nepal capital-gains tax, so a small observed spread would not survive
  trading it.
* **Price/volume factors only.** The fundamental factors the ranking declares
  unavailable (P/E, P/B, yield, index- and sector-relative) have zero weight
  today, so this validates the five price/volume factors and nothing else.

Chronology
----------
Ranking at date ``T`` uses only bars on or before ``T``; the forward return is
measured from ``T`` to the next rebalance date ``T'``. ``T'`` is *outcome*
data, not signal data, so using it is the point of the exercise. Changing any
bar after ``T`` must not change the portfolio formed at ``T`` — that is pinned
by ``test_a_bar_after_the_rebalance_cannot_change_that_periods_portfolio``.

Efficiency, without duplicating a formula
-----------------------------------------
Calling :func:`megatool.ranking.rank_universe` once per period costs ~10 s on
the real store, mostly recomputing trailing indicators over thousands of bars
that cannot affect the answer. Every ranking factor is a trailing window (the
widest is ``distance_from_high_52w`` at 250 bars), so each symbol's frame is
trimmed to its last :data:`FACTOR_HISTORY_WINDOW` bars **at or before** the
rebalance date before ranking. That reuses the real factor code rather than
reimplementing it, and the equivalence is asserted, not assumed — see
``test_the_trim_used_for_speed_returns_exactly_the_same_ranking``.

Trimming must happen *after* truncating at ``as_of``: trimming the full frame
and then truncating would leave a historical rebalance date with only the
sub-sequence that happens to fall in the final window, silently starving old
dates of history.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from megatool.ranking import DEFAULT_WEIGHTS, RankConfig, rank_universe

#: Widest trailing window any ranking factor needs. `distance_from_high_52w`
#: looks back 250 bars; the others need 121, 21 and 20. Keep in step with
#: `PRICE_FACTORS` in megatool/ranking.py — if a factor ever needs more
#: history than this, `test_the_trim_used_for_speed_returns_exactly_the_same_ranking`
#: fails rather than the results quietly changing.
FACTOR_HISTORY_WINDOW = 250

#: Rebalance frequencies accepted by :func:`rebalance_dates`.
FREQUENCIES: dict[str, str] = {
    "M": "monthly",
    "Q": "quarterly",
}

#: Reasons a historical walk-forward number is optimistic, attached to every
#: result so it cannot be quoted without them.
CAVEATS: list[str] = [
    "SURVIVORSHIP BIAS: the store holds only companies still listed today, so "
    "symbols delisted in the past are missing from their own history. Every "
    "figure here is therefore optimistic by an unknown amount.",
    "NO TRANSACTION COSTS: spreads are gross of brokerage, the SEBON fee and "
    "Nepal capital-gains tax. BacktestConfig.fee_rate is a PLACEHOLDER "
    "(KNOWN_BUGS B-11), so no cost can be charged honestly yet.",
    "PRICE/VOLUME FACTORS ONLY: P/E, P/B, dividend yield and index-relative "
    "factors are declared unavailable and carry zero weight, so this validates "
    "the five price/volume factors and nothing else.",
    "EQUAL-WEIGHT, CLOSE-TO-CLOSE: each quantile is held at equal weight and "
    "rebalanced on the last trading day of the period, which assumes every "
    "holding can be traded at that day's close.",
    "RESEARCH, NOT ADVICE: past spreads are not evidence of future returns.",
]


def _date_column(df: pd.DataFrame) -> str:
    """``trading_date`` for store frames, ``date`` for test fixtures."""
    return "trading_date" if "trading_date" in df.columns else "date"


def rebalance_dates(
    frames: dict[str, pd.DataFrame],
    frequency: str = "M",
    start: str | None = None,
    end: str | None = None,
) -> list[str]:
    """Last trading day of each period present in the data, ascending.

    ``frequency`` is a pandas offset alias restricted to :data:`FREQUENCIES`
    so a typo cannot silently produce daily rebalancing.
    """
    if frequency not in FREQUENCIES:
        raise ValueError(f"unknown frequency {frequency!r}; expected one of {sorted(FREQUENCIES)}")
    index: set[pd.Timestamp] = set()
    for frame in frames.values():
        if frame is None or not len(frame):
            continue
        col = _date_column(frame)
        if col not in frame.columns:
            continue
        index.update(pd.DatetimeIndex(frame[col]))
    if not index:
        return []
    series = pd.Series(sorted(index))
    # "Last trading day of the period" = the max observed date per period.
    grouped = series.groupby(series.dt.to_period(frequency)).max()
    out = [str(ts.date()) for ts in grouped]
    if start:
        out = [d for d in out if d >= start]
    if end:
        out = [d for d in out if d <= end]
    return out


def _trimmed_frames(
    frames: dict[str, pd.DataFrame], as_of: str, window: int
) -> dict[str, pd.DataFrame]:
    """Each symbol's last ``window`` bars on or before ``as_of``.

    Truncation comes first (so a rebalance date never sees future bars) and
    trimming second (so an old date keeps its own recent history rather than
    the tail of the whole series). The window is never smaller than
    ``min_bars`` at the call site, so the ranker's eligibility gate sees the
    same answer it would have seen on the full frame.
    """
    out: dict[str, pd.DataFrame] = {}
    stamp = pd.Timestamp(as_of)
    for symbol, frame in frames.items():
        if frame is None or not len(frame):
            out[symbol] = frame
            continue
        col = _date_column(frame)
        cut = frame[frame[col] <= stamp]
        out[symbol] = cut.tail(window)
    return out


#: A forward price older than this many calendar days is flagged as stale.
#: NEPSE has many illiquid names that trade rarely, so a forward price is
#: carried forward from the last close on or before the target date; this
#: threshold marks the ones where that carry is long enough to matter.
STALE_DAYS = 30


def _forward_return(frame: pd.DataFrame, start: str, end: str) -> tuple[float, int] | None:
    """Close-to-close return between two dates, or ``None`` if unmeasurable.

    Uses the **last close on or before** each date rather than requiring an
    exact match. Requiring an exact match silently drops every symbol that
    did not trade on the rebalance day — on the real store that is 9.5% of a
    period, and the drops are not random (they are the suspended names), so
    the surviving sample is biased toward liquid stocks.

    Carrying a price forward has its own cost: a name suspended for months
    reports a return of zero rather than its true outcome. That is why the
    staleness of the end price is returned alongside the return, so a period
    built mostly on stale prices can be identified instead of trusted.

    Returns ``(return, stale_days)`` where ``stale_days`` is the gap between
    the bar actually used for the end price and the target end date, or
    ``None`` when the symbol has no close on or before ``start`` (it was
    delisted before the period began, so there is no honest return to report).
    """
    if frame is None or not len(frame):
        return None
    col = _date_column(frame)
    a = frame[frame[col] <= pd.Timestamp(start)]
    if a.empty:
        return None
    c0 = float(a["close"].iloc[-1])
    b = frame[frame[col] <= pd.Timestamp(end)]
    if b.empty:
        return None
    c1 = float(b["close"].iloc[-1])
    if not c0 or math.isnan(c0) or math.isnan(c1):
        return None
    stale = int((pd.Timestamp(end) - b[col].iloc[-1]).days)
    return c1 / c0 - 1.0, stale


@dataclass(slots=True)
class WalkForwardConfig:
    """How to run the walk-forward."""

    frequency: str = "M"
    start: str | None = None
    end: str | None = None
    #: Fraction of the ranked universe in each tail portfolio.
    top_quantile: float = 0.25
    min_bars: int = 60
    max_missing_fraction: float = 0.5
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    trim_window: int = FACTOR_HISTORY_WINDOW
    #: Random draws for the chance baseline; fixed so a run is reproducible.
    permutations: int = 200
    random_seed: int = 20261012

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.frequency not in FREQUENCIES:
            problems.append(f"frequency must be one of {sorted(FREQUENCIES)}")
        if not 0.0 < self.top_quantile <= 0.5:
            problems.append("top_quantile must be between 0 and 0.5")
        if self.min_bars < 1:
            problems.append("min_bars must be >= 1")
        if self.trim_window < 1:
            problems.append("trim_window must be >= 1")
        if self.permutations < 0:
            problems.append("permutations must be >= 0")
        if self.start and self.end and self.start > self.end:
            problems.append("start must not be after end")
        return problems

    @property
    def factor_window(self) -> int:
        """Trim width: enough history for the widest factor *and* the gate."""
        return max(self.trim_window, self.min_bars)

    @property
    def frequency_label(self) -> str:
        return FREQUENCIES.get(self.frequency, self.frequency)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frequency": self.frequency,
            "frequency_label": FREQUENCIES.get(self.frequency, self.frequency),
            "start": self.start,
            "end": self.end,
            "top_quantile": self.top_quantile,
            "min_bars": self.min_bars,
            "weights": dict(self.weights),
            "trim_window": self.trim_window,
            "permutations": self.permutations,
            "random_seed": self.random_seed,
        }


@dataclass(slots=True)
class PeriodResult:
    """One rebalance period: what was chosen at ``as_of``, and what happened."""

    as_of: str
    next_rebalance: str | None
    universe: int
    long_symbols: list[str]
    short_symbols: list[str]
    long_return: float | None
    short_return: float | None
    benchmark_return: float | None
    spread: float | None
    missing_outcome: list[str] = field(default_factory=list)
    #: Ranked symbols whose forward price is older than :data:`STALE_DAYS`.
    #: Reported, never silently dropped: a period built mostly on stale prices
    #: is a period about illiquid names, and that is a finding in itself.
    stale_outcome: list[str] = field(default_factory=list)
    note: str = ""
    #: Every ranked symbol with a measurable forward return, kept for the
    #: chance baseline. Excluded from ``to_dict`` because a few hundred symbols
    #: per period would dwarf the report; the counts are in ``universe`` and
    #: ``missing_outcome``.
    outcome_returns: dict[str, float] = field(default_factory=dict)

    @property
    def used(self) -> bool:
        """True when the period produced a usable spread."""
        return self.spread is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "next_rebalance": self.next_rebalance,
            "universe": self.universe,
            "long_symbols": self.long_symbols,
            "short_symbols": self.short_symbols,
            "long_return": self.long_return,
            "short_return": self.short_return,
            "benchmark_return": self.benchmark_return,
            "spread": self.spread,
            "missing_outcome": self.missing_outcome,
            "stale_outcome": self.stale_outcome,
            "note": self.note,
            "used": self.used,
        }


@dataclass(slots=True)
class WalkForwardResult:
    """Every period plus the summary and the reasons to discount it."""

    config: WalkForwardConfig
    periods: list[PeriodResult]
    skipped_periods: list[PeriodResult]
    # summary
    periods_used: int = 0
    mean_spread: float | None = None
    median_spread: float | None = None
    spread_std: float | None = None
    hit_rate: float | None = None
    mean_long: float | None = None
    mean_short: float | None = None
    mean_benchmark: float | None = None
    cumulative_long: float | None = None
    cumulative_short: float | None = None
    cumulative_benchmark: float | None = None
    #: Ranked symbols whose forward price was older than :data:`STALE_DAYS`,
    #: summed over all used periods. A large number means much of the result
    #: rests on prices that were carried forward, not traded.
    stale_symbols_total: int = 0
    # chance baseline
    chance_mean_spread: float | None = None
    chance_p95_spread: float | None = None
    observed_percentile: float | None = None
    beats_chance: bool | None = None
    caveats: list[str] = field(default_factory=lambda: list(CAVEATS))
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "summary": {
                "periods_used": self.periods_used,
                "periods_skipped": len(self.skipped_periods),
                "mean_spread": self.mean_spread,
                "median_spread": self.median_spread,
                "spread_std": self.spread_std,
                "hit_rate": self.hit_rate,
                "mean_long": self.mean_long,
                "mean_short": self.mean_short,
                "mean_benchmark": self.mean_benchmark,
                "cumulative_long": self.cumulative_long,
                "cumulative_short": self.cumulative_short,
                "cumulative_benchmark": self.cumulative_benchmark,
                "stale_symbols_total": self.stale_symbols_total,
            },
            "chance_baseline": {
                "permutations": self.config.permutations,
                "random_seed": self.config.random_seed,
                "mean_spread": self.chance_mean_spread,
                "p95_spread": self.chance_p95_spread,
                "observed_percentile": self.observed_percentile,
                "beats_chance": self.beats_chance,
                "what_it_means": (
                    "Mean spread obtained by assigning the same number of symbols to "
                    "each tail at random, every period, over the same dates. If the "
                    "observed spread sits inside this distribution, the ranking has "
                    "not been shown to do better than picking names out of a hat."
                ),
            },
            "caveats": list(self.caveats),
            "notes": list(self.notes),
            "periods": [p.to_dict() for p in self.periods],
            "skipped_periods": [p.to_dict() for p in self.skipped_periods],
        }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _chance_spread(periods: list[PeriodResult], rng: random.Random) -> float | None:
    """One random draw of the null: same universe, same dates, no ranking.

    For each period, ``k`` symbols go long and a disjoint ``k`` go short,
    chosen at random from the symbols that actually produced a forward return
    — the same pool the real portfolios were drawn from. Averaging the spread
    over periods gives one draw of what the ranking would have scored had it
    been choosing names blind.

    Each period uses **its own** tail size, because the ranked universe grows
    over the history: a single global tail size would be too large for the
    early periods and the whole baseline would be abandoned for want of one
    period.

    Returns ``None`` when no period had enough symbols for two disjoint tails,
    so an unusable draw is discarded rather than counted as a zero spread.
    """
    spreads: list[float] = []
    for p in periods:
        k = len(p.long_symbols)
        pool = list(p.outcome_returns)
        if k < 1 or len(pool) < 2 * k:
            continue
        rng.shuffle(pool)
        long_r = _mean([p.outcome_returns[s] for s in pool[:k]])
        short_r = _mean([p.outcome_returns[s] for s in pool[k : 2 * k]])
        if long_r is None or short_r is None:
            continue
        spreads.append(long_r - short_r)
    return _mean(spreads)


def walk_forward(
    frames: dict[str, pd.DataFrame], config: WalkForwardConfig | None = None
) -> WalkForwardResult:
    """Rank at each period end, hold the tails, measure what happened next.

    Parameters
    ----------
    frames:
        symbol -> OHLCV frame ascending by date. Loaded once and reused; the
        store is never touched inside the loop.
    config:
        Rebalance frequency, quantiles and weights. See :class:`WalkForwardConfig`.
    """
    cfg = config or WalkForwardConfig()
    problems = cfg.validate()
    if problems:
        raise ValueError("; ".join(problems))

    dates = rebalance_dates(frames, cfg.frequency, cfg.start, cfg.end)
    if len(dates) < 2:
        return WalkForwardResult(
            config=cfg,
            periods=[],
            skipped_periods=[],
            notes=[
                f"only {len(dates)} rebalance date(s) available; a walk-forward "
                "comparison needs at least two consecutive periods"
            ],
        )

    rank_cfg = RankConfig(
        weights=dict(cfg.weights),
        min_bars=cfg.min_bars,
        max_missing_fraction=cfg.max_missing_fraction,
    )
    window = cfg.factor_window

    periods: list[PeriodResult] = []
    skipped: list[PeriodResult] = []

    for as_of, nxt in zip(dates, dates[1:], strict=False):
        result = rank_universe(_trimmed_frames(frames, as_of, window), rank_cfg)
        ranked = [r for r in result.ranked if r.rank is not None and r.score is not None]
        if not ranked:
            skipped.append(
                PeriodResult(
                    as_of=as_of,
                    next_rebalance=nxt,
                    universe=0,
                    long_symbols=[],
                    short_symbols=[],
                    long_return=None,
                    short_return=None,
                    benchmark_return=None,
                    spread=None,
                    note=f"no symbol was rankable at {as_of}; skipped",
                )
            )
            continue

        ordered = sorted(ranked, key=lambda r: r.rank if r.rank is not None else 10**9)
        # Tradeability gate. A symbol whose last bar is older than STALE_DAYS
        # before T could not have been bought at T's close: it was suspended,
        # suspended-then-relisted, or delisted. Ranking it is meaningless (its
        # "momentum" is measured over the gap) and holding it is impossible, so
        # it is dropped from this period's universe rather than allowed to
        # contaminate the tails. This is universe construction, not a strategy
        # parameter: on the real store 20.3% of ranked symbol-periods were
        # stale, with a p90 gap of 692 days, so leaving them in made the
        # "forward return" a multi-year return measured from a price the
        # portfolio never held. The count is reported, never hidden.
        tradeable: list[Any] = []
        dropped_stale = 0
        as_of_ts = pd.Timestamp(as_of)
        for r in ordered:
            f = frames.get(r.symbol)
            if f is None or not len(f):
                dropped_stale += 1
                continue
            col = _date_column(f)
            last = f[f[col] <= as_of_ts][col]
            if last.empty or int((as_of_ts - last.iloc[-1]).days) > STALE_DAYS:
                dropped_stale += 1
                continue
            tradeable.append(r)
        ordered = tradeable
        symbols = [r.symbol for r in ordered]
        k = max(1, int(round(len(symbols) * cfg.top_quantile)))
        if len(symbols) < 2 * k:
            skipped.append(
                PeriodResult(
                    as_of=as_of,
                    next_rebalance=nxt,
                    universe=len(symbols),
                    long_symbols=[],
                    short_symbols=[],
                    long_return=None,
                    short_return=None,
                    benchmark_return=None,
                    spread=None,
                    note=(
                        f"only {len(symbols)} symbols ranked at {as_of}, fewer than "
                        f"the {2 * k} needed for two tails of {k}; skipped"
                    ),
                )
            )
            continue

        long_names = [r.symbol for r in ordered[:k]]
        short_names = [r.symbol for r in ordered[-k:]]

        returns: dict[str, float] = {}
        missing: list[str] = []
        stale: list[str] = []
        for sym in symbols:
            value = _forward_return(frames.get(sym), as_of, nxt)
            if value is None:
                missing.append(sym)
                continue
            ret, stale_days = value
            returns[sym] = ret
            if stale_days > STALE_DAYS:
                stale.append(sym)

        long_r = _mean([returns[s] for s in long_names if s in returns])
        short_r = _mean([returns[s] for s in short_names if s in returns])
        bench_r = _mean(list(returns.values()))
        spread = None if long_r is None or short_r is None else long_r - short_r

        periods.append(
            PeriodResult(
                as_of=as_of,
                next_rebalance=nxt,
                universe=len(symbols),
                long_symbols=long_names,
                short_symbols=short_names,
                long_return=long_r,
                short_return=short_r,
                benchmark_return=bench_r,
                spread=spread,
                missing_outcome=sorted(missing),
                stale_outcome=sorted(stale),
                outcome_returns=returns,
                note="; ".join(
                    n
                    for n in (
                        (
                            f"{dropped_stale} symbol(s) last traded more than "
                            f"{STALE_DAYS}d before {as_of} and were excluded as "
                            f"untradeable"
                            if dropped_stale
                            else ""
                        ),
                        (
                            f"{len(missing)} ranked symbol(s) had no close on or "
                            f"before {nxt} and were dropped rather than imputed"
                            if missing
                            else ""
                        ),
                    )
                    if n
                ),
            )
        )

    used = [p for p in periods if p.used]
    spreads = [p.spread for p in used if p.spread is not None]
    longs = [p.long_return for p in used if p.long_return is not None]
    shorts = [p.short_return for p in used if p.short_return is not None]
    benches = [p.benchmark_return for p in used if p.benchmark_return is not None]

    out = WalkForwardResult(config=cfg, periods=periods, skipped_periods=skipped)
    out.periods_used = len(used)
    out.mean_spread = _mean(spreads)
    out.median_spread = _quantile(spreads, 0.5)
    out.spread_std = _std(spreads)
    out.hit_rate = sum(1 for s in spreads if s > 0) / len(spreads) if spreads else None
    out.mean_long = _mean(longs)
    out.mean_short = _mean(shorts)
    out.mean_benchmark = _mean(benches)

    def _compound(values: list[float]) -> float | None:
        if not values:
            return None
        acc = 1.0
        for v in values:
            acc *= 1.0 + v
        return acc

    out.cumulative_long = _compound(longs)
    out.cumulative_short = _compound(shorts)
    out.cumulative_benchmark = _compound(benches)
    out.stale_symbols_total = sum(len(p.stale_outcome) for p in used)

    # Chance baseline. One RNG seeded once, so the whole run is reproducible
    # and successive draws differ from each other.
    if cfg.permutations > 0 and used:
        rng = random.Random(cfg.random_seed)
        draws = [
            d for d in (_chance_spread(used, rng) for _ in range(cfg.permutations)) if d is not None
        ]
        if draws:
            out.chance_mean_spread = _mean(draws)
            out.chance_p95_spread = _quantile(draws, 0.95)
            if out.mean_spread is not None:
                above = sum(1 for d in draws if d < out.mean_spread)
                out.observed_percentile = above / len(draws)
                out.beats_chance = bool(out.observed_percentile >= 0.95)
        else:
            out.notes.append(
                "chance baseline not computed: no period had enough symbols with "
                "outcomes for two disjoint tails"
            )

    if not periods and skipped:
        out.notes.append(
            f"no period produced a measurable spread; {len(skipped)} period(s) "
            "were skipped (universe too small to form two tails)"
        )
    return out
