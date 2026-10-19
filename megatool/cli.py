"""Command-line interface.

megatool init        create the local databases
megatool fetch       download the public NEPSE dataset into the store
megatool import FILE import a local CSV/Parquet file
megatool status      show data coverage and freshness
megatool screen      run a saved screen from the command line
megatool serve       start the web terminal
megatool probe       check which data sources are reachable right now
megatool floor       import / summarise a NEPSE floor sheet (import-based)
megatool collector   capture / inspect the published NEPSE market datasets
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from megatool import DISCLAIMER, __version__

#: Default collector poll interval, seconds. The upstream market files publish
#: on a roughly-hourly cadence; polling faster than a minute adds nothing.
DEFAULT_POLL_INTERVAL_CLI = 900


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

    # A FULL fetch (no --symbols / --limit) marks the deployment seed complete,
    # so the runtime auto-seed on a hosted host does not download it a second
    # time. A partial fetch must NOT set the marker.
    if result.symbols_succeeded and not getattr(args, "symbols", None) and not getattr(args, "limit", None):
        try:
            from megatool.deploy_seed import mark_seed_complete

            mark_seed_complete()
        except Exception as exc:  # noqa: BLE001 - a marker write must not fail the fetch
            print(f"NOTE: could not record seed completion: {exc}")

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


def _cmd_ingest_index_ohlc(args: argparse.Namespace) -> int:
    from megatool.config import PATHS
    from megatool.index_ohlc_ingest import ingest_index_ohlc, IngestError

    csv_path = getattr(args, "file", None)
    if not csv_path:
        csv_path = "data/staging/socrateai_nepse_index/nepse_index_ohlc.csv"

    db_path = getattr(args, "db", None)
    dry_run = getattr(args, "dry_run", False)
    source = getattr(args, "source", "socrateai-official/nepse-open-data")
    index_name = getattr(args, "index", "NEPSE")

    print("Ingesting historical NEPSE index OHLC data...")
    print(f"  Source file : {csv_path}")
    print(f"  Database    : {db_path or PATHS.app_db}")
    print(f"  Dry run     : {dry_run}")
    print()

    try:
        result = ingest_index_ohlc(
            csv_path,
            db_path=db_path,
            source=source,
            dry_run=dry_run,
            index_name=index_name,
        )
    except IngestError as exc:
        print(f"ERROR: {exc}")
        return 1

    d = result.as_dict()
    print(f"Discovered  : {d['discovered']} rows")
    print(f"Inserted    : {d['inserted']} new rows")
    print(f"Updated     : {d['updated']} existing rows")
    print(f"Skipped     : {d['skipped']} duplicate rows")
    print(f"Rejected    : {d['rejected']} invalid rows")
    print()
    print(f"Genuine OHLC : {d['genuine']}")
    print(f"Placeholder  : {d['placeholder']} (close-only, O=H=L=C)")
    print(f"Invalid      : {d['invalid']} (OHLC inconsistent)")
    print(f"With turnover: {d['with_turnover']} (market-wide NPR turnover, NOT share volume)")
    if d["first_date"]:
        print(f"Date range   : {d['first_date']} -> {d['last_date']}")
    print()
    print("Source attribution: " + d["source"])
    print("License: MIT (socrateai-official/nepse-open-data)")
    print("NOTE: Volume field is market-wide turnover in NPR, NOT share volume.")
    if dry_run:
        print("\nDRY RUN - no data was written.")
    return 0


def _cmd_import_sectors(args: argparse.Namespace) -> int:
    from megatool.config import PATHS
    from megatool.sectors import import_sectors, SectorError

    csv_path = getattr(args, "file", None)
    if not csv_path:
        print("ERROR: --file is required")
        return 1

    db_path = getattr(args, "db", None)
    source = getattr(args, "source", None)

    print("Importing sector classifications...")
    print(f"  Source file : {csv_path}")
    print(f"  Database    : {db_path or PATHS.market_db}")
    print()

    try:
        with open(csv_path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"ERROR: Source file not found: {csv_path}")
        return 1

    if source is None:
        source = "owner-supplied CSV"

    try:
        from megatool.market_store import MarketStore
        store = MarketStore(db_path) if db_path else MarketStore()
        report = import_sectors(text, source=source, store=store)
        store.close()
    except SectorError as exc:
        print(f"ERROR: {exc}")
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Rows in file    : {report['rows_in_file']}")
    print(f"Classified      : {report['classified']}")
    print(f"Assigned        : {report['assigned']}")
    print(f"Duplicates      : {report['duplicates']}")
    print(f"Skipped         : {len(report['skipped'])}")
    print(f"Ambiguous       : {len(report['ambiguous'])}")
    print(f"Unknown symbols : {len(report['unknown_symbols'])}")
    if report['ambiguous']:
        print(f"  Ambiguous: {report['ambiguous'][:10]}")
    if report['unknown_symbols']:
        print(f"  Unknown (first 10): {report['unknown_symbols'][:10]}")
    if report['skipped']:
        print(f"  Skipped (first 5): {report['skipped'][:5]}")
    print()
    print("Source attribution: " + report['source'])
    print("NOTE: Sector data from owner-supplied CSV. Unresolved classifications remain NULL.")
    return 0


def _cmd_fetch_index(args: argparse.Namespace) -> int:
    """Fetch the published NEPSE composite index into ``index_series`` and the
    index OHLC history the charting view reads.

    Source: ``binayabaral/nepal-market-data`` ``data/nepse/NEPSE_INDEX.csv`` — a
    single openly published file carrying the official composite OHLC from 1997.
    Plain HTTPS, no authentication.
    """
    from megatool.deploy_seed import seed_index
    from megatool.market_store import MarketStore

    print("Fetching the published NEPSE composite index (binayabaral/nepal-market-data)...")
    try:
        with MarketStore() as store:
            out = seed_index(store)
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        print(f"ERROR: could not fetch the NEPSE index: {exc}")
        return 1

    print(f"Rows written  : {out['rows_written']}")
    print(f"Coverage      : {out['coverage_start']} -> {out['coverage_end']}")
    print(
        f"Index OHLC    : {out['genuine_ohlc']} genuine, {out['close_only']} close-only"
    )
    print("Source        : binayabaral/nepal-market-data (published composite, not a live feed)")
    return 0


def _cmd_fetch_sectors(args: argparse.Namespace) -> int:
    """Fetch sector classifications from the public YONEPSE securities snapshot.

    Source: ``shubhamnpk/yonepse`` ``data/other/securities.json`` — one public
    JSON file with each symbol's ``sectorName``. No authentication.
    """
    from megatool.deploy_seed import seed_sectors
    from megatool.market_store import MarketStore

    print("Fetching sector classifications (shubhamnpk/yonepse securities snapshot)...")
    try:
        with MarketStore() as store:
            out = seed_sectors(store)
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        print(f"ERROR: could not fetch sectors: {exc}")
        return 1

    print(f"Classified      : {out['classified']}")
    print(f"Assigned        : {out['assigned']}")
    print("Source          : yonepse/securities.json")
    return 0


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


def _cmd_walk_forward(args: argparse.Namespace) -> int:
    import json

    from megatool.market_store import MarketStore
    from megatool.walkforward import WalkForwardConfig, walk_forward

    config = WalkForwardConfig(
        frequency=args.frequency,
        start=args.start,
        end=args.end,
        top_quantile=args.top_quantile,
        min_bars=args.min_bars,
        permutations=args.permutations,
    )
    problems = config.validate()
    if problems:
        print("; ".join(problems), file=sys.stderr)
        return 2

    with MarketStore(read_only=True) as store:
        frames = {}
        for symbol in store.symbols(min_bars=1):
            df = store.get_bars(symbol)
            if not df.empty:
                frames[symbol] = df

    if not frames:
        print("no stored history to validate", file=sys.stderr)
        return 1

    result = walk_forward(frames, config)
    payload = result.to_dict()

    s = payload["summary"]
    cb = payload["chance_baseline"]
    print(f"Walk-forward validation of the ranking — {config.frequency_label}")
    print(f"  window      : {args.start or 'start of data'} .. {args.end or 'end of data'}")
    print(f"  periods     : {s['periods_used']} used, {s['periods_skipped']} skipped")

    def pct(v):
        return "n/a" if v is None else f"{v * 100:.3f}%"

    print(f"  mean spread : {pct(s['mean_spread'])}   (top quantile - bottom quantile)")
    print(f"  hit rate    : {pct(s['hit_rate'])}")
    print(f"  cum long    : {pct(s['cumulative_long'])}")
    print(f"  cum bench   : {pct(s['cumulative_benchmark'])}")
    print(f"  chance p95  : {pct(cb['p95_spread'])}")
    print(f"  percentile  : {cb['observed_percentile']}")
    print(f"  beats chance: {cb['beats_chance']}")
    print()
    print("Caveats — these numbers are optimistic and are not advice:")
    for c in payload["caveats"]:
        print(f"  - {c}")

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nfull detail written to {args.json_out}")
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


def _print_collector_report(report: dict) -> int:
    """Print one collection report honestly: freshness is stated, never implied."""

    run_id = report["run_id"]
    print(f"collector run {run_id}: {report['status'].upper()}")
    print(f"  started  : {report['started_at']}  (retrieval clock, UTC)")
    print(f"  finished : {report['finished_at']}")
    if report["origin"]:
        print(f"  origin   : {report['origin']}")
    open_state = {None: "unknown", 1: "open", 0: "closed"}[report["is_open"]]
    print(f"  market   : {open_state} (as the upstream status.json states it)")
    print(f"  observed : {report['observed_at'] or 'no stamp anywhere in this snapshot'}")
    if report["observed_age_seconds"] is not None:
        print(
            f"  age      : {report['observed_age_seconds']:,.0f} s -> {report['freshness'].upper()}"
        )
    else:
        print("  age      : unknown (no publisher timestamp)")
    if report["business_date"]:
        print(f"  session  : {report['business_date']} (cross-checked below)")
        print(f"  evidence : {report['business_date_evidence']}")
    else:
        print(f"  session  : undetermined ({report['business_date_evidence']})")
    counts = report.get("dataset_counts") or {}
    datasets = report.get("datasets") or []
    if datasets:
        print()
        print(
            f"  {'dataset':<18} {'status':<18} {'rows':>5} {'ok':>5} {'flag':>5} {'dupl':>5} {'rej':>4}  freshness"
        )
        for ds in datasets:
            c = (
                ds["counts"]
                if "counts" in ds
                else {
                    "read": ds["rows_read"],
                    "valid": ds["rows_valid"],
                    "flagged": ds["rows_flagged"],
                    "duplicate": ds["rows_duplicate"],
                    "rejected": ds["rows_rejected"],
                }
            )
            print(
                f"  {ds['dataset']:<18} {ds['status']:<18} {c['read']:>5} "
                f"{c['valid']:>5} {c['flagged']:>5} {c['duplicate']:>5} {c['rejected']:>4}  "
                f"{ds['freshness']}"
            )
            if ds.get("error"):
                print(f"      error: {ds['error']}")
            if ds.get("notes"):
                print(f"      note : {ds['notes']}")
    else:
        for name, c in (counts or {}).items():
            print(f"      {name}: {c}")
    return 0


def _cmd_collector_snapshot(args: argparse.Namespace) -> int:
    from pathlib import Path as _Path

    from megatool.collector import collect_snapshot
    from megatool.db import init_app_db

    db_path = _Path(args.db) if args.db else None
    init_app_db(db_path)
    out_dir = _Path(args.out) if args.out else None
    try:
        report = collect_snapshot(
            db_path=db_path,
            out_dir=out_dir,
            timeout=args.timeout,
        )
    except Exception as exc:  # noqa: BLE001 - the CLI reports, it never hides
        print(f"collector snapshot failed: {exc}", file=sys.stderr)
        return 1
    if out_dir is not None:
        print(f"JSON snapshots written to {out_dir.resolve()}")
    return _print_collector_report(report)


def _cmd_collector_loop(args: argparse.Namespace) -> int:
    import signal
    from pathlib import Path as _Path

    from megatool.collector import collect_loop
    from megatool.db import init_app_db

    init_app_db(_Path(args.db) if args.db else None)
    stop = {"flag": False}
    previous = signal.getsignal(signal.SIGINT)

    def _stop(signum, frame):  # noqa: ARG001 - signal handler signature
        stop["flag"] = True
        print("\nstopping after the current cycle finishes...", file=sys.stderr)

    signal.signal(signal.SIGINT, _stop)
    try:
        reports = collect_loop(
            db_path=_Path(args.db) if args.db else None,
            out_dir=_Path(args.out) if args.out else None,
            interval=args.interval,
            stop_check=lambda: stop["flag"],
        )
    except KeyboardInterrupt:
        reports = []
    finally:
        signal.signal(signal.SIGINT, previous)
    for i, report in enumerate(reports, 1):
        print(f"--- cycle {i} ---")
        _print_collector_report(report)
    return 0


def _cmd_collector_status(args: argparse.Namespace) -> int:
    from pathlib import Path as _Path

    from megatool.collector import latest_report
    from megatool.db import init_app_db

    db_path = _Path(args.db) if args.db else None
    init_app_db(db_path)  # identity-safe: creates nothing but the empty schema
    report = latest_report(db_path=db_path)
    if report is None:
        print("no collector runs yet; try `megatool collector snapshot`")
        return 1
    report["run_id"] = report["id"]
    _print_collector_report(report)
    print()
    print("  recent runs:")
    for row in report["history"]:
        print(
            f"    #{row['id']:<4} {row['started_at']}  {row['status']:<8} "
            f"ok={row['datasets_ok']} degraded={row['datasets_degraded']} "
            f"failed={row['datasets_failed']} {row['freshness']}"
        )
    return 0


def _cmd_ai_status(args: argparse.Namespace) -> int:
    """Report the AI provider configuration. Makes no network call."""
    from megatool.llm import provider_status

    st = provider_status()
    print("AI provider status (no network call):")
    _print_indented("provider:", st["provider"])
    _print_indented("model:", st["model"] or "(none)")
    _print_indented("endpoint:", st.get("endpoint") or "(provider default)")
    key_txt = f"present, {st['api_key_length']} chars" if st["has_api_key"] else "absent"
    _print_indented("api key:", key_txt)  # presence + length only, never the value
    _print_indented("timeout:", f"{st['timeout_seconds']:g}s")
    _print_indented("max tokens:", st["max_tokens_default"])
    _print_indented("ready:", "yes" if st["configured"] else "no")
    for miss in st.get("missing", []):
        print(f"  missing: {miss}")
    if st.get("note"):
        print(f"\n{st['note']}")
    return 0


def _cmd_ai_ping(args: argparse.Namespace) -> int:
    """One bounded generation against the configured provider.

    Refuses when no provider is configured (no network) and requires an
    explicit ``--allow-hosted`` acknowledgement before spending hosted credit.
    """
    from megatool.llm import LLMError, get_provider, is_configured, normalise_provider

    if not is_configured():
        print("error: no AI provider is configured (or it is incomplete).", file=sys.stderr)
        print("Run `megatool ai status` for what is missing. No request was made.", file=sys.stderr)
        return 1

    provider_name = normalise_provider()
    if provider_name == "openrouter" and not args.allow_hosted:
        print("Refusing to call the hosted gateway without --allow-hosted.", file=sys.stderr)
        print(
            "A hosted request consumes API credit; re-run with --allow-hosted to confirm.",
            file=sys.stderr,
        )
        return 1
    if provider_name == "openrouter":
        print("Note: sending one request to OpenRouter; this consumes API credit.\n")

    prompt = args.prompt or "Reply with the single word: pong"
    p = get_provider()
    try:
        res = p.complete(prompt, max_tokens=args.max_tokens)
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"[{res.provider} / {res.model}] {res.elapsed_seconds:.2f}s")
    print(res.text.strip())
    if res.usage:
        _print_indented("tokens:", f"{res.prompt_tokens} in / {res.completion_tokens} out")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from megatool.config import HOST, PORT

    host, port = args.host or HOST, args.port or PORT
    # Publish the effective bind so the startup access-boundary line reports the
    # address actually being served, not the config default. Without this the
    # message read "Binding 127.0.0.1:8710" while the process listened on the
    # --port the operator passed (e.g. 10000) - a misleading log line.
    os.environ["MEGATOOL_HOST"] = host
    os.environ["MEGATOOL_PORT"] = str(port)
    print(f"Mega Tool starting on http://{host}:{port}")
    # The API has no authentication: journal entries, portfolio positions and
    # transcribed PDF records are served to whoever can reach the socket.
    # Loopback is safe by construction, so only warn when that stops being true
    # (--host 0.0.0.0 or MEGATOOL_HOST=...). A warning, not a block: a user
    # behind their own firewall or an SSH tunnel has a legitimate reason, but
    # they should be told rather than discover it later.
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "  WARNING: bound to a non-loopback address with NO authentication.\n"
            "  Anyone who can reach this address can read and edit your journal,\n"
            "  portfolio and transcribed records. Use 127.0.0.1 unless you have\n"
            "  a firewall or tunnel in front of this.\n",
            file=sys.stderr,
        )
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


def _cmd_metadata_dry_run(args: argparse.Namespace) -> int:
    """Validate a reviewed metadata CSV and report what an import would change.

    Read-only by construction: the store opens ``read_only=True`` and this
    handler writes nothing except the two new dry-run files in ``--out-dir``.
    There is no import subcommand — production writing is a separate,
    owner-approved operation that does not exist yet.
    """
    from megatool.market_store import MarketStore
    from megatool.metadata_dryrun import MetadataDryRunError, build_dry_run, write_outputs

    path = Path(args.input)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1
    db_path = Path(args.db) if args.db else None
    try:
        store = MarketStore(db_path, read_only=True)
        store.query_rows("SELECT 1")  # open now: MarketStore connects lazily,
        # and a missing or locked database must fail here as a message, not a traceback.
    except Exception as exc:  # duckdb raises when the DB is missing or locked
        print(f"error: cannot open the database read-only: {exc}", file=sys.stderr)
        print(
            "hint: the dry run never writes to the database; if the running "
            "server holds the lock, stop it or pass a copy with --db.",
            file=sys.stderr,
        )
        return 1
    try:
        try:
            result = build_dry_run(path, store)
        except MetadataDryRunError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            store.close()
        files = write_outputs(result, Path(args.out_dir))
    except MetadataDryRunError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    s = result["summary"]
    print(f"Dry run for {path.name} (sha256 {result['input']['sha256'][:16]}…)")
    _print_indented("store symbols:", result["store_symbols"])
    _print_indented("records examined:", s["records_examined"])
    _print_indented("rows rejected:", s["rows_rejected"])
    _print_indented("additions:", s["additions"])
    _print_indented("updates:", s["updates"])
    _print_indented("unchanged:", s["unchanged"])
    _print_indented("advisory:", s["advisory"])
    _print_indented("conflicting:", s["conflicting"])
    _print_indented("manual review:", s["requires_manual_review"])
    _print_indented("unknown left blank:", s["unknown_values_left_blank"])
    print()
    print(f"  json:   {files['json']}")
    print(f"  report: {files['markdown']}")
    print("Nothing was imported; importing is a separate owner-approved step.")
    return 0


def _cmd_metadata_gaps(args: argparse.Namespace) -> int:
    """Read-only report of missing/unknown security metadata."""
    from megatool.market_store import MarketStore
    from megatool.metadata_dryrun import (
        metadata_gaps,
        render_gaps_markdown,
        result_json,
    )

    db_path = Path(args.db) if args.db else None
    try:
        store = MarketStore(db_path, read_only=True)
        store.query_rows("SELECT 1")
    except Exception as exc:
        print(f"error: cannot open the database read-only: {exc}", file=sys.stderr)
        return 1

    try:
        result = metadata_gaps(store)
    finally:
        store.close()

    out_dir = Path(args.out_dir)
    stem = (Path(args.db).stem if args.db else "market").replace(".", "_")
    json_path = out_dir / f"{stem}_gaps.json"
    md_path = out_dir / f"{stem}_gaps.md"
    for target in (json_path, md_path):
        if target.exists():
            print(f"error: refusing to overwrite {target}", file=sys.stderr)
            return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(result_json(result), encoding="utf-8")
    md_path.write_text(render_gaps_markdown(result), encoding="utf-8")

    g = result["gaps"]
    print(f"Metadata gaps for {result['store_symbols']} symbols")
    _print_indented("complete records:", result["complete_records"])
    _print_indented("missing sector:", g["sector"]["count"])
    _print_indented("missing instrument_type:", g["instrument_type"]["count"])
    _print_indented("missing name:", g["name"]["count"])
    _print_indented("status unknown:", g["status_unknown"]["count"])
    _print_indented("merged without successor:", g["merged_without_successor"]["count"])
    print()
    print(f"  json:   {json_path}")
    print(f"  report: {md_path}")
    return 0


def _cmd_sources_yonepse(args: argparse.Namespace) -> int:
    """Fetch YONEPSE JSON snapshots and write loader-ready CSVs."""
    from megatool.datasources import yonepse

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        securities = yonepse.fetch_securities()
        financials = yonepse.fetch_financials()
        disclosures = yonepse.fetch_disclosures()
        exchange_messages = yonepse.fetch_exchange_messages()
        notices = yonepse.fetch_notices()
    except yonepse.YonepseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    meta_rows = yonepse.securities_to_metadata_rows(securities)
    sector_rows = yonepse.securities_to_sector_rows(securities)
    fin_rows = yonepse.financials_to_fundamental_rows(financials)
    news_rows = yonepse.notify_to_news_rows(disclosures, exchange_messages, notices)

    files = {
        "metadata": out / "yonepse_metadata.csv",
        "sectors": out / "yonepse_sectors.csv",
        "fundamentals": out / "yonepse_fundamentals.csv",
        "news": out / "yonepse_news.csv",
    }
    for target in files.values():
        if target.exists():
            print(f"error: refusing to overwrite {target}", file=sys.stderr)
            return 1

    files["metadata"].write_text(yonepse.metadata_csv(meta_rows), encoding="utf-8")
    files["sectors"].write_text(yonepse.sector_csv(sector_rows), encoding="utf-8")
    files["fundamentals"].write_text(yonepse.fundamentals_csv(fin_rows), encoding="utf-8")
    files["news"].write_text(yonepse.news_csv(news_rows), encoding="utf-8")

    print(f"YONEPSE snapshots written to {out}")
    print(f"  metadata rows:    {len(meta_rows)}")
    print(f"  sector rows:      {len(sector_rows)}")
    print(f"  fundamentals rows:{len(fin_rows)}")
    print(f"  news rows:        {len(news_rows)}")
    for name, target in files.items():
        print(f"  {name}: {target}")
    print("These files are ready for dry-run review; nothing was imported.")
    return 0


def _cmd_fundamentals_review(args: argparse.Namespace) -> int:
    """Promote a named source's fundamentals from 'extracted' to reviewed.

    Bulk review is an explicit trust act - it says "values from this source are
    trusted" - which is why it names the source and is never automatic. Ratios
    refuse 'extracted' values, so this is the switch that lets a P/E be derived.
    """
    from megatool.db import get_conn, init_app_db
    from megatool.fundamentals import FundamentalError, review_source

    init_app_db()
    try:
        with get_conn() as conn:
            out = review_source(conn, args.source, level=args.level)
    except FundamentalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"source  : {out['source']}")
    print(f"level   : {out['level']}")
    print(f"promoted: {out['promoted']}")
    return 0


def _cmd_sources_binayabaral(args: argparse.Namespace) -> int:
    """Fetch binayabaral reference/index CSVs and write loader-ready CSVs."""
    from megatool.datasources import binayabaral

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        ref_text = binayabaral.fetch_reference_csv()
        idx_text = binayabaral.fetch_index_csv()
    except binayabaral.BinayabaralError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    meta_rows = binayabaral.reference_to_metadata_rows(ref_text)
    sector_rows = binayabaral.reference_to_sector_rows(ref_text)
    idx_csv = binayabaral.index_to_index_csv(idx_text)

    files = {
        "metadata": out / "binayabaral_metadata.csv",
        "sectors": out / "binayabaral_sectors.csv",
        "index": out / "binayabaral_index_nepse.csv",
    }
    for target in files.values():
        if target.exists():
            print(f"error: refusing to overwrite {target}", file=sys.stderr)
            return 1

    files["metadata"].write_text(binayabaral.metadata_csv(meta_rows), encoding="utf-8")
    files["sectors"].write_text(binayabaral.sector_csv(sector_rows), encoding="utf-8")
    files["index"].write_text(idx_csv, encoding="utf-8")

    print(f"binayabaral/nepal-market-data snapshots written to {out}")
    print(f"  metadata rows: {len(meta_rows)}")
    print(f"  sector rows:   {len(sector_rows)}")
    print(f"  index rows:    {len(idx_csv.splitlines()) - 1}")
    for name, target in files.items():
        print(f"  {name}: {target}")
    print("These files are ready for dry-run review; nothing was imported.")
    return 0


def _cmd_events_import(args: argparse.Namespace) -> int:
    from megatool.corporate_events import (
        CorporateEventError,
        import_events,
        parse_events_csv,
    )
    from megatool.db import get_conn, init_app_db

    path = Path(args.file)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        rows = parse_events_csv(text, source=args.source or path.name)
    except CorporateEventError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    init_app_db()
    with get_conn() as conn:
        out = import_events(rows, conn)
    print(f"Corporate events from {path.name}")
    _print_indented("rows in file:", out["total"])
    _print_indented("inserted:", out["inserted"])
    _print_indented("updated:", out["updated"])
    _print_indented("rejected:", out["rejected"])
    if out["rejected"]:
        print("\nRejected rows lacked a symbol, a known event type, a source, or a")
        print("required effective date. A date is never inferred, so a notice with")
        print("no date cannot be placed on the calendar and is refused rather than guessed.")
    return 0


def _cmd_events_list(args: argparse.Namespace) -> int:
    from megatool.corporate_events import calendar
    from megatool.db import get_conn, init_app_db

    init_app_db()
    with get_conn() as conn:
        data = calendar(conn, since=args.since, until=args.until, limit=args.limit)
    print(f"{'DATE':<12} {'SYMBOL':<10} {'TYPE':<11} {'GRADE':<10} SOURCE")
    for ev in data["events"]:
        print(
            f"{(ev.get('effective_date') or '-'):<12} {ev.get('symbol', ''):<10} "
            f"{ev.get('event_type', ''):<11} {ev.get('grade', ''):<10} "
            f"{ev.get('source', '')}"
        )
    print(f"\n{data['count']} event(s). {data['note']}")
    return 0


def _cmd_events_coverage(_args: argparse.Namespace) -> int:
    from megatool.corporate_events import coverage
    from megatool.db import get_conn, init_app_db

    init_app_db()
    with get_conn() as conn:
        data = coverage(conn)
    print("Corporate-event coverage")
    _print_indented("imported notices:", data["stored_total"])
    _print_indented("registry (attested):", data["registry_total"])
    _print_indented("status:", data["status"])
    print("\n" + data["limitation"])
    return 0


def _cmd_alerts_evaluate(args: argparse.Namespace) -> int:
    """One-shot alert evaluation, designed to be run by an external scheduler.

    The application deliberately owns no background thread; scheduling belongs to
    the platform (cron, launchd, systemd timer, Windows Task Scheduler). This
    command is the unit those schedulers run.
    """
    import json

    from megatool.alerts import evaluate_conditions
    from megatool.db import get_conn, init_app_db
    from megatool.market_store import MarketStore

    path = Path(args.file)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 1
    try:
        conditions = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"error: could not read conditions: {exc}", file=sys.stderr)
        return 1
    if isinstance(conditions, dict):
        conditions = conditions.get("conditions") or []
    if not isinstance(conditions, list) or not conditions:
        print("error: the file must contain a non-empty list of conditions", file=sys.stderr)
        return 1

    init_app_db()
    try:
        store = MarketStore(read_only=True)
        store.query_rows("SELECT 1 AS ok")  # force the connection open
    except Exception as exc:  # a locked/unreadable store must fail loudly
        print(
            "error: the market store could not be opened, so no condition could be "
            f"evaluated ({exc}).\nStop whatever holds the file (e.g. a running server), "
            "or point MEGATOOL_DATA_DIR at an unlocked copy. Reporting 'no fire' here "
            "would be indistinguishable from 'no data', so the run is aborted.",
            file=sys.stderr,
        )
        return 2
    try:
        with get_conn() as conn:
            result = evaluate_conditions(store, conn, conditions)
    finally:
        store.close()
    payload = result.to_dict()
    print(f"evaluated={payload.get('evaluated', 0)} fired={len(payload.get('fired') or [])} "
          f"already_active={payload.get('already_active', 0)} "
          f"rejected={len(payload.get('rejected', []))}")
    for firing in payload.get("fired") or []:
        print(f"  {firing.get('severity', ''):<8} {firing.get('symbol', ''):<10} {firing.get('message', '')}")
    if payload.get("rejected"):
        print("\nRejected conditions are listed above by index; nothing was recorded for them.")
    if args.quiet:
        return 0
    print("\nRun this from an external scheduler; the app runs no background thread.")
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

    io = sub.add_parser("ingest-index-ohlc", help="import historical NEPSE index OHLC from a CSV file")
    io.add_argument("file", nargs="?", help="path to the CSV file (default: data/staging/socrateai_nepse_index/nepse_index_ohlc.csv)")
    io.add_argument("--db", help="SQLite database path (default: application DB)")
    io.add_argument("--source", default="socrateai-official/nepse-open-data", help="provenance label")
    io.add_argument("--index", default="NEPSE", help="index name to import (default: NEPSE)")
    io.add_argument("--dry-run", action="store_true", help="validate without writing")
    io.set_defaults(func=_cmd_ingest_index_ohlc)

    is_ = sub.add_parser("import-sectors", help="import sector classifications from a CSV file")
    is_.add_argument("file", help="path to the sector CSV file")
    is_.add_argument("--db", help="DuckDB market database path (default: market DB)")
    is_.add_argument("--source", help="provenance label (default: owner-supplied CSV)")
    is_.set_defaults(func=_cmd_import_sectors)

    sub.add_parser(
        "fetch-index",
        help="download the published NEPSE composite index into index_series",
    ).set_defaults(func=_cmd_fetch_index)

    sub.add_parser(
        "fetch-sectors",
        help="download sector classifications from the public YONEPSE snapshot",
    ).set_defaults(func=_cmd_fetch_sectors)

    sub.add_parser("status", help="show data coverage and freshness").set_defaults(func=_cmd_status)

    s = sub.add_parser("screen", help="run a saved screen")
    s.add_argument(
        "preset",
        help="one of: "
        + ", ".join(["oversold_rsi", "volume_surge", "near_52w_high", "above_sma50"]),
    )
    s.set_defaults(func=_cmd_screen)

    w = sub.add_parser(
        "walk-forward",
        help="validate the ranking historically (rank at each period end, hold the tails)",
    )
    w.add_argument("--frequency", choices=["M", "Q"], default="Q")
    w.add_argument("--start", help="first rebalance date (YYYY-MM-DD)")
    w.add_argument("--end", help="last rebalance date (YYYY-MM-DD)")
    w.add_argument("--top-quantile", type=float, default=0.25)
    w.add_argument("--min-bars", type=int, default=60)
    w.add_argument("--permutations", type=int, default=100)
    w.add_argument("--json", dest="json_out", help="write full detail to this path")
    w.set_defaults(func=_cmd_walk_forward)

    sub.add_parser("probe", help="check which data sources are reachable").set_defaults(
        func=_cmd_probe
    )

    v = sub.add_parser("serve", help="start the web terminal")
    v.add_argument("--host")
    v.add_argument("--port", type=int)
    v.add_argument("--log-level", default="warning")
    v.set_defaults(func=_cmd_serve)

    # ------------------------------------------------------------- ai provider
    ai = sub.add_parser("ai", help="inspect or exercise the optional LLM provider")
    aisub = ai.add_subparsers(dest="ai_command", required=True)
    ais = aisub.add_parser("status", help="show AI provider configuration (no network)")
    ais.set_defaults(func=_cmd_ai_status)
    aip = aisub.add_parser("ping", help="one bounded generation against the configured provider")
    aip.add_argument(
        "prompt", nargs="?", default=None, help="prompt to send (default: a short pong)"
    )
    aip.add_argument("--max-tokens", type=int, default=None, help="token cap for this call")
    aip.add_argument(
        "--allow-hosted",
        action="store_true",
        help="acknowledge a hosted request may consume API credit",
    )
    aip.set_defaults(func=_cmd_ai_ping)

    # ------------------------------------------------------------- written pdf
    def _cmd_pdf_import(args: argparse.Namespace) -> int:
        import json
        from datetime import date

        from megatool.written_pdf import (
            ExtractedRecord,
            ExtractionConfidence,
            RecordType,
            ReviewStatus,
            import_records,
        )

        path = Path(args.file)
        if not path.exists():
            print(f"error: no such file: {path}", file=sys.stderr)
            return 1
        data = json.loads(path.read_text(encoding="utf-8"))
        records = []
        for d in data:
            records.append(
                ExtractedRecord(
                    record_type=RecordType(d["record_type"]),
                    page=d["page"],
                    source_ref=d.get("source_ref", ""),
                    raw_text=d.get("raw_text", ""),
                    value=d.get("value"),
                    field_name=d.get("field_name", ""),
                    symbol=d.get("symbol"),
                    record_date=date.fromisoformat(d["record_date"])
                    if d.get("record_date")
                    else None,
                    unit=d.get("unit"),
                    confidence=ExtractionConfidence(d.get("confidence", "uncertain")),
                    review_status=ReviewStatus(d.get("review_status", "unreviewed")),
                    note=d.get("note", ""),
                )
            )
        out = import_records(records, args.pdf)
        print(f"PDF import from {args.pdf}")
        _print_indented("records:", out["records_total"])
        _print_indented("inserted:", out["records_inserted"])
        _print_indented("updated:", out["records_updated"])
        _print_indented("reviewed:", out["reviewed"])
        _print_indented("unreviewed:", out["unreviewed"])
        if out["unreviewed"]:
            print("\nUnreviewed records are stored but NOT safe for financial use.")
            print(
                "Review them in the web UI, or by id with: megatool pdf review --ids 1 --status reviewed"
            )
        return 0

    def _cmd_pdf_summary(args: argparse.Namespace) -> int:
        from megatool.written_pdf import RecordType, ReviewStatus, query_records

        rows = query_records(
            symbol=args.symbol,
            record_type=RecordType(args.type) if args.type else None,
            page=args.page,
            review_status=ReviewStatus.REVIEWED if args.reviewed else None,
        )
        if not rows:
            print("No extracted records match.")
            print("Import some with: megatool pdf import FILE.json")
            return 0
        # Count by type and review status
        by_type: dict[str, int] = {}
        by_review: dict[str, int] = {}
        for r in rows:
            by_type[r["record_type"]] = by_type.get(r["record_type"], 0) + 1
            by_review[r["review_status"]] = by_review.get(r["review_status"], 0) + 1
        scope = []
        if args.symbol:
            scope.append(f"symbol {args.symbol.upper()}")
        if args.type:
            scope.append(f"type {args.type}")
        if args.page:
            scope.append(f"page {args.page}")
        if args.reviewed:
            scope.append("reviewed only")
        print(f"PDF extraction summary ({', '.join(scope) if scope else 'all records'})")
        _print_indented("total records:", len(rows))
        print("\nBy type:")
        for k, v in sorted(by_type.items()):
            print(f"  {k:<14} {v:>6}")
        print("\nBy review status:")
        for k, v in sorted(by_review.items()):
            print(f"  {k:<14} {v:>6}")
        return 0

    def _cmd_pdf_list(args: argparse.Namespace) -> int:
        from megatool.written_pdf import RecordType, query_records

        rows = query_records(
            symbol=args.symbol,
            record_type=RecordType(args.type) if args.type else None,
            page=args.page,
        )
        if not rows:
            print("No extracted records match.")
            return 0
        rows = rows[: args.limit]
        print(
            f"{'PAGE':>4} {'TYPE':<12} {'SYMBOL':<10} {'FIELD':<14} {'VALUE':<12} {'CONF':<10} {'REVIEW':<10}"
        )
        for r in rows:
            val = r.get("value")
            val_str = str(val)[:12] if val is not None else ""
            print(
                f"{r['page']:>4} {r['record_type']:<12} {r.get('symbol', ''):<10} "
                f"{r.get('field_name', ''):<14} {val_str:<12} "
                f"{r.get('confidence', ''):<10} {r.get('review_status', ''):<10}"
            )
        return 0

    def _cmd_pdf_review(args: argparse.Namespace) -> int:
        from megatool.written_pdf import PdfValidationError, ReviewStatus, set_review_status

        try:
            status = ReviewStatus(args.status)
        except ValueError:
            print(
                f"error: unknown status {args.status!r}. "
                f"Valid: {', '.join(s.value for s in ReviewStatus)}",
                file=sys.stderr,
            )
            return 1
        ids = []
        for part in args.ids.split(","):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit():
                print(f"error: {part!r} is not a record id (use: --ids 1,2,3)", file=sys.stderr)
                return 1
            ids.append(int(part))
        if not ids:
            print("error: no record ids given (use: --ids 1,2,3)", file=sys.stderr)
            return 1
        try:
            out = set_review_status(ids, status)
        except PdfValidationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"Set {out['updated']} record(s) to {out['status']}", flush=True)
        if out["not_found"]:
            print(f"  not found: {out['not_found']} (ids that do not exist)", file=sys.stderr)
            return 1
        return 0

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

    # ------------------------------------------------------------ corporate events
    ev = sub.add_parser(
        "events",
        help="import and browse the corporate-event calendar (dividend, bonus, "
        "rights, IPO, allotment, AGM, merger, retirement). No licensed notice "
        "feed exists, so notices are import-based and never inferred from prices.",
    )
    evsub = ev.add_subparsers(dest="events_command", required=True)

    evi = evsub.add_parser("import", help="import a corporate-event CSV")
    evi.add_argument("file", help="path to the CSV as supplied")
    evi.add_argument("--source", help="where the file came from (default: its filename)")
    evi.set_defaults(func=_cmd_events_import)

    evl = evsub.add_parser("list", help="list stored events plus attested registry actions")
    evl.add_argument("--since", help="only events on/after this date, YYYY-MM-DD")
    evl.add_argument("--until", help="only events on/before this date, YYYY-MM-DD")
    evl.add_argument("--limit", type=int, default=200, help="maximum rows (default 200)")
    evl.set_defaults(func=_cmd_events_list)

    evsub.add_parser(
        "coverage",
        help="state exactly which event types are populated and which have no data",
    ).set_defaults(func=_cmd_events_coverage)

    # --------------------------------------------------------------------- alerts
    al = sub.add_parser(
        "alerts",
        help="evaluate alert conditions once (for an external scheduler; the app "
        "runs no background thread of its own)",
    )
    alsub = al.add_subparsers(dest="alerts_command", required=True)
    ale = alsub.add_parser("evaluate", help="evaluate a JSON file of conditions once")
    ale.add_argument("file", help="path to a JSON file containing a list of conditions")
    ale.add_argument("--quiet", action="store_true", help="suppress the closing note")
    ale.set_defaults(func=_cmd_alerts_evaluate)

    # ---------------------------------------------------------------- collector
    # The collector reads the published YONEPSE market files (the same
    # no-auth public mirror the dashboard serves), validates every row and
    # persists what the source actually stated - never a derived value.
    col = sub.add_parser(
        "collector",
        help="capture / inspect the published NEPSE market datasets "
        "(all-stock board, index, summary, status, sector indices, history, "
        "and the five top-mover rankings)",
    )
    colsub = col.add_subparsers(dest="collector_command", required=True)

    cols = colsub.add_parser(
        "snapshot",
        help="read, validate and persist one collection cycle (all ten datasets)",
    )
    cols.add_argument("--db", help="SQLite app-state path (default: configured store)")
    cols.add_argument("--out", help="also write JSON snapshots to this directory")
    cols.add_argument("--timeout", type=float, default=30.0, help="per-file fetch timeout, s")
    cols.set_defaults(func=_cmd_collector_snapshot)

    coll = colsub.add_parser("loop", help="poll on a configurable interval (floored at 60 s)")
    coll.add_argument("--db", help="SQLite app-state path (default: configured store)")
    coll.add_argument("--out", help="also write JSON snapshots to this directory")
    coll.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_CLI,
        help="seconds between cycles (default 900; floor 60 - the source "
        "publishes hourly, so faster polling adds nothing)",
    )
    coll.set_defaults(func=_cmd_collector_loop)

    colv = colsub.add_parser("status", help="show the latest run and its provenance")
    colv.add_argument("--db", help="SQLite app-state path (default: configured store)")
    colv.set_defaults(func=_cmd_collector_status)

    # ------------------------------------------------------------- written pdf
    wp = sub.add_parser(
        "pdf",
        help="import / inspect records extracted from Written Data.pdf",
    )
    wpsub = wp.add_subparsers(dest="pdf_command", required=True)

    wpi = wpsub.add_parser("import", help="import extracted records from a JSON file")
    wpi.add_argument("file", help="JSON file with extracted records")
    wpi.add_argument("--pdf", default="WRITTENdata.pdf", help="source PDF (for provenance)")
    wpi.set_defaults(func=_cmd_pdf_import)

    wps = wpsub.add_parser("summary", help="show extracted record statistics")
    wps.add_argument("--symbol", help="filter by symbol")
    wps.add_argument("--type", help="filter by record type")
    wps.add_argument("--page", type=int, help="filter by page")
    wps.add_argument("--reviewed", action="store_true", help="only reviewed records")
    wps.set_defaults(func=_cmd_pdf_summary)

    wpl = wpsub.add_parser("list", help="list extracted records")
    wpl.add_argument("--symbol", help="filter by symbol")
    wpl.add_argument("--type", help="filter by record type")
    wpl.add_argument("--page", type=int, help="filter by page")
    wpl.add_argument("--limit", type=int, default=50, help="max rows (default 50)")
    wpl.set_defaults(func=_cmd_pdf_list)

    wpr = wpsub.add_parser(
        "review",
        help="mark specific records reviewed/corrected/rejected (the human step)",
    )
    wpr.add_argument("--ids", required=True, help="comma-separated record ids, e.g. 1,2,3")
    wpr.add_argument(
        "--status",
        required=True,
        help="reviewed | corrected | rejected (not 'unreviewed')",
    )
    wpr.set_defaults(func=_cmd_pdf_review)

    # --------------------------------------------------- reviewed metadata
    md = sub.add_parser(
        "metadata",
        help="review security metadata (dry run only; imports nothing)",
    )
    mdsub = md.add_subparsers(dest="metadata_command", required=True)

    mdd = mdsub.add_parser(
        "dry-run",
        help="validate a reviewed metadata CSV and report what an import would change",
    )
    mdd.add_argument(
        "--input", required=True, help="reviewed CSV: symbol + one or more metadata columns"
    )
    mdd.add_argument(
        "--db",
        help="database to reconcile against, read-only (default: the production store)",
    )
    mdd.add_argument(
        "--out-dir",
        default="data/review/dry_run",
        help="where to write <stem>_dryrun.{json,md}; refuses to overwrite (default: data/review/dry_run)",
    )
    mdd.set_defaults(func=_cmd_metadata_dry_run)

    mdg = mdsub.add_parser(
        "gaps",
        help="read-only report of missing/unknown security metadata",
    )
    mdg.add_argument(
        "--db",
        help="database to read, read-only (default: the production store)",
    )
    mdg.add_argument(
        "--out-dir",
        default="data/review/gaps",
        help="where to write <stem>_gaps.{json,md}; refuses to overwrite (default: data/review/gaps)",
    )
    mdg.set_defaults(func=_cmd_metadata_gaps)

    # ----------------------------------------------------------- data sources
    fund = sub.add_parser(
        "fundamentals",
        help="review (trust) a named fundamentals source so ratios may use it",
    )
    fundsub = fund.add_subparsers(dest="fundamentals_command", required=True)
    fund_r = fundsub.add_parser(
        "review",
        help="promote one source's extracted records to a reviewed level",
    )
    fund_r.add_argument(
        "--source", required=True, help="the exact source string, e.g. yonepse/financials.json"
    )
    fund_r.add_argument(
        "--level",
        default="reviewed",
        choices=("reviewed", "verified"),
        help="the level to promote to (default: reviewed)",
    )
    fund_r.set_defaults(func=_cmd_fundamentals_review)

    src = sub.add_parser(
        "sources",
        help="fetch public data-source snapshots and write loader-ready CSVs",
    )
    srcsub = src.add_subparsers(dest="sources_command", required=True)

    src_y = srcsub.add_parser(
        "yonepse",
        help="fetch YONEPSE securities, financials, notices and write CSVs",
    )
    src_y.add_argument(
        "--out-dir",
        default="data/review/sources/yonepse",
        help="where to write CSVs; refuses to overwrite (default: data/review/sources/yonepse)",
    )
    src_y.set_defaults(func=_cmd_sources_yonepse)

    src_b = srcsub.add_parser(
        "binayabaral",
        help="fetch binayabaral reference and NEPSE index CSVs",
    )
    src_b.add_argument(
        "--out-dir",
        default="data/review/sources/binayabaral",
        help="where to write CSVs; refuses to overwrite (default: data/review/sources/binayabaral)",
    )
    src_b.set_defaults(func=_cmd_sources_binayabaral)

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
