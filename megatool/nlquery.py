"""Constrained natural-language query over the project's own data (Phase E / NF-016).

The interface is deliberately narrow. A question is first parsed into a *plan*
(dataset, fields, filters, limit, calculation) using a fixed set of recognised
shapes. The plan is validated against explicit table/column allowlists and
executed with parameterised statements only. There is no path to arbitrary SQL,
no shell, no filesystem access and no writes.

Anything that cannot be expressed as a supported plan is **rejected** with the
reason, rather than answered by inventing data. When a required dataset or field
is unavailable, the missing item is named.

Security properties (asserted by the tests):
  * read-only access to an allowlisted set of tables;
  * an allowlist of columns per table;
  * parameters are always bound, never interpolated;
  * every query is bounded by a LIMIT and a scan guard (a symbol filter or a
    row cap);
  * a wall-clock budget is recorded for every execution.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any

#: Bounds. Kept small on purpose: this is an interactive explorer, not a bulk
#: export tool.
MAX_ROWS = 200
MAX_LIMIT = 200
TIME_BUDGET_MS = 4000

#: Allowed datasets and their readable columns. A column not listed here can
#: never appear in a generated statement.
_ALLOW: dict[str, dict[str, Any]] = {
    "securities": {
        "backend": "sqlite",
        "table": "securities",
        "columns": ["symbol", "name", "sector", "instrument_type", "delisted",
                    "source", "first_seen", "last_updated"],
        "label": "Listed securities",
    },
    "fundamentals": {
        "backend": "sqlite",
        "table": "fundamentals",
        "columns": ["symbol", "field", "value", "unit", "period_end", "source", "verification"],
        "label": "Stored fundamentals",
    },
    "collector_quotes": {
        "backend": "sqlite",
        "table": "collector_quotes",
        "columns": ["symbol", "ltp", "volume", "observed_at"],
        "label": "Collector quotes",
    },
    "price_bars": {
        "backend": "duckdb",
        "table": "price_bars",
        "columns": ["symbol", "trading_date", "open", "high", "low", "close",
                    "volume", "turnover", "percent_change", "source"],
        "label": "End-of-day bars",
    },
    "index_series": {
        "backend": "duckdb",
        "table": "index_series",
        "columns": ["index_name", "trading_date", "close", "source"],
        "label": "Index series",
    },
}

#: Fundamental field tokens recognised in a question -> canonical stored field.
_FIELDS = {
    "eps": "eps", "earnings per share": "eps",
    "pe": "pe", "p/e": "pe", "price to earnings": "pe",
    "paid up capital": "paid_up_capital", "paid-up capital": "paid_up_capital",
    "profit": "profit", "net profit": "profit",
    "net worth per share": "net_worth_per_share", "networth": "net_worth_per_share",
    "dps": "dps", "dividend per share": "dps",
    "book value": "book_value", "pb": "pb", "p/b": "pb",
}

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,15}$")
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_SYMBOL_TOKEN = re.compile(r"\b([A-Z]{2,15}\d{0,3})\b")
_LIMIT_RE = re.compile(r"\b(?:top|first|last)\s+(\d{1,4})\b")
_DAYS_RE = re.compile(r"\b(?:last|past|over)\s+(\d{1,4})\s*(?:days|sessions|bars)\b")
_YEAR_RE = re.compile(r"\bin\s+(\d{4})\b")

_SUPPORTED = [
    "how many securities", "list securities [in <sector>]",
    "price of <SYMBOL>", "close of <SYMBOL> on <YYYY-MM-DD>",
    "average close of <SYMBOL> over last <N> days",
    "highest/lowest close of <SYMBOL> in <YYYY>",
    "how many bars for <SYMBOL>", "date range for <SYMBOL>",
    "top <N> symbols by volume/turnover/close",
    "<field> of <SYMBOL>", "<field> history of <SYMBOL>",
    "close of <INDEX> index",
]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class QueryError(Exception):
    """Raised when a question cannot be turned into a safe, supported plan."""


def _store(store: Any = None) -> Any:
    if store is not None:
        return store
    from megatool.market_store import MarketStore

    return MarketStore(read_only=True)


def _norm_symbol(tok: str) -> str | None:
    up = tok.strip().upper()
    return up if _SYMBOL_RE.match(up) else None


_STOP_WORDS = {
    "THE", "OF", "FOR", "AND", "HOW", "MANY", "LIST", "TOP", "LAST",
    "PAST", "DAYS", "CLOSE", "PRICE", "AVERAGE", "HIGHEST", "LOWEST",
    "BARS", "DATE", "RANGE", "IN", "ON", "OVER", "BY", "SHOW", "ME",
    "SYMBOLS", "SECURITIES", "INDEX", "STOCK", "STOCKS", "NEPSE",
    "HISTORY", "TREND", "TIME", "VALUE", "QUOTE", "COMPANIES", "NUMBER",
}


def _find_symbol(q: str) -> str | None:
    """Find the symbol token, ignoring field words and ordinary English words.

    A field word such as ``EPS`` looks exactly like a ticker to a regex, so the
    field vocabulary is excluded explicitly; otherwise "eps of NABIL" would be
    parsed as a question about a company called EPS.
    """
    stop = set(_STOP_WORDS)
    for token in _FIELDS:
        stop.update(w.upper() for w in re.split(r"[^a-z0-9]+", token) if w)
    for m in _SYMBOL_TOKEN.finditer(q.upper()):
        tok = m.group(1)
        if tok in stop:
            continue
        if _SYMBOL_RE.match(tok):
            return tok
    return None


# --------------------------------------------------------------------------- #
# Parse -> plan
# --------------------------------------------------------------------------- #

def parse(question: str) -> dict[str, Any]:
    """Turn a question into a plan. Raises QueryError for anything unsupported."""
    q = " ".join((question or "").strip().split())
    if not q:
        raise QueryError("empty question")
    # SQL metacharacters are never needed to express a supported question. A
    # question containing them is refused outright rather than partially parsed,
    # so a payload cannot be smuggled past the symbol/date validators.
    if any(tok in q for tok in (";", "--", "/*", "*/", "'", '"', "\\")):
        raise QueryError("question contains SQL metacharacters and was refused")
    low = q.lower()

    # --- counts / listings over securities
    if re.search(r"\bhow many (securities|symbols|companies|stocks)\b", low) or low in (
        "count securities", "number of securities", "count symbols"
    ):
        return {"intent": "count_securities", "dataset": "securities",
                "fields": ["symbol"], "filters": {}, "limit": 1, "calculation": "count"}
    m = re.search(
        r"\blist\s+(?:(?:top\s+)?(\d{1,4})\s+)?(?:securities|symbols|companies|stocks)\b"
        r"(?:\s+in\s+([a-z ]+))?",
        low,
    )
    if m:
        sector = (m.group(2) or "").strip()
        n = int(m.group(1)) if m.group(1) else 50
        return {"intent": "list_securities", "dataset": "securities",
                "fields": ["symbol", "name", "sector"], "filters": {"sector": sector},
                "limit": min(MAX_LIMIT, n),
                "calculation": "list"}

    # --- index close
    if "index" in low and ("close" in low or "price" in low or "value" in low):
        return {"intent": "index_latest", "dataset": "index_series",
                "fields": ["index_name", "trading_date", "close"], "filters": {},
                "limit": 5, "calculation": "latest_per_group"}

    # --- bar count / coverage for a symbol
    sym = _find_symbol(q)
    if re.search(r"\bhow many bars\b|\bbar count\b|\bnumber of bars\b", low):
        if not sym:
            raise QueryError("no symbol recognised for a bar count")
        return {"intent": "bar_count", "dataset": "price_bars", "fields": ["symbol"],
                "filters": {"symbol": sym}, "limit": 1, "calculation": "count"}
    if re.search(r"\bdate range\b|\bcoverage\b|\bfirst and last\b", low):
        if not sym:
            raise QueryError("no symbol recognised for a coverage query")
        return {"intent": "coverage", "dataset": "price_bars",
                "fields": ["symbol", "trading_date"], "filters": {"symbol": sym},
                "limit": 1, "calculation": "min_max"}

    # --- top movers by a column
    lm = _LIMIT_RE.search(low)
    if re.search(r"\btop\s+\d*\s*\w*\s*by\b|\btop\b.*\bby (volume|turnover|close|percent)", low):
        col = "volume"
        for c in ("turnover", "volume", "percent_change", "close"):
            if c in low:
                col = c
                break
        n = int(lm.group(1)) if lm else 10
        return {"intent": "top_by", "dataset": "price_bars",
                "fields": ["symbol", "trading_date", col], "filters": {"column": col},
                "limit": min(MAX_LIMIT, n), "calculation": "rank_desc_latest"}

    # --- fundamental field for a symbol
    for token, field in sorted(_FIELDS.items(), key=lambda kv: -len(kv[0])):
        if token in low:
            if not sym:
                raise QueryError(f"recognised field {field!r} but no symbol")
            history = "history" in low or "over time" in low or "trend" in low
            return {"intent": "fundamental", "dataset": "fundamentals",
                    "fields": ["symbol", "field", "value", "period_end", "source"],
                    "filters": {"symbol": sym, "field": field},
                    "limit": min(MAX_LIMIT, 24 if history else 1),
                    "calculation": "history" if history else "latest"}

    # --- price statistics
    if sym and re.search(r"\b(average|mean)\b", low):
        days = _DAYS_RE.search(low)
        n = int(days.group(1)) if days else 30
        return {"intent": "price_stat", "dataset": "price_bars",
                "fields": ["symbol", "close"], "filters": {"symbol": sym, "window": n},
                "limit": 1, "calculation": "average_close"}
    if sym and re.search(r"\b(highest|max|lowest|min)\b", low):
        year = _YEAR_RE.search(low)
        agg = "max" if re.search(r"\b(highest|max)\b", low) else "min"
        return {"intent": "price_stat", "dataset": "price_bars",
                "fields": ["symbol", "close", "trading_date"], "filters": {"symbol": sym, "year": year.group(1) if year else None},
                "limit": 1, "calculation": f"{agg}_close"}

    # --- latest price / price on date
    if sym and re.search(r"\b(price|close|quote)\b", low):
        dm = _DATE_RE.search(q)
        if dm:
            return {"intent": "price_on_date", "dataset": "price_bars",
                    "fields": ["symbol", "trading_date", "open", "high", "low", "close", "volume"],
                    "filters": {"symbol": sym, "date": dm.group(1)}, "limit": 1, "calculation": "point"}
        return {"intent": "latest_price", "dataset": "price_bars",
                "fields": ["symbol", "trading_date", "open", "high", "low", "close", "volume"],
                "filters": {"symbol": sym}, "limit": 1, "calculation": "latest"}

    raise QueryError(
        "unsupported question. Supported shapes: " + "; ".join(_SUPPORTED)
    )


def validate(plan: dict[str, Any]) -> dict[str, Any]:
    """Check a plan against the allowlists before anything runs."""
    ds = plan.get("dataset")
    if ds not in _ALLOW:
        raise QueryError(f"dataset {ds!r} is not on the allowlist {sorted(_ALLOW)}")
    allowed_cols = set(_ALLOW[ds]["columns"])
    bad = [c for c in plan.get("fields", []) if c not in allowed_cols]
    if bad:
        raise QueryError(f"columns {bad} are not readable in {ds!r}")
    filt = dict(plan.get("filters") or {})
    if "symbol" in filt:
        if not _SYMBOL_RE.match(str(filt["symbol"]).upper()):
            raise QueryError(f"invalid symbol {filt['symbol']!r}")
    if "date" in filt and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(filt["date"])):
        raise QueryError(f"invalid date {filt['date']!r}")
    if "year" in filt and filt["year"] and not re.match(r"^\d{4}$", str(filt["year"])):
        raise QueryError(f"invalid year {filt['year']!r}")
    if "field" in filt and not re.match(r"^[a-z_]{1,40}$", str(filt["field"])):
        raise QueryError(f"invalid field {filt['field']!r}")
    lim = int(plan.get("limit", 50))
    if lim < 1 or lim > MAX_LIMIT:
        raise QueryError(f"limit {lim} out of range 1..{MAX_LIMIT}")
    plan = dict(plan)
    plan["limit"] = lim
    return plan


# --------------------------------------------------------------------------- #
# Execute
# --------------------------------------------------------------------------- #
def _sqlite(statement: str, params: tuple) -> list[dict[str, Any]]:
    from megatool.db import get_conn

    with get_conn() as conn:
        return [dict(r) for r in conn.execute(statement, params).fetchall()]


def _duck(store: Any, statement: str, params: tuple) -> list[dict[str, Any]]:
    return store.query_df(statement, params).to_dict("records")


def _jsonable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make driver values JSON-safe and driver-independent.

    DuckDB returns ``date``/``Timestamp`` objects while SQLite returns ISO text;
    normalising here means a caller sees the same shape whichever backend
    answered, and the HTTP layer never has to guess.
    """
    import datetime as _dt

    out: list[dict[str, Any]] = []
    for r in rows:
        clean: dict[str, Any] = {}
        for k, v in r.items():
            if isinstance(v, (_dt.datetime,)):
                clean[k] = v.isoformat()
            elif isinstance(v, (_dt.date,)):
                clean[k] = v.isoformat()
            elif hasattr(v, "item") and not isinstance(v, (str, bytes)):
                try:
                    clean[k] = v.item()
                except Exception:  # pragma: no cover - defensive
                    clean[k] = str(v)
            else:
                clean[k] = v
        out.append(clean)
    return out


