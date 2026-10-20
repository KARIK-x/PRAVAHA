"""Hamro Patro calendar extraction, validation and import.

SOURCE
------
https://www.hamropatro.com/calendar/<bsYear>/<bsMonth> — a publicly readable,
server-rendered page. One cell per BS day:

    <a aria-label="31, प्रतिपदा, holiday"
       href="/calendar/2081/12?d=2081-12-31"> … </a>

The `aria-label` carries, in order: the **Gregorian day of month**, then the
event names (comma separated), and the literal token ``holiday`` when the cell
is marked as a holiday (the site's red marking). The `href` carries the
**Bikram Sambat** date as ``?d=YYYY-MM-DD`` (BS).

GREGORIAN RESOLUTION
--------------------
The page supplies the Gregorian *day* but **not** the Gregorian *month/year* for
each cell. That gap is now closed by :mod:`megatool.bs_ad`, which looks each BS
date up in a vendored, community-verified 1:1 mapping (OpenNP ``nepali-dates``,
BS 2050-2086). Resolution is a pure lookup: no month is ever guessed, and a BS
date outside the mapped range — or a BS day that does not exist in that month —
stays ``gregorian_status="unresolved"`` with the reason recorded in ``notes``.

Classification is deliberately conservative: a red/holiday cell is recorded as a
**candidate** (festival or observance), never asserted to be a national public
holiday, and never asserted to be a NEPSE market closure. Market closure has its
own status that stays ``not_independently_verified`` unless a caller supplies
evidence.

Classification is deliberately conservative: a red/holiday cell is recorded as a
**candidate** (festival or observance), never asserted to be a national public
holiday, and never asserted to be a NEPSE market closure. Market closure has its
own status that stays ``not_independently_verified`` unless a caller supplies
evidence.
"""

from __future__ import annotations

import html as _html
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

__all__ = [
    "CalendarRecord",
    "extract_range",
    "fetch_month",
    "write_dataset",
    "load_dataset",
    "CalendarError",
    "parse_calendar_page",
    "records_from_page",
    "classify_event",
    "validate_records",
    "merge_records",
    "extraction_report",
    "resolve_gregorian",
    "BS_MONTH_NAMES",
]

SOURCE_BASE = "https://www.hamropatro.com"


class CalendarError(ValueError):
    """A page or record that cannot be used as-is."""


#: BS month names (1 = Baishakh … 12 = Chaitra). Used only for labelling.
BS_MONTH_NAMES: dict[int, str] = {
    1: "Baishakh", 2: "Jestha", 3: "Ashadh", 4: "Shrawan", 5: "Bhadra",
    6: "Ashwin", 7: "Kartik", 8: "Mangsir", 9: "Poush", 10: "Magh",
    11: "Falgun", 12: "Chaitra",
}

#: BS months run 29–32 days. A parsed day outside this is a parse error.
_BS_DAY_MIN, _BS_DAY_MAX = 1, 32
_GREG_DAY_MIN, _GREG_DAY_MAX = 1, 31

#: Classification vocabulary. `holiday_cell` is the site's own marking; it is a
#: CANDIDATE, not an official determination.
CLASSIFICATIONS = (
    "national_public_holiday",
    "regional_holiday",
    "festival",
    "religious_or_cultural_observance",
    "international_observance",
    "other_calendar_event",
    "unknown",
)

#: Market-closure status, tracked separately from the calendar classification.
MARKET_CLOSURE_STATUSES = (
    "confirmed_nepse_closure",
    "confirmed_trading_session",
    "not_independently_verified",
    "unknown",
)

_CELL_RE = re.compile(
    r'<a\b(?P<attrs>[^>]*?)href="(?P<href>/calendar/(?P<bsy>\d{4})/(?P<bsm>\d{1,2})\?d=(?P<bsd>\d{4}-\d{1,2}-\d{1,2}))"(?P<rest>[^>]*)>(?P<body>.*?)</a>',
    re.S,
)
#: The Gregorian day is the number in the cell's first bare <span>. MEASURED on
#: the live page: aria-label="31, प्रतिपदा, holiday" (31 = the BS day) while the
#: first span reads "13" (the Gregorian day). Reading the label's leading number
#: as the Gregorian day was wrong by construction.
_GREG_SPAN_RE = re.compile(r'<span[^>]*>\s*(\d{1,2})\s*</span>', re.S)
_LABEL_RE = re.compile(r'aria-label="(?P<label>[^"]*)"', re.S)


