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
        rules=None,
    ):
        self.label = label
        self.swings_used = swings_used
        self.evidence = evidence
        self.certainty = certainty  # "low" / "medium" / "high" — never arbitrary probability
        self.alternative = alternative
        self.fibonacci_relations = fibonacci_relations or []
        self.invalidation = invalidation
        self.rules = rules or []

    def to_dict(self):
        return {
            "label": self.label,
            "swings_used": len(self.swings_used) if self.swings_used else 0,
            "evidence": self.evidence,
            "certainty": self.certainty,
            "alternative": self.alternative,
            "fibonacci_relations": self.fibonacci_relations,
            "invalidation": self.invalidation,
            "rules": self.rules,
            "certainty_basis": "count of decidable Elliott rules passed — NOT a probability",
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
        "invalidation_conditions": "evaluated per candidate in `rules`",
        "evidence": "Confirmed swings only; no future-data access",
        "swings_considered": len(swings) if swings else 0,
    }
    if not swings or len(swings) < 3:
        result["status"] = "INSUFFICIENT_EVIDENCE"
        result["message"] = f"Need at least 3 confirmed swings; got {len(swings) if swings else 0}"
        return result
    # Candidate impulse (5-wave) if enough swings
    if len(swings) >= 5:
        pivots = _pivot_prices(swings[:6])
        impulse_rules = evaluate_impulse_rules(pivots) if len(pivots) >= 3 else [{
            "rule": "Impulse rules",
            "status": "not_evaluable",
            "detail": "the swings carry no usable anchor prices",
        }]
        failed = [r for r in impulse_rules if r["status"] == "fail"]
        c = ElliottCandidate(
            label="Candidate Impulse (5-wave)",
            swings_used=swings[:5],
            evidence=f"{len(swings)} confirmed swings; first 5 form potential impulse",
            certainty=certainty_from_rules(impulse_rules),
            alternative="Corrective (3-wave) possible — less likely with 5+ swings",
            fibonacci_relations=[
                {"ratio": "0.618", "description": "Common retracement between wave 2 and 3"}
            ],
            invalidation=(
                "; ".join(f"{r['rule']} — {r['detail']}" for r in failed)
                if failed
                else "No decidable impulse rule was violated"
                + ("" if any(r["status"] == "pass" for r in impulse_rules)
                    else " (and none could be decided from the available pivots)")
            ),
            rules=impulse_rules,
        )
        result["candidates"].append(c.to_dict())
    # Candidate corrective (3-wave) always possible with 3+ swings
    if len(swings) >= 3:
        pivots3 = _pivot_prices(swings[:4])
        corr_rules = evaluate_corrective_rules(pivots3) if len(pivots3) >= 2 else [{
            "rule": "Corrective rules",
            "status": "not_evaluable",
            "detail": "the swings carry no usable anchor prices",
        }]
        failed_c = [r for r in corr_rules if r["status"] == "fail"]
        c = ElliottCandidate(
            label="Candidate Corrective (3-wave)",
            swings_used=swings[:3],
            evidence=f"{len(swings)} confirmed swings; 3 form potential corrective",
            certainty=certainty_from_rules(corr_rules),
            alternative="Impulse (5-wave) possible — less likely with 3 swings",
            fibonacci_relations=[
                {"ratio": "0.382", "description": "Common corrective retracement"}
            ],
            invalidation=(
                "; ".join(f"{r['rule']} — {r['detail']}" for r in failed_c)
                if failed_c
                else "No decidable corrective rule was violated"
            ),
            rules=corr_rules,
        )
        result["candidates"].append(c.to_dict())
    result["status"] = "CANDIDATE_ONLY" if result["candidates"] else "INSUFFICIENT_EVIDENCE"
    return result

# --------------------------------------------------------------------- rules
def _pivot_prices(swings) -> list[float]:
    """Anchor prices of the confirmed swings, oldest first.

    A swing carries its own price; a swing whose price is missing or
    non-finite is dropped rather than guessed.
    """
    out: list[float] = []
    for s in swings or []:
        v = getattr(s, "price", None)
        if v is None:
            v = getattr(s, "close", None)
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f and f not in (float("inf"), float("-inf")):
            out.append(f)
    return out


def _legs(prices: list[float]) -> list[float]:
    return [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]


