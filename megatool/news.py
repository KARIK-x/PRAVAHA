"""News / Events - the LOCAL processing layer (spec Section 22, register item 7).

WHAT THIS IS
------------
A complete, tested pipeline for news records the **owner imports**: parse,
validate, normalise timestamps, deduplicate, associate symbols, store, and
summarise. Every skipped row is reported with its line and reason, exactly
like the floor-sheet importer, because a silently dropped headline is a wrong
"latest news" date.

WHAT THIS IS NOT
----------------
It is not a news source. No live feed is connected (register item 7 / L4 -
ShareSansar licensing is unresolved, and the official NEPSE API is behind a
login, B-09). Nothing here fetches or scrapes, no sentiment is scored, and
nothing predicts prices from headlines. Records exist only if the owner
imported them, and every summary says so.

On top of storage, the summary carries *deterministic classifications* of the
imported headlines: an event category from a closed vocabulary (with the
matched keyword as evidence), a literal symbol-in-headline relevance check,
and a heuristic grouping of repeated coverage. None of these is sentiment, an
impact estimate, or a ranking — each response field says what it is.

SOURCE CONTRACT (what a future adapter or the owner must supply)
----------------------------------------------------------------
CSV (delimiters auto-detected) or JSON (a list of objects, or an object with
an ``items`` list). Recognised keys/headers, case-insensitive:

==================  =========================================================
key                 meaning
==================  =========================================================
``title``            REQUIRED. The headline as published.
``published_at``     REQUIRED. ISO date (``2026-01-05``) or datetime
                     (``2026-01-05T14:30:00``). Dates before 1900 or more
                     than a day in the future are rejected, not stored.
``summary``          Optional body/description text.
``url``              Optional link; used as the dedup identity when present.
``source``           Optional publisher name (ShareSansar, manager's note...).
``symbols``          Optional comma/space separated scrip codes to associate.
==================  =========================================================

Unrecognised columns are ignored (and reported in the parse warnings), so a
richer future feed can be imported without code changes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from megatool.db import get_conn, init_app_db, now_iso

#: A published date before this is a data-entry error, not news.
MIN_PUBLISHED = datetime(1900, 1, 1)

#: Nothing may be published more than this far beyond the import clock.
FUTURE_TOLERANCE_DAYS = 1

#: Titles longer than this are truncated with a warning rather than dropped.
MAX_TITLE_CHARS = 1000

#: Scrip-code sanity bound (longest current NEPSE symbols are well under this).
MAX_SYMBOL_CHARS = 20


class NewsError(Exception):
    """A news import/parse problem, phrased for a person rather than a log."""


_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "headline", "subject"),
    "published_at": ("published_at", "published", "publishedat", "date", "time", "timestamp"),
    "summary": ("summary", "body", "description", "details"),
    "url": ("url", "link", "href"),
    "source": ("source", "publisher", "outlet"),
    "symbols": ("symbols", "symbol", "scrip", "scrips", "ticker", "tickers", "tags"),
}

REQUIRED = ("title", "published_at")


def _norm_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _map_columns(fieldnames: list[str]) -> dict[str, str]:
    """canonical key -> the actual header it was found under."""
    mapping: dict[str, str] = {}
    lowered = {_norm_header(f): f for f in fieldnames}
    for canonical, options in _ALIASES.items():
        for opt in options:
            if opt in lowered:
                mapping[canonical] = lowered[opt]
                break
    return mapping


@dataclass(slots=True)
class NewsItem:
    uid: str
    published_at: str
    title: str
    summary: str = ""
    url: str = ""
    publisher: str = ""
    symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ParseResult:
    rows: list[NewsItem] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_rows: int = 0
    columns_found: list[str] = field(default_factory=list)

    @property
    def duplicates(self) -> int:
        return sum(1 for s in self.skipped if "duplicate" in s["reason"])


def _uid(url: str, title: str, published: str) -> str:
    """Stable identity: the URL when we have one, else title+date."""
    basis = url.strip().lower() if url.strip() else f"{published}|{title.strip().lower()}"
    return hashlib.sha256(basis.encode()).hexdigest()[:32]


def _normalise_timestamp(raw: Any, now: datetime | None) -> tuple[str | None, str | None]:
    """ISO string or a rejection reason - never both, never neither."""
    text = str(raw or "").strip()
    if not text:
        return None, "empty timestamp"
    text = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, f"not an ISO date/datetime: {text!r}"

    clock = now if now is not None else datetime.now(UTC)
    clock_naive = clock.replace(tzinfo=None) if clock.tzinfo else clock
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)

    if parsed < MIN_PUBLISHED:
        return None, f"published {parsed.date()} is before {MIN_PUBLISHED.date()}"
    limit = clock_naive + timedelta(days=FUTURE_TOLERANCE_DAYS)
    if parsed > limit:
        return None, f"published {parsed.isoformat()} is in the future (after {limit.date()})"
    if len(text) <= 10:
        return parsed.date().isoformat(), None
    return parsed.isoformat(timespec="seconds"), None


def _normalise_symbols(raw: Any, warnings: list[str], line_no: int) -> list[str]:
    tokens = re.split(r"[,;\s]+", str(raw or "").strip())
    out: list[str] = []
    for tok in tokens:
        tok = tok.strip().upper().strip(".")
        if not tok:
            continue
        if not tok.isalnum() or len(tok) > MAX_SYMBOL_CHARS:
            warnings.append(f"line {line_no}: symbol {tok!r} is not a scrip code; ignored")
            continue
        if tok not in out:
            out.append(tok)
    return out


def _clean_row(
    raw: dict[str, Any],
    mapping: dict[str, str],
    now: datetime | None,
    line_no: int,
    warnings: list[str],
) -> tuple[NewsItem | None, str | None]:
    def get(key: str) -> str:
        col = mapping.get(key)
        return str(raw.get(col) or "").strip() if col else ""

    title = get("title")
    if not title:
        return None, "missing title"
    if len(title) > MAX_TITLE_CHARS:
        # Truncated, not dropped - but the caller is told, because a headline
        # quietly cut mid-word would be quoted as if it were complete.
        warnings.append(
            f"line {line_no}: title of {len(title)} chars truncated to {MAX_TITLE_CHARS}"
        )
        title = title[:MAX_TITLE_CHARS]

    published, reason = _normalise_timestamp(get("published_at"), now)
    if published is None:
        return None, reason

    url = get("url")
    item = NewsItem(
        uid=_uid(url, title, published),
        published_at=published,
        title=title,
        summary=get("summary"),
        url=url,
        publisher=get("source"),
    )
    item.symbols = _normalise_symbols(get("symbols"), warnings, line_no)
    return item, None


def parse_news(text: str, fmt: str = "csv", now: datetime | None = None) -> ParseResult:
    """Parse owner-supplied news records; every rejection carries a reason."""
    if not text or not text.strip():
        raise NewsError("the file is empty")
    fmt = fmt.lower()
    if fmt not in ("csv", "json"):
        raise NewsError(f"unknown format {fmt!r}: use 'csv' or 'json'")

    out = ParseResult()
    records: list[dict[str, Any]] = []
    if fmt == "csv":
        sample = text.lstrip("﻿")[:4096]
        try:
            dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), dialect=dialect)
        if not reader.fieldnames:
            raise NewsError("the file has no header row")
        out.columns_found = list(reader.fieldnames)
        mapping = _map_columns(list(reader.fieldnames))
        missing = [k for k in REQUIRED if k not in mapping]
        if missing:
            raise NewsError(
                f"missing required column(s): {', '.join(missing)}. "
                f"Columns found: {', '.join(reader.fieldnames)}"
            )
        unknown = [c for c in reader.fieldnames if c not in mapping.values()]
        if unknown:
            out.warnings.append(f"column(s) not recognised and ignored: {', '.join(unknown)}")
        for line_no, raw in enumerate(reader, start=2):
            if raw is None or all(not (v or "").strip() for v in raw.values()):
                continue
            records.append(dict(raw, __line__=line_no))  # type: ignore[arg-type]
    else:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise NewsError(f"not valid JSON: {exc}") from exc
        if isinstance(payload, dict):
            payload = payload.get("items")
            if not isinstance(payload, list):
                raise NewsError("JSON must be a list of objects, or an object with an 'items' list")
        if not isinstance(payload, list):
            raise NewsError("JSON must be a list of objects")
        mapping = {k: k for k in _ALIASES}  # JSON keys are matched directly
        for i, obj in enumerate(payload, start=1):
            if not isinstance(obj, dict):
                out.skipped.append({"line": i, "reason": "not an object"})
                continue
            records.append(dict(obj, __line__=i))

    out.total_rows = len(records)
    seen: set[str] = set()
    for rec in records:
        line_no = rec.pop("__line__", 0)
        # JSON records use canonical keys; CSV records use found headers.
        if fmt == "json":
            canon = {k: rec.get(k) for k in _ALIASES}
        else:
            canon = {k: rec.get(col) for k, col in mapping.items()}
        item, reason = _clean_row(canon, {k: k for k in canon}, now, line_no, out.warnings)
        if item is None:
            out.skipped.append({"line": line_no, "reason": reason or "invalid row"})
            continue
        if item.uid in seen:
            out.skipped.append(
                {"line": line_no, "reason": f"duplicate item {item.title[:40]!r} in this file"}
            )
            continue
        seen.add(item.uid)
        out.rows.append(item)
    return out


def import_news(
    text: str,
    fmt: str = "csv",
    source_file: str = "",
    now: datetime | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Parse and store one owner-supplied file. Idempotent by item identity."""
    init_app_db(db_path)
    parsed = parse_news(text, fmt=fmt, now=now)
    imported_at = now_iso()
    added = 0
    duplicates = 0
    with get_conn(db_path) as conn:
        for item in parsed.rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO news_items "
                "(uid, published_at, title, summary, url, publisher, source_file, imported_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.uid,
                    item.published_at,
                    item.title,
                    item.summary,
                    item.url,
                    item.publisher,
                    source_file,
                    imported_at,
                ),
            )
            if cur.rowcount == 0:
                duplicates += 1
                continue
            added += 1
            news_id = cur.lastrowid
            for sym in item.symbols:
                conn.execute(
                    "INSERT OR IGNORE INTO news_item_symbols (news_id, symbol) VALUES (?, ?)",
                    (news_id, sym),
                )
    return {
        "rows": parsed.total_rows,
        "added": added,
        "duplicates": duplicates + parsed.duplicates,
        "skipped": len(parsed.skipped) - parsed.duplicates,
        "skipped_detail": parsed.skipped[:20],
        "warnings": parsed.warnings,
        "symbols": sorted({s for item in parsed.rows for s in item.symbols}),
        "source_file": source_file,
    }


