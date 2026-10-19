"""Backtesting engine.

Design intent (see docs/TECH_STACK_DECISIONS.md): a small, fully readable engine
whose every rule can be inspected, rather than a large library whose default
assumptions would be invisible. There is no hidden fill model, no hidden
commission, and no lookahead: a signal computed on bar *i* can never fill
before bar *i+1* unless the caller explicitly asks for the optimistic mode.

WHAT THIS IS NOT
----------------
It is not evidence about future returns. Every result carries an ``assumptions``
list that must be shown next to any number derived from it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

#: Trading days per year used for annualising Sharpe. NEPSE trades Sun-Thu, so
#: the calendar has more trading days than a 250-day market; 250 is the common
#: convention and is stated in the assumptions rather than left implicit.
TRADING_DAYS_PER_YEAR = 250

SignalFn = Callable[[pd.DataFrame], np.ndarray]

#: The default fee rate. It is a PLACEHOLDER covering commission and charges,
#: NOT a verified NEPSE figure (B-31 / register R3 / T-12). Its status is
#: carried explicitly in every result's ``cost_model`` block so the number can
#: never be presented without saying what kind of number it is.
PLACEHOLDER_FEE_RATE = 0.004


@dataclass(frozen=True)
class BacktestConfig:
    """Execution and cost assumptions. Every field is user-visible."""

    initial_cash: float = 100_000.0
    #: Fraction of traded value charged **per side**. The default is the
    #: PLACEHOLDER :data:`PLACEHOLDER_FEE_RATE`; supply ``fee_source`` and
    #: ``fee_effective_from`` to mark a rate as verified (see :func:`cost_status`).
    fee_rate: float = PLACEHOLDER_FEE_RATE
    #: Provenance for the fee rate. Both fields or neither: a rate can only be
    #: ``verified`` when its source AND effective date are recorded. This is
    #: what makes it impossible to pass a placeholder off as a real-world rate.
    fee_source: str | None = None
    fee_effective_from: str | None = None
    #: Fraction of adverse price movement applied to fills (0 = none).
    slippage: float = 0.0
    #: ``next_open`` fills on the bar after the signal (no lookahead).
    #: ``same_close`` fills at the close of the bar that produced the signal
    #: and is deliberately optimistic - it exists to show how much that choice
    #: is worth, not to be the default.
    execution: Literal["next_open", "same_close"] = "next_open"
    #: Buy whole units only (cash remainder stays uninvested). NEPSE trades in
    #: board lots, which are company-specific and not modelled here.
    whole_units: bool = True
    allow_short: bool = False
    #: OPT-IN verified component schedule (C3/D-y). ``None`` = the legacy flat
    #: ``fee_rate`` model above, unchanged. A schedule name (e.g.
    #: "official-2083-84") prices each side with tiered commission + SEBON +
    #: the sell-side DP charge from that schedule's components; ``fee_rate``
    #: must then be left at its default (validated below) so the two models
    #: can never both apply to one run.
    fee_schedule: str | None = None
    #: Capital-gains-tax computation is OPT-IN and requires the caller to
    #: DECLARE the investor category - the engine never infers it. Only
    #: "natural_person" is supported (ITA §95क(2)(क) as amended by आर्थिक ऐन
    #: २०८३ gives that class holding-period rates); the company/other-entity
    #: rates are documented but the engine cannot classify an entity, so it
    #: refuses rather than guesses. ``None`` = CGT is not computed and every
    #: result says so.
    cgt: str | None = None

    def validate(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be > 0")
        if self.fee_rate < 0:
            raise ValueError("fee_rate must be >= 0")
        if self.slippage < 0:
            raise ValueError("slippage must be >= 0")
        if self.execution not in ("next_open", "same_close"):
            raise ValueError("execution must be 'next_open' or 'same_close'")
        if (self.fee_source is None) != (self.fee_effective_from is None):
            raise ValueError(
                "fee_source and fee_effective_from must be provided together: a "
                "rate can only be called verified with BOTH a source and an "
                "effective date"
            )
        if self.fee_schedule is not None:
            try:
                sched = get_fee_schedule(self.fee_schedule)
            except KeyError:
                raise ValueError(
                    f"unknown fee_schedule {self.fee_schedule!r}; known: "
                    f"{', '.join(sorted(FEE_SCHEDULES))}"
                ) from None
            unpriced = sched.unknown_components()
            if unpriced:
                raise ValueError(
                    f"fee_schedule {self.fee_schedule!r} has unpriced components "
                    f"({', '.join(unpriced)}): it cannot price a trade"
                )
            if self.fee_rate != PLACEHOLDER_FEE_RATE:
                raise ValueError(
                    "fee_rate is ignored when fee_schedule is set: leave fee_rate "
                    "at its default or drop fee_schedule - one run must use one "
                    "cost model, never both"
                )
        if self.cgt is not None:
            if self.cgt != "natural_person":
                raise ValueError(
                    "cgt must be None (not computed) or 'natural_person'. The "
                    "company/other-entity rates are documented, but the engine "
                    "cannot classify an investor entity and will not guess one."
                )
            if self.fee_schedule is None:
                raise ValueError(
                    "cgt='natural_person' requires fee_schedule: capital gains "
                    "tax is part of the verified schedule, not the flat-fee model"
                )
        if self.allow_short:
            raise ValueError(
                "shorting is not supported: NEPSE has no retail shorting, and a "
                "short model that does not exist in the market would not be honest"
            )


def cost_status(cfg: BacktestConfig) -> str:
    """``verified`` / ``placeholder`` / ``custom`` - never anything else.

    ``verified`` requires provenance recorded on the config OR a named
    schedule whose own status is verified; the default rate is ``placeholder``
    until an owner supplies an authoritative figure (R3).
    """
    if cfg.fee_source and cfg.fee_effective_from:
        return "verified"
    if cfg.fee_schedule is not None:
        # A named schedule carries its own provenance + per-component status
        # (validated in BacktestConfig.validate: no unpriced components).
        return get_fee_schedule(cfg.fee_schedule).status
    if cfg.fee_rate == PLACEHOLDER_FEE_RATE:
        return "placeholder"
    return "custom"


def cost_model(cfg: BacktestConfig) -> dict[str, Any]:
    """The cost model as disclosed metadata that travels with every result."""
    status = cost_status(cfg)
    if cfg.fee_schedule is not None:
        sched = get_fee_schedule(cfg.fee_schedule)
        note = (
            f"Official component schedule '{sched.name}' (sources recorded): "
            "tiered broker commission by transaction size (min NPR 10), the "
            "SEBON transaction charge per side, the NPR 25 sell-side DP charge"
            + (
                ", and capital gains tax computed per declared category."
                if cfg.cgt is not None
                else " — capital gains tax NOT computed (investor category is "
                "not an engine input; declare cgt='natural_person' to include it)."
            )
        )
        return {
            "fee_rate": cfg.fee_rate,
            "slippage": cfg.slippage,
            "status": status,
            "source": cfg.fee_source,
            "effective_from": cfg.fee_effective_from,
            "fee_schedule": cfg.fee_schedule,
            "cgt": cfg.cgt,
            "schedule": sched.to_dict(),
            "note": note,
        }
    return {
        "fee_rate": cfg.fee_rate,
        "slippage": cfg.slippage,
        "status": status,
        "source": cfg.fee_source,
        "effective_from": cfg.fee_effective_from,
        "fee_schedule": None,
        "cgt": None,
        "note": (
            "PLACEHOLDER covering commission and charges - confirm the real "
            "NEPSE rates with your broker (register R3 / T-12) before trusting "
            "any P&L."
            if status == "placeholder"
            else "Verified against the recorded source on the stated date."
            if status == "verified"
            else "Custom rate supplied to this run - unverified, NOT an authoritative NEPSE figure."
        ),
    }


# ----------------------------------------------------------------- fee schedule
# Register R3 / T-12 wants the aggregate PLACEHOLDER_FEE_RATE broken into named
# per-component figures, each carrying {source, retrieved_at, effective_from},
# with the default kept explicitly UNVERIFIED. The placeholder schedule below
# still ships unchanged as the default and still prices nothing.
#
# Shape extension (execution plan A3, 2026-10-14): the schedule can carry
# *tiered* per-transaction components (``FeeTier``) and distinguishes charges
# on traded value from gain-aware taxes on net gain (``applies_to``; capital
# gains tax is levied on the gain at disposal and cannot be expressed as a
# per-side rate at all).
#
# C3 (2026-10-15): every researched figure was verified against OFFICIAL
# sources and is recorded as one opt-in named schedule (see
# ``official_fee_schedule_2083_84``); the default BacktestConfig is untouched:
#   * broker commission — SEBON Securities Businessperson (Securities Broker
#     and Securities Trader) Regulation 2064, 6th amendment, अनुसूची-१४
#     (Schedule 14), machine-read from the official sebon.gov.np PDF
#     (published 2025-07-20; footnote: revised by SEBON board meeting
#     BS 2081-01-23, press: effective 2024-05-14): slabs 0.36/0.33/0.31/
#     0.27/0.24 % of transaction amount by size;
#   * SEBON transaction charge — अनुसूची-१५ (Schedule 15): 0.015% of each
#     purchase and sale amount for shares (identical in two official texts);
#   * settlement/DP charge — NPR 25 flat, sell side (SEBON publication);
#   * capital gains tax — Income Tax Act 2058 §95क(2)(क) as amended by
#     आर्थिक ऐन, २०८३ धारा 57 उप-बिन्दु (२१)(क): natural persons on
#     NEPSE-listed shares 7.5% (>365 days) / 10% (≤365 days), effective
#     साउन १, २०८३ = income year 2083/84 (previously 5% / 7.5%).
# Adding the official schedule is data, not behaviour — engine-side adoption
# landed 2026-10-15 (C3/D-y): opt-in via BacktestConfig.fee_schedule, with
# capital gains tax further gated on a DECLARED investor category (cgt).

#: The fee/tax components the cost model is expected to disclose (register R3).
REQUIRED_FEE_COMPONENTS: tuple[str, ...] = (
    "broker_commission",
    "sebon_fee",
    "settlement_fee",
    "capital_gains_tax",
)


@dataclass(frozen=True)
class FeeTier:
    """One tier of a tiered per-transaction charge.

    ``ceiling`` is the transaction-size upper bound in NPR (``None`` = no upper
    bound, the final tier). ``rate`` is a fraction of traded value, or ``None``
    until an authoritative figure is supplied — a tier boundary without a rate
    states the schedule's shape, never a price.
    """

    ceiling: float | None
    rate: float | None = None


@dataclass(frozen=True)
class FeeComponent:
    """One fee/tax line. ``rate``/``basis`` are None/"" until verified.

    ``rate`` is a number whose meaning depends on ``basis`` (e.g. a fraction of
    traded value, or a flat amount). Leaving both unset states plainly that we
    know the component exists but not what it costs or how it is charged.

    ``tiers`` carries a size-tiered shape (e.g. broker commission falls as
    transaction size rises); a component with tiers is only ``known`` when every
    tier carries a rate. ``applies_to`` distinguishes per-transaction charges on
    traded value from gain-aware taxes on net gain (capital gains tax is levied
    on the gain at disposal, not on turnover — it cannot be expressed as a
    per-side traded-value rate at all).
    """

    key: str
    label: str
    rate: float | None = None
    basis: str = ""
    note: str = ""
    tiers: tuple[FeeTier, ...] = ()
    applies_to: str = "traded_value"

    @property
    def known(self) -> bool:
        if self.tiers:
            return all(t.rate is not None for t in self.tiers)
        return self.rate is not None and bool(self.basis)


@dataclass(frozen=True)
class FeeSchedule:
    """A named set of per-component fee figures plus provenance."""

    name: str
    components: tuple[FeeComponent, ...]
    source: str = ""
    effective_from: str = ""
    retrieved_at: str = ""

    @property
    def provenance_complete(self) -> bool:
        return bool(self.source and self.effective_from)

    @property
    def status(self) -> str:
        """``placeholder`` (no provenance) / ``partial`` / ``verified``."""
        if not self.provenance_complete:
            return "placeholder"
        if all(c.known for c in self.components):
            return "verified"
        return "partial"

    def validate(self) -> None:
        """A schedule cannot claim verification with half its provenance."""
        if bool(self.source) != bool(self.effective_from):
            raise ValueError(
                "source and effective_from must be provided together: a fee "
                "schedule can only carry provenance with BOTH a source and an "
                "effective date"
            )
        known = {c.key for c in self.components}
        missing = [k for k in REQUIRED_FEE_COMPONENTS if k not in known]
        if missing:
            raise ValueError(f"fee schedule is missing component(s): {', '.join(missing)}")

    def component_report(self) -> list[dict[str, Any]]:
        """Exactly what is known and unknown about each component."""
        return [
            {
                "key": c.key,
                "label": c.label,
                "rate": c.rate,
                "basis": c.basis,
                "known": c.known,
                "note": c.note,
                "applies_to": c.applies_to,
                "tiers": [{"ceiling": t.ceiling, "rate": t.rate} for t in c.tiers],
            }
            for c in self.components
        ]

    def unknown_components(self) -> list[str]:
        """Components whose rate/basis is still unverified (the open items)."""
        return [c.key for c in self.components if not c.known]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "source": self.source or None,
            "effective_from": self.effective_from or None,
            "retrieved_at": self.retrieved_at or None,
            "components": self.component_report(),
            "unknown": self.unknown_components(),
        }


def placeholder_fee_schedule() -> FeeSchedule:
    """The default schedule: the four components exist, none is priced.

    Nothing here is a NEPSE figure. It exists so the *shape* of the cost model
    is disclosed and so the absence of verified rates is explicit rather than
    hidden behind a single aggregate number.
    """
    labels = {
        "broker_commission": "Broker commission",
        "sebon_fee": "SEBON charge",
        "settlement_fee": "Settlement / depository charge",
        "capital_gains_tax": "Capital gains tax",
    }
    components = []
    for k in REQUIRED_FEE_COMPONENTS:
        if k == "capital_gains_tax":
            # Shape statement only (no rate): CGT is levied on the net gain at
            # disposal, so it can never be expressed as a per-side rate on
            # traded value. Recording that here keeps the disclosure honest
            # about WHY this component does not fit the flat-rate engine.
            components.append(
                FeeComponent(
                    key=k,
                    label=labels[k],
                    rate=None,
                    basis="",
                    applies_to="net_gain",
                    note=(
                        "Gain-aware: charged on net gain at disposal, not per "
                        "side. Not verified; supply an authoritative figure "
                        "(register R3)."
                    ),
                )
            )
            continue
        components.append(
            FeeComponent(
                key=k,
                label=labels[k],
                rate=None,
                basis="",
                note="Not verified; supply an authoritative figure (register R3).",
            )
        )
    return FeeSchedule(name="placeholder", components=tuple(components))


def official_fee_schedule_2083_84() -> FeeSchedule:
    """The researched-official cost stack for income year 2083/84 (opt-in).

    Every figure carries its official source; nothing here is a broker's
    negotiated price, and nothing here is applied by the engine unless a caller
    explicitly selects this schedule — the default ``BacktestConfig`` keeps
    ``PLACEHOLDER_FEE_RATE`` and stays labelled unverified. Component notes
    carry each rule's own effective date because the four rules were not
    adopted on the same day; the schedule-level ``effective_from`` is the date
    all four were simultaneously in force (2026-07-15 = साउन १, २०८३, the
    capital-gains amendment date).
    """
    components = (
        FeeComponent(
            key="broker_commission",
            label="Broker commission",
            basis="fraction of transaction amount, per purchase and sale, by size slab",
            tiers=(
                FeeTier(ceiling=50_000.0, rate=0.0036),
                FeeTier(ceiling=500_000.0, rate=0.0033),
                FeeTier(ceiling=2_000_000.0, rate=0.0031),
                FeeTier(ceiling=10_000_000.0, rate=0.0027),
                FeeTier(ceiling=None, rate=0.0024),
            ),
            note=(
                "SEBON नियमावली २०६४ (छैठौं संशोधन) अनुसूची-१४: slabs "
                "≤NPR 50k 0.36%, >50k–5L 0.33%, >5L–20L 0.31%, >20L–1Cr "
                "0.27%, >1Cr 0.24% of the transaction amount; minimum NPR 10; "
                "the exchange may set lower within the ceiling (नियम ३२(१)). "
                "Revised by SEBON board meeting BS 2081-01-23 (press: "
                "effective 2024-05-14; previously 0.40/0.37/0.34/0.30/0.27%). "
                "Same schedule: bonds 0.10/0.05/0.02%, other securities "
                "0.15/0.12/0.10%."
            ),
        ),
        FeeComponent(
            key="sebon_fee",
            label="SEBON charge",
            rate=0.00015,
            basis="fraction of transaction amount, each purchase and sale (shares)",
            note=(
                "अनुसूची-१५: the broker remits 0.015% of every share purchase "
                "and sale amount (bonds 0.005%, other securities 0.010%). "
                "Confirmed identically in the standalone 6th-amendment "
                "regulation and the SEBON compiled-laws volume २०८०."
            ),
        ),
        FeeComponent(
            key="settlement_fee",
            label="Settlement / depository charge",
            rate=25.0,
            basis="NPR flat per sell transaction (DP charge, sell side only)",
            note=(
                "NPR 25 per scrip per settlement-day sell transaction (SEBON "
                "investor-rights publication; broker disclosures agree). A "
                "flat amount, not a percentage — it never fits a per-side rate."
            ),
        ),
        FeeComponent(
            key="capital_gains_tax",
            label="Capital gains tax",
            rate=0.10,
            basis=(
                "fraction of net gain at disposal: rate shown is holding "
                "≤365 days; 0.075 applies when held >365 days"
            ),
            applies_to="net_gain",
            note=(
                "ITA 2058 §95क(2)(क) as amended by आर्थिक ऐन, २०८३ "
                "धारा 57 उप-बिन्दु (२१)(क): natural persons (excluding "
                "broker-dealer companies) on NEPSE-listed shares — 7.5% if "
                "held >365 days, 10% if ≤365 days (previously 5%/7.5%); "
                "companies 10%, others 25%. Effective साउन १, २०८३ per "
                "धारा १(२) ⇒ income year 2083/84. The clause says "
                "“natural person”, not “resident”; the charge is on "
                "Nepal-source gains (§37). The ≤365-day rate is stored here "
                "as the worst case; the >365-day rate is stated in basis."
            ),
        ),
    )
    sched = FeeSchedule(
        name="official-2083-84",
        components=components,
        source=(
            "SEBON Regulation 2064 (6th amendment) Schedules 14 & 15 "
            "(sebon.gov.np PDF published 2025-07-20); आर्थिक ऐन, २०८३ "
            "(Nepal Law Commission gazette 2083-07-30, identical IRD copy) "
            "धारा 57(21) amending ITA §95क(2)(क) (ird.gov.np Income Tax "
            "Act PDF); DP charge per SEBON investor-rights publication"
        ),
        effective_from="2026-07-15",
        retrieved_at="2026-10-15",
    )
    sched.validate()  # fail fast: provenance and components must be complete
    return sched


#: Named schedules. The default stays ``placeholder`` (nothing priced, no
#: provenance) so existing runs keep their unverified label and their
#: PLACEHOLDER_FEE_RATE; the official schedule is opt-in data verified against
#: the C3 official sources above (register BLK-5).
FEE_SCHEDULES: dict[str, FeeSchedule] = {
    "placeholder": placeholder_fee_schedule(),
    "official-2083-84": official_fee_schedule_2083_84(),
}


def get_fee_schedule(name: str = "placeholder") -> FeeSchedule:
    """Look up a named schedule; unknown names are an error, not a silent default."""
    try:
        return FEE_SCHEDULES[name]
    except KeyError:
        raise KeyError(
            f"unknown fee schedule {name!r}; known: {', '.join(sorted(FEE_SCHEDULES))}"
        ) from None


def fee_uncertainty(schedule: FeeSchedule | None = None) -> dict[str, Any]:
    """A plain statement of what remains unverified about transaction costs."""
    sched = schedule or placeholder_fee_schedule()
    return {
        "status": sched.status,
        "unknown_components": sched.unknown_components(),
        "has_provenance": sched.provenance_complete,
        "note": (
            "Per-component NEPSE fees/taxes are unverified. The engine uses the "
            "aggregate PLACEHOLDER_FEE_RATE until an owner supplies sourced, "
            "dated figures (register R3 / T-12)."
        ),
    }


# ------------------------------------------------- verified cost engine (C3/D-y)
# One engine, one home: everything that APPLIES a verified schedule lives
# here, and both the backtester and the planning service call into it. Rates
# that the official schedule carries (current commission tiers, the SEBON
# charge, the DP flat) are READ from the schedule object, not duplicated. The
# two DATE-SWITCHED rule sets are recorded here with citations because the
# schedule carries only the current values:
#   * commission revision — SEBON board meeting BS 2081-01-23 (press:
#     effective 2024-05-14). The superseded table below (0.40/0.37/0.34/
#     0.30/0.27%) is the one officially printed in SEBON's सङ्ग्रह २०८०
#     compilation (register §3).
#   * CGT amendment — आर्थिक ऐन, २०८३ धारा 57 उप-बिन्दु (२१)(क), effective
#     साउन १, २०८३ (2026-07-15). The pre-amendment rates (5% / 7.5%) are the
#     official IRD Income Tax Act 2058 consolidated text of §95क(2)(क).
# The SEBON 0.015% charge and the NPR 25 DP charge have NO documented
# effective date in the sources read; they are applied to the whole sample
# and that assumption is disclosed in _assumptions().

#: NPR money precision. Every CHARGE is rounded to this precision at the
#: moment it is computed (like a broker's contract note), and the engine's
#: cash/basis arithmetic then uses the rounded charges, so a trade's
#: gross − costs − tax reconciles to its net exactly, by hand.
MONEY_DP = 2

#: The official schedule's commission revision date (see module comment).
COMMISSION_REVISION_DATE = "2024-05-14"

#: The officially superseded Schedule-14 table, in force before the revision
#: (SEBON सङ्ग्रह २०८०). Ceilings in NPR; ``None`` = no upper bound.
SCHEDULE14_PRE_REVISION: tuple[tuple[float | None, float], ...] = (
    (50_000.0, 0.0040),
    (500_000.0, 0.0037),
    (2_000_000.0, 0.0034),
    (10_000_000.0, 0.0030),
    (None, 0.0027),
)

#: Schedule-14's minimum commission per transaction (official).
MIN_COMMISSION_NPR = 10.0

#: The CGT amendment's effective date (आर्थिक ऐन २०८३ धारा १(२)).
CGT_AMENDMENT_DATE = "2026-07-15"

#: Natural-person rates on NEPSE-listed shares under ITA §95क(2)(क), keyed by
#: era (disposal date vs the amendment) and holding period (>365 days is the
#: "long" case). ``pre_amendment`` = the official pre-2083 ITA text.
CGT_NATURAL_PERSON: dict[str, dict[str, float]] = {
    "current": {"held_over_365": 0.075, "held_365_or_less": 0.10},
    "pre_amendment": {"held_over_365": 0.05, "held_365_or_less": 0.075},
}


@dataclass(frozen=True)
class SideCosts:
    """Every charge on ONE side of a trade, from a verified schedule."""

    side: str
    #: Traded value on this side, rounded to :data:`MONEY_DP` — the amount
    #: actually charged (cash, fees and tax all key off this figure).
    value: float
    commission: float
    commission_rate: float
    sebon: float
    #: Flat NPR DP charge, sell side only (0.0 on the buy side).
    dp: float
    total: float
    #: Which official commission table priced this side (effectiveness dating).
    commission_table: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaxOutcome:
    """Capital gains tax for ONE closed trade, or an explicit refusal."""

    #: True only when the category was declared AND the dates parsed AND the
    #: rate tables applied. Never True by inference.
    computed: bool
    #: Tax in NPR (rounded); ``0.0`` when computed and the trade is a loss.
    #: ``None`` when not computed.
    amount: float | None
    rate: float | None
    #: The gain the rate applies to (net proceeds − cost basis, charges
    #: included); negative on a loss. ``None`` when not computed.
    taxable_gain: float | None
    holding_days: int | None
    #: How it was computed, or exactly why it was not.
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _commission_rate(value: float, on_date: str, schedule: FeeSchedule) -> tuple[float, str]:
    """The commission rate for one side, honoring the revision's effective date."""
    if on_date < COMMISSION_REVISION_DATE:
        for ceiling, rate in SCHEDULE14_PRE_REVISION:
            if ceiling is None or value <= ceiling:
                return rate, "schedule14_pre_revision (सङ्ग्रह २०८० superseded table)"
    comp = next(c for c in schedule.components if c.key == "broker_commission")
    for tier in comp.tiers:  # ascending ceilings; last ceiling is None
        if tier.ceiling is None or value <= tier.ceiling:
            if tier.rate is None:
                raise ValueError("schedule commission tier has no rate")
            return tier.rate, f"schedule14 ({schedule.name})"
    raise ValueError("schedule commission component has no tiers")


