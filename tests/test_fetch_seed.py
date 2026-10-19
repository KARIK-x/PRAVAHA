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


# --- the full `fetch` marks the deployment seed complete ---------------------
def _stub_fetch(monkeypatch):
    """Make `megatool fetch` run offline against a dummy adapter."""
    import types

    from megatool import deploy_seed as ds
    from megatool.datasources import nepse_data_repo

    class DummyAdapter:
        def __init__(self, **_k):
            pass

        def list_symbols(self):
            return ["NABIL"]

    monkeypatch.setattr(nepse_data_repo, "NepseDataRepoAdapter", DummyAdapter)
    fake = types.SimpleNamespace(
        source=types.SimpleNamespace(value="github.com/Aabishkar2/nepse-data"),
        ok=True,
        symbols_succeeded=1,
        symbols_requested=1,
        symbols_failed=0,
        rows_read=10,
        rows_inserted=10,
        rows_updated=0,
        rows_flagged=0,
        coverage_start=None,
        coverage_end=None,
        errors=[],
    )
    monkeypatch.setattr("megatool.ingest.ingest", lambda *a, **k: fake)

    from megatool.db import init_app_db, set_setting

    init_app_db()
    set_setting(ds.SEED_MARKER_KEY, "0")
    assert ds.seed_needed() is True
    return ds


def _fetch_args(**kw):
    import argparse

    base = {"symbols": None, "limit": None, "cache_ttl_hours": 12.0, "quiet": True}
    base.update(kw)
    return argparse.Namespace(**base)


def test_full_fetch_marks_the_seed_complete(monkeypatch):
    ds = _stub_fetch(monkeypatch)
    assert cli._cmd_fetch(_fetch_args()) == 0
    assert ds.seed_needed() is False  # a runtime auto-seed will now be skipped


def test_partial_fetch_does_not_mark_the_seed_complete(monkeypatch):
    ds = _stub_fetch(monkeypatch)
    assert cli._cmd_fetch(_fetch_args(symbols="NABIL")) == 0
    assert ds.seed_needed() is True  # a partial fetch must not claim completeness
