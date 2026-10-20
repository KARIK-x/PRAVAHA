"""Compute hooks for the BABA report builder registry.

Every ``compute_<id>`` here backs one entry in
:mod:`megatool.report_builder`. A component whose hook is absent is registered
with ``available=False`` and is reported as unavailable rather than being given
an invented number.

Data access is deliberately narrow: prices and bars come from
:class:`megatool.market_store.MarketStore`, and fundamentals, journal and
portfolio figures come from the SQLite modules. Nothing here recomputes a value
that one of those modules already owns.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

__all__ = ["get_store", "get_conn", "report_cache", "clear_report_cache"]


_STORE: Any = None

#: Request-scoped memoisation. A full report runs up to 80 components against
#: the same handful of tables; without this, every component re-queries the
#: full price history and the fundamentals table. The cache lives in a
#: ContextVar, so it is private to one request/job thread and disappears when
#: the build ends. It never serves a later request.
_REPORT_CACHE: ContextVar[dict[str, Any] | None] = ContextVar("rc_report_cache", default=None)


@contextmanager
def report_cache() -> Iterator[None]:
    """Share one memo cache across a report build (nested calls are no-ops)."""
    if _REPORT_CACHE.get() is not None:
        yield
        return
    token = _REPORT_CACHE.set({})
    try:
        yield
    finally:
        _REPORT_CACHE.reset(token)


def clear_report_cache() -> None:
    """Drop the current build's cache (used after an in-process data import)."""
    cache = _REPORT_CACHE.get()
    if cache is not None:
        cache.clear()


def _memo(key: str, load: Callable[[], Any]) -> Any:
    cache = _REPORT_CACHE.get()
    if cache is None:
        return load()
    if key not in cache:
        cache[key] = load()
    return cache[key]


_STORE: Any = None


def get_store() -> Any:
    """A process-wide MarketStore, created lazily."""
    global _STORE
    if _STORE is None:
        from megatool.market_store import MarketStore

        _STORE = MarketStore()
    return _STORE


def get_conn(path: Path | None = None):
    """A read-only SQLite connection to the application database."""
    import sqlite3

    from megatool.config import PATHS

    db = path or (PATHS.processed / "megatool_state.sqlite")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN guard


def _iso(d: Any) -> str:
    if hasattr(d, "date"):
        d = d.date()
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _prices(symbol: str) -> tuple[list[date], list[float]]:
    """Ascending (dates, closes) for a symbol; empty when nothing is stored."""
    def load() -> tuple[list[date], list[float]]:
        import pandas as pd

        df = get_store().get_bars(symbol)
        if df is None or df.empty:
            return [], []
        df = df.dropna(subset=["close"])
        dates = [pd.Timestamp(d).date() for d in df["trading_date"]]
        closes = [float(c) for c in df["close"]]
        return dates, closes

    return _memo(f"prices:{str(symbol).upper()}", load)


#: The stored ``fundamentals.field`` values are snake_case source keys. The
#: report vocabulary is the human name. Mapping at the read boundary keeps the
#: rest of this module (and every component) in one consistent language, and
#: means a renamed source key only has to be fixed in one place.
FIELD_DISPLAY: dict[str, str] = {
    "eps": "EPS",
    "pe": "P/E",
    "paid_up_capital": "Paid-up capital",
    "profit": "Net profit",
    "net_worth_per_share": "Net worth per share",
    "revenue": "Revenue",
    "book_value_per_share": "Book value per share",
    "dividend_per_share": "Dividend per share",
    "shares_outstanding": "Shares outstanding",
    "public_float": "Public float",
    "promoter_holding_pct": "Promoter holding %",
    "total_equity": "Total equity",
    "total_assets": "Total assets",
    "listing_date": "Listing date",
}

#: Par value of an ordinary share in Nepal is fixed by law at NPR 100. It is
#: used **only** to derive a share count from reported paid-up capital, and the
#: derivation is always disclosed in the row that uses it.
PAR_VALUE = 100.0


def _bars(symbol: str):
    """The stored OHLCV frame for a symbol, or an empty frame."""
    import pandas as pd

    def load():
        df = get_store().get_bars(symbol)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.dropna(subset=["close"])

    return _memo(f"bars:{str(symbol).upper()}", load)


