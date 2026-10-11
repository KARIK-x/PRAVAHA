"""Trade planning: the arithmetic of a planned trade, before it is taken.

Pure functions with no I/O so the numbers can be checked by hand. Nothing here
recommends a trade - it only converts the owner's own entry, stop and target
into position size and R multiples.

For a long position: ``stop < entry < target``. NEPSE has no retail shorting,
so short plans are rejected rather than silently supported.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class PlanError(ValueError):
    """Invalid plan input."""


@dataclass(frozen=True)
class TradePlan:
    entry: float
    stop: float
    target: float
    risk_per_share: float
    reward_per_share: float
    risk_reward: float
    risk_pct_of_entry: float
    reward_pct_of_entry: float
    invalidation_pct: float
    target_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PositionSizing:
    capital: float
    risk_pct: float
    risk_per_share: float
    units: int
    cash_used: float
    actual_risk: float
    actual_risk_pct: float
    remainder_cash: float
    rounded_down: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_plan(entry: float, stop: float, target: float) -> TradePlan:
    for name, value in (("entry", entry), ("stop", stop), ("target", target)):
        try:
            v = float(value)
        except (TypeError, ValueError) as exc:
            raise PlanError(f"{name} must be a number") from exc
        if v <= 0:
            raise PlanError(f"{name} must be > 0, got {v}")
    entry, stop, target = float(entry), float(stop), float(target)
    if not stop < entry:
        raise PlanError(
            f"for a long plan the stop must be below the entry (got stop {stop}, "
            f"entry {entry}); NEPSE has no retail shorting, so a short plan is not "
            "supported"
        )
    if not target > entry:
        raise PlanError(f"the target must be above the entry (got target {target}, entry {entry})")

    risk = entry - stop
    reward = target - entry
    return TradePlan(
        entry=entry,
        stop=stop,
        target=target,
        risk_per_share=round(risk, 6),
        reward_per_share=round(reward, 6),
        risk_reward=round(reward / risk, 4),
        risk_pct_of_entry=round(risk / entry * 100.0, 4),
        reward_pct_of_entry=round(reward / entry * 100.0, 4),
        invalidation_pct=round((stop / entry - 1.0) * 100.0, 4),
        target_pct=round((target / entry - 1.0) * 100.0, 4),
    )


def position_size(
    capital: float, risk_pct: float, risk_per_share: float, price: float
) -> PositionSizing:
    """Whole units to buy so that a stop-out loses at most ``risk_pct`` of capital.

    ``risk_pct`` is a percentage (2 means 2%). Rounding is always **down**:
    rounding up would risk more than the stated budget.
    """
    try:
        capital = float(capital)
        risk_pct = float(risk_pct)
        risk_per_share = float(risk_per_share)
        price = float(price)
    except (TypeError, ValueError) as exc:
        raise PlanError("capital, risk_pct, risk_per_share and price must be numbers") from exc
    if capital <= 0:
        raise PlanError("capital must be > 0")
    if not 0 < risk_pct <= 100:
        raise PlanError(f"risk_pct must be in (0, 100], got {risk_pct}")
    if risk_per_share <= 0:
        raise PlanError(f"risk_per_share must be > 0, got {risk_per_share}")
    if price <= 0:
        raise PlanError(f"price must be > 0, got {price}")

    budget = capital * risk_pct / 100.0
    raw_units = budget / risk_per_share
    affordable = capital / price
    units = int(min(raw_units, affordable))
    cash_used = units * price
    actual_risk = units * risk_per_share
    return PositionSizing(
        capital=capital,
        risk_pct=risk_pct,
        risk_per_share=round(risk_per_share, 6),
        units=units,
        cash_used=round(cash_used, 2),
        actual_risk=round(actual_risk, 2),
        actual_risk_pct=round(actual_risk / capital * 100.0, 4),
        remainder_cash=round(capital - cash_used, 2),
        rounded_down=units < raw_units,
    )


def plan_outcome(entry: float, stop: float, target: float, exit_price: float) -> dict[str, Any]:
    """Grade a finished trade against the plan it was supposed to follow."""
    plan = make_plan(entry, stop, target)
    exit_price = float(exit_price)
    r = (exit_price - entry) / plan.risk_per_share
    if exit_price >= target:
        result = "target"
    elif exit_price <= stop:
        result = "stop"
    else:
        result = "neither"
    return {
        "result": result,
        "r_multiple": round(r, 4),
        "planned_r": round(plan.risk_reward, 4),
        "planned_vs_actual_pct": round(
            (exit_price - entry) / entry * 100.0 - plan.reward_pct_of_entry, 4
        ),
        "note": "An R multiple expresses the outcome in units of the risk that was "
        "planned at entry. It is a historical measurement, not a forecast.",
    }
