"""Research Assistant: a deterministic analyst over stored data.

HONEST LABELLING
----------------
This is **not** a language model. There is no LLM key in this project and no
local model fits the machine (8 GB RAM). What is here instead is a rules-based
analyst: it runs named calculations over the stored bars and returns the
number, the window it came from, and the exact definition used, so every claim
can be checked.

It answers *descriptive* questions (what is the trend, how volatile, where are
the recent levels, how does it compare to the rest of the market). It
deliberately refuses *predictive* and *prescriptive* questions, and says so,
because no calculation over past prices can answer them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

#: NEPSE trades Sunday-Thursday: 5 sessions a week, roughly 250 a year. Used to
#: annualise volatility. This is a convention, not a measured calendar.
TRADING_DAYS_PER_YEAR = 250

LIMIT_MOVE_PCT = 9.5
"""A day whose close-to-close move exceeds this is flagged as a probable limit
move. NEPSE's circuit band is a rule that changes; 9.5% is a detection
threshold, not a claim about the current rule."""

TOPICS = ("trend", "momentum", "risk", "volume", "levels", "relative", "data")

TOPIC_HELP = {
    "trend": "Where price sits against its own moving averages and its 52-week range.",
    "momentum": "Returns over 1/3/6/12 months, RSI(14), distance from the 20-day high.",
    "risk": "Realised volatility, worst drawdown, largest one-day fall, limit-move days.",
    "volume": "Recent volume against its own 90-day average.",
    "levels": "Nearest recent swing highs and lows (20-bar pivots).",
    "relative": "3-month return ranked against every other stored symbol.",
    "data": "Coverage, gaps and known quality problems in this symbol's history.",
}


@dataclass
class Finding:
    """One checkable number with its provenance."""

    topic: str
    name: str
    value: Any
    unit: str
    window: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchReport:
    symbol: str
    as_of: str
    bars: int
    first_date: str
    findings: list[Finding] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["findings"] = [f.to_dict() for f in self.findings]
        return d


def _sma(values: np.ndarray, n: int) -> float | None:
    if len(values) < n:
        return None
    x = float(np.mean(values[-n:]))
    return None if np.isnan(x) else x


def _pct_change(values: np.ndarray, n: int) -> float | None:
    """Percentage change over the last ``n`` trading days."""
    if len(values) <= n or values[-n - 1] == 0:
        return None
    return round(float((values[-1] / values[-n - 1] - 1.0) * 100.0), 4)


def _volatility(closes: np.ndarray, n: int) -> float | None:
    """Annualised standard deviation of close-to-close returns."""
    if len(closes) <= n or n < 2:
        return None
    ret = np.diff(np.log(closes[-n - 1 :]))
    ret = ret[np.isfinite(ret)]
    if len(ret) < 2 or float(np.std(ret, ddof=1)) == 0.0:
        return None
    return round(float(np.std(ret, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR) * 100.0), 4)


def _max_drawdown(closes: np.ndarray) -> float | None:
    if len(closes) < 2:
        return None
    peak = np.maximum.accumulate(closes)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = (closes / peak - 1.0) * 100.0
    dd = dd[np.isfinite(dd)]
    return None if dd.size == 0 else round(float(dd.min()), 4)


def _swing_levels(highs: np.ndarray, lows: np.ndarray, depth: int = 20) -> dict[str, Any]:
    """Local highs/lows over a ``depth``-bar window on both sides."""
    n = len(highs)
    if n < depth * 2 + 1:
        return {"support": [], "resistance": []}
    resist, support = [], []
    for i in range(depth, n - depth):
        window_h = highs[i - depth : i + depth + 1]
        window_l = lows[i - depth : i + depth + 1]
        if highs[i] == window_h.max():
            resist.append((i, float(highs[i])))
        if lows[i] == window_l.min():
            support.append((i, float(lows[i])))
    return {"support": support, "resistance": resist}


def _fmt_level(idx: int, price: float, dates: pd.Series, last_close: float) -> dict[str, Any]:
    return {
        "price": round(price, 4),
        "date": str(dates.iloc[idx].date()),
        "distance_pct": round(float((price / last_close - 1.0) * 100.0), 4),
    }


def _gaps(dates: pd.Series) -> dict[str, Any]:
    """Weekday sessions between first and last date with no stored bar.

    NEPSE trades Sunday-Thursday. Business days are Monday-Friday, so Sundays
    are (wrongly) counted as expected sessions and Saturdays correctly are not.
    The number below is therefore an approximation of holiday/closure gaps, not
    an exact trading calendar.
    """
    expected = pd.bdate_range(dates.min(), dates.max())
    actual = set(pd.to_datetime(dates).dt.date)
    missing = [d for d in expected.date if d not in actual]
    return {
        "expected_weekdays": int(len(expected)),
        "stored_sessions": int(len(actual)),
        "missing_weekdays": len(missing),
        "first_missing": str(missing[0]) if missing else None,
        "last_missing": str(missing[-1]) if missing else None,
        "note": (
            "Weekdays only (Mon-Fri). NEPSE trades Sun-Thu, so Sundays appear as "
            "'missing' even on an unbroken calendar. Treat this as an upper bound "
            "on real gaps, not a count of closed days."
        ),
    }


def build_report(
    df: pd.DataFrame, symbol: str, universe: pd.DataFrame | None = None
) -> ResearchReport:
    """Build a full descriptive report for one symbol from its stored bars.

    Parameters
    ----------
    df:
        Bars for this symbol, oldest first, with columns trading_date, open,
        high, low, close, volume.
    universe:
        Optional wide close matrix (dates x symbols) for the relative-strength
        ranking.
    """
    symbol = symbol.upper()
    closes = df["close"].to_numpy(dtype=float)
    dates = df["trading_date"].reset_index(drop=True)
    report = ResearchReport(
        symbol=symbol,
        as_of=str(dates.iloc[-1].date()),
        bars=int(len(df)),
        first_date=str(dates.iloc[0].date()),
    )
    last = float(closes[-1])
    findings: list[Finding] = []
    add = findings.append

    def src(extra: str = "") -> str:
        base = f"stored price_bars for {symbol}, unadjusted"
        return f"{base}; {extra}" if extra else base

    # ------------------------------------------------------------------ trend
    for n, label in ((20, "1 month"), (50, "about 2.5 months"), (200, "about 10 months")):
        value = _sma(closes, n)
        add(
            Finding(
                "trend",
                f"sma_{n}",
                None if value is None else round(value, 4),
                "price",
                f"{n} trading days (~{label})",
                src("simple mean of the last N closes"),
            )
        )
        if value is not None:
            add(
                Finding(
                    "trend",
                    f"price_vs_sma_{n}_pct",
                    round(float((last / value - 1.0) * 100.0), 4),
                    "%",
                    f"{n} trading days",
                    src("(close / sma - 1) * 100; positive means price is above"),
                )
            )

    year = closes[-min(250, len(closes)) :]
    hi52, lo52 = float(year.max()), float(year.min())
    add(Finding("trend", "high_252", round(hi52, 4), "price", "last 250 sessions", src()))
    add(Finding("trend", "low_252", round(lo52, 4), "price", "last 250 sessions", src()))
    span = hi52 - lo52
    add(
        Finding(
            "trend",
            "position_in_52w_range_pct",
            None if span == 0 else round(float((last - lo52) / span * 100.0), 4),
            "%",
            "last 250 sessions",
            src("0 = at the 250-session low, 100 = at the high"),
        )
    )
    add(
        Finding(
            "trend",
            "pct_off_252w_high",
            round(float((last / hi52 - 1.0) * 100.0), 4),
            "%",
            "last 250 sessions",
            src("negative means below the high"),
        )
    )

    # -------------------------------------------------------------- momentum
    for n, label in ((21, "1 month"), (63, "3 months"), (126, "6 months"), (250, "1 year")):
        add(
            Finding(
                "momentum",
                f"return_{n}d_pct",
                _pct_change(closes, n),
                "%",
                f"{n} trading days (~{label})",
                src("(close[t] / close[t-n] - 1) * 100"),
            )
        )
    if len(closes) >= 15:
        gain = np.diff(closes[-15:])
        up, down = gain[gain > 0].sum(), -gain[gain < 0].sum()
        rsi = None if up + down == 0 else round(100.0 - 100.0 / (1.0 + up / (down or 1e-12)), 4)
    else:
        rsi = None
    add(
        Finding(
            "momentum",
            "rsi_14",
            rsi,
            "0-100",
            "14 sessions",
            "sum of up-moves vs down-moves over the last 14 closes (simple, not "
            "Wilder-smoothed - use the charting terminal for the smoothed series)",
        )
    )
    hi20 = float(closes[-min(20, len(closes)) :].max())
    add(
        Finding(
            "momentum",
            "pct_below_20d_high",
            round(float((last / hi20 - 1.0) * 100.0), 4),
            "%",
            "20 sessions",
            src("(close / 20-day high - 1) * 100"),
        )
    )

    # ------------------------------------------------------------------- risk
    for n, label in ((20, "1 month"), (60, "3 months"), (250, "1 year")):
        add(
            Finding(
                "risk",
                f"volatility_{n}d_annualised_pct",
                _volatility(closes, n),
                "% per year",
                f"{n} sessions (~{label})",
                f"std-dev of log returns x sqrt({TRADING_DAYS_PER_YEAR}); close-to-close only",
            )
        )
    add(
        Finding(
            "risk",
            "max_drawdown_250d_pct",
            _max_drawdown(closes[-min(251, len(closes)) :]),
            "%",
            "last 250 sessions",
            "worst peak-to-trough fall in closes over the window",
        )
    )
    add(
        Finding(
            "risk",
            "max_drawdown_all_pct",
            _max_drawdown(closes),
            "%",
            f"all {len(closes)} sessions",
            "worst peak-to-trough fall in closes over the whole stored history",
        )
    )
    rets = np.diff(closes) / closes[:-1] * 100.0 if len(closes) > 1 else np.array([])
    if rets.size:
        worst_i = int(np.argmin(rets)) + 1
        add(
            Finding(
                "risk",
                "worst_day_pct",
                round(float(rets[worst_i - 1]), 4),
                "%",
                "worst single session in stored history",
                src(f"close-to-close change on {str(dates.iloc[worst_i].date())}"),
            )
        )
        add(
            Finding(
                "risk",
                "limit_move_days",
                int((np.abs(rets) > LIMIT_MOVE_PCT).sum()),
                "days",
                f"all {len(closes)} sessions",
                f"close-to-close |move| > {LIMIT_MOVE_PCT}%; a detection threshold, "
                "not a statement of the current circuit rule",
            )
        )

    # ----------------------------------------------------------------- volume
    vol = df["volume"].to_numpy(dtype=float)
    v20 = _sma(vol, 20)
    v90 = _sma(vol, 90)
    add(
        Finding(
            "volume",
            "volume_20d_avg",
            None if v20 is None else round(v20, 2),
            "shares",
            "20 sessions",
            src(),
        )
    )
    add(
        Finding(
            "volume",
            "volume_vs_90d_ratio",
            None if (v20 is None or not v90) else round(float(v20 / v90), 4),
            "x",
            "20 sessions vs 90 sessions",
            "20-day average volume divided by 90-day average volume; >1 means the "
            "recent month traded more shares than the prior quarter",
        )
    )
    add(
        Finding(
            "volume",
            "last_day_vs_20d_ratio",
            None if (not v20 or not np.isfinite(vol[-1])) else round(float(vol[-1] / v20), 4),
            "x",
            "last session vs 20 sessions",
            "last session's volume divided by the 20-day average",
        )
    )

    # ----------------------------------------------------------------- levels
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    levels = _swing_levels(highs, lows)
    support = [_fmt_level(i, p, dates, last) for i, p in levels["support"][-3:]][::-1]
    resistance = [_fmt_level(i, p, dates, last) for i, p in levels["resistance"][-3:]]
    add(
        Finding(
            "levels",
            "recent_swing_supports",
            support,
            "price",
            "last 3 pivot lows, 20 bars each side",
            "a bar whose low is the lowest of the 20 bars either side of it",
        )
    )
    add(
        Finding(
            "levels",
            "recent_swing_resistances",
            resistance,
            "price",
            "last 3 pivot highs, 20 bars each side",
            "a bar whose high is the highest of the 20 bars either side of it",
        )
    )

    # --------------------------------------------------------------- relative
    if universe is not None and symbol in universe.columns:
        window = universe.loc[universe[symbol].notna()]
        if len(window) > 63:
            # Measure the return INSIDE the window: first valid value within it
            # to last. Using the series' all-time first value would silently
            # turn a 3-month figure into a lifetime figure.
            recent = window.iloc[-63:]
            rets_3m: dict[str, float] = {}
            for col in universe.columns:
                s = recent[col].dropna()
                if len(s) < 20:
                    continue
                try:
                    base = float(s.iloc[0])
                    last_value = float(s.iloc[-1])
                except (TypeError, ValueError):
                    # Non-numeric column (DuckDB pivots can yield object dtype).
                    continue
                if not np.isfinite(base) or base == 0:
                    continue
                rets_3m[col] = float((last_value / base - 1.0) * 100.0)
            if rets_3m:
                mine = rets_3m.get(symbol)
                others = [v for k, v in rets_3m.items() if k != symbol]
                rank = (
                    None
                    if mine is None or not others
                    else int(sum(1 for v in others if v > mine)) + 1
                )
                add(
                    Finding(
                        "relative",
                        "return_3m_pct",
                        None if mine is None else round(mine, 4),
                        "%",
                        "63 trading days",
                        "first to last close in the window for this symbol",
                    )
                )
                add(
                    Finding(
                        "relative",
                        "peer_median_3m_pct",
                        None if not others else round(float(np.median(others)), 4),
                        "%",
                        "63 trading days",
                        f"median across {len(others)} other stored symbols with enough history",
                    )
                )
                add(
                    Finding(
                        "relative",
                        "rank_of_stored_symbols",
                        rank,
                        f"of {len(rets_3m)}",
                        "63 trading days",
                        "1 = strongest 3-month return among stored symbols; the "
                        "comparison set is only the symbols held locally, not NEPSE",
                    )
                )

    # ------------------------------------------------------------------- data
    add(
        Finding(
            "data",
            "coverage",
            {"first": report.first_date, "last": report.as_of, "bars": report.bars},
            "dates",
            "whole stored history",
            "oldest and newest stored bar for this symbol",
        )
    )
    add(
        Finding(
            "data",
            "weekday_gaps",
            _gaps(dates),
            "sessions",
            "whole stored history",
            "approximate count of weekday sessions with no stored bar",
        )
    )

    report.findings = findings

    # ----------------------------------------------------------------- limits
    report.limits = [
        "This is a rules-based calculation over stored bars, not a language "
        "model and not an opinion. Every number above carries the window and "
        "definition used to produce it.",
        "Prices are UNADJUSTED for bonus and rights issues, so a 'return' here "
        "is a price change and can be distorted by a scrip issue.",
        "It cannot see news, filings, promoter or insider activity, dividend "
        "announcements, circuit-breaker halts, or how much size would actually "
        "fill at a given price.",
        "It cannot tell you when to buy or sell, what price to target, or "
        "whether a setup will work. Those are decisions this tool refuses to "
        "make for you.",
        "A swing 'level' is simply a local high or low in the stored data. It "
        "has no force; other participants may not be looking at it.",
        "Nothing above predicts future prices, and none of it is investment advice.",
    ]

    if report.bars < 63:
        report.warnings.append(
            f"only {report.bars} bars stored for {symbol}: the 3/6/12-month and "
            "relative-strength figures are missing or based on a short window."
        )
    if report.bars < 250:
        report.warnings.append(
            "fewer than 250 bars stored, so the 250-day figures cover the whole "
            "history rather than a year."
        )
    return report


def answer(
    df: pd.DataFrame, symbol: str, question: str, universe: pd.DataFrame | None = None
) -> dict[str, Any]:
    """Answer a plain-language question about one symbol, deterministically.

    Questions are matched by keyword to a topic. Anything that asks for a
    prediction, a target, or a buy/sell instruction is answered with a refusal
    that explains why, and the descriptive topics are offered instead.
    """
    symbol = symbol.upper()
    q = (question or "").lower()
    report = build_report(df, symbol, universe)

    predictive = (
        "will ",
        "should i",
        "should we",
        "buy now",
        "sell now",
        "target price",
        "prediction",
        "predict",
        "going to",
        "gonna",
        "next week",
        "tomorrow",
        "moon",
        "guarantee",
        "sure shot",
        "tip",
        "signal",
    )
    if any(p in q for p in predictive):
        return {
            "symbol": symbol,
            "as_of": report.as_of,
            "topics": [],
            "findings": [],
            "refused": True,
            "refusal_reason": (
                "That question asks for a prediction or a trade instruction. No "
                "calculation over past prices can answer it honestly, so this tool "
                "will not produce one. There is no target price, no entry signal "
                "and no forecast of direction anywhere in this system."
            ),
            "instead_offer": {k: TOPIC_HELP[k] for k in TOPICS},
            "limits": report.limits,
        }

    topic_keys = [t for t in TOPICS if t in q]
    # A bare "how is X doing" reads as everything. An unrecognised question gets
    # no topics and a message listing what can be asked, rather than silently
    # returning the whole report.
    if not topic_keys and any(
        w in q for w in ("doing", "look", "overview", "analyse", "analyze", "research")
    ):
        topic_keys = list(TOPICS)

    findings = [f.to_dict() for f in report.findings if f.topic in topic_keys]
    return {
        "symbol": symbol,
        "as_of": report.as_of,
        "bars": report.bars,
        "refused": False,
        "topics": topic_keys,
        "matched_note": (
            "Matched topics: " + ", ".join(topic_keys)
            if topic_keys
            else "No topic matched. Ask about: " + ", ".join(TOPICS)
        ),
        "findings": findings,
        "topic_help": {k: TOPIC_HELP[k] for k in TOPICS},
        "limits": report.limits,
        "warnings": report.warnings,
    }