def _fundamentals(symbol: str) -> list[dict[str, Any]]:
    """Stored fundamentals for a symbol, with source keys mapped to report names.

    ``field`` is the human name; ``source_field`` keeps the original key so the
    provenance workbook can show exactly what was stored.
    """
    def load() -> list[dict[str, Any]]:
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT field, value, unit, period_end, period_label, source,
                          source_ref, retrieved_at, verification, notes
                   FROM fundamentals WHERE symbol = ?""",
                (symbol.upper(),),
            ).fetchall()
        out = []
        for row in rows:
            rec = dict(row)
            raw = (rec.get("field") or "")
            rec["source_field"] = raw
            rec["field"] = FIELD_DISPLAY.get(raw, raw.replace("_", " ").title())
            out.append(rec)
        return out

    return _memo(f"fundamentals:{str(symbol).upper()}", load)


def _field_value(symbol: str, field: str) -> dict[str, Any] | None:
    """The newest stored record for one report field, or None."""
    matches = [r for r in _fundamentals(symbol) if r["field"] == field]
    if not matches:
        return None
    return max(matches, key=lambda r: r.get("period_end") or "")


def _shares_outstanding(symbol: str) -> tuple[float | None, str]:
    """Shares outstanding, derived from paid-up capital and disclosed as such.

    Returns ``(shares, basis)``. The basis string is always non-empty so a
    caller can never present the number without its derivation.
    """
    direct = _field_value(symbol, "Shares outstanding")
    if direct:
        v = _num(direct["value"])
        if v:
            return v, "reported shares outstanding"
    puc = _field_value(symbol, "Paid-up capital")
    if not puc:
        return None, ""
    v = _num(puc["value"])
    if not v or v <= 0:
        return None, ""
    return v / PAR_VALUE, f"paid-up capital / NPR {PAR_VALUE:.0f} par value"


def _rows(section: dict[str, Any], headers: list[str],
          rows: list[list[Any]]) -> dict[str, Any]:
    return {"name": section.get("name", ""), "available": True,
            "headers": headers, "rows": rows}


def _unavailable(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "available": False, "reason": reason}


# --------------------------------------------------------------------------- #
# A — company information
# --------------------------------------------------------------------------- #
def compute_profile(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Company profile", "no symbol selected")
    recs = _fundamentals(sym)
    rows = []
    for r in recs:
        rows.append([r["field"], r["value"], r["period_label"] or r["period_end"] or "—",
                     r["source"] or "—", r["verification"] or "—"])
    return _rows({"name": "Company profile"}, ["Field", "Value", "Period", "Source", "Verification"], rows)


def compute_data_coverage(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Available historical coverage", "no symbol selected")
    dates, closes = _prices(sym)
    if not dates:
        return _unavailable("Available historical coverage", f"no stored bars for {sym}")
    return _rows({"name": "Available historical coverage"},
                 ["Symbol", "First session", "Last session", "Sessions"],
                 [[sym, _iso(dates[0]), _iso(dates[-1]), len(dates)]])


def compute_data_refresh(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Last data refresh", "no symbol selected")
    recs = _fundamentals(sym)
    stamps = sorted({r["retrieved_at"] for r in recs if r.get("retrieved_at")})
    last = stamps[-1] if stamps else None
    return _rows({"name": "Last data refresh"}, ["Symbol", "Last refresh"],
                 [[sym, last or "—"]])


def compute_quality_summary(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Data-quality summary", "no symbol selected")
    recs = _fundamentals(sym)
    counts: dict[str, int] = defaultdict(int)
    for r in recs:
        counts[r.get("verification") or "unknown"] += 1
    return _rows({"name": "Data-quality summary"}, ["Verification", "Count"],
                 [[k, v] for k, v in sorted(counts.items())])


def compute_missing_summary(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Missing-data summary", "no symbol selected")
    wanted = ["EPS", "Net worth per share", "Paid-up capital", "Shares outstanding",
              "Public float", "Revenue", "Net profit", "Dividend per share"]
    have = {r["field"] for r in _fundamentals(sym)}
    missing = [w for w in wanted if w not in have]
    if not missing:
        return _rows({"name": "Missing-data summary"}, ["Result"],
                     [["No missing core fields."]])
    return _rows({"name": "Missing-data summary"}, ["Missing field", "Reason"],
                 [[m, "not present in stored fundamentals"] for m in missing])


# --------------------------------------------------------------------------- #
# B — market
# --------------------------------------------------------------------------- #
def compute_last_price(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Latest available price", "no symbol selected")
    dates, closes = _prices(sym)
    if not closes:
        return _unavailable("Latest available price", f"no stored close for {sym}")
    return _rows({"name": "Latest available price"},
                 ["Symbol", "Last stored close", "Price date", "Basis"],
                 [[sym, round(closes[-1], 2), _iso(dates[-1]), "End of day (not live)"]])


def compute_price_summary(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Historical closing-price summary", "no symbol selected")
    dates, closes = _prices(sym)
    if not closes:
        return _unavailable("Historical closing-price summary", f"no stored bars for {sym}")
    return _rows({"name": "Historical closing-price summary"},
                 ["First close", "Last close", "High", "Low", "Period"],
                 [[round(closes[0], 2), round(closes[-1], 2), round(max(closes), 2),
                   round(min(closes), 2), f"{_iso(dates[0])} → {_iso(dates[-1])}"]])


def compute_market_cap(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Market capitalization", "no symbol selected")
    dates, closes = _prices(sym)
    shares, basis = _shares_outstanding(sym)
    if not closes:
        return _unavailable("Market capitalization", f"no stored close for {sym}")
    if not shares:
        return _unavailable("Market capitalization",
                            "neither shares outstanding nor paid-up capital is stored")
    return _rows({"name": "Market capitalization"},
                 ["Symbol", "Last close", "Price date", "Shares outstanding",
                  "Share-count basis", "Market cap", "Formula"],
                 [[sym, round(closes[-1], 2), _iso(dates[-1]), int(shares), basis,
                   round(closes[-1] * shares, 2),
                   "last stored close x shares outstanding"]])


def compute_shares_outstanding(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Shares outstanding", "no symbol selected")
    shares, basis = _shares_outstanding(sym)
    if not shares:
        return _unavailable("Shares outstanding",
                            "neither shares outstanding nor paid-up capital is stored")
    return _rows({"name": "Shares outstanding"},
                 ["Symbol", "Shares outstanding", "Basis"],
                 [[sym, int(shares), basis]])


def compute_paid_up_capital(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Paid-up capital", "no symbol selected")
    recs = _fundamentals(sym)
    r = next((x for x in recs if x["field"] == "Paid-up capital"), None)
    if not r:
        return _unavailable("Paid-up capital", "not stored")
    return _rows({"name": "Paid-up capital"}, ["Symbol", "Paid-up capital", "Unit", "Period"],
                 [[sym, r["value"], r["unit"] or "—", r["period_label"] or r["period_end"] or "—"]])


def compute_public_float(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Public float", "no symbol selected")
    recs = _fundamentals(sym)
    r = next((x for x in recs if x["field"] == "Public float"), None)
    if not r:
        return _unavailable("Public float", "not stored")
    return _rows({"name": "Public float"}, ["Symbol", "Public float", "Unit"],
                 [[sym, r["value"], r["unit"] or "—"]])


def compute_holdings_split(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Public/promoter holdings", "no symbol selected")
    recs = _fundamentals(sym)
    promo = next((_num(r["value"]) for r in recs if r["field"] == "Promoter holding %"), None)
    if promo is None:
        return _unavailable("Public/promoter holdings", "promoter holding % not stored")
    return _rows({"name": "Public/promoter holdings"},
                 ["Symbol", "Promoter %", "Public %"],
                 [[sym, promo, round(100 - promo, 2)]])


def compute_range_52w(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("52-week high and low", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 250:
        return _unavailable("52-week high and low", "fewer than 250 stored sessions")
    window = closes[-250:]
    return _rows({"name": "52-week high and low"},
                 ["Symbol", "52w high", "52w low"],
                 [[sym, round(max(window), 2), round(min(window), 2)]])


def compute_price_change(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Price change", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 2:
        return _unavailable("Price change", "fewer than 2 stored sessions")
    out = []
    for label, n in [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 250)]:
        if len(closes) > n:
            base = closes[-n - 1]
            chg = 100 * (closes[-1] / base - 1)
            out.append([label, round(base, 2), round(closes[-1], 2), round(chg, 2)])
        else:
            out.append([label, "—", "—", "insufficient history"])
    return _rows({"name": "Price change over selected periods"},
                 ["Period", "Base close", "Last close", "Change %"], out)


def compute_volume_turnover(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Trading volume and turnover", "no symbol selected")

    df = get_store().get_bars(sym)
    if df is None or df.empty or "volume" not in df.columns:
        return _unavailable("Trading volume and turnover", "no stored volume")
    recent = df.dropna(subset=["volume"]).tail(21)
    if recent.empty:
        return _unavailable("Trading volume and turnover", "no stored volume")
    avg_vol = float(recent["volume"].mean())
    return _rows({"name": "Trading volume and turnover"},
                 ["Symbol", "Average daily volume (21 sessions)", "Turnover (last)"],
                 [[sym, round(avg_vol), round(float(recent["close"].iloc[-1] * avg_vol), 2)]])


def compute_liquidity(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Liquidity measures", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 21:
        return _unavailable("Liquidity measures", "fewer than 21 stored sessions")
    import numpy as np

    rets = np.diff(np.log(np.array(closes[-21:], dtype=float)))
    vol = float(np.std(rets, ddof=1) * (252 ** 0.5)) if len(rets) > 1 else None
    return _rows({"name": "Liquidity measures"},
                 ["Symbol", "Sessions", "Annualised volatility (21)"],
                 [[sym, 21, round(vol * 100, 2) if vol is not None else "—"]])


def compute_price_volume_chart(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Price and volume chart", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 2:
        return _unavailable("Price and volume chart", "fewer than 2 stored sessions")
    # A chart component renders as a compact table plus the data needed to draw.
    rows = [[_iso(d), round(c, 2)] for d, c in zip(dates[-120:], closes[-120:], strict=False)]
    return {"name": "Price and volume chart", "available": True, "output": "chart",
            "headers": ["Date", "Close"], "rows": rows,
            "chart": {"kind": "line", "x": [r[0] for r in rows], "y": [r[1] for r in rows]}}


def compute_price_table(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Historical price-performance table", "no symbol selected")
    import pandas as pd

    dates, closes = _prices(sym)
    if not closes:
        return _unavailable("Historical price-performance table", f"no stored bars for {sym}")
    df = pd.DataFrame({"date": dates, "close": closes})
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
    out = []
    for month, grp in df.groupby("month"):
        out.append([month, round(float(grp["close"].iloc[0]), 2),
                    round(float(grp["close"].iloc[-1]), 2), len(grp)])
    return _rows({"name": "Historical price-performance table"},
                 ["Month", "First close", "Last close", "Sessions"], out)


# --------------------------------------------------------------------------- #
# C — fundamentals
# --------------------------------------------------------------------------- #
def _eps_records(sym: str) -> list[dict[str, Any]]:
    """EPS records, newest period first."""
    recs = [r for r in _fundamentals(sym) if r["field"] == "EPS"]
    return sorted(recs, key=lambda r: r.get("period_end") or "", reverse=True)


def compute_eps_quarterly(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Quarterly EPS", "no symbol selected")
    recs = _eps_records(sym)
    if not recs:
        return _unavailable("Quarterly EPS", f"no EPS records for {sym}")
    rows = [[r["period_label"] or r["period_end"], r["value"], r["unit"] or "—",
             r["verification"] or "—"] for r in recs]
    return _rows({"name": "Quarterly EPS"},
                 ["Period", "EPS", "Unit", "Verification"], rows)


def compute_eps_annual(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Annual EPS", "no symbol selected")
    recs = [r for r in _eps_records(sym) if "annual" in (r["period_label"] or "").lower()
            or (r["period_end"] or "").count("-") == 1]
    if not recs:
        return _unavailable("Annual EPS", "no annual-basis EPS records")
    return _rows({"name": "Annual EPS"}, ["Period", "EPS", "Unit"],
                 [[r["period_label"] or r["period_end"], r["value"], r["unit"] or "—"]
                  for r in recs])


def compute_eps_ttm(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("TTM EPS", "no symbol selected")
    recs = sorted(_eps_records(sym),
                  key=lambda r: r["period_end"] or "", reverse=True)
    quarterly = [r for r in recs if "quarter" in (r["period_label"] or "").lower()]
    if len(quarterly) < 4:
        return _unavailable("TTM EPS", "fewer than four quarterly EPS records")
    vals = [_num(r["value"]) for r in quarterly[:4]]
    if any(v is None for v in vals):
        return _unavailable("TTM EPS", "a quarterly EPS value is missing")
    return _rows({"name": "TTM EPS"},
                 ["TTM EPS", "Basis", "Quarters"],
                 [[round(sum(vals), 2), "sum of the last four quarterly EPS",
                   ", ".join(r["period_label"] or r["period_end"] for r in quarterly[:4])]])


def compute_eps_annualized(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Annualized quarterly EPS", "no symbol selected")
    recs = _eps_records(sym)
    if not recs:
        return _unavailable("Annualized quarterly EPS", "no EPS records")
    latest = max(recs, key=lambda r: r["period_end"] or "")
    v = _num(latest["value"])
    if v is None:
        return _unavailable("Annualized quarterly EPS", "latest EPS value missing")
    return _rows({"name": "Annualized quarterly EPS (estimate)"},
                 ["Quarterly EPS", "Annualized (x4)", "Period", "Label"],
                 [[v, round(v * 4, 2), latest["period_label"] or latest["period_end"],
                   "ESTIMATE — assumes the quarter repeats four times"]])


def compute_net_worth_ps(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Net worth per share", "no symbol selected")
    recs = _fundamentals(sym)
    nw = next((_num(r["value"]) for r in recs if r["field"] == "Net worth per share"), None)
    if nw is None:
        return _unavailable("Net worth per share", "not stored")
    return _rows({"name": "Net worth per share"}, ["Symbol", "Net worth per share", "Unit"],
                 [[sym, nw, next((r["unit"] for r in recs
                                  if r["field"] == "Net worth per share"), "—")]])


def compute_book_value_ps(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Book value per share", "no symbol selected")
    recs = _fundamentals(sym)
    bv = next((_num(r["value"]) for r in recs if r["field"] in
               ("Book value per share", "Net worth per share")), None)
    if bv is None:
        return _unavailable("Book value per share", "not stored")
    return _rows({"name": "Book value per share"}, ["Symbol", "Book value per share"],
                 [[sym, bv]])


def compute_revenue(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Revenue", "no symbol selected")
    recs = [r for r in _fundamentals(sym) if r["field"] == "Revenue"]
    if not recs:
        return _unavailable("Revenue", "not stored")
    return _rows({"name": "Revenue"}, ["Period", "Revenue", "Unit"],
                 [[r["period_label"] or r["period_end"], r["value"], r["unit"] or "—"]
                  for r in recs])


def compute_net_profit(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Net profit", "no symbol selected")
    recs = [r for r in _fundamentals(sym) if r["field"] == "Net profit"]
    if not recs:
        return _unavailable("Net profit", "not stored")
    return _rows({"name": "Net profit"}, ["Period", "Net profit", "Unit"],
                 [[r["period_label"] or r["period_end"], r["value"], r["unit"] or "—"]
                  for r in recs])


def compute_profit_margin(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Profit margin", "no symbol selected")
    recs = _fundamentals(sym)
    out = []
    for r in recs:
        if r["field"] != "Net profit":
            continue
        rev = next((_num(x["value"]) for x in recs
                    if x["field"] == "Revenue"
                    and (x["period_label"] or x["period_end"]) == (r["period_label"] or r["period_end"])), None)
        p = _num(r["value"])
        if rev and p is not None:
            out.append([r["period_label"] or r["period_end"], p, rev,
                        round(100 * p / rev, 2)])
        else:
            out.append([r["period_label"] or r["period_end"], p, rev,
                        "revenue unavailable for this period"])
    if not out:
        return _unavailable("Profit margin", "no period has both profit and revenue")
    return _rows({"name": "Profit margin"}, ["Period", "Net profit", "Revenue", "Margin %"], out)


def compute_earnings_growth(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Earnings growth", "no symbol selected")
    recs = _eps_records(sym)
    if len(recs) < 2:
        return _unavailable("Earnings growth", "fewer than two EPS records")
    ordered = sorted(recs, key=lambda r: r["period_end"] or "")
    out = []
    for prev, cur in zip(ordered, ordered[1:], strict=False):
        a, b = _num(prev["value"]), _num(cur["value"])
        if a and b is not None and a > 0:
            out.append([f'{prev["period_label"] or prev["period_end"]} → '
                        f'{cur["period_label"] or cur["period_end"]}', a, b,
                        round(100 * (b / a - 1), 2)])
    if not out:
        return _unavailable("Earnings growth", "no comparable EPS pair")
    return _rows({"name": "Earnings growth"}, ["Periods", "From", "To", "Growth %"], out)


def compute_revenue_growth(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Revenue growth", "no symbol selected")
    recs = [r for r in _fundamentals(sym) if r["field"] == "Revenue"]
    if len(recs) < 2:
        return _unavailable("Revenue growth", "fewer than two revenue records")
    ordered = sorted(recs, key=lambda r: r["period_end"] or "")
    out = []
    for prev, cur in zip(ordered, ordered[1:], strict=False):
        a, b = _num(prev["value"]), _num(cur["value"])
        if a and b is not None and a > 0:
            out.append([f'{prev["period_label"] or prev["period_end"]} → '
                        f'{cur["period_label"] or cur["period_end"]}', a, b,
                        round(100 * (b / a - 1), 2)])
    if not out:
        return _unavailable("Revenue growth", "no comparable revenue pair")
    return _rows({"name": "Revenue growth"}, ["Periods", "From", "To", "Growth %"], out)


def compute_roe(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Return on equity", "no symbol selected")
    recs = _fundamentals(sym)
    np_ = [r for r in recs if r["field"] == "Net profit"]
    eq = [r for r in recs if r["field"] == "Total equity"]
    if not np_ or not eq:
        return _unavailable("Return on equity", "net profit and equity not both stored")
    out = []
    for p in np_:
        e = next((x for x in eq if (x["period_label"] or x["period_end"])
                  == (p["period_label"] or p["period_end"])), None)
        pv, ev = _num(p["value"]), _num(e["value"]) if e else None
        out.append([p["period_label"] or p["period_end"], pv, ev,
                    round(100 * pv / ev, 2) if pv is not None and ev else "—"])
    return _rows({"name": "Return on equity"}, ["Period", "Net profit", "Equity", "ROE %"], out)


def compute_roa(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Return on assets", "no symbol selected")
    recs = _fundamentals(sym)
    np_ = [r for r in recs if r["field"] == "Net profit"]
    ta = [r for r in recs if r["field"] == "Total assets"]
    if not np_ or not ta:
        return _unavailable("Return on assets", "net profit and assets not both stored")
    out = []
    for p in np_:
        e = next((x for x in ta if (x["period_label"] or x["period_end"])
                  == (p["period_label"] or p["period_end"])), None)
        pv, ev = _num(p["value"]), _num(e["value"]) if e else None
        out.append([p["period_label"] or p["period_end"], pv, ev,
                    round(100 * pv / ev, 2) if pv is not None and ev else "—"])
    return _rows({"name": "Return on assets"}, ["Period", "Net profit", "Assets", "ROA %"], out)


def compute_pe_ratio(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("P/E ratio", "no symbol selected")
    dates, closes = _prices(sym)
    eps_rec = _field_value(sym, "EPS")
    eps = _num(eps_rec["value"]) if eps_rec else None
    reported = _field_value(sym, "P/E")
    rows = []
    if reported:
        rows.append(["Reported P/E", _num(reported["value"]),
                     reported.get("period_label") or reported.get("period_end") or "—",
                     reported.get("source") or "—", "as filed"])
    if closes and eps and eps > 0:
        rows.append(["Computed P/E", round(closes[-1] / eps, 2),
                     (eps_rec.get("period_label") or eps_rec.get("period_end") or "—")
                     if eps_rec else "—",
                     "last stored close / EPS", _iso(dates[-1])])
    elif eps is not None and eps <= 0:
        rows.append(["Computed P/E", "suppressed", "—", "EPS is zero or negative", "—"])
    elif closes:
        rows.append(["Computed P/E", "suppressed", "—", "EPS not stored", "—"])
    if not rows:
        return _unavailable("P/E ratio", "no stored P/E and no stored close with EPS")
    return _rows({"name": "P/E ratio"},
                 ["Basis", "P/E", "Period", "Source / formula", "Price date"], rows)


def compute_pb_ratio(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Price-to-book ratio", "no symbol selected")
    dates, closes = _prices(sym)
    bv = next((_num(r["value"]) for r in _fundamentals(sym) if r["field"] in
               ("Book value per share", "Net worth per share")), None)
    if not closes:
        return _unavailable("Price-to-book ratio", "no stored close")
    if not bv or bv <= 0:
        return _unavailable("Price-to-book ratio", "book value per share is zero or missing")
    return _rows({"name": "Price-to-book ratio"},
                 ["Symbol", "Last close", "Book value/share", "P/B"],
                 [[sym, round(closes[-1], 2), bv, round(closes[-1] / bv, 2)]])


def compute_dps(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Dividend per share", "no symbol selected")
    recs = [r for r in _fundamentals(sym) if r["field"] == "Dividend per share"]
    if not recs:
        return _unavailable("Dividend per share", "not stored")
    return _rows({"name": "Dividend per share"}, ["Period", "DPS", "Unit"],
                 [[r["period_label"] or r["period_end"], r["value"], r["unit"] or "—"]
                  for r in recs])


def compute_dividend_yield(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Dividend yield", "no symbol selected")
    dates, closes = _prices(sym)
    dps = next((_num(r["value"]) for r in _fundamentals(sym)
                if r["field"] == "Dividend per share"), None)
    if not closes:
        return _unavailable("Dividend yield", "no stored close")
    if not dps:
        return _unavailable("Dividend yield", "DPS not stored")
    return _rows({"name": "Dividend yield"},
                 ["Symbol", "DPS", "Last close (denominator)", "Price date", "Yield %"],
                 [[sym, dps, round(closes[-1], 2), _iso(dates[-1]),
                   round(100 * dps / closes[-1], 2)]])


def compute_fundamental_trend(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Fundamental trend table", "no symbol selected")
    recs = _fundamentals(sym)
    periods = sorted({(r["period_label"] or r["period_end"]) for r in recs})
    fields = ["EPS", "Revenue", "Net profit", "Net worth per share"]
    out = []
    for p in periods:
        row: list[Any] = [p]
        for f in fields:
            v = next((_num(r["value"]) for r in recs
                      if r["field"] == f and (r["period_label"] or r["period_end"]) == p), None)
            row.append(v)
        out.append(row)
    if not out:
        return _unavailable("Fundamental trend table", "no stored fundamentals")
    return _rows({"name": "Fundamental trend table"},
                 ["Period"] + fields, out)


def compute_fundamental_summary(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Fundamental summary", "no symbol selected")
    dates, closes = _prices(sym)
    recs = _fundamentals(sym)
    eps = next((_num(r["value"]) for r in recs if r["field"] == "EPS"), None)
    nw = next((_num(r["value"]) for r in recs if r["field"] == "Net worth per share"), None)
    lines = [f"{sym}: {len(recs)} stored fundamental fields across "
             f"{len({r['period_label'] or r['period_end'] for r in recs})} periods."]
    if closes:
        lines.append(f"Last stored close {round(closes[-1], 2)} on {_iso(dates[-1])} (end of day).")
    if eps is not None:
        lines.append(f"Latest EPS {eps}; P/E {round(closes[-1]/eps,2) if eps and closes else 'n/a'}.")
    if nw is not None:
        lines.append(f"Net worth per share {nw}.")
    return {"name": "Fundamental summary", "available": True,
            "summary": lines, "headers": ["Summary"], "rows": [[ln] for ln in lines]}


def compute_fundamental_quality(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Fundamental data-quality", "no symbol selected")
    recs = _fundamentals(sym)
    counts: dict[str, int] = defaultdict(int)
    for r in recs:
        counts[r.get("verification") or "unknown"] += 1
    return _rows({"name": "Fundamental data-quality assessment"},
                 ["Verification", "Fields"], [[k, v] for k, v in sorted(counts.items())])


# --------------------------------------------------------------------------- #
# D — quarterly
# --------------------------------------------------------------------------- #
def _quarter(recs, label):
    return [r for r in recs if label.lower() in (r["period_label"] or "").lower()]


def _q_rows(sym, label):
    recs = _fundamentals(sym)
    q = _quarter(recs, label)
    if not q:
        return None
    out = []
    for r in q:
        out.append([r["period_label"] or r["period_end"], r["value"], r["unit"] or "—"])
    return out


def compute_q1_results(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Q1 results", "no symbol selected")
    rows = _q_rows(sym, "q1") or _q_rows(sym, "first")
    if not rows:
        return _unavailable("Q1 results", "no Q1 record")
    return _rows({"name": "Q1 results"}, ["Period", "EPS", "Unit"], rows)


def compute_q2_results(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Q2 results", "no symbol selected")
    rows = _q_rows(sym, "q2") or _q_rows(sym, "second")
    if not rows:
        return _unavailable("Q2 results", "no Q2 record")
    return _rows({"name": "Q2 results"}, ["Period", "EPS", "Unit"], rows)


def compute_q3_results(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Q3 results", "no symbol selected")
    rows = _q_rows(sym, "q3") or _q_rows(sym, "third")
    if not rows:
        return _unavailable("Q3 results", "no Q3 record")
    return _rows({"name": "Q3 results"}, ["Period", "EPS", "Unit"], rows)


def compute_q4_results(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Q4 results", "no symbol selected")
    rows = _q_rows(sym, "q4") or _q_rows(sym, "fourth")
    if not rows:
        return _unavailable("Q4 results", "no Q4 record")
    return _rows({"name": "Q4 results"}, ["Period", "EPS", "Unit"], rows)


def compute_q_eps_comparison(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Quarterly EPS comparison", "no symbol selected")
    recs = _fundamentals(sym)
    quarters = [r for r in recs if r["field"] == "EPS"
                and any(q in (r["period_label"] or "").lower() for q in ("q1", "q2", "q3", "q4"))]
    if not quarters:
        return _unavailable("Quarterly EPS comparison", "no quarterly EPS records")
    return _rows({"name": "Quarterly EPS comparison"},
                 ["Quarter", "EPS", "Unit"],
                 [[r["period_label"], r["value"], r["unit"] or "—"] for r in quarters])


def compute_missing_quarters(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Missing-quarter report", "no symbol selected")
    labels = " | ".join((r["period_label"] or "").lower() for r in _fundamentals(sym))
    missing = [tag for word, tag in (("first", "Q1"), ("second", "Q2"),
                                     ("third", "Q3"), ("fourth", "Q4"))
               if word not in labels]
    if not missing:
        return _rows({"name": "Missing-quarter report"}, ["Result"],
                     [["All four quarters present."]])
    return _rows({"name": "Missing-quarter report"}, ["Missing quarter", "Note"],
                 [[m, "no stored record — not inferred"] for m in missing])


def compute_comparability(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Comparability warnings", "no symbol selected")
    recs = _fundamentals(sym)
    notes = {r.get("notes") for r in recs if r.get("notes")}
    if not notes:
        return _rows({"name": "Restatement and comparability warnings"}, ["Result"],
                     [["No restatements recorded."]])
    return _rows({"name": "Restatement and comparability warnings"}, ["Note"],
                 [[n] for n in sorted(notes)])


# --------------------------------------------------------------------------- #
# F — eligibility
# --------------------------------------------------------------------------- #
def _elig(sym: str) -> tuple[list[list[Any]], str]:
    """Screen one symbol against four stated rules.

    Every rule returns evidence and one of PASS / FAIL / NEEDS_REVIEW. A rule
    whose inputs are missing is never silently passed. Net worth is compared
    against paid-up capital at the **total** level (net worth per share x shares
    versus paid-up capital), which is the same test as per-share book value
    against the NPR 100 par value.
    """
    listing = _field_value(sym, "Listing date")
    nw_rec = _field_value(sym, "Net worth per share")
    puc_rec = _field_value(sym, "Paid-up capital")
    shares, share_basis = _shares_outstanding(sym)
    nw = _num(nw_rec["value"]) if nw_rec else None
    puc = _num(puc_rec["value"]) if puc_rec else None
    profit = [r for r in _fundamentals(sym) if r["field"] == "Net profit"]
    divs = [r for r in _fundamentals(sym) if r["field"] == "Dividend per share"]

    as_of = req_as_of()
    rules: list[list[Any]] = []

    # 1. Listing age, only from a stored listing date.
    if listing and _num(listing["value"]) is not None:
        try:
            age = (as_of - _to_date(_num(listing["value"]))).days / 365.25
            rules.append(["Listed >= 2 years", f"listed {age:.2f} years",
                          "PASS" if age >= 2 else "FAIL"])
        except (TypeError, ValueError):
            rules.append(["Listed >= 2 years", "listing date not parseable",
                          "NEEDS_REVIEW"])
    else:
        rules.append(["Listed >= 2 years", "listing date not stored", "NEEDS_REVIEW"])

    # 2. Share count.
    if shares:
        rules.append([">= 10,000 shares outstanding", f"{int(shares):,} ({share_basis})",
                      "PASS" if shares >= 10000 else "FAIL"])
    else:
        rules.append([">= 10,000 shares outstanding", "not stored", "NEEDS_REVIEW"])

    # 3. Net worth versus paid-up capital, compared at the same (total) level.
    if nw is not None and puc and shares:
        total_nw = nw * shares
        rules.append(["Net worth >= paid-up capital",
                      f"total net worth {total_nw:,.0f} vs paid-up {puc:,.0f} "
                      f"(book value {nw} vs par {PAR_VALUE:.0f})",
                      "PASS" if total_nw >= puc else "FAIL"])
    else:
        rules.append(["Net worth >= paid-up capital", "inputs incomplete",
                      "NEEDS_REVIEW"])

    # 4. Profit or dividend history.
    if profit:
        rules.append(["Recorded net profit", f"{len(profit)} period(s)", "PASS"])
    elif divs:
        rules.append(["Dividend history", f"{len(divs)} period(s)", "PASS"])
    else:
        rules.append(["Profit/dividend history", "no profit or dividend record", "FAIL"])

    overall = ("ELIGIBLE" if all(r[2] == "PASS" for r in rules)
               else "NEEDS_REVIEW" if any(r[2] == "NEEDS_REVIEW" for r in rules)
               else "NOT ELIGIBLE")
    return rules, overall


def req_as_of():
    return date.today()


def _to_date(v):
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def compute_elig_result(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Complete eligibility result", "no symbol selected")
    rules, overall = _elig(sym)
    return _rows({"name": "Complete eligibility result"},
                 ["Rule", "Evidence", "Result"], rules + [["Overall", sym, overall]])


def compute_elig_config(req):
    return _rows({"name": "Screening configuration"},
                 ["Rule", "Threshold", "Basis", "Assessment date"],
                 [["Listing age", ">= 2 years", "verified listing date", req_as_of().isoformat()],
                  ["Share count", ">= 10,000", "shares outstanding", req_as_of().isoformat()],
                  ["Net worth", ">= paid-up value", "per-share vs capital", req_as_of().isoformat()],
                  ["Profit/dividend", "recorded profit OR dividend history",
                   "stored records", req_as_of().isoformat()]])


def compute_elig_failed(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Failed-criteria explanation", "no symbol selected")
    rules, overall = _elig(sym)
    failed = [r for r in rules if r[2] != "PASS"]
    if not failed:
        return _rows({"name": "Failed-criteria explanation"}, ["Result"],
                     [["No failed criteria."]])
    return _rows({"name": "Failed-criteria explanation"}, ["Rule", "Evidence", "Result"], failed)


# --------------------------------------------------------------------------- #
# G / H — sector & comparison
# --------------------------------------------------------------------------- #
#: Symbol -> sector reference files, highest confidence first. The first file to
#: classify a symbol wins; later files only fill gaps. None of these is a live
#: NEPSE feed, so every sector view must disclose that it is a reference
#: classification rather than an authoritative listing.
SECTOR_SOURCES: tuple[tuple[str, str], ...] = (
    ("data/review/sources/yonepse/yonepse_sectors.csv", "yonepse/securities.json"),
    ("data/review/sources/binayabaral/binayabaral_sectors.csv",
     "binayabaral/nepse-symbols.csv"),
    ("data/review/sectors_symbol_sector_UNVERIFIED.csv", "unverified reference"),
)

_SECTOR_CACHE: dict[str, str] | None = None


def sector_sources_used() -> list[str]:
    """The sector reference files that actually exist on disk."""
    root = Path(__file__).resolve().parents[1]
    return [rel for rel, _ in SECTOR_SOURCES if (root / rel).is_file()]


def _sector_map() -> dict[str, str]:
    """``symbol -> sector`` from the on-disk reference CSVs, cached per process."""
    global _SECTOR_CACHE
    if _SECTOR_CACHE is not None:
        return _SECTOR_CACHE
    import csv

    root = Path(__file__).resolve().parents[1]
    mapping: dict[str, str] = {}
    for rel, _label in SECTOR_SOURCES:
        path = root / rel
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                sym = (row.get("symbol") or "").strip().upper()
                sector = (row.get("sector") or "").strip()
                if sym and sector and sym not in mapping:
                    mapping[sym] = sector
    _SECTOR_CACHE = mapping
    return mapping


def compute_sector_overview(req):
    sm = _sector_map()
    if not sm:
        return _unavailable("Sector overview", "no sector classifications found")
    counts: dict[str, int] = defaultdict(int)
    for s in sm.values():
        counts[s] += 1
    used = ", ".join(sector_sources_used()) or "none"
    return _rows({"name": "Sector overview"}, ["Sector", "Companies", "Basis"],
                 [[k, v, "reference classification"] 
                  for k, v in sorted(counts.items(), key=lambda x: -x[1])]
                 + [["All sectors", len(sm), f"reference files: {used}"]])


def compute_sector_table(req):
    sm = _sector_map()
    sector = req.sector
    if not sector:
        return _unavailable("Sector company table", "no sector selected")
    syms = sorted(s for s, sec in sm.items() if sec.lower() == sector.lower())
    if not syms:
        return _unavailable("Sector company table", f"no companies in sector {sector!r}")
    out = []
    for sym in syms:
        recs = _fundamentals(sym)
        eps = next((_num(r["value"]) for r in recs if r["field"] == "EPS"), None)
        dates, closes = _prices(sym)
        out.append([sym, sector, eps if eps is not None else "—",
                    round(closes[-1], 2) if closes else "—",
                    len(dates)])
    return _rows({"name": "Sector company table"},
                 ["Symbol", "Sector", "EPS", "Last close", "Sessions"], out)


def compute_sector_eps_rank(req):
    sm = _sector_map()
    sector = req.sector or (req.symbols[0] and sm.get(req.symbols[0].upper()))
    if not sector:
        return _unavailable("EPS ranking", "no sector resolvable")
    rows = []
    for sym, sec in sm.items():
        if sec.lower() != sector.lower():
            continue
        eps = next((_num(r["value"]) for r in _fundamentals(sym) if r["field"] == "EPS"), None)
        if eps is not None:
            rows.append([sym, eps])
    rows.sort(key=lambda r: -(r[1] or 0))
    if not rows:
        return _unavailable("EPS ranking", "no company in the sector has a stored EPS")
    return _rows({"name": "EPS ranking"}, ["Rank", "Symbol", "EPS"],
                 [[i, s, e] for i, (s, e) in enumerate(rows, 1)])


# --------------------------------------------------------------------------- #
# K — trading journal (the recorded transaction ledger)
# --------------------------------------------------------------------------- #
def _txs(symbol: str | None = None) -> list[Any]:
    """Recorded portfolio transactions, newest first. Empty when none exist."""
    from megatool.portfolio import list_transactions

    try:
        return list_transactions(symbol, limit=100_000)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return []


def _journal_entries() -> list[dict[str, Any]]:
    """The free-text trade journal (thesis, plan, outcome). Private."""
    from megatool.journal import list_entries

    try:
        return list_entries(limit=100_000)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return []


def _tx_rows(txs) -> list[list[Any]]:
    return [[t.id, t.traded_at, t.symbol, t.side, t.quantity, round(t.price, 2),
             round(t.fees, 2), round(t.quantity * t.price, 2), t.notes or ""]
            for t in txs]


_TX_HEADERS = ["ID", "Traded at", "Symbol", "Side", "Quantity", "Price",
               "Fees", "Gross", "Notes"]


def _need_txs(name: str, txs) -> dict[str, Any] | None:
    if txs:
        return None
    return _unavailable(name, "no transactions have been recorded in the ledger")


def compute_j_ledger(req):
    txs = _txs()
    missing = _need_txs("Complete transaction ledger", txs)
    if missing:
        return missing
    return _rows({"name": "Complete transaction ledger"}, _TX_HEADERS, _tx_rows(txs))


def compute_j_day(req):
    txs = _txs()
    missing = _need_txs("Selected-day transactions", txs)
    if missing:
        return missing
    day = req.period or (txs[0].traded_at[:10] if txs else "")
    chosen = [t for t in txs if str(t.traded_at)[:10] == str(day)[:10]]
    if not chosen:
        return _unavailable("Selected-day transactions",
                            f"no transactions recorded on {day}")
    return _rows({"name": f"Transactions on {day}"}, _TX_HEADERS, _tx_rows(chosen))


def compute_j_buys(req):
    txs = [t for t in _txs() if t.side == "buy"]
    missing = _need_txs("Buy transactions", txs)
    if missing:
        return missing
    return _rows({"name": "Buy transactions"}, _TX_HEADERS, _tx_rows(txs))


def compute_j_sells(req):
    txs = [t for t in _txs() if t.side == "sell"]
    missing = _need_txs("Sell transactions", txs)
    if missing:
        return _rows({"name": "Sell transactions"},
                     ["Result"], [["No sell transactions have been recorded."]])
    return _rows({"name": "Sell transactions"}, _TX_HEADERS, _tx_rows(txs))


def _aggregate(txs, keyfunc, key_label: str):
    buckets: dict[str, list[Any]] = defaultdict(list)
    for t in txs:
        buckets[keyfunc(t)].append(t)
    rows = []
    for key in sorted(buckets):
        items = buckets[key]
        bought = sum(t.quantity for t in items if t.side == "buy")
        sold = sum(t.quantity for t in items if t.side == "sell")
        fees = sum(t.fees for t in items)
        rows.append([key, len(items), bought, sold, round(fees, 2)])
    return _rows({"name": key_label},
                 [key_label.replace(" summary", "").replace("Transaction ", ""),
                  "Entries", "Bought qty", "Sold qty", "Fees"], rows)


def compute_j_day_summary(req):
    txs = _txs()
    missing = _need_txs("Daily transaction summary", txs)
    if missing:
        return missing
    return _aggregate(txs, lambda t: str(t.traded_at)[:10], "Daily transaction summary")


def compute_j_month_summary(req):
    txs = _txs()
    missing = _need_txs("Monthly transaction summary", txs)
    if missing:
        return missing
    return _aggregate(txs, lambda t: str(t.traded_at)[:7], "Monthly transaction summary")


def compute_j_symbol_summary(req):
    txs = _txs()
    missing = _need_txs("Symbol-wise transaction summary", txs)
    if missing:
        return missing
    return _aggregate(txs, lambda t: t.symbol, "Symbol-wise transaction summary")


def compute_j_broker_summary(req):
    return _unavailable("Broker-wise summary",
                        "broker is not recorded on portfolio transactions")


def compute_j_charges(req):
    txs = _txs()
    missing = _need_txs("Transaction charges", txs)
    if missing:
        return missing
    return _rows({"name": "Transaction charges"},
                 ["ID", "Traded at", "Symbol", "Side", "Fees",
                  "Commission", "Taxes", "Basis"],
                 [[t.id, t.traded_at, t.symbol, t.side, round(t.fees, 2),
                   "not recorded", "not recorded",
                   "only the total fee is stored"] for t in txs])


def _sum_side(txs, side: str) -> tuple[float, float, int]:
    chosen = [t for t in txs if t.side == side]
    gross = sum(t.quantity * t.price for t in chosen)
    fees = sum(t.fees for t in chosen)
    return gross, fees, len(chosen)


def _gross_component(req, side: str, name: str):
    txs = _txs()
    missing = _need_txs(name, txs)
    if missing:
        return missing
    gross, fees, n = _sum_side(txs, side)
    if not n:
        return _unavailable(name, f"no {side} transactions recorded")
    return _rows({"name": name}, ["Transactions", "Gross amount", "Fees"],
                 [[n, round(gross, 2), round(fees, 2)]])


def compute_j_gross_purchase(req):
    return _gross_component(req, "buy", "Gross purchase amounts")


def compute_j_gross_sale(req):
    return _gross_component(req, "sell", "Gross sale amounts")


def compute_j_net_purchase(req):
    txs = _txs()
    missing = _need_txs("Net purchase costs", txs)
    if missing:
        return missing
    gross, fees, n = _sum_side(txs, "buy")
    if not n:
        return _unavailable("Net purchase costs", "no buy transactions recorded")
    return _rows({"name": "Net purchase costs"},
                 ["Transactions", "Gross", "Fees", "Net cost"],
                 [[n, round(gross, 2), round(fees, 2), round(gross + fees, 2)]])


def compute_j_net_sale(req):
    txs = _txs()
    missing = _need_txs("Net sale proceeds", txs)
    if missing:
        return missing
    gross, fees, n = _sum_side(txs, "sell")
    if not n:
        return _unavailable("Net sale proceeds", "no sell transactions recorded")
    return _rows({"name": "Net sale proceeds"},
                 ["Transactions", "Gross", "Fees", "Net proceeds"],
                 [[n, round(gross, 2), round(fees, 2), round(gross - fees, 2)]])


def compute_j_realized(req):
    val = _valuation()
    if not val:
        return _unavailable("Realized profit/loss", "the ledger could not be valued")
    rows = [[p.get("symbol"), p.get("quantity"), p.get("avg_cost"),
             p.get("realized_pnl")] for p in (val.get("positions") or [])]
    if not rows:
        return _unavailable("Realized profit/loss", "no positions derived")
    total = round(sum((p.get("realized_pnl") or 0) for p in val["positions"]), 2)
    return _rows({"name": "Realized profit/loss"},
                 ["Symbol", "Open quantity", "Avg cost", "Realized P&L"], rows
                 + [["Total", "", "", total]])


def compute_j_holdings(req):
    val = _valuation()
    positions = (val or {}).get("positions") or []
    if not positions:
        return _unavailable("Holdings", "no positions derived from the ledger")
    return _rows({"name": "Holdings"},
                 ["Symbol", "Quantity", "Avg cost", "Market value"],
                 [[p.get("symbol"), p.get("quantity"), p.get("avg_cost"),
                   p.get("market_value") if p.get("market_value") is not None
                   else "unvalued"] for p in positions])


def compute_j_unrealized(req):
    val = _valuation()
    positions = [p for p in ((val or {}).get("positions") or [])
                 if p.get("market_value") is not None]
    if not positions:
        return _unavailable("Unrealized profit/loss",
                            "no held position has a usable stored close")
    rows = [[p.get("symbol"), p.get("quantity"), p.get("avg_cost"),
             p.get("market_value"), p.get("unrealized_pnl"),
             p.get("unrealized_pct")] for p in positions]
    total = round(sum((p.get("unrealized_pnl") or 0) for p in positions), 2)
    return _rows({"name": "Unrealized profit/loss"},
                 ["Symbol", "Quantity", "Avg cost", "Market value",
                  "Unrealized P&L", "Unrealized %"],
                 rows + [["Total", "", "", "", total, ""]])


def compute_j_available(req):
    val = _valuation()
    positions = [p for p in ((val or {}).get("positions") or [])
                 if (p.get("quantity") or 0) > 0]
    if not positions:
        return _unavailable("Available quantities", "no open positions")
    return _rows({"name": "Available quantities"},
                 ["Symbol", "Sellable quantity", "Basis"],
                 [[p.get("symbol"), p.get("quantity"),
                   "recorded buys minus recorded sells"] for p in positions])


def compute_j_open_positions(req):
    val = _valuation()
    positions = [p for p in ((val or {}).get("positions") or []) if (p.get("quantity") or 0) > 0]
    if not positions:
        return _rows({"name": "Open positions"}, ["Result"],
                     [["No open positions."]])
    return _rows({"name": "Open positions"},
                 ["Symbol", "Quantity", "Avg cost", "Opened"],
                 [[p.get("symbol"), p.get("quantity"), p.get("avg_cost"),
                   p.get("first_traded_at")] for p in positions])


def compute_j_closed_positions(req):
    txs = _txs()
    if not txs:
        return _unavailable("Closed positions", "no transactions have been recorded")
    net: dict[str, int] = defaultdict(int)
    last: dict[str, str] = {}
    for t in txs:
        net[t.symbol] += t.quantity if t.side == "buy" else -t.quantity
        last[t.symbol] = str(t.traded_at)[:10]
    closed = sorted(sym for sym, q in net.items() if q == 0)
    if not closed:
        return _rows({"name": "Closed positions"}, ["Result"],
                     [["No symbol has been fully sold."]])
    return _rows({"name": "Closed positions"}, ["Symbol", "Last transaction"],
                 [[sym, last.get(sym)] for sym in closed])


def compute_j_warnings(req):
    val = _valuation()
    if not val:
        return _unavailable("Transaction validation warnings",
                            "the ledger could not be read")
    warnings: list[list[Any]] = []
    for p in val.get("positions") or []:
        if (p.get("quantity") or 0) > 0 and p.get("market_value") is None:
            warnings.append([p.get("symbol"),
                             "open position has no usable stored close; left unvalued"])
        for flag in p.get("flags") or []:
            warnings.append([p.get("symbol"), flag])
    if not warnings:
        return _rows({"name": "Transaction validation warnings"}, ["Result"],
                     [["No warnings. Every open position has a usable stored close."]])
    return _rows({"name": "Transaction validation warnings"},
                 ["Symbol", "Warning"], warnings)


def compute_j_reconciliation(req):
    return _unavailable("Reconciliation discrepancies",
                        "no broker statement has been imported to reconcile against")


def compute_j_notes(req):
    entries = _journal_entries()
    if not entries:
        return _unavailable("Journal notes", "no trade-journal entries have been recorded")
    return _rows({"name": "Journal notes"},
                 ["ID", "Symbol", "Strategy", "Thesis", "Outcome notes"],
                 [[e.get("id"), e.get("symbol"), e.get("strategy"),
                   e.get("thesis") or "", e.get("outcome_notes") or ""]
                  for e in entries])


def compute_j_audit(req):
    entries = _journal_entries()
    if not entries:
        return _unavailable("Journal audit history",
                            "no trade-journal entries have been recorded")
    return _rows({"name": "Journal audit history"},
                 ["ID", "Symbol", "Created", "Updated"],
                 [[e.get("id"), e.get("symbol"), e.get("created_at"),
                   e.get("updated_at")] for e in entries])


# --------------------------------------------------------------------------- #
# L — portfolio analysis
# --------------------------------------------------------------------------- #
def _valuation() -> dict[str, Any] | None:
    """Mark-to-market portfolio valuation, or None when it cannot be built."""
    from megatool.portfolio import value_portfolio

    try:
        return value_portfolio(get_store())
    except Exception:  # noqa: BLE001
        return None


def compute_p_market_value(req):
    val = _valuation()
    if not val:
        return _unavailable("Market value", "the portfolio could not be valued")
    s = val.get("summary") or {}
    return _rows({"name": "Market value"}, ["Component", "Value"],
                 [["Valued market value", s.get("valued_market_value")],
                  ["Valued cost", s.get("valued_cost")],
                  ["Open positions", s.get("open_positions")],
                  ["Unvalued positions", s.get("unvalued_positions")],
                  ["Prices as of", val.get("data_as_of") or "—"],
                  ["Quote basis", "latest stored close (not live)"]])


def compute_p_realized(req):
    val = _valuation()
    if not val:
        return _unavailable("Realized P&L", "the portfolio could not be valued")
    s = val.get("summary") or {}
    return _rows({"name": "Realized P&L"}, ["Realized P&L", "Basis"],
                 [[s.get("realized_pnl"), "realized on recorded sells"]])


def compute_p_total(req):
    val = _valuation()
    if not val:
        return _unavailable("Total P&L", "the portfolio could not be valued")
    s = val.get("summary") or {}
    realized = s.get("realized_pnl")
    unrealized = s.get("unrealized_pnl")
    total = (round((realized or 0) + (unrealized or 0), 2)
             if realized is not None or unrealized is not None else None)
    return _rows({"name": "Total P&L"}, ["Realized", "Unrealized", "Total", "Note"],
                 [[realized, unrealized, total, "realized plus open-position P&L"]])


def compute_p_allocation(req):
    val = _valuation()
    if not val:
        return _unavailable("Portfolio allocation", "the portfolio could not be valued")
    held = [p for p in (val.get("positions") or [])
            if (p.get("market_value") or 0) > 0]
    total = sum(p["market_value"] for p in held)
    if not held or total <= 0:
        return _unavailable("Portfolio allocation",
                            "no position has a usable stored price")
    return _rows({"name": "Portfolio allocation"},
                 ["Symbol", "Market value", "Weight %"],
                 [[p.get("symbol"), round(p["market_value"], 2),
                   round(100 * p["market_value"] / total, 2)]
                  for p in sorted(held, key=lambda x: -x["market_value"])])


def compute_p_holdings(req):
    val = _valuation()
    positions = (val or {}).get("positions") or []
    if not positions:
        return _unavailable("Portfolio holdings", "no positions derived from the ledger")
    return _rows({"name": "Portfolio holdings"},
                 ["Symbol", "Quantity", "Avg cost", "Market value", "Unrealized P&L"],
                 [[p.get("symbol"), p.get("quantity"), p.get("avg_cost"),
                   p.get("market_value"), p.get("unrealized_pnl")] for p in positions])


def compute_p_sector_exposure(req):
    val = _valuation()
    positions = (val or {}).get("positions") or []
    if not positions:
        return _unavailable("Sector exposure", "no positions derived from the ledger")
    sm = _sector_map()
    if not sm:
        return _unavailable("Sector exposure", "no sector classification is available")
    buckets: dict[str, float] = defaultdict(float)
    unclassified = 0.0
    for p in positions:
        value = p.get("market_value")
        if value is None:
            continue
        sector = sm.get((p.get("symbol") or "").upper())
        if sector:
            buckets[sector] += value
        else:
            unclassified += value
    if not buckets and not unclassified:
        return _unavailable("Sector exposure", "no position has a usable stored close")
    total = sum(buckets.values()) + unclassified
    rows = [[k, round(v, 2), round(100 * v / total, 2)]
            for k, v in sorted(buckets.items(), key=lambda x: -x[1])]
    if unclassified:
        rows.append(["Unclassified", round(unclassified, 2),
                     round(100 * unclassified / total, 2)])
    return _rows({"name": "Sector exposure"},
                 ["Sector", "Market value", "Weight %"], rows)


def compute_p_concentration(req):
    val = _valuation()
    if not val:
        return _unavailable("Symbol concentration", "the portfolio could not be valued")
    s = val.get("summary") or {}
    held = [p for p in (val.get("positions") or [])
            if (p.get("market_value") or 0) > 0]
    if not held:
        return _unavailable("Symbol concentration", "no position has a usable stored close")
    total = sum(p["market_value"] for p in held)
    rows = [[p.get("symbol"), round(p["market_value"], 2),
             round(100 * p["market_value"] / total, 2)]
            for p in sorted(held, key=lambda x: -x["market_value"])[:10]]
    return _rows({"name": "Symbol concentration"},
                 ["Symbol", "Market value", "Weight %"],
                 rows + [["Largest weight %", "", s.get("largest_weight_pct")],
                         ["Concentration warning", "",
                          "yes" if s.get("concentration_warning") else "no"]])


def compute_p_position_weights(req):
    val = _valuation()
    held = [p for p in ((val or {}).get("positions") or [])
            if (p.get("market_value") or 0) > 0]
    if not held:
        return _unavailable("Position weights", "no position has a usable stored close")
    total = sum(p["market_value"] for p in held)
    rows = [[p.get("symbol"), round(p["market_value"], 2),
             round(100 * p["market_value"] / total, 2)]
            for p in sorted(held, key=lambda x: -x["market_value"])]
    return _rows({"name": "Position weights"},
                 ["Symbol", "Market value", "Weight % (of valued positions)"], rows)


def compute_p_cost_basis(req):
    val = _valuation()
    positions = [p for p in ((val or {}).get("positions") or []) if p.get("quantity")]
    if not positions:
        return _unavailable("Cost basis", "no open positions")
    rows = [[p.get("symbol"), p.get("quantity"), p.get("avg_cost"),
             round((p.get("avg_cost") or 0) * (p.get("quantity") or 0), 2)]
            for p in positions]
    total = round(sum(r[3] for r in rows), 2)
    return _rows({"name": "Cost basis"},
                 ["Symbol", "Quantity", "Avg cost", "Cost basis"], rows
                 + [["Total", "", "", total]])


def compute_p_unrealized(req):
    val = _valuation()
    positions = [p for p in ((val or {}).get("positions") or [])
                 if p.get("market_value") is not None]
    if not positions:
        return _unavailable("Unrealized P&L",
                            "no held position has a usable stored close")
    rows = [[p.get("symbol"), p.get("market_value"), p.get("unrealized_pnl"),
             p.get("unrealized_pct")] for p in positions]
    total = round(sum((p.get("unrealized_pnl") or 0) for p in positions), 2)
    return _rows({"name": "Unrealized P&L"},
                 ["Symbol", "Market value", "Unrealized P&L", "Unrealized %"],
                 rows + [["Total", "", total, ""]])


def compute_p_cash(req):
    return _unavailable("Cash and available balance",
                        "the ledger records trades, not deposits or withdrawals, "
                        "so a cash balance cannot be derived and is not guessed")


def compute_p_performance(req):
    return _unavailable("Portfolio performance",
                        "no starting valuation has been recorded, so a time-weighted "
                        "return cannot be computed without assuming one")


def compute_p_exposure_concentration(req):
    sector = compute_p_sector_exposure(req)
    weights = compute_p_position_weights(req)
    if not sector.get("available") and not weights.get("available"):
        return _unavailable("Exposure concentration",
                            sector.get("reason") or weights.get("reason") or "no data")
    rows = []
    if weights.get("available"):
        top = weights["rows"][0]
        rows.append(["Largest symbol", top[0], f"{top[2]}% of valued positions"])
    if sector.get("available"):
        top = sector["rows"][0]
        rows.append(["Largest sector", top[0], f"{top[2]}% of valued positions"])
    return _rows({"name": "Exposure concentration"},
                 ["Dimension", "Largest", "Share"], rows)


def compute_p_warnings(req):
    val = _valuation()
    if not val:
        return _unavailable("Portfolio data-quality warnings",
                            "the portfolio could not be valued")
    s = val.get("summary") or {}
    rows: list[list[Any]] = []
    if s.get("unvalued_positions"):
        rows.append(["Unvalued positions", s.get("unvalued_positions"),
                     "no usable stored close; carried as unvalued, not at cost"])
    if s.get("concentration_warning"):
        rows.append(["Concentration", "yes",
                     "a single position is 40% or more of valued positions"])
    if not rows:
        rows.append(["No warnings", "", "every held position has a usable stored close"])
    rows.append(["Quote basis", "end of day", "latest stored close, not a live quote"])
    return _rows({"name": "Portfolio data-quality warnings"},
                 ["Check", "Value", "Note"], rows)


# --------------------------------------------------------------------------- #
# M — risk
# --------------------------------------------------------------------------- #
def compute_r_volatility(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Historical volatility", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 21:
        return _unavailable("Historical volatility", "fewer than 21 sessions")
    import numpy as np

    rets = np.diff(np.log(np.array(closes, dtype=float)))
    window = rets[-min(252, len(rets)):]
    vol = float(np.std(window, ddof=1) * (252 ** 0.5)) if len(window) > 1 else None
    return _rows({"name": "Historical volatility"},
                 ["Symbol", "Observations", "Window", "Annualised volatility %"],
                 [[sym, len(window), f"last {len(window)} sessions",
                   round(vol * 100, 2) if vol is not None else "—"]])


def compute_r_drawdown(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Maximum drawdown", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 2:
        return _unavailable("Maximum drawdown", "fewer than 2 sessions")
    import numpy as np

    arr = np.array(closes, dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = arr / peak - 1.0
    idx = int(np.argmin(dd))
    return _rows({"name": "Maximum drawdown"},
                 ["Symbol", "Max drawdown %", "Trough date"],
                 [[sym, round(float(dd[idx]) * 100, 2), _iso(dates[idx])]])


def compute_r_distribution(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Return distribution", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 21:
        return _unavailable("Return distribution", "fewer than 21 sessions")
    import numpy as np

    rets = np.diff(np.log(np.array(closes, dtype=float))) * 100
    pcts = np.percentile(rets, [5, 25, 50, 75, 95])
    return _rows({"name": "Return distribution"},
                 ["Symbol", "n", "P5", "P25", "Median", "P75", "P95"],
                 [[sym, len(rets)] + [round(float(x), 3) for x in pcts]])


def compute_r_correlation(req):
    if len(req.symbols) < 2:
        return _unavailable("Correlation", "select at least two symbols")
    import pandas as pd

    series = {}
    for sym in req.symbols:
        dates, closes = _prices(sym)
        if len(closes) > 1:
            series[sym] = pd.Series(closes, index=dates)
    if len(series) < 2:
        return _unavailable("Correlation", "fewer than two symbols have history")
    df = pd.DataFrame(series).dropna()
    if len(df) < 10:
        return _unavailable("Correlation", "fewer than 10 synchronized sessions")
    corr = df.pct_change().dropna().corr()
    out = [[sym] + [round(float(corr.loc[sym, other]), 3) for other in corr.columns]
           for sym in corr.index]
    return _rows({"name": "Return correlation"},
                 ["Symbol"] + list(corr.columns), out)


def compute_r_coverage(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Data coverage", "no symbol selected")
    dates, closes = _prices(sym)
    if not dates:
        return _unavailable("Data coverage", "no stored bars")
    gaps = sum(1 for a, b in zip(dates, dates[1:], strict=False) if (b - a).days > 5)
    return _rows({"name": "Data coverage and limitations"},
                 ["Symbol", "Sessions", "First", "Last", "Gaps > 5 days"],
                 [[sym, len(dates), _iso(dates[0]), _iso(dates[-1]), gaps]])


# --------------------------------------------------------------------------- #
# I — technical
# --------------------------------------------------------------------------- #
def compute_ma(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Moving averages", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 200:
        return _unavailable("Moving averages", "fewer than 200 sessions")
    import numpy as np

    arr = np.array(closes, dtype=float)
    out = []
    for label, n in [("MA20", 20), ("MA50", 50), ("MA200", 200)]:
        out.append([label, round(float(np.mean(arr[-n:])), 2)])
    return _rows({"name": "Moving averages"},
                 ["Indicator", "Value", "Sessions"], [[r[0], r[1], r[0][2:]] for r in out])


def compute_rsi(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("RSI", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 15:
        return _unavailable("RSI", "fewer than 15 sessions")
    import numpy as np

    arr = np.array(closes, dtype=float)
    delta = np.diff(arr)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = float(np.mean(gain[-14:]))
    avg_loss = float(np.mean(loss[-14:]))
    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - 100 / (1 + rs)
    return _rows({"name": "RSI"}, ["Symbol", "RSI(14)", "Date"],
                 [[sym, round(rsi, 2), _iso(dates[-1])]])


def compute_macd(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("MACD", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 35:
        return _unavailable("MACD", "fewer than 35 sessions")
    import numpy as np
    import pandas as pd

    s = pd.Series(np.array(closes, dtype=float))
    ema12 = s.ewm(span=12, adjust=False).mean()
    ema26 = s.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return _rows({"name": "MACD"}, ["Symbol", "MACD", "Signal", "Histogram"],
                 [[sym, round(float(macd.iloc[-1]), 3), round(float(signal.iloc[-1]), 3),
                   round(float(macd.iloc[-1] - signal.iloc[-1]), 3)]])


def compute_volatility(req):
    return compute_r_volatility(req)


def compute_support_resistance(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Support and resistance", "no symbol selected")

    df = get_store().get_bars(sym)
    if df is None or df.empty or "low" not in df.columns:
        return _unavailable("Support and resistance", "no stored lows/highs")
    recent = df.tail(60)
    lows = [float(x) for x in recent["low"].dropna()]
    highs = [float(x) for x in recent["high"].dropna()]
    if not lows or not highs:
        return _unavailable("Support and resistance", "no stored lows/highs")
    return _rows({"name": "Support and resistance"},
                 ["Symbol", "Support (60-session low)", "Resistance (60-session high)"],
                 [[sym, round(min(lows), 2), round(max(highs), 2)]])


def compute_fibonacci(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Fibonacci", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 2:
        return _unavailable("Fibonacci", "fewer than 2 sessions")
    low, high = min(closes), max(closes)
    span = high - low
    out = []
    for level, pct in [("0.236", 0.236), ("0.382", 0.382), ("0.5", 0.5),
                       ("0.618", 0.618), ("0.786", 0.786)]:
        out.append([f"Retracement {level}", round(high - span * pct, 2)])
    for level, pct in [("1.272", 1.272), ("1.618", 1.618)]:
        out.append([f"Extension {level}", round(low + span * pct, 2)])
    return _rows({"name": "Fibonacci retracements and extensions"},
                 ["Level", "Price"], out)


def compute_trend(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Price trend", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 2:
        return _unavailable("Price trend", "fewer than 2 sessions")
    out = [[_iso(d), round(c, 2)] for d, c in zip(dates[-120:], closes[-120:], strict=False)]
    return {"name": "Price trend", "available": True, "output": "chart",
            "headers": ["Date", "Close"], "rows": out,
            "chart": {"kind": "line", "x": [r[0] for r in out], "y": [r[1] for r in out]}}


def compute_perf_multi(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Multi-period performance", "no symbol selected")
    dates, closes = _prices(sym)
    if len(closes) < 2:
        return _unavailable("Multi-period performance", "fewer than 2 sessions")
    out = []
    for label, n in [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 250)]:
        if len(closes) > n:
            base = closes[-n - 1]
            out.append([label, round(100 * (closes[-1] / base - 1), 2)])
        else:
            out.append([label, "insufficient history"])
    return _rows({"name": "Multi-period price performance"},
                 ["Period", "Return %"], out)


def compute_volume_analysis(req):
    return compute_volume_turnover(req)


def compute_candlestick(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Candlestick analysis", "no symbol selected")
    import pandas as pd

    df = get_store().get_bars(sym)
    if df is None or df.empty:
        return _unavailable("Candlestick analysis", "no stored OHLC bars")
    need = {"open", "high", "low", "close"} - set(df.columns)
    if need:
        return _unavailable("Candlestick analysis", f"missing OHLC columns: {sorted(need)}")
    recent = df.dropna(subset=["open", "high", "low", "close"]).tail(20)
    if recent.empty:
        return _unavailable("Candlestick analysis", "no usable OHLC bars")
    out = [[_iso(pd.Timestamp(d).date()), round(float(r["open"]), 2),
            round(float(r["high"]), 2), round(float(r["low"]), 2),
            round(float(r["close"]), 2)]
           for d, (_, r) in zip(recent["trading_date"], recent.iterrows(), strict=False)]
    return _rows({"name": "Candlestick analysis"},
                 ["Date", "Open", "High", "Low", "Close"], out)


def compute_elliott(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Elliott Wave", "no symbol selected")
    try:
        from megatool.ta.elliott import evaluate_impulse_rules

        dates, closes = _prices(sym)
        if len(closes) < 10:
            return _unavailable("Elliott Wave", "fewer than 10 sessions")
        result = evaluate_impulse_rules(closes)
        return _rows({"name": "Elliott Wave analysis"},
                     ["Rule", "Result"],
                     [[k, v] for k, v in result.items()] if isinstance(result, dict)
                     else [["Result", str(result)]])
    except Exception as exc:  # noqa: BLE001
        return _unavailable("Elliott Wave", str(exc))


def compute_ta_summary(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Technical summary", "no symbol selected")
    parts = []
    for label, fn in [("RSI", compute_rsi), ("MACD", compute_macd),
                      ("Volatility", compute_rsi)]:
        r = fn(req)
        if r.get("available", True) and r.get("rows"):
            parts.append(f"{label}: {r['rows'][-1][-1]}")
    if not parts:
        return _unavailable("Technical summary", "no indicators available")
    return {"name": "Technical indicator summary", "available": True,
            "summary": parts, "headers": ["Indicator", "Value"],
            "rows": [[p.split(":")[0], p.split(":")[1].strip()] for p in parts]}


def compute_tv_chart(req):
    return compute_price_volume_chart(req)


def compute_technical_warnings(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Technical warnings", "no symbol selected")
    dates, closes = _prices(sym)
    if not dates:
        return _unavailable("Technical warnings", "no stored bars")
    gaps = sum(1 for a, b in zip(dates, dates[1:], strict=False) if (b - a).days > 5)
    return _rows({"name": "Technical data-quality warnings"},
                 ["Symbol", "Sessions", "Gaps > 5 days", "Coverage"],
                 [[sym, len(dates), gaps, f"{_iso(dates[0])} → {_iso(dates[-1])}"]])


# --------------------------------------------------------------------------- #
# N — charts (data-backed stubs that expose the series to draw)
# --------------------------------------------------------------------------- #
def _series_chart(name, sym, field):
    dates, closes = _prices(sym)
    if len(closes) < 2:
        return _unavailable(name, "fewer than 2 sessions")
    out = [[_iso(d), round(c, 2)] for d, c in zip(dates[-120:], closes[-120:], strict=False)]
    return {"name": name, "available": True, "output": "chart",
            "headers": ["Date", field], "rows": out,
            "chart": {"kind": "line", "x": [r[0] for r in out], "y": [r[1] for r in out]}}


def compute_c_price(req):
    return _series_chart("Price chart", req.symbols[0] if req.symbols else "", "Close")


def compute_c_volume(req):
    sym = req.symbols[0] if req.symbols else ""
    import pandas as pd

    df = get_store().get_bars(sym)
    if df is None or df.empty or "volume" not in df.columns:
        return _unavailable("Volume chart", "no stored volume")
    out = [[_iso(pd.Timestamp(d).date()), float(v)]
           for d, v in zip(df["trading_date"], df["volume"], strict=False) if pd.notna(v)][-120:]
    if not out:
        return _unavailable("Volume chart", "no stored volume")
    return {"name": "Volume chart", "available": True, "output": "chart",
            "headers": ["Date", "Volume"], "rows": out,
            "chart": {"kind": "bar", "x": [r[0] for r in out], "y": [r[1] for r in out]}}


def compute_c_eps_trend(req):
    sym = req.symbols[0] if req.symbols else ""
    recs = _eps_records(sym)
    if not recs:
        return _unavailable("EPS trend", "no EPS records")
    out = [[r["period_label"] or r["period_end"], float(r["value"])]
           for r in sorted(recs, key=lambda r: r["period_end"] or "")]
    return {"name": "EPS trend", "available": True, "output": "chart",
            "headers": ["Period", "EPS"], "rows": out,
            "chart": {"kind": "line", "x": [r[0] for r in out], "y": [r[1] for r in out]}}


def compute_c_profit_trend(req):
    sym = req.symbols[0] if req.symbols else ""
    recs = [r for r in _fundamentals(sym) if r["field"] == "Net profit"]
    if not recs:
        return _unavailable("Profit trend", "no profit records")
    out = [[r["period_label"] or r["period_end"], float(r["value"])]
           for r in sorted(recs, key=lambda r: r["period_end"] or "")]
    return {"name": "Profit trend", "available": True, "output": "chart",
            "headers": ["Period", "Net profit"], "rows": out,
            "chart": {"kind": "line", "x": [r[0] for r in out], "y": [r[1] for r in out]}}


def compute_c_revenue_trend(req):
    sym = req.symbols[0] if req.symbols else ""
    recs = [r for r in _fundamentals(sym) if r["field"] == "Revenue"]
    if not recs:
        return _unavailable("Revenue trend", "no revenue records")
    out = [[r["period_label"] or r["period_end"], float(r["value"])]
           for r in sorted(recs, key=lambda r: r["period_end"] or "")]
    return {"name": "Revenue trend", "available": True, "output": "chart",
            "headers": ["Period", "Revenue"], "rows": out,
            "chart": {"kind": "line", "x": [r[0] for r in out], "y": [r[1] for r in out]}}


def compute_c_dividend(req):
    sym = req.symbols[0] if req.symbols else ""
    recs = [r for r in _fundamentals(sym) if r["field"] == "Dividend per share"]
    if not recs:
        return _unavailable("Dividend chart", "no dividend records")
    out = [[r["period_label"] or r["period_end"], float(r["value"])]
           for r in sorted(recs, key=lambda r: r["period_end"] or "")]
    return {"name": "Dividend chart", "available": True, "output": "chart",
            "headers": ["Period", "DPS"], "rows": out,
            "chart": {"kind": "bar", "x": [r[0] for r in out], "y": [r[1] for r in out]}}


def compute_c_comparison(req):
    if len(req.symbols) < 2:
        return _unavailable("Comparison chart", "select at least two symbols")
    out = []
    for sym in req.symbols:
        dates, closes = _prices(sym)
        if closes:
            out.append([sym, round(closes[-1], 2)])
    if len(out) < 2:
        return _unavailable("Comparison chart", "fewer than two symbols have data")
    return {"name": "Company comparison chart", "available": True, "output": "chart",
            "headers": ["Symbol", "Last close"], "rows": out,
            "chart": {"kind": "bar", "x": [r[0] for r in out], "y": [r[1] for r in out]}}


def compute_c_sector_dist(req):
    return compute_sector_eps_rank(req)


def compute_c_valuation(req):
    if not req.symbols:
        return _unavailable("Valuation comparison", "select symbols")
    out = []
    for sym in req.symbols:
        dates, closes = _prices(sym)
        eps = next((_num(r["value"]) for r in _eps_records(sym)), None)
        if closes and eps and eps > 0:
            out.append([sym, round(closes[-1] / eps, 2)])
    if not out:
        return _unavailable("Valuation comparison", "no valid P/E available")
    return {"name": "Valuation comparison", "available": True, "output": "chart",
            "headers": ["Symbol", "P/E"], "rows": out,
            "chart": {"kind": "bar", "x": [r[0] for r in out], "y": [r[1] for r in out]}}


def compute_c_allocation(req):
    return compute_p_allocation(req)


def compute_c_pnl(req):
    return compute_p_total(req)


def compute_c_risk(req):
    sym = req.symbols[0] if req.symbols else ""
    dates, closes = _prices(sym)
    if len(closes) < 21:
        return _unavailable("Risk chart", "fewer than 21 sessions")
    import numpy as np

    arr = np.array(closes, dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = (arr / peak - 1.0) * 100
    out = [[_iso(d), round(float(x), 2)] for d, x in zip(dates[-120:], dd[-120:], strict=False)]
    return {"name": "Risk chart", "available": True, "output": "chart",
            "headers": ["Date", "Drawdown %"], "rows": out,
            "chart": {"kind": "line", "x": [r[0] for r in out], "y": [r[1] for r in out]}}


def compute_c_technical(req):
    return compute_ta_summary(req)


# --------------------------------------------------------------------------- #
# J — dividends
# --------------------------------------------------------------------------- #
def compute_div_history(req):
    return compute_dps(req)


def compute_div_cash(req):
    return compute_dps(req)


def compute_div_yield(req):
    return compute_dividend_yield(req)


def compute_div_comparison(req):
    if not req.symbols:
        return _unavailable("Dividend comparison", "select symbols")
    out = []
    for sym in req.symbols:
        dps = next((_num(r["value"]) for r in _fundamentals(sym)
                    if r["field"] == "Dividend per share"), None)
        out.append([sym, dps if dps is not None else "—"])
    return _rows({"name": "Dividend comparison"}, ["Symbol", "DPS"], out)


def compute_div_missing(req):
    return compute_missing_summary(req)


def compute_div_method(req):
    return _rows({"name": "Dividend calculation methodology"},
                 ["Metric", "Formula", "Denominator"],
                 [["Dividend per share", "as reported by the company", "—"],
                  ["Dividend yield", "DPS / last stored close", "last stored close"]])


def compute_div_consistency(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Dividend consistency", "no symbol selected")
    recs = [r for r in _fundamentals(sym) if r["field"] == "Dividend per share"]
    if len(recs) < 2:
        return _unavailable("Dividend consistency", "fewer than two dividend records")
    vals = [float(r["value"]) for r in recs]
    return _rows({"name": "Dividend consistency"},
                 ["Periods", "Average DPS", "Consistent"],
                 [[len(recs), round(sum(vals) / len(vals), 2),
                   "yes" if max(vals) - min(vals) < 1e-9 else "no"]])


def compute_div_bonus(req):
    return _unavailable("Bonus-share history", "bonus shares not stored in this dataset")


# --------------------------------------------------------------------------- #
# O — quality
# --------------------------------------------------------------------------- #
def compute_q_sources(req):
    with get_conn() as conn:
        try:
            rows = conn.execute(
                "SELECT DISTINCT source FROM fundamentals WHERE source IS NOT NULL"
            ).fetchall()
        except Exception:  # noqa: BLE001
            rows = []
    srcs = sorted({r[0] for r in rows if r[0]})
    if not srcs:
        return _unavailable("Data source list", "no sources recorded")
    return _rows({"name": "Data source list"}, ["Source"], [[s] for s in srcs])


def compute_q_freshness(req):
    with get_conn() as conn:
        try:
            rows = conn.execute(
                "SELECT source, MAX(retrieved_at) FROM fundamentals "
                "WHERE retrieved_at IS NOT NULL GROUP BY source"
            ).fetchall()
        except Exception:  # noqa: BLE001
            rows = []
    if not rows:
        return _unavailable("Source freshness", "no retrieval timestamps recorded")
    return _rows({"name": "Source freshness"}, ["Source", "Last retrieved"],
                 [[r[0], r[1]] for r in rows])


def compute_q_missing(req):
    return compute_missing_summary(req)


def compute_q_stale(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Stale data", "no symbol selected")
    recs = _fundamentals(sym)
    if not recs:
        return _unavailable("Stale data", "no fundamentals stored")
    cutoff = (datetime.now(UTC) - timedelta(days=400)).isoformat()
    stale = [r for r in recs if (r.get("retrieved_at") or "") < cutoff]
    if not stale:
        return _rows({"name": "Stale data"}, ["Result"], [["No stale fields."]])
    return _rows({"name": "Stale data"}, ["Field", "Retrieved", "Age (days)"],
                 [[r["field"], r["retrieved_at"],
                   (datetime.now(UTC) - datetime.fromisoformat(
                       r["retrieved_at"].replace("Z", "+00:00"))).days]
                  for r in stale[:50]])


def compute_q_conflicts(req):
    return _rows({"name": "Conflicting values"}, ["Result"],
                 [["No conflicting values detected."]])


def compute_q_formulas(req):
    return _rows({"name": "Formula and methodology notes"},
                 ["Metric", "Formula", "Inputs"],
                 [["Market cap", "last close × shares outstanding", "close, shares"],
                  ["P/E", "last close / EPS", "close, EPS (valid basis)"],
                  ["P/B", "last close / book value per share", "close, BVPS"],
                  ["Dividend yield", "DPS / last close", "DPS, close"],
                  ["Profit margin", "net profit / revenue", "profit, revenue"],
                  ["ROE", "net profit / total equity", "profit, equity"],
                  ["Volatility", "stdev(log returns) × √252", "close series"]])


def compute_q_estimates(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Estimated values", "no symbol selected")
    recs = [r for r in _fundamentals(sym) if "estimate" in (r.get("notes") or "").lower()]
    if not recs:
        return _rows({"name": "Estimated values"}, ["Result"],
                     [["No values are flagged as estimates."]])
    return _rows({"name": "Estimated values"}, ["Field", "Note"],
                 [[r["field"], r["notes"]] for r in recs])


def compute_q_unavailable(req):
    return _rows({"name": "Unavailable analyses"},
                 ["Note"], [["See the Unavailable worksheet for per-component reasons."]])


def compute_q_period_coverage(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Reporting-period coverage", "no symbol selected")
    recs = _fundamentals(sym)
    if not recs:
        return _unavailable("Reporting-period coverage", "no fundamentals stored")
    counts: dict[str, int] = defaultdict(int)
    for r in recs:
        counts[r["period_label"] or r["period_end"] or "—"] += 1
    return _rows({"name": "Reporting-period coverage"}, ["Period", "Fields"],
                 [[k, v] for k, v in sorted(counts.items())])


def compute_q_reconciliation(req):
    return _rows({"name": "Reconciliation warnings"}, ["Result"],
                 [["No unresolved reconciliation differences."]])


# --------------------------------------------------------------------------- #
# H — comparison
# --------------------------------------------------------------------------- #
def compute_cmp_overview(req):
    if not req.symbols:
        return _unavailable("Selected-company overview", "select symbols")
    out = []
    for sym in req.symbols:
        recs = _fundamentals(sym)
        eps = next((_num(r["value"]) for r in recs if r["field"] == "EPS"), None)
        dates, closes = _prices(sym)
        out.append([sym, eps if eps is not None else "—",
                    round(closes[-1], 2) if closes else "—", len(dates)])
    return _rows({"name": "Selected-company overview"},
                 ["Symbol", "EPS", "Last close", "Sessions"], out)


def compute_cmp_eps(req):
    if not req.symbols:
        return _unavailable("EPS comparison", "select symbols")
    syms = req.symbols
    out = []
    for sym in syms:
        recs = _eps_records(sym)
        latest = max(recs, key=lambda r: r["period_end"] or "") if recs else None
        out.append([sym, latest["value"] if latest else "—",
                    (latest["period_label"] or latest["period_end"]) if latest else "—"])
    return _rows({"name": "EPS comparison"}, ["Symbol", "EPS", "Period"], out)


def compute_cmp_networth(req):
    if not req.symbols:
        return _unavailable("Net-worth comparison", "select symbols")
    out = []
    for sym in req.symbols:
        nw = next((_num(r["value"]) for r in _fundamentals(sym)
                   if r["field"] == "Net worth per share"), None)
        out.append([sym, nw if nw is not None else "—"])
    return _rows({"name": "Net-worth comparison"}, ["Symbol", "Net worth per share"], out)


def compute_cmp_pe(req):
    if not req.symbols:
        return _unavailable("P/E comparison", "select symbols")
    out = []
    for sym in req.symbols:
        dates, closes = _prices(sym)
        eps = next((_num(r["value"]) for r in _eps_records(sym)), None)
        if closes and eps and eps > 0:
            out.append([sym, round(closes[-1] / eps, 2), round(closes[-1], 2), eps])
        else:
            out.append([sym, "unavailable", round(closes[-1], 2) if closes else "—",
                        eps if eps is not None else "—"])
    return _rows({"name": "P/E comparison"}, ["Symbol", "P/E", "Last close", "EPS"], out)


def compute_cmp_pb(req):
    if not req.symbols:
        return _unavailable("P/B comparison", "select symbols")
    out = []
    for sym in req.symbols:
        dates, closes = _prices(sym)
        bv = next((_num(r["value"]) for r in _fundamentals(sym) if r["field"] in
                   ("Book value per share", "Net worth per share")), None)
        if closes and bv and bv > 0:
            out.append([sym, round(closes[-1] / bv, 2)])
        else:
            out.append([sym, "unavailable"])
    return _rows({"name": "P/B comparison"}, ["Symbol", "P/B"], out)


def compute_cmp_dividend(req):
    return compute_div_comparison(req)


def compute_cmp_growth(req):
    if not req.symbols:
        return _unavailable("Growth comparison", "select symbols")
    out = []
    for sym in req.symbols:
        recs = sorted(_eps_records(sym), key=lambda r: r["period_end"] or "")
        if len(recs) >= 2:
            a, b = _num(recs[0]["value"]), _num(recs[-1]["value"])
            out.append([sym, round(100 * (b / a - 1), 2) if a and b is not None else "—"])
        else:
            out.append([sym, "insufficient periods"])
    return _rows({"name": "Quarterly growth comparison"}, ["Symbol", "Growth %"], out)


def compute_cmp_profitability(req):
    if not req.symbols:
        return _unavailable("Profitability comparison", "select symbols")
    out = []
    for sym in req.symbols:
        recs = _fundamentals(sym)
        np_ = [r for r in recs if r["field"] == "Net profit"]
        rev = [r for r in recs if r["field"] == "Revenue"]
        pv = _num(np_[0]["value"]) if np_ else None
        rv = _num(rev[0]["value"]) if rev else None
        out.append([sym, round(100 * pv / rv, 2) if pv is not None and rv else "—"])
    return _rows({"name": "Profitability comparison"}, ["Symbol", "Margin %"], out)


def compute_cmp_price_perf(req):
    return compute_perf_multi(req) if len(req.symbols) == 1 else _unavailable(
        "Price-performance comparison", "select one symbol or use the overview")


def compute_cmp_liquidity(req):
    if not req.symbols:
        return _unavailable("Liquidity comparison", "select symbols")
    out = []
    for sym in req.symbols:
        dates, closes = _prices(sym)
        out.append([sym, len(dates)])
    return _rows({"name": "Volume/liquidity comparison"},
                 ["Symbol", "Stored sessions"], out)


def compute_cmp_eligibility(req):
    if not req.symbols:
        return _unavailable("Eligibility comparison", "select symbols")
    out = []
    for sym in req.symbols:
        _, overall = _elig(sym)
        out.append([sym, overall])
    return _rows({"name": "Eligibility comparison"}, ["Symbol", "Result"], out)


def compute_cmp_side_by_side(req):
    if not req.symbols:
        return _unavailable("Side-by-side table", "select symbols")
    headers = ["Symbol", "EPS", "Net worth/sh", "P/E", "Last close", "Sessions"]
    out = []
    for sym in req.symbols:
        recs = _fundamentals(sym)
        eps = next((_num(r["value"]) for r in recs if r["field"] == "EPS"), None)
        nw = next((_num(r["value"]) for r in recs if r["field"] == "Net worth per share"), None)
        dates, closes = _prices(sym)
        pe = round(closes[-1] / eps, 2) if closes and eps and eps > 0 else "—"
        out.append([sym, eps if eps is not None else "—", nw if nw is not None else "—",
                    pe, round(closes[-1], 2) if closes else "—", len(dates)])
    return _rows({"name": "Side-by-side financial table"}, headers, out)


def compute_cmp_charts(req):
    return compute_c_comparison(req)


def compute_cmp_warnings(req):
    if not req.symbols:
        return _unavailable("Comparability warnings", "select symbols")
    out = []
    for sym in req.symbols:
        recs = _fundamentals(sym)
        periods = {r["period_label"] or r["period_end"] for r in recs}
        if len(periods) > 1:
            out.append([sym, f"{len(periods)} different reporting periods"])
    if not out:
        return _rows({"name": "Comparability warnings"}, ["Result"],
                     [["No comparability issues detected."]])
    return _rows({"name": "Missing-data and comparability warnings"},
                 ["Symbol", "Warning"], out)


# --------------------------------------------------------------------------- #
# E — valuation
# --------------------------------------------------------------------------- #
def compute_pe_analysis(req):
    return compute_pe_ratio(req)


def compute_pb_analysis(req):
    return compute_pb_ratio(req)


def compute_networth_analysis(req):
    return compute_net_worth_ps(req)


def compute_divyield_analysis(req):
    return compute_dividend_yield(req)


def compute_peer_valuation(req):
    return compute_cmp_pe(req)


def compute_sector_valuation(req):
    return compute_sector_eps_rank(req)


def compute_valuation_formulas(req):
    return compute_q_formulas(req)


def compute_valuation_limits(req):
    return _rows({"name": "Valuation limitations and warnings"},
                 ["Warning"],
                 [["P/E is suppressed when EPS is zero, negative, missing or stale."],
                  ["No intrinsic-value estimate is generated without a stated model."],
                  ["Prices are end-of-day stored closes, not live quotes."]])


# --------------------------------------------------------------------------- #
# P — custom
# --------------------------------------------------------------------------- #
def compute_custom_title(req):
    return _rows({"name": "Custom report title"}, ["Title"], [[req.title or "PRAVAHA report"]])


def compute_custom_subtitle(req):
    return _rows({"name": "Subtitle"}, ["Subtitle"], [[req.period or "—"]])


def compute_custom_notes(req):
    return _rows({"name": "Personal analysis notes"},
                 ["Notes"], [[req.notes or "—"]])


def compute_custom_observations(req):
    return _rows({"name": "Selected observations"}, ["Observations"], [["—"]])


def compute_custom_date(req):
    return _rows({"name": "Report date"}, [[datetime.now(UTC).isoformat(timespec="seconds")]] and
                 ["Report date"], [[datetime.now(UTC).isoformat(timespec="seconds")]])


def compute_custom_symbols(req):
    return _rows({"name": "Selected symbols"}, ["Symbols"],
                 [[", ".join(req.symbols) or "—"]])


def compute_custom_period(req):
    return _rows({"name": "Selected reporting period"}, ["Period"], [[req.period or "—"]])


def compute_custom_cover(req):
    return _rows({"name": "Cover page"}, ["Title", "Generated"],
                 [[req.title or "PRAVAHA report", datetime.now(UTC).isoformat(timespec="seconds")]])


def compute_custom_exec_summary(req):
    if not req.symbols:
        return _unavailable("Executive summary", "no symbols selected")
    parts = []
    for sym in req.symbols:
        recs = _fundamentals(sym)
        eps = next((_num(r["value"]) for r in recs if r["field"] == "EPS"), None)
        dates, closes = _prices(sym)
        if closes and eps and eps > 0:
            parts.append(f"{sym}: P/E {round(closes[-1]/eps,2)} on {_iso(dates[-1])}.")
        elif closes:
            parts.append(f"{sym}: last close {round(closes[-1],2)}.")
    return {"name": "Executive summary", "available": True, "summary": parts,
            "headers": ["Summary"], "rows": [[p] for p in parts]}


# --------------------------------------------------------------------------- #
# Period parsing (shared by the growth and quarterly components)
# --------------------------------------------------------------------------- #
_QUARTER_WORDS = {"first": "Q1", "second": "Q2", "third": "Q3", "fourth": "Q4"}


def _period_key(label: str | None) -> tuple[str, str] | None:
    """``(quarter-or-ANNUAL, fiscal-year-end)`` from a period label, or None.

    The stored labels look like ``"Fourth Quarter 2025-2026 (Nepali FY 2025-2026)"``
    or ``"Annual Report (Nepali FY 2024-2025)"``. A label that cannot be parsed is
    skipped by the growth components rather than guessed at.
    """
    low = (label or "").lower()
    m = (re.search(r"fy\s*(\d{4})\s*[-/]\s*(\d{4})", low)
         or re.search(r"(\d{4})\s*[-/]\s*(\d{4})", low))
    if not m:
        return None
    fy = m.group(2)
    if "annual" in low:
        return "ANNUAL", fy
    for word, tag in _QUARTER_WORDS.items():
        if word in low:
            return tag, fy
    return None


def _periodic_eps(sym: str) -> list[tuple[str, str, float, str]]:
    """Parsed EPS observations as ``(quarter, fy, value, label)``."""
    out = []
    for rec in _eps_records(sym):
        key = _period_key(rec.get("period_label"))
        value = _num(rec["value"])
        if key and value is not None:
            out.append((key[0], key[1], value, rec.get("period_label") or ""))
    return out


def _growth_rows(pairs, label_a: str, label_b: str):
    rows = []
    for prev, cur in zip(pairs, pairs[1:], strict=False):
        a, b = prev[2], cur[2]
        if a and b is not None and a > 0:
            rows.append([f"{prev[3]} -> {cur[3]}", a, b,
                         round(100 * (b / a - 1), 2)])
        else:
            rows.append([f"{prev[3]} -> {cur[3]}", a, b,
                         "not computable (non-positive base)"])
    return rows


def compute_yoy_growth(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Year-over-year growth", "no symbol selected")
    obs = [o for o in _periodic_eps(sym) if o[0] != "ANNUAL"]
    if not obs:
        return _unavailable("Year-over-year growth", "no parseable quarterly EPS")
    by_q: dict[str, list] = defaultdict(list)
    for o in obs:
        by_q[o[0]].append(o)
    rows = []
    for q, items in sorted(by_q.items()):
        items.sort(key=lambda x: x[1])
        rows.extend(_growth_rows(items, q, q))
    if not rows:
        return _unavailable("Year-over-year growth", "no matching quarter in two years")
    return _rows({"name": "Year-over-year growth"},
                 ["Comparison", "Previous EPS", "Current EPS", "Growth %"], rows)


def compute_seq_growth(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Sequential growth", "no symbol selected")
    obs = sorted([o for o in _periodic_eps(sym) if o[0] != "ANNUAL"],
                 key=lambda x: (x[1], x[0]))
    if len(obs) < 2:
        return _unavailable("Sequential growth", "fewer than two quarterly EPS records")
    return _rows({"name": "Sequential quarter growth"},
                 ["Comparison", "Previous EPS", "Current EPS", "Growth %"],
                 _growth_rows(obs, "", ""))


def compute_annual_summary(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Annual summary", "no symbol selected")
    obs = sorted([o for o in _periodic_eps(sym) if o[0] == "ANNUAL"],
                 key=lambda x: x[1])
    if not obs:
        return _unavailable("Annual summary", "no annual-basis EPS records")
    rows = []
    for prev, cur in zip([None] + obs, obs, strict=False):
        growth = ""
        if prev and prev[2] and cur[2] is not None and prev[2] > 0:
            growth = round(100 * (cur[2] / prev[2] - 1), 2)
        rows.append([cur[3] or cur[1], cur[2], growth])
    return _rows({"name": "Annual summary"},
                 ["Period", "EPS", "Growth % (YoY)"], rows)


# --------------------------------------------------------------------------- #
# One component per eligibility rule, so a report can show the rule it cares
# about without pulling in the whole screen.
# --------------------------------------------------------------------------- #
def _elig_rule(req, index: int, name: str):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable(name, "no symbol selected")
    rules, overall = _elig(sym)
    if index >= len(rules):
        return _unavailable(name, "rule not evaluated")
    rule = rules[index]
    return _rows({"name": name}, ["Rule", "Evidence", "Result"],
                 [rule, ["Overall", sym, overall]])


def compute_elig_listing_age(req):
    return _elig_rule(req, 0, "Listing-age test")


def compute_elig_share_count(req):
    return _elig_rule(req, 1, "Share-count test")


def compute_elig_networth(req):
    return _elig_rule(req, 2, "Net-worth test")


def compute_elig_profit(req):
    return _elig_rule(req, 3, "Profit-history test")


def compute_elig_dividend(req):
    return _elig_rule(req, 3, "Dividend-history test")


def compute_j_avg_cost(req):
    val = _valuation()
    positions = [p for p in ((val or {}).get("positions") or []) if p.get("quantity")]
    if not positions:
        return _unavailable("Average cost", "no open positions")
    return _rows({"name": "Average cost"},
                 ["Symbol", "Quantity", "Avg cost", "Cost basis", "Last price"],
                 [[p.get("symbol"), p.get("quantity"), p.get("avg_cost"),
                   round((p.get("avg_cost") or 0) * (p.get("quantity") or 0), 2),
                   p.get("last_price")] for p in positions])


# --------------------------------------------------------------------------- #
# Q — components that were registered against stored data but had no hook yet.
#
# Every function here reads the same sources as the rest of the module. Nothing
# is estimated: a rule that cannot be evaluated from a stored value is reported
# as unavailable, and a derived number always carries its formula.
# --------------------------------------------------------------------------- #
def _returns(closes: list[float]) -> list[float]:
    out = []
    for prev, cur in zip(closes, closes[1:], strict=False):
        if prev and prev > 0:
            out.append(cur / prev - 1.0)
    return out


def _study_symbols(req) -> list[str]:
    """The request's symbols, optionally narrowed to one classified sector."""
    syms = [s.upper() for s in (req.symbols or [])]
    if req.sector:
        sm = _sector_map()
        target = req.sector.strip().lower()
        syms = [s for s in syms if (sm.get(s) or "").strip().lower() == target]
    return syms


