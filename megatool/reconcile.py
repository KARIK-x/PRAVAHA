"""Data-source reconciliation (mission Phase B).

The platform stores the same kind of observation from more than one source in a
few places: fundamentals carry a ``source`` per row; ``market_quotes`` keeps one
row per ``(symbol, quote_date, source)`` on purpose; ``price_bars`` and
``price_ohlc_history`` describe the same sessions from different pipelines.

This module *compares* those sources. It never overwrites one source with
another and it never declares a winner automatically: a newer or more complete
source is not treated as correct. Only a human decision -- recorded through
:func:`resolve` -- selects a source, and that decision is kept as an audit trail.

Findings are recomputed on demand from the live stores so a cached discrepancy
can never be mistaken for the current one. Missing values are reported as
missing, never invented to make two sources line up.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

#: Comparison classifications. Kept explicit so callers and tests share them.
CLASSIFICATIONS = (
    "match",                 # every source agrees within tolerance
    "within_tolerance",      # sources differ but inside the configured tolerance
    "conflict",              # sources disagree beyond tolerance
    "unit_mismatch",         # the same field reported in different units
    "missing_observation",   # one source has the observation, another does not
    "duplicate",             # the same identity appears twice inside one source
    "invalid",               # a value violates a structural rule (e.g. high < low)
    "stale",                 # observation older than the dataset's expected cadence
    "unperiodised",          # values with no period cannot be compared honestly
    "unadjusted",            # prices whose adjustment status is not 'adjusted'
)

RESOLUTIONS = ("accepted", "accepted_both", "left_open", "needs_review")

#: Hard caps so a comparison over a large store stays bounded and fast.
_MAX_FINDINGS = 5000
_MAX_GROUPS_SCANNED = 200_000


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _store(store: Any = None) -> Any:
    """Return a market store for read access.

    ``store`` is passed in by the API (its live handle). Standalone callers get
    a read-only store: a read-write open would take DuckDB's exclusive lock and
    collide with a running server.
    """
    if store is not None:
        return store
    from megatool.market_store import MarketStore

    return MarketStore(read_only=True)


# --------------------------------------------------------------------------- #
# Dataset descriptors
# --------------------------------------------------------------------------- #

#: Each dataset declares where its rows live and how identity, value, unit,
#: observation time and ingestion time are expressed. The reconciliation code
#: reads this, so adding a dataset is data, not new branching logic.
DATASETS: dict[str, dict[str, Any]] = {
    "fundamentals": {
        "label": "Fundamentals (per-period, per-source)",
        "backend": "sqlite",
        "table": "fundamentals",
        "identity": ("symbol", "field", "period_end"),
        "source_col": "source",
        "value_cols": ("value",),
        "unit_col": "unit",
        "observed_col": "period_end",
        "ingested_col": "retrieved_at",
        "multi_source": True,
        "expected_cadence_days": 400,  # quarterly-ish; stale beyond ~13 months
        "adjustment": "not_applicable",
    },
    "price_bars": {
        "label": "End-of-day price bars (DuckDB)",
        "backend": "duckdb",
        "table": "price_bars",
        "identity": ("symbol", "trading_date"),
        "source_col": "source",
        "value_cols": ("open", "high", "low", "close", "volume", "turnover"),
        "unit_col": None,
        "observed_col": "trading_date",
        "ingested_col": "retrieved_at",
        "multi_source": False,
        "expected_cadence_days": 10,
        "adjustment": "adjustment_status",
    },
    "market_quotes": {
        "label": "Near-live quotes (DuckDB, per-source)",
        "backend": "duckdb",
        "table": "market_quotes",
        "identity": ("symbol", "quote_date"),
        "source_col": "source",
        "value_cols": ("ltp", "high", "low", "volume", "turnover"),
        "unit_col": None,
        "observed_col": "quote_date",
        "ingested_col": "retrieved_at",
        "multi_source": True,
        "expected_cadence_days": 10,
        "adjustment": "not_applicable",
    },
}


# --------------------------------------------------------------------------- #
# Low-level readers
# --------------------------------------------------------------------------- #

def _sqlite_rows(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    from megatool.db import get_conn, init_app_db

    init_app_db()  # idempotent; a fresh data dir gets the schema on first use
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def _duck_rows(store: Any, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    df = store.query_df(query, params)
    return df.to_dict("records") if df is not None else []


def _read_dataset(name: str, store: Any) -> list[dict[str, Any]]:
    spec = DATASETS[name]
    table = spec["table"]
    cols = set(spec["identity"]) | set(spec["value_cols"]) | {spec["source_col"]}
    for opt in (spec.get("unit_col"), spec.get("observed_col"), spec.get("ingested_col")):
        if opt:
            cols.add(opt)
    if spec.get("adjustment") not in (None, "not_applicable"):
        cols.add(spec["adjustment"])
    collist = ", ".join(sorted(cols))
    query = f"SELECT {collist} FROM {table}"  # noqa: S608 - table/cols are from the fixed spec
    if spec["backend"] == "sqlite":
        return _sqlite_rows(query)
    return _duck_rows(store, query)


# --------------------------------------------------------------------------- #
# Inventory & profile
# --------------------------------------------------------------------------- #

_COMPARISON_LABELS = {
    "fundamentals": "Fundamentals — cross-source values, coverage, timestamps, duplicates",
    "fundamentals_staleness": "Fundamentals — staleness of the newest stored period",
    "price_bars": "Price bars — cross-source closes, structure, timestamps, duplicates",
    "market_quotes": "Near-live quotes — cross-source values, timestamps, duplicates",
    "index": "Index closes — DuckDB series vs stored index OHLC history",
}


def comparisons() -> list[dict[str, Any]]:
    """The comparison buckets a caller can run, with a human label.

    Distinct from :data:`DATASETS`: a bucket may compose several datasets
    (``price_bars`` also joins quotes and collector quotes) or join across
    backends (``index``).
    """
    return [
        {"name": name, "label": _COMPARISON_LABELS.get(name, name),
         "profile_available": name in DATASETS}
        for name in sorted(_COMPARATORS)
    ]


def _q(name: str, store: Any, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run an aggregate query against the dataset's backend."""
    spec = DATASETS[name]
    if spec["backend"] == "sqlite":
        return _sqlite_rows(sql, params)
    return _duck_rows(store, sql, params)


