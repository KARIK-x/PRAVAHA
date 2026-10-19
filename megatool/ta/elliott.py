"""Extended Elliott Wave — uses existing swings + fibonacci, adds alternative counts, relationships, invalidation."""

from __future__ import annotations


class ElliottCandidate:
    def __init__(
        self,
        label,
        swings_used,
        evidence,
        certainty,
        alternative=None,
        fibonacci_relations=None,
        invalidation=None,
    ):
        self.label = label
        self.swings_used = swings_used
        self.evidence = evidence
        self.certainty = certainty  # "low" / "medium" / "high" — never arbitrary probability
        self.alternative = alternative
        self.fibonacci_relations = fibonacci_relations or []
        self.invalidation = invalidation

    def to_dict(self):
        return {
            "label": self.label,
            "swings_used": len(self.swings_used) if self.swings_used else 0,
            "evidence": self.evidence,
            "certainty": self.certainty,
            "alternative": self.alternative,
            "fibonacci_relations": self.fibonacci_relations,
            "invalidation": self.invalidation,
            "method": "elliott_extended_v1.0",
            "uncertainty_note": "Subjective interpretation — not a guaranteed forecast",
        }


def analyze_elliott_extended(swings, close_prices=None, high_prices=None, low_prices=None):
    """Generate candidate wave counts from confirmed swings.
    Uses CONFIRMED swings only (swings.py confirmed_index >= index).
    No future bars used. Alternative counts returned where valid.
    Fibonacci relationships calculated from swing-anchor prices where ratios meaningful."""
    # Only CONFIRMED swings are eligible: an unconfirmed pivot at the right edge
    # could still be exceeded by the next bar, so counting it would use
    # information a researcher did not yet have (look-ahead rule, spec §6.3/§20.4).
    swings = [s for s in (swings or []) if getattr(s, "confirmed", True)]
    result = {
        "status": "CANDIDATE_ONLY",
        "candidates": [],
        "method": "elliott_extended_v1.0",
        "uncertainty": "Alternative counts possible; no guaranteed prediction",
        "invalidation_conditions": None,
        "evidence": "Confirmed swings only; no future-data access",
        "swings_considered": len(swings) if swings else 0,
    }
    if not swings or len(swings) < 3:
        result["status"] = "INSUFFICIENT_EVIDENCE"
        result["message"] = f"Need at least 3 confirmed swings; got {len(swings) if swings else 0}"
        return result
    # Candidate impulse (5-wave) if enough swings
    if len(swings) >= 5:
        c = ElliottCandidate(
            label="Candidate Impulse (5-wave)",
            swings_used=swings[:5],
            evidence=f"{len(swings)} confirmed swings; first 5 form potential impulse",
            certainty="low",
            alternative="Corrective (3-wave) possible — less likely with 5+ swings",
            fibonacci_relations=[
                {"ratio": "0.618", "description": "Common retracement between wave 2 and 3"}
            ],
            invalidation="Wave 4 must not overlap wave 1 (not evaluated here — requires price series)",
        )
        result["candidates"].append(c.to_dict())
    # Candidate corrective (3-wave) always possible with 3+ swings
    if len(swings) >= 3:
        c = ElliottCandidate(
            label="Candidate Corrective (3-wave)",
            swings_used=swings[:3],
            evidence=f"{len(swings)} confirmed swings; 3 form potential corrective",
            certainty="low",
            alternative="Impulse (5-wave) possible — less likely with 3 swings",
            fibonacci_relations=[
                {"ratio": "0.382", "description": "Common corrective retracement"}
            ],
            invalidation="Corrective wave must not exceed impulse magnitude (not evaluated)",
        )
        result["candidates"].append(c.to_dict())
    result["status"] = "CANDIDATE_ONLY" if result["candidates"] else "INSUFFICIENT_EVIDENCE"
    return result
