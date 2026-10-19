"""Focused tests for the YONEPSE adapter.

All network access is mocked; tests exercise the conversion functions with
synthetic JSON fixtures.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from megatool import fundamentals
from megatool.datasources import yonepse

#: Real downloaded snapshots, when present, let the rules be checked against
#: actual data rather than only against fixtures.
RAW = Path("data/review/source_probe_2026-10-15")


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _mock_json(payload: dict | list) -> _FakeResponse:
    return _FakeResponse(json.dumps(payload).encode("utf-8"))


SECURITIES_FIXTURE = [
    {
        "id": 1,
        "companyName": "Test Bank Ltd.",
        "symbol": "TEST",
        "securityName": "Test Bank",
        "status": "A",
        "companyEmail": "",
        "website": "",
        "sectorName": "Commercial Banks",
        "regulatoryBody": "Nepal Rastra Bank",
        "instrumentType": "Equity",
    },
    {
        "id": 2,
        "companyName": "Delisted Co.",
        "symbol": "GONE",
        "securityName": "Delisted",
        "status": "D",
        "companyEmail": "",
        "website": "",
        "sectorName": "",
        "regulatoryBody": "",
        "instrumentType": "Equity",
    },
]

FINANCIALS_FIXTURE = [
    {
        "id": 100,
        "symbol": "TEST",
        "reports": [
            {
                "type": "Quarterly Report",
                "quarter": "Third Quarter",
                "fy": "2025-2026",
                "fy_nepali": "2082-2083",
                "pe": 20.0,
                "eps": 10.0,
                "paid_up_capital": 1000000.0,
                "profit": 500000.0,
                "net_worth_per_share": 110.0,
                "documents": [{"submitted_date": "2026-05-12", "path": "doc.pdf"}],
            }
        ],
    }
]

DISCLOSURES_FIXTURE = [
    {
        "id": 1,
        "symbol": "TEST",
        "title": "Promoter transaction",
        "body": "Promoter transaction details.",
        "source": "promoter share",
        "publishedAt": "2026-10-12T15:33:27.437",
        "documents": [],
    }
]

EXCHANGE_MESSAGES_FIXTURE = [
    {
        "id": 2,
        "symbol": "TEST",
        "title": "Price adjusted",
        "body": "Adjusted price for bonus.",
        "publishedAt": "2026-10-02T15:51:47.023",
        "expiresAt": "2026-10-02",
    }
]

NOTICES_FIXTURE = {
    "general": [
        {
            "id": 3,
            "title": "General notice",
            "body": "General notice body",
            "expiresAt": "2026-12-01",
            "type": "Company Notice",
            "featured": True,
            "filePath": "notice.pdf",
        }
    ],
    "last_updated": "2026-10-12T00:00:00",
}


def test_fetch_securities_parses_json():
    with patch("megatool.datasources.yonepse.urlopen", return_value=_mock_json(SECURITIES_FIXTURE)):
        data = yonepse.fetch_securities()
    assert len(data) == 2
    assert data[0]["symbol"] == "TEST"


def test_securities_to_metadata_rows_normalizes_status_and_instrument():
    rows = yonepse.securities_to_metadata_rows(SECURITIES_FIXTURE)
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["TEST"]["status"] == "ACTIVE"
    assert by_symbol["TEST"]["instrument_type"] == "ordinary"
    assert by_symbol["TEST"]["sector"] == "Commercial Banks"
    assert by_symbol["GONE"]["status"] == "DELISTED"
    assert by_symbol["GONE"]["sector"] == ""


def test_securities_to_sector_rows_skips_empty_sectors():
    rows = yonepse.securities_to_sector_rows(SECURITIES_FIXTURE)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "TEST"


def test_financials_to_fundamental_rows_flattens_reports():
    rows = yonepse.financials_to_fundamental_rows(FINANCIALS_FIXTURE)
    by_field = {r["field"]: r for r in rows}
    assert "eps" in by_field
    assert by_field["eps"]["symbol"] == "TEST"
    assert by_field["eps"]["unit"] == "NPR"
    assert by_field["eps"]["value"] == 10.0
    assert "pe" in by_field
    assert by_field["pe"]["unit"] == "ratio"


def test_notify_to_news_rows_excludes_general_notices():
    """General notices have no publication date, so they are not emitted.

    Their ``expiresAt`` is an expiry, not a publication date; substituting it
    would hand the pipeline a fabricated timestamp.
    """
    rows = yonepse.notify_to_news_rows(
        DISCLOSURES_FIXTURE, EXCHANGE_MESSAGES_FIXTURE, NOTICES_FIXTURE
    )
    titles = {r["title"] for r in rows}
    assert "Promoter transaction" in titles
    assert "Price adjusted" in titles
    assert "General notice" not in titles
    sym_rows = [r for r in rows if r["symbols"] == "TEST"]
    assert len(sym_rows) == 2
    # These fixture records all carry real timestamps.
    assert all(r["published_at"] for r in rows)


def test_undated_disclosure_is_emitted_with_no_invented_timestamp():
    """A record with no publication date is never back-dated.

    It is emitted with an empty ``published_at`` (the importer then rejects it
    with a reason) rather than carrying an expiry or a "now" stand-in.
    """
    undated = {**DISCLOSURES_FIXTURE[0], "publishedAt": None}
    rows = yonepse.notify_to_news_rows([undated], None, None)
    assert len(rows) == 1
    assert rows[0]["published_at"] == ""


@pytest.mark.skipif(
    not (RAW / "yonepse_disclosures.json").exists(), reason="probe file not downloaded"
)
def test_real_notify_split_334_dated_and_18_undated():
    """Measured on the real snapshot: 334 dated items, 18 undated skipped."""
    disc = json.loads((RAW / "yonepse_disclosures.json").read_text())
    msgs = json.loads((RAW / "yonepse_exchange_messages.json").read_text())
    rows = yonepse.notify_to_news_rows(disc, msgs, None)
    dated = [r for r in rows if r["published_at"]]
    undated = [r for r in rows if not r["published_at"]]
    assert len(dated) == 334
    assert len(undated) == 18


def test_notices_without_publication_date_are_reported_as_unusable():
    out = yonepse.notices_without_publication_date(NOTICES_FIXTURE)
    assert len(out) == 1
    assert out[0]["title"] == "General notice"
    assert "expiry" in out[0]["reason"]
    assert yonepse.notices_without_publication_date({"general": []}) == []
    assert yonepse.notices_without_publication_date(None) == []


def test_dated_general_notice_would_become_usable():
    """If the snapshot ever gains a publication date, the item stops being unusable."""
    notices = {
        "general": [
            {
                "id": 3,
                "title": "Dated notice",
                "body": "body",
                "expiresAt": "2026-12-01",
                "publishedAt": "2026-10-01T09:00:00",
                "type": "Company Notice",
            }
        ]
    }
    assert yonepse.notices_without_publication_date(notices) == []


def test_csv_renderers_produce_headers():
    meta = yonepse.metadata_csv(yonepse.securities_to_metadata_rows(SECURITIES_FIXTURE))
    assert "symbol,name,instrument_type,sector,status" in meta
    sec = yonepse.sector_csv(yonepse.securities_to_sector_rows(SECURITIES_FIXTURE))
    assert "symbol,sector,source,retrieved_at,observed_date" in sec
    fin = yonepse.fundamentals_csv(yonepse.financials_to_fundamental_rows(FINANCIALS_FIXTURE))
    assert "symbol,field,value,unit" in fin
    news = yonepse.news_csv(yonepse.notify_to_news_rows(DISCLOSURES_FIXTURE, None, None))
    assert "title,summary,url,source,published_at,symbols" in news


# ------------------------------------------------- duplicate filing handling


#: Filed dates chosen so each reporting period is distinguishable by its own
#: filing date, which is how the real snapshot behaves. Grouping on the filing
#: date is the documented rule, so distinct periods MUST carry distinct dates.
_FY_FILED = {"2024-2025": "2025-12-15", "2025-2026": "2026-05-12"}


def _report(**kw):
    base = {
        "type": "Quarterly Report",
        "quarter": "Third Quarter",
        "fy": "2025-2026",
        "pe": 29.3,
        "eps": 34.02,
        "paid_up_capital": 367143409.0,
        "profit": 93684506.0,
        "net_worth_per_share": 179.21,
        "documents": [{"submitted_date": _FY_FILED["2025-2026"], "path": "a.pdf"}],
    }
    base.update(kw)
    if "documents" not in kw:
        filed = kw.get("submitted", _FY_FILED.get(kw.get("fy", "2025-2026"), "2026-05-12"))
        base["documents"] = [{"submitted_date": filed, "path": "a.pdf"}]
    kw.pop("submitted", None)
    base.update({k: v for k, v in kw.items() if k != "submitted"})
    return base


def test_identical_duplicate_filings_collapse_without_changing_values():
    records = [{"symbol": "ACLBSL", "reports": [_report(), _report()]}]
    deduped, stats = yonepse.dedupe_financial_reports(records)
    assert len(deduped["ACLBSL"]) == 1
    assert deduped["ACLBSL"][0]["eps"] == 34.02
    assert stats["exact_duplicates_dropped"] == 1
    assert stats["conflicting_periods_resolved"] == 0


def test_annual_figure_wins_over_quarterly_for_the_same_fy_close():
    """Fourth Quarter and Annual Report both close the fiscal year.

    The loader can store only one figure per period, so the complete-period
    figure (annual) is kept and the quarter-only one is dropped — the choice is
    recorded in the emitted notes rather than made silently.
    """
    q4 = _report(
        type="Quarterly Report",
        quarter="Fourth Quarter",
        fy="2025-2026",
        eps=5.0,
        documents=[{"submitted_date": "2026-05-12", "path": "q4.pdf"}],
    )
    annual = _report(
        type="Annual Report",
        quarter=None,
        fy="2025-2026",
        eps=20.0,
        documents=[{"submitted_date": "2026-05-12", "path": "ar.pdf"}],
    )
    records = [{"symbol": "ACLBSL", "reports": [q4, annual]}]
    deduped, stats = yonepse.dedupe_financial_reports(records)

    assert len(deduped["ACLBSL"]) == 1
    assert deduped["ACLBSL"][0]["eps"] == 20.0
    assert deduped["ACLBSL"][0]["type"] == "Annual Report"
    assert stats["conflicting_periods_resolved"] == 1
    assert stats["symbols_with_conflicts"] == 1


def test_latest_filing_wins_when_both_are_the_same_type():
    """Two conflicting quarterly filings of one period: newest wins."""
    old = _report(
        fy="2025-2026", eps=1.0, documents=[{"submitted_date": "2026-05-12", "path": "old.pdf"}]
    )
    new = _report(
        fy="2025-2026", eps=9.0, documents=[{"submitted_date": "2026-05-12", "path": "new.pdf"}]
    )
    records = [{"symbol": "ACLBSL", "reports": [old, new]}]
    deduped, _ = yonepse.dedupe_financial_reports(records)
    assert len(deduped["ACLBSL"]) == 1
    assert deduped["ACLBSL"][0]["eps"] == 9.0


def test_dedupe_does_not_merge_across_periods():
    """Distinct reporting periods must each survive independently."""
    q3_25 = _report(quarter="Third Quarter", fy="2025-2026", eps=1.0)
    q3_24 = _report(quarter="Third Quarter", fy="2024-2025", eps=2.0)
    records = [{"symbol": "ACLBSL", "reports": [q3_25, q3_24]}]
    deduped, stats = yonepse.dedupe_financial_reports(records)
    assert len(deduped["ACLBSL"]) == 2
    assert stats["reports_in"] == 2 and stats["reports_out"] == 2


def test_collapsed_note_records_the_resolution_rule():
    q4 = _report(
        type="Quarterly Report",
        quarter="Fourth Quarter",
        fy="2025-2026",
        eps=5.0,
    )
    annual = _report(type="Annual Report", quarter=None, fy="2025-2026", eps=20.0)
    rows = yonepse.financials_to_fundamental_rows([{"symbol": "ACLBSL", "reports": [q4, annual]}])
    eps_rows = [r for r in rows if r["field"] == "eps"]
    assert len(eps_rows) == 1
    assert "collapsed" in eps_rows[0]["notes"]
    assert "Annual Report" in eps_rows[0]["notes"]


def test_undeduped_conversion_still_produces_one_row_per_report():
    """``dedupe=False`` is the raw pass-through for callers that want it."""
    records = [{"symbol": "ACLBSL", "reports": [_report(), _report()]}]
    rows = yonepse.financials_to_fundamental_rows(records, dedupe=False)
    assert len([r for r in rows if r["field"] == "eps"]) == 2


# ------------------------------------------- point-in-time / look-ahead safety


def test_period_end_is_the_filing_date_and_filed_at_is_exposed():
    """``period_end`` is the date the figure became public; ``filed_at`` carries it.

    The snapshot supplies no trustworthy reporting-period date, so using the
    document submission date is what stops a backtest using a figure before it
    existed.
    """
    rows = yonepse.financials_to_fundamental_rows(
        [{"symbol": "ACLBSL", "reports": [_report(eps=10.0)]}]
    )
    eps = next(r for r in rows if r["field"] == "eps")
    assert eps["filed_at"] == "2026-05-12"
    assert eps["period_end"] == "2026-05-12"
    assert "filed_at=2026-05-12" in eps["notes"]
    # the source's own wording is preserved, not discarded
    assert "Third Quarter" in eps["period_label"]
    assert "2025-2026" in eps["period_label"]


def test_revised_filing_becomes_a_newer_vintage_not_an_overwrite():
    """A corrected filing of the same period must not replace the earlier one.

    Two vintages of one period, filed on different dates, must yield two
    distinct ``period_end`` values so a point-in-time query can select the
    figure that was actually known on the date being tested.
    """
    original = _report(eps=10.0, documents=[{"submitted_date": "2026-05-12", "path": "a.pdf"}])
    revised = _report(eps=12.0, documents=[{"submitted_date": "2026-06-20", "path": "b.pdf"}])
    rows = yonepse.financials_to_fundamental_rows(
        [{"symbol": "ACLBSL", "reports": [original, revised]}], dedupe=False
    )
    eps_periods = sorted(r["period_end"] for r in rows if r["field"] == "eps")
    assert eps_periods == ["2026-05-12", "2026-06-20"]


def test_report_with_no_document_is_not_back_dated():
    """No filing date means no vintage: the row says so and is never invented."""
    rep = _report(eps=1.0)
    rep["documents"] = []
    rows = yonepse.financials_to_fundamental_rows([{"symbol": "ACLBSL", "reports": [rep]}])
    eps = next(r for r in rows if r["field"] == "eps")
    assert eps["filed_at"] == ""
    assert eps["period_end"] == ""
    assert "no filed_at" in eps["notes"]


def test_point_in_time_available_reports_coverage():
    rows = yonepse.financials_to_fundamental_rows(
        [{"symbol": "ACLBSL", "reports": [_report(eps=1.0), _report(eps=2.0)]}]
    )
    pit = yonepse.point_in_time_available(rows)
    assert pit["rows"] == len(rows)
    assert pit["coverage_pct"] == 100.0
    assert pit["earliest"] == "2026-05-12"
    assert "filed_at <=" in pit["usage"]


def test_point_in_time_availability_excludes_undated_rows():
    rep = _report(eps=1.0)
    rep["documents"] = []
    rows = yonepse.financials_to_fundamental_rows([{"symbol": "ACLBSL", "reports": [rep]}])
    pit = yonepse.point_in_time_available(rows)
    assert pit["rows_with_filed_at"] == 0
    assert pit["coverage_pct"] == 0.0


@pytest.mark.skipif(
    not (RAW / "yonepse_financials.json").exists(), reason="probe file not downloaded"
)
def test_real_financials_are_point_in_time_usable():
    """Measured on the real snapshot: nearly every record carries a filing date."""
    records = json.loads((RAW / "yonepse_financials.json").read_text())
    rows = yonepse.financials_to_fundamental_rows(records)
    pit = yonepse.point_in_time_available(rows)
    assert pit["rows"] >= 20_000
    assert pit["coverage_pct"] >= 99.0
    assert pit["earliest"] < pit["latest"]


def test_undated_report_recovers_date_from_identical_dated_twin():
    """An export with no document date, but an identical dated twin, is dated.

    Evidence-only: same symbol, every filing field equal, and the twin's
    submitted date unambiguous. The recovered date is disclosed in the note.
    """
    dated = _report(eps=7.0, documents=[{"submitted_date": "2025-09-09", "path": "x.pdf"}])
    undated = _report(eps=7.0, documents=[])
    rows = yonepse.financials_to_fundamental_rows(
        [{"symbol": "ACLBSL", "reports": [dated, undated]}], dedupe=False
    )
    assert all(r["filed_at"] == "2025-09-09" for r in rows if r["field"] == "eps")
    assert any("recovered from an identical dated twin" in r["notes"] for r in rows)


def test_recovery_refuses_ambiguous_or_absent_twin_dates():
    """Two different dates for the same figures -> no recovery; no twin -> none."""
    # Two dated twins with DIFFERENT dates and identical figures: ambiguous.
    a = _report(eps=3.0, documents=[{"submitted_date": "2025-01-01", "path": "a.pdf"}])
    b = _report(eps=3.0, documents=[{"submitted_date": "2025-02-02", "path": "b.pdf"}])
    undated = _report(eps=3.0, documents=[])
    recovered = yonepse.recover_filing_dates([{"symbol": "ACLBSL", "reports": [a, b, undated]}])
    assert recovered == {}
    # No twin at all.
    lonely = _report(eps=9.0, documents=[])
    assert yonepse.recover_filing_dates([{"symbol": "ACLBSL", "reports": [lonely]}]) == {}


def test_real_financials_are_fully_point_in_time_usable_after_recovery():
    """On the real snapshot every figure now carries a filing date."""
    records = json.loads((RAW / "yonepse_financials.json").read_text())
    rows = yonepse.financials_to_fundamental_rows(records)
    pit = yonepse.point_in_time_available(rows)
    assert pit["coverage_pct"] == 100.0
    assert pit["rows_with_filed_at"] == pit["rows"]


def test_dated_and_undated_twin_collapse_to_one_loadable_row():
    """An undated export must merge into its dated twin, not duplicate it.

    Regression: with ``dedupe=True`` (the integration path) the recovered date
    placed the undated duplicate in the same ``(symbol, field, period_end)``
    slot as its dated twin, so ``fundamentals.records_from_rows`` refused the
    whole file. The undated export is a duplicate of the dated one, so it must
    collapse — keeping the documented representative's source reference.
    """
    dated = _report(eps=7.0, documents=[{"submitted_date": "2025-09-09", "path": "x.pdf"}])
    undated = _report(eps=7.0, documents=[])
    rows = yonepse.financials_to_fundamental_rows(
        [{"symbol": "ACLBSL", "reports": [dated, undated]}]
    )
    eps_rows = [r for r in rows if r["field"] == "eps"]
    assert len(eps_rows) == 1
    assert eps_rows[0]["filed_at"] == "2025-09-09"
    assert eps_rows[0]["source_ref"] == "x.pdf"
    # and the loader accepts the whole emitted set (no duplicate rejection)
    records = fundamentals.records_from_rows(rows)
    assert len(records) == len(rows)


@pytest.mark.skipif(
    not (RAW / "yonepse_financials.json").exists(), reason="probe file not downloaded"
)
def test_real_financials_load_without_duplicate_rejection():
    """The real snapshot converts to a row set the fundamentals loader accepts.

    This is the end-to-end guard the sample fixtures missed: it exercises the
    exact ``(symbol, field, period_end)`` uniqueness the loader enforces on the
    real 21k-row conversion, including the undated-twin recovery.
    """
    records = json.loads((RAW / "yonepse_financials.json").read_text())
    rows = yonepse.financials_to_fundamental_rows(records)
    loaded = fundamentals.records_from_rows(rows)
    assert len(loaded) == len(rows)


def test_fetch_prefers_the_fresh_raw_base_over_the_cached_pages_mirror():
    """Raw repo content is read first; the CDN mirror is only a fallback.

    Measured 2026-10-16: the GitHub-Pages mirror served a ~4-day-old copy while
    the repository's raw content was current to the hour. The ordering is the
    difference between "today's prices" and "last week's prices", so it is
    pinned by a test rather than left to a constant.
    """
    assert yonepse.BASE_URLS[0] == yonepse.RAW_BASE_URL
    assert "raw.githubusercontent.com" in yonepse.RAW_BASE_URL
    assert yonepse.BASE_URLS[-1] == yonepse.PAGES_BASE_URL
    assert yonepse.BASE_URL == yonepse.RAW_BASE_URL

    seen = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode()

    def fake_urlopen(url, timeout=None):
        seen.append(url)
        return _Resp()

    with patch("megatool.datasources.yonepse.urlopen", side_effect=fake_urlopen):
        assert yonepse._fetch_json("data/market/status.json") == {"ok": True}
    # First attempt is the raw base, and only one request is made on success.
    assert seen == [f"{yonepse.RAW_BASE_URL}/data/market/status.json"]


def test_fetch_falls_back_to_pages_only_after_raw_fails():
    seen = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"stale": True}).encode()

    def fake_urlopen(url, timeout=None):
        seen.append(url)
        if "raw.githubusercontent.com" in url:
            raise OSError("network down")
        return _Resp()

    yonepse._COMMIT_CACHE.update(at=0.0, shas=[])
    with patch("megatool.datasources.yonepse.urlopen", side_effect=fake_urlopen):
        assert yonepse._fetch_json("data/market/status.json") == {"stale": True}
    # Raw is attempted first and the Pages mirror last; the middle entries are
    # the (optional) commit walk-back used when `main` is unreadable.
    assert seen[0] == f"{yonepse.RAW_BASE_URL}/data/market/status.json"
    assert seen[-1] == f"{yonepse.PAGES_BASE_URL}/data/market/status.json"


def test_fetch_walks_back_to_a_clean_commit_when_main_is_a_broken_merge():
    """A merge-conflict commit on `main` must not force us onto the stale mirror.

    The upstream automations occasionally land `<<<<<<< HEAD` markers instead of
    JSON. The fresh data still exists in the commit below, so the adapter must
    use it (and report that commit as the origin) rather than serving a
    days-old mirror or inventing a repaired payload.
    """
    yonepse._COMMIT_CACHE.update(at=0.0, shas=["cleansha0001"])
    seen = []

    class _Resp:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._body

    def fake_urlopen(url, timeout=None):
        seen.append(url)
        if url.startswith("https://api.github.com"):
            return _Resp(json.dumps([{"sha": "cleansha0001"}]).encode())
        if "/main/data/market/status.json" in url:
            return _Resp(
                b'{\n<<<<<<< HEAD\n"is_open": true\n=======\n"is_open": false\n>>>>>>> abc\n}'
            )
        if "cleansha0001/data/market/status.json" in url:
            return _Resp(
                json.dumps({"is_open": True, "last_checked": "2026-10-16T07:17:03"}).encode()
            )
        raise AssertionError(f"unexpected fetch: {url}")

    with patch("megatool.datasources.yonepse.urlopen", side_effect=fake_urlopen):
        payload, origin = yonepse._fetch_json_verbose("data/market/status.json")
    assert payload["is_open"] is True
    assert origin == f"{yonepse._RAW_ROOT}/cleansha0001"
    # The Pages mirror was never needed.
    assert not any("github.io" in u for u in seen)


def test_fetch_market_extras_reads_whole_bundle_at_one_ref():
    """Extras share the live trio's newest-parseable-ref decision (one origin)."""
    yonepse._COMMIT_CACHE.update(at=0.0, shas=[])
    yonepse._REF_CACHE.update(at=0.0, ref=None)
    seen: list[str] = []

    class _Resp:
        def __init__(self, body: bytes):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._body

    def fake_urlopen(url, timeout=None):
        seen.append(url)
        if url.startswith("https://api.github.com"):
            return _Resp(json.dumps([{"sha": "goodsha0001"}]).encode())
        if "/main/data/market/live.json" in url:  # _market_ref probes the board
            return _Resp(
                json.dumps([{"symbol": "T", "last_updated": "2026-10-16T10:00:00"}]).encode()
            )
        if "/goodsha0001/data/market/summary.json" in url:
            return _Resp(json.dumps([{"detail": "Total Turnover Rs:", "value": 1.0}]).encode())
        if "/goodsha0001/data/market/top_stocks.json" in url:
            return _Resp(
                json.dumps({"top_gainer": [{"symbol": "T", "percentageChange": 5.0}]}).encode()
            )
        if "/goodsha0001/data/market/sector_indices.json" in url:
            return _Resp(
                json.dumps([{"indexCode": "BANK", "indexName": "Banking SubIndex"}]).encode()
            )
        if "/goodsha0001/data/market/history.json" in url:
            return _Resp(
                json.dumps([{"businessDate": "2026-10-16", "totalTurnover": 1.0}]).encode()
            )
        raise AssertionError(f"unexpected fetch: {url}")

    with patch("megatool.datasources.yonepse.urlopen", side_effect=fake_urlopen):
        files, errors = yonepse.fetch_market_extras(yonepse.MARKET_EXTRA_PATHS)
    assert not errors
    assert set(files) == set(yonepse.MARKET_EXTRA_PATHS)
    payload, origin = files[yonepse.PATH_MARKET_SUMMARY]
    assert payload[0]["value"] == 1.0
    # one ref decided for the whole bundle: every origin is the same commit
    assert all(origin == f"{yonepse._RAW_ROOT}/goodsha0001" for _, origin in files.values())


