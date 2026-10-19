"""User watchlists (directive M1 §8.2).

A watchlist is a named, ordered set of symbols the owner curates. Storage is
the application SQLite (the ``watchlists`` table, present since the Phase-1
schema), so a watchlist survives restarts and never touches the market
database. Names are unique and case-insensitive for comparison but stored as
typed; symbols are normalised to upper-case and de-duplicated while keeping the
owner's order.

This module is deliberately storage-only: it never invents a price. Valuation
(last close, change) is the caller's job against the market store, so a missing
quote shows as missing rather than as a fabricated zero.
"""

from __future__ import annotations

import re
from typing import Any

from megatool.db import get_conn, now_iso

#: Longest accepted watchlist name.
MAX_NAME = 60

#: Hard cap on symbols per watchlist (guards the naive comma-text column).
MAX_SYMBOLS = 200

#: Same well-formed-symbol rule as the API routes (B-47): no path separators,
#: no spaces, bounded length. It does not assert the symbol exists.
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._&-]{0,23}$")


class WatchlistError(ValueError):
    """Invalid watchlist input (blank name, malformed symbol, missing list)."""


def _clean_name(name: str) -> str:
    if not name or not str(name).strip():
        raise WatchlistError("watchlist name must not be blank")
    n = str(name).strip()
    if len(n) > MAX_NAME:
        raise WatchlistError(f"watchlist name must be at most {MAX_NAME} characters")
    return n


def clean_symbols(symbols: Any) -> list[str]:
    """Normalise symbols to an ordered, de-duplicated upper-case list.

    Accepts a list/tuple/set or a comma/whitespace-separated string. A
    malformed token is rejected rather than silently dropped, so a typo cannot
    quietly vanish from a saved list.
    """
    if symbols is None:
        return []
    if isinstance(symbols, str):
        raw = [s for s in re.split(r"[,\s]+", symbols) if s]
    elif isinstance(symbols, (list, tuple, set)):
        raw = [str(s) for s in symbols]
    else:
        raise WatchlistError("symbols must be a list or a comma-separated string")
    out: list[str] = []
    seen: set[str] = set()
    for s in raw:
        t = s.strip().upper()
        if not t:
            continue
        if not _SYMBOL_RE.match(t):
            raise WatchlistError(f"malformed symbol {s!r}")
        if t not in seen:
            seen.add(t)
            out.append(t)
    if len(out) > MAX_SYMBOLS:
        raise WatchlistError(f"a watchlist holds at most {MAX_SYMBOLS} symbols")
    return out


def _row(row: Any) -> dict[str, Any]:
    symbols = [s for s in (row["symbols"] or "").split(",") if s]
    return {
        "name": row["name"],
        "symbols": symbols,
        "count": len(symbols),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_watchlists(db_path: Any = None) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM watchlists ORDER BY name COLLATE NOCASE").fetchall()
    return [_row(r) for r in rows]


def get_watchlist(name: str, db_path: Any = None) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM watchlists WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise WatchlistError(f"no watchlist named {name!r}")
    return _row(row)


def create_watchlist(name: str, symbols: Any = None, db_path: Any = None) -> dict[str, Any]:
    nm = _clean_name(name)
    syms = clean_symbols(symbols)
    ts = now_iso()
    with get_conn(db_path) as conn:
        if conn.execute("SELECT 1 FROM watchlists WHERE name = ?", (nm,)).fetchone():
            raise WatchlistError(f"a watchlist named {nm!r} already exists")
        conn.execute(
            "INSERT INTO watchlists (name, symbols, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (nm, ",".join(syms), ts, ts),
        )
    return {"name": nm, "symbols": syms, "count": len(syms), "created_at": ts, "updated_at": ts}


def update_watchlist(
    name: str,
    *,
    new_name: str | None = None,
    symbols: Any = "__unset__",
    add: Any = None,
    remove: Any = None,
    db_path: Any = None,
) -> dict[str, Any]:
    """Edit a watchlist. ``symbols`` replaces the list; ``add``/``remove`` adjust it.

    ``symbols`` default is a sentinel so "not provided" is distinct from "clear
    the list" (an explicit empty list).
    """
    current = get_watchlist(name, db_path=db_path)
    syms = list(current["symbols"])
    if symbols != "__unset__":
        syms = clean_symbols(symbols)
    else:
        if remove is not None:
            drop = set(clean_symbols(remove))
            syms = [s for s in syms if s not in drop]
        if add is not None:
            for s in clean_symbols(add):
                if s not in syms:
                    syms.append(s)
    final_name = _clean_name(new_name) if new_name is not None else name
    if len(syms) > MAX_SYMBOLS:
        raise WatchlistError(f"a watchlist holds at most {MAX_SYMBOLS} symbols")
    ts = now_iso()
    with get_conn(db_path) as conn:
        if (
            final_name != name
            and conn.execute("SELECT 1 FROM watchlists WHERE name = ?", (final_name,)).fetchone()
        ):
            raise WatchlistError(f"a watchlist named {final_name!r} already exists")
        conn.execute(
            "UPDATE watchlists SET name = ?, symbols = ?, updated_at = ? WHERE name = ?",
            (final_name, ",".join(syms), ts, name),
        )
    return {
        "name": final_name,
        "symbols": syms,
        "count": len(syms),
        "created_at": current["created_at"],
        "updated_at": ts,
    }


def delete_watchlist(name: str, db_path: Any = None) -> bool:
    with get_conn(db_path) as conn:
        cur = conn.execute("DELETE FROM watchlists WHERE name = ?", (name,))
        return cur.rowcount > 0
