"""Sasto Share workspace — the additional reference analytics.

The reference platform (NepseAlpha / SastoShare) carries a set of market,
valuation, risk, rotation and dividend views that the core Mega Tool screens did
not surface. This module assembles them from the **same stored data** the rest
of the tool already uses:

* ``price_bars`` (DuckDB) for prices and volume,
* the ``fundamentals`` table (SQLite) for reported figures,
* the corporate-events registry for notices.

Design rules, carried over from the rest of the project:

* Nothing is synthesised. A missing input yields ``null`` plus a reason, never a
  placeholder number — "no dps record stored" is a valid, honest answer.
* Derived numbers say so. Market capitalisation, relative volume, the sector
  index and the volatility cone are all labelled ``derived`` with their input
  and formula, because a researcher must be able to tell a reported figure from
  a computed one.
* Where an alignment is approximate (fundamental periods have no publication
  date, so a period's figure is used from its *period end*), the payload says so
  instead of implying point-in-time precision the data cannot support.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "market_pulse",
    "movers_context",
    "price_valuation_history",
    "valuation_models",
    "levels_and_risk",
    "volatility_projection",
    "sector_rotation",
    "dividends",
    "backtest_vs_hold",
]

#: Bars of history loaded per symbol for the cross-sectional views (the 52-week
#: window the reference dashboard is built on, plus SMA-200 warm-up).
_BULK_BARS = 260

_PERIOD_UNAVAILABLE = (
    "Fundamental periods carry a period end but no publication date, so a "
    "period's figure is applied from its period end — optimistic by the notice "
    "lag. Treat the series as period-aligned, not point-in-time exact."
)


# --------------------------------------------------------------------------- #
# Small numeric helpers
# --------------------------------------------------------------------------- #
def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else f


def _round(value: float | None, dp: int = 2) -> float | None:
    return None if value is None else round(value, dp)


def _finite(arr: Iterable[float], minimum: int) -> np.ndarray | None:
    a = np.asarray(list(arr), dtype=float)
    a = a[np.isfinite(a)]
    return a if a.size >= minimum else None


def _sma(values: np.ndarray, window: int) -> float | None:
    if values.size < window:
        return None
    return float(np.mean(values[-window:]))


def _pct_change(values: np.ndarray, lookback: int) -> float | None:
    if values.size <= lookback:
        return None
    prev = float(values[-lookback - 1])
    if prev == 0:
        return None
    return round((float(values[-1]) / prev - 1.0) * 100.0, 2)


def _rsi(values: np.ndarray, period: int = 14) -> float | None:
    if values.size < period + 1:
        return None
    diff = np.diff(values)
    gains = np.where(diff > 0, diff, 0.0)
    losses = np.where(diff < 0, -diff, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, diff.size):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100.0 - 100.0 / (1.0 + rs), 1)


def _ema_series(values: np.ndarray, period: int) -> np.ndarray | None:
    if values.size < period:
        return None
    alpha = 2.0 / (period + 1.0)
    out = np.empty(values.size - period + 1, dtype=float)
    out[0] = float(np.mean(values[:period]))
    for i, v in enumerate(values[period:], start=1):
        out[i] = alpha * float(v) + (1.0 - alpha) * out[i - 1]
    return out


def _macd(values: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, Any]:
    """MACD on a close series. Returns the latest line/signal/histogram or nulls."""
    ef = _ema_series(values, fast)
    es = _ema_series(values, slow)
    if ef is None or es is None:
        return {"macd": None, "signal": None, "histogram": None, "state": None}
    # Align: the fast EMA starts earlier; trim to the shorter length.
    n = min(ef.size, es.size)
    line = ef[-n:] - es[-n:]
    sig = _ema_series(line, signal)
    if sig is None:
        return {
            "macd": _round(float(line[-1]), 3),
            "signal": None,
            "histogram": None,
            "state": None,
        }
    m = min(line.size, sig.size)
    hist = line[-m:] - sig[-m:]
    state = "bullish" if hist[-1] > 0 else ("bearish" if hist[-1] < 0 else "flat")
    return {
        "macd": _round(float(line[-1]), 3),
        "signal": _round(float(sig[-1]), 3),
        "histogram": _round(float(hist[-1]), 3),
        "state": state,
    }


def _point_in_time(series: list[tuple[str, float]], when: str) -> float | None:
    """The latest value whose period end is on or before ``when`` (None if none)."""
    if not series:
        return None
    dates = [p[0] for p in series]
    i = bisect_right(dates, when)
    return series[i - 1][1] if i else None


# --------------------------------------------------------------------------- #
# Bulk shared data
# --------------------------------------------------------------------------- #
def _bulk_closes(store: Any, bars: int = _BULK_BARS) -> pd.DataFrame:
    """Last ``bars`` usable closes per symbol, ascending, with volume.

    One query, bounded by a window function, so the cross-sectional views do not
    fan out into hundreds of per-symbol round trips.
    """
    sql = f"""
        WITH w AS (
          SELECT symbol, trading_date, close, high, low, volume,
                 ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) AS rn
          FROM price_bars
          WHERE close > 0 AND high >= low
        )
        SELECT symbol, trading_date, close, high, low, volume
        FROM w WHERE rn <= {int(bars)}
        ORDER BY symbol, trading_date
    """
    try:
        df = store.query_df(sql)
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=["symbol", "trading_date", "close", "high", "low", "volume"])
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame(columns=["symbol", "trading_date", "close", "high", "low", "volume"])
    return df


def _latest_fundamentals(conn: Any) -> dict[str, dict[str, tuple[float, str]]]:
    """``{symbol: {field: (value, period_end)}}`` keeping the newest period."""
    out: dict[str, dict[str, tuple[float, str]]] = {}
    try:
        rows = conn.execute("SELECT symbol, field, value, period_end FROM fundamentals")
    except Exception:  # noqa: BLE001
        return out
    for row in rows:
        sym = str(row["symbol"] or "").upper()
        field = str(row["field"] or "")
        value = _num(row["value"])
        end = str(row["period_end"] or "")
        if not sym or not field or value is None:
            continue
        cur = out.setdefault(sym, {}).get(field)
        if cur is None or end > cur[1]:
            out[sym][field] = (value, end)
    return out


def _fundamental_series(conn: Any) -> dict[str, dict[str, list[tuple[str, float, str]]]]:
    """``{symbol: {field: [(period_end, value, period_label)]}}`` ascending."""
    out: dict[str, dict[str, list[tuple[str, float, str]]]] = {}
    try:
        rows = conn.execute(
            "SELECT symbol, field, value, period_end, period_label FROM fundamentals "
            "ORDER BY period_end"
        )
    except Exception:  # noqa: BLE001
        return out
    for row in rows:
        sym = str(row["symbol"] or "").upper()
        field = str(row["field"] or "")
        value = _num(row["value"])
        end = str(row["period_end"] or "")
        label = str(row["period_label"] or "")
        if not sym or not field or value is None or not end:
            continue
        out.setdefault(sym, {}).setdefault(field, []).append((end[:10], value, label))
    return out


def _is_annual_label(label: str) -> bool:
    """True for period labels that carry a full year's figure.

    NEPSE reports quarterly figures as well as an annual report/fourth quarter,
    so the two frequencies live side by side in one column. Anything that needs
    a year's worth of earnings must say which it took.
    """
    low = (label or "").lower()
    return low.startswith("annual report") or "fourth quarter" in low


def _symbol_series(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {str(s): g for s, g in df.groupby("symbol", sort=False)}


def _latest_close(store: Any, symbol: str) -> tuple[float | None, str | None]:
    df = store.query_df(
        "SELECT trading_date, close FROM price_bars WHERE symbol = ? AND close > 0 "
        "ORDER BY trading_date DESC LIMIT 1",
        [symbol.upper()],
    )
    if df is None or getattr(df, "empty", True):
        return None, None
    return _num(df.iloc[0]["close"]), str(df.iloc[0]["trading_date"])[:10]


# --------------------------------------------------------------------------- #
# 1. Market pulse (barometer, sentiment, sector breadth, valuation ranges)
# --------------------------------------------------------------------------- #
def market_pulse(store: Any, conn: Any, sector_map: dict[str, str]) -> dict[str, Any]:
    df = _bulk_closes(store)
    by_symbol = _symbol_series(df)
    funds = _latest_fundamentals(conn)

    above = {"10": [0, 0], "20": [0, 0], "50": [0, 0], "200": [0, 0]}
    sector_ma: dict[str, dict[str, list[int]]] = {}
    near_high = near_low = considered = 0
    positions: list[dict[str, Any]] = []
    golden = [0, 0]

    for sym, g in by_symbol.items():
        closes = np.asarray(g["close"], dtype=float)
        closes = closes[np.isfinite(closes)]
        if closes.size < 20:
            continue
        sector = sector_map.get(sym, "Unclassified")
        bucket = sector_ma.setdefault(
            sector, {k: [0, 0] for k in ("10", "20", "50", "200", "50_200")}
        )
        for key, window in (("10", 10), ("20", 20), ("50", 50), ("200", 200)):
            s = _sma(closes, window)
            if s is None:
                continue
            ok = bool(closes[-1] >= s)
            above[key][1] += 1
            bucket[key][1] += 1
            if ok:
                above[key][0] += 1
                bucket[key][0] += 1
        s50, s200 = _sma(closes, 50), _sma(closes, 200)
        if s50 is not None and s200 is not None:
            golden[1] += 1
            bucket["50_200"][1] += 1
            if s50 > s200:
                golden[0] += 1
                bucket["50_200"][0] += 1
        # 52-week (250-bar) position — only when the window is really available.
        if closes.size >= 200:
            window = closes[-250:]
            lo, hi = float(window.min()), float(window.max())
            considered += 1
            if hi > lo:
                pos = (float(closes[-1]) - lo) / (hi - lo)
                positions.append(
                    {
                        "symbol": sym,
                        "sector": sector,
                        "position": round(pos, 3),
                        "low_250": round(lo, 2),
                        "high_250": round(hi, 2),
                        "close": round(float(closes[-1]), 2),
                    }
                )
                if pos >= 0.95:
                    near_high += 1
                if pos <= 0.05:
                    near_low += 1

    sentiment = {
        "above_50": {
            "count": above["50"][0],
            "denominator": above["50"][1],
            "pct": _round(above["50"][0] / above["50"][1] * 100.0, 2) if above["50"][1] else None,
        },
        "above_200": {
            "count": above["200"][0],
            "denominator": above["200"][1],
            "pct": _round(above["200"][0] / above["200"][1] * 100.0, 2)
            if above["200"][1]
            else None,
        },
    }
    barometer = {
        "near_high": {
            "count": near_high,
            "denominator": considered,
            "pct": _round(near_high / considered * 100.0, 2) if considered else None,
        },
        "near_low": {
            "count": near_low,
            "denominator": considered,
            "pct": _round(near_low / considered * 100.0, 2) if considered else None,
        },
        "definition": "52-week position = (close − 250-bar low) / (250-bar high − 250-bar low); "
        "near high is ≥ 0.95, near low is ≤ 0.05, over the last 250 stored bars.",
    }

    sector_ma_rows = []
    for sector, b in sorted(sector_ma.items()):
        row: dict[str, Any] = {"sector": sector}
        for key, label in (
            ("10", "above_sma_10"),
            ("20", "above_sma_20"),
            ("50", "above_sma_50"),
            ("200", "above_sma_200"),
            ("50_200", "sma_50_above_200"),
        ):
            n, d = b[key]
            row[label] = {
                "count": n,
                "denominator": d,
                "pct": _round(n / d * 100.0, 2) if d else None,
            }
        sector_ma_rows.append(row)
    sector_ma_rows.sort(key=lambda r: -(r["above_sma_50"]["pct"] or -1))

    # PE / PB / price / dividend-yield distributions by sector.
    price_by_symbol = {s: float(g["close"].iloc[-1]) for s, g in by_symbol.items()}

    def _dist(value_of, edges: list[float]) -> list[dict[str, Any]]:
        rows = []
        for sector in sorted({sector_map.get(s, "Unclassified") for s in price_by_symbol}):
            members = [s for s in price_by_symbol if sector_map.get(s, "Unclassified") == sector]
            vals = [v for v in (value_of(s) for s in members) if v is not None]
            counts = [0] * (len(edges) + 1)
            for v in vals:
                placed = False
                for i in range(len(edges) - 1):
                    if edges[i] <= v < edges[i + 1]:
                        counts[i] += 1
                        placed = True
                        break
                if not placed:
                    counts[-1] += 1
            labels = [f"{edges[i]:g}–{edges[i + 1]:g}" for i in range(len(edges) - 1)]
            labels.append(f"{edges[-1]:g}+")
            rows.append(
                {
                    "sector": sector,
                    "n": len(vals),
                    "bins": [{"label": labels[i], "count": counts[i]} for i in range(len(labels))],
                }
            )
        return rows

    def _pe(s: str) -> float | None:
        f = funds.get(s) or {}
        v = f.get("pe", (None, ""))[0]
        if v is not None and v > 0:
            return v
        eps = f.get("eps", (None, ""))[0]
        price = price_by_symbol.get(s)
        if eps and eps > 0 and price:
            return price / eps
        return None

    def _pb(s: str) -> float | None:
        f = funds.get(s) or {}
        bv = f.get("net_worth_per_share", (None, ""))[0]
        price = price_by_symbol.get(s)
        if bv and bv > 0 and price:
            return price / bv
        return None

    return {
        "barometer": barometer,
        "sentiment": sentiment,
        "golden_cross": {
            "count": golden[0],
            "denominator": golden[1],
            "pct": _round(golden[0] / golden[1] * 100.0, 2) if golden[1] else None,
            "definition": "share of symbols whose SMA(50) is above SMA(200) — a state, not a signal.",
        },
        "sector_ma": sector_ma_rows,
        "pe_ranges": _dist(_pe, [0, 15, 30, 50, 75, 100]),
        "pb_ranges": _dist(_pb, [0, 1, 2, 4, 6, 10]),
        "price_ranges": _dist(lambda s: price_by_symbol.get(s), [0, 100, 300, 500, 1000, 2500]),
        "universe": {"symbols_with_bars": len(by_symbol), "considered_52w": considered},
        "sector_ma_definition": "Each percentage is over the symbols in that sector that have the required "
        "SMA window available — a sector with few long-history symbols says so via its "
        "denominator, it is never filled in from the whole market.",
    }


# --------------------------------------------------------------------------- #
# 2. Movers with sparkline + 52-week range + market cap
# --------------------------------------------------------------------------- #
def movers_context(
    store: Any,
    conn: Any,
    quotes: list[dict[str, Any]],
    limit: int = 12,
    spark: int = 30,
) -> dict[str, Any]:
    funds = _latest_fundamentals(conn)
    by_symbol = _symbol_series(_bulk_closes(store))
    out: dict[str, list[dict[str, Any]]] = {"gainers": [], "losers": []}

    def _decorate(q: dict[str, Any]) -> dict[str, Any]:
        sym = str(q.get("symbol") or "").upper()
        g = by_symbol.get(sym)
        row: dict[str, Any] = {
            "symbol": sym,
            "ltp": _num(q.get("ltp")),
            "percent_change": _num(q.get("percent_change")),
            "volume": _num(q.get("volume")),
            "sparkline": [],
            "sparkline_state": "unavailable",
            "range_52w": None,
            "market_cap": None,
            "rvolume": None,
        }
        if g is not None and len(g):
            closes = [float(v) for v in g["close"].tolist() if _num(v) is not None]
            row["sparkline"] = [_round(c, 2) for c in closes[-spark:]]
            row["sparkline_state"] = "stored daily closes (not intraday)"
            window = closes[-250:]
            lo, hi = min(window), max(window)
            if hi > lo:
                pos = (closes[-1] - lo) / (hi - lo)
                row["range_52w"] = {
                    "low": _round(lo, 2),
                    "high": _round(hi, 2),
                    "position": _round(pos, 3),
                    "bars": len(window),
                    "basis": "close-based 250-bar range",
                }
            elif hi == lo:
                row["range_52w"] = {
                    "low": _round(lo, 2),
                    "high": _round(hi, 2),
                    "position": None,
                    "bars": len(window),
                    "basis": "flat window — a position is undefined when high equals low",
                }
            vols = [float(v) for v in g["volume"].tolist() if _num(v) is not None]
            if len(vols) >= 21 and float(np.mean(vols[-21:-1])) > 0:
                row["rvolume"] = _round(vols[-1] / float(np.mean(vols[-21:-1])), 2)
        f = funds.get(sym) or {}
        cap = f.get("paid_up_capital", (None, ""))[0]
        # The cap uses the quote's last price only. If the quote has no price the
        # cap is unavailable rather than borrowed from a different field.
        price = row["ltp"]
        if cap and price:
            # NEPSE face value is NRs 100, so shares = paid-up capital / 100.
            row["market_cap"] = {
                "value_npr": _round(cap / 100.0 * price, 0),
                "kind": "derived",
                "formula": "paid_up_capital / 100 × last price (NRs 100 face value)",
                "input_period": f.get("paid_up_capital", (None, ""))[1],
            }
        else:
            missing = "paid-up capital" if not cap else "last price"
            row["market_cap"] = {
                "value_npr": None,
                "kind": "derived",
                "unavailable_reason": f"no {missing} stored for {sym}",
            }
        return row

    ranked = [q for q in quotes if _num(q.get("percent_change")) is not None]
    ranked.sort(key=lambda q: float(q["percent_change"]), reverse=True)
    out["gainers"] = [_decorate(q) for q in ranked[:limit]]
    out["losers"] = [_decorate(q) for q in list(reversed(ranked))[:limit]]
    out["coverage"] = {
        "quotes": len(quotes),
        "with_sparkline": sum(1 for r in out["gainers"] + out["losers"] if r["sparkline"]),
        "note": "Sparklines are stored daily closes. The reference site draws intraday lines; "
        "no intraday series is stored here, so none is drawn.",
    }
    return out


# --------------------------------------------------------------------------- #
# 3. Historical P/E and P/B (multi-pane) — real series, honestly aligned
# --------------------------------------------------------------------------- #
def price_valuation_history(
    store: Any,
    conn: Any,
    symbol: str,
    sector_map: dict[str, str],
    limit: int = 750,
    sectors: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    sym = symbol.upper()
    df = store.get_bars(sym, limit=limit)
    if df is None or getattr(df, "empty", True):
        return {"symbol": sym, "available": False, "reason": f"no stored history for {sym}"}

    dates = [str(pd.Timestamp(d).date()) for d in df["trading_date"]]
    closes = [float(v) for v in df["close"].tolist()]
    series = _fundamental_series(conn).get(sym, {})
    eps_series = series.get("eps", [])
    bv_series = series.get("net_worth_per_share", [])

    pe = [
        _round(closes[i] / e, 3) if (e := _point_in_time(eps_series, d)) and e > 0 else None
        for i, d in enumerate(dates)
    ]
    pb = [
        _round(closes[i] / b, 3) if (b := _point_in_time(bv_series, d)) and b > 0 else None
        for i, d in enumerate(dates)
    ]

    # A reported EPS that is a small fraction of the symbol's own annual run-rate
    # is almost always a partial-period or mislabelled figure. It stays in the
    # series (hiding it would be dishonest) but it is flagged, because a single
    # such period is what makes a P/E line spike into the thousands and become
    # unreadable.
    annual_eps = sorted(v for _d, v, _l in eps_series if _is_annual_label(_l) and v > 0)
    median_annual = annual_eps[len(annual_eps) // 2] if annual_eps else None
    suspect: list[dict[str, Any]] = []
    if median_annual and median_annual > 0:
        for d, v, label in eps_series:
            if v is not None and 0 < v < 0.2 * median_annual:
                suspect.append(
                    {
                        "period_end": d,
                        "eps": _round(v, 3),
                        "label": label,
                        "median_annual_eps": _round(median_annual, 3),
                    }
                )

    finite_pe = [(i, v) for i, v in enumerate(pe) if v is not None]
    pe_cap = 150.0
    pe_above_cap = [(i, v) for i, v in finite_pe if v > pe_cap]
    pe_largest = None
    if finite_pe:
        i, v = max(finite_pe, key=lambda t: t[1])
        pe_largest = {
            "value": v,
            "date": dates[i],
            "eps": _round(_point_in_time(eps_series, dates[i]) or 0.0, 3),
        }

    sector = sector_map.get(sym, "Unclassified")
    members = [s for s in (sectors or {}).get(sector, []) if s != sym][:80]
    sector_pe_series: list[dict[str, Any]] = []
    if members and eps_series:
        # Monthly samples keep the cross-section cheap while still showing shape.
        sample_idx = [i for i in range(len(dates)) if i == 0 or dates[i][:7] != dates[i - 1][:7]]
        member_data: list[tuple[list[str], np.ndarray, list[tuple[str, float, str]]]] = []
        for m in members:
            mdf = store.get_bars(m, limit=limit)
            if mdf is None or getattr(mdf, "empty", True):
                continue
            mseries = _fundamental_series(conn).get(m, {}).get("eps", [])
            if not mseries:
                continue
            md = [str(pd.Timestamp(d).date()) for d in mdf["trading_date"]]
            mc = np.asarray(mdf["close"], dtype=float)
            member_data.append((md, mc, mseries))
        for i in sample_idx:
            d = dates[i]
            base = closes[i]
            vals: list[float] = [base / e for e in [_point_in_time(eps_series, d)] if e and e > 0]
            for md, mc, ms in member_data:
                j = bisect_right(md, d) - 1
                if j < 0:
                    continue
                e = _point_in_time(ms, d)
                if e and e > 0:
                    vals.append(float(mc[j]) / e)
            if len(vals) >= 5:
                sector_pe_series.append(
                    {"date": d, "pe": _round(float(np.median(vals)), 3), "n": len(vals)}
                )

    latest_eps = _point_in_time(eps_series, dates[-1]) if eps_series else None
    latest_bv = _point_in_time(bv_series, dates[-1]) if bv_series else None
    reason_bits = []
    if not eps_series:
        reason_bits.append("no eps record stored")
    if not bv_series:
        reason_bits.append("no net_worth_per_share record stored")
    return {
        "symbol": sym,
        "sector": sector,
        "available": bool(eps_series or bv_series),
        "reason": "; ".join(reason_bits) or None,
        "dates": dates,
        "close": [_round(c, 2) for c in closes],
        "pe": pe,
        "pb": pb,
        "pe_last": pe[-1],
        "pb_last": pb[-1],
        "eps_periods": len(eps_series),
        "pb_periods": len(bv_series),
        "latest": {
            "eps": _round(latest_eps, 3),
            "bvps": _round(latest_bv, 3),
            "close": _round(closes[-1], 2),
        },
        "sector_pe_series": sector_pe_series,
        "pe_axis": {
            "cap": pe_cap,
            "points_above_cap": len(pe_above_cap),
            "largest": pe_largest,
        },
        "suspect_periods": suspect,
        "alignment_note": _PERIOD_UNAVAILABLE,
        "method": "P/E = close / latest reported EPS whose period end ≤ the bar date; "
        "P/B = close / latest reported net worth per share on the same rule. The "
        "denominator is whichever period the source published last, so the line "
        "steps at each report date as the price moves with it.",
        "caveats": [
            "A reported EPS is an annual/quarterly figure, so the P/E line is a step function, not a daily re-rating.",
            "The fundamentals column holds both quarterly and annual figures. The P/E uses the most recent one; the growth rate uses ANNUAL (Annual Report / Fourth Quarter) periods only.",
            "The sector line is the median P/E of same-sector symbols sampled monthly (minimum 5 symbols).",
            "A period whose EPS is under a fifth of the symbol's own median annual EPS is listed under suspect_periods: it is usually a partial period or a mislabelled figure, and it is what stretches the top of an unguarded P/E axis.",
        ],
    }


# --------------------------------------------------------------------------- #
# 4. Valuation models (Graham, margin of safety, Gordon, PEG)
# --------------------------------------------------------------------------- #
def valuation_models(
    conn: Any,
    store: Any,
    symbol: str,
    growth_override: float | None = None,
    required_return: float | None = None,
) -> dict[str, Any]:
    sym = symbol.upper()
    latest = _latest_fundamentals(conn).get(sym, {})
    series = _fundamental_series(conn).get(sym, {})
    price, price_date = _latest_close(store, sym)

    eps = (latest.get("eps") or (None, ""))[0]
    eps_end = (latest.get("eps") or (None, ""))[1]
    bvps = (latest.get("net_worth_per_share") or (None, ""))[0]
    pe = (latest.get("pe") or (None, ""))[0]

    # EPS CAGR from the stored EPS history (annual periods only, so quarters do
    # not masquerade as years).
    eps_hist = series.get("eps", [])
    annual_pairs = [(d, v) for d, v, lbl in eps_hist if _is_annual_label(lbl)]
    annual = [v for _d, v in annual_pairs]
    growth = None
    growth_basis = None
    if len(annual) >= 3 and annual[0] > 0:
        years = len(annual) - 1
        if years > 0:
            growth = round(((annual[-1] / annual[0]) ** (1.0 / years) - 1.0) * 100.0, 2)
            growth_basis = (
                f"CAGR over {years} year(s) of stored ANNUAL EPS "
                f"({annual_pairs[0][0]} → {annual_pairs[-1][0]})"
            )
    elif growth_override is None:
        # Say exactly which condition failed: "no annual series" and "the earliest
        # annual figure is a loss" are different facts, and a CAGR off a negative
        # base is undefined rather than zero.
        if len(annual) < 3:
            growth_basis = (
                f"only {len(annual)} stored annual (Annual Report / Fourth Quarter) "
                "EPS period(s); a CAGR needs at least 3"
            )
        else:
            growth_basis = (
                f"the earliest stored annual EPS ({annual_pairs[0][0]}) is "
                f"{_round(annual[0], 3)}, so a compounded growth rate is undefined "
                "(it has no positive base)"
            )
    if growth_override is not None:
        growth = growth_override
        growth_basis = "user-supplied growth assumption"

    models: list[dict[str, Any]] = []

    def model(name, formula, value, inputs, missing, notes, **extra):
        models.append(
            {
                "model": name,
                "formula": formula,
                "value": _round(value, 2) if value is not None else None,
                "inputs": inputs,
                "missing": missing,
                "notes": notes,
                **extra,
            }
        )

    graham = None
    if eps and bvps and eps > 0 and bvps > 0:
        graham = math.sqrt(22.5 * eps * bvps)
    model(
        "Graham number",
        "√(22.5 × EPS × BVPS)",
        graham,
        {"eps": _round(eps, 3), "eps_period": eps_end, "bvps": _round(bvps, 3)},
        []
        if graham is not None
        else [
            (("no" if not eps else "non-positive") + " EPS" if not eps or eps <= 0 else "BVPS")
            + " stored"
        ],
        "Defensive-investor ceiling: the price above which the Graham tests are not met. "
        "It assumes both figures are current — here EPS is a reported period figure, not a forecast.",
    )

    mos = None
    if graham and price and graham > 0:
        mos = (graham - price) / graham * 100.0
    model(
        "Margin of safety",
        "(Graham number − price) / Graham number × 100",
        mos,
        {"graham": _round(graham, 2), "price": _round(price, 2), "price_date": price_date},
        [] if mos is not None else ["Graham number or price unavailable"],
        "Negative means the price is above the Graham ceiling. It is a distance from one "
        "formula, not a probability of loss.",
    )

    gordon = None
    dps = (latest.get("dps") or (None, ""))[0]
    r = required_return if required_return is not None else 12.0
    g = growth if growth is not None else None
    if dps and g is not None and r is not None and (r / 100.0) > (g / 100.0) and g > -100:
        gordon = dps * (1 + g / 100.0) / ((r / 100.0) - (g / 100.0))
    missing_gordon = []
    if not dps:
        missing_gordon.append("no dps record stored")
    if g is None:
        missing_gordon.append("growth unavailable")
    if g is not None and (r is not None and (r / 100.0) <= (g / 100.0)):
        missing_gordon.append("required return must exceed growth for the model to be finite")
    model(
        "Gordon growth",
        "DPS × (1 + g) / (r − g)",
        gordon,
        {
            "dps": _round(dps, 3) if dps else None,
            "growth_pct": g,
            "growth_basis": growth_basis,
            "required_return_pct": r,
        },
        missing_gordon,
        "A constant-growth perpetuity: it assumes growth continues forever below the "
        "discount rate. With no stored DPS it is unavailable — the model is not run on a guess.",
    )

    peg = None
    if pe and growth and growth > 0:
        peg = pe / growth
    model(
        "PEG ratio",
        "P/E ÷ earnings growth (%)",
        peg,
        {"pe": _round(pe, 3), "growth_pct": growth, "growth_basis": growth_basis},
        [] if peg is not None else ["P/E or positive growth unavailable"],
        "Only meaningful against a peer set; below 1 is the conventional screening line, not a verdict.",
    )

    return {
        "symbol": sym,
        "price": _round(price, 2),
        "price_date": price_date,
        "eps": _round(eps, 3),
        "eps_period": eps_end,
        "bvps": _round(bvps, 3),
        "pe": _round(pe, 3),
        "growth_pct": growth,
        "growth_basis": growth_basis,
        "assumptions": {
            "required_return_pct": r,
            "required_return_note": "User-supplied discount rate (default 12%). It is an assumption, not a stored figure.",
            "alignment_note": _PERIOD_UNAVAILABLE,
        },
        "models": models,
        "caveats": [
            "Every input is a reported figure with its own period; a stale input makes the output stale.",
            "These are classical textbook formulas applied to stored data, not recommendations.",
        ],
    }


# --------------------------------------------------------------------------- #
# 5. Support / resistance + risk-reward (daily and weekly) + volatility cone
# --------------------------------------------------------------------------- #
def _weekly_frame(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["trading_date"] = pd.to_datetime(d["trading_date"])
    d = d.set_index("trading_date")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in d:
        agg["volume"] = "sum"
    out = d.resample("W-FRI").agg(agg).dropna(subset=["close"]).reset_index()
    return out


def levels_and_risk(
    store: Any,
    symbol: str,
    limit: int = 250,
    account_size: float = 100_000.0,
    risk_fraction: float = 0.01,
) -> dict[str, Any]:
    from megatool.swing_workbench import swing_workbench

    sym = symbol.upper()
    df = store.get_bars(sym, limit=max(limit, 60))
    if df is None or getattr(df, "empty", True) or len(df) < 20:
        return {"symbol": sym, "available": False, "reason": f"not enough stored history for {sym}"}

    daily = swing_workbench(df, account_size=account_size, risk_fraction=risk_fraction)
    weekly = None
    wk = _weekly_frame(df)
    if len(wk) >= 20:
        try:
            weekly = swing_workbench(wk, account_size=account_size, risk_fraction=risk_fraction)
        except Exception:  # noqa: BLE001
            weekly = None

    def _frame(payload: dict[str, Any], timeframe: str) -> dict[str, Any]:
        ref = payload.get("reference_levels") or {}
        near = payload.get("nearest_levels") or {}
        sizing = payload.get("sizing") or {}
        return {
            "timeframe": timeframe,
            "bars": payload.get("bars"),
            "first_date": payload.get("first_date"),
            "last_date": payload.get("last_date"),
            "trend": (payload.get("structure") or {}).get("trend"),
            "support": near.get("support"),
            "resistance": near.get("resistance"),
            "support_missing_reason": near.get("support_missing_reason"),
            "resistance_missing_reason": near.get("resistance_missing_reason"),
            "last_close": ref.get("last_close"),
            "last_swing_high": ref.get("last_swing_high"),
            "last_swing_low": ref.get("last_swing_low"),
            "entry": None,
            "stop": ref.get("invalidation"),
            "target": ref.get("target"),
            "risk_pct": ref.get("risk_pct"),
            "reward_pct": ref.get("reward_pct"),
            "reward_risk": ref.get("reward_risk"),
            "framing_reason": ref.get("reason"),
            "per_share_risk": sizing.get("per_share_risk"),
            "position_shares": sizing.get("shares"),
            "position_notional": sizing.get("notional"),
            "sizing_reason": sizing.get("reason"),
            "checklist": payload.get("checklist"),
        }

    return {
        "symbol": sym,
        "available": True,
        "as_of": daily.get("last_date"),
        "daily": _frame(daily, "daily"),
        "weekly": _frame(weekly, "weekly")
        if weekly
        else {
            "timeframe": "weekly",
            "available": False,
            "reason": f"only {len(wk)} weekly bar(s) — the weekly structure needs at least 20",
        },
        "caveats": daily.get("caveats"),
        "disclaimer": daily.get("disclaimer"),
        "levels_note": "Entry is deliberately not invented: the reference tables show an entry only when the "
        "engine framed a level. Where it is absent the reason from the engine is shown instead.",
    }


def volatility_projection(store: Any, symbol: str, limit: int = 750) -> dict[str, Any]:
    from megatool.ta.volatility import historical_volatility

    sym = symbol.upper()
    df = store.get_bars(sym, limit=limit)
    if df is None or getattr(df, "empty", True) or len(df) < 40:
        return {"symbol": sym, "available": False, "reason": f"not enough stored history for {sym}"}

    close = np.asarray(df["close"], dtype=float)
    close = close[np.isfinite(close) & (close > 0)]
    if close.size < 40:
        return {"symbol": sym, "available": False, "reason": "fewer than 40 usable closes"}
    rets = np.diff(np.log(close))
    daily_vol = float(np.std(rets, ddof=1))
    ann_vol = daily_vol * math.sqrt(252.0)

    # 20-day realised vol, and its percentile within the last year — context for
    # whether today's vol is high or low for THIS symbol.
    win = 20
    rolled = [float(np.std(rets[i - win : i], ddof=1)) for i in range(win, rets.size + 1)]
    rolled_arr = np.asarray(rolled, dtype=float) if rolled else np.asarray([], dtype=float)
    hv20 = rolled_arr[-1] if rolled_arr.size else None
    hv_pct_1y = None
    if rolled_arr.size >= 60:
        year = rolled_arr[-252:] if rolled_arr.size >= 252 else rolled_arr
        hv_pct_1y = round(float((year <= hv20).mean() * 100.0), 1)

    # Volatility is not constant in time; a projection that ignored that would
    # understate tail risk. ewma gives the recent regime a fairer weight.
    lam = 0.94
    var = float(rets[:20].var(ddof=1))
    for r in rets[20:]:
        var = lam * var + (1 - lam) * float(r) * float(r)
    ewma_daily = math.sqrt(var)

    last = float(close[-1])
    horizons = [5, 10, 20, 60]
    cone = []
    for h in horizons:
        sigma = daily_vol * math.sqrt(h)
        sigma_e = ewma_daily * math.sqrt(h)
        cone.append(
            {
                "horizon_days": h,
                "sigma_move_pct": round(sigma * 100.0, 2),
                "sigma_move_pct_ewma": round(sigma_e * 100.0, 2),
                "band_1sigma": [
                    _round(last * math.exp(-sigma), 2),
                    _round(last * math.exp(sigma), 2),
                ],
                "band_2sigma": [
                    _round(last * math.exp(-2 * sigma), 2),
                    _round(last * math.exp(2 * sigma), 2),
                ],
                "ewma_band_1sigma": [
                    _round(last * math.exp(-sigma_e), 2),
                    _round(last * math.exp(sigma_e), 2),
                ],
            }
        )

    beta = None
    beta_note = None
    try:
        # The official index lives in its own table, not in `price_bars`.
        idx = store.index_closes("NEPSE")
        if idx is None or getattr(idx, "empty", True) or len(idx) < 60:
            beta_note = "the NEPSE index series is not stored, so beta cannot be computed"
        else:
            if limit and len(idx) > limit:
                idx = idx.tail(limit)
            m = pd.merge(
                df[["trading_date", "close"]].assign(
                    trading_date=lambda d: pd.to_datetime(d["trading_date"])
                ),
                idx[["trading_date", "close"]].assign(
                    trading_date=lambda d: pd.to_datetime(d["trading_date"])
                ),
                on="trading_date",
                how="inner",
                suffixes=("_s", "_m"),
            )
            m = m.tail(63)  # about three months of trading days
            if len(m) >= 30:
                rs = np.diff(np.log(np.asarray(m["close_s"], dtype=float)))
                rm = np.diff(np.log(np.asarray(m["close_m"], dtype=float)))
                var_m = float(np.var(rm, ddof=1))
                if var_m > 0:
                    beta = round(float(np.cov(rs, rm, ddof=1)[0, 1] / var_m), 3)
            else:
                beta_note = f"only {len(m)} overlapping bar(s) with the index in the last 3 months"
    except Exception as exc:  # noqa: BLE001
        beta_note = f"beta unavailable: {exc}"

    hv = historical_volatility({"close": np.asarray(df["close"], dtype=float)}) if len(df) else None
    hv_series = None
    if hv is not None and getattr(hv, "values", None):
        raw = hv.values.get("hv")
        if raw is not None:
            hv_series = [None if v != v else round(float(v), 2) for v in np.asarray(raw)]
    return {
        "symbol": sym,
        "available": True,
        "last_close": _round(last, 2),
        "as_of": str(pd.Timestamp(df["trading_date"].iloc[-1]).date()),
        "daily_vol_pct": round(daily_vol * 100.0, 3),
        "annualised_vol_pct": round(ann_vol * 100.0, 2),
        "hv_20d_pct": _round(hv20 * 100.0, 3) if hv20 is not None else None,
        "hv_percentile_1y": hv_pct_1y,
        "ewma_daily_vol_pct": round(ewma_daily * 100.0, 3),
        "beta_3m": beta,
        "beta_note": beta_note,
        "historical_vol_indicator": hv_series,
        "cone": cone,
        "method": "σ_daily = sample standard deviation of log returns; the cone scales it by √horizon "
        "(square-root-of-time). The EWMA variant (λ=0.94) weights recent returns more, and both "
        "bands are lognormal quantiles around the last close.",
        "uncertainty": "These are historical estimates, not forecasts. Square-root-of-time assumes returns are "
        "independent and identically distributed; real markets have fat tails and volatility "
        "clustering, so the tails are usually wider than the bands suggest.",
    }


# --------------------------------------------------------------------------- #
# 6. Sector rotation
# --------------------------------------------------------------------------- #
def sector_rotation(store: Any, sector_map: dict[str, str], bars: int = 260) -> dict[str, Any]:
    df = _bulk_closes(store, bars)
    by_symbol = _symbol_series(df)
    sectors: dict[str, list[str]] = {}
    for sym in by_symbol:
        sectors.setdefault(sector_map.get(sym, "Unclassified"), []).append(sym)

    rows: list[dict[str, Any]] = []
    for sector, members in sectors.items():
        closes = []
        for sym in members:
            g = by_symbol[sym]
            c = np.asarray(g["close"], dtype=float)
            c = c[np.isfinite(c)]
            # A member with too little history is left out of the index rather
            # than truncating the whole sector to its shortest member.
            if c.size >= 60:
                closes.append(c)
        if len(closes) < 3:
            continue
        n = min(c.size for c in closes)
        mat = np.vstack([c[-n:] for c in closes])
        # Equal-weight index rebased to 100 at the first common bar. This is a
        # derived aggregate, and it is labelled as one.
        rebased = mat / mat[:, [0]]
        index = rebased.mean(axis=0) * 100.0
        rows.append(
            {
                "sector": sector,
                "members": len(closes),
                "members_in_sector": len(members),
                "members_excluded_short_history": len(members) - len(closes),
                "bars": n,
                "index_last": round(float(index[-1]), 2),
                "return_1w_pct": _pct_change(index, 5),
                "return_1m_pct": _pct_change(index, 21),
                "return_3m_pct": _pct_change(index, 63),
                "return_6m_pct": _pct_change(index, 126),
                "rsi_14": _rsi(index, 14),
                "macd": _macd(index),
                "index_series": [round(float(v), 2) for v in index[-90:]],
            }
        )

    if not rows:
        return {
            "available": False,
            "reason": "no sector has three members with 60+ stored bars",
            "sectors": [],
            "sectors_map_size": len(sectors),
        }

    for key in ("return_1m_pct", "return_3m_pct"):
        ranked = sorted([r for r in rows if r.get(key) is not None], key=lambda r: -r[key])
        for i, r in enumerate(ranked, start=1):
            r[f"rank_{key.split('_')[1]}"] = i
    for r in rows:
        r1, r3 = r.get("return_1m_pct"), r.get("return_3m_pct")
        if r1 is None or r3 is None:
            r["regime"] = "insufficient history"
        elif r1 > 0 and r3 > 0:
            r["regime"] = "leading (positive 1m and 3m)"
        elif r1 > 0 and r3 <= 0:
            r["regime"] = "improving (1m positive, 3m negative)"
        elif r1 <= 0 and r3 > 0:
            r["regime"] = "weakening (1m negative, 3m positive)"
        else:
            r["regime"] = "lagging (negative 1m and 3m)"

    rows.sort(
        key=lambda r: -(r.get("return_1m_pct") if r.get("return_1m_pct") is not None else -999)
    )
    leader = next((r["sector"] for r in rows if r.get("rank_1m") == 1), None)
    return {
        "available": True,
        "method": "Each sector line is an equal-weight index of the closes of its members that have at "
        "least 60 stored bars, rebased to 100 at their first common bar; a member with "
        "shorter history is excluded rather than truncating the sector. RSI(14) and "
        "MACD(12,26,9) are computed on that derived index.",
        "caveats": [
            "An equal-weight index is not the exchange's sector index; it is a derived aggregate over the "
            "members with enough stored history.",
            "Returns are measured on stored closes and ignore dividends and corporate actions.",
        ],
        "leader_1m": leader,
        "sectors": rows,
    }


# --------------------------------------------------------------------------- #
# 7. Dividends
# --------------------------------------------------------------------------- #
def dividends(conn: Any, store: Any, symbol: str | None = None) -> dict[str, Any]:
    sym = (symbol or "").upper() or None
    events: list[dict[str, Any]] = []
    try:
        from megatool.corporate_events import calendar

        payload = calendar(conn, since=None, until=None)
        events = payload.get("events", []) if isinstance(payload, dict) else []
    except Exception:  # noqa: BLE001
        events = []
    if sym:
        events = [e for e in events if str(e.get("symbol") or "").upper() == sym]

    dividend_types = ("dividend", "bonus", "rights", "cash")
    dividend_events = [
        e for e in events if str(e.get("event_type") or "").lower() in dividend_types
    ]

    yields: list[dict[str, Any]] = []
    funds = _latest_fundamentals(conn)
    by_symbol = _symbol_series(_bulk_closes(store))
    for s, g in by_symbol.items():
        if sym and s != sym:
            continue
        f = funds.get(s) or {}
        dps = (f.get("dps") or (None, ""))[0]
        eps = (f.get("eps") or (None, ""))[0]
        price = _num(g["close"].iloc[-1])
        if dps and price:
            yields.append(
                {
                    "symbol": s,
                    "dps": _round(dps, 3),
                    "price": _round(price, 2),
                    "yield_pct": _round(dps / price * 100.0, 2),
                    "payout_pct": _round(dps / eps * 100.0, 2) if eps and eps > 0 else None,
                    "dps_period": f.get("dps", (None, ""))[1],
                    "kind": "derived",
                }
            )

    buckets = [0, 2.5, 5, 7.5, 10]
    labels = [f"{buckets[i]:g}–{buckets[i + 1]:g}%" for i in range(len(buckets) - 1)] + [
        f"{buckets[-1]:g}%+"
    ]
    counts = [0] * len(labels)
    for y in yields:
        placed = False
        for i in range(len(buckets) - 1):
            if buckets[i] <= y["yield_pct"] < buckets[i + 1]:
                counts[i] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1

    return {
        "symbol": sym,
        "events": dividend_events,
        "event_count": len(dividend_events),
        "event_types_recorded": sorted({str(e.get("event_type")) for e in events}),
        "yields": sorted(yields, key=lambda y: -(y["yield_pct"] or 0))[:50],
        "yield_distribution": [
            {"label": labels[i], "count": counts[i]} for i in range(len(labels))
        ],
        "yield_denominator": len(yields),
        "coverage": {
            "symbols_with_bars": len(by_symbol),
            "symbols_with_dps": len(yields),
            "dividend_notices": len(dividend_events),
            "note": "A dividend row appears only where a dividend-per-share figure is stored. 'No yields' means "
            "no DPS has been imported — it does not mean the companies paid no dividends.",
        },
        "blocker": None
        if dividend_events
        else (
            "No dividend/bonus notice has been imported. Import notices via /api/corporate-events/import "
            "to populate the calendar; nothing is inferred from price history."
        ),
        "scenario": {
            "note": "Data-independent calculator: it uses the price you supply, not a stored quote.",
            "formula": "yield = DPS / price; total return = yield + capital growth; payout = DPS / EPS.",
        },
    }


# --------------------------------------------------------------------------- #
# 8. Backtest vs buy & hold
# --------------------------------------------------------------------------- #
def backtest_vs_hold(
    result: dict[str, Any], df: pd.DataFrame, initial_cash: float = 100_000.0
) -> dict[str, Any]:
    """Add a buy-and-hold curve to an already-computed backtest payload.

    Takes the payload the real engine produced (``POST /api/backtest``) rather
    than re-running the strategy, so the comparison can never disagree with the
    backtest shown elsewhere in the tool.
    """
    sym = str(result.get("symbol") or "").upper()
    equity = result.get("equity") or []
    if not equity:
        return {
            "symbol": sym,
            "available": False,
            "reason": "the backtest engine returned no equity curve",
        }

    close_by_date = {}
    if df is not None and not getattr(df, "empty", True):
        close_by_date = {
            str(pd.Timestamp(d).date()): float(c)
            for d, c in zip(df["trading_date"], df["close"], strict=True)
        }

    first_date = equity[0]["date"]
    last_date = equity[-1]["date"]
    base = close_by_date.get(first_date)
    fee_rate = float((result.get("config") or {}).get("fee_rate") or 0.0)
    slippage = float((result.get("config") or {}).get("slippage") or 0.0)

    curve: list[dict[str, Any]] = []
    peak = -1e18
    max_dd = 0.0
    hold_peak = -1e18
    hold_max_dd = 0.0
    prev = None
    drawdowns: list[dict[str, Any]] = []
    for point in equity:
        d = point["date"]
        eq = float(point["equity"])
        peak = max(peak, eq)
        dd = (eq / peak - 1.0) * 100.0 if peak > 0 else 0.0
        max_dd = min(max_dd, dd)
        c = close_by_date.get(d)
        hold = None
        if base and c:
            # Buy & hold pays the entry cost once, then simply holds.
            hold = initial_cash * (1.0 - fee_rate - slippage) * (c / base)
            hold_peak = max(hold_peak, hold)
            hold_max_dd = min(hold_max_dd, (hold / hold_peak - 1.0) * 100.0)
        if prev is not None:
            drawdowns.append(dd)
        prev = eq
        curve.append(
            {
                "date": d,
                "strategy": round(eq, 2),
                "buy_hold": round(hold, 2) if hold is not None else None,
                "drawdown_pct": round(dd, 3),
                "position": point.get("position"),
            }
        )

    trade_pnls = [float(t.get("pnl") or 0.0) for t in (result.get("trades") or [])]
    final_strategy = curve[-1]["strategy"]
    final_hold = curve[-1]["buy_hold"]
    years = max((pd.Timestamp(last_date) - pd.Timestamp(first_date)).days / 365.25, 1e-9)

    def cagr(v):
        if v is None or v <= 0:
            return None
        return round(((v / initial_cash) ** (1.0 / years) - 1.0) * 100.0, 2)

    return {
        "symbol": sym,
        "strategy": result.get("strategy"),
        "strategy_label": result.get("strategy"),
        "available": True,
        "start": first_date,
        "end": last_date,
        "years": round(years, 2),
        "curve": curve,
        "histogram": _histogram(trade_pnls),
        "trades": len(trade_pnls),
        "comparison": {
            "strategy_final": _round(final_strategy, 2),
            "buy_hold_final": _round(final_hold, 2),
            "strategy_total_return_pct": round((final_strategy / initial_cash - 1.0) * 100.0, 2),
            "buy_hold_total_return_pct": round((final_hold / initial_cash - 1.0) * 100.0, 2)
            if final_hold
            else None,
            "strategy_cagr_pct": cagr(final_strategy),
            "buy_hold_cagr_pct": cagr(final_hold),
            "strategy_max_drawdown_pct": round(max_dd, 2),
            "buy_hold_max_drawdown_pct": round(hold_max_dd, 2),
        },
        "metrics": result.get("metrics"),
        "cost_model": result.get("cost_model"),
        "assumptions": result.get("assumptions"),
        "method": "The strategy is the real backtest engine (/api/backtest). Buy & hold uses the same symbol, "
        "the same dates and the same one-off entry cost (fee + slippage), then never trades.",
        "caveats": [
            "The two curves share a start date, an end date and the entry cost — comparing unequal periods "
            "would flatter whichever curve happened to be longer.",
            "The strategy may hold cash for long stretches, so a lower drawdown is not automatically skill.",
        ],
    }


def _histogram(values: list[float], bins: int = 12) -> dict[str, Any]:
    if not values:
        return {"bins": [], "count": 0}
    arr = np.asarray(values, dtype=float)
    lo, hi = float(arr.min()), float(arr.max())
    if hi == lo:
        return {
            "bins": [{"from": round(lo, 2), "to": round(hi, 2), "count": int(arr.size)}],
            "count": int(arr.size),
        }
    edges = np.linspace(lo, hi, bins + 1)
    counts, _ = np.histogram(arr, bins=edges)
    return {
        "bins": [
            {
                "from": round(float(edges[i]), 2),
                "to": round(float(edges[i + 1]), 2),
                "count": int(counts[i]),
            }
            for i in range(bins)
        ],
        "count": int(arr.size),
    }
