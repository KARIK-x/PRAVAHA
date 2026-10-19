#!/usr/bin/env python
"""Ingest the YONEPSE near-live quote board into a market database.

Dry-run by default: it fetches (or reads) ``market/live.json``, validates and
converts it, prints a per-status summary and writes **nothing**.  Writing to a
database requires ``--apply`` *and* ``MEGATOOL_INTEGRATION_AUTHORIZED=1``, so a
production write can never happen by accident.

Quote rows never touch ``price_bars``: a quote is an evolving intraday snapshot,
not a settled end-of-day bar.  Re-running over the same snapshot is idempotent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from megatool.datasources import yonepse  # noqa: E402
from megatool.market_store import MarketStore  # noqa: E402


def _load_live(args: argparse.Namespace) -> list[dict]:
    if args.from_file:
        raw = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        print(f"read {len(raw)} records from {args.from_file}")
        return raw
    print("fetching yonepse/market/live.json ...")
    return yonepse.fetch_market_live()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--from-file", help="read a cached live.json instead of fetching")
    p.add_argument("--market-db", help="target market DuckDB (required with --apply)")
    p.add_argument("--apply", action="store_true", help="write the rows (gated)")
    p.add_argument("--json-out", help="write the summary JSON here")
    args = p.parse_args()

    records = _load_live(args)
    rows, stats = yonepse.market_live_to_quote_rows(records)

    now = datetime.now(UTC).isoformat(timespec="seconds")
    summary: dict = {"fetched_at": now, "stats": stats}
    print(f"converted {stats['rows_out']} quote rows from {stats['records_in']} records")
    for k in ("no_symbol", "missing_timestamp", "missing_ltp", "invalid_ltp", "suspect"):
        if stats.get(k):
            print(f"  {k}: {stats[k]}")

    if not args.apply:
        print("dry-run: nothing written (pass --apply with MEGATOOL_INTEGRATION_AUTHORIZED=1)")
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 0

    if os.environ.get("MEGATOOL_INTEGRATION_AUTHORIZED") != "1":
        print("refusing to write: set MEGATOOL_INTEGRATION_AUTHORIZED=1", file=sys.stderr)
        return 2
    if not args.market_db:
        print("refusing to write: --market-db is required with --apply", file=sys.stderr)
        return 2

    store = MarketStore(Path(args.market_db))
    before = store.quote_freshness()
    written = store.upsert_quotes(rows)
    after = store.quote_freshness()
    # Prove idempotency rather than assert it.
    store.upsert_quotes(rows)
    after2 = store.quote_freshness()

    summary |= {"before": before, "after": after, "after_second_pass": after2}
    print(f"wrote {written} rows; rows {before['rows']} -> {after['rows']}")
    print(f"idempotency: second pass rows {after2['rows']} (expected {after['rows']})")
    print(f"freshness: {json.dumps(after)}")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
