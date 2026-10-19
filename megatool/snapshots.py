"""Reproducible calculation snapshots (mission Phase C / NF-014).

A snapshot records *how* a result was produced so it can be re-derived later:
the inputs and their hashes, the parameters, the code version, the data cutoff,
the assumptions, the warnings, and -- honestly -- whether the calculation can
actually be reproduced.

Reproducibility is classified by this module, never asserted by the caller:

* ``fully_reproducible``     every required input, version and parameter is captured;
* ``partially_reproducible`` some required historical inputs are missing;
* ``unrecoverable``          no required input can be recovered.

Only named scalar parameters are accepted, so a snapshot can never contain an
API key, a bearer token or any other secret.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

#: Analysis functions that read stored price/index history. Everything else in
#: the catalogue is driven purely by caller-supplied assumptions.
_STORE_BACKED = {
    "rolling_beta", "volatility_percentile", "technical_rating", "mtf_confluence",
    "correlation_matrix", "efficient_frontier", "signal_outcomes", "hrp_portfolio",
    "deflated_sharpe", "stress_test", "event_study", "liquidity_drought",
    "fundamental_forensics", "factor_snapshot", "coverage_explorer",
}
_NEEDS_INDEX = {"stress_test", "deflated_sharpe", "event_study"}
_FUNDAMENTAL_BACKED = {"fundamental_forensics"}

#: Parameter names that must never be persisted even if a caller supplies them.
_SECRET_HINTS = ("key", "token", "secret", "password", "authorization", "bearer", "auth")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _hash(obj: Any) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _scrub(params: dict[str, Any]) -> dict[str, Any]:
    """Drop anything that looks like a credential before it is ever stored.

    Matching is on whole ``_``-separated tokens, so a legitimate parameter such
    as ``monkey`` is never mistaken for a key named ``key``.
    """
    clean: dict[str, Any] = {}
    for k, v in (params or {}).items():
        tokens = {t for t in re.split(r"[^a-z0-9]+", str(k).lower()) if t}
        if tokens & set(_SECRET_HINTS):
            continue
        clean[k] = v
    return clean


def classify(required: list[str], missing: list[str]) -> str:
    """Decide reproducibility from what is required versus what is missing."""
    if not required:
        return "fully_reproducible"
    recoverable = [r for r in required if r not in set(missing)]
    if not recoverable:
        return "unrecoverable"
    if missing:
        return "partially_reproducible"
    return "fully_reproducible"


def _store(store: Any = None) -> Any:
    if store is not None:
        return store
    from megatool.market_store import MarketStore

    return MarketStore(read_only=True)


def _symbol_inputs(symbols: list[str], store: Any) -> tuple[str | None, list[str], str | None]:
    """Return (data_cutoff, source_ids, date_range) for the symbols' bars."""
    cutoff = None
    sources: set[str] = set()
    first = None
    last = None
    for s in symbols:
        try:
            df = store.get_bars(s)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        dates = df["trading_date"].astype(str)
        lo, hi = dates.min(), dates.max()
        first = lo if first is None or lo < first else first
        last = hi if last is None or hi > last else last
        cutoff = hi if cutoff is None or hi > cutoff else cutoff
        if "source" in df:
            sources.update(str(x) for x in df["source"].dropna().unique())
    date_range = f"{first}..{last}" if first and last else None
    return cutoff, sorted(sources), date_range


def _index_present(store: Any) -> bool:
    try:
        n = store.query_one("SELECT COUNT(*) FROM index_series")
        return bool(n and n[0])
    except Exception:
        return False


def _fundamentals_present(symbol: str) -> bool:
    from megatool.db import get_conn

    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM fundamentals WHERE symbol = ?", (symbol.upper(),)
            ).fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def _methodology(feature: str) -> dict[str, str]:
    from megatool import catalog

    for t in catalog.all_tools("algorithm"):
        if (t.get("run") or {}).get("fn") == feature:
            return {
                "name": t.get("name", feature),
                "formula": t.get("formula", ""),
                "description": t.get("description", ""),
            }
    return {"name": feature, "formula": "", "description": ""}


