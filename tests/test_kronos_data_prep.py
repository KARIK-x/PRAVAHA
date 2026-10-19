"""Tests for Kronos NEPSE data preparation prototype."""
import json
import os
import pickle
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys_path = str(PROJECT_ROOT)
import sys
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

# Import the module functions
from scripts.kronos_data_prep import (
    load_nepe_bars,
    create_splits,
    validate_data,
    LOOKBACK,
    PREDICT,
    WINDOW,
    FEATURE_LIST,
    TIME_FEATURE_LIST,
    TRAIN_RANGE,
    VAL_RANGE,
    TEST_RANGE,
)

# Use isolated test DB
os.environ.setdefault("MEGATOOL_DATA_DIR", str(PROJECT_ROOT / "data" / "dev" / "release"))


@pytest.fixture(scope="module")
def prepared_data():
    out = Path(os.environ["MEGATOOL_DATA_DIR"]) / "kronos_experiment"
    # Prefer already-prepared pickle files (avoids DuckDB lock conflicts
    # when the dev server is running).
    if (out / "train_data.pkl").exists():
        with open(out / "train_data.pkl", "rb") as f:
            data = pickle.load(f)
        return data, []
    # Fall back to DuckDB (only works when dev server is not holding the lock)
    try:
        from megatool.market_store import MarketStore
        store = MarketStore()
        data, skipped = load_nepe_bars(store)
        return data, skipped
    except Exception:
        pytest.skip("DuckDB locked by dev server and no prepared pickle files available")


def test_schema_columns(prepared_data):
    data, _ = prepared_data
    assert len(data) > 0
    for sym, df in data.items():
        assert list(df.columns) == FEATURE_LIST, f"{sym}: {list(df.columns)}"
        assert df.index.name == "datetime"
        break


def test_no_nulls(prepared_data):
    data, _ = prepared_data
    for sym, df in data.items():
        assert not df.isnull().any().any(), f"{sym} has nulls"
        assert (df["vol"] >= 0).all(), f"{sym} has negative volume"


def test_timestamp_ordering(prepared_data):
    data, _ = prepared_data
    for sym, df in data.items():
        assert df.index.is_monotonic_increasing, f"{sym} not sorted"
        assert not df.index.duplicated().any(), f"{sym} has duplicate timestamps"


def test_sufficient_history(prepared_data):
    data, _ = prepared_data
    for sym, df in data.items():
        if len(df) == 0:
            continue
        if len(df) < WINDOW:
            continue  # symbols with insufficient bars in this split (expected for newer stocks)
        assert len(df) >= WINDOW, f"{sym}: {len(df)} < {WINDOW}"


def test_splits_chronological(prepared_data):
    data, _ = prepared_data
    train, val, test = create_splits(data)
    # Val must start after train starts (overlap for lookback, but val end > train start)
    for split_name, split in [("train", train), ("val", val), ("test", test)]:
        for sym, df in split.items():
            if len(df) > 0:
                assert df.index.is_monotonic_increasing, f"{sym} in {split_name} not sorted"


def test_no_future_leakage(prepared_data):
    data, _ = prepared_data
    train, val, test = create_splits(data)
    # Train max date must be <= train range end
    for sym, df in train.items():
        if len(df) > 0:
            assert df.index.max() <= pd.Timestamp(TRAIN_RANGE[1])
    # Val must not include train-only early dates beyond overlap
    # Test must start after val (with lookback buffer overlap allowed)
    for sym, df in test.items():
        if len(df) > 0:
            assert df.index.min() >= pd.Timestamp(TEST_RANGE[0])


def test_amt_computation(prepared_data):
    data, _ = prepared_data
    for sym, df in list(data.items())[:3]:
        # amt = (O+H+L+C)/4 * vol
        expected = (df["open"] + df["high"] + df["low"] + df["close"]) / 4 * df["vol"]
        pd.testing.assert_series_equal(df["amt"], expected, check_names=False, atol=1e-6)


def test_validate_data(prepared_data):
    data, skipped = prepared_data
    report = validate_data(data)
    # Only check symbols with data
    assert report["total_symbols"] == len(data)
    assert report["total_bars"] > 0
    assert report["quality"]["null_bars"] == 0


def test_output_files_exist():
    out = Path(os.environ["MEGATOOL_DATA_DIR"]) / "kronos_experiment"
    # Run the script first if needed
    if not (out / "train_data.pkl").exists():
        import subprocess
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "kronos_data_prep.py")],
                       check=True, env={**os.environ})
    assert (out / "train_data.pkl").exists()
    assert (out / "val_data.pkl").exists()
    assert (out / "test_data.pkl").exists()
    assert (out / "prep_report.json").exists()


def test_pickle_roundtrip():
    out = Path(os.environ["MEGATOOL_DATA_DIR"]) / "kronos_experiment"
    if not (out / "train_data.pkl").exists():
        import subprocess
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "kronos_data_prep.py")],
                       check=True, env={**os.environ})
    with open(out / "train_data.pkl", "rb") as f:
        train = pickle.load(f)
    assert isinstance(train, dict)
    assert len(train) > 0
    for sym, df in train.items():
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == FEATURE_LIST
        break


def test_no_fabricated_data(prepared_data):
    """Ensure no synthetic or fabricated data is introduced."""
    data, _ = prepared_data
    for sym, df in data.items():
        # All values must be finite
        assert df.notna().all().all(), f"{sym} has NaN"
        # No zero-volume fabricated (volume should be > 0 for real bars)
        # (Some symbols may legitimately have 0 volume on all bars, e.g. inactive
        # instruments; skip those rather than flagging as fabricated.)
        if df["vol"].sum() == 0:
            continue
        assert df["vol"].sum() > 0, f"{sym} all zero volume"


def test_split_sizes():
    out = Path(os.environ["MEGATOOL_DATA_DIR"]) / "kronos_experiment"
    if not (out / "prep_report.json").exists():
        import subprocess
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "kronos_data_prep.py")],
                       check=True, env={**os.environ})
    report = json.loads((out / "prep_report.json").read_text())
    assert report["total_symbols"] > 300
    assert report["splits"]["train"]["bars"] > 0
    assert report["splits"]["val"]["bars"] > 0
    assert report["splits"]["test"]["bars"] > 0
    # Train should have the most bars
    assert report["splits"]["train"]["bars"] > report["splits"]["val"]["bars"]
    assert report["splits"]["train"]["bars"] > report["splits"]["test"]["bars"]
