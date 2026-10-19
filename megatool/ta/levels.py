"""Support and resistance zones clustered from detected swing points.

Why this exists
---------------
The Master Specification (§14) asks for support/resistance built from actual
price structure — "a small number of defensible, inspectable price zones over
hundreds of meaningless horizontal lines". This module is that: it takes the
swing points from :mod:`megatool.ta.swings` and groups the ones that agree.

Clustering rule (documented, because the rule *is* the result)
-------------------------------------------------------------
1. Swings are sorted ascending by price.
2. A swing joins the current zone when its distance from the zone's running
   centre is within the tolerance; otherwise it starts a new zone.
3. The centre is recomputed as each swing joins (the running mean), so the
   order of processing is fixed by step 1 and the output is deterministic.

The tolerance is the *only* judgement in the method, and it is exposed::

    tolerance_mode = "price"   tolerance = tolerance_frac * reference_price
    tolerance_mode = "atr"     tolerance = atr_multiple * ATR

``"price"`` is a fixed fraction of price; ``"atr"`` scales with recent
volatility so wide-zoned periods get wider zones. Mixing unrelated levels
never happens silently — a level either fits inside the stated tolerance or it
opens a new zone.

What a zone is *not*
--------------------
A zone is a price band that repeated turning points happened to occupy. It is
not order-book liquidity, not institutional accumulation, and not a promise
that the band will hold (§32.2, §32.7). ``touches`` and ``swing_count`` are
raw counts of historical events, never a confidence percentage.

Result label
------------
**DETECTED** — candidate zones found by the explicit rule above.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from megatool.ta.swings import Swing

__all__ = ["Zone", "ZonesError", "build_zones"]

#: Method identifier and version, reported with every result so a later
#: change to the clustering rule cannot silently rewrite old numbers.
METHOD = "swing-cluster"
VERSION = "1.0"


class ZonesError(ValueError):
    """Raised when the inputs cannot produce a meaningful zone analysis."""


@dataclass(slots=True)
class Zone:
    """One clustered price band."""

    lower: float
    upper: float
    center: float
    swing_indices: list[int] = field(default_factory=list)
    swing_prices: list[float] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    reactions: int = 0
    strength: float = 0.0

    @property
    def width(self) -> float:
        return self.upper - self.lower

    @property
    def span(self) -> float:
        """Fractional width of the zone against its centre."""
        return 0.0 if self.center == 0 else self.width / self.center

    def to_dict(self) -> dict[str, Any]:
        return {
            "lower": round(self.lower, 4),
            "upper": round(self.upper, 4),
            "center": round(self.center, 4),
            "width": round(self.width, 4),
            "span": round(self.span, 6),
            "reactions": self.reactions,
            "strength": round(self.strength, 2),
            "swing_count": len(self.swing_indices),
            "swing_indices": list(self.swing_indices),
            "swing_prices": [round(p, 4) for p in self.swing_prices],
            "kinds": list(self.kinds),
        }


def _finite(values: Any, name: str) -> list[float]:
    """Flatten to a list of floats, rejecting anything non-finite."""
    out: list[float] = []
    for v in values:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            raise ZonesError(f"`{name}` must contain only finite values")
        out.append(f)
    return out


def build_zones(
    swings: list[Swing],
    close: Any = (),
    tolerance_frac: float = 0.01,
    tolerance_mode: str = "price",
    atr_multiple: float = 1.0,
    atr: Any = (),
    min_touches: int = 1,
) -> dict[str, Any]:
    """Cluster swing points into support/resistance zones.

    Parameters
    ----------
    swings
        Output of :func:`megatool.ta.swings.find_swings`.
    close
        Closing prices, used only to report each zone's distance from the
        latest available close. Empty is allowed.
    tolerance_frac
        Fraction of price that defines "nearby" when ``tolerance_mode``
        is ``"price"``.
    tolerance_mode
        ``"price"`` (fraction of price) or ``"atr"`` (``atr_multiple`` ATR).
    atr, atr_multiple
        Average true range series and its multiplier, for ``"atr"`` mode.
    min_touches
        Zones supported by fewer distinct swings than this are dropped from
        the *primary* zone list (they are still reported as ``excluded``), so
        a single isolated pivot cannot masquerade as a tested level.

    Returns
    -------
    dict
        Zones, excluded zones, method/version, tolerance actually used, the
        data period, the distance from the latest close, and warnings. Sorted
        by centre price ascending so the chart can place them deterministically.
    """
    if tolerance_frac <= 0:
        raise ZonesError("`tolerance_frac` must be positive")
    if tolerance_mode not in {"price", "atr"}:
        raise ZonesError("`tolerance_mode` must be 'price' or 'atr'")
    if atr_multiple <= 0:
        raise ZonesError("`atr_multiple` must be positive")
    if min_touches < 1:
        raise ZonesError("`min_touches` must be at least 1")
    if not swings:
        # Honest empty answer, not an error: no pivots met the swing rules.
        return {
            "zones": [],
            "excluded": [],
            "method": METHOD,
            "method_version": VERSION,
            "params": {
                "tolerance_mode": tolerance_mode,
                "tolerance_frac": tolerance_frac,
                "atr_multiple": atr_multiple,
                "min_touches": min_touches,
            },
            "tolerance": None,
            "tolerance_note": "no zones, so no tolerance applied",
            "latest_close": None,
            "warnings": ["No swing points met the detection rules, so no zones exist."],
            "interpretation": "detected",
        }

    closes = _finite(close, "close")
    atrs = _finite(atr, "atr")

    # A non-finite swing price would silently poison every zone it joined, so
    # it is rejected up front rather than averaged into a boundary.
    for s in swings:
        if s.price != s.price or s.price in (float("inf"), float("-inf")):
            raise ZonesError(f"swing price must be finite, got {s.price!r}")
        if s.index < 0:
            raise ZonesError(f"swing index must be non-negative, got {s.index}")

    # Sort by price so clustering order — and therefore the output — is fixed.
    ordered = sorted(swings, key=lambda s: s.price)

    warnings: list[str] = []

    # The reference for the tolerance is each zone's running centre. In ATR
    # mode we need a representative ATR; a missing/short series falls back to
    # price mode rather than inventing a volatility number.
    use_atr = tolerance_mode == "atr" and bool(atrs) and not all(a <= 0 for a in atrs)
    if tolerance_mode == "atr" and not use_atr:
        warnings.append(
            "ATR tolerance requested but no usable ATR series was supplied; "
            "fell back to a fixed price-fraction tolerance."
        )
    ref_atr = 0.0
    if use_atr:
        finite_atr = [a for a in atrs if a > 0]
        ref_atr = max(finite_atr) if finite_atr else 0.0
        if ref_atr <= 0:
            use_atr = False
            warnings.append("ATR series contained no positive values; fell back to price mode.")

    def tolerance_for(reference: float) -> float:
        if use_atr:
            return atr_multiple * ref_atr
        return tolerance_frac * abs(reference)

    zones: list[Zone] = []
    for swing in ordered:
        tol = tolerance_for(swing.price)
        if zones:
            current = zones[-1]
            if abs(swing.price - current.center) <= tol:
                current.swing_indices.append(swing.index)
                current.swing_prices.append(swing.price)
                current.kinds.append(swing.kind)
                # Running mean keeps the centre anchored to its members.
                current.center = sum(current.swing_prices) / len(current.swing_prices)
                current.lower = min(current.lower, swing.price)
                current.upper = max(current.upper, swing.price)
                continue
        zones.append(
            Zone(
                lower=swing.price,
                upper=swing.price,
                center=swing.price,
                swing_indices=[swing.index],
                swing_prices=[swing.price],
                kinds=[swing.kind],
            )
        )

    total_bars = len(closes) if closes else 0
    for zone in zones:
        zone.reactions = len(zone.swing_indices)
        # Transparent strength score (0-100):
        #   * touch count: up to 60 (20 per distinct touch, capped at 3)
        #   * recency: +20 if the most recent touch is in the last 20% of bars,
        #              +10 if in the last 40%
        # Touch count and recency only — no reaction-magnitude or volume claim,
        # because those need data this module does not receive.
        touch_score = min(60.0, zone.reactions * 20.0)
        recency = 0.0
        if total_bars > 0 and zone.swing_indices:
            latest_touch = max(zone.swing_indices)
            age_frac = 1.0 - (latest_touch / max(1, total_bars - 1))
            if age_frac <= 0.2:
                recency = 20.0
            elif age_frac <= 0.4:
                recency = 10.0
        zone.strength = touch_score + recency

    # A lone pivot is a point, not a tested level. Keep it visible but out of
    # the primary list rather than pretending it was respected repeatedly.
    kept = [z for z in zones if z.reactions >= min_touches]
    excluded = [z for z in zones if z.reactions < min_touches]

    latest_close = closes[-1] if closes else None
    # In price mode the tolerance is `tolerance_frac * zone centre`, so there is
    # no single absolute number and inventing one would mislead. ATR mode is a
    # genuine constant, so it is reported as an absolute.
    if use_atr:
        tolerance_value: float | None = round(atr_multiple * ref_atr, 6)
        tolerance_note = f"constant: {atr_multiple} x ATR"
    else:
        tolerance_value = None
        tolerance_note = (
            f"varies per zone as tolerance_frac ({tolerance_frac}) x that zone's "
            "centre price; no single absolute applies"
        )

    rows: list[dict[str, Any]] = []
    for zone in sorted(kept, key=lambda z: z.center):
        row = zone.to_dict()
        if latest_close is not None:
            # Signed distance: negative means the zone sits below the last
            # close (a support side), positive means above (resistance side).
            row["distance_from_latest_close"] = round(latest_close - zone.center, 4)
            row["distance_pct"] = (
                round((latest_close - zone.center) / latest_close * 100, 4)
                if latest_close
                else None
            )
            row["side"] = (
                "support"
                if zone.center < latest_close
                else "resistance"
                if zone.center > latest_close
                else "at_close"
            )
        else:
            row["distance_from_latest_close"] = None
            row["distance_pct"] = None
            row["side"] = "unknown"
        rows.append(row)

    excluded_rows = [z.to_dict() for z in sorted(excluded, key=lambda z: z.center)]
    if excluded:
        warnings.append(
            f"{len(excluded)} zone(s) supported by fewer than {min_touches} "
            "distinct swing(s) were excluded from the primary list."
        )
    if latest_close is None:
        warnings.append("No closing prices supplied, so distance from latest close is unknown.")

    return {
        "zones": rows,
        "excluded": excluded_rows,
        "method": METHOD,
        "method_version": VERSION,
        "params": {
            "tolerance_mode": "atr" if use_atr else "price",
            "tolerance_frac": tolerance_frac,
            "atr_multiple": atr_multiple,
            "min_touches": min_touches,
        },
        "tolerance": tolerance_value,
        "tolerance_note": tolerance_note,
        "latest_close": round(float(latest_close), 4) if latest_close is not None else None,
        "counts": {"total": len(zones), "reported": len(rows), "excluded": len(excluded_rows)},
        "warnings": warnings,
        "interpretation": "detected",
        "caveats": [
            "Zones are price bands that repeated detected swing points occupied; "
            "they are not order-book liquidity and not a guarantee any band will hold.",
            "Zone membership depends on the stated tolerance; a different tolerance "
            "gives different, equally defensible zones.",
            "Prices are unadjusted for bonus/split issues, so a zone may reflect a "
            "corporate action rather than trading behaviour.",
        ],
    }
