"""Volume profile over stored daily bars — a deterministic distribution.

WHAT IT IS
----------
A price-level histogram of volume: each session's volume is spread across the
price bins its ``low→high`` range touches, proportionally to the overlap
length. From the bin sums the module derives the known profile landmarks:

* **POC** (point of control) — the bin with the most volume; a tie resolves to
  the *lower* price, deterministically;
* **Value Area (70%)** — the classic two-sided expansion from the POC that
  keeps adding the larger-priced neighbour's bin until at least 70% of the
  session volume is enclosed; ``va_high``/``va_low`` are its outer edges;
* **HVN/LVN** — high-volume/local-peak and low-volume/local-trough bins under
  a strict neighbour comparison (a bin must exceed *both* neighbours to be a
  peak and undercut *both* to be a trough; plateaus are never flagged).

WHAT IT IS NOT
--------------
* Not an intraday profile. Daily bars are the only stored granularity, so each
  session's volume is assumed uniformly distributed across its range — coarse
  by construction and labelled as such in the output.
* Not a prediction. All landmarks describe the *selected window's past*
  distribution; none of them is a forecast, and the volume split is an
  allocation model, not an observation of where trades actually transacted.

Pure arithmetic on arrays the caller pro­vides — no IO, no caching.
"""

from __future__ import annotations

import math
from typing import Any

__all__ = ["ProfileError", "volume_profile", "ALLOCATION_MODEL"]

#: Shared description of how session volume is distributed across price bins.
ALLOCATION_MODEL = (
    "each session's volume is spread across the price bins its low→high range "
    "touches, proportional to each bin's overlap length (half-open "
    "convention); daily bars only — an allocation model, not observed trade "
    "distribution"
)


class ProfileError(ValueError):
    """Raised for inputs that cannot form a meaningful profile."""


def _validate(
    high: list[float],
    low: list[float],
    volume: list[float],
    bins: int,
) -> tuple[list[float], list[float], list[float]] | None:
    """Common validation; returns cleaned lists, or ``None`` with no data."""
    if bins < 2:
        raise ProfileError("bins must be >= 2 to form a profile")
    if not high:
        return None
    if not (len(high) == len(low) == len(volume)):
        raise ProfileError("high, low and volume must be the same length")
    clean_h, clean_l, clean_v = [], [], []
    for h, lo_price, v in zip(high, low, volume, strict=True):
        if not math.isfinite(h) or not (math.isfinite(lo_price)) or not math.isfinite(v):
            continue  # skip malformed rows rather than poisoning the histogram
        if v <= 0.0 or lo_price <= 0.0:
            continue  # a bar without volume or a nonpositive low cannot contribute
        clean_h.append(h)
        clean_l.append(lo_price)
        clean_v.append(v)
    return clean_h, clean_l, clean_v