def test_fetch_market_extras_tolerates_one_missing_file():
    yonepse._COMMIT_CACHE.update(at=0.0, shas=[])
    yonepse._REF_CACHE.update(at=0.0, ref=None)

    class _Resp:
        def __init__(self, body: bytes):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._body

    def fake_urlopen(url, timeout=None):
        # any URL that reaches a 404 in either ref context
        if "top_stocks.json" in url:
            raise HTTPError(url, 404, "Not Found", {"Content-Length": "0"}, io.BytesIO(b""))
        if url.startswith("https://api.github.com"):
            return _Resp(json.dumps([{"sha": "goodsha0001"}]).encode())
        if "/data/market/live.json" in url:
            return _Resp(json.dumps([{"symbol": "T", "last_updated": "2026-10-16"}]).encode())
        if "/data/market/summary.json" in url:
            return _Resp(json.dumps([]).encode())
        raise AssertionError(f"unexpected fetch: {url}")

    with patch("megatool.datasources.yonepse.urlopen", side_effect=fake_urlopen):
        files, errors = yonepse.fetch_market_extras(
            (yonepse.PATH_MARKET_SUMMARY, yonepse.PATH_MARKET_TOP_STOCKS)
        )
    assert files[yonepse.PATH_MARKET_SUMMARY][0] == []
    # a genuinely missing file is an error record, never a fabricated payload
    assert set(errors) == {yonepse.PATH_MARKET_TOP_STOCKS}


def test_fetch_never_repairs_conflict_markers_into_data():
    yonepse._COMMIT_CACHE.update(at=0.0, shas=[])
    broken = b'{\n<<<<<<< HEAD\n"is_open": true\n'

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return broken

    with (
        patch("megatool.datasources.yonepse.urlopen", return_value=_Resp()),
        pytest.raises(yonepse.YonepseError),
    ):
        yonepse._fetch_json("data/market/status.json")


def test_fetch_raises_and_names_every_attempt_when_all_bases_fail():
    def fake_urlopen(url, timeout=None):
        raise OSError("offline")

    with (
        patch("megatool.datasources.yonepse.urlopen", side_effect=fake_urlopen),
        pytest.raises(yonepse.YonepseError) as exc,
    ):
        yonepse._fetch_json("data/market/status.json")
    msg = str(exc.value)
    assert yonepse.RAW_BASE_URL in msg and yonepse.PAGES_BASE_URL in msg