def _dataset_aggregates(name: str, store: Any) -> dict[str, Any]:
    """Coverage facts via SQL aggregates.

    The full result set is never materialised here: ``price_bars`` holds over
    half a million rows, and loading them just to count would make the inventory
    endpoint unusably slow.
    """
    spec = DATASETS[name]
    table, src, obs = spec["table"], spec["source_col"], spec["observed_col"]
    head = _q(name, store, f"SELECT COUNT(*) AS n, MIN({obs}) AS lo, MAX({obs}) AS hi FROM {table}")
    row0 = head[0] if head else {}
    srcs = _q(name, store, f"SELECT {src} AS s, COUNT(*) AS n FROM {table} GROUP BY {src}")
    missing: dict[str, int] = {}
    for col in spec["value_cols"]:
        m = _q(name, store, f"SELECT COUNT(*) AS n FROM {table} WHERE {col} IS NULL")
        missing[col] = int((m[0] if m else {}).get("n") or 0)
    units: dict[str, int] = {}
    if spec.get("unit_col"):
        us = _q(name, store,
                f"SELECT {spec['unit_col']} AS u, COUNT(*) AS n FROM {table} GROUP BY {spec['unit_col']}")
        units = {str(x.get("u") or "none"): int(x.get("n") or 0) for x in us}
    return {
        "rows": int(row0.get("n") or 0),
        "first_observed": str(row0.get("lo")) if row0.get("lo") is not None else None,
        "last_observed": str(row0.get("hi")) if row0.get("hi") is not None else None,
        "sources": {str(x.get("s") or "unknown"): int(x.get("n") or 0) for x in srcs},
        "missing_by_field": missing,
        "units": units,
    }


def inventory(store: Any = None) -> dict[str, Any]:
    """Every dataset this module knows about, with live coverage facts."""
    store = _store(store)
    out = []
    for name, spec in DATASETS.items():
        try:
            agg = _dataset_aggregates(name, store)
        except Exception as exc:  # dataset may be empty/absent
            out.append({**{"dataset": name, "label": spec["label"]}, "available": False,
                        "reason": str(exc)})
            continue
        out.append({
            "dataset": name,
            "label": spec["label"],
            "available": True,
            "rows": agg["rows"],
            "sources": agg["sources"],
            "source_count": len(agg["sources"]),
            "multi_source": spec["multi_source"],
            "fields": list(spec["value_cols"]),
            "first_observed": agg["first_observed"],
            "last_observed": agg["last_observed"],
            "adjustment": spec["adjustment"],
        })
    return {"datasets": out, "comparisons": comparisons(), "generated_at": _now()}


