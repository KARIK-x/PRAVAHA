"""Tests for the vendored Bikram Sambat <-> Gregorian conversion.

The mapping is third-party data (OpenNP ``nepali-dates``) vendored under
``data/bs_ad/``. That directory is git-ignored because it is regenerable, so
these tests validate the mapping when it is present and skip cleanly when it is
not — a missing vendored table is a build step, not a code defect.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from megatool.bs_ad import BsAdError, MAP_PATH, default_map

pytestmark = pytest.mark.skipif(
    not Path(MAP_PATH).is_file(),
    reason="vendored BS<->AD mapping absent (run `python -m megatool.bs_ad --build`)",
)

M = default_map()


# --------------------------------------------------------------- known anchors
#: Independently checkable reference points. Nepali New Year (BS 01-01) falls in
#: mid-April, and the year runs to mid-April of the next Gregorian year.
@pytest.mark.parametrize(
    ("bs", "ad"),
    [
        ((2080, 1, 1), date(2023, 4, 14)),   # Nepali New Year 2080
        ((2080, 12, 30), date(2024, 4, 12)), # last day of BS 2080
        ((2081, 1, 1), date(2024, 4, 13)),   # Nepali New Year 2081
        ((2050, 1, 1), date(1993, 4, 13)),   # first day of the mapped range
        ((2086, 12, 30), date(2030, 4, 13)), # last day of the mapped range
    ],
)
def test_known_new_year_and_range_boundaries(bs, ad):
    assert M.bs_to_ad(*bs).value == ad
    assert M.bs_to_ad(*bs).in_coverage


def test_bs_2080_spans_exactly_one_gregorian_year():
    """A BS year is a 365/366-day run of contiguous Gregorian dates."""
    first = M.bs_to_ad(2080, 1, 1).value
    last = M.bs_to_ad(2080, 12, M.days_in_bs_month(2080, 12)).value
    assert first is not None and last is not None
    assert (last - first).days in (364, 365)


def test_month_lengths_are_realistic():
    """BS months run 29-32 days; nothing else is a valid month."""
    for year in range(M.first_bs_year, M.last_bs_year + 1):
        for month in range(1, 13):
            n = M.days_in_bs_month(year, month)
            assert 29 <= n <= 32, f"BS {year}-{month:02d} has {n} days"


def test_every_bs_year_has_twelve_months():
    for year in range(M.first_bs_year, M.last_bs_year + 1):
        assert sorted({m for m in M._bs_month[year]}) == list(range(1, 13))


# ------------------------------------------------------------------ round trip
def test_round_trip_every_mapped_day():
    """AD->BS->AD is the identity for every day the mapping can resolve.

    The documented source anomalies (90 days in BS 2083) are excluded: those
    triples exist in the published table but are unreachable by ``bs_to_ad``
    because the source month numbering is inconsistent there.
    """
    anomalous = M.anomalous_bs_dates()
    checked = 0
    for year, days in M._bs_to_ad.items():
        for ad_iso in days.values():
            ad = date.fromisoformat(ad_iso)
            back = M.ad_to_bs(ad)
            assert back.in_coverage, ad_iso
            assert back.value[0] == year, ad_iso
            if back.value in anomalous:
                continue
            again = M.bs_to_ad(*back.value)
            assert again.in_coverage and again.value == ad, ad_iso
            checked += 1
    assert checked > 13000


def test_bs_day_restarts_at_one_for_a_normal_month():
    start = M._bs_month_start_doy(2080, 1)
    assert M._bs_day[2080][start - 1] == 1


# ------------------------------------------------------------------- coverage
def test_out_of_range_years_are_unresolved_not_guessed():
    for year in (M.first_bs_year - 1, M.last_bs_year + 1, 1900, 2200):
        out = M.bs_to_ad(year, 1, 1)
        assert not out.in_coverage
        assert out.value is None
        assert "outside the mapped range" in out.note


def test_gregorian_out_of_range_is_unresolved():
    assert not M.ad_to_bs(date(1990, 1, 1)).in_coverage
    assert not M.ad_to_bs(date(2100, 1, 1)).in_coverage


def test_nonexistent_bs_day_is_unresolved():
    """BS 2080-02 has 32 days, so day 31 exists but day 33 does not."""
    assert M.bs_to_ad(2080, 2, 31).in_coverage
    out = M.bs_to_ad(2080, 2, 33)
    assert not out.in_coverage
    assert "does not exist" in out.note


def test_nonexistent_bs_month_is_rejected():
    out = M.bs_to_ad(2080, 13, 1)
    assert not out.in_coverage


def test_malformed_input_is_reported_not_raised():
    """``bs_to_ad`` answers with ``in_coverage=False`` rather than raising.

    Raising would turn a single bad calendar record into a failed import. The
    strict :meth:`BsAdMap._check_ymd` is still available for callers that want
    to validate before converting.
    """
    for args in ((2080, 0, 1), (2080, 13, 1), (2080, 1, 0), (2080, 1, -3), (-1, 1, 1)):
        out = M.bs_to_ad(*args)
        assert not out.in_coverage, args
        assert out.value is None, args
        assert out.note, args
    # The strict validator itself still raises.
    for args in ((2080, 0, 1), (2080, 1, 0), (-1, 1, 1)):
        with pytest.raises(BsAdError):
            M._check_ymd(*args)


def test_non_integer_input_raises():
    with pytest.raises(BsAdError):
        M._check_ymd(2080.5, 1, 1)


# ------------------------------------------------------------------ validation
def test_mapping_validates_cleanly():
    report = M.validate()
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["roundtrip_failures"] == 0
    assert report["days_checked"] > 13000
    assert report["bs_years"] == [M.first_bs_year, M.last_bs_year]


def test_source_anomalies_are_reported_not_hidden():
    """BS 2083 (the current year) has three unusual month starts in the source.

    They are published-source facts. The validator must surface them rather than
    silently "fixing" them, and conversion must still be deterministic.
    """
    report = M.validate()
    anomalies = report["month_start_anomalies"]
    assert any("2083-07" in a for a in anomalies)
    # The affected BS days simply do not resolve; nothing is invented.
    assert report["anomalous_bs_dates"] >= 1
    assert report["missing_bs_days"] >= 1
    # ...and they are exactly the set the converter refuses to guess about.
    assert M.anomalous_bs_dates()
    for triple in M.anomalous_bs_dates():
        assert not M.bs_to_ad(*triple).in_coverage


def test_coverage_spans_the_required_market_history():
    """The market data runs AD 1995-2026; the mapping must cover all of it."""
    assert M.ad_to_bs(date(1995, 1, 1)).in_coverage
    assert M.ad_to_bs(date(2026, 10, 16)).in_coverage


def test_provenance_is_carried_on_every_answer():
    out = M.bs_to_ad(2080, 1, 1)
    assert "nepali-dates" in out.source
    assert "opennp" in M.source
    assert M.version >= 1
    assert M.downloaded_at