@dataclass
class CalendarRecord:
    """One event on one BS date. A date with several events yields several rows."""

    bs_date: str                      # "2081-12-31"
    bs_year: int
    bs_month: int
    bs_day: int
    gregorian_day: int | None         # day-of-month only, as published
    gregorian_date: str | None        # only when a verified anchor was supplied
    gregorian_status: str             # resolved | unresolved
    event_name: str
    event_index: int                  # 0-based, disambiguates same-name events
    holiday_cell: bool                # the site marked this cell as a holiday
    classification: str
    market_closure: str
    source_url: str
    retrieved_at: str
    raw_label: str = ""
    notes: str = ""

    @property
    def event_id(self) -> str:
        """Stable identity: BS date + normalised name + index.

        Re-importing the same page therefore updates in place instead of
        duplicating, while two genuinely different events on one date stay
        distinct rows.
        """
        name = re.sub(r"\s+", " ", self.event_name).strip().lower()
        return f"{self.bs_date}#{name}#{self.event_index}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["event_id"] = self.event_id
        return d


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(text or "")).strip()


def parse_calendar_page(html: str, *, source_url: str = "", bs_year: int | None = None,
                        bs_month: int | None = None) -> dict[str, Any]:
    """Parse one Hamro Patro month page into raw cell records.

    Returns ``{"bs_year", "bs_month", "cells": [ {bs_date, gregorian_day,
    events, holiday_cell, raw_label} ], "errors": [...] }``. ``gregorian_day``
    is read from the cell's first bare span; the ``aria-label``'s leading number
    is the BS day and is cross-checked against the ``href``. No classification
    or date conversion happens here — this is the raw layer.
    """
    if not html or "hamropatro" not in html and "/calendar/" not in html:
        raise CalendarError("not a Hamro Patro calendar page")
    cells: list[dict[str, Any]] = []
    errors: list[str] = []
    for m in _CELL_RE.finditer(html):
        href = m.group("href")
        label_m = _LABEL_RE.search(m.group("attrs") or "") or _LABEL_RE.search(m.group("rest") or "")
        raw_label = label_m.group("label") if label_m else ""
        parts = [_clean(p) for p in raw_label.split(",")] if raw_label else []
        parts = [p for p in parts if p]
        bs_day_from_label = None
        if parts and re.fullmatch(r"\d{1,2}", parts[0]):
            bs_day_from_label = int(parts[0])
            parts = parts[1:]
        holiday_cell = any(p.lower() == "holiday" for p in parts)
        events = [p for p in parts if p.lower() != "holiday"]
        # The Gregorian day comes from the cell's first bare span (see
        # _GREG_SPAN_RE); the label's leading number is the BS day.
        span_m = _GREG_SPAN_RE.search(m.group("body") or "")
        greg_day = int(span_m.group(1)) if span_m else None
        bsd = m.group("bsd")
        y, mo, dd = (int(x) for x in bsd.split("-"))
        if not (_BS_DAY_MIN <= dd <= _BS_DAY_MAX):
            errors.append(f"{bsd}: BS day out of range")
            continue
        if bs_day_from_label is not None and bs_day_from_label != dd:
            errors.append(f"{bsd}: aria-label day {bs_day_from_label} disagrees with href day {dd}")
            continue
        if greg_day is not None and not (_GREG_DAY_MIN <= greg_day <= _GREG_DAY_MAX):
            errors.append(f"{bsd}: Gregorian day {greg_day} out of range")
            continue
        if not events:
            events = [""]           # a date with no named event is still a date
        cells.append({
            "bs_date": f"{y:04d}-{mo:02d}-{dd:02d}",
            "bs_year": y, "bs_month": mo, "bs_day": dd,
            "gregorian_day": greg_day,
            "events": events,
            "holiday_cell": holiday_cell,
            "raw_label": raw_label,
            "source_url": source_url or f"{SOURCE_BASE}{href}",
        })
    if not cells:
        raise CalendarError("no calendar cells found — the page shape may have changed")
    return {
        "bs_year": bs_year if bs_year is not None else cells[0]["bs_year"],
        "bs_month": bs_month if bs_month is not None else cells[0]["bs_month"],
        "cells": cells,
        "errors": errors,
    }


