"""Focused tests for the socrateai ``ohlc_index`` adapter.

Uses a real captured session file (structure verified by hand) plus synthetic
rows for the edge cases: URL-encoded index names, empty numeric fields,
rounding artefacts, the pre-split legacy insurance index, and date mismatch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from megatool.datasources.socrateai import (
    INDEX_NAME_MAP,
    index_csv_url,
    index_name_canonical,
    parse_index_csv,
    to_index_rows,
    validate_observations,
)

RAW = Path("data/review/source_probe_2026-10-15")

HEADER = "timestamp,open,high,low,close,volume,symbol,date_unix,date\n"


def _row(symbol: str, o, h, low, c, v, day: str = "2026-10-13") -> str:
    return f"1791849600.0,{o},{h},{low},{c},{v},{symbol},1791849600.0,{day}\n"


def test_index_csv_url_uses_the_raw_cdn():
    assert index_csv_url("2026-10-13").endswith(
        "/socrateai-official/nepse-open-data/main/ohlc_index/adj_2026-10-13.csv"
    )


def test_url_encoded_index_names_are_decoded_and_canonicalised():
    text = (
        HEADER
        + _row("Development%20Bank_index", 5400.21, 5410.73, 5370.37, 5403.37, 142000818.0)
        + _row("Hotels%20and%20Tourism_index", 6910.70, 6951.10, 6845.50, 6870.57, 181815801.0)
        + _row("NEPSE_index", 2597.94, 2600.95, 2589.36, 2599.93, 4736923427.0)
    )
    parsed = parse_index_csv(text, trading_date="2026-10-13")
    names = {o["index_name"]: o for o in parsed["observations"]}
    assert set(names) == {"Development Banks", "Hotels & Tourism", "NEPSE"}
    # the composite close must survive untouched
    assert names["NEPSE"]["close"] == 2599.93
    assert parsed["date_mismatch"] is False
    assert parsed["unmapped_symbols"] == []


def test_empty_numeric_field_is_reported_missing_never_zero():
    text = HEADER + _row("NEPSE_index", "", 2600.95, 2589.36, 2599.93, "")
    parsed = parse_index_csv(text, trading_date="2026-10-13")
    assert parsed["observations"] == []
    assert len(parsed["missing"]) == 1
    assert parsed["missing"][0]["symbol"] == "NEPSE_index"
    assert set(parsed["missing"][0]["fields"]) == {"open", "volume"}


def test_validation_separates_rounding_artefacts_from_real_inversions():
    rounding_row = {
        # close=713.97 published vs high=713.968: an artefact of 2-dp rounding
        "date": "2019-04-21",
        "index_name": "Others",
        "open": 704.796,
        "high": 713.968,
        "low": 701.936,
        "close": 713.97,
        "volume": 57_224_686,
    }
    genuine_row = {
        "date": "2020-01-01",
        "index_name": "Bogus",
        "open": 100.0,
        "high": 50.0,  # high far below close: a real inversion
        "low": 10.0,
        "close": 100.0,
        "volume": 1.0,
    }
    out = validate_observations([rounding_row, genuine_row])
    assert out["checked"] == 2
    assert out["inverted"] and out["inverted"][0]["index_name"] == "Bogus"
    assert out["rounding_artefacts"] and out["rounding_artefacts"][0]["index_name"] == "Others"


def test_non_positive_close_is_flagged():
    rows = [
        {
            "date": "2020-01-01",
            "index_name": "NEPSE",
            "open": 0.0,
            "high": 0.0,
            "low": 0.0,
            "close": 0.0,
            "volume": 0.0,
        }
    ]
    out = validate_observations(rows)
    assert out["non_positive_close"] == [
        {"date": "2020-01-01", "index_name": "NEPSE", "close": 0.0}
    ]


def test_legacy_pre_split_insurance_index_is_mapped():
    assert index_name_canonical("Insurance_index") == "Insurance (legacy)"
    assert index_name_canonical("Life%20Insurance_index") == "Life Insurance"


def test_to_index_rows_carries_provenance_source():
    text = HEADER + _row("NEPSE_index", 2597.94, 2600.95, 2589.36, 2599.93, 4736923427.0)
    parsed = parse_index_csv(text, trading_date="2026-10-13")
    rows = to_index_rows(parsed["observations"], source="socrateai/ohlc_index")
    assert rows == [
        {
            "index_name": "NEPSE",
            "trading_date": "2026-10-13",
            "close": 2599.93,
            "source": "socrateai/ohlc_index",
        }
    ]


def test_row_date_disagreeing_with_the_filename_is_flagged():
    text = HEADER + _row("NEPSE_index", 1.0, 1.0, 1.0, 1.0, 1.0, day="2026-10-12")
    parsed = parse_index_csv(text, trading_date="2026-10-13")
    assert parsed["date_mismatch"] is True


@pytest.mark.skipif(
    not (RAW / "socrateai_index_2026-10-13.csv").exists(), reason="probe file not downloaded"
)
def test_real_captured_session_parses_and_validates():
    text = (RAW / "socrateai_index_2026-10-13.csv").read_text()
    parsed = parse_index_csv(text, trading_date="2026-10-13")
    assert len(parsed["observations"]) == 16
    assert "NEPSE" in {o["index_name"] for o in parsed["observations"]}
    assert parsed["date_mismatch"] is False
    report = validate_observations(parsed["observations"])
    # Measured reality for this session, read directly from the file: the
    # Life Insurance index publishes close 11825.33 against high 11821.03, an
    # excess of 4.30 that rounding cannot explain. The check must therefore
    # REPORT it rather than assume the source is internally clean.
    assert report["checked"] == 16
    assert report["non_positive_close"] == []
    assert len(report["inverted"]) == 1
    assert report["inverted"][0]["index_name"] == "Life Insurance"
    assert report["inverted"][0]["excess"] == pytest.approx(4.3, abs=0.005)
    assert report["rounding_artefacts"] == []
    assert len(INDEX_NAME_MAP) >= 16


@pytest.mark.skipif(
    not (RAW / "socrateai_index_2026-10-13.csv").exists(), reason="probe file not downloaded"
)
def test_real_file_nepse_close_matches_independent_source():
    """The composite close in the real file is 2599.93 (verified by reading it),
    which is the value an independent repository also publishes for that date."""
    text = (RAW / "socrateai_index_2026-10-13.csv").read_text()
    parsed = parse_index_csv(text, trading_date="2026-10-13")
    nepse = next(o for o in parsed["observations"] if o["index_name"] == "NEPSE")
    assert nepse["low"] <= nepse["close"] <= nepse["high"] + 0.01
    assert nepse["close"] == 2599.93
