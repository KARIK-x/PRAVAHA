"""YONEPSE static JSON adapter.

Fetches read-only JSON snapshots published at https://shubhamnpk.github.io/yonepse
and converts them into formats compatible with the existing ingestion loaders.

The upstream repository (MIT-licensed software) compiles these snapshots from
NEPSE's official API, ShareSansar, Merolagani, ShareHub and socrateai. This
module only reads the published JSON; it does not scrape, authenticate, or
reverse-engineer the upstream API.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import time
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

#: YONEPSE publishes its JSON two ways, and they are NOT equally fresh:
#:
#: * the repository's **raw content** (``raw.githubusercontent.com``) is
#:   updated by the scraper's commits and was, when measured, current to the
#:   hour during a trading session (e.g. ``last_checked`` 31 minutes old); and
#: * the **GitHub Pages mirror** (``shubhamnpk.github.io``) is CDN-cached and
#:   was observed serving a copy **~4 days stale** while the repository itself
#:   kept updating.
#:
#: The adapter reads raw first and falls back to Pages only when raw is
#: unreachable. Either way the payload's own timestamps drive the freshness
#: label (see ``megatool.live``), so a stale fallback can never be presented as
#: live - it is simply labelled with its real age.
#:
#: The upstream automations occasionally land a **merge-conflict commit** (git
#: markers instead of JSON) on ``main``. When that happens the fresh data still
#: exists at the commits *below* the broken merge, so the adapter walks back
#: through recent commits and uses the newest one that parses. Conflict markers
#: are never repaired into data.
_RAW_ROOT = "https://raw.githubusercontent.com/shubhamnpk/yonepse"
GITHUB_API = "https://api.github.com/repos/shubhamnpk/yonepse"

RAW_BASE_URL = f"{_RAW_ROOT}/main"
PAGES_BASE_URL = "https://shubhamnpk.github.io/yonepse"

#: The default base every fetcher uses (raw content, the fresh copy).
BASE_URL = RAW_BASE_URL

#: Bases tried in order. Kept explicit so a stale source is never the only one.
BASE_URLS = (RAW_BASE_URL, PAGES_BASE_URL)

#: Paths relative to BASE_URL.
PATH_SECURITIES = "data/other/securities.json"
PATH_SECTOR_CODES = "data/other/sector_codes.json"
PATH_FINANCIALS = "data/company/financials.json"
PATH_DISCLOSURES = "data/notify/disclosures.json"
PATH_EXCHANGE_MESSAGES = "data/notify/exchange_messages.json"
PATH_NOTICES = "data/notify/notices.json"

#: Near-live market snapshots.  ``market/live.json`` is a per-symbol quote
#: board (ltp/high/low/volume/last_updated) and ``market/status.json`` records
#: whether the exchange is open plus the publisher's last check time.  These are
#: the only YONEPSE paths that carry price data; the adapter historically
#: exposed none of them, which is why the application never received them.
PATH_MARKET_LIVE = "data/market/live.json"
PATH_MARKET_STATUS = "data/market/status.json"
PATH_MARKET_INDICES = "data/market/indices.json"

#: The remaining published market files.  These carry the rest of the
#: exchange's own session dataset: the session totals board, the top-mover
#: rankings, the 17 sector index definitions and the per-day session history.
#: Like the three files above they are read as *published* content - the
#: collector never synthesises anything these files do not state.
PATH_MARKET_SUMMARY = "data/market/summary.json"
PATH_MARKET_TOP_STOCKS = "data/market/top_stocks.json"
PATH_MARKET_SECTOR_INDICES = "data/market/sector_indices.json"
PATH_MARKET_HISTORY = "data/market/history.json"

#: The market files the collector reads beyond the live trio, in one bundle.
MARKET_EXTRA_PATHS = (
    PATH_MARKET_SUMMARY,
    PATH_MARKET_TOP_STOCKS,
    PATH_MARKET_SECTOR_INDICES,
    PATH_MARKET_HISTORY,
)

#: YONEPSE timestamps (``last_updated``) are Nepal local time, UTC+05:45.
NPT_OFFSET_MINUTES = 5 * 60 + 45


class YonepseError(Exception):
    """Something went wrong fetching or parsing a YONEPSE snapshot."""


def utcnow() -> datetime:
    return datetime.now(UTC)


_MISS = object()


def _fetch_json_verbose(path: str, timeout: float = 30.0) -> tuple[Any, str]:
    """Fetch a snapshot, returning ``(payload, base_url_used)``.

    Tries ``main`` first; only if it is unreadable (a broken merge commit, or a
    transient error) does it walk back through recent commits, and finally the
    cache-prone GitHub-Pages mirror. The base that answered is returned so a
    fallback can be stated rather than silently treated as fresh raw content.
    """
    errors: list[str] = []

    def attempt(url: str) -> Any:
        try:
            with urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - the caller tries the next ref
            errors.append(f"{url}: {exc}")
            return _MISS

    payload = attempt(f"{RAW_BASE_URL}/{path}")
    if payload is not _MISS:
        return payload, RAW_BASE_URL
    # main was unreadable: try the commits below it (no API call on the happy path).
    with contextlib.suppress(Exception):
        for sha in _recent_commit_shas():
            payload = attempt(f"{_RAW_ROOT}/{sha}/{path}")
            if payload is not _MISS:
                return payload, f"{_RAW_ROOT}/{sha}"
    payload = attempt(f"{PAGES_BASE_URL}/{path}")
    if payload is not _MISS:
        return payload, PAGES_BASE_URL
    raise YonepseError("failed to fetch " + "; ".join(errors))


def _fetch_json(path: str, timeout: float = 30.0) -> Any:
    """Fetch a snapshot, preferring the fresh raw content over the CDN mirror."""
    return _fetch_json_verbose(path, timeout)[0]


_COMMIT_CACHE: dict[str, Any] = {"at": 0.0, "shas": []}


def _recent_commit_shas(limit: int = 4, timeout: float = 15.0) -> list[str]:
    """Recent commit SHAs, cached, for walking back past a broken ``main``.

    Uses the public GitHub API (no token, no auth). Failures degrade to an empty
    list, which simply means "no commit fallback" - never an error surfaced to
    the caller for what is only an optimisation.
    """
    now = time.monotonic()
    cached = _COMMIT_CACHE["shas"]
    if cached and now - float(_COMMIT_CACHE["at"]) < 600.0:
        return list(cached)
    shas: list[str] = []
    try:
        with urlopen(f"{GITHUB_API}/commits?per_page={limit}", timeout=timeout) as resp:
            for item in json.loads(resp.read().decode("utf-8")) or []:
                sha = item.get("sha") if isinstance(item, dict) else None
                if sha:
                    shas.append(str(sha))
    except Exception:  # noqa: BLE001 - the fallback is optional
        shas = []
    _COMMIT_CACHE.update(at=now, shas=shas)
    return list(shas)


def _newest_quote_stamp(records: Any) -> str:
    """Newest ``last_updated`` string in a quote board (``""`` if none)."""
    stamps = [
        str(r.get("last_updated"))
        for r in (records or [])
        if isinstance(r, dict) and r.get("last_updated")
    ]
    return max(stamps) if stamps else ""


_REF_CACHE: dict[str, Any] = {"at": 0.0, "ref": None}


def _market_ref(timeout: float = 20.0) -> str | None:
    """Pick the ref whose market quote board is newest and parseable.

    ``main`` wins when healthy. When it is a broken merge commit, the commits
    below it are tried and the one with the **newest quotes** is chosen - not
    merely the first that parses, because an older commit can parse while
    carrying older prices. Returns ``None`` when nothing parses (the caller then
    falls back to the Pages mirror).
    """
    now = time.monotonic()
    if _REF_CACHE["ref"] and now - float(_REF_CACHE["at"]) < 240.0:
        return str(_REF_CACHE["ref"])
    best_ref: str | None = None
    best_score = ""
    for ref in ["main", *_recent_commit_shas()]:
        try:
            with urlopen(f"{_RAW_ROOT}/{ref}/{PATH_MARKET_LIVE}", timeout=timeout) as resp:
                records = json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - try the next ref
            continue
        score = _newest_quote_stamp(records)
        if score and score > best_score:
            best_ref, best_score = ref, score
    _REF_CACHE.update(at=now, ref=best_ref)
    return best_ref


def fetch_securities() -> list[dict[str, Any]]:
    return _fetch_json(PATH_SECURITIES)


def fetch_sector_codes() -> dict[str, list[dict[str, str]]]:
    return _fetch_json(PATH_SECTOR_CODES)


def fetch_financials() -> list[dict[str, Any]]:
    return _fetch_json(PATH_FINANCIALS)


def fetch_disclosures() -> list[dict[str, Any]]:
    return _fetch_json(PATH_DISCLOSURES)


def fetch_exchange_messages() -> list[dict[str, Any]]:
    return _fetch_json(PATH_EXCHANGE_MESSAGES)


def fetch_notices() -> dict[str, Any]:
    return _fetch_json(PATH_NOTICES)


def fetch_market_live() -> list[dict[str, Any]]:
    """Fetch the near-live per-symbol quote board (``market/live.json``)."""
    return _fetch_json(PATH_MARKET_LIVE)


def fetch_market_extras(
    paths: tuple[str, ...] = MARKET_EXTRA_PATHS, timeout: float = 30.0
) -> tuple[dict[str, Any], dict[str, str]]:
    """Fetch the remaining market files beside the live quote trio.

    Uses the same newest-parseable-ref logic as :func:`fetch_market_snapshot`
    (one commit decided for the whole bundle), so a broken ``main`` does not
    break only half the session dataset. Resolves one ref, then reads every
    file at that ref; a file that still fails there is retried at the branch
    tip and, failing that, recorded in ``errors`` rather than fabricated.

    Returns ``(files, errors)`` where ``files[p] = (payload, origin_url)``.
    """
    files: dict[str, Any] = {}
    errors: dict[str, str] = {}
    ref = _market_ref(timeout=timeout)
    for path in paths:
        payload = None
        where = ""
        if ref:
            url = f"{_RAW_ROOT}/{ref}/{path}"
            try:
                with urlopen(url, timeout=timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                where = url
            except Exception:  # noqa: BLE001 - per-file fallback below
                payload = None
        if payload is None:
            try:
                payload, where = _fetch_json_verbose(path, timeout=timeout)
            except YonepseError as exc:
                errors[path] = str(exc)
                continue
        files[path] = (payload, where)
    return files, errors


def fetch_market_summary() -> list[dict[str, Any]]:
    """Fetch the session totals board (``market/summary.json``)."""
    return _fetch_json(PATH_MARKET_SUMMARY)


def fetch_top_stocks() -> dict[str, Any]:
    """Fetch the top-mover ranking lists (``market/top_stocks.json``)."""
    return _fetch_json(PATH_MARKET_TOP_STOCKS)


def fetch_sector_indices() -> list[dict[str, Any]]:
    """Fetch the sector index definitions (``market/sector_indices.json``)."""
    return _fetch_json(PATH_MARKET_SECTOR_INDICES)


def fetch_market_history() -> list[dict[str, Any]]:
    """Fetch the per-day session totals history (``market/history.json``)."""
    return _fetch_json(PATH_MARKET_HISTORY)


def fetch_market_status() -> dict[str, Any]:
    """Fetch the exchange open/closed flag and the publisher's last check."""
    return _fetch_json(PATH_MARKET_STATUS)