# --------------------------------------------- deterministic event classification
#: Closed vocabulary for event categorisation. Every category must be earned
#: by an explicit keyword hit recorded as evidence; anything unmatched is
#: "other". These are *classifications of reported headlines*, never sentiment
#: scores and never price-impact estimates.
NEWS_CATEGORIES = (
    "corporate_action",
    "financial_result",
    "regulatory",
    "meeting",
    "listing",
    "market_general",
    "other",
)

#: First match wins, top to bottom. The matched keyword is returned as basis
#: so a human can audit every classification.
_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "corporate_action",
        ("dividend", "bonus share", "right share", "rights", "split", "book close", "payout"),
    ),
    (
        "financial_result",
        (
            "profit",
            "loss",
            "eps",
            "revenue",
            "net worth",
            "quarterly",
            "annual report",
            "financial result",
        ),
    ),
    (
        "regulatory",
        (
            "sebon",
            "circular",
            "suspended",
            "suspension",
            "trading halt",
            "margin",
            "notified",
            "regulator",
        ),
    ),
    ("meeting", ("agm", "egm", "board meeting", "meeting")),
    ("listing", ("listed", "listing", "ipo", "fpo", "debenture", "mutual fund")),
    ("market_general", ("nepse index", "market closed", "market rose", "market fell", "turnover")),
)