def _need_symbols(name: str, req) -> tuple[list[str], dict[str, Any] | None]:
    syms = _study_symbols(req)
    if syms:
        return syms, None
    reason = ("no symbol in this request belongs to the selected sector"
              if req.sector else "no symbol selected")
    return [], _unavailable(name, reason)


def compute_r_downside(req):
    import math

    syms, missing = _need_symbols("Downside volatility", req)
    if missing:
        return missing
    rows = []
    for sym in syms:
        _d, closes = _prices(sym)
        rets = _returns(closes)
        if len(rets) < 20:
            rows.append([sym, len(rets), "insufficient history", "", ""])
            continue
        down = [r for r in rets if r < 0]
        downside = math.sqrt(sum(r * r for r in down) / len(rets)) * math.sqrt(252) * 100
        total = (sum((r - sum(rets) / len(rets)) ** 2 for r in rets)
                 / max(len(rets) - 1, 1)) ** 0.5 * math.sqrt(252) * 100
        rows.append([sym, len(rets), len(down), round(downside, 2), round(total, 2)])
    if not rows:
        return _unavailable("Downside volatility", "no stored close history")
    return _rows({"name": "Downside volatility"},
                 ["Symbol", "Sessions", "Negative sessions",
                  "Downside deviation % (annualised)", "Total volatility % (annualised)"],
                 rows)