def fetch_market_indices() -> list[dict[str, Any]]:
    """Fetch the main and sector index snapshot (``market/indices.json``)."""
    return _fetch_json(PATH_MARKET_INDICES)


def fetch_market_snapshot() -> dict[str, Any]:
    """Fetch the whole market snapshot from the freshest readable ref.

    Returns ``{"status", "live", "indices", "origin"}``. When ``main`` is a
    broken merge commit the newest parseable commit below it is used, so the
    application keeps receiving same-day observations instead of falling all the
    way back to the cache-prone Pages mirror. ``origin`` states which ref
    actually answered.
    """
    ref = _market_ref()
    if ref is None:
        # Nothing in the repository parsed; use the mirror and say so.
        status, origin = _fetch_json_verbose(PATH_MARKET_STATUS)
        live, _ = _fetch_json_verbose(PATH_MARKET_LIVE)
        try:
            indices, _ = _fetch_json_verbose(PATH_MARKET_INDICES)
        except YonepseError:
            indices = []
        return {"status": status, "live": live, "indices": indices, "origin": origin}

    def at(path: str) -> Any:
        url = f"{_RAW_ROOT}/{ref}/{path}"
        with urlopen(url, timeout=30.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    status = at(PATH_MARKET_STATUS)
    live = at(PATH_MARKET_LIVE)
    try:
        indices = at(PATH_MARKET_INDICES)
    except Exception:  # noqa: BLE001 - indices are optional
        indices = []
    return {"status": status, "live": live, "indices": indices, "origin": f"{_RAW_ROOT}/{ref}"}


# --------------------------------------------------------------------- normalize

_STATUS_MAP = {
    "A": "ACTIVE",
    "D": "DELISTED",
    "S": "SUSPENDED",
}

_INSTRUMENT_MAP = {
    "Equity": "ordinary",
    "Non-Convertible Debentures": "debenture",
    "Mutual Funds": "mutual_fund",
    "Preference Shares": "preference",
}


def _map_status(value: str | None) -> str:
    if not value:
        return "UNKNOWN"
    return _STATUS_MAP.get(value.upper(), value.upper())


def _map_instrument(value: str | None) -> str:
    if not value:
        return ""
    return _INSTRUMENT_MAP.get(value, value.lower().replace(" ", "_"))


def securities_to_metadata_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert YONEPSE securities records into metadata-dry-run rows.

    Output columns: symbol, name, instrument_type, sector, status, source,
    sector_source, sector_retrieved_at, sector_observed_date.
    """
    retrieved = utcnow().isoformat(timespec="seconds")
    observed = date.today().isoformat()
    rows = []
    for rec in records:
        symbol = (rec.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        sector = (rec.get("sectorName") or "").strip()
        rows.append(
            {
                "symbol": symbol,
                "name": (rec.get("companyName") or "").strip(),
                "instrument_type": _map_instrument(rec.get("instrumentType")),
                "sector": sector,
                "status": _map_status(rec.get("status")),
                "source": "yonepse/securities.json",
                "sector_source": "yonepse/securities.json",
                "sector_retrieved_at": retrieved,
                "sector_observed_date": observed,
            }
        )
    return rows


def securities_to_sector_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert YONEPSE securities records into the sector-loader CSV shape."""
    retrieved = utcnow().isoformat(timespec="seconds")
    observed = date.today().isoformat()
    rows = []
    for rec in records:
        symbol = (rec.get("symbol") or "").strip().upper()
        sector = (rec.get("sectorName") or "").strip()
        if symbol and sector:
            rows.append(
                {
                    "symbol": symbol,
                    "sector": sector,
                    "source": "yonepse/securities.json",
                    "retrieved_at": retrieved,
                    "observed_date": observed,
                }
            )
    return rows


# ----------------------------------------------------------------- fundamentals

#: Map YONEPSE report field to fundamentals.py field/unit.  Values that are not
#: in KNOWN_FIELDS are still emitted with an explicit unit so the loader can
#: decide what to keep.
_FINANCIAL_FIELDS = {
    "pe": ("pe", "ratio"),
    "eps": ("eps", "NPR"),
    "paid_up_capital": ("paid_up_capital", "NPR"),
    "profit": ("profit", "NPR"),
    "net_worth_per_share": ("net_worth_per_share", "NPR"),
}

#: The numeric fields that identify one distinct filing of a reporting period.
_FILING_FIELDS = ("pe", "eps", "paid_up_capital", "profit", "net_worth_per_share")


def _max_submitted(report: dict[str, Any]) -> str:
    """Latest document ``submitted_date`` in a report, or ``""``."""
    dates = sorted(
        (d.get("submitted_date") or "").strip()
        for d in (report.get("documents") or [])
        if (d.get("submitted_date") or "").strip()
    )
    return dates[-1] if dates else ""


def _filed_at(report: dict[str, Any]) -> str:
    """The date this filing actually became public — or ``""`` if unknown.

    This is the **availability date** and the only exact date the snapshot
    carries for a report. Measured on the real snapshot: 6,902 of 6,908 reports
    supply it, and it is the date a document was submitted, so the figure was
    demonstrably knowable from this date onward. Using it (rather than a
    calendar conversion of the Nepali fiscal year) is what keeps a backtest
    from using a figure before it existed.
    """
    return _max_submitted(report)


def _filing_values(report: dict[str, Any]) -> tuple:
    return tuple((f, report.get(f)) for f in _FILING_FIELDS)


def recover_filing_dates(
    records: list[dict[str, Any]],
) -> dict[tuple[str, tuple], str]:
    """Recover ``filed_at`` for undated reports that have an identical dated twin.

    Measured on the real snapshot: a handful of report objects carry no
    ``documents`` list, so their filing date is unknown and the loader leaves
    ``period_end`` empty. Each such report is a duplicate export of a report
    that *does* carry a document: the two share every figure and the same
    fiscal year / quarter / type.

    This recovers a date **only** from that exact evidence — a same-symbol
    report whose ``_filing_values`` are identical and whose submitted dates are
    unambiguous (a single distinct date). Anything weaker (no twin, or two
    different dates) is left unknown, because a guessed filing date would let a
    backtest use a figure before it was public.
    """
    # First pass: identical-figure -> set of submitted dates, from dated reports.
    dated: dict[tuple[str, tuple], set[str]] = {}
    for rec in records:
        symbol = (rec.get("symbol") or "").strip().upper()
        for report in rec.get("reports") or []:
            submitted = _max_submitted(report)
            if not submitted:
                continue
            dated.setdefault((symbol, _filing_values(report)), set()).add(submitted)

    recovered: dict[tuple[str, tuple], str] = {}
    for rec in records:
        symbol = (rec.get("symbol") or "").strip().upper()
        for report in rec.get("reports") or []:
            if _max_submitted(report):
                continue
            candidates = dated.get((symbol, _filing_values(report)), set())
            if len(candidates) == 1:
                recovered[(symbol, _filing_values(report))] = next(iter(candidates))
    return recovered


def dedupe_financial_reports(
    records: list[dict[str, Any]],
    recovered: dict[tuple[str, tuple], str] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    """Collapse filings that collide on the loader's own identity.

    ``megatool.fundamentals`` refuses to import two different values for the
    same ``(symbol, field, period_end, source)``: letting one silently
    overwrite the other is exactly the failure it exists to stop. The YONEPSE
    snapshot publishes many reporting periods more than once per symbol, so a
    straight conversion is rejected wholesale.

    **Grouping.** Reports are grouped by ``(symbol, filing date)`` using the
    date the document was submitted — *not* by the source's own labels, and not
    by a calendar conversion of the Nepali fiscal year. This matters for two
    reasons. First, the source labels the same fiscal year twice
    (``Annual Report`` and ``Fourth Quarter``), so grouping by label collides.
    Second, an FY-to-Gregorian conversion is unreliable: measured on the real
    snapshot it implies 3,910 filings predating the period they report, so it
    cannot be the basis of a date.

    ``recovered`` (from :func:`recover_filing_dates`) supplies a filing date
    for an export that carries no document but is an exact duplicate of a dated
    twin. When provided, such an export joins its twin's group and is collapsed
    with it, so the same period is never emitted twice — which the loader would
    reject. The representative kept is the one that actually carries a document
    date, preserving its source reference.

    **Resolution rule (stated, deterministic, no invented values).**

    1. Filings whose numeric fields are *identical* are collapsed — nothing is
       lost, and the count is reported.
    2. Conflicting filings resolve by **complete-period figure beats
       quarterly**, then **latest filing wins** (most recent document
       ``submitted_date``), then most attached documents, then upstream order.
       An annual figure describing the whole fiscal year is kept over the
       quarter-only figure for the same FY-closing date, because they measure
       different spans and the loader can store only one per period.

    The winner and the collapsed count are recorded in the emitted ``notes``
    so every collapse stays auditable. Values are never carried across periods,
    symbols or fields.
    """
    stats = {
        "symbols": 0,
        "reports_in": 0,
        "reports_out": 0,
        "exact_duplicates_dropped": 0,
        "conflicting_periods_resolved": 0,
        "symbols_with_conflicts": 0,
    }
    out: dict[str, list[dict[str, Any]]] = {}
    recovered = recovered or {}
    for rec in records:
        symbol = (rec.get("symbol") or "").strip().upper()
        reports = list(rec.get("reports") or [])
        stats["reports_in"] += len(reports)

        groups: dict[Any, list[tuple[int, dict[str, Any]]]] = {}
        for idx, rep in enumerate(reports):
            # Group on the FILING date, not on a calendar conversion of the
            # Nepali fiscal year. Converting FY + quarter to a Gregorian date
            # is unreliable (verified: it produces impossible "filed before the
            # period ended" lags), whereas every filing supplies the date it
            # was actually submitted, which is when the figure became public.
            # An export with no document date but an identical dated twin
            # shares that twin's filing date, so it groups with the twin and
            # collapses as an exact duplicate instead of emitting a second row
            # for the same period (which the fundamentals loader rejects).
            key = _filed_at(rep) or recovered.get((symbol, _filing_values(rep)), "")
            groups.setdefault(key, []).append((idx, rep))

        kept: list[dict[str, Any]] = []
        symbol_had_conflict = False
        for _period_end, items in groups.items():
            items.sort(key=lambda p: p[0])
            distinct: dict[tuple, list[tuple[int, dict[str, Any]]]] = {}
            for idx, rep in items:
                distinct.setdefault(_filing_values(rep), []).append((idx, rep))

            dropped = len(items) - 1
            if len(distinct) == 1:
                # Prefer a representative that carries a document date so a
                # collapsed group keeps its source reference; when every item
                # is dated this still falls back to upstream order, unchanged.
                winner = max(items, key=lambda p: (bool(_max_submitted(p[1])), p[0]))[1]
                stats["exact_duplicates_dropped"] += dropped
            else:
                flat = [item for group in distinct.values() for item in group]
                winner = sorted(
                    flat,
                    key=lambda p: (
                        # Ascending sort + last element: the complete-period
                        # (annual) figure must outrank a quarter-only one, so
                        # it carries the LARGER key.
                        1 if (p[1].get("type") or "").lower().startswith("annual") else 0,
                        _max_submitted(p[1]),
                        len(p[1].get("documents") or []),
                        p[0],
                    ),
                )[-1][1]
                stats["conflicting_periods_resolved"] += 1
                symbol_had_conflict = True

            w = dict(winner)
            if dropped:
                note = f"{dropped} duplicate filing(s) collapsed"
                if len(distinct) > 1:
                    note += (
                        "; conflict resolved by "
                        f"period-supremacy+latest-filing "
                        f"({(winner.get('type') or 'unnamed')}; "
                        f"max submitted_date={_max_submitted(winner) or 'n/a'})"
                    )
                else:
                    note += "; values identical"
                w["_collapsed_note"] = note
            kept.append(w)

        stats["reports_out"] += len(kept)
        if symbol_had_conflict:
            stats["symbols_with_conflicts"] += 1
        out[symbol] = kept
    stats["symbols"] = len(out)
    return out, stats


def _fy_period_end(fy: str, quarter: str | None = None) -> date | None:
    """Best-effort Gregorian period-end from YONEPSE FY/quarter labels.

    YONEPSE reports Nepali fiscal years (e.g. '2025-2026' = FY 2082/83).  The
    exact conversion requires the Nepali calendar; here we map to the rough
    Gregorian midpoint of the quarter, which is good enough for staleness
    screening and is documented as an approximation.
    """
    try:
        start_year = int(fy.split("-")[0])
    except Exception:
        return None
    # Nepali FY starts in mid-July of the Gregorian start_year.
    base = date(start_year, 7, 15)
    if not quarter:
        # Annual report: end of FY is roughly mid-July of the next Gregorian year.
        return date(start_year + 1, 7, 15)
    qmap = {
        "First Quarter": (0, 3),  # ~mid-Oct
        "Second Quarter": (0, 6),  # ~mid-Jan
        "Third Quarter": (0, 9),  # ~mid-Apr
        "Fourth Quarter": (1, 0),  # ~mid-July
    }
    dy, dm = qmap.get(quarter, (0, 3))
    try:
        return date(start_year + dy, base.month, base.day) + timedelta(days=dm * 30)
    except Exception:
        return None


def financials_to_fundamental_rows(
    records: list[dict[str, Any]],
    dedupe: bool = True,
) -> list[dict[str, Any]]:
    """Flatten YONEPSE financial reports into fundamentals-loader rows.

    ``dedupe=True`` (default) applies :func:`dedupe_financial_reports` so the
    output can actually be loaded: without it the loader refuses the whole file
    because the snapshot repeats many reporting periods.
    """
    # Computed from the original records so an undated report can still be
    # matched to its dated twin by identical figures (dedupe may collapse them).
    recovered = recover_filing_dates(records)

    if dedupe:
        deduped, _stats = dedupe_financial_reports(records, recovered=recovered)
        records = [{"symbol": sym, "reports": reps} for sym, reps in deduped.items()]

    rows: list[dict[str, Any]] = []
    source = "yonepse/financials.json"
    retrieved = utcnow().isoformat(timespec="seconds")
    for rec in records:
        symbol = (rec.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        for report in rec.get("reports") or []:
            extra = report.get("_collapsed_note", "")
            quarter = report.get("quarter")
            fy = report.get("fy") or ""
            # period_label preserves the source's own words verbatim, so the
            # reported period is never lost.
            period_label = report.get("type", "")
            if quarter:
                period_label = f"{quarter} {fy}".strip()
            if fy:
                period_label = f"{period_label} (Nepali FY {fy})".strip()

            docs = report.get("documents") or []
            filed_at = _filed_at(report)
            filed_at_recovered = False
            if not filed_at:
                filed_at = recovered.get((symbol, _filing_values(report)), "")
                filed_at_recovered = bool(filed_at)
            source_ref = docs[0].get("path", "") if docs else ""

            # ``period_end`` is the date the figure became public. It is the
            # only exact date the source supplies (6,902 of 6,908 reports carry
            # it) and it is the date that governs whether a backtest may use the
            # figure at all. A filing with no document date leaves period_end
            # empty rather than being back-dated into an invented period.
            period_end = filed_at

            for ykey, (field, unit) in _FINANCIAL_FIELDS.items():
                value = report.get(ykey)
                if value is None or value == "":
                    continue
                try:
                    fvalue = float(value)
                except (TypeError, ValueError):
                    continue
                note = f"yonepse field={ykey}; fy={fy}"
                if filed_at and filed_at_recovered:
                    note += (
                        f"; filed_at={filed_at} (recovered from an identical "
                        "dated twin report; this export carried no document date)"
                    )
                elif filed_at:
                    note += f"; filed_at={filed_at}"
                else:
                    note += "; no filed_at: vintage is unknown, do not use point-in-time"
                if extra:
                    note += f"; {extra}"
                rows.append(
                    {
                        "symbol": symbol,
                        "field": field,
                        "value": fvalue,
                        "unit": unit,
                        "period_end": period_end,
                        "period_label": period_label,
                        "source": source,
                        "source_ref": source_ref,
                        "verification": "extracted",
                        "notes": note,
                        "retrieved_at": retrieved,
                        "filed_at": filed_at,
                    }
                )
    return rows


def point_in_time_available(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Point-in-time availability summary for converted fundamentals rows.

    Returns the share of rows carrying a usable ``filed_at`` (the date the
    figure became public) and the coverage per field. A backtest can then filter
    on ``filed_at <= backtest_date`` and never use a figure before it existed.
    """
    total = len(rows)
    dated = [r for r in rows if r.get("filed_at")]
    by_field: dict[str, dict[str, int]] = {}
    for r in rows:
        entry = by_field.setdefault(r["field"], {"total": 0, "with_filed_at": 0})
        entry["total"] += 1
        if r.get("filed_at"):
            entry["with_filed_at"] += 1
    return {
        "rows": total,
        "rows_with_filed_at": len(dated),
        "coverage_pct": round(len(dated) / total * 100, 2) if total else 0.0,
        "earliest": min((r["filed_at"] for r in dated), default=None),
        "latest": max((r["filed_at"] for r in dated), default=None),
        "by_field": by_field,
        "usage": (
            "Filter on filed_at <= backtest_date to avoid look-ahead bias; "
            "period_end is set to the filing date, so a stale figure is one "
            "whose filing date is old, not one whose fiscal year is old."
        ),
    }


# ------------------------------------------------------------------------ news


def _news_rows_from_list(
    items: list[dict[str, Any]], publisher_default: str
) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        body = (item.get("body") or "").strip()
        published = item.get("publishedAt") or ""
        if isinstance(published, str):
            published = published.replace("Z", "+00:00")
        sym = (item.get("symbol") or "").strip().upper()
        rows.append(
            {
                "title": title,
                "summary": body,
                "url": "",
                "source": item.get("source") or publisher_default,
                "published_at": published,
                "symbols": sym,
            }
        )
    return rows


def notices_without_publication_date(
    notices: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Report general notices that cannot become news items, and why.

    The YONEPSE general-notice snapshot carries only ``expiresAt`` — an expiry,
    *not* a publication date. Emitting it as ``published_at`` would hand the
    pipeline a fake date, so those items are reported as unusable instead of
    being dated by something they are not.
    """
    if not notices or not isinstance(notices.get("general"), list):
        return []
    out: list[dict[str, Any]] = []
    for item in notices["general"]:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        if not (item.get("publishedAt") or item.get("published_at")):
            out.append(
                {
                    "id": item.get("id"),
                    "title": title[:120],
                    "reason": (
                        "snapshot has no publication date (expiresAt is an expiry, "
                        "not a publication date); not dated, not imported"
                    ),
                }
            )
    return out


def notify_to_news_rows(
    disclosures: list[dict[str, Any]] | None = None,
    exchange_messages: list[dict[str, Any]] | None = None,
    notices: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convert YONEPSE notify files into news-importer CSV rows.

    Disclosures and exchange messages are emitted verbatim (title, body,
    publisher, symbol). General notices are deliberately excluded — the
    snapshot gives them no publication date (see
    :func:`notices_without_publication_date`), and an expiry date must never be
    substituted for one.

    A disclosure/message that itself carries no ``publishedAt`` is emitted with
    an empty timestamp rather than a fabricated one; the news importer rejects
    such a row (``published_at`` is required) and reports it with a reason, so
    it never reaches the store. Measured on the real snapshot: 334 dated items
    import and 18 undated rows are skipped.
    """
    rows: list[dict[str, Any]] = []
    if disclosures:
        rows.extend(_news_rows_from_list(disclosures, "yonepse/disclosures"))
    if exchange_messages:
        rows.extend(_news_rows_from_list(exchange_messages, "yonepse/exchange_messages"))
    return rows


# ----------------------------------------------------------------- market quotes


def _finite(value: Any) -> float | None:
    """Coerce to a finite float, or ``None`` for missing/non-finite input."""
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / ±inf
        return None
    return f


def _finite_int(value: Any) -> int | None:
    f = _finite(value)
    if f is None or f < 0:
        return None
    return int(f)


def _parse_quote_ts(value: Any) -> datetime | None:
    """Parse a YONEPSE ``last_updated`` timestamp (naive Nepal local time)."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def market_live_to_quote_rows(
    records: list[dict[str, Any]],
    *,
    retrieved_at: datetime | None = None,
    source: str = "yonepse/market/live.json",
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Convert ``market/live.json`` records into validated quote rows.

    Returns ``(rows, stats)``.  The conversion never invents a value:

    * a record with no symbol is rejected (``no_symbol``);
    * a record with no parseable ``last_updated`` is rejected
      (``missing_timestamp``) because freshness cannot be asserted without it;
    * a missing LTP is stored as ``NULL`` with ``validation_status='missing'`` —
      *unavailable* is not the same as a valid ``0``;
    * a non-finite or non-positive LTP is stored as ``NULL`` with
      ``validation_status='invalid'`` (a trade price of ``0`` is not a price);
    * ``high < low`` is marked ``suspect``.

    Every emitted row carries the source ``last_updated`` and this run's
    ``retrieved_at`` so an auditor can separate source publication time from
    observation time.
    """
    stamp = (retrieved_at or utcnow()).replace(tzinfo=None)
    stats = {
        "records_in": 0,
        "rows_out": 0,
        "no_symbol": 0,
        "missing_timestamp": 0,
        "missing_ltp": 0,
        "invalid_ltp": 0,
        "suspect": 0,
    }
    rows: list[dict[str, Any]] = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        stats["records_in"] += 1
        symbol = str(rec.get("symbol") or "").strip().upper()
        if not symbol:
            stats["no_symbol"] += 1
            continue
        ts = _parse_quote_ts(rec.get("last_updated"))
        if ts is None:
            stats["missing_timestamp"] += 1
            continue

        ltp = _finite(rec.get("ltp"))
        status = "valid"
        if ltp is None:
            status = "missing"
            stats["missing_ltp"] += 1
        elif ltp <= 0:
            status = "invalid"
            ltp = None
            stats["invalid_ltp"] += 1

        low = _finite(rec.get("low"))
        high = _finite(rec.get("high"))
        if high is not None and low is not None and high < low:
            if status == "valid":
                status = "suspect"
            stats["suspect"] += 1

        rows.append(
            {
                "symbol": symbol,
                "quote_date": ts.date().isoformat(),
                "ltp": ltp,
                "previous_close": _finite(rec.get("previous_close")),
                "high": high,
                "low": low,
                "change": _finite(rec.get("change")),
                "percent_change": _finite(rec.get("percent_change")),
                "volume": _finite_int(rec.get("volume")),
                "turnover": _finite(rec.get("turnover")),
                "trades": _finite_int(rec.get("trades")),
                "market_cap": _finite(rec.get("market_cap")),
                "name": (rec.get("name") or "").strip() or None,
                "source": source,
                "source_updated_at": ts.isoformat(timespec="seconds"),
                "retrieved_at": stamp.isoformat(timespec="seconds"),
                "validation_status": status,
            }
        )
    stats["rows_out"] = len(rows)
    return rows, stats


def _is_npt_market_open(now_utc: datetime | None = None) -> bool:
    """Whether Nepal Trading hours are currently active, in Nepal time.

    NEPSE runs Monday-Friday (ISO weekday < 6) 11:00-15:00 NPT. This is local
    wall-clock inference only, so it is only used when the publisher's own
    status poll is stale - never as a substitute for a fresh poll.
    """
    now = (now_utc or utcnow()).astimezone(timezone(timedelta(hours=5, minutes=45)))
    return now.weekday() < 5 and 11 * 60 <= now.hour * 60 + now.minute < 15 * 60


def market_status_summary(
    status: dict[str, Any] | None = None, *, now: datetime | None = None
) -> dict[str, Any]:
    """Describe a ``market/status.json`` snapshot without asserting liveness.

    ``is_open`` is the exchange's *published* flag, passed through untouched: the
    app does not second-guess the publisher, because that flag is a claim about
    the exchange's state, not ours to assert. Only the staleness of the *poll*
    is reported separately, so a stale poll is visible without pretending the app
    knows better than the publisher.
    """
    status = status or {}
    checked = status.get("last_checked")
    checked_dt = _parse_quote_ts(checked) if isinstance(checked, str) else None
    now_value = now or utcnow()
    age = None
    if checked_dt is not None:
        age = (now_value - checked_dt.astimezone(UTC)).total_seconds()
    stale = age is None or age > 600
    extra = ""
    if stale and age is not None:
        extra = f" (poll is stale: {round(age)} s old)"
    return {
        "is_open": status.get("is_open"),
        "is_open_source": "upstream (stale)" if stale else "upstream",
        "status_poll_age_seconds": None if age is None else round(age, 1),
        "status_poll_stale": stale,
        "last_checked": checked,
        "source": "yonepse/market/status.json",
        "note": (
            "is_open is the exchange's flag as published; last_checked is when "
            "the publisher last polled it, not the time of this request." + extra
        ),
    }


# --------------------------------------------------------------------- CSV I/O


def write_csv(rows: list[dict[str, Any]], path: str | Path, fieldnames: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def metadata_csv(rows: list[dict[str, Any]]) -> str:
    """Render metadata rows as a CSV string."""
    fieldnames = [
        "symbol",
        "name",
        "instrument_type",
        "sector",
        "status",
        "source",
        "sector_source",
        "sector_retrieved_at",
        "sector_observed_date",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


def sector_csv(rows: list[dict[str, Any]]) -> str:
    fieldnames = ["symbol", "sector", "source", "retrieved_at", "observed_date"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


def fundamentals_csv(rows: list[dict[str, Any]]) -> str:
    fieldnames = [
        "symbol",
        "field",
        "value",
        "unit",
        "period_end",
        "period_label",
        "source",
        "source_ref",
        "verification",
        "notes",
        "retrieved_at",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


def news_csv(rows: list[dict[str, Any]]) -> str:
    fieldnames = ["title", "summary", "url", "source", "published_at", "symbols"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()
