"""NEPSE data preparation prototype for Kronos fine-tuning.

Reads historical OHLCV from the Mega Tool DuckDB market store and converts
to the Kronos training schema (OHLCVA + time features). Produces strictly
chronological train/val/test splits with lookback buffers.

This script does NOT train, fine-tune, or modify any model. It only prepares
data files in a separate experiment directory.

Usage:
    MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python scripts/kronos_data_prep.py

Output:
    data/kronos_experiment/
        train_data.pkl, val_data.pkl, test_data.pkl
        prep_report.json  (counts, date ranges, quality metrics)
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from megatool.config import PATHS
from megatool.market_store import MarketStore

# Kronos training schema constants (from official finetune/config.py)
LOOKBACK = 90
PREDICT = 10
WINDOW = LOOKBACK + PREDICT + 1  # 101
CLIP = 5.0
FEATURE_LIST = ["open", "high", "low", "close", "vol", "amt"]
TIME_FEATURE_LIST = ["minute", "hour", "weekday", "day", "month"]

# Chronological splits (NEPSE adaptation of official Kronos split)
TRAIN_RANGE = ("2010-01-01", "2022-12-31")
VAL_RANGE = ("2022-09-01", "2024-06-30")
TEST_RANGE = ("2024-04-01", "2025-06-30")
BACKTEST_RANGE = ("2024-07-01", "2026-10-15")

OUT_DIR = PATHS.data / "kronos_experiment"


def load_nepe_bars(store: MarketStore) -> dict[str, pd.DataFrame]:
    """Load all symbols' bars from DuckDB, convert to Kronos schema."""
    import duckdb

    conn = store.conn
    symbols = [r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM price_bars ORDER BY symbol"
    ).fetchall()]

    data = {}
    skipped = []
    for sym in symbols:
        try:
            df = store.get_bars(sym, limit=100000)
        except Exception as e:
            skipped.append((sym, str(e)))
            continue

        if df is None or df.empty:
            skipped.append((sym, "empty"))
            continue

        # Normalize column names
        low = {c.lower(): c for c in df.columns}
        time_col = next((low[k] for k in ("time", "trading_date", "date") if k in low), None)
        if time_col is None:
            skipped.append((sym, "no time column"))
            continue

        # Required columns
        for col in ("open", "high", "low", "close", "volume"):
            if col not in low:
                skipped.append((sym, f"missing {col}"))
                break
        else:
            # Build schema
            out = pd.DataFrame()
            out["datetime"] = pd.to_datetime(df[time_col])
            out["open"] = pd.to_numeric(df[low["open"]], errors="coerce")
            out["high"] = pd.to_numeric(df[low["high"]], errors="coerce")
            out["low"] = pd.to_numeric(df[low["low"]], errors="coerce")
            out["close"] = pd.to_numeric(df[low["close"]], errors="coerce")
            out["vol"] = pd.to_numeric(df[low["volume"]], errors="coerce")

            # amount = (O+H+L+C)/4 * vol (from official preprocessing)
            out["amt"] = (out["open"] + out["high"] + out["low"] + out["close"]) / 4 * out["vol"]

            # Sort by datetime, drop exact duplicates
            out = out.sort_values("datetime").drop_duplicates(subset=["datetime"]).reset_index(drop=True)

            # Drop rows with any NaN in required fields
            out = out.dropna(subset=FEATURE_LIST).reset_index(drop=True)

            # Filter symbols with insufficient data
            if len(out) < WINDOW:
                skipped.append((sym, f"insufficient bars ({len(out)} < {WINDOW})"))
                continue

            # Set datetime as index (Qlib convention)
            out = out.set_index("datetime")
            out = out[FEATURE_LIST]
            data[sym] = out

    print(f"Loaded {len(data)} symbols ({len(skipped)} skipped)")
    if skipped:
        print(f"  Skipped: {skipped[:5]}{'...' if len(skipped)>5 else ''}")
    return data, skipped


def create_splits(data: dict[str, pd.DataFrame]) -> tuple[dict, dict, dict]:
    """Chronological split with lookback buffers. No future leakage."""
    train_data, val_data, test_data = {}, {}, {}

    for symbol, df in data.items():
        train_mask = (df.index >= TRAIN_RANGE[0]) & (df.index <= TRAIN_RANGE[1])
        val_mask = (df.index >= VAL_RANGE[0]) & (df.index <= VAL_RANGE[1])
        test_mask = (df.index >= TEST_RANGE[0]) & (df.index <= TEST_RANGE[1])

        train_data[symbol] = df[train_mask].copy()
        val_data[symbol] = df[val_mask].copy()
        test_data[symbol] = df[test_mask].copy()

    return train_data, val_data, test_data


