"""Fee/cost model provenance: a placeholder can never masquerade as verified.

The engine discloses cost status in three places - ``BacktestResult.cost_model``,
the config dict, and the assumptions text - and this suite pins all three so a
future change cannot silently relabel the 0.004 PLACEHOLDER (B-31 / register R3
/ T-12) as a real-world NEPSE rate.

Fixtures are SYNTHETIC-TEST-FIXTURE rows; test rates are explicit test inputs,
not market data.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from megatool.backtest import (
    FEE_SCHEDULES,
    PLACEHOLDER_FEE_RATE,
    REQUIRED_FEE_COMPONENTS,
    BacktestConfig,
    FeeComponent,
    FeeSchedule,
    FeeTier,
    always_in,
    cost_model,
    cost_status,
    fee_uncertainty,
    get_fee_schedule,
    placeholder_fee_schedule,
    run_backtest,
)

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")

MARKERS = {
    "verified": "VERIFIED rate from source",
    "placeholder": "is a PLACEHOLDER",
    "custom": "CUSTOM rate supplied to this run",
}


def _df(n: int = 6) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["TEST"] * n,
            "trading_date": pd.bdate_range("2026-01-01", periods=n),
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": [1000] * n,
            "source": ["SYNTHETIC-TEST-FIXTURE"] * n,
            "retrieved_at": [RETRIEVED] * n,
            "validation_status": ["valid"] * n,
        }
    )


# ------------------------------------------------------------------- statuses
def test_default_rate_is_declared_placeholder():
    cfg = BacktestConfig()
    assert cfg.fee_rate == PLACEHOLDER_FEE_RATE == 0.004
    assert cost_status(cfg) == "placeholder"
    assert cost_model(cfg)["status"] == "placeholder"
    assert cost_model(cfg)["source"] is None


def test_custom_rate_is_custom_not_verified_never_placeholder():
    for rate in (0.0, 0.0025, 0.01):
        cfg = BacktestConfig(fee_rate=rate)
        assert cost_status(cfg) == "custom", rate
        # the critical property: a caller-chosen number is never "verified"
        assert cost_status(cfg) != "verified"


def test_provenance_is_what_makes_a_rate_verified():
    cfg = BacktestConfig(
        fee_rate=0.0035,
        fee_source="broker schedule 2076-07 (owner-supplied)",
        fee_effective_from="2026-01-01",
    )
    assert cost_status(cfg) == "verified"
    cm = cost_model(cfg)
    assert cm["status"] == "verified"
    assert cm["source"] == "broker schedule 2076-07 (owner-supplied)"
    assert cm["effective_from"] == "2026-01-01"
    assert cm["fee_rate"] == 0.0035


def test_provenance_overrides_the_default_rate_label():
    # Even when the number equals the placeholder, recorded provenance is what
    # determines the status - the owner may have confirmed 0.004 is the real rate.
    cfg = BacktestConfig(
        fee_rate=0.004,
        fee_source="owner confirmation",
        fee_effective_from="2026-10-14",
    )
    assert cost_status(cfg) == "verified"


def test_half_provenance_is_rejected():
    with pytest.raises(ValueError, match="together"):
        BacktestConfig(fee_source="broker sheet").validate()
    with pytest.raises(ValueError, match="together"):
        BacktestConfig(fee_effective_from="2026-01-01").validate()


def test_status_never_claims_verification_without_source_and_date():
    for cfg in (
        BacktestConfig(),
        BacktestConfig(fee_rate=0.0025),
        BacktestConfig(fee_rate=0.0),
        BacktestConfig(fee_source="lonely source"),
    ):
        if cfg.fee_source and not cfg.fee_effective_from:
            with pytest.raises(ValueError):
                cfg.validate()
            continue
        assert cost_status(cfg) in ("placeholder", "custom")


# ------------------------------------------------------- disclosure in results
def _run(cfg: BacktestConfig):
    return run_backtest(_df(), always_in, cfg, symbol="TEST", strategy="buy&hold")


def test_result_carries_a_cost_model_block():
    res = _run(BacktestConfig())
    assert res.cost_model["status"] == "placeholder"
    assert res.cost_model["fee_rate"] == 0.004
    assert "PLACEHOLDER" in res.cost_model["note"]
    payload = res.to_dict()
    assert payload["cost_model"]["status"] == "placeholder"
    json.dumps(payload)  # must serialise


def test_fees_are_charged_exactly_once_per_side_never_double_counted():
    """One hand-computed round trip: the equity loss == entry fee + exit fee.

    Flat 100-price market (open=close=100), 1% per side, 10,000 cash, whole
    units, buy on bar1 (fills bar2 open) and sell on bar2 (fills bar3 open):

      zero-fee run: buy 100 @100 = 10,000, cash 0; sell 100 @100 -> 10,000.
                    final_equity = 10,000.
      1%-fee run:   affordable = floor(10,000 / (100*1.01)) = floor(99.0099) = 99
                    buy 99 @100 = 9,900, entry fee 99, cash = 10,000-9,900-99 = 1
                    sell 99 @100 = 9,900, exit fee 99, cash = 1+9,900-99 = 9,802
                    total fees = 99 + 99 = 198;  final_equity = 9,802.

    The gap 10,000 - 9,802 = 198 is EXACTLY the two fees - each charged once.
    A double-count bug would make that gap 396.
    """
    import numpy as np

    sig = lambda _d: np.asarray([0, 1, 0, 0], dtype=np.int8)  # noqa: E731
    free = run_backtest(
        _df(n=4), sig, BacktestConfig(initial_cash=10_000.0, fee_rate=0.0), symbol="TEST"
    )
    paid = run_backtest(
        _df(n=4), sig, BacktestConfig(initial_cash=10_000.0, fee_rate=0.01), symbol="TEST"
    )

    assert free.metrics["final_equity"] == pytest.approx(10_000.0, abs=1e-6)
    assert paid.metrics["final_equity"] == pytest.approx(9_802.0, abs=1e-6)
    assert paid.metrics["fees_paid"] == pytest.approx(198.0, abs=1e-6)
    # the equity gap equals the disclosed fees exactly - no hidden 2nd charge
    assert free.metrics["final_equity"] - paid.metrics["final_equity"] == pytest.approx(
        paid.metrics["fees_paid"], abs=1e-6
    )
    # and the single trade's own fee figure agrees with the metric total
    assert paid.trades[0]["fees_paid"] == pytest.approx(198.0, abs=1e-6)


def test_assumptions_show_exactly_the_matching_status_marker():
    cases = [
        (BacktestConfig(), "placeholder"),
        (BacktestConfig(fee_rate=0.0025), "custom"),
        (
            BacktestConfig(
                fee_rate=0.0035, fee_source="broker sheet", fee_effective_from="2026-01-01"
            ),
            "verified",
        ),
    ]
    for cfg, expected in cases:
        res = _run(cfg)
        joined = " ".join(res.assumptions)
        for status, marker in MARKERS.items():
            if status == expected:
                assert marker in joined, (status, expected, joined)
            else:
                assert marker not in joined, (status, expected, joined)


def test_custom_assumption_text_disclaims_authority():
    joined = " ".join(_run(BacktestConfig(fee_rate=0.005)).assumptions)
    assert "UNVERIFIED" in joined
    assert "not an authoritative NEPSE figure" in joined


def test_verified_assumption_text_names_source_and_date():
    cfg = BacktestConfig(
        fee_rate=0.0035, fee_source="broker sheet A", fee_effective_from="2026-01-01"
    )
    joined = " ".join(_run(cfg).assumptions)
    assert "broker sheet A" in joined
    assert "2026-01-01" in joined


def test_config_block_in_result_exposes_provenance_fields():
    res = _run(BacktestConfig())
    assert res.config["fee_source"] is None
    assert res.config["fee_effective_from"] is None
    assert res.config["fee_rate"] == 0.004


# ------------------------------------------------------- fee schedule (register R3)
def test_required_components_match_the_register():
    assert REQUIRED_FEE_COMPONENTS == (
        "broker_commission",
        "sebon_fee",
        "settlement_fee",
        "capital_gains_tax",
    )


def test_placeholder_schedule_is_shipped_and_unverified():
    sched = get_fee_schedule("placeholder")
    assert sched.name == "placeholder"
    assert sched.status == "placeholder"
    assert sched.provenance_complete is False
    # Every component exists but none is priced — nothing is fabricated.
    assert {c.key for c in sched.components} == set(REQUIRED_FEE_COMPONENTS)
    assert all(c.rate is None for c in sched.components)
    assert all(not c.known for c in sched.components)
    assert sched.unknown_components() == list(REQUIRED_FEE_COMPONENTS)


def test_registry_holds_placeholder_and_the_verified_official_schedule():
    # C3 (2026-10-15): the official schedule was added once every figure was
    # verified against official sources; the placeholder stays the default.
    assert set(FEE_SCHEDULES) == {"placeholder", "official-2083-84"}
    assert get_fee_schedule().name == "placeholder"
    assert get_fee_schedule("placeholder").status == "placeholder"


def test_unknown_schedule_name_is_an_error_not_a_silent_default():
    with pytest.raises(KeyError) as exc:
        get_fee_schedule("nepse-2026")
    assert "nepse-2026" in str(exc.value)


def test_partial_provenance_is_rejected():
    with pytest.raises(ValueError):
        FeeSchedule(
            name="half",
            components=placeholder_fee_schedule().components,
            source="only-source",
            effective_from="",
        ).validate()


def test_schedule_missing_a_required_component_is_rejected():
    with pytest.raises(ValueError) as exc:
        FeeSchedule(
            name="missing",
            components=(FeeComponent(key="broker_commission", label="Broker"),),
            source="s",
            effective_from="2026-01-01",
        ).validate()
    assert "sebon_fee" in str(exc.value)


def test_full_provenance_plus_known_rates_is_verified():
    comps = tuple(
        FeeComponent(key=k, label=k, rate=0.001, basis="fraction of traded value")
        for k in REQUIRED_FEE_COMPONENTS
    )
    sched = FeeSchedule(
        name="verified-fixture",
        components=comps,
        source="SEBON notice (fixture)",
        effective_from="2026-01-01",
    )
    sched.validate()
    assert sched.status == "verified"
    assert sched.unknown_components() == []


def test_provenance_with_some_unknown_rates_is_partial_not_verified():
    comps = (
        FeeComponent(key="broker_commission", label="b", rate=0.001, basis="turnover"),
        FeeComponent(key="sebon_fee", label="s", rate=None),
        FeeComponent(key="settlement_fee", label="f", rate=None),
        FeeComponent(key="capital_gains_tax", label="c", rate=None),
    )
    sched = FeeSchedule(name="partial", components=comps, source="s", effective_from="2026-01-01")
    assert sched.status == "partial"
    assert "sebon_fee" in sched.unknown_components()


def test_component_report_and_uncertainty_state_exactly_what_is_unknown():
    report = placeholder_fee_schedule().component_report()
    assert len(report) == len(REQUIRED_FEE_COMPONENTS)
    assert all(r["known"] is False and r["rate"] is None for r in report)
    unc = fee_uncertainty()
    assert unc["status"] == "placeholder"
    assert set(unc["unknown_components"]) == set(REQUIRED_FEE_COMPONENTS)
    assert unc["has_provenance"] is False
    assert "unverified" in unc["note"]


def test_fee_schedule_does_not_change_the_default_backtest_rate():
    # The additive schedule is disclosure only; the engine still runs on the
    # PLACEHOLDER aggregate and its status is untouched.
    assert PLACEHOLDER_FEE_RATE == 0.004
    assert cost_status(BacktestConfig()) == "placeholder"


# ------------------------------------------- shape extension (plan A3, no rates)
def test_tiered_component_is_known_only_when_every_tier_carries_a_rate():
    tiered = FeeComponent(
        key="broker_commission",
        label="Broker commission",
        tiers=(
            FeeTier(ceiling=50_000.0, rate=0.0036),
            FeeTier(ceiling=500_000.0, rate=0.0033),
            FeeTier(ceiling=None, rate=0.0030),
        ),
        basis="fraction of traded value",
    )
    assert tiered.known is True
    assert [t.ceiling for t in tiered.tiers] == [50_000.0, 500_000.0, None]


def test_tiered_component_with_an_unpriced_tier_is_not_known():
    tiered = FeeComponent(
        key="broker_commission",
        label="Broker commission",
        tiers=(FeeTier(ceiling=50_000.0, rate=0.0036), FeeTier(ceiling=None)),
    )
    assert tiered.known is False


def test_gain_aware_component_distinguishes_net_gain_from_traded_value():
    cgt = FeeComponent(
        key="capital_gains_tax",
        label="Capital gains tax",
        rate=0.075,
        basis="fraction of net gain",
        applies_to="net_gain",
    )
    assert cgt.known is True
    assert cgt.applies_to == "net_gain"
    flat = FeeComponent(key="sebon_fee", label="SEBON", rate=0.00015, basis="turnover")
    assert flat.applies_to == "traded_value"


def test_placeholder_cgt_declares_the_gain_shape_without_asserting_a_rate():
    sched = placeholder_fee_schedule()
    cgt = next(c for c in sched.components if c.key == "capital_gains_tax")
    assert cgt.applies_to == "net_gain"
    assert cgt.rate is None and cgt.basis == ""
    assert "net gain" in cgt.note
    # No tier boundaries or rates are recorded anywhere in the placeholder.
    assert all(not c.tiers for c in sched.components)
    assert all(c.rate is None for c in sched.components)


def test_schedule_report_exposes_tiers_and_applies_to():
    comps = (
        FeeComponent(
            key="broker_commission",
            label="b",
            tiers=(FeeTier(ceiling=50_000.0, rate=0.0036), FeeTier(ceiling=None, rate=0.0030)),
            basis="fraction of traded value",
        ),
        FeeComponent(key="sebon_fee", label="s", rate=0.00015, basis="fraction of traded value"),
        FeeComponent(key="settlement_fee", label="f", rate=25.0, basis="flat NPR per sell"),
        FeeComponent(
            key="capital_gains_tax",
            label="c",
            rate=0.075,
            basis="fraction of net gain",
            applies_to="net_gain",
        ),
    )
    sched = FeeSchedule(
        name="shape-fixture", components=comps, source="fixture", effective_from="2026-01-01"
    )
    sched.validate()
    assert sched.status == "verified"
    assert sched.unknown_components() == []
    report = sched.component_report()
    assert report[0]["tiers"] == [
        {"ceiling": 50_000.0, "rate": 0.0036},
        {"ceiling": None, "rate": 0.0030},
    ]
    assert report[3]["applies_to"] == "net_gain"
    json.dumps(sched.to_dict())  # the extended shape must serialise


def test_tiered_schedule_with_an_unpriced_tier_stays_partial():
    comps = (
        FeeComponent(
            key="broker_commission",
            label="b",
            tiers=(FeeTier(ceiling=50_000.0, rate=0.0036), FeeTier(ceiling=None)),
        ),
        FeeComponent(key="sebon_fee", label="s", rate=0.00015, basis="fraction of traded value"),
        FeeComponent(key="settlement_fee", label="f", rate=25.0, basis="flat NPR per sell"),
        FeeComponent(
            key="capital_gains_tax",
            label="c",
            rate=0.075,
            basis="fraction of net gain",
            applies_to="net_gain",
        ),
    )
    sched = FeeSchedule(
        name="partial-fixture", components=comps, source="fixture", effective_from="2026-01-01"
    )
    assert sched.status == "partial"
    assert sched.unknown_components() == ["broker_commission"]


# ------------------------------------- C3 official schedule (2026-10-15, data only)
# These tests pin the OFFICIALLY VERIFIED figures so a typo cannot silently
# change them. They assert data, not engine behaviour: the default run still
# uses PLACEHOLDER_FEE_RATE and still reports "placeholder".


def test_official_schedule_is_verified_with_complete_provenance():
    sched = get_fee_schedule("official-2083-84")
    assert sched.provenance_complete is True
    assert sched.status == "verified"
    assert sched.unknown_components() == []
    assert sched.source  # every figure traces back to an official document
    assert sched.effective_from == "2026-07-15"  # साउन १, २०८३: all four in force
    assert sched.retrieved_at == "2026-10-15"
    sched.validate()  # must not raise


def test_official_commission_tiers_match_sebon_schedule_14():
    sched = get_fee_schedule("official-2083-84")
    commission = next(c for c in sched.components if c.key == "broker_commission")
    assert commission.known is True
    assert [(t.ceiling, t.rate) for t in commission.tiers] == [
        (50_000.0, 0.0036),
        (500_000.0, 0.0033),
        (2_000_000.0, 0.0031),
        (10_000_000.0, 0.0027),
        (None, 0.0024),
    ]


def test_official_sebon_transaction_charge_is_0_015_percent_per_side():
    sched = get_fee_schedule("official-2083-84")
    sebon = next(c for c in sched.components if c.key == "sebon_fee")
    assert sebon.rate == 0.00015  # 0.015% of the transaction amount
    assert "purchase" in sebon.basis and "sale" in sebon.basis


def test_official_settlement_charge_is_flat_npr_on_the_sell_side():
    sched = get_fee_schedule("official-2083-84")
    dp = next(c for c in sched.components if c.key == "settlement_fee")
    assert dp.rate == 25.0
    assert "sell" in dp.basis.lower()


def test_official_cgt_is_gain_aware_and_states_both_holding_periods():
    sched = get_fee_schedule("official-2083-84")
    cgt = next(c for c in sched.components if c.key == "capital_gains_tax")
    assert cgt.applies_to == "net_gain"
    assert cgt.rate == 0.10  # ≤365 days (worst case stored)
    assert "0.075" in cgt.basis  # >365 days is stated, not hidden
    assert "365" in cgt.basis
    assert "95" in cgt.note  # ITA §95क citation present
    assert "2083" in cgt.note  # the amending Act + effective year cited


def test_default_run_behaviour_is_untouched_by_the_official_schedule():
    # The official schedule is opt-in data; the engine default must not move.
    assert PLACEHOLDER_FEE_RATE == 0.004
    cfg = BacktestConfig()
    assert cfg.fee_rate == PLACEHOLDER_FEE_RATE
    assert cost_status(cfg) == "placeholder"
    unc = fee_uncertainty()
    assert unc["status"] == "placeholder"
    assert set(unc["unknown_components"]) == set(REQUIRED_FEE_COMPONENTS)


# ------------------------- verified-schedule engine disclosure (C3/D-y, 2026-10-15)
def test_schedule_backed_config_reports_verified_status():
    cfg = BacktestConfig(fee_schedule="official-2083-84")
    assert cost_status(cfg) == "verified"
    block = cost_model(cfg)
    assert block["status"] == "verified"
    assert block["fee_schedule"] == "official-2083-84"
    assert block["schedule"]["name"] == "official-2083-84"
    assert block["schedule"]["unknown"] == []
    assert "NOT computed" in block["note"]  # no category declared -> stated


def test_declared_category_changes_only_the_disclosure_not_the_status():
    cfg = BacktestConfig(fee_schedule="official-2083-84", cgt="natural_person")
    block = cost_model(cfg)
    assert block["status"] == "verified"
    assert block["cgt"] == "natural_person"
    assert "capital gains tax computed" in block["note"]


def test_flat_model_disclosure_gains_explicit_null_schedule_keys():
    block = cost_model(BacktestConfig())
    assert block["fee_schedule"] is None and block["cgt"] is None
    assert "schedule" not in block  # the schedule sub-block exists only when one is used
    assert block["status"] == "placeholder"