def _distinct_sources(rows: list[dict[str, Any]], col: str) -> dict[str, int]:
    d: dict[str, int] = {}
    for r in rows:
        d[str(r.get(col) or "unknown")] = d.get(str(r.get(col) or "unknown"), 0) + 1
    return d


def profile(dataset: str, store: Any = None) -> dict[str, Any]:
    """Coverage, missing-value and structural facts for one dataset."""
    if dataset not in DATASETS:
        raise ValueError(f"unknown dataset {dataset!r}; choose from {sorted(DATASETS)}")
    store = _store(store)
    spec = DATASETS[dataset]
    agg = _dataset_aggregates(dataset, store)
    return {
        "dataset": dataset,
        "label": spec["label"],
        "rows": agg["rows"],
        "sources": agg["sources"],
        "fields": list(spec["value_cols"]),
        "missing_by_field": agg["missing_by_field"],
        "units": agg["units"],
        "first_observed": agg["first_observed"],
        "last_observed": agg["last_observed"],
        "expected_cadence_days": spec["expected_cadence_days"],
        "adjustment": spec["adjustment"],
        "generated_at": _now(),
    }


# --------------------------------------------------------------------------- #
# Comparison engines
# --------------------------------------------------------------------------- #

def _finding(fid: str, dataset: str, classification: str, severity: str, key: dict,
             sources: list[dict], detail: str, *, symbol: Any = None, period: Any = None) -> dict:
    return {
        "id": fid,
        "dataset": dataset,
        "classification": classification,
        "severity": severity,
        "key": key,
        "symbol": symbol,
        "period": period,
        "sources": sources,
        "detail": detail,
    }


def compare_fundamentals(*, tolerance_pct: float = 0.0, include_matches: bool = False) -> list[dict]:
    """Compare fundamentals reported by more than one source for one identity.

    Identity is ``(symbol, field, period_end)``. A blank ``period_end`` cannot be
    compared honestly (two sources may be describing different vintages) and is
    classified ``unperiodised``.
    """
    rows = _sqlite_rows(
        "SELECT symbol, field, value, unit, period_end, source, source_ref, "
        "retrieved_at, verification FROM fundamentals"
    )
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        if r.get("value") is None:
            continue
        groups.setdefault((r["symbol"], r["field"], r.get("period_end") or ""), []).append(r)
    findings: list[dict] = []
    for (symbol, field, period), members in groups.items():
        if len(findings) >= _MAX_FINDINGS:
            break
        srcs = {str(m.get("source") or "unknown") for m in members}
        if len(srcs) < 2:
            continue
        key = {"symbol": symbol, "field": field, "period_end": period}
        fid = f"fundamentals:{symbol}:{field}:{period or 'unknown'}"
        if not period:
            findings.append(_finding(
                fid, "fundamentals", "unperiodised", "low", key,
                [{"source": m["source"], "value": m["value"], "unit": m.get("unit")} for m in members],
                "Same field reported without a period; sources cannot be compared as one vintage.",
                symbol=symbol, period=None,
            ))
            continue
        units = {str(m.get("unit")) for m in members}
        if len(units) > 1:
            findings.append(_finding(
                fid, "fundamentals", "unit_mismatch", "high", key,
                [{"source": m["source"], "value": m["value"], "unit": m.get("unit")} for m in members],
                f"Sources disagree on unit: {sorted(units)}. Values cannot be compared until units agree.",
                symbol=symbol, period=period,
            ))
            continue
        values = [abs(float(m["value"])) for m in members]
        lo, hi = min(values), max(values)
        base = hi if hi else 1.0
        rel = (hi - lo) / base if base else 0.0
        if rel == 0.0:
            cls, sev = "match", "info"
        elif rel * 100.0 <= tolerance_pct:
            cls, sev = "within_tolerance", "low"
        else:
            cls, sev = "conflict", ("high" if rel > 0.05 else "medium")
        if cls == "match" and not include_matches:
            continue
        findings.append(_finding(
            fid, "fundamentals", cls, sev, key,
            [{"source": m["source"], "value": m["value"], "unit": m.get("unit"),
              "retrieved_at": m.get("retrieved_at"), "verification": m.get("verification"),
              "source_ref": m.get("source_ref")} for m in members],
            f"Values differ by {rel * 100:.3f}% across sources ({sorted(srcs)}).",
            symbol=symbol, period=period,
        ))
    return findings


