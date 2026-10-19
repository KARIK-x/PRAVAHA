"""Portfolio intelligence: transactions are the source of truth.

Positions are **derived** from the transaction ledger rather than stored
separately, so the two can never disagree. The ``portfolio_positions`` table
exists only for a position the owner records *without* transactions (for
example a holding predating this tool); every row of the result says which of
the two it came from.

Nothing here places orders, and no cash balance is modelled - the portfolio is
valued in terms of invested positions only, which is stated in the API output.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from megatool.db import get_conn, now_iso

VALID_SIDES = ("buy", "sell")


class PortfolioError(ValueError):
    """Invalid portfolio input (the caller can map this to HTTP 400)."""


@dataclass
class Transaction:
    id: int
    symbol: str
    side: str
    quantity: int
    price: float
    fees: float
    traded_at: str
    notes: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Position:
    symbol: str
    quantity: int
    avg_cost: float
    realized_pnl: float = 0.0
    first_traded_at: str | None = None
    last_traded_at: str | None = None
    buy_value: float = 0.0
    #: Lifetime spend on this symbol (every buy's quantity x price + fees).
    #: It never decreases when you sell, so it is NOT the cost basis - that is
    #: ``avg_cost * quantity``. Kept because it shows how much cash went in.
    origin: str = "transactions"
    notes: str | None = None
    #: filled in during valuation
    last_price: float | None = None
    #: the trading date of ``last_price``. A portfolio whose positions carry
    #: different dates is a portfolio mixing old and new prices, so the date
    #: travels with the number instead of being summarised far away.
    price_as_of: str | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pct: float | None = None
    weight_pct: float | None = None
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CashFlow:
    """The cash effect of one recorded trade.

    ``net`` is signed from the account's point of view: a **buy** costs
    ``quantity x price + fees`` (negative), a **sell** returns
    ``quantity x price - fees`` (positive). ``cumulative`` is the running sum in
    ledger order. Fees are part of the trade's cash effect; they are not added
    or dropped.
    """

    id: int
    symbol: str
    side: str
    quantity: int
    price: float
    fees: float
    traded_at: str
    gross: float  # quantity x price, before fees
    net: float  # signed cash effect (buy negative, sell positive)
    cumulative: float  # running sum of ``net`` in ledger order

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        for key in ("price", "gross", "net", "cumulative", "fees"):
            out[key] = round(out[key], 2)
        return out


# ------------------------------------------------------------------- validation
def _normalise(tx: dict[str, Any]) -> dict[str, Any]:
    symbol = str(tx.get("symbol") or "").strip().upper()
    if not symbol:
        raise PortfolioError("symbol is required")
    side = str(tx.get("side") or "").strip().lower()
    if side not in VALID_SIDES:
        raise PortfolioError(f"side must be one of {VALID_SIDES}, got {side!r}")
    raw_qty = tx.get("quantity")
    try:
        qty_f = float(raw_qty)
    except (TypeError, ValueError) as exc:
        raise PortfolioError("quantity must be a whole number") from exc
    if not float(qty_f).is_integer():
        # int(2.5) would silently become 2, hiding a caller mistake.
        raise PortfolioError("quantity must be a whole number")
    quantity = int(qty_f)
    if quantity <= 0:
        raise PortfolioError("quantity must be > 0")
    try:
        price = float(tx.get("price"))
    except (TypeError, ValueError) as exc:
        raise PortfolioError("price must be a number") from exc
    if not math.isfinite(price):
        # NaN and +/-inf are numbers in Python, and `NaN <= 0` is False, so
        # without this check they sail through the comparison below. NaN then
        # hits SQLite's NOT NULL as a 500; inf is STORED and poisons every
        # derived figure (a 1e999 from a browser parses as Infinity).
        raise PortfolioError("price must be a finite number")
    if price <= 0:
        raise PortfolioError("price must be > 0")
    try:
        fees = float(tx.get("fees") or 0.0)
    except (TypeError, ValueError) as exc:
        raise PortfolioError("fees must be a number") from exc
    if not math.isfinite(fees):
        raise PortfolioError("fees must be a finite number")
    if fees < 0:
        raise PortfolioError("fees cannot be negative")
    traded_at = tx.get("traded_at") or now_iso()
    try:
        dt = datetime.fromisoformat(str(traded_at).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortfolioError(f"traded_at is not an ISO timestamp: {traded_at!r}") from exc
    # Store UTC. The ledger is replayed in ORDER BY traded_at, so two rows
    # written with different offsets would otherwise be ordered by wall-clock
    # text rather than by when they happened - and average cost and realised
    # P&L depend on that order.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)  # naive means UTC, as now_iso() writes
    traded_at = dt.astimezone(UTC).isoformat(timespec="seconds")
    return {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "fees": fees,
        "traded_at": str(traded_at),
        "notes": tx.get("notes"),
    }


# ------------------------------------------------------------------ ledger read
def list_transactions(
    symbol: str | None = None, limit: int = 500, db_path=None
) -> list[Transaction]:
    sql = "SELECT * FROM portfolio_transactions"
    params: list[Any] = []
    if symbol:
        sql += " WHERE symbol = ?"
        params.append(symbol.upper())
    sql += " ORDER BY traded_at DESC, id DESC LIMIT ?"
    params.append(int(limit))
    with get_conn(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        Transaction(
            id=r["id"],
            symbol=r["symbol"],
            side=r["side"],
            quantity=r["quantity"],
            price=r["price"],
            fees=r["fees"] or 0.0,
            traded_at=r["traded_at"],
            notes=r["notes"],
        )
        for r in rows
    ]


def add_transaction(tx: dict[str, Any], db_path=None) -> Transaction:
    """Append one transaction, rejecting a sale of shares not held.

    Rejected sales are reported rather than silently clamped: a ledger that
    quietly rewrites history would make every derived number untrustworthy.
    """
    clean = _normalise(tx)
    with get_conn(db_path) as conn:
        if clean["side"] == "sell":
            held = _held_quantity(conn, clean["symbol"], as_of=clean["traded_at"])
            if clean["quantity"] > held:
                raise PortfolioError(
                    f"cannot sell {clean['quantity']} of {clean['symbol']} on "
                    f"{clean['traded_at']}: only {held} held in the ledger as of "
                    f"that date. A sale must be dated on or after the buys that "
                    f"funded it, otherwise the realised P&L of both trades is "
                    f"computed out of order."
                )
        cur = conn.execute(
            """
            INSERT INTO portfolio_transactions
              (symbol, side, quantity, price, fees, traded_at, notes, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                clean["symbol"],
                clean["side"],
                clean["quantity"],
                clean["price"],
                clean["fees"],
                clean["traded_at"],
                clean["notes"],
                now_iso(),
            ),
        )
        row_id = int(cur.lastrowid)
    return Transaction(id=row_id, **clean)