def categorize_headline(title: str, summary: str = "") -> dict[str, Any]:
    """Deterministically classify one headline into the closed vocabulary.

    Returns ``{"category", "basis", "kind"}`` where ``kind`` is always
    ``"deterministic_classification"`` — this function never scores sentiment
    or estimates price impact, and no response field implies that it does.
    """
    text = f"{title} {summary}".lower()
    for category, keywords in _CATEGORY_RULES:
        for keyword in keywords:
            # Word-boundary match: "eps" must not fire inside "nepse", and
            # evidence names the keyword exactly as matched.
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                return {
                    "category": category,
                    "basis": f"keyword: {keyword!r} in headline text",
                    "kind": "deterministic_classification",
                }
    return {
        "category": "other",
        "basis": "no vocabulary keyword matched",
        "kind": "deterministic_classification",
    }


def relevance_for(title: str, symbol: str | None) -> dict[str, Any]:
    """Explainable per-symbol relevance: is the symbol literally named?

    A symbol linked only through the import mapping is *associated*, not
    *mentioned*; the distinction is stated rather than collapsed into a score.
    """
    if not symbol:
        return {
            "direct_mention": False,
            "basis": "no symbol in scope",
            "kind": "deterministic_match",
        }
    named = re.search(rf"\b{re.escape(symbol)}\b", title or "", re.IGNORECASE) is not None
    return {
        "direct_mention": named,
        "basis": (
            f"{symbol} appears as a word in the headline"
            if named
            else f"{symbol} linked via import mapping, not named in the headline"
        ),
        "kind": "deterministic_match",
    }


def story_key(title: str) -> str:
    """Heuristic grouping key for repeated coverage of one story.

    Normalises case/punctuation and keeps the first eight words, so rewrites
    of the same lead sentence group together. It is a *heuristic* — groups are
    reported for review, never silently merged.
    """
    normalised = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    head = " ".join(normalised.split()[:8])
    return hashlib.sha1(head.encode("utf-8")).hexdigest()[:16]


