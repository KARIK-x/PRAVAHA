"""Tests for the Hamro Patro calendar extraction pipeline.

The parser is exercised against a synthetic page shaped exactly like the real
one (verified 2026-10-20 against https://www.hamropatro.com/calendar/2082/1,
which yielded 35 cells / 63 events / 14 red-marked dates / 0 parse errors).
Nothing here invents a BS<->AD conversion: an unresolved Gregorian date must
stay unresolved.
"""

from __future__ import annotations

import os as _os
from pathlib import Path as _Path

import pytest

from megatool.calendar_import import (
    CalendarError,
    _dict_to_record,
    classify_event,
    extraction_report,
    load_dataset,
    merge_records,
    parse_calendar_page,
    records_from_page,
    validate_records,
)

PAGE = """<html><body>
<a aria-label="31, प्रतिपदा, holiday" class="x" href="/calendar/2081/12?d=2081-12-31">
  <div><span>13</span></div></a>
<a aria-label="1, नयाँ वर्ष, बिस्का: , holiday" class="x" href="/calendar/2082/1?d=2082-01-01">
  <div><span>14</span></div></a>
<a aria-label="2, द्वितीया" class="x" href="/calendar/2082/1?d=2082-01-02">
  <div><span>15</span></div></a>
<a aria-label="3" class="x" href="/calendar/2082/1?d=2082-01-03">
  <div><span>16</span></div></a>
</body></html>"""


def _page(**kw):
    return parse_calendar_page(PAGE, source_url="https://www.hamropatro.com/calendar/2082/1", **kw)


def test_parses_every_cell_and_keeps_multiple_events_per_date():
    page = _page()
    assert len(page["cells"]) == 4
    assert page["errors"] == []
    first = page["cells"][1]                      # 2082-01-01
    assert first["bs_date"] == "2082-01-01"
    assert first["gregorian_day"] == 14
    assert first["holiday_cell"] is True
    assert first["events"] == ["नयाँ वर्ष", "बिस्का:"], "both events on one date must be kept"


def test_a_date_with_no_named_event_is_still_a_date():
    page = _page()
    bare = page["cells"][3]                       # aria-label="3"
    assert bare["gregorian_day"] == 16
    assert bare["events"] == [""]
    assert bare["holiday_cell"] is False


def test_the_holiday_token_is_not_kept_as_an_event_name():
    page = _page()
    for c in page["cells"]:
        assert all(e.lower() != "holiday" for e in c["events"])


def test_garbage_input_is_refused():
    with pytest.raises(CalendarError):
        parse_calendar_page("<html>nothing here</html>")
    with pytest.raises(CalendarError):
        parse_calendar_page("")


def test_an_out_of_range_bs_day_is_a_parse_error_not_a_record():
    bad = PAGE.replace("?d=2082-01-03", "?d=2082-01-99")
    page = parse_calendar_page(bad)
    assert any("out of range" in e for e in page["errors"])
    assert all(c["bs_date"] != "2082-01-99" for c in page["cells"])


def test_classification_is_conservative():
    # A red cell with a name is a FESTIVAL CANDIDATE, never a national holiday.
    assert classify_event("नयाँ वर्ष", True) == "festival"
    assert classify_event("द्वितीया", False) == "religious_or_cultural_observance"
    assert classify_event("", True) == "other_calendar_event"
    assert classify_event("International Women's Day", False) == "international_observance"
    for name in ("नयाँ वर्ष", "द्वितीया", ""):
        assert classify_event(name, True) != "national_public_holiday"


def test_market_closure_is_never_inferred_from_a_red_cell():
    recs = records_from_page(_page())
    assert recs
    assert all(r.market_closure == "not_independently_verified" for r in recs)


def test_without_an_anchor_the_gregorian_date_stays_unresolved():
    recs = records_from_page(_page())
    assert all(r.gregorian_date is None for r in recs)
    assert all(r.gregorian_status == "unresolved" for r in recs)
    # The published day-of-month is still carried through.
    assert recs[0].gregorian_day == 13


def test_with_a_verified_anchor_gregorian_dates_are_derived_contiguously():
    recs = records_from_page(_page(), anchor={"bs_date": "2082-01-01", "gregorian_date": "2025-04-14"})
    by_date = {r.bs_date: r.gregorian_date for r in recs}
    assert by_date["2082-01-01"] == "2025-04-14"
    assert by_date["2082-01-02"] == "2025-04-15"
    assert by_date["2082-01-03"] == "2025-04-16"
    assert by_date["2081-12-31"] == "2025-04-13"     # counted backwards
    assert all(r.gregorian_status == "resolved" for r in recs)