def delete_transaction(tx_id: int, db_path=None) -> bool:
    with get_conn(db_path) as conn:
        cur = conn.execute("DELETE FROM portfolio_transactions WHERE id=?", (tx_id,))
        return cur.rowcount > 0


def _held_quantity(conn, symbol: str, as_of: str | None = None) -> int:
    """Shares held, optionally only counting the ledger up to ``as_of``.

    ``as_of`` matters when a sale is being validated: checking the net of the
    WHOLE ledger lets a sale dated before the buys that funded it pass, and
    the chronological derivation then computes a nonsense realised P&L (a
    "-fees" loss on a profitable trade) that no warning explains.
    """
    if as_of is None:
        row = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN side='buy' THEN quantity ELSE -quantity END),0) "
            "AS q FROM portfolio_transactions WHERE symbol=?",
            (symbol,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN side='buy' THEN quantity ELSE -quantity END),0) "
            "AS q FROM portfolio_transactions WHERE symbol=? AND traded_at <= ?",
            (symbol, as_of),
        ).fetchone()
    return int(row["q"])


# ------------------------------------------------------------------ derivation
def derive_positions(db_path=None) -> list[Position]:
    """Rebuild positions from the ledger, in chronological order."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM portfolio_transactions ORDER BY traded_at ASC, id ASC"
        ).fetchall()
        manual = conn.execute(
            "SELECT symbol, quantity, avg_cost, notes FROM portfolio_positions"
        ).fetchall()

    positions: dict[str, Position] = {}
    for r in rows:
        sym = r["symbol"]
        p = positions.get(sym)
        if p is None:
            p = Position(symbol=sym, quantity=0, avg_cost=0.0)
            positions[sym] = p
        qty, price, fees = int(r["quantity"]), float(r["price"]), float(r["fees"] or 0.0)
        if r["side"] == "buy":
            total_cost = p.quantity * p.avg_cost + qty * price + fees
            p.quantity += qty
            p.avg_cost = total_cost / p.quantity if p.quantity else 0.0
            p.buy_value += qty * price + fees
        else:
            # Realise against the average cost; fees reduce proceeds.
            held_avg = p.avg_cost
            sold = min(qty, p.quantity)
            p.realized_pnl += (price * sold - fees) - held_avg * sold
            p.quantity -= sold
            if p.quantity == 0:
                p.avg_cost = 0.0
            if sold != qty:
                p.flags.append(f"ledger sold {qty} but only {sold} were held")
        if p.first_traded_at is None:
            p.first_traded_at = r["traded_at"]
        p.last_traded_at = r["traded_at"]

    for r in manual:
        if r["symbol"] in positions:
            # Both sources present: the ledger wins, and the conflict is shown.
            positions[r["symbol"]].flags.append(
                "a manual position row also exists for this symbol; the transaction ledger is used"
            )
            continue
        positions[r["symbol"]] = Position(
            symbol=r["symbol"],
            quantity=int(r["quantity"]),
            avg_cost=float(r["avg_cost"]),
            origin="manual",
            notes=r["notes"],
        )

    return sorted(
        (p for p in positions.values() if p.quantity != 0 or p.realized_pnl), key=lambda p: p.symbol
    )


def add_manual_position(
    symbol: str, quantity: int, avg_cost: float, notes: str | None = None, db_path=None
) -> None:
    """Record a holding that has no transaction history in this tool."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise PortfolioError("symbol is required")
    if quantity <= 0:
        raise PortfolioError("quantity must be > 0")
    if not math.isfinite(avg_cost):
        raise PortfolioError("avg_cost must be a finite number")
    if avg_cost <= 0:
        raise PortfolioError("avg_cost must be > 0")
    with get_conn(db_path) as conn:
        if _held_quantity(conn, symbol) != 0:
            raise PortfolioError(
                f"{symbol} already has transactions; add the trades instead of a "
                "manual position so the ledger stays the single source of truth"
            )
        # ``symbol`` is not UNIQUE in the schema, so upsert by delete+insert.
        conn.execute("DELETE FROM portfolio_positions WHERE symbol=?", (symbol,))
        conn.execute(
            """
            INSERT INTO portfolio_positions
              (symbol, quantity, avg_cost, notes, created_at, updated_at)
            VALUES (?,?,?,?,?,?)
            """,
            (symbol, int(quantity), float(avg_cost), notes, now_iso(), now_iso()),
        )