def side_transaction_costs(
    value: float, side: str, on_date: str, schedule: FeeSchedule
) -> SideCosts:
    """Price ONE side of a trade with a verified component schedule.

    Commission is tiered by the side's traded value (Schedule 14, with the
    pre-revision table applied before 2024-05-14) with the official NPR 10
    minimum per transaction; the SEBON charge is a fraction of the value on
    both sides; the flat NPR 25 DP charge applies to sells only. Every charge
    is rounded to :data:`MONEY_DP`.
    """
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    v = round(float(value), MONEY_DP)
    rate, table = _commission_rate(v, on_date, schedule)
    commission = round(max(v * rate, MIN_COMMISSION_NPR), MONEY_DP)
    sebon_comp = next(c for c in schedule.components if c.key == "sebon_fee")
    if sebon_comp.rate is None:
        raise ValueError("schedule sebon_fee component has no rate")
    sebon = round(v * sebon_comp.rate, MONEY_DP)
    dp = 0.0
    if side == "sell":
        dp_comp = next(c for c in schedule.components if c.key == "settlement_fee")
        if dp_comp.rate is None:
            raise ValueError("schedule settlement_fee component has no rate")
        dp = round(float(dp_comp.rate), MONEY_DP)
    return SideCosts(
        side=side,
        value=v,
        commission=commission,
        commission_rate=rate,
        sebon=sebon,
        dp=dp,
        total=round(commission + sebon + dp, MONEY_DP),
        commission_table=table,
    )


