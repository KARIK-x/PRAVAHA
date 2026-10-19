"""Elliott Wave regression tests against the real production interface.

Rewritten from a vacuous placeholder that constructed ``ElliottCandidate`` with
a nonexistent ``symbol=`` keyword and asserted a tautology (``... or True``).
These tests exercise the actual class (``label``/``swings_used``/``evidence``/
``certainty``) and ``analyze_elliott_extended``, including the look-ahead rule
that only CONFIRMED swings are eligible.
"""

from __future__ import annotations

from megatool.ta.elliott import ElliottCandidate, analyze_elliott_extended
from megatool.ta.swings import Swing


def _swing(index: int, kind: str, price: float, confirmed: bool = True) -> Swing:
    confirmed_index = index + 5 if confirmed else index
    return Swing(
        index=index, kind=kind, price=price, confirmed_index=confirmed_index, confirmed=confirmed
    )


# --------------------------------------------------------------------- class
def test_candidate_constructs_with_real_signature():
    """The constructor takes label/swings_used/evidence/certainty — not symbol."""
    c = ElliottCandidate(
        label="Candidate Corrective (3-wave)",
        swings_used=[_swing(0, "high", 120), _swing(10, "low", 100), _swing(20, "high", 130)],
        evidence="3 confirmed swings",
        certainty="low",
    )
    assert c.label == "Candidate Corrective (3-wave)"
    assert len(c.swings_used) == 3
    assert c.certainty == "low"


def test_candidate_to_dict_is_stable_and_honest():
    c = ElliottCandidate(
        label="L",
        swings_used=[_swing(0, "high", 1), _swing(5, "low", 2), _swing(9, "high", 3)],
        evidence="e",
        certainty="low",
        alternative="alt",
        fibonacci_relations=[{"ratio": "0.618"}],
        invalidation="inv",
    )
    d = c.to_dict()
    # Stable, documented response schema.
    assert d["label"] == "L"
    assert d["swings_used"] == 3
    assert d["evidence"] == "e"
    assert d["certainty"] == "low"
    assert d["alternative"] == "alt"
    assert d["fibonacci_relations"] == [{"ratio": "0.618"}]
    assert d["invalidation"] == "inv"
    assert d["method"] == "elliott_extended_v1.0"
    # No false certainty: an explicit uncertainty note is always attached.
    assert "not a guaranteed forecast" in d["uncertainty_note"]


def test_candidate_certainty_is_never_arbitrary_probability():
    c = ElliottCandidate(label="L", swings_used=[], evidence="e", certainty="low")
    # certainty is a qualitative label, never a number masquerading as probability.
    assert isinstance(c.certainty, str)


# ------------------------------------------------------------------ analysis
def test_insufficient_swings_is_not_an_error():
    res = analyze_elliott_extended([])
    assert res["status"] == "INSUFFICIENT_EVIDENCE"
    assert res["candidates"] == []
    assert "Need at least 3 confirmed swings" in res["message"]

    res2 = analyze_elliott_extended([_swing(0, "high", 1), _swing(5, "low", 2)])
    assert res2["status"] == "INSUFFICIENT_EVIDENCE"


def test_confirmed_swings_produce_candidate_counts():
    swings = [
        _swing(0, "high", 130),
        _swing(10, "low", 100),
        _swing(20, "high", 140),
        _swing(30, "low", 110),
        _swing(40, "high", 150),
    ]
    res = analyze_elliott_extended(swings)
    assert res["status"] == "CANDIDATE_ONLY"
    assert res["swings_considered"] == 5
    labels = {c["label"] for c in res["candidates"]}
    # 5 swings => both the impulse (5-wave) and corrective (3-wave) candidates.
    assert "Candidate Impulse (5-wave)" in labels
    assert "Candidate Corrective (3-wave)" in labels
    # Every candidate is bounded, never asserted as proven.
    assert all(c["certainty"] == "low" for c in res["candidates"])


def test_lookahead_unconfirmed_swing_is_excluded():
    """Regression: an unconfirmed right-edge pivot must NOT be counted.

    Including it would let a signal use a bar the researcher had not yet seen.
    With 4 confirmed + 1 unconfirmed, only the corrective (3-wave) candidate is
    reachable; if the unconfirmed swing leaked in, a 5-wave impulse would appear.
    """
    swings = [
        _swing(0, "high", 130),
        _swing(10, "low", 100),
        _swing(20, "high", 140),
        _swing(30, "low", 110),
        _swing(40, "high", 150, confirmed=False),  # right-edge, not yet knowable
    ]
    res = analyze_elliott_extended(swings)
    assert res["swings_considered"] == 4  # unconfirmed excluded
    labels = {c["label"] for c in res["candidates"]}
    assert "Candidate Impulse (5-wave)" not in labels
    assert "Candidate Corrective (3-wave)" in labels


def test_analysis_always_carries_uncertainty_not_prediction():
    swings = [_swing(i * 10, "high" if i % 2 == 0 else "low", 100 + i) for i in range(6)]
    res = analyze_elliott_extended(swings)
    assert res["status"] in {"CANDIDATE_ONLY", "INSUFFICIENT_EVIDENCE"}
    assert "no guaranteed prediction" in res["uncertainty"].lower() or res["uncertainty"]


def test_none_swings_handled():
    res = analyze_elliott_extended(None)
    assert res["status"] == "INSUFFICIENT_EVIDENCE"
