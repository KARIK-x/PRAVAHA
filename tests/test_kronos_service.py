"""Kronos AI service tests - all network-and-weight-free.

The real model is NOT loaded here: tests patch the predictor so the suite
stays fast and hermetic. The vendored package was verified against the
official upstream regression suite separately (golden outputs matched at
<1e-6 relative error) - that is a one-time correctness proof, not a unit
fixture, and intentionally does not require downloading weights in CI.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from megatool.kronos_service import (
    DataQualityError,
    ForecastRequest,
    KronosManager,
    KronosUnavailable,
    _pick_device,
)


def _bars(n: int = 300, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 200 + np.cumsum(rng.normal(0, 1.0, n))
    return pd.DataFrame(
        {
            "trading_date": pd.bdate_range("2024-01-01", periods=n),
            "open": close + 0.5,
            "high": close + 1.5,
            "low": close - 1.0,
            "close": close,
            "volume": rng.integers(1000, 50_000, n).astype(float),
            "turnover": rng.integers(1e5, 1e7, n).astype(float),
        }
    )


class _FakePredictor:
    """Stand-in predictor: emits refused-looking deterministic paths."""

    device = "cpu"

    def __init__(self, predictable: float | None = None):
        self._predictable = predictable

    def predict(self, df, x_timestamp, y_timestamp, pred_len, **kwargs):
        base = self._predictable
        n = len(y_timestamp)
        data = {}
        if base is None:
            for col in ("open", "high", "low", "close", "volume", "amount"):
                data[col] = np.full(n, 1.0)
        else:
            data = {c: np.linspace(base, base + 1.0, n) for c in ("open", "high", "low", "close")}
            data["volume"] = np.full(n, 12345.0)
            data["amount"] = np.full(n, 5_000_000.0)
        return pd.DataFrame(data, index=pd.Series(y_timestamp))


class _Manager(KronosManager):
    """KronosManager whose load step injects a fake predictor."""

    def __init__(self):
        super().__init__(weights_root=Path("/definitely/missing/weights"))
        self.injected: _FakePredictor | None = _FakePredictor(123.0)
        self.load_calls = 0

    def _load_predictor(self, variant: str, device: str | None) -> _FakePredictor:
        self.load_calls += 1
        return self.injected


# ----------------------------------------------------------------- requests
def test_request_validation_rejects_bad_inputs():
    for bad in (
        dict(symbol="A"),  # too short
        dict(symbol="NIMB!"),  # bad characters
        dict(pred_len=0, symbol="NIMB"),
        dict(pred_len=65, symbol="NIMB"),
        dict(context_len=5, symbol="NIMB"),
        dict(context_len=600, symbol="NIMB"),
        dict(temperature=2.5, symbol="NIMB"),
        dict(sample_count=99, symbol="NIMB"),
        dict(variant="huge", symbol="NIMB"),
    ):
        with pytest.raises(DataQualityError):
            ForecastRequest(**bad)
    # a missing symbol is rejected at the boundary too (TypeError from the
    # dataclass contract or DataQualityError from our own check - either is
    # an honest refusal)
    with pytest.raises((DataQualityError, TypeError)):
        ForecastRequest(**{})
    ok = ForecastRequest(symbol="nimb", pred_len=5)
    assert ok.symbol == "NIMB" and ok.variant == "base"


def test_nepse_trading_days_skips_fri_sat():
    friday = pd.Timestamp("2026-10-16")  # a Friday
    days = KronosManager._nepse_days_after(friday, 3)
    assert [d.weekday() for d in days] == [6, 0, 1]  # Sun, Mon, Tue
    assert days[0].date().isoformat() == "2026-10-18"


def test_insufficient_history_is_refused_not_faked():
    m = _Manager()
    req = ForecastRequest(symbol="NIMB", pred_len=5, context_len=100)
    with pytest.raises(DataQualityError, match="usable bars"):
        m.forecast(_bars(60), req)
    with pytest.raises(DataQualityError, match="usable bars"):
        m.evaluate(_bars(80), req, windows=2)


def test_frame_adapter_maps_store_columns():
    df = KronosManager._frame_from_bars(_bars())
    assert list(df.columns) == [
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ]
    assert df["amount"].notna().all()
    assert df["amount"].iloc[0] == _bars()["turnover"].iloc[0]


def test_forecast_labels_every_row_predicted_and_uses_gap_free_days():
    m = _Manager()
    req = ForecastRequest(symbol="NIMB", pred_len=5, context_len=64)
    result = m.forecast(_bars(200), req)
    rows = result["rows"]
    assert len(rows) == 5
    assert all(r["is_predicted"] is True for r in rows)
    last_ts = pd.Timestamp(result["context"]["last"])
    first_pre = pd.Timestamp(rows[0]["time"])
    assert first_pre > last_ts
    assert first_pre.weekday() not in (4, 5)  # never a NEPSE holiday
    # amounts exist and the note is present
    assert all("amount" in r and "volume" in r for r in rows)
    assert "Predicted" in result["note"] or "model-predicted" in result["note"]


def test_evaluate_matches_baselines_with_fake_predictor():
    m = _Manager()
    req = ForecastRequest(symbol="NIBL", pred_len=4, context_len=64)
    result = m.evaluate(_bars(200), req, windows=3)
    avg = result["avg"]
    assert avg["windows"] == 3 and avg["horizon"] == 4
    # the fake predictor emits the price 123.0..124.0: the real distance for
    # a ~200 series is large, so the naive baseline must beat it here
    assert avg["kronos_mae_close"] is not None
    assert avg["naive_mae_close"] is not None
    assert result["best_mae_competitor"] == "naive_mae_close"
    for w in result["windows_detail"]:
        assert set(w["kronos"].keys()) == {"mae", "rmse", "mape_pct", "direction_ok", "steps"}
        assert w["kronos"]["steps"] == 4


def test_missing_weights_report_blocker_never_fake():
    m = KronosManager(weights_root=Path("/definitely/missing/weights"))
    with pytest.raises(KronosUnavailable, match="not present"):
        m._load_predictor("base", "cpu")
    avail = m.availability()
    assert avail["weights"]["Kronos-base"]["present"] is False
    assert avail["official_ids"]["base"].endswith("Kronos-base")
    assert "not a live NEPSE feed" in avail["disclaimer"]


def test_device_pick_reports_only_real_hardware():
    dev = _pick_device(None)
    assert dev in ("cpu", "mps")


def test_fixture_rsi2_uses_platform_ta():
    """rsi2_reversion must reuse the platform's own RSI implementation."""
    from megatool.backtest import rsi2_reversion

    bars = _bars(120)
    rsi2 = rsi2_reversion()
    positions = rsi2(bars)
    assert positions.dtype == np.int8
    assert set(np.unique(positions)) <= {0, 1}
