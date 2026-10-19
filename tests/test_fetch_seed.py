"""Tests for the deployment seed commands: ``megatool fetch-index`` / ``fetch-sectors``.

These populate the two datasets the dashboard needs beyond the per-symbol price
bars: the published NEPSE composite index (``index_series``) and the sector
classifications (``security_master.sector``).

Offline: the network fetchers are monkeypatched with fixture text, so nothing
here touches GitHub. The shared conftest isolates both databases.
"""

from __future__ import annotations

import argparse

import pytest

from megatool import cli
from megatool.datasources import binayabaral, yonepse
from megatool.market_store import MarketStore

# --- fixtures ---------------------------------------------------------------
INDEX_CSV = (
    "published_date,open,high,low,close,per_change,traded_quantity,traded_amount,status\n"
    "2026-10-15,2600.0,2630.0,2590.0,2625.93,0.17,,4717028104.35,A\n"
    "2026-10-16,2627.0,2638.0,2622.0,2634.17,0.31,,4880005921.16,A\n"
    # a row with a blank close must be skipped, never treated as 0
    "2026-10-17,2630.0,2640.0,2625.0,,0.0,,,\n"
    # a non-positive close must be skipped
    "2026-10-18,0,0,0,0,0,,,\n"
)

SECURITIES = [
    {"symbol": "NABIL", "sectorName": "Commercial Banks"},
    {"symbol": "ADBL", "sectorName": "Commercial Banks"},
    {"symbol": "CHCL", "sectorName": "Hydropower"},
    {"symbol": "NOSECTOR", "sectorName": ""},  # dropped: no sector
]


# --- fetch-index ------------------------------------------------------------
def test_fetch_index_writes_the_composite_series(monkeypatch):
    monkeypatch.setattr(binayabaral, "fetch_index_csv", lambda: INDEX_CSV)
    rc = cli._cmd_fetch_index(argparse.Namespace())
    assert rc == 0

    with MarketStore() as store:
        assert store.index_names() == ["NEPSE"]
        closes = store.index_closes("NEPSE")
    # Only the two usable rows survive; the blank and non-positive are skipped.
    assert len(closes) == 2
    assert float(closes["close"].iloc[-1]) == pytest.approx(2634.17)


def test_fetch_index_is_idempotent(monkeypatch):
    monkeypatch.setattr(binayabaral, "fetch_index_csv", lambda: INDEX_CSV)
    assert cli._cmd_fetch_index(argparse.Namespace()) == 0
    assert cli._cmd_fetch_index(argparse.Namespace()) == 0
    with MarketStore() as store:
        assert len(store.index_closes("NEPSE")) == 2  # no duplicate days


def test_fetch_index_reports_a_fetch_failure(monkeypatch):
    def boom():
        raise binayabaral.BinayabaralError("network down")

    monkeypatch.setattr(binayabaral, "fetch_index_csv", boom)
    assert cli._cmd_fetch_index(argparse.Namespace()) == 1


def test_fetch_index_rejects_a_file_with_no_usable_rows(monkeypatch):
    monkeypatch.setattr(binayabaral, "fetch_index_csv", lambda: "published_date,close\n,,\n")
    assert cli._cmd_fetch_index(argparse.Namespace()) == 1


# --- fetch-sectors ----------------------------------------------------------
def test_securities_to_sector_rows_skips_symbols_without_a_sector():
    rows = yonepse.securities_to_sector_rows(SECURITIES)
    assert {r["symbol"] for r in rows} == {"NABIL", "ADBL", "CHCL"}
    assert all(r["sector"] for r in rows)
    assert all(r["source"] == "yonepse/securities.json" for r in rows)


def test_fetch_sectors_classifies_known_symbols(monkeypatch):
    # Seed the security master so the classifier has symbols to assign to.
    # (``upsert_bars`` does not create master rows — ``upsert_securities`` does.)
    with MarketStore() as store:
        store.upsert_securities(
            [{"symbol": s, "source": "SYNTHETIC-TEST-FIXTURE"} for s in ("NABIL", "ADBL", "CHCL")]
        )

    monkeypatch.setattr(yonepse, "fetch_securities", lambda: SECURITIES)
    rc = cli._cmd_fetch_sectors(argparse.Namespace())
    assert rc == 0

    with MarketStore() as store:
        rows = store.execute(
            "SELECT symbol, sector FROM security_master WHERE sector IS NOT NULL"
        ).fetchall()
    mapped = {r[0]: r[1] for r in rows}
    assert mapped.get("NABIL") == "Commercial Banks"
    assert mapped.get("CHCL") == "Hydropower"


def test_fetch_sectors_reports_a_fetch_failure(monkeypatch):
    def boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(yonepse, "fetch_securities", boom)
    assert cli._cmd_fetch_sectors(argparse.Namespace()) == 1


def test_fetch_sectors_rejects_an_empty_snapshot(monkeypatch):
    monkeypatch.setattr(yonepse, "fetch_securities", lambda: [])
    assert cli._cmd_fetch_sectors(argparse.Namespace()) == 1


# --- CLI wiring -------------------------------------------------------------
def test_the_seed_commands_are_registered():
    parser = cli.build_parser()
    assert parser.parse_args(["fetch-index"]).func is cli._cmd_fetch_index
    assert parser.parse_args(["fetch-sectors"]).func is cli._cmd_fetch_sectors