def capital_gains_tax(
    cost_basis: float,
    net_proceeds: float,
    entry_date: str,
    exit_date: str,
    category: str | None,
) -> TaxOutcome:
    """CGT for ONE closed trade under ITA §95क(2)(क) as amended (register §3).

    ``cost_basis`` = entry traded value + buy-side charges; ``net_proceeds``
    = exit traded value − sell-side charges. The gain is taken NET of
    transaction costs (cost of acquisition including incidental charges);
    the exact §37 deductible-cost basis was not separately machine-verified
    and is flagged in the register — the RATES and the holding-period rule
    are official. A loss is never taxed (the charge is on the gain amount).
    The investor category must be DECLARED; the engine never infers it.
    """
    if category is None:
        return TaxOutcome(
            computed=False,
            amount=None,
            rate=None,
            taxable_gain=None,
            holding_days=None,
            reason=(
                "investor category not declared: the engine will not infer a "
                "personal attribute (declare cgt='natural_person' to compute)"
            ),
        )
    if category != "natural_person":
        return TaxOutcome(
            computed=False,
            amount=None,
            rate=None,
            taxable_gain=None,
            holding_days=None,
            reason=(
                f"investor category {category!r} is not supported: the "
                "company/other-entity rates are documented, but classifying "
                "an investor entity is not an engine input"
            ),
        )
    try:
        holding = int((pd.Timestamp(exit_date) - pd.Timestamp(entry_date)).days)
    except (ValueError, TypeError):
        return TaxOutcome(
            computed=False,
            amount=None,
            rate=None,
            taxable_gain=None,
            holding_days=None,
            reason=(
                f"unparseable trade dates for the holding-period test: "
                f"{entry_date!r} -> {exit_date!r}"
            ),
        )
    era = "current" if str(exit_date) >= CGT_AMENDMENT_DATE else "pre_amendment"
    rates = CGT_NATURAL_PERSON[era]
    rate = rates["held_over_365"] if holding > 365 else rates["held_365_or_less"]
    gain = float(net_proceeds) - float(cost_basis)
    table_note = (
        "आर्थिक ऐन २०८३ rates"
        if era == "current"
        else "pre-amendment ITA rates (disposal before 2026-07-15)"
    )
    if gain <= 0:
        return TaxOutcome(
            computed=True,
            amount=0.0,
            rate=rate,
            taxable_gain=round(gain, MONEY_DP),
            holding_days=holding,
            reason=(
                f"no taxable gain (net {gain:.2f} <= 0): the charge is on the "
                f"gain amount, so a loss is not taxed ({table_note})"
            ),
        )
    return TaxOutcome(
        computed=True,
        amount=round(gain * rate, MONEY_DP),
        rate=rate,
        taxable_gain=round(gain, MONEY_DP),
        holding_days=holding,
        reason=(f"natural person, held {holding} day(s), {table_note}: {rate:.2%} of the net gain"),
    )


def _affordable_units(
    cash: float, price: float, on_date: str, schedule: FeeSchedule, whole_units: bool
) -> tuple[float, SideCosts]:
    """The largest units whose value + buy-side schedule costs fit in ``cash``.

    Tiered commission makes affordability implicit (cost depends on value,
    value depends on units), so this binary-searches the feasible size; all
    charges are nondecreasing in value, so the feasible set is an interval
    and the search is exact to a float step. With ``whole_units`` the result
    is floored, which can only make it cheaper.
    """
    if price <= 0 or cash <= 0:
        return 0.0, side_transaction_costs(0.0, "buy", on_date, schedule)

    def feasible(u: float) -> bool:
        sc = side_transaction_costs(u * price, "buy", on_date, schedule)
        return sc.value + sc.total <= cash

    lo, hi = 0.0, cash / price  # costs are strictly positive: hi is infeasible-ish
    if feasible(hi):
        # Degenerate: costs fit even at the no-cost bound (cannot happen with
        # positive charges, but never return an unpriced guess).
        u = math.floor(hi) if whole_units else hi
        return u, side_transaction_costs(u * price, "buy", on_date, schedule)
    for _ in range(60):  # binary search: converges to a float step
        mid = (lo + hi) / 2.0
        if feasible(mid):
            lo = mid
        else:
            hi = mid
    u = math.floor(lo) if whole_units else lo
    return u, side_transaction_costs(u * price, "buy", on_date, schedule)


@dataclass
class Trade:
    entry_date: str
    exit_date: str | None
    entry_price: float
    exit_price: float | None
    units: float
    fees_paid: float = 0.0
    pnl: float | None = None
    return_pct: float | None = None
    bars_held: int = 0
    #: --- gross/cost/tax decomposition (C3/D-y). ``pnl`` above IS the net
    #: figure: gross_pnl - transaction_costs - capital_gains_tax. Every field
    #: is rounded to NPR money precision so the reconciliation is exact.
    #: Charged traded value on entry (value actually priced by the cost
    #: model; the flat-fee model records the same figure for disclosure).
    entry_value: float | None = None
    exit_value: float | None = None
    #: Price P&L before any charges (exit value - entry value).
    gross_pnl: float | None = None
    #: All transaction charges on the round trip (buy + sell sides).
    transaction_costs: float | None = None
    #: The gain the CGT rate was applied to (net of charges); None when tax
    #: was not computed. Negative on a loss (a loss is never taxed).
    taxable_gain: float | None = None
    #: Tax in NPR; None when CGT was not computed (category not declared).
    capital_gains_tax: float | None = None
    #: How the tax was computed, or exactly why it was not.
    tax_note: str = ""


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    params: dict[str, Any]
    config: dict[str, Any]
    start: str
    end: str
    bars: int
    metrics: dict[str, Any]
    equity: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Cost provenance (rate, status, source) - disclosed alongside the result
    #: so a fee number can never be read without its verification status.
    cost_model: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------- metrics
def max_drawdown(equity: Sequence[float]) -> float:
    """Largest peak-to-trough decline, as a negative fraction."""
    if not equity:
        return 0.0
    arr = np.asarray(equity, dtype=float)
    peak = np.maximum.accumulate(arr)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, arr / peak - 1.0, 0.0)
    return float(np.min(dd)) if len(dd) else 0.0