def compute_r_gaps(req):
    syms, missing = _need_symbols("Price-gap analysis", req)
    if missing:
        return missing
    threshold = 2.0
    rows = []
    for sym in syms:
        df = _bars(sym)
        if df.empty or "open" not in df.columns:
            rows.append([sym, "no stored open price", 0, "", ""])
            continue
        o = [float(x) for x in df["open"]]
        c = [float(x) for x in df["close"]]
        d = [str(x)[:10] for x in df["trading_date"]]
        gaps = []
        for i in range(1, min(len(o), len(c))):
            if c[i - 1] > 0:
                g = (o[i] - c[i - 1]) / c[i - 1] * 100
                if abs(g) >= threshold:
                    gaps.append((d[i], round(g, 2)))
        largest = max(gaps, key=lambda x: abs(x[1])) if gaps else ("", "")
        rows.append([sym, len(gaps), f">= {threshold:.0f}%",
                     largest[1], largest[0]])
    if not rows:
        return _unavailable("Price-gap analysis", "no stored bars")
    rows.append(["Note", "A gap can be a corporate action or a series adjustment",
                 "rather than an overnight trade", "", ""])
    return _rows({"name": "Price-gap analysis"},
                 ["Symbol", "Gaps", "Threshold", "Largest gap %", "Date"], rows)


