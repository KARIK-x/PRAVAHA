"""Tests for the runtime deployment seeder (``megatool.deploy_seed``).

These cover the decision logic and the DB writes. The network fetchers are
monkeypatched, so nothing here touches GitHub. The shared conftest isolates both
databases.
"""

from __future__ import annotations

from megatool import deploy_seed as ds
from megatool.datasources import binayabaral, yonepse
from megatool.market_store import MarketStore

INDEX_CSV = (
    "published_date,open,high,low,close,per_change,traded_quantity,traded_amount,status\n"
    "2026-10-15,2600.0,2630.0,2590.0,2625.93,0.17,,4717028104.35,A\n"
    "2026-10-16,2627.0,2638.0,2622.0,2634.17,0.31,,4880005921.16,A\n"
)

SECURITIES = [
    {"symbol": "NABIL", "sectorName": "Commercial Banks"},
    {"symbol": "CHCL", "sectorName": "Hydropower"},
]


# --------------------------------------------------------------- decision logic
def test_auto_seed_is_off_for_loopback(monkeypatch):
    monkeypatch.delenv(ds.AUTO_SEED_ENV, raising=False)
    for host in ("127.0.0.1", "localhost", "::1", "127.0.0.5"):
        assert ds.auto_seed_enabled(host) is False, host


def test_auto_seed_is_on_for_a_hosted_bind(monkeypatch):
    monkeypatch.delenv(ds.AUTO_SEED_ENV, raising=False)
    assert ds.auto_seed_enabled("0.0.0.0") is True
    assert ds.auto_seed_enabled("10.0.0.5") is True


def test_auto_seed_env_overrides(monkeypatch):
    monkeypatch.setenv(ds.AUTO_SEED_ENV, "0")
    assert ds.auto_seed_enabled("0.0.0.0") is False
    monkeypatch.setenv(ds.AUTO_SEED_ENV, "1")
    assert ds.auto_seed_enabled("127.0.0.1") is True


def test_seed_needed_until_marked():
    assert ds.seed_needed() is True
    ds.mark_seed_complete()
    assert ds.seed_needed() is False


def test_start_background_seed_does_nothing_on_loopback(monkeypatch):
    monkeypatch.delenv(ds.AUTO_SEED_ENV, raising=False)
    with MarketStore() as store:
        assert ds.start_background_seed(store, host="127.0.0.1") is None


def test_start_background_seed_runs_on_a_hosted_bind(monkeypatch):
    monkeypatch.setenv(ds.AUTO_SEED_ENV, "1")
    ran = {}

    def fake_seed_all(store, log=print, limit=None):
        ran["called"] = True
        return {"price_bars": {"succeeded": 3, "rows_inserted": 10}}

    monkeypatch.setattr(ds, "seed_all", fake_seed_all)
    with MarketStore() as store:
        t = ds.start_background_seed(store, host="0.0.0.0")
        assert t is not None
        t.join(timeout=10)
    assert ran.get("called") is True


# ------------------------------------------------------------------- DB writes
def test_seed_index_writes_both_tables(monkeypatch):
    monkeypatch.setattr(binayabaral, "fetch_index_csv", lambda: INDEX_CSV)
    with MarketStore() as store:
        out = ds.seed_index(store)
        assert out["rows_written"] == 2
        assert out["coverage_start"] == "2026-10-15"
        assert len(store.index_closes("NEPSE")) == 2

    from megatool.db import get_conn

    with get_conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM index_ohlc_history WHERE index_name='NEPSE'"
        ).fetchone()[0]
    assert n == 2


def test_seed_sectors_classifies_known_symbols(monkeypatch):
    with MarketStore() as store:
        store.upsert_securities(
            [{"symbol": s, "source": "SYNTHETIC-TEST-FIXTURE"} for s in ("NABIL", "CHCL")]
        )
    monkeypatch.setattr(yonepse, "fetch_securities", lambda: SECURITIES)
    with MarketStore() as store:
        out = ds.seed_sectors(store)
        assert out["classified"] == 2
        rows = store.execute(
            "SELECT symbol, sector FROM security_master WHERE sector IS NOT NULL"
        ).fetchall()
    mapped = {r[0]: r[1] for r in rows}
    assert mapped.get("NABIL") == "Commercial Banks"
    assert mapped.get("CHCL") == "Hydropower"


# ------------------------------------------------------------- error isolation
def test_seed_all_reports_a_failing_step_without_aborting(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("dataset down")

    monkeypatch.setattr(ds, "seed_price_bars", boom)
    monkeypatch.setattr(binayabaral, "fetch_index_csv", lambda: INDEX_CSV)
    monkeypatch.setattr(yonepse, "fetch_securities", lambda: SECURITIES)

    with MarketStore() as store:
        out = ds.seed_all(store, log=lambda *_: None)

    assert "error" in out["price_bars"]
    # The other steps still ran.
    assert out["index"]["rows_written"] == 2
    assert "classified" in out["sectors"]


def test_a_failed_price_step_leaves_the_marker_unset(monkeypatch):
    monkeypatch.setenv(ds.AUTO_SEED_ENV, "1")
    monkeypatch.setattr(
        ds, "seed_all", lambda store, log=print, limit=None: {"price_bars": {"succeeded": 0}}
    )
    with MarketStore() as store:
        t = ds.start_background_seed(store, host="0.0.0.0")
        t.join(timeout=10)
    assert ds.seed_needed() is True  # retried on the next boot