def test_an_anchor_that_is_not_on_the_page_is_refused():
    with pytest.raises(CalendarError):
        records_from_page(_page(), anchor={"bs_date": "2099-01-01", "gregorian_date": "2025-04-14"})
    with pytest.raises(CalendarError):
        records_from_page(_page(), anchor={"bs_date": "2082-01-01", "gregorian_date": "not-a-date"})


def test_a_derived_date_that_disagrees_with_the_published_day_is_flagged():
    recs = records_from_page(_page(), anchor={"bs_date": "2082-01-01", "gregorian_date": "2025-04-14"})
    assert validate_records(recs) == []
    # Force a contradiction: claim the anchor is the 20th while the cell says 14.
    bad = records_from_page(_page(), anchor={"bs_date": "2082-01-01", "gregorian_date": "2025-04-20"})
    problems = validate_records(bad)
    assert any("mismatch" in p["problem"] for p in problems)


def test_validation_catches_structural_problems():
    recs = records_from_page(_page())
    recs[0].bs_day = 99
    recs[0].source_url = ""
    problems = validate_records(recs)
    assert any("BS day 99" in p["problem"] for p in problems)
    assert any("missing source URL" in p["problem"] for p in problems)


def test_event_identity_is_stable_and_disambiguates_same_name_events():
    recs = records_from_page(_page())
    ids = [r.event_id for r in recs]
    assert len(set(ids)) == len(ids), "every event must have a unique id"
    assert ids[0].startswith("2081-12-31#")
    # Re-parsing the same page yields the same ids.
    assert [r.event_id for r in records_from_page(_page())] == ids


def test_merge_is_idempotent():
    recs = records_from_page(_page())
    first = merge_records([], recs)
    assert first["added"] == len(recs) and first["total"] == len(recs)
    again = merge_records(first["records"], records_from_page(_page()))
    assert again["added"] == 0 and again["unchanged"] == len(recs)
    assert again["total"] == len(recs)


def test_merge_updates_a_changed_classification_but_never_downgrades_to_unknown():
    recs = records_from_page(_page())
    merged = merge_records([], recs)
    changed = records_from_page(_page())
    changed[0].classification = "unknown"
    out = merge_records(merged["records"], changed)
    kept = next(r for r in out["records"] if r["event_id"] == changed[0].event_id)
    assert kept["classification"] != "unknown", "an unknown classification must not overwrite a known one"
    assert out["updated"] == 0


def test_extraction_report_counts_are_correct():
    rep = extraction_report([r.to_dict() for r in records_from_page(_page())])
    assert rep["distinct_bs_dates"] == 4          # 2081-12-31, 2082-01-01, -02, -03
    assert rep["event_records"] == 5              # 1 + 2 + 1 + 1
    assert rep["red_marked_dates"] == 2           # 2081-12-31 and 2082-01-01
    assert rep["holidays_classified"] == 3
    assert rep["gregorian_unresolved"] == 5
    assert rep["periods_covered"] == ["2081-12", "2082-01"]
    assert rep["missing_periods"] == []


def test_extraction_report_reports_missing_periods_it_is_given():
    rep = extraction_report([r.to_dict() for r in records_from_page(_page())],
                            missing_periods=["2082-03"])
    assert rep["missing_periods"] == ["2082-03"]


# --------------------------------------------------- real extracted dataset
#: The extraction writes under MEGATOOL_DATA_DIR (data/ is git-ignored, so this
#: test validates the dataset when it is present and skips when it is not —
#: regenerating it needs network access to the public calendar.
_DATASET = _Path(_os.environ.get("MEGATOOL_DATA_DIR", "data")) / "calendar" / "hamropatro_calendar.json"


@pytest.mark.skipif(not _DATASET.is_file(),
                    reason="no extracted calendar dataset present (run `megatool calendar-import`)")
def test_the_real_dataset_is_valid_deduplicated_and_provenanced():
    recs = load_dataset(_DATASET)
    assert len(recs) > 1000, "an extracted dataset should hold many events"
    ids = [r["event_id"] for r in recs]
    assert len(set(ids)) == len(ids), "the dataset must not contain duplicate event ids"
    assert validate_records([_dict_to_record(r) for r in recs]) == [], "every stored record must validate"
    rep = extraction_report(recs)
    assert rep["distinct_bs_dates"] > 500
    assert rep["red_marked_dates"] > 0
    # Provenance and honesty properties that must hold for the whole dataset.
    assert all(r.get("source_url") for r in recs), "every record keeps its source URL"
    assert all(r.get("retrieved_at") for r in recs), "every record keeps its retrieval time"
    assert all(r["market_closure"] == "not_independently_verified" for r in recs), (
        "no red calendar cell may be promoted to a NEPSE closure"
    )
    assert not any(r["classification"] == "national_public_holiday" for r in recs), (
        "a calendar marking is a candidate, never an official public holiday"
    )