def _keyval(v: Any) -> str:
    """Normalise a join-key component so a date object matches its ISO text.

    DuckDB hands back ``date``/``Timestamp`` objects while SQLite returns ISO
    strings; comparing them without normalisation silently matched nothing.
    """
    if v is None:
        return ""
    try:
        import datetime as _dt

        if isinstance(v, (_dt.date, _dt.datetime)):
            return v.isoformat()[:10]
    except Exception:  # pragma: no cover
        pass
    s = str(v)
    # A timestamp string like '2003-07-17 00:00:00' joins to '2003-07-17'.
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        return s[:10]
    return s


def _compare_pair(rows_a: list[dict], a_col: str, cols_a: dict[str, str],
                  key_a: tuple, rows_b: list[dict], b_col: str, cols_b: dict[str, str],
                  key_b: tuple, *, dataset: str, label: str, tolerance_bps: float,
                  id_prefix: str, symbol_key: str = "symbol") -> list[dict]:
    """Join two row sets on their key and compare named columns.

    ``cols_a``/``cols_b`` map a comparison label to the column in each set.
    """
    by_a = {tuple(_keyval(r.get(k)) for k in key_a): r for r in rows_a}
    findings: list[dict] = []
    for r in rows_b:
        k = tuple(_keyval(r.get(x)) for x in key_b)
        a = by_a.get(k)
        if a is None:
            continue
        if len(findings) >= _MAX_FINDINGS:
            break
        for label_col, bcol in cols_b.items():
            acol = cols_a[label_col]
            av, bv = a.get(acol), r.get(bcol)
            if av is None or bv is None:
                continue
            if not (isinstance(av, (int, float)) and isinstance(bv, (int, float))):
                continue
            if math.isnan(av) or math.isnan(bv):
                continue
            base = max(abs(av), abs(bv)) or 1.0
            diff_bps = abs(av - bv) / base * 10_000.0
            if diff_bps <= tolerance_bps:
                continue
            findings.append(_finding(
                f"{id_prefix}:{_keyval(r.get(symbol_key))}:{k[-1]}:{label_col}", dataset,
                "conflict", "high" if diff_bps > 100 else "medium",
                {"match_key": [str(x) for x in k], "field": label_col},
                [{"source": f"{label}:A ({a.get('source') or a_col})", "value": av},
                 {"source": f"{label}:B ({r.get(b_col) or b_col})", "value": bv}],
                f"{label_col}: {av!r} vs {bv!r} differ by {diff_bps:.0f} bps (tolerance {tolerance_bps:g} bps).",
                symbol=r.get(symbol_key), period=str(k[-1]),
            ))
    return findings


