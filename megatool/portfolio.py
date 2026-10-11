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
    origin: str = "transactions"
    notes: str | None = None
    #: filled in during valuation
    last_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pct: float | None = None
    weight_pct: float | None = None
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    if price <= 0:
        raise PortfolioError("price must be > 0")
    try:
        fees = float(tx.get("fees") or 0.0)
    except (TypeError, ValueError) as exc:
        raise PortfolioError("fees must be a number") from exc
    if fees < 0:
        raise PortfolioError("fees cannot be negative")
    traded_at = tx.get("traded_at") or now_iso()
    try:
        datetime.fromisoformat(str(traded_at).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortfolioError(f"traded_at is not an ISO timestamp: {traded_at!r}") from exc
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
            held = _held_quantity(conn, clean["symbol"])
            if clean["quantity"] > held:
                raise PortfolioError(
                    f"cannot sell {clean['quantity']} of {clean['symbol']}: only "
                    f"{held} held in the ledger"
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


def _held_quantity(conn, symbol: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN side='buy' THEN quantity ELSE -quantity END),0) "
        "AS q FROM portfolio_transactions WHERE symbol=?",
        (symbol,),
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


# ------------------------------------------------------------------- valuation
def value_portfolio(store, db_path=None) -> dict[str, Any]:
    """Positions plus a mark-to-market using the latest stored close.

    A symbol with no stored price is left unvalued and flagged rather than
    being carried at cost as though nothing were missing.
    """
    positions = derive_positions(db_path)
    held = [p for p in positions if p.quantity > 0]

    prices: dict[str, float] = {}
    data_as_of: str | None = None
    if held:
        latest = store.latest_bars([p.symbol for p in held])
        if not latest.empty:
            for _, row in latest.iterrows():
                close = row.get("close")
                if close is not None and close == close:  # NaN check
                    prices[str(row["symbol"])] = float(close)
                    ts = row["trading_date"]
                    d = str(ts.date()) if hasattr(ts, "date") else str(ts)[:10]
                    if data_as_of is None or d > data_as_of:
                        data_as_of = d

    valued_total = 0.0
    unvalued_cost = 0.0
    for p in held:
        cost = p.avg_cost * p.quantity
        if p.symbol in prices:
            p.last_price = prices[p.symbol]
            p.market_value = p.last_price * p.quantity
            p.unrealized_pnl = p.market_value - cost
            p.unrealized_pct = (p.unrealized_pnl / cost * 100.0) if cost else None
            valued_total += p.market_value
        else:
            p.flags.append("no stored price for this symbol: left unvalued (never carried at cost)")
            unvalued_cost += cost

    for p in held:
        if p.market_value is not None and valued_total > 0:
            p.weight_pct = p.market_value / valued_total * 100.0

    realized = sum(p.realized_pnl for p in positions)
    cost_valued = sum(p.avg_cost * p.quantity for p in held if p.market_value is not None)
    unrealized = valued_total - cost_valued if cost_valued else 0.0
    weights = [p.weight_pct for p in held if p.weight_pct is not None]
    largest = max(weights) if weights else None

    return {
        "positions": [p.to_dict() for p in positions],
        "summary": {
            "open_positions": len(held),
            "valued_market_value": round(valued_total, 2),
            "valued_cost": round(cost_valued, 2),
            "unrealized_pnl": round(unrealized, 2),
            "realized_pnl": round(realized, 2),
            "unvalued_cost": round(unvalued_cost, 2),
            "largest_weight_pct": None if largest is None else round(largest, 2),
            "concentration_warning": bool(largest is not None and largest >= 40.0),
        },
        "data_as_of": data_as_of,
        "live": False,
        "note": "Positions are derived from your transaction ledger. Valuation uses "
        "the latest STORED close (not a live quote); symbols without a stored "
        "price are left unvalued. Cash balances are not modelled.",
    }


def portfolio_summary(db_path=None) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        n = int(conn.execute("SELECT COUNT(*) c FROM portfolio_transactions").fetchone()["c"])
        manual = int(conn.execute("SELECT COUNT(*) c FROM portfolio_positions").fetchone()["c"])
    return {
        "transactions": n,
        "manual_positions": manual,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