def validate_data(data: dict[str, pd.DataFrame]) -> dict:
    """Validate data quality and return metrics."""
    report = {
        "total_symbols": len(data),
        "total_bars": sum(len(df) for df in data.values()),
        "date_range": {
            "min": (lambda x: x.strftime("%Y-%m-%d") if x is not None else None)(min((df.index.min() for df in data.values() if len(df) > 0), default=None)),
            "max": (lambda x: x.strftime("%Y-%m-%d") if x is not None else None)(max((df.index.max() for df in data.values() if len(df) > 0), default=None)),
        },
        "per_symbol": {},
        "quality": {
            "null_bars": 0,
            "duplicate_timestamps": 0,
            "insufficient_history": 0,
        },
    }

    for symbol, df in data.items():
        if len(df) == 0:
            report["per_symbol"][symbol] = {"bars": 0, "first": None, "last": None, "null_count": 0}
            continue
        report["per_symbol"][symbol] = {
            "bars": len(df),
            "first": df.index.min().strftime("%Y-%m-%d"),
            "last": df.index.max().strftime("%Y-%m-%d"),
            "null_count": int(df.isnull().sum().sum()),
        }
        report["quality"]["null_bars"] += int(df.isnull().sum().sum())

    # Check for duplicate timestamps across symbols
    all_ts = []
    for df in data.values():
        all_ts.extend(df.index.tolist())
    report["quality"]["duplicate_timestamps"] = len(all_ts) - len(set(all_ts))

    return report


def main():
    print("=" * 60)
    print("Kronos NEPSE Data Preparation Prototype")
    print("=" * 60)

    store = MarketStore()
    data, skipped = load_nepe_bars(store)

    # Validate
    report = validate_data(data)
    report["skipped"] = [{"symbol": s, "reason": r} for s, r in skipped]

    # Create splits
    train_data, val_data, test_data = create_splits(data)

    # Report split sizes
    report["splits"] = {
        "train": {
            "symbols": len(train_data),
            "bars": sum(len(df) for df in train_data.values()),
            "date_range": {
                "min": min((df.index.min() for df in train_data.values() if len(df) > 0), default=None),
                "max": max((df.index.max() for df in train_data.values() if len(df) > 0), default=None),
            },
        },
        "val": {
            "symbols": len(val_data),
            "bars": sum(len(df) for df in val_data.values()),
            "date_range": {
                "min": min((df.index.min() for df in val_data.values() if len(df) > 0), default=None),
                "max": max((df.index.max() for df in val_data.values() if len(df) > 0), default=None),
            },
        },
        "test": {
            "symbols": len(test_data),
            "bars": sum(len(df) for df in test_data.values()),
            "date_range": {
                "min": min((df.index.min() for df in test_data.values() if len(df) > 0), default=None),
                "max": max((df.index.max() for df in test_data.values() if len(df) > 0), default=None),
            },
        },
    }

    # Format dates
    for split in report["splits"].values():
        dr = split["date_range"]
        if dr["min"] is not None:
            dr["min"] = dr["min"].strftime("%Y-%m-%d")
        if dr["max"] is not None:
            dr["max"] = dr["max"].strftime("%Y-%m-%d")

    # Save outputs
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "train_data.pkl", "wb") as f:
        pickle.dump(train_data, f)
    with open(OUT_DIR / "val_data.pkl", "wb") as f:
        pickle.dump(val_data, f)
    with open(OUT_DIR / "test_data.pkl", "wb") as f:
        pickle.dump(test_data, f)

    # Save report
    with open(OUT_DIR / "prep_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nOutput directory: {OUT_DIR}")
    print(f"Total symbols: {report['total_symbols']}")
    print(f"Total bars: {report['total_bars']}")
    print(f"Date range: {report['date_range']['min']} to {report['date_range']['max']}")
    print(f"Train: {report['splits']['train']['symbols']} symbols, {report['splits']['train']['bars']} bars")
    print(f"Val:   {report['splits']['val']['symbols']} symbols, {report['splits']['val']['bars']} bars")
    print(f"Test:  {report['splits']['test']['symbols']} symbols, {report['splits']['test']['bars']} bars")
    print(f"Null bars: {report['quality']['null_bars']}")
    print(f"Skipped: {len(skipped)}")
    print("\nDone. No model training performed.")


if __name__ == "__main__":
    main()