def compare_price_sources(*, tolerance_bps: float = 25.0, store: Any = None) -> list[dict]:
    """Compare cross-source price observations and flag structural defects.

    Comparisons performed:
      * ``price_bars.close`` vs ``market_quotes.ltp`` on the same symbol/day;
      * ``price_bars.close`` vs ``collector_quotes.ltp`` on the same symbol/day
        (collector quotes are an independent ingestion path);
      * intra-source OHLC structural validity.

    A quote is an evolving snapshot and a close is settled; small differences are
    expected, so the default tolerance is deliberately loose. Any difference is
    reported -- never resolved -- here.
    """
    store = _store(store)
    bars = _duck_rows(
        store,
        "SELECT symbol, trading_date, open, high, low, close, volume, turnover, "
        "source, adjustment_status, validation_status, flags FROM price_bars",
    )
    quotes = _duck_rows(
        store,
        "SELECT symbol, quote_date, ltp, source FROM market_quotes",
    )
    findings = _compare_pair(
        bars, "price_bars.close", {"close": "close"}, ("symbol", "trading_date"),
        quotes, "market_quotes.ltp", {"close": "ltp"}, ("symbol", "quote_date"),
        dataset="price_bars", label="close", tolerance_bps=tolerance_bps,
        id_prefix="price_bars~market_quotes",
    )
    # Independent collector quotes (SQLite). Take the newest observed_at per
    # (symbol, date) so a re-run does not by itself look like a conflict.
    try:
        cq = _sqlite_rows(
            "SELECT c.symbol AS symbol, substr(c.observed_at,1,10) AS quote_date, "
            "c.ltp AS ltp, 'collector' AS source FROM collector_quotes c "
            "WHERE c.ltp IS NOT NULL"
        )
    except Exception:
        cq = []
    if cq:
        findings += _compare_pair(
            bars, "price_bars.close", {"close": "close"}, ("symbol", "trading_date"),
            cq, "collector_quotes.ltp", {"close": "ltp"}, ("symbol", "quote_date"),
            dataset="price_bars", label="close", tolerance_bps=tolerance_bps,
            id_prefix="price_bars~collector_quotes",
        )
    # Structural validity of every bar (independent of any second source).
    # These are aggregated per subtype: a single bad convention on old data would
    # otherwise bury every genuine cross-source discrepancy under thousands of
    # identical rows. ``open outside [low, high]`` is a known NEPSE daily-data
    # convention that the platform's own validator already flags, so it is
    # reported at low severity; the others are hard impossibilities.
    severity_map = {
        "high < low": "high",
        "close outside [low, high]": "high",
        "close <= 0": "high",
        "open outside [low, high]": "low",
    }
    struct_counts: dict[str, int] = {}
    struct_examples: dict[str, list[str]] = {}
    already_flagged = 0
    for r in bars:
        o, h, l, c = r.get("open"), r.get("high"), r.get("low"), r.get("close")
        bad = None
        if all(isinstance(x, (int, float)) for x in (h, l)) and h < l:
            bad = "high < low"
        elif all(isinstance(x, (int, float)) for x in (o, h, l)) and not (l <= o <= h):
            bad = "open outside [low, high]"
        elif all(isinstance(x, (int, float)) for x in (c, h, l)) and not (l <= c <= h):
            bad = "close outside [low, high]"
        elif isinstance(c, (int, float)) and c <= 0:
            bad = "close <= 0"
        if not bad:
            continue
        if bad == "open outside [low, high]" and "open_outside_range" in str(r.get("flags") or ""):
            already_flagged += 1
        struct_counts[bad] = struct_counts.get(bad, 0) + 1
        ex = struct_examples.setdefault(bad, [])
        if len(ex) < 5:
            ex.append(f"{r.get('symbol')}@{str(r.get('trading_date'))[:10]}")
    for subtype, n in sorted(struct_counts.items()):
        findings.append(_finding(
            f"price_bars:structural:{subtype}", "price_bars", "invalid",
            severity_map.get(subtype, "medium"),
            {"subtype": subtype, "count": n,
             "already_flagged_by_platform": already_flagged if subtype == "open outside [low, high]" else 0},
            [{"source": "price_bars", "value": n}],
            f"{n} stored bars match '{subtype}'; examples: {', '.join(struct_examples[subtype])}. "
            "Counts are aggregated because these are intra-source structural facts, not "
            "cross-source disagreements.",
            symbol=None, period=None,
        ))
    return findings


def compare_quotes(*, tolerance_bps: float = 50.0, store: Any = None) -> list[dict]:
    """Compare the same quote reported by two sources in ``market_quotes``."""
    store = _store(store)
    rows = _duck_rows(
        store,
        "SELECT symbol, quote_date, ltp, high, low, volume, turnover, source FROM market_quotes",
    )
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["symbol"], r["quote_date"]), []).append(r)
    findings: list[dict] = []
    for (symbol, day), members in groups.items():
        srcs = {str(m.get("source") or "unknown") for m in members}
        if len(srcs) < 2:
            continue
        for field in ("ltp", "high", "low", "volume", "turnover"):
            vals = [(m["source"], m.get(field)) for m in members if m.get(field) is not None]
            if len(vals) < 2:
                continue
            nums = [v for _, v in vals]
            base = max(abs(x) for x in nums) or 1.0
            diff_bps = (max(nums) - min(nums)) / base * 10_000.0
            if diff_bps <= tolerance_bps:
                continue
            if len(findings) >= _MAX_FINDINGS:
                return findings
            findings.append(_finding(
                f"market_quotes:{symbol}:{day}:{field}", "market_quotes", "conflict",
                "high" if diff_bps > 200 else "medium",
                {"symbol": symbol, "quote_date": str(day), "field": field},
                [{"source": s, "value": v} for s, v in vals],
                f"{field} differs by {diff_bps:.0f} bps across sources {sorted(srcs)}.",
                symbol=symbol, period=str(day),
            ))
    return findings