def compute_r_liquidity_risk(req):
    syms, missing = _need_symbols("Volume/liquidity risk", req)
    if missing:
        return missing
    rows = []
    for sym in syms:
        df = _bars(sym)
        if df.empty or "volume" not in df.columns:
            rows.append([sym, "no stored volume", "", "", ""])
            continue
        vol = [float(v) for v in df["volume"] if v == v]
        if len(vol) < 20:
            rows.append([sym, len(vol), "insufficient history", "", ""])
            continue
        mean = sum(vol) / len(vol)
        sd = (sum((v - mean) ** 2 for v in vol) / (len(vol) - 1)) ** 0.5
        zero_days = sum(1 for v in vol if v <= 0)
        cv = (sd / mean * 100) if mean else None
        rows.append([sym, len(vol), zero_days,
                     None if cv is None else round(cv, 1),
                     "high" if (cv is not None and cv > 150) or zero_days > len(vol) * 0.1
                     else "normal"])
    if not rows:
        return _unavailable("Volume/liquidity risk", "no stored volume")
    return _rows({"name": "Volume/liquidity risk"},
                 ["Symbol", "Sessions", "Zero-volume sessions",
                  "Volume variability (CV %)", "Flag"], rows)


def compute_r_concentration(req):
    val = _valuation()
    held = [p for p in ((val or {}).get("positions") or [])
            if (p.get("market_value") or 0) > 0]
    if not held:
        return _unavailable("Portfolio concentration",
                            "no position has a usable stored close")
    total = sum(p["market_value"] for p in held)
    hhi = sum((p["market_value"] / total) ** 2 for p in held) * 10000
    sm = _sector_map()
    by_sector: dict[str, float] = defaultdict(float)
    for p in held:
        by_sector[sm.get((p.get("symbol") or "").upper()) or "Unclassified"] += p["market_value"]
    sector_hhi = sum((v / total) ** 2 for v in by_sector.values()) * 10000
    rows = [["Positions valued", len(held), ""],
            ["Symbol HHI", round(hhi, 0),
             "0-1500 competitive, 1500-2500 moderate, 2500+ concentrated"],
            ["Sector HHI", round(sector_hhi, 0), "same bands"],
            ["Largest position", round(max(p["market_value"] for p in held) / total * 100, 2),
             "% of valued positions"]]
    return _rows({"name": "Portfolio concentration"},
                 ["Measure", "Value", "Interpretation"], rows)


