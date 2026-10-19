"""Collector tests - every network access mocked, every claim checked.

The fixtures mirror the *actual published shapes* of the YONEPSE market files
(sampled from ``data/market/*.json`` on 2026-10-16), so these tests pin the
parser to reality, not to invented schema.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from megatool import collector as col
from megatool.collector import (
    CollectorError,
    business_date_evidence,
    collect_loop,
    collect_snapshot,
    dataset_freshness,
    latest_report,
    validate_history,
    validate_index,
    validate_market_live,
    validate_rankings,
    validate_sector_indices,
    validate_status,
    validate_summary,
)
from megatool.db import get_conn, init_app_db

NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=UTC)


def _iso(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")


# ---------------------------------------------------------------- fixtures
LIVE_FIXTURE = [
    {
        "symbol": "NIMB",
        "name": "Nepal Investment Mega Bank Limited",
        "ltp": 206.2,
        "previous_close": 205.0,
        "change": 1.2,
        "percent_change": 0.59,
        "high": 207.0,
        "low": 204.0,
        "volume": 894286,
        "turnover": 184391_572.0,
        "trades": 1307,
        "last_updated": _iso(5),  # newest stamp in the whole snapshot
    },
    {
        "symbol": "GHL",
        "name": "Ghalemdi Hydro Limited",
        "ltp": 310.9,
        "previous_close": 305.0,
        "change": 5.9,
        "percent_change": 1.93,
        "high": 315.0,
        "low": 304.0,
        "volume": 660_164,
        "turnover": 204_930_344.0,
        "trades": 990,
        "last_updated": _iso(10),
    },
    {
        "symbol": "gHL",  # duplicate after normalisation
        "ltp": 311.0,
        "last_updated": _iso(8),
    },
    {
        "symbol": "SUSP",  # no ltp: flagged, kept
        "last_updated": _iso(12),
    },
]

STATUS_FIXTURE = {"is_open": True, "last_checked": _iso(15)}

INDEX_FIXTURE = [
    {
        "index": "Sensitive Index",
        "close": 475.99,
        "high": 478.3995,
        "low": 475.4719,
        "previousClose": 477.9573,
        "change": 1.97,
        "perChange": 0.41,
        "fiftyTwoWeekHigh": 507.0,
        "fiftyTwoWeekLow": 435.29,
        "generatedTime": _iso(10),
    },
    {
        "index": "NEPSE Index",
        "close": 2625.93,
        "high": 2638.4229,
        "low": 2622.7842,
        "previousClose": 2634.1703,
        "change": 8.23,
        "perChange": 0.31,
        "fiftyTwoWeekHigh": 2960.4,
        "fiftyTwoWeekLow": 2487.18,
        "generatedTime": _iso(10),
    },
]

SUMMARY_FIXTURE = [
    {"detail": "Total Turnover Rs:", "value": 4880089108.16},
    {"detail": "Total Traded Shares", "value": 13376489.0},
    {"detail": "Total Transactions", "value": 39295.0},
    {"detail": "Total Scrips Traded", "value": 348.0},
    {"detail": "Total Market Capitalization Rs:", "value": 4534351688640.2},
    {"detail": "Total Float Market Capitalization Rs:", "value": 1546326109886.4},
    {"detail": "Some New Upstream Metric", "value": 7.0},  # schema drift: kept
]

HISTORY_FIXTURE = [
    {
        "businessDate": "2026-10-16",
        "totalTurnover": 4880089108.16,
        "totalTradedShares": 13376489,
        "totalTransactions": 39295,
        "tradedScrips": 348,
    },
    {
        "businessDate": "2026-10-15",
        "totalTurnover": 4311256437.94,
        "totalTradedShares": 12777797,
        "totalTransactions": 39101,
        "tradedScrips": 333,
    },
]

SECTOR_FIXTURE = [
    {
        "id": 51,
        "indexCode": "BANKSUBIND",
        "indexName": "Banking SubIndex",
        "description": "Index of All the Listed Commercial Banks",
        "sectorMaster": {"id": 37, "sectorDescription": "Commercial Banks"},
        "activeStatus": "A",
        "keyIndexFlag": "N",
    },
    {
        "id": 52,
        "indexCode": "HOTELIND",
        "indexName": "Hotels And Tourism Index",
        "description": "All the companies Listed in Hotels Group",
        "sectorMaster": {"id": 39, "sectorDescription": "Hotels And Tourism"},
        "activeStatus": "A",
        "keyIndexFlag": "N",
    },
]

TOP_FIXTURE = {
    "top_gainer": [
        {
            "symbol": "CKHL",
            "ltp": 581.0,
            "cp": 581.0,
            "pointChange": 75.0,
            "percentageChange": 14.82,
            "securityName": "Chirkhwa Hydropower Limited ",
            "securityId": 9232,
        },
        {
            "symbol": "UPPER",
            "ltp": 100.0,
            "pointChange": 10.0,
            "percentageChange": 10.0,
            "securityName": "Upper",
        },
        {
            "symbol": "NOMETRIC",  # no percentageChange -> rejected
        },
    ],
    "top_loser": [
        {
            "symbol": "SBLD89",
            "ltp": 1370.0,
            "cp": 1370.0,
            "pointChange": -85.0,
            "percentageChange": -5.84,
            "securityName": "10.75% SBL Debenture 2089",
            "securityId": 8098,
        }
    ],
    "top_turnover": [
        {
            "symbol": "GHL",
            "turnover": 204930344.0,
            "closingPrice": 310.9,
            "securityName": "Ghalemdi Hydro Limited",
            "securityId": 2806,
        }
    ],
    "top_trade": [
        {
            "symbol": "NIMB",
            "shareTraded": 894286,
            "closingPrice": 206.2,
            "securityName": "Nepal Investment Mega Bank Limited",
            "securityId": 132,
        }
    ],
    "top_transaction": [
        {
            "securityId": 132,
            "totalTrades": 1307,
            "lastTradedPrice": 206.2,
            "securityName": "Nepal Investment Mega Bank Limited",
            "symbol": "NIMB",
        }
    ],
}


def _patch_upstream(monkeypatch, *, snapshot=None, extras=None, snap_exc=None, extras_exc=None):
    if snap_exc is not None:

        def raise_snap(*a, **k):
            raise snap_exc

        monkeypatch.setattr(col.yonepse, "fetch_market_snapshot", raise_snap)
    else:
        monkeypatch.setattr(col.yonepse, "fetch_market_snapshot", lambda *a, **k: snapshot)

    if extras_exc is not None:

        def raise_extras(*a, **k):
            raise extras_exc

        monkeypatch.setattr(col.yonepse, "fetch_market_extras", raise_extras)
    else:
        monkeypatch.setattr(col.yonepse, "fetch_market_extras", lambda *a, **k: (extras or {}, {}))


@pytest.fixture
def happy_payloads():
    snap = {
        "status": STATUS_FIXTURE,
        "live": LIVE_FIXTURE,
        "indices": INDEX_FIXTURE,
        "origin": "https://raw.githubusercontent.com/shubhamnpk/yonepse/main",
    }
    extras = {
        col.yonepse.PATH_MARKET_SUMMARY: (SUMMARY_FIXTURE, "https://raw/.../summary.json"),
        col.yonepse.PATH_MARKET_HISTORY: (HISTORY_FIXTURE, "https://raw/.../history.json"),
        col.yonepse.PATH_MARKET_SECTOR_INDICES: (
            SECTOR_FIXTURE,
            "https://raw/.../sector_indices.json",
        ),
        col.yonepse.PATH_MARKET_TOP_STOCKS: (TOP_FIXTURE, "https://raw/.../top_stocks.json"),
    }
    return snap, extras


@pytest.fixture
def fresh_db(tmp_path):
    path = tmp_path / "collector_state.sqlite"
    init_app_db(path)
    return path


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    """Freeze the retrieval clock, but make it monotonic.

    A real retrieval clock never repeats, and two cycles of one loop must not
    collide on ``collector_runs.started_at``; the counter emulates microsecond
    progression deterministically.
    """
    counter = {"n": 0}

    def clock():
        counter["n"] += 1
        return NOW + timedelta(microseconds=counter["n"])

    monkeypatch.setattr(col, "_utcnow", clock)


# ---------------------------------------------------------------- happy path
def test_snapshot_happy_path_all_datasets(fresh_db, tmp_path, monkeypatch, happy_payloads):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    out_dir = tmp_path / "snaps"
    report = collect_snapshot(db_path=fresh_db, out_dir=out_dir)

    # 11 dataset records: the mission's ten + history (the cross-check source)
    names = {d["dataset"] for d in report["datasets"]}
    assert names == {
        "market_live",
        "index",
        "summary",
        "status",
        "sector_indices",
        "history",
        "top_gainer",
        "top_loser",
        "top_turnover",
        "top_trade",
        "top_transaction",
    }
    assert report["status"] == "success"
    assert report["datasets_ok"] == 11
    assert report["run_id"] >= 1
    assert report["finished_at"]

    # retrieval clock never respun into an observation stamp
    observed = report["observed_at"]
    assert observed == col.newest_source_stamp(validate_market_live(LIVE_FIXTURE)[0], "observed_at")
    assert report["observed_age_seconds"] == pytest.approx(300.0)
    assert report["freshness"] == "delayed"  # market open, within publish window

    with get_conn(fresh_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM collector_quotes").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM collector_index").fetchone()[0] == 2
        # 7 run-summary metrics + 4 dated metrics x 2 history days = 15
        assert conn.execute("SELECT COUNT(*) FROM collector_summary").fetchone()[0] == 15
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM collector_summary WHERE source_label='history.json'"
            ).fetchone()[0]
            == 8
        )
        assert conn.execute("SELECT COUNT(*) FROM collector_status").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM collector_sector_indices").fetchone()[0] == 2
        for ds in ("top_gainer", "top_loser", "top_turnover", "top_trade", "top_transaction"):
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM collector_rankings WHERE dataset=?", (ds,)
                ).fetchone()[0]
                >= 1
            )
        # history written as dated summary metrics: 4 per business day
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM collector_summary WHERE metric LIKE '2026-10-16%'"
            ).fetchone()[0]
            == 4
        )
        log = conn.execute(
            "SELECT source, status FROM ingestion_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert log["source"] == "collector/yonepse"
        assert log["status"] == "success"

    # JSON bundle written
    assert (out_dir / "latest.json").exists()
    bundled = json.loads((out_dir / "latest.json").read_text())
    assert bundled["status"] == "success"
    assert "market_live" in bundled["rows"]


def test_market_live_rows_persist_honest_values(fresh_db, tmp_path, monkeypatch, happy_payloads):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    report = collect_snapshot(db_path=fresh_db)
    with get_conn(fresh_db) as conn:
        rows = {
            r["symbol"]: dict(r)
            for r in conn.execute(
                "SELECT * FROM collector_quotes WHERE run_id=?", (report["run_id"],)
            ).fetchall()
        }
    assert rows["NIMB"]["ltp"] == 206.2
    assert rows["NIMB"]["turnover"] == 184391_572.0
    assert rows["NIMB"]["observed_at"] == _iso(5)
    assert rows["NIMB"]["validation"] == "valid"
    # duplicate symbol suppression: first occurrence kept
    assert "GHL" in rows and rows["GHL"]["ltp"] == 310.9
    flagged = rows["SUSP"]
    assert flagged["ltp"] is None and "missing_ltp" in flagged["flags"]


def test_index_rows_persist(fresh_db, tmp_path, monkeypatch, happy_payloads):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    collect_snapshot(db_path=fresh_db)
    with get_conn(fresh_db) as conn:
        rows = {r["index_name"]: dict(r) for r in conn.execute("SELECT * FROM collector_index")}
    assert rows["NEPSE Index"]["close"] == 2625.93
    assert rows["NEPSE Index"]["previous_close"] == 2634.1703
    assert rows["NEPSE Index"]["percent_change"] == pytest.approx(0.31)


def test_rankings_rank_and_reject(fresh_db, tmp_path, monkeypatch, happy_payloads):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    collect_snapshot(db_path=fresh_db)
    with get_conn(fresh_db) as conn:
        gainers = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM collector_rankings WHERE dataset='top_gainer' ORDER BY rank"
            )
        ]
        loser = dict(
            conn.execute(
                "SELECT * FROM collector_rankings WHERE dataset='top_loser' LIMIT 1"
            ).fetchone()
        )
    assert [g["rank"] for g in gainers] == [1, 2]
    assert gainers[0]["symbol"] == "CKHL" and gainers[0]["percent_change"] == 14.82
    assert loser["symbol"] == "SBLD89"
    assert loser["percent_change"] == -5.84  # negative is meaningful, never rewritten


def test_summary_metrics_normalised_with_drift_note(
    fresh_db, tmp_path, monkeypatch, happy_payloads
):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    report = collect_snapshot(db_path=fresh_db)
    with get_conn(fresh_db) as conn:
        metrics = {
            r["metric"]: r["value"]
            for r in conn.execute(
                "SELECT * FROM collector_summary WHERE run_id=? AND source_label!='history.json'",
                (report["run_id"],),
            )
        }
    assert metrics["total_turnover"] == 4880089108.16
    assert metrics["total_scrips_traded"] == 348.0
    # the upstream's new label is kept, not dropped
    assert metrics["other"] == 7.0
    drift = next(d for d in report["datasets"] if d["dataset"] == "summary")
    assert "Some New Upstream Metric" in drift["notes"]


def test_status_dataset_persisted(fresh_db, tmp_path, monkeypatch, happy_payloads):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    collect_snapshot(db_path=fresh_db)
    with get_conn(fresh_db) as conn:
        row = dict(conn.execute("SELECT * FROM collector_status LIMIT 1").fetchone())
    assert row["is_open"] == 1
    assert row["last_checked"] == _iso(15)
    assert row["source"] == "upstream"


def test_sector_indices_persisted_with_values_note(fresh_db, tmp_path, monkeypatch, happy_payloads):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    report = collect_snapshot(db_path=fresh_db)
    with get_conn(fresh_db) as conn:
        rows = {
            r["index_code"]: dict(r) for r in conn.execute("SELECT * FROM collector_sector_indices")
        }
    assert rows["BANKSUBIND"]["sector"] == "Commercial Banks"
    ds = next(d for d in report["datasets"] if d["dataset"] == "sector_indices")
    assert "no current index values" in ds["notes"]


def test_business_date_crosscheck_in_report(fresh_db, tmp_path, monkeypatch, happy_payloads):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    report = collect_snapshot(db_path=fresh_db)
    assert report["business_date"] == "2026-10-16"
    assert "turnover" in report["business_date_evidence"]


def test_business_date_crosscheck_mismatch(fresh_db, tmp_path, monkeypatch):
    snap = {"status": STATUS_FIXTURE, "live": LIVE_FIXTURE, "indices": INDEX_FIXTURE, "origin": "x"}
    extras = {
        col.yonepse.PATH_MARKET_SUMMARY: (SUMMARY_FIXTURE, "o"),
        col.yonepse.PATH_MARKET_HISTORY: (HISTORY_FIXTURE[:1], "o"),
        # history matches but transactions differ beyond tolerance -> partial
    }
    bad_hist = [
        {
            "businessDate": "2026-10-16",
            "totalTurnover": 1.0,  # turnover now mismatches
            "totalTradedShares": 2.0,
            "totalTransactions": 3.0,
        },
        {
            "businessDate": "2026-10-15",
            "totalTurnover": 4311256437.94,
            "totalTradedShares": 12777797,
            "totalTransactions": 39101,
        },
    ]
    extras[col.yonepse.PATH_MARKET_HISTORY] = (bad_hist, "o")
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    report = collect_snapshot(db_path=fresh_db)
    assert report["business_date"] is None
    assert "no history row matched" in report["business_date_evidence"]


# ------------------------------------------------------------------- failures
def test_snapshot_partial_when_datasets_unavailable(
    fresh_db, tmp_path, monkeypatch, happy_payloads
):
    snap, _extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras_exc=CollectorError("404 not published"))
    report = collect_snapshot(db_path=fresh_db)
    assert report["status"] == "partial"
    failed = {d["dataset"] for d in report["datasets"] if d["status"] == "source_unavailable"}
    assert failed == {
        "summary",
        "history",
        "sector_indices",
        "top_gainer",
        "top_loser",
        "top_turnover",
        "top_trade",
        "top_transaction",
    }
    with get_conn(fresh_db) as conn:
        # no fabricated ranking/summary rows
        assert conn.execute("SELECT COUNT(*) FROM collector_rankings").fetchone()[0] == 0
        since = conn.execute(
            "SELECT COUNT(*) FROM collector_summary WHERE metric NOT LIKE '2026-10-%'"
        ).fetchone()[0]
        assert since == 0


def test_snapshot_failed_when_everything_unavailable(fresh_db, tmp_path, monkeypatch):
    _patch_upstream(
        monkeypatch,
        snap_exc=CollectorError("network down"),
        extras_exc=CollectorError("network down"),
    )
    report = collect_snapshot(db_path=fresh_db)
    assert report["status"] == "failed"
    assert report["observed_at"] is None
    assert report["observed_age_seconds"] is None
    assert report["freshness"] == "unknown"
    # and everything is observable, not padded
    assert all(d["status"] == "source_unavailable" for d in report["datasets"])
    assert report["rows_inserted"] == 0


def test_malformed_payloads_never_fabricate(fresh_db, tmp_path, monkeypatch):
    snap = {
        "status": {"is_open": "false"},  # wrong type -> degraded, nothing stored
        "live": [["not", "a", "dict"]],  # non-dict rows -> nothing
        "indices": "nonsense",  # wrong shape -> degraded
        "origin": "x",
    }
    extras = {
        col.yonepse.PATH_MARKET_SUMMARY: ({"detail": "not a list"}, "o"),
        col.yonepse.PATH_MARKET_HISTORY: ("nope", "o"),
        col.yonepse.PATH_MARKET_SECTOR_INDICES: (7, "o"),
        col.yonepse.PATH_MARKET_TOP_STOCKS: ({"top_gainer": None}, "o"),
    }
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    report = collect_snapshot(db_path=fresh_db)
    assert report["status"] in ("partial", "failed")
    by = {d["dataset"]: d for d in report["datasets"]}
    assert by["status"]["status"] == "degraded"
    assert by["status"]["counts"]["valid"] == 0
    assert by["market_live"]["counts"]["rejected"] == 0  # non-dict rows simply unread
    assert by["market_live"]["counts"]["read"] == 0
    assert by["summary"]["counts"]["valid"] == 0
    assert by["history"]["counts"]["valid"] == 0
    assert by["sector_indices"]["counts"]["valid"] == 0
    assert by["top_gainer"]["counts"]["valid"] == 0
    with get_conn(fresh_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM collector_status").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM collector_quotes").fetchone()[0] == 0


def test_persistence_rolls_back_entire_run(fresh_db, tmp_path, monkeypatch, happy_payloads):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    real_insert = col._insert_row
    calls = {"n": 0}

    def break_midway(conn, run_id, dataset, row):
        calls["n"] += 1
        if calls["n"] > 5:  # fail after the first few rows are written
            raise CollectorError("simulated persistence failure")
        return real_insert(conn, run_id, dataset, row)

    monkeypatch.setattr(col, "_insert_row", break_midway)
    with pytest.raises(CollectorError):
        collect_snapshot(db_path=fresh_db)
    with get_conn(fresh_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM collector_runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM collector_quotes").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM collector_datasets").fetchone()[0] == 0
        # no ingestion log entry for a rolled-back run
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM ingestion_log WHERE source='collector/yonepse'"
            ).fetchone()[0]
            == 0
        )


# ----------------------------------------------------------------- freshness
def test_freshness_bands_market_open(monkeypatch, fresh_db, tmp_path, happy_payloads):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    report = collect_snapshot(db_path=fresh_db)
    ds = next(d for d in report["datasets"] if d["dataset"] == "market_live")
    assert ds["observed_at"] == _iso(5)
    assert ds["observed_age_seconds"] == pytest.approx(300.0)
    assert ds["freshness"] == "delayed"  # inside the 2x publish window, market open

    assert report["freshness"] == "delayed"


def test_freshness_stale_beyond_publish_window(monkeypatch, fresh_db, tmp_path, happy_payloads):
    old_live = [
        {k: v for k, v in r.items() if k != "last_updated"} | {"last_updated": _iso(300)}
        for r in LIVE_FIXTURE
    ]
    snap = {"status": STATUS_FIXTURE, "live": old_live, "indices": INDEX_FIXTURE, "origin": "x"}
    _patch_upstream(monkeypatch, snapshot=snap, extras=happy_payloads[1])
    report = collect_snapshot(db_path=fresh_db)
    ds = next(d for d in report["datasets"] if d["dataset"] == "market_live")
    assert ds["freshness"] == "stale"  # market open, 5h old >> 90-min window


def test_freshness_last_close_when_market_shut(monkeypatch, fresh_db, tmp_path, happy_payloads):
    shut = {"is_open": False, "last_checked": _iso(20)}
    snap = {"status": shut, "live": LIVE_FIXTURE, "indices": INDEX_FIXTURE, "origin": "x"}
    _patch_upstream(monkeypatch, snapshot=snap, extras=happy_payloads[1])
    report = collect_snapshot(db_path=fresh_db)
    ds = next(d for d in report["datasets"] if d["dataset"] == "market_live")
    assert ds["freshness"] == "last-close"  # expected end-of-day stamp, not "stale"


def test_freshness_historical_and_unknown(monkeypatch, fresh_db, tmp_path, happy_payloads):
    ancient = [
        {k: v for k, v in r.items() if k != "last_updated"} | {"last_updated": _iso(8000)}
        for r in LIVE_FIXTURE
    ]
    snap0, extras = happy_payloads
    snap = {"status": snap0["status"], "live": ancient, "indices": INDEX_FIXTURE, "origin": "x"}
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    report = collect_snapshot(db_path=fresh_db)
    ds = next(d for d in report["datasets"] if d["dataset"] == "market_live")
    assert ds["freshness"] == "historical"
    # rankings have no source stamp -> unknown, never inherited
    top = next(d for d in report["datasets"] if d["dataset"] == "top_gainer")
    assert top["observed_at"] is None
    assert top["freshness"] == "unknown"
    assert "no timestamps" in top["notes"]


def test_dataset_freshness_function():
    retrieved = NOW.isoformat(timespec="seconds")
    age, label = dataset_freshness(_iso(5), retrieved, True)
    assert age == pytest.approx(300.0)
    assert label == "delayed"
    # no stamp -> unknown regardless of anything else
    assert dataset_freshness(None, retrieved, True) == (None, "unknown")
    # garbage stamp -> unknown
    assert dataset_freshness("not-a-timestamp", retrieved, True) == (None, "unknown")


# ------------------------------------------------------------------- loop/CLI
def test_loop_rejects_fast_polling():
    with pytest.raises(CollectorError, match="floor"):
        collect_loop(None, None, interval=10, max_cycles=1)


def test_loop_two_cycles_with_floor_interval(fresh_db, tmp_path, monkeypatch, happy_payloads):
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    slept: list[float] = []
    monkeypatch.setattr(col.time, "sleep", lambda s: slept.append(s))
    reports = collect_loop(fresh_db, tmp_path, interval=60, max_cycles=2)
    assert len(reports) == 2
    assert slept == [60.0]
    with get_conn(fresh_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM collector_runs").fetchone()[0] == 2


def test_latest_report_shape(fresh_db, monkeypatch, happy_payloads):
    assert latest_report(fresh_db) is None
    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    collect_snapshot(db_path=fresh_db)
    report = latest_report(fresh_db)
    assert report is not None
    assert report["status"] == "success"
    assert {d["dataset"] for d in report["datasets"]} >= {"market_live", "status"}
    assert len(report["history"]) == 1


def test_cli_snapshot_and_status(tmp_path, monkeypatch, happy_payloads, capsys):
    import sys

    from megatool import cli

    snap, extras = happy_payloads
    _patch_upstream(monkeypatch, snapshot=snap, extras=extras)
    db = tmp_path / "cli.sqlite"
    out = tmp_path / "out"
    argv = ["megatool", "collector", "snapshot", "--db", str(db), "--out", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    rc = cli.main()
    assert rc == 0
    text = capsys.readouterr().out
    assert "SUCCESS" in text
    assert "market_live" in text
    assert (out / "latest.json").exists()

    argv = ["megatool", "collector", "status", "--db", str(db)]
    monkeypatch.setattr(sys, "argv", argv)
    rc = cli.main()
    assert rc == 0
    assert "recent runs" in capsys.readouterr().out


# --------------------------------------------------------------------- units
def test_validate_market_live_rules():
    rows, counts = validate_market_live(LIVE_FIXTURE)
    syms = {r["symbol"]: r for r in rows}
    assert counts["duplicate"] == 1
    assert "GHL" in syms and syms["GHL"]["turnover"] == 204_930_344.0
    assert syms["SUSP"]["flags"] == "missing_ltp"
    # negative count/turnover reject; negative change is legitimate
    neg, nc = validate_market_live(
        [{"symbol": "NEG", "ltp": 10.0, "turnover": -1.0, "last_updated": _iso(1)}]
    )
    assert nc["rejected"] == 1 and "NEG" not in {r["symbol"] for r in neg}
    down, dc = validate_market_live(
        [{"symbol": "DOWN", "ltp": 90.0, "change": -10.0, "last_updated": _iso(1)}]
    )
    assert dc["valid"] == 1 and down[0]["change"] == -10.0


def test_validate_rankings_rules():
    gainers, counts = validate_rankings("top_gainer", TOP_FIXTURE["top_gainer"])
    assert counts["rejected"] == 1  # the metric-less row
    assert [g["rank"] for g in gainers] == [1, 2]
    assert counts["duplicate"] >= 0
    # a negative defining metric for quantity boards is rejected
    bad, bcounts = validate_rankings("top_trade", [{"symbol": "X", "shareTraded": -5.0}])
    assert bcounts["rejected"] == 1 and bad == []
    # ...but percentage-based boards keep the sign
    keep, kcounts = validate_rankings(
        "top_loser", [{"symbol": "L", "ltp": 100.0, "percentageChange": -9.9}]
    )
    assert kcounts["valid"] == 1 and keep[0]["percent_change"] == -9.9
    # a ranking row without its ltp is flagged, never silently dropped
    flagged, fcounts = validate_rankings("top_loser", [{"symbol": "M", "percentageChange": -3.2}])
    assert fcounts["flagged"] == 1 and flagged[0]["flags"] == "missing_ltp"


def test_validate_summary_rules():
    rows, counts, unknown = validate_summary(SUMMARY_FIXTURE)
    assert counts["valid"] == 7 and counts["read"] == 7
    assert {r["metric"] for r in rows} >= {"total_turnover", "total_float_market_cap"}
    assert unknown == ["Some New Upstream Metric"]
    bad, bcounts, _ = validate_summary(
        [{"detail": "", "value": 1.0}, {"detail": "x", "value": "nan"}]
    )
    assert bcounts["rejected"] == 2 and bad == []


def test_validate_status_rules():
    row, counts, notes = validate_status(dict(STATUS_FIXTURE))
    assert counts["valid"] == 1 and row["is_open"] == 1 and not notes
    nrow, ncounts, nnotes = validate_status({"is_open": "false"})
    assert nrow is None and nnotes and ncounts["rejected"] == 1


def test_validate_index_rules():
    rows, counts = validate_index(INDEX_FIXTURE)
    assert counts["valid"] == 2
    # high < low rejects the row
    bad, bcounts = validate_index([{"index": "BAD", "close": 1.0, "high": 1.0, "low": 9.0}])
    assert bcounts["rejected"] == 1 and bad == []
    # missing close flags but keeps
    flag, fcounts = validate_index([{"index": "NOCLOSE", "high": 2.0, "low": 1.0}])
    assert fcounts["flagged"] == 1 and flag[0]["flags"] == "missing_close"


def test_validate_sector_indices_rules():
    rows, counts = validate_sector_indices(SECTOR_FIXTURE)
    assert counts["valid"] == 2 and rows[0]["index_code"] == "BANKSUBIND"
    bad, bcounts = validate_sector_indices([{"indexCode": "", "indexName": "x"}])
    assert bcounts["rejected"] == 1 and bad == []


def test_validate_history_rules():
    rows, counts = validate_history(HISTORY_FIXTURE)
    assert counts["valid"] == 2 and rows[0]["total_turnover"] == 4880089108.16


def test_business_date_evidence_direct():
    summary = [
        {"metric": "total_turnover", "value": 1000.0},
        {"metric": "total_traded_shares", "value": 100.0},
        {"metric": "total_transactions", "value": 10.0},
    ]
    hist = [
        {
            "business_date": "2026-10-15",
            "total_turnover": 1000.0,
            "total_traded_shares": 100.0,
            "total_transactions": 10.0,
            "traded_scrips": 5.0,
        }
    ]
    day, why = business_date_evidence(summary, hist)
    # the attestation names the history row's session date, not the retrieval day
    assert day == "2026-10-15"
    # empty history -> unchecked
    day2, why2 = business_date_evidence(summary, [])
    assert day2 is None and "cannot cross-check" in why2
    # zero summary turnover -> unchecked
    day3, why3 = business_date_evidence([], hist)
    assert day3 is None and "cannot cross-check" in why3