def remove_manual_position(symbol: str, db_path=None) -> bool:
    with get_conn(db_path) as conn:
        cur = conn.execute("DELETE FROM portfolio_positions WHERE symbol=?", (symbol.upper(),))
        return cur.rowcount > 0


# ------------------------------------------------------------------- cash flow
def cash_flows(db_path=None) -> dict[str, Any]:
    """Cash-flow view derived from the recorded transactions.

    Every recorded trade has one cash effect:

    * **buy**  -> ``quantity x price + fees`` leaves the account (``net < 0``);
    * **sell** -> ``quantity x price - fees`` enters it (``net > 0``).

    ``cumulative`` is the running total in ledger order (the same
    ``traded_at, id`` ordering the position derivation replays). This is the
    cash effect of the *recorded trades only*: deposits, withdrawals,
    dividends, interest and taxes are not recorded here, so ``net_cash_flow``
    is **not** an account cash balance - it is what the trades have moved.

    A sell larger than the quantity held cannot normally be recorded (the
    transaction writer refuses an oversell), but if a ledger ever contained one,
    this view would still move the recorded amount rather than cap or repair it;
    the anomaly is surfaced by :func:`derive_positions`, not hidden here.
    """
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM portfolio_transactions ORDER BY traded_at ASC, id ASC"
        ).fetchall()

    flows: list[CashFlow] = []
    per_symbol: dict[str, float] = {}
    total_invested = 0.0
    total_proceeds = 0.0
    total_fees = 0.0
    cumulative = 0.0
    for r in rows:
        qty = int(r["quantity"])
        price = float(r["price"])
        fees = float(r["fees"] or 0.0)
        gross = qty * price
        if r["side"] == "buy":
            net = -(gross + fees)
            total_invested += gross + fees
        else:
            net = gross - fees
            total_proceeds += net
        total_fees += fees
        cumulative += net
        sym = r["symbol"]
        per_symbol[sym] = per_symbol.get(sym, 0.0) + net
        flows.append(
            CashFlow(
                id=int(r["id"]),
                symbol=sym,
                side=r["side"],
                quantity=qty,
                price=price,
                fees=fees,
                traded_at=r["traded_at"],
                gross=gross,
                net=net,
                cumulative=cumulative,
            )
        )

    return {
        "flows": [f.to_dict() for f in flows],
        "summary": {
            "transactions": len(flows),
            "total_invested": round(total_invested, 2),
            "total_proceeds": round(total_proceeds, 2),
            "total_fees": round(total_fees, 2),
            "net_cash_flow": round(cumulative, 2),
            "per_symbol_net": {s: round(v, 2) for s, v in sorted(per_symbol.items())},
        },
        "note": "Cash flow from RECORDED trades only: a buy costs quantity x "
        "price + fees, a sell returns quantity x price - fees. Deposits, "
        "withdrawals, dividends and interest are not recorded, so "
        "'net_cash_flow' is the trades' net cash effect, not an account cash "
        "balance.",
    }