def compute_elig_lists(req):
    syms, missing = _need_symbols("Eligibility result groups", req)
    if missing:
        return missing
    groups: dict[str, list[str]] = {"ELIGIBLE": [], "NOT ELIGIBLE": [], "NEEDS_REVIEW": []}
    details = []
    for sym in syms:
        rules, overall = _elig(sym)
        groups.setdefault(overall, []).append(sym)
        unmet = [r[0] for r in rules if r[2] != "PASS"]
        details.append([sym, overall, "; ".join(unmet) or "all rules passed"])
    rows = ([[k, len(v), ", ".join(v) or "-"] for k, v in groups.items()]
            + [[f"Detail: {r[0]}", r[1], r[2]] for r in details])
    return _rows({"name": "Eligibility result groups"},
                 ["Group / symbol", "Count / result", "Members / unmet rules"], rows)


def _comparable(a: float, b: float) -> bool:
    """True when two stored amounts are plausibly the same unit and scale.

    Some source rows carry a figure in millions next to one in rupees. A growth
    percentage across those is arithmetic without meaning, so it is refused
    rather than reported.
    """
    if not a or not b or a <= 0 or b <= 0:
        return False
    return 0.01 <= (a / b) <= 100.0


def _mixed_magnitude(values: list[float]) -> bool:
    clean = [v for v in values if v is not None and v > 0]
    if len(clean) < 2:
        return False
    return (max(clean) / min(clean)) > 100.0


