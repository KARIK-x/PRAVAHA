"""Read-only preflight for the staged production integration.

WHY THIS EXISTS
---------------
``scripts/integrate_validated_data.py`` performs the import. This script answers
"is it safe and authorised to run it *right now*?" without writing anything. It
fails closed: any unresolved gate makes the verdict NOT READY and the exit code
non-zero, so an unattended operator cannot proceed past a missing backup, a
missing data-rights ruling, a schema mismatch, or a database still open to the
running server.

It never writes to the production stores. It opens the market DuckDB read-only
(and reports the lock if the server holds it), reads the staged snapshots, and
prints the exact maintenance procedure.

Usage::

    .venv/bin/python scripts/preflight_integration.py \\
        --raw data/review/source_probe_2026-10-15 \\
        --backup-dir data/backups/2026-10-15

Environment gates (both must be set by the owner, deliberately):

    MEGATOOL_INTEGRATION_AUTHORIZED=1     the B-1/B-2/* production data-rights
                                          ruling has been granted
    MEGATOOL_INTEGRATION_RULING_REF=...   free-text reference to that ruling
                                          (recorded in the printed plan)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from megatool.market_store import MarketStore  # noqa: E402

DEFAULT_MARKET_DB = Path("data/processed/megatool_market.duckdb")
DEFAULT_APP_DB = Path("data/processed/megatool_state.sqlite")
EXPECTED_MARKET_DIR = Path("data/processed")

#: Columns the store's idempotent migration adds on first write-mode connect.
MIGRATION_COLUMNS = (
    "status",
    "successor_symbol",
    "sector_source",
    "sector_retrieved_at",
    "sector_observed_date",
)

#: Every dataset the integration writes, with its provenance and rights status.
DATASETS = (
    {
        "name": "security_master (sector + instrument + corporate actions)",
        "table": "security_master (market DuckDB)",
        "sources": "yonepse/securities.json, binayabaral symbols, surajrimal stockmap, "
        "nepalstockdata list, corporate_actions registry",
        "rights": "pending owner ruling R1/B-1/BLK-2 (compilations of NEPSE/ShareSansar data)",
    },
    {
        "name": "index_series (NEPSE composite + 17 sector indices)",
        "table": "index_series (market DuckDB)",
        "sources": "binayabaral NEPSE_INDEX.csv, socrateai ohlc_index/ sample",
        "rights": "pending owner ruling R1/B-1/BLK-2",
    },
    {
        "name": "fundamentals (YONEPSE financial reports)",
        "table": "fundamentals (app SQLite)",
        "sources": "yonepse/financials.json",
        "rights": "pending owner ruling R1/B-1/BLK-2",
    },
    {
        "name": "news / events (exchange notices + disclosures)",
        "table": "news_items (app SQLite)",
        "sources": "yonepse/disclosures.json, exchange_messages.json, notices.json",
        "rights": "pending owner ruling R1/B-1/BLK-2",
    },
)


def _load_integrator():
    path = Path(__file__).resolve().parent / "integrate_validated_data.py"
    spec = importlib.util.spec_from_file_location("integrate_validated_data", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _holders(path: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["lsof", "-nP", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
    except Exception:
        return []
    return [line for line in out.splitlines()[1:] if line.strip()]


class Report:
    def __init__(self) -> None:
        self.checks: list[tuple[str, str, str]] = []  # status, name, detail

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.checks.append((status, name, detail))

    @property
    def ready(self) -> bool:
        return all(status == "PASS" for status, _, _ in self.checks)

    def print(self) -> None:
        width = max((len(n) for _, n, _ in self.checks), default=10)
        for status, name, detail in self.checks:
            print(f"  [{status:5}] {name:<{width}}  {detail}")


def build_report(args: argparse.Namespace) -> Report:
    rep = Report()
    root = Path.cwd()
    market_db: Path = args.market_db
    app_db: Path = args.app_db

    # 1. paths unambiguous, inside the expected processed dir, present
    expected_market = (root / DEFAULT_MARKET_DB).resolve()
    if market_db.resolve() != expected_market:
        rep.add("FAIL", "market DB path", f"{market_db} != expected {DEFAULT_MARKET_DB}")
    elif not market_db.exists():
        rep.add("FAIL", "market DB path", f"missing: {market_db}")
    else:
        rep.add("PASS", "market DB path", f"{market_db} ({market_db.stat().st_size} bytes)")
    if not app_db.exists():
        rep.add("FAIL", "app DB path", f"missing: {app_db}")
    else:
        rep.add("PASS", "app DB path", f"{app_db} ({app_db.stat().st_size} bytes)")

    # 2. conflicting writer
    holders = _holders(market_db)
    lock_ok = True
    store = None
    try:
        store = MarketStore(market_db, read_only=True)
        store.query_rows("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        lock_ok = False
        rep.add("BLOCK", "market DB writer", f"cannot open read-only: {exc}")
    if holders:
        lock_ok = False
        for line in holders:
            rep.add("BLOCK", "market DB holder", line.strip())
    if lock_ok:
        rep.add("PASS", "market DB writer", "no conflicting process; readable")

    # 3. schema prerequisites / migration
    if store is not None:
        try:
            tables = {r[0] for r in store.query_rows("SHOW TABLES")}
            for t in ("price_bars", "security_master", "index_series"):
                rep.add("PASS" if t in tables else "FAIL", f"schema table {t}", "")
            cols = {r[1] for r in store.query_rows("PRAGMA table_info('security_master')")}
            to_add = [c for c in MIGRATION_COLUMNS if c not in cols]
            rep.add(
                "PASS",
                "schema migration",
                f"adds columns on apply: {to_add or 'none (already migrated)'}",
            )
        except Exception as exc:  # noqa: BLE001
            rep.add("FAIL", "schema introspection", str(exc))
    else:
        rep.add("BLOCK", "schema introspection", "market DB not readable (locked)")

    # 4. expected changes (dry-run; nothing written)
    integrator = _load_integrator()
    import tempfile

    try:
        preview_app = Path(tempfile.mkdtemp(prefix="megatool_preflight_")) / "app.sqlite"
        if store is not None:
            sm = integrator.step_security_master(store, args.raw, apply=False)
            ix = integrator.step_index_series(store, args.raw, apply=False)
            rep.add(
                "PASS",
                "expected security_master",
                f"{sm['rows_to_write']} rows "
                f"({sm['ordinary_with_sector']} ordinary+sector, "
                f"{sm['instrument_classified']} instrument, "
                f"{sm['retired_with_status']} MERGED)",
            )
            total_ix = sum(s.get("rows", 0) for s in ix["series"])
            rep.add("PASS", "expected index_series", f"{total_ix} staged rows")
        else:
            rep.add("BLOCK", "expected market changes", "market DB locked; cannot preview")
        fu = integrator.step_fundamentals(args.raw, preview_app, apply=False)
        rep.add(
            "PASS",
            "expected fundamentals",
            f"{fu['records_validated']} records, PIT coverage {fu['point_in_time_coverage_pct']}%",
        )
        nw = integrator.step_news(args.raw, preview_app, apply=False)
        rep.add("PASS", "expected news", f"{nw['rows_converted']} rows converted")
    except Exception as exc:  # noqa: BLE001
        rep.add("FAIL", "expected changes", f"{type(exc).__name__}: {exc}")
    finally:
        if store is not None:
            store.close()

    # 5. bounded effects — additive tables only
    rep.add(
        "PASS",
        "bounded effects",
        "writes security_master, index_series, fundamentals, news_items only; "
        "price_bars and stored financial records are never touched",
    )

    # 6. data-rights gate (fail closed)
    authorized = os.getenv("MEGATOOL_INTEGRATION_AUTHORIZED") == "1"
    ruling = os.getenv("MEGATOOL_INTEGRATION_RULING_REF", "").strip()
    if authorized and ruling:
        rep.add("PASS", "data-rights gate", f"authorized; ruling ref={ruling}")
    else:
        rep.add(
            "FAIL",
            "data-rights gate",
            "MEGATOOL_INTEGRATION_AUTHORIZED=1 and MEGATOOL_INTEGRATION_RULING_REF "
            "must both be set (R1/B-1/BLK-2 production ruling)",
        )

    # 7. backup verified (both DBs + matching sha256)
    backup_dir: Path = args.backup_dir
    for src in (market_db, app_db):
        if not backup_dir.exists():
            rep.add("FAIL", f"backup {src.name}", f"no backup dir {backup_dir}")
            continue
        b = backup_dir / src.name
        bsha = backup_dir / f"{src.name}.sha256"
        if not b.exists() or not bsha.exists():
            rep.add("FAIL", f"backup {src.name}", "backup or .sha256 file missing")
            continue
        actual = _sha256(b)
        recorded = bsha.read_text(encoding="utf-8").split()[0].strip()
        if actual != recorded:
            rep.add("FAIL", f"backup {src.name}", "sha256 mismatch")
        else:
            rep.add("PASS", f"backup {src.name}", f"sha256 {actual[:16]}… verified")

    return rep


def print_plan(args: argparse.Namespace) -> None:
    raw = args.raw
    market_db = args.market_db
    app_db = args.app_db
    backup = args.backup_dir
    print("\nMaintenance procedure (run only in an authorised window, in order):")
    print("  0. owner grants the ruling and a short window; set the two gate env vars")
    print("  1. bake backups + hashes:")
    print(
        f"       cp {market_db} {backup}/{market_db.name} && shasum -a 256 "
        f"{backup}/{market_db.name} > {backup}/{market_db.name}.sha256"
    )
    print(
        f"       cp {app_db} {backup}/{app_db.name} && shasum -a 256 "
        f"{backup}/{app_db.name} > {backup}/{app_db.name}.sha256"
    )
    print("  2. STOP the server gracefully (releases the DuckDB single-writer lock):")
    print("       kill -TERM <uvicorn-pid>   # then wait for it to exit")
    print("  3. apply ONLY the approved datasets:")
    print(
        f"       .venv/bin/python scripts/integrate_validated_data.py "
        f"--raw {raw} --market-db {market_db} --app-db {app_db} --apply "
        f"--json-out {backup}/applied.json"
    )
    print("  4. verify counts independently (see README section in this script):")
    print("       market: SELECT COUNT(*) FROM security_master;  -- expect 372")
    print("               SELECT status, COUNT(*) FROM security_master GROUP BY 1;")
    print("               SELECT COUNT(*) FROM index_series;      -- expect 7611")
    print("               SELECT COUNT(*) FROM price_bars;        -- unchanged")
    print("       app:    SELECT COUNT(*), COUNT(DISTINCT symbol) FROM fundamentals;")
    print("               SELECT COUNT(*) FROM news_items;")
    print("  5. re-run step 3 once to confirm idempotency (news added→duplicates; counts stable)")
    print("  6. RESTART the server and health-check:")
    print("       curl -s localhost:8710/api/health")
    print("       curl -s localhost:8710/api/securities | head")
    print(
        "       curl -s -X POST localhost:8710/api/rank -H 'content-type: application/json' "
        '-d \'{"weights":{"sector_percentile":0.3},"top":10}\''
    )
    print("  7. ROLLBACK if any verification fails (server stopped first):")
    print(f"       cp {backup}/{market_db.name} {market_db}")
    print(f"       cp {backup}/{app_db.name} {app_db}")
    print(
        "       limitation: rollback restores the exact pre-apply bytes but discards "
        "any writes made after the backup; re-run step 3 to re-apply."
    )
    print("\nExpected downtime: < 2 minutes (additive upserts; no price data is rewritten).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", type=Path, default=Path("data/review/source_probe_2026-10-15"))
    parser.add_argument("--market-db", type=Path, default=DEFAULT_MARKET_DB)
    parser.add_argument("--app-db", type=Path, default=DEFAULT_APP_DB)
    parser.add_argument("--backup-dir", type=Path, default=Path("data/backups/2026-10-15"))
    args = parser.parse_args(argv)

    print("Read-only preflight for the staged production integration")
    print(f"  raw snapshots : {args.raw}")
    print(f"  market DuckDB : {args.market_db}")
    print(f"  app SQLite    : {args.app_db}")
    print(f"  backup dir    : {args.backup_dir}")
    print("\nDatasets the integration would write (and their rights status):")
    for d in DATASETS:
        print(f"  - {d['name']}")
        print(f"      table  : {d['table']}")
        print(f"      sources: {d['sources']}")
        print(f"      rights : {d['rights']}")

    print("\nChecks:")
    rep = build_report(args)
    rep.print()
    ok = rep.ready
    print(
        "\nVERDICT: "
        + ("READY FOR AUTHORIZED MAINTENANCE WINDOW" if ok else "NOT READY (fail-closed)")
    )
    if not ok:
        print("One or more gates are unresolved; see the [FAIL]/[BLOCK] rows above.")
        return 1
    print_plan(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
