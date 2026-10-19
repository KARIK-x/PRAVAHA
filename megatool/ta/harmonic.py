"""Harmonic XABCD pattern candidates (Master Specification §7 / Section 13).

Why this exists
---------------
The specification marks harmonic patterns as mandatory, and the requirements
register recorded them as ``NOT IMPLEMENTED — needs XABCD ratio definitions``.
Task T-28 states that no owner decision is needed to start this work — only
that output must be framed as *candidates with evidence and invalidation,
never asserted signals*. This module supplies the ratio definitions and that
framing.

Ratio definitions
-----------------
The five patterns and their bands follow the canonical harmonic construction
popularised by Scott Carney (*The Harmonic Trader* / *The Definitive Guide to
Harmonic Patterns*) — the most widely published table of these definitions:

===========  ==================================================================
Pattern      Defining constraints (measured on confirmed swings only)
===========  ==================================================================
Gartley      AB/XA 0.500–0.700 (0.618), BC/AB 0.382–0.886,
           CD/BC 1.130–1.618, completion of XA 0.720–0.840 (0.786 retracement)
Bat           AB/XA 0.330–0.500, BC/AB 0.382–0.886,
           CD/BC 1.618–2.618, completion of XA 0.840–0.930 (0.886 retracement)
Butterfly     AB/XA 0.730–0.830 (0.786), BC/AB 0.382–0.886,
           CD/BC 1.618–2.240, completion of XA 1.150–1.450 (1.27 external,
           i.e. D completes *beyond* X)
Crab          AB/XA 0.382–0.618, BC/AB 0.382–0.886,
           CD/BC 2.240–3.618, completion of XA 1.500–1.780 (1.618 external)
Cypher       AB/XA 0.382–0.618, BC/AB 1.130–1.414 (BC extends past AB),
           DC/XC 0.680–0.860 (0.786 of XC)
===========  ==================================================================

``completion`` is the signed ratio ``(A − D) / (A − X)``: values in (0, 1)
mean D retraces inside the XA leg; values > 1 mean D completes beyond X
(the defining trait of Butterfly/Crab); a negative value (D beyond A) can
never match any band, which rules out the degenerate geometry explicitly.

These are literature conventions — not owner-supplied data, not validated
predictions. Every candidate therefore carries ``certainty="low"``, its
measured ratios, the exact band it matched, an invalidation price level, and
an uncertainty note. Honesty rules:

* **Confirmed swings only** — point D must be knowable when the candidate is
  reported (same look-ahead rule as :mod:`megatool.ta.elliott`).
* **Candidates, not signals** — nothing here claims predictive power.
* **No fabrication** — degenerate legs (zero-length AB, equal anchors) make
  the window unmeasurable and are skipped, never approximated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

METHOD = "harmonic_xabcd_v1.0"
UNCERTAINTY = (
    "Ratio bands are published literature conventions — a match is a candidate "
    "structure, not a guaranteed prediction"
)

#: Human labels for each measured ratio, as reported to callers.
MEASURE_LABELS: dict[str, str] = {
    "ab_xa": "AB/XA",
    "bc_ab": "BC/AB",
    "cd_bc": "CD/BC",
    "dc_xc": "DC/XC",
    "completion": "completion_of_XA",
}


@dataclass(frozen=True, slots=True)
class Constraint:
    """One ratio band a pattern must satisfy. ``target`` names the published value."""

    measure: str
    lo: float
    hi: float
    target: str


@dataclass(frozen=True, slots=True)
class HarmonicSpec:
    """One harmonic pattern definition: name, bands, and completion base."""

    name: str
    constraints: tuple[Constraint, ...]
    completion_base: str  # e.g. "XA retracement" / "XC retracement"


def _completion_constraint(spec: HarmonicSpec) -> Constraint | None:
    """The band that anchors the invalidation price (completion, else DC/XC)."""
    for c in spec.constraints:
        if c.measure in ("completion", "dc_xc"):
            return c
    return None


DEFAULT_SPECS: tuple[HarmonicSpec, ...] = (
    HarmonicSpec(
        name="Gartley",
        completion_base="XA retracement",
        constraints=(
            Constraint("ab_xa", 0.500, 0.700, "0.618"),
            Constraint("bc_ab", 0.382, 0.886, "0.382–0.886"),
            Constraint("cd_bc", 1.130, 1.618, "1.27–1.618"),
            Constraint("completion", 0.720, 0.840, "0.786 retracement"),
        ),
    ),
    HarmonicSpec(
        name="Bat",
        completion_base="XA retracement",
        constraints=(
            Constraint("ab_xa", 0.330, 0.500, "0.382–0.500"),
            Constraint("bc_ab", 0.382, 0.886, "0.382–0.886"),
            Constraint("cd_bc", 1.618, 2.618, "1.618–2.618"),
            Constraint("completion", 0.840, 0.930, "0.886 retracement"),
        ),
    ),
    HarmonicSpec(
        name="Butterfly",
        completion_base="XA external (D beyond X)",
        constraints=(
            Constraint("ab_xa", 0.730, 0.830, "0.786"),
            Constraint("bc_ab", 0.382, 0.886, "0.382–0.886"),
            Constraint("cd_bc", 1.618, 2.240, "1.618–2.240"),
            Constraint("completion", 1.150, 1.450, "1.27 external"),
        ),
    ),
    HarmonicSpec(
        name="Crab",
        completion_base="XA external (D beyond X)",
        constraints=(
            Constraint("ab_xa", 0.382, 0.618, "0.382–0.618"),
            Constraint("bc_ab", 0.382, 0.886, "0.382–0.886"),
            Constraint("cd_bc", 2.240, 3.618, "2.240–3.618"),
            Constraint("completion", 1.500, 1.780, "1.618 external"),
        ),
    ),
    HarmonicSpec(
        name="Cypher",
        completion_base="XC retracement",
        constraints=(
            Constraint("ab_xa", 0.382, 0.618, "0.382–0.618"),
            Constraint("bc_ab", 1.130, 1.414, "1.13–1.414"),
            Constraint("dc_xc", 0.680, 0.860, "0.786 of XC"),
        ),
    ),
)


def _measures(sw: tuple) -> dict[str, float] | None:
    """Measure every ratio for one XABCD window, or None if unmeasurable.

    Returns None (window skipped, never approximated) when any denominator is
    zero or any price is non-finite — e.g. a zero-length AB leg or equal
    anchors.
    """
    prices = [s.price for s in sw]
    if not all(math.isfinite(p) for p in prices):
        return None
    x, a, b, c, d = prices
    xa, ab, bc = a - x, b - a, c - b
    xc = c - x

    def ratio(num: float, den: float) -> float | None:
        if den == 0.0:
            return None
        return abs(num) / abs(den)

    ab_xa = ratio(ab, xa)
    bc_ab = ratio(bc, ab)
    cd_bc = ratio(d - c, bc)
    dc_xc = ratio(d - c, xc)
    if None in (ab_xa, bc_ab, cd_bc, dc_xc, xa):
        return None
    completion = (a - d) / xa  # signed: (0,1) inside XA, >1 beyond X, <0 beyond A
    return {
        "ab_xa": ab_xa,
        "bc_ab": bc_ab,
        "cd_bc": cd_bc,
        "dc_xc": dc_xc,
        "completion": completion,
    }


def _match(spec: HarmonicSpec, m: dict[str, float], slack: float) -> list[dict] | None:
    """Return the matched bands, or None if any band is violated.

    ``slack`` widens every band edge symmetrically (0 = published ranges
    exactly); it is a documented tuning knob, not a way to force a match.
    """
    matched: list[dict] = []
    for c in spec.constraints:
        lo, hi = c.lo - slack, c.hi + slack
        v = m[c.measure]
        if not (lo <= v <= hi):
            return None
        matched.append(
            {
                "measure": MEASURE_LABELS[c.measure],
                "measured": round(v, 4),
                "range": [round(lo, 4), round(hi, 4)],
                "target": c.target,
            }
        )
    return matched


def _invalidation_price(spec: HarmonicSpec, sw: tuple) -> float | None:
    """Price level beyond which the matched reading fails.

    Uses the completion band's far edge (``A - hi * (A - X)``) for
    XA-anchored patterns and ``C - hi * (C - X)`` for Cypher's XC anchor.
    The signed formula yields the deeper edge for either direction.
    """
    c = _completion_constraint(spec)
    if c is None:
        return None
    x, a, _, cc, _ = (s.price for s in sw)
    if c.measure == "completion":
        return round(a - c.hi * (a - x), 4)
    return round(cc - c.hi * (cc - x), 4)


def _candidate(spec: HarmonicSpec, sw: tuple, m: dict[str, float], matched: list[dict]) -> dict:
    x, a, b, cc, d = sw
    direction = "bullish" if d.kind == "low" else "bearish"
    comp = next((r for r in matched if r["measure"] == MEASURE_LABELS["completion"]), None)
    comp_desc = comp["target"] if comp else "0.786 of XC"
    return {
        "pattern": spec.name,
        "direction": direction,
        "label": f"Candidate Harmonic {spec.name} ({direction})",
        "points": {
            "X": x.to_dict(),
            "A": a.to_dict(),
            "B": b.to_dict(),
            "C": cc.to_dict(),
            "D": d.to_dict(),
        },
        "measures": {MEASURE_LABELS[k]: round(v, 4) for k, v in m.items()},
        "matched_ranges": matched,
        "invalidation": (
            f"price closing beyond {_invalidation_price(spec, sw)} "
            f"({comp_desc}, {spec.completion_base}) invalidates the {spec.name} reading; "
            f"a deeper completion reclassifies rather than confirms"
        ),
        "certainty": "low",
        "evidence": (
            f"5 confirmed swings form XABCD; {len(matched)} published "
            f"{spec.name} bands matched on measured ratios"
        ),
        "method": METHOD,
        "uncertainty_note": UNCERTAINTY,
    }


def analyze_harmonic(swings, *, slack: float = 0.0, specs=DEFAULT_SPECS) -> dict:
    """Find harmonic XABCD candidates among *confirmed* swings.

    Slides a window of five consecutive confirmed swings, measures the
    published ratios, and reports every pattern whose bands all match.

    Status values:

    ``CANDIDATE_ONLY``
        at least one pattern matched (candidates listed, all certainty "low").
    ``NO_MATCH``
        measurable windows were tested but no band set matched.
    ``INSUFFICIENT_EVIDENCE``
        fewer than five confirmed swings, or no measurable window (degenerate
        or non-alternating structure).

    ``slack`` widens every band by that amount symmetrically.
    """
    if slack < 0:
        raise ValueError("slack must be >= 0")
    confirmed = [s for s in (swings or []) if getattr(s, "confirmed", True)]
    result: dict = {
        "status": "INSUFFICIENT_EVIDENCE",
        "candidates": [],
        "method": METHOD,
        "uncertainty": UNCERTAINTY,
        "evidence": "Confirmed swings only; published ratio bands; no future-data access",
        "swings_considered": len(confirmed),
        "patterns_tested": [s.name for s in specs],
        "windows_tested": 0,
        "message": "",
    }
    if len(confirmed) < 5:
        result["message"] = (
            f"Need at least 5 confirmed swings for an XABCD structure; got {len(confirmed)}"
        )
        return result

    windows = 0
    for i in range(len(confirmed) - 4):
        w = tuple(confirmed[i : i + 5])
        if any(w[k].kind == w[k + 1].kind for k in range(4)):
            continue  # not an alternating XABCD structure
        m = _measures(w)
        if m is None:
            continue  # degenerate legs: skipped, never approximated
        windows += 1
        for spec in specs:
            hit = _match(spec, m, slack)
            if hit is not None:
                result["candidates"].append(_candidate(spec, w, m, hit))
    result["windows_tested"] = windows

    if windows == 0:
        result["message"] = "No measurable XABCD window (degenerate or non-alternating legs)"
        return result
    if result["candidates"]:
        result["status"] = "CANDIDATE_ONLY"
        result["message"] = ""
    else:
        result["status"] = "NO_MATCH"
        result["message"] = (
            f"{windows} window(s) tested against {len(specs)} published definitions; "
            f"no band set matched within tolerance"
        )
    return result