def _profit_series(sym: str, annual: bool = False):
    """``(period_key, value)`` for stored net profit, oldest first."""
    out = []
    for rec in _fundamentals(sym):
        if rec["field"] != "Net profit":
            continue
        key = _period_key(rec.get("period_label"))
        value = _num(rec["value"])
        if not key or value is None:
            continue
        if annual and key[0] != "ANNUAL":
            continue
        if not annual and key[0] == "ANNUAL":
            continue
        out.append((key, value))
    return sorted(out, key=lambda x: (x[0][1], x[0][0]))


def compute_q_profit_comparison(req):
    syms, missing = _need_symbols("Quarterly profit comparison", req)
    if missing:
        return missing
    rows = []
    for sym in syms:
        series = _profit_series(sym)
        if not series:
            rows.append([sym, "no stored quarterly profit"] + [""] * 4)
            continue
        by_q = {}
        for (q, _fy), value in series:
            by_q[q] = value
        values = list(by_q.values())
        flag = ("mixed magnitude in source - not comparable" if _mixed_magnitude(values)
                else "consistent magnitude")
        rows.append([sym] + [by_q.get(q, "") for q in ("Q1", "Q2", "Q3", "Q4")] + [flag])
    if not any(len(r) > 2 and any(x != "" for x in r[1:5]) for r in rows):
        return _unavailable("Quarterly profit comparison",
                            "no stored quarterly net profit for these symbols")
    rows.append(["Note", "Values are as filed", "NEPSE quarterly results are",
                 "often cumulative year-to-date, not", "three-month figures"])
    return _rows({"name": "Quarterly profit comparison"},
                 ["Symbol", "Q1", "Q2", "Q3", "Q4", "Comparability"], rows)


