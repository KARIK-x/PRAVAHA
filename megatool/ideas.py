"""Investment-idea models, driven by the data Mega Tool actually stores.

The reference platform (see ``docs/ui-redesign/REFERENCE_INVENTORY.md``) indexes
nine named methodologies as cards — MultiBagger, Peter Lynch, CANSLIM, Magic
Formula, F-score, Z-score, G-score, Bargain, 52-week Bargain. This module models
that catalogue **honestly**:

* a model is only *Calculated* when every input it needs is present in the
  database;
* otherwise it reports ``insufficient_data`` and **names the missing fields** —
  it never fabricates a score to fill a card.

What Mega Tool stores today (see ``megatool/fundamentals.py``): ``eps``, ``pe``,
``net_worth_per_share``, ``paid_up_capital``, ``profit`` — plus daily OHLCV. It
does **not** store EBIT, EV, working capital, total assets, cash-flow, current
ratio or share issuance, so Magic Formula, Piotroski F-score and Altman Z-score
are declared insufficient rather than approximated.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from megatool.fundamentals import query_symbol

__all__ = ["MODELS", "model_catalogue", "evaluate", "IdeasError"]


class IdeasError(ValueError):
    """Unknown model id (the caller maps this to HTTP 404)."""


#: Fields a model needs that Mega Tool can source from the stored fundamentals.
_HAVE = {"eps", "net_worth_per_share", "pe", "profit", "paid_up_capital"}
#: Fields that are simply not in the database (declared, never guessed).
_MISSING_ALWAYS = [
    "ebit",
    "enterprise_value",
    "total_assets",
    "current_assets",
    "current_liabilities",
    "cash_flow_from_operations",
    "shares_outstanding_prior",
    "gross_profit",
    "revenue",
]


MODELS: list[dict[str, Any]] = [
    {
        "id": "graham",
        "name": "Graham value",
        "category": "Value",
        "source": "Graham Number = sqrt(22.5 x EPS x Book value per share)",
        "blurb": "Intrinsic-value proxy from earnings and book value; ranked by margin of safety.",
        "requires": ["eps", "net_worth_per_share", "price"],
        "status": "available",
    },
    {
        "id": "lynch",
        "name": "Peter Lynch (PEG)",
        "category": "Growth at a fair price",
        "source": "PEG = (P/E) / annual EPS growth %; Lynch favoured PEG <= 1",
        "blurb": "Cheap growth: earnings growth rate against the price you pay for it.",
        "requires": ["eps", "price", "eps_growth"],
        "status": "available",
    },
    {
        "id": "pb_bargain",
        "name": "Book-value bargain",
        "category": "Value",
        "source": "Price / book value per share",
        "blurb": "Trading below (or near) book value, cheapest first.",
        "requires": ["net_worth_per_share", "price"],
        "status": "available",
    },
    {
        "id": "low_52w",
        "name": "52-week bargain",
        "category": "Value / mean reversion",
        "source": "Position within the trailing 52-week range",
        "blurb": "Names trading near the bottom of their yearly range.",
        "requires": ["price", "bars_252"],
        "status": "available",
    },
    {
        "id": "momentum",
        "name": "Relative momentum",
        "category": "Momentum",
        "source": "12-1 momentum: 252-bar return excluding the last 21 bars",
        "blurb": "Persistent winners, deliberately skipping the most recent month.",
        "requires": ["bars_252"],
        "status": "available",
    },
    {
        "id": "multibagger",
        "name": "Multi-bagger candidates",
        "category": "Growth",
        "source": "PEG <= 1 AND positive 12-1 momentum AND price above the 200-bar mean",
        "blurb": "Cheap growth already in an uptrend — the reference's MultiBagger idea.",
        "requires": ["eps", "price", "eps_growth", "bars_252"],
        "status": "available",
    },
    {
        "id": "canslim",
        "name": "CAN SLIM",
        "category": "Growth",
        "source": "O'Neil's CAN SLIM",
        "blurb": "Needs current+annual quarterly earnings acceleration, institutional "
        "sponsorship and float; only the C and part of L are derivable here.",
        "requires": ["eps", "eps_growth", "bars_252", "quarterly_eps_series", "float_shares"],
        "status": "partial",
    },
    {
        "id": "magic_formula",
        "name": "Magic Formula",
        "category": "Value",
        "source": "Greenblatt: EBIT/EV and ROIC ranks",
        "blurb": "Requires EBIT and enterprise value, which are not stored.",
        "requires": ["ebit", "enterprise_value", "roic"],
        "status": "insufficient_data",
    },
    {
        "id": "piotroski",
        "name": "Piotroski F-score",
        "category": "Financial strength",
        "source": "Piotroski 9-point F-score",
        "blurb": "Nine accounting tests across profitability, leverage, liquidity and "
        "operating efficiency. None of the balance-sheet inputs are stored.",
        "requires": [
            "return_on_assets",
            "cash_flow_from_operations",
            "return_on_assets_prior",
            "cash_flow_gt_income",
            "leverage_change",
            "current_ratio",
            "current_ratio_prior",
            "shares_outstanding_change",
            "gross_margin_change",
            "asset_turnover_change",
        ],
        "status": "insufficient_data",
    },
    {
        "id": "altman",
        "name": "Altman Z-score",
        "category": "Bankruptcy risk",
        "source": "Altman Z = 1.2X1 + 1.4X2 + 3.3X3 + 0.6X4 + 1.0X5",
        "blurb": "Distress score; needs working capital, retained earnings, EBIT, "
        "market value of equity and total assets.",
        "requires": [
            "working_capital",
            "retained_earnings",
            "ebit",
            "market_value_equity",
            "total_assets",
        ],
        "status": "insufficient_data",
    },
]


def model_catalogue() -> list[dict[str, Any]]:
    """Every model with the inputs it needs and whether they are present."""
    out = []
    for m in MODELS:
        missing = [f for f in m["requires"] if f in _MISSING_ALWAYS]
        out.append(
            {
                **m,
                "missing_inputs": missing,
                "stored_inputs": [f for f in m["requires"] if f in _HAVE],
            }
        )
    return out


# --------------------------------------------------------------- data helpers
def _latest_by_field(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Newest record per field (by period_end, then retrieved_at)."""
    best: dict[str, dict[str, Any]] = {}
    for r in rows or []:
        f = r.get("field")
        if not f:
            continue
        cur = best.get(f)
        key = (str(r.get("period_end") or ""), str(r.get("retrieved_at") or ""))
        if cur is None or key > (
            str(cur.get("period_end") or ""),
            str(cur.get("retrieved_at") or ""),
        ):
            best[f] = r
    return best


