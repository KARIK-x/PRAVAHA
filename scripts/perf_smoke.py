#!/usr/bin/env python
"""Isolated performance smoke test for the Mega Tool API.

What this measures
------------------
Backend-only, in-process request latency through FastAPI's ``TestClient`` for a
synthetic universe written to an **isolated** DuckDB file under
``data/dev/perf/`` (git-ignored). It deliberately:

* redirects ``MEGATOOL_DATA_DIR`` to that dev directory *before* importing
  ``megatool`` so no production database or directory is touched;
* never sets ``MEGATOOL_NEPSE_API_AUTHORIZED`` (the gated collector stays off);
* reports median (p50) and p95 over a small number of repetitions **and the
  sample size**, because percentiles from a handful of runs are indicative, not
  a guarantee;
* separates backend handling time from real network/browser latency (this is
  not end-to-end and is not live-market latency).

Usage::

    .venv/bin/python scripts/perf_smoke.py --symbols 60 --bars 650 --runs 15
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "data" / "dev" / "perf"
DEV.mkdir(parents=True, exist_ok=True)
# Point the app at the isolated dev directory BEFORE importing megatool.config.
os.environ["MEGATOOL_DATA_DIR"] = str(DEV)
os.environ.pop("MEGATOOL_NEPSE_API_AUTHORIZED", None)  # collector stays gated OFF

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from megatool.api import create_app  # noqa: E402
from megatool.market_store import MarketStore  # noqa: E402


def _bars_frame(symbol: str, closes: np.ndarray, dates) -> pd.DataFrame:
    high = closes * 1.01
    low = closes * 0.99
    vol = np.full(len(closes), 20_000.0)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": dates,
            "open": closes,
            "high": high,
            "low": low,
            "close": closes,
            "volume": vol.astype(np.int64),
            "turnover": closes * vol,
            "percent_change": np.nan,
            "source": "perf-fixture",
            "retrieved_at": pd.Timestamp("2026-01-01"),
        }
    )


def seed(store: MarketStore, symbols: int, bars: int) -> list[str]:
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2023-01-01", periods=bars)
    names: list[str] = []
    for i in range(symbols):
        sym = f"SYM{i:03d}"
        names.append(sym)
        rets = rng.normal(0.0005, 0.02, bars)
        close = 100.0 * np.exp(np.cumsum(rets))
        store.upsert_bars(_bars_frame(sym, close, dates))
    # A composite index series so ranking has a benchmark.
    idx = 2000.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.008, bars)))
    store.upsert_index_rows(
        [
            {"index_name": "NEPSE", "trading_date": d, "close": float(c), "source": "perf-fixture"}
            for d, c in zip(dates, idx, strict=False)
        ]
    )
    return names


def _time(client: TestClient, method: str, url: str, **kw):
    t0 = time.perf_counter()
    r = client.request(method, url, **kw)
    return (time.perf_counter() - t0) * 1000.0, r.status_code  # ms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=int, default=60)
    ap.add_argument("--bars", type=int, default=650)
    ap.add_argument("--runs", type=int, default=15, help="repetitions per endpoint")
    ap.add_argument("--warmup", type=int, default=2)
    args = ap.parse_args()

    db = DEV / "perf_market.duckdb"
    if db.exists():
        db.unlink()
    for suffix in (".wal",):
        p = Path(str(db) + suffix)
        if p.exists():
            p.unlink()

    store = MarketStore(db)
    names = seed(store, args.symbols, args.bars)
    one = names[0]
    # Building the app initialises the schema, so redirect the application
    # SQLite store to the perf playground: a benchmark must not migrate the
    # operator's real state database.
    os.environ.setdefault("MEGATOOL_APP_DB", str(DEV / "perf_state.sqlite"))
    app = create_app(store=store)

    screen_tree = {
        "op": "AND",
        "conditions": [
            {"metric": "rsi", "operator": "lt", "value": 70},
            {"metric": "bars_listed", "operator": "gte", "value": 200},
        ],
    }
    cases = [
        ("GET", "/api/dashboard", {}),
        ("GET", "/api/quotes", {}),
        ("GET", f"/api/bars/{one}", {}),
        ("GET", f"/api/bars/{one}/indicator?name=rsi", {}),
        ("GET", f"/api/bars/{one}/patterns", {}),
        ("GET", f"/api/bars/{one}/statistics", {}),
        ("POST", "/api/screen", {"json": {"tree": screen_tree}}),
        ("POST", "/api/rank", {"json": {}}),
        ("POST", "/api/backtest", {"json": {"symbol": one, "strategy": "sma_cross"}}),
        ("GET", f"/api/stats/correlation?symbols={names[0]},{names[1]},{names[2]}", {}),
    ]

    print(f"Isolated DB: {db}")
    print(f"Universe: {args.symbols} symbols x {args.bars} bars  (synthetic, seeded)")
    print(
        f"Repetitions per endpoint: {args.runs} (+{args.warmup} warmup), backend-only via TestClient\n"
    )
    header = f"{'endpoint':52s} {'status':>6s} {'p50 ms':>9s} {'p95 ms':>9s} {'n':>4s}"
    print(header)
    print("-" * len(header))
    results = []
    with TestClient(app) as client:
        for method, url, kw in cases:
            for _ in range(args.warmup):
                client.request(method, url, **kw)
            times, status = [], None
            for _ in range(args.runs):
                dt, status = _time(client, method, url, **kw)
                times.append(dt)
            times.sort()
            p50 = statistics.median(times)
            p95 = times[min(len(times) - 1, int(round(0.95 * (len(times) - 1))))]
            label = f"{method} {url.split('?')[0]}"
            print(f"{label:52s} {status:>6d} {p50:>9.1f} {p95:>9.1f} {len(times):>4d}")
            results.append(
                {
                    "endpoint": label,
                    "status": status,
                    "p50_ms": round(p50, 2),
                    "p95_ms": round(p95, 2),
                    "n": len(times),
                }
            )
    store.close()
    print("\nNote: backend-only, warm in-process latency. Not end-to-end, not live-market latency.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