def _repeated_coverage(rows: list[tuple[Any, ...]], limit: int = 25) -> dict[str, Any]:
    """Groups of items sharing a story key (title, published_at rows)."""
    groups: dict[str, dict[str, Any]] = {}
    for published, title in rows:
        key = story_key(str(title))
        g = groups.setdefault(
            key,
            {
                "story_key": key,
                "items": 0,
                "titles": [],
                "first_published": None,
                "last_published": None,
            },
        )
        g["items"] += 1
        if str(title) not in g["titles"] and len(g["titles"]) < 3:
            g["titles"].append(str(title))
        pub = str(published)
        if g["first_published"] is None or pub < g["first_published"]:
            g["first_published"] = pub
        if g["last_published"] is None or pub > g["last_published"]:
            g["last_published"] = pub
    repeated = sorted(
        (g for g in groups.values() if g["items"] > 1),
        key=lambda g: (-g["items"], g["story_key"]),
    )[:limit]
    return {
        "groups": repeated,
        "method": "first-8-words normalised title (heuristic; review before treating as one story)",
        "note": "Repeated coverage is grouped for review only; nothing is merged or deleted.",
    }


def news_summary(
    symbol: str | None = None,
    since: str | None = None,
    top: int = 10,
    now: datetime | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Counts and recency over the IMPORTED records - never more than that."""
    init_app_db(db_path)
    sym = symbol.upper().strip() if symbol else None
    where: list[str] = []
    params: list[Any] = []
    join = ""
    if sym:
        join = " JOIN news_item_symbols nis ON nis.news_id = n.id"
        where.append("nis.symbol = ?")
        params.append(sym)
    if since:
        where.append("n.published_at >= ?")
        params.append(since)
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    with get_conn(db_path) as conn:
        totals = conn.execute(
            f"SELECT COUNT(*) AS items, MIN(n.published_at) AS first_published, "
            f"MAX(n.published_at) AS last_published FROM news_items n{join} {clause}",
            params,
        ).fetchone()
        by_symbol = conn.execute(
            "SELECT nis.symbol, COUNT(*) AS items, MAX(n.published_at) AS latest "
            "FROM news_item_symbols nis JOIN news_items n ON n.id = nis.news_id "
            "GROUP BY nis.symbol ORDER BY items DESC, nis.symbol LIMIT ?",
            [top],
        ).fetchall()
        by_date = conn.execute(
            f"SELECT substr(n.published_at, 1, 10) AS day, COUNT(*) AS items "
            f"FROM news_items n{join} {clause} GROUP BY day ORDER BY day DESC LIMIT 30",
            params,
        ).fetchall()
        recent = conn.execute(
            f"SELECT n.published_at, n.title, n.publisher, n.url FROM news_items n{join} "
            f"{clause} ORDER BY n.published_at DESC LIMIT ?",
            [*params, top],
        ).fetchall()
        all_titles = conn.execute(
            f"SELECT n.published_at, n.title FROM news_items n{join} {clause}",
            params,
        ).fetchall()

    clock = now if now is not None else datetime.now(UTC)
    clock_naive = clock.replace(tzinfo=None) if clock.tzinfo else clock
    warnings: list[str] = []
    last = totals["last_published"] if totals else None
    if last:
        try:
            age = (clock_naive - datetime.fromisoformat(str(last)).replace(tzinfo=None)).days
            if age > 7:
                warnings.append(
                    f"the newest item was published {age} days ago: this is an "
                    "import archive, not a live feed"
                )
        except ValueError:
            warnings.append(f"stored timestamp {last!r} is not ISO-parseable")

    return {
        "filter": {"symbol": sym, "since": since},
        "totals": {
            "items": int(totals["items"]) if totals else 0,
            "first_published": totals["first_published"] if totals else None,
            "last_published": last,
        },
        "by_symbol": [dict(r) for r in by_symbol],
        "by_date": [dict(r) for r in by_date],
        "recent": [
            {
                **dict(r),
                "event": categorize_headline(str(r["title"])),
                "relevance": relevance_for(str(r["title"]), sym),
                "fact_vs_derived": (
                    "headline, publisher, published_at and url are reported "
                    "facts; 'event' and 'relevance' are deterministic "
                    "classifications with their basis stated — not sentiment, "
                    "not price-impact estimates"
                ),
            }
            for r in recent
        ],
        "repeated_coverage": _repeated_coverage(
            [(r["published_at"], r["title"]) for r in all_titles]
        ),
        "warnings": warnings,
        "note": (
            "News records exist ONLY if the owner imported them: no live source "
            "is connected (register item 7 / L4) and nothing is fetched or "
            "scraped. Headlines are descriptions of what was published, not "
            "signals, and certainly not investment advice. Event categories "
            "and per-symbol relevance are deterministic keyword classifications "
            "with their evidence shown; no sentiment score and no price-impact "
            "estimate is produced anywhere in this pipeline."
        ),
    }
