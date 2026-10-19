"""NEPSE trading calendar and event-to-session alignment (Part 19).

NEPSE trades Sunday-Thursday, 11:00-15:00 Asia/Kathmandu; Friday and
Saturday are weekly holidays. Public holidays are configurable
(config/trading_calendar.json) because the official holiday list changes
yearly. When a holiday list is absent, only weekends are excluded and this
approximation is flagged in outputs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from ..normalization.timestamps import KATHMANDU, parse_timestamp, to_kathmandu

MARKET_OPEN = time(11, 0)
MARKET_CLOSE = time(15, 0)
# NEPSE weekday sessions: Sunday(6)..Thursday(3) in Python's isoweekday
# (Mon=1..Sun=7). Weekly holidays: Friday(5), Saturday(6).
_TRADING_ISOWEEKDAYS = {7, 1, 2, 3, 4}  # Sun, Mon, Tue, Wed, Thu


@dataclass
class TradingCalendar:
    holidays: set[date]
    approximated: bool = True            # True when no holiday list supplied

    @classmethod
    def from_file(cls, path: str | Path | None) -> "TradingCalendar":
        if path and Path(path).exists():
            data = json.loads(Path(path).read_text())
            hols = {date.fromisoformat(d) for d in data.get("holidays", [])}
            return cls(hols, approximated=False)
        return cls(set(), approximated=True)

    def is_trading_day(self, d: date) -> bool:
        return d.isoweekday() in _TRADING_ISOWEEKDAYS and d not in self.holidays

    def next_trading_day(self, d: date) -> date:
        d = d + timedelta(days=1)
        while not self.is_trading_day(d):
            d += timedelta(days=1)
        return d

    def trading_days_after(self, d: date, n: int) -> list[date]:
        days = []
        cur = d
        while len(days) < n:
            cur = self.next_trading_day(cur)
            days.append(cur)
        return days


def first_eligible_session(published_at: str, calendar: TradingCalendar) -> dict:
    """Map a publication timestamp to the first NEPSE session that can
    react to it. News published after 15:00 NPT or on a non-trading day
    affects the NEXT trading session, never the preceding one."""
    dt = parse_timestamp(published_at)
    if dt is None:
        return {"session_date": None, "status": "unknown_publication_time"}
    local = to_kathmandu(dt)
    d = local.date()
    if calendar.is_trading_day(d) and local.time() < MARKET_OPEN:
        session = d                       # before open: same session
    elif calendar.is_trading_day(d) and MARKET_OPEN <= local.time() <= MARKET_CLOSE:
        session = d                       # during session: same session
    else:
        session = calendar.next_trading_day(d)  # after close / holiday
    return {"session_date": session.isoformat(),
            "publication_local": local.isoformat(),
            "calendar_approximated": calendar.approximated,
            "status": "ok"}
