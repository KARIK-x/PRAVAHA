#!/usr/bin/env python
"""Ingest the NEPSE official intraday quote board into a market database.

Dry-run by default: it fetches (or reads) the exchange's ``lives-market`` board,
validates and converts it, prints a per-status summary and writes **nothing**.

Two independent gates stand between the network and a write:

  * any network fetch needs ``MEGATOOL_NEPSE_API_AUTHORIZED=1`` — the official
    API is undocumented and its token generator is obfuscated, so automated use
    is an explicit owner decision (see ``megatool/datasources/nepse_official_live.py``);
  * ``--apply`` additionally needs ``MEGATOOL_INTEGRATION_AUTHORIZED=1`` and a
    ``--market-db``.

Quote rows never touch ``price_bars``: a quote is an evolving intraday snapshot,
not a settled end-of-day bar. Re-running over the same snapshot is idempotent
(keyed ``(symbol, quote_date, source)``).
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

from megatool.datasources import nepse_official_live as officallive  # noqa: E402
from megatool.market_store import MarketStore  # noqa: E402


def _load_live(args: argparse.Namespace) -> tuple[list[dict], dict]:
    """Return (records, meta). Reads a cached file when given; else fetches."""
    if args.from_file:
        raw = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        records = raw.get("records") if isinstance(raw, dict) else raw
        meta = {"origin": f"file:{args.from_file}", "records_in": len(records or [])}
        print(f"read {len(records or [])} records from {args.from_file}")
        return list(records or []), meta

    print("fetching nepalstock.com.np/api/nots/lives-market ...")
    with officallive.NepseOfficialLiveClient() as client:
        status = officallive.market_status_summary(client.market_status())
        records = client.live_market()
    meta = {"origin": "live", "market_status": status, "records_in": len(records)}
    print(f"market status: {json.dumps(status)}")
    return records, meta


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--from-file", help="read a cached lives-market JSON instead of fetching")
    p.add_argument("--market-db", help="target market DuckDB (required with --apply)")
    p.add_argument("--apply", action="store_true", help="write the rows (gated)")
    p.add_argument("--json-out", help="write the summary JSON here")
    args = p.parse_args()

    if not args.from_file and os.environ.get(officallive.AUTH_ENV) != "1":
        print(
            f"refusing to fetch: set {officallive.AUTH_ENV}=1 to authorize automated "
            "access to the NEPSE official API (or use --from-file for a cached snapshot)",
            file=sys.stderr,
        )
        return 2

    records, meta = _load_live(args)
    rows, stats = officallive.live_market_to_quote_rows(records)

    now = datetime.now(UTC).isoformat(timespec="seconds")
    summary: dict = {"fetched_at": now, "meta": meta, "stats": stats}
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