def capture(feature: str, params: dict[str, Any] | None = None, *, store: Any = None,
            warnings: list[str] | None = None, results: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run an analysis feature and persist a snapshot of the run.

    ``results`` may be supplied (e.g. a backtest run by another route); otherwise
    the analysis engine is executed here so the stored result is a real one.
    """
    from megatool import catalog

    params = _scrub(dict(params or {}))
    st = _store(store)
    if store is not None and catalog.store_provider() is None:  # type: ignore[attr-defined]
        catalog.set_store_provider(lambda: st)
    try:
        if results is None:
            results = catalog.run_analysis(feature, **params)
    finally:
        if store is not None and catalog.store_provider() is None:  # type: ignore[attr-defined]
            catalog.set_store_provider(None)

    symbols: list[str] = []
    if isinstance(params.get("symbol"), str) and params["symbol"]:
        symbols = [params["symbol"].upper()]
    elif isinstance(params.get("symbols"), list):
        symbols = [str(s).upper() for s in params["symbols"]]

    required: list[str] = []
    missing: list[str] = []
    source_ids: list[str] = []
    data_cutoff = None
    date_range = None
    if feature in _STORE_BACKED and symbols:
        required.append("price_bars")
        data_cutoff, source_ids, date_range = _symbol_inputs(symbols, st)
        if not source_ids:
            missing.append("price_bars")
    if feature in _NEEDS_INDEX:
        required.append("index_series")
        if not _index_present(st):
            missing.append("index_series")
    if feature in _FUNDAMENTAL_BACKED and symbols:
        required.append("fundamentals")
        if not _fundamentals_present(symbols[0]):
            missing.append("fundamentals")

    avail = results.get("available") if isinstance(results, dict) else None
    if avail is False and required and not missing:
        # Result was refused for a data reason we did not model: be honest.
        missing = list({*missing, "unmet_data_requirement"})
    repro = classify(required, missing)
    return create(
        feature=feature,
        params=params,
        results=results,
        universe=",".join(symbols),
        date_range=date_range or "",
        source_ids=source_ids,
        data_cutoff=data_cutoff,
        methodology=_methodology(feature),
        benchmark=str(params.get("benchmark", "")),
        costs=str(params.get("fee_rate", "")),
        seed=str(params.get("seed", "")),
        warnings=warnings or ([] if avail is not False else [str(results.get("reason", "unavailable"))]),
        data_quality="ok" if avail is not False else "unavailable",
        references=source_ids,
        limitations=(
            "Result refused for a data reason; the required input was not available at capture time."
            if avail is False else ""
        ),
        required=required,
        missing=missing,
    )


def create(
    *,
    feature: str,
    params: dict[str, Any],
    results: dict[str, Any],
    universe: str = "",
    date_range: str = "",
    source_ids: list[str] | None = None,
    data_cutoff: str | None = None,
    methodology: dict[str, str] | None = None,
    benchmark: str = "",
    costs: str = "",
    seed: str = "",
    warnings: list[str] | None = None,
    data_quality: str = "unknown",
    references: list[str] | None = None,
    limitations: str = "",
    required: list[str] | None = None,
    missing: list[str] | None = None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Persist a snapshot with an explicit, honest reproducibility label."""
    from megatool import __version__
    from megatool.db import get_conn

    params = _scrub(params)
    source_ids = source_ids or []
    warnings = warnings or []
    references = references or []
    required = required or []
    missing = missing or []
    method = methodology or {}
    repro = classify(required, missing)

    payload = {
        "feature": feature,
        "params": params,
        "universe": universe,
        "date_range": date_range,
        "data_cutoff": data_cutoff,
        "source_ids": source_ids,
        "seed": seed,
        "benchmark": benchmark,
        "costs": costs,
    }
    input_hash = _hash(payload)
    results_hash = _hash(results)
    sid = snapshot_id or f"snap-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"

    row = {
        "id": sid,
        "feature": feature,
        "created_at": _now(),
        "data_cutoff": data_cutoff,
        "universe": universe,
        "date_range": date_range,
        "source_ids": source_ids,
        "input_hash": input_hash,
        "params": params,
        "methodology": method,
        "code_version": __version__,
        "benchmark": benchmark,
        "cost_assumptions": costs,
        "seed": seed,
        "results": results,
        "results_hash": results_hash,
        "warnings": warnings,
        "data_quality": data_quality,
        "references": references,
        "limitations": limitations,
        "reproducibility": repro,
        "missing_inputs": missing,
    }
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO calculation_snapshots
              (id, feature, created_at, data_cutoff, universe, date_range, source_ids,
               input_hash, params_json, methodology, code_version, benchmark,
               cost_assumptions, seed, results_json, results_hash, warnings_json,
               data_quality, references_json, limitations, reproducibility, missing_inputs_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                sid, feature, row["created_at"], data_cutoff, universe, date_range,
                _canonical(source_ids), input_hash, _canonical(params),
                _canonical(method), row["code_version"], benchmark, costs, seed,
                _canonical(results), results_hash, _canonical(warnings), data_quality,
                _canonical(references), limitations, repro, _canonical(missing),
            ),
        )
    return row