def _eps_growth(rows: list[dict[str, Any]], min_days: int = 200) -> float | None:
    """Annualised EPS growth (%) between the two newest EPS periods.

    Requires two periods at least ``min_days`` apart, so a quarter-on-quarter
    pair cannot masquerade as an annual growth rate.
    """
    eps = [r for r in rows or [] if r.get("field") == "eps" and r.get("period_end")]
    eps.sort(key=lambda r: str(r["period_end"]))
    if len(eps) < 2:
        return None
    try:
        new, old = eps[-1], eps[-2]
        d_new = date.fromisoformat(str(new["period_end"])[:10])
        d_old = date.fromisoformat(str(old["period_end"])[:10])
        v_new, v_old = float(new["value"]), float(old["value"])
    except (TypeError, ValueError):
        return None
    days = (d_new - d_old).days
    # Both endpoints must be positive: a fractional power of a negative ratio
    # is complex, and a loss-to-loss 'growth' rate is not a growth rate.
    if days < min_days or v_old <= 0 or v_new <= 0:
        return None
    years = days / 365.25
    try:
        cagr = (v_new / v_old) ** (1.0 / years) - 1.0
    except (OverflowError, ValueError, ZeroDivisionError):
        return None
    return cagr * 100.0


def _price_stats(store: Any, universe: list[str]) -> dict[str, dict[str, Any]]:
    """Per-symbol price statistics from stored bars, in ONE query.

    Invalid bars are excluded by the same rule the store applies everywhere
    (``high < low``, non-positive or missing prices): an impossible row must not
    drive a 52-week low or a momentum rank.
    """
    out: dict[str, dict[str, Any]] = {}
    if not universe:
        return out
    placeholders = ",".join("?" for _ in universe)
    sql = (
        "SELECT symbol, trading_date, close, high, low FROM price_bars "
        f"WHERE symbol IN ({placeholders}) "
        "AND close IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL "
        "AND close > 0 AND high >= low "
        "ORDER BY symbol, trading_date"
    )
    try:
        df = store.query_df(sql, [s.upper() for s in universe])
    except Exception:  # noqa: BLE001 - a store shape without price_bars
        return out
    if df is None or getattr(df, "empty", True):
        return out
    for sym, g in df.groupby("symbol"):
        close = g["close"].astype(float).to_numpy()
        n = len(close)
        row: dict[str, Any] = {"last": float(close[-1]), "bars": n}
        if n >= 253:
            row["mom_12_1"] = (close[-22] / close[-253] - 1.0) * 100.0
        if n >= 200:
            row["sma200"] = float(sum(close[-200:]) / 200.0)
        tail = g.tail(252)
        hi, lo = float(tail["high"].max()), float(tail["low"].min())
        row["range_high"], row["range_low"] = hi, lo
        if hi > lo:
            row["range_pos"] = (float(close[-1]) - lo) / (hi - lo) * 100.0
        out[str(sym)] = row
    return out


