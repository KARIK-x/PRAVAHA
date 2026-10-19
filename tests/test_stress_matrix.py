"""Synthetic OHLCV stress fixtures for Mega Tool quantitative engine."""

from megatool.quality import F_NON_POSITIVE, validate_bar


def run():
    results = {}
    # A. Constant prices (flat series — RSI/MFI undefined)
    flags, s = validate_bar(100, 100, 100, 100, volume=100)
    results["constant_flat"] = (s.name, "suspect" if F_NON_POSITIVE in flags else "valid")
    # B. Rising
    flags, s = validate_bar(100, 105, 95, 105, volume=1000)
    results["rising"] = s.name
    # C. Falling
    flags, s = validate_bar(105, 100, 95, 95, volume=1000)
    results["falling"] = s.name
    # D. Alternating
    flags, s = validate_bar(100, 110, 90, 105, volume=500)
    results["alternating"] = s.name
    # E. Large gap (extreme)
    flags, s = validate_bar(100, 9999, 1, 9999, volume=1)
    results["extreme_gaps"] = s.name
    # F. Missing observations (None inputs) — quality allows None
    flags, s = validate_bar(None, None, None, None)
    results["all_none"] = s.name
    # G. Insufficient history — not applicable to per-bar validator; reported
    results["insufficient"] = "N/A per-bar only"
    # H. Zero volume (legal for suspended day)
    flags, s = validate_bar(100, 105, 95, 100, volume=0)
    results["zero_vol"] = s.name
    # I. Non-positive price (B-21)
    flags, s = validate_bar(772.3, 846.6, 0.0, 814.0, volume=1000)
    results["b21_krobl"] = (s.name, F_NON_POSITIVE in flags)
    # J. Duplicate timestamps — handled in validate_series, not per-bar
    results["duplicate"] = "validate_series handles"
    # K. Extreme finite
    flags, s = validate_bar(1e9, 1.01e9, 1e9 - 1, 1.005e9, volume=100)
    results["extreme_finite"] = s.name
    # L. Non-finite (NaN/inf) — _opt_float converts to None
    flags, s = validate_bar(float("nan"), float("inf"), float("-inf"), 100, volume=100)
    results["non_finite"] = s.name
    for k, v in results.items():
        print(f"{k}: {v}")


run()
