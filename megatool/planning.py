"""Trade planning: the arithmetic of a planned trade, before it is taken.

Pure functions with no I/O so the numbers can be checked by hand. Nothing here
recommends a trade - it only converts the owner's own entry, stop and target
into position size and R multiples.

For a long position: ``stop < entry < target``. NEPSE has no retail shorting,
so short plans are rejected rather than silently supported.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date as _date
from typing import Any

from megatool.backtest import get_fee_schedule, side_transaction_costs


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
    #: Set when the risk budget cannot even buy one unit: the honest reading
    #: is "do not take this trade at this size", not "buy zero".
    warning: str | None = None

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
    if not all(math.isfinite(v) for v in (capital, risk_pct, risk_per_share, price)):
        # NaN/inf are numbers, and `NaN <= 0` is False, so without this they
        # reach int() below and explode as a plain ValueError (a 500).
        raise PlanError("capital, risk_pct, risk_per_share and price must be finite numbers")
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
    # NOTE: this affordability cap deliberately IGNORES broker/sebon fees and
    # taxes, so the real cash needed for `units` is slightly above cash_used.
    affordable = capital / price
    units = int(min(raw_units, affordable))
    cash_used = units * price
    actual_risk = units * risk_per_share
    # Which limit actually binds? Comparing against `raw_units` would be wrong:
    # it is itself capped by cash, so any truncated size would look cash-limited.
    capped_by_cash = units > 0 and affordable < raw_units
    if units == 0:
        # The honest reading is "this trade is not sizeable", never "buy zero".
        warning = (
            f"Your risk budget (NPR {budget:,.2f}) cannot buy a single unit at "
            f"NPR {price:,.2f}. Do not take this trade at these settings: either "
            f"the stop is too tight for the price, or the size is too small for "
            f"your capital."
        )
    elif capped_by_cash:
        warning = (
            "Sizing is limited by the cash you have, not by your risk budget: "
            "the full capital buys only this many units. This figure EXCLUDES "
            "broker and sebon fees and taxes, so the real order costs slightly "
            "more than cash_used."
        )
    else:
        warning = None
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
        warning=warning,
    )


def entry_cost_estimate(
    value: float, on_date: str | None = None, schedule_name: str = "official-2083-84"
) -> dict[str, Any]:
    """What ONE buy-side order of ``value`` NPR would cost under the verified
    schedule — the same engine the backtester uses (C3/D-y, one fee engine).

    Returns the component breakdown plus an explicit note. This is an
    ESTIMATE for planning: the real contract note is the broker's. ``on_date``
    defaults to today so the commission table honours the 2024-05-14
    revision; no capital-gains tax is included because a buy has none.
    """
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise PlanError("value must be a number") from exc
    if not math.isfinite(v) or v <= 0:
        raise PlanError(f"value must be a finite number > 0, got {value!r}")
    if on_date is None:
        on_date = _date.today().isoformat()
    try:
        schedule = get_fee_schedule(schedule_name)
    except KeyError as exc:
        raise PlanError(str(exc)) from None
    costs = side_transaction_costs(v, "buy", on_date, schedule)
    return {
        **costs.to_dict(),
        "schedule": schedule_name,
        "on_date": on_date,
        "note": (
            "Buy-side estimate from the verified schedule: tiered broker "
            "commission (minimum NPR 10) plus the SEBON charge; no DP charge "
            "(sell side only) and no capital-gains tax (a buy is not a "
            "disposal). An estimate for planning — the broker's contract note "
            "is authoritative."
        ),
    }


def constraint_check(
    *,
    symbol: str | None,
    entry: float,
    sizing: PositionSizing | None = None,
    current_units: int = 0,
    current_price: float | None = None,
    current_price_date: str | None = None,
    valued_total: float = 0.0,
    open_positions: int = 0,
    unvalued_positions: int = 0,
    max_weight_pct: float = 40.0,
) -> dict[str, Any]:
    """Check a planned trade against the owner's local portfolio (feature 11).

    Pure arithmetic over caller-supplied figures - no I/O here. Every weight
    that cannot be computed states its reason instead of being approximated:

    * the current weight is position value (units x latest **stored** close)
      over the valued portfolio total;
    * the post-trade weight adds ``sizing.units`` at the **entry** price to
      both the position and the denominator, under an explicitly stated
      funding assumption (the ledger models no cash, so a purchase funded by
      selling another position must be rechecked after that sale);
    * a held position with no usable stored price leaves both weights
      unchecked rather than inventing a price.

    This is arithmetic, never advice, and it never places or prepares an order.
    """
    if not math.isfinite(max_weight_pct) or not 0 < max_weight_pct <= 100:
        raise PlanError(f"max_weight_pct must be in (0, 100], got {max_weight_pct}")

    sym = symbol.upper().strip() if symbol and symbol.strip() else None
    price_ok = current_price is not None and math.isfinite(current_price) and current_price > 0

    # ------------------------------------------------------------ current
    current_value: float | None = None
    current_weight: float | None = None
    if current_units > 0:
        if not price_ok:
            current_weight_reason = (
                f"no usable stored close for {sym or 'the held symbol'}: the "
                "position's weight cannot be computed without inventing a price"
            )
        elif valued_total <= 0:
            current_weight_reason = (
                "the valued portfolio total is 0 while this position is held: "
                "no denominator to take a share of"
            )
        else:
            current_value = current_units * float(current_price)
            current_weight = current_value / valued_total * 100.0
            current_weight_reason = None
    else:
        current_weight_reason = None
    current = {
        "units": int(current_units),
        "price": current_price if price_ok else None,
        "price_date": current_price_date,
        "value": None if current_value is None else round(current_value, 2),
        "weight_pct": None if current_weight is None else round(current_weight, 4),
        "weight_reason": current_weight_reason if current_units > 0 else None,
    }

    # ---------------------------------------------------------- post-trade
    post: dict[str, Any] = {
        "checked": False,
        "reason": None,
        "units": None,
        "value_at_entry": None,
        "weight_pct": None,
        "within_limit": None,
    }
    if sizing is None:
        post["reason"] = (
            "position sizing not requested: supply capital and risk_pct to "
            "check a post-trade weight"
        )
    elif current_units > 0 and not price_ok:
        post["reason"] = (
            f"cannot check the post-trade weight: {sym or 'the symbol'} is "
            "held but has no usable stored close, and the pre-existing shares "
            "would be missing from the denominator"
        )
    else:
        total_units = int(current_units) + int(sizing.units)
        post_value = total_units * entry
        denominator = valued_total + sizing.units * entry
        if denominator <= 0:
            post["reason"] = "the denominator is zero: no share to compute a share of"
        else:
            weight = post_value / denominator * 100.0
            post.update(
                {
                    "checked": True,
                    "units": total_units,
                    "value_at_entry": round(post_value, 2),
                    "weight_pct": round(weight, 4),
                    "within_limit": weight <= max_weight_pct,
                    "funded_by": (
                        "assumes units x entry of NEW capital enters the "
                        "portfolio at purchase; cash is not modelled, so a "
                        "purchase funded by selling another position must be "
                        "rechecked after that sale"
                    ),
                }
            )

    warnings: list[str] = []
    if sizing is not None and sizing.warning:
        warnings.append(sizing.warning)
    if unvalued_positions:
        warnings.append(
            f"{unvalued_positions} position(s) have no usable stored price: "
            "the denominator counts valued positions only, so the true "
            "post-trade weight may differ from the figure above."
        )
    warnings.append(
        "Weights are arithmetic over stored data (latest stored close / your "
        "entry price), not advice; cash balances are not modelled."
    )

    return {
        "symbol": sym,
        "checked": post["checked"],
        "current": current,
        "post_trade": post,
        "limit": {
            "max_weight_pct": round(float(max_weight_pct), 4),
            "breach": (not post["within_limit"]) if post["checked"] else None,
        },
        "diversification": {
            "open_positions": int(open_positions),
            "symbol_already_held": (current_units > 0) if sym else None,
        },
        "warnings": warnings,
    }


def plan_outcome(entry: float, stop: float, target: float, exit_price: float) -> dict[str, Any]:
    """Grade a finished trade against the plan it was supposed to follow."""
    plan = make_plan(entry, stop, target)
    exit_price = float(exit_price)
    if not math.isfinite(exit_price):
        raise PlanError("exit_price must be a finite number")
    if exit_price <= 0:
        raise PlanError(f"exit_price must be > 0, got {exit_price}")
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
