"""Floor-sheet import and analysis.

A NEPSE floor sheet lists **every printed trade of one session**: symbol, buyer
broker, seller broker, quantity, rate, amount. It is the most concrete record
the market publishes, and it is also easy to over-read.

WHAT THE NUMBERS ARE
--------------------
`buyer` and `seller` are **broker IDs, not beneficial owners**. A broker code
can represent many clients, and a house can trade against itself. Concentration
therefore says "this code printed a lot", never "this person is accumulating".
A floor sheet records what was printed, not why, and contains no information
about the future.

IMPORT MODEL
------------
There is no floor-sheet API to call (the aggregator sites publish pages, and
the official API is auth-walled), so this module is deliberately **import
based**: paste or upload the CSV for a session. Re-importing the same file is
a no-op (`content_hash`), and the same trade arriving in two different files
**for the same session** cannot be counted twice (per-row unique key). A file
is not protected across sessions: importing identical bytes under a second
`traded_at` stores them again and is reported as a warning.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from megatool.db import get_conn, init_app_db, now_iso

#: Column aliases accepted, lower-cased and stripped of punctuation. NEPSE and
#: the two aggregator sites all publish slightly different headers.
_ALIASES: dict[str, tuple[str, ...]] = {
    "symbol": ("symbol", "scrip", "script", "company"),
    "buyer": ("buyer", "buyerid", "buy", "buyerbroker", "buyercode"),
    "seller": ("seller", "sellerid", "sell", "sellerbroker", "sellercode"),
    "quantity": ("quantity", "qty", "units", "share", "shares"),
    "rate": ("rate", "price", "ltp"),
    "amount": ("amount", "turnover", "value"),
    "date": ("date", "tradingdate", "tradedate", "session"),
}

REQUIRED = ("symbol", "buyer", "seller", "quantity", "rate")
#: An amount that disagrees with quantity x rate by more than this is flagged.
AMOUNT_TOLERANCE = 0.01


class FloorSheetError(ValueError):
    """The file could not be read as a floor sheet."""


@dataclass
class ParsedRow:
    symbol: str
    buyer: str
    seller: str
    quantity: int
    rate: float
    amount: float
    date: str | None = None


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    columns_found: list[str] = field(default_factory=list)
    date_from_file: str | None = None

    @property
    def total_rows(self) -> int:
        return len(self.rows) + len(self.skipped)


def _norm(header: str) -> str:
    return "".join(ch for ch in header.lower() if ch.isalnum())


def _map_columns(fieldnames: list[str]) -> dict[str, str]:
    """Map canonical name -> the actual column header present."""
    normalised = {_norm(f): f for f in fieldnames if f and f.strip()}
    mapping: dict[str, str] = {}
    for canonical, options in _ALIASES.items():
        for option in options:
            if option in normalised:
                mapping[canonical] = normalised[option]
                break
    missing = [c for c in REQUIRED if c not in mapping]
    if missing:
        raise FloorSheetError(
            f"missing required column(s): {', '.join(missing)}. "
            f"Columns found: {', '.join(fieldnames) or '(none)'}"
        )
    return mapping


def _to_float(raw: str) -> float:
    """Parse a number that may carry thousand separators or a currency sign.

    ``Rs. 1,000`` must become 1000, not 0.1. The old filter kept the "." of
    "Rs." and dropped the "," and silently returned a rate one thousand times
    too small - and a wrong rate flows into amount, turnover and HHI with no
    warning anywhere.

    The string is first offered to ``float()`` **verbatim**, which is the only
    reading that cannot corrupt a value: the fallback filter below removes
    every character that is not a digit, so ``1e400`` would become ``1400``
    and ``1e5`` would become ``15`` - a plausible-looking wrong quantity.
    Scientific notation therefore survives intact (and overflow arrives as
    ``inf``, which the callers reject rather than store).
    """
    text = raw.strip()
    try:
        return float(text)
    except ValueError:
        pass  # currency signs, separators, spaced negatives: handled below
    text = re.sub(r"(?i)\b(rs|npr|nrs|inr|usd|np)\b\.?", "", text)
    if re.search(r"[eE]", text):
        # Scientific notation that did NOT parse verbatim, i.e. it also
        # carried a currency sign, spacing or separators ("Rs 1e5"). The
        # separator-stripping fallback below would delete the exponent
        # marker and turn "1e5 USD" into the plausible-looking wrong number
        # 15 - the exact corruption B-36 exists to stop. Reject the value
        # (the row is skipped with a reason) instead of guessing at it.
        raise ValueError(f"not a number: {raw!r}")
    text = re.sub(r"[^\d.,\-]", "", text)
    negative = text.startswith("-")
    text = text.replace("-", "")
    if "," in text and "." in text:
        # Both separators: the last one is the decimal point.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", "")
    if text.count(".") > 1:
        raise ValueError(f"not a number: {raw!r}")
    if text in ("", "."):
        raise ValueError(f"not a number: {raw!r}")
    value = float(text)
    return -value if negative else value


def parse_floorsheet(text: str) -> ParseResult:
    """Parse floor-sheet CSV text into rows, reporting every skipped line.

    Skipped rows are kept with their line number and reason rather than being
    silently dropped, because a silently dropped row is a wrong total.
    """
    if not text or not text.strip():
        raise FloorSheetError("the file is empty")

    sample = text.lstrip("﻿")[:4096]
    try:
        dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel  # fall back to commas; most published sheets use them

    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), dialect=dialect)
    if not reader.fieldnames:
        raise FloorSheetError("the file has no header row")
    mapping = _map_columns(list(reader.fieldnames))

    out = ParseResult(columns_found=list(reader.fieldnames))
    seen: set[tuple] = set()
    for line_no, raw in enumerate(reader, start=2):
        if raw is None or all(not (v or "").strip() for v in raw.values()):
            continue  # trailing blank line
        try:
            symbol = (raw.get(mapping["symbol"]) or "").strip().upper()
            buyer = (raw.get(mapping["buyer"]) or "").strip()
            seller = (raw.get(mapping["seller"]) or "").strip()
            qty_raw = _to_float(raw.get(mapping["quantity"]) or "")
            quantity = int(round(qty_raw))
            rate = _to_float(raw.get(mapping["rate"]) or "")
        except (ValueError, TypeError, OverflowError) as exc:
            # OverflowError: a quantity like 1e400 is a float, and int() of it
            # has no SQLite representation. The row is skipped like any other
            # bad row - it must not abort the whole session's import.
            out.skipped.append({"line": line_no, "reason": str(exc)})
            continue

        if abs(qty_raw - quantity) > 1e-9:
            # Fractional quantities are round-half-to-even, so 2.5 -> 2 and
            # 3.5 -> 4. Odd lots are reported here rather than rounded away
            # silently, exactly like a disagreeing amount.
            out.warnings.append(
                f"line {line_no}: quantity {qty_raw:g} is fractional; stored as {quantity}"
            )

        if not symbol or not buyer or not seller:
            out.skipped.append({"line": line_no, "reason": "empty symbol, buyer or seller"})
            continue
        if quantity <= 0:
            out.skipped.append({"line": line_no, "reason": f"quantity {quantity} <= 0"})
            continue
        if quantity > 10**12:
            # Well beyond any real NEPSE print, and beyond what SQLite's
            # INTEGER column accepts without raising mid-INSERT - which would
            # abort the whole session instead of skipping one corrupt line.
            out.skipped.append(
                {"line": line_no, "reason": f"quantity {quantity} is implausibly large"}
            )
            continue
        if not math.isfinite(rate):
            # float() happily parses "1e400" as inf and "nan" as nan; neither
            # is a price. Skipping keeps a corrupt rate out of amount,
            # turnover and every broker share computed from it.
            out.skipped.append({"line": line_no, "reason": f"rate {rate} is not a usable price"})
            continue
        if rate <= 0:
            out.skipped.append({"line": line_no, "reason": f"rate {rate} <= 0"})
            continue

        date_value: str | None = None
        if "date" in mapping:
            date_value = (raw.get(mapping["date"]) or "").strip() or None
        out.date_from_file = out.date_from_file or date_value

        expected = quantity * rate
        if "amount" in mapping and (raw.get(mapping["amount"]) or "").strip():
            try:
                amount = _to_float(raw[mapping["amount"]])
            except ValueError:
                amount = expected
                out.warnings.append(
                    f"line {line_no}: amount {raw[mapping['amount']]!r} was not a "
                    f"number; recomputed as quantity x rate"
                )
            else:
                if abs(amount - expected) > max(AMOUNT_TOLERANCE, expected * 0.005):
                    out.warnings.append(
                        f"line {line_no}: amount {amount} disagrees with quantity x "
                        f"rate ({round(expected, 4)}); using quantity x rate"
                    )
                    amount = expected
        else:
            amount = expected

        key = (symbol, buyer, seller, quantity, round(rate, 6))
        if key in seen:
            out.skipped.append({"line": line_no, "reason": "duplicate row in the same file"})
            continue
        seen.add(key)

        out.rows.append(
            ParsedRow(
                symbol=symbol,
                buyer=buyer,
                seller=seller,
                quantity=quantity,
                rate=rate,
                amount=round(amount, 4),
                date=date_value,
            )
        )
    return out


def import_floorsheet(
    text: str,
    traded_at: str,
    source: str = "manual import",
    db_path=None,
) -> dict[str, Any]:
    """Import one floor sheet. Idempotent for a given (file, session).

    ``traded_at`` is the session the sheet describes; any per-row ``date``
    column in the file takes precedence for that individual row.
    """
    init_app_db(db_path)
    try:
        datetime.fromisoformat(str(traded_at).replace("Z", "+00:00"))
    except ValueError as exc:
        # A typo'd session date would otherwise be stored as a label and every
        # summary would treat it as a real trading day.
        raise FloorSheetError(
            f"traded_at must be an ISO date or timestamp, got {traded_at!r}"
        ) from exc
    parsed = parse_floorsheet(text)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    with get_conn(db_path) as conn:
        elsewhere = conn.execute(
            "SELECT DISTINCT traded_at FROM floorsheet_imports "
            "WHERE content_hash = ? AND traded_at <> ?",
            (content_hash, traded_at),
        ).fetchall()
        if elsewhere:
            # A file is one session. If identical bytes arrive under a second
            # label, both sessions now count the same prints - say so loudly
            # rather than letting turnover and concentration be inflated.
            other = ", ".join(r["traded_at"] for r in elsewhere)
            parsed.warnings.append(
                f"This exact file was already imported for session(s) {other}. "
                f"Importing it again under {traded_at} stores the same prints a "
                f"second time, so combined totals across those sessions will "
                f"double-count."
            )
        existing = conn.execute(
            "SELECT id, imported_at FROM floorsheet_imports "
            "WHERE content_hash = ? AND traded_at = ?",
            (content_hash, traded_at),
        ).fetchone()
        if existing:
            count = conn.execute(
                "SELECT COUNT(*) FROM floorsheet_trades WHERE traded_at = ?",
                (traded_at,),
            ).fetchone()[0]
            return {
                "already_imported": True,
                "import_id": existing["id"],
                "traded_at": traded_at,
                "rows_total": parsed.total_rows,
                "rows_imported": 0,
                "rows_skipped": len(parsed.skipped),
                "stored_trades": count,
                "skipped": parsed.skipped[:50],
                "warnings": parsed.warnings[:50],
                "note": "This exact file was already imported for this session; nothing was added.",
            }

        inserted = 0
        for row in parsed.rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO floorsheet_trades "
                "(traded_at, symbol, buyer, seller, quantity, rate, amount, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.date or traded_at,
                    row.symbol,
                    row.buyer,
                    row.seller,
                    row.quantity,
                    row.rate,
                    row.amount,
                    source,
                ),
            )
            inserted += cur.rowcount

        cur = conn.execute(
            "INSERT INTO floorsheet_imports "
            "(source, content_hash, traded_at, rows_total, rows_imported, "
            " rows_skipped, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                source,
                content_hash,
                traded_at,
                parsed.total_rows,
                inserted,
                len(parsed.skipped),
                now_iso(),
            ),
        )
        import_id = int(cur.lastrowid or 0)
        # ``stored_trades`` means the same thing in both return paths: how many
        # trades the session holds in total. The duplicate-file branch already
        # reported the session total, so this branch must too.
        stored = conn.execute(
            "SELECT COUNT(*) FROM floorsheet_trades WHERE traded_at = ?",
            (traded_at,),
        ).fetchone()[0]

    return {
        "already_imported": False,
        "import_id": import_id,
        "traded_at": traded_at,
        "rows_total": parsed.total_rows,
        "rows_imported": inserted,
        "rows_skipped": len(parsed.skipped),
        "stored_trades": stored,
        "skipped": parsed.skipped[:50],
        "warnings": parsed.warnings[:50],
        "columns_found": parsed.columns_found,
        "note": (
            f"{inserted} trade(s) stored for {traded_at}; "
            f"{len(parsed.skipped)} row(s) skipped and reported above."
        ),
    }


def _shares(
    rows: list[dict[str, Any]], key: str, scope_quantity: int, scope_amount: float
) -> list[dict[str, Any]]:
    """Rank one side of the sheet, with each row's share of the SCOPE total.

    The denominator must be the whole session (or filter), never the top-N
    subset that survived the LIMIT: with the subset, ten brokers holding 84%
    of the flow each report an inflated share and the listed shares sum to
    exactly 100% while covering less than the session.
    """
    out = []
    for r in rows:
        q = int(r[key + "_quantity"])
        out.append(
            {
                key: r[key],
                "quantity": q,
                "amount": round(float(r["amount"]), 2),
                "share_of_quantity_pct": round(q / scope_quantity * 100.0, 4)
                if scope_quantity
                else None,
                "share_of_amount_pct": round(float(r["amount"]) / scope_amount * 100.0, 4)
                if scope_amount
                else None,
            }
        )
    return out


def _hhi(shares: list[float]) -> float | None:
    """Herfindahl-Hirschman index over quantity shares (0-10,000)."""
    shares = [s for s in shares if s is not None]
    if not shares:
        return None
    return round(float(sum(s * s for s in shares)), 2)


def summary(
    db_path=None,
    traded_at: str | None = None,
    symbol: str | None = None,
    top: int = 10,
) -> dict[str, Any]:
    """Concentration and counterparty analysis over the imported floor sheets.

    Everything here is descriptive. No figure is a signal, and the broker IDs
    are not beneficial owners.
    """
    init_app_db(db_path)
    where = []
    params: list[Any] = []
    if traded_at:
        where.append("traded_at = ?")
        params.append(traded_at)
    if symbol:
        where.append("symbol = ?")
        params.append(symbol.upper())
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    with get_conn(db_path) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS trades, COUNT(DISTINCT symbol) AS symbols, "
            f"COUNT(DISTINCT traded_at) AS sessions, "
            f"COALESCE(SUM(quantity), 0) AS quantity, "
            f"COALESCE(SUM(amount), 0) AS amount "
            f"FROM floorsheet_trades {clause}",
            params,
        ).fetchone()
        buys = conn.execute(
            f"SELECT buyer, SUM(quantity) AS buyer_quantity, SUM(amount) AS amount "
            f"FROM floorsheet_trades {clause} GROUP BY buyer "
            f"ORDER BY buyer_quantity DESC LIMIT ?",
            [*params, top],
        ).fetchall()
        sells = conn.execute(
            f"SELECT seller, SUM(quantity) AS seller_quantity, SUM(amount) AS amount "
            f"FROM floorsheet_trades {clause} GROUP BY seller "
            f"ORDER BY seller_quantity DESC LIMIT ?",
            [*params, top],
        ).fetchall()
        symbols = conn.execute(
            f"SELECT symbol, SUM(quantity) AS qty, SUM(amount) AS amount, "
            f"COUNT(*) AS prints, COUNT(DISTINCT buyer) AS buyers, "
            f"COUNT(DISTINCT seller) AS sellers "
            f"FROM floorsheet_trades {clause} GROUP BY symbol "
            f"ORDER BY amount DESC LIMIT ?",
            [*params, top],
        ).fetchall()
        pairs = conn.execute(
            f"SELECT buyer, seller, COUNT(*) AS prints, SUM(quantity) AS qty, "
            f"SUM(amount) AS amount FROM floorsheet_trades {clause} "
            f"GROUP BY buyer, seller ORDER BY amount DESC LIMIT ?",
            [*params, top],
        ).fetchall()
        shares_by_buyer = conn.execute(
            f"SELECT buyer, SUM(quantity) AS q FROM floorsheet_trades {clause} GROUP BY buyer",
            params,
        ).fetchall()
        shares_by_seller = conn.execute(
            f"SELECT seller, SUM(quantity) AS q FROM floorsheet_trades {clause} GROUP BY seller",
            params,
        ).fetchall()
        sessions = conn.execute(
            f"SELECT traded_at, COUNT(*) AS prints, SUM(amount) AS amount "
            f"FROM floorsheet_trades {clause} GROUP BY traded_at ORDER BY traded_at",
            params,
        ).fetchall()
        imports = conn.execute(
            "SELECT source, traded_at, rows_total, rows_imported, rows_skipped, "
            "imported_at FROM floorsheet_imports ORDER BY imported_at DESC LIMIT 10"
        ).fetchall()

    trades = int(total["trades"])
    buyer_shares = (
        [r["q"] / total["quantity"] * 100.0 for r in shares_by_buyer] if total["quantity"] else []
    )
    seller_shares = (
        [r["q"] / total["quantity"] * 100.0 for r in shares_by_seller] if total["quantity"] else []
    )
    buyer_hhi, seller_hhi = _hhi(buyer_shares), _hhi(seller_shares)

    warnings: list[str] = []
    if trades == 0:
        warnings.append(
            "No floor sheet has been imported. Import a session's CSV before "
            "reading anything into these numbers."
        )
    if traded_at is None and int(total["sessions"] or 0) > 1:
        warnings.append(
            f"This summary spans {int(total['sessions'])} sessions. Pass traded_at "
            "for a single day: mixing sessions double-counts the same shares."
        )
    for name, value in (("buyer", buyer_hhi), ("seller", seller_hhi)):
        if value is not None and value >= 2500:
            warnings.append(
                f"{name} concentration is high (HHI {value}). A high HHI here "
                "usually means one broker code printed a lot - which can be a "
                "single large client, a house trading with itself, or a "
                "cross. It is NOT evidence of accumulation or distribution."
            )

    return {
        "filter": {"traded_at": traded_at, "symbol": (symbol or "").upper() or None},
        "totals": {
            "trades": trades,
            "symbols": int(total["symbols"] or 0),
            "sessions": int(total["sessions"] or 0),
            "quantity": int(total["quantity"] or 0),
            "amount": round(float(total["amount"] or 0), 2),
        },
        "top_buyers": _shares(
            [dict(r) for r in buys],
            "buyer",
            int(total["quantity"] or 0),
            float(total["amount"] or 0),
        ),
        "top_sellers": _shares(
            [dict(r) for r in sells],
            "seller",
            int(total["quantity"] or 0),
            float(total["amount"] or 0),
        ),
        "top_symbols": [
            {
                "symbol": r["symbol"],
                "quantity": int(r["qty"]),
                "amount": round(float(r["amount"]), 2),
                "prints": int(r["prints"]),
                "distinct_buyers": int(r["buyers"]),
                "distinct_sellers": int(r["sellers"]),
            }
            for r in symbols
        ],
        "top_counterparties": [
            {
                "buyer": r["buyer"],
                "seller": r["seller"],
                "prints": int(r["prints"]),
                "quantity": int(r["qty"]),
                "amount": round(float(r["amount"]), 2),
            }
            for r in pairs
        ],
        "concentration": {
            "unique_buyers": len(shares_by_buyer),
            "unique_sellers": len(shares_by_seller),
            "buyer_hhi": buyer_hhi,
            "seller_hhi": seller_hhi,
            "interpretation": (
                "HHI is the sum of squared percentage shares (0-10,000). Below "
                "1500 is dispersed, 1500-2500 moderate, above 2500 concentrated. "
                "It describes broker CODES, which are not beneficial owners."
            ),
        },
        "sessions": [
            {
                "traded_at": r["traded_at"],
                "prints": int(r["prints"]),
                "amount": round(float(r["amount"]), 2),
            }
            for r in sessions
        ],
        "recent_imports": [dict(r) for r in imports],
        "warnings": warnings,
        "limits": [
            "A floor sheet records what was printed, not why. Nothing here "
            "identifies a beneficial owner: a broker code can carry many "
            "clients and a house can trade against itself.",
            "Concentration is descriptive, not a signal. A single large seller "
            "may be rebalancing, meeting a margin call, or transferring stock "
            "between accounts - this data cannot distinguish those.",
            "Only the sessions you have imported are covered. A blank here "
            "means nothing was imported, not that nothing traded.",
            "Rates are unadjusted for bonus and rights issues.",
            "Nothing here predicts future prices, and none of it is investment advice.",
        ],
    }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    return float(ordered[mid]) if n % 2 else (float(ordered[mid - 1]) + float(ordered[mid])) / 2


def trend(
    db_path=None,
    *,
    symbol: str | None = None,
    sessions: int = 10,
    top: int = 5,
) -> dict[str, Any]:
    """Multi-session activity trend and per-broker net flow (feature 3).

    Two clearly separated things:

    * **activity (observed)** — per-session trades/quantity/turnover with an
      activity direction for the latest session vs the median of the prior
      sessions in the window. These are printed facts.
    * **broker net flow (inferred)** — per broker, bought minus sold quantity
      over the window, labelled ``net_buyer``/``net_seller``/``balanced``.
      The quantities are observed; the label is an *inference about flow*, not
      evidence that anyone accumulated, and broker codes are not beneficial
      owners.

    Fewer than two imported sessions in the window yields an explicit
    ``insufficient_sessions`` status instead of a "trend" from one point.
    """
    init_app_db(db_path)
    sym = symbol.upper().strip() if symbol else None
    where = []
    params: list[Any] = []
    if sym:
        where.append("symbol = ?")
        params.append(sym)
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    with get_conn(db_path) as conn:
        rows = conn.execute(
            f"SELECT traded_at, COUNT(*) AS prints, SUM(quantity) AS quantity, "
            f"SUM(amount) AS turnover, COUNT(DISTINCT buyer) AS buyers, "
            f"COUNT(DISTINCT seller) AS sellers "
            f"FROM floorsheet_trades {clause} "
            f"GROUP BY traded_at ORDER BY traded_at DESC LIMIT ?",
            [*params, sessions],
        ).fetchall()
        activity = [
            {
                "traded_at": r["traded_at"],
                "prints": int(r["prints"]),
                "quantity": int(r["quantity"]),
                "turnover": round(float(r["turnover"]), 2),
                "buyers": int(r["buyers"]),
                "sellers": int(r["sellers"]),
            }
            for r in rows
        ]
        window = [r["traded_at"] for r in rows]

        broker_rows: list[Any] = []
        if len(window) >= 2:
            marks = ",".join("?" * len(window))
            # Bought/sold per broker within the window, in the same scope.
            broker_rows = conn.execute(
                f"SELECT broker, SUM(bought) AS bought, SUM(sold) AS sold FROM ("
                f"  SELECT buyer AS broker, quantity AS bought, 0 AS sold "
                f"  FROM floorsheet_trades WHERE traded_at IN ({marks})"
                + (" AND symbol = ?" if sym else "")
                + f"  UNION ALL "
                f"  SELECT seller AS broker, 0, quantity "
                f"  FROM floorsheet_trades WHERE traded_at IN ({marks})"
                + (" AND symbol = ?" if sym else "")
                + ") GROUP BY broker",
                ([*window, *([sym] if sym else [])] + [*window, *([sym] if sym else [])]),
            ).fetchall()

    base = {"symbol": sym, "window_sessions": window}
    if len(window) < 2:
        return {
            **base,
            "status": "insufficient_sessions",
            "activity": activity,
            "sessions_found": len(window),
            "reason": (
                f"{len(window)} imported session(s) in this scope; an activity "
                "trend needs at least 2"
            ),
            "broker_net": [],
            "note": (
                "A blank scope means nothing was imported for it, not that "
                "nothing traded. Import more sessions before reading a trend."
            ),
        }

    # activity direction: latest session vs the median of the prior ones
    chron = list(reversed(activity))  # oldest first for the comparison
    prior = [s["turnover"] for s in chron[:-1]]
    med = _median(prior)
    last = chron[-1]["turnover"]
    ratio = (last / med) if med > 0 else None
    if ratio is None:
        direction, basis = "unknown", "prior sessions have zero turnover; no ratio is defined"
    elif ratio > 1.2:
        direction, basis = "rising", None
    elif ratio < 0.8:
        direction, basis = "falling", None
    else:
        direction, basis = "steady", None
    if basis is None:
        basis = (
            f"latest session turnover {last:,.2f} vs median {med:,.2f} of the "
            f"prior {len(prior)} session(s) in the window (ratio {ratio:.2f}; "
            "rising >1.2, falling <0.8)"
        )

    flows = []
    for r in broker_rows:
        bought, sold = int(r["bought"]), int(r["sold"])
        net = bought - sold
        flows.append(
            {
                "broker": r["broker"],
                "bought": bought,
                "sold": sold,
                "net": net,
                "flow": "net_buyer" if net > 0 else "net_seller" if net < 0 else "balanced",
            }
        )
    flows.sort(key=lambda f: (-abs(f["net"]), f["broker"]))
    integrity: dict[str, Any] | None = None
    if sym:
        # Every print of one symbol is one purchase and one sale, so the
        # per-broker nets must sum to exactly zero. A non-zero sum would mean
        # the arithmetic is wrong.
        integrity = {"net_sums_to_zero": sum(f["net"] for f in flows) == 0}

    return {
        **base,
        "status": "ok",
        "scope": (
            f"symbol {sym}: activity and per-broker flow within that symbol"
            if sym
            else "whole imported sheet: activity and per-broker cross-symbol flow"
        ),
        "activity": chron,
        "activity_trend": {
            "direction": direction,
            "basis": basis,
            "kind": "observed_activity",
        },
        "broker_net": flows[:top],
        "integrity": integrity,
        "limits": [
            "Activity figures are observed prints; the direction label compares "
            "the latest session to the median of the prior sessions in the "
            "window (thresholds stated in activity_trend.basis).",
            "'net_buyer'/'net_seller' are inferences from observed bought vs "
            "sold quantities. They are NOT evidence of accumulation or "
            "distribution by any beneficial owner: broker codes are not owners "
            "and a house can trade against itself.",
            "Only imported sessions are covered; no session is invented.",
        ],
    }


def list_sessions(db_path=None) -> list[dict[str, Any]]:
    """Every session with an imported floor sheet, newest first."""
    init_app_db(db_path)
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT traded_at, COUNT(*) AS prints, COUNT(DISTINCT symbol) AS symbols, "
            "SUM(amount) AS amount, MIN(source) AS source "
            "FROM floorsheet_trades GROUP BY traded_at ORDER BY traded_at DESC"
        ).fetchall()
    return [
        {
            "traded_at": r["traded_at"],
            "prints": int(r["prints"]),
            "symbols": int(r["symbols"]),
            "amount": round(float(r["amount"] or 0), 2),
            "source": r["source"],
        }
        for r in rows
    ]
