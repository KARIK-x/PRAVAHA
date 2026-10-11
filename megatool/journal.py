"""Trading journal: what the owner planned, what they did, and how it went.

The journal is deliberately opinionated about *measurement* and silent about
*advice*. It records the thesis, the plan (target and invalidation) and the
outcome, then computes adherence and R multiples so the owner can see whether
they follow their own rules - which is the only thing a journal can honestly
score.

All state lives in SQLite (``journal_entries``); no market data is written here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from megatool.db import get_conn, now_iso
from megatool.planning import plan_outcome

CONFIDENCE_LEVELS = ("low", "medium", "high")


class JournalError(ValueError):
    """Invalid journal input."""


def _parse_ts(value: Any, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise JournalError(f"{field_name} is not an ISO timestamp: {value!r}") from exc
    return str(value)


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["symbol"] = str(data["symbol"]).strip().upper() if data.get("symbol") else None
    out["strategy"] = data.get("strategy")
    out["thesis"] = data.get("thesis")
    # `notes` is accepted as an alias for `outcome_notes`. Without this, a
    # client sending `notes` got HTTP 200 and its text was silently discarded -
    # the worst possible behaviour for a field whose entire purpose is to
    # remember what the owner was thinking at the time.
    out["outcome_notes"] = data.get("outcome_notes") or data.get("notes")

    for name in ("entry_price", "exit_price", "planned_target", "planned_invalidation", "fees"):
        raw = data.get(name)
        if raw in (None, ""):
            out[name] = None
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise JournalError(f"{name} must be a number") from exc
        if (
            name in ("entry_price", "exit_price", "planned_target", "planned_invalidation")
            and value <= 0
        ):
            raise JournalError(f"{name} must be > 0")
        if name == "fees" and value < 0:
            raise JournalError("fees cannot be negative")
        out[name] = value

    qty = data.get("quantity")
    if qty in (None, ""):
        out["quantity"] = None
    else:
        try:
            q = float(qty)
        except (TypeError, ValueError) as exc:
            raise JournalError("quantity must be a whole number") from exc
        if not q.is_integer() or q <= 0:
            raise JournalError("quantity must be a whole number > 0")
        out["quantity"] = int(q)

    conf = data.get("confidence")
    if conf not in (None, "") and conf not in CONFIDENCE_LEVELS:
        raise JournalError(f"confidence must be one of {CONFIDENCE_LEVELS}, got {conf!r}")
    out["confidence"] = conf

    fp = data.get("followed_plan")
    if fp in (None, ""):
        out["followed_plan"] = None
    elif isinstance(fp, bool):
        out["followed_plan"] = int(fp)
    else:
        try:
            v = int(fp)
        except (TypeError, ValueError) as exc:
            raise JournalError("followed_plan must be 1, 0 or null") from exc
        if v not in (0, 1):
            raise JournalError("followed_plan must be 1, 0 or null")
        out["followed_plan"] = v

    out["opened_at"] = _parse_ts(data.get("opened_at"), "opened_at")
    out["closed_at"] = _parse_ts(data.get("closed_at"), "closed_at")
    return out


_COLUMNS = (
    "symbol",
    "strategy",
    "thesis",
    "entry_price",
    "exit_price",
    "quantity",
    "fees",
    "planned_target",
    "planned_invalidation",
    "confidence",
    "followed_plan",
    "opened_at",
    "closed_at",
    "outcome_notes",
)


def create_entry(data: dict[str, Any], db_path=None) -> int:
    clean = _clean(data)
    if clean["entry_price"] is None and clean["thesis"] is None:
        raise JournalError("an entry needs at least a thesis or an entry price")
    if clean["closed_at"] and clean["exit_price"] is None:
        raise JournalError("a closed entry needs an exit_price")
    if (
        clean["exit_price"] is not None
        and clean["opened_at"]
        and clean["closed_at"]
        and clean["closed_at"] < clean["opened_at"]
    ):
        raise JournalError("closed_at cannot be before opened_at")
    cols = ", ".join(_COLUMNS)
    marks = ", ".join("?" for _ in _COLUMNS)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            f"INSERT INTO journal_entries ({cols}, created_at, updated_at) VALUES ({marks}, ?, ?)",
            [clean[c] for c in _COLUMNS] + [now_iso(), now_iso()],
        )
        return int(cur.lastrowid)


def update_entry(entry_id: int, data: dict[str, Any], db_path=None) -> bool:
    """Merge ``data`` into an existing entry. ``False`` if it does not exist."""
    try:
        existing = get_entry(entry_id, db_path)
    except JournalError:
        return False
    clean = _clean({**existing, **data})
    sets = ", ".join(f"{c}=?" for c in _COLUMNS)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            f"UPDATE journal_entries SET {sets}, updated_at=? WHERE id=?",
            [clean[c] for c in _COLUMNS] + [now_iso(), entry_id],
        )
        return cur.rowcount > 0


def delete_entry(entry_id: int, db_path=None) -> bool:
    with get_conn(db_path) as conn:
        cur = conn.execute("DELETE FROM journal_entries WHERE id=?", (entry_id,))
        return cur.rowcount > 0


def get_entry(entry_id: int, db_path=None) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM journal_entries WHERE id=?", (entry_id,)).fetchone()
    if row is None:
        raise JournalError(f"no journal entry with id {entry_id}")
    return dict(row)


def list_entries(
    symbol: str | None = None,
    strategy: str | None = None,
    status: str | None = None,
    limit: int = 500,
    db_path=None,
) -> list[dict[str, Any]]:
    """Entries, newest first. ``status`` is ``open`` or ``closed``."""
    where: list[str] = []
    params: list[Any] = []
    if symbol:
        where.append("symbol = ?")
        params.append(symbol.upper())
    if strategy:
        where.append("strategy = ?")
        params.append(strategy)
    if status == "open":
        where.append("closed_at IS NULL")
    elif status == "closed":
        where.append("closed_at IS NOT NULL")
    elif status is not None:
        raise JournalError("status must be 'open', 'closed' or null")
    sql = "SELECT * FROM journal_entries"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(opened_at, created_at) DESC, id DESC LIMIT ?"
    params.append(int(limit))
    with get_conn(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---------------------------------------------------------------------- stats
def _r_multiple(e: dict[str, Any]) -> float | None:
    required = ("entry_price", "exit_price", "planned_target", "planned_invalidation")
    if any(e.get(k) is None for k in required):
        return None
    stop, entry, target = e["planned_invalidation"], e["entry_price"], e["planned_target"]
    if not stop < entry < target:
        return None
    return (e["exit_price"] - entry) / (entry - stop)


def journal_stats(db_path=None) -> dict[str, Any]:
    rows = list_entries(limit=100_000, db_path=db_path)
    closed = [e for e in rows if e["closed_at"] and e["exit_price"] is not None]
    wins = [e for e in closed if e["exit_price"] > e["entry_price"]]
    losses = [e for e in closed if e["exit_price"] < e["entry_price"]]

    r_values = [r for r in (_r_multiple(e) for e in closed) if r is not None]
    adherence = [e["followed_plan"] for e in rows if e["followed_plan"] is not None]

    by_strategy: dict[str, dict[str, Any]] = {}
    for e in closed:
        key = e["strategy"] or "(no strategy recorded)"
        bucket = by_strategy.setdefault(
            key, {"strategy": key, "closed": 0, "wins": 0, "r_values": []}
        )
        bucket["closed"] += 1
        if e["exit_price"] > e["entry_price"]:
            bucket["wins"] += 1
        r = _r_multiple(e)
        if r is not None:
            bucket["r_values"].append(r)

    strategies = []
    for bucket in sorted(by_strategy.values(), key=lambda b: -b["closed"]):
        rs = bucket["r_values"]
        strategies.append(
            {
                "strategy": bucket["strategy"],
                "closed": bucket["closed"],
                "wins": bucket["wins"],
                "win_rate_pct": round(100.0 * bucket["wins"] / bucket["closed"], 2)
                if bucket["closed"]
                else None,
                "avg_r": round(sum(rs) / len(rs), 4) if rs else None,
                "graded_r": len(rs),
            }
        )

    total_planned = len(adherence)
    followed = sum(1 for a in adherence if a == 1)

    return {
        "entries": len(rows),
        "open": sum(1 for e in rows if not e["closed_at"]),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(closed) - len(wins) - len(losses),
        "win_rate_pct": round(100.0 * len(wins) / len(closed), 2) if closed else None,
        "avg_r": round(sum(r_values) / len(r_values), 4) if r_values else None,
        "graded_r": len(r_values),
        "plan_adherence_pct": round(100.0 * followed / total_planned, 2) if total_planned else None,
        "adherence_sample": total_planned,
        "by_strategy": strategies,
        "note": "Win rate and R are measurements of recorded trades only. A small "
        "sample says almost nothing, and nothing here predicts future results.",
        "warnings": _warnings(len(closed), total_planned, len(r_values)),
    }


def _warnings(closed: int, adherence: int, graded: int) -> list[str]:
    out: list[str] = []
    if closed == 0:
        out.append("No closed trades yet, so no performance statistics are shown.")
    elif closed < 10:
        out.append(
            f"Only {closed} closed trade(s): win rate and average R are not "
            "statistically meaningful."
        )
    if adherence == 0:
        out.append(
            "No entry records whether the plan was followed, so adherence cannot "
            "be measured. Set `followed_plan` when you close a trade."
        )
    if graded and graded < closed:
        out.append(
            f"{closed - graded} closed trade(s) have no complete plan (entry, "
            "target, invalidation), so they are excluded from R statistics."
        )
    return out


def grade_entry(entry_id: int, db_path=None) -> dict[str, Any] | None:
    """Grade one closed entry against its own plan, if the plan is complete."""
    e = get_entry(entry_id, db_path)
    if e["exit_price"] is None:
        return None
    required = ("entry_price", "planned_target", "planned_invalidation")
    if any(e.get(k) is None for k in required):
        return None
    return plan_outcome(
        e["entry_price"], e["planned_invalidation"], e["planned_target"], e["exit_price"]
    )