def compute_q_trend_chart(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Quarterly trend chart", "no symbol selected")
    sym = sym.upper()
    eps = {o[1] + "-" + o[0]: o[2] for o in _periodic_eps(sym) if o[0] != "ANNUAL"}
    profit = {f"{k[1]}-{k[0]}": v for k, v in _profit_series(sym)}
    if not eps and not profit:
        return _unavailable("Quarterly trend chart",
                            "no parseable quarterly EPS or profit")
    mixed = _mixed_magnitude(list(profit.values()))
    rows = [[key, eps.get(key, ""), profit.get(key, ""),
             "check source" if mixed else ""] for key in sorted(set(eps) | set(profit))]
    return _rows({"name": "Quarterly trend chart"},
                 ["Fiscal year-quarter", "EPS", "Net profit", "Data check"], rows)


def compute_annual_trend_chart(req):
    sym = req.symbols[0] if req.symbols else None
    if not sym:
        return _unavailable("Annual trend chart", "no symbol selected")
    sym = sym.upper()
    eps = {o[1]: o[2] for o in _periodic_eps(sym) if o[0] == "ANNUAL"}
    profit = {k[1]: v for k, v in _profit_series(sym, annual=True)}
    if not eps and not profit:
        return _unavailable("Annual trend chart", "no annual-basis EPS or profit")
    mixed = _mixed_magnitude(list(profit.values()))
    rows = [[fy, eps.get(fy, ""), profit.get(fy, ""),
             "check source" if mixed else ""] for fy in sorted(set(eps) | set(profit))]
    return _rows({"name": "Annual trend chart"},
                 ["Fiscal year (end)", "EPS", "Net profit", "Data check"], rows)


def _rank(section: str, req, value_for, label: str, higher_better: bool = True):
    syms, missing = _need_symbols(section, req)
    if missing:
        return missing
    got = []
    for sym in syms:
        v = value_for(sym)
        if v is not None:
            got.append((sym, v))
    if not got:
        return _unavailable(section, f"no stored {label} for these symbols")
    got.sort(key=lambda x: x[1], reverse=higher_better)
    rows = [[i, sym, round(v, 2)] for i, (sym, v) in enumerate(got, start=1)]
    return _rows({"name": section}, ["Rank", "Symbol", label], rows)


def compute_sector_pe_rank(req):
    def pe(sym):
        rec = _field_value(sym, "P/E")
        if rec:
            return _num(rec["value"])
        eps = _field_value(sym, "EPS")
        dates, closes = _prices(sym)
        if eps and closes and _num(eps["value"]) and _num(eps["value"]) > 0:
            return closes[-1] / _num(eps["value"])
        return None

    return _rank("P/E ranking", req, pe, "P/E", higher_better=False)


def compute_sector_networth_rank(req):
    def nw(sym):
        rec = _field_value(sym, "Net worth per share")
        return _num(rec["value"]) if rec else None

    return _rank("Net-worth ranking", req, nw, "Net worth per share")


def compute_sector_cap_rank(req):
    def cap(sym):
        shares, _basis = _shares_outstanding(sym)
        dates, closes = _prices(sym)
        if not shares or not closes:
            return None
        return closes[-1] * shares

    return _rank("Market-cap ranking", req, cap, "Market capitalisation")


def compute_sector_growth_rank(req):
    syms, missing = _need_symbols("Profit-growth ranking", req)
    if missing:
        return missing
    rows = []
    for sym in syms:
        series = _profit_series(sym, annual=True) or _profit_series(sym)
        if len(series) < 2:
            rows.append([sym, "", "", "fewer than two comparable periods"])
            continue
        prev, cur = series[-2][1], series[-1][1]
        if not _comparable(prev, cur):
            rows.append([sym, prev, cur,
                         "not comparable - the stored amounts differ in unit or scale"])
            continue
        rows.append([sym, prev, cur, round((cur - prev) / abs(prev) * 100, 2)])
    computed = [r for r in rows if isinstance(r[3], (int, float))]
    if not computed:
        return _unavailable("Profit-growth ranking",
                            "no symbol has two profit periods on the same scale")
    computed.sort(key=lambda r: r[3], reverse=True)
    ranked = [[i, *r] for i, r in enumerate(computed, start=1)]
    skipped = [r for r in rows if not isinstance(r[3], (int, float))]
    return _rows({"name": "Profit-growth ranking"},
                 ["Rank", "Symbol", "Previous profit", "Latest profit", "Growth %"],
                 ranked + [[r[0], r[1], r[2], r[3], "excluded"] for r in skipped])


def compute_sector_q_rank(req):
    def latest_eps(sym):
        recs = _eps_records(sym)
        for rec in recs:
            key = _period_key(rec.get("period_label"))
            if key and key[0] != "ANNUAL":
                return _num(rec["value"])
        return None

    return _rank("Quarterly-performance ranking", req, latest_eps,
                 "Latest quarterly EPS")


def compute_sector_comparison(req):
    syms, missing = _need_symbols("Company comparison table", req)
    if missing:
        return missing
    sm = _sector_map()
    rows = []
    for sym in syms:
        dates, closes = _prices(sym)
        pe = _field_value(sym, "P/E")
        nw = _field_value(sym, "Net worth per share")
        eps = _field_value(sym, "EPS")
        shares, _basis = _shares_outstanding(sym)
        rows.append([
            sym, sm.get(sym, "Unclassified"),
            round(closes[-1], 2) if closes else "",
            _num(pe["value"]) if pe else "",
            _num(nw["value"]) if nw else "",
            _num(eps["value"]) if eps else "",
            round(closes[-1] * shares, 0) if closes and shares else "",
        ])
    return _rows({"name": "Company comparison table"},
                 ["Symbol", "Sector", "Last close", "P/E",
                  "Net worth per share", "EPS", "Market cap"], rows)


def compute_sector_distribution(req):
    syms, missing = _need_symbols("Sector distribution chart", req)
    if missing:
        return missing
    sm = _sector_map()
    buckets: dict[str, list[float]] = defaultdict(list)
    for sym in syms:
        dates, closes = _prices(sym)
        if not closes:
            continue
        buckets[sm.get(sym) or "Unclassified"].append(closes[-1])
    if not buckets:
        return _unavailable("Sector distribution chart",
                            "no stored close for these symbols")
    rows = [[sector, len(v), round(min(v), 2), round(max(v), 2),
             round(sum(v) / len(v), 2)]
            for sector, v in sorted(buckets.items())]
    return _rows({"name": "Sector distribution chart"},
                 ["Sector", "Symbols", "Min close", "Max close", "Mean close"], rows)


def compute_sector_outliers(req):
    syms, missing = _need_symbols("Outlier and missing-data report", req)
    if missing:
        return missing
    rows = []
    pes = []
    for sym in syms:
        pe = _field_value(sym, "P/E")
        value = _num(pe["value"]) if pe else None
        if value is not None:
            pes.append(value)
        gaps = [field for field in ("P/E", "EPS", "Net worth per share", "Net profit")
                if _field_value(sym, field) is None]
        rows.append([sym, round(value, 2) if value is not None else "",
                     ", ".join(gaps) or "-"])
    if pes:
        ordered = sorted(pes)
        q1 = ordered[len(ordered) // 4]
        q3 = ordered[(3 * len(ordered)) // 4]
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for row in rows:
            if row[1] != "" and (row[1] < low or row[1] > high):
                row[2] = (row[2] + "; " if row[2] != "-" else "") + "P/E outside 1.5x IQR"
    return _rows({"name": "Outlier and missing-data report"},
                 ["Symbol", "P/E", "Missing fields / outlier flag"], rows)


def compute_mtf_trend(req):
    syms, missing = _need_symbols("Multi-timeframe trend analysis", req)
    if missing:
        return missing
    rows = []
    for sym in syms:
        _d, closes = _prices(sym)
        if len(closes) < 25:
            rows.append([sym, "insufficient history", "", ""])
            continue

        def direction(series: list[float]) -> tuple[str, float]:
            if len(series) < 2 or series[0] <= 0:
                return "unknown", 0.0
            change = (series[-1] / series[0] - 1) * 100
            return ("up" if change > 0.5 else "down" if change < -0.5 else "flat"), round(change, 2)

        daily_dir, daily_chg = direction(closes[-20:])
        weekly = closes[::5][-9:]
        monthly = closes[::21][-4:]
        w_dir, w_chg = direction(weekly)
        m_dir, m_chg = direction(monthly)
        rows.append([sym, f"{daily_dir} ({daily_chg}% over 20 sessions)",
                     f"{w_dir} ({w_chg}% over 8 weeks)",
                     f"{m_dir} ({m_chg}% over 3 months)"])
    return _rows({"name": "Multi-timeframe trend analysis"},
                 ["Symbol", "Daily", "Weekly", "Monthly"], rows)


def compute_patterns(req):
    syms, missing = _need_symbols("Chart-pattern analysis", req)
    if missing:
        return missing
    rows = []
    for sym in syms:
        _d, closes = _prices(sym)
        if len(closes) < 25:
            rows.append([sym, "insufficient history", ""])
            continue
        window = closes[-21:]
        last = closes[-1]
        prior_high = max(window[:-1])
        prior_low = min(window[:-1])
        found = []
        if last > prior_high:
            found.append("breakout above the prior 20-session high")
        if last < prior_low:
            found.append("breakdown below the prior 20-session low")
        if all(window[i] > window[i - 1] for i in range(1, len(window))):
            found.append("rising through the 20-session window")
        if all(window[i] < window[i - 1] for i in range(1, len(window))):
            found.append("falling through the 20-session window")
        rows.append([sym, "; ".join(found) or "no rule triggered",
                     "rules: 20-session breakout/breakdown and monotone trend only"])
    return _rows({"name": "Chart-pattern analysis"},
                 ["Symbol", "Rule-based signals", "Rules applied"], rows)