def execute(plan: dict[str, Any], *, store: Any = None) -> dict[str, Any]:
    """Run a validated plan through parameterised, bounded statements."""
    plan = validate(plan)
    st = _store(store)
    ds = plan["dataset"]
    spec = _ALLOW[ds]
    backend = spec["backend"]
    filt = plan.get("filters") or {}
    intent = plan["intent"]
    limit = plan["limit"]
    rows: list[dict[str, Any]] = []
    provenance: list[str] = []
    start = time.perf_counter()

    def read(statement: str, params: tuple) -> list[dict[str, Any]]:
        return _sqlite(statement, params) if backend == "sqlite" else _duck(st, statement, params)

    try:
        if intent == "count_securities":
            r = read("SELECT COUNT(*) AS n FROM securities", ())
            rows = r
        elif intent == "list_securities":
            if filt.get("sector"):
                rows = read(
                    "SELECT symbol, name, sector FROM securities WHERE lower(sector) LIKE ? "
                    "ORDER BY symbol LIMIT ?",
                    (f"%{filt['sector'].lower()}%", limit),
                )
            else:
                rows = read(
                    "SELECT symbol, name, sector FROM securities ORDER BY symbol LIMIT ?",
                    (limit,),
                )
        elif intent == "index_latest":
            rows = read(
                "SELECT index_name, trading_date, close FROM index_series "
                "ORDER BY trading_date DESC LIMIT ?",
                (limit,),
            )
        elif intent == "bar_count":
            rows = read("SELECT COUNT(*) AS bars FROM price_bars WHERE symbol = ?",
                        (filt["symbol"],))
        elif intent == "coverage":
            rows = read(
                "SELECT MIN(trading_date) AS first_date, MAX(trading_date) AS last_date, "
                "COUNT(*) AS bars FROM price_bars WHERE symbol = ?",
                (filt["symbol"],),
            )
        elif intent == "top_by":
            col = filt["column"]
            if col not in _ALLOW["price_bars"]["columns"]:
                raise QueryError(f"column {col!r} not readable")
            rows = read(
                f"SELECT symbol, trading_date, {col} AS value FROM price_bars "
                f"WHERE trading_date = (SELECT MAX(trading_date) FROM price_bars) "
                f"AND {col} IS NOT NULL ORDER BY {col} DESC LIMIT ?",  # noqa: S608 - col allowlisted
                (limit,),
            )
        elif intent == "fundamental":
            if plan["calculation"] == "latest":
                rows = read(
                    "SELECT symbol, field, value, unit, period_end, source FROM fundamentals "
                    "WHERE symbol = ? AND field = ? ORDER BY period_end DESC LIMIT ?",
                    (filt["symbol"], filt["field"], limit),
                )
            else:
                rows = read(
                    "SELECT symbol, field, value, unit, period_end, source FROM fundamentals "
                    "WHERE symbol = ? AND field = ? ORDER BY period_end DESC LIMIT ?",
                    (filt["symbol"], filt["field"], limit),
                )
        elif intent == "latest_price":
            rows = read(
                "SELECT symbol, trading_date, open, high, low, close, volume FROM price_bars "
                "WHERE symbol = ? ORDER BY trading_date DESC LIMIT 1",
                (filt["symbol"],),
            )
        elif intent == "price_on_date":
            rows = read(
                "SELECT symbol, trading_date, open, high, low, close, volume FROM price_bars "
                "WHERE symbol = ? AND trading_date = ? LIMIT 1",
                (filt["symbol"], filt["date"]),
            )
        elif intent == "price_stat":
            calc = plan["calculation"]
            if calc == "average_close":
                n = int(filt.get("window", 30))
                rows = read(
                    "SELECT symbol, AVG(close) AS average_close, COUNT(*) AS bars FROM ("
                    "SELECT symbol, close FROM price_bars WHERE symbol = ? "
                    "ORDER BY trading_date DESC LIMIT ?) t GROUP BY symbol",
                    (filt["symbol"], min(n, 500)),
                )
            else:
                agg = "MAX" if calc == "max_close" else "MIN"
                if filt.get("year"):
                    rows = read(
                        f"SELECT symbol, {agg}(close) AS value FROM price_bars "
                        f"WHERE symbol = ? AND trading_date >= ? AND trading_date <= ? "
                        f"GROUP BY symbol",
                        (filt["symbol"], f"{filt['year']}-01-01", f"{filt['year']}-12-31"),
                    )
                else:
                    rows = read(
                        f"SELECT symbol, {agg}(close) AS value FROM price_bars "
                        f"WHERE symbol = ? GROUP BY symbol",  # noqa: S608 - agg allowlisted
                        (filt["symbol"],),
                    )
        else:
            raise QueryError(f"intent {intent!r} has no executor")
    except QueryError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise QueryError(f"execution failed: {exc}") from exc

    duration_ms = int((time.perf_counter() - start) * 1000)
    if duration_ms > TIME_BUDGET_MS:
        return {"status": "error", "reason": f"query exceeded the {TIME_BUDGET_MS} ms budget",
                "plan": plan, "duration_ms": duration_ms, "rows": []}
    rows = _jsonable(rows)[:MAX_ROWS]
    provenance = [spec["label"], f"backend={backend}"]
    return {
        "status": "ok",
        "plan": plan,
        "rows": rows,
        "row_count": len(rows),
        "provenance": provenance,
        "duration_ms": duration_ms,
        "missing": [] if rows else [f"no stored rows in {ds!r} matched {filt or 'the query'}"],
        "limitations": (
            "Read-only, allowlisted and limited; only the project's stored data is queried. "
            "Daily data only; no intraday, order-book or trade-level detail."
        ),
        "as_of": _now(),
    }