# ------------------------------------------------------------------- valuation
def value_portfolio(store, db_path=None) -> dict[str, Any]:
    """Positions plus a mark-to-market using the latest stored close.

    A symbol with no usable stored price is left unvalued and flagged rather
    than being carried at cost as though nothing were missing. Two causes are
    reported separately, because they are different problems:

    * **no bar at all** - the symbol has no stored history;
    * **a bar whose close is not a price** (zero or negative) - the row
      exists and is preserved, but a non-positive close is not something a
      share can trade at, so marking the position to it would invent a
      total loss. The position is left unvalued instead (B-21 / register R1
      decides the long-run policy; this never mutates the stored row).
    """
    positions = derive_positions(db_path)
    held = [p for p in positions if p.quantity > 0]

    prices: dict[str, float] = {}
    price_dates: dict[str, str] = {}
    rejected: dict[str, str] = {}  # symbol -> date of a bar with an unusable close
    data_as_of: str | None = None
    if held:
        latest = store.latest_bars([p.symbol for p in held])
        if not latest.empty:
            for _, row in latest.iterrows():
                close = row.get("close")
                sym = str(row["symbol"])
                ts = row["trading_date"]
                d = str(ts.date()) if hasattr(ts, "date") else str(ts)[:10]
                # A usable mark must be a FINITE, POSITIVE number - the same
                # rule the backtest engine applies (a NaN passes a bare
                # ``> 0``-style check only via the ``close == close`` test,
                # and +inf would pass ``> 0`` outright, poisoning every
                # total with infinity).
                if close is not None and math.isfinite(float(close)) and float(close) > 0:
                    prices[sym] = float(close)
                    price_dates[sym] = d
                    if data_as_of is None or d > data_as_of:
                        data_as_of = d
                else:
                    rejected[sym] = d

    valued_total = 0.0
    unvalued_cost = 0.0
    for p in held:
        cost = p.avg_cost * p.quantity
        if p.symbol in prices:
            p.last_price = prices[p.symbol]
            p.price_as_of = price_dates.get(p.symbol)
            if p.price_as_of and data_as_of and p.price_as_of < data_as_of:
                # Without this the summary would value one position at a
                # today price and another at a two-year-old one, then present
                # the combined market value and weights as if they were
                # comparable. They are not, and the trader should be told.
                p.flags.append(
                    f"latest stored close is {p.price_as_of}, while the newest "
                    f"data is {data_as_of}: this position is valued on an older "
                    f"price than the rest"
                )
            p.market_value = p.last_price * p.quantity
            p.unrealized_pnl = p.market_value - cost
            p.unrealized_pct = (p.unrealized_pnl / cost * 100.0) if cost else None
            valued_total += p.market_value
        else:
            if p.symbol in rejected:
                p.flags.append(
                    f"the stored close on {rejected[p.symbol]} is not a usable "
                    "price (zero, negative or missing): left unvalued rather "
                    "than marking the position to zero; the stored row is "
                    "unchanged"
                )
            else:
                p.flags.append(
                    "no stored price for this symbol: left unvalued (never carried at cost)"
                )
            unvalued_cost += cost

    for p in held:
        if p.market_value is not None and valued_total > 0:
            p.weight_pct = p.market_value / valued_total * 100.0

    realized = sum(p.realized_pnl for p in positions)
    cost_valued = sum(p.avg_cost * p.quantity for p in held if p.market_value is not None)
    unrealized = valued_total - cost_valued if cost_valued else 0.0
    weights = [p.weight_pct for p in held if p.weight_pct is not None]
    largest = max(weights) if weights else None
    unvalued_count = sum(1 for p in held if p.market_value is None)

    out = {
        "positions": [p.to_dict() for p in positions],
        "summary": {
            "open_positions": len(held),
            "valued_market_value": round(valued_total, 2),
            "valued_cost": round(cost_valued, 2),
            "unrealized_pnl": round(unrealized, 2),
            "realized_pnl": round(realized, 2),
            "unvalued_cost": round(unvalued_cost, 2),
            "unvalued_positions": unvalued_count,
            "largest_weight_pct": None if largest is None else round(largest, 2),
            "concentration_warning": bool(largest is not None and largest >= 40.0),
        },
        "data_as_of": data_as_of,
        "live": False,
        "cash_flow": cash_flows(db_path)["summary"],
        "note": "Positions are derived from your transaction ledger. Valuation uses "
        "the latest STORED close (not a live quote); symbols without a stored "
        "price - or whose latest close is zero/negative - are left unvalued, "
        "never marked to zero. Cash balances are not modelled. The `cash_flow` "
        "block is the net cash effect of the recorded trades (fees included); "
        "it is not an account balance. Weights and "
        "the concentration warning are shares of VALUED positions only: with an "
        "unvalued position present, the real largest weight is smaller than "
        "shown.",
    }

    # Denominator disclosure (see unvalued_positions above): a partial
    # valuation must say so, or a single missing price silently inflates every
    # weight and can trip a concentration warning on a portfolio that isn't.
    return out


def portfolio_summary(db_path=None) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        n = int(conn.execute("SELECT COUNT(*) c FROM portfolio_transactions").fetchone()["c"])
        manual = int(conn.execute("SELECT COUNT(*) c FROM portfolio_positions").fetchone()["c"])
    return {
        "transactions": n,
        "manual_positions": manual,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
