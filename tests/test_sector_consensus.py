"""Focused tests for the cross-source sector consensus (BLOCKER 1).

The behaviours pinned here are the ones that make the mapping safe:

* an ordinary share takes a business sector; a non-ordinary instrument never
  does;
* promoter shares, debentures, mutual funds and preference shares are
  classified by instrument, not by the issuer's business sector;
* two sources disagreeing leaves the symbol conflicted, never averaged;
* a symbol no source covers stays unresolved;
* the ranker map contains ordinary shares only.

Synthetic fixtures are used for the rules; the real snapshots are used for the
integration test that proves the rules hold on 649 real records.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from megatool.datasources.sector_consensus import (
    INSTRUMENT_BUCKETS,
    build_consensus,
    canon_sector,
    is_promoter_share_symbol,
    load_binayabaral,
    load_nepalstockdata,
    load_stockmap,
    load_yonepse,
    non_ordinary_with_sector,
    ordinary_only_sector_map,
    sector_map_for_ranker,
)

RAW = Path("data/review/source_probe_2026-10-15")

# ------------------------------------------------------------------- fixtures

YONEPSE_FIXTURE = [
    {  # an ordinary share with a business sector
        "symbol": "NABIL",
        "companyName": "Nabil Bank Limited",
        "status": "A",
        "sectorName": "Commercial Banks",
        "instrumentType": "Equity",
    },
    {  # a bank's debenture: the source still tags it by the issuer's sector
        "symbol": "ADBLB",
        "companyName": "4% Agricultural Bond",
        "status": "A",
        "sectorName": "Commercial Banks",
        "instrumentType": "Non-Convertible Debentures",
    },
]

NSD_FIXTURE = (
    "Commercial_Banks,Corporate_Debentures,Promoter_Share,Mutual_Fund\nNABIL,ADBLB,NABILPO,C30MF\n"
)

STOCKMAP_FIXTURE = {
    "NABIL": {
        "name": "Nabil Bank Limited",
        "sector": "Commercial Banks",
        "internalSector": "Banking Index",
    },
    # same debenture, declared here by issuer sector too
    "ADBLB": {
        "name": "4% Agricultural Bond",
        "sector": "Commercial Banks",
        "internalSector": "Banking Index",
    },
}

BINAYABARAL_FIXTURE = (
    "symbol,name,source_category,instrument_type,sector,status\n"
    "NABIL,Nabil Bank,Bank,ordinary,Commercial Banks,listed\n"
)


# ----------------------------------------------------------------- unit rules


def test_promoter_share_suffix_is_detected():
    assert is_promoter_share_symbol("NABILPO") is True
    assert is_promoter_share_symbol("SLBBLP") is False  # no PO suffix
    assert is_promoter_share_symbol("NABIL") is False
    assert is_promoter_share_symbol("PO") is False  # too short to be real


def test_sector_names_are_normalised_across_source_vocabularies():
    assert canon_sector("Commercial Bank") == "Commercial Banks"
    assert canon_sector("Development Bank Limited") == "Development Banks"
    assert canon_sector("Hotels And Tourism") == "Hotels & Tourism"
    assert canon_sector("") is None
    assert canon_sector(None) is None


def test_ordinary_share_gets_a_business_sector():
    c = build_consensus(
        ["NABIL"],
        yonepse=load_yonepse(YONEPSE_FIXTURE),
        stockmap=load_stockmap(STOCKMAP_FIXTURE),
        binayabaral=load_binayabaral(BINAYABARAL_FIXTURE),
    )
    rec = c["resolved"]["NABIL"]
    assert rec["sector"] == "Commercial Banks"
    assert rec["is_ordinary"] is True
    assert rec["instrument"] == "ordinary"
    assert len(rec["votes"]) >= 2


def test_debenture_never_receives_an_ordinary_company_sector():
    """Both issuer-sector sources call ADBLB 'Commercial Banks'; it is still
    classified by instrument, because it is not an ordinary company."""
    c = build_consensus(
        ["ADBLB"],
        yonepse=load_yonepse(YONEPSE_FIXTURE),
        stockmap=load_stockmap(STOCKMAP_FIXTURE),
    )
    rec = c["resolved"]["ADBLB"]
    assert rec["sector"] is None
    assert rec["is_ordinary"] is False
    assert rec["instrument"] == "debenture"
    assert rec["classification"] == "Corporate Debentures"
    assert rec["classification"] in INSTRUMENT_BUCKETS


def test_promoter_share_is_classified_by_instrument_even_with_a_po_suffix_only():
    """NABILPO appears only in the instrument-bucket source and by suffix."""
    c = build_consensus(["NABILPO"], nepalstockdata=load_nepalstockdata(NSD_FIXTURE))
    rec = c["resolved"]["NABILPO"]
    assert rec["is_ordinary"] is False
    assert rec["instrument"] == "promoter_share"
    assert rec["classification"] == "Promoter Shares"
    assert rec["sector"] is None


def test_conflicting_sources_leave_a_symbol_conflicted_not_averaged():
    yon = load_yonepse([{**YONEPSE_FIXTURE[0], "sectorName": "Commercial Banks"}])
    sm = load_stockmap({"NABIL": {"name": "Nabil", "sector": "Development Banks"}})
    c = build_consensus(["NABIL"], yonepse=yon, stockmap=sm)
    assert "NABIL" in c["conflicted"][0]["symbol"] or c["conflicted"][0]["symbol"] == "NABIL"
    assert set(c["conflicted"][0]["candidates"]) == {"Commercial Banks", "Development Banks"}
    assert "NABIL" not in c["resolved"]


def test_uncovered_symbol_is_reported_unresolved_and_never_guessed():
    c = build_consensus(
        ["TOTALLYUNKNOWN"],
        yonepse=load_yonepse(YONEPSE_FIXTURE),
        stockmap=load_stockmap(STOCKMAP_FIXTURE),
    )
    assert c["unresolved"] == ["TOTALLYUNKNOWN"]
    assert c["resolved"] == {}


def test_ranker_map_excludes_instrument_classified_symbols():
    c = build_consensus(
        ["NABIL", "ADBLB"],
        yonepse=load_yonepse(YONEPSE_FIXTURE),
        nepalstockdata=load_nepalstockdata(NSD_FIXTURE),
    )
    ranker = sector_map_for_ranker(c)
    assert ranker == {"NABIL": "Commercial Banks"}
    assert "ADBLB" not in ranker


# ------------------------------------------------- ordinary-only ranking scope


def test_ordinary_only_map_excludes_mutual_funds_and_debentures():
    """The rule the ranking API applies, pinned against real observed metadata.

    Measured on the real compilations: a bank mutual fund (``NMBSF1``) and a
    bank bond (``NIBD2082``) both carry ``sectorName = "Commercial Banks"``.
    Ranking them inside that sector would compare an instrument with ordinary
    bank shares.
    """
    meta = {
        "NABIL": {"sector": "Commercial Banks", "instrument_type": "ordinary"},
        "NMBSF1": {"sector": "Commercial Banks", "instrument_type": "mutual_fund"},
        "NIBD2082": {"sector": "Commercial Banks", "instrument_type": "debenture"},
        "UNKNOWNKIND": {"sector": "Commercial Banks", "instrument_type": None},
    }
    ranker = ordinary_only_sector_map(meta)
    assert ranker == {"NABIL": "Commercial Banks"}
    excluded = non_ordinary_with_sector(meta)
    assert set(excluded) == {"NMBSF1", "NIBD2082", "UNKNOWNKIND"}
    assert excluded["NMBSF1"] == "mutual_fund"
    assert excluded["UNKNOWNKIND"] == "unspecified"


def test_ordinary_only_map_treats_blank_and_none_instrument_types_the_same():
    meta = {
        "A": {"sector": "Finance", "instrument_type": ""},
        "B": {"sector": "Finance", "instrument_type": None},
    }
    assert ordinary_only_sector_map(meta) == {}


def test_ordinary_only_map_passes_equity_alias_only_when_ordinary():
    """``equity`` alone is not enough: the app's canonical value is ``ordinary``."""
    meta = {"A": {"sector": "Finance", "instrument_type": "equity"}}
    assert ordinary_only_sector_map(meta) == {}