def classify_event(event_name: str, holiday_cell: bool) -> str:
    """Classify a cell CONSERVATIVELY.

    A red/holiday cell is a *candidate*: a named festival is recorded as a
    festival, an unnamed one as a generic observance. Nothing is promoted to
    ``national_public_holiday`` from the calendar marking alone.
    """
    name = _clean(event_name)
    if not name:
        return "other_calendar_event"
    lowered = name.lower()
    # International observances the site lists by name are recognisable as such.
    if lowered in {"international women's day", "world environment day", "labour day",
                   "international labour day", "human rights day", "world aids day"}:
        return "international_observance"
    if holiday_cell:
        return "festival"
    return "religious_or_cultural_observance"


def records_from_page(page: dict[str, Any], *, anchor: dict[str, Any] | None = None,
                      retrieved_at: str | None = None,
                      market_closure: str = "not_independently_verified") -> list[CalendarRecord]:
    """Turn raw cells into classified records.

    ``anchor`` (optional) must be ``{"bs_date": "YYYY-MM-DD", "gregorian_date":
    "YYYY-MM-DD"}`` — a VERIFIED correspondence the caller supplies. When given,
    the Gregorian date of every cell is derived by counting forward/backward in
    days **within the parsed cells only**; a cell whose offset cannot be
    established stays unresolved. Without an anchor every Gregorian date is left
    unresolved rather than guessed.
    """
    if market_closure not in MARKET_CLOSURE_STATUSES:
        raise CalendarError(f"unknown market closure status {market_closure!r}")
    when = retrieved_at or datetime.now(UTC).isoformat(timespec="seconds")
    cells = page.get("cells") or []
    resolved: dict[str, str] = {}
    if anchor:
        from datetime import date as _date
        try:
            a_bs = str(anchor["bs_date"])
            a_greg = _date.fromisoformat(str(anchor["gregorian_date"]))
        except (KeyError, ValueError) as exc:
            raise CalendarError(f"bad anchor: {exc}") from exc
        idx = next((i for i, c in enumerate(cells) if c["bs_date"] == a_bs), None)
        if idx is None:
            raise CalendarError(f"anchor {a_bs} is not on this page")
        for i, c in enumerate(cells):
            resolved[c["bs_date"]] = (a_greg + (i - idx) * _ONE_DAY).isoformat()

    out: list[CalendarRecord] = []
    for c in cells:
        for i, name in enumerate(c["events"]):
            out.append(CalendarRecord(
                bs_date=c["bs_date"], bs_year=c["bs_year"], bs_month=c["bs_month"],
                bs_day=c["bs_day"], gregorian_day=c["gregorian_day"],
                gregorian_date=resolved.get(c["bs_date"]),
                gregorian_status="resolved" if resolved.get(c["bs_date"]) else "unresolved",
                event_name=name, event_index=i,
                holiday_cell=bool(c["holiday_cell"]),
                classification=classify_event(name, bool(c["holiday_cell"])),
                market_closure=market_closure,
                source_url=c.get("source_url", ""), retrieved_at=when,
                raw_label=c.get("raw_label", ""),
            ))
    return out

_ONE_DAY = timedelta(days=1)