def compare_index(*, tolerance_bps: float = 5.0, store: Any = None) -> list[dict]:
    """Compare an index close between the DuckDB series and index_ohlc_history."""
    store = _store(store)
    try:
        a = _duck_rows(store, "SELECT index_name, trading_date, close, source FROM index_series")
    except Exception:
        a = []
    b = _sqlite_rows(
        "SELECT index_name, trading_date, close, source FROM index_ohlc_history"
    )
    return _compare_pair(
        a, "index_series.close", {"close": "close"}, ("index_name", "trading_date"),
        b, "index_ohlc_history.close", {"close": "close"}, ("index_name", "trading_date"),
        dataset="index", label="close", tolerance_bps=tolerance_bps,
        id_prefix="index", symbol_key="index_name",
    )


def compare_fundamentals_staleness(*, as_of: str | None = None) -> list[dict]:
    """Flag the newest fundamental period per symbol when it is stale."""
    rows = _sqlite_rows(
        "SELECT symbol, MAX(period_end) AS newest FROM fundamentals WHERE period_end <> '' "
        "GROUP BY symbol"
    )
    ref = as_of or datetime.now(UTC).date().isoformat()
    try:
        ref_y, ref_m, ref_d = (int(x) for x in ref.split("-"))
        import datetime as _dt

        ref_date = _dt.date(ref_y, ref_m, ref_d)
    except Exception:
        return []
    findings: list[dict] = []
    for r in rows:
        newest = r["newest"]
        try:
            y, m, d = (int(x) for x in str(newest).split("-"))
            import datetime as _dt

            age = (ref_date - _dt.date(y, m, d)).days
        except Exception:
            continue
        if age > DATASETS["fundamentals"]["expected_cadence_days"]:
            findings.append(_finding(
                f"fundamentals:stale:{r['symbol']}", "fundamentals", "stale", "medium",
                {"symbol": r["symbol"], "newest_period": newest},
                [{"source": "fundamentals", "value": None}],
                f"Newest stored period {newest} is {age} days old (> cadence "
                f"{DATASETS['fundamentals']['expected_cadence_days']}d).",
                symbol=r["symbol"], period=newest,
            ))
    return findings


def find_duplicates(dataset: str, *, store: Any = None) -> list[dict]:
    """Find repeated observations of the same identity.

    The storage layer enforces uniqueness on the compared identities, so this
    normally returns nothing. It is still run on every comparison: if a future
    importer writes around the constraint, the duplicate is reported here rather
    than silently averaged into the series. For a multi-source dataset, the same
    identity from *different* sources is expected and only a repeat **within one
    source** is flagged.

    Implemented as a grouped count so the full table is never materialised.
    """
    spec = DATASETS[dataset]
    store = _store(store)
    identity = list(spec["identity"])
    group_cols = identity + ([spec["source_col"]] if spec["multi_source"] else [])
    collist = ", ".join(group_cols)
    rows = _q(dataset, store,
              f"SELECT {collist}, COUNT(*) AS n FROM {spec['table']} "  # noqa: S608 - fixed spec
              f"GROUP BY {collist} HAVING COUNT(*) > 1 ORDER BY n DESC LIMIT 200")
    findings: list[dict] = []
    for r in rows:
        n = int(r.get("n") or 0)
        key = {c: _keyval(r.get(c)) for c in group_cols}
        sym = r.get("symbol") or r.get("index_name")
        findings.append(_finding(
            f"{dataset}:duplicate:{':'.join(str(v) for v in key.values())}", dataset,
            "duplicate", "high", key,
            [{"source": r.get(spec["source_col"]), "value": n}],
            f"{n} rows share the identity {key}.",
            symbol=sym,
        ))
    return findings