def run(question: str, *, store: Any = None, persist: bool = True) -> dict[str, Any]:
    """Parse, validate, execute and record one natural-language query."""
    from megatool.db import get_conn

    plan: dict[str, Any] = {}
    status, reason, n, ms = "error", "", 0, 0
    result: dict[str, Any]
    try:
        plan = validate(parse(question))
        result = execute(plan, store=store)
        status = result["status"]
        n = result.get("row_count", 0)
        ms = result.get("duration_ms", 0)
        if status != "ok":
            reason = result.get("reason", "")
    except QueryError as exc:
        reason = str(exc)
        result = {"status": "rejected", "reason": reason, "question": question,
                  "supported": _SUPPORTED}
        status = "rejected"
    if persist:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO nl_query_runs (created_at, question, plan_json, status, reason, rows, duration_ms) "
                "VALUES (?,?,?,?,?,?,?)",
                (_now(), question, _canonical(plan), status, reason, n, ms),
            )
    result["question"] = question
    return result


def _canonical(obj: Any) -> str:
    import json

    return json.dumps(obj, sort_keys=True, default=str)


def history(limit: int = 50) -> list[dict[str, Any]]:
    from megatool.db import get_conn

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, created_at, question, status, reason, rows, duration_ms "
            "FROM nl_query_runs ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
    return [dict(r) for r in rows]