def validate_records(records: list[CalendarRecord]) -> list[dict[str, str]]:
    """Report every problem found. Returns ``[{event_id, problem}]`` (empty = OK)."""
    problems: list[dict[str, str]] = []
    seen: dict[str, CalendarRecord] = {}
    for r in records:
        if not (_BS_DAY_MIN <= r.bs_day <= _BS_DAY_MAX):
            problems.append({"event_id": r.event_id, "problem": f"BS day {r.bs_day} out of range"})
        if not (1 <= r.bs_month <= 12):
            problems.append({"event_id": r.event_id, "problem": f"BS month {r.bs_month} out of range"})
        if r.gregorian_day is not None and not (_GREG_DAY_MIN <= r.gregorian_day <= _GREG_DAY_MAX):
            problems.append({"event_id": r.event_id, "problem": "Gregorian day out of range"})
        if r.classification not in CLASSIFICATIONS:
            problems.append({"event_id": r.event_id, "problem": f"unknown classification {r.classification!r}"})
        if r.market_closure not in MARKET_CLOSURE_STATUSES:
            problems.append({"event_id": r.event_id, "problem": f"unknown closure status {r.market_closure!r}"})
        if not r.source_url:
            problems.append({"event_id": r.event_id, "problem": "missing source URL"})
        if (r.gregorian_date and r.gregorian_day is not None
                and int(r.gregorian_date[-2:]) != r.gregorian_day):
            problems.append({
                "event_id": r.event_id,
                "problem": f"Gregorian day mismatch: date says {r.gregorian_date}, cell says {r.gregorian_day}",
            })
        prev = seen.get(r.event_id)
        if prev is not None and (prev.event_name != r.event_name or prev.classification != r.classification):
            problems.append({"event_id": r.event_id, "problem": "contradictory duplicate"})
        seen[r.event_id] = r
    return problems


def merge_records(existing: list[dict[str, Any]], incoming: list[CalendarRecord]) -> dict[str, Any]:
    """Idempotent merge keyed on ``event_id``.

    * A new event is added.
    * An identical event is left alone (``unchanged``).
    * A changed event is updated, but a record whose classification is
      ``unknown`` never overwrites one that is classified.
    """
    by_id: dict[str, dict[str, Any]] = {r["event_id"]: dict(r) for r in existing if r.get("event_id")}
    added = updated = unchanged = 0
    for r in incoming:
        d = r.to_dict()
        cur = by_id.get(d["event_id"])
        if cur is None:
            by_id[d["event_id"]] = d
            added += 1
            continue
        if all(cur.get(k) == d.get(k) for k in ("event_name", "classification", "holiday_cell",
                                                "gregorian_date", "source_url")):
            unchanged += 1
            continue
        if d["classification"] == "unknown" and cur.get("classification") not in (None, "", "unknown"):
            unchanged += 1
            continue
        by_id[d["event_id"]] = d
        updated += 1
    return {"records": sorted(by_id.values(), key=lambda r: (r["bs_date"], r["event_index"])),
            "added": added, "updated": updated, "unchanged": unchanged, "total": len(by_id)}


def resolve_gregorian(records: list[CalendarRecord], *, mapping: Any = None,
                      source: str | None = None) -> dict[str, int]:
    """Fill ``gregorian_date`` / ``gregorian_status`` from the vendored BS<->AD map.

    Returns the outcome counts. A record is only ever marked ``resolved`` when
    the mapping actually contains that exact BS day; everything else stays
    ``unresolved`` and the reason is written into ``notes`` so a consumer can see
    *why* rather than just that it failed.
    """
    from megatool.bs_ad import BsAdError, default_map

    m = mapping or default_map()
    src = source or m.source
    counts = {"resolved": 0, "unresolved": 0, "out_of_range": 0, "invalid_bs_date": 0}
    for r in records:
        try:
            out = m.bs_to_ad(r.bs_year, r.bs_month, r.bs_day)
        except BsAdError as exc:
            r.gregorian_date = None
            r.gregorian_status = "unresolved"
            r.notes = f"{r.notes}; {exc}" if r.notes else str(exc)
            counts["invalid_bs_date"] += 1
            continue
        if out.in_coverage and out.value is not None:
            r.gregorian_date = out.value.isoformat()
            r.gregorian_status = "resolved"
            r.notes = f"{r.notes}; gregorian={out.value.isoformat()} via {src}" if r.notes \
                else f"gregorian={out.value.isoformat()} via {src}"
            counts["resolved"] += 1
        else:
            r.gregorian_date = None
            r.gregorian_status = "unresolved"
            reason = out.note or "outside the mapped range"
            r.notes = f"{r.notes}; unresolved: {reason}" if r.notes else f"unresolved: {reason}"
            counts["out_of_range"] += 1
    return counts


