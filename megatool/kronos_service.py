"""Kronos AI service - real inference with the OFFICIAL model, on stored bars.

Kronos (https://github.com/shiyu-coder/Kronos, MIT licence) is a financial
time-series foundation model: a tokenizer plus an autoregressive transformer
trained on millions of daily candles. Its published checkpoint predicts a
future candle path conditioned on a window of past OHLC + volume + amount.
It is a *forecast generator*, not a live feed: every output here is labelled
as predicted and is measured against data a walk-forward evaluation is
entitled to see.

Integration notes
-----------------
- The official ``model`` package is vendored verbatim under ``vendor/kronos``
  (its MIT licence file sits alongside) and imported exactly as upstream
  documents: ``from model import Kronos, KronosPredictor, KronosTokenizer``.
- Weights are the official ``NeoQuasar/`` repositories downloaded into
  ``data/models/`` and loaded from the local directory - no runtime network.
- Models load lazily, one variant resident at a time (mini/small/base) so the
  process never holds two large models simultaneously.
- Decoding defaults to nucleus sampling (``top_k=0``, ``top_p=0.9``, ``T=1.0``),
  which is reproducible-ish and avoids the autoregressive collapse that greedy
  (``top_k=1``) produced. Set ``sample_count`` > 1 only for experimentation
  (averaging flattens the forecast further).

Honesty rules enforced here
---------------------------
- Predictions carry ``is_predicted``; their timestamps are strictly after the
  last observed bar and land on valid NEPSE trading days (Sun-Thu).
- Nothing is invented for insufficient history: a data-quoted error is raised
  instead, and the caller renders an honest state for it.
- The evaluation walks chronologically and never looks beyond each window's
  anchor; baselines see exactly the context Kronos sees.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VENDOR_ROOT = Path(__file__).resolve().parent.parent / "vendor" / "kronos"
WEIGHTS_ROOT = Path(__file__).resolve().parent.parent / "data" / "models"

# Official per-variant limits (upstream model zoo, README table):
#   Kronos-mini  ← Kronos-Tokenizer-2k, context 2048, 4.1M params
#   Kronos-small ← Kronos-Tokenizer-base, context 512, 24.7M
#   Kronos-base  ← Kronos-Tokenizer-base, context 512, 102.3M
MAX_CONTEXT = 512
VARIANT_MAX_CONTEXT = {"mini": 2048, "small": 512, "base": 512}
DEFAULT_CONTEXT = 256
PRICE_COLS = ("open", "high", "low", "close", "volume", "amount")

# official Hugging Face ids (upstream README); disk folders hold the downloaded
# weights under data/models/<folder>, mirroring the official names.
OFFICIAL_IDS = {
    "mini": "NeoQuasar/Kronos-mini",
    "small": "NeoQuasar/Kronos-small",
    "base": "NeoQuasar/Kronos-base",
    "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
}
_OFFICIAL_TOKENIZERS = {
    "mini": "Kronos-Tokenizer-2k",
    "small": "Kronos-Tokenizer-base",
    "base": "Kronos-Tokenizer-base",
    None: "Kronos-Tokenizer-base",
}
_WEIGHT_DIRS = {
    "mini": "Kronos-mini",
    "small": "Kronos-small",
    "base": "Kronos-base",
    None: "Kronos-Tokenizer-base",
}


class KronosUnavailable(RuntimeError):
    """The official model is missing (weights / deps / package) - never faked."""


class DataQualityError(RuntimeError):
    """The stored history cannot honestly supply the requested forecast."""


@dataclass
class ForecastRequest:
    symbol: str
    pred_len: int = 10
    context_len: int = DEFAULT_CONTEXT
    variant: str = "base"
    temperature: float = 1.0
    sample_count: int = 1

    def __post_init__(self) -> None:
        self.variant = (self.variant or "base").strip().lower()
        if self.variant not in OFFICIAL_IDS:
            raise DataQualityError(
                f"unknown model variant {self.variant!r}; expected one of mini/small/base"
            )
        if not 1 <= int(self.pred_len) <= 64:
            raise DataQualityError("pred_len must be 1..64 predicted daily candles")
        self.pred_len = int(self.pred_len)
        # Per-variant official context limit: mini supports 2048 context bars
        # (Kronos-Tokenizer-2k), small/base max 512. Validated HERE, not just
        # in the UI, so the configuration is enforced server-side too.
        ctx_limit = VARIANT_MAX_CONTEXT.get(self.variant, MAX_CONTEXT)
        if not 12 <= int(self.context_len) <= ctx_limit:
            raise DataQualityError(
                f"context_len must be 12..{ctx_limit} for variant {self.variant}"
            )
        self.context_len = int(self.context_len)
        self.symbol = str(self.symbol).strip().upper()
        if len(self.symbol) < 2 or not re.fullmatch(r"[A-Z0-9&]+", self.symbol):
            raise DataQualityError(f"invalid NEPSE symbol {self.symbol!r}")
        temp = float(self.temperature)
        if not 0.0 < temp <= 2.0:
            raise DataQualityError("temperature must be in (0, 2]")
        self.temperature = temp
        if not 1 <= int(self.sample_count) <= 16:
            raise DataQualityError("sample_count must be 1..16")
        self.sample_count = int(self.sample_count)


def _pick_device(requested: str | None) -> str:
    """MPS on Apple silicon, else CPU. Never claims hardware that is absent."""
    import torch

    if requested == "cpu":
        return "cpu"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _import_torch():
    if importlib.util.find_spec("torch") is None:
        raise KronosUnavailable("torch is not installed in this venv; inference unavailable")
    import torch

    return torch


class KronosManager:
    """Loads official weights lazily; one variant resident at a time."""

    def __init__(self, weights_root: Path | None = None) -> None:
        self._weights_root = weights_root or WEIGHTS_ROOT
        self._lock = threading.Lock()
        self._loaded_variant: str | None = None
        self._predictor: Any = None
        self._load_seconds: float | None = None

    # -- availability -----------------------------------------------------

    def availability(self) -> dict[str, Any]:
        """What exists in the environment and on disk. No inference is run."""
        folders = (
            "Kronos-mini",
            "Kronos-small",
            "Kronos-base",
            "Kronos-Tokenizer-base",
            "Kronos-Tokenizer-2k",
        )
        weights: dict[str, Any] = {}
        for folder in folders:
            d = self._weights_root / folder
            weights[folder] = {
                "present": (d / "model.safetensors").is_file() and (d / "config.json").is_file(),
                "bytes": (d / "model.safetensors").stat().st_size
                if (d / "model.safetensors").is_file()
                else 0,
            }
        return {
            "torch_installed": importlib.util.find_spec("torch") is not None,
            "einops_installed": importlib.util.find_spec("einops") is not None,
            "weights_root": str(self._weights_root),
            "weights": weights,
            "loaded_variant": self._loaded_variant,
            "load_seconds": self._load_seconds,
            "device_selected": self._safe_device(),
            "max_context": MAX_CONTEXT,
            # per-variant official context limits + the tokenizer each variant
            # is documented to require (upstream model zoo). The UI maps these
            # limits; the backend validates them independently of the UI.
            "variant_max_context": VARIANT_MAX_CONTEXT,
            "variant_tokenizer": _OFFICIAL_TOKENIZERS,
            "official_repo": "https://github.com/shiyu-coder/Kronos",
            "official_ids": OFFICIAL_IDS,
            "disclaimer": (
                "Kronos forecasts future candle paths from stored daily OHLCV history; "
                "it is not a live NEPSE feed and never replaces observed prices."
            ),
        }

    def _safe_device(self) -> str:
        try:
            _import_torch()
            return _pick_device(None)
        except KronosUnavailable:
            return "unavailable"

    # -- loading ----------------------------------------------------------

    def _load_predictor(self, variant: str, device: str | None) -> Any:
        with self._lock:
            if self._loaded_variant == variant and self._predictor is not None:
                return self._predictor
            if not (VENDOR_ROOT / "model" / "kronos.py").is_file():
                raise KronosUnavailable(f"official vendored model package missing at {VENDOR_ROOT}")
            weights = self._weights_root / _WEIGHT_DIRS[variant]
            if not (weights / "model.safetensors").is_file():
                raise KronosUnavailable(
                    f"official {OFFICIAL_IDS[variant]} weights not present under {weights}; "
                    "download them from Hugging Face - sample outputs are never substituted."
                )
            torch = _import_torch()
            if VENDOR_ROOT not in sys.path:
                sys.path.insert(0, str(VENDOR_ROOT))
            # upstream import contract
            for stale in ("model", "model.module", "model.kronos"):
                sys.modules.pop(stale, None)
            from model import Kronos, KronosPredictor, KronosTokenizer

            dev = _pick_device(device)
            # drop the previously resident variant BEFORE loading the next one
            self._predictor = None
            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
            t0 = time.perf_counter()
            # Each variant is paired with its own OFFICIAL tokenizer (model zoo):
            # mini pairs with Kronos-Tokenizer-2k, small/base with the base
            # tokenizer. Loading mini against the base tokenizer would be a
            # silent misconfiguration, not "Mini working".
            tokenizer = KronosTokenizer.from_pretrained(
                str(self._weights_root / _OFFICIAL_TOKENIZERS[variant])
            )
            model = Kronos.from_pretrained(str(weights)).eval()
            predictor = KronosPredictor(
                model, tokenizer, device=dev, max_context=VARIANT_MAX_CONTEXT[variant]
            )
            self._load_seconds = round(time.perf_counter() - t0, 3)
            self._loaded_variant = variant
            self._predictor = predictor
            return self._predictor

    def unload(self) -> dict[str, Any]:
        """Release the resident model (weights stay on disk)."""
        with self._lock:
            self._predictor = None
            self._loaded_variant = None
            try:
                torch = _import_torch()
                if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                    torch.mps.empty_cache()
            except KronosUnavailable:
                pass
        return {"loaded_variant": None, "note": "model unloaded; reload on next forecast"}

    # -- data shaping -----------------------------------------------------

    @staticmethod
    def _frame_from_bars(bars: Any) -> Any:
        """Adapt the store's daily bars to Kronos' exact six-feature frame."""
        import pandas as pd

        df = bars.copy()
        low = {c.lower(): c for c in df.columns}
        time_col = next((low[k] for k in ("time", "trading_date", "date") if k in low), None)
        if time_col is None:
            raise DataQualityError("bar frame has no date column (time/trading_date/date)")
        # the store publishes the value column as `turnover`; Kronos expects
        # `amount`. Accept either name; never invent the value.
        if "amount" not in low and "turnover" in low:
            df = df.rename(columns={low["turnover"]: "amount"})
            low = {c.lower(): c for c in df.columns}
        missing = [c for c in PRICE_COLS if c not in low]
        if missing:
            raise DataQualityError(f"bar frame lacks required columns: {missing}")
        keep = [time_col] + [low[c] for c in PRICE_COLS]
        df = df[keep].copy()
        df.columns = ["time"] + list(PRICE_COLS)
        df["time"] = pd.to_datetime(df["time"])
        df = df.sort_values("time").reset_index(drop=True)
        return df

    @staticmethod
    def _nepse_days_after(last: Any, n: int) -> list[Any]:
        """n projected NEPSE trading days after ``last``: closed Fri (4) & Sat (5)."""
        import pandas as pd

        nxt = last
        out: list[Any] = []
        while len(out) < n:
            nxt += pd.Timedelta(days=1)
            if nxt.weekday() in (4, 5):
                continue
            out.append(nxt)
        return out

    # -- forecasting ------------------------------------------------------

    def forecast(
        self,
        bars: Any,
        req: ForecastRequest,
        device: str | None = None,
    ) -> dict[str, Any]:
        """Produce REAL Kronos inference output for one symbol's stored bars.

        ``bars`` is a chronologically ascending frame (market-store ``get_bars``
        output). Nothing fetches from the network here; only the caller-provided
        history plus the official weights are used.
        """
        import pandas as pd
        import torch

        df = self._frame_from_bars(bars)
        df = df.dropna(subset=list(PRICE_COLS)).reset_index(drop=True)
        if len(df) < req.context_len:
            raise DataQualityError(
                f"{req.symbol}: need at least {req.context_len} usable bars, have {len(df)}"
                + (
                    f" (history only spans {df['time'].iloc[0]:%Y-%m-%d})"
                    if len(df)
                    else " (history is empty)"
                )
            )
        context = df.iloc[-req.context_len :].reset_index(drop=True)
        x_ts = context["time"]
        future_ts = pd.Series(self._nepse_days_after(x_ts.iloc[-1], req.pred_len), name="time")
        y_ts = future_ts

        predictor = self._load_predictor(req.variant, device)
        t0 = time.perf_counter()
        with torch.no_grad():
            pred = predictor.predict(
                df=context.drop(columns=["time"]).reset_index(drop=True),
                x_timestamp=x_ts.reset_index(drop=True),
                y_timestamp=y_ts,
                pred_len=req.pred_len,
                T=req.temperature,
                top_k=0,
                top_p=0.9,
                sample_count=req.sample_count,
                verbose=False,
            )
        infer_seconds = round(time.perf_counter() - t0, 3)

        pred = pred.reset_index(drop=True)
        rows = []
        for i, ts in enumerate(y_ts):
            rows.append(
                {
                    "time": ts.strftime("%Y-%m-%d"),
                    "open": round(float(pred["open"].iloc[i]), 2),
                    "high": round(float(pred["high"].iloc[i]), 2),
                    "low": round(float(pred["low"].iloc[i]), 2),
                    "close": round(float(pred["close"].iloc[i]), 2),
                    "volume": round(float(pred["volume"].iloc[i]), 0),
                    "amount": round(float(pred["amount"].iloc[i]), 0),
                    "is_predicted": True,
                    "step": i + 1,
                }
            )
        return {
            "symbol": req.symbol,
            "variant": req.variant,
            "device": str(predictor.device),
            "context": {
                "bars": len(context),
                "first": x_ts.iloc[0].strftime("%Y-%m-%d"),
                "last": x_ts.iloc[-1].strftime("%Y-%m-%d"),
                "last_close": round(float(context["close"].iloc[-1]), 2),
            },
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "sample_count": req.sample_count,
            "temperature": req.temperature,
            "inference_seconds": infer_seconds,
            "load_seconds": self._load_seconds,
            "rows": rows,
            "note": (
                "All rows above are model-predicted candles (is_predicted=true); "
                "their timestamps follow the last stored bar. They are not observed "
                "NEPSE trades and must never be charted as history."
            ),
        }

    # -- evaluation -------------------------------------------------------

    def evaluate(
        self,
        bars: Any,
        req: ForecastRequest,
        windows: int = 6,
        device: str | None = None,
    ) -> dict[str, Any]:
        """Chronological walk-forward: Kronos vs honest baselines. No leakage.

        Window anchors are spaced ``pred_len`` apart so no realized day serves
        as the target of two windows; each anchor's realized range ends
        strictly after its own last context day, and context never extends
        into the anchor's future.
        """
        import numpy as np
        import torch

        df = self._frame_from_bars(bars)
        df = df.dropna(subset=list(PRICE_COLS)).reset_index(drop=True)
        need = req.context_len + req.pred_len
        if len(df) < need:
            raise DataQualityError(
                f"{req.symbol}: a {req.context_len}-day context + {req.pred_len}-day horizon "
                f"needs {need} usable bars, have {len(df)}"
            )
        starts = sorted(set(range(len(df) - req.pred_len, req.context_len, -req.pred_len)))[
            : max(1, int(windows))
        ]

        predictor = self._load_predictor(req.variant, device)
        per: list[dict[str, Any]] = []
        total0 = time.perf_counter()
        for s in starts:
            context = df.iloc[s - req.context_len : s].reset_index(drop=True)
            realized = df.iloc[s : s + req.pred_len].reset_index(drop=True)
            x_ts = context["time"]
            r_close = realized["close"].to_numpy(np.float32)
            t0 = time.perf_counter()
            with torch.no_grad():
                pred = predictor.predict(
                    df=context.drop(columns=["time"]).reset_index(drop=True),
                    x_timestamp=x_ts.reset_index(drop=True),
                    y_timestamp=realized["time"],
                    pred_len=req.pred_len,
                    T=req.temperature,
                    top_k=0,
                    top_p=0.9,
                    sample_count=1,
                    verbose=False,
                )
            infer = round(time.perf_counter() - t0, 3)
            k_close = pred["close"].to_numpy(np.float32)
            last_close = float(context["close"].iloc[-1])
            naive = np.full_like(r_close, last_close)
            drift = last_close + float(
                np.mean(np.diff(context["close"].tail(20).to_numpy(np.float32)))
            ) * np.arange(1, len(r_close) + 1)
            per.append(
                {
                    "anchor": x_ts.iloc[-1].strftime("%Y-%m-%d"),
                    "realized_span": (
                        f"{realized['time'].iloc[0]:%Y-%m-%d} to "
                        f"{realized['time'].iloc[-1]:%Y-%m-%d}"
                    ),
                    "inference_seconds": infer,
                    "kronos": {
                        "mae": round(float(np.mean(np.abs(k_close - r_close))), 4),
                        "rmse": round(float(np.sqrt(np.mean((k_close - r_close) ** 2))), 4),
                        "mape_pct": round(
                            float(
                                np.mean(np.abs(k_close - r_close) / np.maximum(r_close, 1e-9)) * 100
                            ),
                            3,
                        ),
                        "direction_ok": int(
                            np.sum(
                                np.sign(np.diff(np.concatenate(([last_close], k_close))))
                                == np.sign(np.diff(np.concatenate(([last_close], r_close))))
                            )
                        ),
                        "steps": len(r_close),
                    },
                    "naive_last_close": {"mae": round(float(np.mean(np.abs(naive - r_close))), 4)},
                    "drift20": {"mae": round(float(np.mean(np.abs(drift - r_close))), 4)},
                }
            )
        if not per:
            raise DataQualityError(
                "no usable walk-forward windows (contexts contain broken candles)"
            )

        def agg(section: str, field: str) -> float | None:
            vals = [w[section][field] for w in per if section in w and field in w[section]]
            return round(float(np.mean(vals)), 4) if vals else None

        avg = {
            "kronos_mae_close": agg("kronos", "mae"),
            "kronos_rmse_close": agg("kronos", "rmse"),
            "kronos_mape_pct": agg("kronos", "mape_pct"),
            "kronos_direction_pct": round(
                100
                * sum(w["kronos"]["direction_ok"] for w in per)
                / max(1, sum(int(w["kronos"]["steps"]) for w in per)),
                2,
            ),
            "naive_mae_close": agg("naive_last_close", "mae"),
            "drift20_mae_close": agg("drift20", "mae"),
            "windows": len(per),
            "horizon": req.pred_len,
            "total_seconds": round(time.perf_counter() - total0, 2),
        }
        comparison = {
            k: avg[k]
            for k in ("kronos_mae_close", "naive_mae_close", "drift20_mae_close")
            if avg[k] is not None
        }
        return {
            "symbol": req.symbol,
            "variant": req.variant,
            "device": str(predictor.device),
            "context_len": req.context_len,
            "horizon": req.pred_len,
            "avg": avg,
            "best_mae_competitor": min(comparison, key=comparison.get) if comparison else None,
            "windows_detail": per,
            "note": (
                "Walk-forward research measurement on stored history. Lower MAE is better; "
                "direction% is next-day up/down agreement, not tradable alpha. Actual candles "
                "used for scoring are labeled by their own dates in each window."
            ),
        }


_MANAGER = KronosManager()


def get_manager() -> KronosManager:
    return _MANAGER
