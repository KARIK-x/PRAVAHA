"""Trading journal: what the owner planned, what they did, and how it went.

The journal is deliberately opinionated about *measurement* and silent about
*advice*. It records the thesis, the plan (target and invalidation) and the
outcome, then computes adherence and R multiples so the owner can see whether
they follow their own rules - which is the only thing a journal can honestly
score.

All state lives in SQLite (``journal_entries``); no market data is written here.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
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
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise JournalError(f"{field_name} is not an ISO timestamp: {value!r}") from exc
    # Store UTC. Comparisons in this module are lexicographic, so a timestamp
    # written with a local offset ("+05:45") would sort against a UTC one by
    # its wall-clock text rather than by when it happened - and a trade that
    # really closed before it opened could pass the closed-at check.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)  # naive means UTC, as now_iso() writes
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    _reject_unknown_fields(data)
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
        if not math.isfinite(value):
            # `NaN <= 0` is False, so NaN passes the comparisons below and is
            # then stored by SQLite as NULL: the entry looks saved and has
            # silently lost its prices.
            raise JournalError(f"{name} must be a finite number")
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
            v = float(fp)
        except (TypeError, ValueError) as exc:
            raise JournalError("followed_plan must be 1, 0 or null") from exc
        # int(1.7) == 1, so truncating would record a definite "followed the
        # plan" for a value that is neither 1 nor 0.
        if not math.isfinite(v) or v not in (0.0, 1.0):
            raise JournalError("followed_plan must be 1, 0 or null")
        out["followed_plan"] = int(v)

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


def _reject_unknown_fields(data: dict[str, Any]) -> None:
    """Reject keys this module does not read, rather than dropping them.

    A silently ignored field is the failure mode this whole module is built to
    avoid: a caller sending ``entry_prc`` (a typo for ``entry_price``) would
    otherwise get HTTP 200 and lose their entry price with no signal that
    anything went wrong. Failing loudly costs one round-trip; silently
    discarding a trader's recorded number costs them their journal.

    Derived from ``_COLUMNS`` plus the one documented alias, so the two
    definitions cannot drift apart.
    """
    known = set(_COLUMNS) | {"notes"}  # `notes` is the alias for outcome_notes
    unknown = set(data) - known
    if unknown:
        raise JournalError(
            f"unknown field(s): {', '.join(sorted(unknown))}. These would be "
            f"ignored, and ignoring them silently is how a trader loses data. "
            f"Accepted fields: {', '.join(sorted(known))}."
        )


def _validate(clean: dict[str, Any]) -> None:
    """Cross-field rules every write must satisfy, create *and* update.

    Keeping this separate from ``create_entry`` matters: an update that skips
    it can close a trade without an exit price, and the stats then report an
    entry that is neither open nor closed - silently under-counting the sample
    every win rate in this module is built on.
    """
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


def create_entry(data: dict[str, Any], db_path=None) -> int:
    clean = _clean(data)
    _validate(clean)
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
    # ``notes`` is an alias for ``outcome_notes``. On a merge the stored value
    # would otherwise win over the incoming ``notes`` and the edit would be
    # dropped with a 200 - the exact silent discard this alias exists to avoid.
    if "outcome_notes" not in data and "notes" in data:
        data = {**data, "outcome_notes": data["notes"]}
    # `get_entry` returns the whole row, including bookkeeping columns the
    # caller cannot set. Strip them so the unknown-field check reads the
    # OWNER's keys, not the schema's.
    existing = {k: v for k, v in existing.items() if k in _COLUMNS}
    clean = _clean({**existing, **data})
    _validate(clean)
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
    # An entry may be closed with an exit price and no entry price (a
    # thesis-only trade is legal). Comparing exit to a missing entry raises
    # TypeError and used to kill this whole endpoint with a 500, so such
    # entries are counted and excluded from the win rate instead.
    comparable = [e for e in closed if e["entry_price"] is not None]
    unpriced = len(closed) - len(comparable)
    wins = [e for e in comparable if e["exit_price"] > e["entry_price"]]
    losses = [e for e in comparable if e["exit_price"] < e["entry_price"]]

    r_values = [r for r in (_r_multiple(e) for e in closed) if r is not None]
    adherence = [e["followed_plan"] for e in rows if e["followed_plan"] is not None]

    by_strategy: dict[str, dict[str, Any]] = {}
    for e in closed:
        key = e["strategy"] or "(no strategy recorded)"
        bucket = by_strategy.setdefault(
            key,
            {
                "strategy": key,
                "closed": 0,
                "comparable": 0,
                "wins": 0,
                "r_values": [],
            },
        )
        bucket["closed"] += 1
        if e["entry_price"] is not None:
            bucket["comparable"] += 1
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
                "comparable": bucket["comparable"],
                "wins": bucket["wins"],
                "win_rate_pct": round(100.0 * bucket["wins"] / bucket["comparable"], 2)
                if bucket["comparable"]
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
        "breakeven": len(comparable) - len(wins) - len(losses),
        # `comparable` is the win-rate denominator. Exposing it stops the rate
        # being quoted without the sample it rests on.
        "comparable": len(comparable),
        "win_rate_pct": round(100.0 * len(wins) / len(comparable), 2) if comparable else None,
        "closed_without_entry_price": unpriced,
        "avg_r": round(sum(r_values) / len(r_values), 4) if r_values else None,
        "graded_r": len(r_values),
        "plan_adherence_pct": round(100.0 * followed / total_planned, 2) if total_planned else None,
        "adherence_sample": total_planned,
        "by_strategy": strategies,
        "note": "Win rate and R are measurements of recorded trades only. A small "
        "sample says almost nothing, and nothing here predicts future results.",
        "warnings": _warnings(len(closed), total_planned, len(r_values), unpriced),
    }


def _warnings(closed: int, adherence: int, graded: int, unpriced: int = 0) -> list[str]:
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
    if unpriced:
        out.append(
            f"{unpriced} closed trade(s) recorded an exit price but no entry "
            "price, so they cannot be counted as a win or a loss. The win rate "
            f"is computed over the other {closed - unpriced}."
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


def reflection_context(entry_id: int, db_path=None) -> dict[str, Any]:
    """Deterministic reflection material for one entry — computed locally.

    The entry as recorded, its plan grade (if closeable), and the journal's
    own statistics. Nothing here involves a model: this is the AI-independent
    half of the reflection feature.
    """
    e = get_entry(entry_id, db_path)
    stats = journal_stats(db_path)
    return {
        "entry": e,
        "plan_grade": grade_entry(entry_id, db_path),
        "journal_stats": {
            k: stats.get(k)
            for k in ("closed", "wins", "losses", "win_rate_pct", "avg_r")
            if k in stats
        },
        "kind": "deterministic",
        "note": "Computed locally from the journal; independent of any AI.",
    }


def reflect(
    entry_id: int,
    *,
    provider: str | None = None,
    authorize_private: bool = False,
    db_path=None,
    provider_instance: Any = None,
) -> dict[str, Any] | None:
    """Deterministic reflection context plus an OPTIONAL AI reflection.

    Privacy contract: journal content is private. Without
    ``authorize_private=True`` no model is invoked at all — the caller gets
    only the local deterministic context and an explicit ``not_authorized``
    status. With the flag, the configured provider is used and the recipient
    (local Ollama vs hosted OpenRouter) is named in the response, so the owner
    always knows where their journal entry went. Returns ``None`` when the
    entry does not exist.
    """
    try:
        ctx = reflection_context(entry_id, db_path)
    except JournalError:
        return None

    if not authorize_private:
        return {
            "entry_id": entry_id,
            "deterministic": ctx,
            "ai_interpretation": {
                "status": "not_authorized",
                "text": None,
                "reason": (
                    "journal content is private; no AI call was made. Pass "
                    "authorize_private=true to send this entry's context to "
                    "the configured provider (local Ollama keeps it on this "
                    "machine)."
                ),
                "recipient": "none — no model call was made",
            },
        }

    from megatool.agent import ToolResult, interpret

    tr = ToolResult(
        tool="journal",
        status="ok",
        private=True,
        summary=f"journal entry {entry_id} for {ctx['entry'].get('symbol', '?')}",
        provenance="local journal (SQLite app DB); private",
        data=ctx,
    )
    ai = interpret(
        f"Reflect on journal entry {entry_id}: what went as planned, what did "
        "not, and what is worth checking next time. Ground every statement in "
        "the entry's own recorded fields.",
        [tr],
        provider=provider,
        include_private=True,
        provider_instance=provider_instance,
    )
    if ai.get("status") == "ok":
        pname = str(ai.get("provider") or "").lower()
        ai["recipient"] = (
            "local machine (Ollama)" if "ollama" in pname else f"hosted ({ai.get('provider')})"
        )
    else:
        ai["recipient"] = "none — no model call was made"
    return {"entry_id": entry_id, "deterministic": ctx, "ai_interpretation": ai}