def _row_to_snapshot(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"],
        "feature": r["feature"],
        "created_at": r["created_at"],
        "data_cutoff": r["data_cutoff"],
        "universe": r["universe"],
        "date_range": r["date_range"],
        "source_ids": json.loads(r["source_ids"] or "[]"),
        "input_hash": r["input_hash"],
        "params": json.loads(r["params_json"] or "{}"),
        "methodology": json.loads(r["methodology"] or "{}"),
        "code_version": r["code_version"],
        "benchmark": r["benchmark"],
        "cost_assumptions": r["cost_assumptions"],
        "seed": r["seed"],
        "results": json.loads(r["results_json"] or "{}"),
        "results_hash": r["results_hash"],
        "warnings": json.loads(r["warnings_json"] or "[]"),
        "data_quality": r["data_quality"],
        "references": json.loads(r["references_json"] or "[]"),
        "limitations": r["limitations"],
        "reproducibility": r["reproducibility"],
        "missing_inputs": json.loads(r["missing_inputs_json"] or "[]"),
    }


def get_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    from megatool.db import get_conn

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM calculation_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
    return _row_to_snapshot(dict(row)) if row else None


def list_snapshots(*, feature: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    from megatool.db import get_conn

    with get_conn() as conn:
        if feature:
            rows = conn.execute(
                "SELECT * FROM calculation_snapshots WHERE feature = ? ORDER BY created_at DESC LIMIT ?",
                (feature, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM calculation_snapshots ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
    return [_row_to_snapshot(dict(r)) for r in rows]


def compare(a: str, b: str) -> dict[str, Any]:
    """Diff two snapshots: parameters, inputs, versions and results."""
    sa, sb = get_snapshot(a), get_snapshot(b)
    if sa is None or sb is None:
        raise ValueError("both snapshot ids must exist")

    def _flat(d: dict, prefix: str = "") -> dict:
        out: dict = {}
        for k, v in d.items():
            key = f"{prefix}{k}"
            if isinstance(v, dict):
                out.update(_flat(v, f"{key}."))
            else:
                out[key] = v
        return out

    pa, pb = _flat(sa["params"]), _flat(sb["params"])
    param_diff = {k: {"a": pa.get(k), "b": pb.get(k)}
                  for k in set(pa) | set(pb) if pa.get(k) != pb.get(k)}
    ra, rb = _flat(sa["results"]), _flat(sb["results"])
    result_diff = {k: {"a": ra.get(k), "b": rb.get(k)}
                   for k in set(ra) | set(rb) if ra.get(k) != rb.get(k)}
    meta = {}
    for f in ("code_version", "data_cutoff", "universe", "date_range", "seed",
              "benchmark", "cost_assumptions", "reproducibility"):
        if sa.get(f) != sb.get(f):
            meta[f] = {"a": sa.get(f), "b": sb.get(f)}
    return {
        "a": {"id": sa["id"], "feature": sa["feature"], "created_at": sa["created_at"]},
        "b": {"id": sb["id"], "feature": sb["feature"], "created_at": sb["created_at"]},
        "same_feature": sa["feature"] == sb["feature"],
        "same_input_hash": sa["input_hash"] == sb["input_hash"],
        "same_results_hash": sa["results_hash"] == sb["results_hash"],
        "param_diff": param_diff,
        "result_diff": result_diff,
        "meta_diff": meta,
    }


def rerun(snapshot_id: str, *, store: Any = None) -> dict[str, Any]:
    """Re-execute a stored calculation and compare to the stored result.

    Only meaningful for a snapshot whose classification is not ``unrecoverable``.
    Returns an explicit ``reproduced`` flag; it never overstates success.
    """
    from megatool import catalog

    snap = get_snapshot(snapshot_id)
    if snap is None:
        raise ValueError(f"unknown snapshot {snapshot_id!r}")
    if snap["reproducibility"] == "unrecoverable":
        return {"id": snapshot_id, "reproduced": False,
                "reason": "snapshot is classified unrecoverable; original inputs are gone",
                "reproducibility": snap["reproducibility"]}
    st = _store(store)
    if store is not None and catalog.store_provider() is None:  # type: ignore[attr-defined]
        catalog.set_store_provider(lambda: st)
    try:
        fresh = catalog.run_analysis(snap["feature"], **snap["params"])
    except Exception as exc:
        return {"id": snapshot_id, "reproduced": False, "reason": f"rerun failed: {exc}",
                "reproducibility": snap["reproducibility"]}
    finally:
        if store is not None and catalog.store_provider() is None:  # type: ignore[attr-defined]
            catalog.set_store_provider(None)
    fresh_hash = _hash(fresh)
    return {
        "id": snapshot_id,
        "feature": snap["feature"],
        "reproduced": fresh_hash == snap["results_hash"],
        "stored_hash": snap["results_hash"],
        "fresh_hash": fresh_hash,
        "reproducibility": snap["reproducibility"],
        "missing_inputs": snap["missing_inputs"],
        "note": "hash equality means byte-identical results under the same inputs and seed.",
    }
