"""Focused tests for the binayabaral/nepal-market-data adapter.

Network access is mocked; tests use inline CSV fixtures.
"""

from __future__ import annotations

from unittest.mock import patch

from megatool.datasources import binayabaral

REFERENCE_CSV = """symbol,name,source_category,instrument_type,sector,status
ACLBSL,Aarambha Chautari Laghubitta Bittiya Sanstha Limited,Microfinance,ordinary,Microfinance,listed
MERGEDCO,Merged Company,Finance,ordinary,Finance,merged
NOSECTOR,No Sector Co,Finance,ordinary,,listed
"""

INDEX_CSV = """published_date,open,high,low,close,per_change,traded_quantity,traded_amount,status
2026-10-14,2600.0,2620.0,2590.0,2620.0,0.5,,1000000,A
2026-10-13,2590.0,2605.0,2585.0,2605.0,0.4,,900000,A
"""


def test_reference_to_metadata_rows_maps_status_and_preserves_empty_sector():
    rows = binayabaral.reference_to_metadata_rows(REFERENCE_CSV)
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["ACLBSL"]["status"] == "ACTIVE"
    assert by_symbol["ACLBSL"]["sector"] == "Microfinance"
    assert by_symbol["MERGEDCO"]["status"] == "MERGED"
    assert by_symbol["NOSECTOR"]["sector"] == ""


def test_reference_to_sector_rows_skips_empty_sectors():
    rows = binayabaral.reference_to_sector_rows(REFERENCE_CSV)
    assert len(rows) == 2
    assert all(r["symbol"] != "NOSECTOR" for r in rows)


def test_index_to_index_csv_selects_date_and_close():
    out = binayabaral.index_to_index_csv(INDEX_CSV)
    lines = out.strip().splitlines()
    assert lines[0] == "date,close"
    assert lines[1] == "2026-10-14,2620.0"
    assert lines[2] == "2026-10-13,2605.0"


def test_fetch_reference_csv_uses_urlopen():
    with patch("megatool.datasources.binayabaral.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value.read.return_value = REFERENCE_CSV.encode(
            "utf-8"
        )
        text = binayabaral.fetch_reference_csv()
    assert "ACLBSL" in text
