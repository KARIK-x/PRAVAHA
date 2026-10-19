"""Sector importer tests: validation, no fabrication, no field clobbering.

Every CSV here is a SYNTHETIC fixture; nothing asserts anything about real
NEPSE sector labels. The properties that matter are the loader's refusals:
missing columns, empty sectors, conflicting classifications, symbols that do
not exist in the security master must never be silently invented, and every
sector assignment must carry stored provenance.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from megatool.market_store import MarketStore
from megatool.sectors import (
    REQUIRED_COLUMNS,
    SectorError,
    classify_sectors,
    import_sectors,
    read_sectors_csv,
)


def _store(tmp_path) -> MarketStore:
    return MarketStore(tmp_path / "sectors.duckdb")


def _seed(store: MarketStore, symbols=("ABC", "XYZ")) -> None:
    store.upsert_securities(
        [{"symbol": s, "name": f"{s} Ltd", "source": "test", "sector": None} for s in symbols]
    )


def _sector_of(store: MarketStore, symbol: str):
    row = store.execute("SELECT sector FROM security_master WHERE symbol = ?", (symbol,)).fetchone()
    return None if row is None else row[0]


def _provenance_of(store: MarketStore, symbol: str):
    row = store.execute(
        "SELECT sector_source, sector_retrieved_at, sector_observed_date "
        "FROM security_master WHERE symbol = ?",
        (symbol,),
    ).fetchone()
    return (
        None
        if row is None
        else {
            "sector_source": row[0],
            "sector_retrieved_at": row[1],
            "sector_observed_date": row[2],
        }
    )


# ------------------------------------------------------------------ parsing


def test_required_columns_are_declared():
    assert REQUIRED_COLUMNS == ("symbol", "sector")


def test_read_refuses_missing_required_column():
    with pytest.raises(SectorError) as exc:
        read_sectors_csv("symbol\nABC\n")
    assert "sector" in str(exc.value)


def test_read_refuses_empty_file():
    with pytest.raises(SectorError):
        read_sectors_csv("")


def test_read_strips_bom_and_whitespace():
    rows = read_sectors_csv("﻿symbol , sector \n ABC , Banking \n")
    assert rows == [{"symbol": "ABC", "sector": "Banking"}]


# ------------------------------------------------------------------ classification


def test_classify_builds_mapping_and_counts():
    rows = read_sectors_csv("symbol,sector\nABC,Banking\nXYZ,Finance\n")
    mapping, report = classify_sectors(rows)
    assert mapping == {"ABC": "Banking", "XYZ": "Finance"}
    assert report["classified"] == 2
    assert report["skipped"] == []


def test_classify_skips_empty_sector_with_reason():
    rows = read_sectors_csv("symbol,sector\nABC,Banking\nDEF,\n")
    mapping, report = classify_sectors(rows)
    assert "DEF" not in mapping
    assert any(s["symbol"] == "DEF" and s["reason"] == "empty sector" for s in report["skipped"])


def test_classify_reports_conflicting_sectors_as_ambiguous_not_a_winner():
    rows = read_sectors_csv("symbol,sector\nABC,Banking\nABC,Technology\n")
    mapping, report = classify_sectors(rows)
    # No winner picked; the symbol is dropped and flagged ambiguous.
    assert "ABC" not in mapping
    assert report["ambiguous"] == ["ABC"]


def test_classify_collapses_identical_duplicates():
    rows = read_sectors_csv("symbol,sector\nABC,Banking\nABC,Banking\n")
    mapping, report = classify_sectors(rows)
    assert mapping == {"ABC": "Banking"}
    assert report["duplicates"] == 1


def test_classify_skips_empty_symbol():
    rows = read_sectors_csv("symbol,sector\n,Banking\n")
    mapping, report = classify_sectors(rows)
    assert mapping == {}
    assert any(s["reason"] == "symbol is empty" for s in report["skipped"])


def test_classify_rejects_lowercase_symbols():
    rows = read_sectors_csv("symbol,sector\nadbl,Banking\n")
    mapping, report = classify_sectors(rows)
    assert "ADBL" not in mapping
    assert any(s["symbol"] == "adbl" and "uppercase" in s["reason"] for s in report["skipped"])


def test_classify_rejects_symbols_with_spaces_or_punctuation():
    rows = read_sectors_csv("symbol,sector\nA DBL,Banking\nADBL!,Banking\n")
    mapping, report = classify_sectors(rows)
    assert mapping == {}
    reasons = " ".join(s["reason"] for s in report["skipped"])
    assert "uppercase letters, digits, hyphens or slashes" in reasons


def test_classify_accepts_bond_symbols_with_hyphens_and_slashes():
    rows = read_sectors_csv("symbol,sector\nNMBD87-88,Debenture\nGBD80/81,Debenture\n")
    mapping, report = classify_sectors(rows)
    assert "NMBD87-88" in mapping
    assert "GBD80/81" in mapping
    assert not any("NMBD87-88" in str(s.get("symbol")) for s in report["skipped"])


# ------------------------------------------------------------------ import


def test_import_assigns_sector_to_existing_symbols(tmp_path):
    store = _store(tmp_path)
    _seed(store, ("ABC", "XYZ"))
    text = "symbol,sector\nABC,Banking\nXYZ,Finance\n"
    report = import_sectors(text, source="unit-test fixture", store=store)
    assert report["assigned"] == 2
    assert report["source"] == "unit-test fixture"
    assert report["unknown_symbols"] == []
    assert _sector_of(store, "ABC") == "Banking"
    assert _sector_of(store, "XYZ") == "Finance"


def test_import_reports_unknown_symbols_and_never_creates_them(tmp_path):
    store = _store(tmp_path)
    _seed(store, ("ABC",))
    text = "symbol,sector\nABC,Banking\nZZZ,Telecom\n"
    report = import_sectors(text, source="unit-test fixture", store=store)
    assert report["assigned"] == 1
    assert "ZZZ" in report["unknown_symbols"]
    # ZZZ must not have been invented into the master.
    assert store.execute("SELECT 1 FROM security_master WHERE symbol = 'ZZZ'").fetchone() is None


def test_import_does_not_clobber_name_or_delisted(tmp_path):
    store = _store(tmp_path)
    store.upsert_securities(
        [{"symbol": "ABC", "name": "Alpha Bank", "source": "test", "delisted": True}]
    )
    import_sectors("symbol,sector\nABC,Banking\n", source="s", store=store)
    row = store.execute(
        "SELECT name, delisted, sector FROM security_master WHERE symbol = 'ABC'"
    ).fetchone()
    name, delisted, sector = row  # DuckDB fetchone() returns a positional tuple
    assert name == "Alpha Bank"
    assert bool(delisted) is True
    assert sector == "Banking"


def test_import_requires_non_blank_source(tmp_path):
    store = _store(tmp_path)
    _seed(store)
    with pytest.raises(SectorError):
        import_sectors("symbol,sector\nABC,Banking\n", source="   ", store=store)


def test_import_refuses_file_with_no_data_rows(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(SectorError):
        import_sectors("symbol,sector\n", source="s", store=store)


def test_import_is_idempotent_for_same_classification(tmp_path):
    store = _store(tmp_path)
    _seed(store, ("ABC",))
    text = "symbol,sector\nABC,Banking\n"
    first = import_sectors(text, source="s", store=store)
    second = import_sectors(text, source="s", store=store)
    assert first["assigned"] == 1 and second["assigned"] == 1
    assert _sector_of(store, "ABC") == "Banking"


# ------------------------------------------------------------------ provenance


def test_import_records_call_level_provenance(tmp_path):
    store = _store(tmp_path)
    _seed(store, ("ABC",))
    observed = date(2026, 10, 15)
    report = import_sectors(
        "symbol,sector\nABC,Banking\n",
        source="owner-csv",
        store=store,
        retrieved_at="2026-10-15T09:30:00+00:00",
        observed_date=observed,
    )
    assert report["source"] == "owner-csv"
    prov = _provenance_of(store, "ABC")
    assert prov["sector_source"] == "owner-csv"
    assert prov["sector_retrieved_at"] == datetime(2026, 10, 15, 9, 30, 0)
    assert prov["sector_observed_date"] == observed


def test_import_records_per_row_provenance(tmp_path):
    store = _store(tmp_path)
    _seed(store, ("ABC", "XYZ"))
    text = (
        "symbol,sector,source,retrieved_at,observed_date\n"
        "ABC,Banking,row-source,2026-10-14T10:00:00Z,2026-10-14\n"
        "XYZ,Finance,other-source,2026-10-13T08:00:00+05:45,2026-10-13\n"
    )
    import_sectors(text, source="fallback", store=store)
    abc = _provenance_of(store, "ABC")
    assert abc["sector_source"] == "row-source"
    assert abc["sector_retrieved_at"] == datetime(2026, 10, 14, 10, 0, 0)
    assert abc["sector_observed_date"] == date(2026, 10, 14)
    xyz = _provenance_of(store, "XYZ")
    assert xyz["sector_source"] == "other-source"
    # +05:45 -> UTC 02:15 on 2026-10-13
    assert xyz["sector_retrieved_at"] == datetime(2026, 10, 13, 2, 15, 0)
    assert xyz["sector_observed_date"] == date(2026, 10, 13)


def test_import_uses_call_level_fallback_when_row_provenance_missing(tmp_path):
    store = _store(tmp_path)
    _seed(store, ("ABC",))
    before = datetime.now(UTC).replace(tzinfo=None)
    import_sectors(
        "symbol,sector\nABC,Banking\n",
        source="fallback-source",
        store=store,
    )
    after = datetime.now(UTC).replace(tzinfo=None)
    prov = _provenance_of(store, "ABC")
    assert prov["sector_source"] == "fallback-source"
    assert prov["sector_observed_date"] is None
    assert prov["sector_retrieved_at"] is not None
    assert before <= prov["sector_retrieved_at"] <= after


def test_import_rejects_malformed_retrieved_at(tmp_path):
    store = _store(tmp_path)
    _seed(store, ("ABC",))
    with pytest.raises(SectorError, match="invalid retrieved_at"):
        import_sectors(
            "symbol,sector,retrieved_at\nABC,Banking,not-a-date\n",
            source="s",
            store=store,
        )


def test_import_rejects_malformed_observed_date(tmp_path):
    store = _store(tmp_path)
    _seed(store, ("ABC",))
    with pytest.raises(SectorError, match="invalid observed_date"):
        import_sectors(
            "symbol,sector,observed_date\nABC,Banking,2026-99-01\n",
            source="s",
            store=store,
        )


def test_import_partial_provenance_update(tmp_path):
    """A re-import updates supplied provenance fields but preserves ones left blank."""
    store = _store(tmp_path)
    _seed(store, ("ABC",))
    import_sectors(
        "symbol,sector,source,observed_date\nABC,Banking,original,2026-10-01\n",
        source="ignored",
        store=store,
    )
    import_sectors(
        "symbol,sector\nABC,Banking\n",
        source="updated-source",
        store=store,
    )
    prov = _provenance_of(store, "ABC")
    assert prov["sector_source"] == "updated-source"
    # observed_date was not resupplied, so the original value survives.
    assert prov["sector_observed_date"] == date(2026, 10, 1)
