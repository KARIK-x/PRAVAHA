"""Idempotent integration of the validated source data into the app's stores.

WHY THIS EXISTS
---------------
``scripts/validate_source_pipeline.py`` proves each source conversion reaches
the loaders *inside a throwaway database*. It deliberately never writes the
production files. This script is the missing half: the single, reviewable
operation that performs the same imports against the real stores, so
"integrate the validated data" is one command instead of a manual ritual.

WHAT IT WRITES
--------------
Market DuckDB (``--market-db``):
  * ``security_master`` — one row per stored symbol: name, business sector
    (ordinary shares only), instrument type, and a ``MERGED`` status plus
    successor for every symbol in the corporate-action registry.
  * ``index_series``    — the NEPSE composite and the socrateai sector indices.

SQLite app DB (``--app-db``):
  * ``fundamentals``    — YONEPSE financial reports, point-in-time dated.
  * ``news_items``      — dated exchange notices / disclosures / messages.

SAFETY
------
* **Dry run by default.** Without ``--apply`` nothing is written anywhere; the
  script prints what each step *would* change.
* Every write is an **idempotent upsert**: re-running changes nothing.
* Price bars and any stored financial record are never touched, overwritten or
  deleted — only additive metadata/series/news/fundamentals rows are written.
* The registry never invents a successor, and active symbols are left with an
  ``UNKNOWN`` status rather than a fabricated ``ACTIVE``: not being retired is
  not the same as being attested tradable.

Usage::

    # inspect (writes nothing)
    .venv/bin/python scripts/integrate_validated_data.py \\
        --raw data/review/source_probe_2026-10-15

    # perform the import (stop the server first if the market DB is locked)
    .venv/bin/python scripts/integrate_validated_data.py \\
        --raw data/review/source_probe_2026-10-15 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from megatool import corporate_actions  # noqa: E402
from megatool import fundamentals as fund  # noqa: E402
from megatool import news as news_mod  # noqa: E402
from megatool.datasources import binayabaral, sector_consensus, socrateai, yonepse  # noqa: E402
from megatool.db import get_conn, init_app_db  # noqa: E402
from megatool.index_series import import_index_series  # noqa: E402
from megatool.market_store import MarketStore  # noqa: E402

DEFAULT_MARKET_DB = Path("data/processed/megatool_market.duckdb")
DEFAULT_APP_DB = Path("data/processed/megatool_state.sqlite")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_sector_sources(raw: Path) -> dict[str, dict[str, Any]]:
    return {
        "yonepse": sector_consensus.load_yonepse(_read_json(raw / "yonepse_securities.json")),
        "stockmap": sector_consensus.load_stockmap(_read_json(raw / "surajrimal_stockmap.json")),
        "binayabaral": sector_consensus.load_binayabaral(
            (raw / "binayabaral_symbols.csv").read_text(encoding="utf-8")
        ),
        "nepalstockdata": sector_consensus.load_nepalstockdata(
            (raw / "nepalstockdata_listed_company.csv").read_text(encoding="utf-8")
        ),
    }


# --------------------------------------------------------------------------- steps


def step_security_master(store: MarketStore, raw: Path, apply: bool) -> dict[str, Any]:
    """Corporations actions + sector/instrument classification → security_master."""
    universe = store.symbols(min_bars=1)
    consensus = sector_consensus.build_consensus(universe, **_load_sector_sources(raw))

    rows: list[dict[str, Any]] = []
    for symbol in universe:
        if corporate_actions.is_inactive(symbol):
            continue  # the registry supplies these rows, with MERGED + successor
        rec = consensus["resolved"].get(symbol)
        row: dict[str, Any] = {
            "symbol": symbol,
            "source": "sector consensus (4 public sources; ordinary/instrument rule)",
        }
        if rec:
            if rec.get("company_name"):
                row["name"] = rec["company_name"]
            if rec["is_ordinary"] and rec.get("sector"):
                row["sector"] = rec["sector"]
            row["instrument_type"] = "ordinary" if rec["is_ordinary"] else rec["instrument"]
            # status is intentionally NOT set: the consensus attests a
            # classification, never current tradability.
        rows.append(row)
    # Registry rows last so a retired symbol always carries its attested status.
    rows += corporate_actions.security_master_rows()

    summary = {
        "step": "security_master",
        "universe": len(universe),
        "rows_to_write": len(rows),
        "ordinary_with_sector": sum(
            1 for r in rows if r.get("sector") and r.get("instrument_type") == "ordinary"
        ),
        "instrument_classified": sum(
            1 for r in rows if r.get("instrument_type") and r.get("instrument_type") != "ordinary"
        ),
        "retired_with_status": sum(1 for r in rows if str(r.get("status") or "") == "MERGED"),
    }
    if apply:
        summary["written"] = store.upsert_securities(rows)
    return summary


def step_index_series(store: MarketStore, raw: Path, apply: bool) -> dict[str, Any]:
    """NEPSE composite (binayabaral) + sector indices (socrateai) → index_series."""
    out: dict[str, Any] = {"step": "index_series", "series": []}

    index_text = (raw / "binayabaral_index.csv").read_text(encoding="utf-8")
    converted = binayabaral.index_to_index_csv(index_text)
    if apply:
        import_index_series(
            converted,
            index_name="NEPSE",
            source="binayabaral/nepal-market-data/data/nepse/NEPSE_INDEX.csv",
            store=store,
        )
    n_nepse = max(0, converted.count("\n") - 1)
    out["series"].append({"index_name": "NEPSE", "rows": n_nepse, "source": "binayabaral"})

    sample_dir = raw / "socrateai_index_sample"
    if sample_dir.is_dir() and any(sample_dir.glob("adj_*.csv")):
        observations: list[dict[str, Any]] = []
        for csv_path in sorted(sample_dir.glob("adj_*.csv")):
            parsed = socrateai.parse_index_csv(csv_path.read_text(), trading_date=csv_path.stem[4:])
            observations += parsed["observations"]
        rows = socrateai.to_index_rows(observations, source="socrateai/ohlc_index")
        if apply:
            store.upsert_index_rows(rows)
        indices = sorted({o["index_name"] for o in observations})
        out["series"].append(
            {"index_name": "sector indices", "rows": len(rows), "indices": len(indices)}
        )
        out["socrateai_indices"] = indices
    else:
        out["series"].append({"index_name": "sector indices", "rows": 0, "note": "no sample dir"})
    return out


def step_fundamentals(raw: Path, app_db: Path, apply: bool) -> dict[str, Any]:
    """YONEPSE financial reports → the app DB (point-in-time dated)."""
    records = _read_json(raw / "yonepse_financials.json")
    rows = yonepse.financials_to_fundamental_rows(records)
    pit = yonepse.point_in_time_available(rows)
    loaded = fund.records_from_rows(rows)
    out: dict[str, Any] = {
        "step": "fundamentals",
        "rows_converted": len(rows),
        "records_validated": len(loaded),
        "point_in_time_coverage_pct": pit["coverage_pct"],
    }
    if apply:
        init_app_db(app_db)
        with get_conn(app_db) as conn:
            out["written"] = fund.import_records(loaded, conn)
            out["summary"] = fund.fundamentals_summary(conn)
    return out


def step_news(raw: Path, app_db: Path, apply: bool) -> dict[str, Any]:
    """Dated exchange notices/disclosures/messages → the app DB."""
    rows = yonepse.notify_to_news_rows(
        _read_json(raw / "yonepse_disclosures.json"),
        _read_json(raw / "yonepse_exchange_messages.json"),
        _read_json(raw / "yonepse_notices.json"),
    )
    csv_text = yonepse.news_csv(rows)
    out: dict[str, Any] = {"step": "news", "rows_converted": len(rows)}
    if apply:
        init_app_db(app_db)
        result = news_mod.import_news(csv_text, fmt="csv", source_file="yonepse", db_path=app_db)
        out["imported"] = {
            "added": result["added"],
            "duplicates": result["duplicates"],
            "skipped": result["skipped"],
        }
    return out


# --------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--raw", required=True, type=Path, help="source snapshot directory (source_probe_*)"
    )
    parser.add_argument("--market-db", type=Path, default=DEFAULT_MARKET_DB)
    parser.add_argument("--app-db", type=Path, default=DEFAULT_APP_DB)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the writes; without it every step is planned and nothing changes",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    raw: Path = args.raw
    if not raw.is_dir():
        print(f"error: --raw is not a directory: {raw}", file=sys.stderr)
        return 2

    mode = "APPLY" if args.apply else "DRY RUN (nothing will be written)"
    print(f"mode             : {mode}")
    print(f"raw snapshots    : {raw}")
    print(f"market DuckDB    : {args.market_db}")
    print(f"app SQLite       : {args.app_db}")
    print()

    report: dict[str, Any] = {"mode": "apply" if args.apply else "dry_run", "raw": str(raw)}

    if not args.market_db.exists():
        print(f"error: market db not found: {args.market_db}", file=sys.stderr)
        return 2

    store: MarketStore | None = None
    try:
        try:
            store = MarketStore(args.market_db, read_only=not args.apply)
            store.query_rows("SELECT 1")
        except Exception as exc:  # noqa: BLE001 - surface the lock prominently
            print(
                "error: could not open the market DB "
                f"({'write' if args.apply else 'read'} mode): {exc}\n"
                "       a running server holds a lock on it; stop the server to "
                "apply, or point --market-db at a copy to preview.",
                file=sys.stderr,
            )
            return 3

        report["security_master"] = step_security_master(store, raw, args.apply)
        report["index_series"] = step_index_series(store, raw, args.apply)
        if not args.apply:
            # Read-only store: report what the market steps would touch.
            report["market_db_writable"] = False
    finally:
        if store is not None:
            store.close()

    # Fundamentals/news need a writable app DB even to preview, so preview them
    # against a throwaway copy so the plan is measured, not guessed.
    preview_app = args.app_db
    if not args.apply:
        preview_app = Path(tempfile.mkdtemp(prefix="megatool_integrate_")) / "app.sqlite"
    report["fundamentals"] = step_fundamentals(raw, preview_app, args.apply)
    report["news"] = step_news(raw, preview_app, args.apply)

    print("Security master :")
    sm = report["security_master"]
    print(f"  rows to write        : {sm['rows_to_write']}")
    print(f"  ordinary w/ sector   : {sm['ordinary_with_sector']}")
    print(f"  instrument-classified: {sm['instrument_classified']}")
    print(f"  registry MERGED rows : {sm['retired_with_status']}")
    print("Index series    :")
    for s in report["index_series"]["series"]:
        extra = f", {s['indices']} indices" if "indices" in s else ""
        print(f"  {s['index_name']:<16} {s['rows']} rows{extra}")
    print("Fundamentals    :")
    f = report["fundamentals"]
    print(f"  records validated    : {f['records_validated']}")
    print(f"  point-in-time cover  : {f['point_in_time_coverage_pct']}%")
    print("News / events   :")
    print(f"  rows converted       : {report['news']['rows_converted']}")

    print()
    if not args.apply:
        print("DRY RUN: nothing was written. Re-run with --apply to integrate.")
    else:
        print("APPLIED: imports are idempotent; re-running changes nothing.")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"report written       : {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
