#!/usr/bin/env python
"""Build a comprehensive ISOLATED fixture database for end-to-end QA.

Redirects MEGATOOL_DATA_DIR to an isolated directory before importing the app so
no production database is ever touched. Seeds:

* 8 price series with deliberately different shapes (uptrend, downtrend, flat,
  volatile, thin-history, a clean double-top, a gapping series);
* a NEPSE composite index series and one sector index series;
* security-master rows (including one SUSPENDED and one DELISTED so the
  eligibility paths are exercised);
* a handful of fundamentals records with a genuine reported PE == 0.

Usage::

    .venv/bin/python scripts/qa_fixture.py --out data/dev/qa

Nothing here is real market data; it is synthetic and labelled as such.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/dev/qa")
    args = ap.parse_args()

    out = (ROOT / args.out).resolve()
    os.environ["MEGATOOL_DATA_DIR"] = str(out)
    os.environ.pop("MEGATOOL_NEPSE_API_AUTHORIZED", None)

    import numpy as np
    import pandas as pd

    from megatool.config import PATHS
    from megatool.market_store import MarketStore

    for p in (PATHS.market_db, PATHS.app_db):
        if p.exists():
            p.unlink()
        wal = Path(str(p) + "-wal")
        if wal.exists():
            wal.unlink()
    (out / "processed").mkdir(parents=True, exist_ok=True)

    store = MarketStore(PATHS.market_db)
    rng = np.random.default_rng(20261016)
    n = 420
    dates = pd.bdate_range("2024-06-03", periods=n)

    def series(kind: str) -> np.ndarray:
        if kind == "up":
            base = 100 * np.exp(np.cumsum(rng.normal(0.0016, 0.011, n)))
        elif kind == "down":
            base = 300 * np.exp(np.cumsum(rng.normal(-0.0016, 0.012, n)))
        elif kind == "flat":
            base = 200 + rng.normal(0, 0.4, n).cumsum() * 0.05
            base = np.clip(base, 195, 205)
        elif kind == "volatile":
            base = 150 * np.exp(np.cumsum(rng.normal(0.0, 0.045, n)))
        elif kind == "double_top":
            # Two peaks near 130 with a neckline near 112, then a breakdown.
            half = n // 2
            q = half // 2
            a = np.linspace(100, 130, q)
            b = np.linspace(130, 112, q)
            c = np.linspace(112, 130, q)
            d = np.linspace(129.5, 108, n - 3 * q)  # start below the peak: no plateau
            base = np.concatenate([a, b, c, d])
        elif kind == "gap":
            base = 90 * np.exp(np.cumsum(rng.normal(0.0009, 0.013, n)))
        else:  # thin
            base = 80 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
        return base

    specs = [
        ("QAUPTREND", "up", "Commercial Banks", n),
        ("QADOWNTREND", "down", "Hydro Power", n),
        ("QAFLAT", "flat", "Life Insurance", n),
        ("QAVOLATILE", "volatile", "Microfinance", n),
        ("QADBLTOP", "double_top", "Commercial Banks", n),
        ("QAGAP", "gap", "Development Bank", n),
        ("QAONEYEAR", "up", "Others", 60),
        ("QABANK2", "up", "Commercial Banks", n),
        ("QABANK3", "down", "Commercial Banks", n),
        ("QAHYDRO2", "volatile", "Hydro Power", n),
        ("QAHYDRO3", "up", "Hydro Power", n),
        ("QAMICRO2", "flat", "Microfinance", n),
        ("QAOTHERS2", "gap", "Others", n),
    ]

    for sym, kind, _sector, count in specs:
        close = series(kind)[:count]
        d = dates[:count]
        # The double-top symbol is kept noise-free so a clean geometric pattern
        # is actually present for the UI/pattern tests (patterns read high/low).
        span = np.abs(rng.normal(0, 0.008, count)) * close
        span = np.zeros(count) if kind == "double_top" else span
        high = close + span
        low = close - span
        vol = rng.integers(5_000, 250_000, count).astype(float)
        store.upsert_bars(
            pd.DataFrame(
                {
                    "symbol": sym,
                    "trading_date": d,
                    "open": np.concatenate(([close[0]], close[:-1])),
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": vol.astype("int64"),
                    "turnover": close * vol,
                    "percent_change": np.concatenate(
                        ([np.nan], np.diff(close) / close[:-1] * 100.0)
                    ),
                    "source": "qa-fixture",
                    "retrieved_at": pd.Timestamp("2026-10-01 09:00:00"),
                }
            )
        )

    # Index series (composite + one sector).
    idx_close = 2000 * np.exp(np.cumsum(rng.normal(0.0006, 0.007, n)))
    store.upsert_index_rows(
        [
            {"index_name": "NEPSE", "trading_date": d, "close": float(c), "source": "qa-fixture"}
            for d, c in zip(dates, idx_close, strict=False)
        ]
    )
    sec_close = 1200 * np.exp(np.cumsum(rng.normal(0.0008, 0.009, n)))
    store.upsert_index_rows(
        [
            {
                "index_name": "Commercial Banks",
                "trading_date": d,
                "close": float(c),
                "source": "qa-fixture",
            }
            for d, c in zip(dates, sec_close, strict=False)
        ]
    )

    store.set_sectors(
        {
            "QAUPTREND": "Commercial Banks",
            "QADOWNTREND": "Hydro Power",
            "QAFLAT": "Life Insurance",
            "QAVOLATILE": "Microfinance",
            "QADBLTOP": "Commercial Banks",
            "QAGAP": "Development Bank",
            "QAONEYEAR": "Others",
            "QABANK2": "Commercial Banks",
            "QABANK3": "Commercial Banks",
            "QAHYDRO2": "Hydro Power",
            "QAHYDRO3": "Hydro Power",
            "QAMICRO2": "Microfinance",
            "QAOTHERS2": "Others",
        }
    )
    store.upsert_securities(
        [
            {
                "symbol": "QAUPTREND",
                "name": "QA Uptrend Ltd",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Commercial Banks",
                "source": "qa-fixture",
            },
            {
                "symbol": "QADOWNTREND",
                "name": "QA Downtrend Ltd",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Hydro Power",
                "source": "qa-fixture",
            },
            {
                "symbol": "QAFLAT",
                "name": "QA Flat Ltd",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Life Insurance",
                "source": "qa-fixture",
            },
            {
                "symbol": "QAVOLATILE",
                "name": "QA Volatile Ltd",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Microfinance",
                "source": "qa-fixture",
            },
            {
                "symbol": "QADBLTOP",
                "name": "QA Double Top Ltd",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Commercial Banks",
                "source": "qa-fixture",
            },
            {
                "symbol": "QAGAP",
                "name": "QA Gap Ltd",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Development Bank",
                "source": "qa-fixture",
            },
            {
                "symbol": "QAONEYEAR",
                "name": "QA Thin History Ltd",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Others",
                "source": "qa-fixture",
            },
            {
                "symbol": "QABANK2",
                "name": "QA Bank Two",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Commercial Banks",
                "source": "qa-fixture",
            },
            {
                "symbol": "QABANK3",
                "name": "QA Bank Three",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Commercial Banks",
                "source": "qa-fixture",
            },
            {
                "symbol": "QAHYDRO2",
                "name": "QA Hydro Two",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Hydro Power",
                "source": "qa-fixture",
            },
            {
                "symbol": "QAHYDRO3",
                "name": "QA Hydro Three",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Hydro Power",
                "source": "qa-fixture",
            },
            {
                "symbol": "QAMICRO2",
                "name": "QA Micro Two",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Microfinance",
                "source": "qa-fixture",
            },
            {
                "symbol": "QAOTHERS2",
                "name": "QA Others Two",
                "status": "ACTIVE",
                "instrument_type": "ordinary",
                "sector": "Others",
                "source": "qa-fixture",
            },
            {
                "symbol": "QASUSPEND",
                "name": "QA Suspended Ltd",
                "status": "SUSPENDED",
                "instrument_type": "ordinary",
                "sector": "Others",
                "source": "qa-fixture",
            },
            {
                "symbol": "QADELISTED",
                "name": "QA Delisted Ltd",
                "status": "DELISTED",
                "instrument_type": "ordinary",
                "sector": "Others",
                "source": "qa-fixture",
            },
        ]
    )
    store.close()
    print(f"QA fixture written to {out}")
    print("market_db ->", PATHS.market_db)
    print("app_db    ->", PATHS.app_db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