# ------------------------------------------------------------- real snapshots


@pytest.mark.skipif(
    not (RAW / "yonepse_securities.json").exists(), reason="probe files not downloaded"
)
def test_real_snapshots_resolve_without_inventing_a_sector():
    """The documented rule, applied to the four real sources.

    Verified by running it: symbols that no source classifies stay unresolved,
    so the four non-ordinary instrument buckets are honoured rather than
    overridden by an issuer sector.
    """
    yon = load_yonepse(json.loads((RAW / "yonepse_securities.json").read_text()))
    nsd = load_nepalstockdata((RAW / "nepalstockdata_listed_company.csv").read_text())
    sm = load_stockmap(json.loads((RAW / "surajrimal_stockmap.json").read_text()))
    bnr = load_binayabaral((RAW / "binayabaral_symbols.csv").read_text())

    universe = list(yon) + [
        "HEIP",
        "HIDCLP",
        "LBL",
        "NIB",
        "NIMBPO",
        "PLI",
        "PLIC",
        "RBCLPO",
        "RHPC",
        "SLBBLP",
        "SLI",
        "SLICL",
    ]
    c = build_consensus(universe, yonepse=yon, stockmap=sm, binayabaral=bnr, nepalstockdata=nsd)

    stats = c["stats"]
    assert stats["resolved"] == 654
    assert stats["resolved_ordinary"] == 489
    assert stats["resolved_instrument"] == 165
    assert stats["conflicted"] == 0
    assert stats["unresolved"] == 7

    # the seven symbols no source covers are exactly these, and stay unresolved
    assert set(c["unresolved"]) == {"LBL", "NIB", "PLI", "PLIC", "RHPC", "SLI", "SLICL"}

    # the five promoter shares are classified by instrument, not by a sector
    for sym in ("HEIP", "HIDCLP", "NIMBPO", "RBCLPO", "SLBBLP"):
        rec = c["resolved"][sym]
        assert rec["is_ordinary"] is False, sym
        assert rec["sector"] is None, sym
        assert rec["classification"] == "Promoter Shares", sym

    # a real bank debenture is classified by instrument even though three
    # sources call its issuer a Commercial Bank
    adblb = c["resolved"].get("ADBLB")
    if adblb:
        assert adblb["is_ordinary"] is False
        assert adblb["sector"] is None

    ranker = sector_map_for_ranker(c)
    assert len(ranker) == 489
    assert all(sym not in ranker for sym in ("HEIP", "HIDCLP", "NIMBPO", "RBCLPO", "SLBBLP"))