def extraction_report(records: list[dict[str, Any]], *, missing_periods: list[str] | None = None) -> dict[str, Any]:
    """Coverage and classification counts for an extraction run."""
    dates = {r["bs_date"] for r in records}
    red = {r["bs_date"] for r in records if r.get("holiday_cell")}
    classes: dict[str, int] = {}
    closures: dict[str, int] = {}
    for r in records:
        classes[r["classification"]] = classes.get(r["classification"], 0) + 1
        closures[r["market_closure"]] = closures.get(r["market_closure"], 0) + 1
    periods = sorted({f"{r['bs_year']}-{int(r['bs_month']):02d}" for r in records})
    return {
        "distinct_bs_dates": len(dates),
        "event_records": len(records),
        "red_marked_dates": len(red),
        "holidays_classified": sum(v for k, v in classes.items()
                                   if k in ("national_public_holiday", "regional_holiday", "festival")),
        "observances_classified": sum(v for k, v in classes.items()
                                      if k in ("religious_or_cultural_observance", "international_observance")),
        "unverified_records": classes.get("unknown", 0) + closures.get("not_independently_verified", 0),
        "gregorian_resolved": sum(1 for r in records if r.get("gregorian_status") == "resolved"),
        "gregorian_unresolved": sum(1 for r in records if r.get("gregorian_status") != "resolved"),
        "by_classification": dict(sorted(classes.items())),
        "by_market_closure": dict(sorted(closures.items())),
        "periods_covered": periods,
        "first_period": periods[0] if periods else None,
        "last_period": periods[-1] if periods else None,
        "missing_periods": list(missing_periods or []),
    }

# ------------------------------------------------------------------ fetching
#: Pages are cached on disk so a re-run never re-fetches a month it already has.
#: The cache is deliberately NOT committed: it is fetched public data.
def cache_path(cache_dir: Any, bs_year: int, bs_month: int) -> Any:
    from pathlib import Path

    return Path(cache_dir) / f"hp-{bs_year:04d}-{bs_month:02d}.html"  # noqa: E501