#: Per-share fields are rupees per share. A value outside this band is a unit
#: error in the source (e.g. total equity stored as net worth per share), not a
#: price-to-book ratio - so it is refused rather than ranked.
_PER_SHARE_MIN = 1.0
_PER_SHARE_MAX = 1_000_000.0


def _per_share(value: float | None) -> float | None:
    if value is None or not (_PER_SHARE_MIN <= value <= _PER_SHARE_MAX):
        return None
    return value


# ------------------------------------------------------------------- evaluate
def evaluate(model_id: str, store: Any, conn: Any, *, limit: int = 40) -> dict[str, Any]:
    """Run one model and return ranked rows or an explicit insufficiency."""
    model = next((m for m in MODELS if m["id"] == model_id), None)
    if model is None:
        raise IdeasError(f"unknown model {model_id!r}")

    if model["status"] == "insufficient_data":
        return {
            "model": model,
            "status": "insufficient_data",
            "missing_inputs": [f for f in model["requires"] if f in _MISSING_ALWAYS],
            "rows": [],
            "note": (
                "This model needs fields Mega Tool does not store. It is shown so the "
                "methodology is discoverable, but no score is produced from missing data."
            ),
        }

    universe = _universe(store, conn)
    fund: dict[str, list[dict[str, Any]]] = {}
    latest: dict[str, dict[str, Any]] = {}
    growth: dict[str, float | None] = {}
    for sym in universe:
        rows = query_symbol(conn, sym)
        fund[sym] = rows
        latest[sym] = _latest_by_field(rows)
        growth[sym] = _eps_growth(rows)

    stats = _price_stats(store, universe)
    rows: list[dict[str, Any]] = []

    for sym in universe:
        m = latest.get(sym, {})
        r = stats.get(sym, {})

        def val(field: str, _m: dict = m) -> float | None:
            rec = _m.get(field)
            if not rec:
                return None
            try:
                v = float(rec["value"])
            except (TypeError, ValueError):
                return None
            return v if math.isfinite(v) else None

        price = r.get("last")
        if price is None:
            continue
        eps, bvps = _per_share(val("eps")), _per_share(val("net_worth_per_share"))
        entry: dict[str, Any] = {"symbol": sym, "price": round(price, 2)}
        score: float | None = None

        if model_id == "graham":
            if eps and bvps and eps > 0 and bvps > 0:
                fair = math.sqrt(22.5 * eps * bvps)
                score = (fair - price) / fair * 100.0
                entry.update(
                    {
                        "fair_value": round(fair, 2),
                        "eps": round(eps, 2),
                        "book_value": round(bvps, 2),
                    }
                )
        elif model_id == "pb_bargain":
            if bvps and bvps > 0:
                score = price / bvps
                entry.update({"pb": round(score, 3), "book_value": round(bvps, 2)})
        elif model_id in ("lynch", "multibagger"):
            g = growth.get(sym)
            pe = val("pe")
            if g and g > 0:
                if pe and pe > 0:
                    score = pe / g
                    entry.update(
                        {"pe": round(pe, 2), "eps_growth_pct": round(g, 2), "peg": round(score, 2)}
                    )
                elif eps and eps > 0:
                    pe_calc = price / eps
                    score = pe_calc / g
                    entry.update(
                        {
                            "pe": round(pe_calc, 2),
                            "eps_growth_pct": round(g, 2),
                            "peg": round(score, 2),
                        }
                    )
            if model_id == "multibagger" and score is not None:
                mom, sma = r.get("mom_12_1"), r.get("sma200")
                entry.update(
                    {
                        "momentum_pct": None if mom is None else round(mom, 2),
                        "above_200sma": None if sma is None else price > sma,
                    }
                )
                if not (mom is not None and mom > 0 and sma is not None and price > sma):
                    score = None  # not a multi-bagger candidate
        elif model_id == "low_52w":
            hi, lo = r.get("range_high"), r.get("range_low")
            if hi is not None and lo is not None and hi > lo:
                pos = (price - lo) / (hi - lo) * 100.0
                score = -pos  # nearest the low ranks first
                entry.update(
                    {
                        "pct_above_low": round(pos, 1),
                        "range_low": round(lo, 2),
                        "range_high": round(hi, 2),
                    }
                )
        elif model_id == "momentum":
            mom = r.get("mom_12_1")
            if mom is not None:
                score = mom
                entry.update(
                    {
                        "momentum_pct": round(mom, 2),
                        "above_200sma": None if r.get("sma200") is None else price > r["sma200"],
                    }
                )
        elif model_id == "canslim":
            g = growth.get(sym)
            mom = r.get("mom_12_1")
            if g is not None and mom is not None:
                entry.update({"eps_growth_pct": round(g, 2), "momentum_pct": round(mom, 2)})
                score = (100.0 if g > 25 else 0.0) + (100.0 if mom > 0 else 0.0)

        if score is None:
            continue
        entry["score"] = round(float(score), 4)
        rows.append(entry)

    # Lower is better for a ratio (PEG, P/B); higher is better for a margin
    # of safety (Graham) and for momentum.
    ascending = model_id in ("lynch", "multibagger", "pb_bargain")
    rows.sort(key=lambda x: x["score"], reverse=not ascending)
    rows = rows[:limit]
    # "calculated" means the model ran over the universe. Zero matches is a
    # result ("nothing qualifies"), not a data gap - only a missing *input* is.
    return {
        "model": model,
        "status": "calculated",
        "missing_inputs": [],
        "evaluated": len(universe),
        "matched": len(rows),
        "rows": rows,
        "note": (
            f"{len(universe)} symbols with stored prices evaluated; "
            f"{len(rows)} met every condition."
            if rows
            else f"{len(universe)} symbols evaluated; none met every condition."
        ),
    }


def _universe(store: Any, conn: Any) -> list[str]:
    """Every symbol with stored prices; models filter for the inputs they need.

    Restricting the universe to symbols that happen to have fundamentals would
    silently drop price-only models (momentum, 52-week range) on names with no
    filings, and would misreport "evaluated N" — so the universe is *price*
    membership, and a fundamental model reports its own coverage.
    """
    try:
        have = [str(x).upper() for x in store.symbols()]
    except Exception:  # noqa: BLE001 - store shape differs by version
        have = []
    if have:
        return sorted(set(have))
    return sorted(
        {str(r["symbol"]).upper() for r in conn.execute("SELECT DISTINCT symbol FROM fundamentals")}
    )