def sharpe_ratio(
    returns: Sequence[float], periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float | None:
    """Annualised Sharpe of a return series. ``None`` when it is undefined."""
    arr = np.asarray([r for r in returns if r is not None], dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return None
    sd = float(np.std(arr, ddof=1))
    if sd == 0.0:
        return None
    return float(np.mean(arr) / sd * math.sqrt(periods_per_year))


def cagr(start_value: float, end_value: float, days: float) -> float | None:
    if start_value <= 0 or end_value <= 0 or days <= 0:
        return None
    return float((end_value / start_value) ** (365.25 / days) - 1.0)


# ------------------------------------------------------------------- strategies
def sma_cross(fast: int = 20, slow: int = 50) -> SignalFn:
    """Long while the fast SMA is above the slow SMA (flat otherwise)."""
    if fast >= slow:
        raise ValueError("sma_cross: fast period must be < slow period")

    def sig(df: pd.DataFrame) -> np.ndarray:
        c = df["close"].astype(float)
        f = c.rolling(fast).mean()
        s = c.rolling(slow).mean()
        out = (f > s).to_numpy() & f.notna().to_numpy() & s.notna().to_numpy()
        return out.astype(np.int8)

    return sig


def rsi_threshold(period: int = 14, buy_below: float = 30.0, sell_above: float = 70.0) -> SignalFn:
    """Long while RSI is below ``buy_below``; exit above ``sell_above``.

    Hysteresis (two levels) so the strategy does not churn on every bar.
    """
    from megatool.ta import compute as ta_compute

    def sig(df: pd.DataFrame) -> np.ndarray:
        data = {
            "open": df["open"].to_numpy(float),
            "high": df["high"].to_numpy(float),
            "low": df["low"].to_numpy(float),
            "close": df["close"].to_numpy(float),
            "volume": df["volume"].to_numpy(float),
        }
        r = np.asarray(ta_compute("rsi", data, period=period).values["rsi"], dtype=float)
        out = np.zeros(len(df), dtype=np.int8)
        position = 0
        for i, v in enumerate(r):
            if np.isnan(v):
                out[i] = 0
                continue
            if position == 0 and v < buy_below:
                position = 1
            elif position == 1 and v > sell_above:
                position = 0
            out[i] = position
        return out

    return sig


def always_in(_df: pd.DataFrame) -> np.ndarray:
    """Invested for the whole window - the buy-and-hold control."""
    return np.ones(len(_df), dtype=np.int8)


def never_in(_df: pd.DataFrame) -> np.ndarray:
    return np.zeros(len(_df), dtype=np.int8)


def ma_slope_trend(period: int = 100, min_slope: float = 0.0) -> SignalFn:
    """Long while a long SMA is rising (a deliberately slow trend filter)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        ma = df["close"].astype(float).rolling(period).mean()
        slope = ma.diff()
        ok = (slope > min_slope).to_numpy() & ma.notna().to_numpy()
        ok &= slope.notna().to_numpy()
        return ok.astype(np.int8)

    return sig


# --------------------------------------------------------------------------
# Algorithm-workshop strategy catalogue. Everything below shares the same
# position-array contract as the four founders above (int8, 1 = long, 0 =
# flat), runs inside the identical engine, and carries a `category` label for
# the workshop UI. No strategy here can predict: each is a historical rule.
# --------------------------------------------------------------------------


def _sma(series: pd.Series, n: int) -> pd.Series:
    return series.astype(float).rolling(max(2, int(n)), min_periods=max(2, n)).mean()


def donchian_breakout(breakout_days: int = 20, exit_days: int = 10) -> SignalFn:
    """Long after the close makes a N-day-high breakout; flat below M-day low.

    The channel is taken from PREVIOUS bars (shift(1)), so today's own bar can
    never become the level it must exceed - the standard leak-free form.
    """

    def sig(df: pd.DataFrame) -> np.ndarray:
        close = df["close"].astype(float)
        hi = close.rolling(max(2, breakout_days), min_periods=2).max().shift(1)
        lo = close.rolling(max(2, exit_days), min_periods=2).min().shift(1)
        pos = pd.Series(0, index=df.index, dtype=float)
        pos[close > hi] = 1.0
        pos[close < lo] = 0.0
        pos[(close <= hi) & (close >= lo)] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)

    return sig


def bollinger_revert(period: int = 20, band_k: float = 2.0) -> SignalFn:
    """Mean-reversion: long below the lower band, flat at the mid band."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        close = df["close"].astype(float)
        mid = _sma(close, period)
        sd = close.rolling(max(2, period), min_periods=2).std()
        lower = mid - float(band_k) * sd
        pos = pd.Series(0.0, index=df.index)
        pos[close < lower] = 1.0
        pos[close > mid] = 0.0
        pos[(close >= lower) & (close <= mid)] = np.nan
        if lower.isna().all():
            return np.zeros(len(df), dtype=np.int8)
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)

    return sig


def macd_trend(fast: int = 12, slow: int = 26, signal: int = 9) -> SignalFn:
    """Long while the MACD line is above its signal line (a trend rule)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        ema_fast = df["close"].astype(float).ewm(span=max(1, fast), adjust=False).mean()
        ema_slow = df["close"].astype(float).ewm(span=max(2, slow), adjust=False).mean()
        macd = ema_fast - ema_slow
        trigger = macd.ewm(span=max(1, signal), adjust=False).mean()
        return (macd > trigger).to_numpy(dtype=np.int8)

    return sig


def momentum_90d(days: int = 90) -> SignalFn:
    """Long while the symbol has a positive N-day return (time-series momentum)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        close = df["close"].astype(float)
        past = close.shift(int(days))
        ok = (close > past) & past.notna()
        return ok.to_numpy(dtype=np.int8)

    return sig


def rsi2_reversion(period: int = 2, buy_below: float = 10.0, exit_above: float = 60.0) -> SignalFn:
    """The Connors-style short-RSI reversion: dip into the 2-day RSI, exit
    once it recovers. A high-turnover mean-reversion rule by design."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        from megatool.ta.momentum import rsi as ta_rsi  # reuse the platform's RSI

        result = ta_rsi({"close": df["close"].astype(float).to_numpy()}, int(period))
        value = pd.Series(result.values["rsi"], index=df.index)
        pos = pd.Series(0.0, index=df.index)
        pos[value < float(buy_below)] = 1.0
        pos[value > float(exit_above)] = 0.0
        pos[value.isna()] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)

    return sig


def trend200_filter(period: int = 200) -> SignalFn:
    """Long only while price is above its N-day SMA (a slow regime filter)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        ma = _sma(df["close"].astype(float), period)
        ok = (df["close"].astype(float) > ma) & ma.notna()
        return ok.to_numpy(dtype=np.int8)

    return sig


def vol_regime(vol_days: int = 20, max_ret_pct: float = 90.0) -> SignalFn:
    """Stay long while realized volatility is CALM (percentile of its own
    trailing history, computed with prior bars only)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        close = df["close"].astype(float)
        ret = close.pct_change()
        vol = ret.rolling(max(2, vol_days), min_periods=2).std()
        rolling_q = vol.rolling(120, min_periods=20).quantile(max_ret_pct / 100.0).shift(1)
        ok = (vol <= rolling_q) & vol.notna() & rolling_q.notna()
        return ok.to_numpy(dtype=np.int8)

    return sig


def atr_channel(atr_days: int = 14, entry_k: float = 2.0, exit_k: float = 0.5) -> SignalFn:
    """ATR trend channel: long after close exceeds the previous bar's range
    top + entry multiple of ATR; flat when close weakens near the range
    (exit multiple). Channel from previous bars only."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        from megatool.ta.trend import atr as ta_atr

        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        result = ta_atr(
            {
                "high": high.to_numpy(),
                "low": low.to_numpy(),
                "close": close.to_numpy(),
            },
            int(atr_days),
        )
        atr_range = pd.Series(result.values["atr"], index=df.index).shift(1)
        upper = high.shift(1).rolling(3, min_periods=1).max().shift(1) + float(entry_k) * atr_range
        lower = low.shift(1).rolling(3, min_periods=1).min().shift(1) - float(exit_k) * atr_range
        pos = pd.Series(0.0, index=df.index)
        pos[close > upper] = 1.0
        pos[close < lower] = 0.0
        pos[(close <= upper) & (close >= lower)] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)

    return sig


def ema_ribbon(fast: int = 8, mid: int = 13, slow: int = 21) -> SignalFn:
    """Long while three EMAs are stacked bullish (fast above mid above slow)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        close = df["close"].astype(float)
        e_fast = close.ewm(span=max(1, fast), adjust=False).mean()
        e_mid = close.ewm(span=max(2, mid), adjust=False).mean()
        e_slow = close.ewm(span=max(3, slow), adjust=False).mean()
        return ((e_fast > e_mid) & (e_mid > e_slow)).to_numpy(dtype=np.int8)

    return sig


def rate_of_change(days: int = 20, min_pct: float = 0.0) -> SignalFn:
    """Long while the N-day rate of change exceeds a floor (often 0)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        close = df["close"].astype(float)
        roc = (close / close.shift(int(days)) - 1.0) * 100.0
        ok = (roc > float(min_pct)) & roc.notna()
        return ok.to_numpy(dtype=np.int8)

    return sig


def stochastic_revert(
    k_days: int = 14, buy_below: float = 20.0, exit_above: float = 80.0
) -> SignalFn:
    """Slow-%K reversion: enter when the range position is pinned low, exit high."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        n = max(2, int(k_days))
        hi = high.rolling(n, min_periods=n).max()
        lo = low.rolling(n, min_periods=n).min()
        k = 100.0 * (close - lo) / (hi - lo).replace(0.0, np.nan)
        pos = pd.Series(0.0, index=df.index)
        pos[k < float(buy_below)] = 1.0
        pos[k > float(exit_above)] = 0.0
        pos[k.isna()] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)

    return sig


def cci_trend(days: int = 20) -> SignalFn:
    """Long while the Commodity Channel Index is positive (momentum rule)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        n = max(2, int(days))
        typical = (
            df["high"].astype(float) + df["low"].astype(float) + df["close"].astype(float)
        ) / 3.0
        sma = typical.rolling(n, min_periods=n).mean()
        dev = (typical - sma).abs().rolling(n, min_periods=n).mean()
        cci = (typical - sma) / max(1e-9, 0.015) / dev.replace(0.0, np.nan)
        return (cci > 0).astype(np.int8).to_numpy()

    return sig


def accum_dist_trend(ema_days: int = 20) -> SignalFn:
    """Long while the accumulation/distribution line is above its EMA."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        hl_range = (df["high"].astype(float) - df["low"].astype(float)).replace(0.0, np.nan)
        multiplier = (
            (df["close"].astype(float) - df["low"].astype(float))
            - (df["high"].astype(float) - df["close"].astype(float))
        ) / hl_range
        mfm = multiplier.fillna(0.0) * df["volume"].astype(float).fillna(0.0)
        ad = mfm.cumsum()
        line = ad.ewm(span=max(2, int(ema_days)), adjust=False).mean()
        return (ad > line).to_numpy(dtype=np.int8)

    return sig


def obv_trend(ema_days: int = 20) -> SignalFn:
    """Long while on-balance volume is above its EMA (a volume-trend rule)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        close = df["close"].astype(float)
        vol = df["volume"].astype(float).fillna(0.0)
        signed = np.sign(close.diff().fillna(0.0)) * vol
        obv = signed.cumsum()
        trigger = obv.ewm(span=max(2, int(ema_days)), adjust=False).mean()
        return (obv > trigger).to_numpy(dtype=np.int8)

    return sig


