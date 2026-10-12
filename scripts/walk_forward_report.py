#!/usr/bin/env python3
"""Reproduce the walk-forward validation of the multi-factor ranking.

This is the command behind the numbers recorded in
``docs/RESEARCH_REGISTER.md``. It ranks the universe at every period end using
only data available then, holds the top and bottom quantiles for one period,
and reports what actually happened next — against both the whole-universe
benchmark and a random-selection baseline.

It reads the real store. It writes nothing.

    python scripts/walk_forward_report.py                       # default windows
    python scripts/walk_forward_report.py --frequency Q --start 2018-01-01
    python scripts/walk_forward_report.py --json out.json        # full detail

Read the caveats the script prints. The most important one is survivorship
bias: the store holds only companies still listed today, so every figure here
is optimistic by an unknown amount.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from megatool.config import PATHS  # noqa: E402
from megatool.market_store import MarketStore  # noqa: E402
from megatool.walkforward import CAVEATS, WalkForwardConfig, walk_forward  # noqa: E402

#: The windows worth reporting: split at market-relevant boundaries rather than
#: chopped evenly, so a result that flips sign between them is visible.
DEFAULT_RUNS: list[tuple[str, str, str]] = [
    ("Q", "1995-01-01", "2007-12-31"),
    ("Q", "2008-01-01", "2017-12-31"),
    ("Q", "2018-01-01", "2026-12-31"),
    ("Q", "1995-01-01", "2026-12-31"),
    ("M", "2015-01-01", "2026-12-31"),
]


def load_frames() -> dict:
    """Every symbol's bars, loaded once and reused across all windows."""
    store = MarketStore(PATHS.market_db)
    rows = store.execute(
        "SELECT symbol, trading_date, open, high, low, close, volume "
        "FROM price_bars ORDER BY symbol, trading_date"
    ).df()
    store.close()
    frames = {s: g.reset_index(drop=True) for s, g in rows.groupby("symbol")}
    del rows
    return frames


def _pct(value: float | None) -> str:
    return "     n/a" if value is None else f"{value * 100:8.3f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description="Walk-forward validation of the ranking")
    ap.add_argument("--frequency", choices=["M", "Q"], help="run a single window")
    ap.add_argument("--start", help="run a single window")
    ap.add_argument("--end", help="run a single window")
    ap.add_argument("--permutations", type=int, default=100)
    ap.add_argument("--json", dest="json_out", help="write full detail to this path")
    args = ap.parse_args()

    runs = (
        [(args.frequency, args.start, args.end)] if args.frequency and args.start else DEFAULT_RUNS
    )

    print("Loading the store ...", flush=True)
    t0 = time.perf_counter()
    frames = load_frames()
    print(f"  {len(frames)} symbols in {time.perf_counter() - t0:.1f}s\n")

    header = (
        f"{'freq':<5}{'start':<12}{'end':<12}{'n':>4}"
        f"{'mean spr':>11}{'med spr':>11}{'hit rate':>11}"
        f"{'cum long':>11}{'cum bench':>11}{'chance p95':>12}{'pctile':>9}"
    )
    print(header)
    print("-" * len(header))

    detail: list[dict] = []
    for freq, start, end in runs:
        cfg = WalkForwardConfig(
            frequency=freq, start=start, end=end, permutations=args.permutations
        )
        t = time.perf_counter()
        result = walk_forward(frames, cfg)
        elapsed = time.perf_counter() - t
        d = result.to_dict()
        s = d["summary"]
        cb = d["chance_baseline"]
        pctile = cb["observed_percentile"]
        print(
            f"{freq:<5}{start:<12}{end:<12}{s['periods_used']:>4}"
            f"{_pct(s['mean_spread']):>11}{_pct(s['median_spread']):>11}"
            f"{_pct(s['hit_rate']):>11}{_pct(s['cumulative_long']):>11}"
            f"{_pct(s['cumulative_benchmark']):>11}{_pct(cb['p95_spread']):>12}"
            f"{'n/a' if pctile is None else f'{pctile:9.3f}'}",
            flush=True,
        )
        detail.append({"elapsed_seconds": round(elapsed, 1), **d})

    print()
    print("Reading these numbers")
    print("---------------------")
    print("mean spr   : mean per-period (top quantile - bottom quantile) return.")
    print("             NEGATIVE means the ranking's favourites underperformed its")
    print("             rejects — the opposite of what a ranking is for.")
    print("hit rate   : fraction of periods in which the top quantile beat the bottom.")
    print("chance p95 : 95th percentile of the same spread obtained by assigning the")
    print("             same number of symbols to each tail at random, every period.")
    print("pctile     : where the observed mean spread sits in that random")
    print("             distribution. Near 0 = worse than chance; near 1 = better.")
    print()
    print("Caveats — these numbers are optimistic and are not advice:")
    for c in CAVEATS:
        print(f"  - {c}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(detail, indent=2))
        print(f"\nfull detail written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
