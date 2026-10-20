"""Tests for the Elliott Wave rule evaluator.

Before this, the module *stated* the standard impulse rules as text but never
evaluated them, and hardcoded ``certainty="low"``. These tests pin the actual
arithmetic and the honest ``not_evaluable`` states.

Fixtures are hand-built pivot prices so every expected value can be computed by
hand.
"""

from __future__ import annotations

from megatool.ta.elliott import (
    certainty_from_rules,
    evaluate_corrective_rules,
    evaluate_impulse_rules,
)


def _status(rules, fragment):
    r = next((x for x in rules if fragment in x["rule"]), None)
    assert r is not None, f"rule containing {fragment!r} missing from {rules}"
    return r["status"]


def test_a_clean_upward_impulse_passes_every_decidable_rule():
    # 100 -> 120 -> 110 -> 160 -> 140 -> 200
    # legs: +20, -10, +50, -20, +60
    rules = evaluate_impulse_rules([100, 120, 110, 160, 140, 200])
    assert _status(rules, "Wave 2") == "pass"        # 10/20 = 0.5 <= 1
    assert _status(rules, "Wave 3") == "pass"        # 50 > min(20, 50, 60) = 20
    assert _status(rules, "Wave 4") == "pass"        # 140 > 120 (wave 1 end)
    assert certainty_from_rules(rules) == "high"


def test_a_clean_downward_impulse_is_the_mirror():
    rules = evaluate_impulse_rules([200, 180, 190, 140, 160, 100])
    assert _status(rules, "Wave 2") == "pass"
    assert _status(rules, "Wave 3") == "pass"
    assert _status(rules, "Wave 4") == "pass"        # 160 < 180 (wave 1 end)


def test_wave_four_overlapping_wave_one_fails():
    # wave 1 ends at 120; wave 4 trades back to 115 -> overlap
    rules = evaluate_impulse_rules([100, 120, 110, 160, 115, 200])
    assert _status(rules, "Wave 4") == "fail"
    assert "120.00" in next(r for r in rules if "Wave 4" in r["rule"])["detail"]


def test_wave_two_retracing_more_than_wave_one_fails():
    # wave 1 = +20, wave 2 = -30 -> 150% retracement
    rules = evaluate_impulse_rules([100, 120, 90, 130, 120, 180])
    assert _status(rules, "Wave 2") == "fail"
    assert "1.500" in next(r for r in rules if "Wave 2" in r["rule"])["detail"]


def test_wave_three_being_the_shortest_fails():
    # |w1| = 20, |w3| = 20, |w5| = 180 -> wave 3 ties the shortest
    rules = evaluate_impulse_rules([100, 120, 110, 130, 120, 300])
    assert _status(rules, "Wave 3") == "fail"


def test_rules_are_not_evaluable_rather_than_passing_when_pivots_are_missing():
    rules = evaluate_impulse_rules([100, 120, 110])
    assert _status(rules, "Wave 3") == "not_evaluable"
    assert _status(rules, "Wave 4") == "not_evaluable"
    # A rule that cannot be decided must never be reported as a pass.
    assert all(r["status"] != "pass" or "Wave 2" in r["rule"] for r in rules)
    assert certainty_from_rules(rules) == "medium"   # only wave 2 was decidable


def test_zero_first_leg_is_not_evaluable_not_a_division_error():
    rules = evaluate_impulse_rules([100, 100, 110])
    assert _status(rules, "Wave 2") == "not_evaluable"


def test_certainty_is_a_rule_count_never_a_probability():
    all_fail = [{"rule": "a", "status": "fail", "detail": ""}]
    all_unknown = [{"rule": "a", "status": "not_evaluable", "detail": ""}]
    one_pass = [{"rule": "a", "status": "pass", "detail": ""}]
    two_pass = [{"rule": "a", "status": "pass", "detail": ""},
                {"rule": "b", "status": "pass", "detail": ""}]
    mixed = [{"rule": "a", "status": "pass", "detail": ""},
             {"rule": "b", "status": "fail", "detail": ""}]
    assert certainty_from_rules(all_fail) == "low"
    assert certainty_from_rules(all_unknown) == "low"
    assert certainty_from_rules(one_pass) == "medium"
    assert certainty_from_rules(two_pass) == "high"
    assert certainty_from_rules(mixed) == "medium"


def test_corrective_rule_checks_the_b_leg():
    assert _status(evaluate_corrective_rules([100, 120, 110]), "Wave B") == "pass"
    assert _status(evaluate_corrective_rules([100, 120, 80]), "Wave B") == "fail"
    assert _status(evaluate_corrective_rules([100]), "Wave B") == "not_evaluable"


def test_analysis_reports_rules_and_an_honest_uncertainty_note():
    from megatool.ta.elliott import analyze_elliott_extended

    class S:
        def __init__(self, price):
            self.price = price
            self.confirmed = True

    out = analyze_elliott_extended([S(p) for p in (100, 120, 110, 160, 140, 200)])
    assert out["status"] == "CANDIDATE_ONLY"
    assert out["candidates"], "six confirmed swings must produce a candidate"
    cand = out["candidates"][0]
    assert cand["rules"], "a candidate must carry its evaluated rule table"
    assert cand["certainty"] in ("low", "medium", "high")
    assert "NOT a probability" in cand["certainty_basis"]
    assert "not a guaranteed forecast" in cand["uncertainty_note"]
    # The invalidation line now reports real numbers, not "not evaluated here".
    assert "not evaluated here" not in str(cand["invalidation"])


def test_unconfirmed_swings_are_still_excluded():
    from megatool.ta.elliott import analyze_elliott_extended

    class S:
        def __init__(self, price, confirmed=True):
            self.price = price
            self.confirmed = confirmed

    swings = [S(p) for p in (100, 120, 110, 160, 140)] + [S(200, confirmed=False)]
    out = analyze_elliott_extended(swings)
    assert out["swings_considered"] == 5, "the unconfirmed pivot must not be counted"
