"""Shared test fixtures.

Every fixture here is SYNTHETIC and deterministic. Nothing in this directory is
real market data, and no test asserts anything about real NEPSE prices.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _isolate_databases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect BOTH databases to a throwaway directory for every test.

    A test that forgets to pass ``db_path`` would otherwise write synthetic
    rows into the owner's real ``data/processed/`` databases, mixing fixture
    data with genuine records. This guard makes that failure impossible
    instead of relying on every test remembering to pass a path.

    The application store is redirected through the supported
    ``MEGATOOL_APP_DB`` environment override rather than by replacing the
    property, so the override that read-only tooling depends on is itself
    exercised by the suite.
    """
    from megatool.config import APP_DB_ENV, Paths

    monkeypatch.setenv(APP_DB_ENV, str(tmp_path / "isolated_state.sqlite"))
    monkeypatch.setattr(
        Paths, "market_db", property(lambda self: tmp_path / "isolated_market.duckdb")
    )


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(20261011)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """An isolated SQLite file for a single test (never the owner's database)."""
    return tmp_path / "test_state.sqlite"


@pytest.fixture
def closes(rng: np.random.Generator) -> np.ndarray:
    """A deterministic, mildly trending daily close series."""
    steps = rng.normal(0.0005, 0.015, size=400)
    return 100.0 * np.exp(np.cumsum(steps))


@pytest.fixture
def ohlcv(rng: np.random.Generator, closes: np.ndarray) -> dict[str, np.ndarray]:
    """Synthetic OHLCV consistent with `closes` (high >= max(o,c), low <= min(o,c))."""
    n = len(closes)
    open_ = np.empty(n)
    open_[0] = closes[0]
    open_[1:] = closes[:-1] * (1 + rng.normal(0, 0.002, size=n - 1))
    span = np.abs(rng.normal(0, 0.01, size=n)) * closes
    high = np.maximum(open_, closes) + span
    low = np.minimum(open_, closes) - span
    low = np.clip(low, 0.5, None)
    volume = rng.integers(1_000, 200_000, size=n).astype(float)
    return {"open": open_, "high": high, "low": low, "close": closes, "volume": volume}


@pytest.fixture
def tiny() -> dict[str, np.ndarray]:
    """Small hand-checkable series used for exact-value assertions.

    close: 44.34 44.09 44.15 43.61 44.33 44.83 45.10 45.42 45.84 46.08
           45.89 46.03 45.61 46.28 46.28 46.00 46.03 46.41 46.22 45.64
    These are the first 20 closes of Wilder's own RSI worked example, which
    makes the RSI values checkable against the published reference.
    """
    close = np.array(
        [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
            46.00,
            46.03,
            46.41,
            46.22,
            45.64,
        ]
    )
    high = close + np.array([0.5] * len(close), dtype=float)
    low = close - np.array([0.5] * len(close), dtype=float)
    volume = np.full(len(close), 10_000.0)
    return {
        "open": close.copy(),
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }
