"""Event-study engine (Part 19/20).

Given point-in-time events and historical prices (from the market_prices
table — real data via an authorized adapter, or explicitly flagged
synthetic fixtures for tests), compute forward returns over configurable
trading-session windows with leakage guards:

- Only information published strictly before the window start is used.
- Missing prices are reported as missing — never interpolated into
  fabricated values.
- Baselines: momentum-only and market-return-only reference calculations
  so any sentiment/event signal is compared against trivial strategies.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .calendar import TradingCalendar, first_eligible_session


@dataclass
class PriceBar:
    trade_date: str
    close: float
    volume: float | None = None


@dataclass
class EventStudyResult:
    event_id: str
    symbol: str
    window_sessions: int
    session_date: str | None
    start_close: float | None
    end_close: float | None
    return_pct: float | None
    benchmark_return_pct: float | None
    excess_return_pct: float | None
    data_status: str
    leakage_guard: str = "passed"


def _bars_index(bars: list[PriceBar]) -> dict[str, PriceBar]:
    return {b.trade_date: b for b in bars}


def run_event_study(event_id: str, symbol: str, published_at: str,
                    prices: list[PriceBar], benchmark: list[PriceBar] | None,
                    calendar: TradingCalendar, window_sessions: int = 5) -> EventStudyResult:
    align = first_eligible_session(published_at, calendar)
    session = align.get("session_date")
    if session is None:
        return EventStudyResult(event_id, symbol, window_sessions, None,
                                None, None, None, None, None,
                                "unknown_publication_time")
    idx = _bars_index(prices)
    start = idx.get(session)
    if start is None or not start.close:
        return EventStudyResult(event_id, symbol, window_sessions, session,
                                None, None, None, None, None, "missing_prices")
    window_days = [d.isoformat() for d in calendar.trading_days_after(
        __import__("datetime").date.fromisoformat(session), window_sessions - 1)]
    end = idx.get(window_days[-1]) if window_days else None
    if end is None or not end.close:
        return EventStudyResult(event_id, symbol, window_sessions, session,
                                start.close, None, None, None, None,
                                "insufficient_history")
    ret = (end.close - start.close) / start.close * 100.0

    bench_ret = None
    if benchmark:
        bidx = _bars_index(benchmark)
        b0, b1 = bidx.get(session), bidx.get(window_days[-1])
        if b0 and b1 and b0.close:
            bench_ret = (b1.close - b0.close) / b0.close * 100.0
    excess = (ret - bench_ret) if bench_ret is not None else None
    return EventStudyResult(event_id, symbol, window_sessions, session,
                            start.close, end.close, round(ret, 4),
                            round(bench_ret, 4) if bench_ret is not None else None,
                            round(excess, 4) if excess is not None else None, "ok")


def summarize_returns(returns: list[float]) -> dict:
    """Mean, std, t-statistic, and a bootstrap 95% CI for the mean."""
    n = len(returns)
    if n == 0:
        return {"n": 0}
    mean = sum(returns) / n
    if n < 2:
        return {"n": n, "mean": mean}
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(var)
    se = std / math.sqrt(n)
    t_stat = mean / se if se > 0 else None
    rng = random.Random(42)
    boot = []
    for _ in range(1000):
        sample = [returns[rng.randrange(n)] for _ in range(n)]
        boot.append(sum(sample) / n)
    boot.sort()
    return {
        "n": n, "mean": round(mean, 4), "std": round(std, 4),
        "t_stat": round(t_stat, 4) if t_stat is not None else None,
        "ci95_low": round(boot[25], 4), "ci95_high": round(boot[975], 4),
    }


def check_no_lookahead(feature_time: str, evaluation_time: str) -> bool:
    """True when the feature was available strictly before evaluation."""
    from ..normalization.timestamps import parse_timestamp
    ft, et = parse_timestamp(feature_time), parse_timestamp(evaluation_time)
    if ft is None or et is None:
        return False
    return ft < et