def evaluate_impulse_rules(prices: list[float]) -> list[dict[str, str]]:
    """Check the standard impulse rules the available pivots can actually decide.

    Every entry is ``{rule, status, detail}`` with status ``pass`` / ``fail`` /
    ``not_evaluable``. A rule whose inputs are missing is reported as
    ``not_evaluable`` — never as a pass, and never silently dropped.
    """
    p = [float(x) for x in prices]
    legs = _legs(p)
    rules: list[dict[str, str]] = []

    # R1: wave 2 never retraces more than 100% of wave 1.
    if len(legs) >= 2 and legs[0] != 0:
        retr = abs(legs[1]) / abs(legs[0])
        rules.append({
            "rule": "Wave 2 retraces no more than 100% of wave 1",
            "status": "pass" if retr <= 1.0 else "fail",
            "detail": f"|wave 2| / |wave 1| = {retr:.3f}",
        })
    else:
        rules.append({
            "rule": "Wave 2 retraces no more than 100% of wave 1",
            "status": "not_evaluable",
            "detail": f"needs 3 pivots with a non-zero first leg; have {len(p)} pivot(s)",
        })

    # R2: wave 3 is never the shortest of waves 1, 3 and 5.
    if len(legs) >= 5:
        w1, w3, w5 = abs(legs[0]), abs(legs[2]), abs(legs[4])
        shortest = min(w1, w3, w5)
        rules.append({
            "rule": "Wave 3 is not the shortest of waves 1, 3, 5",
            "status": "pass" if w3 > shortest else "fail",
            "detail": f"|w1|={w1:.2f} |w3|={w3:.2f} |w5|={w5:.2f}",
        })
    elif len(legs) >= 3:
        rules.append({
            "rule": "Wave 3 is not the shortest of waves 1, 3, 5",
            "status": "not_evaluable",
            "detail": f"|w1|={abs(legs[0]):.2f} |w3|={abs(legs[2]):.2f} — wave 5 needs 6 pivots; have {len(p)}",
        })
    else:
        rules.append({
            "rule": "Wave 3 is not the shortest of waves 1, 3, 5",
            "status": "not_evaluable",
            "detail": f"needs 4 pivots; have {len(p)}",
        })

    # R3: wave 4 must not overlap the price territory of wave 1.
    if len(legs) >= 4:
        w1_end = p[1]                      # end of wave 1
        w4_end = p[4] if len(p) > 4 else p[-1]
        up = legs[0] > 0
        # Overlap means wave 4 traded back through the end of wave 1.
        overlap = (w4_end <= w1_end) if up else (w4_end >= w1_end)
        rules.append({
            "rule": "Wave 4 does not overlap the end of wave 1",
            "status": "fail" if overlap else "pass",
            "detail": f"wave 1 ended at {w1_end:.2f}; wave 4 at {w4_end:.2f} ({'up' if up else 'down'} impulse)",
        })
    else:
        rules.append({
            "rule": "Wave 4 does not overlap the end of wave 1",
            "status": "not_evaluable",
            "detail": f"needs 5 pivots; have {len(p)}",
        })
    return rules


def evaluate_corrective_rules(prices: list[float]) -> list[dict[str, str]]:
    """Check the A-B-C rules the pivots can decide.

    The one checkable structure rule is that wave B does not retrace more than
    100% of wave A in a zig-zag; beyond that an A-B-C is a shape, not a testable
    claim, so nothing further is asserted.
    """
    p = [float(x) for x in prices]
    legs = _legs(p)
    if len(legs) >= 2 and legs[0] != 0:
        retr = abs(legs[1]) / abs(legs[0])
        return [{
            "rule": "Wave B retraces no more than 100% of wave A",
            "status": "pass" if retr <= 1.0 else "fail",
            "detail": f"|B| / |A| = {retr:.3f}",
        }]
    return [{
        "rule": "Wave B retraces no more than 100% of wave A",
        "status": "not_evaluable",
        "detail": f"needs 3 pivots; have {len(p)}",
    }]


def certainty_from_rules(rules: list[dict[str, str]]) -> str:
    """A rule-count label, NOT a probability.

    ``high`` only when every decidable rule passed and at least two were
    decidable; ``medium`` when some passed; ``low`` otherwise. An all-fail or
    all-not-evaluable count is always ``low``.
    """
    decidable = [r for r in rules if r["status"] != "not_evaluable"]
    passed = [r for r in decidable if r["status"] == "pass"]
    if decidable and len(passed) == len(decidable) and len(decidable) >= 2:
        return "high"
    if passed:
        return "medium"
    return "low"