def golden_cross(fast: int = 50, slow: int = 200) -> SignalFn:
    """Long while SMA(fast) is above SMA(slow) AND price is above SMA(fast)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        close = df["close"].astype(float)
        ma_fast = _sma(close, fast)
        ma_slow = _sma(close, slow)
        ok = (ma_fast > ma_slow) & (close > ma_fast) & ma_fast.notna() & ma_slow.notna()
        return ok.to_numpy(dtype=np.int8)

    return sig


def range_rider(days: int = 60, upper_frac: float = 0.5) -> SignalFn:
    """Long while the close sits in the top portion of its trailing range
    (a strength/continuation rule)."""

    def sig(df: pd.DataFrame) -> np.ndarray:
        n = max(2, int(days))
        high = df["high"].astype(float).rolling(n, min_periods=n).max()
        low = df["low"].astype(float).rolling(n, min_periods=n).min()
        close = df["close"].astype(float)
        span = (high - low).replace(0.0, np.nan)
        pos = (close - low) / span
        ok = (pos > float(upper_frac)) & pos.notna()
        return ok.to_numpy(dtype=np.int8)

    return sig


STRATEGIES: dict[str, dict[str, Any]] = {
    "sma_cross": {
        "label": "SMA crossover",
        "description": "Long while SMA(fast) > SMA(slow). Classic trend following.",
        "params": {"fast": 20, "slow": 50},
        "factory": sma_cross,
        "category": "trend",
    },
    "rsi_threshold": {
        "label": "RSI mean-reversion",
        "description": "Buy below oversold, exit above overbought (two levels, "
        "so it does not churn every bar). RSI is a historical statistic, "
        "not a prediction.",
        "params": {"period": 14, "buy_below": 30.0, "sell_above": 70.0},
        "factory": rsi_threshold,
        "category": "reversion",
    },
    "ma_slope_trend": {
        "label": "Long-trend filter",
        "description": "Long while a 100-bar SMA is rising. Slow, low-turnover.",
        "params": {"period": 100, "min_slope": 0.0},
        "factory": ma_slope_trend,
        "category": "trend",
    },
    "always_in": {
        "label": "Buy and hold",
        "description": "Invested for the whole window. The control every other "
        "result should be compared against.",
        "params": {},
        "factory": lambda: always_in,
        "category": "baseline",
    },
    "donchian_breakout": {
        "label": "Donchian breakout",
        "description": "Buy a new N-day high, exit below an M-day low. The "
        "classic trend/breakout family, computed from prior bars only.",
        "params": {"breakout_days": 20, "exit_days": 10},
        "factory": donchian_breakout,
        "category": "breakout",
    },
    "bollinger_revert": {
        "label": "Bollinger mean reversion",
        "description": "Long under the lower band, flat at the mid band.",
        "params": {"period": 20, "band_k": 2.0},
        "factory": bollinger_revert,
        "category": "reversion",
    },
    "macd_trend": {
        "label": "MACD trend",
        "description": "Long while MACD is above its signal line.",
        "params": {"fast": 12, "slow": 26, "signal": 9},
        "factory": macd_trend,
        "category": "trend",
    },
    "momentum_90d": {
        "label": "N-day momentum",
        "description": "Long while the 90-day return is positive (classic time-series momentum).",
        "params": {"days": 90},
        "factory": momentum_90d,
        "category": "momentum",
    },
    "rsi2_reversion": {
        "label": "RSI(2) dip reversion",
        "description": "Connors-style: buy tiny dips (RSI(2)<10), leave once "
        "RSI recovers. High-turnover by design.",
        "params": {"period": 2, "buy_below": 10.0, "exit_above": 60.0},
        "factory": rsi2_reversion,
        "category": "reversion",
    },
    "trend200_filter": {
        "label": "200-day regime filter",
        "description": "Long only while price is above its 200-day SMA; a "
        "slow, very-low-turnout regime filter.",
        "params": {"period": 200},
        "factory": trend200_filter,
        "category": "regime",
    },
    "vol_regime": {
        "label": "Calm-volatility regime",
        "description": "Stay long only while realized volatility sits in its "
        "calm half (trailing 120-day percentile of its own past).",
        "params": {"vol_days": 20, "max_ret_pct": 90.0},
        "factory": vol_regime,
        "category": "regime",
    },
    "atr_channel": {
        "label": "ATR channel breakout",
        "description": "Enter beyond the previous range + 2×ATR; exit near the "
        "opposite ATR channel edge.",
        "params": {"atr_days": 14, "entry_k": 2.0, "exit_k": 0.5},
        "factory": atr_channel,
        "category": "breakout",
    },
    "ema_ribbon": {
        "label": "EMA ribbon stack",
        "description": "Long while EMA(8) > EMA(13) > EMA(21) are stacked bullishly.",
        "params": {"fast": 8, "mid": 13, "slow": 21},
        "factory": ema_ribbon,
        "category": "trend",
    },
    "rate_of_change": {
        "label": "Rate-of-change floor",
        "description": "Long while the 20-day rate of change is positive.",
        "params": {"days": 20, "min_pct": 0.0},
        "factory": rate_of_change,
        "category": "momentum",
    },
    "stochastic_revert": {
        "label": "Stochastic reversion",
        "description": "Long when slow %K is pinned under 20; exit above 80.",
        "params": {"k_days": 14, "buy_below": 20.0, "exit_above": 80.0},
        "factory": stochastic_revert,
        "category": "reversion",
    },
    "cci_trend": {
        "label": "CCI trend",
        "description": "Long while a 20-day Commodity Channel Index is above 0.",
        "params": {"days": 20},
        "factory": cci_trend,
        "category": "momentum",
    },
    "accum_dist_trend": {
        "label": "Accumulation / distribution trend",
        "description": "Long while the AD line stays above its own EMA - a "
        "volume-confirmed trend rule.",
        "params": {"ema_days": 20},
        "factory": accum_dist_trend,
        "category": "volume",
    },
    "obv_trend": {
        "label": "On-balance-volume trend",
        "description": "Long while OBV is above its EMA(20) - price trend confirmed by net volume.",
        "params": {"ema_days": 20},
        "factory": obv_trend,
        "category": "volume",
    },
    "golden_cross": {
        "label": "Golden cross",
        "description": "Long while SMA(50) > SMA(200) and price > SMA(50). The "
        "textbook long-only regime rule.",
        "params": {"fast": 50, "slow": 200},
        "factory": golden_cross,
        "category": "regime",
    },
    "range_rider": {
        "label": "Range rider",
        "description": "Long while the close sits in the top half of its "
        "trailing 60-day range (strength continuation).",
        "params": {"days": 60, "upper_frac": 0.5},
        "factory": range_rider,
        "category": "breakout",
    },
}


def build_strategy(key: str, **overrides: Any) -> tuple[SignalFn, str, dict[str, Any]]:
    if key not in STRATEGIES:
        raise ValueError(f"unknown strategy {key!r}; known: {', '.join(sorted(STRATEGIES))}")
    spec = STRATEGIES[key]
    params = {**spec["params"], **overrides}
    unknown = set(params) - set(spec["params"])
    if unknown:
        raise ValueError(
            f"{key}: unknown parameter(s) {sorted(unknown)}; allowed {sorted(spec['params'])}"
        )
    # Web forms and JSON send numbers as floats; a period of 20.5 would fail
    # deep inside pandas, so coerce (or reject) at the boundary instead.
    for name, default in spec["params"].items():
        value = params[name]
        if isinstance(default, bool):
            params[name] = bool(value)
        elif isinstance(default, int):
            if isinstance(value, bool):
                raise ValueError(f"{key}.{name} must be a whole number, got {value!r}")
            if isinstance(value, float) and float(value).is_integer():
                params[name] = int(value)
            elif isinstance(value, int):
                params[name] = value
            else:
                raise ValueError(f"{key}.{name} must be a whole number, got {value!r}")
        elif isinstance(default, float):
            params[name] = float(value)
    fn = spec["factory"](**params)
    return fn, spec["label"], params


# ----------------------------------------------------------------------- engine
def run_backtest(
    df: pd.DataFrame,
    signal_fn: SignalFn,
    config: BacktestConfig | None = None,
    symbol: str = "",
    strategy: str = "",
    params: dict[str, Any] | None = None,
) -> BacktestResult:
    """Run a long/flat strategy over ``df`` (ascending dates).

    Returns metrics, an equity curve, the closed trades, and the list of
    assumptions the numbers depend on.
    """
    cfg = config or BacktestConfig()
    cfg.validate()
    # The verified component schedule, resolved ONCE. ``None`` = the legacy
    # flat-fee path below, byte-for-byte unchanged (C3/D-y guardrail).
    schedule = get_fee_schedule(cfg.fee_schedule) if cfg.fee_schedule is not None else None

    required = {"trading_date", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"backtest input is missing columns: {sorted(missing)}")

    # Normalize the session column BEFORE sorting and duplicate detection.
    # The store hands over real Timestamps, but a direct caller could pass
    # mixed representations ("2026-01-08" vs "2026-01-08 00:00:00"); without
    # normalization the duplicate check and the dates list would treat the
    # SAME session as two different rows. Unparseable dates fail loudly.
    try:
        trading_dates = pd.to_datetime(df["trading_date"], format="mixed")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"unparseable trading_date in backtest input: {exc}") from exc

    data = df.copy()
    data["trading_date"] = trading_dates
    data = data.sort_values("trading_date").reset_index(drop=True)
    n = len(data)
    warnings: list[str] = []

    if n < 2:
        raise ValueError(f"need at least 2 bars to backtest, got {n}")

    # Duplicate sessions would silently double-count bars (and could let the
    # same signal fill twice on one calendar day). The store can surface
    # duplicate-date rows flagged `suspect`, so this is rejected loudly rather
    # than priced twice.
    dup_mask = data["trading_date"].duplicated(keep=False)
    if bool(dup_mask.any()):
        dupes = sorted(
            {
                str(d.date()) if hasattr(d, "date") else str(d)
                for d in data.loc[dup_mask, "trading_date"]
            }
        )
        raise ValueError(
            f"duplicate trading date(s) in input: {', '.join(dupes[:5])} - a "
            "backtest needs exactly one row per session"
        )

    raw = signal_fn(data)
    if len(raw) != n:
        raise ValueError(f"signal length {len(raw)} does not match bars {n}")
    signal = np.asarray(raw, dtype=float)
    if not np.all(np.isin(signal[np.isfinite(signal)], (0.0, 1.0, -1.0))):
        raise ValueError("signal must contain only 0 (flat), 1 (long) or -1 (short)")
    if np.any(signal < 0):
        raise ValueError("short signals are not supported (see BacktestConfig.allow_short)")

    dates = [str(d.date()) if hasattr(d, "date") else str(d) for d in data["trading_date"]]
    opens = data["open"].to_numpy(dtype=float)
    closes = data["close"].to_numpy(dtype=float)

    cash = float(cfg.initial_cash)
    units = 0.0
    entry_index = 0
    fees_total = 0.0
    tax_total = 0.0
    tax_computed_any = False
    pre_revision_sides = 0
    open_trade: Trade | None = None
    trades: list[Trade] = []
    equity: list[float] = []
    position_hist: list[int] = []
    skipped_fills = 0
    unaffordable = 0
    stale_marks = 0
    mark: float | None = None  # last usable (finite, positive) close

    pending = 0.0  # signal from the previous bar, filled on this bar (next_open)
    for i in range(n):
        if cfg.execution == "next_open":
            target = pending
            fill = opens[i]
        else:
            target = signal[i]
            fill = closes[i]

        if not np.isfinite(fill) or fill <= 0:
            # Source occasionally publishes a bad/absent open: fall back to the
            # close of the same bar and count it, rather than silently skipping.
            fill = closes[i]
            if not np.isfinite(fill) or fill <= 0:
                skipped_fills += 1
                fill = np.nan

        current = 1.0 if units > 0 else 0.0
        if np.isfinite(fill) and target != current:
            if target > current:
                price = fill * (1.0 + cfg.slippage)
                if schedule is not None:
                    # Tiered costs make affordability implicit: solved exactly
                    # against the schedule (C3/D-y), never against fee_rate.
                    take, buy_costs = _affordable_units(
                        cash, price, dates[i], schedule, cfg.whole_units
                    )
                else:
                    affordable = cash / (price * (1.0 + cfg.fee_rate))
                    take = math.floor(affordable) if cfg.whole_units else affordable
                    buy_costs = None
                if take > 0:
                    if buy_costs is not None:
                        # Cash and basis use the CHARGED (rounded) value, so a
                        # trade reconciles by hand: value + charges = cash out.
                        cost = buy_costs.value
                        fee = buy_costs.total
                        if buy_costs.commission_table.startswith("schedule14_pre"):
                            pre_revision_sides += 1
                    else:
                        cost = take * price
                        fee = cost * cfg.fee_rate
                    cash -= cost + fee
                    fees_total += fee
                    units = take
                    entry_index = i
                    open_trade = Trade(
                        entry_date=dates[i],
                        exit_date=None,
                        entry_price=price,
                        exit_price=None,
                        units=take,
                        fees_paid=fee,
                        entry_value=round(cost, MONEY_DP),
                    )
                else:
                    # The strategy asked to be long but no position was
                    # affordable. Without this the result would report 0%
                    # exposure with no explanation at all.
                    unaffordable += 1
                if units > 0 and mark is None:
                    # Entered before any usable close existed: anchor the mark
                    # to the real fill price (a price that actually traded).
                    mark = float(open_trade.entry_price)
            else:
                price = fill * (1.0 - cfg.slippage)
                if schedule is not None:
                    sell_costs = side_transaction_costs(units * price, "sell", dates[i], schedule)
                    proceeds = sell_costs.value
                    fee = sell_costs.total
                    if sell_costs.commission_table.startswith("schedule14_pre"):
                        pre_revision_sides += 1
                else:
                    proceeds = units * price
                    fee = proceeds * cfg.fee_rate
                cash += proceeds - fee
                fees_total += fee
                if open_trade is not None:
                    # Cost basis already includes the entry fee paid on entry,
                    # so the round-trip P&L counts both sides exactly once.
                    entry_fee = open_trade.fees_paid
                    if schedule is not None and open_trade.entry_value is not None:
                        # Charged-value basis: entry_value already IS the
                        # rounded value + the same rounding the sell side used.
                        cost_basis = open_trade.entry_value + entry_fee
                    else:
                        cost_basis = open_trade.entry_price * open_trade.units + entry_fee
                    tax_amount = 0.0
                    if schedule is not None:
                        tax = capital_gains_tax(
                            cost_basis=cost_basis,
                            net_proceeds=proceeds - fee,
                            entry_date=dates[entry_index],
                            exit_date=dates[i],
                            category=cfg.cgt,
                        )
                        open_trade.taxable_gain = tax.taxable_gain
                        open_trade.capital_gains_tax = tax.amount
                        open_trade.tax_note = tax.reason
                        if tax.computed:
                            tax_computed_any = True
                            tax_total += tax.amount or 0.0
                            tax_amount = tax.amount or 0.0
                    open_trade.exit_date = dates[i]
                    open_trade.exit_price = price
                    open_trade.exit_value = round(proceeds, MONEY_DP)
                    open_trade.fees_paid = entry_fee + fee
                    open_trade.gross_pnl = round(
                        proceeds
                        - (
                            open_trade.entry_value
                            if open_trade.entry_value is not None
                            else open_trade.entry_price * open_trade.units
                        ),
                        MONEY_DP,
                    )
                    open_trade.transaction_costs = round(entry_fee + fee, MONEY_DP)
                    open_trade.pnl = (proceeds - fee) - cost_basis - tax_amount
                    open_trade.return_pct = (
                        (open_trade.pnl / cost_basis * 100.0) if cost_basis else None
                    )
                    open_trade.bars_held = i - entry_index
                    trades.append(open_trade)
                    open_trade = None
                units = 0.0

        # --- equity marking -------------------------------------------------
        # Only a FINITE, POSITIVE close is a price a real share could trade
        # at. A missing or zero close must not be read as "the position is
        # worth nothing" - that invents a crash out of a data gap. The
        # position is marked at the last usable close instead, and the bar is
        # counted. The stored historical row is never altered (B-21 / R1).
        close_i = closes[i]
        usable_close = bool(np.isfinite(close_i) and close_i > 0)
        if usable_close:
            mark = float(close_i)
        if units > 0:
            if not usable_close:
                stale_marks += 1
            # ``mark`` is always set while holding (usable close above, or the
            # real entry fill price when the position was opened).
            equity.append(cash + units * (mark if mark is not None else float("nan")))
        else:
            equity.append(cash)
        position_hist.append(1 if units > 0 else 0)
        pending = signal[i]

    if skipped_fills:
        warnings.append(
            f"{skipped_fills} bar(s) had no usable price for a fill; those fills were skipped"
        )
    if unaffordable:
        warnings.append(
            f"{unaffordable} long signal(s) could not be filled: cash could not "
            "afford even one unit at the fill price"
        )
    if stale_marks:
        warnings.append(
            f"{stale_marks} held bar(s) had no usable close to mark the position; "
            "those bars are valued at the last usable close (STALE), never at a "
            "fabricated price and never collapsed to zero"
        )
    if schedule is not None and cfg.cgt is None:
        warnings.append(
            "capital gains tax was NOT computed: the investor category is not "
            "an engine input and will not be inferred; set cgt='natural_person' "
            "to declare it and include CGT in net P&L"
        )
    if pre_revision_sides:
        warnings.append(
            f"{pre_revision_sides} side(s) predate the 2024-05-14 commission "
            "revision and were priced with the officially superseded SEBON "
            "table (सङ्ग्रह २०८०)"
        )

    # Close any still-open position for accounting purposes (marked, not sold).
    open_at_end = units > 0
    if open_trade is not None:
        open_trade.exit_date = None
        open_trade.exit_price = None
        open_trade.bars_held = n - 1 - entry_index
        trades.append(open_trade)

    final_equity = equity[-1]
    days = 0.0
    try:
        d0 = pd.Timestamp(dates[0])
        d1 = pd.Timestamp(dates[-1])
        days = float((d1 - d0).days)
    except (ValueError, TypeError):
        days = float(n)

    daily_returns = (
        np.diff(equity) / np.asarray(equity[:-1], dtype=float) if n > 1 else np.array([])
    )
    daily_returns = daily_returns[np.isfinite(daily_returns)]

    exposure = float(np.mean(position_hist)) if position_hist else 0.0
    closed = [t for t in trades if t.exit_date is not None and t.pnl is not None]
    wins = [t for t in closed if (t.pnl or 0) > 0]
    realized = float(sum(t.pnl for t in closed))
    unrealized: float | None = None
    if open_at_end and open_trade is not None and mark is not None:
        # Consistent with the final equity mark: value minus the cost basis
        # (entry price x units + the entry fee actually paid; the charged
        # value when the schedule priced the entry).
        basis = (
            (open_trade.entry_value or 0.0) + open_trade.fees_paid
            if open_trade.entry_value is not None
            else open_trade.entry_price * open_trade.units + open_trade.fees_paid
        )
        unrealized = units * mark - basis

    # Benchmark: buy and hold with the same cost model.
    benchmark = _buy_and_hold_benchmark(opens, closes, cfg, n, first_date=dates[0])
    cagr_value = cagr(cfg.initial_cash, final_equity, days)
    sharpe_value = sharpe_ratio(daily_returns)

    metrics: dict[str, Any] = {
        "initial_cash": cfg.initial_cash,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity / cfg.initial_cash - 1.0) * 100.0, 4),
        "cagr_pct": None if cagr_value is None else round(cagr_value * 100.0, 4),
        "max_drawdown_pct": round(max_drawdown(equity) * 100.0, 4),
        "sharpe": None if sharpe_value is None else round(sharpe_value, 4),
        "trades": len(closed),
        "open_position_at_end": open_at_end,
        "win_rate_pct": None if not closed else round(100.0 * len(wins) / len(closed), 2),
        "exposure_pct": round(exposure * 100.0, 2),
        "fees_paid": round(fees_total, 2),
        # ``avg_trade_pct`` averages Trade.return_pct, which - like every
        # ``*_pct`` field in this payload - is a PERCENT, not a fraction.
        "avg_trade_pct": None
        if not closed
        else round(float(np.mean([(t.return_pct or 0.0) for t in closed])), 4),
        "realized_pnl": round(realized, 2),
        "unrealized_pnl": None if unrealized is None else round(unrealized, 2),
        # CGT is tracked SEPARATELY from fees; None means "not computed for
        # this run" (investor category not declared), never "zero tax".
        "capital_gains_tax_paid": None if not tax_computed_any else round(tax_total, 2),
        "benchmark_total_return_pct": benchmark["total_return_pct"],
        "benchmark_final_equity": benchmark["final_equity"],
        "active_days": int(np.sum(position_hist)),
        "total_days": n,
    }

    assumptions = _assumptions(cfg, dates, days, n)
    if open_at_end:
        warnings.append(
            "a position was still open at the end of the sample; it is marked to "
            "market, not closed, so it contributes no realised trade"
        )
    if len(closed) < 5:
        warnings.append(
            f"only {len(closed)} completed trade(s): win rate and average trade are "
            "not statistically meaningful"
        )
    if days < 365:
        warnings.append("sample shorter than one year: annualised figures are unreliable")

    return BacktestResult(
        symbol=symbol,
        strategy=strategy or "custom",
        params=params or {},
        config=asdict(cfg),
        start=dates[0],
        end=dates[-1],
        bars=n,
        metrics=metrics,
        equity=[
            {"date": d, "equity": round(e, 2), "position": p}
            for d, e, p in zip(dates, equity, position_hist, strict=True)
        ],
        trades=[asdict(t) for t in trades],
        assumptions=assumptions,
        warnings=warnings,
        cost_model=cost_model(cfg),
    )


def _buy_and_hold_benchmark(
    opens: np.ndarray, closes: np.ndarray, cfg: BacktestConfig, n: int, first_date: str = ""
) -> dict[str, Any]:
    """Same cost model, invested on the first bar and held.

    With a schedule, the BUY-side charges are the schedule's (tiered
    commission + SEBON; no DP, no CGT — the benchmark never sells), priced at
    ``first_date`` so effectiveness dating matches the strategy's own entry.
    """
    fill = opens[0] if np.isfinite(opens[0]) and opens[0] > 0 else closes[0]
    if not np.isfinite(fill) or fill <= 0:
        return {"total_return_pct": None, "final_equity": None}
    price = fill * (1.0 + cfg.slippage)
    schedule = get_fee_schedule(cfg.fee_schedule) if cfg.fee_schedule is not None else None
    if schedule is not None:
        units, buy_costs = _affordable_units(
            cfg.initial_cash, price, first_date or "9999-12-31", schedule, cfg.whole_units
        )
        invested = buy_costs.value
        fee = buy_costs.total
    else:
        affordable = cfg.initial_cash / (price * (1.0 + cfg.fee_rate))
        units = math.floor(affordable) if cfg.whole_units else affordable
        invested = units * price
        fee = invested * cfg.fee_rate
    cash = cfg.initial_cash - invested - fee
    last = closes[-1]
    if not np.isfinite(last) or last <= 0:
        # A zero/absent final close is not a price; returning a number built
        # from it would fabricate a benchmark return.
        return {"total_return_pct": None, "final_equity": None}
    final = cash + units * last
    return {
        "total_return_pct": round((final / cfg.initial_cash - 1.0) * 100.0, 4),
        "final_equity": round(final, 2),
    }


def _assumptions(cfg: BacktestConfig, dates: list[str], days: float, bars: int) -> list[str]:
    exec_note = (
        "Signals fill on the NEXT bar's open - no lookahead."
        if cfg.execution == "next_open"
        else "OPTIMISTIC MODE: signals fill at the close of the bar that produced "
        "them, which a real order could not have done. Compare against next_open."
    )
    status = cost_status(cfg)
    tax_note: str | None = None
    if cfg.fee_schedule is not None:
        # Component schedule in force: describe IT, not the flat fee_rate
        # (the schedule's own provenance travels in cost_model).
        sched = get_fee_schedule(cfg.fee_schedule)
        fee_note = (
            f"Cost model: official component schedule '{sched.name}' — tiered "
            f"broker commission by transaction size (min NPR {MIN_COMMISSION_NPR:.0f}), "
            f"the SEBON charge per side, the NPR 25 sell-side DP charge; slippage "
            f"{cfg.slippage:.4%}. Sides before {COMMISSION_REVISION_DATE} use the "
            "officially superseded commission table (सङ्ग्रह २०८०); the SEBON and "
            "DP charges have no documented effective date and are applied to the "
            "whole sample."
        )
        tax_note = (
            "Capital gains tax: computed per closed trade at disposal — natural "
            "person (declared), >365 days vs <=365 days rates, pre-2026-07-15 "
            "disposals at the pre-amendment rates, a loss never taxed, gain "
            "taken net of transaction charges."
            if cfg.cgt is not None
            else "Capital gains tax: NOT computed — the investor category is "
            "not an engine input and will not be inferred; declare "
            "cgt='natural_person' to include it in net P&L."
        )
    elif status == "verified":
        fee_note = (
            f"Cost model: {cfg.fee_rate:.4%} of traded value per side, "
            f"slippage {cfg.slippage:.4%}. VERIFIED rate from source "
            f"'{cfg.fee_source}', effective {cfg.fee_effective_from}."
        )
    elif status == "placeholder":
        fee_note = (
            f"Cost model: {cfg.fee_rate:.4%} of traded value per side, "
            f"slippage {cfg.slippage:.4%}. The fee is a PLACEHOLDER - confirm real "
            "NEPSE commission and charges with your broker."
        )
    else:
        fee_note = (
            f"Cost model: {cfg.fee_rate:.4%} of traded value per side, "
            f"slippage {cfg.slippage:.4%}. CUSTOM rate supplied to this run - "
            "UNVERIFIED and not an authoritative NEPSE figure."
        )
    return [
        exec_note,
        fee_note,
        *([tax_note] if tax_note is not None else []),
        "Prices are UNADJUSTED for bonus/rights issues, so long-horizon returns "
        "are price returns, not total returns. Dividends are not modelled.",
        "Filled in whole units (cash remainder stays uninvested). NEPSE board "
        "lots are company-specific and are NOT modelled."
        if cfg.whole_units
        else "Fractional units are filled - NEPSE does not actually allow this.",
        "Long/flat only. Shorting is not modelled because NEPSE has no retail shorting.",
        "No partial fills, order queues, circuit-breaker limits, suspension days, "
        "liquidity limits or T+2 settlement delays are modelled.",
        f"Annualisation uses {TRADING_DAYS_PER_YEAR} trading days/year; the "
        "Sharpe ratio has no risk-free rate subtracted.",
        f"Sample: {bars} bars, {dates[0]} to {dates[-1]} ({days:.0f} calendar days).",
        "Past performance does not indicate future results. This is a research "
        "calculation, not a forecast or advice.",
    ]


# ==========================================================================
# Expanded algorithm library.
#
# Every strategy below shares the founders' contract exactly: ``sig(df)``
# returns an ``int8`` numpy array of length ``len(df)`` where 1 = long and
# 0 = flat, computed from PRIOR bars only (no look-ahead). They are registered
# into ``STRATEGIES`` at import time so ``/api/backtest`` runs them through the
# identical engine, cost model and metrics as the founders.
# ==========================================================================


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.astype(float).ewm(span=max(1, int(n)), adjust=False).mean()


def _flat(df: pd.DataFrame) -> pd.Series:
    return pd.Series(0.0, index=df.index)


def _rsi_series(close: pd.Series, n: int) -> pd.Series:
    delta = close.astype(float).diff()
    up = delta.clip(lower=0.0).ewm(alpha=1.0 / max(1, int(n)), adjust=False).mean()
    dn = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / max(1, int(n)), adjust=False).mean()
    rs = up / dn.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_series(df: pd.DataFrame, n: int) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev = close.shift(1)
    tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / max(1, int(n)), adjust=False).mean()


def _hold_while(cond: pd.Series, df: pd.DataFrame) -> np.ndarray:
    pos = _flat(df)
    pos[cond.fillna(False)] = 1.0
    return pos.to_numpy(dtype=np.int8)


# ---- trend ---------------------------------------------------------------
def ema_cross(fast: int = 12, slow: int = 26) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        return _hold_while(_ema(c, fast) > _ema(c, slow), df)
    return sig


def triple_ma(fast: int = 20, mid: int = 50, slow: int = 200) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        return _hold_while((_sma(c, fast) > _sma(c, mid)) & (_sma(c, mid) > _sma(c, slow)), df)
    return sig


def price_above_rising_sma(period: int = 50, slope_days: int = 5) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        ma = _sma(c, period)
        return _hold_while((c > ma) & (ma > ma.shift(int(slope_days))), df)
    return sig


def adx_di_trend(period: int = 14, threshold: float = 20.0) -> SignalFn:
    def sig(df):
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        up = high.diff()
        dn = -low.diff()
        plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
        minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
        atr = _atr_series(df, period)
        pdi = 100.0 * plus.ewm(alpha=1.0 / period, adjust=False).mean() / atr.replace(0, np.nan)
        mdi = 100.0 * minus.ewm(alpha=1.0 / period, adjust=False).mean() / atr.replace(0, np.nan)
        dx = 100.0 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
        adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
        return _hold_while((adx > threshold) & (pdi > mdi), df)
    return sig


def linreg_slope_trend(period: int = 60) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        x = np.arange(int(period))
        xm = x.mean()
        denom = ((x - xm) ** 2).sum()

        def slope(w):
            return float(((x - xm) * (w - w.mean())).sum() / denom)

        s = c.rolling(int(period), min_periods=int(period)).apply(slope, raw=True)
        return _hold_while(s > 0, df)
    return sig


def turtle_55(breakout_days: int = 55, exit_days: int = 20) -> SignalFn:
    return donchian_breakout(breakout_days=breakout_days, exit_days=exit_days)


def channel_midpoint_trend(period: int = 60) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        hi = c.rolling(period, min_periods=2).max()
        lo = c.rolling(period, min_periods=2).min()
        mid = (hi + lo) / 2.0
        return _hold_while(c > mid, df)
    return sig


def supertrend(atr_days: int = 10, multiplier: float = 3.0) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        atr = _atr_series(df, atr_days)
        upper = c - multiplier * atr
        # Trailing long stop: ratchet up only.
        stop = upper.copy()
        for i in range(1, len(stop)):
            if pd.isna(stop.iloc[i]):
                continue
            if pd.isna(stop.iloc[i - 1]):
                continue
            stop.iloc[i] = max(stop.iloc[i], stop.iloc[i - 1]) if c.iloc[i] > stop.iloc[i - 1] else upper.iloc[i]
        return _hold_while(c > stop, df)
    return sig


# ---- momentum ------------------------------------------------------------
def roc_momentum(days: int = 60, min_pct: float = 0.0) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        roc = c / c.shift(int(days)) - 1.0
        return _hold_while(roc > float(min_pct) / 100.0, df)
    return sig


def momentum_with_vol_filter(momentum_days: int = 90, vol_days: int = 20, max_vol: float = 0.6) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        mom = c / c.shift(int(momentum_days)) - 1.0
        vol = c.pct_change().rolling(int(vol_days)).std() * np.sqrt(252)
        return _hold_while((mom > 0) & (vol < float(max_vol)), df)
    return sig


def momentum_12_1(days: int = 252, skip: int = 21) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        end = c.shift(int(skip))
        start = c.shift(int(skip) + int(days))
        return _hold_while(end / start - 1.0 > 0, df)
    return sig


def momentum_acceleration(short: int = 20, long: int = 60) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        rs = c / c.shift(int(short)) - 1.0
        rl = c / c.shift(int(long)) - 1.0
        return _hold_while((rs > 0) & (rs > rl), df)
    return sig


def macd_zero_cross(fast: int = 12, slow: int = 26, signal: int = 9) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        macd = _ema(c, fast) - _ema(c, slow)
        trig = _ema(macd, signal)
        return _hold_while((macd > trig) & (macd > 0), df)
    return sig


def stochastic_momentum(k_days: int = 14, d_days: int = 3) -> SignalFn:
    def sig(df):
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        ll = low.rolling(int(k_days)).min()
        hh = high.rolling(int(k_days)).max()
        k = 100.0 * (close - ll) / (hh - ll).replace(0, np.nan)
        d = k.rolling(int(d_days)).mean()
        return _hold_while(k > d, df)
    return sig


def williams_momentum(days: int = 14, threshold: float = -50.0) -> SignalFn:
    def sig(df):
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        hh = high.rolling(int(days)).max()
        ll = low.rolling(int(days)).min()
        wr = -100.0 * (hh - close) / (hh - ll).replace(0, np.nan)
        return _hold_while(wr > float(threshold), df)
    return sig


def rsi_trend_filter(period: int = 14, threshold: float = 50.0) -> SignalFn:
    def sig(df):
        return _hold_while(_rsi_series(df["close"], period) > float(threshold), df)
    return sig


def cmf_trend(period: int = 20, threshold: float = 0.0) -> SignalFn:
    def sig(df):
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        vol = df["volume"].astype(float) if "volume" in df else pd.Series(1.0, index=df.index)
        mfm = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
        mfv = mfm * vol
        cmf = mfv.rolling(int(period)).sum() / vol.rolling(int(period)).sum().replace(0, np.nan)
        return _hold_while(cmf > float(threshold), df)
    return sig


# ---- mean reversion ------------------------------------------------------
def zscore_revert(window: int = 20, entry_z: float = -1.5, exit_z: float = 0.0) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        m = c.rolling(int(window)).mean()
        s = c.rolling(int(window)).std()
        z = (c - m) / s.replace(0, np.nan)
        pos = _flat(df)
        pos[z < float(entry_z)] = 1.0
        pos[z > float(exit_z)] = 0.0
        pos[z.isna()] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def percent_b_revert(period: int = 20, band_k: float = 2.0, entry: float = 0.0) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        m = _sma(c, period)
        s = c.rolling(int(period)).std()
        upper = m + band_k * s
        lower = m - band_k * s
        pb = (c - lower) / (upper - lower).replace(0, np.nan)
        pos = _flat(df)
        pos[pb < float(entry)] = 1.0
        pos[pb > 0.5] = 0.0
        pos[pb.isna()] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def distance_ma_revert(period: int = 20, pct: float = 0.10) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        m = _sma(c, period)
        dev = c / m - 1.0
        pos = _flat(df)
        pos[dev < -abs(float(pct))] = 1.0
        pos[dev > 0] = 0.0
        pos[dev.isna()] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def keltner_revert(period: int = 20, mult: float = 2.0) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        mid = _ema(c, period)
        atr = _atr_series(df, period)
        lower = mid - mult * atr
        pos = _flat(df)
        pos[c < lower] = 1.0
        pos[c > mid] = 0.0
        pos[(c >= lower) & (c <= mid)] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def rsi4_reversion(period: int = 4, buy_below: float = 25.0, exit_above: float = 60.0) -> SignalFn:
    def sig(df):
        r = _rsi_series(df["close"], period)
        pos = _flat(df)
        pos[r < float(buy_below)] = 1.0
        pos[r > float(exit_above)] = 0.0
        pos[r.isna()] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def williams_revert(days: int = 14, buy_below: float = -80.0, exit_above: float = -20.0) -> SignalFn:
    def sig(df):
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        hh = high.rolling(int(days)).max()
        ll = low.rolling(int(days)).min()
        wr = -100.0 * (hh - close) / (hh - ll).replace(0, np.nan)
        pos = _flat(df)
        pos[wr < float(buy_below)] = 1.0
        pos[wr > float(exit_above)] = 0.0
        pos[wr.isna()] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def cci_revert(days: int = 20, buy_below: float = -100.0, exit_above: float = 0.0) -> SignalFn:
    def sig(df):
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        tp = (high + low + close) / 3.0
        ma = tp.rolling(int(days)).mean()
        md = (tp - ma).abs().rolling(int(days)).mean()
        cci = (tp - ma) / (0.015 * md.replace(0, np.nan))
        pos = _flat(df)
        pos[cci < float(buy_below)] = 1.0
        pos[cci > float(exit_above)] = 0.0
        pos[cci.isna()] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def gap_reversion(max_gap: float = 0.05) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        o = df["open"].astype(float) if "open" in df else c.shift(1)
        gap = o / c.shift(1) - 1.0
        pos = _flat(df)
        pos[gap < -abs(float(max_gap))] = 1.0
        pos[gap > 0] = 0.0
        pos[gap.isna()] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


# ---- breakout & pullback -------------------------------------------------
def breakout_pullback(breakout_days: int = 20, pullback_pct: float = 0.03, exit_days: int = 10) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        hi = c.rolling(int(breakout_days), min_periods=2).max().shift(1)
        broke = c > hi
        # Enter when, after a breakout in the last 10 bars, price pulls back to
        # within pullback_pct of the breakout level but stays above the exit low.
        recent_break = broke.rolling(10, min_periods=1).max().fillna(0) > 0
        near = c >= hi * (1.0 - float(pullback_pct))
        lo = c.rolling(int(exit_days), min_periods=2).min().shift(1)
        pos = _flat(df)
        pos[recent_break & near & (c > lo)] = 1.0
        pos[c < lo] = 0.0
        pos[~(recent_break & near) & ~(c < lo)] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def nr7_breakout() -> SignalFn:
    def sig(df):
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        rng = high - low
        nr7 = rng <= rng.rolling(7).min() + 1e-12
        entry = nr7.shift(1).fillna(False) & (close > high.shift(1))
        pos = _flat(df)
        pos[entry] = 1.0
        pos[~entry] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def inside_bar_breakout() -> SignalFn:
    def sig(df):
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        inside = (high < high.shift(1)) & (low > low.shift(1))
        entry = inside.shift(1).fillna(False) & (close > high.shift(1))
        exit_ = inside.shift(1).fillna(False) & (close < low.shift(1))
        pos = _flat(df)
        pos[entry] = 1.0
        pos[exit_] = 0.0
        pos[~entry & ~exit_] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def high_52w_breakout(window: int = 250, exit_ma: int = 20) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        hi = c.rolling(int(window), min_periods=2).max().shift(1)
        ma = _sma(c, exit_ma)
        pos = _flat(df)
        pos[c > hi] = 1.0
        pos[c < ma] = 0.0
        pos[(c <= hi) & (c >= ma)] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def range_expansion_breakout(range_days: int = 20, mult: float = 2.0) -> SignalFn:
    def sig(df):
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        rng = high - low
        base = rng.rolling(int(range_days)).mean().shift(1)
        pos = _flat(df)
        pos[(rng > mult * base) & (close > close.shift(1))] = 1.0
        pos[(rng > mult * base) & (close < close.shift(1))] = 0.0
        pos[~(rng > mult * base)] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def volatility_breakout(atr_days: int = 14, k: float = 2.0) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        atr = _atr_series(df, atr_days)
        prev = c.shift(1)
        pos = _flat(df)
        pos[c > prev + k * atr] = 1.0
        pos[c < prev - k * atr] = 0.0
        pos[(c <= prev + k * atr) & (c >= prev - k * atr)] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


def volume_breakout(volume_mult: float = 2.0, price_days: int = 20) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        vol = df["volume"].astype(float) if "volume" in df else pd.Series(1.0, index=df.index)
        base = vol.rolling(20).mean().shift(1)
        hi = c.rolling(int(price_days), min_periods=2).max().shift(1)
        pos = _flat(df)
        pos[(vol > volume_mult * base) & (c > hi)] = 1.0
        pos[(vol > volume_mult * base) & (c < c.shift(1))] = 0.0
        pos[~(vol > volume_mult * base)] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


# ---- risk-managed --------------------------------------------------------
def atr_trailing_stop_trend(period: int = 50, atr_days: int = 14, k: float = 3.0) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        ma = _sma(c, period)
        atr = _atr_series(df, atr_days)
        trail = (c - k * atr).cummax()
        pos = _flat(df)
        pos[(c > ma) & (c > trail)] = 1.0
        pos[(c < ma) | (c < trail)] = 0.0
        return pos.to_numpy(dtype=np.int8)
    return sig


def drawdown_guard(period: int = 50, max_drawdown: float = 0.15) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        peak = c.cummax()
        dd = c / peak - 1.0
        trend = c > _sma(c, period)
        return _hold_while(trend & (dd > -abs(float(max_drawdown))), df)
    return sig


def volatility_target_trend(period: int = 100, vol_days: int = 20, target_vol: float = 0.35) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        trend = c > _sma(c, period)
        vol = c.pct_change().rolling(int(vol_days)).std() * np.sqrt(252)
        return _hold_while(trend & (vol < float(target_vol)), df)
    return sig


def trend_with_stop(period: int = 50, stop_pct: float = 0.08) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        ma = _sma(c, period)
        pos = _flat(df)
        pos[c > ma] = 1.0
        pos[c < ma * (1.0 - float(stop_pct))] = 0.0
        pos[(c <= ma) & (c >= ma * (1.0 - float(stop_pct)))] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


# ---- volume --------------------------------------------------------------
def obv_breakout(ema_days: int = 20, lookback: int = 60) -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        vol = df["volume"].astype(float) if "volume" in df else pd.Series(1.0, index=df.index)
        direction = np.sign(c.diff().fillna(0.0))
        obv = (direction * vol).cumsum()
        return _hold_while(obv > obv.rolling(int(lookback)).max().shift(1) * 0.999, df)
    return sig


def pocket_pivot_volume() -> SignalFn:
    def sig(df):
        c = df["close"].astype(float)
        vol = df["volume"].astype(float) if "volume" in df else pd.Series(1.0, index=df.index)
        up = c > c.shift(1)
        down = c < c.shift(1)
        prior_down_max = vol.where(down).rolling(10, min_periods=1).max().shift(1)
        entry = up & (vol > prior_down_max)
        pos = _flat(df)
        pos[entry] = 1.0
        pos[~entry] = np.nan
        return pos.ffill().fillna(0).to_numpy(dtype=np.int8)
    return sig


_NEW_STRATEGIES: dict[str, dict[str, Any]] = {
    "ema_cross": {"label": "EMA crossover", "description": "Long while EMA(fast) > EMA(slow). Smooth trend rule.",
                   "params": {"fast": 12, "slow": 26}, "factory": ema_cross, "category": "trend"},
    "triple_ma": {"label": "Triple moving-average stack", "description": "Long while SMA(fast) > SMA(mid) > SMA(slow).",
                   "params": {"fast": 20, "mid": 50, "slow": 200}, "factory": triple_ma, "category": "trend"},
    "price_above_rising_sma": {"label": "Price above rising SMA", "description": "Long while price > SMA and the SMA is rising.",
                   "params": {"period": 50, "slope_days": 5}, "factory": price_above_rising_sma, "category": "trend"},
    "adx_di_trend": {"label": "ADX/+DI trend", "description": "Long while ADX exceeds a threshold and +DI > -DI.",
                   "params": {"period": 14, "threshold": 20.0}, "factory": adx_di_trend, "category": "trend"},
    "linreg_slope_trend": {"label": "Linear-regression slope", "description": "Long while the rolling OLS slope of price is positive.",
                   "params": {"period": 60}, "factory": linreg_slope_trend, "category": "trend"},
    "turtle_55": {"label": "Turtle 55/20", "description": "Long on a 55-day high, exit below the 20-day low.",
                   "params": {"breakout_days": 55, "exit_days": 20}, "factory": turtle_55, "category": "breakout"},
    "channel_midpoint_trend": {"label": "Channel-midpoint trend", "description": "Long while price is above the midpoint of its trailing channel.",
                   "params": {"period": 60}, "factory": channel_midpoint_trend, "category": "trend"},
    "supertrend": {"label": "Supertrend (ATR trailing)", "description": "Long while price is above a ratcheting ATR trailing stop.",
                   "params": {"atr_days": 10, "multiplier": 3.0}, "factory": supertrend, "category": "trend"},
    "roc_momentum": {"label": "Rate-of-change (N-day)", "description": "Long while the N-day rate of change exceeds a floor.",
                   "params": {"days": 60, "min_pct": 0.0}, "factory": roc_momentum, "category": "momentum"},
    "momentum_with_vol_filter": {"label": "Momentum + volatility filter", "description": "Long on positive momentum only while realized volatility stays below a cap.",
                   "params": {"momentum_days": 90, "vol_days": 20, "max_vol": 0.6}, "factory": momentum_with_vol_filter, "category": "momentum"},
    "momentum_12_1": {"label": "12-1 momentum", "description": "Classic 12-month momentum skipping the most recent month.",
                   "params": {"days": 252, "skip": 21}, "factory": momentum_12_1, "category": "momentum"},
    "momentum_acceleration": {"label": "Momentum acceleration", "description": "Long while short-term momentum is positive and exceeds long-term momentum.",
                   "params": {"short": 20, "long": 60}, "factory": momentum_acceleration, "category": "momentum"},
    "macd_zero_cross": {"label": "MACD above zero", "description": "Long while MACD is above its signal AND above zero.",
                   "params": {"fast": 12, "slow": 26, "signal": 9}, "factory": macd_zero_cross, "category": "momentum"},
    "stochastic_momentum": {"label": "Stochastic momentum", "description": "Long while %K is above %D.",
                   "params": {"k_days": 14, "d_days": 3}, "factory": stochastic_momentum, "category": "momentum"},
    "williams_momentum": {"label": "Williams %R momentum", "description": "Long while Williams %R is above a threshold.",
                   "params": {"days": 14, "threshold": -50.0}, "factory": williams_momentum, "category": "momentum"},
    "rsi_trend_filter": {"label": "RSI trend filter", "description": "Long while RSI is above a threshold (trend-side, not reversion).",
                   "params": {"period": 14, "threshold": 50.0}, "factory": rsi_trend_filter, "category": "momentum"},
    "cmf_trend": {"label": "Chaikin money-flow trend", "description": "Long while the Chaikin Money Flow is positive.",
                   "params": {"period": 20, "threshold": 0.0}, "factory": cmf_trend, "category": "volume"},
    "zscore_revert": {"label": "Z-score reversion", "description": "Long when price is z standard deviations below its mean; exit at the mean.",
                   "params": {"window": 20, "entry_z": -1.5, "exit_z": 0.0}, "factory": zscore_revert, "category": "reversion"},
    "percent_b_revert": {"label": "Bollinger %B reversion", "description": "Long when %B is below a threshold; exit above the mid band.",
                   "params": {"period": 20, "band_k": 2.0, "entry": 0.0}, "factory": percent_b_revert, "category": "reversion"},
    "distance_ma_revert": {"label": "Distance-from-MA reversion", "description": "Long when price is a set fraction below its MA; exit at the MA.",
                   "params": {"period": 20, "pct": 0.10}, "factory": distance_ma_revert, "category": "reversion"},
    "keltner_revert": {"label": "Keltner reversion", "description": "Long below the lower Keltner channel; exit at the EMA.",
                   "params": {"period": 20, "mult": 2.0}, "factory": keltner_revert, "category": "reversion"},
    "rsi4_reversion": {"label": "RSI(4) reversion", "description": "Connors-style short-period RSI reversion.",
                   "params": {"period": 4, "buy_below": 25.0, "exit_above": 60.0}, "factory": rsi4_reversion, "category": "reversion"},
    "williams_revert": {"label": "Williams %R reversion", "description": "Long when %R is deeply oversold; exit when it recovers.",
                   "params": {"days": 14, "buy_below": -80.0, "exit_above": -20.0}, "factory": williams_revert, "category": "reversion"},
    "cci_revert": {"label": "CCI reversion", "description": "Long when CCI is below -100; exit above 0.",
                   "params": {"days": 20, "buy_below": -100.0, "exit_above": 0.0}, "factory": cci_revert, "category": "reversion"},
    "gap_reversion": {"label": "Gap-down reversion", "description": "Long after a large opening gap down; exit once the gap closes.",
                   "params": {"max_gap": 0.05}, "factory": gap_reversion, "category": "reversion"},
    "breakout_pullback": {"label": "Breakout + pullback", "description": "Enter on a shallow pullback toward a recent breakout level; exit below the range low.",
                   "params": {"breakout_days": 20, "pullback_pct": 0.03, "exit_days": 10}, "factory": breakout_pullback, "category": "breakout"},
    "nr7_breakout": {"label": "NR7 breakout", "description": "Buy when a narrowest-range-7 day is followed by an upside break.",
                   "params": {}, "factory": nr7_breakout, "category": "breakout"},
    "inside_bar_breakout": {"label": "Inside-bar breakout", "description": "Trade the break of the bar following an inside bar.",
                   "params": {}, "factory": inside_bar_breakout, "category": "breakout"},
    "high_52w_breakout": {"label": "52-week-high breakout", "description": "Long on a new 250-day high; exit below a 20-day MA.",
                   "params": {"window": 250, "exit_ma": 20}, "factory": high_52w_breakout, "category": "breakout"},
    "range_expansion_breakout": {"label": "Range-expansion breakout", "description": "Trade in the direction of an unusually wide range bar.",
                   "params": {"range_days": 20, "mult": 2.0}, "factory": range_expansion_breakout, "category": "breakout"},
    "volatility_breakout": {"label": "Volatility breakout (ATR)", "description": "Long above previous close + k×ATR; exit below previous close - k×ATR.",
                   "params": {"atr_days": 14, "k": 2.0}, "factory": volatility_breakout, "category": "breakout"},
    "volume_breakout": {"label": "Volume-confirmed breakout", "description": "Long only when a price breakout coincides with a volume surge.",
                   "params": {"volume_mult": 2.0, "price_days": 20}, "factory": volume_breakout, "category": "breakout"},
    "atr_trailing_stop_trend": {"label": "ATR trailing-stop trend", "description": "Trend rule with an ATR trailing stop that only ratchets up.",
                   "params": {"period": 50, "atr_days": 14, "k": 3.0}, "factory": atr_trailing_stop_trend, "category": "risk"},
    "drawdown_guard": {"label": "Drawdown guard", "description": "Trend-follow but exit whenever drawdown from the peak exceeds a cap.",
                   "params": {"period": 50, "max_drawdown": 0.15}, "factory": drawdown_guard, "category": "risk"},
    "volatility_target_trend": {"label": "Volatility-filtered trend", "description": "Trend rule that stands aside when realized volatility is above a target.",
                   "params": {"period": 100, "vol_days": 20, "target_vol": 0.35}, "factory": volatility_target_trend, "category": "risk"},
    "trend_with_stop": {"label": "Trend with fixed stop", "description": "Long above the MA; exit on a fixed percentage stop below the MA.",
                   "params": {"period": 50, "stop_pct": 0.08}, "factory": trend_with_stop, "category": "risk"},
    "obv_breakout": {"label": "OBV breakout", "description": "Long when on-balance volume makes a new N-day high.",
                   "params": {"ema_days": 20, "lookback": 60}, "factory": obv_breakout, "category": "volume"},
    "pocket_pivot_volume": {"label": "Pocket-pivot volume rule", "description": "Long on a pocket-pivot day (up close on volume above every prior down-day volume).",
                   "params": {}, "factory": pocket_pivot_volume, "category": "volume"},
}

STRATEGIES.update(_NEW_STRATEGIES)