def compare_fundamentals_coverage(*, min_sources: int = 2) -> list[dict]:
    """Flag a field one source reports for a period that another source omits.

    A gap is not a disagreement: the second source may simply not cover that
    field. It is reported so a consumer knows the observation is single-sourced.
    """
    rows = _sqlite_rows(
        "SELECT symbol, field, period_end, source FROM fundamentals WHERE period_end <> ''"
    )
    by_period: dict[tuple, dict[str, set[str]]] = {}
    for r in rows:
        by_period.setdefault((r["symbol"], r["period_end"]), {}).setdefault(
            str(r.get("source") or "unknown"), set()
        ).add(str(r["field"]))
    findings: list[dict] = []
    for (symbol, period), srcs in by_period.items():
        if len(srcs) < min_sources:
            continue
        union_fields = set().union(*srcs.values())
        for src, fields in srcs.items():
            for field in sorted(union_fields - fields):
                if len(findings) >= _MAX_FINDINGS:
                    return findings
                findings.append(_finding(
                    f"fundamentals:missing:{symbol}:{period}:{src}:{field}", "fundamentals",
                    "missing_observation", "low",
                    {"symbol": symbol, "period_end": period, "field": field, "source": src},
                    [{"source": s, "value": sorted(f) if f else None} for s, f in srcs.items()],
                    f"Source {src!r} has no {field!r} for {period} while another source does.",
                    symbol=symbol, period=period,
                ))
    return findings


def compare_timestamps(dataset: str, *, store: Any = None) -> list[dict]:
    """Check observation-time versus ingestion-time ordering for one dataset.

    * ``price_bars`` -- a bar cannot be ingested before the session it describes.
    * ``market_quotes`` -- the source cannot claim an update later than the fetch.
    * ``fundamentals`` -- a reported period cannot end after the fetch that read it.

    None of these imply a wrong value; they are provenance defects that make the
    ingestion timestamp unreliable as a knowledge time.
    """
    store = _store(store)
    findings: list[dict] = []

    def add(fid: str, sym: Any, period: Any, detail: str) -> None:
        if len(findings) >= _MAX_FINDINGS:
            return
        findings.append(_finding(
            fid, dataset, "invalid", "medium",
            {"symbol": sym, "period": str(period)}, [{"source": dataset, "value": None}],
            detail, symbol=sym, period=str(period),
        ))

    if dataset == "price_bars":
        rows = _duck_rows(store, "SELECT symbol, trading_date, retrieved_at, source FROM price_bars")
        for r in rows:
            obs, ing = _keyval(r.get("trading_date")), _keyval(r.get("retrieved_at"))
            if obs and ing and ing < obs:
                add(f"price_bars:ts:{r.get('symbol')}:{obs}", r.get("symbol"), obs,
                    f"ingested {ing} before the session date {obs}.")
    elif dataset == "market_quotes":
        rows = _duck_rows(
            store, "SELECT symbol, quote_date, retrieved_at, source_updated_at, source FROM market_quotes"
        )
        for r in rows:
            ing, upd = _keyval(r.get("retrieved_at")), _keyval(r.get("source_updated_at"))
            obs = _keyval(r.get("quote_date"))
            if upd and ing and upd > ing:
                add(f"market_quotes:ts:{r.get('symbol')}:{obs}", r.get("symbol"), obs,
                    f"source_updated_at {upd} is later than retrieved_at {ing}.")
    elif dataset == "fundamentals":
        rows = _sqlite_rows(
            "SELECT symbol, field, period_end, retrieved_at, source FROM fundamentals "
            "WHERE period_end <> '' AND retrieved_at <> ''"
        )
        for r in rows:
            obs, ing = _keyval(r.get("period_end")), _keyval(r.get("retrieved_at"))
            if obs and ing and obs > ing:
                add(f"fundamentals:ts:{r.get('symbol')}:{r.get('field')}:{obs}", r.get("symbol"), obs,
                    f"period_end {obs} is after retrieved_at {ing}: the period had not ended at ingestion.")
    else:
        raise ValueError(f"timestamp comparison not defined for {dataset!r}")
    return findings