def fetch_month(bs_year: int, bs_month: int, *, cache_dir: Any = None,
                timeout: float = 20.0, session: Any = None) -> str:
    """Fetch one BS month page, using the on-disk cache when present.

    Plain HTTPS GET against the documented public page; no cookies, no
    authentication, no attempt to bypass any control.
    """
    if not (1 <= bs_month <= 12):
        raise CalendarError(f"BS month {bs_month} out of range")
    cached = cache_path(cache_dir, bs_year, bs_month) if cache_dir else None
    if cached is not None and cached.is_file():
        text = cached.read_text(encoding="utf-8", errors="replace")
        if "/calendar/" in text:
            return text
    url = f"{SOURCE_BASE}/calendar/{bs_year}/{bs_month}"
    req = None
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={
            "User-Agent": "PRAVAHA-research/0.1 (public calendar import; contact: owner)",
            "Accept": "text/html",
        })
        opener = session or urllib.request.urlopen
        with opener(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        raise CalendarError(f"could not fetch {url}: {exc}") from exc
    if cached is not None:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(text, encoding="utf-8")
    return text


def _month_list(start: str, end: str) -> list[tuple[int, int]]:
    """Inclusive ``["YYYY-MM", "YYYY-MM"]`` -> ``[(bs_year, bs_month), …]``."""
    def parse(v: str) -> tuple[int, int]:
        y, m = str(v).split("-")
        yi, mi = int(y), int(m)
        if not (1 <= mi <= 12):
            raise CalendarError(f"bad BS month in {v!r}")
        return yi, mi

    sy, sm = parse(start)
    ey, em = parse(end)
    if (ey, em) < (sy, sm):
        raise CalendarError("end is before start")
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def extract_range(start: str, end: str, *, cache_dir: Any = None, delay: float = 1.2,
                  timeout: float = 20.0, progress: Any = None,
                  anchor: dict[str, Any] | None = None,
                  market_closure: str = "not_independently_verified",
                  resolve_gregorian_dates: bool = True) -> dict[str, Any]:
    """Extract every BS month in ``[start, end]`` into one record list.

    A month that fails to fetch or parse is recorded in ``failed`` and the run
    continues — one bad month never aborts the whole extraction. Requests are
    spaced by ``delay`` seconds and every page is cached.
    """
    import time as _time

    records: list[CalendarRecord] = []
    failed: list[str] = []
    periods: list[str] = []
    months = _month_list(start, end)
    for i, (y, m) in enumerate(months, start=1):
        key = f"{y:04d}-{m:02d}"
        periods.append(key)
        if progress is not None:
            progress(key, i, len(months))
        try:
            html = fetch_month(y, m, cache_dir=cache_dir, timeout=timeout)
            page = parse_calendar_page(html, source_url=f"{SOURCE_BASE}/calendar/{y}/{m}",
                                       bs_year=y, bs_month=m)
            records.extend(records_from_page(page, anchor=anchor, market_closure=market_closure))
        except CalendarError as exc:
            failed.append(f"{key}: {exc}")
        if delay and i < len(months):
            _time.sleep(delay)
    resolution = None
    if resolve_gregorian_dates:
        resolution = resolve_gregorian(records)
    return {
        "records": records,
        "failed": failed,
        "periods": periods,
        "missing_periods": [f.split(":")[0] for f in failed],
        "resolution": resolution,
    }


def write_dataset(records: list[dict[str, Any]], path: Any, *, report: dict[str, Any] | None = None,
                  generated_at: str | None = None) -> dict[str, Any]:
    """Write the versioned dataset. Existing records are MERGED, not replaced."""
    import json
    from pathlib import Path

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if dest.is_file():
        try:
            prior = json.loads(dest.read_text(encoding="utf-8"))
            existing = prior.get("records") or []
        except (json.JSONDecodeError, AttributeError):
            existing = []
    merged = merge_records(existing, [_dict_to_record(r) for r in records])
    payload = {
        "version": 1,
        "source": SOURCE_BASE,
        "generated_at": generated_at or datetime.now(UTC).isoformat(timespec="seconds"),
        "note": (
            "Hamro Patro public calendar. A red-marked cell is a holiday/event "
            "CANDIDATE, not an official public holiday and not a confirmed NEPSE "
            "closure. Gregorian dates are published by the source as a day of "
            "month; a full Gregorian date is present only when a verified anchor "
            "was supplied."
        ),
        "records": merged["records"],
        "report": report or extraction_report(merged["records"]),
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"path": str(dest), **{k: merged[k] for k in ("added", "updated", "unchanged", "total")}}


def load_dataset(path: Any) -> list[dict[str, Any]]:
    import json
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        return []
    try:
        return (json.loads(p.read_text(encoding="utf-8")).get("records")) or []
    except (json.JSONDecodeError, AttributeError):
        return []


def _dict_to_record(d: dict[str, Any]) -> CalendarRecord:
    """Rehydrate a stored record so ``merge_records`` can compare like for like."""
    fields = {f: d.get(f) for f in CalendarRecord.__dataclass_fields__ if f in d}
    fields.setdefault("event_name", "")
    fields.setdefault("event_index", 0)
    fields.setdefault("bs_date", "")
    fields.setdefault("bs_year", 0)
    fields.setdefault("bs_month", 0)
    fields.setdefault("bs_day", 0)
    fields.setdefault("classification", "unknown")
    fields.setdefault("market_closure", "not_independently_verified")
    fields.setdefault("source_url", "")
    fields.setdefault("retrieved_at", "")
    fields.setdefault("gregorian_status", "unresolved")
    fields.setdefault("holiday_cell", False)
    return CalendarRecord(**fields)

