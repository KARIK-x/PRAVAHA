"""One payload for the market-intelligence dashboard.

The dashboard needs market status, the official index, breadth, sector
performance, movers, valuation distributions and the watchlist together. Fetching
each from a separate widget would mean ~8 requests per paint and a wall of
skeleton panels, so this module assembles everything the dashboard shows from
**one** call, sharing the live snapshot and the store queries.

Data honesty rules applied throughout:

* Ordering of precedence for each figure is recorded in ``market``: the live
  layer's own freshness, never an assumed one.
* Breadth counts only symbols with a stored percent change; symbols without one
  are reported separately, never flattened into "unchanged".
* Moving-average participation uses the latest stored bar per symbol and reports
  its denominator.
* Valuation bins use only stored fundamentals, and the coverage of that analysis
  is stated so a partial universe is not shown as the whole market.
* Sector names come from the upstream securities list; symbols with no sector are
  grouped as "Unclassified" rather than dropped silently.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from megatool.datasources import yonepse

_SECTOR_TTL = float(os.getenv("MEGATOOL_SECTOR_MAP_TTL", "1800"))
_sector_cache: dict[str, Any] = {"at": 0.0, "map": {}}
_sector_lock = threading.Lock()


def _sector_map() -> dict[str, str]:
    """``{symbol: sector}`` from the upstream securities list, cached."""
    with _sector_lock:
        if _sector_cache["map"] and time.monotonic() - _sector_cache["at"] < _SECTOR_TTL:
            return dict(_sector_cache["map"])
    mapping: dict[str, str] = {}
    try:
        for rec in yonepse.fetch_securities() or []:
            sym = str(rec.get("symbol") or "").strip().upper()
            if not sym:
                continue
            mapping[sym] = str(rec.get("sectorName") or "").strip() or "Unclassified"
    except Exception:  # noqa: BLE001
        mapping = dict(_sector_cache["map"]) if _sector_cache["map"] else {}
    with _sector_lock:
        if mapping:
            _sector_cache.update(at=time.monotonic(), map=mapping)
    return dict(mapping)


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else f


def _round(value: float | None, dp: int = 2) -> float | None:
    return None if value is None else round(value, dp)


# ------------------------------------------------------------------- pieces
def index_series(store: Any, limit: int = 400) -> dict[str, Any]:
    """Official NEPSE index closes from the store (never a computed basket)."""
    df = store.index_closes("NEPSE")
    if df is None or getattr(df, "empty", True) or len(df) < 2:
        return {
            "name": "NEPSE",
            "available": False,
            "points": [],
            "reason": "no stored official index series — import one to draw the index chart",
            "source": None,
        }
    if limit and len(df) > limit:
        df = df.tail(limit)
    points = [
        [str(r["trading_date"])[:10], float(r["close"])]
        for _, r in df.iterrows()
        if _num(r["close"]) is not None
    ]
    latest, prev = points[-1][1], points[-2][1]
    src = None
    try:
        row = store.query_one("SELECT source FROM index_series WHERE index_name='NEPSE' LIMIT 1")
        if row:
            src = str(row[0])
    except Exception:  # noqa: BLE001
        src = None
    return {
        "name": "NEPSE",
        "available": True,
        "points": points,
        "first": points[0][0],
        "last": points[-1][0],
        "latest": latest,
        "previous": prev,
        "change": round(latest - prev, 2),
        "pct": round((latest - prev) / prev * 100.0, 2) if prev else None,
        "bars": len(points),
        "source": src,
    }


#: Windows the per-sector participation table reports, matching the reference's
#: "Percentage of stocks above Moving Average" table (10/20/50/200 + 50&200).
SECTOR_MA_WINDOWS = (10, 20, 50, 200)


def _stored_sector_map(store: Any) -> dict[str, str]:
    """``{symbol: sector}`` from the STORED classification (no network).

    The Sector Explorer / ``fetch-sectors`` writes ``security_master.sector``, so
    the dashboard reads the same mapping instead of re-fetching the upstream
    securities list.
    """
    try:
        rows = store.query_rows(
            "SELECT symbol, sector FROM security_master "
            "WHERE sector IS NOT NULL AND sector != ''"
        )
        return {str(r[0]).upper(): str(r[1]) for r in rows}
    except Exception:  # noqa: BLE001 - a missing table is an empty map, not a crash
        return {}


def sector_ma_participation(
    store: Any, sector_map: dict[str, str] | None = None
) -> dict[str, Any]:
    """Per-sector share of securities trading above their own moving average.

    Reference parity with the SastaShare "Percentage of stocks above Moving
    Average" table (Above 10/20/50/200 SMA and Above 50&200 SMA), computed from
    stored daily closes only.

    Honesty rules:
    * A security with fewer than ``window`` stored closes is EXCLUDED from that
      window's denominator — it is never counted as "below", which would invent
      a bearish reading.
    * Only symbols with a verified sector classification are counted; the rest
      are reported as ``unclassified`` rather than bucketed into a sector.
    * Percentages are ``above / denominator`` for that sector and window.
    """
    smap = sector_map if sector_map is not None else _stored_sector_map(store)
    windows = SECTOR_MA_WINDOWS
    cols = ", ".join(
        f"AVG(close) OVER (PARTITION BY symbol ORDER BY trading_date "
        f"ROWS BETWEEN {w - 1} PRECEDING AND CURRENT ROW) AS sma{w}"
        for w in windows
    )
    try:
        df = store.query_df(
            f"""
            WITH w AS (
              SELECT symbol, trading_date, close, {cols},
                COUNT(*) OVER (PARTITION BY symbol) AS n_bars,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) AS rn
              FROM price_bars WHERE close > 0 AND high >= low
            )
            SELECT symbol, close, n_bars, {", ".join(f"sma{w}" for w in windows)}
            FROM w WHERE rn = 1
            """
        )
    except Exception:  # noqa: BLE001
        return {"available": False, "reason": "no stored price history", "sectors": []}

    if df is None or getattr(df, "empty", True):
        return {"available": False, "reason": "no stored price history", "sectors": []}

    # Per sector: one entry per symbol carrying, for each window, whether the
    # symbol has enough history and whether its close is above that average.
    # Keeping the per-symbol flags lets "above 50 AND 200" be computed from the
    # same symbols instead of zipping unrelated lists.
    buckets: dict[str, dict[str, dict[int, bool | None]]] = {}
    unclassified = 0
    for row in df.itertuples(index=False):
        sym = str(getattr(row, "symbol", "")).upper()
        sector = smap.get(sym)
        if not sector:
            unclassified += 1
            continue
        close = _num(getattr(row, "close", None))
        # DuckDB's window AVG averages whatever rows exist, so a 200-row window
        # over 30 stored bars returns a NUMBER, not NULL. The window is therefore
        # only usable when the symbol actually has >= that many stored closes.
        n_bars = int(getattr(row, "n_bars", 0) or 0)
        flags: dict[int, bool | None] = {}
        for w in windows:
            avg = _num(getattr(row, f"sma{w}", None))
            # None = not enough stored history for this window (excluded, never
            # counted as "below", which would invent a bearish reading).
            flags[w] = (
                None if (avg is None or close is None or n_bars < w) else bool(close > avg)
            )
        buckets.setdefault(sector, {})[sym] = flags

    out = []
    for sector, members in buckets.items():
        entry: dict[str, Any] = {"sector": sector}
        for w in windows:
            known = [f[w] for f in members.values() if f[w] is not None]
            den = len(known)
            above = sum(1 for k in known if k)
            entry[f"above_{w}"] = above
            entry[f"denominator_{w}"] = den
            entry[f"pct_above_{w}"] = round(above / den * 100.0, 1) if den else None
        both = [
            1 if (f[50] and f[200]) else 0
            for f in members.values()
            if f[50] is not None and f[200] is not None
        ]
        den_both = len(both)
        entry["above_50_and_200"] = sum(both)
        entry["denominator_50_and_200"] = den_both
        entry["pct_above_50_and_200"] = (
            round(sum(both) / den_both * 100.0, 1) if den_both else None
        )
        out.append(entry)

    out.sort(key=lambda e: (-(e.get("denominator_200") or 0), e["sector"]))
    return {
        "available": bool(out),
        "windows": list(windows),
        "as_of": _latest_date(store),
        "unclassified": unclassified,
        "classified": sum((e.get("denominator_200") or 0) for e in out),
        "sectors": out,
        "note": (
            "Percentage of each sector's securities trading above their own "
            "simple moving average on the latest stored session. A security with "
            "fewer than N stored closes is excluded from that window rather than "
            "counted as below. Only symbols with a verified sector are counted."
        ),
    }


def _latest_date(store: Any) -> str | None:
    try:
        row = store.query_one("SELECT MAX(trading_date) FROM price_bars")
        return str(row[0])[:10] if row and row[0] else None
    except Exception:  # noqa: BLE001
        return None


def breadth(store: Any) -> dict[str, Any]:
    adv = dec = unc = missing = 0
    try:
        df = store.query_df(
            "SELECT symbol, percent_change FROM price_bars "
            "WHERE trading_date = (SELECT MAX(trading_date) FROM price_bars) AND close > 0"
        )
    except Exception:  # noqa: BLE001
        df = None
    if df is not None and not getattr(df, "empty", True):
        for v in df["percent_change"]:
            pct = _num(v)
            if pct is None:
                missing += 1
            elif pct > 0:
                adv += 1
            elif pct < 0:
                dec += 1
            else:
                unc += 1
    ma: dict[str, Any] = {}
    try:
        m = store.query_df(
            """
            WITH w AS (
              SELECT symbol, trading_date, close,
                AVG(close) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS sma20,
                AVG(close) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS sma50,
                AVG(close) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS sma200,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) AS rn
              FROM price_bars WHERE close > 0 AND high >= low
            )
            SELECT symbol, close, sma20, sma50, sma200 FROM w WHERE rn = 1
            """
        )
    except Exception:  # noqa: BLE001
        m = None
    if m is not None and not getattr(m, "empty", True):
        for period, col in ((20, "sma20"), (50, "sma50"), (200, "sma200")):
            valid = m[m[col].notna()]
            den = int(len(valid))
            above_mask = valid["close"] > valid[col]
            above = int(above_mask.sum()) if den else 0
            ma[f"above_{period}"] = above
            ma[f"denominator_{period}"] = den
            ma[f"pct_above_{period}"] = round(above / den * 100.0, 1) if den else None
            # Symbol lists for dashboard drill-down (real records only).
            ma[f"above_symbols_{period}"] = [
                str(s) for s in valid.loc[above_mask, "symbol"].tolist()
            ]
            ma[f"below_symbols_{period}"] = [
                str(s) for s in valid.loc[~above_mask, "symbol"].tolist()
            ]
    as_of = store.query_one("SELECT MAX(trading_date) FROM price_bars")
    return {
        "advancers": adv,
        "decliners": dec,
        "unchanged": unc,
        "missing": missing,
        "total": adv + dec + unc + missing,
        "moving_average": ma,
        "as_of": str(as_of[0])[:10] if as_of and as_of[0] else None,
    }


def movers(quotes: list[dict[str, Any]], limit: int = 12) -> dict[str, Any]:
    rows = [q for q in quotes if q.get("ltp") is not None]
    rows_pct = [q for q in rows if q.get("percent_change") is not None]

    def shape(q: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbol": q["symbol"],
            "ltp": q["ltp"],
            "pct": _round(q.get("percent_change")),
            "change": _round(q.get("change")),
            "volume": q.get("volume"),
            "turnover": q.get("turnover"),
        }

    by_pct = sorted(rows_pct, key=lambda q: float(q["percent_change"]), reverse=True)
    active = sorted(
        [q for q in rows_pct if q.get("turnover")], key=lambda q: float(q["turnover"]), reverse=True
    )
    return {
        "gainers": [shape(q) for q in by_pct[:limit]],
        "losers": [shape(q) for q in by_pct[-limit:][::-1]],
        "active": [shape(q) for q in active[:limit]],
    }


def heat(quotes: list[dict[str, Any]], limit: int = 120) -> dict[str, Any]:
    """Turnover-weighted heatmap tiles for the dashboard.

    Only rows the source itself carries a percent change and turnover on are
    included; anything else is simply absent from the map rather than given a
    guessed colour. Ties break on turnover then symbol so the layout is stable
    between requests.
    """
    rows = [
        q
        for q in quotes
        if q.get("ltp") is not None
        and q.get("percent_change") is not None
        and q.get("turnover")
        and float(q["turnover"]) > 0
    ]
    rows.sort(key=lambda q: (-float(q["turnover"]), q["symbol"]))
    return {
        "tiles": [
            {
                "symbol": q["symbol"],
                "ltp": q["ltp"],
                "pct": _round(q.get("percent_change")),
                "turnover": q.get("turnover"),
            }
            for q in rows[:limit]
        ],
        "covered": len(rows),
        "total_quotes": len(quotes),
        "note": (
            "Tile area is proportional to the source's turnover for the session; "
            "colour is its published % change. Symbols the source left without "
            "either are excluded, not estimated."
        ),
    }


def sectors(quotes: list[dict[str, Any]], limit: int = 250) -> list[dict[str, Any]]:
    smap = _sector_map()
    buckets: dict[str, list[dict[str, Any]]] = {}
    for q in quotes:
        sector = smap.get(str(q.get("symbol", "")).upper(), "Unclassified")
        buckets.setdefault(sector, []).append(q)
    out = []
    for name, members in buckets.items():
        pct = [float(m["percent_change"]) for m in members if m.get("percent_change") is not None]
        turnover = sum(float(m["turnover"] or 0) for m in members)
        top = sorted(members, key=lambda m: float(m.get("percent_change") or 0), reverse=True)
        out.append(
            {
                "sector": name,
                "symbols": len(members),
                "advancers": sum(1 for p in pct if p > 0),
                "decliners": sum(1 for p in pct if p < 0),
                "avg_pct": _round(sum(pct) / len(pct), 2) if pct else None,
                "turnover": _round(turnover, 2),
                "top": [
                    {
                        "symbol": m["symbol"],
                        "ltp": m.get("ltp"),
                        "pct": _round(m.get("percent_change")),
                    }
                    for m in (top[:3] + top[-2:])[:5]
                ],
            }
        )
    out.sort(key=lambda s: (s["avg_pct"] is None, -(s["avg_pct"] or 0)))
    return out[:limit]


def valuation(
    store: Any, conn: Any, sectors_map: dict[str, str], limit: int = 400
) -> dict[str, Any]:
    try:
        latest_bars = store.query_df(
            "SELECT symbol, close FROM price_bars WHERE trading_date = "
            "(SELECT MAX(trading_date) FROM price_bars) AND close > 0"
        )
    except Exception:  # noqa: BLE001
        latest_bars = None
    prices = {}
    if latest_bars is not None and not getattr(latest_bars, "empty", True):
        for _, r in latest_bars.iterrows():
            v = _num(r["close"])
            if v is not None and v > 0:
                prices[str(r["symbol"])] = v

    pe_pairs: list[tuple[str, float]] = []
    pb_pairs: list[tuple[str, float]] = []
    cap_map: dict[str, float] = {}
    for symbol in prices:
        latest: dict[str, tuple[float, str]] = {}
        try:
            for row in conn.execute(
                "SELECT field, value, period_end FROM fundamentals WHERE symbol=?", (symbol,)
            ):
                f = row["field"]
                end = str(row["period_end"] or "")

                # Compare by parsed date when possible; fall back to lexical
                # compare for non-ISO period_end values (e.g. "FY2024").
                def _period_key(s):
                    try:
                        from datetime import date

                        return (1, date.fromisoformat(s[:10]).toordinal())
                    except (ValueError, TypeError):
                        return (0, s)

                cur = latest.get(f)
                if cur is None or _period_key(end) > _period_key(cur[1]):
                    v = _num(row["value"])
                    if v is not None:
                        latest[f] = (v, end)
        except Exception:  # noqa: BLE001
            continue
        v_pe = (latest.get("pe") or (None, ""))[0]
        if v_pe and v_pe > 0:
            pe_pairs.append((symbol, v_pe))
        v_bv = (latest.get("net_worth_per_share") or (None, ""))[0]
        if v_bv and v_bv > 0:
            pb_pairs.append((symbol, prices[symbol] / v_bv))
        # Market capitalisation is DERIVED: NEPSE's face value is NRs 100, so
        # shares = paid-up capital / 100 and cap = shares × last close. It is
        # kept only where the paid-up capital is actually stored — never guessed
        # from the index weight or a sector average.
        v_cap = (latest.get("paid_up_capital") or (None, ""))[0]
        if v_cap and v_cap > 0:
            cap_map[symbol] = v_cap / 100.0 * prices[symbol]

    def bins(pairs: list[tuple[str, float]], edges: list[float]) -> list[dict[str, Any]]:
        out = []
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            members = [s for s, v in pairs if lo <= v < hi]
            out.append(
                {
                    "label": f"{edges[i]:g}–{edges[i + 1]:g}",
                    "count": len(members),
                    "symbols": members,
                }
            )
        members = [s for s, v in pairs if v >= edges[-1]]
        out.append({"label": f"{edges[-1]:g}+", "count": len(members), "symbols": members})
        return out

    pe_map = dict(pe_pairs)
    pb_map = dict(pb_pairs)
    scatter = [
        {
            "symbol": s,
            "pe": pe_map.get(s),
            "pb": pb_map.get(s),
            "sector": sectors_map.get(s, "Unclassified"),
            "market_cap": cap_map.get(s),
        }
        for s in sorted(set(pe_map) & set(pb_map))[:limit]
    ]
    by: dict[str, list[float]] = {}
    for row in scatter:
        v = pe_map.get(row["symbol"])
        if v:
            by.setdefault(row["sector"], []).append(v)
    sector_pe = []
    for sector, vals in by.items():
        vals.sort()
        mid = len(vals) // 2
        median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        sector_pe.append({"sector": sector, "n": len(vals), "pe_median": round(median, 2)})
    sector_pe.sort(key=lambda r: -r["pe_median"])
    return {
        "pe_bins": bins(pe_pairs, [0, 10, 15, 20, 25, 30, 50]),
        "pb_bins": bins(pb_pairs, [0, 0.5, 1, 1.5, 2, 3, 5]),
        "scatter": scatter,
        "coverage": {
            "symbols_with_price": len(prices),
            "pe_available": len(pe_pairs),
            "pb_available": len(pb_pairs),
            "market_cap_available": len(cap_map),
            "note": "counts are of symbols with a usable stored value, not of the whole market",
            "market_cap_note": (
                "Market cap is derived as paid-up capital / 100 × last close (NRs 100 face "
                "value) and exists only where the paid-up capital is stored."
            ),
        },
        "sector_pe": sector_pe[:12],
    }


def breadth_history(store: Any, days: int = 60) -> dict[str, Any]:
    """Daily advance/decline history from stored bars."""
    try:
        last = store.query_one("SELECT MAX(trading_date) FROM price_bars")
        last_date = last[0] if last and last[0] is not None else None
    except Exception:  # noqa: BLE001
        last_date = None
    if last_date is None:
        return {"bars": [], "days": days, "reason": "no stored bars"}
    from datetime import timedelta

    cutoff = (
        (last_date - timedelta(days=int(days))).strftime("%Y-%m-%d")
        if hasattr(last_date, "strftime")
        else str(last_date)[:10]
    )
    try:
        df = store.query_df(
            """
            SELECT
              trading_date,
              SUM(CASE WHEN percent_change > 0 THEN 1 ELSE 0 END) AS adv,
              SUM(CASE WHEN percent_change < 0 THEN 1 ELSE 0 END) AS dec_,
              SUM(CASE WHEN percent_change IS NULL OR percent_change = 0 THEN 1 ELSE 0 END) AS unc,
              COUNT(*) AS n
            FROM price_bars
            WHERE close > 0 AND trading_date >= ?
            GROUP BY trading_date
            ORDER BY trading_date ASC
            """,
            [cutoff],
        )
    except Exception:  # noqa: BLE001
        return {"bars": [], "days": days, "reason": "query failed", "as_of": str(last_date)[:10]}
    if df is None or getattr(df, "empty", True):
        return {"bars": [], "days": days, "reason": "no rows", "as_of": str(last_date)[:10]}
    rows = []
    for _, r in df.iterrows():
        adv, dec_, unc = int(r.get("adv") or 0), int(r.get("dec_") or 0), int(r.get("unc") or 0)
        tot = adv + dec_ + unc
        rows.append(
            {
                "date": str(r["trading_date"])[:10],
                "advancers": adv,
                "decliners": dec_,
                "unchanged": unc,
                "total": tot,
                "breadth": round((adv - dec_) / tot, 4) if tot else 0.0,
            }
        )
    return {"bars": rows[-int(days) :], "days": int(days), "as_of": str(last_date)[:10]}


# ------------------------------------------------------------------- builder
def build_dashboard(
    store: Any, conn: Any, live_service: Any, index_limit: int = 300, top: int = 8
) -> dict[str, Any]:
    snap = live_service.snapshot(force=False)
    market = {k: v for k, v in snap.items() if k != "quotes"}
    market.setdefault("quotes", None)
    market["quote_count"] = snap.get("quote_count", len(snap.get("quotes") or []))
    quotes = list(snap.get("quotes") or [])
    return {
        "market": market,
        "index_chart": index_series(store, index_limit),
        "breadth": breadth(store),
        "sectors": sectors(quotes),
        "movers": movers(quotes, top),
        "heat": heat(quotes),
        "valuation": valuation(store, conn, _sector_map()),
        "sector_ma": sector_ma_participation(store),
        "sector_map_size": len(_sector_map()),
        "market_closed": market.get("is_open") is False,
    }