def volume_profile(
    high: list[float],
    low: list[float],
    volume: list[float],
    bins: int = 48,
    *,
    value_area_pct: float = 0.70,
) -> dict[str, Any]:
    """Build the daily-bar volume profile over the supplied bars.

    ``high``/``low``/``volume`` must be equal-length lists; malformed rows
    (non-finite prices, non-positive volume) are skipped and counted, not
    estimated. ``bins`` is the price-bin count across the range
    ``[min(low), max(high)]``.
    """
    cleaned = _validate(high, low, volume, bins)
    if cleaned is None:
        raise ProfileError("no usable bars were supplied")
    clean_h, clean_l, clean_v = cleaned
    if not clean_h:
        raise ProfileError(
            "every supplied bar is unusable (non-finite prices or non-positive volume); "
            "no profile is estimated from zero volume"
        )

    round6 = lambda x: round(float(x), 6)  # noqa: E731
    least = min(clean_l)
    greatest = max(clean_h)
    if greatest <= 0.0:
        raise ProfileError("price range is nonpositive; cannot bin prices")
    span = greatest - least
    # every bar trades at one price: a one-bin profile is the honest shape
    bin_count = 1 if span <= 0.0 or math.isclose(span, 0.0) else min(max(int(bins), 2), 4096)

    width = span / bin_count if bin_count > 1 else 1.0
    sums = [0.0] * bin_count
    for h, lo_price, v in zip(clean_h, clean_l, clean_v, strict=True):
        if bin_count == 1:
            sums[0] += v
            continue
        lo_idx = int((lo_price - least) / width)
        # Half-open allocation: a bar's range [low, high) owns the bins its
        # interior overlaps, so a high exactly on a bin boundary does NOT
        # spill into the next bin (zero-length overlap = zero volume). An
        # exactly-at-range-end high still falls in the final bin because the
        # top bin is closed on the right.
        raw_hi = int((h - least) / width)
        if math.isclose((h - least) % width, 0.0) and (h - least) > 0:
            raw_hi -= 1
        hi_idx = raw_hi
        if h - least >= greatest - least:  # the top bin is closed on the right
            hi_idx = bin_count - 1
        lo_idx = max(0, min(bin_count - 1, lo_idx))
        hi_idx = max(lo_idx, min(bin_count - 1, hi_idx))
        if lo_idx == hi_idx or h <= lo_price:
            sums[lo_idx] += v  # single-price bar: one price, one bin
            continue
        # Proportional-to-overlap allocation: a bin's share is the length of
        # [low, high] inside that bin divided by the bar's full range.
        range_len = h - lo_price
        for k in range(lo_idx, hi_idx + 1):
            bin_lo = least + k * width
            overlap = min(h, bin_lo + width) - max(lo_price, bin_lo)
            if overlap > 0.0:
                sums[k] += v * (overlap / range_len)

    total = sum(sums)
    if bin_count == 1:
        # Every usable bar trades at one price; the honest profile is flat at
        # that price with nothing to expand.
        price = round(float(greatest), 6)
        return {
            "bins_count": 1,
            "total_volume": round6(total),
            "usable_bars": len(clean_h),
            "skipped_bars": len(high) - len(clean_h),
            "price_range": {"low": price, "high": price},
            "bin_width": 0.0,
            "poc": {
                "bin": 0,
                "price": price,
                "bin_low": price,
                "bin_high": price,
                "volume": round6(total),
                "volume_pct": 100.0 if total else None,
                "tie_policy": "not applicable (one bin)",
            },
            "value_area": {
                "high": price,
                "low": price,
                "volume_pct": 100.0 if total else None,
                "policy": "single-price window: nothing beyond the one traded price",
                "pct_requested": value_area_pct,
            },
            "high_volume_nodes": [],
            "low_volume_nodes": [],
            "hvn_rule": "not applicable (one bin)",
            "lvn_rule": "not applicable (one bin)",
            "allocation_model": ALLOCATION_MODEL,
        }

    poc_idx = max(range(bin_count), key=lambda k: (sums[k], -k))
    # --- value area: classic two-sided expansion from the POC ----------------
    target = total * max(0.0, min(1.0, value_area_pct))
    covered = sums[poc_idx]
    lptr, rptr = poc_idx, poc_idx
    while covered < target and (lptr > 0 or rptr < bin_count - 1):
        left_val = sums[lptr - 1] if lptr > 0 else -1.0
        right_val = sums[rptr + 1] if rptr < bin_count - 1 else -1.0
        if left_val >= right_val:
            lptr -= 1
            covered += left_val
        else:
            rptr += 1
            covered += right_val
    va_low_price = float(least + lptr * width)
    va_high_price = float(least + (rptr + 1) * width)

    # --- HVN / LVN: strict local peaks and troughs ---------------------------
    hvn: list[int] = []
    lvn: list[int] = []
    if bin_count >= 3:
        # Plateaus are skipped: a bin equal to a neighbour is neither peak nor
        # trough, so a multi-bin plateau is honestly unflagged.
        for k in range(1, bin_count - 1):
            v, left_v, right_v = sums[k], sums[k - 1], sums[k + 1]
            if v > left_v and v > right_v:
                hvn.append(k)
            elif v < left_v and v < right_v:
                lvn.append(k)

    def center(k: int) -> float:
        return float(least + (k + 0.5) * width)

    return {
        "bins_count": bin_count,
        "total_volume": round6(total),
        "usable_bars": len(clean_h),
        "skipped_bars": len(high) - len(clean_h),
        "price_range": {"low": round6(least), "high": round6(greatest)},
        "bin_width": round6(width),
        "poc": {
            "bin": poc_idx,
            "price": round6(center(poc_idx)),
            "bin_low": round6(float(least + poc_idx * width)),
            "bin_high": round6(float(least + (poc_idx + 1) * width)),
            "volume": round6(sums[poc_idx]),
            "volume_pct": round6(100.0 * sums[poc_idx] / total) if total else None,
            "tie_policy": "equal bins resolve to the lower price",
        },
        "value_area": {
            "high": round6(va_high_price),
            "low": round6(va_low_price),
            "volume_pct": round6(100.0 * covered / total) if total else None,
            "policy": (
                f"classic two-sided expansion from the POC until at least "
                f"{value_area_pct:.0%} of the window's volume is enclosed"
            ),
            "pct_requested": value_area_pct,
        },
        "high_volume_nodes": [round6(center(k)) for k in hvn],
        "low_volume_nodes": [round6(center(k)) for k in lvn],
        "hvn_rule": "strict local peak: bin volume exceeds both neighbours (plateaus skipped)",
        "lvn_rule": "strict local trough: bin volume undercuts both neighbours (plateaus skipped)",
        "allocation_model": ALLOCATION_MODEL,
    }
