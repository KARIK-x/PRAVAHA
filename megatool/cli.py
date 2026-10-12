"""Command-line interface.

megatool init        create the local databases
megatool fetch       download the public NEPSE dataset into the store
megatool import FILE import a local CSV/Parquet file
megatool status      show data coverage and freshness
megatool screen      run a saved screen from the command line
megatool serve       start the web terminal
megatool probe       check which data sources are reachable right now
megatool floor       import / summarise a NEPSE floor sheet (import-based)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from megatool import DISCLAIMER, __version__


def _cmd_init(args: argparse.Namespace) -> int:
    from megatool.config import PATHS, ensure_dirs
    from megatool.db import init_app_db
    from megatool.market_store import MarketStore

    ensure_dirs()
    ver = init_app_db()
    try:
        with MarketStore() as store:
            store.bar_count()
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        # The common case: the server is running and holds the DuckDB lock.
        print(f"Mega Tool {__version__} initialised (app state only).")
        print(f"  app state (SQLite) : {PATHS.app_db}")
        print(f"  schema version      : {ver}")
        print()
        print("The market database could not be opened:")
        print(f"  {exc}")
        print()
        print("This is expected while `megatool serve` is running: DuckDB allows")
        print("one writer. Stop the server, then run `megatool init` again if you")
        print("want to confirm the market store. The app state above is ready.")
        return 1
    print(f"Mega Tool {__version__} initialised.")
    print(f"  app state (SQLite) : {PATHS.app_db}")
    print(f"  market data (DuckDB): {PATHS.market_db}")
    print(f"  schema version      : {ver}")
    return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    from megatool.datasources.nepse_data_repo import NepseDataRepoAdapter
    from megatool.ingest import ingest
    from megatool.market_store import MarketStore

    adapter = NepseDataRepoAdapter(cache_ttl_hours=args.cache_ttl_hours)

    def progress(symbol: str, i: int, total: int) -> None:
        if args.quiet:
            return
        if i == 1 or i % 10 == 0 or i == total:
            print(f"  [{i}/{total}] {symbol}", flush=True)

    print("Fetching the public NEPSE dataset (community-maintained GitHub copy)...")
    print("Note: this is NOT the exchange's own feed. See docs/DATA_SOURCES.md.\n")

    with MarketStore() as store:
        result = ingest(
            adapter,
            symbols=_resolve_symbols(args, adapter),
            store=store,
            progress=progress,
        )

    print(f"\nSource      : {result.source.value}")
    print(f"Status      : {'OK' if result.ok else 'COMPLETED WITH ERRORS'}")
    print(
        f"Symbols     : {result.symbols_succeeded}/{result.symbols_requested} succeeded"
        + (f", {result.symbols_failed} failed" if result.symbols_failed else "")
    )
    print(
        f"Rows        : {result.rows_read} read, {result.rows_inserted} new, "
        f"{result.rows_updated} refreshed, {result.rows_flagged} flagged"
    )
    if result.coverage_start:
        print(f"Coverage    : {result.coverage_start} -> {result.coverage_end}")
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for e in result.errors[:15]:
            print(f"  - {e}")
    return 0 if result.symbols_succeeded else 1


def _resolve_symbols(args: argparse.Namespace, adapter) -> list[str] | None:
    if getattr(args, "symbols", None):
        return [s.upper().strip() for s in args.symbols.split(",") if s.strip()]
    if getattr(args, "limit", None):
        return adapter.list_symbols()[: args.limit]
    return None


def _cmd_import(args: argparse.Namespace) -> int:
    from megatool.ingest import ingest_local_csv
    from megatool.market_store import MarketStore

    path = Path(args.file)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2

    with MarketStore() as store:
        result = ingest_local_csv(path, symbol=args.symbol, store=store)

    print(f"Imported {path.name}")
    print(f"  source   : {result.source.value} (explicitly labelled local import)")
    print(f"  symbols  : {result.symbols_succeeded}/{result.symbols_requested}")
    print(
        f"  rows     : {result.rows_inserted} new, {result.rows_updated} refreshed, "
        f"{result.rows_flagged} flagged"
    )
    if result.errors:
        for e in result.errors[:10]:
            print(f"  ! {e}", file=sys.stderr)
    return 0 if result.symbols_succeeded else 1


def _cmd_status(args: argparse.Namespace) -> int:
    from megatool.db import get_conn, init_app_db
    from megatool.market_store import MarketStore

    init_app_db()
    with MarketStore(read_only=False) as store:
        cov = store.global_coverage()
    print(f"Mega Tool {__version__} - data status")
    print(f"  symbols stored : {cov.get('symbols', 0)}")
    print(f"  bars stored    : {cov.get('bars', 0)}")
    print(f"  first bar      : {cov.get('first_date')}")
    print(f"  latest bar     : {cov.get('last_date')}   <- the data is as fresh as this date")
    print(f"  last retrieved : {cov.get('last_retrieved')}")
    print("\n  Live NEPSE feed: NOT CONNECTED (official API requires an authenticated session).")

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT source, status, finished_at, symbols_succeeded, rows_inserted "
            "FROM ingestion_log ORDER BY id DESC LIMIT 5"
        ).fetchall()
    if rows:
        print("\n  Recent ingestion runs:")
        for r in rows:
            print(
                f"    {r['finished_at']}  {r['source']:<40} {r['status']:<8} "
                f"{r['symbols_succeeded']} symbols, {r['rows_inserted']} new rows"
            )
    return 0


def _cmd_screen(args: argparse.Namespace) -> int:
    from megatool.market_store import MarketStore
    from megatool.scanner import PRESET_SCREENS, ScreenNode, run_screen

    if args.preset not in PRESET_SCREENS:
        print(
            f"unknown preset {args.preset!r}. Available: {', '.join(PRESET_SCREENS)}",
            file=sys.stderr,
        )
        return 2

    preset = PRESET_SCREENS[args.preset]
    node = ScreenNode.from_dict(preset["tree"])
    with MarketStore(read_only=True) as store:
        results = run_screen(store, node)

    passed = [r for r in results if r.passed]
    ineligible = [r for r in results if not r.eligible]
    print(f"Screen: {preset['name']}")
    print(f"  {preset['description']}\n")
    print(f"  Condition: {node.render()}")
    print(
        f"  Evaluated {len(results)} securities "
        f"({len(ineligible)} ineligible for insufficient data)\n"
    )

    if not passed:
        print("  No securities passed.")
    else:
        print(f"  {'SYMBOL':<10} {'AS OF':<12} WHY")
        for r in passed:
            print(f"  {r.symbol:<10} {str(r.last_date):<12} {'; '.join(r.reasons)}")
    print(
        f"\n  {len(passed)} passed. A screen result describes historical conditions "
        "only and is not a recommendation."
    )
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    from megatool.datasources.nepalstock_official import NepalStockOfficialAdapter
    from megatool.datasources.nepse_data_repo import NepseDataRepoAdapter

    print("Probing data sources (bounded, one request each)...\n")

    repo = NepseDataRepoAdapter()
    try:
        syms = repo.list_symbols()
        print(f"[AVAILABLE] {repo.config.label}")
        print(f"            {len(syms)} symbols listed. {repo.config.terms_note}")
    except Exception as exc:
        print(f"[UNAVAILABLE] {repo.config.label}: {exc}")

    print()
    official = NepalStockOfficialAdapter()
    probe = official.probe()
    print(f"[{'BLOCKED' if probe.get('blocked') else 'UNEXPECTED'}] {official.config.label}")
    print(f"            probed {probe.get('url')} -> HTTP {probe.get('http_status')}")
    print(f"            {probe.get('conclusion')}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from megatool.config import HOST, PORT

    host, port = args.host or HOST, args.port or PORT
    print(f"Mega Tool starting on http://{host}:{port}")
    print("  Press Ctrl-C to stop.\n")
    print(DISCLAIMER)
    print()
    uvicorn.run("megatool.api:app", host=host, port=port, log_level=args.log_level)
    return 0


def _print_indented(label: str, value: object, width: int = 22) -> None:
    print(f"  {label:<{width}} {value}")


def _cmd_floor_import(args: argparse.Namespace) -> int:
    from megatool.floorsheet import FloorSheetError, import_floorsheet

    path = Path(args.file)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        out = import_floorsheet(text, args.date, source=args.source or path.name)
    except FloorSheetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Floor sheet for {out['traded_at']} ({path.name})")
    _print_indented("rows in file:", out["rows_total"])
    _print_indented("trades stored:", out["rows_imported"])
    _print_indented("rows skipped:", out["rows_skipped"])
    if out["already_imported"]:
        print("\nThis exact file was already imported for this session; nothing was added.")
    for warning in out["warnings"][:10]:
        print(f"  warning: {warning}")
    for row in out["skipped"][:10]:
        print(f"  skipped line {row['line']}: {row['reason']}")
    if out["warnings"] or out["skipped"]:
        print("\nSkipped rows are reported above rather than dropped silently,")
        print("because a silently dropped row would make every total wrong.")
    return 0


def _cmd_floor_summary(args: argparse.Namespace) -> int:
    from megatool.floorsheet import list_sessions, summary

    if args.sessions:
        rows = list_sessions()
        if not rows:
            print("No floor sheet has been imported.")
            print("Import one with: megatool floor import FILE --date YYYY-MM-DD")
            return 0
        print(f"{'DATE':<14} {'PRINTS':>8} {'SYMBOLS':>8} {'AMOUNT':>16}  SOURCE")
        for row in rows:
            print(
                f"{row['traded_at']:<14} {row['prints']:>8} {row['symbols']:>8} "
                f"{row['amount']:>16,.2f}  {row['source']}"
            )
        return 0

    data = summary(traded_at=args.date, symbol=args.symbol, top=args.top)
    totals = data["totals"]
    if totals["trades"] == 0:
        print("No floor sheet has been imported.")
        print("Import one with: megatool floor import FILE --date YYYY-MM-DD")
        for warning in data["warnings"]:
            print(f"\n{warning}")
        return 0

    scope = args.date or f"{totals['sessions']} imported session(s)"
    if args.symbol:
        scope = f"{scope}, symbol {args.symbol.upper()}"
    print(f"Floor-sheet summary ({scope})")
    _print_indented("trades:", f"{totals['trades']:,}")
    _print_indented("symbols:", totals["symbols"])
    _print_indented("quantity:", f"{totals['quantity']:,}")
    _print_indented("amount:", f"NPR {totals['amount']:,.2f}")

    if data["top_buyers"]:
        print("\nTop buyers (by quantity):")
        for row in data["top_buyers"]:
            print(
                f"  {row['buyer']:<12} {row['quantity']:>12,}  "
                f"{row['share_of_quantity_pct']:>7.2f}%  NPR {row['amount']:>16,.2f}"
            )
    if data["top_sellers"]:
        print("\nTop sellers (by quantity):")
        for row in data["top_sellers"]:
            print(
                f"  {row['seller']:<12} {row['quantity']:>12,}  "
                f"{row['share_of_quantity_pct']:>7.2f}%  NPR {row['amount']:>16,.2f}"
            )
    if data["top_symbols"]:
        print("\nMost traded symbols (by amount):")
        for row in data["top_symbols"]:
            print(
                f"  {row['symbol']:<12} {row['prints']:>6} prints  "
                f"NPR {row['amount']:>16,.2f}  "
                f"{row['distinct_buyers']} buyer(s) / {row['distinct_sellers']} seller(s)"
            )

    conc = data["concentration"]
    print("\nConcentration (broker CODES, not beneficial owners):")
    _print_indented("unique buyers:", conc["unique_buyers"])
    _print_indented("unique sellers:", conc["unique_sellers"])
    _print_indented("buyer HHI:", conc["buyer_hhi"])
    _print_indented("seller HHI:", conc["seller_hhi"])

    for warning in data["warnings"]:
        print(f"\nWARNING: {warning}")
    print("\nWhat these numbers are not:")
    for limit in data["limits"]:
        print(f"  - {limit}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="megatool",
        description="Mega Tool - local NEPSE research terminal. " + DISCLAIMER,
    )
    p.add_argument("--version", action="version", version=f"megatool {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the local databases").set_defaults(func=_cmd_init)

    f = sub.add_parser("fetch", help="download the public NEPSE dataset")
    f.add_argument("--symbols", help="comma-separated symbols (default: all)")
    f.add_argument("--limit", type=int, help="fetch only the first N symbols")
    f.add_argument(
        "--cache-ttl-hours",
        type=float,
        default=12.0,
        help="reuse cached downloads younger than this (default 12)",
    )
    f.add_argument("--quiet", action="store_true")
    f.set_defaults(func=_cmd_fetch)

    i = sub.add_parser("import", help="import a local CSV/Parquet file")
    i.add_argument("file")
    i.add_argument("--symbol", help="symbol for a single-symbol file")
    i.set_defaults(func=_cmd_import)

    sub.add_parser("status", help="show data coverage and freshness").set_defaults(func=_cmd_status)

    s = sub.add_parser("screen", help="run a saved screen")
    s.add_argument(
        "preset",
        help="one of: "
        + ", ".join(["oversold_rsi", "volume_surge", "near_52w_high", "above_sma50"]),
    )
    s.set_defaults(func=_cmd_screen)

    sub.add_parser("probe", help="check which data sources are reachable").set_defaults(
        func=_cmd_probe
    )

    v = sub.add_parser("serve", help="start the web terminal")
    v.add_argument("--host")
    v.add_argument("--port", type=int)
    v.add_argument("--log-level", default="warning")
    v.set_defaults(func=_cmd_serve)

    fl = sub.add_parser(
        "floor",
        help="import and analyse a NEPSE floor sheet (there is no floor-sheet "
        "API, so this is import-based by design)",
    )
    flsub = fl.add_subparsers(dest="floor_command", required=True)

    fli = flsub.add_parser("import", help="import one session's floor-sheet CSV")
    fli.add_argument("file", help="path to the CSV as published")
    fli.add_argument("--date", required=True, help="the session date, YYYY-MM-DD")
    fli.add_argument("--source", help="where the file came from (default: its filename)")
    fli.set_defaults(func=_cmd_floor_import)

    fls = flsub.add_parser("summary", help="concentration and counterparty analysis")
    fls.add_argument("--date", help="restrict to one session, YYYY-MM-DD")
    fls.add_argument("--symbol", help="restrict to one symbol")
    fls.add_argument("--top", type=int, default=10, help="rows per table (default 10)")
    fls.add_argument("--sessions", action="store_true", help="list imported sessions instead")
    fls.set_defaults(func=_cmd_floor_summary)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrupted.")
        return 130
    except ValueError as exc:
        # Bad input (an unreadable file, an unknown preset, an invalid filter
        # tree) must read as a message, never as a traceback.
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