def _compare_bucket(dataset: str, tol: float, store: Any) -> list[dict]:
    """Compose every check that applies to one reconciliation bucket."""
    if dataset == "price_bars":
        return (
            compare_price_sources(tolerance_bps=tol, store=store)
            + find_duplicates("price_bars", store=store)
            + compare_timestamps("price_bars", store=store)
        )
    if dataset == "fundamentals":
        return (
            compare_fundamentals(tolerance_pct=tol)
            + compare_fundamentals_coverage()
            + compare_timestamps("fundamentals")
            + find_duplicates("fundamentals")
        )
    if dataset == "market_quotes":
        return (
            compare_quotes(tolerance_bps=tol, store=store)
            + compare_timestamps("market_quotes", store=store)
            + find_duplicates("market_quotes", store=store)
        )
    if dataset == "index":
        return compare_index(tolerance_bps=tol, store=store)
    if dataset == "fundamentals_staleness":
        return compare_fundamentals_staleness()
    raise ValueError(f"unknown comparison {dataset!r}")


_COMPARATORS = {
    "fundamentals": _compare_bucket,
    "fundamentals_staleness": _compare_bucket,
    "price_bars": _compare_bucket,
    "market_quotes": _compare_bucket,
    "index": _compare_bucket,
}


def run(dataset: str, *, tolerance: float | None = None, store: Any = None,
        persist: bool = True) -> dict[str, Any]:
    """Run a comparison, persist a summary row, and return the findings."""
    if dataset not in _COMPARATORS:
        raise ValueError(f"unknown comparison {dataset!r}; choose from {sorted(_COMPARATORS)}")
    st = _store(store)
    if dataset in ("price_bars", "market_quotes", "index"):
        default_tol = {"price_bars": 25.0, "market_quotes": 50.0, "index": 5.0}[dataset]
    else:
        default_tol = 0.0
    tol = float(default_tol if tolerance is None else tolerance)
    findings = _compare_bucket(dataset, tol, st)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["classification"]] = counts.get(f["classification"], 0) + 1
    summary = {
        "dataset": dataset,
        "tolerance": tol,
        "findings": len(findings),
        "by_classification": counts,
        "generated_at": _now(),
    }
    if persist:
        from megatool.db import get_conn, init_app_db

        init_app_db()  # idempotent; guarantees the audit tables exist
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO reconciliation_runs (dataset, created_at, tolerances_json, findings, detail_json) "
                "VALUES (?,?,?,?,?)",
                (dataset, summary["generated_at"], str({"tolerance": tol}),
                 len(findings), str(counts)),
            )
    return {**summary, "items": findings}


# --------------------------------------------------------------------------- #
# Resolutions (audit history)
# --------------------------------------------------------------------------- #

def resolve(*, dataset: str, finding_key: str, classification: str, resolution: str,
            chosen_source: str = "", note: str = "", actor: str = "local") -> dict[str, Any]:
    """Record a human decision about one finding. Never rewrites source data."""
    if dataset not in DATASETS and dataset not in _COMPARATORS:
        raise ValueError(f"unknown dataset {dataset!r}")
    if resolution not in RESOLUTIONS:
        raise ValueError(f"unknown resolution {resolution!r}; choose from {RESOLUTIONS}")
    if not finding_key:
        raise ValueError("finding_key is required")
    if resolution == "accepted" and not chosen_source:
        raise ValueError("resolution 'accepted' requires chosen_source")
    from megatool.db import get_conn, init_app_db

    init_app_db()  # idempotent; guarantees the audit table exists
    created = _now()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO reconciliation_resolutions "
            "(dataset, finding_key, classification, chosen_source, resolution, note, actor, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (dataset, finding_key, classification, chosen_source, resolution, note, actor, created),
        )
        rid = int(cur.lastrowid)
    return {"id": rid, "dataset": dataset, "finding_key": finding_key,
            "resolution": resolution, "chosen_source": chosen_source, "created_at": created}


def history(*, dataset: str | None = None, limit: int = 100) -> dict[str, Any]:
    clause = "WHERE dataset = ?" if dataset else ""
    params: tuple = (dataset,) if dataset else ()
    runs = _sqlite_rows(
        f"SELECT id, dataset, created_at, findings, tolerances_json FROM reconciliation_runs "
        f"{clause} ORDER BY id DESC LIMIT ?", (*params, int(limit)),
    )
    res = _sqlite_rows(
        f"SELECT id, dataset, finding_key, classification, chosen_source, resolution, note, actor, created_at "
        f"FROM reconciliation_resolutions {clause} ORDER BY id DESC LIMIT ?", (*params, int(limit)),
    )
    return {"runs": runs, "resolutions": res}
